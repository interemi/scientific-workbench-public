import Foundation

enum RadialVelocityInspectionError: LocalizedError, Equatable {
  case missingInput(String)
  case directoryUnsupported
  case unreadableInput
  case noDataRows
  case invalidSelection(String)

  var errorDescription: String? {
    switch self {
    case .missingInput(let path):
      return "The radial-velocity table does not exist: \(path)"
    case .directoryUnsupported:
      return "Choose one RV table, not a folder."
    case .unreadableInput:
      return "The RV table could not be read as UTF-8 text."
    case .noDataRows:
      return "No usable tabular rows were found."
    case .invalidSelection(let message):
      return message
    }
  }
}

struct RadialVelocityInspectionService {
  func inspect(path: String) throws -> RadialVelocityTableReview {
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) else {
      throw RadialVelocityInspectionError.missingInput(path)
    }
    guard !isDirectory.boolValue else {
      throw RadialVelocityInspectionError.directoryUnsupported
    }
    guard let text = try? String(contentsOfFile: path, encoding: .utf8) else {
      throw RadialVelocityInspectionError.unreadableInput
    }

    let lines = text.components(separatedBy: .newlines)
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    let contentLines = lines.filter { !$0.hasPrefix("#") }
    guard let firstLine = contentLines.first else {
      throw RadialVelocityInspectionError.noDataRows
    }

    let separator = detectedSeparator(in: firstLine)
    let firstFields = fields(in: firstLine, separator: separator)
    let hasNamedColumn = firstFields.contains { scoreTime($0) > 0 || scoreVelocity($0) > 0 }
    let hasHeader = hasNamedColumn || firstFields.allSatisfy { Double($0) == nil }
    let metadata = commentMetadata(lines)
    let positionalTime = nameTokens(metadata["time_standard"] ?? "")
    let scaleFromTime = timeScale(positionalTime)
    let scaleFromComment = timeScale(nameTokens(metadata["time_scale"] ?? ""))
    if !hasHeader, let scaleFromTime, let scaleFromComment, scaleFromTime != scaleFromComment {
      throw RadialVelocityInspectionError.invalidSelection("The time standard and time scale comments disagree.")
    }
    let positionalScale = scaleFromComment ?? scaleFromTime
    let positionalUnits = [
      1: velocityUnit(nameTokens(metadata["value_units"] ?? "")),
      2: velocityUnit(nameTokens(metadata["uncertainty_units"] ?? ""))
    ].compactMapValues { $0 }
    let dataLines = hasHeader ? Array(contentLines.dropFirst()) : contentLines
    let parsedRows = dataLines.map { fields(in: $0, separator: separator) }
    let columnCount = max(firstFields.count, parsedRows.map(\.count).max() ?? 0)
    guard columnCount > 0, !parsedRows.isEmpty else {
      throw RadialVelocityInspectionError.noDataRows
    }

    let names = hasHeader
      ? normalizedHeaders(firstFields, count: columnCount)
      : (0..<columnCount).map { "column_\($0 + 1)" }
    let columns = names.enumerated().map { index, name in
      let tokens = nameTokens(name)
      let isPositionalTime = !hasHeader && index == 0
      let numericCount = parsedRows.reduce(into: 0) { count, row in
        guard index < row.count, finiteNumber(row[index]) != nil else { return }
        count += 1
      }
      let positionalScores = hasHeader ? (0, 0, 0) : (
        index == 0 ? 100 : 0,
        index == 1 ? 100 : 0,
        index == 2 ? 100 : 0
      )
      return RadialVelocityColumn(
        index: index,
        name: name,
        numericCount: numericCount,
        rowCount: parsedRows.count,
        timeScore: hasHeader ? scoreTime(name) : positionalScores.0,
        velocityScore: hasHeader ? scoreVelocity(name) : positionalScores.1,
        uncertaintyScore: hasHeader ? scoreUncertainty(name) : positionalScores.2,
        declaredTimeSystem: timeSystem(tokens) ?? (isPositionalTime ? timeSystem(positionalTime) : nil),
        declaredTimeScale: timeScale(tokens) ?? (isPositionalTime ? positionalScale : nil),
        declaredVelocityUnit: velocityUnit(tokens) ?? (hasHeader ? nil : positionalUnits[index]),
        usesOffsetTime: usesOffsetTime(tokens) || (isPositionalTime && usesOffsetTime(positionalTime))
      )
    }

    let recommendedTime = uniqueRecommendation(columns, score: \.timeScore)
    let recommendedVelocity = uniqueRecommendation(columns, score: \.velocityScore)
    let recommendedUncertainty = uniqueRecommendation(columns, score: \.uncertaintyScore)
    let inferredTimeSystem = recommendedTime.flatMap { columns[safe: $0]?.declaredTimeSystem }
    let inferredVelocityUnit = recommendedVelocity.flatMap { columns[safe: $0]?.declaredVelocityUnit }

    var findings: [String] = []
    var nextActions: [String] = []
    let numericColumns = columns.filter { $0.numericCount > 0 }
    var status: RadialVelocityReviewStatus = .pass

    if columnCount < 2 || numericColumns.count < 2 {
      status = .blocked
      findings.append("At least two numeric columns are required for time and radial velocity.")
      nextActions.append("Choose a table with numeric time and radial-velocity columns.")
    } else {
      if recommendedTime == nil {
        status = .warning
        findings.append("The time column is ambiguous.")
        nextActions.append("Select the time column and confirm JD, BJD, HJD, or MJD.")
      }
      if recommendedVelocity == nil {
        status = .warning
        findings.append("The radial-velocity column is ambiguous.")
        nextActions.append("Select the radial-velocity column.")
      }
      if recommendedUncertainty == nil {
        status = .warning
        findings.append("No unique uncertainty column was detected.")
        nextActions.append("Select an uncertainty column or continue without uncertainties.")
      }
      if inferredVelocityUnit == nil {
        status = .warning
        findings.append("Velocity units could not be inferred from the column name.")
        nextActions.append("Confirm whether the selected velocity is in km/s or m/s.")
      }
      if !hasHeader {
        status = .warning
        findings.append("Columns were inferred positionally because the table has no header.")
        nextActions.append("Review the positional column mapping before running.")
      }
    }

    return RadialVelocityTableReview(
      inputPath: path,
      separatorLabel: separator.label,
      columns: columns,
      rows: parsedRows,
      status: status,
      findings: findings,
      nextActions: nextActions,
      recommendedTimeColumn: recommendedTime,
      recommendedVelocityColumn: recommendedVelocity,
      recommendedUncertaintyColumn: recommendedUncertainty,
      inferredTimeSystem: inferredTimeSystem,
      inferredVelocityUnit: inferredVelocityUnit,
      usedPositionalColumns: !hasHeader
    )
  }

  func validate(
    review: RadialVelocityTableReview,
    selection: RadialVelocitySelection
  ) -> RadialVelocitySelectionValidation {
    var findings: [String] = []
    var nextActions: [String] = []
    guard let timeColumn = selection.timeColumn else {
      return blocked("Select a time column.", findings: findings, nextActions: nextActions)
    }
    guard let velocityColumn = selection.velocityColumn else {
      return blocked("Select a radial-velocity column.", findings: findings, nextActions: nextActions)
    }
    guard timeColumn != velocityColumn else {
      return blocked("Time and radial velocity must use different columns.", findings: findings, nextActions: nextActions)
    }
    if let uncertaintyColumn = selection.uncertaintyColumn,
       uncertaintyColumn == timeColumn || uncertaintyColumn == velocityColumn {
      return blocked("Uncertainty must use a separate column.", findings: findings, nextActions: nextActions)
    }
    guard let time = review.column(at: timeColumn), let velocity = review.column(at: velocityColumn) else {
      return blocked("The selected columns are outside the table.", findings: findings, nextActions: nextActions)
    }
    guard time.numericCount == time.rowCount else {
      let invalidRows = time.rowCount - time.numericCount
      return blocked("The selected time column has \(invalidRows) missing, nonnumeric, or nonfinite rows.",
                     findings: findings, nextActions: nextActions)
    }
    guard velocity.numericCount > 0 else {
      return blocked("The selected RV column has no finite numeric values.", findings: findings, nextActions: nextActions)
    }
    guard !time.usesOffsetTime else {
      return blocked("The selected column declares offset dates. Provide full JD, BJD, HJD, or MJD values in a reviewed copy.",
                     findings: findings, nextActions: nextActions)
    }
    guard let timeSystem = selection.timeSystem else {
      return blocked("Select the time format and reference (JD, BJD, HJD, or MJD).",
                     findings: findings, nextActions: nextActions)
    }
    if let declared = time.declaredTimeSystem, declared != timeSystem {
      return blocked("The selected time column declares \(declared.rawValue). Choose that format or select a different column.",
                     findings: findings, nextActions: nextActions)
    }
    guard let timeScale = selection.timeScale else {
      return blocked("Select the time scale documented for the selected column, such as UTC or TDB.",
                     findings: findings, nextActions: nextActions)
    }
    if let declared = time.declaredTimeScale, declared != timeScale {
      return blocked("The selected time column declares the \(declared.rawValue) scale.",
                     findings: findings, nextActions: nextActions)
    }
    guard let velocityUnit = selection.velocityUnit else {
      return blocked("Select the radial-velocity unit (km/s or m/s).", findings: findings, nextActions: nextActions)
    }
    if let declared = velocity.declaredVelocityUnit, declared != velocityUnit {
      return blocked("The selected radial-velocity column declares \(declared.rawValue).",
                     findings: findings, nextActions: nextActions)
    }

    if let index = selection.uncertaintyColumn {
      guard let uncertainty = review.column(at: index), uncertainty.numericCount > 0 else {
        return blocked("Select an uncertainty column containing finite numbers, or choose None.",
                       findings: findings, nextActions: nextActions)
      }
      guard let uncertaintyUnit = selection.uncertaintyUnit else {
        return blocked("Select the unit of the uncertainty column (km/s or m/s).",
                       findings: findings, nextActions: nextActions)
      }
      if let declared = uncertainty.declaredVelocityUnit, declared != uncertaintyUnit {
        return blocked("The selected uncertainty column declares \(declared.rawValue).",
                       findings: findings, nextActions: nextActions)
      }
    } else {
      findings.append("The staged RV table will not include uncertainties.")
      nextActions.append("Add an uncertainty column before fitting when measurement errors are available.")
    }
    if review.usedPositionalColumns {
      findings.append("The source table has no header; the confirmed positional mapping will be recorded.")
    }
    let status: RadialVelocityReviewStatus = findings.isEmpty ? .pass : .warning
    return RadialVelocitySelectionValidation(
      status: status,
      findings: unique(findings),
      nextActions: unique(nextActions)
    )
  }

  func stage(
    review: RadialVelocityTableReview,
    selection: RadialVelocitySelection,
    runDirectory: String
  ) throws -> RadialVelocityStagedInput {
    let validation = validate(review: review, selection: selection)
    guard validation.canRun,
          let timeColumn = selection.timeColumn,
          let velocityColumn = selection.velocityColumn,
          let timeSystem = selection.timeSystem,
          let timeScale = selection.timeScale,
          let velocityUnit = selection.velocityUnit else {
      throw RadialVelocityInspectionError.invalidSelection(
        validation.findings.first ?? "The RV column selection is incomplete."
      )
    }

    let inputsURL = URL(fileURLWithPath: runDirectory)
      .appendingPathComponent("inputs", isDirectory: true)
    let velsURL = inputsURL.appendingPathComponent("selected_columns.vels")
    let mappingURL = inputsURL.appendingPathComponent("rv_column_mapping.json")

    var acceptedRows = 0
    var skippedRows = 0
    var dataLines: [String] = []
    for row in review.rows {
      guard timeColumn < row.count,
            velocityColumn < row.count,
            var time = finiteNumber(row[timeColumn]),
            var velocity = finiteNumber(row[velocityColumn]) else {
        skippedRows += 1
        continue
      }
      if timeSystem == .mjd {
        time += 2_400_000.5
      }
      if velocityUnit == .metersPerSecond {
        velocity /= 1_000
      }

      var values = [render(time), render(velocity)]
      if let uncertaintyColumn = selection.uncertaintyColumn {
        guard uncertaintyColumn < row.count,
              var uncertainty = finiteNumber(row[uncertaintyColumn]),
              uncertainty > 0 else {
          skippedRows += 1
          continue
        }
        if selection.uncertaintyUnit == .metersPerSecond {
          uncertainty /= 1_000
        }
        values.append(render(uncertainty))
      }
      dataLines.append(values.joined(separator: " "))
      acceptedRows += 1
    }
    guard acceptedRows > 0 else {
      throw RadialVelocityInspectionError.invalidSelection(
        "No rows remained after applying the selected columns and numeric validation."
      )
    }

    let sourceName = URL(fileURLWithPath: review.inputPath).lastPathComponent
    let uncertaintyName = selection.uncertaintyColumn.flatMap { review.columns[safe: $0]?.name }
    let uncertaintyUnit = uncertaintyName == nil ? nil : selection.uncertaintyUnit
    let outputTimeSystem = timeSystem == .mjd ? RadialVelocityTimeSystem.jd : timeSystem
    let header = [
      "# Source File = \(sourceName)",
      "# Time Column = \(review.columns[timeColumn].name)",
      "# Input Time Standard = \(timeSystem.rawValue)",
      "# Time Standard = \(outputTimeSystem.rawValue)",
      "# Time Scale = \(timeScale.rawValue)",
      "# Velocity Column = \(review.columns[velocityColumn].name)",
      "# Uncertainty Column = \(uncertaintyName ?? "none")",
      "# Value Units = km/s",
      "# Original Modified = false"
    ] + (uncertaintyUnit == nil ? [] : ["# Uncertainty Units = km/s"])
    try FileManager.default.createDirectory(at: inputsURL, withIntermediateDirectories: true)
    try (header + dataLines).joined(separator: "\n")
      .appending("\n")
      .write(to: velsURL, atomically: true, encoding: .utf8)

    let mapping: [String: Any] = [
      "source_path": review.inputPath,
      "staged_path": velsURL.path,
      "time_column": review.columns[timeColumn].name,
      "time_input_system": timeSystem.rawValue,
      "time_output_system": outputTimeSystem.rawValue,
      "time_scale": timeScale.rawValue,
      "time_scale_conversion_applied": false,
      "velocity_column": review.columns[velocityColumn].name,
      "velocity_input_unit": velocityUnit.rawValue,
      "velocity_output_unit": "km/s",
      "uncertainty_column": uncertaintyName ?? NSNull(),
      "uncertainty_input_unit": uncertaintyUnit?.rawValue ?? NSNull(),
      "uncertainty_output_unit": uncertaintyUnit == nil ? NSNull() : "km/s",
      "accepted_rows": acceptedRows,
      "skipped_rows": skippedRows,
      "original_modified": false,
      "next_actions": validation.nextActions
    ]
    let mappingData = try JSONSerialization.data(
      withJSONObject: mapping,
      options: [.prettyPrinted, .sortedKeys]
    )
    try mappingData.write(to: mappingURL, options: .atomic)

    return RadialVelocityStagedInput(
      velsPath: velsURL.path,
      mappingPath: mappingURL.path,
      acceptedRows: acceptedRows,
      skippedRows: skippedRows
    )
  }

  private enum Separator {
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

  private func detectedSeparator(in line: String) -> Separator {
    if line.contains("\t") { return .tab }
    if line.contains(",") { return .comma }
    if line.contains(";") { return .semicolon }
    return .whitespace
  }

  private func fields(in line: String, separator: Separator) -> [String] {
    switch separator {
    case .whitespace:
      return line.split(whereSeparator: \.isWhitespace).map(String.init)
    case .comma:
      return delimitedFields(in: line, separator: ",")
    case .semicolon:
      return delimitedFields(in: line, separator: ";")
    case .tab:
      return delimitedFields(in: line, separator: "\t")
    }
  }

  private func delimitedFields(in line: String, separator: Character) -> [String] {
    var fields: [String] = []
    var current = ""
    var quoted = false
    var index = line.startIndex
    while index < line.endIndex {
      let character = line[index]
      if character == "\"" {
        let next = line.index(after: index)
        if quoted, next < line.endIndex, line[next] == "\"" {
          current.append("\"")
          index = next
        } else {
          quoted.toggle()
        }
      } else if character == separator, !quoted {
        fields.append(current.trimmingCharacters(in: .whitespaces))
        current = ""
      } else {
        current.append(character)
      }
      index = line.index(after: index)
    }
    fields.append(current.trimmingCharacters(in: .whitespaces))
    return fields
  }

  private func normalizedHeaders(_ headers: [String], count: Int) -> [String] {
    (0..<count).map { index in
      guard index < headers.count else { return "column_\(index + 1)" }
      let trimmed = headers[index].trimmingCharacters(in: .whitespacesAndNewlines)
      return trimmed.isEmpty ? "column_\(index + 1)" : trimmed
    }
  }

  private func finiteNumber(_ value: String) -> Double? {
    guard let number = Double(value.trimmingCharacters(in: .whitespacesAndNewlines)),
          number.isFinite else {
      return nil
    }
    return number
  }

  private func normalizedName(_ name: String) -> String {
    name.lowercased()
      .replacingOccurrences(of: "[^a-z0-9]+", with: "_", options: .regularExpression)
      .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
  }

  private func scoreTime(_ name: String) -> Int {
    let key = normalizedName(name)
    let tokens = nameTokens(name)
    if timeSystem(tokens) != nil || usesOffsetTime(tokens) || ["time", "epoch"].contains(key) { return 100 }
    if key.contains("julian") { return 85 }
    if key.contains("time") || key.contains("epoch") { return 70 }
    return 0
  }

  private func scoreVelocity(_ name: String) -> Int {
    let key = normalizedName(name)
    if ["error", "err", "sigma", "uncertainty"].contains(where: key.contains) { return 0 }
    if ["rv", "radial_velocity", "velocity", "vrad", "vel"].contains(key) { return 100 }
    if key.contains("radial_velocity") || key.hasPrefix("rv_") || key.hasSuffix("_rv") { return 85 }
    if key.contains("velocity") || key.contains("vrad") { return 75 }
    return 0
  }

  private func scoreUncertainty(_ name: String) -> Int {
    let key = normalizedName(name)
    if ["error", "err", "sigma", "uncertainty", "rv_error", "rv_err", "rv_sigma"].contains(key) {
      return 100
    }
    if key.contains("uncert") || key.contains("sigma") || key.contains("error") || key.hasSuffix("_err") {
      return 85
    }
    return 0
  }

  private func uniqueRecommendation(
    _ columns: [RadialVelocityColumn],
    score: KeyPath<RadialVelocityColumn, Int>
  ) -> Int? {
    let ranked = columns
      .filter { $0.numericCount > 0 && $0[keyPath: score] > 0 }
      .sorted {
        if $0[keyPath: score] != $1[keyPath: score] {
          return $0[keyPath: score] > $1[keyPath: score]
        }
        return $0.numericFraction > $1.numericFraction
      }
    guard let first = ranked.first else { return nil }
    guard ranked.count == 1 || first[keyPath: score] - ranked[1][keyPath: score] >= 15 else {
      return nil
    }
    return first.index
  }

  private func nameTokens(_ value: String) -> [String] {
    normalizedName(value).split(separator: "_").map(String.init)
  }

  private func timeSystem(_ tokens: [String]) -> RadialVelocityTimeSystem? {
    let declarations = Set(tokens.compactMap { RadialVelocityTimeSystem(rawValue: $0.uppercased()) })
    return declarations.count == 1 ? declarations.first : nil
  }

  private func timeScale(_ tokens: [String]) -> RadialVelocityTimeScale? {
    let declarations = Set(tokens.compactMap { RadialVelocityTimeScale(rawValue: $0.uppercased()) })
    return declarations.count == 1 ? declarations.first : nil
  }

  private func usesOffsetTime(_ tokens: [String]) -> Bool {
    if !Set(tokens).isDisjoint(with: ["rjd", "bkjd", "btjd"]) { return true }
    guard timeSystem(tokens) != nil else { return false }
    return tokens.contains("offset") || tokens.contains("minus")
      || tokens.contains { $0.count >= 5 && Int($0) != nil }
  }

  private func velocityUnit(_ tokens: [String]) -> RadialVelocityUnit? {
    let pairs = Array(zip(tokens, tokens.dropFirst()))
    let km = tokens.contains("kms") || tokens.contains("kmps")
      || pairs.contains { $0 == "km" && $1 == "s" }
    let m = tokens.contains("mps") || pairs.contains { $0 == "m" && $1 == "s" }
      || pairs.contains { $0 == "ms" && $1 == "1" }
    guard km != m else { return nil }
    return km ? .kilometersPerSecond : .metersPerSecond
  }

  private func commentMetadata(_ lines: [String]) -> [String: String] {
    var declarations: [String: Set<String>] = [:]
    for line in lines.prefix(while: { $0.hasPrefix("#") }) {
      let pair = line.dropFirst().split(separator: "=", maxSplits: 1)
      guard pair.count == 2 else { continue }
      declarations[normalizedName(String(pair[0])), default: []].insert(normalizedName(String(pair[1])))
    }
    return declarations.compactMapValues { values in
      values.count == 1 ? values.first : nil
    }
  }

  private func blocked(
    _ message: String,
    findings: [String],
    nextActions: [String]
  ) -> RadialVelocitySelectionValidation {
    RadialVelocitySelectionValidation(
      status: .blocked,
      findings: unique(findings + [message]),
      nextActions: unique(nextActions + [message])
    )
  }

  private func unique(_ values: [String]) -> [String] {
    var seen = Set<String>()
    return values.filter { seen.insert($0).inserted }
  }

  private func render(_ value: Double) -> String {
    String(value)
  }
}

private extension Collection {
  subscript(safe index: Index) -> Element? {
    indices.contains(index) ? self[index] : nil
  }
}
