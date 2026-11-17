import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func radialVelocityInspectorMapsHappyColumnsAndUnits() throws {
    let root = try makeScenarioFixture(name: "rv-happy", files: [
      "rv.csv": """
      bjd_tdb,rv_km_s,rv_error_km_s,instrument
      2459000.1,12.4,0.3,HARPS
      2459001.2,13.1,0.4,HARPS
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }

    let review = try RadialVelocityInspectionService()
      .inspect(path: root.appendingPathComponent("rv.csv").path)

    #expect(review.status == .pass)
    #expect(review.columns.map(\.name) == ["bjd_tdb", "rv_km_s", "rv_error_km_s", "instrument"])
    #expect(review.recommendedTimeColumn == 0)
    #expect(review.recommendedVelocityColumn == 1)
    #expect(review.recommendedUncertaintyColumn == 2)
    #expect(review.inferredTimeSystem == .bjd)
    #expect(review.inferredVelocityUnit == .kilometersPerSecond)
    #expect(review.column(at: 0)?.declaredTimeScale == .tdb)
  }

  @Test
  func radialVelocityInspectorSurfacesAmbiguousCandidates() throws {
    let root = try makeScenarioFixture(name: "rv-ambiguous", files: [
      "rv.csv": """
      jd,bjd,rv_primary,rv_secondary,error
      2459000.1,2459000.2,12.4,12.6,0.3
      2459001.1,2459001.2,13.1,13.0,0.4
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }

    let review = try RadialVelocityInspectionService()
      .inspect(path: root.appendingPathComponent("rv.csv").path)

    #expect(review.status == .warning)
    #expect(review.recommendedTimeColumn == nil)
    #expect(review.recommendedVelocityColumn == nil)
    #expect(review.nextActions.contains { $0.contains("time column") })
    #expect(review.nextActions.contains { $0.contains("radial-velocity column") })
  }

  @Test
  func radialVelocityValidationRequiresUndeclaredTimeAndUnits() throws {
    let root = try makeScenarioFixture(name: "rv-unknown-units", files: [
      "rv.csv": "time,rv,error\n2459000,12,0.2\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let service = RadialVelocityInspectionService()
    let review = try service.inspect(path: root.appendingPathComponent("rv.csv").path)
    var selection = RadialVelocitySelection(
      timeColumn: 0, velocityColumn: 1, uncertaintyColumn: 2, timeSystem: nil, velocityUnit: nil
    )
    #expect(service.validate(review: review, selection: selection).findings.first?.contains("time format") == true)
    selection.timeSystem = .jd
    #expect(service.validate(review: review, selection: selection).findings.first?.contains("time scale") == true)
    selection.timeScale = .utc
    #expect(service.validate(review: review, selection: selection).findings.first?.contains("velocity unit") == true)
    selection.velocityUnit = .kilometersPerSecond
    #expect(service.validate(review: review, selection: selection).findings.first?.contains("uncertainty column") == true)
    selection.uncertaintyUnit = .kilometersPerSecond
    #expect(service.validate(review: review, selection: selection).canRun)
  }

  @Test
  func radialVelocityInspectorBlocksBrokenTable() throws {
    let root = try makeScenarioFixture(name: "rv-broken", files: [
      "broken.csv": "object\nalpha\nbeta\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }

    let review = try RadialVelocityInspectionService()
      .inspect(path: root.appendingPathComponent("broken.csv").path)

    #expect(review.status == .blocked)
    #expect(review.nextActions.contains { $0.contains("numeric time") })
  }

  @Test
  func radialVelocityStagingConvertsMJDAndMetersPerSecondWithoutTouchingOriginal() throws {
    let root = try makeScenarioFixture(name: "rv-stage", files: [
      "rv.tsv": "mjd_utc\trv_m_s\tsigma_km_s\n59000\t1200\t0.05\n59001\t1400\t0.06\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let input = root.appendingPathComponent("rv.tsv")
    let original = try Data(contentsOf: input)
    let service = RadialVelocityInspectionService()
    let review = try service.inspect(path: input.path)
    let selection = RadialVelocitySelection(
      timeColumn: 0,
      velocityColumn: 1,
      uncertaintyColumn: 2,
      timeSystem: .mjd,
      timeScale: .utc,
      velocityUnit: .metersPerSecond,
      uncertaintyUnit: .kilometersPerSecond
    )

    let staged = try service.stage(
      review: review,
      selection: selection,
      runDirectory: root.appendingPathComponent("run").path
    )
    let output = try String(contentsOfFile: staged.velsPath, encoding: .utf8)

    #expect(output.contains("2459000.5 1.2 0.05"))
    #expect(output.contains("# Input Time Standard = MJD"))
    #expect(output.contains("# Time Standard = JD"))
    #expect(output.contains("# Time Scale = UTC"))
    #expect(output.contains("# Uncertainty Units = km/s"))
    let mapping = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: staged.mappingPath))) as? [String: Any])
    #expect(mapping["time_scale_conversion_applied"] as? Bool == false)
    #expect(mapping["uncertainty_input_unit"] as? String == "km/s")
    #expect(mapping["velocity_input_unit"] as? String == "m/s")
    let reopened = try service.inspect(path: staged.velsPath)
    #expect(reopened.column(at: 0)?.declaredTimeSystem == .jd)
    #expect(reopened.column(at: 0)?.declaredTimeScale == .utc)
    #expect(reopened.column(at: 2)?.declaredVelocityUnit == .kilometersPerSecond)
    #expect(staged.acceptedRows == 2)
    #expect(staged.skippedRows == 0)
    #expect(try Data(contentsOf: input) == original)
  }

  @Test
  func radialVelocityStagingAllowsExplicitMissingUncertaintyWithWarning() throws {
    let root = try makeScenarioFixture(name: "rv-no-error", files: [
      "rv.csv": "jd,rv_km_s\n2459000,12.0\n2459001,12.5\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let service = RadialVelocityInspectionService()
    let review = try service.inspect(path: root.appendingPathComponent("rv.csv").path)
    let selection = RadialVelocitySelection(
      timeColumn: 0,
      velocityColumn: 1,
      uncertaintyColumn: nil,
      timeSystem: .jd,
      timeScale: .utc,
      velocityUnit: .kilometersPerSecond
    )

    let validation = service.validate(review: review, selection: selection)
    let staged = try service.stage(
      review: review,
      selection: selection,
      runDirectory: root.appendingPathComponent("run").path
    )
    let mappingData = try Data(contentsOf: URL(fileURLWithPath: staged.mappingPath))
    let mapping = try #require(JSONSerialization.jsonObject(with: mappingData) as? [String: Any])

    #expect(validation.status == .warning)
    #expect(validation.canRun)
    #expect(validation.nextActions.contains { $0.contains("uncertainty column") })
    #expect(mapping["uncertainty_column"] is NSNull)
  }

  @Test
  @MainActor
  func radialVelocityHeadlessReviewInitializesSelection() throws {
    let root = try makeScenarioFixture(name: "rv-store", files: [
      "rv.csv": "jd_utc,rv_km_s,error_km_s,epoch_other,other_value\n2459000,12,0.2,2459000,12000\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.inputPaths = [root.appendingPathComponent("rv.csv").path]

    store.reviewRadialVelocityInput()

    #expect(store.radialVelocityReview?.status == .pass)
    #expect(store.radialVelocityTimeColumn == 0)
    #expect(store.radialVelocityValueColumn == 1)
    #expect(store.radialVelocityUncertaintyColumn == 2)
    #expect(store.radialVelocitySelectionValidation?.canRun == true)
    store.radialVelocityTimeColumn = 3
    store.radialVelocityValueColumn = 4
    #expect(store.radialVelocityTimeSystem == nil)
    #expect(store.radialVelocityTimeScale == nil)
    #expect(store.radialVelocityUnit == nil)
    #expect(store.radialVelocitySelectionValidation?.canRun == false)
  }

  @Test
  func radialVelocityConflictingDeclarationsAreBlockedAndTimePrecisionIsRetained() throws {
    let root = try makeScenarioFixture(name: "rv-conflicting-units", files: [
      "rv.csv": "bjd_tdb,rv_m_s,sigma_m_s\n2459000.123456789,1200,50\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let service = RadialVelocityInspectionService()
    let review = try service.inspect(path: root.appendingPathComponent("rv.csv").path)
    var selection = RadialVelocitySelection(
      timeColumn: 0, velocityColumn: 1, uncertaintyColumn: 2, timeSystem: .jd, timeScale: .utc,
      velocityUnit: .kilometersPerSecond, uncertaintyUnit: .kilometersPerSecond
    )
    #expect(service.validate(review: review, selection: selection).findings.first?.contains("BJD") == true)
    selection.timeSystem = .bjd
    #expect(service.validate(review: review, selection: selection).findings.first?.contains("TDB") == true)
    selection.timeScale = .tdb
    #expect(service.validate(review: review, selection: selection).findings.first?.contains("radial-velocity column declares m/s") == true)
    selection.velocityUnit = .metersPerSecond
    #expect(service.validate(review: review, selection: selection).findings.first?.contains("uncertainty column declares m/s") == true)
    selection.uncertaintyUnit = .metersPerSecond
    let staged = try service.stage(review: review, selection: selection, runDirectory: root.appendingPathComponent("run").path)
    let output = try String(contentsOfFile: staged.velsPath, encoding: .utf8)
    #expect(output.contains("2459000.123456789 1.2 0.05"))
    #expect(output.contains("# Time Standard = BJD"))
    #expect(output.contains("# Time Scale = TDB"))
  }

  @Test
  func radialVelocityValidationBlocksInvalidTimeRowsAndExplicitOffsetsBeforeStaging() throws {
    let root = try makeScenarioFixture(name: "rv-invalid-time", files: [
      "missing.csv": "NaN,12\n2459000,13\n",
      "offset.csv": "bjd_tdb_minus_2450000,rv_km_s\n9000.1,12\n",
      "conflicting.vels": "# Time Standard = BJD_TDB\n# Time Scale = UTC\n2459000 12\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let service = RadialVelocityInspectionService()
    let selection = RadialVelocitySelection(
      timeColumn: 0, velocityColumn: 1, uncertaintyColumn: nil, timeSystem: .bjd, timeScale: .tdb,
      velocityUnit: .kilometersPerSecond
    )
    for (file, reason) in [("missing.csv", "nonfinite"), ("offset.csv", "offset dates")] {
      let review = try service.inspect(path: root.appendingPathComponent(file).path)
      let validation = service.validate(review: review, selection: selection)
      #expect(!validation.canRun)
      #expect(validation.findings.first?.contains(reason) == true)
      let run = root.appendingPathComponent("run-\(file)")
      #expect(throws: RadialVelocityInspectionError.self) {
        try service.stage(review: review, selection: selection, runDirectory: run.path)
      }
      #expect(!FileManager.default.fileExists(atPath: run.path))
    }
    #expect(throws: RadialVelocityInspectionError.invalidSelection("The time standard and time scale comments disagree.")) {
      try service.inspect(path: root.appendingPathComponent("conflicting.vels").path)
    }
  }
}
