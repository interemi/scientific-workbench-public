import Foundation

struct OptionalAstronomyBackendService {
  var runner = ProcessRunner()

  func refresh(
    skillRoot: String,
    pythonExecutable: String,
    stiltsCommand: String,
    stiltsJar: String,
    topcatCommand: String,
    topcatJar: String,
    aptCommand: String,
    aptPreferences: String
  ) async -> OptionalAstronomyBackendStatus {
    let envScript = URL(fileURLWithPath: skillRoot)
      .appendingPathComponent("scripts/datanalysis_env.py")
      .path
    let summaryURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("ScientificWorkbench-STILTS-\(UUID().uuidString).json")
    defer { try? FileManager.default.removeItem(at: summaryURL) }

    var arguments = [
      envScript,
      "run-tool",
      "external_astro_tools_preflight",
      "--probe",
      "--summary-json",
      summaryURL.path
    ]
    appendOption("--stilts-command", value: stiltsCommand, to: &arguments)
    appendOption("--stilts-jar", value: stiltsJar, to: &arguments)
    appendOption("--topcat-command", value: topcatCommand, to: &arguments)
    appendOption("--topcat-jar", value: topcatJar, to: &arguments)
    appendOption("--apt-command", value: aptCommand, to: &arguments)
    appendOption("--apt-preferences", value: aptPreferences, to: &arguments)

    let command = ProcessCommand(
      executable: pythonExecutable.isEmpty ? DefaultPaths.systemPython : pythonExecutable,
      arguments: arguments,
      workingDirectory: skillRoot,
      timeoutSeconds: 30,
      environmentPolicy: .restricted,
      environmentOverrides: SkillPythonEnvironment.overrides(forSkillRoot: skillRoot)
    )

    do {
      let result = try await runner.run(command)
      if let parsed = parse(result.stdout) {
        return parsed
      }
      return OptionalAstronomyBackendStatus(
        overallStatus: "failed",
        java: .unknown,
        stilts: .warning,
        topcat: .unknown,
        aptOverallStatus: "WARNING",
        aptCommand: .unknown,
        aptPreferences: .unknown,
        aptBatch: .unknown,
        summary: "The optional backend check returned unreadable output.",
        blockingMessage: result.stderr.isEmpty ? "No parseable JSON envelope was returned." : result.stderr,
        aptSummary: "APT readiness could not be read from the optional backend check.",
        aptBlockingMessage: result.stderr.isEmpty ? "No parseable JSON envelope was returned." : result.stderr,
        aptNextActions: ["Check the configured APT command and preferences paths."],
        nativeAlternativeCapabilityID: "catalog_workbench.crossmatch-sky",
        aptNativeAlternativeCapabilityIDs: ["inspect_fits", "photometry_noise_budget"],
        checkedAt: Date()
      )
    } catch {
      return OptionalAstronomyBackendStatus(
        overallStatus: "failed",
        java: .unknown,
        stilts: .warning,
        topcat: .unknown,
        aptOverallStatus: "WARNING",
        aptCommand: .unknown,
        aptPreferences: .unknown,
        aptBatch: .unknown,
        summary: "The optional backend check could not run.",
        blockingMessage: error.localizedDescription,
        aptSummary: "APT readiness could not be checked.",
        aptBlockingMessage: error.localizedDescription,
        aptNextActions: ["Check the skill path and Python environment, then retry the optional backend check."],
        nativeAlternativeCapabilityID: "catalog_workbench.crossmatch-sky",
        aptNativeAlternativeCapabilityIDs: ["inspect_fits", "photometry_noise_budget"],
        checkedAt: Date()
      )
    }
  }

  func parse(_ text: String) -> OptionalAstronomyBackendStatus? {
    guard
      let payload = JSONOutputExtractor.lastObject(
        in: text,
        matching: { $0["results"] is [String: Any] }
      ),
      let results = payload["results"] as? [String: Any],
      let capabilities = results["capabilities"] as? [String: Any]
    else {
      return nil
    }

    let javaReady = capabilities["java_ready"] as? Bool ?? false
    let stiltsReady = capabilities["stilts_ready"] as? Bool ?? false
    let topcatReady = capabilities["topcat_ready"] as? Bool ?? false
    let aptKeysPresent = capabilities["apt_command_ready"] != nil || capabilities["apt_batch_ready"] != nil
    let aptCommandReady = capabilities["apt_command_ready"] as? Bool ?? false
    let aptBatchReady = capabilities["apt_batch_ready"] as? Bool ?? false
    let aptPreferences = results["apt_preferences"] as? [String: Any]
    let aptPreferencesReady = aptPreferences?["found"] as? Bool ?? false
    let appStatus = payload["app_status"] as? String ?? payload["status"] as? String ?? "WARNING"
    let blocking = (results["blocking_findings"] as? [String]) ?? []
    let warnings = (results["warning_findings"] as? [String]) ?? []
    let alternative = ((results["native_alternatives"] as? [String: Any])?["stilts"] as? [String: Any])?["capability_id"] as? String
    let aptAlternative = ((results["native_alternatives"] as? [String: Any])?["apt"] as? [String: Any])?["capability_id"] as? String

    let summary: String
    if stiltsReady {
      summary = topcatReady
        ? "Java, STILTS, and TOPCAT are available. Reproducible operations should still use STILTS."
        : "Java and STILTS are ready. TOPCAT remains optional for interactive inspection."
    } else {
      summary = "STILTS/TOPCAT is unavailable. Core app workflows remain ready; use the native catalog crossmatch when it is equivalent."
    }
    let aptSummary: String
    let aptOverallStatus: String
    let aptNextActions: [String]
    if !aptKeysPresent {
      aptSummary = "APT readiness was not included in this backend report."
      aptOverallStatus = "unknown"
      aptNextActions = []
    } else if aptBatchReady {
      aptSummary = "Java, APT, and saved preferences are ready for an optional batch workflow."
      aptOverallStatus = "PASS"
      aptNextActions = ["Run APT only when compatibility with its saved GUI preferences is required."]
    } else {
      aptSummary = "APT batch mode is unavailable. Core app workflows remain ready; use native FITS and photometry tools when suitable."
      aptOverallStatus = "BLOCKED_CONTROLADO"
      aptNextActions = [
        "Configure APT.csh/APT.bat and save APT.pref before retrying.",
        "Use native FITS inspection or photometry preparation when APT compatibility is not required.",
      ]
    }
    let aptMessage = (blocking + warnings).first {
      let text = $0.localizedLowercase
      return text.contains("apt") || text.contains("preferences")
    }

    return OptionalAstronomyBackendStatus(
      overallStatus: appStatus,
      java: javaReady ? .ready : .unavailable,
      stilts: stiltsReady ? .ready : .unavailable,
      topcat: topcatReady ? .ready : .unavailable,
      aptOverallStatus: aptOverallStatus,
      aptCommand: aptKeysPresent ? (aptCommandReady ? .ready : .unavailable) : .unknown,
      aptPreferences: aptKeysPresent ? (aptPreferencesReady ? .ready : .unavailable) : .unknown,
      aptBatch: aptKeysPresent ? (aptBatchReady ? .ready : .unavailable) : .unknown,
      summary: summary,
      blockingMessage: blocking.first ?? warnings.first,
      aptSummary: aptSummary,
      aptBlockingMessage: aptMessage,
      aptNextActions: aptNextActions,
      nativeAlternativeCapabilityID: alternative ?? "catalog_workbench.crossmatch-sky",
      aptNativeAlternativeCapabilityIDs: [
        aptAlternative == "aperture_photometry" ? "inspect_fits" : aptAlternative,
        "photometry_noise_budget",
      ].compactMap(\.self),
      checkedAt: Date()
    )
  }

  private func appendOption(_ option: String, value: String, to arguments: inout [String]) {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    arguments.append(contentsOf: [option, trimmed])
  }
}
