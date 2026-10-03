import SwiftUI

struct SettingsView: View {
  @ObservedObject var store: WorkbenchStore

  var body: some View {
    Form {
      Section("Setup Checklist") {
        SetupChecklistCard(store: store, compact: true, showActions: false)
      }

      Section("Installation Profiles") {
        Text("Core supports the synthetic first-run examples and common table, FITS, and document workflows. It does not need an Ollama model or a cloud account.")
        Text("Full adds Python packages for advanced workflows, including notebook and presentation routes. Its reviewed locked setup currently targets Apple Silicon, Python 3.11, and macOS 15 or later; it does not install external applications.")
        Text("Ollama models, TeX, LibreOffice, IRAF, and other optional backends need separate setup only for routes that use them. Check each capability's requirements and preflight before running it.")
        Text("The source repository's INSTALL.md lists exact commands, supported lock combinations, and current validation limits.")
          .foregroundStyle(.secondary)
      }

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

      Section("Optional Astronomy Backends") {
        OptionalAstronomyBackendsView(store: store)
      }

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
        StatusBadge(status: store.environmentStatus.status)
        Text(store.environmentStatus.details)
          .font(.system(.caption, design: .monospaced))
          .textSelection(.enabled)
          .frame(maxHeight: 160)
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
