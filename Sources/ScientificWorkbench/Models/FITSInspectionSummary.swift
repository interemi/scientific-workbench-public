import Foundation

struct FITSInspectionSummary: Decodable, Sendable {
  let path: String?
  let hdus: [HDU]
  let preview: Preview?
  let previewExtension: Int?
  let pixelLookup: PixelLookup?

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

  struct PixelLookup: Decodable, Sendable {
    struct WorldAxis: Decodable, Sendable {
      let name: String
      let value: Double
      let unit: String
    }

    let hduIndex: Int
    let imageXy: [Int]
    let planeIndices: [Int]
    let pixelValue: HeaderValue?
    let pixelUnit: String?
    let pixelStatus: String
    let worldAxes: [WorldAxis]
    let worldReason: String?
    let referenceFrame: String?
  }

  func attachedSource(in job: JobRecord) -> String? {
    guard let path, path.hasPrefix("/") || path.hasPrefix("~/") else { return nil }
    let source = FilesystemPath.canonicalURL(path)
    guard (try? source.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else { return nil }
    for attachedPath in job.requestInputPaths {
      let attached = FilesystemPath.canonicalURL(attachedPath)
      if source.path == attached.path { return source.path }
      let prefix = attached.path.hasSuffix("/") ? attached.path : attached.path + "/"
      if source.path.hasPrefix(prefix),
         (try? attached.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true {
        return source.path
      }
    }
    return nil
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

enum FITSInspectionAction: Sendable {
  case lookup(x: Int, y: Int)
  case crop(x: Int, y: Int, width: Int, height: Int)

  var isPixelLookup: Bool {
    if case .lookup = self { return true }
    return false
  }

  func arguments(in run: URL) -> [String] {
    switch self {
    case let .lookup(x, y):
      return ["--pixel", "\(x),\(y)"]
    case let .crop(x, y, width, height):
      return ["--crop", "\(x),\(y),\(width),\(height)",
              "--preview", run.appendingPathComponent("previews/fits_quicklook.png").path,
              "--preview-if-available"]
    }
  }
}
