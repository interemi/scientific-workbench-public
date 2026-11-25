import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func measurementSynthesisSendsOnlyReviewedValuesAndResolvesModelSelectionsLocally() async throws {
    let fixture = try await measurementSynthesisFixture()
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    let recorder = RequestRecorder(responseBody: #"{"output_text":"{\"highlights\":[\"diagnostics-1\",\"measurements-1\"]}"}"#)
    let store = measurementSynthesisStore(job: fixture.job, client: CloudAIClient(dataLoader: recorder.load))
    store.selectResultArtifact(fixture.selected.id, for: fixture.job)
    let review = try await store.prepareMeasurementSynthesis(artifact: fixture.selected, jobID: fixture.job.id)
    #expect(await recorder.requests.isEmpty)
    #expect(review.userMessage.contains("19.375"))
    for withheld in ["21.75", "alternate.json", "local-observatory-token", "/Users/", fixture.job.id.uuidString] {
      #expect(!review.userMessage.contains(withheld))
    }

    let result = try await store.confirmMeasurementSynthesis(review)
    #expect(result.map(\.id) == ["diagnostics-1", "measurements-1"])
    #expect(result.map { $0.quantity.value } == [16, 19.375])
    #expect(result[1].quantity.unit == "mag")
    #expect(result[1].quantity.uncertainty == 0.125)
    #expect(result[1].pointer == "/results/measurement_summary/measurements/0")
    let requests = await recorder.requests
    #expect(requests.count == 1)
    let requestBody = try #require(requests.first?.httpBody)
    let payload = try #require(JSONSerialization.jsonObject(with: requestBody) as? [String: Any])
    #expect(payload["input"] as? String == review.userMessage)

    for answer in [
      #"{"highlights":["invented-1"]}"#,
      #"{"highlights":["measurements-1","measurements-1"]}"#,
      #"{"highlights":["measurements-1"],"value":999}"#,
    ] {
      let body = try JSONSerialization.data(withJSONObject: ["output_text": answer])
      let invalid = RequestRecorder(responseBody: String(decoding: body, as: UTF8.self))
      await #expect(throws: MeasurementSynthesisError.self) {
        try await MeasurementSynthesisService().synthesize(
          from: review, apiKey: "", client: CloudAIClient(dataLoader: invalid.load)
        )
      }
    }

    store.selectResultArtifact(fixture.primary.id, for: fixture.job)
    await #expect(throws: MeasurementSynthesisError.self) {
      try await store.confirmMeasurementSynthesis(review)
    }
    store.selectResultArtifact(fixture.selected.id, for: fixture.job)
    store.openAIModel = review.destination.model == "gpt-4o" ? "gpt-5.2" : "gpt-4o"
    await #expect(throws: MeasurementSynthesisError.self) {
      try await store.confirmMeasurementSynthesis(review)
    }
    #expect(await recorder.requests.count == 1)
  }

  @Test
  @MainActor
  func measurementSynthesisDiscardsRepliesWhenTheArtifactChangesInFlight() async throws {
    let fixture = try await measurementSynthesisFixture()
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    let recorder = RequestRecorder(responseBody: #"{"output_text":"{\"highlights\":[\"measurements-1\"]}"}"#)
    let source = fixture.selected.url
    let original = try Data(contentsOf: source)
    let client = CloudAIClient { request in
      try Data("changed after review".utf8).write(to: source, options: .atomic)
      return try await recorder.load(request)
    }
    let store = measurementSynthesisStore(job: fixture.job, client: client)
    store.selectResultArtifact(fixture.selected.id, for: fixture.job)
    let review = try await store.prepareMeasurementSynthesis(artifact: fixture.selected, jobID: fixture.job.id)
    await #expect(throws: MeasurementSynthesisError.self) { try await store.confirmMeasurementSynthesis(review) }
    #expect(await recorder.requests.count == 1)
    #expect(try Data(contentsOf: source) != original)
    await #expect(throws: MeasurementSynthesisError.self) {
      try await store.prepareMeasurementSynthesis(artifact: fixture.selected, jobID: fixture.job.id)
    }
    #expect(await recorder.requests.count == 1)
  }

  @MainActor
  private func measurementSynthesisStore(job: JobRecord, client: CloudAIClient) -> WorkbenchStore {
    let store = WorkbenchStore(loadSecrets: false, loadPersistedState: false, cloudAIClient: client)
    store.aiProvider = .openAI
    store.openAIAPIKey = "local-observatory-token"
    store.jobs = [job]
    store.selectedJobID = job.id
    return store
  }

  private func measurementSynthesisFixture() async throws -> (root: URL, job: JobRecord, primary: Artifact, selected: Artifact) {
    let base = """
      {
        "tool": "photometric_solution", "app_status": "WARNING", "status": "warning",
        "qa": {"status": "warning", "findings": ["Review single-night calibration."]},
        "results": {"measurement_summary": {
          "method": "Weighted least squares",
          "measurements": [{"label": "Zero point local-observatory-token /Users/private-observer/data", "value": 21.75,
                            "unit": "mag", "uncertainty": 0.125}],
          "diagnostics": [{"label": "Samples used", "value": 16, "unit": "count"}],
          "assumptions": []
        }}
      }
      """
    let alternate = base.replacingOccurrences(of: "21.75", with: "19.375")
    let root = try makeScenarioFixture(
      name: "measurement-synthesis", files: ["summary.json": base, "alternate.json": alternate]
    )
    let capability = CapabilityEntry(
      id: "photometric_solution", label: "Photometry", script: "scripts/photometric_solution.py", visibleBlock: "astronomy",
      kind: "supporting_tool", supportLevel: "stable", platform: "portable",
      requiresDatanalysis: true, preflightMode: "none", smokeTier: "core", shortDescription: "Synthetic evidence."
    )
    var job = JobRecord(capability: capability, runDirectory: root.path)
    job.status = .succeeded
    let source = Artifact(path: root.appendingPathComponent("summary.json").path, relativePath: "summary.json",
                          byteCount: Int64(base.utf8.count), artifactType: "summary_json")
    let selection = Artifact(path: root.appendingPathComponent("alternate.json").path, relativePath: "alternate.json",
                             byteCount: Int64(alternate.utf8.count), artifactType: "summary_json")
    job.artifacts = [source, selection]
    let service = RunProvenanceService()
    let capture = await service.captureStart(
      request: RunRequest(capabilityID: capability.id, inputPaths: [], outputDirectory: root.path, rawArguments: ""),
      capability: capability, skillRoot: root.path, outputRootConfirmationUsed: false, secrets: []
    )
    job.artifacts.append(try service.write(start: capture, job: job))
    return (root, job, source, selection)
  }
}
