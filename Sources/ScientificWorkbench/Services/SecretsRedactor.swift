import Foundation

enum SecretsRedactor {
  static let replacement = "[REDACTED]"

  static func applicableSecrets(_ secrets: [String]) -> [String] {
    secrets.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { $0.count >= 8 }
  }

  static func redact(_ text: String, secrets: [String]) -> String {
    applicableSecrets(secrets).reduce(text) { redacted, secret in
      redacted.replacingOccurrences(of: secret, with: replacement)
    }
  }
}
