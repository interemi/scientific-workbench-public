import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func portableRunSharesSelectedEvidenceAndVerifiesHashesWithoutExtraction() async throws {
    let root = try makeScenarioFixture(
      name: "portable-run-package",
      files: [
        "run/publish.csv": "id,flux\n1234567890123456789,0.42\n",
        "run/private.csv": "name,source\nexample,/Users/synthetic/private.fits\n",
        "run/command.txt": "synthetic-secret-credential",
        "run/notes.json": "{\"prompt\":\"private background text\"}",
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let run = root.appendingPathComponent("run")
    let source = try FirstRunExampleService().create(.table, at: root.appendingPathComponent("example"))
    let capability = sampleCapability()
    var job = JobRecord(capability: capability, runDirectory: run.path)
    job.status = .succeeded
    job.requestInputPaths = source.inputPaths
    job.requestRawArguments = "private argument from another scope"
    job.artifacts = ArtifactDiscovery().discover(in: run.path)
    let service = RunProvenanceService()
    let start = await service.captureStart(
      request: .init(capabilityID: job.capabilityID, inputPaths: job.requestInputPaths, outputDirectory: run.path,
                     rawArguments: job.requestRawArguments),
      capability: capability, skillRoot: root.path, outputRootConfirmationUsed: false, secrets: []
    )
    let original = try service.write(start: start, job: job)
    let originalEvidence = try Data(contentsOf: original.url)
    job.artifacts.append(original)

    let packages = PortableRunPackageService()
    let destination = root.appendingPathComponent("portable.zip")
    let share = try #require(job.artifacts.first { $0.relativePath == "publish.csv" })
    let privateOutput = try #require(job.artifacts.first { $0.relativePath == "private.csv" })
    #expect(packages.fixtureCandidates(for: job).map(\.input) == [1])
    let exported = try packages.export(job: job, selection: .init(outputIDs: [share.id], fixtureIDs: [1]),
                                       to: destination, secrets: ["synthetic-secret-credential"])
    let archive = try Data(contentsOf: destination)
    var files = try PortableRunZIP.decode(archive)
    #expect(Set(files.keys) == [
      "manifest.json", "summary.json", "readme.md", "scripts/verify_package.py", "scripts/verify_tool.py",
      "fixtures/input-1.csv", "outputs/output-1.csv",
    ])
    #expect(files["outputs/output-1.csv"] == Data("id,flux\n1234567890123456789,0.42\n".utf8))
    #expect(!String(decoding: archive, as: UTF8.self).contains(root.path))
    #expect(!String(decoding: archive, as: UTF8.self).contains("private argument from another scope"))
    #expect(!String(decoding: archive, as: UTF8.self).contains("synthetic-secret-credential"))
    #expect(!String(decoding: archive, as: UTF8.self).contains("private background text"))
    let beforeReview = try FileManager.default.contentsOfDirectory(atPath: root.path).sorted()
    let verified = try packages.review(at: destination)
    #expect(verified.summary.sourceJobID == job.id)
    #expect(verified.includesSelectedData)
    #expect(verified.entries.map(\.sha256) == exported.entries.map(\.sha256))
    #expect(verified.dependencyWarnings(capabilities: [], environment: nil).contains {
      $0.contains("capability is missing")
    })
    #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).sorted() == beforeReview)
    #expect(try Data(contentsOf: original.url) == originalEvidence)
    #expect(try Data(contentsOf: destination) == archive)

    let omitted = root.appendingPathComponent("omitted.zip")
    let withoutData = try packages.export(job: job, selection: .init(), to: omitted, secrets: [])
    #expect(!withoutData.includesSelectedData)
    #expect(!withoutData.entries.contains { $0.kind == .syntheticFixture })
    let privateDestination = root.appendingPathComponent("private.zip")
    #expect(throws: PortableRunPackageService.Unavailable.unsafeContent) {
      try packages.export(job: job, selection: .init(outputIDs: [privateOutput.id]), to: privateDestination, secrets: [])
    }
    #expect(!FileManager.default.fileExists(atPath: privateDestination.path))
    #expect(throws: PortableRunPackageService.Unavailable.outputLocation) {
      try packages.export(job: job, selection: .init(), to: destination, secrets: [])
    }

    files["outputs/output-1.csv"] = Data("id,flux\n1234567890123456789,0.43\n".utf8)
    let changed = root.appendingPathComponent("changed.zip")
    try PortableRunZIP.encode(files).write(to: changed, options: .withoutOverwriting)
    #expect(throws: PortableRunPackageService.Unavailable.package) { try packages.review(at: changed) }
  }

  @Test
  func portableZIPKeepsBinaryBytesAndRejectsUnsupportedMemberNames() throws {
    let members = ["readme.md": Data("Verified members\n".utf8), "outputs/output-1.png": Data([0, 0x80, 0xFF, 0])]
    let canonical = try PortableRunZIP.encode(members)
    #expect(try PortableRunZIP.decode(canonical) == members)
    #expect(throws: PortableRunZIP.Invalid.archive) { try PortableRunZIP.decode(Data(canonical.dropLast())) }
    #expect(throws: PortableRunZIP.Invalid.archive) { try PortableRunZIP.encode(["outer/../summary.json": Data()]) }
    #expect(throws: PortableRunZIP.Invalid.archive) { try PortableRunZIP.encode(["/summary.json": Data()]) }
  }
}
