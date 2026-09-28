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
  let columns: [CatalogCrossmatchColumn]
  let sampledRowCount: Int
  let sampleWasTruncated: Bool
}

struct CatalogCrossmatchSelection: Equatable, Sendable {
  var leftRAColumn: Int?
  var leftDecColumn: Int?
  var rightRAColumn: Int?
  var rightDecColumn: Int?
  var radiusArcseconds: Double
  var coordinateUnitsConfirmed: Bool
}

struct CatalogCrossmatchValidation: Equatable, Sendable {
  let status: CatalogCrossmatchStatus
  let findings: [String]
  let nextActions: [String]

  var canRun: Bool {
    status != .blocked
  }
}

struct CatalogCrossmatchPreparedRun: Equatable, Sendable {
  let leftPath: String
  let rightPath: String
  let leftRAColumn: String
  let leftDecColumn: String
  let rightRAColumn: String
  let rightDecColumn: String
  let radiusArcseconds: Double

  func arguments(runURL: URL) -> [String] {
    [
      leftPath,
      rightPath,
      runURL.appendingPathComponent("artifacts/catalog_crossmatch.ecsv").path,
      "--left-ra", leftRAColumn,
      "--left-dec", leftDecColumn,
      "--right-ra", rightRAColumn,
      "--right-dec", rightDecColumn,
      "--radius-arcsec", String(
        format: "%.12g",
        locale: Locale(identifier: "en_US_POSIX"),
        radiusArcseconds
      ),
      "--summary-json", runURL.appendingPathComponent("summary.json").path,
      "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
    ]
  }
}
