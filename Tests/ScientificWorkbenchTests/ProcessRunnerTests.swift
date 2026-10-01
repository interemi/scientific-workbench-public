import Darwin
import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func externalProcessTimeoutPolicyProvidesSafeFiveMinutePresets() {
    #expect(ExternalProcessTimeoutPolicy.options.first == 5)
    #expect(ExternalProcessTimeoutPolicy.options.last == 120)
    #expect(ExternalProcessTimeoutPolicy.options.count == 24)
    #expect(ExternalProcessTimeoutPolicy.options.allSatisfy { $0.isMultiple(of: 5) })
    #expect(ExternalProcessTimeoutPolicy.normalized(minutes: -10) == 5)
    #expect(ExternalProcessTimeoutPolicy.normalized(minutes: 32) == 30)
    #expect(ExternalProcessTimeoutPolicy.normalized(minutes: 33) == 35)
    #expect(ExternalProcessTimeoutPolicy.normalized(minutes: 999) == 120)
    #expect(ExternalProcessTimeoutPolicy.seconds(for: 30) == 1_800)
  }

  @Test
  func processRunnerCancelsActiveProcess() async throws {
    let runner = ProcessRunner()
    let command = ProcessCommand(
      executable: "/bin/sleep",
      arguments: ["5"],
      workingDirectory: nil
    )
    let startedAt = Date()
    let task = Task {
      try await runner.run(command)
    }

    try await Task.sleep(nanoseconds: 200_000_000)
    await runner.cancelAll()
    let result = try await task.value

    #expect(result.exitCode != 0)
    #expect(result.finishedAt.timeIntervalSince(startedAt) < 3)
  }

  @Test
  func processRunnerUsesSelectedWorkingDirectory() async throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-WorkingDirectory-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }

    let result = try await ProcessRunner().run(
      ProcessCommand(
        executable: "/bin/pwd",
        arguments: [],
        workingDirectory: directory.path
      )
    )

    let reportedPath = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
    #expect(result.exitCode == 0)
    #expect(
      URL(fileURLWithPath: reportedPath).resolvingSymlinksInPath().path
        == directory.resolvingSymlinksInPath().path
    )
  }

  @Test
  func processRunnerSanitizesEnvironmentByDefault() {
    let environment = ProcessRunner.sanitizedEnvironment(parent: [
      "HOME": "/Users/example",
      "LANG": "en_US.UTF-8",
      "LC_ALL": "C",
      "OPENAI_API_KEY": "sk-should-not-leak",
      "ASTROMETRY_NET_API_KEY_FILE": "/tmp/key-file",
      "GITHUB_PAT": "github-pat-should-not-leak",
      "HTTP_COOKIE": "cookie-should-not-leak",
      "APP_SESSION_ID": "session-should-not-leak",
      "DATABASE_URL": "postgres://user:password@database.example/science",
      "SERVICE_TOKEN": "token-should-not-leak",
      "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
      "PATH": "/custom/bin:/usr/bin",
      "CUSTOM_ALLOWED": "kept",
      "SCIENTIFIC_WORKBENCH_ALLOW_PROCESS_ENV": "CUSTOM_ALLOWED,SERVICE_TOKEN"
    ])

    #expect(environment["HOME"] == "/Users/example")
    #expect(environment["LANG"] == "en_US.UTF-8")
    #expect(environment["LC_ALL"] == "C")
    #expect(environment["CUSTOM_ALLOWED"] == "kept")
    #expect(environment["OPENAI_API_KEY"] == nil)
    #expect(environment["ASTROMETRY_NET_API_KEY_FILE"] == nil)
    #expect(environment["GITHUB_PAT"] == nil)
    #expect(environment["HTTP_COOKIE"] == nil)
    #expect(environment["APP_SESSION_ID"] == nil)
    #expect(environment["DATABASE_URL"] == nil)
    #expect(environment["SERVICE_TOKEN"] == nil)
    #expect(environment["SSH_AUTH_SOCK"] == nil)
    #expect(environment["PATH"]?.contains("/opt/homebrew/bin") == true)
    #expect(environment["PATH"]?.contains("/custom/bin") == true)
  }

  @Test
  func processRunnerAppliesOnlySafeEnvironmentOverrides() {
    let environment = ProcessRunner.sanitizedEnvironment(
      parent: [
        "HOME": "/Users/example",
        "PYTHONPATH": "/untrusted/user/path",
        "OPENAI_API_KEY": "sk-should-not-leak"
      ],
      overrides: [
        "PYTHONPATH": "/trusted/skill/scripts:/trusted/skill/fixtures",
        "DATABASE_URL": "postgres://user:password@database.example/science",
        "PUBLIC_SERVICE_URL": "https://database.example/science",
        "OPENAI_API_KEY": "sk-should-not-leak",
        "BAD-NAME": "ignored"
      ]
    )

    #expect(environment["HOME"] == "/Users/example")
    #expect(environment["PYTHONPATH"] == "/trusted/skill/scripts:/trusted/skill/fixtures")
    #expect(environment["DATABASE_URL"] == nil)
    #expect(environment["PUBLIC_SERVICE_URL"] == "https://database.example/science")
    #expect(environment["OPENAI_API_KEY"] == nil)
    #expect(environment["BAD-NAME"] == nil)
  }

  @Test
  func processRunnerCanInheritFilteredEnvironmentForCompatibility() {
    let environment = ProcessRunner.sanitizedEnvironment(parent: [
      "SCIENTIFIC_WORKBENCH_INHERIT_PROCESS_ENV": "1",
      "UNUSUAL_TOOL_FLAG": "enabled",
      "XAI_API_KEY": "xai-should-not-leak",
      "BUILD_PASSWORD": "password-should-not-leak",
      "GITHUB_PAT": "github-pat-should-not-leak",
      "HTTP_COOKIE": "cookie-should-not-leak",
      "APP_SESSION_ID": "session-should-not-leak",
      "DATABASE_URL": "postgres://user:password@database.example/science",
      "PUBLIC_SERVICE_URL": "https://database.example/science",
      "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
      "DYLD_INSERT_LIBRARIES": "/tmp/untrusted.dylib",
      "LD_PRELOAD": "/tmp/untrusted.so",
      "BASH_ENV": "/tmp/untrusted-bash-env",
      "ENV": "/tmp/untrusted-shell-env",
      "CDPATH": "/tmp/untrusted-cdpath",
      "PYTHONHOME": "/tmp/untrusted-python-home",
      "PYTHONPATH": "/tmp/untrusted-python-path",
      "NODE_OPTIONS": "--require=/tmp/untrusted-node.js",
      "RUBYOPT": "-r/tmp/untrusted-ruby.rb",
      "PATH": "/compat/bin"
    ])

    #expect(environment["UNUSUAL_TOOL_FLAG"] == "enabled")
    #expect(environment["XAI_API_KEY"] == nil)
    #expect(environment["BUILD_PASSWORD"] == nil)
    #expect(environment["GITHUB_PAT"] == nil)
    #expect(environment["HTTP_COOKIE"] == nil)
    #expect(environment["APP_SESSION_ID"] == nil)
    #expect(environment["DATABASE_URL"] == nil)
    #expect(environment["PUBLIC_SERVICE_URL"] == "https://database.example/science")
    #expect(environment["SSH_AUTH_SOCK"] == nil)
    #expect(environment["DYLD_INSERT_LIBRARIES"] == nil)
    #expect(environment["LD_PRELOAD"] == nil)
    #expect(environment["BASH_ENV"] == nil)
    #expect(environment["ENV"] == nil)
    #expect(environment["CDPATH"] == nil)
    #expect(environment["PYTHONHOME"] == nil)
    #expect(environment["PYTHONPATH"] == nil)
    #expect(environment["NODE_OPTIONS"] == nil)
    #expect(environment["RUBYOPT"] == nil)
    #expect(environment["PATH"]?.contains("/compat/bin") == true)
    #expect(environment["PATH"]?.hasPrefix("/usr/local/bin:/opt/homebrew/bin:") == true)
  }

  @Test
  func processRunnerStrictEnvironmentIgnoresCompatibilitySwitches() {
    let environment = ProcessRunner.sanitizedEnvironment(
      parent: [
        "HOME": "/Users/example",
        "LC_ALL": "C",
        "PATH": "/untrusted/compat/bin",
        "SCIENTIFIC_WORKBENCH_INHERIT_PROCESS_ENV": "1",
        "SCIENTIFIC_WORKBENCH_ALLOW_PROCESS_ENV": "CUSTOM_ALLOWED,SSH_AUTH_SOCK",
        "UNUSUAL_TOOL_FLAG": "must-not-leak",
        "CUSTOM_ALLOWED": "must-not-leak",
        "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
        "GITHUB_PAT": "github-pat-should-not-leak",
        "HTTP_COOKIE": "cookie-should-not-leak",
        "APP_SESSION_ID": "session-should-not-leak",
        "DATABASE_URL": "postgres://user:password@database.example/science"
      ],
      policy: .strict
    )

    #expect(environment["HOME"] == "/Users/example")
    #expect(environment["LC_ALL"] == "C")
    #expect(environment["UNUSUAL_TOOL_FLAG"] == nil)
    #expect(environment["CUSTOM_ALLOWED"] == nil)
    #expect(environment["SSH_AUTH_SOCK"] == nil)
    #expect(environment["GITHUB_PAT"] == nil)
    #expect(environment["HTTP_COOKIE"] == nil)
    #expect(environment["APP_SESSION_ID"] == nil)
    #expect(environment["DATABASE_URL"] == nil)
    #expect(environment["PATH"]?.contains("/untrusted/compat/bin") == false)
    #expect(environment["PATH"]?.contains("/usr/bin") == true)
  }

  @Test
  func processRunnerTimesOutLongRunningProcess() async throws {
    let runner = ProcessRunner(defaultTimeoutSeconds: 0.3)
    let command = ProcessCommand(
      executable: "/bin/sleep",
      arguments: ["5"],
      workingDirectory: nil
    )
    let startedAt = Date()

    do {
      _ = try await runner.run(command)
      Issue.record("Expected long-running process to time out.")
    } catch ProcessRunnerError.timedOut(let seconds) {
      #expect(seconds == 0.3)
      #expect(Date().timeIntervalSince(startedAt) < 3)
    } catch {
      Issue.record("Unexpected timeout error: \(error)")
    }
  }

  @Test
  func processRunnerStopsWhenTemporaryOutputExceedsDiskLimit() async throws {
    let runner = ProcessRunner(
      defaultTimeoutSeconds: 30,
      maximumCapturedOutputBytes: 1_024,
      maximumTemporaryOutputBytesPerStream: 4_096
    )
    let startedAt = Date()

    do {
      _ = try await runner.run(
        ProcessCommand(
          executable: "/usr/bin/python3",
          arguments: [
            "-c",
            "import sys, time; sys.stdout.write('x' * 100000); sys.stdout.flush(); time.sleep(30)"
          ],
          workingDirectory: nil
        )
      )
      Issue.record("Expected excessive temporary stdout to stop the process.")
    } catch ProcessRunnerError.outputLimitExceeded(let stream, let limitBytes) {
      #expect(stream == "stdout")
      #expect(limitBytes == 4_096)
      #expect(Date().timeIntervalSince(startedAt) < 3)
    } catch {
      Issue.record("Unexpected temporary-output limit error: \(error)")
    }
  }

  @Test
  func processRunnerTimeoutStillOwnsChildAfterParentExits() async throws {
    let pidDirectory = try makeProcessTreeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: pidDirectory) }
    let parentPIDURL = pidDirectory.appendingPathComponent("exited-parent.pid")
    let childPIDURL = pidDirectory.appendingPathComponent("surviving-child.pid")
    let runner = ProcessRunner(defaultTimeoutSeconds: 0.4)

    do {
      _ = try await runner.run(
        ProcessCommand(
          executable: "/bin/sh",
          arguments: [
            "-c",
            "printf '%s' \"$$\" > \"$1\"; /bin/sleep 30 & printf '%s' \"$!\" > \"$2\"; exit 0",
            "process-runner-fixture",
            parentPIDURL.path,
            childPIDURL.path
          ],
          workingDirectory: nil
        )
      )
      Issue.record("Expected the surviving child process to keep the run active until timeout.")
    } catch ProcessRunnerError.timedOut(let seconds) {
      #expect(seconds == 0.4)
    } catch {
      Issue.record("Unexpected surviving-child timeout error: \(error)")
    }

    let childPID = try await waitForProcessPID(at: childPIDURL)
    #expect(await processTreeExited([childPID]))
  }

  @Test
  func cancellingRunnerTaskStopsChildAfterParentExits() async throws {
    let pidDirectory = try makeProcessTreeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: pidDirectory) }
    let parentPIDURL = pidDirectory.appendingPathComponent("cancelled-parent.pid")
    let childPIDURL = pidDirectory.appendingPathComponent("cancelled-child.pid")
    let runner = ProcessRunner(defaultTimeoutSeconds: 30)
    let task = Task {
      try await runner.run(
        ProcessCommand(
          executable: "/bin/sh",
          arguments: [
            "-c",
            "printf '%s' \"$$\" > \"$1\"; /bin/sleep 30 & printf '%s' \"$!\" > \"$2\"; exit 0",
            "process-runner-fixture",
            parentPIDURL.path,
            childPIDURL.path
          ],
          workingDirectory: nil
        )
      )
    }

    let parentPID = try await waitForProcessPID(at: parentPIDURL)
    let childPID = try await waitForProcessPID(at: childPIDURL)
    #expect(await processTreeExited([parentPID]))
    #expect(processExists(childPID))
    task.cancel()

    do {
      _ = try await task.value
      Issue.record("Expected cancellation while the surviving child was active.")
    } catch ProcessRunnerError.cancelled {
      // Expected.
    } catch {
      Issue.record("Unexpected surviving-child cancellation error: \(error)")
    }
    #expect(await processTreeExited([childPID]))
  }

  @Test
  func processRunnerBoundsNoisyOutputAndPreservesHeadAndTail() async throws {
    let runner = ProcessRunner(maximumCapturedOutputBytes: 1_024)
    let result = try await runner.run(
      ProcessCommand(
        executable: "/usr/bin/python3",
        arguments: [
          "-c",
          "import sys; print('STDOUT_HEAD'); print('x' * 5000); print('STDOUT_TAIL'); "
            + "print('STDERR_HEAD', file=sys.stderr); print('y' * 5000, file=sys.stderr); "
            + "print('STDERR_TAIL', file=sys.stderr)"
        ],
        workingDirectory: nil
      )
    )

    #expect(result.exitCode == 0)
    #expect(result.stdout.contains("STDOUT_HEAD"))
    #expect(result.stdout.contains("STDOUT_TAIL"))
    #expect(result.stdout.contains("Scientific Workbench truncated"))
    #expect(result.stderr.contains("STDERR_HEAD"))
    #expect(result.stderr.contains("STDERR_TAIL"))
    #expect(result.stderr.contains("Scientific Workbench truncated"))
    #expect(result.stdout.utf8.count < 1_200)
    #expect(result.stderr.utf8.count < 1_200)
    #expect(result.stdoutWasTruncated)
    #expect(result.stderrWasTruncated)
    #expect(result.stdoutTotalBytes > result.stdout.utf8.count)
    #expect(result.stderrTotalBytes > result.stderr.utf8.count)
  }

  @Test
  func processRunnerTruncationPreservesFinalEnvelopeAndUTF8Text() async throws {
    let runner = ProcessRunner(maximumCapturedOutputBytes: 1_024)
    let result = try await runner.run(
      ProcessCommand(
        executable: "/usr/bin/python3",
        arguments: [
          "-c",
          "print('BEGIN_' + '🔬' * 1500); "
            + "print('{\"tool\":\"bounded.fixture\",\"status\":\"OK\",\"contract_version\":\"2\"}')"
        ],
        workingDirectory: nil
      )
    )

    let envelope = try #require(ToolEnvelopeParser().parse(result.stdout))
    #expect(envelope.tool == "bounded.fixture")
    #expect(envelope.status == "OK")
    #expect(result.stdoutWasTruncated)
    #expect(result.stdout.contains("🔬"))
  }

  @Test
  func processRunnerReportsEmptyUntruncatedOutput() async throws {
    let runner = ProcessRunner(maximumCapturedOutputBytes: 256)
    let result = try await runner.run(
      ProcessCommand(executable: "/usr/bin/true", arguments: [], workingDirectory: nil)
    )

    #expect(result.stdout.isEmpty)
    #expect(result.stderr.isEmpty)
    #expect(result.stdoutTotalBytes == 0)
    #expect(result.stderrTotalBytes == 0)
    #expect(!result.stdoutWasTruncated)
    #expect(!result.stderrWasTruncated)
  }

  @Test
  func processRunnerCancellationTerminatesOnlyTheOwnedProcessTree() async throws {
    let fixture = processTreeFixtureURL()
    let pidDirectory = try makeProcessTreeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: pidDirectory) }

    let unrelated = Process()
    unrelated.executableURL = URL(fileURLWithPath: "/bin/sleep")
    unrelated.arguments = ["30"]
    try unrelated.run()
    defer {
      if unrelated.isRunning {
        unrelated.terminate()
        unrelated.waitUntilExit()
      }
    }

    let runner = ProcessRunner()
    let task = Task {
      try await runner.run(
        ProcessCommand(
          executable: "/usr/bin/python3",
          arguments: [fixture.path, pidDirectory.path, "parent", "normal"],
          workingDirectory: nil
        )
      )
    }

    let pids = try await waitForProcessTree(in: pidDirectory)
    #expect(processGroupMatchesTree(pids))
    #expect(getpgid(unrelated.processIdentifier) != pids.parent)

    await runner.cancelAll()
    let result = try await task.value

    #expect(result.exitCode != 0)
    #expect(await processTreeExited(pids.all))
    #expect(unrelated.isRunning)
  }

  @Test
  func processRunnerTimeoutTerminatesParentChildAndGrandchild() async throws {
    let fixture = processTreeFixtureURL()
    let pidDirectory = try makeProcessTreeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: pidDirectory) }

    // Give all three Python processes time to start on a loaded CI runner.
    let timeoutSeconds: TimeInterval = 8
    let runner = ProcessRunner(defaultTimeoutSeconds: timeoutSeconds)
    let task = Task {
      try await runner.run(
        ProcessCommand(
          executable: "/usr/bin/python3",
          arguments: [fixture.path, pidDirectory.path, "parent", "ignore-soft"],
          workingDirectory: nil
        )
      )
    }

    let pids = try await waitForProcessTree(in: pidDirectory)
    #expect(processGroupMatchesTree(pids))

    do {
      _ = try await task.value
      Issue.record("Expected the process tree to time out.")
    } catch ProcessRunnerError.timedOut(let seconds) {
      #expect(seconds == timeoutSeconds)
    } catch {
      Issue.record("Unexpected process-tree timeout error: \(error)")
    }

    #expect(await processTreeExited(pids.all))
  }

  private func processTreeFixtureURL() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Fixtures/process_tree_fixture.py")
  }

  private func makeProcessTreeTemporaryDirectory() throws -> URL {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-ProcessTree-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
  }

  private func waitForProcessTree(in directory: URL) async throws -> ProcessTreePIDs {
    let deadline = Date().addingTimeInterval(15)
    while Date() < deadline {
      if let parent = readProcessTreePID(directory.appendingPathComponent("parent.pid")),
         let child = readProcessTreePID(directory.appendingPathComponent("child.pid")),
         let grandchild = readProcessTreePID(directory.appendingPathComponent("grandchild.pid")) {
        return ProcessTreePIDs(parent: parent, child: child, grandchild: grandchild)
      }
      try await Task.sleep(nanoseconds: 50_000_000)
    }
    throw ProcessTreeTestError.fixtureDidNotStart
  }

  private func readProcessTreePID(_ url: URL) -> pid_t? {
    guard let text = try? String(contentsOf: url, encoding: .utf8),
          let pid = pid_t(text.trimmingCharacters(in: .whitespacesAndNewlines)),
          pid > 1 else {
      return nil
    }
    return pid
  }

  private func waitForProcessPID(at url: URL) async throws -> pid_t {
    let deadline = Date().addingTimeInterval(5)
    while Date() < deadline {
      if let pid = readProcessTreePID(url) {
        return pid
      }
      try await Task.sleep(nanoseconds: 50_000_000)
    }
    throw ProcessTreeTestError.fixtureDidNotStart
  }

  private func processGroupMatchesTree(_ pids: ProcessTreePIDs) -> Bool {
    getpgid(pids.parent) == pids.parent
      && getpgid(pids.child) == pids.parent
      && getpgid(pids.grandchild) == pids.parent
  }

  private func processTreeExited(_ pids: [pid_t]) async -> Bool {
    let deadline = Date().addingTimeInterval(4)
    while Date() < deadline {
      if pids.allSatisfy({ !processExists($0) }) {
        return true
      }
      try? await Task.sleep(nanoseconds: 50_000_000)
    }
    return pids.allSatisfy { !processExists($0) }
  }

  private func processExists(_ pid: pid_t) -> Bool {
    if Darwin.kill(pid, 0) == 0 {
      return true
    }
    return errno == EPERM
  }
}

private struct ProcessTreePIDs {
  let parent: pid_t
  let child: pid_t
  let grandchild: pid_t

  var all: [pid_t] {
    [parent, child, grandchild]
  }
}

private enum ProcessTreeTestError: Error {
  case fixtureDidNotStart
}
