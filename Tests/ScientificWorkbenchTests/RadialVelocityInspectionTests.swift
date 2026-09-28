import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func radialVelocityInspectorMapsHappyColumnsAndUnits() throws {
    let root = try makeScenarioFixture(name: "rv-happy", files: [
      "rv.csv": """
      bjd,rv_km_s,rv_error_km_s,instrument
      2459000.1,12.4,0.3,HARPS
      2459001.2,13.1,0.4,HARPS
      """
    ])
    defer { try? FileManager.default.removeItem(at: root) }

    let review = try RadialVelocityInspectionService()
      .inspect(path: root.appendingPathComponent("rv.csv").path)

    #expect(review.status == .pass)
    #expect(review.columns.map(\.name) == ["bjd", "rv_km_s", "rv_error_km_s", "instrument"])
    #expect(review.recommendedTimeColumn == 0)
    #expect(review.recommendedVelocityColumn == 1)
    #expect(review.recommendedUncertaintyColumn == 2)
    #expect(review.inferredTimeSystem == .bjd)
    #expect(review.inferredVelocityUnit == .kilometersPerSecond)
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
  func radialVelocityValidationKeepsUnknownUnitsAsWarning() throws {
    let root = try makeScenarioFixture(name: "rv-unknown-units", files: [
      "rv.csv": "time,rv,error\n2459000,12,0.2\n"
    ])
    defer { try? FileManager.default.removeItem(at: root) }
    let service = RadialVelocityInspectionService()
    let review = try service.inspect(path: root.appendingPathComponent("rv.csv").path)
    let validation = service.validate(
      review: review,
      selection: RadialVelocitySelection(
        timeColumn: 0,
        velocityColumn: 1,
        uncertaintyColumn: 2,
        timeSystem: .jd,
        velocityUnit: .kilometersPerSecond
      )
    )

    #expect(validation.status == .warning)
    #expect(validation.nextActions.contains { $0.contains("time standard") })
    #expect(validation.nextActions.contains { $0.contains("velocity unit") })
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
      "rv.tsv": "mjd\trv_m_s\tsigma_m_s\n59000\t1200\t50\n59001\t1400\t60\n"
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
      velocityUnit: .metersPerSecond
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
      "rv.csv": "jd,rv_km_s,error\n2459000,12,0.2\n"
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
  }
}
