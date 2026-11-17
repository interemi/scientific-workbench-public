import Foundation

struct ScientificMeasurementSummary: Sendable {
  struct Quantity: Decodable, Sendable {
    let label: String
    let value: Double
    let unit: String
    let uncertainty: Double?
  }

  struct Quality: Decodable, Sendable {
    let status: String
    let findings: [String]

    private struct Finding: Decodable {
      let message: String
    }

    private enum CodingKeys: String, CodingKey {
      case status, findings
    }

    init(from decoder: any Decoder) throws {
      let values = try decoder.container(keyedBy: CodingKeys.self)
      status = try values.decode(String.self, forKey: .status)
      if let text = try? values.decode([String].self, forKey: .findings) {
        findings = text
      } else {
        findings = try values.decode([Finding].self, forKey: .findings).map(\.message)
      }
    }
  }

  private struct Details: Decodable {
    let method: String
    let measurements: [Quantity]
    let diagnostics: [Quantity]
    let assumptions: [String]
  }

  private struct Envelope: Decodable {
    struct Results: Decodable {
      let measurementSummary: Details
    }

    let tool: String
    let results: Results
    let qa: Quality
  }

  let method: String
  let measurements: [Quantity]
  let diagnostics: [Quantity]
  let assumptions: [String]
  let quality: Quality

  static func supports(_ capabilityID: String) -> Bool {
    ["photometric_solution", "li6708_equivalent_width_workbench.measure", "sb2_double_gaussian_workbench.fit"]
      .contains(capabilityID)
  }

  static func load(from url: URL, capabilityID: String) -> Self? {
    let maximumBytes = 1_000_000
    guard supports(capabilityID), let handle = try? FileHandle(forReadingFrom: url) else { return nil }
    defer { try? handle.close() }
    guard let data = try? handle.read(upToCount: maximumBytes + 1),
          data.count <= maximumBytes else { return nil }
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    guard let envelope = try? decoder.decode(Envelope.self, from: data),
          envelope.tool == capabilityID else { return nil }
    let details = envelope.results.measurementSummary
    guard (details.measurements + details.diagnostics).allSatisfy({
      $0.value.isFinite && !$0.unit.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        && ($0.uncertainty.map { $0.isFinite && $0 >= 0 } ?? true)
    }) else { return nil }
    return Self(method: details.method, measurements: details.measurements,
                diagnostics: details.diagnostics, assumptions: details.assumptions, quality: envelope.qa)
  }
}
