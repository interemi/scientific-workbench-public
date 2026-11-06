import SwiftUI

struct ArtifactComparisonSource: Identifiable {
  let id = UUID()
  let job: JobRecord
  let artifact: Artifact
}

struct ArtifactComparisonSheet: View {
  @Environment(\.dismiss) private var dismiss
  @ObservedObject var store: WorkbenchStore
  let source: ArtifactComparisonSource

  @State private var comparisonJobID: UUID?
  @State private var comparisonArtifactID: UUID?

  private let inspectionService = ArtifactInspectionService()

  private var candidateJobs: [JobRecord] {
    store.jobs.filter { !candidates(in: $0).isEmpty }
  }

  private var comparisonJob: JobRecord? {
    candidateJobs.first { $0.id == comparisonJobID }
  }

  private var comparisonArtifact: Artifact? {
    comparisonJob?.artifacts.first { $0.id == comparisonArtifactID }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack {
        Text("Compare two artifacts")
          .font(.title2)
          .fontWeight(.semibold)
        Spacer()
        Button("Done") { dismiss() }
      }

      HStack(spacing: 16) {
        Picker("Compare with run", selection: $comparisonJobID) {
          ForEach(candidateJobs) { job in
            Text("\(job.capabilityLabel) · \(DateFormatters.timestamp.string(from: job.createdAt))")
              .tag(Optional(job.id))
          }
        }
        .accessibilityIdentifier("results.compare-run")

        Picker("Artifact", selection: $comparisonArtifactID) {
          if let comparisonJob {
            ForEach(candidates(in: comparisonJob)) { artifact in
              Text(store.redactedPreviewText(artifact.relativePath))
                .tag(Optional(artifact.id))
            }
          }
        }
        .accessibilityIdentifier("results.compare-target")
      }

      if let comparisonJob, let comparisonArtifact {
        Text(inspectionService.comparisonSummary(
          inspectionService.inspect(source.artifact, in: source.job),
          inspectionService.inspect(comparisonArtifact, in: comparisonJob)
        ))
        .font(.caption)
        .foregroundStyle(.secondary)

        HStack(alignment: .top, spacing: 10) {
          ArtifactPreview(store: store, job: source.job, artifact: source.artifact)
            .frame(minWidth: 430, maxWidth: .infinity)
          Divider()
          ArtifactPreview(store: store, job: comparisonJob, artifact: comparisonArtifact)
            .frame(minWidth: 430, maxWidth: .infinity)
        }
      } else {
        ContentUnavailableView(
          "No comparison target",
          systemImage: "square.split.2x1",
          description: Text("Select another retained artifact from this run or a different run.")
        )
      }
    }
    .padding(20)
    .frame(minWidth: 1_000, minHeight: 680)
    .onAppear {
      let preferredJob = candidateJobs.first { job in
        job.id != source.job.id && candidates(in: job).contains {
          $0.relativePath == source.artifact.relativePath
        }
      } ?? candidateJobs.first
      comparisonJobID = preferredJob?.id
      comparisonArtifactID = preferredJob.flatMap { preferredArtifact(in: $0)?.id }
    }
    .onChange(of: comparisonJobID) {
      comparisonArtifactID = comparisonJob.flatMap { preferredArtifact(in: $0)?.id }
    }
  }

  private func candidates(in job: JobRecord) -> [Artifact] {
    job.artifacts.filter { $0.id != source.artifact.id }
  }

  private func preferredArtifact(in job: JobRecord) -> Artifact? {
    let available = candidates(in: job)
    return available.first { $0.relativePath == source.artifact.relativePath }
      ?? available.first { $0.artifactType == source.artifact.artifactType }
      ?? available.first
  }
}

struct ArtifactMetadataView: View {
  @ObservedObject var store: WorkbenchStore
  let job: JobRecord
  let artifact: Artifact
  let inspection: ArtifactInspection

  var body: some View {
    VStack(alignment: .leading, spacing: 5) {
      Text("\(inspection.role.rawValue) · \(typeName) · \(sizeName)")
        .fontWeight(.medium)
      Text("Produced by \(store.redactedPreviewText(job.capabilityLabel)) in run \(job.id.uuidString.prefix(8)).")
      Text("File modified: \(inspection.modifiedAt.map(DateFormatters.timestamp.string(from:)) ?? "Unavailable")")
      if let recordedByteCount = inspection.recordedByteCount {
        Text("Manifest size: \(ByteCountFormatter.string(fromByteCount: recordedByteCount, countStyle: .file))")
      }
      if let hash = inspection.recordedSHA256 {
        Text("Recorded SHA-256: \(hash)")
          .font(.system(.caption2, design: .monospaced))
          .textSelection(.enabled)
      } else {
        Text("Recorded SHA-256: not available")
      }
      if let current = inspection.currentByteCount,
         let recorded = inspection.recordedByteCount,
         current != recorded {
        Text("Current size differs from the manifest. Inspect the evidence before using this result.")
          .foregroundStyle(.orange)
      }
    }
    .font(.caption)
    .foregroundStyle(.secondary)
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(10)
    .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
  }

  private var typeName: String {
    let type = artifact.artifactType ?? artifact.url.pathExtension.uppercased()
    return type.isEmpty ? "Unknown type" : type
  }

  private var sizeName: String {
    guard let byteCount = inspection.currentByteCount else { return "Size unavailable" }
    return ByteCountFormatter.string(fromByteCount: byteCount, countStyle: .file)
  }
}
