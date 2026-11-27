import Foundation

struct RunReplayComparison: Codable, Sendable {
  static let filename = "replay-comparison.json"
  static let absoluteTolerance = 1e-10
  static let relativeTolerance = 1e-10

  enum Outcome: String, Codable, Sendable {
    case matches, differences
    case notReproducible = "not_reproducible"

    var title: String {
      switch self {
      case .matches: "Recorded outputs match"
      case .differences: "Replay found differences"
      case .notReproducible: "Not reproducible from the available evidence"
      }
    }
  }

  struct Difference: Codable, Sendable {
    enum Method: String, Codable, Sendable {
      case sha256, numericTable
    }

    enum Status: String, Codable, Sendable {
      case identical, withinTolerance, changed, added, missing, unavailable
    }

    let path: String
    let method: Method
    let status: Status
    let originalSHA256: String?
    let replaySHA256: String?
    var comparedNumbers: Int? = nil
    var differingCells: Int? = nil
    var maximumAbsoluteDifference: Double? = nil
  }

  let schemaVersion: Int
  let originalJobID: UUID
  let replayJobID: UUID
  let outcome: Outcome
  let detail: String
  let absoluteTolerance: Double
  let relativeTolerance: Double
  let outputs: [Difference]

  static func retain(_ plan: RunReplayService.Plan, for job: JobRecord) throws -> (Self, Artifact) {
    let comparison = compare(plan, job: job)
    guard plan.ownsDirectory() else { throw CocoaError(.fileWriteInvalidFileName) }
    let url = plan.directory.appendingPathComponent(filename)
    let data = try JSONEncoder.scientificWorkbench.encode(comparison)
    try data.write(to: url, options: .withoutOverwriting)
    return (comparison, Artifact(path: url.path, relativePath: filename, byteCount: Int64(data.count),
                                 artifactType: "metadata_json", label: "Replay comparison"))
  }

  private static func compare(_ plan: RunReplayService.Plan, job: JobRecord) -> Self {
    func report(_ outcome: Outcome, _ detail: String, outputs: [Difference] = []) -> Self {
      Self(schemaVersion: 1, originalJobID: plan.original.id, replayJobID: job.id, outcome: outcome,
           detail: detail, absoluteTolerance: absoluteTolerance, relativeTolerance: relativeTolerance, outputs: outputs)
    }
    guard job.status == .succeeded, let record = RunOutputEvidence.provenance(for: job),
          let receipt = RunExecutionEvidence.read(for: job) else {
      return report(.notReproducible, "The replay did not complete successfully with local execution evidence.")
    }
    guard receipt.pythonInventorySHA256 == plan.pythonInventorySHA256,
          receipt.commandSHA256 == plan.commandDigest, record.tool == plan.tool,
          record.approvals == plan.approvals, !record.outputRootConfirmationUsed,
          record.reportedBackend == nil, !record.limits.contains(.backendNotReported) else {
      return report(.notReproducible, "The observed runtime, tool or permissions differed from the reviewed execution.")
    }
    guard record.inputs.map(\.before) == plan.inputFingerprints,
          record.inputs.allSatisfy({ $0.contentUnchanged == true }) else {
      return report(.notReproducible, "The replay input copies did not match or changed during execution.")
    }
    let inputs = Set(plan.inputPaths.map(FilesystemPath.canonicalURL))
    let files = RunProvenanceService.retainedOutputFiles(for: job, excluding: inputs, attachedDirectories: [])
    let names = files.compactMap { RunReplayService.relativePath($0, under: plan.directory) }
    guard names.count == record.outputs.count, !names.isEmpty else {
      return report(.notReproducible, "The replay output inventory could not be verified.")
    }
    let before = Dictionary(uniqueKeysWithValues: plan.originalOutputs.map { ($0.relativePath, $0.fingerprint) })
    let after = Dictionary(uniqueKeysWithValues: zip(names, record.outputs.map(\.fingerprint)))
    let originalRoot = FilesystemPath.canonicalURL(plan.original.runDirectory)
    let originals = plan.originalOutputs.map { originalRoot.appendingPathComponent($0.relativePath) }
    let originalCurrent = RunProvenanceService.fingerprints(originals.map(Optional.some))
    let replayCurrent = RunProvenanceService.fingerprints(files.map(Optional.some))
    guard originalCurrent == plan.originalOutputs.map(\.fingerprint), replayCurrent == record.outputs.map(\.fingerprint) else {
      return report(.notReproducible, "Retained output files changed during the comparison.")
    }
    let relativePaths = Set(before.keys).union(after.keys).sorted()
    let results = relativePaths.map { path -> Difference in
      let a = before[path]?.sha256
      let b = after[path]?.sha256
      let name = SecretsRedactor.redact(path, secrets: plan.settings.secrets)
      let status: Difference.Status
      if before[path] == nil { status = .added }
      else if after[path] == nil { status = .missing }
      else if a == nil || b == nil { status = .unavailable }
      else if a == b { status = .identical }
      else {
        if let columns = numericColumns[plan.capability.id],
           let expected = before[path], let observed = after[path],
           let numbers = compareTable(
            originalRoot.appendingPathComponent(path), plan.directory.appendingPathComponent(path),
            original: expected, replay: observed, columns: columns
           ) {
          return Difference(path: name, method: .numericTable, status: numbers.differences == 0 ? .withinTolerance : .changed,
                            originalSHA256: a, replaySHA256: b, comparedNumbers: numbers.compared,
                            differingCells: numbers.differences, maximumAbsoluteDifference: numbers.maximum)
        }
        status = .changed
      }
      return Difference(path: name, method: .sha256, status: status, originalSHA256: a, replaySHA256: b)
    }
    if results.contains(where: { $0.status == .unavailable }) {
      return report(.notReproducible, "Some output fingerprints were unavailable.", outputs: results)
    }
    let match = results.allSatisfy { $0.status == .identical || $0.status == .withinTolerance }
    return report(match ? .matches : .differences,
                  "Compared \(results.count) files by relative path. Logs and manifests can differ with the new folder and timestamps.",
                  outputs: results)
  }

  // Only schema-defined measurement columns admit numerical tolerance. IDs,
  // unit strings and all other cells must match exactly.
  private static let numericColumns: [String: Set<String>] = [
    "photometric_solution": ["value", "uncertainty", "observed_offset_mag", "model_offset_mag", "residual_mag",
                             "normalized_residual"],
    "catalog_workbench.crossmatch-sky": ["match_sep_arcsec"],
    "li6708_equivalent_width_workbench.measure": [
      "line_depth", "ew_angstrom", "ew_milliangstrom", "uncertainty_milliangstrom", "continuum_rms",
      "random_like_uncertainty_milliangstrom", "literature_ew_milliangstrom", "literature_delta_milliangstrom",
    ],
  ]

  static func compareTable(
    _ old: URL, _ new: URL, original: RunFileFingerprint, replay: RunFileFingerprint, columns: Set<String>
  ) -> (compared: Int, differences: Int, maximum: Double)? {
    let ext = old.pathExtension.lowercased()
    let budget: Int64 = 2 * 1_024 * 1_024
    guard ext == "csv" || ext == "tsv" else { return nil }
    let a = RunFileFingerprint.readSample(old, maximumBytes: budget, range: 0..<budget)
    let b = RunFileFingerprint.readSample(new, maximumBytes: budget, range: 0..<budget)
    guard a.fingerprint == original, b.fingerprint == replay else { return nil }
    let delimiter: UInt8 = ext == "tsv" ? 9 : 44
    guard let first = try? TablePreviewService.completeDelimitedRows(a.bytes, delimiter: delimiter),
          let second = try? TablePreviewService.completeDelimitedRows(b.bytes, delimiter: delimiter),
          first.count == second.count, let header = first.first, header == second.first,
          Set(header).count == header.count else { return nil }
    let coefficientSchema = header == ["parameter", "value", "uncertainty", "unit"]
    let numeric = Set(header.indices.filter { index in
      columns.contains(header[index]) && (coefficientSchema || !["value", "uncertainty"].contains(header[index]))
    })
    guard !numeric.isEmpty else { return nil }
    var compared = 0
    var differences = 0
    var maximum = 0.0
    for (left, right) in zip(first.dropFirst(), second.dropFirst()) {
      guard left.count == header.count, right.count == header.count else { return nil }
      for index in header.indices {
        if numeric.contains(index), let x = Double(left[index]), let y = Double(right[index]),
           x.isFinite, y.isFinite, abs(x - y).isFinite {
          compared += 1
          let error = abs(x - y)
          maximum = max(maximum, error)
          if error > max(absoluteTolerance, relativeTolerance * max(abs(x), abs(y))) { differences += 1 }
        } else if left[index] != right[index] {
          differences += 1
        }
      }
    }
    return compared > 0 ? (compared, differences, maximum) : nil
  }
}
