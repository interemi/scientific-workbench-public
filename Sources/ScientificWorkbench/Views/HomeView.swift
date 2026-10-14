import SwiftUI
import UniformTypeIdentifiers

struct HomeView: View {
  @ObservedObject var store: WorkbenchStore
  @State private var isDropTargeted = false
  @State private var pendingExampleKind: FirstRunExampleKind?
  @State private var isReplacingInputSelection = false
  @State private var showMoreExamples = false
  @State private var showWorkbenchDetails = false

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        header
        if !store.setupChecklistIsReady {
          SetupChecklistCard(store: store, compact: false)
        }
        resumeRun
        taskLauncher
        moreExamples
        dropZone
        inputList
        DisclosureGroup("Workbench details", isExpanded: $showWorkbenchDetails) {
          VStack(alignment: .leading, spacing: 18) {
            readinessGrid
            recentJobs
          }
          .padding(.top, 12)
        }
      }
      .padding(.vertical, 28)
      .padding(.horizontal, 36)
      .frame(maxWidth: 1080, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .navigationTitle("Scientific Workbench")
    .confirmationDialog(
      "Replace the current input selection?",
      isPresented: $isReplacingInputSelection
    ) {
      Button("Use Synthetic Example") {
        if let pendingExampleKind {
          store.prepareFirstRunExample(pendingExampleKind)
        }
        pendingExampleKind = nil
      }
      Button("Cancel", role: .cancel) {
        pendingExampleKind = nil
      }
    } message: {
      Text("The selected files will be removed from this session's input list. They will not be changed or deleted on disk.")
    }
  }

  private var header: some View {
    VStack(alignment: .leading, spacing: 8) {
      Text("Scientific Workbench")
        .font(.largeTitle)
        .fontWeight(.semibold)
      Text("A local macOS control center for the installed scientific-data-analysis skill.")
        .foregroundStyle(.secondary)
    }
  }

  @ViewBuilder
  private var resumeRun: some View {
    if let job = store.jobs.first {
      VStack(alignment: .leading, spacing: 12) {
        Label("Continue your work", systemImage: "arrow.uturn.forward.circle")
          .font(.title3)
          .fontWeight(.semibold)
        HStack(alignment: .top) {
          VStack(alignment: .leading, spacing: 4) {
            Text(job.capabilityLabel)
              .fontWeight(.medium)
            Text("Last run: \(DateFormatters.timestamp.string(from: job.createdAt)). Review its status, evidence, and next steps before running anything again.")
              .font(.caption)
              .foregroundStyle(.secondary)
          }
          Spacer(minLength: 12)
          StatusBadge(status: job.displaySeverity)
        }
        Button {
          store.openJob(job)
        } label: {
          Label(job.status == .running || job.status == .queued ? "View active run" : "Open latest run", systemImage: "arrow.right")
        }
        .buttonStyle(.borderedProminent)
        .accessibilityIdentifier("home.open-latest-run")
      }
      .padding(18)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }
  }

  private var taskLauncher: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("Start a task")
        .font(.title3)
        .fontWeight(.semibold)
      Text("Choose the work you want to do. Open the task to review your own inputs, or prepare a safe synthetic example first. Nothing runs until you confirm it.")
        .font(.callout)
        .foregroundStyle(.secondary)

      LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: 12)], spacing: 12) {
        ForEach([FirstRunExampleKind.table, .fits, .mixed]) { kind in
          VStack(alignment: .leading, spacing: 10) {
            Text(kind.launcherTitle)
              .font(.headline)
            Text(kind.launcherDetail)
              .font(.caption)
              .foregroundStyle(.secondary)
            Spacer(minLength: 0)
            HStack {
              Button("Open task") {
                store.openFirstRunTask(kind)
              }
              .buttonStyle(.borderedProminent)
              .accessibilityLabel("Open \(kind.launcherTitle) task")
              .accessibilityIdentifier("home.open-task.\(kind.id)")

              Button("Try example") {
                requestExample(kind)
              }
              .accessibilityLabel("Prepare \(kind.title) example")
              .accessibilityIdentifier("home.prepare-example.\(kind.id)")
              .disabled(store.hasActiveJob)
            }
            Button("Read task guide") { store.openFirstRunGuide(for: kind) }
              .font(.caption)
              .accessibilityLabel("Read the \(kind.launcherTitle) task guide")
              .accessibilityIdentifier("home.open-task-guide.\(kind.id)")
          }
          .padding(14)
          .frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
          .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
      }

      if let prepared = store.preparedFirstRunExample {
        Divider()
        Text("Prepared \(prepared.kind.title) in \(prepared.directory.path).")
          .font(.caption)
          .textSelection(.enabled)
        Button("Reset Example (New Copy)") {
          requestExample(prepared.kind)
        }
        .accessibilityIdentifier("home.reset-example")
        .disabled(store.hasActiveJob)
        Text("Reset creates a new copy and preserves all earlier example folders.")
          .font(.caption)
          .foregroundStyle(.secondary)
      }

      if let error = store.firstRunExampleError {
        Label(error, systemImage: "exclamationmark.triangle")
          .font(.caption)
          .foregroundStyle(.orange)
      }
    }
    .padding(18)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }

  private var moreExamples: some View {
    DisclosureGroup("More synthetic examples", isExpanded: $showMoreExamples) {
      VStack(alignment: .leading, spacing: 12) {
        Text("Examples create new local copies and preserve earlier example folders. They need no cloud account or optional backend.")
          .font(.caption)
          .foregroundStyle(.secondary)
        ForEach([FirstRunExampleKind.spectrum, .document]) { kind in
          HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
              Text(kind.title).fontWeight(.medium)
              Text(kind.detail).font(.caption).foregroundStyle(.secondary)
              Text("Expect: \(kind.expectedResult)").font(.caption)
            }
            Spacer(minLength: 12)
            Button("Prepare") {
              requestExample(kind)
            }
            .accessibilityLabel("Prepare \(kind.title) example")
            .accessibilityIdentifier("home.prepare-example.\(kind.id)")
            .disabled(store.hasActiveJob)
          }
        }
      }
      .padding(.top, 12)
    }
  }

  private func requestExample(_ kind: FirstRunExampleKind) {
    if !store.inputPaths.isEmpty,
       store.inputPaths != store.preparedFirstRunExample?.inputPaths {
      pendingExampleKind = kind
      isReplacingInputSelection = true
    } else {
      store.prepareFirstRunExample(kind)
    }
  }

  private var dropZone: some View {
    VStack(spacing: 12) {
      Image(systemName: "tray.and.arrow.down")
        .font(.system(size: 34))
        .foregroundStyle(.secondary)
      Text("Drop files or folders here")
        .font(.title3)
        .fontWeight(.medium)
      Text("Inputs stay untouched. Runs write to the configured output folder.")
        .font(.caption)
        .foregroundStyle(.secondary)
      HStack(spacing: 10) {
        Button {
          store.chooseInputFiles()
        } label: {
          Label("Add Files", systemImage: "doc.badge.plus")
        }
        .accessibilityIdentifier("home.add-files")

        Button {
          store.chooseInputFolders()
        } label: {
          Label("Add Folder", systemImage: "folder.badge.plus")
        }
        .accessibilityIdentifier("home.add-folder")
      }
    }
    .frame(maxWidth: .infinity, minHeight: 160)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    .overlay {
      if isDropTargeted {
        RoundedRectangle(cornerRadius: 8)
          .fill(Color.blue.opacity(0.12))
      }
    }
    .overlay(
      RoundedRectangle(cornerRadius: 8)
        .strokeBorder(isDropTargeted ? Color.blue : Color.secondary.opacity(0.2), style: StrokeStyle(lineWidth: 1, dash: [6, 4]))
    )
    .onDrop(of: [UTType.fileURL.identifier], isTargeted: $isDropTargeted) { providers in
      handleDrop(providers)
    }
  }

  private var inputList: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack {
        Text("Inputs")
          .font(.headline)
        Spacer()
        Button("Clear") {
          store.clearInputs()
        }
        .disabled(store.inputPaths.isEmpty)
        .accessibilityIdentifier("home.clear-inputs")
      }

      if store.inputPaths.isEmpty {
        Text("No inputs yet.")
          .foregroundStyle(.secondary)
      } else {
        ForEach(store.inputPaths, id: \.self) { path in
          HStack(spacing: 10) {
            Image(systemName: "doc")
              .foregroundStyle(.secondary)
            Text(path)
              .lineLimit(1)
              .truncationMode(.middle)
              .textSelection(.enabled)
            Spacer()
            Button {
              store.removeInputPath(path)
            } label: {
              Image(systemName: "xmark.circle.fill")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .accessibilityLabel("Remove input \(URL(fileURLWithPath: path).lastPathComponent)")
            .accessibilityHint("Removes this item from the current input selection without deleting it from disk.")
          }
          .padding(8)
          .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
      }
    }
  }

  private var readinessGrid: some View {
    LazyVGrid(
      columns: [GridItem(.adaptive(minimum: 260, maximum: 360), spacing: 18, alignment: .leading)],
      alignment: .leading,
      spacing: 14
    ) {
      SummaryTile(title: "Environment", value: store.environmentStatus.status.uppercased(), systemImage: "checkmark.seal")
      SummaryTile(title: "Capabilities", value: "\(store.userCapabilities.count)", systemImage: "square.grid.2x2")
      SummaryTile(title: "Maintenance", value: "\(store.maintainerCapabilities.count)", systemImage: "wrench.and.screwdriver")
      SummaryTile(title: "Output Root", value: URL(fileURLWithPath: store.outputRootPath).lastPathComponent, systemImage: "folder")
      SummaryTile(title: "Jobs", value: "\(store.jobs.count)", systemImage: "list.bullet.rectangle")
      SummaryTile(title: "Inputs", value: "\(store.inputPaths.count)", systemImage: "paperclip")
    }
  }

  private var recentJobs: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Recent Jobs")
        .font(.headline)
      if store.jobs.isEmpty {
        Text("Runs will appear here after you launch a capability.")
          .foregroundStyle(.secondary)
      } else {
        ForEach(store.jobs.prefix(5)) { job in
          Button {
            store.openJob(job)
          } label: {
            HStack {
              StatusBadge(status: job.displaySeverity)
              Text(job.capabilityLabel)
                .lineLimit(1)
              Spacer()
              Text(DateFormatters.timestamp.string(from: job.createdAt))
                .font(.caption)
                .foregroundStyle(.secondary)
            }
          }
          .buttonStyle(.plain)
          .padding(8)
          .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
      }
    }
  }

  private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
    for provider in providers {
      provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
        let url: URL?
        if let data = item as? Data {
          url = URL(dataRepresentation: data, relativeTo: nil)
        } else {
          url = item as? URL
        }

        if let url {
          Task { @MainActor in
            store.addInputPath(url.path)
          }
        }
      }
    }
    return true
  }
}

struct SummaryTile: View {
  let title: String
  let value: String
  let systemImage: String

  var body: some View {
    HStack(spacing: 12) {
      Image(systemName: systemImage)
        .foregroundStyle(.secondary)
        .frame(width: 20)
      VStack(alignment: .leading, spacing: 2) {
        Text(title)
          .font(.caption)
          .foregroundStyle(.secondary)
        Text(value)
          .font(.headline)
          .lineLimit(1)
      }
      Spacer(minLength: 0)
    }
    .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
    .padding(14)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }
}
