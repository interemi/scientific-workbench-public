import SwiftUI

struct JobIdentityView: View {
  @ObservedObject var store: WorkbenchStore
  let job: JobRecord

  var body: some View {
    VStack(alignment: .leading, spacing: 4) {
      Text("Job ID: \(job.id.uuidString)")
      if let runID = store.workflowRunID(for: job) {
        Text("Workflow Run ID: \(runID.uuidString)")
      }
      if let plan = store.agentPlan,
         let step = plan.steps.first(where: { store.agentPlanStepExecutions[$0.id]?.jobID == job.id }) {
        Text("Plan ID: \(plan.id.uuidString)")
        Text("Step ID: \(step.id.uuidString)")
      }
    }
    .font(.caption2)
    .foregroundStyle(.secondary)
    .textSelection(.enabled)
    .accessibilityIdentifier("job.evidence-identity")
  }
}
