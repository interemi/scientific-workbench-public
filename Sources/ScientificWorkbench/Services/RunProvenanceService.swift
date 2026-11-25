import Foundation

struct JobRunProvenance: Codable, Sendable {
  static let filename = "run-provenance.json"

  struct Tool: Codable, Sendable {
    let capabilityID: String?
    let skillRole: SkillRootRole?
    let contractRevision: Int?
    let registrySHA256: String?
    let entryPointSHA256: String?
    let implementationSHA256: String?
  }

  struct Input: Codable, Sendable {
    let id: String
    let before: RunFileFingerprint
    let after: RunFileFingerprint
    let contentUnchanged: Bool?
  }

  struct Output: Codable, Sendable {
    let id: String
    let fingerprint: RunFileFingerprint
  }

  enum Limit: String, Codable, Sendable {
    case attachedInputScope = "attached_input_scope"
    case directoryContentsNotCaptured = "directory_contents_not_captured"
    case incompleteFingerprints = "incomplete_fingerprints"
    case inputContentChanged = "input_content_changed"
    case localArgumentsRequired = "local_arguments_required"
    case runtimeAndDependencyVersionsNotCaptured = "runtime_and_dependency_versions_not_captured"
    case backendAndModelNotCaptured = "backend_and_model_not_captured"
    case furtherConsentEvidenceRequired = "further_consent_evidence_required"
  }

  let schemaVersion: Int
  let jobID: UUID
  let appVersion: String?
  let appBuild: String?
  let tool: Tool
  let status: JobStatus
  let exitCode: Int32?
  let startedAt: Date?
  let finishedAt: Date?
  let outputRootConfirmationUsed: Bool
  let inputs: [Input]
  let outputs: [Output]
  let limits: [Limit]
}

struct RunProvenanceService {
  struct Start: Sendable {
    fileprivate let inputPaths: [String]
    fileprivate let inputURLs: [URL]
    fileprivate let fingerprints: [RunFileFingerprint]
    fileprivate let runRoot: URL
    fileprivate let tool: JobRunProvenance.Tool
    fileprivate let appVersion: String?
    fileprivate let appBuild: String?
    fileprivate let outputRootConfirmationUsed: Bool
  }

  func captureStart(
    request: RunRequest, capability: CapabilityEntry, skillRoot: String,
    outputRootConfirmationUsed: Bool, secrets: [String]
  ) async -> Start {
    await Task.detached(priority: .utility) {
      let owner = FilesystemPath.canonicalURL(capability.resolvedSkillRoot(fallback: skillRoot))
      let entryPoint = owner.appendingPathComponent(capability.script)
      let implementation = owner.appendingPathComponent("fixtures", isDirectory: true)
        .appendingPathComponent(entryPoint.lastPathComponent)
      let registry = capability.registryFingerprint
      let tool = JobRunProvenance.Tool(
        capabilityID: Self.safeIdentifier(capability.id, secrets: secrets),
        skillRole: capability.owningSkillRole.flatMap(SkillRootRole.init(rawValue:)),
        contractRevision: capability.ioContract?.revision,
        registrySHA256: registry.flatMap { value in
          value.utf8.count == 64 && value.utf8.allSatisfy(Self.isHexDigit) ? value.lowercased() : nil
        },
        entryPointSHA256: Self.digest(entryPoint, inside: owner),
        implementationSHA256: Self.digest(implementation, inside: owner)
      )
      let inputURLs = request.inputPaths.map(FilesystemPath.canonicalURL)
      return Start(
        inputPaths: request.inputPaths,
        inputURLs: inputURLs,
        fingerprints: Self.fingerprints(inputURLs),
        runRoot: FilesystemPath.canonicalURL(request.outputDirectory),
        tool: tool,
        appVersion: Self.appVersion("CFBundleShortVersionString"),
        appBuild: Self.appVersion("CFBundleVersion"),
        outputRootConfirmationUsed: outputRootConfirmationUsed
      )
    }.value
  }

  func write(start: Start, job: JobRecord) throws -> Artifact {
    let root = FilesystemPath.canonicalURL(job.runDirectory)
    guard root == start.runRoot else { throw CocoaError(.fileWriteInvalidFileName) }
    let updatedURLs = start.inputPaths.map(FilesystemPath.canonicalURL)
    let after = Self.fingerprints(zip(start.inputURLs, updatedURLs).map { $0 == $1 ? $0 : nil })
    let inputs = zip(start.fingerprints, after).enumerated().map { index, pair in
      let (before, after) = pair
      let unchanged = before.sha256.flatMap { digest in after.sha256.map { $0 == digest } }
      return JobRunProvenance.Input(
        id: "input-\(index + 1)", before: before, after: after, contentUnchanged: unchanged
      )
    }

    let stagedInputs = root.appendingPathComponent("inputs", isDirectory: true)
    let inputURLs = Set(start.inputURLs + updatedURLs)
    let inputDirectories = zip(start.inputURLs, start.fingerprints).compactMap { url, digest in
      digest.state == .directory ? url : nil
    }
    let outputURLs = Set(job.artifacts.map { FilesystemPath.canonicalURL($0.path) }).filter { url in
      Self.isInside(url, root: root) && !Self.isInside(url, root: stagedInputs)
        && url != root.appendingPathComponent(JobRunProvenance.filename)
        && !inputURLs.contains(url) && !inputDirectories.contains { Self.isInside(url, root: $0) }
    }
    let outputs = Self.fingerprints(outputURLs.sorted { $0.path < $1.path }).enumerated().map { index, digest in
      JobRunProvenance.Output(id: "output-\(index + 1)", fingerprint: digest)
    }
    let fingerprints = inputs.flatMap { [$0.before, $0.after] } + outputs.map(\.fingerprint)
    var limits: [JobRunProvenance.Limit] = [
      .attachedInputScope, .localArgumentsRequired, .runtimeAndDependencyVersionsNotCaptured,
      .backendAndModelNotCaptured, .furtherConsentEvidenceRequired,
    ]
    if fingerprints.contains(where: { $0.state == .directory }) { limits.append(.directoryContentsNotCaptured) }
    if fingerprints.contains(where: { $0.state != .recorded }) { limits.append(.incompleteFingerprints) }
    if inputs.contains(where: { $0.contentUnchanged == false }) { limits.append(.inputContentChanged) }

    let provenance = JobRunProvenance(
      schemaVersion: 1, jobID: job.id, appVersion: start.appVersion, appBuild: start.appBuild,
      tool: start.tool, status: job.status, exitCode: job.exitCode, startedAt: job.startedAt,
      finishedAt: job.finishedAt, outputRootConfirmationUsed: start.outputRootConfirmationUsed,
      inputs: inputs, outputs: outputs, limits: limits
    )
    let data = try JSONEncoder.scientificWorkbench.encode(provenance)
    let destination = root.appendingPathComponent(JobRunProvenance.filename)
    let staging = root.appendingPathComponent(".run-provenance-\(UUID().uuidString).tmp")
    try data.write(to: staging, options: .withoutOverwriting)
    defer { try? FileManager.default.removeItem(at: staging) }
    try FileManager.default.moveItem(at: staging, to: destination)
    return Artifact(path: destination.path, relativePath: JobRunProvenance.filename,
                    byteCount: Int64(data.count), artifactType: "metadata_json")
  }

  private static func fingerprints(_ urls: [URL?]) -> [RunFileFingerprint] {
    // Each pass has its own budget so a large input cannot hide the outputs.
    var remaining = RunFileFingerprint.defaultReadBudget
    return urls.map { url in
      guard let url else { return RunFileFingerprint(state: .changed, byteCount: nil, sha256: nil) }
      let digest = RunFileFingerprint.read(url, maximumBytes: remaining)
      if let size = digest.byteCount, size >= 0, size <= remaining { remaining -= size }
      return digest
    }
  }

  private static func digest(_ url: URL, inside root: URL) -> String? {
    let resolved = FilesystemPath.canonicalURL(url.path)
    guard isInside(resolved, root: root) else { return nil }
    return RunFileFingerprint.read(resolved, maximumBytes: RunFileFingerprint.defaultReadBudget).sha256
  }

  private static func isInside(_ url: URL, root: URL) -> Bool {
    url.path.hasPrefix(root.path.hasSuffix("/") ? root.path : root.path + "/")
  }

  private static func safeIdentifier(_ value: String, secrets: [String]) -> String? {
    guard value.range(of: #"^[a-z][a-z0-9_.-]{0,127}$"#, options: .regularExpression) != nil,
          SecretsRedactor.redact(value, secrets: secrets) == value else { return nil }
    return value
  }

  private static func appVersion(_ key: String) -> String? {
    guard let value = Bundle.main.object(forInfoDictionaryKey: key) as? String,
          value.range(of: #"^[0-9]+(?:\.[0-9]+){0,3}$"#, options: .regularExpression) != nil else { return nil }
    return value
  }

  private static func isHexDigit(_ byte: UInt8) -> Bool {
    (48...57).contains(byte) || (65...70).contains(byte) || (97...102).contains(byte)
  }
}
