import Foundation

enum LegacyReportEvidenceRole: String, CaseIterable, Hashable, Identifiable, Sendable {
  case unused
  case environment
  case inventory
  case fxcor
  case radialVelocity
  case istarmod
  case lithium
  case externalReference

  var id: String { rawValue }

  var title: String {
    switch self {
    case .unused: return "Do not include"
    case .environment: return "Environment check"
    case .inventory: return "MULTISPE inventory"
    case .fxcor: return "FXCOR summary"
    case .radialVelocity: return "RV analysis"
    case .istarmod: return "iSTARMOD summary"
    case .lithium: return "Li 6708 summary"
    case .externalReference: return "External reference"
    }
  }

  var commandOption: String? {
    switch self {
    case .unused: return nil
    case .environment: return "--envcheck"
    case .inventory: return "--inventory-summary"
    case .fxcor: return "--fxcor-summary"
    case .radialVelocity: return "--rv-summary"
    case .istarmod: return "--istarmod-summary"
    case .lithium: return "--li-summary"
    case .externalReference: return "--external-reference-summary"
    }
  }

  var allowsMultiple: Bool {
    self == .fxcor || self == .lithium || self == .unused
  }
}

struct LegacyReportEvidenceReview: Equatable, Sendable {
  let path: String
  let toolID: String?
  let status: String?
}

struct LegacyReportEvidenceAssignment: Equatable, Sendable {
  let path: String
  let role: LegacyReportEvidenceRole
}

struct LegacyReportPopulateSelection: Equatable, Sendable {
  var projectPath: String
  var assignments: [LegacyReportEvidenceAssignment]
  var mappingConfirmed: Bool
}

enum LegacyReportPopulateStatus: String, Equatable, Sendable {
  case pass = "PASS"
  case warning = "WARNING"
  case blocked = "BLOCKED_CONTROLADO"
}

struct LegacyReportPopulateValidation: Equatable, Sendable {
  let status: LegacyReportPopulateStatus
  let findings: [String]
  let nextActions: [String]

  var canRun: Bool {
    status != .blocked
  }
}

struct LegacyReportPreparedRun: Equatable, Sendable {
  let projectPath: String
  let evidenceByRole: [LegacyReportEvidenceRole: [String]]

  var inputPaths: [String] {
    [projectPath] + LegacyReportEvidenceRole.allCases.flatMap { evidenceByRole[$0] ?? [] }
  }

  func arguments(runURL: URL) -> [String] {
    var arguments = [projectPath]
    for role in LegacyReportEvidenceRole.allCases where role != .unused {
      guard let option = role.commandOption else { continue }
      for path in evidenceByRole[role] ?? [] {
        arguments += [option, path]
      }
    }
    arguments += [
      "--summary-json", runURL.appendingPathComponent("summary.json").path,
      "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
    ]
    return arguments
  }
}
