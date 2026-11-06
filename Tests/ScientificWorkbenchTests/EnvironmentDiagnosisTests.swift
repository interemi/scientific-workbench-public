import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  @MainActor
  func overlappingAutomaticAndManualEnvironmentChecksShareOneProbe() async throws {
    let root = try makeEnvironmentProbeFixture(holdStatus: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let suite = "Scientific-Workbench-Environment-Coalescing-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set(root.path, forKey: "skillRootPath")
    defaults.set("/bin/sh", forKey: "pythonExecutable")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)

    let automatic = Task { await store.startupRefresh() }
    defer { automatic.cancel() }
    try await waitForEnvironmentProbe(at: root.appendingPathComponent("probe.log"))
    var manualInvoked = false
    let manual = Task {
      manualInvoked = true
      await store.refreshEnvironment()
    }
    defer { manual.cancel() }
    while !manualInvoked { await Task.yield() }
    try Data().write(to: root.appendingPathComponent("release-status"))
    await automatic.value
    await manual.value

    let invocations = try environmentProbeInvocations(at: root)
    #expect(invocations == ["status", "doctor"])
    #expect(store.environmentDiagnosis.coreReady == true)
    #expect(!store.isCheckingEnvironment)
  }

  @Test
  @MainActor
  func environmentCheckReusesFreshResultsExpiresAndRechecksExplicitly() async throws {
    let root = try makeEnvironmentProbeFixture()
    defer { try? FileManager.default.removeItem(at: root) }
    let suite = "Scientific-Workbench-Environment-Expiry-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set(root.path, forKey: "skillRootPath")
    defaults.set("/bin/sh", forKey: "pythonExecutable")
    let store = WorkbenchStore(
      loadSecrets: false, defaults: defaults, loadPersistedState: false,
      environmentCheckLifetime: .seconds(1)
    )

    await store.startupRefresh()
    let originalReport = store.environmentStatus
    await store.startupRefresh()
    #expect(try environmentProbeInvocations(at: root) == ["status", "doctor"])
    #expect(store.environmentStatus == originalReport)
    #expect(store.environmentCheckState == .current)

    await store.refreshEnvironment()
    #expect(try environmentProbeInvocations(at: root) == ["status", "doctor", "status", "doctor"])
    #expect(store.environmentCheckState == .current)
    let clock = ContinuousClock()
    let deadline = clock.now.advanced(by: .seconds(4))
    while store.environmentCheckState != .expired, clock.now < deadline {
      try await Task.sleep(for: .milliseconds(20))
    }
    #expect(store.environmentCheckState == .expired)
    #expect(store.environmentSummaryStatus == "expired")
    #expect(store.environmentDiagnosis.coreReady == true)
    #expect(store.setupChecklistItems.first { $0.id == "environment" }?.state == .action)
    #expect(try environmentProbeInvocations(at: root).count == 4)

    await store.startupRefresh()
    #expect(try environmentProbeInvocations(at: root).count == 6)
    #expect(store.environmentCheckState == .current)
  }

  @Test
  @MainActor
  func changingPythonAndSkillRootInvalidatesChecksAndRetiresTheOldProbe() async throws {
    let oldRoot = try makeEnvironmentProbeFixture(holdStatus: true)
    let newRoot = try makeEnvironmentProbeFixture()
    defer {
      try? FileManager.default.removeItem(at: oldRoot)
      try? FileManager.default.removeItem(at: newRoot)
    }
    let suite = "Scientific-Workbench-Environment-Invalidation-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set(oldRoot.path, forKey: "skillRootPath")
    defaults.set("/bin/sh", forKey: "pythonExecutable")
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults, loadPersistedState: false)

    let oldCheck = Task { await store.refreshEnvironment() }
    defer { oldCheck.cancel() }
    try await waitForEnvironmentProbe(at: oldRoot.appendingPathComponent("probe.log"))
    store.pythonExecutable = "/usr/bin/false"
    #expect(store.environmentCheckState == .configurationChanged)
    #expect(store.environmentDiagnosis == .unknown)
    store.skillRootPath = newRoot.path
    store.pythonExecutable = "/bin/sh"
    await store.refreshEnvironment()
    await oldCheck.value

    #expect(try environmentProbeInvocations(at: oldRoot) == ["status"])
    #expect(try environmentProbeInvocations(at: newRoot) == ["status", "doctor"])
    #expect(store.environmentStatus.skillRoot == newRoot.path)
    #expect(store.environmentDiagnosis.coreReady == true)
    store.pythonExecutable = "/bin/sh"
    #expect(store.environmentCheckState == .current)

    store.skillRootPath = oldRoot.path
    #expect(store.environmentStatus == .unknown(skillRoot: oldRoot.path))
    #expect(store.environmentDiagnosis == .unknown)
    store.skillRootPath = newRoot.path
    await store.refreshEnvironment()
    await store.reloadRegistry()
    #expect(store.environmentCheckState == .configurationChanged)
    #expect(store.environmentDiagnosis == .unknown)
    #expect(try environmentProbeInvocations(at: newRoot).count == 4)
  }

  private func makeEnvironmentProbeFixture(holdStatus: Bool = false) throws -> URL {
    var files = ["scripts/datanalysis_env.py": """
    #!/bin/sh
    printf '%s\\n' "$1" >> probe.log
    case "$1" in
      status)
        remaining=100
        while [ -f hold-status ] && [ ! -f release-status ]; do
          [ "$remaining" -gt 0 ] || exit 9
          remaining=$((remaining - 1))
          /bin/sleep 0.05
        done
        printf '%s\\n' '{"selected_python":"/synthetic/python"}'
        ;;
      doctor)
        printf '%s\\n' '{"capabilities":{"core_ready":true,"full_ready":false},"environment":{"python_executable":"/synthetic/python","python_version":"3.11"}}'
        ;;
      *) exit 8 ;;
    esac
    """]
    if holdStatus { files["hold-status"] = "" }
    return try makeScenarioFixture(name: "environment-refresh", files: files)
  }

  private func waitForEnvironmentProbe(at url: URL) async throws {
    let clock = ContinuousClock()
    let deadline = clock.now.advanced(by: .seconds(4))
    while !FileManager.default.fileExists(atPath: url.path), clock.now < deadline {
      try await Task.sleep(for: .milliseconds(10))
    }
    try #require(FileManager.default.fileExists(atPath: url.path))
  }

  private func environmentProbeInvocations(at root: URL) throws -> [String] {
    try String(contentsOf: root.appendingPathComponent("probe.log"), encoding: .utf8)
      .split(separator: "\n").map(String.init)
  }

  @Test
  func environmentDiagnosisKeepsCoreAndFullReadinessSeparate() throws {
    let report = """
    diagnostic prefix
    {
      "capabilities": {"core_ready": true, "full_ready": false},
      "environment": {"python_executable": "~/core/datanalysis/bin/python", "python_version": "3.11.15"},
      "core_modules": {"missing": []},
      "optional_groups": {
        "notebook_runtime": {"label": "Notebook runtime", "missing": ["nbclient", "ipykernel"]},
        "astronomy_extras": {"label": "Astronomy extras", "missing": ["specutils"]},
        "documents_ocr": {"label": "Document OCR", "missing": []}
      }
    }
    """
    let diagnosis = try #require(
      EnvironmentDiagnosis.parse(report, selectedPython: "~/core/datanalysis/bin/python")
    )
    #expect(diagnosis.status == "warning")
    #expect(diagnosis.coreReady == true)
    #expect(diagnosis.fullReady == false)
    #expect(diagnosis.pythonVersion == "3.11.15")
    #expect(diagnosis.missingCoreModules.isEmpty)
    #expect(diagnosis.missingOptionalGroups.map(\.id) == ["astronomy_extras", "notebook_runtime"])
    #expect(diagnosis.missingOptionalGroups[1].modules == ["ipykernel", "nbclient"])
  }

  @Test
  func environmentDiagnosisDoesNotInventReadinessFromInvalidOutput() {
    #expect(EnvironmentDiagnosis.parse("status: ok", selectedPython: nil) == nil)
    let unavailable = EnvironmentDiagnosis.unavailable(
      "The report could not be parsed.",
      selectedPython: "/selected/python"
    )
    #expect(unavailable.coreReady == nil)
    #expect(unavailable.status == "failed")
  }

  @Test
  func failedDiagnosticProcessCannotReportCoreReady() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("swb-diagnosis-\(UUID().uuidString)", isDirectory: true)
    let scripts = root.appendingPathComponent("scripts", isDirectory: true)
    try FileManager.default.createDirectory(at: scripts, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let fakeDoctor = scripts.appendingPathComponent("datanalysis_env.py")
    try """
    #!/bin/sh
    printf '%s\\n' '{"capabilities":{"core_ready":true,"full_ready":true},"environment":{"python_version":"3.11"}}'
    exit 7
    """.write(to: fakeDoctor, atomically: true, encoding: .utf8)

    let diagnosis = await SkillEnvironmentService().diagnose(
      skillRoot: root.path,
      pythonExecutable: "/bin/sh",
      selectedPython: "/selected/python"
    )
    #expect(diagnosis.status == "failed")
    #expect(diagnosis.coreReady == nil)
    #expect(diagnosis.selectedPython == "/selected/python")
  }

  @Test
  func repairPlanNamesAUniqueNewDestinationAndMakesInstallationExplicit() throws {
    let identifier = try #require(UUID(uuidString: "12345678-1234-1234-1234-123456789ABC"))
    let plan = EnvironmentRepairPlan.make(
      profile: .core,
      identifier: identifier,
      homeDirectory: URL(fileURLWithPath: "/Users/example"),
      isAppleSilicon: true,
      macOSMajorVersion: 15
    )
    #expect(plan.destination == "/Users/example/Library/Application Support/Scientific Workbench/environments/core-12345678-1234-1234-1234-123456789abc/datanalysis")
    #expect(plan.usesReviewedLock)
    #expect(plan.previewCommand.contains("--locked"))
    #expect(plan.previewCommand.contains("--destination '\(plan.destination)'"))
    #expect(!plan.previewCommand.contains("--install"))
    #expect(plan.installCommand == plan.previewCommand + " --install")

    let intelPlan = EnvironmentRepairPlan.make(
      profile: .full,
      identifier: identifier,
      homeDirectory: URL(fileURLWithPath: "/Users/example"),
      isAppleSilicon: false,
      macOSMajorVersion: 15
    )
    #expect(!intelPlan.usesReviewedLock)
    #expect(!intelPlan.previewCommand.contains("--locked"))

    let quotedPlan = EnvironmentRepairPlan.make(
      profile: .core,
      identifier: identifier,
      homeDirectory: URL(fileURLWithPath: "/Users/O'Neil"),
      isAppleSilicon: true,
      macOSMajorVersion: 15
    )
    #expect(quotedPlan.previewCommand.contains("/Users/O'\\''Neil/"))
  }
}
