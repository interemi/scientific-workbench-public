import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func optionalAstronomyBackendParserTreatsMissingSTILTSAsControlledBlock() throws {
    let payload = """
    {
      "tool": "external_astro_tools_preflight",
      "status": "blocked",
      "app_status": "BLOCKED_CONTROLADO",
      "results": {
        "capabilities": {
          "java_ready": true,
          "topcat_ready": false,
          "stilts_ready": false,
          "apt_command_ready": false,
          "apt_batch_ready": false
        },
        "blocking_findings": [
          "Optional backend unavailable: STILTS is required for the requested workflow."
        ],
        "warning_findings": [
          "APT batch command is not available."
        ],
        "apt_preferences": {
          "found": false
        },
        "native_alternatives": {
          "stilts": {
            "capability_id": "catalog_workbench.crossmatch-sky"
          }
        }
      }
    }
    """

    let status = try #require(
      OptionalAstronomyBackendService().parse(
        "diagnostic {\"phase\":\"preflight\"}\n" + payload
      )
    )
    #expect(status.overallStatus == "BLOCKED_CONTROLADO")
    #expect(status.java == .ready)
    #expect(status.stilts == .unavailable)
    #expect(status.topcat == .unavailable)
    #expect(status.aptOverallStatus == "BLOCKED_CONTROLADO")
    #expect(status.aptCommand == .unavailable)
    #expect(status.aptPreferences == .unavailable)
    #expect(status.aptBatch == .unavailable)
    #expect(status.aptNextActions.contains { $0.contains("APT.pref") })
    #expect(status.nativeAlternativeCapabilityID == "catalog_workbench.crossmatch-sky")
    #expect(status.blockingMessage?.contains("Optional backend unavailable") == true)
  }

  @Test
  func optionalAstronomyBackendParserReportsReadyCommands() throws {
    let payload = """
    {
      "tool": "external_astro_tools_preflight",
      "status": "ok",
      "app_status": "PASS",
      "results": {
        "capabilities": {
          "java_ready": true,
          "topcat_ready": true,
          "stilts_ready": true,
          "apt_command_ready": true,
          "apt_batch_ready": true
        },
        "apt_preferences": {
          "found": true
        },
        "blocking_findings": [],
        "warning_findings": [],
        "native_alternatives": {}
      }
    }
    """

    let status = try #require(OptionalAstronomyBackendService().parse(payload))
    #expect(status.overallStatus == "PASS")
    #expect(status.java == .ready)
    #expect(status.stilts == .ready)
    #expect(status.topcat == .ready)
    #expect(status.aptOverallStatus == "PASS")
    #expect(status.aptCommand == .ready)
    #expect(status.aptPreferences == .ready)
    #expect(status.aptBatch == .ready)
  }

  @Test
  func optionalAstronomyBackendParserReportsPartialOptionalReadinessWithoutBlockingPanel() throws {
    let payload = """
    {
      "tool": "external_astro_tools_preflight",
      "status": "warning",
      "app_status": "WARNING",
      "results": {
        "capabilities": {
          "java_ready": true,
          "topcat_ready": false,
          "stilts_ready": false,
          "apt_command_ready": true,
          "apt_batch_ready": false
        },
        "apt_preferences": {
          "found": false
        },
        "blocking_findings": [],
        "warning_findings": [
          "STILTS is not available; use catalog_workbench.py for small/medium Python crossmatches or install STILTS for large/VO workflows.",
          "APT was found, but batch mode depends on a saved APT.pref preferences file."
        ],
        "native_alternatives": {
          "apt": {
            "capability_id": "aperture_photometry"
          }
        }
      }
    }
    """

    let status = try #require(OptionalAstronomyBackendService().parse(payload))
    #expect(status.overallStatus == "WARNING")
    #expect(status.java == .ready)
    #expect(status.stilts == .unavailable)
    #expect(status.topcat == .unavailable)
    #expect(status.blockingMessage?.contains("STILTS is not available") == true)
    #expect(status.aptOverallStatus == "BLOCKED_CONTROLADO")
    #expect(status.aptCommand == .ready)
    #expect(status.aptPreferences == .unavailable)
    #expect(status.aptBatch == .unavailable)
    #expect(status.aptBlockingMessage?.contains("APT.pref") == true)
    #expect(status.aptNativeAlternativeCapabilityIDs.contains("inspect_fits"))
  }

  @Test
  @MainActor
  func optionalAstronomyBackendNativeAlternativeSelectsCatalogWorkbench() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.capabilities = [
      CapabilityEntry(
        id: "catalog_workbench.crossmatch-sky",
        label: "catalog_workbench.py crossmatch-sky",
        script: "scripts/catalog_workbench.py",
        visibleBlock: "notebooks + cross-domain",
        kind: "supporting_tool",
        supportLevel: "stable",
        platform: "portable",
        requiresDatanalysis: true,
        preflightMode: "none",
        smokeTier: "core",
        shortDescription: "Native sky crossmatch."
      )
    ]

    store.useNativeCatalogAlternative()

    #expect(store.selectedCapabilityID == "catalog_workbench.crossmatch-sky")
    #expect(store.selectedSection == .capabilities)
  }

  @Test
  func controlledBackendEnvelopeResolvesToBlockedJobState() {
    #expect(
      JobStatus.resolved(
        exitCode: 2,
        envelopeStatus: "blocked",
        appStatus: "BLOCKED_CONTROLADO"
      ) == .blocked
    )
    #expect(
      JobStatus.resolved(
        exitCode: 1,
        envelopeStatus: "fail",
        appStatus: "FAIL"
      ) == .failed
    )
  }

  @Test
  @MainActor
  func optionalAstronomyBackendNativeAPTAlternativeSelectsFitsInspection() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.capabilities = [
      CapabilityEntry(
        id: "inspect_fits",
        label: "inspect_fits.py",
        script: "scripts/inspect_fits.py",
        visibleBlock: "astronomy observational",
        kind: "golden_path",
        supportLevel: "stable",
        platform: "portable",
        requiresDatanalysis: true,
        preflightMode: "none",
        smokeTier: "core",
        shortDescription: "Native FITS inspection."
      )
    ]

    store.useNativeAPTAlternative()

    #expect(store.selectedCapabilityID == "inspect_fits")
    #expect(store.selectedSection == .capabilities)
  }

  @Test
  @MainActor
  func optionalAstronomyBackendPersistsAPTPaths() {
    let suite = "Scientific-Workbench-Tests-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    let store = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )
    store.aptCommand = "/opt/apt/APT.csh"
    store.aptPreferences = "/tmp/APT.pref"
    store.persistSettings()

    let restored = WorkbenchStore(
      loadSecrets: false,
      defaults: defaults,
      loadPersistedState: false
    )

    #expect(restored.aptCommand == "/opt/apt/APT.csh")
    #expect(restored.aptPreferences == "/tmp/APT.pref")
  }
}
