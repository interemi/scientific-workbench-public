import CryptoKit
import Foundation

struct PortableRunPackageService {
  enum Unavailable: LocalizedError, Equatable {
    case provenance, selection, unsafeContent, changedArtifact, package, outputLocation

    var errorDescription: String? {
      switch self {
      case .provenance: "The job needs a successful run with readable provenance."
      case .selection: "One of the selected files is unavailable or outside the supported package scope."
      case .unsafeContent: "Selected content includes a private path, credential, prompt field, or unsupported encoding."
      case .changedArtifact: "A selected output differs from the recorded run."
      case .package: "The package manifest, member types, or SHA-256 values do not match."
      case .outputLocation: "Choose an unused ZIP destination outside the original run and input folders."
      }
    }
  }

  struct Summary: Codable, Sendable {
    let sourceJobID: UUID
    let tool: JobRunProvenance.Tool
    let appVersion: String?
    let appBuild: String?
    let hostMacOSVersion: String?
    let runtime: RunRuntimeEvidence?
    let externalBackend: RunBackendEvidence.Backend?
    let inputs: [JobRunProvenance.Input]
    let command: RunCommandEvidence?
    let limits: [JobRunProvenance.Limit]
  }

  struct Entry: Identifiable, Codable, Sendable {
    enum Kind: String, Codable, Sendable { case summary, instructions, script, selectedOutput, syntheticFixture }

    let name: String
    let kind: Kind
    let byteCount: Int
    let sha256: String
    let originalSHA256: String?
    var id: String { name }
  }

  private struct Manifest: Codable {
    let schemaVersion: Int
    let format: String
    let entries: [Entry]
  }

  struct Fixture: Identifiable, Sendable {
    let input: Int
    let ext: String
    let sha256: String
    var id: Int { input }
  }

  struct Selection: Sendable {
    var outputIDs: Set<UUID> = []
    var fixtureIDs: Set<Int> = []
  }

  struct Review: Sendable {
    let summary: Summary
    let entries: [Entry]

    var includesSelectedData: Bool { entries.contains { $0.kind == .selectedOutput } }

    func dependencyWarnings(capabilities: [CapabilityEntry], environment: EnvironmentDiagnosis?) -> [String] {
      var warnings: [String] = []
      if let capability = capabilities.first(where: { $0.id == summary.tool.capabilityID }) {
        if summary.tool.registryDeclaredRelease != capability.registryDeclaredRelease
          || summary.tool.registrySHA256 != capability.registryFingerprint {
          warnings.append("The installed skill registry differs from the registry recorded for this run.")
        }
      } else {
        warnings.append("The recorded capability is missing from the installed skills.")
      }
      if let runtime = summary.runtime {
        if let environment {
          if environment.pythonVersion != runtime.pythonVersion {
            warnings.append("The selected Python version differs from the recorded version or is unavailable.")
          }
          let missing = runtime.profilePackages.keys.sorted().filter { package in
            let module = PortableRunPackageService.moduleNames[package] ?? package
            return environment.inspectedModules[module] == false
          }
          if !missing.isEmpty {
            warnings.append("Missing recorded packages: \(missing.joined(separator: ", ")).")
          }
          let unverified = runtime.profilePackages.keys.filter { package in
            let module = PortableRunPackageService.moduleNames[package] ?? package
            return environment.inspectedModules[module] == nil
          }
          if !unverified.isEmpty { warnings.append("Some recorded packages have no local availability result.") }
          if !runtime.profilePackages.isEmpty { warnings.append("Check version pins in the recorded package list before reproducing.") }
        } else {
          warnings.append("Run the environment check in Settings to assess the recorded Python dependencies.")
        }
      } else {
        warnings.append("The original run did not record its Python and package versions.")
      }
      if summary.externalBackend != nil || summary.limits.contains(.backendNotReported) {
        warnings.append("Verify the external backend and its settings separately.")
      }
      if summary.inputs.count > entries.filter({ $0.kind == .syntheticFixture }).count {
        warnings.append("Obtain separate copies of the inputs that are missing from the package and match their hashes.")
      }
      if summary.command == nil || summary.command?.requiresLocalArguments == true {
        warnings.append("Reproduction needs locally reviewed command arguments.")
      }
      return warnings
    }
  }

  private static let manifestName = "manifest.json"
  private static let format = "scientific_workbench_portable_run"
  private static let moduleNames = [
    "python-docx": "docx", "python-pptx": "pptx", "PyYAML": "yaml", "scikit-learn": "sklearn",
    "rapidocr-onnxruntime": "rapidocr_onnxruntime", "python-calamine": "python_calamine",
    "numbers-parser": "numbers_parser", "jupyter_client": "jupyter_client",
  ]

  func outputCandidates(for job: JobRecord) -> [Artifact] {
    guard job.status == .succeeded else { return [] }
    let inspection = ArtifactInspectionService()
    return job.artifacts.filter { artifact in
      let role = inspection.role(for: artifact)
      return (role == .result || role == .primaryResult)
        && PortableRunContent.Format(rawValue: artifact.url.pathExtension.lowercased()) != nil
        && artifact.byteCount >= 0 && artifact.byteCount <= PortableRunZIP.maximumMemberBytes
        && !artifact.relativePath.split(separator: "/").contains(where: { $0.hasPrefix(".") || $0 == "inputs" })
    }
  }

  func fixtureCandidates(for job: JobRecord) -> [Fixture] {
    guard let record = RunOutputEvidence.provenance(for: job) else { return [] }
    return fixtures(in: record.inputs)
  }

  func export(job: JobRecord, selection: Selection, to destination: URL, secrets: [String]) throws -> Review {
    let originalRoot = FilesystemPath.canonicalURL(job.runDirectory)
    let target = FilesystemPath.canonicalURL(destination.path)
    let outputFolder = target.deletingLastPathComponent()
    guard destination.isFileURL, destination.pathExtension.lowercased() == "zip",
          RunReplayService.relativePath(target, under: originalRoot) == nil,
          !FileManager.default.fileExists(atPath: destination.path) else { throw Unavailable.outputLocation }
    if case .blocked = FilesystemSafetyPolicy().assessOutputRoot(outputFolder.path, inputPaths: job.requestInputPaths) {
      throw Unavailable.outputLocation
    }
    let data = try PortableRunZIP.encode(assemble(job: job, selection: selection, secrets: secrets))
    let review = try inspect(files: PortableRunZIP.decode(data))
    try Task.checkCancellation()
    try data.write(to: destination, options: .withoutOverwriting)
    return review
  }

  func review(at url: URL) throws -> Review {
    let limit = Int64(PortableRunZIP.maximumArchiveBytes)
    guard url.isFileURL else { throw Unavailable.package }
    let capture = RunFileFingerprint.readSample(url, maximumBytes: limit, range: 0..<limit)
    if capture.fingerprint.state == .overBudget { throw PortableRunZIP.Invalid.size }
    guard capture.fingerprint.state == .recorded else { throw Unavailable.package }
    return try inspect(files: PortableRunZIP.decode(capture.bytes))
  }

  private func assemble(job: JobRecord, selection: Selection, secrets: [String]) throws -> [String: Data] {
    guard job.status == .succeeded, let record = RunOutputEvidence.provenance(for: job),
          record.status == .succeeded else { throw Unavailable.provenance }
    let candidates = outputCandidates(for: job).filter { selection.outputIDs.contains($0.id) }
    let matchedFixtures = fixtures(in: record.inputs).filter { selection.fixtureIDs.contains($0.input) }
    guard candidates.count == selection.outputIDs.count, matchedFixtures.count == selection.fixtureIDs.count,
          candidates.count + matchedFixtures.count + Self.fixedMembers.count + 2 <= PortableRunZIP.maximumMembers else {
      throw Unavailable.selection
    }
    let summary = Summary(sourceJobID: record.jobID, tool: record.tool, appVersion: record.appVersion,
      appBuild: record.appBuild, hostMacOSVersion: record.hostMacOSVersion, runtime: record.runtime?.validated()?.shareable,
      externalBackend: record.reportedBackend?.backend, inputs: record.inputs, command: record.command, limits: record.limits)

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    var files: [String: Data] = [:]
    var entries: [Entry] = []
    var byteCount = 0
    func add(_ name: String, _ data: Data, kind: Entry.Kind, original: String? = nil) throws {
      guard byteCount + data.count <= PortableRunZIP.maximumArchiveBytes,
            data.count <= PortableRunZIP.maximumMemberBytes else { throw PortableRunZIP.Invalid.size }
      byteCount += data.count
      files[name] = data
      entries.append(.init(name: name, kind: kind, byteCount: data.count, sha256: Self.digest(data), originalSHA256: original))
    }
    let metadata = try encoder.encode(summary)
    guard PortableRunContent.isShareableText(metadata, secrets: secrets) else { throw Unavailable.unsafeContent }
    try add("summary.json", metadata, kind: .summary)
    for (name, content) in Self.fixedMembers {
      try add(name, Data(content.utf8), kind: name == "readme.md" ? .instructions : .script)
    }
    for (index, artifact) in candidates.enumerated() {
      try Task.checkCancellation()
      guard let format = PortableRunContent.Format(rawValue: artifact.url.pathExtension.lowercased()) else {
        throw Unavailable.selection
      }
      let retained = try RunOutputEvidence(artifact: artifact, job: job)
      let limit = Int64(PortableRunZIP.maximumMemberBytes)
      let captured = RunFileFingerprint.readSample(retained.url, maximumBytes: limit, range: 0..<limit)
      if captured.fingerprint.state == .overBudget { throw PortableRunZIP.Invalid.size }
      guard retained.matches(captured.fingerprint), let hash = captured.fingerprint.sha256 else {
        throw Unavailable.changedArtifact
      }
      let data: Data
      if format == .png {
        guard let raster = PortableRunContent.publicPNG(captured.bytes) else { throw Unavailable.selection }
        data = raster
      } else {
        guard PortableRunContent.isShareableText(captured.bytes, secrets: secrets) else { throw Unavailable.unsafeContent }
        data = captured.bytes
      }
      try add("outputs/output-\(index + 1).\(format.rawValue)", data, kind: .selectedOutput, original: hash)
    }
    for fixture in matchedFixtures {
      guard let sample = FirstRunExampleService.portableFixture(sha256: fixture.sha256) else { throw Unavailable.selection }
      try add("fixtures/input-\(fixture.input).\(fixture.ext)", sample.data, kind: .syntheticFixture, original: fixture.sha256)
    }
    files[Self.manifestName] = try encoder.encode(Manifest(schemaVersion: 1, format: Self.format,
                                                          entries: entries.sorted { $0.name < $1.name }))
    return files
  }

  private func inspect(files: [String: Data]) throws -> Review {
    let decoder = JSONDecoder()
    guard let manifestData = files[Self.manifestName], manifestData.count <= 64 * 1024,
          let manifest = try? decoder.decode(Manifest.self, from: manifestData),
          manifest.schemaVersion == 1, manifest.format == Self.format,
          !manifest.entries.contains(where: { $0.name == Self.manifestName }),
          Set(manifest.entries.map(\.name)).count == manifest.entries.count,
          files.count == manifest.entries.count + 1,
          manifest.entries.contains(where: { $0.name == "summary.json" && $0.kind == .summary }),
          let metadata = files["summary.json"], metadata.count <= 128 * 1024,
          PortableRunContent.isShareableText(metadata, secrets: []),
          let summary = try? decoder.decode(Summary.self, from: metadata),
          let tool = summary.tool.capabilityID, tool.range(of: #"\A[a-z][a-z0-9_.-]{0,127}\z"#, options: .regularExpression) != nil,
          Self.fixedMembers.keys.allSatisfy({ files[$0] != nil }) else { throw Unavailable.package }

    let fixtures = fixtures(in: summary.inputs)
    for entry in manifest.entries {
      try Task.checkCancellation()
      guard let data = files[entry.name], data.count == entry.byteCount, Self.digest(data) == entry.sha256 else {
        throw Unavailable.package
      }
      switch entry.kind {
      case .summary:
        guard entry.name == "summary.json", entry.originalSHA256 == nil else { throw Unavailable.package }
      case .instructions, .script:
        guard entry.originalSHA256 == nil,
              entry.kind == (entry.name == "readme.md" ? .instructions : .script),
              let content = Self.fixedMembers[entry.name], data == Data(content.utf8) else { throw Unavailable.package }
      case .selectedOutput:
        guard let original = entry.originalSHA256, RunExecutionEvidence.isDigest(original),
              entry.name.range(of: #"\Aoutputs/output-[1-9][0-9]?\.(csv|tsv|ecsv|png)\z"#,
                               options: .regularExpression) != nil else { throw Unavailable.package }
        if entry.name.hasSuffix(".png") {
          guard data.starts(with: [137, 80, 78, 71, 13, 10, 26, 10]) else { throw Unavailable.package }
        } else {
          guard original == entry.sha256, PortableRunContent.isShareableText(data, secrets: []) else {
            throw Unavailable.unsafeContent
          }
        }
      case .syntheticFixture:
        guard fixtures.contains(where: {
          entry.name == "fixtures/input-\($0.input).\($0.ext)"
            && entry.sha256 == $0.sha256 && entry.originalSHA256 == $0.sha256
        }) else { throw Unavailable.package }
      }
    }
    return Review(summary: summary, entries: manifest.entries)
  }

  private func fixtures(in inputs: [JobRunProvenance.Input]) -> [Fixture] {
    inputs.enumerated().compactMap { index, input in
      guard input.contentUnchanged == true, let hash = input.before.sha256,
            let sample = FirstRunExampleService.portableFixture(sha256: hash) else { return nil }
      return Fixture(input: index + 1, ext: sample.ext, sha256: hash)
    }
  }

  private static func digest(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }

  private static let fixedMembers = [
    "readme.md": """
      # Scientific Workbench portable run

      Use **Jobs → Inspect Portable ZIP** to verify the manifest and inspect the
      recorded run. Inspection does not extract files, install anything, or execute code.
      SHA-256 checks record integrity, not authorship or scientific validity.

      Review the selected outputs before sharing them. Their archive names are
      neutral. PNG previews were encoded again to remove embedded metadata.
      Optional fixtures are verified synthetic examples generated by the app.
      They are available under the project's PolyForm Noncommercial 1.0.0 license.

      To reproduce, obtain Scientific Workbench and the skill family from
      https://github.com/interemi/scientific-workbench-public. See its INSTALL.md
      and the commands for the recorded capability. Match the available input
      hashes, restore private arguments locally, and write into a fresh output
      folder. Review the tool, package versions, backend, and original limitations
      in summary.json.

      The scripts are inspection helpers. From a separate copy of the package,
      after reviewing the script source, you may run:

      `python3 scripts/verify_package.py package.zip`

      `python3 scripts/verify_tool.py package.zip entrypoint.py implementation.py`
      """,
    "scripts/verify_package.py": """
      #!/usr/bin/env python3
      import hashlib
      import json
      import sys
      import zipfile

      with zipfile.ZipFile(sys.argv[1]) as archive:
          members = archive.infolist()
          names = {member.filename for member in members}
          if (not 1 <= len(members) <= 32 or len(names) != len(members)
                  or "manifest.json" not in names
                  or any(m.compress_type != zipfile.ZIP_STORED or m.file_size > 8 * 1024**2 for m in members)
                  or sum(m.file_size for m in members) > 32 * 1024**2):
              raise SystemExit("Unexpected member names, sizes or compression.")
          manifest = json.loads(archive.read("manifest.json"))
          entries = manifest["entries"]
          expected = {entry["name"] for entry in entries}
          if (manifest["schemaVersion"] != 1 or manifest["format"] != "scientific_workbench_portable_run"
                  or len(expected) != len(entries) or names != expected | {"manifest.json"}):
              raise SystemExit("ZIP members do not match the manifest.")
          for entry in entries:
              payload = archive.read(entry["name"])
              if len(payload) != entry["byteCount"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                  raise SystemExit("A member failed SHA-256 verification.")
      print(f"Verified {len(entries)} portable members.")
      """,
    "scripts/verify_tool.py": """
      #!/usr/bin/env python3
      import hashlib
      import json
      from pathlib import Path
      import sys
      import zipfile

      with zipfile.ZipFile(sys.argv[1]) as archive:
          member = archive.getinfo("summary.json")
          if member.compress_type != zipfile.ZIP_STORED or member.file_size > 128 * 1024:
              raise SystemExit("Unexpected summary format.")
          tool = json.loads(archive.read(member))["tool"]
      for field, argument in zip(("entryPointSHA256", "implementationSHA256"), sys.argv[2:], strict=True):
          expected = tool.get(field)
          source = Path(argument)
          if not expected or not source.is_file() or source.stat().st_size > 8 * 1024**2:
              raise SystemExit("Missing recorded fingerprint or local source.")
          if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
              raise SystemExit(f"{field} differs.")
      print("Both recorded tool fingerprints match the supplied source files.")
      """,
  ]
}
