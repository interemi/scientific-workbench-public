import CryptoKit
import Foundation

enum DocumentWorkflowError: LocalizedError, Equatable {
  case missingInput(String)
  case unsupportedDOCX
  case unsupportedPresentation
  case unreadableSummary
  case invalidSummary
  case copyFailed(String)
  case originalChanged
  case confirmationRequired
  case noReviewedChanges
  case keynotePreflightRequired
  case keynoteConfirmationRequired

  var errorDescription: String? {
    switch self {
    case .missingInput(let path):
      return "The selected input does not exist: \(path)"
    case .unsupportedDOCX:
      return "Choose one .docx file for the style workflow."
    case .unsupportedPresentation:
      return "Choose one .key, .pptx, or .pptm presentation."
    case .unreadableSummary:
      return "The workflow summary could not be read."
    case .invalidSummary:
      return "The workflow returned an invalid or incomplete summary."
    case .copyFailed(let message):
      return "The input could not be copied into the run: \(message)"
    case .originalChanged:
      return "The original input changed during a copy-only workflow."
    case .confirmationRequired:
      return "Review and confirm the replacement preview before writing an edited copy."
    case .noReviewedChanges:
      return "No matching reviewed runs contain the find text."
    case .keynotePreflightRequired:
      return "Run a successful Keynote preflight before approving GUI automation."
    case .keynoteConfirmationRequired:
      return "Confirm the copied-deck GUI export before launching Keynote."
    }
  }
}

struct DocumentWorkflowService {
  func stageDOCX(sourcePath: String, runDirectory: String) throws -> StagedDocumentCopy {
    guard URL(fileURLWithPath: sourcePath).pathExtension.lowercased() == "docx" else {
      throw DocumentWorkflowError.unsupportedDOCX
    }
    return try stageCopy(sourcePath: sourcePath, runDirectory: runDirectory)
  }

  func stagePresentation(sourcePath: String, runDirectory: String) throws -> StagedDocumentCopy {
    let allowed = ["key", "pptx", "pptm"]
    guard allowed.contains(URL(fileURLWithPath: sourcePath).pathExtension.lowercased()) else {
      throw DocumentWorkflowError.unsupportedPresentation
    }
    return try stageCopy(sourcePath: sourcePath, runDirectory: runDirectory)
  }

  func stageCopy(sourcePath: String, runDirectory: String) throws -> StagedDocumentCopy {
    let source = URL(fileURLWithPath: sourcePath)
    guard FileManager.default.fileExists(atPath: source.path) else {
      throw DocumentWorkflowError.missingInput(sourcePath)
    }
    let fingerprint = try fingerprint(path: sourcePath)
    let inputs = URL(fileURLWithPath: runDirectory).appendingPathComponent("inputs", isDirectory: true)
    try FileManager.default.createDirectory(at: inputs, withIntermediateDirectories: true)
    let destination = inputs.appendingPathComponent(source.lastPathComponent, isDirectory: source.hasDirectoryPath)
    if FileManager.default.fileExists(atPath: destination.path) {
      try FileManager.default.removeItem(at: destination)
    }
    do {
      try FileManager.default.copyItem(at: source, to: destination)
    } catch {
      throw DocumentWorkflowError.copyFailed(error.localizedDescription)
    }
    return StagedDocumentCopy(
      sourcePath: sourcePath,
      stagedPath: destination.path,
      originalFingerprint: fingerprint
    )
  }

  func originalIsUnchanged(_ staged: StagedDocumentCopy) -> Bool {
    (try? fingerprint(path: staged.sourcePath)) == staged.originalFingerprint
  }

  func parseDOCXInventory(summaryPath: String, originalFingerprint: String) throws -> DOCXStyleReview {
    let object = try summaryObject(at: summaryPath)
    guard
      let results = object["results"] as? [String: Any],
      let inventory = results["inventory"] as? [String: Any],
      let rawMatches = inventory["matches"] as? [[String: Any]]
    else {
      throw DocumentWorkflowError.invalidSummary
    }
    let matches = rawMatches.compactMap(parseStyleMatch)
    let qa = object["qa"] as? [String: Any]
    let findings = stringFindings(qa?["findings"])
    let limitations = inventory["limitations"] as? [String] ?? []
    return DOCXStyleReview(
      inputPath: inventory["input"] as? String ?? "",
      status: status(from: object),
      requirements: inventory["requirements"] as? [String: Bool] ?? [:],
      matches: matches,
      findings: findings,
      limitations: limitations,
      originalFingerprint: originalFingerprint
    )
  }

  func parseKeynotePreflight(summaryPath: String, originalFingerprint: String) throws -> KeynotePreflightReview {
    let object = try summaryObject(at: summaryPath)
    guard
      let results = object["results"] as? [String: Any],
      let capabilities = results["capabilities"] as? [String: Any]
    else {
      throw DocumentWorkflowError.invalidSummary
    }
    let blocking = results["blocking_findings"] as? [String] ?? []
    let warnings = results["warning_findings"] as? [String] ?? []
    return KeynotePreflightReview(
      status: status(from: object),
      platform: capabilities["platform"] as? String ?? "unknown",
      osascriptAvailable: capabilities["osascript"] as? Bool ?? false,
      keynoteAvailable: capabilities["keynote_app"] as? Bool ?? false,
      recommendation: results["recommendation"] as? String ?? "Review Keynote readiness.",
      findings: blocking + warnings,
      originalFingerprint: originalFingerprint
    )
  }

  func diff(review: DOCXStyleReview, find: String, replace: String) -> [DOCXStyleDiff] {
    guard !find.isEmpty else { return [] }
    return review.matches.compactMap { match in
      let count = match.text.components(separatedBy: find).count - 1
      guard count > 0 else { return nil }
      return DOCXStyleDiff(
        match: match,
        before: match.text,
        after: match.text.replacingOccurrences(of: find, with: replace),
        replacementCount: count
      )
    }
  }

  func validateReplacementApproval(confirmed: Bool, diff: [DOCXStyleDiff]) throws {
    guard confirmed else {
      throw DocumentWorkflowError.confirmationRequired
    }
    guard !diff.isEmpty else {
      throw DocumentWorkflowError.noReviewedChanges
    }
  }

  func validateKeynoteExportApproval(
    confirmed: Bool,
    preflight: KeynotePreflightReview?
  ) throws {
    guard confirmed else {
      throw DocumentWorkflowError.keynoteConfirmationRequired
    }
    guard preflight?.canExport == true else {
      throw DocumentWorkflowError.keynotePreflightRequired
    }
  }

  func fingerprint(path: String) throws -> String {
    let root = URL(fileURLWithPath: path)
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: root.path, isDirectory: &isDirectory) else {
      throw DocumentWorkflowError.missingInput(path)
    }
    var hasher = SHA256()
    if !isDirectory.boolValue {
      hasher.update(data: try Data(contentsOf: root))
      return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
    guard let enumerator = FileManager.default.enumerator(
      at: root,
      includingPropertiesForKeys: [.isRegularFileKey],
      options: [.skipsHiddenFiles]
    ) else {
      return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
    let files = enumerator.compactMap { $0 as? URL }.filter {
      (try? $0.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true
    }.sorted { $0.path < $1.path }
    for file in files {
      let relative = String(file.path.dropFirst(root.path.count))
      hasher.update(data: Data(relative.utf8))
      hasher.update(data: try Data(contentsOf: file))
    }
    return hasher.finalize().map { String(format: "%02x", $0) }.joined()
  }

  private func summaryObject(at path: String) throws -> [String: Any] {
    guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)) else {
      throw DocumentWorkflowError.unreadableSummary
    }
    guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      throw DocumentWorkflowError.invalidSummary
    }
    return object
  }

  private func status(from object: [String: Any]) -> DocumentWorkflowStatus {
    let raw = (object["app_status"] as? String ?? object["status"] as? String ?? "WARNING").uppercased()
    switch raw {
    case "PASS", "OK", "SUCCESS": return .pass
    case "BLOCKED", "BLOCKED_CONTROLADO": return .blocked
    case "FAIL", "FAILED", "ERROR": return .fail
    default: return .warning
    }
  }

  private func parseStyleMatch(_ object: [String: Any]) -> DOCXStyleMatch? {
    guard
      let location = object["location"] as? String,
      let paragraphIndex = object["paragraph_index"] as? Int,
      let runIndex = object["run_index"] as? Int,
      let text = object["text"] as? String
    else {
      return nil
    }
    return DOCXStyleMatch(
      location: location,
      paragraphIndex: paragraphIndex,
      tableIndex: object["table_index"] as? Int,
      rowIndex: object["row_index"] as? Int,
      cellIndex: object["cell_index"] as? Int,
      runIndex: runIndex,
      text: text,
      bold: object["bold"] as? Bool ?? false,
      italic: object["italic"] as? Bool ?? false,
      underline: object["underline"] as? Bool ?? false,
      paragraphStyle: object["paragraph_style"] as? String,
      characterStyle: object["character_style"] as? String
    )
  }

  private func stringFindings(_ value: Any?) -> [String] {
    guard let items = value as? [Any] else { return [] }
    return items.map { item in
      if let text = item as? String { return text }
      if let object = item as? [String: Any] {
        return object["detail"] as? String
          ?? object["message"] as? String
          ?? object["title"] as? String
          ?? String(describing: object)
      }
      return String(describing: item)
    }
  }
}
