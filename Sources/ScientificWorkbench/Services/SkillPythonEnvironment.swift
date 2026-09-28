import Foundation

enum SkillPythonEnvironment {
  static func overrides(forSkillRoot skillRoot: String) -> [String: String] {
    let rootURL = URL(fileURLWithPath: skillRoot, isDirectory: true)
    let candidates = [
      rootURL.appendingPathComponent("scripts", isDirectory: true),
      rootURL.appendingPathComponent("fixtures", isDirectory: true)
    ]
    let pythonPath = candidates
      .map(\.path)
      .filter { FileManager.default.fileExists(atPath: $0) }
      .joined(separator: ":")
    return pythonPath.isEmpty ? [:] : ["PYTHONPATH": pythonPath]
  }
}
