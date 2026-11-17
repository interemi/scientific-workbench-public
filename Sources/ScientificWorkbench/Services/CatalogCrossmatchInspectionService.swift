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

    let lines = text.components(separatedBy: .newlines)
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    let isECSV = suffix == "ecsv" || lines.first?.hasPrefix("# %ECSV ") == true
    let contentLines = lines.filter { !$0.hasPrefix("#") }
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
      backendFormat: isECSV ? "ecsv" : separator.label,
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
    let prepared: CatalogCrossmatchPreparedRun
    do {
      prepared = try prepare(left: left, right: right, selection: selection)
    } catch {
      return blocked(error.localizedDescription)
    }

    var findings: [String] = []
    var nextActions: [String] = []
    if left.sampleWasTruncated || right.sampleWasTruncated {
      findings.append("Column checks used a bounded preview; the backend will validate every row before writing output.")
      nextActions.append("Review any backend warning about rows outside the preview.")
    }
    if prepared.radiusArcseconds > 3_600 {
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
    guard left.inputPath != right.inputPath else {
      throw CatalogCrossmatchInspectionError.invalidSelection("Choose two different catalog files.")
    }
    guard let radius = selection.radiusArcseconds, radius.isFinite, radius > 0,
          radius <= CatalogCrossmatchSelection.maximumRadiusArcseconds else {
      throw CatalogCrossmatchInspectionError.invalidSelection(
        "Enter a finite search radius greater than zero and at most 648,000 arcseconds (180 degrees)."
      )
    }
    guard selection.sharedICRSConfirmed else {
      throw CatalogCrossmatchInspectionError.invalidSelection("Confirm that both catalogs use ICRS coordinates.")
    }
    guard let epoch = selection.coordinateEpochJulianYear, epoch.isFinite, epoch > 0 else {
      throw CatalogCrossmatchInspectionError.invalidSelection(
        "Enter the common coordinate epoch as a positive Julian year (for example, 2016.0)."
      )
    }
    guard selection.left.raColumn != selection.left.decColumn || selection.left.raColumn == nil,
          selection.right.raColumn != selection.right.decColumn || selection.right.raColumn == nil else {
      throw CatalogCrossmatchInspectionError.invalidSelection("RA and Dec must use different columns in each catalog.")
    }
    return CatalogCrossmatchPreparedRun(
      leftPath: left.inputPath,
      rightPath: right.inputPath,
      leftFormat: left.backendFormat,
      rightFormat: right.backendFormat,
      leftRA: try mappedColumn(left, index: selection.left.raColumn, unit: selection.left.raUnit, isRA: true, label: "left RA"),
      leftDec: try mappedColumn(left, index: selection.left.decColumn, unit: selection.left.decUnit, isRA: false, label: "left Dec"),
      rightRA: try mappedColumn(right, index: selection.right.raColumn, unit: selection.right.raUnit, isRA: true, label: "right RA"),
      rightDec: try mappedColumn(right, index: selection.right.decColumn, unit: selection.right.decUnit, isRA: false, label: "right Dec"),
      radiusArcseconds: radius,
      coordinateEpochJulianYear: epoch
    )
  }

  private func mappedColumn(
    _ review: CatalogCrossmatchTableReview,
    index: Int?,
    unit: CatalogCrossmatchCoordinateUnit?,
    isRA: Bool,
    label: String
  ) throws -> CatalogCrossmatchMappedColumn {
    guard let index, review.columns.indices.contains(index), let unit else {
      throw CatalogCrossmatchInspectionError.invalidSelection("Select the \(label) column and its unit.")
    }
    let column = review.columns[index]
    guard column.sampledRowCount > 0, column.numericCount == column.sampledRowCount,
          let values = column.finiteRange else {
      throw CatalogCrossmatchInspectionError.invalidSelection(
        "The selected \(label) column contains missing or non-numeric sampled values."
      )
    }
    let tokens = column.name.lowercased().split { !$0.isLetter && !$0.isNumber }
    let unitLabels: [Substring: CatalogCrossmatchCoordinateUnit] = [
      "deg": .degrees, "degree": .degrees, "degrees": .degrees,
      "rad": .radians, "radian": .radians, "radians": .radians,
      "hour": .hours, "hours": .hours, "hourangle": .hours,
    ]
    let labelUnits = tokens.compactMap { unitLabels[$0] }
    if labelUnits.contains(where: { $0 != unit }) {
      throw CatalogCrossmatchInspectionError.invalidSelection(
        "The selected \(label) unit conflicts with the column label \(column.name)."
      )
    }
    if tokens.contains(where: { ["fk4", "fk5", "galactic"].contains($0) }) {
      throw CatalogCrossmatchInspectionError.invalidSelection(
        "The column label \(column.name) indicates a different frame. Convert the catalog to ICRS before matching."
      )
    }
    if !isRA, unit == .hours {
      throw CatalogCrossmatchInspectionError.invalidSelection("Declination must be in degrees or radians.")
    }
    let quarterCircle = unit.fullCircle / 4
    let inRange = isRA
      ? values.lowerBound >= 0 && values.upperBound < unit.fullCircle
      : values.lowerBound >= -quarterCircle && values.upperBound <= quarterCircle
    guard inRange else {
      let rangeLabel: String = switch (isRA, unit) {
      case (true, .degrees): "[0, 360) degrees"
      case (true, .radians): "[0, 2π) radians"
      case (true, .hours): "[0, 24) hours"
      case (false, .radians): "[-π/2, π/2] radians"
      case (false, _): "[-90, 90] degrees"
      }
      throw CatalogCrossmatchInspectionError.invalidSelection("The selected \(label) values must be in \(rangeLabel).")
    }
    return CatalogCrossmatchMappedColumn(name: column.name, unit: unit)
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
