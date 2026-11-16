import SwiftUI

struct WorkflowJourneyBar: View, Equatable {
  private let store: WorkbenchStore
  private let currentStage: WorkflowJourneyStage
  private let hasSelectedJob: Bool
  private let hasSummary: Bool
  private let hasPlan: Bool
  private let isRunningWorkflow: Bool
  private let guideKind: FirstRunExampleKind?

  init(store: WorkbenchStore, currentStage: WorkflowJourneyStage) {
    self.store = store
    self.currentStage = currentStage
    hasSelectedJob = store.selectedJob != nil
    hasSummary = store.hasAvailableWorkflowSummary
    hasPlan = store.agentPlan != nil
    isRunningWorkflow = store.isRunningAgentWorkflow
    guideKind = store.currentWorkflowGuideKind
  }

  nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
    lhs.store === rhs.store
      && lhs.currentStage == rhs.currentStage
      && lhs.hasSelectedJob == rhs.hasSelectedJob
      && lhs.hasSummary == rhs.hasSummary
      && lhs.hasPlan == rhs.hasPlan
      && lhs.isRunningWorkflow == rhs.isRunningWorkflow
      && lhs.guideKind == rhs.guideKind
  }

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
              .disabled(stage == .results && !hasSelectedJob)
              .accessibilityValue(stage == currentStage ? "Current view" : "")
              .accessibilityIdentifier("workflow.stage.\(stage.id)")
          }
          Button("Summary", systemImage: "doc.text.magnifyingglass") {
            store.openWorkflowSummary()
          }
          .font(.caption)
          .disabled(!hasSummary)
          .accessibilityIdentifier("workflow.open-summary")
        }
      }
      .fixedSize(horizontal: false, vertical: true)
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 10)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.bar)
    .accessibilityElement(children: .contain)
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
        .disabled(!hasPlan)
        .help(isRunningWorkflow
          ? "Open the plan. Editing stays disabled until the workflow stops."
          : "Open Chat to review and edit the current plan.")
        .accessibilityIdentifier("workflow.edit-plan")
      Button("Exit to Dashboard") { store.navigateWorkflow(to: .inputs) }
        .help("Return to Dashboard with the draft preserved. Active work continues; use Cancel in Chat or Jobs to stop it.")
        .accessibilityIdentifier("workflow.exit-to-dashboard")
      if let kind = guideKind {
        Button("Task Guide", systemImage: "questionmark.circle") { store.openFirstRunGuide(for: kind) }
          .help("Open the bundled guide for this task's inputs, review, output evidence, and limits.")
          .accessibilityIdentifier("workflow.open-task-guide")
      }
    }
    .font(.caption)
    .fixedSize()
  }
}
