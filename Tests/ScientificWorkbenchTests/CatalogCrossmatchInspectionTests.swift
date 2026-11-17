import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func catalogCrossmatchReviewRequiresExplicitValidCoordinateMapping() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Crossmatch-\(UUID().uuidString)", isDirectory: true)
    let leftPath = root.appendingPathComponent("left.csv")
    let rightPath = root.appendingPathComponent("right.tsv")
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try "ra_deg,dec_deg,source_id\n120.0,-30.0,L1\n120.1,-30.1,L2\n"
      .write(to: leftPath, atomically: true, encoding: .utf8)
    try "source_id\tra\tdec\nR1\t120.0001\t-30.0001\nR2\t121.0\t-31.0\n"
      .write(to: rightPath, atomically: true, encoding: .utf8)

    let service = CatalogCrossmatchInspectionService()
    let loader = GuidedInputReviewLoader()
    let missing = root.appendingPathComponent("missing.csv").path
    let candidates = try await loader.catalogFiles(in: [root.path, leftPath.path, missing, rightPath.path])
    #expect(candidates == [leftPath.path, rightPath.path])
    let left = try await loader.inspectCatalog(at: leftPath.path)
    let right = try await loader.inspectCatalog(at: rightPath.path)
    let cancelled = Task {
      withUnsafeCurrentTask { $0?.cancel() }
      return try await loader.inspectCatalog(at: missing)
    }
    await #expect(throws: CancellationError.self) { try await cancelled.value }
    let reviewed = CatalogCrossmatchSelection(
      left: .init(raColumn: 0, decColumn: 1, raUnit: .degrees, decUnit: .degrees),
      right: .init(raColumn: 1, decColumn: 2, raUnit: .degrees, decUnit: .degrees),
      radiusArcseconds: 1.5,
      sharedICRSConfirmed: true,
      coordinateEpochJulianYear: 2016.25
    )

    #expect(left.formatLabel == "comma")
    #expect(right.formatLabel == "tab")
    #expect(left.columns.map(\.name) == ["ra_deg", "dec_deg", "source_id"])
    #expect(service.validate(left: left, right: right, selection: reviewed).status == .pass)

    let prepared = try service.prepare(left: left, right: right, selection: reviewed)
    let arguments = prepared.arguments(runURL: root.appendingPathComponent("run"))
    #expect(arguments.dropFirst(3).prefix(20).elementsEqual([
      "--left-ra", "ra_deg", "--left-ra-unit", "deg",
      "--left-dec", "dec_deg", "--left-dec-unit", "deg",
      "--right-ra", "ra", "--right-ra-unit", "deg",
      "--right-dec", "dec", "--right-dec-unit", "deg",
      "--left-format", "comma", "--right-format", "tab",
    ]))
    #expect(arguments.suffix(10).elementsEqual([
      "--radius-arcsec", "1.5", "--coordinate-frame", "icrs",
      "--coordinate-epoch-jyear", "2016.25",
      "--summary-json", root.appendingPathComponent("run/summary.json").path,
      "--manifest-json", root.appendingPathComponent("run/manifest.json").path,
    ]))
    #expect(arguments.contains(root.appendingPathComponent("run/artifacts/catalog_crossmatch.ecsv").path))

    let skillRoot = try makeScenarioFixture(
      name: "catalog-crossmatch-guided-builder",
      files: ["scripts/datanalysis_env.py": "# fixture\n"]
    )
    defer { try? FileManager.default.removeItem(at: skillRoot) }
    let entry = CapabilityEntry(
      id: "catalog_workbench.crossmatch-sky",
      label: "Catalog crossmatch",
      script: "scripts/catalog_workbench.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "supporting_tool",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: true,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Reviewed sky crossmatch."
    )
    let command = try CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3").build(
      capability: entry,
      request: RunRequest(
        capabilityID: entry.id,
        inputPaths: [leftPath.path, rightPath.path],
        outputDirectory: root.appendingPathComponent("run").path,
        rawArguments: arguments.map(ShellWords.quote).joined(separator: " ")
      ),
      skillRoot: skillRoot.path
    )
    #expect(command.arguments.contains("crossmatch-sky"))
    #expect(command.arguments.contains(leftPath.path))
    #expect(command.arguments.contains(rightPath.path))

    var unconfirmed = reviewed
    unconfirmed.sharedICRSConfirmed = false
    #expect(service.validate(left: left, right: right, selection: unconfirmed).findings.first?.contains("ICRS") == true)

    var missingEpoch = reviewed
    missingEpoch.coordinateEpochJulianYear = nil
    #expect(service.validate(left: left, right: right, selection: missingEpoch).findings.first?.contains("Julian year") == true)

    var missingUnit = reviewed
    missingUnit.right.raUnit = nil
    #expect(service.validate(left: left, right: right, selection: missingUnit).findings.first?.contains("column and its unit") == true)

    var duplicated = reviewed
    duplicated.left.decColumn = duplicated.left.raColumn
    #expect(service.validate(left: left, right: right, selection: duplicated).status == .blocked)
  }

  @Test
  func catalogCrossmatchReviewBlocksInvalidRangesAndNonNumericCoordinates() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Crossmatch-Invalid-\(UUID().uuidString)", isDirectory: true)
    let leftPath = root.appendingPathComponent("left.csv")
    let rightPath = root.appendingPathComponent("right.csv")
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try "ra,dec\n361.0,-30.0\n"
      .write(to: leftPath, atomically: true, encoding: .utf8)
    try "ra,dec\n120.0,not-a-number\n"
      .write(to: rightPath, atomically: true, encoding: .utf8)

    let service = CatalogCrossmatchInspectionService()
    let left = try service.inspect(path: leftPath.path)
    let right = try service.inspect(path: rightPath.path)
    let selection = CatalogCrossmatchSelection(
      left: .init(raColumn: 0, decColumn: 1, raUnit: .degrees, decUnit: .degrees),
      right: .init(raColumn: 0, decColumn: 1, raUnit: .degrees, decUnit: .degrees),
      radiusArcseconds: 1,
      sharedICRSConfirmed: true,
      coordinateEpochJulianYear: 2016
    )
    let invalidRange = service.validate(left: left, right: right, selection: selection)
    #expect(invalidRange.status == .blocked)
    #expect(invalidRange.findings.first?.contains("[0, 360)") == true)

    try "ra,dec\n120.0,-30.0\n"
      .write(to: leftPath, atomically: true, encoding: .utf8)
    let validLeft = try service.inspect(path: leftPath.path)
    let nonNumeric = service.validate(left: validLeft, right: right, selection: selection)
    #expect(nonNumeric.status == .blocked)
    #expect(nonNumeric.findings.first?.contains("non-numeric") == true)
  }

  @Test
  func catalogCrossmatchReviewDistinguishesAngularUnitsAndRadiusLimits() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Crossmatch-Units-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    let leftPath = root.appendingPathComponent("left.csv")
    let rightPath = root.appendingPathComponent("right.csv")
    try "ra_hours,dec_deg\n23.999,90\n0,-90\n".write(to: leftPath, atomically: true, encoding: .utf8)
    try "ra_rad,dec_rad\n6.28,\(Double.pi / 2)\n0,\(-Double.pi / 2)\n"
      .write(to: rightPath, atomically: true, encoding: .utf8)

    let service = CatalogCrossmatchInspectionService()
    let left = try service.inspect(path: leftPath.path)
    let right = try service.inspect(path: rightPath.path)
    var selection = CatalogCrossmatchSelection(
      left: .init(raColumn: 0, decColumn: 1, raUnit: .hours, decUnit: .degrees),
      right: .init(raColumn: 0, decColumn: 1, raUnit: .degrees, decUnit: .radians),
      radiusArcseconds: 1,
      sharedICRSConfirmed: true,
      coordinateEpochJulianYear: 2016
    )
    #expect(service.validate(left: left, right: right, selection: selection).findings.first?.contains("ra_rad") == true)
    selection.right.raUnit = .radians
    #expect(service.validate(left: left, right: right, selection: selection).status == .pass)

    selection.radiusArcseconds = CatalogCrossmatchSelection.maximumRadiusArcseconds
    #expect(service.validate(left: left, right: right, selection: selection).status == .warning)
    for invalidRadius in [Double.infinity, Double.nan, 0, -1, 648_000.01] {
      selection.radiusArcseconds = invalidRadius
      #expect(service.validate(left: left, right: right, selection: selection).status == .blocked)
    }
    selection.radiusArcseconds = 1

    try "ra_rad,dec_rad\n\(2 * Double.pi),0\n".write(to: rightPath, atomically: true, encoding: .utf8)
    let outsideRange = try service.inspect(path: rightPath.path)
    #expect(service.validate(left: left, right: outsideRange, selection: selection).findings.first?.contains("[0, 2π)") == true)
  }
}
