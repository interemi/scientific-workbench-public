import SwiftUI

struct CapabilityCatalogView: View {
  @ObservedObject var store: WorkbenchStore
  let entries: [CapabilityEntry]
  let title: String
  let subtitle: String
  let isMaintenance: Bool
  @State private var rawArguments = ""
  @State private var accessConfirmed = false

  var body: some View {
    HStack(spacing: 0) {
      capabilityList
        .frame(width: 390)

      Divider()

      CapabilityDetailPanel(
        store: store,
        capability: selectedEntry,
        rawArguments: $rawArguments,
        accessConfirmed: $accessConfirmed,
        isMaintenance: isMaintenance
      )
      .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity)
    }
    .onChange(of: entries.map(\.id)) { _, _ in
      let visibleIDs = modeEntries.map(\.id)
      if store.selectedCapabilityID == nil || !visibleIDs.contains(store.selectedCapabilityID ?? "") {
        store.selectedCapabilityID = modeEntries.first?.id
      }
    }
    .onChange(of: store.selectedCapabilityID) {
      rawArguments = ""
      accessConfirmed = false
    }
    .onChange(of: store.capabilityCatalogMode) {
      guard !isMaintenance else { return }
      store.searchText = ""
      store.selectedCapabilityID = modeEntries.first?.id
      rawArguments = ""
      accessConfirmed = false
    }
    .onAppear {
      if !modeEntries.contains(where: { $0.id == store.selectedCapabilityID }) {
        store.selectedCapabilityID = modeEntries.first?.id
      }
    }
  }

  private var capabilityList: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(alignment: .leading, spacing: 6) {
        Text(title)
          .font(.title2)
          .fontWeight(.semibold)
          .lineLimit(1)
        Text(subtitle)
          .font(.callout)
          .foregroundStyle(.secondary)
          .lineLimit(2)
      }
      .padding(.horizontal, 16)
      .padding(.top, 18)

      if !isMaintenance {
        Picker("Workflow mode", selection: $store.capabilityCatalogMode) {
          ForEach(CapabilityCatalogMode.allCases) { mode in
            Label(mode.title, systemImage: mode.iconName)
              .tag(mode)
          }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .padding(.horizontal, 16)
        .help("Choose which workflow class is visible")

        HStack {
          Text(store.capabilityCatalogMode.detail)
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(2)
          Spacer()
          Text("\(modeEntries.count)")
            .font(.caption)
            .monospacedDigit()
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 16)
      }

      TextField("Search \(title.lowercased())", text: $store.searchText)
        .textFieldStyle(.roundedBorder)
        .padding(.horizontal, 16)

      if let error = store.registryError {
        Text(error)
          .foregroundStyle(.red)
          .padding(.horizontal, 16)
      }

      if let notice = store.registryNotice {
        Label(notice, systemImage: "puzzlepiece.extension")
          .font(.caption)
          .foregroundStyle(.secondary)
          .padding(.horizontal, 16)
      }

      List(selection: $store.selectedCapabilityID) {
        ForEach(filteredEntries.groupedByBlock(), id: \.0) { block, blockEntries in
          Section(block) {
            ForEach(blockEntries) { entry in
              CapabilityRow(entry: entry)
                .tag(Optional(entry.id))
            }
          }
        }
      }
      .listStyle(.sidebar)
    }
    .frame(maxHeight: .infinity)
    .background(.bar)
  }

  private var filteredEntries: [CapabilityEntry] {
    let query = store.searchText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !query.isEmpty else { return modeEntries }
    return modeEntries.filter { entry in
      [entry.id, entry.label, entry.visibleBlock, entry.kind, entry.supportLevel, entry.shortDescription]
        .joined(separator: " ")
        .localizedCaseInsensitiveContains(query)
    }
  }

  private var selectedEntry: CapabilityEntry? {
    if let selected = store.selectedCapability, modeEntries.contains(selected) {
      return selected
    }
    return modeEntries.first
  }

  private var modeEntries: [CapabilityEntry] {
    guard !isMaintenance else { return entries }
    return entries.filter { $0.isVisible(in: store.capabilityCatalogMode) }
  }
}

struct CapabilityRow: View {
  let entry: CapabilityEntry

  var body: some View {
    HStack(spacing: 10) {
      Image(systemName: entry.blockIconName)
        .foregroundStyle(.secondary)
        .frame(width: 16)
      VStack(alignment: .leading, spacing: 2) {
        Text(entry.label)
          .lineLimit(1)
        Text("\(entry.appReadiness.title) · \(entry.supportLevel)")
          .font(.caption)
          .foregroundStyle(.secondary)
          .lineLimit(1)
      }
      Spacer()
      if entry.requiresDatanalysis {
        Image(systemName: "bolt.horizontal")
          .foregroundStyle(.orange)
          .help("Requires datanalysis")
      }
    }
  }
}

struct CapabilityDetailPanel: View {
  @ObservedObject var store: WorkbenchStore
  let capability: CapabilityEntry?
  @Binding var rawArguments: String
  @Binding var accessConfirmed: Bool
  let isMaintenance: Bool

  var body: some View {
    Group {
      if let capability {
        ScrollView {
          VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 8) {
              HStack {
                Text(capability.label)
                  .font(.title2)
                  .fontWeight(.semibold)
                Spacer()
                StatusBadge(status: capability.supportLevel)
              }
              Text(capability.shortDescription)
                .foregroundStyle(.secondary)
              Text(capability.id)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
            }

            metadataGrid(capability)

            inputsPanel

            if let mode = capability.catalogMode, !isMaintenance {
              WorkflowAccessNotice(
                mode: mode,
                readiness: capability.appReadiness,
                capabilityID: capability.id,
                requiresConfirmation: requiresAccessConfirmation(capability),
                confirmed: $accessConfirmed
              )
            }

            if showsOptionalAstronomyPanel(capability) {
              OptionalAstronomyBackendsView(store: store)
            }

            Group {
              if capability.id == "radial_velocity_workbench.inspect" {
                RadialVelocityInspectionView(store: store, capability: capability)
              } else if capability.id == "photometric_solution" {
                PhotometricCalibrationView(store: store, capability: capability)
              } else if capability.id == "office_roundtrip.docx-style-inventory"
                || capability.id == "office_roundtrip.docx-styled-replace" {
                DocumentRoundtripView(store: store, capability: capability)
              } else if capability.id == "keynote_export" {
                KeynoteExportView(store: store, capability: capability)
              } else if GuidedCapabilityControls.supports(capability.id) {
                GuidedCapabilityControls(store: store, capability: capability)
              } else {
                genericRunControls(capability)
              }
            }
            .disabled(requiresAccessConfirmation(capability) && !accessConfirmed)
          }
          .padding(24)
        }
      } else {
        ContentUnavailableView("No Capability Selected", systemImage: "square.grid.2x2")
      }
    }
  }

  private var inputsPanel: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack {
        Text("Inputs")
          .font(.headline)
        Spacer()
        Button {
          store.chooseInputFiles()
        } label: {
          Label("Add Files", systemImage: "doc.badge.plus")
        }
        Button {
          store.chooseInputFolders()
        } label: {
          Label("Add Folder", systemImage: "folder.badge.plus")
        }
        Button("Clear") {
          store.clearInputs()
        }
        .disabled(store.inputPaths.isEmpty)
      }

      if store.inputPaths.isEmpty {
        Text("No inputs yet. Add files or folders here, or drag them onto Inicio.")
          .font(.caption)
          .foregroundStyle(.secondary)
      } else {
        ForEach(store.inputPaths, id: \.self) { path in
          HStack(spacing: 8) {
            Image(systemName: "paperclip")
              .foregroundStyle(.secondary)
            Text(path)
              .font(.caption)
              .lineLimit(1)
              .truncationMode(.middle)
              .textSelection(.enabled)
            Spacer()
            Button {
              store.removeInputPath(path)
            } label: {
              Image(systemName: "xmark.circle.fill")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
          }
          .padding(8)
          .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
      }
    }
  }

  private func canRun(_ capability: CapabilityEntry) -> Bool {
    guard !store.canCancelActiveRun else { return false }
    guard !requiresAccessConfirmation(capability) || accessConfirmed else { return false }
    if !rawArguments.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      return true
    }
    return capability.guidedRunRequirement.isSatisfied(inputCount: store.inputPaths.count)
  }

  private func runReadinessMessage(for capability: CapabilityEntry) -> String {
    if store.canCancelActiveRun {
      return "A Scientific Workbench operation is already active."
    }
    if !rawArguments.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      return "Ready using the advanced CLI arguments."
    }
    if capability.guidedRunRequirement.isSatisfied(inputCount: store.inputPaths.count) {
      return "Ready for a guided run."
    }
    return capability.guidedRunRequirement.detail
  }

  @ViewBuilder
  private func genericRunControls(_ capability: CapabilityEntry) -> some View {
    if capability.supportsGuidedRun {
      VStack(alignment: .leading, spacing: 10) {
        Text("Guided Run")
          .font(.headline)
        Text("Scientific Workbench will construct the command, route outputs to a fresh run folder, and preserve the selected inputs.")
          .font(.callout)
          .foregroundStyle(.secondary)

        DisclosureGroup("Advanced argument override") {
          advancedArgumentsField
            .padding(.top, 6)
        }

        runFooter(capability)
      }
    } else {
      VStack(alignment: .leading, spacing: 10) {
        Label("Advanced parameters required", systemImage: "terminal")
          .font(.headline)
        Text("This capability is correctly classified but does not yet have a safe guided form. It remains available here only in its expert or specialist context.")
          .font(.callout)
          .foregroundStyle(.secondary)
        advancedArgumentsField
        runFooter(capability)
      }
    }
  }

  private var advancedArgumentsField: some View {
    VStack(alignment: .leading, spacing: 6) {
      TextField("CLI arguments", text: $rawArguments, axis: .vertical)
        .lineLimit(3...8)
        .textFieldStyle(.roundedBorder)
      Text("Arguments are passed through datanalysis_env.py run-tool. Outputs should target the generated run folder.")
        .font(.caption)
        .foregroundStyle(.secondary)
    }
  }

  private func runFooter(_ capability: CapabilityEntry) -> some View {
    HStack {
      Label(
        runReadinessMessage(for: capability),
        systemImage: canRun(capability) ? "checkmark.circle" : "exclamationmark.triangle"
      )
      .font(.caption)
      .foregroundStyle(canRun(capability) ? Color.secondary : Color.orange)

      Spacer()

      Button {
        Task {
          await store.run(capability: capability, rawArguments: rawArguments)
        }
      } label: {
        Label("Run Capability", systemImage: "play.fill")
      }
      .buttonStyle(.borderedProminent)
      .disabled(!canRun(capability))

      if store.canCancelActiveRun {
        Button(role: .cancel) {
          store.cancelActiveRun()
        } label: {
          Label(store.isCancellationRequested ? "Cancelling..." : "Cancel", systemImage: "xmark.circle")
        }
        .disabled(store.isCancellationRequested)
      }

      Button("Use Example Args") {
        rawArguments = exampleArguments(for: capability)
      }
      .disabled(exampleArguments(for: capability).isEmpty)
    }
  }

  private func requiresAccessConfirmation(_ capability: CapabilityEntry) -> Bool {
    !isMaintenance && capability.requiresPlannerConfirmation
  }

  private func showsOptionalAstronomyPanel(_ capability: CapabilityEntry) -> Bool {
    [
      "external_astro_tools_preflight",
      "stilts_workbench",
      "apt_workbench",
      "teareduce_router",
    ].contains(capability.id)
  }

  private func metadataGrid(_ capability: CapabilityEntry) -> some View {
    Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
      GridRow {
        MetadataPill(label: "Block", value: capability.visibleBlock)
        MetadataPill(label: "Kind", value: capability.kind)
      }
      GridRow {
        MetadataPill(label: "Platform", value: capability.platform)
        MetadataPill(label: "Smoke", value: capability.smokeTier)
      }
      GridRow {
        MetadataPill(label: "Script", value: capability.script)
        MetadataPill(label: "Datanalysis", value: capability.requiresDatanalysis ? "required" : "optional")
      }
    }
  }

  private func exampleArguments(for capability: CapabilityEntry) -> String {
    let exampleRoot = capability.resolvedSkillRoot(fallback: store.skillRootPath)
    switch capability.id {
    case "profile_table":
      return "\"\(exampleRoot)/examples/tabular/ops.csv\" --summary-json summary.json"
    case "inspect_fits":
      return "\"\(exampleRoot)/examples/science/legacy_spectroscopy_mini/mini_template.fits\" --summary-json summary.json"
    case "document_intake_workbench":
      return "--output-dir artifacts \"\(exampleRoot)/examples/documents\" --summary-json summary.json"
    case "portable_smoke_test":
      return "--output-dir artifacts --examples-dir \"\(exampleRoot)/examples\" --profile core --summary-json summary.json"
    default:
      return ""
    }
  }
}

struct MetadataPill: View {
  let label: String
  let value: String

  var body: some View {
    VStack(alignment: .leading, spacing: 3) {
      Text(label)
        .font(.caption)
        .foregroundStyle(.secondary)
      Text(value)
        .font(.callout)
        .lineLimit(1)
        .truncationMode(.middle)
        .textSelection(.enabled)
    }
    .frame(minWidth: 200, alignment: .leading)
    .padding(10)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }
}

private struct WorkflowAccessNotice: View {
  let mode: CapabilityCatalogMode
  let readiness: CapabilityAppReadiness
  let capabilityID: String
  let requiresConfirmation: Bool
  @Binding var confirmed: Bool

  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: mode.iconName)
        .foregroundStyle(color)
        .frame(width: 18)

      VStack(alignment: .leading, spacing: 4) {
        Text("\(mode.title) workflow")
          .font(.subheadline)
          .fontWeight(.semibold)
        Text(message)
          .font(.caption)
          .foregroundStyle(.secondary)

        if requiresConfirmation {
          Toggle("I reviewed the domain and safety requirements for this run.", isOn: $confirmed)
            .font(.caption)
            .toggleStyle(.checkbox)
            .padding(.top, 4)
        }
      }

      Spacer()

      StatusBadge(status: readiness.title)
    }
    .padding(12)
    .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
  }

  private var message: String {
    if capabilityID == "notebook_workbench.execute-copy" {
      return "This executes code from a copied notebook with your macOS user permissions. Review the notebook and its preflight findings; originals are not intentionally modified, but notebook code itself is trusted code."
    }
    switch mode {
    case .normal:
      return "Suitable for routine guided use with the capability's documented inputs."
    case .expert:
      return "Domain-specific assumptions may affect interpretation. Review units, columns, and scientific scope before running."
    case .optional:
      return "Availability depends on an external backend or platform feature. Run preflight first; absence is a controlled block."
    case .legacy:
      return "This narrow workflow is retained for compatible legacy environments and copied coursework workspaces."
    }
  }

  private var color: Color {
    switch mode {
    case .normal: return .green
    case .expert: return .orange
    case .optional: return .blue
    case .legacy: return .secondary
    }
  }
}
