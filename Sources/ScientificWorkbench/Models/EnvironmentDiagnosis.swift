import Foundation

struct EnvironmentMissingGroup: Identifiable, Equatable, Sendable {
  let id: String
  let label: String
  let modules: [String]
}

struct EnvironmentDiagnosis: Equatable, Sendable {
  let status: String
  let selectedPython: String?
  let pythonVersion: String?
  let coreReady: Bool?
  let fullReady: Bool?
  let missingCoreModules: [String]
  let missingOptionalGroups: [EnvironmentMissingGroup]
  let message: String?
  let checkedAt: Date?

  static let unknown = EnvironmentDiagnosis(
    status: "unknown",
    selectedPython: nil,
    pythonVersion: nil,
    coreReady: nil,
    fullReady: nil,
    missingCoreModules: [],
    missingOptionalGroups: [],
    message: nil,
    checkedAt: nil
  )

  static func blocked(_ message: String, selectedPython: String? = nil) -> EnvironmentDiagnosis {
    EnvironmentDiagnosis(
      status: "blocked",
      selectedPython: selectedPython,
      pythonVersion: nil,
      coreReady: false,
      fullReady: nil,
      missingCoreModules: [],
      missingOptionalGroups: [],
      message: message,
      checkedAt: Date()
    )
  }

  static func unavailable(_ message: String, selectedPython: String?) -> EnvironmentDiagnosis {
    EnvironmentDiagnosis(
      status: "failed",
      selectedPython: selectedPython,
      pythonVersion: nil,
      coreReady: nil,
      fullReady: nil,
      missingCoreModules: [],
      missingOptionalGroups: [],
      message: message,
      checkedAt: Date()
    )
  }

  static func parse(_ text: String, selectedPython: String?) -> EnvironmentDiagnosis? {
    guard
      let payload = JSONOutputExtractor.lastObject(
        in: text,
        matching: { $0["capabilities"] is [String: Any] && $0["environment"] is [String: Any] }
      ),
      let capabilities = payload["capabilities"] as? [String: Any],
      let coreReady = capabilities["core_ready"] as? Bool,
      let fullReady = capabilities["full_ready"] as? Bool,
      let environment = payload["environment"] as? [String: Any]
    else { return nil }

    let coreModules = payload["core_modules"] as? [String: Any]
    let missingCore = coreModules?["missing"] as? [String] ?? []
    let optionalGroups = payload["optional_groups"] as? [String: [String: Any]] ?? [:]
    let missingGroups = optionalGroups.compactMap { id, group -> EnvironmentMissingGroup? in
      let modules = group["missing"] as? [String] ?? []
      guard !modules.isEmpty else { return nil }
      return EnvironmentMissingGroup(
        id: id,
        label: group["label"] as? String ?? id,
        modules: modules.sorted()
      )
    }
    .sorted { $0.label < $1.label }

    return EnvironmentDiagnosis(
      status: !coreReady ? "blocked" : fullReady ? "ok" : "warning",
      selectedPython: selectedPython ?? environment["python_executable"] as? String,
      pythonVersion: environment["python_version"] as? String,
      coreReady: coreReady,
      fullReady: fullReady,
      missingCoreModules: missingCore.sorted(),
      missingOptionalGroups: missingGroups,
      message: nil,
      checkedAt: Date()
    )
  }
}
