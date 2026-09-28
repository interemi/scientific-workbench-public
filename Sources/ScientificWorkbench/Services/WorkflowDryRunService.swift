import Foundation

@MainActor
struct WorkflowDryRunService {
  struct Request {
    var plan: AgentPlan?
    var capabilities: [CapabilityEntry]
    var inputPaths: [String]
    var pythonExecutable: String
    var timeoutSeconds: TimeInterval
    var skillRootPath: String
    var makeRunDirectory: (CapabilityEntry) -> String
    var resolveRawArguments: (String, String?, String?, [String: String]) -> String
    var redact: (String) -> String
  }

  struct Result {
    var report: String
    var statusMessage: String
  }

  func buildReport(request: Request) -> Result {
    guard let plan = request.plan else {
      return Result(
        report: "Create or import a plan before dry-run.",
        statusMessage: "Create or import a plan before dry-run."
      )
    }
    let enabledSteps = plan.steps.filter(\.isEnabled)
    guard !enabledSteps.isEmpty else {
      return Result(
        report: "Enable at least one plan step before dry-run.",
        statusMessage: "Enable at least one plan step before dry-run."
      )
    }

    var previousRunDirectory: String?
    var completedRunDirectories: [String: String] = [:]
    var foundIssues = false
    var lines = [
      "Dry run for '\(request.redact(plan.title))': \(enabledSteps.count) enabled step\(enabledSteps.count == 1 ? "" : "s").",
      "No commands were executed and no output folders were created."
    ]

    for (stepIndex, step) in enabledSteps.enumerated() {
      guard let capability = request.capabilities.first(where: { $0.id == step.capabilityID }) else {
        foundIssues = true
        lines.append("\(stepIndex + 1). BLOCKED `\(request.redact(step.capabilityID))`: capability is not available in the current registry.")
        continue
      }

      var stepInputs = step.usesInputs ? request.inputPaths : []
      if step.usesPreviousOutput, let previousRunDirectory,
         !stepInputs.contains(previousRunDirectory) {
        stepInputs.append(previousRunDirectory)
      }
      for referencedRunDirectory in WorkflowPlaceholderValidator.referencedRunDirectories(
        in: step.rawArguments,
        completedRunDirectories: completedRunDirectories
      ) where !stepInputs.contains(referencedRunDirectory) {
        stepInputs.append(referencedRunDirectory)
      }

      let plannedRunDirectory = request.makeRunDirectory(capability)
      let rawArguments = request.resolveRawArguments(
        step.rawArguments,
        plannedRunDirectory,
        previousRunDirectory,
        completedRunDirectories
      )
      let unresolvedTokens = WorkflowPlaceholderValidator.unresolvedTokens(in: rawArguments)
      if !unresolvedTokens.isEmpty {
        foundIssues = true
        lines.append(
          "\(stepIndex + 1). BLOCKED `\(request.redact(capability.label))`: unresolved placeholders \(unresolvedTokens.joined(separator: ", "))."
        )
        continue
      }
      do {
        let effectiveRawArguments = try LegacyReportProjectStagingService().previewPopulateArgumentsIfNeeded(
          capabilityID: capability.id,
          rawArguments: rawArguments,
          inputPaths: stepInputs,
          runDirectory: plannedRunDirectory
        )
        let runRequest = RunRequest(
          capabilityID: capability.id,
          inputPaths: stepInputs,
          outputDirectory: plannedRunDirectory,
          rawArguments: effectiveRawArguments
        )
        let builder = CapabilityCommandBuilder(
          pythonExecutable: request.pythonExecutable,
          timeoutSeconds: request.timeoutSeconds
        )
        let command = try builder.build(
          capability: capability,
          request: runRequest,
          skillRoot: request.skillRootPath
        )
        lines.append("\(stepIndex + 1). OK `\(request.redact(capability.label))`")
        lines.append("   \(request.redact(command.pretty))")
        previousRunDirectory = plannedRunDirectory
        completedRunDirectories[step.capabilityID] = plannedRunDirectory
        completedRunDirectories["step\(stepIndex + 1)"] = plannedRunDirectory
      } catch {
        foundIssues = true
        lines.append("\(stepIndex + 1). BLOCKED `\(request.redact(capability.label))`: \(request.redact(error.localizedDescription))")
      }
    }

    return Result(
      report: lines.joined(separator: "\n"),
      statusMessage: foundIssues ? "Dry run found issues." : "Dry run passed."
    )
  }
}
