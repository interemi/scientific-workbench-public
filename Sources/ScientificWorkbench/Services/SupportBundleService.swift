import Foundation

struct SupportBundleExportResult {
  var bundleURL: URL
  var copiedWorkflowSummary: Bool
}

struct SupportBundlePayload: Codable {
  var version: Int
  var generatedAt: Date
  var appName: String
  var skillRootPath: String
  var outputRootPath: String
  var pythonExecutable: String
  var selectedSection: AppSection?
  var aiProvider: AIProvider
  var aiModel: String
  var cloudAttachmentContextMode: CloudAttachmentContextMode
  var agentMode: AgentRunMode
  var agentAutoRun: Bool
  var agentStatusMessage: String
  var inputPaths: [String]
  var setupChecklistItems: [SetupChecklistItem]
  var setupRecoveryState: SetupRecoveryState?
  var environmentStatus: EnvironmentStatus
  var ollamaSetupStatus: OllamaSetupStatus
  var aiConnectionStatuses: [String: AIConnectionStatus]
  var capabilityCounts: [String: Int]
  var agentPlan: AgentPlan?
  var stepExecutions: [AgentPlanStepExecution]
  var workflowRecoveryState: WorkflowRecoveryState?
  var jobs: [JobRecord]
  var recentMessages: [AgentChatMessage]
  var lastWorkflowSummaryPath: String?
  var lastExportedPlanPath: String?
}

struct SupportBundleService {
  func export(
    generatedAt: Date,
    supportBundlesDirectory: URL,
    payload: SupportBundlePayload,
    latestWorkflowSummaryPath: String?,
    redact: (String) -> String
  ) throws -> SupportBundleExportResult {
    let bundleName = "\(DateFormatters.runFolder.string(from: generatedAt))_support_bundle_\(UUID().uuidString.prefix(8))"
    let bundleURL = supportBundlesDirectory.appendingPathComponent(bundleName, isDirectory: true)
    let stateURL = bundleURL.appendingPathComponent("state.json")
    let reportURL = bundleURL.appendingPathComponent("support_bundle.md")
    let copiedSummaryURL = bundleURL.appendingPathComponent("latest_workflow_summary.md")

    try FileManager.default.createDirectory(at: bundleURL, withIntermediateDirectories: true)

    let data = try JSONEncoder.scientificWorkbench.encode(payload)
    try data.write(to: stateURL, options: [.atomic])

    let copiedWorkflowSummary = copyLatestWorkflowSummary(
      from: latestWorkflowSummaryPath,
      to: copiedSummaryURL,
      redact: redact
    )

    let markdown = supportBundleMarkdown(
      payload: payload,
      generatedAt: generatedAt,
      bundleURL: bundleURL,
      copiedWorkflowSummary: copiedWorkflowSummary,
      redact: redact
    )
    try markdown.write(to: reportURL, atomically: true, encoding: .utf8)

    return SupportBundleExportResult(
      bundleURL: bundleURL,
      copiedWorkflowSummary: copiedWorkflowSummary
    )
  }

  func exportJob(
    job: JobRecord,
    redactedJob: JobRecord? = nil,
    supportBundlesDirectory: URL,
    redact: (String) -> String
  ) throws -> SupportBundleExportResult {
    let generatedAt = Date()
    let cleanCapability = job.capabilityID
      .replacingOccurrences(of: ".", with: "_")
      .replacingOccurrences(of: "/", with: "_")
    let bundleName = "\(DateFormatters.runFolder.string(from: generatedAt))_\(cleanCapability)_support_\(UUID().uuidString.prefix(8))"
    let bundleURL = supportBundlesDirectory.appendingPathComponent(bundleName, isDirectory: true)
    try FileManager.default.createDirectory(at: bundleURL, withIntermediateDirectories: true)

    let stateURL = bundleURL.appendingPathComponent("job_state.json")
    let reportURL = bundleURL.appendingPathComponent("support_bundle.md")
    try JSONEncoder.scientificWorkbench.encode(redactedJob ?? job).write(to: stateURL, options: [.atomic])

    let copied = copySafeRunSidecars(
      from: URL(fileURLWithPath: job.runDirectory, isDirectory: true),
      to: bundleURL,
      redact: redact
    )
    let artifactLines = job.artifacts.isEmpty
      ? "- No artifacts were indexed."
      : job.artifacts.map {
        "- `\(redact($0.relativePath))` (\($0.artifactType ?? "unknown"), \($0.byteCount) bytes)"
      }.joined(separator: "\n")
    let nextActionLines = job.nextActions.isEmpty
      ? job.recoveryAdvice.map { "- \(redact($0))" }.joined(separator: "\n")
      : job.nextActions.map { "- \(redact($0.label))" }.joined(separator: "\n")
    let safeNextActions = nextActionLines.isEmpty ? "- No further action recorded." : nextActionLines
    let markdown = """
    # Scientific Workbench Job Support Bundle

    Generated: \(ISO8601DateFormatter().string(from: generatedAt))
    Capability: `\(redact(job.capabilityID))`
    Status: \(job.status.title)
    Run: `\(redact(job.runDirectory))`

    This diagnostic bundle contains redacted job state and safe text sidecars. Heavy or personal artifacts remain in the original run folder and are only listed below.

    ## Indexed Artifacts

    \(artifactLines)

    ## Recovery And Next Actions

    \(safeNextActions)

    ## Included Sidecars

    \(copied.isEmpty ? "- No readable run sidecars were available." : copied.map { "- `\($0)`" }.joined(separator: "\n"))
    """
    try markdown.write(to: reportURL, atomically: true, encoding: .utf8)
    return SupportBundleExportResult(bundleURL: bundleURL, copiedWorkflowSummary: false)
  }

  private func copyLatestWorkflowSummary(
    from latestWorkflowSummaryPath: String?,
    to copiedSummaryURL: URL,
    redact: (String) -> String
  ) -> Bool {
    guard let latestWorkflowSummaryPath else { return false }
    let sourceURL = URL(fileURLWithPath: latestWorkflowSummaryPath)
    guard FileManager.default.fileExists(atPath: sourceURL.path) else { return false }

    if let summary = try? String(contentsOf: sourceURL, encoding: .utf8) {
      try? redact(summary).write(to: copiedSummaryURL, atomically: true, encoding: .utf8)
    } else {
      try? FileManager.default.copyItem(at: sourceURL, to: copiedSummaryURL)
    }
    return FileManager.default.fileExists(atPath: copiedSummaryURL.path)
  }

  private func copySafeRunSidecars(
    from runURL: URL,
    to bundleURL: URL,
    redact: (String) -> String
  ) -> [String] {
    var copied: [String] = []
    for name in ["summary.json", "manifest.json", "stdout.txt", "stderr.txt", "command.txt", "next_steps.md"] {
      let source = runURL.appendingPathComponent(name)
      guard
        let data = try? Data(contentsOf: source, options: [.mappedIfSafe]),
        let text = String(data: Data(data.prefix(512_000)), encoding: .utf8)
      else {
        continue
      }
      let destination = bundleURL.appendingPathComponent(name)
      if (try? redact(text).write(to: destination, atomically: true, encoding: .utf8)) != nil {
        copied.append(name)
      }
    }
    return copied
  }

  private func supportBundleMarkdown(
    payload: SupportBundlePayload,
    generatedAt: Date,
    bundleURL: URL,
    copiedWorkflowSummary: Bool,
    redact: (String) -> String
  ) -> String {
    let recoveryLines: String
    if let recovery = payload.workflowRecoveryState {
      let advice = recovery.recoveryAdvice.isEmpty
        ? "- No recovery advice recorded."
        : recovery.recoveryAdvice.map { "- \(redact($0))" }.joined(separator: "\n")
      recoveryLines = """
      Status: \(redact(recovery.title))
      Next step: \(recovery.resumeStepIndex) / \(recovery.totalCount) - `\(redact(recovery.resumeStepCapabilityID))`
      Run Remaining available: \(recovery.canResume ? "yes" : "no")

      \(advice)
      """
    } else {
      recoveryLines = "No active workflow recovery state."
    }

    let checklistLines = payload.setupChecklistItems.map { item in
      "- \(item.state.badgeTitle): \(redact(item.title)) - \(redact(item.detail))"
    }.joined(separator: "\n")
    let setupRecoveryLines: String
    if let setupRecoveryState = payload.setupRecoveryState {
      let actions = setupRecoveryState.recommendedActions
        .map { "- \(redact($0))" }
        .joined(separator: "\n")
      setupRecoveryLines = """
      \(redact(setupRecoveryState.detail))

      \(actions)
      """
    } else {
      setupRecoveryLines = "Setup is ready for local workflows."
    }
    let jobLines = payload.jobs.prefix(12).map { job in
      let exitCode = job.exitCode.map(String.init) ?? "-"
      return "- \(redact(job.capabilityLabel)): \(job.status.title), exit \(exitCode), run `\(redact(job.runDirectory))`"
    }.joined(separator: "\n")
    let jobsSection = jobLines.isEmpty ? "- No jobs recorded." : jobLines
    let summaryLine = copiedWorkflowSummary
      ? "- `latest_workflow_summary.md` copied into this bundle."
      : "- No latest workflow summary was available to copy."

    return """
    # Scientific Workbench Support Bundle

    Generated: \(ISO8601DateFormatter().string(from: generatedAt))
    Bundle: `\(redact(bundleURL.path))`

    This folder is a local diagnostic snapshot. It redacts configured API keys, but still review personal file paths before sharing it outside your machine.

    ## What To Inspect First

    1. `support_bundle.md` for the human-readable summary.
    2. `state.json` for exact app state, plan, jobs, recovery, and recent messages.
    3. `latest_workflow_summary.md` if present.
    4. The job run folders referenced below for heavy artifacts and logs.

    ## Recovery

    \(recoveryLines)

    ## Setup Checklist

    \(checklistLines)

    ## Setup Recovery

    \(setupRecoveryLines)

    ## Current Configuration

    AI provider: \(payload.aiProvider.title)
    AI model: \(payload.aiModel)
    Cloud attachment context: \(payload.cloudAttachmentContextMode.title)
    Agent mode: \(payload.agentMode.title)
    Auto-run: \(payload.agentAutoRun ? "on" : "off")
    Output root: `\(redact(payload.outputRootPath))`
    Python: `\(redact(payload.pythonExecutable))`

    ## Recent Jobs

    \(jobsSection)

    ## Included Files

    - `state.json`
    \(summaryLine)
    """
  }
}
