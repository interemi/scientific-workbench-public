import Darwin
import Foundation

struct ProcessGroupSmokeOptions {
  let fixturePath: String
  let reportPath: String

  static func parse(_ arguments: [String]) -> ProcessGroupSmokeOptions? {
    guard let index = arguments.firstIndex(of: "--process-group-smoke"),
          arguments.indices.contains(index + 2) else {
      return nil
    }
    return ProcessGroupSmokeOptions(
      fixturePath: arguments[index + 1],
      reportPath: arguments[index + 2]
    )
  }
}

struct ProcessGroupSmokeService {
  func run(options: ProcessGroupSmokeOptions) async -> Int32 {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-ProcessGroup-Smoke-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }

    do {
      try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
      let cancellation = try await runCancellationScenario(
        fixturePath: options.fixturePath,
        root: root.appendingPathComponent("cancellation", isDirectory: true)
      )
      let timeout = try await runTimeoutScenario(
        fixturePath: options.fixturePath,
        root: root.appendingPathComponent("timeout", isDirectory: true)
      )
      let report = ProcessGroupSmokeReport(
        passed: cancellation.passed && timeout.passed,
        cancellation: cancellation,
        timeout: timeout
      )
      try write(report, to: options.reportPath)
      return report.passed ? 0 : 1
    } catch {
      let report = ProcessGroupSmokeReport(
        passed: false,
        cancellation: .failedBeforeLaunch(error.localizedDescription),
        timeout: .failedBeforeLaunch("Not run because cancellation scenario failed.")
      )
      try? write(report, to: options.reportPath)
      return 1
    }
  }

  private func runCancellationScenario(
    fixturePath: String,
    root: URL
  ) async throws -> ProcessGroupSmokeScenario {
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
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
          arguments: [fixturePath, root.path, "parent", "normal"],
          workingDirectory: nil
        )
      )
    }

    let pids = try await waitForProcessTree(in: root)
    defer { forceCleanupIfOwned(pids) }
    let snapshot = processSnapshot(pids.all + [unrelated.processIdentifier])
    let processGroupID = getpgid(pids.parent)
    let ownedGroup = processGroupID == pids.parent && processGroupMatchesTree(pids)
    let unrelatedOutsideGroup = getpgid(unrelated.processIdentifier) != pids.parent

    await runner.cancelAll()
    let result = try await task.value
    let treeExited = await processTreeExited(pids.all)
    let unrelatedSurvived = unrelated.isRunning

    return ProcessGroupSmokeScenario(
      passed: ownedGroup
        && unrelatedOutsideGroup
        && result.exitCode != 0
        && treeExited
        && unrelatedSurvived,
      parentPID: pids.parent,
      childPID: pids.child,
      grandchildPID: pids.grandchild,
      processGroupID: processGroupID,
      processSnapshot: snapshot,
      treeExited: treeExited,
      unrelatedProcessSurvived: unrelatedSurvived,
      outcome: "exit_code=\(result.exitCode)"
    )
  }

  private func runTimeoutScenario(
    fixturePath: String,
    root: URL
  ) async throws -> ProcessGroupSmokeScenario {
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    let runner = ProcessRunner(defaultTimeoutSeconds: 1.0)
    let task = Task {
      try await runner.run(
        ProcessCommand(
          executable: "/usr/bin/python3",
          arguments: [fixturePath, root.path, "parent", "ignore-soft"],
          workingDirectory: nil
        )
      )
    }

    let pids = try await waitForProcessTree(in: root)
    defer { forceCleanupIfOwned(pids) }
    let snapshot = processSnapshot(pids.all)
    let processGroupID = getpgid(pids.parent)
    let ownedGroup = processGroupID == pids.parent && processGroupMatchesTree(pids)
    let outcome: String
    do {
      let result = try await task.value
      outcome = "unexpected_exit_code=\(result.exitCode)"
    } catch ProcessRunnerError.timedOut(let seconds) {
      outcome = "timed_out_after=\(seconds)"
    } catch {
      outcome = "unexpected_error=\(error.localizedDescription)"
    }
    let treeExited = await processTreeExited(pids.all)

    return ProcessGroupSmokeScenario(
      passed: ownedGroup && outcome.hasPrefix("timed_out_after=") && treeExited,
      parentPID: pids.parent,
      childPID: pids.child,
      grandchildPID: pids.grandchild,
      processGroupID: processGroupID,
      processSnapshot: snapshot,
      treeExited: treeExited,
      unrelatedProcessSurvived: nil,
      outcome: outcome
    )
  }

  private func waitForProcessTree(in directory: URL) async throws -> ProcessTreePIDs {
    let deadline = Date().addingTimeInterval(5)
    while Date() < deadline {
      if let parent = readPID(directory.appendingPathComponent("parent.pid")),
         let child = readPID(directory.appendingPathComponent("child.pid")),
         let grandchild = readPID(directory.appendingPathComponent("grandchild.pid")) {
        return ProcessTreePIDs(parent: parent, child: child, grandchild: grandchild)
      }
      try await Task.sleep(nanoseconds: 50_000_000)
    }
    throw ProcessGroupSmokeError.fixtureDidNotStart
  }

  private func readPID(_ url: URL) -> pid_t? {
    guard let text = try? String(contentsOf: url, encoding: .utf8),
          let pid = pid_t(text.trimmingCharacters(in: .whitespacesAndNewlines)),
          pid > 1 else {
      return nil
    }
    return pid
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

  private func forceCleanupIfOwned(_ pids: ProcessTreePIDs) {
    guard pids.parent > 1, getpgid(pids.parent) == pids.parent else { return }
    Darwin.kill(-pids.parent, SIGKILL)
  }

  private func processSnapshot(_ pids: [pid_t]) -> [String] {
    let process = Process()
    let pipe = Pipe()
    process.executableURL = URL(fileURLWithPath: "/bin/ps")
    process.arguments = [
      "-o", "pid=,ppid=,pgid=,stat=,command=",
      "-p", pids.map(String.init).joined(separator: ",")
    ]
    process.standardOutput = pipe
    process.standardError = FileHandle.nullDevice
    do {
      try process.run()
      process.waitUntilExit()
      let data = pipe.fileHandleForReading.readDataToEndOfFile()
      return String(decoding: data, as: UTF8.self)
        .split(separator: "\n")
        .map(String.init)
    } catch {
      return ["ps failed: \(error.localizedDescription)"]
    }
  }

  private func write(_ report: ProcessGroupSmokeReport, to path: String) throws {
    let url = URL(fileURLWithPath: path)
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    let data = try JSONEncoder.scientificWorkbench.encode(report)
    try data.write(to: url, options: .atomic)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
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

private struct ProcessGroupSmokeReport: Codable {
  let passed: Bool
  let cancellation: ProcessGroupSmokeScenario
  let timeout: ProcessGroupSmokeScenario
}

private struct ProcessGroupSmokeScenario: Codable {
  let passed: Bool
  let parentPID: pid_t?
  let childPID: pid_t?
  let grandchildPID: pid_t?
  let processGroupID: pid_t?
  let processSnapshot: [String]
  let treeExited: Bool
  let unrelatedProcessSurvived: Bool?
  let outcome: String

  static func failedBeforeLaunch(_ outcome: String) -> ProcessGroupSmokeScenario {
    ProcessGroupSmokeScenario(
      passed: false,
      parentPID: nil,
      childPID: nil,
      grandchildPID: nil,
      processGroupID: nil,
      processSnapshot: [],
      treeExited: false,
      unrelatedProcessSurvived: nil,
      outcome: outcome
    )
  }
}

private enum ProcessGroupSmokeError: LocalizedError {
  case fixtureDidNotStart

  var errorDescription: String? {
    "The process-tree fixture did not create parent, child, and grandchild PID files."
  }
}
