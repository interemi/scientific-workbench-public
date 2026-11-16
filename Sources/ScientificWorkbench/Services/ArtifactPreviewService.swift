import AppKit
import Darwin
import Foundation
import ImageIO
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

enum ArtifactPreviewImage: Sendable {
  case raster(CGImage)
  case pdfThumbnail(CGImage)
}

struct ArtifactPreviewPayload: Sendable {
  var kind: ArtifactPreviewKind
  var title: String
  var text: String?
  var image: ArtifactPreviewImage?
  var note: String?

  static let outsideRun = ArtifactPreviewPayload(
    kind: .unavailable,
    title: "Preview unavailable",
    note: "The artifact is missing or resolves outside its recorded run folder."
  )
}

struct ArtifactPreviewService {
  static let rasterLoader = RasterPreviewLoader()
  private static let rasterExtensions: Set<String> = ["png", "jpg", "jpeg", "tif", "tiff"]
  private let maximumRasterFileBytes = 256 * 1024 * 1024
  private let maximumRasterDimension = 16_384
  private let maximumRasterPixels = 100_000_000
  private let maximumThumbnailDimension = 1_600
  private let maximumBytes = 80_000
  private let maximumLines = 80

  static func isRaster(_ artifact: Artifact) -> Bool {
    rasterExtensions.contains(artifact.url.pathExtension.lowercased())
  }

  func loadRaster(_ artifact: Artifact, in job: JobRecord) async -> ArtifactPreviewPayload? {
    await Self.rasterLoader.load(artifact, in: job)
  }

  func load(
    artifact: Artifact,
    redact: (String) -> String
  ) -> ArtifactPreviewPayload {
    load(at: artifact.url.standardizedFileURL.resolvingSymlinksInPath(),
         fileExtension: artifact.url.pathExtension.lowercased(), redact: redact)
  }

  fileprivate func load(
    at url: URL,
    fileExtension: String,
    redact: (String) -> String
  ) -> ArtifactPreviewPayload {
    if Self.rasterExtensions.contains(fileExtension) { return imagePreview(url) }
    switch fileExtension {
    case "pdf":
      return pdfPreview(url)
    case "csv", "tsv", "ecsv":
      return textPreview(url, kind: .table, title: "Table preview", redact: redact)
    case "md":
      return textPreview(url, kind: .markdown, title: "Markdown preview", redact: redact)
    case "txt", "log":
      return textPreview(url, kind: .log, title: "Log preview", redact: redact)
    case "json":
      return textPreview(url, kind: .json, title: "JSON preview", redact: redact)
    case "ipynb":
      return notebookPreview(url, redact: redact)
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

  fileprivate func imagePreview(_ url: URL) -> ArtifactPreviewPayload {
    let unreadable = ArtifactPreviewPayload(
      kind: .unavailable, title: "Image preview unavailable",
      note: "The image could not be decoded."
    )
    let tooLarge = ArtifactPreviewPayload(
      kind: .unavailable, title: "Image preview unavailable",
      note: "The image exceeds the in-app preview size limit. Reveal the original artifact to inspect it."
    )
    guard let size = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize else { return unreadable }
    guard size <= maximumRasterFileBytes else { return tooLarge }
    let readOptions = [kCGImageSourceShouldCache: false] as CFDictionary
    guard let source = CGImageSourceCreateWithURL(url as CFURL, readOptions),
          let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, readOptions) as? [CFString: Any],
          let width = properties[kCGImagePropertyPixelWidth] as? Int,
          let height = properties[kCGImagePropertyPixelHeight] as? Int,
          width > 0, height > 0 else { return unreadable }
    guard max(width, height) <= maximumRasterDimension,
          width <= maximumRasterPixels / height else { return tooLarge }

    let thumbnailOptions = [
      kCGImageSourceCreateThumbnailFromImageAlways: true,
      kCGImageSourceCreateThumbnailWithTransform: true,
      kCGImageSourceThumbnailMaxPixelSize: min(max(width, height), maximumThumbnailDimension),
      kCGImageSourceShouldCacheImmediately: true,
    ] as CFDictionary
    guard let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, thumbnailOptions),
          max(thumbnail.width, thumbnail.height) <= maximumThumbnailDimension else {
      return unreadable
    }
    let note = max(width, height) > maximumThumbnailDimension
      ? "Display preview reduced to \(thumbnail.width) × \(thumbnail.height) pixels. Use the original artifact for measurements."
      : nil
    return ArtifactPreviewPayload(kind: .image, title: "Image preview", image: .raster(thumbnail), note: note)
  }

  private func pdfPreview(_ url: URL) -> ArtifactPreviewPayload {
    guard
      let document = PDFDocument(url: url),
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
      image: thumbnail.cgImage(forProposedRect: nil, context: nil, hints: nil).map { .pdfThumbnail($0) },
      note: document.pageCount > 1 ? "Showing page 1 of \(document.pageCount)." : "Showing page 1."
    )
  }

  private func textPreview(
    _ url: URL,
    kind: ArtifactPreviewKind,
    title: String,
    redact: (String) -> String
  ) -> ArtifactPreviewPayload {
    guard let handle = try? FileHandle(forReadingFrom: url) else {
      return ArtifactPreviewPayload(
        kind: .unavailable,
        title: "\(title) unavailable",
        note: "The file is not readable UTF-8 text."
      )
    }
    defer { try? handle.close() }
    let data: Data
    do {
      data = try handle.read(upToCount: maximumBytes + 1) ?? Data()
    } catch {
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
    let lines = redact(text).split(omittingEmptySubsequences: false, whereSeparator: \.isNewline)
    let bounded = lines
      .prefix(maximumLines)
      .joined(separator: "\n")
    let truncated = data.count > maximumBytes || lines.count > maximumLines
    return ArtifactPreviewPayload(
      kind: kind,
      title: title,
      text: bounded,
      note: truncated ? "Preview truncated; review the complete file before opening it externally." : nil
    )
  }

  private func notebookPreview(
    _ url: URL,
    redact: (String) -> String
  ) -> ArtifactPreviewPayload {
    guard
      let data = try? Data(contentsOf: url, options: [.mappedIfSafe]),
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

struct ArtifactPreviewSnapshot: Sendable {
  let inspection: ArtifactInspection
  var payload: ArtifactPreviewPayload?
  let isGeneratedFITS: Bool
}

actor ArtifactPreviewLoader {
  static let shared = ArtifactPreviewLoader()

  private let inspection = ArtifactInspectionService()

  func load(
    _ artifact: Artifact, in job: JobRecord, includePreview: Bool,
    redact: @Sendable (String) -> String
  ) async -> ArtifactPreviewSnapshot? {
    guard !Task.isCancelled else { return nil }
    let metadata = autoreleasepool { inspection.inspect(artifact, in: job) }
    guard !Task.isCancelled else { return nil }

    var payload: ArtifactPreviewPayload?
    if includePreview {
      if let url = metadata.resolvedPreviewURL {
        if ArtifactPreviewService.isRaster(artifact) {
          payload = await ArtifactPreviewService.rasterLoader.load(at: url)
        } else {
          payload = autoreleasepool {
            ArtifactPreviewService().load(
              at: url, fileExtension: artifact.url.pathExtension.lowercased(), redact: redact
            )
          }
        }
      } else {
        payload = .outsideRun
      }
    }
    guard !Task.isCancelled else { return nil }
    let generated = artifact.artifactType == "preview_png" && job.capabilityID == "inspect_fits"
      && (job.requestInputPaths.first.map(FirstRunExampleService.isGeneratedFITS(at:)) ?? false)
    return ArtifactPreviewSnapshot(inspection: metadata, payload: payload, isGeneratedFITS: generated)
  }

  func comparison(
    _ first: Artifact, in firstJob: JobRecord, _ second: Artifact, in secondJob: JobRecord
  ) -> String? {
    guard !Task.isCancelled else { return nil }
    return autoreleasepool {
      let lhs = inspection.inspect(first, in: firstJob)
      guard !Task.isCancelled else { return nil }
      let rhs = inspection.inspect(second, in: secondJob)
      return inspection.comparisonSummary(lhs, rhs)
    }
  }

  func previewURL(for artifact: Artifact, in job: JobRecord) -> URL? {
    guard !Task.isCancelled else { return nil }
    return inspection.previewURL(for: artifact, in: job)
  }
}

// A canceled caller can finish an in-flight ImageIO call, but queued work
// checks cancellation before opening its file and never publishes that result.
actor RasterPreviewLoader {
  static let maximumCacheBytes = 12 * 1024 * 1024

  struct CacheUsage: Equatable, Sendable {
    fileprivate let id: UUID?
    let bytes: Int
  }

  private struct SourceVersion: Equatable {
    let device: dev_t
    let inode: ino_t
    let bytes: off_t
    let modifiedSeconds: Int
    let modifiedNanoseconds: Int
    let changedSeconds: Int
    let changedNanoseconds: Int

    init?(_ url: URL) {
      var info = stat()
      guard lstat(url.path, &info) == 0, info.st_mode & S_IFMT == S_IFREG else { return nil }
      device = info.st_dev
      inode = info.st_ino
      bytes = info.st_size
      modifiedSeconds = info.st_mtimespec.tv_sec
      modifiedNanoseconds = info.st_mtimespec.tv_nsec
      changedSeconds = info.st_ctimespec.tv_sec
      changedNanoseconds = info.st_ctimespec.tv_nsec
    }
  }

  private struct CacheEntry {
    let id = UUID()
    let url: URL
    let version: SourceVersion
    let payload: ArtifactPreviewPayload
    let bytes: Int
  }

  private var cache: CacheEntry?

  func cacheUsage() -> CacheUsage {
    CacheUsage(id: cache?.id, bytes: cache?.bytes ?? 0)
  }

  func clearCache(reviewed usage: CacheUsage) -> CacheUsage? {
    guard usage.id == cache?.id else { return nil }
    cache = nil
    return cacheUsage()
  }

  func load(_ artifact: Artifact, in job: JobRecord) -> ArtifactPreviewPayload? {
    guard !Task.isCancelled else { return nil }
    guard let url = ArtifactInspectionService().previewURL(for: artifact, in: job) else { return .outsideRun }
    return load(at: url)
  }

  fileprivate func load(at url: URL) -> ArtifactPreviewPayload? {
    guard !Task.isCancelled else { return nil }
    guard let version = SourceVersion(url) else { return .outsideRun }
    if let cache, cache.url == url, cache.version == version { return cache.payload }

    let result = ArtifactPreviewService().imagePreview(url)
    guard !Task.isCancelled else { return nil }
    guard SourceVersion(url) == version else {
      return ArtifactPreviewPayload(
        kind: .unavailable,
        title: "Image preview unavailable",
        note: "The artifact changed while loading. Select it again to refresh the preview."
      )
    }
    if case .raster(let thumbnail) = result.image {
      let bytes = thumbnail.bytesPerRow * thumbnail.height
      if bytes <= Self.maximumCacheBytes {
        cache = CacheEntry(url: url, version: version, payload: result, bytes: bytes)
      }
    }
    return result
  }
}
