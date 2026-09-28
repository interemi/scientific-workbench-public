import SwiftUI

struct EditablePlanCard: View {
  @ObservedObject var store: WorkbenchStore
  let plan: AgentPlan

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .top) {
        VStack(alignment: .leading, spacing: 8) {
          TextField("Plan title", text: titleBinding)
            .font(.title3)
            .fontWeight(.semibold)
            .textFieldStyle(.plain)
          Text("\(plan.source.title) - \(DateFormatters.timestamp.string(from: plan.createdAt))")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        Spacer()
        Button {
          store.exportAgentPlan()
        } label: {
          Label("Export Plan", systemImage: "square.and.arrow.down")
        }
        .help("Export this editable plan as JSON.")

        Button {
          let report = store.dryRunAgentPlan()
          store.agentChatMessages.append(AgentChatMessage(role: .assistant, text: report))
        } label: {
          Label("Dry Run", systemImage: "checklist")
        }
        .help("Validate commands and placeholders without executing the plan.")
        .disabled(store.enabledAgentPlanSteps.isEmpty || store.isRunningAgentWorkflow)

        if store.lastExportedPlanPath != nil {
          Button {
            store.revealExportedPlans()
          } label: {
            Label("Reveal Plans", systemImage: "folder")
          }
          .help("Open the exported plans folder.")
        }

        if store.canResumeAgentPlan {
          Button {
            Task {
              let result = await store.resumeAgentPlanFromLastSuccess()
              store.agentChatMessages.append(AgentChatMessage(role: .assistant, text: result))
            }
          } label: {
            Label("Run Remaining", systemImage: "forward.end.fill")
          }
          .help("Continue from the last successful workflow step.")
          .disabled(store.isRunningAgentWorkflow)
        }

        Button {
          Task {
            let result = await store.runAgentPlan()
            store.agentChatMessages.append(AgentChatMessage(role: .assistant, text: result))
          }
        } label: {
          Label(store.isRunningAgentWorkflow ? "Running..." : "Run Enabled", systemImage: "play.fill")
        }
        .buttonStyle(.borderedProminent)
        .disabled(store.isRunningAgentWorkflow || store.enabledAgentPlanSteps.isEmpty)

        if store.isRunningAgentWorkflow {
          Button(role: .cancel) {
            store.cancelActiveRun()
          } label: {
            Label(store.isCancellationRequested ? "Cancelling..." : "Cancel", systemImage: "xmark.circle")
          }
          .disabled(store.isCancellationRequested)
        }
      }

      TextField("Why this plan?", text: rationaleBinding, axis: .vertical)
        .lineLimit(2...5)
        .textFieldStyle(.roundedBorder)

      PlanEstimateView(estimate: AgentPlanEstimate.estimate(plan: currentPlan))

      HStack(spacing: 8) {
        StatusBadge(status: "\(store.enabledAgentPlanSteps.count)/\(plan.steps.count)")
        Text("enabled steps")
          .font(.caption)
          .foregroundStyle(.secondary)
        Spacer()
      }

      ForEach(Array(plan.steps.enumerated()), id: \.element.id) { index, step in
        EditableAgentStepRow(store: store, index: index + 1, step: step)
      }
    }
    .padding(14)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }

  private var currentPlan: AgentPlan {
    store.agentPlan ?? plan
  }

  private var titleBinding: Binding<String> {
    Binding(get: {
      store.agentPlan?.title ?? plan.title
    }, set: { value in
      store.updateAgentPlanTitle(value)
    })
  }

  private var rationaleBinding: Binding<String> {
    Binding(get: {
      store.agentPlan?.rationale ?? plan.rationale
    }, set: { value in
      store.updateAgentPlanRationale(value)
    })
  }
}

private struct PlanEstimateView: View {
  let estimate: AgentPlanEstimate

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack(spacing: 12) {
        Label(estimate.runtimeText, systemImage: "clock")
        Label(estimate.costNote, systemImage: "creditcard")
      }
      .font(.caption)
      .foregroundStyle(.secondary)

      if let caution = estimate.caution {
        Label(caution, systemImage: "exclamationmark.triangle")
          .font(.caption)
          .foregroundStyle(.orange)
      }
    }
    .padding(10)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
  }
}

private struct EditableAgentStepRow: View {
  @ObservedObject var store: WorkbenchStore
  let index: Int
  let step: AgentPlanStep

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack(alignment: .center, spacing: 12) {
        Text("\(index)")
          .font(.caption)
          .fontWeight(.semibold)
          .frame(width: 24, height: 24)
          .background(.thinMaterial, in: Circle())

        Toggle("Run", isOn: enabledBinding)
          .toggleStyle(.checkbox)

        Picker("Capability", selection: capabilityBinding) {
          ForEach(store.userCapabilities) { capability in
            Text(capability.label).tag(capability.id)
          }
        }
        .pickerStyle(.menu)
        .frame(maxWidth: 320)

        if let capability {
          StatusBadge(status: capability.supportLevel)
          StatusBadge(status: capability.workflowMode.rawValue)
          StatusBadge(status: capability.appReadiness.rawValue)
        } else {
          StatusBadge(status: "blocked")
        }

        if let execution = store.execution(for: currentStep) {
          StatusBadge(status: execution.status.rawValue)
        }

        Spacer()

        Picker("Input", selection: inputModeBinding) {
          ForEach(StepInputMode.allCases) { mode in
            Label(mode.title, systemImage: mode.systemImage).tag(mode)
          }
        }
        .pickerStyle(.menu)
        .frame(width: 180)
      }

      TextField("Step summary", text: summaryBinding, axis: .vertical)
        .lineLimit(1...3)
        .textFieldStyle(.roundedBorder)

      TextField("Raw arguments, optional", text: rawArgumentsBinding, axis: .vertical)
        .font(.system(.caption, design: .monospaced))
        .lineLimit(1...5)
        .textFieldStyle(.roundedBorder)
    }
    .padding(10)
    .opacity(currentStep.isEnabled ? 1 : 0.55)
    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 8))
  }

  private var currentStep: AgentPlanStep {
    store.agentPlan?.steps.first { $0.id == step.id } ?? step
  }

  private var capability: CapabilityEntry? {
    store.capabilities.first { $0.id == currentStep.capabilityID }
  }

  private var enabledBinding: Binding<Bool> {
    Binding(get: {
      currentStep.isEnabled
    }, set: { value in
      store.updateAgentPlanStep(step.id) { $0.isEnabled = value }
    })
  }

  private var capabilityBinding: Binding<String> {
    Binding(get: {
      currentStep.capabilityID
    }, set: { value in
      store.updateAgentPlanStep(step.id) { $0.capabilityID = value }
    })
  }

  private var inputModeBinding: Binding<StepInputMode> {
    Binding(get: {
      StepInputMode(step: currentStep)
    }, set: { mode in
      store.updateAgentPlanStep(step.id) { step in
        step.usesInputs = mode == .attachments
        step.usesPreviousOutput = mode == .previousOutput
      }
    })
  }

  private var summaryBinding: Binding<String> {
    Binding(get: {
      currentStep.summary
    }, set: { value in
      store.updateAgentPlanStep(step.id) { $0.summary = value }
    })
  }

  private var rawArgumentsBinding: Binding<String> {
    Binding(get: {
      currentStep.rawArguments
    }, set: { value in
      store.updateAgentPlanStep(step.id) { $0.rawArguments = value }
    })
  }
}

private enum StepInputMode: String, CaseIterable, Identifiable {
  case attachments
  case previousOutput
  case none

  var id: String { rawValue }

  var title: String {
    switch self {
    case .attachments: return "Attachments"
    case .previousOutput: return "Previous output"
    case .none: return "No input"
    }
  }

  var systemImage: String {
    switch self {
    case .attachments: return "paperclip"
    case .previousOutput: return "arrow.triangle.branch"
    case .none: return "circle"
    }
  }

  init(step: AgentPlanStep) {
    if step.usesPreviousOutput {
      self = .previousOutput
    } else if step.usesInputs {
      self = .attachments
    } else {
      self = .none
    }
  }
}
