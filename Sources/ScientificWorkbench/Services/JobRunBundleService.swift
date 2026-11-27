import Foundation

struct JobRunBundleSnapshot {
  var envelope: ToolEnvelope?
  var artifacts: [Artifact]
  var command: String?
  var stdout: String?
  var stderr: String?
  var nextSteps: String?
}

struct JobRunCapture: Sendable {
  let command: String
  let stdout: String
  let stderr: String

  func applying(to job: JobRecord) -> JobRecord {
    var detailed = job
    detailed.command = command
    detailed.stdout = stdout
    detailed.stderr = stderr
    return detailed
  }
}

struct JobRunBundleService {
  enum Completion: Sendable {
    case finished(ProcessResult, cancellationRequested: Bool)
    case interrupted(InterruptedProcessOutput?)
  }

  private let maximumSidecarBytes = 512_000
  private let parser = ToolEnvelopeParser()
  private let artifactDiscovery = ArtifactDiscovery()

  func finalize(
    _ record: JobRecord, completion: Completion, secrets: [String],
    provenance: RunProvenanceService.Start? = nil
  ) async -> JobRecord {
    // An interrupted or cancelled caller still needs its captured evidence.
    await Task.detached(priority: .userInitiated) {
      autoreleasepool {
        let redact: (String) -> String = { SecretsRedactor.redact($0, secrets: secrets) }
        var job = record
        var fallbackEnvelope: ToolEnvelope?
        let retainedLogs: Set<RunLogStream>

        switch completion {
        case let .finished(result, _):
          fallbackEnvelope = parser.parse(result.stdout)
          job.stdout = redact(result.stdout)
          job.stderr = redact(result.stderr)
          job.exitCode = result.exitCode
          job.finishedAt = result.finishedAt
          retainedLogs = result.retainedLogs
        case .interrupted(let partial):
          if let partial {
            job.stdout = redact(partial.stdout)
            job.stderr = redact(partial.stderr)
          }
          retainedLogs = partial?.retainedLogs ?? []
        }

        writeCaptureFiles(
          runDirectory: job.runDirectory,
          command: job.command,
          stdout: job.stdout,
          stderr: job.stderr.isEmpty ? (job.message ?? "") : job.stderr,
          retaining: retainedLogs
        )
        hydrate(&job, fallbackEnvelope: fallbackEnvelope, redact: redact)
        if case let .finished(result, cancellationRequested) = completion {
          if cancellationRequested {
            job.status = .cancelled
            job.message = "Run cancelled by user."
          } else {
            job.status = JobStatus.resolved(
              exitCode: result.exitCode, envelopeStatus: job.parsedStatus, appStatus: job.appStatus
            )
            if result.exitCode != 0 {
              job.message = redact(result.stderr.isEmpty ? "Process exited with \(result.exitCode)." : result.stderr)
            }
          }
          if job.message == nil {
            job.message = job.structuredErrors.first?.message
          }
        }
        writeNextStepsIfMissing(for: job)
        let envelope = hydrate(&job, fallbackEnvelope: fallbackEnvelope, redact: redact)
        if let provenance {
          do {
            let artifact = try RunProvenanceService().write(start: provenance, job: job, envelope: envelope)
            job.artifacts.append(artifact)
          } catch {
            job.warnings.append("The app could not retain the run provenance record.")
          }
        }
        return job
      }
    }.value
  }

  func load(
    runDirectory: String, stdoutFallback: String = "", includingCapture: Bool = true
  ) -> JobRunBundleSnapshot {
    let root = URL(fileURLWithPath: runDirectory, isDirectory: true)
    let nextSteps = readText(root.appendingPathComponent("next_steps.md"))
    let sidecarEnvelope = ["summary.json", "manifest.json"]
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
    // Older runs may report their searchable summary only in stdout.
    let stdout = includingCapture || sidecarEnvelope == nil
      ? readLog(root.appendingPathComponent(RunLogStream.stdout.fileName)) : nil
    let envelope = sidecarEnvelope ?? parser.parse(stdout ?? "") ?? parser.parse(stdoutFallback)

    return JobRunBundleSnapshot(
      envelope: envelope,
      artifacts: artifactDiscovery.discover(in: runDirectory),
      command: includingCapture ? readText(root.appendingPathComponent("command.txt")) : nil,
      stdout: includingCapture ? stdout : nil,
      stderr: includingCapture ? readLog(root.appendingPathComponent(RunLogStream.stderr.fileName)) : nil,
      nextSteps: nextSteps
    )
  }

  @discardableResult
  func hydrate(
    _ job: inout JobRecord,
    fallbackEnvelope: ToolEnvelope? = nil,
    includingCapture: Bool = true,
    redact: (String) -> String = { $0 }
  ) -> ToolEnvelope? {
    let snapshot = load(
      runDirectory: job.runDirectory, stdoutFallback: job.stdout, includingCapture: includingCapture
    )
    let envelope = snapshot.envelope ?? fallbackEnvelope
    job.artifacts = snapshot.artifacts
    if !includingCapture {
      job.command = redact(job.command)
      job.stdout = redact(job.stdout)
      job.stderr = redact(job.stderr)
    }
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
      return nil
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
    return envelope
  }

  func capture(for job: JobRecord, redact: (String) -> String) throws -> JobRunCapture {
    let root = URL(fileURLWithPath: job.runDirectory, isDirectory: true)
    try Task.checkCancellation()
    let command = readText(root.appendingPathComponent("command.txt")) ?? job.command
    try Task.checkCancellation()
    let stdout = readLog(root.appendingPathComponent(RunLogStream.stdout.fileName)) ?? job.stdout
    try Task.checkCancellation()
    return JobRunCapture(
      command: redact(command),
      stdout: redact(stdout),
      stderr: redact(readLog(root.appendingPathComponent(RunLogStream.stderr.fileName)) ?? job.stderr)
    )
  }

  func writeCaptureFiles(
    runDirectory: String,
    command: String,
    stdout: String,
    stderr: String,
    retaining retainedLogs: Set<RunLogStream> = []
  ) {
    let root = URL(fileURLWithPath: runDirectory, isDirectory: true)
    try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    write(command, to: root.appendingPathComponent("command.txt"))
    if !retainedLogs.contains(.stdout) {
      write(stdout, to: root.appendingPathComponent(RunLogStream.stdout.fileName))
    }
    if !retainedLogs.contains(.stderr) {
      write(stderr, to: root.appendingPathComponent(RunLogStream.stderr.fileName))
    }
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

  private func readLog(_ url: URL) -> String? {
    BoundedProcessOutput.read(at: url, maximumBytes: maximumSidecarBytes)?.text
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
