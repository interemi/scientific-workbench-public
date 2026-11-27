import Foundation

enum GuidedCapabilityArguments {
  enum CountUnit: String, CaseIterable {
    case electrons, adu

    var title: String { self == .adu ? "ADU" : "Electrons" }
  }

  enum Language: String, CaseIterable {
    case english = "en"
    case spanish = "es"
    case bilingual

    var title: String { deliverableValue.capitalized }

    var deliverableValue: String {
      switch self {
      case .english: "english"
      case .spanish: "spanish"
      case .bilingual: "bilingual"
      }
    }
  }

  enum Runtime: String, CaseIterable {
    case local, colab

    var title: String { self == .colab ? "Colab" : "Local" }
  }

  enum NotebookDomain: String, CaseIterable {
    case general, applied, astronomy

    var title: String { rawValue.capitalized }
  }

  enum DeliverableFormat: String, CaseIterable {
    case markdown, latex, html

    var title: String {
      switch self {
      case .markdown: "Markdown"
      case .latex: "LaTeX"
      case .html: "HTML"
      }
    }
  }

  struct NoiseBudget {
    var sourceSignal = 10_000.0
    var skyPerPixel = 50.0
    var darkPerPixel = 0.1
    var readNoise = 5.0
    var aperturePixels = 20.0
    var includeBackgroundEstimate = true
    var skyEstimatePixels = 100.0
    var frameCount = 1
    var units: CountUnit = .electrons
    var gain = 1.0

    var isValid: Bool {
      [sourceSignal, skyPerPixel, darkPerPixel, readNoise].allSatisfy { $0.isFinite && $0 >= 0 }
        && aperturePixels.isFinite && aperturePixels > 0
        && (!includeBackgroundEstimate || (skyEstimatePixels.isFinite && skyEstimatePixels > 0))
        && frameCount > 0
        && (units != .adu || (gain.isFinite && gain > 0))
    }

    func arguments(runURL: URL) -> [String] {
      func number(_ value: Double) -> String { String(format: "%.12g", value) }
      var arguments = [
        "--source", number(sourceSignal),
        "--sky-per-pixel", number(skyPerPixel),
        "--dark-per-pixel", number(darkPerPixel),
        "--read-noise", number(readNoise),
        "--n-pixels", number(aperturePixels),
        "--n-frames", String(frameCount),
        "--units", units.rawValue,
      ]
      if includeBackgroundEstimate {
        arguments += ["--sky-estimate-pixels", number(skyEstimatePixels)]
      }
      if units == .adu {
        arguments += ["--gain", number(gain)]
      }
      return arguments + [
        "--report-md", runURL.appendingPathComponent("reports/noise_budget.md").path,
      ] + evidenceArguments(runURL)
    }
  }

  struct ForecastNotebook {
    var title = "Scientific Workbench Forecast"
    var dateColumn = ""
    var valueColumn = ""
    var frequency = ""
    var testHorizon = 12
    var language: Language = .bilingual
    var runtime: Runtime = .local

    func arguments(input: String, runURL: URL) -> [String] {
      var arguments = [
        "--output-dir", runURL.appendingPathComponent("artifacts/forecasting").path,
        "--title=\(trimmed(title))",
        "--language", language.rawValue,
        "--runtime-profile", runtime.rawValue,
        "--data-path", input,
        "--test-horizon", String(testHorizon),
      ] + evidenceArguments(runURL)
      for (option, value) in [
        ("--date-column", dateColumn), ("--value-column", valueColumn), ("--frequency", frequency),
      ] {
        let value = trimmed(value)
        if !value.isEmpty { arguments.append("\(option)=\(value)") }
      }
      return arguments
    }
  }

  struct DeliverableScaffold {
    static let kinds = [
      "status-report", "executive-summary", "project-brief", "proposal",
      "qa-summary", "report", "minutes", "presentation", "academic-report",
    ]

    var title = "Scientific Workbench Deliverable"
    var kind = "status-report"
    var format: DeliverableFormat = .markdown
    var language: Language = .bilingual

    func arguments(runURL: URL) -> [String] {
      [
        runURL.appendingPathComponent("artifacts/deliverable").path,
        "--kind", kind,
        "--format", format.rawValue,
        "--title=\(trimmed(title))",
        "--language", language.deliverableValue,
      ] + evidenceArguments(runURL)
    }
  }

  struct AnalysisNotebook {
    var title = "Scientific Workbench Analysis"
    var domain: NotebookDomain = .general
    var language: Language = .bilingual
    var runtime: Runtime = .local

    func arguments(input: String?, runURL: URL) -> [String] {
      var arguments = [
        runURL.appendingPathComponent("artifacts/analysis_notebook.ipynb").path,
        "--title=\(trimmed(title))",
        "--domain", domain.rawValue,
        "--language", language.rawValue,
        "--runtime-profile", runtime.rawValue,
      ] + evidenceArguments(runURL)
      if let input { arguments += ["--data-path", input] }
      return arguments
    }
  }

  static func companionRoute(task: String, inputPaths: [String], runURL: URL) -> [String] {
    var arguments = ["--task=\(trimmed(task))"]
    for path in inputPaths {
      arguments += ["--file", path]
    }
    let formats = Set(inputPaths.map { URL(fileURLWithPath: $0).pathExtension.lowercased() })
    for format in formats.sorted() where !format.isEmpty {
      arguments += ["--format", format]
    }
    return arguments + ["--summary-json", runURL.appendingPathComponent("summary.json").path]
  }

  private static func evidenceArguments(_ runURL: URL) -> [String] {
    [
      "--summary-json", runURL.appendingPathComponent("summary.json").path,
      "--manifest-json", runURL.appendingPathComponent("manifest.json").path,
    ]
  }

  private static func trimmed(_ value: String) -> String {
    value.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
