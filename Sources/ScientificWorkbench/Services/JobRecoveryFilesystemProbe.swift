import Foundation

struct JobRecoveryFilesystemProbe: Sendable {
  private let maximumCheckedInputs = 20

  func inspect(issue: JobRecoveryIssue, job: JobRecord, outputRootPath: String) -> String {
    let fileManager = FileManager.default
    let checkedInputs = Array(job.requestInputPaths.prefix(maximumCheckedInputs))
    let readableInputs = checkedInputs.filter { fileManager.isReadableFile(atPath: $0) }.count
    let inputCount = job.requestInputPaths.count
    let inputSummary = inputCount == 0
      ? "No input paths were recorded for this job."
      : "\(readableInputs)/\(checkedInputs.count) recorded input paths are currently readable"
        + (inputCount > checkedInputs.count ? " (first \(checkedInputs.count) of \(inputCount) checked)." : ".")

    switch issue {
    case .missingInput:
      return "Current input check: \(inputSummary) Attach the required input to a new run; this does not validate its scientific content."
    case .permissionDenied:
      return "Current file-access check: \(inputSummary) \(outputRootAccess(outputRootPath, fileManager: fileManager)) "
        + "macOS privacy prompts and subprocess access can still differ."
    case .diskSpace:
      return "Current disk check: \(outputRootCapacity(outputRootPath, fileManager: fileManager)) "
        + "The required space for this job was not recorded, so this cannot establish that a new run will fit."
    case .outputConflict:
      let risk = FilesystemSafetyPolicy().assessOutputRoot(
        outputRootPath,
        inputPaths: job.requestInputPaths
      )
      let rootStatus: String
      switch risk {
      case .safe:
        rootStatus = "The selected output root passes current overlap checks."
      case .requiresConfirmation:
        rootStatus = "The selected output root needs confirmation in Settings."
      case .blocked:
        rootStatus = "The selected output root is blocked by the safety policy."
      }
      return "Current output check: \(rootStatus) The exact occupied target was not retained in this job, "
        + "so it cannot be rechecked here. Choose a new destination and inspect Dry Run before starting."
    default:
      return "No read-only file check is available for this error. Use its recovery action."
    }
  }

  private func outputRootAccess(_ path: String, fileManager: FileManager) -> String {
    var isDirectory = ObjCBool(false)
    guard fileManager.fileExists(atPath: path, isDirectory: &isDirectory), isDirectory.boolValue else {
      return "The selected output root is not an existing directory now."
    }
    return fileManager.isWritableFile(atPath: path)
      ? "The selected output root currently appears writable."
      : "The selected output root does not currently appear writable."
  }

  private func outputRootCapacity(_ path: String, fileManager: FileManager) -> String {
    var isDirectory = ObjCBool(false)
    guard fileManager.fileExists(atPath: path, isDirectory: &isDirectory), isDirectory.boolValue else {
      return "The selected output root is not an existing directory; available space was not measured."
    }
    guard let bytes = try? URL(fileURLWithPath: path, isDirectory: true)
      .resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
      .volumeAvailableCapacityForImportantUsage else {
      return "Available space on the selected output volume was not reported."
    }
    return String(format: "The selected output volume currently reports %.1f GiB available.", Double(bytes) / 1_073_741_824)
  }
}
