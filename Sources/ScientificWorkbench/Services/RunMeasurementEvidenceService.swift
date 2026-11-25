import CryptoKit
import Foundation

struct RunMeasurementEvidence: Sendable {
  let source: String
  let sha256: String
  let summary: ScientificMeasurementSummary
}

struct RunMeasurementEvidenceService {
  enum Unavailable: Error, Sendable {
    case unfinishedJob, missingSummary, ambiguousSummary, missingProvenance, changedSummary, invalidSummary

    var reason: String {
      switch self {
      case .unfinishedJob: "The linked job did not succeed."
      case .missingSummary: "The registered summary is missing or unreadable."
      case .ambiguousSummary: "Multiple registered summaries match. Select a single artifact to review."
      case .missingProvenance: "The job has no readable provenance record matching this run and tool."
      case .changedSummary: "The current summary does not match a recorded output hash."
      case .invalidSummary: "The summary did not contain usable measurements or diagnostics for this tool."
      }
    }
  }

  private let inspection = ArtifactInspectionService()

  func read(for job: JobRecord) -> Result<RunMeasurementEvidence, Unavailable> {
    guard job.status == .succeeded else { return .failure(.unfinishedJob) }
    let registered = job.artifacts.filter { $0.artifactType == "summary_json" || $0.relativePath == "summary.json" }
    let standard = registered.filter { $0.relativePath == "summary.json" }
    let candidates = standard.isEmpty ? registered : standard
    guard let summary = candidates.first else { return .failure(.missingSummary) }
    guard candidates.count == 1 else { return .failure(.ambiguousSummary) }
    return read(summary, for: job)
  }

  func read(_ artifact: Artifact, for job: JobRecord) -> Result<RunMeasurementEvidence, Unavailable> {
    guard job.status == .succeeded else { return .failure(.unfinishedJob) }
    guard job.artifacts.contains(artifact),
          artifact.artifactType == "summary_json" || artifact.relativePath == "summary.json",
          let preview = inspection.previewURL(for: artifact, in: job) else { return .failure(.missingSummary) }
    let root = FilesystemPath.canonicalURL(job.runDirectory)
    let url = FilesystemPath.canonicalURL(preview.path)
    let prefix = root.path.hasSuffix("/") ? root.path : root.path + "/"
    guard url.path.hasPrefix(prefix), let data = readData(at: url) else { return .failure(.missingSummary) }
    let provenanceName = JobRunProvenance.filename
    let provenanceFile = Artifact(path: root.appendingPathComponent(provenanceName).path,
                                  relativePath: provenanceName, byteCount: 0)
    guard let provenanceURL = inspection.previewURL(for: provenanceFile, in: job),
          let provenanceData = readData(at: provenanceURL),
          let provenance = try? JSONDecoder.scientificWorkbench.decode(JobRunProvenance.self, from: provenanceData),
          provenance.schemaVersion == 1, provenance.jobID == job.id,
          provenance.status == .succeeded, provenance.tool.capabilityID == job.capabilityID else {
      return .failure(.missingProvenance)
    }

    // Hash the same bytes used for parsing so a changed artifact cannot supply a new value.
    let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    guard provenance.outputs.contains(where: {
      $0.fingerprint.state == .recorded && $0.fingerprint.byteCount == Int64(data.count) && $0.fingerprint.sha256 == digest
    }) else { return .failure(.changedSummary) }
    guard let summary = ScientificMeasurementSummary.decode(data, capabilityID: job.capabilityID),
          summary.evidenceOutcome != nil, !summary.measurements.isEmpty || !summary.diagnostics.isEmpty else {
      return .failure(.invalidSummary)
    }
    return .success(RunMeasurementEvidence(source: String(url.path.dropFirst(prefix.count)), sha256: digest, summary: summary))
  }

  private func readData(at url: URL) -> Data? {
    guard let captured = BoundedProcessOutput.read(at: url, maximumBytes: ScientificMeasurementSummary.maximumBytes),
          !captured.wasTruncated else { return nil }
    let data = Data(captured.text.utf8)
    return data.count == captured.totalBytes ? data : nil
  }
}
