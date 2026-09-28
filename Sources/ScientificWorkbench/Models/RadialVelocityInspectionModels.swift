import Foundation

enum RadialVelocityReviewStatus: String, Sendable {
  case pass = "PASS"
  case warning = "WARNING"
  case blocked = "BLOCKED_CONTROLADO"
}

enum RadialVelocityTimeSystem: String, CaseIterable, Identifiable, Sendable {
  case jd = "JD"
  case bjd = "BJD"
  case hjd = "HJD"
  case mjd = "MJD"

  var id: String { rawValue }

  var title: String {
    switch self {
    case .jd: return "JD"
    case .bjd: return "BJD"
    case .hjd: return "HJD"
    case .mjd: return "MJD"
    }
  }
}

enum RadialVelocityUnit: String, CaseIterable, Identifiable, Sendable {
  case kilometersPerSecond = "km/s"
  case metersPerSecond = "m/s"

  var id: String { rawValue }
  var title: String { rawValue }
}

struct RadialVelocityColumn: Identifiable, Hashable, Sendable {
  let index: Int
  let name: String
  let numericCount: Int
  let rowCount: Int
  let timeScore: Int
  let velocityScore: Int
  let uncertaintyScore: Int

  var id: Int { index }

  var numericFraction: Double {
    guard rowCount > 0 else { return 0 }
    return Double(numericCount) / Double(rowCount)
  }
}

struct RadialVelocityTableReview: Sendable {
  let inputPath: String
  let separatorLabel: String
  let columns: [RadialVelocityColumn]
  let rows: [[String]]
  let status: RadialVelocityReviewStatus
  let findings: [String]
  let nextActions: [String]
  let recommendedTimeColumn: Int?
  let recommendedVelocityColumn: Int?
  let recommendedUncertaintyColumn: Int?
  let inferredTimeSystem: RadialVelocityTimeSystem?
  let inferredVelocityUnit: RadialVelocityUnit?
  let usedPositionalColumns: Bool
}

struct RadialVelocitySelection: Equatable, Sendable {
  var timeColumn: Int?
  var velocityColumn: Int?
  var uncertaintyColumn: Int?
  var timeSystem: RadialVelocityTimeSystem
  var velocityUnit: RadialVelocityUnit
}

struct RadialVelocitySelectionValidation: Equatable, Sendable {
  let status: RadialVelocityReviewStatus
  let findings: [String]
  let nextActions: [String]

  var canRun: Bool {
    status != .blocked
  }
}

struct RadialVelocityStagedInput: Equatable, Sendable {
  let velsPath: String
  let mappingPath: String
  let acceptedRows: Int
  let skippedRows: Int
}
