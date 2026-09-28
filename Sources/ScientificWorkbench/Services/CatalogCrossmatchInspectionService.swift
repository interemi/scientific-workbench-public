import Foundation

enum CatalogCrossmatchInspectionError: LocalizedError, Equatable {
  case missingInput(String)
  case directoryUnsupported
  case unsupportedFormat(String)
  case unreadableInput
  case noDataRows
  case duplicateColumnNames([String])
  case invalidSelection(String)

  var errorDescription: String? {
    switch self {
    case .missingInput(let path):
      return "The catalog does not exist: \(path)"
    case .directoryUnsupported:
      return "Choose catalog files, not folders."
    case .unsupportedFormat(let suffix):
      return "The guided column review supports CSV, TSV, ECSV, and delimited text. Convert \(suffix.isEmpty ? "this table" : suffix) to one of those formats or use the expert CLI after reviewing its columns."
    case .unreadableInput:
      return "The catalog could not be read as UTF-8 text."
    case .noDataRows:
      return "The catalog needs a header and at least one data row."
    case .duplicateColumnNames(let names):
      return "Catalog column names must be unique. Duplicates: \(names.joined(separator: ", "))."
    case .invalidSelection(let message):
      return message
    }
  }
}

struct CatalogCrossmatchInspectionService {
  private let maximumPreviewBytes = 1_048_576

  func inspect(path: String) throws -> CatalogCrossmatchTableReview {
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) else {
      throw CatalogCrossmatchInspectionError.missingInput(path)
    }
    guard !isDirectory.boolValue else {
      throw CatalogCrossmatchInspectionError.directoryUnsupported
    }

    let url = URL(fileURLWithPath: path)
    let suffix = url.pathExtension.lowercased()
    let supported = ["csv", "tsv", "tab", "ecsv", "txt", "text", "dat", "ascii"]
    guard supported.contains(suffix) else {
      throw CatalogCrossmatchInspectionError.unsupportedFormat(suffix)
    }

    let fileHandle: FileHandle
    do {
      fileHandle = try FileHandle(forReadingFrom: url)
    } catch {
      throw CatalogCrossmatchInspectionError.unreadableInput
    }
    defer { try? fileHandle.close() }

    let data: Data
    do {
      data = try fileHandle.read(upToCount: maximumPreviewBytes + 1) ?? Data()
    } catch {
      throw CatalogCrossmatchInspectionError.unreadableInput
    }
    let wasTruncated = data.count > maximumPreviewBytes
    let previewData = Data(data.prefix(maximumPreviewBytes))
    guard var text = String(data: previewData, encoding: .utf8) else {
      throw CatalogCrossmatchInspectionError.unreadableInput
    }
    if wasTruncated, let lastNewline = text.lastIndex(of: "\n") {
      text = String(text[...lastNewline])
    }

    let contentLines = text.components(separatedBy: .newlines)
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty && !$0.hasPrefix("#") }
    guard contentLines.count >= 2 else {
      throw CatalogCrossmatchInspectionError.noDataRows
    }

    let separator = detectedSeparator(in: contentLines[0], suffix: suffix)
    let header = fields(in: contentLines[0], separator: separator)
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
    let rows = contentLines.dropFirst().map { fields(in: $0, separator: separator) }
    guard !header.isEmpty, !rows.isEmpty else {
      throw CatalogCrossmatchInspectionError.noDataRows
    }

    let duplicateNames = Dictionary(grouping: header, by: { $0 })
      .filter { !$0.key.isEmpty && $0.value.count > 1 }
      .map(\.key)
      .sorted()
    guard duplicateNames.isEmpty else {
      throw CatalogCrossmatchInspectionError.duplicateColumnNames(duplicateNames)
    }

    let columns = header.enumerated().map { index, rawName in
      let name = rawName.isEmpty ? "column_\(index + 1)" : rawName
      let values = rows.compactMap { row -> Double? in
        guard index < row.count else { return nil }
        return finiteNumber(row[index])
      }
      return CatalogCrossmatchColumn(
        index: index,
        name: name,
        numericCount: values.count,
        sampledRowCount: rows.count,
        finiteRange: range(values)
      )
    }

    return CatalogCrossmatchTableReview(
      inputPath: path,
      formatLabel: separator.label,
      columns: columns,
      sampledRowCount: rows.count,
      sampleWasTruncated: wasTruncated
    )
  }

  func validate(
    left: CatalogCrossmatchTableReview,
    right: CatalogCrossmatchTableReview,
    selection: CatalogCrossmatchSelection
  ) -> CatalogCrossmatchValidation {
    guard left.inputPath != right.inputPath else {
      return blocked("Choose two different catalog files.")
    }
    guard selection.radiusArcseconds.isFinite, selection.radiusArcseconds > 0 else {
      return blocked("The search radius must be finite and greater than zero arcseconds.")
    }
    guard selection.coordinateUnitsConfirmed else {
      return blocked("Confirm that all four coordinate columns contain decimal degrees.")
    }
    guard let leftRA = selection.leftRAColumn else {
      return blocked("Select the left-catalog RA column.")
    }
    guard let leftDec = selection.leftDecColumn else {
      return blocked("Select the left-catalog Dec column.")
    }
    guard let rightRA = selection.rightRAColumn else {
      return blocked("Select the right-catalog RA column.")
    }
    guard let rightDec = selection.rightDecColumn else {
      return blocked("Select the right-catalog Dec column.")
    }
    guard leftRA != leftDec, rightRA != rightDec else {
      return blocked("RA and Dec must use different columns in each catalog.")
    }

    let selected = [
      (left, leftRA, true, "left RA"),
      (left, leftDec, false, "left Dec"),
      (right, rightRA, true, "right RA"),
      (right, rightDec, false, "right Dec"),
    ]
    for (review, index, isRA, label) in selected {
      guard review.columns.indices.contains(index) else {
        return blocked("The selected \(label) column is outside the table.")
      }
      let column = review.columns[index]
      guard column.sampledRowCount > 0,
            column.numericCount == column.sampledRowCount,
            let values = column.finiteRange else {
        return blocked("The selected \(label) column contains missing or non-numeric sampled values.")
      }
      if isRA, values.lowerBound < 0 || values.upperBound >= 360 {
        return blocked("The selected \(label) values must be in [0, 360) degrees.")
      }
      if !isRA, values.lowerBound < -90 || values.upperBound > 90 {
        return blocked("The selected \(label) values must be in [-90, 90] degrees.")
      }
    }

    var findings: [String] = []
    var nextActions: [String] = []
    if left.sampleWasTruncated || right.sampleWasTruncated {
      findings.append("Column checks used a bounded preview; the backend will validate every row before writing output.")
      nextActions.append("Review any backend warning about rows outside the preview.")
    }
    if selection.radiusArcseconds > 3_600 {
      findings.append("The search radius is larger than one degree.")
      nextActions.append("Confirm that the unusually large sky radius is intentional.")
    }
    return CatalogCrossmatchValidation(
      status: findings.isEmpty ? .pass : .warning,
      findings: findings,
      nextActions: nextActions
    )
  }

  func prepare(
    left: CatalogCrossmatchTableReview,
    right: CatalogCrossmatchTableReview,
    selection: CatalogCrossmatchSelection
  ) throws -> CatalogCrossmatchPreparedRun {
    let validation = validate(left: left, right: right, selection: selection)
    guard validation.canRun,
          let leftRA = selection.leftRAColumn,
          let leftDec = selection.leftDecColumn,
          let rightRA = selection.rightRAColumn,
          let rightDec = selection.rightDecColumn else {
      throw CatalogCrossmatchInspectionError.invalidSelection(
        validation.findings.first ?? "The catalog column selection is incomplete."
      )
    }
    return CatalogCrossmatchPreparedRun(
      leftPath: left.inputPath,
      rightPath: right.inputPath,
      leftRAColumn: left.columns[leftRA].name,
      leftDecColumn: left.columns[leftDec].name,
      rightRAColumn: right.columns[rightRA].name,
      rightDecColumn: right.columns[rightDec].name,
      radiusArcseconds: selection.radiusArcseconds
    )
  }

  private enum Separator: Equatable {
    case comma
    case semicolon
    case tab
    case whitespace

    var label: String {
      switch self {
      case .comma: return "comma"
      case .semicolon: return "semicolon"
      case .tab: return "tab"
      case .whitespace: return "whitespace"
      }
    }
  }

  private func detectedSeparator(in line: String, suffix: String) -> Separator {
    if line.contains("\t") || ["tsv", "tab"].contains(suffix) { return .tab }
    if line.contains(";") && !line.contains(",") { return .semicolon }
    if line.contains(",") || suffix == "csv" { return .comma }
    return .whitespace
  }

  private func fields(in line: String, separator: Separator) -> [String] {
    if separator == .whitespace {
      return line.split(whereSeparator: \.isWhitespace).map(String.init)
    }
    let character: Character = switch separator {
    case .comma: ","
    case .semicolon: ";"
    case .tab: "\t"
    case .whitespace: " "
    }
    var values: [String] = []
    var current = ""
    var quoted = false
    var index = line.startIndex
    while index < line.endIndex {
      let value = line[index]
      if value == "\"" {
        let next = line.index(after: index)
        if quoted, next < line.endIndex, line[next] == "\"" {
          current.append("\"")
          index = next
        } else {
          quoted.toggle()
        }
      } else if value == character, !quoted {
        values.append(current.trimmingCharacters(in: .whitespaces))
        current = ""
      } else {
        current.append(value)
      }
      index = line.index(after: index)
    }
    values.append(current.trimmingCharacters(in: .whitespaces))
    return values
  }

  private func finiteNumber(_ value: String) -> Double? {
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let number = Double(normalized), number.isFinite else { return nil }
    return number
  }

  private func range(_ values: [Double]) -> ClosedRange<Double>? {
    guard let minimum = values.min(), let maximum = values.max() else { return nil }
    return minimum...maximum
  }

  private func blocked(_ message: String) -> CatalogCrossmatchValidation {
    CatalogCrossmatchValidation(
      status: .blocked,
      findings: [message],
      nextActions: []
    )
  }
}
