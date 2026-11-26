import SwiftUI

struct RunVerificationSheet: View {
  @Environment(\.dismiss) private var dismiss
  let store: WorkbenchStore
  let job: JobRecord

  @State private var report: RunVerificationReport?
  @State private var didFinish = false

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
      } else if didFinish {
        ContentUnavailableView("Verification unavailable", systemImage: "checkmark.shield",
                               description: Text("Wait for active work to finish and open a fresh verification."))
      } else {
        ProgressView("Checking retained files and the selected Python environment…")
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      HStack {
        Spacer()
        Button(didFinish ? "Close" : "Cancel") { dismiss() }
          .keyboardShortcut(.cancelAction)
      }
    }
    .padding(24)
    .frame(width: 550, height: 465)
    .task {
      let verified = await store.verifyJob(job)
      guard !Task.isCancelled else { return }
      report = verified
      didFinish = true
    }
  }
}
