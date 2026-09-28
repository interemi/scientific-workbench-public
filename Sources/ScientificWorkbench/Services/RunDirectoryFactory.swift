import Foundation

struct RunDirectoryFactory {
  var date: () -> Date = Date.init
  var nonce: () -> String = { UUID().uuidString.lowercased() }

  func makePath(root: String, capabilityID: String) -> String {
    let cleanID = sanitizedComponent(capabilityID)
    let uniqueSuffix = sanitizedComponent(nonce())
    let folderName = [
      DateFormatters.runFolder.string(from: date()),
      cleanID,
      uniqueSuffix,
    ].joined(separator: "_")
    return URL(fileURLWithPath: root, isDirectory: true)
      .appendingPathComponent(folderName, isDirectory: true)
      .path
  }

  private func sanitizedComponent(_ value: String) -> String {
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
    let scalars = value.unicodeScalars.map { allowed.contains($0) ? Character(String($0)) : "_" }
    let result = String(scalars)
      .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
    return result.isEmpty ? "run" : result
  }
}
