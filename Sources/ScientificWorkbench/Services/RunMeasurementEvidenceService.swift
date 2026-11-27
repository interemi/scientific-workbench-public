import CryptoKit
import Foundation

struct RunMeasurementEvidence: Sendable {
  let source: String
  let sha256: String
  let summary: ScientificMeasurementSummary
}

struct RunMeasurementEvidenceService {
  static func isSummary(_ artifact: Artifact) -> Bool {
    artifact.artifactType == "summary_json" || artifact.relativePath == "summary.json"
  }

  func read(for job: JobRecord) -> Result<RunMeasurementEvidence, RunEvidenceUnavailable> {
    guard job.status == .succeeded else { return .failure(.unfinishedJob) }
    let registered = job.artifacts.filter(Self.isSummary)
    let standard = registered.filter { $0.relativePath == "summary.json" }
    let candidates = standard.isEmpty ? registered : standard
    guard let summary = candidates.first else { return .failure(.missingSummary) }
    guard candidates.count == 1 else { return .failure(.ambiguousSummary) }
    return read(summary, for: job)
  }

  func read(_ artifact: Artifact, for job: JobRecord) -> Result<RunMeasurementEvidence, RunEvidenceUnavailable> {
    guard Self.isSummary(artifact) else { return .failure(.missingSummary) }
    do {
      let output = try RunOutputEvidence(artifact: artifact, job: job)
      guard let data = RunOutputEvidence.readJSON(at: output.url) else { return .failure(.missingSummary) }
      let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
      guard output.matches(.init(state: .recorded, byteCount: Int64(data.count), sha256: digest)) else {
        return .failure(.changedArtifact)
      }
      guard let summary = ScientificMeasurementSummary.decode(data, capabilityID: job.capabilityID),
            summary.evidenceOutcome != nil, !summary.measurements.isEmpty || !summary.diagnostics.isEmpty else {
        return .failure(.invalidSummary)
      }
      return .success(RunMeasurementEvidence(source: output.source, sha256: digest, summary: summary))
    } catch RunEvidenceUnavailable.missingArtifact {
      return .failure(.missingSummary)
    } catch let error as RunEvidenceUnavailable {
      return .failure(error)
    } catch {
      return .failure(.missingProvenance)
    }
  }
}
