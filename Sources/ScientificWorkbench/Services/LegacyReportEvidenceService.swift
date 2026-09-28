import Foundation

enum LegacyReportEvidenceError: LocalizedError, Equatable {
  case missingEvidence(String)
  case evidenceIsDirectory(String)
  case oversizedEvidence(String)
  case invalidJSON(String)
  case invalidSelection(String)

  var errorDescription: String? {
    switch self {
    case .missingEvidence(let path):
      return "The evidence file does not exist: \(path)"
    case .evidenceIsDirectory(let path):
      return "Choose a summary JSON file for evidence, not a folder: \(path)"
    case .oversizedEvidence(let path):
      return "The evidence JSON is unexpectedly large and was not loaded: \(path)"
    case .invalidJSON(let path):
      return "The evidence is not a readable JSON object: \(path)"
    case .invalidSelection(let message):
      return message
    }
  }
}

struct LegacyReportEvidenceService {
  private let maximumEvidenceBytes = 10 * 1_024 * 1_024

  func inspect(path: String) throws -> LegacyReportEvidenceReview {
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) else {
      throw LegacyReportEvidenceError.missingEvidence(path)
    }
    guard !isDirectory.boolValue else {
      throw LegacyReportEvidenceError.evidenceIsDirectory(path)
    }
    let attributes = try? FileManager.default.attributesOfItem(atPath: path)
    if let size = attributes?[.size] as? NSNumber,
       size.intValue > maximumEvidenceBytes {
      throw LegacyReportEvidenceError.oversizedEvidence(path)
    }
    guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
          let object = try? JSONSerialization.jsonObject(with: data),
          let payload = object as? [String: Any] else {
      throw LegacyReportEvidenceError.invalidJSON(path)
    }
    return LegacyReportEvidenceReview(
      path: path,
      toolID: payload["tool"] as? String,
      status: (payload["app_status"] as? String) ?? (payload["status"] as? String)
    )
  }

  func validate(
    selection: LegacyReportPopulateSelection,
    attachedInputPaths: [String],
    reviews: [String: LegacyReportEvidenceReview]
  ) -> LegacyReportPopulateValidation {
    guard !selection.projectPath.isEmpty else {
      return blocked("Select the legacy report scaffold project.")
    }
    guard attachedInputPaths.contains(selection.projectPath) else {
      return blocked("The selected report scaffold must remain attached as an input.")
    }
    var projectIsDirectory: ObjCBool = false
    guard FileManager.default.fileExists(
      atPath: selection.projectPath,
      isDirectory: &projectIsDirectory
    ), projectIsDirectory.boolValue else {
      return blocked("The selected report scaffold is not a readable directory.")
    }
    let mainTeX = URL(fileURLWithPath: selection.projectPath)
      .appendingPathComponent("main.tex").path
    guard FileManager.default.fileExists(atPath: mainTeX) else {
      return blocked("The selected folder is not a legacy report scaffold because main.tex is missing.")
    }

    let used = selection.assignments.filter { $0.role != .unused }
    guard !used.isEmpty else {
      return blocked("Assign at least one evidence JSON before populating the report.")
    }
    let duplicatePaths = Dictionary(grouping: used, by: \.path)
      .filter { $0.value.count > 1 }
      .map(\.key)
    guard duplicatePaths.isEmpty else {
      return blocked("Each evidence file can be assigned to only one report role.")
    }
    for assignment in used {
      guard attachedInputPaths.contains(assignment.path) else {
        return blocked("Every mapped evidence file must remain attached: \(assignment.path)")
      }
      guard reviews[assignment.path] != nil else {
        return blocked("Inspect the mapped evidence JSON before running: \(assignment.path)")
      }
    }

    for role in LegacyReportEvidenceRole.allCases where !role.allowsMultiple {
      let count = used.filter { $0.role == role }.count
      guard count <= 1 else {
        return blocked("\(role.title) accepts only one evidence file.")
      }
    }

    var findings: [String] = []
    var nextActions: [String] = []
    for assignment in used {
      guard let review = reviews[assignment.path] else { continue }
      if let toolID = review.toolID {
        let expected = expectedToolIDs(for: assignment.role)
        guard expected.contains(toolID) else {
          return blocked(
            "\(URL(fileURLWithPath: assignment.path).lastPathComponent) reports tool '\(toolID)', which does not match the selected \(assignment.role.title) role."
          )
        }
      } else {
        findings.append("\(URL(fileURLWithPath: assignment.path).lastPathComponent) has no standard tool identifier.")
        nextActions.append("Confirm its provenance before relying on that report section.")
      }
      if let status = review.status?.uppercased(),
         ["FAIL", "FAILED", "ERROR", "ROTO", "BLOCKED", "BLOCKED_CONTROLADO"].contains(status) {
        findings.append("\(URL(fileURLWithPath: assignment.path).lastPathComponent) reports status \(status).")
        nextActions.append("Review the failed or blocked evidence before including it in the report.")
      }
    }
    guard selection.mappingConfirmed else {
      return blocked("Review and confirm the evidence-to-section mapping before running.")
    }

    return LegacyReportPopulateValidation(
      status: findings.isEmpty ? .pass : .warning,
      findings: findings,
      nextActions: nextActions
    )
  }

  func prepare(
    selection: LegacyReportPopulateSelection,
    attachedInputPaths: [String],
    reviews: [String: LegacyReportEvidenceReview]
  ) throws -> LegacyReportPreparedRun {
    let validation = validate(
      selection: selection,
      attachedInputPaths: attachedInputPaths,
      reviews: reviews
    )
    guard validation.canRun else {
      throw LegacyReportEvidenceError.invalidSelection(
        validation.findings.first ?? "The legacy report evidence mapping is incomplete."
      )
    }
    var evidenceByRole: [LegacyReportEvidenceRole: [String]] = [:]
    for assignment in selection.assignments where assignment.role != .unused {
      evidenceByRole[assignment.role, default: []].append(assignment.path)
    }
    return LegacyReportPreparedRun(
      projectPath: selection.projectPath,
      evidenceByRole: evidenceByRole
    )
  }

  private func expectedToolIDs(for role: LegacyReportEvidenceRole) -> Set<String> {
    switch role {
    case .unused:
      return []
    case .environment:
      return ["legacy_spectroscopy_envcheck"]
    case .inventory:
      return ["echelle_multispec_inventory"]
    case .fxcor:
      return ["fxcor_iraf_workbench.run-auto"]
    case .radialVelocity:
      return ["legacy_rv_coursework_workbench.analyze"]
    case .istarmod:
      return ["istarmod_workbench.prepare-copy"]
    case .lithium:
      return ["li6708_equivalent_width_workbench.measure"]
    case .externalReference:
      return ["legacy_external_reference_check.check"]
    }
  }

  private func blocked(_ message: String) -> LegacyReportPopulateValidation {
    LegacyReportPopulateValidation(
      status: .blocked,
      findings: [message],
      nextActions: []
    )
  }
}
