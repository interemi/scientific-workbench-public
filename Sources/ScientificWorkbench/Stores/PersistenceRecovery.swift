import Foundation
import CoreFoundation

enum PersistenceStoreError: LocalizedError, Equatable {
  case invalidDocument(String)
  case missingCollection(String)
  case unsupportedVersion(kind: String, version: Int)
  case oversizedFile(String)
  case unsafeFileType(String)
  case recoveryWriteNotApproved(String)

  var errorDescription: String? {
    switch self {
    case .invalidDocument(let name):
      return "The persisted \(name) is not a readable JSON object."
    case .missingCollection(let name):
      return "The persisted \(name) does not contain its required record collection."
    case .unsupportedVersion(let kind, let version):
      return "The persisted \(kind) uses unsupported schema version \(version). It was left unchanged."
    case .oversizedFile(let path):
      return "The persisted state is larger than the 128 MiB recovery limit and was left unchanged: \(path)"
    case .unsafeFileType(let path):
      return "The persisted state must be a regular file and cannot be a symbolic link: \(path)"
    case .recoveryWriteNotApproved(let path):
      return "Persisted state was read but cannot be migrated until the output root is approved: \(path)"
    }
  }

  var canRecoverByArchiving: Bool {
    switch self {
    case .invalidDocument, .missingCollection:
      return true
    case .unsupportedVersion, .oversizedFile, .unsafeFileType, .recoveryWriteNotApproved:
      return false
    }
  }
}

struct PersistenceLoadDiagnostics: Equatable, Sendable {
  let kind: String
  let sourceVersion: Int
  let currentVersion: Int
  var recoveredItemCount: Int
  var discardedItemCount: Int
  var duplicateIdentifierCount: Int
  var normalizedInterruptedCount: Int
  var messages: [String]

  var requiresRewrite: Bool {
    sourceVersion != currentVersion
      || discardedItemCount > 0
      || duplicateIdentifierCount > 0
      || normalizedInterruptedCount > 0
  }

  var summary: String {
    var parts: [String] = []
    if sourceVersion != currentVersion {
      parts.append("migrated schema \(sourceVersion) to \(currentVersion)")
    }
    if recoveredItemCount > 0 {
      parts.append("recovered \(recoveredItemCount) record(s)")
    }
    if discardedItemCount > 0 {
      parts.append("discarded \(discardedItemCount) invalid record(s)")
    }
    if duplicateIdentifierCount > 0 {
      parts.append("resolved \(duplicateIdentifierCount) duplicate identifier(s)")
    }
    if normalizedInterruptedCount > 0 {
      parts.append("marked \(normalizedInterruptedCount) interrupted record(s) as cancelled")
    }
    return parts.isEmpty ? "no recovery changes" : parts.joined(separator: ", ")
  }
}

enum PersistenceFileAccess {
  private static let maximumBytes: Int64 = 128 * 1_024 * 1_024

  static func readData(from url: URL) throws -> Data? {
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory) else {
      return nil
    }
    guard !isDirectory.boolValue else {
      throw PersistenceStoreError.unsafeFileType(url.path)
    }
    let values = try url.resourceValues(forKeys: [
      .isRegularFileKey,
      .isSymbolicLinkKey,
      .fileSizeKey,
    ])
    guard values.isSymbolicLink != true, values.isRegularFile == true else {
      throw PersistenceStoreError.unsafeFileType(url.path)
    }
    if let fileSize = values.fileSize, Int64(fileSize) > maximumBytes {
      throw PersistenceStoreError.oversizedFile(url.path)
    }
    return try Data(contentsOf: url, options: [.mappedIfSafe])
  }

  static func validateWriteTarget(_ url: URL) throws {
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory) else {
      return
    }
    guard !isDirectory.boolValue else {
      throw PersistenceStoreError.unsafeFileType(url.path)
    }
    let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
    guard values.isSymbolicLink != true, values.isRegularFile == true else {
      throw PersistenceStoreError.unsafeFileType(url.path)
    }
  }

  static func jsonObject(from data: Data, kind: String) throws -> [String: Any] {
    guard let object = try? JSONSerialization.jsonObject(with: data),
          let dictionary = object as? [String: Any] else {
      throw PersistenceStoreError.invalidDocument(kind)
    }
    return dictionary
  }

  static func schemaVersion(
    in object: [String: Any],
    kind: String,
    currentVersion: Int
  ) throws -> Int {
    guard let number = object["version"] as? NSNumber,
          CFGetTypeID(number) != CFBooleanGetTypeID() else {
      throw PersistenceStoreError.invalidDocument(kind)
    }
    let version = number.intValue
    guard number.doubleValue == Double(version), (1...currentVersion).contains(version) else {
      throw PersistenceStoreError.unsupportedVersion(kind: kind, version: version)
    }
    return version
  }

  static func decode<T: Decodable>(_ type: T.Type, from object: Any) throws -> T {
    let data = try JSONSerialization.data(withJSONObject: object)
    return try JSONDecoder.scientificWorkbench.decode(type, from: data)
  }
}

struct PersistenceRecoveryArchive {
  func preserveOriginal(at sourceURL: URL, reason: String) throws -> URL {
    _ = try PersistenceFileAccess.readData(from: sourceURL)
    let directory = sourceURL.deletingLastPathComponent()
      .appendingPathComponent("recovery", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyyMMdd'T'HHmmssSSS'Z'"
    let timestamp = formatter.string(from: Date())
    let safeReason = reason
      .lowercased()
      .map { $0.isLetter || $0.isNumber ? String($0) : "-" }
      .joined()
      .replacingOccurrences(of: "--", with: "-")
    let stem = sourceURL.deletingPathExtension().lastPathComponent
    let suffix = String(UUID().uuidString.prefix(8)).lowercased()
    let archiveURL = directory.appendingPathComponent(
      "\(stem).\(safeReason).\(timestamp).\(suffix).json"
    )
    try FileManager.default.copyItem(at: sourceURL, to: archiveURL)
    return archiveURL
  }
}
