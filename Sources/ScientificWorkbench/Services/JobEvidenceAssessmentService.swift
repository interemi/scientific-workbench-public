import CryptoKit
import Foundation

enum EvidenceLevel: String, Sendable {
  case pass
  case warning
  case blocked
  case fail
  case incomplete
  case pending
}

struct EvidenceStage: Sendable {
  let title: String
  let level: EvidenceLevel
  let detail: String
}

struct JobEvidenceAssessment: Sendable {
  let stages: [EvidenceStage]
}

/// Reads retained run evidence without changing the persisted job or its artifacts.
struct JobEvidenceAssessmentService: Sendable {
  private let maximumSidecarBytes = 1_000_000
  private let maximumVerifiedOutputBytes: Int64 = 64 * 1_024 * 1_024

  func assess(job: JobRecord) -> JobEvidenceAssessment {
    let root = URL(fileURLWithPath: job.runDirectory, isDirectory: true)
      .standardizedFileURL.resolvingSymlinksInPath()
    let summary = readJSON(root.appendingPathComponent("summary.json"), under: root)
    let manifest = readJSON(root.appendingPathComponent("manifest.json"), under: root)

    return JobEvidenceAssessment(stages: [
      processStage(job),
      toolStage(job, summary: summary),
      artifactStage(job, root: root, summary: summary, manifest: manifest),
      qaStage(job, summary: summary),
      EvidenceStage(
        title: "Human scientific review",
        level: .incomplete,
        detail: "Not recorded by automatic checks. Review methods, units, uncertainties, and limits before using the result scientifically."
      )
    ])
  }

  private func processStage(_ job: JobRecord) -> EvidenceStage {
    switch job.status {
    case .queued, .running:
      return EvidenceStage(title: "Process", level: .pending, detail: "The process has not finished.")
    default:
      break
    }
    guard let exitCode = job.exitCode else {
      return EvidenceStage(title: "Process", level: .incomplete, detail: "No process exit code was retained.")
    }
    return EvidenceStage(
      title: "Process",
      level: exitCode == 0 ? .pass : .fail,
      detail: "Process exited with code \(exitCode). This does not establish artifact or scientific validity."
    )
  }

  private func toolStage(_ job: JobRecord, summary: [String: Any]?) -> EvidenceStage {
    if job.status == .queued || job.status == .running {
      return EvidenceStage(title: "Tool outcome", level: .pending, detail: "Waiting for the tool contract.")
    }
    let statuses = [job.appStatus, job.parsedStatus, summary?["app_status"] as? String,
                    summary?["status"] as? String]
      .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
    let level: EvidenceLevel
    if statuses.contains(where: { ["FAIL", "FAILED", "ERROR", "ROTO"].contains($0) }) {
      level = .fail
    } else if statuses.contains(where: { ["BLOCKED", "BLOCKED_CONTROLADO"].contains($0) }) {
      level = .blocked
    } else if statuses.contains(where: { ["WARNING", "WARN"].contains($0) }) {
      level = .warning
    } else if statuses.contains(where: { ["PASS", "OK", "SUCCESS"].contains($0) }) {
      level = .pass
    } else {
      level = .incomplete
    }
    let detail: String
    switch level {
    case .pass: detail = "The tool reports success; check artifacts and QA separately."
    case .warning: detail = "The tool reports a warning; inspect the retained findings."
    case .blocked: detail = "The tool reports a controlled block; no scientific output is approved."
    case .fail: detail = "The tool reports failure, regardless of process exit code."
    case .incomplete: detail = "No recognized tool outcome was retained."
    case .pending: detail = "Waiting for the tool contract."
    }
    return EvidenceStage(title: "Tool outcome", level: level, detail: detail)
  }

  private func artifactStage(
    _ job: JobRecord,
    root: URL,
    summary: [String: Any]?,
    manifest: [String: Any]?
  ) -> EvidenceStage {
    let title = "Artifact contract"
    if job.status == .queued || job.status == .running {
      return EvidenceStage(title: title, level: .pending, detail: "Waiting for run artifacts.")
    }
    guard summary != nil, let manifest,
          let outputs = manifest["outputs"] as? [[String: Any]], !outputs.isEmpty else {
      return EvidenceStage(title: title, level: .incomplete,
                           detail: "A readable summary and manifest with declared outputs are required.")
    }

    var verifiedBytes: Int64 = 0
    for output in outputs {
      guard let rawPath = output["path"] as? String,
            let url = outputURL(rawPath, under: root) else {
        return EvidenceStage(title: title, level: .incomplete,
                             detail: "A declared output has no safe path inside the run folder.")
      }
      guard output["exists"] as? Bool == true,
            let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey]),
            values.isRegularFile == true,
            let fileSize = values.fileSize else {
        return EvidenceStage(title: title, level: .fail,
                             detail: "A declared output is missing or is not a regular file.")
      }
      guard let recordedSize = output["size_bytes"] as? NSNumber,
            recordedSize.int64Value >= 0 else {
        return EvidenceStage(title: title, level: .incomplete,
                             detail: "A declared output has no usable size in the manifest.")
      }
      if recordedSize.int64Value != Int64(fileSize) {
        return EvidenceStage(title: title, level: .fail,
                             detail: "A declared output size differs from the manifest.")
      }
      guard let expectedHash = output["sha256"] as? String,
            expectedHash.count == 64,
            expectedHash.allSatisfy({ $0.isHexDigit }) else {
        return EvidenceStage(title: title, level: .incomplete,
                             detail: "A declared output has no usable SHA-256 in the manifest.")
      }
      guard fileSize <= maximumVerifiedOutputBytes - verifiedBytes else {
        return EvidenceStage(title: title, level: .incomplete,
                             detail: "Outputs exceed the 64 MiB on-demand verification limit; inspect the retained manifest separately.")
      }
      verifiedBytes += Int64(fileSize)
      guard let (actualHash, bytesRead) = try? sha256(url, maximumBytes: Int64(fileSize)),
            bytesRead == Int64(fileSize) else {
        return EvidenceStage(title: title, level: .incomplete,
                             detail: "A declared output could not be read within its recorded size for SHA-256 verification.")
      }
      guard actualHash.caseInsensitiveCompare(expectedHash) == .orderedSame else {
        return EvidenceStage(title: title, level: .fail,
                             detail: "A declared output SHA-256 differs from the manifest.")
      }
    }
    return EvidenceStage(title: title, level: .pass,
                         detail: "\(outputs.count) declared output(s) are present and match their recorded sizes and SHA-256 hashes.")
  }

  private func qaStage(_ job: JobRecord, summary: [String: Any]?) -> EvidenceStage {
    let title = "Automatic QA"
    if job.status == .queued || job.status == .running {
      return EvidenceStage(title: title, level: .pending, detail: "Waiting for QA evidence.")
    }
    guard let qa = summary?["qa"] as? [String: Any],
          let rawStatus = qa["status"] as? String,
          let findings = qa["findings"] as? [Any] else {
      return EvidenceStage(title: title, level: .incomplete,
                           detail: "No complete automatic QA status and findings were retained.")
    }
    let normalized = rawStatus.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    let level: EvidenceLevel
    switch normalized {
    case "OK", "PASS", "SUCCESS": level = findings.isEmpty ? .pass : .warning
    case "WARNING", "WARN": level = .warning
    case "BLOCKED", "BLOCKED_CONTROLADO": level = .blocked
    case "FAIL", "FAILED", "ERROR", "ROTO": level = .fail
    default: level = .incomplete
    }
    let detail = level == .incomplete
      ? "The retained QA status is not recognized."
      : "The retained QA reports \(level.rawValue); \(findings.count) finding(s). Review its method and scope."
    return EvidenceStage(title: title, level: level, detail: detail)
  }

  private func readJSON(_ url: URL, under root: URL) -> [String: Any]? {
    let resolved = url.resolvingSymlinksInPath()
    guard isInside(resolved, root: root),
          let values = try? resolved.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey]),
          values.isRegularFile == true,
          let fileSize = values.fileSize,
          fileSize <= maximumSidecarBytes,
          let data = try? readBounded(resolved, maximumBytes: maximumSidecarBytes),
          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      return nil
    }
    return object
  }

  private func outputURL(_ rawPath: String, under root: URL) -> URL? {
    guard !rawPath.isEmpty else { return nil }
    let expanded = (rawPath as NSString).expandingTildeInPath
    let candidate = expanded.hasPrefix("/")
      ? URL(fileURLWithPath: expanded)
      : root.appendingPathComponent(expanded)
    let resolved = candidate.standardizedFileURL.resolvingSymlinksInPath()
    return isInside(resolved, root: root) ? resolved : nil
  }

  private func isInside(_ url: URL, root: URL) -> Bool {
    url.path.hasPrefix(root.path + "/")
  }

  private func readBounded(_ url: URL, maximumBytes: Int) throws -> Data? {
    let file = try FileHandle(forReadingFrom: url)
    defer { try? file.close() }
    guard let data = try file.read(upToCount: maximumBytes + 1),
          data.count <= maximumBytes else { return nil }
    return data
  }

  private func sha256(_ url: URL, maximumBytes: Int64) throws -> (String, Int64)? {
    let file = try FileHandle(forReadingFrom: url)
    defer { try? file.close() }
    var hasher = SHA256()
    var bytesRead: Int64 = 0
    while let chunk = try file.read(upToCount: 65_536), !chunk.isEmpty {
      guard Int64(chunk.count) <= maximumBytes - bytesRead else { return nil }
      hasher.update(data: chunk)
      bytesRead += Int64(chunk.count)
    }
    return (hasher.finalize().map { String(format: "%02x", $0) }.joined(), bytesRead)
  }
}
