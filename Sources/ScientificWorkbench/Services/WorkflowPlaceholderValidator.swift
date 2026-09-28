import Foundation

enum WorkflowPlaceholderValidator {
  private static let pattern = #"\{(?:outputRoot|runDirectory|artifactsDir|summaryJson|manifestJson|previousRunDirectory|previousArtifactsDir|previousSummaryJson|previousManifestJson|input\d+)(?::[^{}]+)?\}"#
  private static let expression = try? NSRegularExpression(pattern: pattern)
  private static let namedDependencyPattern = #"\{(?:runDirectory|artifactsDir|summaryJson|manifestJson):([^{}]+)\}"#
  private static let namedDependencyExpression = try? NSRegularExpression(
    pattern: namedDependencyPattern
  )

  static func unresolvedTokens(in arguments: String) -> [String] {
    guard let expression else { return [] }
    let range = NSRange(arguments.startIndex..<arguments.endIndex, in: arguments)
    return expression.matches(in: arguments, range: range).compactMap { match in
      guard let tokenRange = Range(match.range, in: arguments) else { return nil }
      return String(arguments[tokenRange])
    }
  }

  static func referencedRunDirectories(
    in arguments: String,
    completedRunDirectories: [String: String]
  ) -> [String] {
    guard let namedDependencyExpression else { return [] }
    let range = NSRange(arguments.startIndex..<arguments.endIndex, in: arguments)
    var seenDirectories: Set<String> = []
    var directories: [String] = []

    for match in namedDependencyExpression.matches(in: arguments, range: range) {
      guard match.numberOfRanges > 1,
            let identifierRange = Range(match.range(at: 1), in: arguments) else {
        continue
      }
      let identifier = String(arguments[identifierRange])
      guard let runDirectory = completedRunDirectories[identifier],
            seenDirectories.insert(runDirectory).inserted else {
        continue
      }
      directories.append(runDirectory)
    }
    return directories
  }
}
