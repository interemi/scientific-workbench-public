import Foundation

enum DocumentWorkflowStatus: String, Sendable {
  case pass = "PASS"
  case warning = "WARNING"
  case blocked = "BLOCKED_CONTROLADO"
  case fail = "FAIL"
}

struct DOCXStyleMatch: Identifiable, Hashable, Sendable {
  let location: String
  let paragraphIndex: Int
  let tableIndex: Int?
  let rowIndex: Int?
  let cellIndex: Int?
  let runIndex: Int
  let text: String
  let bold: Bool
  let italic: Bool
  let underline: Bool
  let paragraphStyle: String?
  let characterStyle: String?

  var id: String {
    [
      location,
      String(tableIndex ?? 0),
      String(rowIndex ?? 0),
      String(cellIndex ?? 0),
      String(paragraphIndex),
      String(runIndex),
    ].joined(separator: ":")
  }

  var locationLabel: String {
    if location == "table" {
      return "Table \(tableIndex ?? 0), row \(rowIndex ?? 0), cell \(cellIndex ?? 0), run \(runIndex)"
    }
    return "Paragraph \(paragraphIndex), run \(runIndex)"
  }

  var styleLabels: [String] {
    var labels: [String] = []
    if bold { labels.append("Bold") }
    if italic { labels.append("Italic") }
    if underline { labels.append("Underline") }
    return labels
  }
}

struct DOCXStyleReview: Sendable {
  let inputPath: String
  let status: DocumentWorkflowStatus
  let requirements: [String: Bool]
  let matches: [DOCXStyleMatch]
  let findings: [String]
  let limitations: [String]
  let originalFingerprint: String

  var matchCount: Int { matches.count }

  var styleCounts: DOCXStyleCounts {
    DOCXStyleCounts(
      bold: matches.count { $0.bold },
      italic: matches.count { $0.italic },
      underline: matches.count { $0.underline },
      body: matches.count { $0.location == "body" },
      table: matches.count { $0.location == "table" }
    )
  }
}

struct DOCXStyleCounts: Equatable, Sendable {
  let bold: Int
  let italic: Int
  let underline: Int
  let body: Int
  let table: Int
}

struct DOCXStyleDiff: Identifiable, Hashable, Sendable {
  let match: DOCXStyleMatch
  let before: String
  let after: String
  let replacementCount: Int

  var id: String { match.id }
}

struct StagedDocumentCopy: Equatable, Sendable {
  let sourcePath: String
  let stagedPath: String
  let originalFingerprint: String
}

struct KeynotePreflightReview: Sendable {
  let status: DocumentWorkflowStatus
  let platform: String
  let osascriptAvailable: Bool
  let keynoteAvailable: Bool
  let recommendation: String
  let findings: [String]
  let originalFingerprint: String

  var canExport: Bool {
    status == .pass || status == .warning
  }
}
