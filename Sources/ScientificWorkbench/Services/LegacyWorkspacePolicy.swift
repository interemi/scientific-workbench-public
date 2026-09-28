import Foundation

struct LegacyWorkspacePolicy {
  static let shared = LegacyWorkspacePolicy()
  static let maximumCompatibleRootBytes = 72

  let safeWorkspaceRoot: String

  init(safeWorkspaceRoot: String = DefaultPaths.legacyWorkspaceRoot) {
    self.safeWorkspaceRoot = safeWorkspaceRoot
  }

  func runRoot(for capabilityID: String, preferredOutputRoot: String) -> String {
    guard requiresSafeWorkspace(capabilityID),
          !isLegacyCompatible(path: preferredOutputRoot) else {
      return preferredOutputRoot
    }
    return safeWorkspaceRoot
  }

  func requiresSafeWorkspace(_ capabilityID: String) -> Bool {
    Self.pathSensitiveCapabilityIDs.contains(capabilityID)
  }

  func isLegacyCompatible(path: String) -> Bool {
    !path.isEmpty &&
      path.utf8.count <= Self.maximumCompatibleRootBytes &&
      path.unicodeScalars.allSatisfy { scalar in
      scalar.isASCII && !CharacterSet.whitespacesAndNewlines.contains(scalar)
    }
  }

  func notice(for outputRootPath: String) -> String? {
    guard !isLegacyCompatible(path: outputRootPath) else {
      return "Legacy IRAF/fxcor workspace: selected output root is path-compatible."
    }
    return "Legacy IRAF/fxcor runs use \(URL(fileURLWithPath: safeWorkspaceRoot).lastPathComponent) automatically because the selected output root contains spaces, non-ASCII characters, or is too long for reliable legacy execution."
  }

  private static let pathSensitiveCapabilityIDs: Set<String> = [
    "legacy_spectroscopy_envcheck",
    "fxcor_iraf_workbench.prepare-session",
    "fxcor_iraf_workbench.run-auto",
    "legacy_rv_coursework_workbench.analyze",
    "legacy_external_reference_check",
    "legacy_spectroscopy_report_builder.scaffold",
    "legacy_spectroscopy_report_builder.populate",
    "latex_workbench.review",
    "latex_workbench.compile"
  ]
}
