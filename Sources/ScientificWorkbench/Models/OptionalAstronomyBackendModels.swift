import Foundation

enum OptionalBackendState: String, Codable, Equatable, Sendable {
  case unknown
  case ready
  case unavailable
  case warning

  var title: String {
    switch self {
    case .unknown: return "Not checked"
    case .ready: return "Ready"
    case .unavailable: return "Unavailable"
    case .warning: return "Needs attention"
    }
  }
}

struct OptionalAstronomyBackendStatus: Equatable, Sendable {
  var overallStatus: String
  var java: OptionalBackendState
  var stilts: OptionalBackendState
  var topcat: OptionalBackendState
  var aptOverallStatus: String
  var aptCommand: OptionalBackendState
  var aptPreferences: OptionalBackendState
  var aptBatch: OptionalBackendState
  var summary: String
  var blockingMessage: String?
  var aptSummary: String
  var aptBlockingMessage: String?
  var aptNextActions: [String]
  var nativeAlternativeCapabilityID: String?
  var aptNativeAlternativeCapabilityIDs: [String]
  var checkedAt: Date?

  static let unknown = OptionalAstronomyBackendStatus(
    overallStatus: "unknown",
    java: .unknown,
    stilts: .unknown,
    topcat: .unknown,
    aptOverallStatus: "unknown",
    aptCommand: .unknown,
    aptPreferences: .unknown,
    aptBatch: .unknown,
    summary: "Run the optional backend check to inspect Java, STILTS, and TOPCAT.",
    blockingMessage: nil,
    aptSummary: "Run the optional backend check to inspect APT command, preferences, and batch readiness.",
    aptBlockingMessage: nil,
    aptNextActions: [],
    nativeAlternativeCapabilityID: "catalog_workbench.crossmatch-sky",
    aptNativeAlternativeCapabilityIDs: ["inspect_fits", "photometry_noise_budget"],
    checkedAt: nil
  )
}
