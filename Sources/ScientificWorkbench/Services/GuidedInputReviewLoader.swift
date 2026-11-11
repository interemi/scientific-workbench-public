import Foundation

struct LegacyReportInputReview: Sendable {
  var directories: [String] = []
  var evidenceFiles: [String] = []
  var scaffoldIssues: [String: String] = [:]
  var evidence: [String: Result<LegacyReportEvidenceReview, any Error>] = [:]

  var reviews: [String: LegacyReportEvidenceReview] {
    evidence.compactMapValues { try? $0.get() }
  }
}

actor GuidedInputReviewLoader {
  static let shared = GuidedInputReviewLoader()

  func catalogFiles(in paths: [String]) throws -> [String] {
    try paths.filter { path in
      try Task.checkCancellation()
      var isDirectory: ObjCBool = false
      return FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
        && !isDirectory.boolValue
    }
  }

  func inspectCatalog(at path: String) throws -> CatalogCrossmatchTableReview {
    try Task.checkCancellation()
    let review = try autoreleasepool { try CatalogCrossmatchInspectionService().inspect(path: path) }
    try Task.checkCancellation()
    return review
  }

  func inspectReportInputs(_ paths: [String]) throws -> LegacyReportInputReview {
    let service = LegacyReportEvidenceService()
    var review = LegacyReportInputReview()
    for path in paths {
      try Task.checkCancellation()
      var isDirectory: ObjCBool = false
      guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) else { continue }
      if isDirectory.boolValue {
        review.directories.append(path)
        review.scaffoldIssues[path] = service.scaffoldIssue(at: path)
      } else if URL(fileURLWithPath: path).pathExtension.lowercased() == "json" {
        review.evidenceFiles.append(path)
        review.evidence[path] = autoreleasepool { Result { try service.inspect(path: path) } }
      }
    }
    try Task.checkCancellation()
    return review
  }

  func prepareReport(
    selection: LegacyReportPopulateSelection,
    attachedInputPaths: [String],
    reviews: [String: LegacyReportEvidenceReview]
  ) throws -> LegacyReportPreparedRun {
    try Task.checkCancellation()
    let prepared = try LegacyReportEvidenceService().prepare(
      selection: selection, attachedInputPaths: attachedInputPaths, reviews: reviews
    )
    try Task.checkCancellation()
    return prepared
  }
}
