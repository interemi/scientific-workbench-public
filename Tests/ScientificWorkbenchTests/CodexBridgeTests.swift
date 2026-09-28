import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func codexBridgeReturnsLastMessageFromFakeCLI() async throws {
    let root = try makeCodexBridgeFixture(
      scriptBody: """
      #!/bin/sh
      last_message=""
      while [ "$#" -gt 0 ]; do
        if [ "$1" = "--output-last-message" ]; then
          shift
          last_message="$1"
        fi
        shift
      done
      printf 'Fake Codex final answer\\n' > "$last_message"
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let response = try await CodexBridge(executablePath: root.appendingPathComponent("fake-codex").path).run(
      prompt: "Explain the fixture.",
      inputPaths: [],
      outputRootPath: root.path,
      sandboxMode: "read-only",
      timeoutSeconds: 5
    )

    #expect(response == "Fake Codex final answer")
  }

  @Test
  func codexBridgeRejectsLastMessageWhenCLIExitsWithFailure() async throws {
    let root = try makeCodexBridgeFixture(
      scriptBody: """
      #!/bin/sh
      last_message=""
      while [ "$#" -gt 0 ]; do
        if [ "$1" = "--output-last-message" ]; then
          shift
          last_message="$1"
        fi
        shift
      done
      printf 'This partial answer must not be accepted\n' > "$last_message"
      printf 'intentional fake Codex failure\n' >&2
      exit 17
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    do {
      _ = try await CodexBridge(executablePath: root.appendingPathComponent("fake-codex").path).run(
        prompt: "Return a partial answer and fail.",
        inputPaths: [],
        outputRootPath: root.path,
        sandboxMode: "read-only",
        timeoutSeconds: 5
      )
      Issue.record("Expected a nonzero Codex CLI exit to reject its last message.")
    } catch CodexBridgeError.executionFailed(let message) {
      #expect(message.contains("intentional fake Codex failure"))
      #expect(!message.contains("partial answer"))
    } catch {
      Issue.record("Unexpected nonzero Codex CLI error: \(error)")
    }
  }

  @Test
  func codexBridgeRejectsSuccessfulEmptyResponses() async throws {
    let root = try makeCodexBridgeFixture(
      scriptBody: """
      #!/bin/sh
      exit 0
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    var sawEmptyResponse = false
    do {
      _ = try await CodexBridge(executablePath: root.appendingPathComponent("fake-codex").path).run(
        prompt: "Return nothing.",
        inputPaths: [],
        outputRootPath: root.path,
        sandboxMode: "read-only",
        timeoutSeconds: 5
      )
      Issue.record("Expected empty Codex response to fail.")
    } catch CodexBridgeError.emptyResponse {
      sawEmptyResponse = true
    } catch {
      Issue.record("Unexpected error: \(error)")
    }
    #expect(sawEmptyResponse)
  }

  @Test
  func codexBridgeDowngradesUnrestrictedSandboxRequestsToReadOnly() async throws {
    let root = try makeCodexBridgeFixture(
      scriptBody: """
      #!/bin/sh
      last_message=""
      sandbox=""
      while [ "$#" -gt 0 ]; do
        if [ "$1" = "--output-last-message" ]; then
          shift
          last_message="$1"
        elif [ "$1" = "--sandbox" ]; then
          shift
          sandbox="$1"
        fi
        shift
      done
      if [ "$sandbox" != "read-only" ]; then
        printf 'unsafe sandbox: %s\n' "$sandbox" >&2
        exit 93
      fi
      printf 'safe sandbox confirmed\n' > "$last_message"
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let response = try await CodexBridge(
      executablePath: root.appendingPathComponent("fake-codex").path
    ).run(
      prompt: "Do not use unrestricted access.",
      inputPaths: [],
      outputRootPath: root.path,
      sandboxMode: "danger-full-access",
      timeoutSeconds: 5
    )

    #expect(response == "safe sandbox confirmed")
  }

  @Test
  func codexBridgeTimesOutFakeCLIQuickly() async throws {
    let root = try makeCodexBridgeFixture(
      scriptBody: """
      #!/bin/sh
      sleep 30
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    do {
      _ = try await CodexBridge(executablePath: root.appendingPathComponent("fake-codex").path).run(
        prompt: "Sleep forever.",
        inputPaths: [],
        outputRootPath: root.path,
        sandboxMode: "read-only",
        timeoutSeconds: 0.1
      )
      Issue.record("Expected fake Codex CLI to time out.")
    } catch CodexBridgeError.timedOut(let seconds) {
      #expect(Int(seconds) == 5)
    } catch {
      Issue.record("Unexpected error: \(error)")
    }
  }

  @Test
  func codexBridgeDoesNotExposeParentSecrets() async throws {
    let root = try makeCodexBridgeFixture(
      scriptBody: """
      #!/bin/sh
      if [ -n "${OPENAI_API_KEY+x}" ] || [ -n "${UNLISTED_FLAG+x}" ] || \
         [ -n "${CUSTOM_ALLOWED+x}" ] || [ -n "${SSH_AUTH_SOCK+x}" ] || \
         [ -n "${GITHUB_PAT+x}" ] || [ -n "${HTTP_COOKIE+x}" ] || \
         [ -n "${APP_SESSION_ID+x}" ] || [ -n "${DATABASE_URL+x}" ]; then
        printf 'restricted environment leaked\n' >&2
        exit 91
      fi
      if [ "$HOME" != "/safe/home" ]; then
        printf 'expected safe HOME value\n' >&2
        exit 92
      fi
      printf 'restricted environment confirmed\n'
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
    let response = try await CodexBridge(
      executablePath: root.appendingPathComponent("fake-codex").path,
      runner: runner
    ).run(
      prompt: "Inspect the environment.",
      inputPaths: [],
      outputRootPath: root.path,
      sandboxMode: "read-only",
      timeoutSeconds: 5
    )

    #expect(response == "restricted environment confirmed")
  }

  @Test
  func cancellingCodexBridgeStopsTheActiveCLI() async throws {
    let root = try makeCodexBridgeFixture(
      scriptBody: """
      #!/bin/sh
      sleep 30
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let bridge = CodexBridge(
      executablePath: root.appendingPathComponent("fake-codex").path
    )
    let startedAt = Date()
    let task = Task {
      try await bridge.run(
        prompt: "Wait forever.",
        inputPaths: [],
        outputRootPath: root.path,
        sandboxMode: "read-only",
        timeoutSeconds: 30
      )
    }

    try await Task.sleep(nanoseconds: 200_000_000)
    task.cancel()

    do {
      _ = try await task.value
      Issue.record("Expected the Codex bridge task to be cancelled.")
    } catch CodexBridgeError.cancelled {
      #expect(Date().timeIntervalSince(startedAt) < 3)
    } catch {
      Issue.record("Unexpected cancellation error: \(error)")
    }
  }

  private func makeCodexBridgeFixture(scriptBody: String) throws -> URL {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-CodexBridge-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    let executable = root.appendingPathComponent("fake-codex")
    try scriptBody.write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: NSNumber(value: Int16(0o755))],
      ofItemAtPath: executable.path
    )
    return root
  }
}
