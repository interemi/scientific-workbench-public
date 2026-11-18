import Foundation

enum CatalogCrossmatchStatus: String, Equatable, Sendable {
  case pass = "PASS"
  case warning = "WARNING"
  case blocked = "BLOCKED_CONTROLADO"
}

struct CatalogCrossmatchColumn: Identifiable, Hashable, Sendable {
  let index: Int
  let name: String
  let numericCount: Int
  let sampledRowCount: Int
  let finiteRange: ClosedRange<Double>?

  var id: Int { index }
}

struct CatalogCrossmatchTableReview: Sendable {
  let inputPath: String
  let formatLabel: String
  let backendFormat: String
  let columns: [CatalogCrossmatchColumn]
  let sampledRowCount: Int
  let sampleWasTruncated: Bool
}

enum CatalogCrossmatchCoordinateUnit: String, CaseIterable, Sendable {
  case degrees = "deg"
  case radians = "rad"
  case hours = "hourangle"

  var label: String {
    switch self {
    case .degrees: "Decimal degrees"
    case .radians: "Radians"
    case .hours: "Decimal hours"
    }
  }

  var fullCircle: Double {
    switch self {
    case .degrees: 360
    case .radians: 2 * .pi
    case .hours: 24
    }
  }
}

struct CatalogCrossmatchMapping: Equatable, Sendable {
  var raColumn: Int?
  var decColumn: Int?
  var raUnit: CatalogCrossmatchCoordinateUnit?
  var decUnit: CatalogCrossmatchCoordinateUnit?
}

struct CatalogCrossmatchSelection: Equatable, Sendable {
  static let maximumRadiusArcseconds = 180.0 * 3_600

  var left: CatalogCrossmatchMapping
  var right: CatalogCrossmatchMapping
  var radiusArcseconds: Double?
  var sharedICRSConfirmed: Bool
  var coordinateEpochJulianYear: Double?
}

struct CatalogCrossmatchValidation: Equatable, Sendable {
  let status: CatalogCrossmatchStatus
  let findings: [String]
  let nextActions: [String]

  var canRun: Bool {
    status != .blocked
  }
}

struct CatalogCrossmatchMappedColumn: Equatable, Sendable {
  let name: String
  let unit: CatalogCrossmatchCoordinateUnit

  func arguments(role: String) -> [String] {
    ["--\(role)=\(name)", "--\(role)-unit", unit.rawValue]
  }
}

struct CatalogCrossmatchPreparedRun: Equatable, Sendable {
  let leftPath: String
  let rightPath: String
  let leftFormat: String
  let rightFormat: String
  let leftRA: CatalogCrossmatchMappedColumn
  let leftDec: CatalogCrossmatchMappedColumn
  let rightRA: CatalogCrossmatchMappedColumn
  let rightDec: CatalogCrossmatchMappedColumn
  let radiusArcseconds: Double
  let coordinateEpochJulianYear: Double

  func arguments(runURL: URL) -> [String] {
    let columnArguments = leftRA.arguments(role: "left-ra")
      + leftDec.arguments(role: "left-dec")
      + rightRA.arguments(role: "right-ra")
      + rightDec.arguments(role: "right-dec")
    return [
      leftPath,
      rightPath,
      runURL.appendingPathComponent("artifacts/catalog_crossmatch.ecsv").path,
    ] + columnArguments + [
      "--left-format", leftFormat,
      "--right-format", rightFormat,
      "--radius-arcsec", String(radiusArcseconds),
      "--coordinate-frame", "icrs",
      "--coordinate-epoch-jyear", String(coordinateEpochJulianYear),
      "--summary-json", runURL.appendingPathComponent("summary.json").path,
      "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
    ]
  }
}
