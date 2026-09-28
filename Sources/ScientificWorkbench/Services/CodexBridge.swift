import Foundation

struct CodexBridge: Sendable {
  static let defaultTimeoutSeconds: TimeInterval = 60

  var executablePath: String
  private let runner: ProcessRunner

  init(
    executablePath: String,
    runner: ProcessRunner = ProcessRunner()
  ) {
    self.executablePath = executablePath
    self.runner = runner
  }

  var isAvailable: Bool {
    FileManager.default.isExecutableFile(atPath: resolvedExecutablePath)
  }

  var resolvedExecutablePath: String {
    if !executablePath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      return executablePath
    }
    let bundled = "/Applications/Codex.app/Contents/Resources/codex"
    if FileManager.default.isExecutableFile(atPath: bundled) {
      return bundled
    }
    return "/usr/local/bin/codex"
  }

  func run(
    prompt: String,
    inputPaths: [String],
    outputRootPath: String,
    sandboxMode: String,
    timeoutSeconds: TimeInterval = Self.defaultTimeoutSeconds
  ) async throws -> String {
    guard isAvailable else {
      throw CodexBridgeError.missingExecutable(resolvedExecutablePath)
    }

    let tempURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Codex-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempURL, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempURL) }

    let lastMessageURL = tempURL.appendingPathComponent("last-message.txt")
    let timeout = max(5, timeoutSeconds)
    var command = ProcessCommand(
      executable: resolvedExecutablePath,
      arguments: [
        "--ask-for-approval", "never",
        "exec",
        "--skip-git-repo-check",
        "--color", "never",
        "--sandbox", normalizedSandboxMode(sandboxMode),
        "--cd", outputRootPath,
        "--output-last-message", lastMessageURL.path,
        augmentedPrompt(prompt, inputPaths: inputPaths, outputRootPath: outputRootPath)
      ],
      workingDirectory: outputRootPath
    )
    command.timeoutSeconds = timeout
    command.environmentPolicy = .strict
    command.redirectStandardInputToNull = true

    let result: ProcessResult
    do {
      result = try await runner.run(command)
    } catch ProcessRunnerError.cancelled {
      throw CodexBridgeError.cancelled
    } catch ProcessRunnerError.timedOut(let seconds) {
      throw CodexBridgeError.timedOut(seconds)
    }

    let lastMessage = (try? String(contentsOf: lastMessageURL, encoding: .utf8))?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let stdout = result.stdout
    let stderr = result.stderr

    guard result.exitCode == 0 else {
      let diagnostic = stderr.isEmpty ? stdout : stderr
      let fallback = "Process exited with code \(result.exitCode)."
      throw CodexBridgeError.executionFailed(diagnostic.isEmpty ? fallback : diagnostic)
    }

    if let lastMessage, !lastMessage.isEmpty {
      return lastMessage
    }

    if !stdout.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      return stdout.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    throw CodexBridgeError.emptyResponse
  }

  private func normalizedSandboxMode(_ sandboxMode: String) -> String {
    sandboxMode == "workspace-write" ? "workspace-write" : "read-only"
  }

  private func augmentedPrompt(_ prompt: String, inputPaths: [String], outputRootPath: String) -> String {
    """
    You are running inside Scientific Workbench through Codex CLI.
    Keep the user-facing answer concise.
    Treat attached paths as read-only unless the user explicitly asks for edits.
    Put any generated outputs under this output root when possible:
    \(outputRootPath)

    Attached paths:
    \(inputPaths.isEmpty ? "(none)" : inputPaths.joined(separator: "\n"))

    User request:
    \(prompt)
    """
  }
}

enum CodexBridgeError: LocalizedError {
  case missingExecutable(String)
  case executionFailed(String)
  case timedOut(TimeInterval)
  case cancelled
  case emptyResponse

  var errorDescription: String? {
    switch self {
    case .missingExecutable(let path):
      return "Could not find an executable Codex CLI at \(path)."
    case .executionFailed(let message):
      return "Codex CLI failed: \(message)"
    case .timedOut(let seconds):
      return "Codex CLI did not finish within \(Int(seconds)) seconds. No result was accepted; try a narrower prompt or run this directly in Codex."
    case .cancelled:
      return "Codex CLI run was cancelled. No result was accepted."
    case .emptyResponse:
      return "Codex CLI finished but returned no final message. No result was accepted; try a narrower prompt or run this directly in Codex."
    }
  }
}
