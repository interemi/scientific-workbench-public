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

    let contentLines = text.components(separatedBy: .newlines)
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty && !$0.hasPrefix("#") }
    guard let firstLine = contentLines.first else {
      throw RadialVelocityInspectionError.noDataRows
    }

    let separator = detectedSeparator(in: firstLine)
    let firstFields = fields(in: firstLine, separator: separator)
    let hasHeader = firstFields.contains { finiteNumber($0) == nil }
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
        uncertaintyScore: hasHeader ? scoreUncertainty(name) : positionalScores.2
      )
    }

    let recommendedTime = uniqueRecommendation(columns, score: \.timeScore)
    let recommendedVelocity = uniqueRecommendation(columns, score: \.velocityScore)
    let recommendedUncertainty = uniqueRecommendation(columns, score: \.uncertaintyScore)
    let inferredTimeSystem = inferTimeSystem(from: recommendedTime.flatMap { columns[safe: $0]?.name })
    let inferredVelocityUnit = inferVelocityUnit(from: recommendedVelocity.flatMap { columns[safe: $0]?.name })

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
    guard review.columns.indices.contains(timeColumn),
          review.columns.indices.contains(velocityColumn) else {
      return blocked("The selected columns are outside the table.", findings: findings, nextActions: nextActions)
    }
    guard review.columns[timeColumn].numericCount > 0 else {
      return blocked("The selected time column has no finite numeric values.", findings: findings, nextActions: nextActions)
    }
    guard review.columns[velocityColumn].numericCount > 0 else {
      return blocked("The selected RV column has no finite numeric values.", findings: findings, nextActions: nextActions)
    }

    if selection.uncertaintyColumn == nil {
      findings.append("The staged RV table will not include uncertainties.")
      nextActions.append("Add an uncertainty column before fitting when measurement errors are available.")
    }
    if review.inferredTimeSystem == nil {
      findings.append("The time standard was not inferred from the source column.")
      nextActions.append("Confirm the selected JD, BJD, HJD, or MJD time standard.")
    }
    if review.inferredVelocityUnit == nil {
      findings.append("Velocity units were not inferred from the source column.")
      nextActions.append("Confirm the selected km/s or m/s velocity unit.")
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
          let velocityColumn = selection.velocityColumn else {
      throw RadialVelocityInspectionError.invalidSelection(
        validation.findings.first ?? "The RV column selection is incomplete."
      )
    }

    let inputsURL = URL(fileURLWithPath: runDirectory)
      .appendingPathComponent("inputs", isDirectory: true)
    try FileManager.default.createDirectory(at: inputsURL, withIntermediateDirectories: true)
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
      if selection.timeSystem == .mjd {
        time += 2_400_000.5
      }
      if selection.velocityUnit == .metersPerSecond {
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
        if selection.velocityUnit == .metersPerSecond {
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
    let outputTimeSystem = selection.timeSystem == .mjd ? RadialVelocityTimeSystem.jd : selection.timeSystem
    let header = [
      "# Source File = \(sourceName)",
      "# Time Column = \(review.columns[timeColumn].name)",
      "# Input Time Standard = \(selection.timeSystem.rawValue)",
      "# Time Standard = \(outputTimeSystem.rawValue)",
      "# Velocity Column = \(review.columns[velocityColumn].name)",
      "# Uncertainty Column = \(uncertaintyName ?? "none")",
      "# Value Units = km/s",
      "# Original Modified = false"
    ]
    try (header + dataLines).joined(separator: "\n")
      .appending("\n")
      .write(to: velsURL, atomically: true, encoding: .utf8)

    let mapping: [String: Any] = [
      "source_path": review.inputPath,
      "staged_path": velsURL.path,
      "time_column": review.columns[timeColumn].name,
      "time_input_system": selection.timeSystem.rawValue,
      "time_output_system": outputTimeSystem.rawValue,
      "velocity_column": review.columns[velocityColumn].name,
      "velocity_input_unit": selection.velocityUnit.rawValue,
      "velocity_output_unit": "km/s",
      "uncertainty_column": uncertaintyName ?? NSNull(),
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
    if ["jd", "bjd", "hjd", "mjd", "time", "epoch"].contains(key) { return 100 }
    if key.contains("julian") || key.hasSuffix("_jd") || key.hasPrefix("jd_") { return 85 }
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

  private func inferTimeSystem(from name: String?) -> RadialVelocityTimeSystem? {
    guard let key = name.map(normalizedName) else { return nil }
    if key.contains("bjd") { return .bjd }
    if key.contains("hjd") { return .hjd }
    if key.contains("mjd") { return .mjd }
    if key.contains("jd") || key.contains("julian") { return .jd }
    return nil
  }

  private func inferVelocityUnit(from name: String?) -> RadialVelocityUnit? {
    guard let key = name.map(normalizedName) else { return nil }
    if key.contains("km_s") || key.contains("kms") || key.contains("kmps") {
      return .kilometersPerSecond
    }
    if key.contains("m_s") || key.contains("mps") || key.contains("ms_1") {
      return .metersPerSecond
    }
    return nil
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
    String(format: "%.12g", locale: Locale(identifier: "en_US_POSIX"), value)
  }
}

private extension Collection {
  subscript(safe index: Index) -> Element? {
    indices.contains(index) ? self[index] : nil
  }
}
