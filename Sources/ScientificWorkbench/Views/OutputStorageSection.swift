import SwiftUI

struct OutputStorageSection: View {
  @ObservedObject var store: WorkbenchStore

  private struct Scope: Equatable {
    let outputRoot: String
    let inputPaths: [String]
    let historyRevision: UInt64
  }

  @State private var requestedScope: Scope?
  @State private var result: (scope: Scope, inventory: RunStorageInventory)?
  @State private var failure: String?

  private var scope: Scope {
    Scope(outputRoot: store.outputRootPath, inputPaths: store.inputPaths, historyRevision: store.jobsRevision)
  }

  var body: some View {
    let currentScope = scope
    let measurement = result?.scope == currentScope ? result?.inventory : nil
    Section("Output Storage") {
      Text("Measure file sizes in the current output folder using the runs listed in Jobs.")
        .font(.callout)
      if let measurement {
        LabeledContent("Retained stdout and stderr", value: formattedSize(measurement.retainedStreamBytes))
          .accessibilityIdentifier("settings.storage.streams")
        LabeledContent("Run logs folder", value: formattedSize(measurement.runLogBytes))
        LabeledContent("Run previews folder", value: formattedSize(measurement.runPreviewBytes))
        Text("\(measurement.measuredFolders) run folders measured. \(measurement.skippedFolders) skipped because they were unavailable or outside the measurement scope.")
          .font(.caption)
          .foregroundStyle(.secondary)
        if measurement.hasUnreadableEntries {
          Label("Some entries could not be read. The totals are partial.", systemImage: "exclamationmark.triangle")
            .font(.caption)
        }
      }
      if requestedScope == currentScope {
        ProgressView("Measuring output storage…")
          .controlSize(.small)
      }
      if let failure {
        Label(failure, systemImage: "exclamationmark.triangle")
          .font(.caption)
      }
      Button(measurement == nil ? "Measure Storage" : "Refresh Measurement") {
        failure = nil
        requestedScope = currentScope
      }
      .disabled(requestedScope != nil || store.isRestoringJobHistory)
      .accessibilityIdentifier("settings.storage.measure")
      RasterPreviewCacheControls()
      Text("The preview cache holds one thumbnail up to \(RasterPreviewLoader.maximumCacheBytes / (1024 * 1024)) MiB. The temporary output limit is \(ProcessRunner.defaultMaximumTemporaryOutputBytesPerStream / (1024 * 1024)) MiB per process stream. Retained logs and saved previews remain with their runs.")
        .font(.caption)
        .foregroundStyle(.secondary)
    }
    .onChange(of: currentScope) {
      requestedScope = nil
      result = nil
      failure = nil
    }
    .task(id: requestedScope) {
      guard let requestedScope else { return }
      let jobs = store.jobs
      let task = Task.detached(priority: .utility) {
        try RunStorageInventory.measure(
          outputRoot: requestedScope.outputRoot, jobs: jobs, inputPaths: requestedScope.inputPaths
        )
      }
      let outcome = await withTaskCancellationHandler {
        await task.result
      } onCancel: {
        task.cancel()
      }
      guard !Task.isCancelled, scope == requestedScope else { return }
      switch outcome {
      case .success(let inventory):
        result = (requestedScope, inventory)
      case .failure(let error):
        failure = store.redactedPreviewText(error.localizedDescription)
      }
      self.requestedScope = nil
    }
  }

  private func formattedSize(_ bytes: Int64) -> String {
    ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
  }
}
