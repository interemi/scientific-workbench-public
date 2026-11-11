import Foundation

struct RunStorageInventory: Equatable, Sendable {
  var retainedStreamBytes: Int64 = 0
  var runLogBytes: Int64 = 0
  var runPreviewBytes: Int64 = 0
  var measuredFolders = 0
  var skippedFolders = 0
  var hasUnreadableEntries = false

  static func measure(
    outputRoot: String, jobs: [JobRecord], inputPaths: [String]
  ) throws -> Self {
    if case .blocked(let reason) = FilesystemSafetyPolicy().assessOutputRoot(outputRoot, inputPaths: inputPaths) {
      throw FilesystemSafetyError.blocked(reason)
    }
    let root = FilesystemPath.canonicalURL(outputRoot)
    let activeInputs = inputPaths.map(FilesystemPath.canonicalURL)
    var inventory = Self()
    var measuredRuns: Set<URL> = []
    var skippedRuns: Set<URL> = []
    var countedFiles: Set<URL> = []
    let keys: Set<URLResourceKey> = [.isDirectoryKey, .isSymbolicLinkKey, .isRegularFileKey, .fileSizeKey]
    let manager = FileManager.default

    func overlaps(_ first: URL, _ second: URL) -> Bool {
      first.pathComponents.starts(with: second.pathComponents)
        || second.pathComponents.starts(with: first.pathComponents)
    }

    func metadata(_ url: URL) -> URLResourceValues? {
      do {
        return try url.resourceValues(forKeys: keys)
      } catch let error as CocoaError where error.code == .fileReadNoSuchFile || error.code == .fileNoSuchFile {
        return nil
      } catch {
        inventory.hasUnreadableEntries = true
        return nil
      }
    }

    func fileBytes(_ url: URL, values: URLResourceValues) -> Int64 {
      guard values.isSymbolicLink == false, values.isRegularFile == true,
            countedFiles.insert(url).inserted else { return 0 }
      guard let size = values.fileSize else {
        inventory.hasUnreadableEntries = true
        return 0
      }
      return Int64(size)
    }

    func folderBytes(_ folder: URL) throws -> Int64 {
      guard let values = metadata(folder), values.isSymbolicLink == false,
            values.isDirectory == true else { return 0 }
      guard let entries = manager.enumerator(
        at: folder, includingPropertiesForKeys: Array(keys),
        options: [.skipsHiddenFiles, .skipsPackageDescendants],
        errorHandler: { _, _ in
          inventory.hasUnreadableEntries = true
          return true
        }
      ) else {
        inventory.hasUnreadableEntries = true
        return 0
      }
      var bytes: Int64 = 0
      for case let file as URL in entries {
        try Task.checkCancellation()
        guard let values = metadata(file) else { continue }
        bytes += fileBytes(file, values: values)
      }
      return bytes
    }

    for job in jobs {
      try Task.checkCancellation()
      guard job.runDirectory.hasPrefix("/") else { continue }
      let run = FilesystemPath.canonicalURL(job.runDirectory)
      let inputs = activeInputs + job.requestInputPaths.map(FilesystemPath.canonicalURL)
      guard run.path != root.path, run.pathComponents.starts(with: root.pathComponents),
            !inputs.contains(where: { overlaps($0, run) }) else {
        skippedRuns.insert(run)
        continue
      }
      guard !measuredRuns.contains(run) else { continue }
      guard metadata(run)?.isDirectory == true else {
        skippedRuns.insert(run)
        continue
      }
      measuredRuns.insert(run)
      for stream in [RunLogStream.stdout, .stderr] {
        let file = run.appendingPathComponent(stream.fileName)
        if let values = metadata(file) {
          inventory.retainedStreamBytes += fileBytes(file, values: values)
        }
      }
      let logs = try folderBytes(run.appendingPathComponent("logs", isDirectory: true))
      let previews = try folderBytes(run.appendingPathComponent("previews", isDirectory: true))
      inventory.runLogBytes += logs
      inventory.runPreviewBytes += previews
    }
    inventory.measuredFolders = measuredRuns.count
    inventory.skippedFolders = skippedRuns.subtracting(measuredRuns).count
    return inventory
  }
}
