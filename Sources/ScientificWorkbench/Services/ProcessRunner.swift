import Darwin
import Foundation

struct ProcessEnvironmentPolicy: Equatable, Sendable {
  var inheritParentEnvironment: Bool
  var additionalAllowedKeys: Set<String>
  var allowsCompatibilityEnvironmentOverrides: Bool

  static let strict = ProcessEnvironmentPolicy(
    inheritParentEnvironment: false,
    additionalAllowedKeys: [],
    allowsCompatibilityEnvironmentOverrides: false
  )

  static let restricted = ProcessEnvironmentPolicy(
    inheritParentEnvironment: false,
    additionalAllowedKeys: [],
    allowsCompatibilityEnvironmentOverrides: true
  )

  static func restricted(allowing keys: Set<String>) -> ProcessEnvironmentPolicy {
    ProcessEnvironmentPolicy(
      inheritParentEnvironment: false,
      additionalAllowedKeys: keys,
      allowsCompatibilityEnvironmentOverrides: true
    )
  }
}

enum ProcessEnvironmentKeyPolicy {
  static nonisolated func isValidName(_ key: String) -> Bool {
    key.range(
      of: #"^[A-Za-z_][A-Za-z0-9_]*$"#,
      options: .regularExpression
    ) != nil
  }

  static nonisolated func isSensitive(_ key: String, value: String? = nil) -> Bool {
    let upper = key.uppercased()
    let exact: Set<String> = [
      "GEMINI_API_KEY",
      "GOOGLE_API_KEY",
      "OPENAI_API_KEY",
      "XAI_API_KEY"
    ]
    guard !exact.contains(upper) else { return true }

    let sensitiveTokens: Set<String> = [
      "APIKEY",
      "AUTH",
      "COOKIE",
      "COOKIES",
      "CREDENTIAL",
      "CREDENTIALS",
      "DSN",
      "KEY",
      "PASS",
      "PASSWORD",
      "PAT",
      "SECRET",
      "SESSION",
      "SESSIONID",
      "TOKEN"
    ]
    if upper.split(separator: "_").contains(where: { sensitiveTokens.contains(String($0)) }) {
      return true
    }
    if upper.contains("COOKIE") || upper.contains("SESSION") {
      return true
    }
    return value.map(containsCredentialBearingURL) ?? false
  }

  static nonisolated func isUnsafeForInheritance(_ key: String) -> Bool {
    let upper = key.uppercased()
    if upper.hasPrefix("DYLD_")
      || upper.hasPrefix("LD_")
      || upper.hasPrefix("BASH_FUNC_")
      || upper.hasPrefix("GIT_CONFIG_") {
      return true
    }

    let exact: Set<String> = [
      "BASH_ENV",
      "CDPATH",
      "ENV",
      "GCONV_PATH",
      "GIT_ASKPASS",
      "GIT_SSH_COMMAND",
      "HOSTALIASES",
      "IFS",
      "JAVA_TOOL_OPTIONS",
      "JDK_JAVA_OPTIONS",
      "LOCPATH",
      "NODE_OPTIONS",
      "NODE_PATH",
      "NLSPATH",
      "PERL5DB",
      "PERL5LIB",
      "PERL5OPT",
      "PROMPT_COMMAND",
      "PS4",
      "PYTHONHOME",
      "PYTHONINSPECT",
      "PYTHONPATH",
      "PYTHONSTARTUP",
      "RUBYLIB",
      "RUBYOPT",
      "SHELLOPTS",
      "SSH_ASKPASS",
      "ZDOTDIR",
      "_JAVA_OPTIONS"
    ]
    return exact.contains(upper)
  }

  private static nonisolated func containsCredentialBearingURL(_ value: String) -> Bool {
    value.split(whereSeparator: { character in
      character.isWhitespace || character == "," || character == ";"
    }).contains { candidate in
      guard let components = URLComponents(string: String(candidate)),
            components.scheme != nil,
            components.host != nil else {
        return false
      }
      return components.user?.isEmpty == false || components.password != nil
    }
  }
}

actor ProcessRunner {
  static let defaultTimeoutSeconds: TimeInterval = 30 * 60
  static let defaultMaximumCapturedOutputBytes = 4 * 1024 * 1024
  static let defaultMaximumTemporaryOutputBytesPerStream = 256 * 1024 * 1024

  private var activeProcesses: [UUID: ProcessGroupProcess] = [:]
  private let defaultTimeoutSeconds: TimeInterval
  private let maximumCapturedOutputBytes: Int
  private let maximumTemporaryOutputBytesPerStream: Int
  private let parentEnvironment: @Sendable () -> [String: String]

  init(
    defaultTimeoutSeconds: TimeInterval = ProcessRunner.defaultTimeoutSeconds,
    maximumCapturedOutputBytes: Int = ProcessRunner.defaultMaximumCapturedOutputBytes,
    maximumTemporaryOutputBytesPerStream: Int = ProcessRunner.defaultMaximumTemporaryOutputBytesPerStream,
    parentEnvironment: @escaping @Sendable () -> [String: String] = {
      ProcessInfo.processInfo.environment
    }
  ) {
    self.defaultTimeoutSeconds = defaultTimeoutSeconds
    self.maximumCapturedOutputBytes = max(256, maximumCapturedOutputBytes)
    self.maximumTemporaryOutputBytesPerStream = max(1, maximumTemporaryOutputBytesPerStream)
    self.parentEnvironment = parentEnvironment
  }

  func cancelAll() async {
    for process in activeProcesses.values {
      await stop(process)
    }
  }

  func run(
    _ command: ProcessCommand,
    retainingLogs archive: RunLogArchive? = nil,
    onInterrupted: (@Sendable (InterruptedProcessOutput) async -> Void)? = nil,
    cancellationRequested: (@Sendable () async -> Bool)? = nil
  ) async throws -> ProcessResult {
    if await cancellationRequested?() == true {
      throw ProcessRunnerError.cancelled
    }
    let startedAt = Date()
    let tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(
      at: tempRoot, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]
    )
    defer { try? FileManager.default.removeItem(at: tempRoot) }

    let stdoutURL = tempRoot.appendingPathComponent("stdout.txt")
    let stderrURL = tempRoot.appendingPathComponent("stderr.txt")
    FileManager.default.createFile(atPath: stdoutURL.path, contents: nil)
    FileManager.default.createFile(atPath: stderrURL.path, contents: nil)

    let stdoutHandle = try FileHandle(forWritingTo: stdoutURL)
    let stderrHandle = try FileHandle(forWritingTo: stderrURL)
    let stdinHandle = command.redirectStandardInputToNull
      ? try FileHandle(forReadingFrom: URL(fileURLWithPath: "/dev/null"))
      : nil
    defer {
      try? stdinHandle?.close()
      try? stdoutHandle.close()
      try? stderrHandle.close()
    }

    let processID = UUID()
    let process = try ProcessGroupProcess(
      executable: command.executable,
      arguments: command.arguments,
      workingDirectory: command.workingDirectory,
      environment: Self.sanitizedEnvironment(
        parent: parentEnvironment(),
        policy: command.environmentPolicy,
        overrides: command.environmentOverrides
      ),
      standardInput: stdinHandle,
      standardOutput: stdoutHandle,
      standardError: stderrHandle
    )
    activeProcesses[processID] = process
    defer { activeProcesses[processID] = nil }
    let timeoutSeconds = command.timeoutSeconds ?? defaultTimeoutSeconds
    let deadline = timeoutSeconds > 0 ? startedAt.addingTimeInterval(timeoutSeconds) : nil

    do {
      while true {
        let parentIsRunning = try process.poll()
        let groupIsAlive = process.groupIsAlive()
        if let stream = Self.outputStreamExceedingLimit(
          stdoutURL: stdoutURL,
          stderrURL: stderrURL,
          limitBytes: maximumTemporaryOutputBytesPerStream
        ) {
          throw ProcessRunnerError.outputLimitExceeded(
            stream: stream,
            limitBytes: maximumTemporaryOutputBytesPerStream
          )
        }
        guard parentIsRunning || groupIsAlive else { break }

        if Task.isCancelled {
          throw ProcessRunnerError.cancelled
        }
        if let deadline, Date() >= deadline {
          throw ProcessRunnerError.timedOut(timeoutSeconds)
        }
        do {
          try await Task.sleep(nanoseconds: 100_000_000)
        } catch is CancellationError {
          throw ProcessRunnerError.cancelled
        }
      }
    } catch {
      await stop(process)
      activeProcesses[processID] = nil
      if archive != nil || onInterrupted != nil {
        let capture = await captureOutput(stdoutURL: stdoutURL, stderrURL: stderrURL, archive: archive)
        await onInterrupted?(InterruptedProcessOutput(
          stdout: capture.stdout.text, stderr: capture.stderr.text, retainedLogs: capture.retainedLogs
        ))
      }
      throw error
    }

    let finishedAt = Date()
    activeProcesses[processID] = nil
    let capture = await captureOutput(stdoutURL: stdoutURL, stderrURL: stderrURL, archive: archive)
    return ProcessResult(
      exitCode: process.terminationStatus ?? 1,
      stdout: capture.stdout.text,
      stderr: capture.stderr.text,
      startedAt: startedAt,
      finishedAt: finishedAt,
      stdoutTotalBytes: capture.stdout.totalBytes,
      stderrTotalBytes: capture.stderr.totalBytes,
      stdoutWasTruncated: capture.stdout.wasTruncated,
      stderrWasTruncated: capture.stderr.wasTruncated,
      retainedLogs: capture.retainedLogs
    )
  }

  private func captureOutput(
    stdoutURL: URL, stderrURL: URL, archive: RunLogArchive?
  ) async -> (stdout: BoundedProcessOutput, stderr: BoundedProcessOutput, retainedLogs: Set<RunLogStream>) {
    let excerptLimit = maximumCapturedOutputBytes
    guard let archive else {
      return (
        BoundedProcessOutput.read(at: stdoutURL, maximumBytes: excerptLimit) ?? .empty,
        BoundedProcessOutput.read(at: stderrURL, maximumBytes: excerptLimit) ?? .empty,
        []
      )
    }
    let secrets = await archive.currentSecrets()
    let inputLimit = maximumTemporaryOutputBytesPerStream
    // A cancelled process still needs to finish retaining its partial output.
    return await Task.detached(priority: .utility) {
      let stdout = archive.retain(
        from: stdoutURL, stream: .stdout, maximumInputBytes: inputLimit,
        maximumExcerptBytes: excerptLimit, additionalSecrets: secrets
      )
      let stderr = archive.retain(
        from: stderrURL, stream: .stderr, maximumInputBytes: inputLimit,
        maximumExcerptBytes: excerptLimit, additionalSecrets: secrets
      )
      var retained: Set<RunLogStream> = []
      if stdout != nil { retained.insert(.stdout) }
      if stderr != nil { retained.insert(.stderr) }
      return (
        stdout ?? Self.retentionFailure(at: stdoutURL),
        stderr ?? Self.retentionFailure(at: stderrURL),
        retained
      )
    }.value
  }

  private static nonisolated func retentionFailure(at url: URL) -> BoundedProcessOutput {
    BoundedProcessOutput(
      text: "[Scientific Workbench could not retain this log.]",
      totalBytes: fileSize(at: url),
      wasTruncated: true
    )
  }

  private func stop(_ process: ProcessGroupProcess) async {
    let escalation: [(signal: Int32, waitNanoseconds: UInt64)] = [
      (SIGTERM, 500_000_000),
      (SIGINT, 500_000_000),
      (SIGKILL, 1_500_000_000),
    ]

    for stage in escalation where process.groupIsAlive() {
      try? process.signalGroup(stage.signal)
      if await waitForGroupExit(process, timeoutNanoseconds: stage.waitNanoseconds) {
        return
      }
    }
    _ = try? process.poll()
  }

  private func waitForGroupExit(
    _ process: ProcessGroupProcess,
    timeoutNanoseconds: UInt64
  ) async -> Bool {
    let deadline = DispatchTime.now().uptimeNanoseconds + timeoutNanoseconds
    repeat {
      _ = try? process.poll()
      if !process.groupIsAlive() {
        return true
      }
      await Self.uncancellableSleep(nanoseconds: 50_000_000)
    } while DispatchTime.now().uptimeNanoseconds < deadline
    return !process.groupIsAlive()
  }

  private static func uncancellableSleep(nanoseconds: UInt64) async {
    await Task.detached {
      try? await Task.sleep(nanoseconds: nanoseconds)
    }.value
  }

  private static nonisolated func outputStreamExceedingLimit(
    stdoutURL: URL,
    stderrURL: URL,
    limitBytes: Int
  ) -> String? {
    if fileSize(at: stdoutURL) > limitBytes {
      return "stdout"
    }
    if fileSize(at: stderrURL) > limitBytes {
      return "stderr"
    }
    return nil
  }

  private static nonisolated func fileSize(at url: URL) -> Int {
    guard let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
          let size = attributes[.size] as? NSNumber else {
      return 0
    }
    return size.intValue
  }

  static nonisolated func sanitizedEnvironment(
    parent: [String: String],
    policy: ProcessEnvironmentPolicy = .restricted,
    overrides: [String: String] = [:]
  ) -> [String: String] {
    let compatibilityInheritanceRequested =
      policy.allowsCompatibilityEnvironmentOverrides
        && parent["SCIENTIFIC_WORKBENCH_INHERIT_PROCESS_ENV"] == "1"
    let shouldInherit = policy.inheritParentEnvironment || compatibilityInheritanceRequested
    var environment: [String: String]
    if shouldInherit {
      environment = parent.filter {
        !ProcessEnvironmentKeyPolicy.isSensitive($0.key, value: $0.value)
          && !ProcessEnvironmentKeyPolicy.isUnsafeForInheritance($0.key)
      }
    } else {
      let compatibilityAllowedKeys = policy.allowsCompatibilityEnvironmentOverrides
        ? extraAllowedKeys(from: parent)
        : []
      let allowedKeys = defaultAllowedEnvironmentKeys
        .union(policy.additionalAllowedKeys)
        .union(compatibilityAllowedKeys)
      environment = parent.filter { key, value in
        (allowedKeys.contains(key) || key.hasPrefix("LC_"))
          && !ProcessEnvironmentKeyPolicy.isSensitive(key, value: value)
          && !ProcessEnvironmentKeyPolicy.isUnsafeForInheritance(key)
      }
    }

    let defaultSearchPaths = [
      "/usr/local/bin",
      "/opt/homebrew/bin",
      "/Library/TeX/texbin",
      "/Applications/XGTerm.app/Contents/Resources/bin",
      "/opt/X11/bin",
      "/usr/X11/bin",
      "/usr/bin",
      "/bin",
      "/usr/sbin",
      "/sbin",
    ]
    let currentPaths = policy.allowsCompatibilityEnvironmentOverrides || policy.inheritParentEnvironment
      ? (parent["PATH"] ?? environment["PATH"] ?? "").split(separator: ":").map(String.init)
      : []
    let mergedPaths = (defaultSearchPaths + currentPaths).reduce(into: [String]()) { paths, path in
      if !paths.contains(path) {
        paths.append(path)
      }
    }
    environment["PATH"] = mergedPaths.joined(separator: ":")
    for (key, value) in overrides
      where ProcessEnvironmentKeyPolicy.isValidName(key)
        && !ProcessEnvironmentKeyPolicy.isSensitive(key, value: value) {
      environment[key] = value
    }
    return environment
  }

  private static nonisolated var defaultAllowedEnvironmentKeys: Set<String> {
    [
      "COLORTERM",
      "CONDA_DEFAULT_ENV",
      "CONDA_EXE",
      "CONDA_PREFIX",
      "CONDA_SHLVL",
      "DISPLAY",
      "HOME",
      "LANG",
      "LOGNAME",
      "MAMBA_ROOT_PREFIX",
      "PATH",
      "PWD",
      "SHELL",
      "TEMP",
      "TERM",
      "TMP",
      "TMPDIR",
      "USER",
      "VIRTUAL_ENV",
      "XPC_FLAGS",
      "XPC_SERVICE_NAME",
      "__CFBundleIdentifier"
    ]
  }

  private static nonisolated func extraAllowedKeys(from parent: [String: String]) -> Set<String> {
    let raw = parent["SCIENTIFIC_WORKBENCH_ALLOW_PROCESS_ENV"] ?? ""
    return Set(
      raw.split(separator: ",")
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter {
          ProcessEnvironmentKeyPolicy.isValidName($0)
            && !ProcessEnvironmentKeyPolicy.isSensitive($0)
            && !ProcessEnvironmentKeyPolicy.isUnsafeForInheritance($0)
        }
    )
  }
}

struct InterruptedProcessOutput: Sendable {
  let stdout: String
  let stderr: String
  let retainedLogs: Set<RunLogStream>
}

enum ProcessRunnerError: LocalizedError, Equatable {
  case cancelled
  case timedOut(TimeInterval)
  case outputLimitExceeded(stream: String, limitBytes: Int)

  var errorDescription: String? {
    switch self {
    case .cancelled:
      return "Run cancelled by user."
    case .timedOut(let seconds):
      return "Run timed out after \(max(1, Int(seconds.rounded(.up)))) seconds."
    case .outputLimitExceeded(let stream, let limitBytes):
      return "Run stopped because \(stream) exceeded the temporary output limit of \(limitBytes) bytes."
    }
  }
}
