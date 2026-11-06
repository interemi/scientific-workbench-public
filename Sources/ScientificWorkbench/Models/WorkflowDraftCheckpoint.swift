import Foundation

// A separate archive format; existing job and agent-state schemas stay unchanged.
struct WorkflowDraftCheckpoint: Codable, Sendable {
  static let currentVersion = 1

  var version = Self.currentVersion
  var id = UUID()
  var createdAt = Date()
  var outputRootPath: String
  var inputPaths: [String]
  var prompt: String
  var plan: AgentPlan?
  var stepExecutions: [AgentPlanStepExecution]
  var summaryPath: String?
  var selectedCapabilityID: String?
  var selectedJobID: UUID?
  var argumentDrafts: [String: String]
  var messages: [AgentChatMessage]

  func redacted(using redact: (String) -> String) -> Self {
    var copy = self
    copy.outputRootPath = redact(outputRootPath)
    copy.inputPaths = inputPaths.map(redact)
    copy.prompt = redact(prompt)
    copy.summaryPath = summaryPath.map(redact)
    copy.argumentDrafts = argumentDrafts.mapValues(redact)
    copy.messages = messages.map {
      var message = $0
      message.text = redact(message.text)
      return message
    }
    copy.plan = plan.map {
      var plan = $0
      plan.title = redact(plan.title)
      plan.rationale = redact(plan.rationale)
      plan.steps = plan.steps.map {
        var step = $0
        step.summary = redact(step.summary)
        step.rawArguments = redact(step.rawArguments)
        return step
      }
      return plan
    }
    copy.stepExecutions = stepExecutions.map {
      var execution = $0
      execution.runDirectory = redact(execution.runDirectory)
      return execution
    }
    return copy
  }
}

struct WorkflowDraftBackup {
  var checkpoint: WorkflowDraftCheckpoint
  var archivePath: String
}
