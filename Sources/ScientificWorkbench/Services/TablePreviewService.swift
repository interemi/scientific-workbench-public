import Darwin
import Foundation

struct TablePreviewPage: Sendable {
  let firstRecord: Int
  let rows: [[String]]
  let widestRecord: Int
  let hasOmittedCellText: Bool
  let ecsvHeader: String?
  let next: TablePreviewService.Cursor?
}

struct TableSynthesisScope: Equatable, Sendable {
  static let maximumCells = 24
  let cursor: TablePreviewService.Cursor
  let rows: ClosedRange<Int>
  let columns: ClosedRange<Int>
}

struct TableRangeEvidence: Sendable {
  struct Cell: Sendable {
    let record: Int
    let column: Int
    let value: String
  }

  let source: String
  let sha256: String
  let cells: [Cell]
}

actor TablePreviewService {
  static let shared = TablePreviewService()
  static let maximumColumns = 16
  private let maximumRows = 80
  private let maximumBytes = 128 * 1024
  private let maximumCellCharacters = 256

  struct Cursor: Equatable, Sendable {
    fileprivate let offset: Int
    fileprivate let record: Int
    fileprivate let version: FileVersion?
    fileprivate let delimiter: UInt8?
    fileprivate let ecsvHeader: String?

    static let first = Cursor(offset: 0, record: 1, version: nil, delimiter: nil, ecsvHeader: nil)
  }

  fileprivate struct FileVersion: Equatable, Sendable {
    let device: dev_t
    let inode: ino_t
    let size: Int
    let modifiedSeconds: Int
    let modifiedNanoseconds: Int

    init(_ file: FileHandle) throws {
      var info = stat()
      guard fstat(file.fileDescriptor, &info) == 0, info.st_mode & S_IFMT == S_IFREG else {
        throw PreviewError.unavailable
      }
      self.init(info)
    }

    init(_ info: stat) {
      device = info.st_dev
      inode = info.st_ino
      size = Int(info.st_size)
      modifiedSeconds = info.st_mtimespec.tv_sec
      modifiedNanoseconds = info.st_mtimespec.tv_nsec
    }
  }

  enum PreviewError: LocalizedError {
    case outsideRun, unavailable, changed, invalidRecord, recordTooLarge, unsupportedECSV

    var errorDescription: String? {
      switch self {
      case .outsideRun: "The table is missing or resolves outside its recorded run folder."
      case .unavailable: "The table could not be read."
      case .changed: "The table changed during preview. Start at the first page to read the current file."
      case .invalidRecord: "A record has unsupported quoting or invalid UTF-8. Use the text sample or review the complete file."
      case .recordTooLarge: "A record exceeds the page byte limit. Use the text sample or review the complete file."
      case .unsupportedECSV: "This ECSV header is outside the preview's supported syntax. Use the text sample to inspect it."
      }
    }
  }

  static func supports(_ artifact: Artifact) -> Bool {
    ["csv", "tsv", "ecsv"].contains(artifact.url.pathExtension.lowercased())
  }

  func load(
    _ artifact: Artifact,
    in job: JobRecord,
    from cursor: Cursor,
    redact: @Sendable (String) -> String
  ) throws -> TablePreviewPage {
    try Task.checkCancellation()
    guard let url = ArtifactInspectionService().previewURL(for: artifact, in: job) else {
      throw PreviewError.outsideRun
    }
    let descriptor = open(url.path, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC)
    guard descriptor >= 0 else { throw PreviewError.unavailable }
    let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
    defer { try? handle.close() }
    let version = try FileVersion(handle)
    guard cursor.version.map({ $0 == version }) ?? true else { throw PreviewError.changed }
    try handle.seek(toOffset: UInt64(cursor.offset))
    let bytes = Array(try handle.read(upToCount: maximumBytes) ?? Data())
    let atEnd = cursor.offset + bytes.count == version.size
    let parsed = try parsePage(bytes, from: cursor, ext: artifact.url.pathExtension.lowercased(),
                               atEnd: atEnd, redact: redact)
    guard try FileVersion(handle) == version else { throw PreviewError.changed }

    var hasOmittedCellText = false
    let rows = redactedRows(parsed.records, redact: redact).map { row in
      row.map { value in
        let prefix = value.prefix(maximumCellCharacters)
        guard prefix.endIndex != value.endIndex else { return value }
        hasOmittedCellText = true
        return String(prefix) + "…"
      }
    }
    let nextOffset = cursor.offset + parsed.bytesConsumed
    let next = nextOffset < version.size
      ? Cursor(offset: nextOffset, record: cursor.record + parsed.records.count, version: version,
               delimiter: parsed.delimiter, ecsvHeader: parsed.ecsvHeader)
      : nil
    return TablePreviewPage(
      firstRecord: cursor.record,
      rows: rows,
      widestRecord: parsed.records.map(\.columns).max() ?? 0,
      hasOmittedCellText: hasOmittedCellText,
      ecsvHeader: parsed.ecsvHeader,
      next: next
    )
  }

  func readEvidence(
    _ artifact: Artifact, in job: JobRecord, scope: TableSynthesisScope, redact: @Sendable (String) -> String
  ) throws -> TableRangeEvidence {
    let cursor = scope.cursor
    let budget = RunFileFingerprint.defaultReadBudget
    guard Self.supports(artifact), scope.rows.lowerBound >= cursor.record, scope.columns.lowerBound >= 1,
          scope.columns.upperBound <= Self.maximumColumns, scope.rows.upperBound - scope.rows.lowerBound < maximumRows,
          scope.rows.count * scope.columns.count <= TableSynthesisScope.maximumCells,
          cursor.offset >= 0, Int64(cursor.offset) < budget else { throw RunEvidenceUnavailable.invalidTableRange }
    let output = try RunOutputEvidence(artifact: artifact, job: job)
    let offset = Int64(cursor.offset)
    let read = RunFileFingerprint.readSample(output.url, maximumBytes: budget,
                                             range: offset..<(offset + Int64(maximumBytes)))
    try Task.checkCancellation()
    guard output.matches(read.fingerprint), let hash = read.fingerprint.sha256, let info = read.information
    else { throw RunEvidenceUnavailable.changedArtifact }
    let version = FileVersion(info)
    guard cursor.version.map({ $0 == version }) ?? true else { throw PreviewError.changed }
    let bytes = Array(read.bytes)
    let parsed = try parsePage(bytes, from: cursor, ext: artifact.url.pathExtension.lowercased(),
                               atEnd: cursor.offset + bytes.count == version.size, redact: redact)
    guard scope.rows.upperBound - cursor.record < parsed.records.count else {
      throw RunEvidenceUnavailable.invalidTableRange
    }
    let rows = redactedRows(parsed.records, redact: redact)
    let cells = scope.rows.flatMap { record in
      let row = rows[record - cursor.record]
      return scope.columns.compactMap { column -> TableRangeEvidence.Cell? in
        guard row.indices.contains(column - 1) else { return nil }
        let value = row[column - 1].trimmingCharacters(in: .whitespacesAndNewlines)
        guard value.utf8.count <= 80, Double(value)?.isFinite == true,
              value.range(of: #"\A[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\z"#,
                          options: .regularExpression) != nil else { return nil }
        return .init(record: record, column: column, value: value)
      }
    }
    guard !cells.isEmpty else { throw RunEvidenceUnavailable.noNumericCells }
    return TableRangeEvidence(source: output.source, sha256: hash, cells: cells)
  }

  private struct ParsedPage {
    let records: [Record]
    let bytesConsumed: Int
    let delimiter: UInt8
    let ecsvHeader: String?
  }

  private func parsePage(
    _ bytes: [UInt8], from cursor: Cursor, ext: String, atEnd: Bool, redact: (String) -> String
  ) throws -> ParsedPage {
    var position = cursor.offset == 0 && bytes.starts(with: [0xEF, 0xBB, 0xBF]) ? 3 : 0
    var delimiter = cursor.delimiter ?? (ext == "tsv" ? 9 : 44)
    var ecsvHeader = cursor.ecsvHeader
    if cursor.offset == 0, ext == "ecsv" {
      let header = try readECSVHeader(bytes, from: &position)
      delimiter = header.delimiter
      ecsvHeader = redact(header.text)
    }

    var records: [Record] = []
    while position < bytes.count, records.count < maximumRows {
      try Task.checkCancellation()
      guard let record = try readRecord(bytes, from: &position, delimiter: delimiter, atEnd: atEnd) else {
        if records.isEmpty { throw PreviewError.recordTooLarge }
        break
      }
      records.append(record)
    }
    return .init(records: records, bytesConsumed: position, delimiter: delimiter, ecsvHeader: ecsvHeader)
  }

  private func redactedRows(_ records: [Record], redact: (String) -> String) -> [[String]] {
    let rawPage = records.map(\.source).joined()
    let redactedRecords = records.map { redact($0.source) }
    let spansRecords = redact(rawPage) != redactedRecords.joined()
    return zip(records, redactedRecords).map { record, redactedRecord in
      spansRecords || record.source != redactedRecord ? ["[REDACTED]"] : record.cells.map(redact)
    }
  }

  private struct Record {
    let source: String
    let cells: [String]
    let columns: Int
  }

  private enum FieldState {
    case start, unquoted, quoted, closingQuote
  }

  private func readRecord(
    _ bytes: [UInt8], from position: inout Int, delimiter: UInt8, atEnd: Bool
  ) throws -> Record? {
    var index = position
    var fieldStart = index
    var state = FieldState.start
    var cells: [String] = []
    var columns = 0

    func finishField(at end: Int) throws {
      columns += 1
      guard columns <= Self.maximumColumns else { return }
      let quoted = state == .closingQuote
      let range = quoted ? (fieldStart + 1)..<(end - 1) : fieldStart..<end
      guard let text = String(bytes: bytes[range], encoding: .utf8) else {
        throw PreviewError.invalidRecord
      }
      cells.append(quoted ? text.replacingOccurrences(of: "\"\"", with: "\"") : text)
    }

    func finishRecord(at end: Int) throws -> Record {
      try finishField(at: index)
      guard let source = String(bytes: bytes[position..<end], encoding: .utf8) else {
        throw PreviewError.invalidRecord
      }
      return Record(source: source, cells: cells, columns: columns)
    }

    while index < bytes.count {
      let byte = bytes[index]
      if state != .quoted {
        if byte == delimiter {
          try finishField(at: index)
          fieldStart = index + 1
          state = .start
          index += 1
          continue
        }
        if byte == 10 || byte == 13 {
          let following = index + 1
          if byte == 13 && following == bytes.count && !atEnd { return nil }
          let end = byte == 13 && following < bytes.count && bytes[following] == 10
            ? following + 1 : following
          let record = try finishRecord(at: end)
          position = end
          return record
        }
      }

      switch (state, byte) {
      case (.start, 34), (.closingQuote, 34): state = .quoted
      case (.quoted, 34): state = .closingQuote
      case (.closingQuote, _), (.unquoted, 34): throw PreviewError.invalidRecord
      case (.start, _): state = .unquoted
      default: break
      }
      index += 1
    }
    guard atEnd else { return nil }
    guard state != .quoted else { throw PreviewError.invalidRecord }
    let record = try finishRecord(at: index)
    position = index
    return record
  }

  private func readECSVHeader(_ bytes: [UInt8], from position: inout Int) throws -> (text: String, delimiter: UInt8) {
    let start = position
    var delimiter: UInt8 = 32
    while position < bytes.count, bytes[position] == 35 {
      guard let end = bytes[position...].firstIndex(of: 10),
            let line = String(bytes: bytes[position..<end], encoding: .utf8) else {
        throw PreviewError.unsupportedECSV
      }
      if position == start, !line.hasPrefix("# %ECSV 1.0") { throw PreviewError.unsupportedECSV }
      if line.hasPrefix("# delimiter:") {
        let value = line.dropFirst("# delimiter:".count).trimmingCharacters(in: .whitespacesAndNewlines)
        switch value {
        case "','", "\",\"": delimiter = 44
        case "' '", "\" \"": delimiter = 32
        default: throw PreviewError.unsupportedECSV
        }
      }
      position = end + 1
    }
    guard position > start, position < bytes.count,
          let text = String(bytes: bytes[start..<position], encoding: .utf8) else {
      throw PreviewError.unsupportedECSV
    }
    return (text, delimiter)
  }
}
