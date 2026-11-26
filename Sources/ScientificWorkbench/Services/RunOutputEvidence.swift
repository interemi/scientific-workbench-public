import Foundation

enum RunEvidenceUnavailable: Error, Sendable {
  case unfinishedJob, missingArtifact, missingSummary, ambiguousSummary, missingProvenance, changedArtifact, invalidSummary
  case invalidTableRange, noNumericCells

  var reason: String {
    switch self {
    case .unfinishedJob: "The linked job did not succeed."
    case .missingArtifact: "The registered artifact is missing or unreadable."
    case .missingSummary: "The registered summary is missing or unreadable."
    case .ambiguousSummary: "Multiple registered summaries match. Select a single artifact to review."
    case .missingProvenance: "The job has no readable provenance record matching this run and tool."
    case .changedArtifact: "The current artifact does not match a recorded output hash."
    case .invalidSummary: "The summary did not contain usable measurements or diagnostics for this tool."
    case .invalidTableRange: "The selected table range is unavailable or exceeds the supported size."
    case .noNumericCells: "The selected range contains no retained finite numeric cells."
    }
  }
}

struct RunOutputEvidence {
  let url: URL
  let source: String
  private let outputs: [JobRunProvenance.Output]

  init(artifact: Artifact, job: JobRecord) throws {
    guard job.status == .succeeded else { throw RunEvidenceUnavailable.unfinishedJob }
    let inspection = ArtifactInspectionService()
    guard job.artifacts.contains(artifact), let preview = inspection.previewURL(for: artifact, in: job) else {
      throw RunEvidenceUnavailable.missingArtifact
    }
    let root = FilesystemPath.canonicalURL(job.runDirectory)
    let prefix = root.path.hasSuffix("/") ? root.path : root.path + "/"
    url = FilesystemPath.canonicalURL(preview.path)
    guard url.path.hasPrefix(prefix) else { throw RunEvidenceUnavailable.missingArtifact }
    source = String(url.path.dropFirst(prefix.count))

    let name = JobRunProvenance.filename
    let record = Artifact(path: root.appendingPathComponent(name).path, relativePath: name, byteCount: 0)
    guard let recordURL = inspection.previewURL(for: record, in: job),
          let data = Self.readJSON(at: recordURL),
          let provenance = try? JSONDecoder.scientificWorkbench.decode(JobRunProvenance.self, from: data),
          provenance.schemaVersion == 1, provenance.jobID == job.id,
          provenance.status == .succeeded, provenance.tool.capabilityID == job.capabilityID else {
      throw RunEvidenceUnavailable.missingProvenance
    }
    outputs = provenance.outputs
  }

  func matches(_ fingerprint: RunFileFingerprint) -> Bool {
    fingerprint.state == .recorded && outputs.contains { $0.fingerprint == fingerprint }
  }

  static func readJSON(at url: URL) -> Data? {
    guard let captured = BoundedProcessOutput.read(at: url, maximumBytes: ScientificMeasurementSummary.maximumBytes),
          !captured.wasTruncated else { return nil }
    let data = Data(captured.text.utf8)
    return data.count == captured.totalBytes ? data : nil
  }
}
