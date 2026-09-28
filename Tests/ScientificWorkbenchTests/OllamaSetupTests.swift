import Darwin
import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func ollamaModelProfilesExposeBalancedDefaultAndCustomMatching() {
    #expect(OllamaModelProfile.recommended == .balanced)
    #expect(OllamaModelProfile.allCases.map(\.model) == ["qwen3:1.7b", "qwen3:4b-instruct", "qwen3:8b"])
    #expect(OllamaModelProfile.matching(model: " qwen3:4b-instruct ") == .balanced)
    #expect(OllamaModelProfile.matching(model: "custom-local-model") == nil)
    #expect(OllamaModelProfile.balanced.detailText.contains("16 GB RAM"))
  }

  @Test
  func ollamaSetupServiceLocatesCLIAndParsesInstalledModels() async throws {
    let recorder = RequestRecorder(
      responseBody: #"{"models":[{"name":"qwen3:4b-instruct"},{"name":"llama3.2"}]}"#
    )
    let service = OllamaSetupService(
      pathEnvironment: "/custom/bin",
      fileExists: { $0 == "/custom/bin/ollama" },
      dataLoader: { request in
        try await recorder.load(request)
      }
    )

    let status = await service.status(
      baseURL: "http://localhost:11434",
      model: "qwen3:4b-instruct"
    )

    let request = try #require(await recorder.requests.first)
    #expect(service.locateCLI() == "/custom/bin/ollama")
    #expect(status.serverReachable == true)
    #expect(status.modelInstalled == true)
    #expect(status.badgeTitle == "ok")
    #expect(request.url?.absoluteString == "http://localhost:11434/api/tags")
    #expect(request.timeoutInterval == 3)
  }

  @Test
  func ollamaSetupServiceReportsMissingInstallBeforeNetworkDetails() async {
    let service = OllamaSetupService(
      pathEnvironment: "",
      fileExists: { _ in false },
      dataLoader: { _ in
        throw URLError(.cannotConnectToHost)
      }
    )

    let status = await service.status(
      baseURL: "http://localhost:11434",
      model: "qwen3:4b-instruct"
    )

    #expect(status.cliPath == nil)
    #expect(status.serverReachable == false)
    #expect(status.badgeTitle == "install")
    #expect(status.message.contains("Install Ollama"))
  }

  @Test
  func ollamaSetupServiceRejectsRemoteEndpointBeforeAnyNetworkRequest() async {
    let recorder = RequestRecorder(responseBody: #"{"models":[]}"#)
    let service = OllamaSetupService(
      pathEnvironment: "/custom/bin",
      fileExists: { $0 == "/custom/bin/ollama" },
      dataLoader: { request in
        try await recorder.load(request)
      }
    )

    let status = await service.status(
      baseURL: "https://ollama.example.invalid:11434",
      model: "qwen3:4b-instruct"
    )

    #expect(await recorder.requests.isEmpty)
    #expect(!status.serverReachable)
    #expect(status.message.localizedCaseInsensitiveContains("loopback"))
    #expect(status.message.contains("ollama.example.invalid"))
  }

  @Test
  func ollamaPullUsesRestrictedEnvironmentAndCapturesLargeOutput() async throws {
    let root = try makeFakeOllamaCLI(
      scriptBody: """
      #!/bin/sh
      if [ -n "${OPENAI_API_KEY+x}" ] || [ -n "${UNLISTED_FLAG+x}" ] || \
         [ -n "${CUSTOM_ALLOWED+x}" ] || [ -n "${SSH_AUTH_SOCK+x}" ] || \
         [ -n "${GITHUB_PAT+x}" ] || [ -n "${HTTP_COOKIE+x}" ] || \
         [ -n "${APP_SESSION_ID+x}" ] || [ -n "${DATABASE_URL+x}" ]; then
        printf 'restricted environment leaked\n' >&2
        exit 91
      fi
      if [ "$1" != "pull" ] || [ "$2" != "test-model" ]; then
        printf 'unexpected arguments\n' >&2
        exit 92
      fi
      /usr/bin/python3 -c 'import sys; sys.stdout.write("o" * 200000 + "\\nOLLAMA_STDOUT_DONE\\n"); sys.stderr.write("e" * 200000 + "\\nOLLAMA_STDERR_DONE\\n")'
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let runner = ProcessRunner(parentEnvironment: {
      [
        "HOME": "/safe/home",
        "PATH": "/usr/bin:/bin",
        "SCIENTIFIC_WORKBENCH_INHERIT_PROCESS_ENV": "1",
        "SCIENTIFIC_WORKBENCH_ALLOW_PROCESS_ENV": "CUSTOM_ALLOWED,SSH_AUTH_SOCK",
        "OPENAI_API_KEY": "sk-must-not-leak",
        "UNLISTED_FLAG": "must-not-leak",
        "CUSTOM_ALLOWED": "must-not-leak",
        "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
        "GITHUB_PAT": "github-pat-must-not-leak",
        "HTTP_COOKIE": "cookie-must-not-leak",
        "APP_SESSION_ID": "session-must-not-leak",
        "DATABASE_URL": "postgres://user:password@database.example/science"
      ]
    })
    let service = OllamaSetupService(
      pathEnvironment: root.path,
      runner: runner,
      pullTimeoutSeconds: 5
    )

    let result = try await service.pullModel("test-model")

    #expect(result.exitCode == 0)
    #expect(result.stdout.contains("OLLAMA_STDOUT_DONE"))
    #expect(result.stderr.contains("OLLAMA_STDERR_DONE"))
    #expect(result.stdout.utf8.count > 200_000)
    #expect(result.stderr.utf8.count > 200_000)
  }

  @Test
  func ollamaPullTimesOutThroughTheHardenedRunner() async throws {
    let root = try makeFakeOllamaCLI(
      scriptBody: """
      #!/bin/sh
      sleep 30
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let service = OllamaSetupService(
      pathEnvironment: root.path,
      pullTimeoutSeconds: 0.3
    )
    let startedAt = Date()

    do {
      _ = try await service.pullModel("test-model")
      Issue.record("Expected the Ollama pull to time out.")
    } catch OllamaSetupError.timedOut(let seconds) {
      #expect(seconds == 0.3)
      #expect(Date().timeIntervalSince(startedAt) < 3)
    } catch {
      Issue.record("Unexpected timeout error: \(error)")
    }
  }

  @Test
  func cancellingOllamaPullTerminatesItsProcessGroup() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-OllamaTree-\(UUID().uuidString)", isDirectory: true)
    let parentPIDURL = root.appendingPathComponent("parent.pid")
    let childPIDURL = root.appendingPathComponent("child.pid")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let executable = root.appendingPathComponent("ollama")
    let scriptBody = """
    #!/bin/sh
    printf '%s' "$$" > "\(parentPIDURL.path)"
    /bin/sleep 30 &
    printf '%s' "$!" > "\(childPIDURL.path)"
    wait
    """
    try scriptBody.write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: NSNumber(value: Int16(0o755))],
      ofItemAtPath: executable.path
    )

    let service = OllamaSetupService(
      pathEnvironment: root.path,
      pullTimeoutSeconds: 30
    )
    let task = Task {
      try await service.pullModel("test-model")
    }

    let parentPID = try await waitForOllamaFixturePID(at: parentPIDURL)
    let childPID = try await waitForOllamaFixturePID(at: childPIDURL)
    #expect(getpgid(parentPID) == parentPID)
    #expect(getpgid(childPID) == parentPID)

    task.cancel()
    do {
      _ = try await task.value
      Issue.record("Expected the Ollama pull task to be cancelled.")
    } catch OllamaSetupError.cancelled {
      // Expected.
    } catch {
      Issue.record("Unexpected cancellation error: \(error)")
    }

    #expect(await ollamaFixtureProcessesExited([parentPID, childPID]))
  }

  private func makeFakeOllamaCLI(scriptBody: String) throws -> URL {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-OllamaCLI-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    let executable = root.appendingPathComponent("ollama")
    try scriptBody.write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: NSNumber(value: Int16(0o755))],
      ofItemAtPath: executable.path
    )
    return root
  }

  private func waitForOllamaFixturePID(at url: URL) async throws -> pid_t {
    let deadline = Date().addingTimeInterval(5)
    while Date() < deadline {
      if let text = try? String(contentsOf: url, encoding: .utf8),
         let pid = pid_t(text.trimmingCharacters(in: .whitespacesAndNewlines)),
         pid > 1 {
        return pid
      }
      try await Task.sleep(nanoseconds: 50_000_000)
    }
    throw OllamaFixtureError.processDidNotStart
  }

  private func ollamaFixtureProcessesExited(_ pids: [pid_t]) async -> Bool {
    let deadline = Date().addingTimeInterval(4)
    while Date() < deadline {
      if pids.allSatisfy({ !ollamaFixtureProcessExists($0) }) {
        return true
      }
      try? await Task.sleep(nanoseconds: 50_000_000)
    }
    return pids.allSatisfy { !ollamaFixtureProcessExists($0) }
  }

  private func ollamaFixtureProcessExists(_ pid: pid_t) -> Bool {
    if Darwin.kill(pid, 0) == 0 {
      return true
    }
    return errno == EPERM
  }

}

private enum OllamaFixtureError: Error {
  case processDidNotStart
}
