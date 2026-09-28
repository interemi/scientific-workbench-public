import Foundation

enum PhotometricCalibrationError: LocalizedError, Equatable {
  case missingInput(String)
  case directoryUnsupported
  case unreadableInput
  case noDataRows
  case invalidSelection(String)

  var errorDescription: String? {
    switch self {
    case .missingInput(let path):
      return "The standard-star table does not exist: \(path)"
    case .directoryUnsupported:
      return "Choose one standard-star table, not a folder."
    case .unreadableInput:
      return "The calibration table could not be read as UTF-8 text."
    case .noDataRows:
      return "No usable rows were found in the calibration table."
    case .invalidSelection(let message):
      return message
    }
  }
}

struct PhotometricCalibrationService {
  func inspect(path: String) throws -> PhotometricCalibrationReview {
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) else {
      throw PhotometricCalibrationError.missingInput(path)
    }
    guard !isDirectory.boolValue else {
      throw PhotometricCalibrationError.directoryUnsupported
    }
    guard let text = try? String(contentsOfFile: path, encoding: .utf8) else {
      throw PhotometricCalibrationError.unreadableInput
    }

    let lines = text.components(separatedBy: .newlines)
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty && !$0.hasPrefix("#") }
    guard let headerLine = lines.first, lines.count > 1 else {
      throw PhotometricCalibrationError.noDataRows
    }
    let separator = detectedSeparator(in: headerLine)
    let headers = fields(in: headerLine, separator: separator)
    let rows = lines.dropFirst().map { fields(in: $0, separator: separator) }
    guard !headers.isEmpty, !rows.isEmpty else {
      throw PhotometricCalibrationError.noDataRows
    }

    let columns = headers.enumerated().map { index, rawName in
      let name = rawName.isEmpty ? "column_\(index + 1)" : rawName
      let numericCount = rows.reduce(into: 0) { count, row in
        guard index < row.count, finiteNumber(row[index]) != nil else { return }
        count += 1
      }
      return PhotometricCalibrationColumn(
        index: index,
        name: name,
        numericCount: numericCount,
        rowCount: rows.count,
        instrumentalScore: scoreInstrumental(name),
        catalogScore: scoreCatalog(name),
        airmassScore: scoreAirmass(name),
        filterScore: scoreFilter(name),
        uncertaintyScore: scoreUncertainty(name),
        colorScore: scoreColor(name)
      )
    }

    let instrumental = uniqueRecommendation(columns, score: \.instrumentalScore, numeric: true)
    let catalog = uniqueRecommendation(columns, score: \.catalogScore, numeric: true)
    let airmass = uniqueRecommendation(columns, score: \.airmassScore, numeric: true)
    let filter = uniqueRecommendation(columns, score: \.filterScore, numeric: false)
    let uncertainty = uniqueRecommendation(columns, score: \.uncertaintyScore, numeric: true)
    let color = uniqueRecommendation(columns, score: \.colorScore, numeric: true)
    let filterValues = distinctValues(rows: rows, column: filter)

    var findings: [String] = []
    var nextActions: [String] = []
    var status: PhotometricCalibrationStatus = .pass
    for (column, label) in [
      (instrumental, "instrumental magnitude"),
      (catalog, "catalog magnitude"),
      (airmass, "airmass"),
    ] where column == nil {
      status = .warning
      findings.append("The \(label) column is ambiguous or missing.")
      nextActions.append("Select the \(label) column.")
    }
    if filter == nil {
      status = .warning
      findings.append("No unique filter column was detected.")
      nextActions.append("Select a filter column when the table contains multiple passbands.")
    } else if filterValues.count > 1 {
      status = .warning
      findings.append("The table contains multiple filter values.")
      nextActions.append("Choose one filter before fitting a single-band solution.")
    }
    if uncertainty == nil {
      status = .warning
      findings.append("No unique uncertainty column was detected.")
      nextActions.append("Select an offset uncertainty column or continue unweighted.")
    }
    if columns.filter({ $0.numericCount > 0 }).count < 3 {
      status = .blocked
      findings.append("At least three numeric calibration columns are required.")
      nextActions.append("Choose a table with instrumental magnitude, catalog magnitude, and airmass.")
    }

    return PhotometricCalibrationReview(
      inputPath: path,
      separatorLabel: separator.label,
      columns: columns,
      rows: Array(rows),
      status: status,
      findings: unique(findings),
      nextActions: unique(nextActions),
      recommendedInstrumentalColumn: instrumental,
      recommendedCatalogColumn: catalog,
      recommendedAirmassColumn: airmass,
      recommendedFilterColumn: filter,
      recommendedUncertaintyColumn: uncertainty,
      recommendedColorColumn: color,
      filterValues: filterValues
    )
  }

  func filterValues(
    review: PhotometricCalibrationReview,
    filterColumn: Int?
  ) -> [String] {
    distinctValues(rows: review.rows, column: filterColumn)
  }

  func validate(
    review: PhotometricCalibrationReview,
    selection: PhotometricCalibrationSelection
  ) -> PhotometricCalibrationValidation {
    guard let instrumental = selection.instrumentalColumn else {
      return blocked("Select the instrumental magnitude column.")
    }
    guard let catalog = selection.catalogColumn else {
      return blocked("Select the catalog magnitude column.")
    }
    guard let airmass = selection.airmassColumn else {
      return blocked("Select the airmass column.")
    }
    let required = [instrumental, catalog, airmass]
    guard Set(required).count == required.count else {
      return blocked("Instrumental magnitude, catalog magnitude, and airmass must use different columns.")
    }
    guard required.allSatisfy(review.columns.indices.contains) else {
      return blocked("One or more selected columns are outside the table.")
    }
    if let uncertainty = selection.uncertaintyColumn, required.contains(uncertainty) {
      return blocked("Uncertainty must use a separate column.")
    }
    if selection.includeColorTerm {
      guard let color = selection.colorColumn else {
        return blocked("Select a color-index column before including a color term.")
      }
      if required.contains(color) || color == selection.uncertaintyColumn {
        return blocked("Color index must use a separate column.")
      }
    }

    let availableFilters = filterValues(review: review, filterColumn: selection.filterColumn)
    if selection.filterColumn != nil, availableFilters.count > 1,
       selection.filterValue?.isEmpty != false {
      return blocked("Choose one filter value before fitting.")
    }

    var selectedRows = 0
    var usableRows = 0
    var skippedNonfinite = 0
    var nonpositiveUncertainty = 0
    var instrumentalValues: [Double] = []
    var catalogValues: [Double] = []
    var airmassValues: [Double] = []
    var colorValues: [Double] = []

    for row in review.rows where rowMatchesFilter(row, selection: selection) {
      selectedRows += 1
      guard let inst = value(row, at: instrumental),
            let std = value(row, at: catalog),
            let air = value(row, at: airmass) else {
        skippedNonfinite += 1
        continue
      }
      if let uncertaintyColumn = selection.uncertaintyColumn {
        guard let uncertainty = value(row, at: uncertaintyColumn) else {
          skippedNonfinite += 1
          continue
        }
        if uncertainty <= 0 {
          nonpositiveUncertainty += 1
          continue
        }
      }
      if selection.includeColorTerm, let colorColumn = selection.colorColumn {
        guard let color = value(row, at: colorColumn) else {
          skippedNonfinite += 1
          continue
        }
        colorValues.append(color)
      }
      instrumentalValues.append(inst)
      catalogValues.append(std)
      airmassValues.append(air)
      usableRows += 1
    }

    if nonpositiveUncertainty > 0 {
      return blocked("All selected uncertainties must be positive.")
    }
    if usableRows < 3 {
      return blocked(
        "Need at least three finite rows after applying the selected columns and filter.",
        selectedRows: selectedRows,
        usableRows: usableRows,
        skippedRows: skippedNonfinite
      )
    }

    var findings: [String] = []
    var nextActions: [String] = []
    let airRange = range(airmassValues)
    let catalogRange = range(catalogValues)
    let colorRange = range(colorValues)

    if skippedNonfinite > 0 {
      findings.append("\(skippedNonfinite) selected row(s) contain NaN, Inf, or non-numeric required values and will be excluded.")
      nextActions.append("Review excluded standards before trusting the fit.")
    }
    if selection.uncertaintyColumn == nil {
      findings.append("The solution will be unweighted because no uncertainty column is selected.")
      nextActions.append("Select an offset uncertainty column when measurement errors are available.")
    }
    if selection.filterColumn == nil {
      findings.append("No filter column is selected; the table is assumed to contain one passband.")
      nextActions.append("Confirm that all selected standards belong to the same filter.")
    }
    if let airRange {
      if airRange.lowerBound < 0.95 || airRange.upperBound > 5.0 {
        findings.append("Airmass values fall outside the usual approximately 1 to 5 range.")
        nextActions.append("Check airmass units and column selection.")
      }
      if airRange.upperBound - airRange.lowerBound < 0.25 {
        findings.append("Airmass coverage is narrow; extinction may be weakly constrained.")
      }
    }
    if let catalogRange,
       catalogRange.lowerBound < -30 || catalogRange.upperBound > 40 {
      findings.append("Catalog magnitudes are outside a broad plausible range.")
      nextActions.append("Check the catalog magnitude column and units.")
    }
    if usableRows < 5 {
      findings.append("Only a small number of standards will be fitted.")
    }
    if selection.includeColorTerm, let colorRange,
       colorRange.upperBound - colorRange.lowerBound < 0.3 {
      findings.append("Color coverage is narrow; the color term may be unstable.")
    }

    return PhotometricCalibrationValidation(
      status: findings.isEmpty ? .pass : .warning,
      findings: unique(findings),
      nextActions: unique(nextActions),
      selectedRowCount: selectedRows,
      usableRowCount: usableRows,
      skippedNonfiniteRows: skippedNonfinite,
      airmassRange: airRange,
      catalogMagnitudeRange: catalogRange,
      colorRange: colorRange
    )
  }

  func stage(
    review: PhotometricCalibrationReview,
    selection: PhotometricCalibrationSelection,
    runDirectory: String
  ) throws -> PhotometricCalibrationStagedInput {
    let validation = validate(review: review, selection: selection)
    guard validation.canRun,
          let instrumental = selection.instrumentalColumn,
          let catalog = selection.catalogColumn,
          let airmass = selection.airmassColumn else {
      throw PhotometricCalibrationError.invalidSelection(
        validation.findings.first ?? "The calibration column selection is incomplete."
      )
    }

    let inputsURL = URL(fileURLWithPath: runDirectory)
      .appendingPathComponent("inputs", isDirectory: true)
    try FileManager.default.createDirectory(at: inputsURL, withIntermediateDirectories: true)
    let tableURL = inputsURL.appendingPathComponent("selected_photometric_standards.csv")
    let mappingURL = inputsURL.appendingPathComponent("photometric_column_mapping.json")

    var headers = ["inst_mag", "std_mag", "airmass"]
    if selection.filterColumn != nil { headers.append("filter") }
    if selection.includeColorTerm { headers.append("color_index") }
    if selection.uncertaintyColumn != nil { headers.append("offset_err") }

    var outputRows: [[String]] = []
    for row in review.rows where rowMatchesFilter(row, selection: selection) {
      guard let inst = value(row, at: instrumental),
            let std = value(row, at: catalog),
            let air = value(row, at: airmass) else {
        continue
      }
      var output = [render(inst), render(std), render(air)]
      if let filterColumn = selection.filterColumn {
        output.append(row[safe: filterColumn] ?? "")
      }
      if selection.includeColorTerm, let colorColumn = selection.colorColumn,
         let color = value(row, at: colorColumn) {
        output.append(render(color))
      } else if selection.includeColorTerm {
        continue
      }
      if let uncertaintyColumn = selection.uncertaintyColumn,
         let uncertainty = value(row, at: uncertaintyColumn), uncertainty > 0 {
        output.append(render(uncertainty))
      } else if selection.uncertaintyColumn != nil {
        continue
      }
      outputRows.append(output)
    }
    guard outputRows.count >= 3 else {
      throw PhotometricCalibrationError.invalidSelection(
        "Fewer than three rows remained after staging the selected calibration data."
      )
    }

    let csv = ([headers] + outputRows)
      .map { $0.map(csvField).joined(separator: ",") }
      .joined(separator: "\n") + "\n"
    try csv.write(to: tableURL, atomically: true, encoding: .utf8)

    let sourceName = URL(fileURLWithPath: review.inputPath).lastPathComponent
    let mapping: [String: Any] = [
      "source_path": review.inputPath,
      "source_filename": sourceName,
      "staged_path": tableURL.path,
      "instrumental_mag_column": review.columns[instrumental].name,
      "catalog_mag_column": review.columns[catalog].name,
      "airmass_column": review.columns[airmass].name,
      "filter_column": selection.filterColumn.flatMap { review.columns[safe: $0]?.name } ?? NSNull(),
      "filter_value": selection.filterValue ?? NSNull(),
      "uncertainty_column": selection.uncertaintyColumn.flatMap { review.columns[safe: $0]?.name } ?? NSNull(),
      "color_column": selection.colorColumn.flatMap { review.columns[safe: $0]?.name } ?? NSNull(),
      "include_color_term": selection.includeColorTerm,
      "accepted_rows": outputRows.count,
      "skipped_rows": validation.selectedRowCount - outputRows.count,
      "original_modified": false,
      "preflight_findings": validation.findings,
      "next_actions": validation.nextActions,
    ]
    let mappingData = try JSONSerialization.data(
      withJSONObject: mapping,
      options: [.prettyPrinted, .sortedKeys]
    )
    try mappingData.write(to: mappingURL, options: .atomic)

    return PhotometricCalibrationStagedInput(
      tablePath: tableURL.path,
      mappingPath: mappingURL.path,
      acceptedRows: outputRows.count,
      skippedRows: validation.selectedRowCount - outputRows.count,
      includesUncertainty: selection.uncertaintyColumn != nil,
      includesColorTerm: selection.includeColorTerm
    )
  }

  private enum Separator {
    case comma
    case semicolon
    case tab

    var label: String {
      switch self {
      case .comma: return "comma"
      case .semicolon: return "semicolon"
      case .tab: return "tab"
      }
    }
  }

  private func detectedSeparator(in line: String) -> Separator {
    if line.contains("\t") { return .tab }
    if line.contains(";") && !line.contains(",") { return .semicolon }
    return .comma
  }

  private func fields(in line: String, separator: Separator) -> [String] {
    let character: Character = switch separator {
    case .comma: ","
    case .semicolon: ";"
    case .tab: "\t"
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

  private func normalized(_ name: String) -> String {
    name.lowercased()
      .replacingOccurrences(of: "[^a-z0-9]+", with: "_", options: .regularExpression)
      .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
  }

  private func scoreInstrumental(_ name: String) -> Int {
    let key = normalized(name)
    if ["inst_mag", "instrumental_mag", "m_inst", "mag_inst"].contains(key) { return 100 }
    if key.contains("instrumental") && key.contains("mag") { return 90 }
    if key.contains("inst") && key.contains("mag") { return 80 }
    return 0
  }

  private func scoreCatalog(_ name: String) -> Int {
    let key = normalized(name)
    if ["std_mag", "standard_mag", "catalog_mag", "calibrated_mag", "m_std"].contains(key) { return 100 }
    if (key.contains("catalog") || key.contains("standard")) && key.contains("mag") { return 90 }
    if key.contains("std") && key.contains("mag") { return 80 }
    return 0
  }

  private func scoreAirmass(_ name: String) -> Int {
    let key = normalized(name)
    if ["airmass", "air_mass", "secz", "sec_z"].contains(key) { return 100 }
    if key.contains("airmass") { return 90 }
    return 0
  }

  private func scoreFilter(_ name: String) -> Int {
    let key = normalized(name)
    if ["filter", "band", "passband", "filter_name"].contains(key) { return 100 }
    if key.contains("filter") || key.contains("passband") { return 85 }
    return 0
  }

  private func scoreUncertainty(_ name: String) -> Int {
    let key = normalized(name)
    if ["offset_err", "mag_error", "mag_err", "error", "err", "sigma", "uncertainty"].contains(key) { return 100 }
    if key.contains("uncert") || key.contains("error") || key.contains("sigma") || key.hasSuffix("_err") { return 85 }
    return 0
  }

  private func scoreColor(_ name: String) -> Int {
    let key = normalized(name)
    if ["color", "color_index", "b_minus_v", "b_v", "bv", "g_r", "bp_rp"].contains(key) { return 100 }
    if key.contains("color") || key.contains("minus") { return 85 }
    return 0
  }

  private func uniqueRecommendation(
    _ columns: [PhotometricCalibrationColumn],
    score: KeyPath<PhotometricCalibrationColumn, Int>,
    numeric: Bool
  ) -> Int? {
    let ranked = columns
      .filter { (!numeric || $0.numericCount > 0) && $0[keyPath: score] > 0 }
      .sorted {
        if $0[keyPath: score] != $1[keyPath: score] {
          return $0[keyPath: score] > $1[keyPath: score]
        }
        return $0.numericCount > $1.numericCount
      }
    guard let first = ranked.first else { return nil }
    guard ranked.count == 1 || first[keyPath: score] - ranked[1][keyPath: score] >= 15 else {
      return nil
    }
    return first.index
  }

  private func distinctValues(rows: [[String]], column: Int?) -> [String] {
    guard let column else { return [] }
    return Array(
      Set(
        rows.compactMap { row in
          guard let raw = row[safe: column]?.trimmingCharacters(in: .whitespacesAndNewlines),
                !raw.isEmpty else { return nil }
          return raw
        }
      )
    ).sorted { $0.localizedStandardCompare($1) == .orderedAscending }
  }

  private func rowMatchesFilter(
    _ row: [String],
    selection: PhotometricCalibrationSelection
  ) -> Bool {
    guard let filterColumn = selection.filterColumn,
          let filterValue = selection.filterValue,
          !filterValue.isEmpty else {
      return true
    }
    return row[safe: filterColumn]?.trimmingCharacters(in: .whitespacesAndNewlines) == filterValue
  }

  private func finiteNumber(_ raw: String) -> Double? {
    guard let number = Double(raw.trimmingCharacters(in: .whitespacesAndNewlines)),
          number.isFinite else {
      return nil
    }
    return number
  }

  private func value(_ row: [String], at index: Int) -> Double? {
    row[safe: index].flatMap(finiteNumber)
  }

  private func range(_ values: [Double]) -> ClosedRange<Double>? {
    guard let minimum = values.min(), let maximum = values.max() else { return nil }
    return minimum...maximum
  }

  private func blocked(
    _ message: String,
    selectedRows: Int = 0,
    usableRows: Int = 0,
    skippedRows: Int = 0
  ) -> PhotometricCalibrationValidation {
    PhotometricCalibrationValidation(
      status: .blocked,
      findings: [message],
      nextActions: [message],
      selectedRowCount: selectedRows,
      usableRowCount: usableRows,
      skippedNonfiniteRows: skippedRows,
      airmassRange: nil,
      catalogMagnitudeRange: nil,
      colorRange: nil
    )
  }

  private func render(_ value: Double) -> String {
    String(format: "%.12g", locale: Locale(identifier: "en_US_POSIX"), value)
  }

  private func csvField(_ value: String) -> String {
    guard value.contains(",") || value.contains("\"") || value.contains("\n") else {
      return value
    }
    return "\"\(value.replacingOccurrences(of: "\"", with: "\"\""))\""
  }

  private func unique(_ values: [String]) -> [String] {
    var seen = Set<String>()
    return values.filter { seen.insert($0).inserted }
  }
}

private extension Array {
  subscript(safe index: Int) -> Element? {
    indices.contains(index) ? self[index] : nil
  }
}
