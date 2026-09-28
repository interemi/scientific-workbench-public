import Foundation

enum LegacyReportProjectStagingError: LocalizedError, Equatable {
  case missingProjectPath
  case projectPathMustBeAbsolute(String)
  case projectNotAttached(String)
  case projectIsNotDirectory(String)
  case symbolicLinkNotAllowed(String)
  case destinationAlreadyExists(String)
  case copyFailed(String)

  var errorDescription: String? {
    switch self {
    case .missingProjectPath:
      return "The legacy report populate step needs the scaffold project as its first argument."
    case .projectPathMustBeAbsolute(let path):
      return "The legacy report scaffold path must be absolute: \(path)"
    case .projectNotAttached(let path):
      return "The legacy report scaffold is not inside an attached input or a recorded previous run: \(path)"
    case .projectIsNotDirectory(let path):
      return "The legacy report scaffold is not a readable directory: \(path)"
    case .symbolicLinkNotAllowed(let path):
      return "The legacy report scaffold contains a symbolic link and cannot be staged safely: \(path)"
    case .destinationAlreadyExists(let path):
      return "The isolated legacy report destination already exists and will not be overwritten: \(path)"
    case .copyFailed(let message):
      return "Could not stage an isolated copy of the legacy report project: \(message)"
    }
  }
}

struct LegacyReportProjectStagingService {
  static let populateCapabilityID = "legacy_spectroscopy_report_builder.populate"

  private struct StagingPlan {
    let source: URL
    let destination: URL
    let rawArguments: String
  }

  func previewPopulateArgumentsIfNeeded(
    capabilityID: String,
    rawArguments: String,
    inputPaths: [String],
    runDirectory: String
  ) throws -> String {
    try stagingPlan(
      capabilityID: capabilityID,
      rawArguments: rawArguments,
      inputPaths: inputPaths,
      runDirectory: runDirectory
    )?.rawArguments ?? rawArguments
  }

  private func stagingPlan(
    capabilityID: String,
    rawArguments: String,
    inputPaths: [String],
    runDirectory: String
  ) throws -> StagingPlan? {
    guard capabilityID == Self.populateCapabilityID else { return nil }

    var arguments = try ShellWords.split(rawArguments)
    guard let sourceArgument = arguments.first else {
      throw LegacyReportProjectStagingError.missingProjectPath
    }
    guard let sourcePath = expandedAbsolutePath(sourceArgument) else {
      throw LegacyReportProjectStagingError.projectPathMustBeAbsolute(sourceArgument)
    }

    let sourceURL = URL(fileURLWithPath: sourcePath, isDirectory: true).standardizedFileURL
    let canonicalSource = sourceURL.resolvingSymlinksInPath()
    let canonicalRun = URL(fileURLWithPath: runDirectory, isDirectory: true)
      .standardizedFileURL
      .resolvingSymlinksInPath()

    if contains(canonicalRun, canonicalSource) {
      return nil
    }

    let attachedInputs = inputPaths.map {
      URL(fileURLWithPath: NSString(string: $0).expandingTildeInPath)
        .standardizedFileURL
        .resolvingSymlinksInPath()
    }
    guard attachedInputs.contains(where: { contains($0, canonicalSource) }) else {
      throw LegacyReportProjectStagingError.projectNotAttached(canonicalSource.path)
    }

    let destination = canonicalRun
      .appendingPathComponent("artifacts", isDirectory: true)
      .appendingPathComponent("legacy_report", isDirectory: true)
      .standardizedFileURL
      .resolvingSymlinksInPath()
    guard contains(canonicalRun, destination) else {
      throw LegacyReportProjectStagingError.copyFailed("the destination escaped the current run")
    }
    arguments[0] = destination.path
    return StagingPlan(
      source: sourceURL,
      destination: destination,
      rawArguments: arguments.map(ShellWords.quote).joined(separator: " ")
    )
  }

  func stagePopulateProjectIfNeeded(
    capabilityID: String,
    rawArguments: String,
    inputPaths: [String],
    runDirectory: String,
    fileManager: FileManager = .default
  ) throws -> String {
    guard let plan = try stagingPlan(
      capabilityID: capabilityID,
      rawArguments: rawArguments,
      inputPaths: inputPaths,
      runDirectory: runDirectory
    ) else { return rawArguments }
    let sourceURL = plan.source
    let canonicalSource = sourceURL.resolvingSymlinksInPath()
    let destination = plan.destination
    let sourceValues: URLResourceValues
    do {
      sourceValues = try sourceURL.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
    } catch {
      throw LegacyReportProjectStagingError.projectIsNotDirectory(canonicalSource.path)
    }
    guard sourceValues.isDirectory == true else {
      throw LegacyReportProjectStagingError.projectIsNotDirectory(canonicalSource.path)
    }
    if sourceValues.isSymbolicLink == true {
      throw LegacyReportProjectStagingError.symbolicLinkNotAllowed(sourceURL.path)
    }
    try rejectSymbolicLinks(in: sourceURL, fileManager: fileManager)

    guard !fileManager.fileExists(atPath: destination.path) else {
      throw LegacyReportProjectStagingError.destinationAlreadyExists(destination.path)
    }

    do {
      try fileManager.createDirectory(
        at: destination.deletingLastPathComponent(),
        withIntermediateDirectories: true
      )
      try fileManager.copyItem(at: sourceURL, to: destination)
    } catch {
      if fileManager.fileExists(atPath: destination.path) {
        try? fileManager.removeItem(at: destination)
      }
      throw LegacyReportProjectStagingError.copyFailed(error.localizedDescription)
    }

    return plan.rawArguments
  }

  private func rejectSymbolicLinks(in root: URL, fileManager: FileManager) throws {
    var enumerationError: Error?
    guard let enumerator = fileManager.enumerator(
      at: root,
      includingPropertiesForKeys: [.isSymbolicLinkKey],
      options: [],
      errorHandler: { _, error in
        enumerationError = error
        return false
      }
    ) else {
      throw LegacyReportProjectStagingError.projectIsNotDirectory(root.path)
    }

    while let item = enumerator.nextObject() as? URL {
      do {
        if try item.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink == true {
          throw LegacyReportProjectStagingError.symbolicLinkNotAllowed(item.path)
        }
      } catch let error as LegacyReportProjectStagingError {
        throw error
      } catch {
        throw LegacyReportProjectStagingError.copyFailed(error.localizedDescription)
      }
    }
    if let enumerationError {
      throw LegacyReportProjectStagingError.copyFailed(enumerationError.localizedDescription)
    }
  }

  private func expandedAbsolutePath(_ value: String) -> String? {
    if value.hasPrefix("/") {
      return value
    }
    if value == "~" || value.hasPrefix("~/") {
      return NSString(string: value).expandingTildeInPath
    }
    return nil
  }

  private func contains(_ parent: URL, _ child: URL) -> Bool {
    if parent.path == child.path { return true }
    let prefix = parent.path == "/" ? "/" : parent.path + "/"
    return child.path.hasPrefix(prefix)
  }
}
