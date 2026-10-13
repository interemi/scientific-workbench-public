import SwiftUI

struct JobJourneyView: View {
  @ObservedObject var store: WorkbenchStore
  let job: JobRecord

  private var journey: JobJourneyState {
    JobJourneyState(
      job: job,
      plan: store.agentPlan,
      stepExecutions: store.agentPlanStepExecutions,
      isRunningWorkflow: store.isRunningAgentWorkflow,
      isCancellationRequested: store.isCancellationRequested
    )
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Run → Job → Result")
        .font(.headline)

      JobIdentityView(store: store, job: job)

      stage("Run", detail: journey.runStage, image: "checkmark.circle")
      stage("Job", detail: journey.jobStage, image: "gearshape.2")
      stage("Result", detail: journey.resultStage, image: "doc.richtext")

      if let currentStep = journey.currentStep {
        Text(currentStep)
          .font(.subheadline)
          .fontWeight(.medium)
      } else {
        Text("Current task: \(job.capabilityLabel)")
          .font(.subheadline)
          .fontWeight(.medium)
      }

      HStack(spacing: 12) {
        Text("Last recorded change: \(DateFormatters.timestamp.string(from: journey.lastActivityAt))")
        if job.status == .running, let startedAt = job.startedAt {
          TimelineView(.periodic(from: .now, by: 1)) { context in
            Text("Elapsed: \(DateFormatters.duration.string(from: max(0, context.date.timeIntervalSince(startedAt))) ?? "0s")")
          }
        }
      }
      .font(.caption)
      .foregroundStyle(.secondary)

      Text(journey.guidance)
        .font(.caption)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)

      HStack(spacing: 10) {
        if job.status != .queued && job.status != .running {
          Button {
            store.openJobResults(job)
          } label: {
            Label("Open Results", systemImage: "arrow.right")
          }
          .accessibilityIdentifier("jobs.open-results")
        }

        Button {
          store.revealRunDirectory(job)
        } label: {
          Label("Reveal Run Folder", systemImage: "folder")
        }
        .accessibilityIdentifier("jobs.reveal-run-folder")
      }

      if let primary = job.artifacts.first(where: { $0.primary == true })
        ?? job.artifacts.first,
        FileManager.default.fileExists(atPath: primary.path) {
        Button {
          store.revealArtifact(primary)
        } label: {
          Label("Reveal artifact: \(primary.label ?? primary.relativePath)", systemImage: "folder")
        }
        .accessibilityIdentifier("jobs.reveal-artifact")
      }
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }

  private func stage(_ title: String, detail: String, image: String) -> some View {
    HStack(alignment: .firstTextBaseline, spacing: 8) {
      Label(title, systemImage: image)
        .fontWeight(.medium)
        .frame(width: 90, alignment: .leading)
      Text(detail)
        .foregroundStyle(.secondary)
    }
    .font(.caption)
  }
}
