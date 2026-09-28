import Foundation

enum PhotometricCalibrationStatus: String, Sendable {
  case pass = "PASS"
  case warning = "WARNING"
  case blocked = "BLOCKED_CONTROLADO"
}

struct PhotometricCalibrationColumn: Identifiable, Hashable, Sendable {
  let index: Int
  let name: String
  let numericCount: Int
  let rowCount: Int
  let instrumentalScore: Int
  let catalogScore: Int
  let airmassScore: Int
  let filterScore: Int
  let uncertaintyScore: Int
  let colorScore: Int

  var id: Int { index }
}

struct PhotometricCalibrationReview: Sendable {
  let inputPath: String
  let separatorLabel: String
  let columns: [PhotometricCalibrationColumn]
  let rows: [[String]]
  let status: PhotometricCalibrationStatus
  let findings: [String]
  let nextActions: [String]
  let recommendedInstrumentalColumn: Int?
  let recommendedCatalogColumn: Int?
  let recommendedAirmassColumn: Int?
  let recommendedFilterColumn: Int?
  let recommendedUncertaintyColumn: Int?
  let recommendedColorColumn: Int?
  let filterValues: [String]
}

struct PhotometricCalibrationSelection: Equatable, Sendable {
  var instrumentalColumn: Int?
  var catalogColumn: Int?
  var airmassColumn: Int?
  var filterColumn: Int?
  var filterValue: String?
  var uncertaintyColumn: Int?
  var colorColumn: Int?
  var includeColorTerm: Bool
}

struct PhotometricCalibrationValidation: Equatable, Sendable {
  let status: PhotometricCalibrationStatus
  let findings: [String]
  let nextActions: [String]
  let selectedRowCount: Int
  let usableRowCount: Int
  let skippedNonfiniteRows: Int
  let airmassRange: ClosedRange<Double>?
  let catalogMagnitudeRange: ClosedRange<Double>?
  let colorRange: ClosedRange<Double>?

  var canRun: Bool {
    status != .blocked
  }
}

struct PhotometricCalibrationStagedInput: Equatable, Sendable {
  let tablePath: String
  let mappingPath: String
  let acceptedRows: Int
  let skippedRows: Int
  let includesUncertainty: Bool
  let includesColorTerm: Bool
}
