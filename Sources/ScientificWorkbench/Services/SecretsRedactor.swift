import Foundation

enum SecretsRedactor {
  static func redact(_ text: String, secrets: [String]) -> String {
    var redacted = text
    for secret in secrets {
      let trimmed = secret.trimmingCharacters(in: .whitespacesAndNewlines)
      guard trimmed.count >= 8 else { continue }
        redacted = redacted.replacingOccurrences(of: trimmed, with: "[REDACTED]")
    }
    return redacted
  }
}
