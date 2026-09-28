import Foundation

enum CloudPrivacySanitizer {
  static func filename(for path: String) -> String {
    let name = URL(fileURLWithPath: path).lastPathComponent
    return name.isEmpty ? "(unnamed local item)" : name
  }

  static func withholdingAbsolutePaths(in text: String) -> String {
    text
      .split(separator: "\n", omittingEmptySubsequences: false)
      .map { line in
        let value = String(line)
        guard let start = firstLocalPathStart(in: value) else { return value }
        return String(value[..<start]).trimmingCharacters(in: .whitespaces) + "[local path withheld]"
      }
      .joined(separator: "\n")
  }

  private static func firstLocalPathStart(in line: String) -> String.Index? {
    if line.hasPrefix("~/") || line.hasPrefix("/") || line.hasPrefix("file:/") {
      return line.startIndex
    }

    var index = line.startIndex
    while index < line.endIndex {
      if line[index] == "~" {
        let next = line.index(after: index)
        if next < line.endIndex, line[next] == "/", isPathBoundary(line: line, at: index) {
          return index
        }
      }

      if line[index] == "/", isPathBoundary(line: line, at: index) {
        return index
      }
      index = line.index(after: index)
    }
    return nil
  }

  private static func isPathBoundary(line: String, at index: String.Index) -> Bool {
    guard index > line.startIndex else { return true }
    let previous = line[line.index(before: index)]
    if previous.isWhitespace || "=([{\"',;<>`".contains(previous) {
      return true
    }
    if previous == ":" {
      let prefix = String(line[..<index]).localizedLowercase
      return !prefix.hasSuffix("http:") && !prefix.hasSuffix("https:")
    }
    return false
  }
}

struct AgentRoutingService {
  func resolvedMode(
    configuredMode: AgentRunMode,
    prompt: String,
    hasInputs: Bool
  ) -> AgentRunMode {
    guard configuredMode == .auto else { return configuredMode }

    let lower = prompt.localizedLowercase
    let workflowHints = [
      "ejecuta", "run", "analiza", "procesa", "workflow", "práctica", "practica",
      "fits", "csv", "carpeta", "archivo", "tabla", "notebook", "pdf", "report",
      "informe", "producto final", "docus", "capability", "capabilities"
    ]
    if hasInputs, workflowHints.contains(where: { lower.contains($0) }) {
      return .workflow
    }

    if hasInputs || workflowHints.contains(where: { lower.contains($0) }) {
      return .workflow
    }

    return .chat
  }

  func chatSummary(for plan: AgentPlan) -> String {
    return """
    I drafted a \(plan.source.title.lowercased()) workflow plan below.
    Review it, then run it when ready.
    """
  }

  func cloudConsentRequest(
    provider: AIProvider,
    model: String,
    purpose: CloudRequestPurpose,
    hasConversationHistory: Bool,
    inputCount: Int,
    attachmentContextMode: CloudAttachmentContextMode,
    hasWorkflowRecovery: Bool
  ) -> CloudConsentRequest? {
    guard provider.requiresAPIKey else { return nil }

    var categories: [CloudDataCategory] = [.currentMessage]
    if purpose == .chat, hasConversationHistory {
      categories.append(.recentConversation)
    }

    if inputCount > 0 {
      switch attachmentContextMode {
      case .previews:
        categories.append(.attachmentFilenames)
        if purpose == .chat {
          categories.append(.attachmentPreviews)
        }
      case .filenamesOnly:
        categories.append(.attachmentFilenames)
      case .none:
        categories.append(.attachmentCount)
      }
    }

    if purpose == .chat, hasWorkflowRecovery {
      categories.append(.workflowRecoveryStatus)
      switch attachmentContextMode {
      case .previews:
        categories.append(.workflowRecoveryFilenames)
        categories.append(.workflowRecoveryExcerpts)
      case .filenamesOnly:
        categories.append(.workflowRecoveryFilenames)
      case .none:
        break
      }
    }

    if purpose == .workflowPlanning {
      categories.append(.capabilityCatalog)
      categories.append(.deterministicRouterPlan)
    }

    return CloudConsentRequest(
      provider: provider,
      model: model,
      purpose: purpose,
      categories: categories,
      attachmentContextMode: attachmentContextMode
    )
  }

  func cloudConsentRequest(
    provider: AIProvider,
    model: String,
    purpose: CloudRequestPurpose,
    prompt: String,
    history: [AgentChatMessage],
    inputPaths: [String],
    attachmentContextMode: CloudAttachmentContextMode,
    workflowRecoveryContext: String?,
    capabilities: [CapabilityEntry]
  ) -> CloudConsentRequest? {
    guard var request = cloudConsentRequest(
      provider: provider,
      model: model,
      purpose: purpose,
      hasConversationHistory: !history.isEmpty,
      inputCount: inputPaths.count,
      attachmentContextMode: attachmentContextMode,
      hasWorkflowRecovery: workflowRecoveryContext?.isEmpty == false
    ) else {
      return nil
    }

    let relevantHistory = purpose == .chat
      ? history.suffix(12).map { CloudConsentHistoryItem(role: $0.role, text: $0.text) }
      : []
    let capabilityCatalog = purpose == .workflowPlanning
      ? capabilities.plannerVisible.map { capability in
        CloudConsentCapabilityFingerprint(
          id: capability.id,
          label: capability.label,
          visibleBlock: capability.visibleBlock,
          shortDescription: capability.shortDescription,
          guidedRequirement: capability.guidedRunRequirement.title,
          appReadiness: capability.appReadiness.rawValue,
          workflowMode: capability.workflowMode.rawValue
        )
      }
      : []
    request.fingerprint = CloudConsentFingerprint(
      provider: provider,
      model: model,
      purpose: purpose,
      prompt: prompt,
      history: relevantHistory,
      inputs: inputPaths.map {
        cloudInputFingerprint(
          for: $0,
          includePreview: purpose == .chat && attachmentContextMode == .previews
        )
      },
      attachmentContextMode: attachmentContextMode,
      categories: request.categories,
      workflowRecoveryContext: workflowRecoveryContext,
      capabilityCatalog: capabilityCatalog
    )
    return request
  }

  func workflowRecoveryPromptContext(
    recovery: WorkflowRecoveryState?,
    stoppedJob: JobRecord?,
    lastWorkflowSummaryPath: String?,
    attachmentContextMode: CloudAttachmentContextMode,
    redact: (String) -> String
  ) -> String? {
    guard let recovery else { return nil }
    var lines = [
      "Workflow recovery state:",
      "- Completed enabled steps: \(recovery.completedCount)/\(recovery.totalCount)",
      "- Resume step index: \(recovery.resumeStepIndex)",
      "- Can use Run Remaining: \(recovery.canResume ? "yes" : "no")"
    ]

    if let stoppedStatus = recovery.stoppedStatus {
      lines.append("- Stopped status: \(stoppedStatus.title)")
    }

    guard attachmentContextMode != .none else {
      lines.append("Local names, paths, previews, and logs are withheld by the cloud privacy setting.")
      lines.append("Answer recovery questions only from this status metadata. Do not invent file edits or job results.")
      return lines.joined(separator: "\n")
    }

    lines.append("- Resume capability: \(recovery.resumeStepCapabilityID)")

    if let stoppedJob {
      lines.append(contentsOf: [
        "- Stopped job: \(safeRecoveryText(stoppedJob.capabilityLabel, redact: redact))",
        "- Exit code: \(stoppedJob.exitCode.map(String.init) ?? "-")",
        "- Run folder name: \(CloudPrivacySanitizer.filename(for: stoppedJob.runDirectory))"
      ])
    }

    if let lastWorkflowSummaryPath {
      lines.append("- Latest workflow summary filename: \(CloudPrivacySanitizer.filename(for: lastWorkflowSummaryPath))")
    }

    guard attachmentContextMode == .previews else {
      lines.append("Recovery text, advice, and logs are withheld by the filenames-only privacy setting.")
      lines.append("Answer recovery questions from this metadata. Do not invent file edits or job results.")
      return lines.joined(separator: "\n")
    }

    lines.append("- Resume step summary: \(safeRecoveryText(recovery.resumeStepSummary, redact: redact))")

    if let stoppedJob {
      lines.append("- Parsed status: \(safeRecoveryText(stoppedJob.parsedStatus ?? "-", redact: redact))")
      if let message = stoppedJob.message, !message.isEmpty {
        lines.append("- Job message: \(recoverySnippet(message, redact: redact))")
      }
      if !stoppedJob.stderr.isEmpty {
        lines.append("- stderr excerpt: \(recoverySnippet(stoppedJob.stderr, redact: redact))")
      }
      if !stoppedJob.stdout.isEmpty {
        lines.append("- stdout excerpt: \(recoverySnippet(stoppedJob.stdout, redact: redact))")
      }
    }

    if !recovery.recoveryAdvice.isEmpty {
      lines.append("- App recovery advice:")
      lines.append(contentsOf: recovery.recoveryAdvice.map { "  - \(safeRecoveryText($0, redact: redact))" })
    }

    lines.append("Answer recovery questions from this context. Do not invent file edits or job results.")
    return lines.joined(separator: "\n")
  }

  private func recoverySnippet(
    _ text: String,
    limit: Int = 700,
    redact: (String) -> String
  ) -> String {
    let cleaned = safeRecoveryText(text, redact: redact)
      .replacingOccurrences(of: "\r", with: "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard cleaned.count > limit else { return cleaned }
    return String(cleaned.prefix(limit)) + "..."
  }

  private func safeRecoveryText(
    _ text: String,
    redact: (String) -> String
  ) -> String {
    CloudPrivacySanitizer.withholdingAbsolutePaths(in: redact(text))
  }

  private func cloudInputFingerprint(
    for path: String,
    includePreview: Bool
  ) -> CloudConsentInputFingerprint {
    let selectedURL = URL(fileURLWithPath: NSString(string: path).expandingTildeInPath)
    let canonicalURL = selectedURL.standardizedFileURL.resolvingSymlinksInPath()
    var isDirectory: ObjCBool = false
    let exists = FileManager.default.fileExists(atPath: selectedURL.path, isDirectory: &isDirectory)
    let attributes = exists
      ? (try? FileManager.default.attributesOfItem(atPath: selectedURL.path)) ?? [:]
      : [:]
    let byteCount = (attributes[.size] as? NSNumber)?.int64Value
    let modificationTime = (attributes[.modificationDate] as? Date)?.timeIntervalSince1970

    var previewBytes: Data?
    var directoryPreviewEntries: [String] = []
    if includePreview, exists, isDirectory.boolValue {
      directoryPreviewEntries = Array(
        ((try? FileManager.default.contentsOfDirectory(atPath: selectedURL.path)) ?? [])
          .sorted()
          .prefix(40)
      )
    } else if includePreview, exists, isCloudPreviewTextFile(selectedURL) {
      previewBytes = (try? Data(contentsOf: selectedURL, options: [.mappedIfSafe]))
        .map { Data($0.prefix(16_000)) }
    }

    return CloudConsentInputFingerprint(
      canonicalPath: canonicalURL.path,
      presentedName: CloudPrivacySanitizer.filename(for: selectedURL.path),
      kind: !exists ? .missing : (isDirectory.boolValue ? .directory : .file),
      byteCount: byteCount,
      modificationTime: modificationTime,
      previewBytes: previewBytes,
      directoryPreviewEntries: directoryPreviewEntries
    )
  }

  private func isCloudPreviewTextFile(_ url: URL) -> Bool {
    let textExtensions: Set<String> = [
      "txt", "md", "csv", "tsv", "json", "jsonl", "yaml", "yml", "tex",
      "py", "swift", "ipynb", "log", "dat"
    ]
    return textExtensions.contains(url.pathExtension.localizedLowercase)
  }
}
