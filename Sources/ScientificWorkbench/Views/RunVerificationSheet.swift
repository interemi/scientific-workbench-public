import SwiftUI

struct RunVerificationSheet: View {
  @Environment(\.dismiss) private var dismiss
  let store: WorkbenchStore
  let job: JobRecord

  @State private var report: RunVerificationReport?
  @State private var didFinish = false
  @State private var isReplaying = false
  @State private var replayError: String?

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      Text("Verify Run").font(.title2.weight(.semibold))
      Text(job.capabilityLabel).font(.headline)
      if let report {
        Label(report.matchesRecordedEvidence ? "Recorded checks match" : "Not reproducible from the available evidence",
              systemImage: report.matchesRecordedEvidence ? "checkmark.circle" : "exclamationmark.triangle")
          .accessibilityIdentifier("jobs.verification.outcome")
        ScrollView {
          VStack(alignment: .leading, spacing: 10) {
            ForEach(report.checks) { check in
              VStack(alignment: .leading, spacing: 4) {
                HStack {
                  Text(verbatim: check.subject).font(.subheadline.weight(.semibold))
                  Spacer()
                  Text(verbatim: check.status.rawValue)
                    .foregroundStyle(check.status == .matches ? Color.secondary : Color.orange)
                }
                Text(verbatim: check.detail).foregroundStyle(.secondary)
              }
              .accessibilityElement(children: .combine)
            }
          }
          .textSelection(.enabled)
        }
        if let message = replayError ?? report.replayBlockReason {
          Text(message)
            .font(.callout)
            .foregroundStyle(.secondary)
            .accessibilityIdentifier("jobs.replay.reason")
        } else {
          Text("Replay uses verified copies of the inputs and saves the comparison with the new job.")
            .font(.callout)
            .foregroundStyle(.secondary)
        }
      } else if didFinish {
        ContentUnavailableView("Verification unavailable", systemImage: "checkmark.shield",
                               description: Text("Wait for active work to finish and open a fresh verification."))
      } else {
        ProgressView("Checking retained files and the selected Python environment…")
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      HStack {
        if isReplaying {
          ProgressView().controlSize(.small)
          Text("Preparing replay…")
        }
        Spacer()
        Button(didFinish ? "Close" : "Cancel") { dismiss() }
          .disabled(isReplaying)
          .keyboardShortcut(.cancelAction)
        if let report, report.replayBlockReason == nil {
          Button("Replay in New Folder") {
            isReplaying = true
            replayError = nil
            Task {
              replayError = await store.replayJob(job)
              isReplaying = false
              if replayError == nil { dismiss() }
            }
          }
          .disabled(isReplaying)
          .accessibilityIdentifier("jobs.replay")
        }
      }
    }
    .padding(24)
    .frame(width: 550, height: 465)
    .interactiveDismissDisabled(isReplaying)
    .task {
      let verified = await store.verifyJob(job)
      guard !Task.isCancelled else { return }
      report = verified
      didFinish = true
    }
  }
}
