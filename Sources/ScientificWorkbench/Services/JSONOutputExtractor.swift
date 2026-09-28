import Foundation

enum JSONOutputExtractor {
  static func decodeLast<T: Decodable>(
    _ type: T.Type,
    from text: String,
    using decoder: JSONDecoder = JSONDecoder()
  ) -> T? {
    for candidate in balancedObjectCandidates(in: text).reversed() {
      guard let data = candidate.data(using: .utf8) else { continue }
      if let value = try? decoder.decode(type, from: data) {
        return value
      }
    }
    return nil
  }

  static func lastObject(
    in text: String,
    matching predicate: ([String: Any]) -> Bool = { _ in true }
  ) -> [String: Any]? {
    for candidate in balancedObjectCandidates(in: text).reversed() {
      guard
        let data = candidate.data(using: .utf8),
        let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        predicate(object)
      else {
        continue
      }
      return object
    }
    return nil
  }

  private static func balancedObjectCandidates(in text: String) -> [String] {
    outputSegments(in: text).flatMap(balancedObjectCandidatesInSegment)
  }

  private static func outputSegments(in text: String) -> [String] {
    let markerPrefix = "[Scientific Workbench truncated "
    guard
      let markerStart = text.range(of: markerPrefix),
      let markerEnd = text.range(
        of: "]\n\n",
        range: markerStart.upperBound..<text.endIndex
      )
    else {
      return [text]
    }
    return [
      String(text[..<markerStart.lowerBound]),
      String(text[markerEnd.upperBound...])
    ]
  }

  private static func balancedObjectCandidatesInSegment(_ text: String) -> [String] {
    var candidates: [(text: String, rootStart: String.Index, depth: Int)] = []
    var validRootStarts = Set<String.Index>()
    var objectStarts: [String.Index] = []
    var isInsideString = false
    var isEscaping = false

    for index in text.indices {
      let character = text[index]

      guard !objectStarts.isEmpty else {
        if character == "{" {
          objectStarts.append(index)
          isInsideString = false
          isEscaping = false
        }
        continue
      }

      if isInsideString {
        if isEscaping {
          isEscaping = false
        } else if character == "\\" {
          isEscaping = true
        } else if character == "\"" {
          isInsideString = false
        }
        continue
      }

      switch character {
      case "\"":
        isInsideString = true
      case "{":
        objectStarts.append(index)
      case "}":
        let depth = objectStarts.count
        let rootStart = objectStarts[0]
        if let start = objectStarts.popLast() {
          let candidate = String(text[start...index])
          candidates.append((candidate, rootStart, depth))
          if depth == 1, let data = candidate.data(using: .utf8),
             (try? JSONSerialization.jsonObject(with: data)) != nil {
            validRootStarts.insert(rootStart)
          }
        }
        if objectStarts.isEmpty {
          isInsideString = false
          isEscaping = false
        }
      default:
        break
      }
    }

    // Nested diagnostics are not standalone responses. Recover nested objects
    // only when a noisy log prefix left their enclosing object invalid.
    return candidates
      .filter { $0.depth == 1 || !validRootStarts.contains($0.rootStart) }
      .map(\.text)
  }
}
