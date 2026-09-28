import SwiftUI

struct OptionalAstronomyBackendsView: View {
  @ObservedObject var store: WorkbenchStore

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack(alignment: .top) {
        VStack(alignment: .leading, spacing: 4) {
          Text("STILTS / TOPCAT")
            .font(.headline)
          Text(store.optionalAstronomyBackendStatus.summary)
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        Spacer()
        StatusBadge(status: store.optionalAstronomyBackendStatus.overallStatus)
      }

      Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 8) {
        backendRow("Java", state: store.optionalAstronomyBackendStatus.java)
        backendRow("STILTS", state: store.optionalAstronomyBackendStatus.stilts)
        backendRow("TOPCAT", state: store.optionalAstronomyBackendStatus.topcat)
      }

      DisclosureGroup("Custom backend paths") {
        VStack(alignment: .leading, spacing: 8) {
          TextField("STILTS command", text: $store.stiltsCommand)
          TextField("STILTS JAR", text: $store.stiltsJar)
          TextField("TOPCAT command", text: $store.topcatCommand)
          TextField("TOPCAT JAR", text: $store.topcatJar)
          Text("Leave fields empty to use PATH discovery. These optional tools are never required for core Scientific Workbench workflows.")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.top, 6)
      }

      if let blockingMessage = store.optionalAstronomyBackendStatus.blockingMessage {
        Label(blockingMessage, systemImage: "info.circle")
          .font(.caption)
          .foregroundStyle(.secondary)
      }

      HStack {
        Button {
          Task { await store.refreshOptionalAstronomyBackends() }
        } label: {
          Label(
            store.isCheckingOptionalAstronomyBackends ? "Checking..." : "Check Backends",
            systemImage: "arrow.clockwise"
          )
        }
        .disabled(store.isCheckingOptionalAstronomyBackends)

        Button {
          store.openOptionalCapability("stilts_workbench")
        } label: {
          Label("Open STILTS Tool", systemImage: "terminal")
        }

        Button {
          store.useNativeCatalogAlternative()
        } label: {
          Label("Use Native Crossmatch", systemImage: "point.3.connected.trianglepath.dotted")
        }
        .disabled(!store.hasNativeCatalogAlternative)
      }

      Divider()

      HStack(alignment: .top) {
        VStack(alignment: .leading, spacing: 4) {
          Text("Aperture Photometry Tool (APT)")
            .font(.headline)
          Text(store.optionalAstronomyBackendStatus.aptSummary)
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        Spacer()
        StatusBadge(status: store.optionalAstronomyBackendStatus.aptOverallStatus)
      }

      Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 8) {
        backendRow("APT command", state: store.optionalAstronomyBackendStatus.aptCommand)
        backendRow("APT.pref", state: store.optionalAstronomyBackendStatus.aptPreferences)
        backendRow("Batch readiness", state: store.optionalAstronomyBackendStatus.aptBatch)
      }

      DisclosureGroup("APT paths and provenance") {
        VStack(alignment: .leading, spacing: 8) {
          HStack {
            TextField("APT.csh or APT.bat", text: $store.aptCommand)
            Button {
              store.chooseFile(assignTo: \.aptCommand)
            } label: {
              Image(systemName: "folder")
            }
            .help("Choose APT command")
          }
          HStack {
            TextField("Saved APT.pref", text: $store.aptPreferences)
            Button {
              store.chooseFile(assignTo: \.aptPreferences)
            } label: {
              Image(systemName: "folder")
            }
            .help("Choose saved APT preferences")
          }
          Text("APT preferences control apertures, background, and source-coordinate interpretation. Keep the saved file with the run provenance.")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.top, 6)
      }

      if let message = store.optionalAstronomyBackendStatus.aptBlockingMessage {
        Label(message, systemImage: "info.circle")
          .font(.caption)
          .foregroundStyle(.secondary)
      }

      ForEach(store.optionalAstronomyBackendStatus.aptNextActions, id: \.self) { action in
        Label(action, systemImage: "arrow.right")
          .font(.caption)
          .foregroundStyle(.secondary)
      }

      HStack {
        Button {
          Task { await store.runAPTPreflight() }
        } label: {
          Label("Run APT Preflight", systemImage: "checkmark.shield")
        }
        .disabled(store.hasActiveJob)

        Button {
          store.openOptionalCapability("apt_workbench")
        } label: {
          Label("Open APT Tool", systemImage: "terminal")
        }

        Button {
          store.useNativeAPTAlternative("inspect_fits")
        } label: {
          Label("Inspect FITS Instead", systemImage: "photo.on.rectangle.angled")
        }

        Button {
          store.useNativeAPTAlternative("photometry_noise_budget")
        } label: {
          Label("Use Native Noise Budget", systemImage: "function")
        }
      }

      if let job = store.latestAPTJob {
        HStack {
          Label(
            "Latest APT run: \(job.status.title), \(job.artifacts.count) artifact(s). Logs are preserved in Jobs.",
            systemImage: "doc.text.magnifyingglass"
          )
          .font(.caption)
          .foregroundStyle(.secondary)
          Spacer()
          Button("Results") {
            store.showLatestAPTResults()
          }
          Button {
            store.revealLatestAPTRun()
          } label: {
            Image(systemName: "folder")
          }
          .help("Reveal latest APT run folder")
        }
      }
    }
  }

  private func backendRow(_ label: String, state: OptionalBackendState) -> some View {
    GridRow {
      Text(label)
      Label(state.title, systemImage: icon(for: state))
        .foregroundStyle(color(for: state))
    }
  }

  private func icon(for state: OptionalBackendState) -> String {
    switch state {
    case .ready: return "checkmark.circle.fill"
    case .unavailable: return "minus.circle"
    case .warning: return "exclamationmark.triangle.fill"
    case .unknown: return "questionmark.circle"
    }
  }

  private func color(for state: OptionalBackendState) -> Color {
    switch state {
    case .ready: return .green
    case .warning: return .orange
    case .unavailable, .unknown: return .secondary
    }
  }
}
