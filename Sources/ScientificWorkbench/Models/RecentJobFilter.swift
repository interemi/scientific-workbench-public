import Foundation

enum RecentJobWindow: String, CaseIterable {
  case any
  case lastDay
  case lastWeek
  case lastMonth

  var title: String {
    switch self {
    case .any: return "Any date"
    case .lastDay: return "Last 24 hours"
    case .lastWeek: return "Last 7 days"
    case .lastMonth: return "Last 30 days"
    }
  }

  var duration: TimeInterval? {
    switch self {
    case .any: return nil
    case .lastDay: return 24 * 60 * 60
    case .lastWeek: return 7 * 24 * 60 * 60
    case .lastMonth: return 30 * 24 * 60 * 60
    }
  }
}

enum RecentArtifactType: String, CaseIterable {
  case any
  case table
  case image
  case fits
  case notebook
  case pdf
  case log
  case json
  case document
  case other

  var title: String {
    switch self {
    case .any: return "Any artifact"
    case .table: return "Table"
    case .image: return "Image"
    case .fits: return "FITS"
    case .notebook: return "Notebook"
    case .pdf: return "PDF"
    case .log: return "Log"
    case .json: return "JSON"
    case .document: return "Document"
    case .other: return "Other"
    }
  }

  static func classify(_ artifact: Artifact) -> RecentArtifactType {
    let ext = artifact.url.pathExtension.lowercased()
    let type = artifact.artifactType?.lowercased() ?? ""
    if ["fit", "fits", "fts"].contains(ext) { return .fits }
    if ["csv", "tsv", "ecsv", "parquet"].contains(ext) { return .table }
    if ["png", "jpg", "jpeg", "tif", "tiff", "heic"].contains(ext) { return .image }
    if ext == "ipynb" { return .notebook }
    if ext == "pdf" { return .pdf }
    if ext == "log" || ["stdout.txt", "stderr.txt", "command.txt"].contains(artifact.relativePath.lowercased()) {
      return .log
    }
    if ext == "json" { return .json }
    if ["md", "txt", "docx", "odt", "tex", "pptx", "key"].contains(ext) { return .document }
    if type.hasPrefix("fits_") { return .fits }
    if type.hasPrefix("table_") { return .table }
    if ["preview_png", "app_preview"].contains(type) { return .image }
    if type == "log_txt" { return .log }
    if type.hasSuffix("_json") { return .json }
    return .other
  }
}

struct RecentJobFilter {
  var query = ""
  var window: RecentJobWindow = .any
  var status: JobStatus?
  var artifactType: RecentArtifactType = .any

  var isActive: Bool {
    !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
      window != .any || status != nil || artifactType != .any
  }

  func matches(_ job: JobRecord, now: Date = Date()) -> Bool {
    if let duration = window.duration, job.createdAt < now.addingTimeInterval(-duration) {
      return false
    }
    if let status, job.status != status { return false }
    if artifactType != .any,
       !job.artifacts.contains(where: { RecentArtifactType.classify($0) == artifactType }) {
      return false
    }

    let terms = query.split(whereSeparator: \.isWhitespace)
    guard !terms.isEmpty else { return true }
    let searchable = [
      job.capabilityLabel,
      job.capabilityID,
      job.id.uuidString,
      job.status.title,
      job.displaySeverity,
      DateFormatters.timestamp.string(from: job.createdAt),
      job.shortSummary ?? "",
      job.parsedTool ?? ""
    ] + job.tags + job.artifacts.flatMap { artifact in
      [artifact.label ?? "", artifact.relativePath, artifact.artifactType ?? ""]
    }
    return terms.allSatisfy { term in
      searchable.contains { $0.localizedStandardContains(String(term)) }
    }
  }
}
