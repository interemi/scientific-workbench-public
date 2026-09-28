import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func photometricCalibrationMapsHappyColumns() throws {
    let root = try makeScenarioFixture(name: "photometric-happy", files: [
      "standards.csv": """
      star,instrumental_mag,catalog_mag,airmass,filter,offset_err,b_minus_v
      A,12.10,11.02,1.05,R,0.02,0.40
      B,12.32,11.18,1.22,R,0.02,0.55
      C,12.61,11.38,1.48,R,0.03,0.72
      D,12.92,11.61,1.79,R,0.03,0.90
      E,13.21,11.82,2.08,R,0.04,1.10
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }

    let review = try PhotometricCalibrationService()
      .inspect(path: root.appendingPathComponent("standards.csv").path)

    #expect(review.status == .pass)
    #expect(review.recommendedInstrumentalColumn == 1)
    #expect(review.recommendedCatalogColumn == 2)
    #expect(review.recommendedAirmassColumn == 3)
    #expect(review.recommendedFilterColumn == 4)
    #expect(review.recommendedUncertaintyColumn == 5)
    #expect(review.recommendedColorColumn == 6)
    #expect(review.filterValues == ["R"])
  }

  @Test
  func photometricCalibrationSurfacesAmbiguousColumns() throws {
    let root = try makeScenarioFixture(name: "photometric-ambiguous", files: [
      "standards.csv": """
      inst_mag,instrumental_mag,std_mag,catalog_mag,airmass,secz
      12.1,12.1,11.0,11.0,1.1,1.1
      12.3,12.3,11.2,11.2,1.4,1.4
      12.6,12.6,11.4,11.4,1.8,1.8
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }

    let review = try PhotometricCalibrationService()
      .inspect(path: root.appendingPathComponent("standards.csv").path)

    #expect(review.status == .warning)
    #expect(review.recommendedInstrumentalColumn == nil)
    #expect(review.recommendedCatalogColumn == nil)
    #expect(review.recommendedAirmassColumn == nil)
    #expect(review.nextActions.contains { $0.contains("instrumental magnitude") })
    #expect(review.nextActions.contains { $0.contains("catalog magnitude") })
    #expect(review.nextActions.contains { $0.contains("airmass") })
  }

  @Test
  func photometricCalibrationWarnsAndExcludesNonfiniteRows() throws {
    let root = try makeScenarioFixture(name: "photometric-nonfinite", files: [
      "standards.csv": """
      inst_mag,std_mag,airmass,filter,offset_err
      12.1,11.0,1.1,R,0.02
      NaN,11.2,1.3,R,0.02
      12.5,11.4,1.5,R,0.03
      12.7,Inf,1.7,R,0.03
      12.9,11.8,1.9,R,0.04
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let service = PhotometricCalibrationService()
    let review = try service.inspect(path: root.appendingPathComponent("standards.csv").path)
    let selection = PhotometricCalibrationSelection(
      instrumentalColumn: 0,
      catalogColumn: 1,
      airmassColumn: 2,
      filterColumn: 3,
      filterValue: "R",
      uncertaintyColumn: 4,
      colorColumn: nil,
      includeColorTerm: false
    )

    let validation = service.validate(review: review, selection: selection)

    #expect(validation.status == .warning)
    #expect(validation.canRun)
    #expect(validation.selectedRowCount == 5)
    #expect(validation.usableRowCount == 3)
    #expect(validation.skippedNonfiniteRows == 2)
    #expect(validation.findings.contains { $0.contains("NaN, Inf") })
  }

  @Test
  func photometricCalibrationBlocksMissingRequiredColumns() throws {
    let root = try makeScenarioFixture(name: "photometric-missing", files: [
      "standards.csv": "star,filter\nA,R\nB,R\nC,R\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let service = PhotometricCalibrationService()
    let review = try service.inspect(path: root.appendingPathComponent("standards.csv").path)
    let validation = service.validate(
      review: review,
      selection: PhotometricCalibrationSelection(
        instrumentalColumn: nil,
        catalogColumn: nil,
        airmassColumn: nil,
        filterColumn: 1,
        filterValue: "R",
        uncertaintyColumn: nil,
        colorColumn: nil,
        includeColorTerm: false
      )
    )

    #expect(review.status == .blocked)
    #expect(validation.status == .blocked)
    #expect(!validation.canRun)
    #expect(validation.findings.first?.contains("instrumental magnitude") == true)
  }

  @Test
  func photometricCalibrationRequiresOneFilterForMultibandInput() throws {
    let root = try makeScenarioFixture(name: "photometric-filter", files: [
      "standards.csv": """
      inst_mag,std_mag,airmass,filter,offset_err
      12.1,11.0,1.1,B,0.02
      12.2,11.1,1.2,R,0.02
      12.4,11.2,1.4,R,0.03
      12.6,11.4,1.7,R,0.03
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let service = PhotometricCalibrationService()
    let review = try service.inspect(path: root.appendingPathComponent("standards.csv").path)
    var selection = PhotometricCalibrationSelection(
      instrumentalColumn: 0,
      catalogColumn: 1,
      airmassColumn: 2,
      filterColumn: 3,
      filterValue: nil,
      uncertaintyColumn: 4,
      colorColumn: nil,
      includeColorTerm: false
    )

    #expect(service.validate(review: review, selection: selection).status == .blocked)
    selection.filterValue = "R"
    #expect(service.validate(review: review, selection: selection).canRun)
  }

  @Test
  func photometricCalibrationWarnsAboutSuspiciousRanges() throws {
    let root = try makeScenarioFixture(name: "photometric-ranges", files: [
      "standards.csv": """
      inst_mag,std_mag,airmass,filter,offset_err
      12.1,61.0,0.7,R,0.02
      12.2,61.1,0.8,R,0.02
      12.3,61.2,0.9,R,0.03
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let service = PhotometricCalibrationService()
    let review = try service.inspect(path: root.appendingPathComponent("standards.csv").path)
    let validation = service.validate(
      review: review,
      selection: PhotometricCalibrationSelection(
        instrumentalColumn: 0,
        catalogColumn: 1,
        airmassColumn: 2,
        filterColumn: 3,
        filterValue: "R",
        uncertaintyColumn: 4,
        colorColumn: nil,
        includeColorTerm: false
      )
    )

    #expect(validation.status == .warning)
    #expect(validation.findings.contains { $0.contains("Airmass values") })
    #expect(validation.findings.contains { $0.contains("Catalog magnitudes") })
    #expect(validation.findings.contains { $0.contains("coverage is narrow") })
  }

  @Test
  func photometricCalibrationStagesCanonicalCopyWithoutTouchingOriginal() throws {
    let root = try makeScenarioFixture(name: "photometric-stage", files: [
      "standards.tsv": """
      object	m_inst	m_std	secz	band	sigma	b_v
      A	12.10	11.02	1.05	B	0.02	0.40
      B	12.32	11.18	1.22	R	0.02	0.55
      C	12.61	11.38	1.48	R	0.03	0.72
      D	12.92	11.61	1.79	R	0.03	0.90
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let input = root.appendingPathComponent("standards.tsv")
    let original = try Data(contentsOf: input)
    let service = PhotometricCalibrationService()
    let review = try service.inspect(path: input.path)
    let selection = PhotometricCalibrationSelection(
      instrumentalColumn: 1,
      catalogColumn: 2,
      airmassColumn: 3,
      filterColumn: 4,
      filterValue: "R",
      uncertaintyColumn: 5,
      colorColumn: 6,
      includeColorTerm: true
    )

    let staged = try service.stage(
      review: review,
      selection: selection,
      runDirectory: root.appendingPathComponent("run").path
    )
    let table = try String(contentsOfFile: staged.tablePath, encoding: .utf8)
    let mappingData = try Data(contentsOf: URL(fileURLWithPath: staged.mappingPath))
    let mapping = try #require(JSONSerialization.jsonObject(with: mappingData) as? [String: Any])

    #expect(table.hasPrefix("inst_mag,std_mag,airmass,filter,color_index,offset_err\n"))
    #expect(!table.contains(",B,"))
    #expect(staged.acceptedRows == 3)
    #expect(staged.skippedRows == 0)
    #expect(staged.includesUncertainty)
    #expect(staged.includesColorTerm)
    #expect(mapping["filter_value"] as? String == "R")
    #expect(mapping["original_modified"] as? Bool == false)
    #expect(try Data(contentsOf: input) == original)
  }

  @Test
  @MainActor
  func photometricCalibrationHeadlessReviewInitializesSelection() throws {
    let root = try makeScenarioFixture(name: "photometric-store", files: [
      "standards.csv": """
      inst_mag,std_mag,airmass,filter,offset_err
      12.1,11.0,1.1,R,0.02
      12.3,11.2,1.4,R,0.02
      12.6,11.4,1.8,R,0.03
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.inputPaths = [root.appendingPathComponent("standards.csv").path]

    store.reviewPhotometricCalibrationInput()

    #expect(store.photometricCalibrationReview?.status == .pass)
    #expect(store.photometricInstrumentalColumn == 0)
    #expect(store.photometricCatalogColumn == 1)
    #expect(store.photometricAirmassColumn == 2)
    #expect(store.photometricFilterColumn == 3)
    #expect(store.photometricFilterValue == "R")
    #expect(store.photometricUncertaintyColumn == 4)
    #expect(store.photometricCalibrationValidation?.canRun == true)
  }
}
