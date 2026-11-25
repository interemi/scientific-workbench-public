import CoreFoundation
import Foundation

struct RunBackendEvidence: Codable, Equatable, Sendable {
  enum Backend: String, Codable, Sendable {
    case apt, stilts, iraf, latexmk, pdflatex, keynote, libreOffice, quickLook
    case iWorkPreviewAsset, pdfFirstPage, imageCopy
  }

  let backend: Backend
  let reportedExitCodes: [Int32]

  private static let subprocessRoutes: [String: Backend] = [
    "apt_workbench.run-batch": .apt,
    "stilts_workbench.convert": .stilts,
    "stilts_workbench.filter": .stilts,
    "stilts_workbench.crossmatch-sky": .stilts,
    "stilts_workbench.votlint": .stilts,
  ]

  static func tracks(_ tool: String) -> Bool {
    subprocessRoutes[tool] != nil || [
      "fxcor_iraf_workbench.run-auto", "latex_workbench.compile", "keynote_export",
      "quicklook_bridge", "iwork_workbench", "presentation_workbench.inspect",
      "presentation_workbench.existing-deck-style-audit",
    ].contains(tool)
  }

  static func reported(in payload: [String: Any]) -> Self? {
    guard let tool = payload["tool"] as? String, let results = payload["results"] as? [String: Any] else {
      return nil
    }
    if let backend = subprocessRoutes[tool] {
      guard boolean(results["dry_run"]) == false, let exitCode = exitCode(results["returncode"]) else { return nil }
      return Self(backend: backend, reportedExitCodes: [exitCode])
    }

    switch tool {
    case "fxcor_iraf_workbench.run-auto":
      let runs = results["case_runs"] as? [[String: Any]] ?? []
      let codes = runs.compactMap { run in exitCode((run["outcome"] as? [String: Any])?["returncode"]) }
      return codes.isEmpty ? nil : Self(backend: .iraf, reportedExitCodes: codes)
    case "latex_workbench.compile":
      guard boolean(results["attempted"]) == true,
            let count = exitCode(results["pass_count"]), count > 0 else { return nil }
      switch results["engine"] as? String {
      case "latexmk": return Self(backend: .latexmk, reportedExitCodes: [])
      case "pdflatex": return Self(backend: .pdflatex, reportedExitCodes: [])
      default: return nil
      }
    case "keynote_export":
      let qa = payload["qa"] as? [String: Any]
      let metrics = qa?["metrics"] as? [String: Any]
      return boolean(metrics?["used_gui_path"]) == true
        ? Self(backend: .keynote, reportedExitCodes: []) : nil
    case "quicklook_bridge":
      guard ["PASS", "WARNING"].contains(payload["app_status"] as? String ?? "") else { return nil }
      return localPreview(results["method"])
    case "iwork_workbench":
      guard let output = results["native_preview"] as? String, !output.isEmpty else { return nil }
      return localPreview(results["native_preview_method"])
    case "presentation_workbench.inspect":
      let inspection = results["inspection"] as? [String: Any]
      return presentationExport(inspection?["preview_export"] as? [String: Any])
    case "presentation_workbench.existing-deck-style-audit":
      let preview = results["reference_preview"] as? [String: Any]
      guard boolean(preview?["success"]) == true else { return nil }
      let result = preview?["export_result"] as? [String: Any]
      return presentationExport(result) ?? localPreview(result?["method"])
    default:
      return nil
    }
  }

  private static func localPreview(_ value: Any?) -> Self? {
    let methods: [String: Backend] = [
      "qlmanage": .quickLook, "iwork_preview_asset": .iWorkPreviewAsset,
      "pdf_first_page": .pdfFirstPage, "image_copy": .imageCopy,
    ]
    return (value as? String).flatMap { methods[$0] }.map { Self(backend: $0, reportedExitCodes: []) }
  }

  private static func presentationExport(_ report: [String: Any]?) -> Self? {
    guard boolean(report?["success"]) == true else { return nil }
    switch report?["backend_used"] as? String {
    case "soffice": return Self(backend: .libreOffice, reportedExitCodes: [])
    case "keynote": return Self(backend: .keynote, reportedExitCodes: [])
    default: return nil
    }
  }

  private static func boolean(_ value: Any?) -> Bool? {
    guard let number = value as? NSNumber, CFGetTypeID(number) == CFBooleanGetTypeID() else { return nil }
    return number.boolValue
  }

  private static func exitCode(_ value: Any?) -> Int32? {
    guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
    return Int32(exactly: number.doubleValue)
  }
}
