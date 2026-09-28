import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  func sampleCapability() -> CapabilityEntry {
    CapabilityEntry(
      id: "profile_table",
      label: "profile_table.py",
      script: "scripts/profile_table.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Profile a table."
    )
  }

  func makeScenarioFixture(name: String, files: [String: String]) throws -> URL {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Scenario-\(name)-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    for (relativePath, contents) in files {
      let url = root.appendingPathComponent(relativePath)
      try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
      )
      try contents.write(to: url, atomically: true, encoding: .utf8)
    }
    return root
  }

  func makeSuccessfulEnvironmentSkillFixture() throws -> URL {
    try makeScenarioFixture(
      name: "successful-environment",
      files: [
        "scripts/datanalysis_env.py": """
          import json
          import sys
          from pathlib import Path

          if len(sys.argv) != 6 or sys.argv[1:4] != ["run-tool", "datanalysis_env", "status"] or sys.argv[4] != "--summary-json":
              raise SystemExit(2)

          summary = Path(sys.argv[5])
          payload = {"tool": "datanalysis_env.status", "status": "ok"}
          summary.write_text(json.dumps(payload), encoding="utf-8")
          print(json.dumps(payload))
          """
      ]
    )
  }

  func environmentCapability() -> CapabilityEntry {
    CapabilityEntry(
      id: "datanalysis_env.status",
      label: "datanalysis_env.py status",
      script: "scripts/datanalysis_env.py",
      visibleBlock: "core / routing",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Check environment."
    )
  }

  func expertFITSCapability() -> CapabilityEntry {
    CapabilityEntry(
      id: "inspect_fits",
      label: "inspect_fits.py",
      script: "scripts/inspect_fits.py",
      visibleBlock: "astronomy observational",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Inspect FITS data."
    )
  }

  func maintainerCapability() -> CapabilityEntry {
    CapabilityEntry(
      id: "portable_smoke_test",
      label: "portable_smoke_test.py",
      script: "scripts/portable_smoke_test.py",
      visibleBlock: "core / routing",
      kind: "maintainer_only",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "none",
      shortDescription: "Maintainer-only release gate."
    )
  }

  func legacyCLIOnlyCapability() -> CapabilityEntry {
    CapabilityEntry(
      id: "legacy_spectroscopy_envcheck",
      label: "legacy_spectroscopy_envcheck.py",
      script: "scripts/legacy_spectroscopy_envcheck.py",
      visibleBlock: "astronomy observational",
      kind: "compatibility",
      supportLevel: "legacy",
      platform: "macos",
      requiresDatanalysis: true,
      preflightMode: "required",
      smokeTier: "none",
      shortDescription: "Check the legacy spectroscopy environment."
    )
  }

  actor RequestRecorder {
    private var recordedRequests: [URLRequest] = []
    let statusCode: Int
    let responseBody: String

    init(responseBody: String, statusCode: Int = 200) {
      self.responseBody = responseBody
      self.statusCode = statusCode
    }

    var requests: [URLRequest] {
      recordedRequests
    }

    func load(_ request: URLRequest) async throws -> (Data, URLResponse) {
      recordedRequests.append(request)
      let response = HTTPURLResponse(
        url: request.url!,
        statusCode: statusCode,
        httpVersion: nil,
        headerFields: ["Content-Type": "application/json"]
      )!
      return (Data(responseBody.utf8), response)
    }
  }

  func jsonBody(from request: URLRequest) throws -> [String: Any] {
    let data = try #require(request.httpBody)
    let object = try JSONSerialization.jsonObject(with: data)
    return try #require(object as? [String: Any])
  }

  func canonicalJSONBody(from request: URLRequest) throws -> String {
    let data = try #require(request.httpBody)
    let object = try JSONSerialization.jsonObject(with: data)
    return try canonicalJSONString(from: object)
  }

  private func canonicalJSONString(from value: Any) throws -> String {
    if let dictionary = value as? [String: Any] {
      let fields = try dictionary.keys.sorted().map { key in
        let keyData = try JSONEncoder().encode(key)
        let keyText = try #require(String(data: keyData, encoding: .utf8))
        let valueText = try canonicalJSONString(from: dictionary[key] as Any)
        return "\(keyText):\(valueText)"
      }
      return "{\(fields.joined(separator: ","))}"
    }

    if let array = value as? [Any] {
      let values = try array.map { try canonicalJSONString(from: $0) }
      return "[\(values.joined(separator: ","))]"
    }

    if let string = value as? String {
      let data = try JSONEncoder().encode(string)
      return try #require(String(data: data, encoding: .utf8))
    }

    if let number = value as? NSNumber {
      if CFGetTypeID(number) == CFBooleanGetTypeID() {
        return number.boolValue ? "true" : "false"
      }
      let double = number.doubleValue
      if double.rounded() == double {
        return String(Int64(double))
      }
      return String(format: "%.15g", locale: Locale(identifier: "en_US_POSIX"), double)
    }

    if value is NSNull {
      return "null"
    }

    throw CocoaError(.coderInvalidValue)
  }
}
