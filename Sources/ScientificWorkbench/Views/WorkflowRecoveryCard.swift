import SwiftUI

struct WorkflowRecoveryCard: View {
  @ObservedObject var store: WorkbenchStore
  let recovery: WorkflowRecoveryState

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .firstTextBaseline) {
        Label("Recovery", systemImage: "lifepreserver")
          .font(.title3)
          .fontWeight(.semibold)
        Spacer()
        StatusBadge(status: recovery.badgeTitle)
      }

      VStack(alignment: .leading, spacing: 4) {
        Text(recovery.title)
          .font(.headline)
        Text(recovery.detail)
          .font(.caption)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      if !recovery.recoveryAdvice.isEmpty {
        VStack(alignment: .leading, spacing: 6) {
          ForEach(recovery.recoveryAdvice, id: \.self) { advice in
            Label(advice, systemImage: "lightbulb")
              .font(.caption)
              .foregroundStyle(.secondary)
              .textSelection(.enabled)
          }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
      }

      HStack(spacing: 10) {
        if recovery.stoppedJobID != nil {
          Button {
            store.selectedJobID = recovery.stoppedJobID
            store.selectedSection = .jobs
          } label: {
            Label("Open Job", systemImage: "list.bullet.rectangle")
          }
        }

        Button {
          let report = store.dryRunAgentPlan()
          store.agentChatMessages.append(AgentChatMessage(role: .assistant, text: report))
        } label: {
          Label("Dry Run", systemImage: "checklist")
        }
        .disabled(store.enabledAgentPlanSteps.isEmpty || store.isRunningAgentWorkflow)

        Button {
          Task {
            let result = await store.resumeAgentPlanFromLastSuccess()
            store.agentChatMessages.append(AgentChatMessage(role: .assistant, text: result))
          }
        } label: {
          Label("Run Remaining", systemImage: "forward.end.fill")
        }
        .buttonStyle(.borderedProminent)
        .disabled(!recovery.canResume || store.isRunningAgentWorkflow)

        if store.lastWorkflowSummaryPath != nil {
          Button {
            store.openWorkflowSummary()
          } label: {
            Label("Open Summary", systemImage: "doc.text.magnifyingglass")
          }
        }

        Button {
          store.exportSupportBundle()
        } label: {
          Label("Support Bundle", systemImage: "shippingbox")
        }

        Spacer(minLength: 0)
      }
    }
    .padding(14)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }
}
