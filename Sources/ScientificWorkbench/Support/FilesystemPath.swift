import Foundation

enum FilesystemPath {
  static func canonicalURL(_ path: String) -> URL {
    let expanded = NSString(string: path).expandingTildeInPath
    let absolute = expanded.hasPrefix("/")
      ? expanded : FileManager.default.currentDirectoryPath + "/" + expanded
    var pending = absolute.split(separator: "/").map(String.init)
    var current = URL(fileURLWithPath: "/", isDirectory: true)
    var followedLinks = 0

    // Resolve links before '..', including links to missing destinations.
    // This also keeps /tmp and /private/tmp consistent for newly created runs.
    while !pending.isEmpty {
      let component = pending.removeFirst()
      if component == "." { continue }
      if component == ".." {
        current.deleteLastPathComponent()
        continue
      }
      let candidate = current.appendingPathComponent(component)
      if let target = try? FileManager.default.destinationOfSymbolicLink(atPath: candidate.path) {
        followedLinks += 1
        guard followedLinks <= 40 else {
          // Leave cyclic/unresolvable paths unresolved; filesystem access fails.
          return URL(fileURLWithPath: absolute)
        }
        if target.hasPrefix("/") {
          current = URL(fileURLWithPath: "/", isDirectory: true)
        }
        pending = target.split(separator: "/").map(String.init) + pending
      } else {
        current = candidate
      }
    }
    return current
  }
}
