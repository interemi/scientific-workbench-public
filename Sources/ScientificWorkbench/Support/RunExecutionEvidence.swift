import CryptoKit
import Darwin
import Foundation

struct RunExecutionEvidence: Codable, Sendable {
  static let filename = ".swb-replay.json"

  let schemaVersion: Int
  let jobID: UUID
  let commandSHA256: String
  let pythonInventorySHA256: String

  private struct Invocation: Encodable {
    let executable: String
    let arguments: [String]
    let workingDirectory: String
    let timeoutSeconds: TimeInterval?
    let redirectsInput: Bool
    let environment: [String: String]
    let launcherHashes: [String]
  }

  static func commandDigest(_ command: ProcessCommand, secrets: [String]) -> String? {
    guard let directory = command.workingDirectory, let launcher = command.arguments.first,
          command.arguments.dropFirst().first == "run-tool" else { return nil }
    let root = FilesystemPath.canonicalURL(directory)
    let wrapper = FilesystemPath.canonicalURL(launcher)
    guard wrapper == root.appendingPathComponent("scripts/datanalysis_env.py") else { return nil }
    var environment = ProcessRunner.sanitizedEnvironment(
      parent: ProcessInfo.processInfo.environment, policy: command.environmentPolicy, overrides: command.environmentOverrides
    )
    environment.removeValue(forKey: RunRuntimeEvidence.environmentKey)
    let strings = [command.executable, directory] + command.arguments + Array(environment.values)
    guard strings.allSatisfy({ SecretsRedactor.redact($0, secrets: secrets) == $0 }) else { return nil }
    let launcherFiles = [
      wrapper,
      root.appendingPathComponent("scripts/_internal/fixture_script_dispatch.py"),
      root.appendingPathComponent("scripts/_internal/deferred_internal.py"),
      root.appendingPathComponent("fixtures/datanalysis_env.py"),
      root.appendingPathComponent("fixtures/_internal/fixture_script_dispatch.py"),
    ]
    let launcherHashes = launcherFiles.compactMap {
      RunFileFingerprint.read($0, maximumBytes: 2_000_000).sha256
    }
    guard launcherHashes.count == launcherFiles.count else { return nil }

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    let invocation = Invocation(
      executable: command.executable, arguments: command.arguments, workingDirectory: directory,
      timeoutSeconds: command.timeoutSeconds, redirectsInput: command.redirectStandardInputToNull,
      environment: environment, launcherHashes: launcherHashes
    )
    guard let data = try? encoder.encode(invocation) else { return nil }
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }

  static func isDigest(_ value: String) -> Bool {
    value.utf8.count == 64 && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
  }

  static func retain(jobID: UUID, root: URL, command: String, pythonInventory: String) throws {
    let receipt = Self(schemaVersion: 1, jobID: jobID, commandSHA256: command, pythonInventorySHA256: pythonInventory)
    let data = try JSONEncoder().encode(receipt)
    let url = root.appendingPathComponent(filename)
    let descriptor = open(url.path, O_WRONLY | O_CLOEXEC | O_NOFOLLOW | O_CREAT | O_EXCL, 0o600)
    guard descriptor >= 0 else { throw POSIXError(.init(rawValue: errno) ?? .EIO) }
    let file = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
    defer { try? file.close() }
    try file.write(contentsOf: data)
  }

  static func read(for job: JobRecord) -> Self? {
    let url = FilesystemPath.canonicalURL(job.runDirectory).appendingPathComponent(filename)
    let (fingerprint, bytes, status) = RunFileFingerprint.readSample(url, maximumBytes: 4_096, range: 0..<4_096)
    guard fingerprint.state == .recorded, let status, status.st_nlink == 1, status.st_uid == getuid(),
          (status.st_mode & 0o777) == 0o600,
          let receipt = try? JSONDecoder().decode(Self.self, from: bytes),
          receipt.schemaVersion == 1, receipt.jobID == job.id,
          isDigest(receipt.commandSHA256), isDigest(receipt.pythonInventorySHA256) else { return nil }
    return receipt
  }
}
