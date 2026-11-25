import SwiftUI

struct GuidedCapabilityControls: View {
  @ObservedObject var store: WorkbenchStore
  let capability: CapabilityEntry

  @State private var noiseBudget = GuidedCapabilityArguments.NoiseBudget()
  @State private var forecast = GuidedCapabilityArguments.ForecastNotebook()
  @State private var deliverable = GuidedCapabilityArguments.DeliverableScaffold()
  @State private var notebook = GuidedCapabilityArguments.AnalysisNotebook()
  @State private var companionTask = ""

  static func supports(_ capabilityID: String) -> Bool {
    [
      "photometry_noise_budget",
      "timeseries_forecasting_workbench",
      "deliverable_factory.scaffold",
      "bootstrap_analysis_notebook",
      "companion_route_check",
      "catalog_workbench.crossmatch-sky",
      "legacy_spectroscopy_report_builder.populate",
    ].contains(capabilityID)
  }

  @ViewBuilder
  var body: some View {
    switch capability.id {
    case "photometry_noise_budget":
      noiseBudgetForm
    case "timeseries_forecasting_workbench":
      forecastingForm
    case "deliverable_factory.scaffold":
      deliverableForm
    case "bootstrap_analysis_notebook":
      notebookForm
    case "companion_route_check":
      companionRouteForm
    case "catalog_workbench.crossmatch-sky":
      CatalogCrossmatchView(store: store, capability: capability)
    case "legacy_spectroscopy_report_builder.populate":
      LegacyReportPopulateView(store: store, capability: capability)
    default:
      EmptyView()
    }
  }

  private var noiseBudgetForm: some View {
    VStack(alignment: .leading, spacing: 14) {
      formHeading(
        "Noise Budget",
        detail: "Estimate signal-to-noise from measured counts and detector properties."
      )

      Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
        GridRow {
          noiseField("Net source signal / frame", value: $noiseBudget.sourceSignal)
          noiseField("Sky / pixel / frame", value: $noiseBudget.skyPerPixel)
        }
        GridRow {
          noiseField("Dark / pixel / frame", value: $noiseBudget.darkPerPixel)
          noiseField("Read noise (e⁻ / pixel / frame)", value: $noiseBudget.readNoise)
        }
        GridRow {
          noiseField("Aperture pixels", value: $noiseBudget.aperturePixels)
          noiseField("Background-estimate pixels", value: $noiseBudget.skyEstimatePixels)
            .disabled(!noiseBudget.includeBackgroundEstimate)
        }
        GridRow {
          Picker("Units", selection: $noiseBudget.units) {
            ForEach(GuidedCapabilityArguments.CountUnit.allCases, id: \.self) { unit in
              Text(unit.title).tag(unit)
            }
          }
          Stepper("Frames: \(noiseBudget.frameCount)", value: $noiseBudget.frameCount, in: 1...10_000)
        }
        if noiseBudget.units == .adu {
          GridRow {
            noiseField("Gain (e⁻/ADU)", value: $noiseBudget.gain)
            Spacer()
          }
        }
      }
      .pickerStyle(.segmented)

      Toggle("Include uncertainty from estimating the background", isOn: $noiseBudget.includeBackgroundEstimate)

      guidedFooter(
        readiness: noiseBudget.isValid
          ? "Source, sky and dark are in \(noiseBudget.units.rawValue)."
          : "Enter finite counts and read noise, with positive pixel counts and gain where used.",
        canRun: noiseBudget.isValid
      ) {
        await store.runGuided(capability: capability, inputPathsOverride: []) { runURL in
          noiseBudget.arguments(runURL: runURL)
        }
      }
    }
  }

  private var forecastingForm: some View {
    VStack(alignment: .leading, spacing: 14) {
      formHeading(
        "Forecasting Notebook",
        detail: "Create a reproducible notebook and side products from one regular time-series table."
      )

      TextField("Notebook title", text: $forecast.title)
        .textFieldStyle(.roundedBorder)

      Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
        GridRow {
          TextField("Date column (optional)", text: $forecast.dateColumn)
          TextField("Value column (optional)", text: $forecast.valueColumn)
        }
        GridRow {
          TextField("Frequency, for example MS", text: $forecast.frequency)
          Stepper("Test horizon: \(forecast.testHorizon)", value: $forecast.testHorizon, in: 1...10_000)
        }
        GridRow {
          Picker("Language", selection: $forecast.language) {
            ForEach(GuidedCapabilityArguments.Language.allCases, id: \.self) { language in
              Text(language.title).tag(language)
            }
          }
          Picker("Runtime", selection: $forecast.runtime) {
            ForEach(GuidedCapabilityArguments.Runtime.allCases, id: \.self) { runtime in
              Text(runtime.title).tag(runtime)
            }
          }
        }
      }
      .pickerStyle(.menu)

      guidedFooter(
        readiness: store.inputPaths.isEmpty
          ? "Add one CSV, TSV, spreadsheet, or table-like source."
          : "Ready to scaffold against \(URL(fileURLWithPath: store.inputPaths[0]).lastPathComponent).",
        canRun: !store.inputPaths.isEmpty && !forecast.title.trimmed.isEmpty
      ) {
        guard let input = store.inputPaths.first else { return }
        await store.runGuided(capability: capability, inputPathsOverride: [input]) { runURL in
          forecast.arguments(input: input, runURL: runURL)
        }
      }
    }
  }

  private var deliverableForm: some View {
    VStack(alignment: .leading, spacing: 14) {
      formHeading(
        "Deliverable Scaffold",
        detail: "Create a clean report or handoff structure in a new run folder."
      )

      TextField("Title", text: $deliverable.title)
        .textFieldStyle(.roundedBorder)

      Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
        GridRow {
          Picker("Kind", selection: $deliverable.kind) {
            ForEach(GuidedCapabilityArguments.DeliverableScaffold.kinds, id: \.self) { value in
              Text(value.replacingOccurrences(of: "-", with: " ").capitalized).tag(value)
            }
          }
          Picker("Format", selection: $deliverable.format) {
            ForEach(GuidedCapabilityArguments.DeliverableFormat.allCases, id: \.self) { format in
              Text(format.title).tag(format)
            }
          }
        }
        GridRow {
          Picker("Language", selection: $deliverable.language) {
            ForEach(GuidedCapabilityArguments.Language.allCases, id: \.self) { language in
              Text(language.title).tag(language)
            }
          }
          Spacer()
        }
      }
      .pickerStyle(.menu)

      guidedFooter(
        readiness: deliverable.title.trimmed.isEmpty
          ? "Enter a title before creating the scaffold."
          : "Ready to create a \(deliverable.kind.replacingOccurrences(of: "-", with: " ")).",
        canRun: !deliverable.title.trimmed.isEmpty
      ) {
        await store.runGuided(capability: capability, inputPathsOverride: []) { runURL in
          deliverable.arguments(runURL: runURL)
        }
      }
    }
  }

  private var notebookForm: some View {
    VStack(alignment: .leading, spacing: 14) {
      formHeading(
        "Analysis Notebook",
        detail: "Scaffold a reproducible notebook, optionally prefilled with the first selected input."
      )

      TextField("Notebook title", text: $notebook.title)
        .textFieldStyle(.roundedBorder)

      Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
        GridRow {
          Picker("Domain", selection: $notebook.domain) {
            ForEach(GuidedCapabilityArguments.NotebookDomain.allCases, id: \.self) { domain in
              Text(domain.title).tag(domain)
            }
          }
          Picker("Language", selection: $notebook.language) {
            ForEach(GuidedCapabilityArguments.Language.allCases, id: \.self) { language in
              Text(language.title).tag(language)
            }
          }
        }
        GridRow {
          Picker("Runtime", selection: $notebook.runtime) {
            ForEach(GuidedCapabilityArguments.Runtime.allCases, id: \.self) { runtime in
              Text(runtime.title).tag(runtime)
            }
          }
          Text(store.inputPaths.first.map { URL(fileURLWithPath: $0).lastPathComponent } ?? "No data source selected")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
      }
      .pickerStyle(.menu)

      guidedFooter(
        readiness: notebook.title.trimmed.isEmpty
          ? "Enter a notebook title."
          : "Ready. A data source is optional.",
        canRun: !notebook.title.trimmed.isEmpty
      ) {
        await store.runGuided(
          capability: capability,
          inputPathsOverride: Array(store.inputPaths.prefix(1))
        ) { runURL in
          notebook.arguments(input: store.inputPaths.first, runURL: runURL)
        }
      }
    }
  }

  private var companionRouteForm: some View {
    VStack(alignment: .leading, spacing: 14) {
      formHeading(
        "Companion Route",
        detail: "Ask for an advisory handoff to installed companion skills without invoking them."
      )

      TextField("Describe the task", text: $companionTask, axis: .vertical)
        .lineLimit(2...5)
        .textFieldStyle(.roundedBorder)

      guidedFooter(
        readiness: companionTask.trimmed.isEmpty
          ? "Describe the task before requesting a route."
          : "Ready. Selected filenames and formats will be included as advisory context.",
        canRun: !companionTask.trimmed.isEmpty
      ) {
        await store.runGuided(capability: capability) { runURL in
          GuidedCapabilityArguments.companionRoute(
            task: companionTask, inputPaths: store.inputPaths, runURL: runURL
          )
        }
      }
    }
  }

  private func noiseField(_ title: String, value: Binding<Double>) -> some View {
    VStack(alignment: .leading, spacing: 4) {
      Text(title).font(.caption).accessibilityHidden(true)
      numericField(title, value: value)
    }
  }

  private func formHeading(_ title: String, detail: String) -> some View {
    VStack(alignment: .leading, spacing: 4) {
      Text(title)
        .font(.headline)
      Text(detail)
        .font(.callout)
        .foregroundStyle(.secondary)
    }
  }

  private func numericField(_ title: String, value: Binding<Double>) -> some View {
    TextField(title, value: value, format: .number)
      .textFieldStyle(.roundedBorder)
  }

  private func guidedFooter(
    readiness: String,
    canRun: Bool,
    action: @escaping @MainActor () async -> Void
  ) -> some View {
    HStack {
      Label(
        readiness,
        systemImage: canRun ? "checkmark.circle" : "exclamationmark.triangle"
      )
      .font(.caption)
      .foregroundStyle(canRun ? Color.secondary : Color.orange)

      Spacer()

      Button {
        Task { await action() }
      } label: {
        Label("Run Guided Workflow", systemImage: "play.fill")
      }
      .buttonStyle(.borderedProminent)
      .disabled(!canRun || store.hasActiveJob)
    }
  }

}

private extension String {
  var trimmed: String {
    trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
