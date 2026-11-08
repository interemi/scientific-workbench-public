import SwiftUI

struct JobCaptureDetail<Content: View>: View {
  private struct Request: Equatable {
    let jobID: JobRecord.ID
    let runDirectory: String
    let historyRevision: UInt64
    let needsCapture: Bool
  }

  let store: WorkbenchStore
  let job: JobRecord
  @ViewBuilder let content: (JobRecord) -> Content
  @State private var loaded: (request: Request, capture: JobRunCapture)?

  var body: some View {
    let request = Request(
      jobID: job.id, runDirectory: job.runDirectory, historyRevision: store.historyCaptureRevision,
      needsCapture: store.hasDeferredCapture(for: job)
    )
    Group {
      if !request.needsCapture {
        content(job)
      } else if let loaded, loaded.request == request {
        content(loaded.capture.applying(to: job))
      } else {
        ProgressView("Loading run details…")
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .task(id: request) {
      guard request.needsCapture else {
        loaded = nil
        return
      }
      let redact = store.previewRedactor()
      let task = Task.detached(priority: .userInitiated) {
        try JobRunBundleService().capture(for: job, redact: redact)
      }
      let capture = await withTaskCancellationHandler {
        try? await task.value
      } onCancel: {
        task.cancel()
      }
      guard !Task.isCancelled, let capture else { return }
      loaded = (request, capture)
    }
  }
}
