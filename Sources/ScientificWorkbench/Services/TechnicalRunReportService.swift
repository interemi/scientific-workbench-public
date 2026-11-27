import Darwin
import Foundation

struct TechnicalRunReportService {
  enum Unavailable: LocalizedError, Equatable {
    case question, provenance, outputs, location

    var errorDescription: String? {
      switch self {
      case .question: "Enter a research question or technical objective of up to 1,000 characters."
      case .provenance: "The job needs a successful run with readable provenance."
      case .outputs: "The output inventory no longer matches the original run or no outputs could be verified."
      case .location: "Choose an unused output location separate from the original run and inputs."
      }
    }
  }

  struct Draft: Sendable {
    let markdown: String
    let citationCount: Int
    let omittedOutputs: Int
  }

  private struct Citation {
    let reference: String
    let file: String
    let recorded: JobRunProvenance.Output
  }

  private struct ToolResult: Decodable {
    struct Results: Decodable {
      struct HDU: Decodable {
        struct Image: Decodable {
          let shape: [Int]?
          let sampledPixels: Int?
          let finitePixels: Int?
        }

        struct WCS: Decodable {
          let crval: [Double]?
          let axisUnits: [String]?
          let referenceFrame: String?
        }

        let index: Int
        let dataSummary: Image?
        let wcs: WCS?
      }

      let rows: Int?
      let columns: Int?
      let hdus: [HDU]?
    }

    let tool: String
    let appStatus: String
    let results: Results
  }

  func prepare(job: JobRecord, question: String, secrets: [String]) throws -> Draft {
    let objective = display(question, secrets: secrets, maximum: 1_001)
    guard !objective.isEmpty, objective.count <= 1_000 else { throw Unavailable.question }
    guard job.status == .succeeded, let record = RunOutputEvidence.provenance(for: job),
          record.status == .succeeded else { throw Unavailable.provenance }

    let root = FilesystemPath.canonicalURL(job.runDirectory)
    let currentInputs = job.requestInputPaths.map(FilesystemPath.canonicalURL)
    let directories = zip(currentInputs, record.inputs).compactMap { url, input in
      input.before.state == .directory ? url : nil
    }
    let urls = RunProvenanceService.retainedOutputFiles(for: job, excluding: Set(currentInputs), attachedDirectories: directories)
    guard urls.count == record.outputs.count else { throw Unavailable.outputs }
    let summaryLocations = Set(job.artifacts.filter(RunMeasurementEvidenceService.isSummary)
      .map { FilesystemPath.canonicalURL($0.path).path })
    let skipped = Set(["command.txt", "stdout.txt", "stderr.txt", "next_steps.md"])
    var citations: [Citation] = []
    var omitted = 0
    var summary: (Data, Citation)?
    for (url, output) in zip(urls, record.outputs) {
      try Task.checkCancellation()
      guard let relative = RunReplayService.relativePath(url, under: root), !skipped.contains(relative) else { continue }
      guard let size = output.fingerprint.byteCount, size >= 0, size <= RunFileFingerprint.defaultReadBudget,
            let hash = output.fingerprint.sha256, RunExecutionEvidence.isDigest(hash), citations.count < 24 else {
        omitted += 1
        continue
      }
      let sizeToCapture = summaryLocations.contains(url.path) && size <= ScientificMeasurementSummary.maximumBytes ? size : 0
      let snapshot = RunFileFingerprint.readSample(url, maximumBytes: size, range: 0..<sizeToCapture)
      guard snapshot.fingerprint == output.fingerprint else {
        omitted += 1
        continue
      }
      let citation = Citation(reference: "A\(citations.count + 1)", file: display(relative, secrets: secrets), recorded: output)
      citations.append(citation)
      if sizeToCapture > 0, summary == nil || relative == "summary.json" {
        summary = (snapshot.bytes, citation)
      }
    }
    guard !citations.isEmpty else { throw Unavailable.outputs }

    let tool = display(job.capabilityID, secrets: secrets)
    var lines = [
      TechnicalReportPDF.heading,
      "",
      "Generated technical draft • Review the evidence before using this report.",
      "",
      "## Question or objective supplied by the author",
      "",
      objective,
      "",
      "## Recorded methods and execution context",
      "",
      "- Capability: \(tool)",
      "- Run ID: \(job.id.uuidString)",
    ]
    if let revision = record.tool.contractRevision { lines.append("- Contract revision: \(revision)") }
    if let version = record.tool.registryDeclaredRelease { lines.append("- Registry release: \(display(version, secrets: secrets))") }
    if let version = record.appVersion, let build = record.appBuild {
      lines.append("- App version: \(display(version, secrets: secrets)) (build \(display(build, secrets: secrets)))")
    }
    if let runtime = record.runtime?.validated() {
      lines.append("- Python: \(runtime.pythonVersion) (\(runtime.architecture))")
    }
    if let backend = record.reportedBackend?.backend { lines.append("- Backend reported by the tool: \(backend.rawValue)") }

    lines += ["", "## Recorded parameters", ""]
    if let command = record.command {
      if let operation = command.operation { lines.append("- Operation: \(display(operation, secrets: secrets))") }
      lines += command.arguments.prefix(32).map { parameter in
        "- " + describe(parameter, secrets: secrets)
      }
      if command.arguments.isEmpty { lines.append("The run recorded no additional arguments.") }
      if command.arguments.count > 32 { lines.append("More arguments are available in the original run provenance.") }
    } else {
      lines.append("No typed parameters were recorded for this run.")
    }

    lines += ["", "## Recorded data and input integrity", ""]
    if record.inputs.isEmpty { lines.append("The run has no recorded attached inputs.") }
    for (index, input) in record.inputs.prefix(24).enumerated() {
      let unchanged = input.contentUnchanged.map { $0 ? "unchanged during the original run" : "changed during the original run" } ?? "integrity unavailable"
      let size = input.before.byteCount.map { ", \($0) bytes" } ?? ""
      lines.append("- Input \(index + 1): \(unchanged)\(size).")
      if let hash = input.before.sha256, RunExecutionEvidence.isDigest(hash) {
        lines.append("  Recorded SHA-256: \(hash)")
      }
    }
    if record.inputs.count > 24 { lines.append("Additional input fingerprints are available in the original provenance.") }

    lines += ["", "## Verified results", ""]
    if let (bytes, citation) = summary {
      lines += resultLines(bytes, capability: job.capabilityID, citation: citation.reference, secrets: secrets)
    } else {
      lines.append("See the verified output files in the evidence index for the recorded results.")
    }

    lines += [
      "", "## Generated interpretation note", "",
      "This note was generated from a fixed template. The figures and references above are retained run evidence. Interpret the results against the stated objective after reviewing the data, methods, and assumptions.",
      "", "## Limitations", "",
      "- The report verifies retained output bytes. Input fingerprints describe the original run.",
      "- A successful execution provides technical evidence. Scientific validity requires separate review.",
    ]
    if omitted > 0 {
      lines.append("- \(omitted) outputs are outside the verified evidence index because their bytes could not be verified or the report reached its evidence limit.")
    }
    let limitations = record.limits.filter { [.inputContentChanged, .directoryContentsNotCaptured, .runtimeInventoryPartial,
                                               .runtimeAndDependencyVersionsNotCaptured, .backendVersionNotRecorded,
                                               .backendNotReported, .localArgumentsRequired].contains($0) }
    lines += limitations.map { "- \($0.guidance)" }
    lines += ["", "## Evidence index", "", "Locations are relative to the original run folder. Use the recorded SHA-256 to verify each cited file.", ""]
    for citation in citations {
      let fingerprint = citation.recorded.fingerprint
      lines += [
        "### [\(citation.reference)] \(citation.file)",
        "\(fingerprint.byteCount ?? 0) bytes · SHA-256: \(fingerprint.sha256 ?? "")",
        "",
      ]
    }
    return Draft(markdown: lines.joined(separator: "\n") + "\n", citationCount: citations.count, omittedOutputs: omitted)
  }

  func export(job: JobRecord, question: String, parent: URL, secrets: [String]) throws -> URL {
    guard parent.isFileURL,
          RunReplayService.relativePath(FilesystemPath.canonicalURL(parent.path),
                                        under: FilesystemPath.canonicalURL(job.runDirectory)) == nil else {
      throw Unavailable.location
    }
    if case .blocked = FilesystemSafetyPolicy().assessOutputRoot(parent.path, inputPaths: job.requestInputPaths) {
      throw Unavailable.location
    }
    let report = try prepare(job: job, question: question, secrets: secrets)
    let pdf = try TechnicalReportPDF.render(markdown: report.markdown)
    try Task.checkCancellation()
    let name = "Scientific Workbench Report \(job.id.uuidString.prefix(8)) \(UUID().uuidString.prefix(8))"
    let output = parent.appendingPathComponent(name, isDirectory: true)
    let staging = parent.appendingPathComponent(".swb-report-\(UUID().uuidString)", isDirectory: true)
    guard mkdir(staging.path, 0o700) == 0 else { throw Unavailable.location }
    defer { try? FileManager.default.removeItem(at: staging) }
    try Data(report.markdown.utf8).write(to: staging.appendingPathComponent("report.md"), options: .withoutOverwriting)
    try pdf.write(to: staging.appendingPathComponent("report.pdf"), options: .withoutOverwriting)
    try FileManager.default.moveItem(at: staging, to: output)
    return output
  }

  func regenerate(source: URL, destination: URL) throws {
    guard source.isFileURL, destination.isFileURL, destination.pathExtension.lowercased() == "pdf",
          !FileManager.default.fileExists(atPath: destination.path) else { throw Unavailable.location }
    let limit = Int64(TechnicalReportPDF.maximumSourceBytes)
    let snapshot = RunFileFingerprint.readSample(source, maximumBytes: limit, range: 0..<limit)
    guard snapshot.fingerprint.state == .recorded, let markdown = String(data: snapshot.bytes, encoding: .utf8) else {
      throw TechnicalReportPDF.Unavailable.source
    }
    let pdf = try TechnicalReportPDF.render(markdown: markdown)
    try Task.checkCancellation()
    try pdf.write(to: destination, options: .withoutOverwriting)
  }

  private func resultLines(_ data: Data, capability: String, citation: String, secrets: [String]) -> [String] {
    let reference = "[\(citation)]"
    if let summary = ScientificMeasurementSummary.decode(data, capabilityID: capability), summary.evidenceOutcome != nil {
      var results = ["Method reported by the tool: \(display(summary.method, secrets: secrets)) \(reference)", ""]
      let numeric = summary.measurements + summary.diagnostics
      for quantity in numeric.prefix(28) {
        let uncertainty = quantity.uncertainty.map { " ± \($0)" } ?? ""
        results.append("- \(display(quantity.label, secrets: secrets)): \(quantity.value)\(uncertainty) \(display(quantity.unit, secrets: secrets)) \(reference)")
      }
      if !summary.assumptions.isEmpty {
        results += ["", "Assumptions recorded by the tool \(reference)"]
        results += summary.assumptions.prefix(8).map { "- \(display($0, secrets: secrets))" }
      }
      if numeric.count > 28 { results.append("The cited file contains additional measurements or diagnostics.") }
      return results
    }
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    guard let result = try? decoder.decode(ToolResult.self, from: data), result.tool == capability,
          ["PASS", "WARNING"].contains(result.appStatus) else {
      return ["Inspect the recorded results in \(reference) and the evidence index below."]
    }
    switch capability {
    case "profile_table":
      if let rows = result.results.rows, rows >= 0, let columns = result.results.columns, columns >= 0 {
        return ["- Rows profiled: \(rows) \(reference)", "- Columns profiled: \(columns) \(reference)"]
      }
    case "inspect_fits":
      if let hdus = result.results.hdus {
        var lines = ["- Header/data units inspected: \(hdus.count) \(reference)"]
        for hdu in hdus.prefix(8) {
          if let shape = hdu.dataSummary?.shape {
            lines.append("- HDU \(hdu.index) recorded array shape: \(shape.map(String.init).joined(separator: " × ")) \(reference)")
          }
          if let finite = hdu.dataSummary?.finitePixels, let sampled = hdu.dataSummary?.sampledPixels {
            lines.append("- HDU \(hdu.index) finite sample: \(finite) of \(sampled) pixels \(reference)")
          }
          if let wcs = hdu.wcs, let values = wcs.crval, let units = wcs.axisUnits,
             !values.isEmpty, values.count == units.count, values.count <= 4 {
            let axes = zip(values, units).map { value, unit in "\(value) \(display(unit, secrets: secrets))" }.joined(separator: ", ")
            let frame = wcs.referenceFrame.map { " (\(display($0, secrets: secrets)))" } ?? ""
            lines.append("- HDU \(hdu.index) WCS reference: \(axes)\(frame) \(reference)")
          }
        }
        if hdus.count > 8 { lines.append("The cited file contains additional HDUs.") }
        return lines
      }
    default: break
    }
    return ["Inspect the recorded results in \(reference) and the evidence index below."]
  }

  private func describe(_ argument: RunCommandEvidence.Argument, secrets: [String]) -> String {
    let option = argument.option.map { display($0, secrets: secrets) }
    let value: String
    switch argument.kind {
    case .flag: return option ?? "Recorded flag"
    case .boundary: return "Positional argument separator"
    case .input, .runLocation: value = argument.reference ?? "Recorded location"
    case .choice: value = argument.choice ?? "Recorded choice"
    case .integer: value = argument.integers?.map(String.init).joined(separator: ", ") ?? "Recorded integer"
    case .number: value = argument.numbers?.map { String($0) }.joined(separator: ", ") ?? "Recorded number"
    case .withheld: value = "Local value withheld"
    }
    return [option, display(value, secrets: secrets)].compactMap { $0 }.joined(separator: " ")
  }

  private func display(_ value: String, secrets: [String], maximum: Int = 280) -> String {
    let text = SecretsRedactor.redact(value, secrets: secrets)
    let publicText = CloudPrivacySanitizer.withholdingAbsolutePaths(in: text)
    let singleLine = publicText.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    return String(singleLine.prefix(maximum))
  }
}
