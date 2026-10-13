import SwiftUI

struct WorkflowJourneyBar: View {
  @ObservedObject var store: WorkbenchStore
  let currentStage: WorkflowJourneyStage

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      ViewThatFits(in: .horizontal) {
        HStack(spacing: 12) {
          currentView
          Spacer(minLength: 12)
          navigationActions
        }
        VStack(alignment: .leading, spacing: 8) {
          currentView
          navigationActions
        }
      }

      ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 8) {
          ForEach(WorkflowJourneyStage.allCases) { stage in
            Button(stage.title) { store.navigateWorkflow(to: stage) }
              .font(.caption)
              .disabled(stage == .results && store.selectedJob == nil)
              .accessibilityValue(stage == currentStage ? "Current view" : "")
              .accessibilityIdentifier("workflow.stage.\(stage.id)")
          }
          Button("Summary", systemImage: "doc.text.magnifyingglass") {
            store.openWorkflowSummary()
          }
          .font(.caption)
          .disabled(!store.hasAvailableWorkflowSummary)
          .accessibilityIdentifier("workflow.open-summary")
        }
      }
      .fixedSize(horizontal: false, vertical: true)
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 10)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.bar)
    .accessibilityIdentifier("workflow.journey")
  }

  private var currentView: some View {
    Text("Current view: \(currentStage.title)")
      .font(.caption)
      .fontWeight(.semibold)
      .fixedSize()
      .accessibilityIdentifier("workflow.current-view")
  }

  private var navigationActions: some View {
    HStack(spacing: 10) {
      Button("Back", systemImage: "chevron.left") { store.navigateBackInWorkflow() }
        .disabled(currentStage.previous == nil)
        .help("Go to the preceding workflow view, keeping inputs, drafts, and selection.")
        .accessibilityIdentifier("workflow.back")
      Button("Edit Plan", systemImage: "pencil") { store.navigateWorkflow(to: .plan) }
        .disabled(store.agentPlan == nil)
        .help(store.isRunningAgentWorkflow
          ? "Open the plan. Editing stays disabled until the workflow stops."
          : "Open Chat to review and edit the current plan.")
        .accessibilityIdentifier("workflow.edit-plan")
      Button("Exit to Dashboard") { store.navigateWorkflow(to: .inputs) }
        .help("Return to Dashboard with the draft preserved. Active work continues; use Cancel in Chat or Jobs to stop it.")
        .accessibilityIdentifier("workflow.exit-to-dashboard")
    }
    .font(.caption)
    .fixedSize()
  }
}
