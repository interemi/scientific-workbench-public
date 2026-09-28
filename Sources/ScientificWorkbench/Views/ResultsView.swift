import SwiftUI

struct ResultsView: View {
  @ObservedObject var store: WorkbenchStore
  @State private var selectedArtifactID: UUID?

  var body: some View {
    HSplitView {
      VStack(alignment: .leading, spacing: 12) {
        Text("Artifacts")
          .font(.title2)
          .fontWeight(.semibold)
          .padding(.horizontal)
          .padding(.top)

        if let job = store.selectedJob {
          Text(store.redactedPreviewText(job.runDirectory))
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .truncationMode(.middle)
            .padding(.horizontal)

          List(selection: $selectedArtifactID) {
            ForEach(job.artifacts) { artifact in
              HStack {
                Image(systemName: icon(for: artifact))
                  .foregroundStyle(.secondary)
                  .frame(width: 16)
                VStack(alignment: .leading, spacing: 2) {
                  Text(store.redactedPreviewText(artifact.label ?? artifact.relativePath))
                    .lineLimit(1)
                    .truncationMode(.middle)
                  Text(artifactDetail(for: artifact))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
              }
              .tag(Optional(artifact.id))
            }
          }
        } else {
          ContentUnavailableView {
            Label("No Results Yet", systemImage: "doc.richtext")
          } description: {
            Text("Complete a workflow or capability run to inspect its preserved artifacts.")
          } actions: {
            Button("Open Chat") {
              store.selectedSection = .agent
            }
            .accessibilityIdentifier("results.empty.open-chat")
          }
        }
      }
      .frame(minWidth: 340, idealWidth: 390)

      if let artifact = selectedArtifact {
        ArtifactPreview(store: store, artifact: artifact)
      } else if let job = store.selectedJob {
        ResultsSummaryView(store: store, job: job)
      } else {
        ContentUnavailableView {
          Label("Run a Capability", systemImage: "play")
        } description: {
          Text("Results remain linked to their job, run folder, logs, and provenance metadata.")
        } actions: {
          Button("Browse Capabilities") {
            store.selectedSection = .capabilities
          }
          .accessibilityIdentifier("results.empty.open-capabilities")
        }
      }
    }
    .navigationTitle("Results")
    .onAppear {
      selectPreferredArtifact()
    }
    .onChange(of: store.selectedJobID) {
      selectedArtifactID = nil
      selectPreferredArtifact()
    }
  }

  private var selectedArtifact: Artifact? {
    guard
      let selectedArtifactID,
      let artifacts = store.selectedJob?.artifacts
    else {
      return nil
    }
    return artifacts.first { $0.id == selectedArtifactID }
  }

  private func icon(for artifact: Artifact) -> String {
    switch artifact.artifactType {
    case "preview_png", "app_preview": return "photo"
    case "edited_document": return "doc.badge.checkmark"
    case "manifest_json", "summary_json", "metadata_json": return "curlybraces"
    case "table_csv": return "tablecells"
    case "report_md", "log_txt": return "doc.text"
    case "handoff_bundle": return "shippingbox"
    case "fits_product", "fits_visual": return "waveform.path.ecg.rectangle"
    default: break
    }
    switch artifact.url.pathExtension.lowercased() {
    case "png", "jpg", "jpeg", "tif", "tiff": return "photo"
    case "pdf": return "doc.richtext"
    case "json": return "curlybraces"
    case "csv", "tsv": return "tablecells"
    case "md", "txt", "log": return "doc.text"
    default: return "doc"
    }
  }

  private func artifactDetail(for artifact: Artifact) -> String {
    let size = ByteCountFormatter.string(fromByteCount: artifact.byteCount, countStyle: .file)
    guard let artifactType = artifact.artifactType, !artifactType.isEmpty else {
      return size
    }
    return "\(artifactType) - \(size)"
  }

  private func selectPreferredArtifact() {
    guard selectedArtifactID == nil, let job = store.selectedJob else { return }
    let preferredTypes = job.previewArtifactTypes + ["preview_png", "preview_pdf", "app_preview", "report_md", "table_csv"]
    selectedArtifactID = preferredTypes.lazy.compactMap { type in
      job.artifacts.first { $0.artifactType == type }?.id
    }.first ?? job.artifacts.first(where: { $0.primary == true })?.id ?? job.artifacts.first?.id
  }
}

struct ResultsSummaryView: View {
  @ObservedObject var store: WorkbenchStore
  let job: JobRecord

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        HStack {
          Text(job.capabilityLabel)
            .font(.title2)
            .fontWeight(.semibold)
          Spacer()
          StatusBadge(status: job.displaySeverity)
        }
        Text("Select an artifact to preview it, or reveal the run folder for the full bundle.")
          .foregroundStyle(.secondary)

        if let shortSummary = job.shortSummary {
          Text(shortSummary)
            .font(.headline)
            .textSelection(.enabled)
        }

        HStack {
          Button {
            store.revealRunDirectory(job)
          } label: {
            Label("Reveal Run Folder", systemImage: "folder")
          }
          Button {
            store.refreshRunBundle(for: job)
          } label: {
            Label("Refresh", systemImage: "arrow.clockwise")
          }
          Button {
            store.exportJobSupportBundle(job)
          } label: {
            Label("Support Bundle", systemImage: "lifepreserver")
          }
        }

        JobFindingsView(
          warnings: job.warnings,
          errors: job.structuredErrors,
          nextActions: job.nextActions
        )
        LogBlock(title: "stdout", text: job.stdout)
        LogBlock(title: "stderr", text: job.stderr)
      }
      .padding(24)
    }
  }
}

struct ArtifactPreview: View {
  @ObservedObject var store: WorkbenchStore
  let artifact: Artifact
  @State private var payload: ArtifactPreviewPayload?
  private let previewService = ArtifactPreviewService()

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack {
        VStack(alignment: .leading, spacing: 4) {
          Text(store.redactedPreviewText(artifact.relativePath))
            .font(.title2)
            .fontWeight(.semibold)
            .lineLimit(1)
            .truncationMode(.middle)
          Text(store.redactedPreviewText(artifact.path))
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .truncationMode(.middle)
            .textSelection(.enabled)
        }
        Spacer()
        Button {
          store.openArtifact(artifact)
        } label: {
          Label("Open", systemImage: "arrow.up.right.square")
        }
        Button {
          store.revealArtifact(artifact)
        } label: {
          Label("Reveal", systemImage: "folder")
        }
      }

      preview
    }
    .padding(24)
    .task(id: artifact.id) {
      payload = previewService.load(
        artifact: artifact,
        redact: store.redactedPreviewText
      )
    }
  }

  @ViewBuilder
  private var preview: some View {
    if let payload {
      VStack(alignment: .leading, spacing: 10) {
        Text(payload.title)
          .font(.headline)

        if let imageData = payload.imageData, let image = NSImage(data: imageData) {
          Image(nsImage: image)
            .resizable()
            .scaledToFit()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let text = payload.text {
          ScrollView {
            Text(text)
              .font(.system(.caption, design: .monospaced))
              .textSelection(.enabled)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(12)
          }
        } else {
          ContentUnavailableView("Preview unavailable", systemImage: "doc")
        }

        if let note = payload.note {
          Text(note)
            .font(.caption)
            .foregroundStyle(.secondary)
        }
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
      .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    } else {
      ProgressView("Loading preview...")
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
  }
}
