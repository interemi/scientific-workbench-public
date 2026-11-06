import SwiftUI

struct SettingsView: View {
  @ObservedObject var store: WorkbenchStore

  var body: some View {
    ScrollViewReader { proxy in
      settingsForm
        .onAppear {
          guard let destination = store.settingsRecoverySection else { return }
          proxy.scrollTo(destination, anchor: .top)
          store.settingsRecoverySection = nil
        }
    }
  }

  private var settingsForm: some View {
    Form {
      Section("Setup Checklist") {
        SetupChecklistCard(store: store, compact: true, showActions: false)
      }

      Section("Installation Profiles") {
        Text("Start with Core. Install Full in a separate new Python environment only when your chosen workflow needs its additional packages. Switching the Python path does not update or remove an existing environment.")
          .font(.callout)

        InstallationProfileCard(
          title: "Core · recommended start",
          icon: "checkmark.circle",
          scope: "Five synthetic examples; common table, FITS, and document workflows. No Ollama model or cloud account is needed for deterministic runs.",
          installation: "32 locked Python runtime requirements; about 455 MiB installed on the development Mac. Reviewed lock: Apple Silicon, Python 3.11, macOS 14 or later."
        )
        InstallationProfileCard(
          title: "Full · add only when needed",
          icon: "square.stack.3d.up",
          scope: "Includes Core and adds Python packages for advanced notebook, presentation, SQL, OCR, and scientific routes. A working Core environment does not establish Full readiness.",
          installation: "200 locked Python runtime requirements plus 3 build tools; about 1.43 GiB installed on the development Mac. Reviewed lock: Apple Silicon, Python 3.11, macOS 15 or later."
        )

        Text("The disk figures are one measurement from 2026-10-03, not download sizes or a promise for another Mac. Intel uses an unpinned compatibility route; check the installation guide before choosing it.")
          .font(.caption)
          .foregroundStyle(.secondary)

        Label("Neither profile installs Ollama models, TeX, LibreOffice, IRAF, Keynote, APT, or TEAREDUCE. Set up an external tool only for a route that requires it; a missing dependency must remain visible as a block or warning.", systemImage: "puzzlepiece.extension")
          .font(.callout)

        HStack {
          Button("Check Core and Full readiness") {
            store.searchText = ""
            store.openOptionalCapability("env_doctor")
          }
          .accessibilityIdentifier("settings.open-profile-diagnostic")
          .help("Opens the environment diagnostic; run it to inspect missing packages and optional backends without changing an environment.")

          Button("Open Installation Guide") {
            store.openUserGuide()
          }
          .disabled(store.userGuideURL == nil)
        }
        Text("The diagnostic opens in Capabilities and runs only after you select Run Capability. The bundled user guide and source INSTALL.md explain exact commands, supported locks, and recovery steps.")
          .font(.caption)
          .foregroundStyle(.secondary)
      }

      Section("Environment Diagnosis") {
        EnvironmentDiagnosisView(store: store)
      }
      .id(SettingsRecoverySection.environment)

      Section("Paths") {
        HStack {
          TextField("Mother skill root", text: $store.skillRootPath)
          Button("Choose") {
            store.chooseDirectory(assignTo: \.skillRootPath)
          }
        }
        Text("Scientific Workbench discovers the astro, documents, notebooks, and maintainer child skills next to this mother skill.")
          .font(.caption)
          .foregroundStyle(.secondary)
        HStack {
          TextField("Output root", text: $store.outputRootPath)
          Button("Choose") {
            store.chooseDirectory(assignTo: \.outputRootPath)
          }
        }
        outputRootSafetyNotice
        if let notice = store.legacyWorkspaceNotice {
          Text(notice)
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        HStack {
          TextField("Python executable", text: $store.pythonExecutable)
          Button("Choose") {
            store.choosePythonExecutable()
          }
        }
      }
      .id(SettingsRecoverySection.paths)

      Section("Behavior") {
        CapabilityTimeoutControl(minutes: $store.externalProcessTimeoutMinutes)
        Text("Maximum time for each capability process. The 30-minute default is conservative; long scientific tools may need a higher value.")
          .font(.caption)
          .foregroundStyle(.secondary)

        Button("Save Settings") {
          store.persistSettings()
        }
        Button("Reload Registry") {
          Task { await store.reloadRegistry() }
        }
        Button("Refresh Environment") {
          Task { await store.refreshEnvironment() }
        }
      }
      .id(SettingsRecoverySection.behavior)

      Section("Optional Astronomy Backends") {
        OptionalAstronomyBackendsView(store: store)
      }
      .id(SettingsRecoverySection.optionalBackends)

      Section("Configuration") {
        Button("Export Configuration") {
          store.exportConfiguration()
        }

        Button("Import Configuration") {
          store.chooseConfigurationFile()
        }

        Text("Configuration exports record local paths for review. API keys are never exported or imported. Import applies only portable preferences such as models, provider, Ollama endpoint, attachment context, and process timeout. Local paths, executables, and the Codex sandbox stay unchanged.")
          .font(.caption)
          .foregroundStyle(.secondary)
      }

      Section("Help And Output") {
        Button("Open User Guide") {
          store.openUserGuide()
        }
        .disabled(store.userGuideURL == nil)

        Button("Reveal Output Folder") {
          store.revealOutputRoot()
        }

        Button("Reveal Exported Plans") {
          store.revealExportedPlans()
        }

        Button("Export Support Bundle") {
          store.exportSupportBundle()
        }

        if store.lastWorkflowSummaryPath != nil {
          Button("Open Latest Workflow Summary") {
            store.openWorkflowSummary()
          }
        }

        Text("Use the guide and support bundle when a run stalls: they explain where to continue, which artifacts to inspect, and how the local AI should reason about recovery.")
          .font(.caption)
          .foregroundStyle(.secondary)
      }

      Section("Local AI Setup") {
        OllamaSetupView(store: store)
      }
      .id(SettingsRecoverySection.localAI)

      Section("AI Connections") {
        Picker("Provider", selection: $store.aiProvider) {
          ForEach(AIProvider.allCases) { provider in
            Text(provider.title).tag(provider)
          }
        }
        Text("Ollama is configured in Local AI Setup above. OpenAI, Grok/xAI, and Gemini remain optional cloud providers; their credentials are saved in Keychain when used. Gemini currently uses an API key: OAuth is not implemented and Scientific Workbench does not store OAuth tokens.")
          .font(.caption)
          .foregroundStyle(.secondary)

        Picker("Cloud attachment context", selection: $store.cloudAttachmentContextMode) {
          ForEach(CloudAttachmentContextMode.allCases) { mode in
            Text(mode.title).tag(mode)
          }
        }
        Text(store.cloudAttachmentContextMode.detail)
          .font(.caption)
          .foregroundStyle(.secondary)
        Text("This only affects OpenAI, Grok/xAI, and Gemini. Ollama and the deterministic local planner are not affected.")
          .font(.caption)
          .foregroundStyle(.secondary)
        ForEach(AIProvider.allCases.filter(\.requiresAPIKey)) { provider in
          ProviderConnectionRow(store: store, provider: provider)
        }
        Button("Save Connections") {
          store.persistSettings(saveSecrets: true)
        }
        if let message = store.credentialSaveMessage {
          Label(
            message,
            systemImage: store.credentialSaveFailed
              ? "exclamationmark.triangle.fill"
              : "checkmark.circle.fill"
          )
          .font(.caption)
          .foregroundStyle(store.credentialSaveFailed ? Color.orange : Color.secondary)
          .accessibilityIdentifier("connections.saveStatus")
        }
      }
      .id(SettingsRecoverySection.connections)

      Section("Codex Bridge") {
        TextField("Codex executable", text: $store.codexExecutablePath)
        Picker("Sandbox", selection: $store.codexSandboxMode) {
          Text("Read only").tag("read-only")
          Text("Workspace write").tag("workspace-write")
        }
        Text("Codex only runs when Chat Mode is set to Codex. Read only cannot edit files. Workspace write is confined by Codex to the approved output workspace; unrestricted filesystem access is not exposed by Scientific Workbench.")
          .font(.caption)
          .foregroundStyle(.secondary)
        Button("Save Codex Settings") {
          store.persistSettings()
        }
      }

      Section("Environment Details") {
        DisclosureGroup("Raw environment report") {
          Text(store.environmentStatus.details)
            .font(.system(.caption, design: .monospaced))
            .textSelection(.enabled)
            .frame(maxHeight: 160)
        }
      }
    }
    .formStyle(.grouped)
    .padding()
  }

  @ViewBuilder
  private var outputRootSafetyNotice: some View {
    switch store.outputRootRisk {
    case .safe:
      Label("Outputs use a dedicated location separated from the selected inputs.", systemImage: "checkmark.shield")
        .font(.caption)
        .foregroundStyle(.secondary)
    case .requiresConfirmation(let reason):
      Label(reason, systemImage: "exclamationmark.triangle")
        .font(.caption)
        .foregroundStyle(.orange)
      Toggle("Allow this higher-risk output root for this app session", isOn: $store.outputRootRiskApproved)
    case .blocked(let reason):
      Label(reason, systemImage: "xmark.shield")
        .font(.caption)
        .foregroundStyle(.red)
    }
  }
}

private struct InstallationProfileCard: View {
  let title: String
  let icon: String
  let scope: String
  let installation: String

  var body: some View {
    VStack(alignment: .leading, spacing: 7) {
      Label(title, systemImage: icon)
        .font(.headline)
      Text(scope)
        .font(.callout)
      Text(installation)
        .font(.caption)
        .foregroundStyle(.secondary)
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }
}
