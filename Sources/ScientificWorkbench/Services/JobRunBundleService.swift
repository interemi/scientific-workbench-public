import Foundation

struct JobRunBundleSnapshot {
  var envelope: ToolEnvelope?
  var artifacts: [Artifact]
  var command: String?
  var stdout: String?
  var stderr: String?
  var nextSteps: String?
}

struct JobRunBundleService {
  private let maximumSidecarBytes = 512_000
  private let parser = ToolEnvelopeParser()
  private let artifactDiscovery = ArtifactDiscovery()

  func load(runDirectory: String, stdoutFallback: String = "") -> JobRunBundleSnapshot {
    let root = URL(fileURLWithPath: runDirectory, isDirectory: true)
    let command = readText(root.appendingPathComponent("command.txt"))
    let stdout = readText(root.appendingPathComponent("stdout.txt"))
    let stderr = readText(root.appendingPathComponent("stderr.txt"))
    let nextSteps = readText(root.appendingPathComponent("next_steps.md"))
    let envelope = ["summary.json", "manifest.json"]
      .lazy
      .compactMap { fileName -> ToolEnvelope? in
        let url = root.appendingPathComponent(fileName)
        guard
          let data = try? Data(contentsOf: url, options: [.mappedIfSafe]),
          let text = String(data: Data(data.prefix(512_000)), encoding: .utf8)
        else {
          return nil
        }
        guard let envelope = parser.parse(text), isUsable(envelope) else { return nil }
        return envelope
      }
      .first
      ?? parser.parse(stdout ?? "")
      ?? parser.parse(stdoutFallback)

    return JobRunBundleSnapshot(
      envelope: envelope,
      artifacts: artifactDiscovery.discover(in: runDirectory),
      command: command,
      stdout: stdout,
      stderr: stderr,
      nextSteps: nextSteps
    )
  }

  func hydrate(
    _ job: inout JobRecord,
    fallbackEnvelope: ToolEnvelope? = nil,
    redact: (String) -> String = { $0 }
  ) {
    let snapshot = load(runDirectory: job.runDirectory, stdoutFallback: job.stdout)
    let envelope = snapshot.envelope ?? fallbackEnvelope
    job.artifacts = snapshot.artifacts
    if let command = snapshot.command {
      job.command = redact(command)
    }
    if let stdout = snapshot.stdout {
      job.stdout = redact(stdout)
    }
    if let stderr = snapshot.stderr {
      job.stderr = redact(stderr)
    }
    let fileNextActions = parseNextActions(snapshot.nextSteps, redact: redact)
    guard let envelope else {
      if !fileNextActions.isEmpty {
        job.nextActions = fileNextActions
      }
      return
    }

    job.parsedTool = envelope.tool.map(redact) ?? job.parsedTool
    job.parsedStatus = envelope.status.map(redact) ?? job.parsedStatus
    job.contractVersion = envelope.contractVersion.map(redact)
    job.appStatus = envelope.appStatus.map(redact)
    job.originalModified = envelope.originalModified.map(redact)
    job.warnings = envelope.warnings.map(redact)
    job.structuredErrors = envelope.errors.compactMap { error in
      guard let message = error.message, !message.isEmpty else { return nil }
      return JobStructuredError(
        kind: redact(error.kind ?? "unknown"),
        message: redact(message),
        recoveryHint: error.recoveryHint.map(redact)
      )
    }
    let envelopeActions: [JobNextAction] = envelope.nextActions.compactMap { action -> JobNextAction? in
      guard let label = action.label, !label.isEmpty else { return nil }
      return JobNextAction(
        label: redact(label),
        kind: action.kind.map(redact),
        priority: action.priority.map(redact)
      )
    }
    job.nextActions = envelopeActions.isEmpty
      ? fileNextActions
      : envelopeActions
    job.shortSummary = envelope.appHints?.shortSummary.map(redact)
    job.severity = envelope.appHints?.severity.map(redact)
    job.previewArtifactTypes = envelope.appHints?.previewArtifactTypes.map(redact) ?? []
    job.tags = envelope.appHints?.tags.map(redact) ?? []
  }

  func writeCaptureFiles(
    runDirectory: String,
    command: String,
    stdout: String,
    stderr: String
  ) {
    let root = URL(fileURLWithPath: runDirectory, isDirectory: true)
    try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    write(command, to: root.appendingPathComponent("command.txt"))
    write(stdout, to: root.appendingPathComponent("stdout.txt"))
    write(stderr, to: root.appendingPathComponent("stderr.txt"))
  }

  func writeNextStepsIfMissing(for job: JobRecord) {
    let url = URL(fileURLWithPath: job.runDirectory, isDirectory: true)
      .appendingPathComponent("next_steps.md")
    guard !FileManager.default.fileExists(atPath: url.path) else { return }

    let actions = job.nextActions.map(\.label)
    let lines = actions.isEmpty ? job.recoveryAdvice : actions
    let body: String
    if lines.isEmpty {
      body = "# Next steps\n\nNo further action is required.\n"
    } else {
      body = "# Next steps\n\n" + lines.map { "- \($0)" }.joined(separator: "\n") + "\n"
    }
    write(body, to: url)
  }

  private func write(_ text: String, to url: URL) {
    try? text.write(to: url, atomically: true, encoding: .utf8)
  }

  private func readText(_ url: URL) -> String? {
    guard
      let data = try? Data(contentsOf: url, options: [.mappedIfSafe]),
      let text = String(data: Data(data.prefix(maximumSidecarBytes)), encoding: .utf8)
    else {
      return nil
    }
    return text
  }

  private func parseNextActions(
    _ text: String?,
    redact: (String) -> String
  ) -> [JobNextAction] {
    guard let text else { return [] }
    return text
      .split(separator: "\n")
      .compactMap { rawLine -> JobNextAction? in
        let line = rawLine.trimmingCharacters(in: .whitespaces)
        guard line.hasPrefix("- ") || line.hasPrefix("* ") else { return nil }
        let label = String(line.dropFirst(2)).trimmingCharacters(in: .whitespaces)
        guard !label.isEmpty else { return nil }
        return JobNextAction(label: redact(label), kind: "inspect_artifact", priority: nil)
      }
      .prefix(20)
      .map { $0 }
  }

  private func isUsable(_ envelope: ToolEnvelope) -> Bool {
    envelope.tool != nil
      || envelope.status != nil
      || envelope.appStatus != nil
      || !envelope.typedArtifacts.isEmpty
      || !envelope.errors.isEmpty
      || envelope.appHints != nil
  }
}
