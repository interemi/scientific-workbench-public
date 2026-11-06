import AppKit
import Foundation
import PDFKit

enum ArtifactPreviewKind: String, Equatable {
  case image
  case pdf
  case table
  case markdown
  case notebook
  case log
  case json
  case unavailable
}

struct ArtifactPreviewPayload: Equatable {
  var kind: ArtifactPreviewKind
  var title: String
  var text: String?
  var imageData: Data?
  var note: String?
}

struct ArtifactPreviewService {
  private let maximumBytes = 80_000
  private let maximumLines = 80

  func load(
    artifact: Artifact,
    redact: (String) -> String
  ) -> ArtifactPreviewPayload {
    let ext = artifact.url.pathExtension.lowercased()
    switch ext {
    case "png", "jpg", "jpeg", "tif", "tiff":
      return imagePreview(artifact)
    case "pdf":
      return pdfPreview(artifact)
    case "csv", "tsv", "ecsv":
      return textPreview(artifact, kind: .table, title: "Table preview", redact: redact)
    case "md":
      return textPreview(artifact, kind: .markdown, title: "Markdown preview", redact: redact)
    case "txt", "log":
      return textPreview(artifact, kind: .log, title: "Log preview", redact: redact)
    case "json":
      return textPreview(artifact, kind: .json, title: "JSON preview", redact: redact)
    case "ipynb":
      return notebookPreview(artifact, redact: redact)
    case "fit", "fits", "fts":
      return ArtifactPreviewPayload(
        kind: .unavailable,
        title: "FITS image preview unavailable",
        note: "Select a generated PNG quicklook when present. Raw FITS image rendering is not supported in this bounded preview."
      )
    default:
      return ArtifactPreviewPayload(
        kind: .unavailable,
        title: "Preview unavailable",
        note: "This file has no in-app preview. Review its location before choosing an external app."
      )
    }
  }

  private func imagePreview(_ artifact: Artifact) -> ArtifactPreviewPayload {
    guard let data = try? Data(contentsOf: artifact.url, options: [.mappedIfSafe]),
          NSImage(data: data) != nil else {
      return ArtifactPreviewPayload(
        kind: .unavailable,
        title: "Image preview unavailable",
        note: "The image could not be decoded."
      )
    }
    return ArtifactPreviewPayload(kind: .image, title: "Image preview", imageData: data)
  }

  private func pdfPreview(_ artifact: Artifact) -> ArtifactPreviewPayload {
    guard
      let document = PDFDocument(url: artifact.url),
      let page = document.page(at: 0)
    else {
      return ArtifactPreviewPayload(
        kind: .unavailable,
        title: "PDF preview unavailable",
        note: "The PDF is corrupt, empty, or unsupported."
      )
    }
    let thumbnail = page.thumbnail(of: NSSize(width: 1_200, height: 1_600), for: .mediaBox)
    return ArtifactPreviewPayload(
      kind: .pdf,
      title: "PDF preview",
      imageData: thumbnail.tiffRepresentation,
      note: document.pageCount > 1 ? "Showing page 1 of \(document.pageCount)." : "Showing page 1."
    )
  }

  private func textPreview(
    _ artifact: Artifact,
    kind: ArtifactPreviewKind,
    title: String,
    redact: (String) -> String
  ) -> ArtifactPreviewPayload {
    guard let data = try? Data(contentsOf: artifact.url, options: [.mappedIfSafe]) else {
      return ArtifactPreviewPayload(
        kind: .unavailable,
        title: "\(title) unavailable",
        note: "The file is not readable UTF-8 text."
      )
    }
    let byteLimit = min(data.count, maximumBytes)
    let possibleBoundaryBytes = data.count > maximumBytes ? 3 : 0
    var decoded: String?
    for trailingBytes in 0...possibleBoundaryBytes where byteLimit >= trailingBytes {
      if let text = String(data: data.prefix(byteLimit - trailingBytes), encoding: .utf8) {
        decoded = text
        break
      }
    }
    guard let text = decoded else {
      return ArtifactPreviewPayload(
        kind: .unavailable,
        title: "\(title) unavailable",
        note: "The file is not readable UTF-8 text."
      )
    }
    let bounded = text.split(separator: "\n", omittingEmptySubsequences: false)
      .prefix(maximumLines)
      .joined(separator: "\n")
    let truncated = data.count > maximumBytes || text.split(separator: "\n").count > maximumLines
    return ArtifactPreviewPayload(
      kind: kind,
      title: title,
      text: redact(bounded),
      note: truncated ? "Preview truncated; review the complete file before opening it externally." : nil
    )
  }

  private func notebookPreview(
    _ artifact: Artifact,
    redact: (String) -> String
  ) -> ArtifactPreviewPayload {
    guard
      let data = try? Data(contentsOf: artifact.url, options: [.mappedIfSafe]),
      let object = try? JSONSerialization.jsonObject(with: Data(data.prefix(2_000_000))) as? [String: Any],
      let cells = object["cells"] as? [[String: Any]]
    else {
      return ArtifactPreviewPayload(
        kind: .unavailable,
        title: "Notebook preview unavailable",
        note: "The notebook JSON is corrupt or too large to preview safely."
      )
    }

    var lines = ["Notebook cells: \(cells.count)", ""]
    for (index, cell) in cells.prefix(12).enumerated() {
      let cellType = cell["cell_type"] as? String ?? "unknown"
      let source: String
      if let values = cell["source"] as? [String] {
        source = values.joined()
      } else {
        source = cell["source"] as? String ?? ""
      }
      let excerpt = source
        .split(separator: "\n", omittingEmptySubsequences: false)
        .prefix(8)
        .joined(separator: "\n")
      lines += ["[\(index + 1)] \(cellType)", excerpt, ""]
    }
    if cells.count > 12 {
      lines.append("Preview truncated after 12 cells.")
    }
    return ArtifactPreviewPayload(
      kind: .notebook,
      title: "Notebook preview",
      text: redact(lines.joined(separator: "\n")),
      note: cells.count > 12 ? "Only source text is shown. Review the full notebook before opening it externally." : nil
    )
  }
}
