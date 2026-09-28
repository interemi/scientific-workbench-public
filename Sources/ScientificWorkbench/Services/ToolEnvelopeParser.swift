import Foundation

struct ToolEnvelope: Equatable, Sendable {
  let tool: String?
  let status: String?
  let contractVersion: String?
  let appStatus: String?
  let command: ToolEnvelopeCommand?
  let inputs: [ToolEnvelopeIORecord]
  let outputs: [ToolEnvelopeIORecord]
  let typedArtifacts: [ToolEnvelopeArtifact]
  let warnings: [String]
  let errors: [ToolEnvelopeError]
  let nextActions: [ToolEnvelopeNextAction]
  let originalModified: String?
  let appHints: ToolEnvelopeAppHints?
}

struct ToolEnvelopeCommand: Equatable, Sendable {
  let argv: [String]
  let cwd: String?
  let redacted: Bool?
}

struct ToolEnvelopeIORecord: Equatable, Sendable {
  let path: String?
  let role: String?
  let kind: String?
  let artifactType: String?
  let exists: Bool?
}

struct ToolEnvelopeArtifact: Equatable, Sendable {
  let path: String?
  let artifactType: String?
  let label: String?
  let primary: Bool?
}

struct ToolEnvelopeError: Equatable, Sendable {
  let kind: String?
  let message: String?
  let recoveryHint: String?
}

struct ToolEnvelopeNextAction: Equatable, Sendable {
  let label: String?
  let kind: String?
  let priority: String?
}

struct ToolEnvelopeAppHints: Equatable, Sendable {
  let shortSummary: String?
  let severity: String?
  let previewArtifactTypes: [String]
  let tags: [String]
}

struct ToolEnvelopeParser {
  func parse(_ text: String) -> ToolEnvelope? {
    guard let payload = lastEnvelopePayload(in: text) else { return nil }
    return ToolEnvelope(
      tool: payload["tool"] as? String,
      status: payload["status"] as? String,
      contractVersion: payload["contract_version"] as? String,
      appStatus: payload["app_status"] as? String,
      command: parseCommand(payload["command"]),
      inputs: parseIORecords(payload["inputs"]),
      outputs: parseIORecords(payload["outputs"]),
      typedArtifacts: parseArtifacts(payload["typed_artifacts"]),
      warnings: parseWarnings(payload["warnings"]),
      errors: parseErrors(payload["errors"]),
      nextActions: parseNextActions(payload["next_actions"]),
      originalModified: parseOriginalModified(payload["original_modified"]),
      appHints: parseAppHints(payload["app_hints"])
    )
  }

  private func lastEnvelopePayload(in text: String) -> [String: Any]? {
    JSONOutputExtractor.lastObject(in: text, matching: looksLikeEnvelope)
  }

  private func looksLikeEnvelope(_ payload: [String: Any]) -> Bool {
    let recognizedStatuses: Set<String> = [
      "OK", "PASS", "SUCCESS", "SUCCEEDED", "READY", "WARNING", "WARN", "SKIP", "SKIPPED",
      "BLOCKED", "BLOCKED_CONTROLADO", "FAIL", "FAILED", "ERROR", "ROTO",
    ]
    let statuses = [payload["status"], payload["app_status"]]
      .compactMap { ($0 as? String)?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased() }
    guard statuses.contains(where: recognizedStatuses.contains) else { return false }
    return [payload["tool"], payload["contract_version"]].contains {
      guard let value = $0 as? String else { return false }
      return !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
  }

  private func parseCommand(_ value: Any?) -> ToolEnvelopeCommand? {
    guard let object = value as? [String: Any] else { return nil }
    return ToolEnvelopeCommand(
      argv: object["argv"] as? [String] ?? [],
      cwd: object["cwd"] as? String,
      redacted: object["redacted"] as? Bool
    )
  }

  private func parseIORecords(_ value: Any?) -> [ToolEnvelopeIORecord] {
    guard let items = value as? [[String: Any]] else { return [] }
    return items.map {
      ToolEnvelopeIORecord(
        path: $0["path"] as? String,
        role: $0["role"] as? String,
        kind: $0["kind"] as? String,
        artifactType: $0["artifact_type"] as? String,
        exists: $0["exists"] as? Bool
      )
    }
  }

  private func parseArtifacts(_ value: Any?) -> [ToolEnvelopeArtifact] {
    guard let items = value as? [[String: Any]] else { return [] }
    return items.map {
      ToolEnvelopeArtifact(
        path: $0["path"] as? String,
        artifactType: $0["artifact_type"] as? String,
        label: $0["label"] as? String,
        primary: $0["primary"] as? Bool
      )
    }
  }

  private func parseErrors(_ value: Any?) -> [ToolEnvelopeError] {
    guard let items = value as? [[String: Any]] else { return [] }
    return items.map {
      ToolEnvelopeError(
        kind: $0["kind"] as? String,
        message: $0["message"] as? String,
        recoveryHint: $0["recovery_hint"] as? String
      )
    }
  }

  private func parseWarnings(_ value: Any?) -> [String] {
    guard let items = value as? [Any] else { return [] }
    return items.compactMap { item in
      if let text = item as? String {
        return text
      }
      if let object = item as? [String: Any] {
        return object["message"] as? String
          ?? object["detail"] as? String
          ?? object["warning"] as? String
      }
      return nil
    }
  }

  private func parseNextActions(_ value: Any?) -> [ToolEnvelopeNextAction] {
    guard let items = value as? [[String: Any]] else { return [] }
    return items.map {
      ToolEnvelopeNextAction(
        label: $0["label"] as? String,
        kind: $0["kind"] as? String,
        priority: $0["priority"] as? String
      )
    }
  }

  private func parseOriginalModified(_ value: Any?) -> String? {
    if let bool = value as? Bool {
      return bool ? "true" : "false"
    }
    return value as? String
  }

  private func parseAppHints(_ value: Any?) -> ToolEnvelopeAppHints? {
    guard let object = value as? [String: Any] else { return nil }
    return ToolEnvelopeAppHints(
      shortSummary: object["short_summary"] as? String,
      severity: object["severity"] as? String,
      previewArtifactTypes: object["preview_artifact_types"] as? [String] ?? [],
      tags: object["tags"] as? [String] ?? []
    )
  }
}
