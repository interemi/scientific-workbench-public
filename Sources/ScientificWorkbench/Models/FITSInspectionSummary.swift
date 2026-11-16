import Foundation

struct FITSInspectionSummary: Decodable, Sendable {
  let hdus: [HDU]
  let preview: Preview?
  let previewExtension: Int?

  struct HDU: Decodable, Identifiable, Sendable {
    let index: Int
    let name: String
    let type: String
    let hasData: Bool
    let dataKind: String?
    let header: [String: HeaderValue]
    let wcs: WCS?
    let dataSummary: DataSummary?

    var id: Int { index }
  }

  struct HeaderValue: Decodable, Sendable {
    let text: String

    init(from decoder: any Decoder) throws {
      let value = try decoder.singleValueContainer()
      if let string = try? value.decode(String.self) {
        text = string
      } else if let boolean = try? value.decode(Bool.self) {
        text = boolean ? "true" : "false"
      } else if let integer = try? value.decode(Int64.self) {
        text = String(integer)
      } else if let number = try? value.decode(Double.self) {
        text = String(number)
      } else {
        text = "Unavailable"
      }
    }
  }

  struct WCS: Decodable, Sendable {
    let status: String?
    let ctype: [String]?
    let crpix: [Double]?
    let crval: [Double]?
    let axisUnits: [String]?
    let referenceFrame: String?
    let projectionPlaneScaleArcsec: [Double]?
  }

  struct DataSummary: Decodable, Sendable {
    let shape: [Int]?
    let rows: Int?
    let columns: Int?
    let columnNames: [String]?
    let dtype: String?
    let totalPixels: Int?
    let sampledPixels: Int?
    let nonfiniteSampledPixels: Int?
    let samplingReason: String?
  }

  struct Preview: Decodable, Sendable {
    let status: String
    let hduIndex: Int?
    let regionXywh: [Int]?
    let planeIndices: [Int]?
    let coordinates: String?
    let reason: String?
  }

  private struct Envelope: Decodable {
    let tool: String
    let results: FITSInspectionSummary
  }

  static func load(from url: URL) -> FITSInspectionSummary? {
    let maximumBytes = 1_000_000
    guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
    defer { try? handle.close() }
    guard let data = try? handle.read(upToCount: maximumBytes + 1),
          data.count <= maximumBytes else { return nil }
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    guard let envelope = try? decoder.decode(Envelope.self, from: data),
          envelope.tool == "inspect_fits",
          Set(envelope.results.hdus.map(\.index)).count == envelope.results.hdus.count else {
      return nil
    }
    return envelope.results
  }
}
