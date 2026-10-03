import SwiftUI
import UniformTypeIdentifiers

struct HomeView: View {
  @ObservedObject var store: WorkbenchStore
  @State private var isDropTargeted = false
  @State private var pendingExampleKind: FirstRunExampleKind?
  @State private var isReplacingInputSelection = false

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        header
        SetupChecklistCard(store: store, compact: false)
        firstRunExamples
        dropZone
        inputList
        readinessGrid
        recentJobs
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

  private var firstRunExamples: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("Try a synthetic example")
        .font(.title3)
        .fontWeight(.semibold)
      Text("Create a fresh local copy, review the expected result, then run its suggested capability. These examples require no Ollama model, cloud account, or optional backend.")
        .font(.callout)
        .foregroundStyle(.secondary)

      ForEach(FirstRunExampleKind.allCases) { kind in
        HStack(alignment: .top, spacing: 12) {
          VStack(alignment: .leading, spacing: 4) {
            Text(kind.title)
              .fontWeight(.medium)
            Text(kind.detail)
              .font(.caption)
              .foregroundStyle(.secondary)
            Text("Expect: \(kind.expectedResult)")
              .font(.caption)
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
          HStack {
            StatusBadge(status: job.displaySeverity)
            Text(job.capabilityLabel)
              .lineLimit(1)
            Spacer()
            Text(DateFormatters.timestamp.string(from: job.createdAt))
              .font(.caption)
              .foregroundStyle(.secondary)
          }
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
