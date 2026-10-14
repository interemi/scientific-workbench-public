import Darwin
import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func ollamaPullUsesReviewedEndpointAndRejectsRemoteTargetsBeforeLaunching() async throws {
    let root = try makeFakeOllamaCLI(scriptBody: """
      #!/bin/sh
      printf '%s' "$OLLAMA_HOST"
      printf '%s' "$2" > "$(dirname "$0")/launched.txt"
      """)
    defer { try? FileManager.default.removeItem(at: root) }
    let marker = root.appendingPathComponent("launched.txt")
    let service = OllamaSetupService(pathEnvironment: root.path, pullTimeoutSeconds: 5)
    do {
      _ = try await service.pullModel("test-model", baseURL: "https://remote.example.invalid")
      Issue.record("A remote target must not launch the download client.")
    } catch OllamaSetupError.unsafeEndpoint { }
    #expect(!FileManager.default.fileExists(atPath: marker.path))

    for endpoint in ["http://127.0.0.1:0", "http://127.0.0.1:65536"] {
      do {
        _ = try await service.pullModel("test-model", baseURL: endpoint)
        Issue.record("An invalid port must not fall back to another download server.")
      } catch OllamaSetupError.invalidBaseURL { }
    }
    #expect(!FileManager.default.fileExists(atPath: marker.path))

    let result = try await service.pullModel("test-model",
      baseURL: "http://127.0.0.1:11435/proxy/api/chat")
    #expect(result.succeeded)
    #expect(result.stdout == "http://127.0.0.1:11435/proxy")
    #expect(try String(contentsOf: marker, encoding: .utf8) == "test-model")
    #expect(try OllamaEndpointPolicy.commandBaseURL(baseURL: nil) == "http://localhost:11434")
    #expect(try OllamaEndpointPolicy.commandBaseURL(baseURL: "http://[::1]:11435/api") == "http://[::1]:11435")
  }

  @Test
  @MainActor
  func preparingDownloadSendsNothingAndChangedModelOrEndpointRequiresNewReview() async throws {
    let root = try makeFakeOllamaCLI(scriptBody: """
      #!/bin/sh
      printf 'unexpected' > "$(dirname "$0")/launched.txt"
      """)
    defer { try? FileManager.default.removeItem(at: root) }
    let recorder = RequestRecorder(responseBody: #"{"models":[]}"#)
    let service = OllamaSetupService(pathEnvironment: root.path, dataLoader: recorder.load)
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Download-Review-\(UUID())")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults,
      loadPersistedState: false, ollamaSetupService: service)
    store.setModel("test-model", for: .ollama)
    store.setBaseURL("http://127.0.0.1:11435", for: .ollama)
    let original = try #require(store.prepareOllamaModelDownload())
    #expect(original.reviewDetail.contains("size unknown"))
    #expect(!store.isPullingOllamaModel)
    #expect(await recorder.requests.isEmpty)

    store.setBaseURL("http://127.0.0.1:11436", for: .ollama)
    await store.confirmOllamaModelDownload(original)
    #expect(store.ollamaSetupStatus.message.contains("nothing was downloaded"))
    let changedEndpoint = try #require(store.prepareOllamaModelDownload())
    store.setModel("another-model", for: .ollama)
    await store.confirmOllamaModelDownload(changedEndpoint)
    #expect(store.ollamaSetupStatus.message.contains("nothing was downloaded"))
    #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent("launched.txt").path))
    #expect(await recorder.requests.isEmpty)

    let busyRequest = try #require(store.prepareOllamaModelDownload())
    store.isPlanningAgentWorkflow = true
    await store.confirmOllamaModelDownload(busyRequest)
    #expect(store.ollamaSetupStatus.message.contains("active Scientific Workbench operation"))
    #expect(!store.isPullingOllamaModel)
    #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent("launched.txt").path))
    #expect(await recorder.requests.isEmpty)
    store.isPlanningAgentWorkflow = false

    store.setModel("--help", for: .ollama)
    #expect(store.prepareOllamaModelDownload() == nil)
    #expect(store.ollamaSetupStatus.message.contains("without spaces or command options"))
  }

  @Test
  @MainActor
  func failedOllamaDownloadRetainsErrorAfterSetupRecheck() async throws {
    let root = try makeFakeOllamaCLI(scriptBody: """
      #!/bin/sh
      printf 'synthetic download failure at %s' "$OLLAMA_HOST" >&2
      exit 7
      """)
    defer { try? FileManager.default.removeItem(at: root) }
    let recorder = RequestRecorder(responseBody: #"{"models":[]}"#)
    let service = OllamaSetupService(pathEnvironment: root.path,
      dataLoader: recorder.load, pullTimeoutSeconds: 5)
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Download-Failure-\(UUID())")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults,
      loadPersistedState: false, ollamaSetupService: service)
    store.setModel("test-model", for: .ollama)
    store.setBaseURL("http://127.0.0.1:11435", for: .ollama)
    let request = try #require(store.prepareOllamaModelDownload())
    await store.confirmOllamaModelDownload(request)

    #expect(!store.isPullingOllamaModel)
    #expect(store.ollamaSetupStatus.presentationState() == .downloadModel)
    #expect(store.ollamaSetupStatus.message.contains("exited with 7"))
    #expect(store.ollamaSetupStatus.message.contains("synthetic download failure at http://127.0.0.1:11435"))
    #expect(await recorder.requests.count == 1)
    #expect(await recorder.requests.first?.url?.absoluteString == "http://127.0.0.1:11435/api/tags")
  }

  @Test
  func ollamaModelProfilesExposeBalancedDefaultAndCustomMatching() {
    #expect(OllamaModelProfile.recommended == .balanced)
    #expect(OllamaModelProfile.allCases.map(\.model) == ["qwen3:1.7b", "qwen3:4b-instruct", "qwen3:8b"])
    #expect(OllamaModelProfile.matching(model: " qwen3:4b-instruct ") == .balanced)
    #expect(OllamaModelProfile.matching(model: "custom-local-model") == nil)
    #expect(OllamaModelProfile.balanced.detailText.contains("fit on this Mac is not guaranteed"))
  }

  @Test
  func ollamaPresentationExplainsUnavailableAndActiveStatesWithoutClaimingReadiness() {
    var status = OllamaSetupStatus.unknown(model: "test-model")
    #expect(status.presentationState() == .unchecked)
    #expect(status.badgeTitle == "check")
    #expect(status.detailLines == ["Local AI setup has not been checked."])
    #expect(status.presentationState().guidance(model: status.targetModel).contains("Deterministic planning"))

    status.checkedAt = Date()
    #expect(status.presentationState() == .install)
    status.cliPath = "/isolated/ollama"
    #expect(status.presentationState() == .startServer)
    status.serverReachable = true
    status.cliPath = nil
    #expect(status.presentationState() == .downloadRequiresCLI)
    status.cliPath = "/isolated/ollama"
    #expect(status.presentationState() == .downloadModel)
    #expect(status.presentationState().guidance(model: status.targetModel).contains("test-model"))
    #expect(status.presentationState(isDownloading: true) == .downloadingModel)
    #expect(status.presentationState(isDownloading: true, isCancellationRequested: true) == .cancellingDownload)

    status.installedModels = ["test-model"]
    #expect(status.presentationState() == .ready)
    #expect(status.presentationState().title(model: status.targetModel).contains("last check"))
    status.cliPath = nil
    #expect(status.presentationState() == .ready)
  }

  @Test
  func ollamaSetupReportsReachableServerWithoutCLIAccurately() async {
    let service = OllamaSetupService(
      pathEnvironment: "",
      fileExists: { _ in false },
      dataLoader: { request in
        let response = HTTPURLResponse(
          url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil
        )!
        return (Data(#"{"models":[{"name":"test-model"}]}"#.utf8), response)
      }
    )
    let status = await service.status(baseURL: "http://localhost:11434", model: "test-model")
    #expect(status.serverReachable)
    #expect(status.cliPath == nil)
    #expect(status.presentationState() == .ready)
    #expect(status.message.contains("in-app downloads still need the Ollama CLI"))

    let missing = await service.status(baseURL: "http://localhost:11434", model: "missing-model")
    #expect(missing.presentationState() == .downloadRequiresCLI)
    #expect(missing.message.contains("CLI is needed to download it here"))
  }

  @Test
  func ollamaSetupServiceLocatesCLIAndParsesInstalledModels() async throws {
    let recorder = RequestRecorder(
      responseBody: #"{"models":[{"name":"qwen3:4b-instruct"},{"name":"llama3.2"}]}"#
    )
    let service = OllamaSetupService(
      pathEnvironment: "/custom/bin",
      fileExists: { $0 == "/custom/bin/ollama" },
      dataLoader: { request in
        try await recorder.load(request)
      }
    )

    let status = await service.status(
      baseURL: "http://localhost:11434",
      model: "qwen3:4b-instruct"
    )

    let request = try #require(await recorder.requests.first)
    #expect(service.locateCLI() == "/custom/bin/ollama")
    #expect(status.serverReachable == true)
    #expect(status.modelInstalled == true)
    #expect(status.badgeTitle == "ok")
    #expect(request.url?.absoluteString == "http://localhost:11434/api/tags")
    #expect(request.timeoutInterval == 3)
  }

  @Test
  func ollamaSetupServiceReportsMissingInstallBeforeNetworkDetails() async {
    let service = OllamaSetupService(
      pathEnvironment: "",
      fileExists: { _ in false },
      dataLoader: { _ in
        throw URLError(.cannotConnectToHost)
      }
    )

    let status = await service.status(
      baseURL: "http://localhost:11434",
      model: "qwen3:4b-instruct"
    )

    #expect(status.cliPath == nil)
    #expect(status.serverReachable == false)
    #expect(status.badgeTitle == "install")
    #expect(status.message.contains("Install Ollama"))
  }

  @Test
  func ollamaSetupUnreachableEndpointDoesNotAssumeServerIsStopped() async {
    let service = OllamaSetupService(
      pathEnvironment: "/isolated/bin",
      fileExists: { $0 == "/isolated/bin/ollama" },
      dataLoader: { _ in throw URLError(.cannotConnectToHost) }
    )

    let status = await service.status(
      baseURL: "http://127.0.0.1:65534",
      model: "qwen3:4b-instruct"
    )

    #expect(status.presentationState() == .startServer)
    #expect(status.message.contains("configured local endpoint could not be verified"))
    #expect(status.message.contains("start Ollama if needed"))
    #expect(status.presentationState().guidance(model: status.targetModel).contains("Check its address"))
  }

  @Test
  func ollamaSetupServiceRejectsRemoteEndpointBeforeAnyNetworkRequest() async {
    let recorder = RequestRecorder(responseBody: #"{"models":[]}"#)
    let service = OllamaSetupService(
      pathEnvironment: "/custom/bin",
      fileExists: { $0 == "/custom/bin/ollama" },
      dataLoader: { request in
        try await recorder.load(request)
      }
    )

    let status = await service.status(
      baseURL: "https://ollama.example.invalid:11434",
      model: "qwen3:4b-instruct"
    )

    #expect(await recorder.requests.isEmpty)
    #expect(!status.serverReachable)
    #expect(status.message.localizedCaseInsensitiveContains("loopback"))
    #expect(status.message.contains("ollama.example.invalid"))
  }

  @Test
  func ollamaPullUsesRestrictedEnvironmentAndCapturesLargeOutput() async throws {
    let root = try makeFakeOllamaCLI(
      scriptBody: """
      #!/bin/sh
      if [ -n "${OPENAI_API_KEY+x}" ] || [ -n "${UNLISTED_FLAG+x}" ] || \
         [ -n "${CUSTOM_ALLOWED+x}" ] || [ -n "${SSH_AUTH_SOCK+x}" ] || \
         [ -n "${GITHUB_PAT+x}" ] || [ -n "${HTTP_COOKIE+x}" ] || \
         [ -n "${APP_SESSION_ID+x}" ] || [ -n "${DATABASE_URL+x}" ]; then
        printf 'restricted environment leaked\n' >&2
        exit 91
      fi
      if [ "$1" != "pull" ] || [ "$2" != "test-model" ]; then
        printf 'unexpected arguments\n' >&2
        exit 92
      fi
      /usr/bin/python3 -c 'import sys; sys.stdout.write("o" * 200000 + "\\nOLLAMA_STDOUT_DONE\\n"); sys.stderr.write("e" * 200000 + "\\nOLLAMA_STDERR_DONE\\n")'
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let runner = ProcessRunner(parentEnvironment: {
      [
        "HOME": "/safe/home",
        "PATH": "/usr/bin:/bin",
        "SCIENTIFIC_WORKBENCH_INHERIT_PROCESS_ENV": "1",
        "SCIENTIFIC_WORKBENCH_ALLOW_PROCESS_ENV": "CUSTOM_ALLOWED,SSH_AUTH_SOCK",
        "OPENAI_API_KEY": "sk-must-not-leak",
        "UNLISTED_FLAG": "must-not-leak",
        "CUSTOM_ALLOWED": "must-not-leak",
        "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
        "GITHUB_PAT": "github-pat-must-not-leak",
        "HTTP_COOKIE": "cookie-must-not-leak",
        "APP_SESSION_ID": "session-must-not-leak",
        "DATABASE_URL": "postgres://user:password@database.example/science"
      ]
    })
    let service = OllamaSetupService(
      pathEnvironment: root.path,
      runner: runner,
      pullTimeoutSeconds: 5
    )

    let result = try await service.pullModel("test-model")

    #expect(result.exitCode == 0)
    #expect(result.stdout.contains("OLLAMA_STDOUT_DONE"))
    #expect(result.stderr.contains("OLLAMA_STDERR_DONE"))
    #expect(result.stdout.utf8.count > 200_000)
    #expect(result.stderr.utf8.count > 200_000)
  }

  @Test
  func ollamaPullTimesOutThroughTheHardenedRunner() async throws {
    let root = try makeFakeOllamaCLI(
      scriptBody: """
      #!/bin/sh
      sleep 30
      """
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let service = OllamaSetupService(
      pathEnvironment: root.path,
      pullTimeoutSeconds: 0.3
    )
    let startedAt = Date()

    do {
      _ = try await service.pullModel("test-model")
      Issue.record("Expected the Ollama pull to time out.")
    } catch OllamaSetupError.timedOut(let seconds) {
      #expect(seconds == 0.3)
      #expect(Date().timeIntervalSince(startedAt) < 3)
    } catch {
      Issue.record("Unexpected timeout error: \(error)")
    }
  }

  @Test
  func cancellingOllamaPullTerminatesItsProcessGroup() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-OllamaTree-\(UUID().uuidString)", isDirectory: true)
    let parentPIDURL = root.appendingPathComponent("parent.pid")
    let childPIDURL = root.appendingPathComponent("child.pid")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let executable = root.appendingPathComponent("ollama")
    let scriptBody = """
    #!/bin/sh
    printf '%s' "$$" > "\(parentPIDURL.path)"
    /bin/sleep 30 &
    printf '%s' "$!" > "\(childPIDURL.path)"
    wait
    """
    try scriptBody.write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: NSNumber(value: Int16(0o755))],
      ofItemAtPath: executable.path
    )

    let service = OllamaSetupService(
      pathEnvironment: root.path,
      pullTimeoutSeconds: 30
    )
    let task = Task {
      try await service.pullModel("test-model")
    }

    let parentPID = try await waitForOllamaFixturePID(at: parentPIDURL)
    let childPID = try await waitForOllamaFixturePID(at: childPIDURL)
    #expect(getpgid(parentPID) == parentPID)
    #expect(getpgid(childPID) == parentPID)

    task.cancel()
    do {
      _ = try await task.value
      Issue.record("Expected the Ollama pull task to be cancelled.")
    } catch OllamaSetupError.cancelled {
      // Expected.
    } catch {
      Issue.record("Unexpected cancellation error: \(error)")
    }

    #expect(await ollamaFixtureProcessesExited([parentPID, childPID]))
  }

  private func makeFakeOllamaCLI(scriptBody: String) throws -> URL {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-OllamaCLI-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    let executable = root.appendingPathComponent("ollama")
    try scriptBody.write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: NSNumber(value: Int16(0o755))],
      ofItemAtPath: executable.path
    )
    return root
  }

  private func waitForOllamaFixturePID(at url: URL) async throws -> pid_t {
    let deadline = Date().addingTimeInterval(5)
    while Date() < deadline {
      if let text = try? String(contentsOf: url, encoding: .utf8),
         let pid = pid_t(text.trimmingCharacters(in: .whitespacesAndNewlines)),
         pid > 1 {
        return pid
      }
      try await Task.sleep(nanoseconds: 50_000_000)
    }
    throw OllamaFixtureError.processDidNotStart
  }

  private func ollamaFixtureProcessesExited(_ pids: [pid_t]) async -> Bool {
    let deadline = Date().addingTimeInterval(4)
    while Date() < deadline {
      if pids.allSatisfy({ !ollamaFixtureProcessExists($0) }) {
        return true
      }
      try? await Task.sleep(nanoseconds: 50_000_000)
    }
    return pids.allSatisfy { !ollamaFixtureProcessExists($0) }
  }

  private func ollamaFixtureProcessExists(_ pid: pid_t) -> Bool {
    if Darwin.kill(pid, 0) == 0 {
      return true
    }
    return errno == EPERM
  }

}

private enum OllamaFixtureError: Error {
  case processDidNotStart
}
