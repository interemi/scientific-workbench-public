import Foundation

struct ArtifactDiscovery {
  func discover(in directory: String) -> [Artifact] {
    let rootURL = URL(fileURLWithPath: directory).resolvingSymlinksInPath()
    let typedMetadata = loadTypedArtifactMetadata(from: rootURL)
    guard let enumerator = FileManager.default.enumerator(
      at: rootURL,
      includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey],
      options: [.skipsHiddenFiles]
    ) else {
      return []
    }

    var artifacts: [Artifact] = []
    for case let fileURL as URL in enumerator {
      let values = try? fileURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
      guard values?.isRegularFile == true else { continue }
      let resolvedFileURL = fileURL.resolvingSymlinksInPath()
      let relativePath = relativePath(for: resolvedFileURL, under: rootURL)
      let metadata = typedMetadata[relativePath]
      let declaredType = metadata?.artifactType?.trimmingCharacters(in: .whitespacesAndNewlines)
      artifacts.append(Artifact(
        path: resolvedFileURL.path,
        relativePath: relativePath,
        byteCount: Int64(values?.fileSize ?? 0),
        artifactType: declaredType == nil || declaredType == "" || declaredType == "unknown"
          ? inferredArtifactType(for: relativePath)
          : declaredType,
        label: metadata?.label,
        primary: metadata?.primary
      ))
    }
    return artifacts.sorted { $0.relativePath.localizedStandardCompare($1.relativePath) == .orderedAscending }
  }

  private struct TypedArtifactMetadata {
    let artifactType: String?
    let label: String?
    let primary: Bool?
  }

  private func loadTypedArtifactMetadata(from rootURL: URL) -> [String: TypedArtifactMetadata] {
    var metadata: [String: TypedArtifactMetadata] = [:]
    var documents: [[String: Any]] = []
    for fileName in ["summary.json", "manifest.json"] {
      let url = rootURL.appendingPathComponent(fileName)
      guard
        let data = try? Data(contentsOf: url),
        let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
      else {
        continue
      }
      documents.append(object)
    }
    // Typed declarations take precedence over file inventories in either document.
    for key in ["outputs", "artifacts", "typed_artifacts"] {
      for document in documents {
        mergeTypedArtifacts(from: document[key], rootURL: rootURL, into: &metadata)
      }
    }
    return metadata
  }

  private func mergeTypedArtifacts(
    from value: Any?,
    rootURL: URL,
    into metadata: inout [String: TypedArtifactMetadata]
  ) {
    guard let items = value as? [[String: Any]] else { return }
    for item in items {
      guard let rawPath = item["path"] as? String, !rawPath.isEmpty else { continue }
      let relative = normalizedRelativeArtifactPath(rawPath, rootURL: rootURL)
      guard !relative.isEmpty else { continue }
      let existing = metadata[relative]
      metadata[relative] = TypedArtifactMetadata(
        artifactType: item["artifact_type"] as? String ?? existing?.artifactType,
        label: item["label"] as? String ?? existing?.label,
        primary: item["primary"] as? Bool ?? existing?.primary
      )
    }
  }

  private func normalizedRelativeArtifactPath(_ path: String, rootURL: URL) -> String {
    let expanded = (path as NSString).expandingTildeInPath
    if expanded.hasPrefix("/") {
      return relativePath(for: URL(fileURLWithPath: expanded).resolvingSymlinksInPath(), under: rootURL)
    }
    return path.hasPrefix("./") ? String(path.dropFirst(2)) : path
  }

  private func relativePath(for fileURL: URL, under rootURL: URL) -> String {
    let rootPath = rootURL.path.hasSuffix("/") ? rootURL.path : rootURL.path + "/"
    let filePath = fileURL.path
    guard filePath.hasPrefix(rootPath) else {
      return fileURL.lastPathComponent
    }
    return String(filePath.dropFirst(rootPath.count))
  }

  private func inferredArtifactType(for relativePath: String) -> String {
    let normalized = relativePath.lowercased()
    switch normalized {
    case "summary.json":
      return "summary_json"
    case "manifest.json":
      return "manifest_json"
    case "stdout.txt", "stderr.txt", "command.txt":
      return "log_txt"
    case "next_steps.md":
      return "report_md"
    default:
      break
    }

    switch URL(fileURLWithPath: normalized).pathExtension {
    case "png", "jpg", "jpeg", "tif", "tiff":
      return "preview_png"
    case "pdf":
      return "preview_pdf"
    case "csv", "tsv":
      return "table_csv"
    case "ecsv":
      return "table_ecsv"
    case "ipynb":
      return "notebook_ipynb"
    case "fit", "fits", "fts":
      return "fits_product"
    case "md":
      return "report_md"
    case "txt", "log":
      return "log_txt"
    case "json":
      return "metadata_json"
    default:
      return "unknown"
    }
  }
}
