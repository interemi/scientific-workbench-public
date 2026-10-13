import Foundation

struct WorkflowDraftArchiveService {
  func write(checkpoint: WorkflowDraftCheckpoint, redact: (String) -> String) throws -> URL {
    let root = FilesystemPath.canonicalURL(checkpoint.outputRootPath)
    let directory = root.appendingPathComponent("Workflow Drafts", isDirectory: true)
    guard FilesystemPath.canonicalURL(directory.path).path == directory.path else {
      throw PersistenceStoreError.unsafeFileType(directory.path)
    }
    let url = directory.appendingPathComponent("\(checkpoint.id.uuidString.lowercased())_workflow_draft.json")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let data = try JSONEncoder.scientificWorkbench.encode(checkpoint.redacted(using: redact))
    try data.write(to: url, options: [.withoutOverwriting])
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    return url
  }
}
