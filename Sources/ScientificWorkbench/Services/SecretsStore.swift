import Foundation
import LocalAuthentication
import Security

enum CredentialWriteResult: Equatable {
  case success
  case failure(OSStatus)
}

@MainActor
protocol CloudCredentialStoring {
  func readKey(for provider: AIProvider) -> String
  func saveKey(_ key: String, for provider: AIProvider) -> CredentialWriteResult
}

@MainActor
struct KeychainCredentialStore: CloudCredentialStoring {
  private let service: String

  init(service: String = SecretsStore.defaultService) {
    self.service = service
  }

  func readKey(for provider: AIProvider) -> String {
    switch provider {
    case .ollama: return ""
    case .openAI: return SecretsStore.readOpenAIKey(service: service)
    case .grok: return SecretsStore.readGrokKey(service: service)
    case .gemini: return SecretsStore.readGeminiKey(service: service)
    }
  }

  func saveKey(_ key: String, for provider: AIProvider) -> CredentialWriteResult {
    switch provider {
    case .ollama: return .success
    case .openAI: return SecretsStore.saveOpenAIKey(key, service: service)
    case .grok: return SecretsStore.saveGrokKey(key, service: service)
    case .gemini: return SecretsStore.saveGeminiKey(key, service: service)
    }
  }
}

enum SecretsStore {
  static let defaultService = "com.emilio.scientific-workbench"
  private static let openAIAccount = "OPENAI_API_KEY"
  private static let grokAccount = "XAI_API_KEY"
  private static let geminiAccount = "GEMINI_API_KEY"

  static func readOpenAIKey(service: String = defaultService) -> String {
    readKey(account: openAIAccount, service: service)
  }

  static func saveOpenAIKey(_ key: String, service: String = defaultService) -> CredentialWriteResult {
    saveKey(key, account: openAIAccount, service: service)
  }

  static func readGrokKey(service: String = defaultService) -> String {
    readKey(account: grokAccount, service: service)
  }

  static func saveGrokKey(_ key: String, service: String = defaultService) -> CredentialWriteResult {
    saveKey(key, account: grokAccount, service: service)
  }

  static func readGeminiKey(service: String = defaultService) -> String {
    readKey(account: geminiAccount, service: service)
  }

  static func saveGeminiKey(_ key: String, service: String = defaultService) -> CredentialWriteResult {
    saveKey(key, account: geminiAccount, service: service)
  }

  private static func readKey(account: String, service: String) -> String {
    let context = LAContext()
    context.interactionNotAllowed = true
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
      kSecUseAuthenticationContext as String: context,
      kSecUseAuthenticationUI as String: kSecUseAuthenticationUISkip
    ]

    var result: AnyObject?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let data = result as? Data else { return "" }
    return String(data: data, encoding: .utf8) ?? ""
  }

  private static func saveKey(_ key: String, account: String, service: String) -> CredentialWriteResult {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account
    ]

    let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty {
      let status = SecItemDelete(query as CFDictionary)
      return status == errSecSuccess || status == errSecItemNotFound ? .success : .failure(status)
    }

    let data = Data(trimmed.utf8)
    let update: [String: Any] = [kSecValueData as String: data]
    let updateStatus = SecItemUpdate(query as CFDictionary, update as CFDictionary)
    if updateStatus == errSecSuccess { return .success }
    guard updateStatus == errSecItemNotFound else { return .failure(updateStatus) }

    let addQuery: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
      kSecValueData as String: data
    ]
    let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
    if addStatus == errSecSuccess { return .success }
    if addStatus == errSecDuplicateItem {
      let retryStatus = SecItemUpdate(query as CFDictionary, update as CFDictionary)
      return retryStatus == errSecSuccess ? .success : .failure(retryStatus)
    }
    return .failure(addStatus)
  }
}
