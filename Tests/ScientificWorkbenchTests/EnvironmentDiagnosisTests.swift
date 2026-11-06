import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
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
