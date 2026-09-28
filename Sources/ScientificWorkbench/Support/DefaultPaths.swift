import Foundation

enum DefaultPaths {
  static var motherSkillRoot: String {
    FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".codex/skills/scientific-data-analysis")
      .path
  }

  static var outputRoot: String {
    FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Documents/Scientific Workbench Runs")
      .path
  }

  static func sanitizedPersistedOutputRoot(_ path: String) -> String {
    let transientGateMarkers = [
      "/scientificworkbench-bundle-verify.",
      "/scientific-workbench-secrets.",
      "/scientificworkbench-smoke.",
      "/scientificworkbench-ui-smoke.",
      "/scientificworkbench-finder-dock.",
      "/scientificworkbench-real-run."
    ]
    guard transientGateMarkers.contains(where: { path.contains($0) }) else {
      return path
    }
    return outputRoot
  }

  static var legacyWorkspaceRoot: String {
    FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Documents/ScientificWorkbenchRuns/LegacyWorkspaces")
      .path
  }

  static var systemPython: String {
    "/usr/bin/python3"
  }
}
