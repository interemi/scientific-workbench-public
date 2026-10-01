import CryptoKit
import Foundation
import PDFKit
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func syntheticExamplesHaveValidFormatsAndVerifiedProvenance() throws {
    let root = try makeExampleTestRoot()
    defer { removeEphemeralExampleTestRoot(root) }
    let service = FirstRunExampleService()

    for kind in FirstRunExampleKind.allCases {
      let destination = root.appendingPathComponent(kind.rawValue, isDirectory: true)
      let prepared = try service.create(kind, at: destination)
      #expect(prepared.inputPaths.count == 1)
      #expect(prepared.inputPaths.allSatisfy { $0.hasPrefix(destination.path + "/input/") })

      let manifestURL = destination.appendingPathComponent("expected.json")
      let manifestData = try Data(contentsOf: manifestURL)
      let manifest = try #require(
        JSONSerialization.jsonObject(with: manifestData) as? [String: Any]
      )
      #expect(manifest["schema_version"] as? Int == 1)
      #expect(manifest["synthetic"] as? Bool == true)
      #expect(manifest["example"] as? String == kind.rawValue)
      #expect(manifest["expected_result"] as? String == kind.expectedResult)

      let files = try #require(manifest["files"] as? [[String: String]])
      #expect(files.count == (kind == .mixed ? 3 : 1))
      for record in files {
        let relativePath = try #require(record["path"])
        #expect(relativePath.hasPrefix("input/"))
        #expect(!relativePath.contains(".."))
        let data = try Data(contentsOf: destination.appendingPathComponent(relativePath))
        let actualHash = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        #expect(actualHash == record["sha256"])
      }

      if kind == .document || kind == .mixed {
        let pdfURL = kind == .document
          ? destination.appendingPathComponent("input/observing_note.pdf")
          : destination.appendingPathComponent("input/mixed_bundle/observing_note.pdf")
        let pdf = try #require(PDFDocument(url: pdfURL))
        #expect(pdf.pageCount == 1)
        #expect(pdf.string?.contains("No real observation") == true)
      }
    }

    let table = try String(
      contentsOf: root.appendingPathComponent("table/input/ops.csv"), encoding: .utf8
    )
    #expect(table.split(separator: "\n").count == 4)
    #expect(table.contains("alpha,5,12,ops"))
    let spectrum = try String(
      contentsOf: root.appendingPathComponent("spectrum/input/spectrum.csv"), encoding: .utf8
    )
    #expect(spectrum.split(separator: "\n").count == 6)
    #expect(spectrum.contains("wavelength_nm,flux_relative,error_relative"))
  }

  @Test
  func syntheticFITSHasExpectedImagePixelsAndCelestialReference() throws {
    let root = try makeExampleTestRoot()
    defer { removeEphemeralExampleTestRoot(root) }
    let prepared = try FirstRunExampleService().create(
      .fits, at: root.appendingPathComponent("fits", isDirectory: true)
    )
    let fits = try Data(contentsOf: URL(fileURLWithPath: try #require(prepared.inputPaths.first)))
    #expect(fits.count == 5760)
    let header = try #require(String(data: fits.prefix(2880), encoding: .ascii))
    let cards = stride(from: 0, to: 2880, by: 80).map { offset in
      String(header[header.index(header.startIndex, offsetBy: offset)..<header.index(header.startIndex, offsetBy: offset + 80)])
    }
    #expect(cards.contains { $0.hasPrefix("NAXIS1  =") && $0.contains("8") })
    #expect(cards.contains { $0.hasPrefix("NAXIS2  =") && $0.contains("8") })
    #expect(cards.contains { $0.hasPrefix("CTYPE1  =") && $0.contains("RA---TAN") })
    #expect(cards.contains { $0.hasPrefix("CTYPE2  =") && $0.contains("DEC--TAN") })
    #expect(cards.contains { $0.hasPrefix("CRVAL1  =") && $0.contains("150.0") })
    #expect(cards.contains { $0.hasPrefix("CRVAL2  =") && $0.contains("-30.0") })
    #expect(cards.contains { $0.hasPrefix("BUNIT   =") && $0.contains("adu") })
    #expect(cards.contains { $0.hasPrefix("END") })

    let pixels = (0..<64).map { index -> Float in
      let start = 2880 + index * 4
      let bits = fits[start..<(start + 4)].reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
      return Float(bitPattern: bits)
    }
    #expect(pixels[9].isNaN)
    #expect(pixels.enumerated().allSatisfy { index, value in
      index == 9 ? value.isNaN : value == Float(index)
    })
  }

  @Test
  func onlyTheKnownSyntheticFITSRequestsAVisualWCSPreview() throws {
    let root = try makeScenarioFixture(
      name: "synthetic-fits-preview",
      files: ["scripts/datanalysis_env.py": "# test wrapper\n"]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let prepared = try FirstRunExampleService().create(
      .fits, at: root.appendingPathComponent("example", isDirectory: true)
    )
    let input = try #require(prepared.inputPaths.first)
    let run = root.appendingPathComponent("run", isDirectory: true)
    let capability = expertFITSCapability()
    let builder = CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
    let command = try builder.build(
      capability: capability,
      request: RunRequest(
        capabilityID: capability.id,
        inputPaths: [input],
        outputDirectory: run.path,
        rawArguments: ""
      ),
      skillRoot: root.path
    )
    #expect(command.arguments.contains("--preview"))
    #expect(command.arguments.contains(run.appendingPathComponent("previews/synthetic_wcs.png").path))
    #expect(command.arguments.contains("CUNIT1"))
    #expect(command.arguments.contains("CDELT2"))

    var changed = try Data(contentsOf: URL(fileURLWithPath: input))
    changed[2880] = 0x01
    let changedURL = root.appendingPathComponent("changed.fits")
    try changed.write(to: changedURL)
    let ordinaryCommand = try builder.build(
      capability: capability,
      request: RunRequest(
        capabilityID: capability.id,
        inputPaths: [changedURL.path],
        outputDirectory: run.path,
        rawArguments: ""
      ),
      skillRoot: root.path
    )
    #expect(!ordinaryCommand.arguments.contains("--preview"))
    #expect(!ordinaryCommand.arguments.contains("--header-key"))
    #expect(try Data(contentsOf: URL(fileURLWithPath: input)) != changed)
  }

  @Test
  func recreatingAnExampleNeverOverwritesAnEarlierCopy() throws {
    let root = try makeExampleTestRoot()
    defer { removeEphemeralExampleTestRoot(root) }
    let service = FirstRunExampleService()
    let firstURL = root.appendingPathComponent("copy-1", isDirectory: true)
    let first = try service.create(.table, at: firstURL)
    let original = try Data(contentsOf: URL(fileURLWithPath: try #require(first.inputPaths.first)))

    #expect(throws: FirstRunExampleError.self) {
      try service.create(.table, at: firstURL)
    }
    #expect(try Data(contentsOf: URL(fileURLWithPath: try #require(first.inputPaths.first))) == original)

    let second = try service.create(
      .table, at: root.appendingPathComponent("copy-2", isDirectory: true)
    )
    #expect(second.directory != first.directory)
    #expect(try Data(contentsOf: URL(fileURLWithPath: try #require(second.inputPaths.first))) == original)
  }

  @Test
  @MainActor
  func preparingAnExpertExampleSelectsItsCapabilityAndPreservesEarlierInputs() throws {
    let root = try makeExampleTestRoot()
    defer { removeEphemeralExampleTestRoot(root) }
    let defaults = try #require(UserDefaults(suiteName: "Scientific-Workbench-Example-\(UUID().uuidString)"))
    let output = root.appendingPathComponent("Outputs", isDirectory: true)
    let library = root.appendingPathComponent("Examples", isDirectory: true)
    defaults.set(output.path, forKey: "outputRootPath")
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      filesystemSafetyPolicy: FilesystemSafetyPolicy(homeDirectory: root),
      firstRunExampleLibraryRoot: library
    )
    store.capabilities = [expertFITSCapability()]

    store.prepareFirstRunExample(.fits)
    let first = try #require(store.preparedFirstRunExample)
    #expect(store.firstRunExampleError == nil)
    #expect(first.directory.deletingLastPathComponent() == library)
    #expect(store.inputPaths == first.inputPaths)
    #expect(store.selectedCapabilityID == "inspect_fits")
    #expect(store.capabilityCatalogMode == .expert)
    #expect(store.searchText == "inspect_fits")
    #expect(store.selectedSection == .capabilities)
    let original = try Data(contentsOf: URL(fileURLWithPath: try #require(first.inputPaths.first)))

    store.prepareFirstRunExample(.fits)
    let second = try #require(store.preparedFirstRunExample)
    #expect(second.directory != first.directory)
    #expect(store.inputPaths == second.inputPaths)
    #expect(try Data(contentsOf: URL(fileURLWithPath: try #require(first.inputPaths.first))) == original)
  }

  @Test
  @MainActor
  func mixedFolderFollowUpReusesTheInputAndLinksTheTwoPreservedJobs() throws {
    let root = try makeExampleTestRoot()
    defer { removeEphemeralExampleTestRoot(root) }
    let prepared = try FirstRunExampleService().create(
      .mixed, at: root.appendingPathComponent("mixed", isDirectory: true)
    )
    let defaults = try #require(UserDefaults(suiteName: "Scientific-Workbench-Mixed-\(UUID().uuidString)"))
    defaults.set(root.appendingPathComponent("Outputs", isDirectory: true).path, forKey: "outputRootPath")
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false,
      filesystemSafetyPolicy: FilesystemSafetyPolicy(homeDirectory: root)
    )
    let documentCapability = CapabilityEntry(
      id: "document_intake_workbench",
      label: "Document intake",
      script: "scripts/document_intake_workbench.py",
      visibleBlock: "documents + reporting",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Inspect documents."
    )
    let tableCapability = CapabilityEntry(
      id: "cross_domain_data_workbench",
      label: "Mixed data inventory",
      script: "scripts/cross_domain_data_workbench.py",
      visibleBlock: "notebooks + cross-domain",
      kind: "golden_path",
      supportLevel: "stable",
      platform: "portable",
      requiresDatanalysis: false,
      preflightMode: "none",
      smokeTier: "core",
      shortDescription: "Inspect mixed data."
    )
    store.capabilities = [documentCapability, tableCapability]
    var intakeJob = JobRecord(capability: documentCapability, runDirectory: root.appendingPathComponent("intake-run").path)
    intakeJob.status = .succeeded
    intakeJob.requestInputPaths = prepared.inputPaths
    var tableJob = JobRecord(capability: tableCapability, runDirectory: root.appendingPathComponent("table-run").path)
    tableJob.status = .succeeded
    tableJob.requestInputPaths = prepared.inputPaths
    store.jobs = [tableJob, intakeJob]

    #expect(store.canPrepareMixedDataFollowUp(for: intakeJob))
    store.prepareMixedDataFollowUp(for: intakeJob)
    #expect(store.inputPaths == prepared.inputPaths)
    #expect(store.selectedCapabilityID == tableCapability.id)
    #expect(store.searchText == tableCapability.id)
    #expect(store.selectedSection == .capabilities)
    #expect(store.relatedFirstRunJobs(to: intakeJob).map(\.id) == [tableJob.id])
    #expect(store.relatedFirstRunJobs(to: tableJob).map(\.id) == [intakeJob.id])

    intakeJob.status = .failed
    #expect(!store.canPrepareMixedDataFollowUp(for: intakeJob))
  }

  private func makeExampleTestRoot() throws -> URL {
    let environment = ProcessInfo.processInfo.environment
    let base = environment["SCIENTIFIC_WORKBENCH_EXAMPLE_EVIDENCE_ROOT"].map {
      URL(fileURLWithPath: $0, isDirectory: true)
    } ?? FileManager.default.temporaryDirectory
    let root = base.appendingPathComponent(
      "Scientific-Workbench-Example-Tests-\(UUID().uuidString)", isDirectory: true
    )
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    return root
  }

  private func removeEphemeralExampleTestRoot(_ root: URL) {
    guard ProcessInfo.processInfo.environment["SCIENTIFIC_WORKBENCH_EXAMPLE_EVIDENCE_ROOT"] == nil else {
      return
    }
    try? FileManager.default.removeItem(at: root)
  }
}
