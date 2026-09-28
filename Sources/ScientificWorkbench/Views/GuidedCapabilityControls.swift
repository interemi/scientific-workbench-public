import SwiftUI

struct GuidedCapabilityControls: View {
  @ObservedObject var store: WorkbenchStore
  let capability: CapabilityEntry

  @State private var sourceSignal = 10_000.0
  @State private var skyPerPixel = 50.0
  @State private var darkPerPixel = 0.1
  @State private var readNoise = 5.0
  @State private var aperturePixels = 20.0
  @State private var skyEstimatePixels = 100.0
  @State private var frameCount = 1
  @State private var noiseUnits = "electrons"
  @State private var gain = 1.0

  @State private var forecastTitle = "Scientific Workbench Forecast"
  @State private var dateColumn = ""
  @State private var valueColumn = ""
  @State private var frequency = ""
  @State private var testHorizon = 12
  @State private var forecastLanguage = "bilingual"
  @State private var runtimeProfile = "local"

  @State private var deliverableTitle = "Scientific Workbench Deliverable"
  @State private var deliverableKind = "status-report"
  @State private var deliverableFormat = "markdown"
  @State private var deliverableLanguage = "bilingual"

  @State private var notebookTitle = "Scientific Workbench Analysis"
  @State private var notebookDomain = "general"
  @State private var notebookLanguage = "bilingual"
  @State private var notebookRuntime = "local"

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
          numericField("Source signal", value: $sourceSignal)
          numericField("Sky / pixel", value: $skyPerPixel)
        }
        GridRow {
          numericField("Dark / pixel", value: $darkPerPixel)
          numericField("Read noise", value: $readNoise)
        }
        GridRow {
          numericField("Aperture pixels", value: $aperturePixels)
          numericField("Sky estimate pixels", value: $skyEstimatePixels)
        }
        GridRow {
          Picker("Units", selection: $noiseUnits) {
            Text("Electrons").tag("electrons")
            Text("ADU").tag("adu")
          }
          Stepper("Frames: \(frameCount)", value: $frameCount, in: 1...10_000)
        }
        if noiseUnits == "adu" {
          GridRow {
            numericField("Gain (e-/ADU)", value: $gain)
            Spacer()
          }
        }
      }
      .pickerStyle(.segmented)

      guidedFooter(
        readiness: noiseBudgetIsValid
          ? "Ready. Counts are interpreted as \(noiseUnits)."
          : "Source, read noise, aperture size, frame count, and gain must be physically valid.",
        canRun: noiseBudgetIsValid
      ) {
        await store.runGuided(capability: capability, inputPathsOverride: []) { runURL in
          var arguments = [
            "--source", number(sourceSignal),
            "--sky-per-pixel", number(skyPerPixel),
            "--dark-per-pixel", number(darkPerPixel),
            "--read-noise", number(readNoise),
            "--n-pixels", number(aperturePixels),
            "--sky-estimate-pixels", number(skyEstimatePixels),
            "--n-frames", String(frameCount),
            "--units", noiseUnits,
          ]
          if noiseUnits == "adu" {
            arguments += ["--gain", number(gain)]
          }
          return arguments + standardOutputs(
            runURL,
            reportName: "noise_budget.md",
            artifactName: "noise_budget.json"
          )
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

      TextField("Notebook title", text: $forecastTitle)
        .textFieldStyle(.roundedBorder)

      Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
        GridRow {
          TextField("Date column (optional)", text: $dateColumn)
          TextField("Value column (optional)", text: $valueColumn)
        }
        GridRow {
          TextField("Frequency, for example MS", text: $frequency)
          Stepper("Test horizon: \(testHorizon)", value: $testHorizon, in: 1...10_000)
        }
        GridRow {
          Picker("Language", selection: $forecastLanguage) {
            Text("English").tag("en")
            Text("Spanish").tag("es")
            Text("Bilingual").tag("bilingual")
          }
          Picker("Runtime", selection: $runtimeProfile) {
            Text("Local").tag("local")
            Text("Colab").tag("colab")
          }
        }
      }
      .pickerStyle(.menu)

      guidedFooter(
        readiness: store.inputPaths.isEmpty
          ? "Add one CSV, TSV, spreadsheet, or table-like source."
          : "Ready to scaffold against \(URL(fileURLWithPath: store.inputPaths[0]).lastPathComponent).",
        canRun: !store.inputPaths.isEmpty && !forecastTitle.trimmed.isEmpty
      ) {
        guard let input = store.inputPaths.first else { return }
        await store.runGuided(capability: capability, inputPathsOverride: [input]) { runURL in
          var arguments = [
            "--output-dir", runURL.appendingPathComponent("artifacts/forecasting").path,
            "--title", forecastTitle.trimmed,
            "--language", forecastLanguage,
            "--runtime-profile", runtimeProfile,
            "--data-path", input,
            "--test-horizon", String(testHorizon),
            "--summary-json", runURL.appendingPathComponent("summary.json").path,
            "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
          ]
          appendOption("--date-column", value: dateColumn, to: &arguments)
          appendOption("--value-column", value: valueColumn, to: &arguments)
          appendOption("--frequency", value: frequency, to: &arguments)
          return arguments
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

      TextField("Title", text: $deliverableTitle)
        .textFieldStyle(.roundedBorder)

      Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
        GridRow {
          Picker("Kind", selection: $deliverableKind) {
            ForEach([
              "status-report", "executive-summary", "project-brief", "proposal",
              "qa-summary", "report", "minutes", "presentation", "academic-report",
            ], id: \.self) { value in
              Text(value.replacingOccurrences(of: "-", with: " ").capitalized).tag(value)
            }
          }
          Picker("Format", selection: $deliverableFormat) {
            Text("Markdown").tag("markdown")
            Text("LaTeX").tag("latex")
            Text("HTML").tag("html")
          }
        }
        GridRow {
          Picker("Language", selection: $deliverableLanguage) {
            Text("English").tag("english")
            Text("Spanish").tag("spanish")
            Text("Bilingual").tag("bilingual")
          }
          Spacer()
        }
      }
      .pickerStyle(.menu)

      guidedFooter(
        readiness: deliverableTitle.trimmed.isEmpty
          ? "Enter a title before creating the scaffold."
          : "Ready to create a \(deliverableKind.replacingOccurrences(of: "-", with: " ")).",
        canRun: !deliverableTitle.trimmed.isEmpty
      ) {
        await store.runGuided(capability: capability, inputPathsOverride: []) { runURL in
          [
            runURL.appendingPathComponent("artifacts/deliverable").path,
            "--kind", deliverableKind,
            "--format", deliverableFormat,
            "--title", deliverableTitle.trimmed,
            "--language", deliverableLanguage,
            "--summary-json", runURL.appendingPathComponent("summary.json").path,
            "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
          ]
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

      TextField("Notebook title", text: $notebookTitle)
        .textFieldStyle(.roundedBorder)

      Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
        GridRow {
          Picker("Domain", selection: $notebookDomain) {
            Text("General").tag("general")
            Text("Applied").tag("applied")
            Text("Astronomy").tag("astronomy")
          }
          Picker("Language", selection: $notebookLanguage) {
            Text("English").tag("en")
            Text("Spanish").tag("es")
            Text("Bilingual").tag("bilingual")
          }
        }
        GridRow {
          Picker("Runtime", selection: $notebookRuntime) {
            Text("Local").tag("local")
            Text("Colab").tag("colab")
          }
          Text(store.inputPaths.first.map { URL(fileURLWithPath: $0).lastPathComponent } ?? "No data source selected")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
      }
      .pickerStyle(.menu)

      guidedFooter(
        readiness: notebookTitle.trimmed.isEmpty
          ? "Enter a notebook title."
          : "Ready. A data source is optional.",
        canRun: !notebookTitle.trimmed.isEmpty
      ) {
        await store.runGuided(
          capability: capability,
          inputPathsOverride: Array(store.inputPaths.prefix(1))
        ) { runURL in
          var arguments = [
            runURL.appendingPathComponent("artifacts/analysis_notebook.ipynb").path,
            "--title", notebookTitle.trimmed,
            "--domain", notebookDomain,
            "--language", notebookLanguage,
            "--runtime-profile", notebookRuntime,
            "--summary-json", runURL.appendingPathComponent("summary.json").path,
            "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
          ]
          if let input = store.inputPaths.first {
            arguments += ["--data-path", input]
          }
          return arguments
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
          var arguments = ["--task", companionTask.trimmed]
          for path in store.inputPaths {
            arguments += ["--file", path]
          }
          for format in Set(store.inputPaths.map { URL(fileURLWithPath: $0).pathExtension.lowercased() })
            .filter({ !$0.isEmpty })
            .sorted() {
            arguments += ["--format", format]
          }
          arguments += ["--summary-json", runURL.appendingPathComponent("summary.json").path]
          return arguments
        }
      }
    }
  }

  private var noiseBudgetIsValid: Bool {
    sourceSignal >= 0
      && skyPerPixel >= 0
      && darkPerPixel >= 0
      && readNoise >= 0
      && aperturePixels > 0
      && skyEstimatePixels > 0
      && frameCount > 0
      && (noiseUnits != "adu" || gain > 0)
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

  private func standardOutputs(
    _ runURL: URL,
    reportName: String,
    artifactName: String
  ) -> [String] {
    [
      "--summary-json", runURL.appendingPathComponent("summary.json").path,
      "--output-json", runURL.appendingPathComponent("artifacts/\(artifactName)").path,
      "--report-md", runURL.appendingPathComponent("reports/\(reportName)").path,
      "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
    ]
  }

  private func number(_ value: Double) -> String {
    String(format: "%.12g", value)
  }

  private func appendOption(_ option: String, value: String, to arguments: inout [String]) {
    let trimmed = value.trimmed
    guard !trimmed.isEmpty else { return }
    arguments += [option, trimmed]
  }
}

private extension String {
  var trimmed: String {
    trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
