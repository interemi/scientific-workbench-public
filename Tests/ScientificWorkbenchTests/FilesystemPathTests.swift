import Foundation
import Testing
@testable import ScientificWorkbench

struct FilesystemPathTests {
  @Test
  func existingRootAndMissingChildrenUseTheSameCanonicalPrefix() throws {
    let root = URL(fileURLWithPath: "/private/tmp")
      .appendingPathComponent("Scientific-Workbench-Canonical-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let canonical = FilesystemPath.canonicalURL(root.path)
    let child = root.appendingPathComponent("new-run/transcript.json")
    #expect(FilesystemPath.canonicalURL(child.path).path == canonical.appendingPathComponent("new-run/transcript.json").path)
    let alias = root.path.replacingOccurrences(of: "/private/tmp/", with: "/tmp/")
    #expect(FilesystemPath.canonicalURL(alias).path == canonical.path)
    try FilesystemSafetyPolicy().validateRunDirectory(
      root.appendingPathComponent("new-run").path,
      inputPaths: [], allowedRoots: [alias]
    )
  }

  @Test
  func missingSymlinkTargetsStillRespectProtectedLocations() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Canonical-Link-\(UUID().uuidString)")
    let home = root.appendingPathComponent("home")
    let protected = home.appendingPathComponent(".ssh")
    let output = root.appendingPathComponent("output")
    try FileManager.default.createDirectory(at: protected, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let alias = output.appendingPathComponent("link")
    let missing = protected.appendingPathComponent("not-created")
    try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: missing)

    #expect(FilesystemPath.canonicalURL(alias.path).path == FilesystemPath.canonicalURL(missing.path).path)
    let policy = FilesystemSafetyPolicy(homeDirectory: home)
    guard case .blocked = policy.assessOutputRoot(alias.path, inputPaths: []) else {
      Issue.record("A dangling symlink into a protected location must remain blocked.")
      return
    }
  }

  @Test
  func parentComponentsAreResolvedAfterSymlinks() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Canonical-Parent-\(UUID().uuidString)")
    let home = root.appendingPathComponent("home")
    let output = root.appendingPathComponent("output")
    try FileManager.default.createDirectory(at: home.appendingPathComponent("public"), withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: home.appendingPathComponent(".ssh"), withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createSymbolicLink(
      at: output.appendingPathComponent("link"),
      withDestinationURL: home.appendingPathComponent("public")
    )
    let path = output.path + "/link/../.ssh/not-created"
    #expect(FilesystemPath.canonicalURL(path).path == FilesystemPath.canonicalURL(home.path + "/.ssh/not-created").path)
    guard case .blocked = FilesystemSafetyPolicy(homeDirectory: home).assessOutputRoot(path, inputPaths: []) else {
      Issue.record("Lexical normalization must not hide a protected symlink destination.")
      return
    }
  }
}
