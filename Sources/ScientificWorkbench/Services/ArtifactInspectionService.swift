import Foundation

enum ArtifactRole: String, Sendable {
  case primaryResult = "Primary result"
  case result = "Result"
  case evidence = "Evidence"
  case log = "Log"
}

struct ArtifactInspection: Sendable {
  let role: ArtifactRole
  let isInsideRun: Bool
  let isReadableFile: Bool
  let currentByteCount: Int64?
  let modifiedAt: Date?
  let recordedByteCount: Int64?
  let recordedSHA256: String?

  var canPreview: Bool { isInsideRun && isReadableFile }
}

/// Derives presentation metadata from a retained run without changing JobRecord or Artifact.
struct ArtifactInspectionService {
  private let maximumManifestBytes = 1_000_000
  private let homeDirectory: URL

  init(homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser) {
    self.homeDirectory = homeDirectory
  }

  func inspect(_ artifact: Artifact, in job: JobRecord) -> ArtifactInspection {
    let root = URL(fileURLWithPath: job.runDirectory, isDirectory: true)
      .standardizedFileURL.resolvingSymlinksInPath()
    let file = artifact.url.standardizedFileURL.resolvingSymlinksInPath()
    let inside = isInside(file, root: root)
    let values = inside ? try? file.resourceValues(forKeys: [
      .isRegularFileKey, .fileSizeKey, .contentModificationDateKey
    ]) : nil
    let readable = values?.isRegularFile == true
    let recorded = inside ? manifestOutput(for: file, root: root) : nil
    return ArtifactInspection(
      role: role(for: artifact),
      isInsideRun: inside,
      isReadableFile: readable,
      currentByteCount: readable ? values?.fileSize.map(Int64.init) : nil,
      modifiedAt: readable ? values?.contentModificationDate : nil,
      recordedByteCount: recorded?.size,
      recordedSHA256: recorded?.sha256
    )
  }

  func comparisonSummary(_ first: ArtifactInspection, _ second: ArtifactInspection) -> String {
    guard first.canPreview, second.canPreview else {
      return "At least one artifact is unavailable within its run folder."
    }
    guard let firstHash = first.recordedSHA256,
          let secondHash = second.recordedSHA256 else {
      return "Both recorded hashes are needed for a hash comparison. Review the bounded previews and metadata."
    }
    return firstHash.caseInsensitiveCompare(secondHash) == .orderedSame
      ? "Recorded SHA-256 values match. This does not re-verify the current files or their scientific meaning."
      : "Recorded SHA-256 values differ. Run-specific paths or timestamps may account for this; review the data before inferring a scientific change."
  }

  func role(for artifact: Artifact) -> ArtifactRole {
    if artifact.primary == true { return .primaryResult }
    let name = artifact.relativePath.lowercased()
    if artifact.artifactType == "log_txt" ||
       ["stdout.txt", "stderr.txt", "command.txt"].contains(name) {
      return .log
    }
    if ["summary.json", "manifest.json", "next_steps.md"].contains(name) ||
       artifact.artifactType.map({
         ["summary_json", "manifest_json", "metadata_json"].contains($0)
       }) == true {
      return .evidence
    }
    return .result
  }

  private func manifestOutput(for file: URL, root: URL) -> (size: Int64?, sha256: String?)? {
    let manifest = root.appendingPathComponent("manifest.json").resolvingSymlinksInPath()
    guard isInside(manifest, root: root),
          let handle = try? FileHandle(forReadingFrom: manifest) else { return nil }
    defer { try? handle.close() }
    guard let data = try? handle.read(upToCount: maximumManifestBytes + 1),
          data.count <= maximumManifestBytes,
          let document = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let outputs = document["outputs"] as? [[String: Any]] else { return nil }

    for output in outputs {
      guard let rawPath = output["path"] as? String else { continue }
      let candidate: URL
      if rawPath.hasPrefix("~/") {
        candidate = homeDirectory.appendingPathComponent(String(rawPath.dropFirst(2)))
      } else if rawPath.hasPrefix("/") {
        candidate = URL(fileURLWithPath: rawPath)
      } else {
        candidate = root.appendingPathComponent(rawPath)
      }
      let resolved = candidate.standardizedFileURL.resolvingSymlinksInPath()
      guard isInside(resolved, root: root), resolved.path == file.path else { continue }
      let size = (output["size_bytes"] as? NSNumber)?.int64Value
      let rawHash = output["sha256"] as? String
      let hash = rawHash?.count == 64 && rawHash?.allSatisfy(\.isHexDigit) == true
        ? rawHash?.lowercased() : nil
      return (size: size.flatMap { $0 >= 0 ? $0 : nil }, sha256: hash)
    }
    return nil
  }

  private func isInside(_ file: URL, root: URL) -> Bool {
    let prefix = root.path.hasSuffix("/") ? root.path : root.path + "/"
    return file.path.hasPrefix(prefix)
  }
}
