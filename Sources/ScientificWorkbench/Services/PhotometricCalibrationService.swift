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
      let key = normalized(name)
      let tokens = Set(key.split(separator: "_").map(String.init))
      let system = magnitudeSystem(tokens)
      let unit = measurementUnit(key, tokens: tokens, system: system)
      let isOffset = tokens.contains("offset")
      let describesUncertainty = !tokens.isDisjoint(with: ["err", "error", "sigma", "uncert", "uncertainty"])
      let isComponent = !tokens.isDisjoint(with: ["inst", "instrumental", "std", "catalog", "standard"])
      let isWeight = !tokens.isDisjoint(with: ["variance", "ivar", "weight", "weights", "snr"])
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
        colorScore: scoreColor(name),
        declaredUnit: unit,
        declaredMagnitudeSystem: system,
        declaredOffsetUncertaintyUnit: isOffset && describesUncertainty ? magnitudeUnit(from: unit) : nil,
        isIncompatibleUncertainty: isWeight || (isComponent && !isOffset)
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

  func needsInputUnitConfirmation(
    review: PhotometricCalibrationReview,
    selection: PhotometricCalibrationSelection
  ) -> Bool {
    let columns = [selection.instrumentalColumn, selection.catalogColumn, selection.airmassColumn,
                   selection.includeColorTerm ? selection.colorColumn : nil]
    return columns.compactMap { review.column(at: $0) }.contains { $0.declaredUnit == nil }
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
    if let uncertainty = selection.uncertaintyColumn,
       !review.columns.indices.contains(uncertainty) || required.contains(uncertainty) {
      return blocked("Select a separate uncertainty column within the table.")
    }
    if selection.includeColorTerm {
      guard let color = selection.colorColumn else {
        return blocked("Select a color-index column before including a color term.")
      }
      if !review.columns.indices.contains(color) || required.contains(color) || color == selection.uncertaintyColumn {
        return blocked("Select a separate color-index column within the table.")
      }
    }

    let convention: PhotometricCalibrationConvention
    do {
      convention = try validatedConvention(review: review, selection: selection)
    } catch {
      return blocked(error.localizedDescription)
    }

    var selectedRows = 0
    var usableRows = 0
    var skippedNonfinite = 0
    var nonpositiveUncertainty = 0
    var nonpositiveAirmass = 0
    var instrumentalValues: [Double] = []
    var catalogValues: [Double] = []
    var airmassValues: [Double] = []
    var colorValues: [Double] = []

    for row in review.rows where rowMatchesFilter(row, column: selection.filterColumn, passband: convention.passband) {
      selectedRows += 1
      guard let inst = value(row, at: instrumental),
            let std = value(row, at: catalog),
            let air = value(row, at: airmass) else {
        skippedNonfinite += 1
        continue
      }
      if air <= 0 {
        nonpositiveAirmass += 1
        continue
      }
      if let uncertaintyColumn = selection.uncertaintyColumn {
        guard let uncertainty = value(row, at: uncertaintyColumn) else {
          skippedNonfinite += 1
          continue
        }
        if uncertaintyMagnitude(uncertainty, unit: convention.offsetUncertaintyUnit) <= 0 {
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

    if nonpositiveAirmass > 0 {
      return blocked("Airmass must be positive and dimensionless.")
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
      colorRange: colorRange,
      convention: convention
    )
  }

  func stage(
    review: PhotometricCalibrationReview,
    selection: PhotometricCalibrationSelection,
    runDirectory: String
  ) throws -> PhotometricCalibrationStagedInput {
    let validation = validate(review: review, selection: selection)
    guard validation.canRun,
          let convention = validation.convention,
          let instrumental = selection.instrumentalColumn,
          let catalog = selection.catalogColumn,
          let airmass = selection.airmassColumn else {
      throw PhotometricCalibrationError.invalidSelection(
        validation.findings.first ?? "The calibration column selection is incomplete."
      )
    }

    let inputsURL = URL(fileURLWithPath: runDirectory)
      .appendingPathComponent("inputs", isDirectory: true)
    let tableURL = inputsURL.appendingPathComponent("selected_photometric_standards.csv")
    let mappingURL = inputsURL.appendingPathComponent("photometric_column_mapping.json")

    var headers = ["inst_mag", "std_mag", "airmass"]
    if selection.filterColumn != nil { headers.append("filter") }
    if selection.includeColorTerm { headers.append("color_index") }
    if selection.uncertaintyColumn != nil { headers.append("offset_err") }
    headers += ["catalog_magnitude_system", "calibration_passband"]

    var outputRows: [[String]] = []
    for row in review.rows where rowMatchesFilter(row, column: selection.filterColumn, passband: convention.passband) {
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
        output.append(render(uncertaintyMagnitude(uncertainty, unit: convention.offsetUncertaintyUnit)))
      } else if selection.uncertaintyColumn != nil {
        continue
      }
      outputRows.append(output + [convention.magnitudeSystem, convention.passband])
    }
    guard outputRows.count >= 3 else {
      throw PhotometricCalibrationError.invalidSelection(
        "Fewer than three rows remained after staging the selected calibration data."
      )
    }

    let csv = ([headers] + outputRows)
      .map { $0.map(csvField).joined(separator: ",") }
      .joined(separator: "\n") + "\n"
    try FileManager.default.createDirectory(at: inputsURL, withIntermediateDirectories: true)
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
      "filter_value": convention.passband,
      "catalog_magnitude_system": convention.magnitudeSystem,
      "magnitude_unit": "mag",
      "airmass_unit": "dimensionless",
      "color_index_unit": selection.includeColorTerm ? "mag" : NSNull(),
      "uncertainty_column": selection.uncertaintyColumn.flatMap { review.columns[safe: $0]?.name } ?? NSNull(),
      "offset_uncertainty_input_unit": convention.offsetUncertaintyUnit?.rawValue ?? NSNull(),
      "offset_uncertainty_output_unit": convention.offsetUncertaintyUnit == nil ? NSNull() : "mag",
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
    if key.contains("uncert") || key.contains("error") || key.contains("sigma")
      || key.split(separator: "_").contains("err") { return 85 }
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

  private func validatedConvention(
    review: PhotometricCalibrationReview,
    selection: PhotometricCalibrationSelection
  ) throws -> PhotometricCalibrationConvention {
    let magnitudeColumns = [
      (selection.instrumentalColumn, "instrumental magnitude"),
      (selection.catalogColumn, "catalog magnitude"),
      (selection.includeColorTerm ? selection.colorColumn : nil, "color index")
    ]
    for (index, label) in magnitudeColumns {
      if let unit = review.column(at: index)?.declaredUnit, unit != .magnitude(.magnitude) {
        throw PhotometricCalibrationError.invalidSelection("The selected \(label) column must be in magnitudes.")
      }
    }
    if let unit = review.column(at: selection.airmassColumn)?.declaredUnit, unit != .dimensionless {
      throw PhotometricCalibrationError.invalidSelection("Select a dimensionless airmass column.")
    }
    if needsInputUnitConfirmation(review: review, selection: selection), !selection.inputUnitsConfirmed {
      throw PhotometricCalibrationError.invalidSelection("Confirm magnitudes and dimensionless airmass for the unlabeled columns.")
    }
    guard let system = selection.magnitudeSystem else {
      throw PhotometricCalibrationError.invalidSelection("Select the magnitude system of the catalog standards.")
    }
    if let declared = review.column(at: selection.catalogColumn)?.declaredMagnitudeSystem, declared != system {
      throw PhotometricCalibrationError.invalidSelection("The catalog magnitude column declares the \(declared.rawValue) system.")
    }
    let systemName = system == .other
      ? selection.customMagnitudeSystem.trimmingCharacters(in: .whitespacesAndNewlines) : system.rawValue
    guard !systemName.isEmpty else {
      throw PhotometricCalibrationError.invalidSelection("Enter the documented catalog magnitude system.")
    }
    let passband: String
    if let filter = selection.filterColumn {
      guard review.columns.indices.contains(filter) else {
        throw PhotometricCalibrationError.invalidSelection("Select a filter column within the table.")
      }
      let values = filterValues(review: review, filterColumn: filter)
      let selected = selection.filterValue ?? (values.count == 1 ? values.first : nil)
      guard let selected, values.contains(selected) else {
        throw PhotometricCalibrationError.invalidSelection("Choose one filter value before fitting.")
      }
      passband = selected
    } else {
      passband = selection.singlePassband.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !passband.isEmpty else {
        throw PhotometricCalibrationError.invalidSelection("Enter the single passband represented by the selected standards.")
      }
    }
    let uncertainty = review.column(at: selection.uncertaintyColumn)
    if let uncertainty {
      if uncertainty.isIncompatibleUncertainty {
        throw PhotometricCalibrationError.invalidSelection("Select the uncertainty of the magnitude offset, or fit without weights.")
      }
      guard let unit = selection.offsetUncertaintyUnit else {
        throw PhotometricCalibrationError.invalidSelection("Confirm the offset uncertainty in mag or mmag.")
      }
      if let declared = uncertainty.declaredUnit, declared != .magnitude(unit) {
        throw PhotometricCalibrationError.invalidSelection("The declared uncertainty unit conflicts with the selected mag or mmag unit.")
      }
    }
    return PhotometricCalibrationConvention(
      magnitudeSystem: systemName, passband: passband,
      offsetUncertaintyUnit: uncertainty == nil ? nil : selection.offsetUncertaintyUnit
    )
  }

  private func magnitudeSystem(_ tokens: Set<String>) -> PhotometricMagnitudeSystem? {
    guard !tokens.isDisjoint(with: ["mag", "mags", "magnitude", "magnitudes", "abmag", "vegamag", "stmag"])
    else { return nil }
    let declarations: [(PhotometricMagnitudeSystem, Set<String>)] = [
      (.ab, ["ab", "abmag"]), (.vega, ["vega", "vegamag"]), (.st, ["st", "stmag"])
    ]
    let detected = declarations.filter { !tokens.isDisjoint(with: $0.1) }
    return detected.count == 1 ? detected.first?.0 : nil
  }

  private func measurementUnit(
    _ key: String, tokens: Set<String>, system: PhotometricMagnitudeSystem?
  ) -> PhotometricColumnUnit? {
    if !tokens.isDisjoint(with: [
      "jy", "mjy", "ujy", "njy", "adu", "counts", "electrons", "deg", "degree", "degrees",
      "rad", "radian", "radians", "percent", "pct", "snr", "variance", "ivar"
    ]) {
      return .incompatible
    }
    if !tokens.isDisjoint(with: ["mmag", "mmags", "millimagnitude", "millimagnitudes"]) {
      return .magnitude(.millimagnitude)
    }
    if system != nil || !tokens.isDisjoint(with: ["mag", "mags", "magnitude", "magnitudes"])
      || ["m_inst", "m_std", "b_minus_v", "b_v", "bv", "g_r", "bp_rp"].contains(key) {
      return .magnitude(.magnitude)
    }
    if !tokens.isDisjoint(with: ["airmass", "secz", "dimensionless"]) || ["air_mass", "sec_z"].contains(key) {
      return .dimensionless
    }
    return tokens.contains("flux") ? .incompatible : nil
  }

  private func magnitudeUnit(from declaration: PhotometricColumnUnit?) -> PhotometricMagnitudeUnit? {
    guard case let .magnitude(unit)? = declaration else { return nil }
    return unit
  }

  private func uncertaintyMagnitude(_ value: Double, unit: PhotometricMagnitudeUnit?) -> Double {
    unit == .millimagnitude ? value / 1_000 : value
  }

  private func rowMatchesFilter(_ row: [String], column: Int?, passband: String) -> Bool {
    guard let column else { return true }
    return row[safe: column]?.trimmingCharacters(in: .whitespacesAndNewlines) == passband
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
