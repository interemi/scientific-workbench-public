import SwiftUI

struct CapabilityCatalogView: View {
  @ObservedObject var store: WorkbenchStore
  let entries: [CapabilityEntry]
  let title: String
  let subtitle: String
  let isMaintenance: Bool
  @State private var rawArguments = ""
  @State private var accessConfirmed = false
  @State private var discoveryFilters = CapabilityDiscoveryFilters()
  @State private var maintenanceSearchText = ""

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
      selectVisibleEntryIfNeeded()
    }
    .onChange(of: filteredEntries.map(\.id)) { _, _ in
      selectVisibleEntryIfNeeded()
    }
    .onChange(of: store.selectedCapabilityID) {
      rawArguments = ""
      accessConfirmed = false
      revealExternallySelectedEntryIfNeeded()
    }
    .onAppear {
      revealExternallySelectedEntryIfNeeded()
      selectVisibleEntryIfNeeded()
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

      TextField(
        isMaintenance ? "Search maintenance gates" : "Find a task, e.g. inspect FITS or profile CSV",
        text: isMaintenance ? $maintenanceSearchText : $store.searchText
      )
        .textFieldStyle(.roundedBorder)
        .padding(.horizontal, 16)
        .accessibilityIdentifier("catalog.search")

      if !isMaintenance {
        discoveryControls
      }

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
        if filteredEntries.isEmpty {
          ContentUnavailableView(
            "No matching capabilities",
            systemImage: "line.3.horizontal.decrease.circle",
            description: Text("Change the task or requirement filters, or clear the search.")
          )
          .accessibilityIdentifier("catalog.empty-results")
        } else if isMaintenance {
          ForEach(filteredEntries.groupedByBlock(), id: \.0) { block, blockEntries in
            Section(block) {
              ForEach(blockEntries) { entry in
                CapabilityRow(entry: entry)
                  .tag(Optional(entry.id))
              }
            }
          }
        } else {
          ForEach(CapabilityTask.allCases) { task in
            let taskEntries = filteredEntries
              .filter { CapabilityDiscovery.forEntry($0).task == task }
              .sorted {
                if $0.isGoldenPath != $1.isGoldenPath {
                  return $0.isGoldenPath
                }
                return CapabilityDiscovery.forEntry($0).title.localizedStandardCompare(
                  CapabilityDiscovery.forEntry($1).title
                ) == .orderedAscending
              }
            if !taskEntries.isEmpty {
              Section(task.title) {
                ForEach(taskEntries) { entry in
                  CapabilityRow(entry: entry)
                    .tag(Optional(entry.id))
                }
              }
            }
          }
        }
      }
      .listStyle(.sidebar)
    }
    .frame(maxHeight: .infinity)
    .background(.bar)
  }

  private var discoveryControls: some View {
    VStack(alignment: .leading, spacing: 4) {
      HStack {
        Text("Find by task and requirements")
          .font(.caption)
          .fontWeight(.semibold)
        Spacer()
        Button("Clear filters") {
          discoveryFilters = CapabilityDiscoveryFilters()
          store.searchText = ""
        }
        .font(.caption)
        .accessibilityIdentifier("catalog.clear-filters")
      }

      Picker("Task", selection: $discoveryFilters.task) {
        Text("All tasks").tag(Optional<CapabilityTask>.none)
        ForEach(CapabilityTask.allCases) { task in
          Text(task.title).tag(Optional(task))
        }
      }
      .accessibilityIdentifier("catalog.filter.task")

      Picker("Format", selection: $discoveryFilters.format) {
        Text("All formats").tag(Optional<CapabilityInputFormat>.none)
        ForEach(CapabilityInputFormat.allCases) { format in
          Text(format.title).tag(Optional(format))
        }
      }
      .accessibilityIdentifier("catalog.filter.format")

      Picker("Python profile", selection: $discoveryFilters.profile) {
        Text("All profiles").tag(Optional<CapabilityProfileFilter>.none)
        ForEach(CapabilityProfileFilter.allCases) { profile in
          Text(profile.title).tag(Optional(profile))
        }
      }
      .accessibilityIdentifier("catalog.filter.profile")

      Picker("App readiness", selection: $discoveryFilters.readiness) {
        Text("All readiness levels").tag(Optional<CapabilityReadinessFilter>.none)
        ForEach(CapabilityReadinessFilter.allCases) { readiness in
          Text(readiness.title).tag(Optional(readiness))
        }
      }
      .accessibilityIdentifier("catalog.filter.readiness")

      Picker("Owning skill", selection: $discoveryFilters.skill) {
        Text("All skills").tag(Optional<SkillRootRole>.none)
        ForEach(SkillRootRole.allCases.filter { $0 != .maintainer }, id: \.self) { skill in
          Text(skill.defaultDirectoryName).tag(Optional(skill))
        }
      }
      .accessibilityIdentifier("catalog.filter.skill")

      Picker("Workflow level", selection: $discoveryFilters.level) {
        Text("All levels").tag(Optional<CapabilityCatalogMode>.none)
        ForEach(CapabilityCatalogMode.allCases) { level in
          Text(level.title).tag(Optional(level))
        }
      }
      .accessibilityIdentifier("catalog.filter.level")

      Text("\(filteredEntries.count) of \(entries.count) routes · Full includes Core. Catalog readiness is not a live backend check; review Settings before running.")
        .font(.caption)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .pickerStyle(.menu)
    .controlSize(.small)
    .padding(.horizontal, 16)
  }

  private var filteredEntries: [CapabilityEntry] {
    if isMaintenance {
      let query = maintenanceSearchText.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !query.isEmpty else { return entries }
      return entries.filter {
        [$0.id, $0.label, $0.shortDescription]
          .joined(separator: " ").localizedCaseInsensitiveContains(query)
      }
    }
    return entries.filter { discoveryFilters.matches($0, query: store.searchText) }
  }

  private var selectedEntry: CapabilityEntry? {
    if let selected = store.selectedCapability, filteredEntries.contains(selected) {
      return selected
    }
    return filteredEntries.first
  }

  private func selectVisibleEntryIfNeeded() {
    if !filteredEntries.contains(where: { $0.id == store.selectedCapabilityID }) {
      store.selectedCapabilityID = filteredEntries.first?.id
    }
  }

  private func revealExternallySelectedEntryIfNeeded() {
    guard !isMaintenance,
          let id = store.selectedCapabilityID,
          entries.contains(where: { $0.id == id }),
          !filteredEntries.contains(where: { $0.id == id }) else { return }
    discoveryFilters = CapabilityDiscoveryFilters()
    if !filteredEntries.contains(where: { $0.id == id }) {
      store.searchText = ""
    }
  }
}

struct CapabilityRow: View {
  let entry: CapabilityEntry

  var body: some View {
    let discovery = CapabilityDiscovery.forEntry(entry)
    HStack(spacing: 10) {
      Image(systemName: entry.blockIconName)
        .foregroundStyle(.secondary)
        .frame(width: 16)
      VStack(alignment: .leading, spacing: 2) {
        Text(entry.isMaintainerOnly ? entry.label : discovery.title)
          .lineLimit(1)
        Text(entry.isMaintainerOnly
          ? entry.supportLevel
          : "\(entry.workflowMode.title) · \(entry.appReadiness.title) · \(discovery.profile.title)")
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
    .accessibilityLabel("\(discovery.title), \(entry.workflowMode.title), \(entry.appReadiness.title), \(discovery.profile.title)")
    .accessibilityIdentifier("catalog.capability.\(entry.id)")
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
                Text(capability.isMaintainerOnly
                  ? capability.label : CapabilityDiscovery.forEntry(capability).title)
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
              if !isMaintenance {
                Text("\(capability.workflowMode.title) · \(capability.appReadiness.title) · \(CapabilityDiscovery.forEntry(capability).profile.title)")
                  .font(.caption)
                  .foregroundStyle(.secondary)
                if capability.appReadiness == .cliOnly || capability.appReadiness == .notApplicableToApp {
                  Text("CLI route: review docs/CAPABILITY_SETUP_MATRIX.md and the owning skill's --help before using advanced parameters.")
                    .font(.callout)
                    .foregroundStyle(.orange)
                }
              }
            }

            metadataGrid(capability)

            if let example = store.preparedFirstRunExample,
               store.inputPaths == example.inputPaths,
               capability.id == example.kind.capabilityID {
              VStack(alignment: .leading, spacing: 6) {
                Label("Synthetic example ready", systemImage: "checkmark.circle")
                  .font(.headline)
                Text("Expect: \(example.kind.expectedResult)")
                Text("Run the capability below, then inspect its job and artifacts in Jobs and Results. Do not treat this example as a calibrated observation.")
                  .foregroundStyle(.secondary)
              }
              .font(.callout)
              .padding(12)
              .frame(maxWidth: .infinity, alignment: .leading)
              .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
              .accessibilityIdentifier("capability.synthetic-example-expectation")
            }

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
        .accessibilityLabel("Clear selected inputs")
        .accessibilityHint("Removes inputs from this selection without deleting them from disk.")
      }

      if store.inputPaths.isEmpty {
        Text("No inputs yet. Add files or folders here, or drag them onto Dashboard.")
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
            .accessibilityLabel("Remove input \(URL(fileURLWithPath: path).lastPathComponent)")
            .accessibilityHint("Removes this item from the current input selection without deleting it from disk.")
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
        Label(
          capability.appReadiness == .cliOnly || capability.appReadiness == .notApplicableToApp
            ? "Run CLI Route" : "Run Capability",
          systemImage: "play.fill"
        )
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
