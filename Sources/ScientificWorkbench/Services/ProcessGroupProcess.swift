import Darwin
import Foundation

final class ProcessGroupProcess {
  let processIdentifier: pid_t

  private(set) var terminationStatus: Int32?

  init(
    executable: String,
    arguments: [String],
    workingDirectory: String?,
    environment: [String: String],
    standardInput: FileHandle?,
    standardOutput: FileHandle,
    standardError: FileHandle
  ) throws {
    var attributes: posix_spawnattr_t?
    var fileActions: posix_spawn_file_actions_t?

    try Self.check(posix_spawnattr_init(&attributes), operation: "initialize spawn attributes")
    defer { posix_spawnattr_destroy(&attributes) }

    try Self.check(posix_spawn_file_actions_init(&fileActions), operation: "initialize spawn file actions")
    defer { posix_spawn_file_actions_destroy(&fileActions) }

    var signalMask = sigset_t()
    sigemptyset(&signalMask)
    try Self.check(
      posix_spawnattr_setsigmask(&attributes, &signalMask),
      operation: "clear the inherited signal mask"
    )

    var defaultSignals = sigset_t()
    sigemptyset(&defaultSignals)
    for signal in [SIGTERM, SIGINT, SIGHUP, SIGQUIT] {
      sigaddset(&defaultSignals, signal)
    }
    try Self.check(
      posix_spawnattr_setsigdefault(&attributes, &defaultSignals),
      operation: "restore default process-control signals"
    )

    let flags = Int16(
      POSIX_SPAWN_SETPGROUP
        | POSIX_SPAWN_SETSIGMASK
        | POSIX_SPAWN_SETSIGDEF
        | POSIX_SPAWN_CLOEXEC_DEFAULT
    )
    try Self.check(posix_spawnattr_setflags(&attributes, flags), operation: "enable process-group creation")
    try Self.check(posix_spawnattr_setpgroup(&attributes, 0), operation: "create a new process group")

    try Self.addOutputRedirection(
      fileDescriptor: standardOutput.fileDescriptor,
      destination: STDOUT_FILENO,
      actions: &fileActions
    )
    try Self.addOutputRedirection(
      fileDescriptor: standardError.fileDescriptor,
      destination: STDERR_FILENO,
      actions: &fileActions
    )
    if let standardInput {
      try Self.addInputRedirection(
        fileDescriptor: standardInput.fileDescriptor,
        actions: &fileActions
      )
    }

    if let workingDirectory {
      // The macOS 14/15 SDKs expose only the non-portable chdir spawn action.
      let result = workingDirectory.withCString { path in
        posix_spawn_file_actions_addchdir_np(&fileActions, path)
      }
      try Self.check(result, operation: "set the working directory")
    }

    let argumentStorage = try CStringArray([executable] + arguments)
    let environmentStorage = try CStringArray(
      environment.keys.sorted().compactMap { key in
        environment[key].map { "\(key)=\($0)" }
      }
    )

    var pid: pid_t = 0
    let result = executable.withCString { executablePointer in
      argumentStorage.withUnsafeMutableBufferPointer { argumentPointers in
        environmentStorage.withUnsafeMutableBufferPointer { environmentPointers in
          posix_spawn(
            &pid,
            executablePointer,
            &fileActions,
            &attributes,
            argumentPointers.baseAddress,
            environmentPointers.baseAddress
          )
        }
      }
    }
    try Self.check(result, operation: "launch \(executable)")
    guard pid > 1 else {
      throw ProcessGroupProcessError.invalidProcessIdentifier(pid)
    }
    processIdentifier = pid
  }

  var processGroupIdentifier: pid_t {
    processIdentifier
  }

  func poll() throws -> Bool {
    guard terminationStatus == nil else { return false }

    var status: Int32 = 0
    while true {
      let result = waitpid(processIdentifier, &status, WNOHANG)
      if result == 0 {
        return true
      }
      if result == processIdentifier {
        terminationStatus = Self.exitCode(fromWaitStatus: status)
        return false
      }
      if result == -1, errno == EINTR {
        continue
      }
      if result == -1, errno == ECHILD {
        terminationStatus = terminationStatus ?? 1
        return false
      }
      throw ProcessGroupProcessError.posix(operation: "poll process", code: errno)
    }
  }

  func groupIsAlive() -> Bool {
    guard processGroupIdentifier > 1 else { return false }
    if Darwin.kill(-processGroupIdentifier, 0) == 0 {
      return true
    }
    return errno == EPERM
  }

  func signalGroup(_ signal: Int32) throws {
    guard processGroupIdentifier > 1 else {
      throw ProcessGroupProcessError.invalidProcessIdentifier(processGroupIdentifier)
    }
    if Darwin.kill(-processGroupIdentifier, signal) != 0, errno != ESRCH {
      throw ProcessGroupProcessError.posix(
        operation: "signal process group \(processGroupIdentifier)",
        code: errno
      )
    }
  }

  private static func addOutputRedirection(
    fileDescriptor: Int32,
    destination: Int32,
    actions: inout posix_spawn_file_actions_t?
  ) throws {
    try check(
      posix_spawn_file_actions_adddup2(&actions, fileDescriptor, destination),
      operation: "redirect file descriptor \(destination)"
    )
    if fileDescriptor != destination {
      try check(
        posix_spawn_file_actions_addclose(&actions, fileDescriptor),
        operation: "close inherited file descriptor \(fileDescriptor)"
      )
    }
  }

  private static func addInputRedirection(
    fileDescriptor: Int32,
    actions: inout posix_spawn_file_actions_t?
  ) throws {
    try check(
      posix_spawn_file_actions_adddup2(&actions, fileDescriptor, STDIN_FILENO),
      operation: "redirect file descriptor \(STDIN_FILENO)"
    )
    if fileDescriptor != STDIN_FILENO {
      try check(
        posix_spawn_file_actions_addclose(&actions, fileDescriptor),
        operation: "close inherited file descriptor \(fileDescriptor)"
      )
    }
  }

  private static func exitCode(fromWaitStatus status: Int32) -> Int32 {
    let terminationSignal = status & 0x7f
    if terminationSignal == 0 {
      return (status >> 8) & 0xff
    }
    return terminationSignal
  }

  private static func check(_ result: Int32, operation: String) throws {
    guard result == 0 else {
      throw ProcessGroupProcessError.posix(operation: operation, code: result)
    }
  }
}

private final class CStringArray {
  private var pointers: [UnsafeMutablePointer<CChar>?]

  init(_ strings: [String]) throws {
    pointers = []
    pointers.reserveCapacity(strings.count + 1)
    for string in strings {
      guard let pointer = strdup(string) else {
        pointers.forEach { free($0) }
        throw ProcessGroupProcessError.outOfMemory
      }
      pointers.append(pointer)
    }
    pointers.append(nil)
  }

  deinit {
    pointers.forEach { free($0) }
  }

  func withUnsafeMutableBufferPointer<Result>(
    _ body: (UnsafeMutableBufferPointer<UnsafeMutablePointer<CChar>?>) throws -> Result
  ) rethrows -> Result {
    try pointers.withUnsafeMutableBufferPointer { buffer in
      try body(buffer)
    }
  }
}

enum ProcessGroupProcessError: LocalizedError {
  case invalidProcessIdentifier(pid_t)
  case outOfMemory
  case posix(operation: String, code: Int32)

  var errorDescription: String? {
    switch self {
    case .invalidProcessIdentifier(let pid):
      return "Refused to manage unsafe process-group identifier \(pid)."
    case .outOfMemory:
      return "Could not allocate process launch arguments."
    case .posix(let operation, let code):
      return "\(operation) failed: \(String(cString: strerror(code))) (errno \(code))."
    }
  }
}
