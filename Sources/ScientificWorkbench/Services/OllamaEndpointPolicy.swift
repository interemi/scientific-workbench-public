import Foundation

enum OllamaEndpointPolicyError: Error, Equatable, Sendable {
  case invalidBaseURL(String)
  case unsafeEndpoint(String)
}

enum OllamaEndpointPolicy {
  static func apiURL(baseURL: String?, endpoint: String) throws -> URL {
    let raw = (baseURL?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false)
      ? baseURL!
      : "http://localhost:11434"
    guard var components = URLComponents(string: raw),
          let scheme = components.scheme?.lowercased() else {
      throw OllamaEndpointPolicyError.invalidBaseURL(raw)
    }
    let host = components.host ?? ""
    guard ["http", "https"].contains(scheme),
          components.user == nil,
          components.password == nil,
          isExplicitLoopbackHost(host) else {
      throw OllamaEndpointPolicyError.unsafeEndpoint(raw)
    }

    var path = components.percentEncodedPath
    while path.count > 1, path.hasSuffix("/") {
      path.removeLast()
    }
    let knownEndpoints = ["chat", "tags"]
    if path.isEmpty || path == "/" {
      path = "/api/\(endpoint)"
    } else if knownEndpoints.contains(where: { path.hasSuffix("/api/\($0)") }) {
      path = String(path.dropLast(path.split(separator: "/").last?.count ?? 0)) + endpoint
    } else if path.hasSuffix("/api") {
      path += "/\(endpoint)"
    } else {
      path += "/api/\(endpoint)"
    }
    components.percentEncodedPath = path
    components.query = nil
    components.fragment = nil

    guard let url = components.url else {
      throw OllamaEndpointPolicyError.invalidBaseURL(raw)
    }
    return url
  }

  private static func isExplicitLoopbackHost(_ rawHost: String) -> Bool {
    let lower = rawHost.lowercased()
    let host = lower.hasPrefix("[") && lower.hasSuffix("]")
      ? String(lower.dropFirst().dropLast())
      : lower
    if host == "localhost" || host == "::1" {
      return true
    }

    let octets = host.split(separator: ".", omittingEmptySubsequences: false)
    guard octets.count == 4 else { return false }
    let values = octets.compactMap { octet -> Int? in
      guard !octet.isEmpty,
            octet.utf8.allSatisfy({ (48...57).contains($0) }),
            let value = Int(octet),
            (0...255).contains(value),
            String(value) == octet else {
        return nil
      }
      return value
    }
    return values.count == 4 && values[0] == 127
  }
}
