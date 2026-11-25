import Foundation
@testable import ScientificWorkbench
import Testing

struct GuidedCLIInvocation: Encodable {
  let id: String
  let skill: String
  let argv: [String]
  var variant = "default"

  static func retain(_ invocations: [Self], as filename: String) throws {
    guard let directory = ProcessInfo.processInfo.environment["SCIENTIFIC_WORKBENCH_GUIDED_CLI_EVIDENCE_DIR"] else {
      return
    }
    let output = URL(fileURLWithPath: directory, isDirectory: true).appendingPathComponent(filename)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    try encoder.encode(invocations).write(to: output, options: .withoutOverwriting)
  }
}

extension ScientificWorkbenchTests {
  @Test
  func dedicatedGuidedFormsProduceCommandArguments() throws {
    let checkout = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
      .deletingLastPathComponent().deletingLastPathComponent()
    let mother = checkout.appendingPathComponent("skills/scientific-data-analysis").path
    let entries = try CapabilityRegistryLoader().load(skillRoot: mother).userFacing
    let fixture = try makeScenarioFixture(
      name: "guided-form-cli-contracts",
      files: [
        "first table.csv": "-RA,Dec\n12.0,0.12\n12.1,0.13\n",
        "second table.tsv": "RA\tDec\n180\t7\n182\t8\n",
        "legacy report/project.tex": "% synthetic report\n",
      ]
    )
    defer { try? FileManager.default.removeItem(at: fixture) }
    let first = fixture.appendingPathComponent("first table.csv").path
    let second = fixture.appendingPathComponent("second table.tsv").path
    let run = fixture.appendingPathComponent("fresh run", isDirectory: true)
    let builder = CapabilityCommandBuilder(pythonExecutable: "/usr/bin/python3")
    var invocations: [GuidedCLIInvocation] = []

    func retain(_ id: String, _ variant: String, inputs: [String] = [], arguments: [String]) throws {
      let entry = try #require(entries.first { $0.id == id })
      let request = RunRequest(
        capabilityID: id, inputPaths: inputs, outputDirectory: run.path,
        rawArguments: arguments.map(ShellWords.quote).joined(separator: " ")
      )
      let command = try builder.build(capability: entry, request: request, skillRoot: mother)
      let workdir = try #require(command.workingDirectory)
      let expected = (entry.inferredSubcommand.map { [$0] } ?? []) + arguments
      #expect(Array(command.arguments.dropFirst(3)) == expected)
      invocations.append(GuidedCLIInvocation(
        id: id, skill: URL(fileURLWithPath: workdir).lastPathComponent,
        argv: Array(command.arguments.dropFirst(3)), variant: variant
      ))
    }

    typealias Form = GuidedCapabilityArguments
    for units in Form.CountUnit.allCases {
      for withBackground in [false, true] {
        let form = Form.NoiseBudget(includeBackgroundEstimate: withBackground, units: units, gain: 1.7)
        let arguments = form.arguments(runURL: run)
        #expect(form.isValid)
        #expect(arguments.contains("--gain") == (units == .adu))
        #expect(arguments.contains("--sky-estimate-pixels") == withBackground)
        try retain(
          "photometry_noise_budget", "form-\(units.rawValue)-background-\(withBackground)", arguments: arguments
        )
      }
    }

    try retain(
      "timeseries_forecasting_workbench", "form-without-overrides", inputs: [first],
      arguments: Form.ForecastNotebook().arguments(input: first, runURL: run)
    )
    for language in Form.Language.allCases {
      for runtime in Form.Runtime.allCases {
        let form = Form.ForecastNotebook(
          title: "-Synthetic forecast", dateColumn: " -date ", valueColumn: "value column", frequency: "MS",
          testHorizon: 3, language: language, runtime: runtime
        )
        try retain(
          "timeseries_forecasting_workbench", "form-\(language.rawValue)-\(runtime.rawValue)", inputs: [first],
          arguments: form.arguments(input: first, runURL: run)
        )
      }
    }

    for kind in Form.DeliverableScaffold.kinds {
      for (format, language) in zip(Form.DeliverableFormat.allCases, Form.Language.allCases) {
        let form = Form.DeliverableScaffold(
          title: "-Synthetic report", kind: kind, format: format, language: language
        )
        try retain(
          "deliverable_factory.scaffold", "form-\(kind)-\(format.rawValue)-\(language.rawValue)",
          arguments: form.arguments(runURL: run)
        )
      }
    }

    try retain(
      "bootstrap_analysis_notebook", "form-without-data", arguments: Form.AnalysisNotebook().arguments(input: nil, runURL: run)
    )
    for domain in Form.NotebookDomain.allCases {
      for language in Form.Language.allCases {
        for runtime in Form.Runtime.allCases {
          let form = Form.AnalysisNotebook(
            title: "-Synthetic notebook", domain: domain, language: language, runtime: runtime
          )
          try retain(
            "bootstrap_analysis_notebook", "form-\(domain.rawValue)-\(language.rawValue)-\(runtime.rawValue)",
            inputs: [first], arguments: form.arguments(input: first, runURL: run)
          )
        }
      }
    }

    for inputs in [[], [first, second]] {
      try retain(
        "companion_route_check", "form-\(inputs.count)-files", inputs: inputs,
        arguments: Form.companionRoute(task: " -Inspect these data files ", inputPaths: inputs, runURL: run)
      )
    }

    let crossmatch = CatalogCrossmatchInspectionService()
    let selection = CatalogCrossmatchSelection(
      left: .init(raColumn: 0, decColumn: 1, raUnit: .hours, decUnit: .radians),
      right: .init(raColumn: 0, decColumn: 1, raUnit: .degrees, decUnit: .degrees),
      radiusArcseconds: 1.5, sharedICRSConfirmed: true, coordinateEpochJulianYear: 2016.25
    )
    let catalogs = try crossmatch.prepare(
      left: crossmatch.inspect(path: first), right: crossmatch.inspect(path: second), selection: selection
    )
    try retain(
      "catalog_workbench.crossmatch-sky", "reviewed-angular-units", inputs: [first, second],
      arguments: catalogs.arguments(runURL: run)
    )

    let evidence: [LegacyReportEvidenceRole: [String]] = Dictionary(
      uniqueKeysWithValues: LegacyReportEvidenceRole.allCases.filter { $0 != .unused }.map { role in
        let prefix = fixture.appendingPathComponent(role.rawValue).path
        return (role, role.allowsMultiple ? ["\(prefix)-1.json", "\(prefix)-2.json"] : ["\(prefix).json"])
      }
    )
    let project = LegacyReportPreparedRun(
      projectPath: fixture.appendingPathComponent("legacy report").path, evidenceByRole: evidence
    )
    let staged = try LegacyReportProjectStagingService().stagePopulateProjectIfNeeded(
      capabilityID: "legacy_spectroscopy_report_builder.populate",
      rawArguments: project.arguments(runURL: run).map(ShellWords.quote).joined(separator: " "),
      inputPaths: project.inputPaths, runDirectory: run.path
    )
    try retain(
      "legacy_spectroscopy_report_builder.populate", "reviewed-evidence-roles", inputs: project.inputPaths,
      arguments: ShellWords.split(staged)
    )

    try GuidedCLIInvocation.retain(invocations, as: "guided-forms.json")
  }
}
