import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func catalogCrossmatchReviewRequiresExplicitValidCoordinateMapping() throws {
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
    let left = try service.inspect(path: leftPath.path)
    let right = try service.inspect(path: rightPath.path)
    let reviewed = CatalogCrossmatchSelection(
      leftRAColumn: 0,
      leftDecColumn: 1,
      rightRAColumn: 1,
      rightDecColumn: 2,
      radiusArcseconds: 1.5,
      coordinateUnitsConfirmed: true
    )

    #expect(left.formatLabel == "comma")
    #expect(right.formatLabel == "tab")
    #expect(left.columns.map(\.name) == ["ra_deg", "dec_deg", "source_id"])
    #expect(service.validate(left: left, right: right, selection: reviewed).status == .pass)

    let prepared = try service.prepare(left: left, right: right, selection: reviewed)
    let arguments = prepared.arguments(runURL: root.appendingPathComponent("run"))
    #expect(arguments.contains("--left-ra"))
    #expect(arguments.contains("ra_deg"))
    #expect(arguments.contains("--right-dec"))
    #expect(arguments.contains("dec"))
    #expect(arguments.contains("1.5"))
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
    unconfirmed.coordinateUnitsConfirmed = false
    #expect(service.validate(left: left, right: right, selection: unconfirmed).status == .blocked)

    var duplicated = reviewed
    duplicated.leftDecColumn = duplicated.leftRAColumn
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
      leftRAColumn: 0,
      leftDecColumn: 1,
      rightRAColumn: 0,
      rightDecColumn: 1,
      radiusArcseconds: 1,
      coordinateUnitsConfirmed: true
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
}
