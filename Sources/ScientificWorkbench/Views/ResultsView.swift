import SwiftUI

struct ResultsView: View {
  @ObservedObject var store: WorkbenchStore
  @State private var pendingMixedFollowUpJob: JobRecord?
  @State private var isReplacingInputSelection = false
  @State private var comparisonSource: ArtifactComparisonSource?

  private let inspectionService = ArtifactInspectionService()

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

          JobEvidenceStagesView(job: job, compact: true)
            .padding(.horizontal)

          JobIdentityView(store: store, job: job)
            .padding(.horizontal)

          if store.canPrepareMixedDataFollowUp(for: job) {
            VStack(alignment: .leading, spacing: 6) {
              Button("Inspect folder data") {
                if !store.inputPaths.isEmpty && store.inputPaths != job.requestInputPaths {
                  pendingMixedFollowUpJob = job
                  isReplacingInputSelection = true
                } else {
                  store.prepareMixedDataFollowUp(for: job)
                }
              }
              .accessibilityIdentifier("results.mixed-data-follow-up")
              .disabled(store.hasActiveJob)
              Text("Prepares a separate table and data inventory with the same folder. Review it before running; no combined scientific conclusion is produced.")
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal)
          }

          let relatedJobs = store.relatedFirstRunJobs(to: job)
          if !relatedJobs.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
              Text("Related runs for this input")
                .font(.caption)
                .fontWeight(.semibold)
              ForEach(relatedJobs.prefix(3)) { related in
                Button("\(related.capabilityLabel) · \(related.status.title)") {
                  store.selectedJobID = related.id
                }
                .accessibilityIdentifier("results.related-job.\(related.id.uuidString)")
              }
            }
            .padding(.horizontal)
          }

          if let artifact = selectedArtifact {
            Button {
              comparisonSource = ArtifactComparisonSource(job: job, artifact: artifact)
            } label: {
              Label("Compare two artifacts", systemImage: "square.split.2x1")
            }
            .disabled(!store.jobs.contains { candidate in
              candidate.artifacts.contains { $0.id != artifact.id }
            })
            .accessibilityIdentifier("results.compare-artifacts")
            .padding(.horizontal)
          }

          if job.artifacts.isEmpty {
            ContentUnavailableView {
              Label("No Recorded Artifacts", systemImage: "doc.questionmark")
            } description: {
              Text("Inspect the job status and logs, or refresh its run bundle after the process stops.")
            }
          } else {
            List(selection: artifactSelection) {
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
                    Text(inspectionService.role(for: artifact).rawValue)
                      .font(.caption2)
                      .foregroundStyle(.secondary)
                  }
                }
                .tag(Optional(artifact.id))
              }
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
        if let job = store.selectedJob {
          ArtifactPreview(store: store, job: job, artifact: artifact)
        }
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
      comparisonSource = nil
      selectPreferredArtifact()
    }
    .onChange(of: store.selectedJob?.artifacts.map(\.id)) {
      selectPreferredArtifact()
    }
    .sheet(item: $comparisonSource) { source in
      ArtifactComparisonSheet(store: store, source: source)
    }
    .confirmationDialog(
      "Replace the current input selection?",
      isPresented: $isReplacingInputSelection
    ) {
      Button("Use This Job's Folder") {
        if let pendingMixedFollowUpJob {
          store.prepareMixedDataFollowUp(for: pendingMixedFollowUpJob)
        }
        pendingMixedFollowUpJob = nil
      }
      Button("Cancel", role: .cancel) {
        pendingMixedFollowUpJob = nil
      }
    } message: {
      Text("The current session selection will change to this job's folder. No input file will be changed or deleted.")
    }
  }

  private var selectedArtifact: Artifact? {
    guard
      let job = store.selectedJob,
      let selectedArtifactID = store.selectedResultArtifactID(for: job)
    else {
      return nil
    }
    return job.artifacts.first { $0.id == selectedArtifactID }
  }

  private var artifactSelection: Binding<UUID?> {
    let job = store.selectedJob
    return Binding(
      get: { job.flatMap { store.selectedResultArtifactID(for: $0) } },
      set: { artifactID in
        if let job {
          store.selectResultArtifact(artifactID, for: job)
        }
      }
    )
  }

  private func icon(for artifact: Artifact) -> String {
    switch artifact.artifactType {
    case "preview_png", "app_preview": return "photo"
    case "edited_document": return "doc.badge.checkmark"
    case "manifest_json", "summary_json", "metadata_json": return "curlybraces"
    case "table_csv", "table_ecsv": return "tablecells"
    case "report_md", "log_txt": return "doc.text"
    case "handoff_bundle": return "shippingbox"
    case "fits_product", "fits_visual": return "waveform.path.ecg.rectangle"
    default: break
    }
    switch artifact.url.pathExtension.lowercased() {
    case "png", "jpg", "jpeg", "tif", "tiff": return "photo"
    case "pdf": return "doc.richtext"
    case "json": return "curlybraces"
    case "csv", "tsv", "ecsv": return "tablecells"
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
    guard let job = store.selectedJob else { return }
    store.selectPreferredResultArtifact(for: job)
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
        Text(job.artifacts.isEmpty
          ? "No artifact is recorded for this job. Inspect its logs and recovery advice; a running job may still have partial files in its separate run folder."
          : "Select an artifact to preview it, or reveal the run folder for the full bundle.")
          .foregroundStyle(.secondary)

        if let shortSummary = job.shortSummary {
          Text(shortSummary)
            .font(.headline)
            .textSelection(.enabled)
        }

        HStack {
          if job.artifacts.isEmpty {
            Button("Open Job") { store.selectedSection = .jobs }
          }
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
  let job: JobRecord
  let artifact: Artifact
  @State private var payload: ArtifactPreviewPayload?
  private let previewService = ArtifactPreviewService()
  private let inspectionService = ArtifactInspectionService()

  var body: some View {
    let inspection = inspectionService.inspect(artifact, in: job)
    return VStack(alignment: .leading, spacing: 12) {
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
          store.revealArtifact(artifact)
        } label: {
          Label("Reveal", systemImage: "folder")
        }
        .accessibilityLabel("Reveal artifact \(store.redactedPreviewText(artifact.relativePath))")
        .accessibilityHint("Shows the selected artifact in Finder.")
        .disabled(!inspection.canPreview)
      }

      ArtifactMetadataView(store: store, job: job, artifact: artifact, inspection: inspection)
      preview
    }
    .padding(24)
    .task(id: artifact.id) {
      let currentInspection = inspectionService.inspect(artifact, in: job)
      payload = currentInspection.canPreview
        ? previewService.load(artifact: artifact, redact: store.redactedPreviewText)
        : ArtifactPreviewPayload(
          kind: .unavailable,
          title: "Preview unavailable",
          note: "The artifact is missing or resolves outside its recorded run folder."
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

        if artifact.artifactType == "preview_png",
           job.capabilityID == "inspect_fits" {
          if let input = job.requestInputPaths.first,
             FirstRunExampleService.isGeneratedFITS(at: input) {
            Text("Synthetic TAN WCS: horizontal right ascension and vertical declination in ICRS, one arcsecond per pixel; pixel unit: adu.")
              .font(.caption)
          }
          Text("Display-scaled quicklook only. Check summary.json for WCS and units when present; this image does not establish astrometric calibration.")
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
