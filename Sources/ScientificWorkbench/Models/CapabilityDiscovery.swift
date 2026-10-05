import Foundation

enum CapabilityTask: String, CaseIterable, Identifiable {
  case setup
  case inspect
  case validate
  case analyze
  case prepare
  case other

  var id: String { rawValue }

  var title: String {
    switch self {
    case .inspect: return "Inspect data"
    case .validate: return "Validate or compare"
    case .analyze: return "Analyze data"
    case .prepare: return "Prepare an output"
    case .setup: return "Check setup and routes"
    case .other: return "Other tasks"
    }
  }
}

enum CapabilityInputFormat: String, CaseIterable, Identifiable {
  case fits
  case table
  case spectrum
  case document
  case presentation
  case notebook
  case manifest
  case folder
  case general

  var id: String { rawValue }

  var title: String {
    switch self {
    case .fits: return "FITS / image"
    case .table: return "CSV / table"
    case .spectrum: return "Spectrum"
    case .document: return "Document / LaTeX"
    case .presentation: return "Presentation"
    case .notebook: return "Notebook"
    case .manifest: return "JSON / manifest"
    case .folder: return "Folder / container"
    case .general: return "No specific file"
    }
  }
}

enum CapabilityStartingProfile: String {
  case core
  case full
  case fullRecommended
  case fullTested
  case coreRoutingFullNotebook
  case undocumented

  var title: String {
    switch self {
    case .core: return "Core"
    case .full: return "Full"
    case .fullRecommended: return "Full recommended"
    case .fullTested: return "Full tested"
    case .coreRoutingFullNotebook: return "Core routing; Full notebook"
    case .undocumented: return "Check setup matrix"
    }
  }
}

enum CapabilityProfileFilter: String, CaseIterable, Identifiable {
  case core
  case full

  var id: String { rawValue }
  var title: String { self == .core ? "Core starting point" : "Full routes" }
}

enum CapabilityReadinessFilter: String, CaseIterable, Identifiable {
  case appReady
  case conditional
  case cli

  var id: String { rawValue }

  var title: String {
    switch self {
    case .appReady: return "App ready classification"
    case .conditional: return "Conditional / review"
    case .cli: return "CLI / outside app"
    }
  }

  static func classification(of entry: CapabilityEntry) -> Self {
    switch entry.appReadiness {
    case .appReady: return .appReady
    case .appReadyPartial, .blockedOptional: return .conditional
    case .cliOnly, .notApplicableToApp, .maintainerOnly: return .cli
    }
  }
}

struct CapabilityDiscovery {
  let title: String
  let task: CapabilityTask
  let formats: Set<CapabilityInputFormat>
  let profile: CapabilityStartingProfile

  init(
    _ title: String,
    task: CapabilityTask,
    formats: Set<CapabilityInputFormat> = [.general],
    profile: CapabilityStartingProfile = .core
  ) {
    self.title = title
    self.task = task
    self.formats = formats
    self.profile = profile
  }

  static func forEntry(_ entry: CapabilityEntry) -> Self {
    catalog[entry.id] ?? Self(
      entry.label, task: .other, formats: [.general], profile: .undocumented
    )
  }

  // These labels and profiles are a user-facing index of the reviewed
  // CAPABILITY_SETUP_MATRIX.md. An unknown registry ID stays visible but is
  // explicitly undocumented until this index is reviewed.
  private static let catalog: [String: Self] = [
    "datanalysis_env.status": .init("Check selected Python", task: .setup),
    "datanalysis_healthcheck": .init("Check science packages", task: .setup),
    "env_doctor": .init("Diagnose environment", task: .setup),
    "companion_route_check": .init("Find a skill for a task", task: .setup),
    "external_astro_tools_preflight": .init("Check external astronomy tools", task: .setup),
    "teareduce_router": .init(
      "Check CCD reduction route", task: .setup, formats: [.fits, .notebook],
      profile: .coreRoutingFullNotebook
    ),

    "inspect_fits": .init("Inspect a FITS image", task: .inspect, formats: [.fits]),
    "radial_velocity_workbench.inspect": .init("Inspect radial velocities", task: .inspect, formats: [.table]),
    "echelle_multispec_inventory": .init("Inspect echelle orders", task: .inspect, formats: [.fits, .spectrum]),
    "istarmod_workbench.inspect-tree": .init("Inspect a legacy spectrum tree", task: .inspect, formats: [.spectrum, .folder]),
    "document_intake_workbench": .init("Inspect a document folder", task: .inspect, formats: [.document, .folder]),
    "presentation_workbench.inspect": .init("Inspect slides", task: .inspect, formats: [.presentation], profile: .full),
    "iwork_workbench": .init("Inspect Pages or Keynote files", task: .inspect, formats: [.document, .presentation]),
    "office_roundtrip.docx-style-inventory": .init("Inspect Word styles", task: .inspect, formats: [.document]),
    "quicklook_bridge": .init("Preview a document", task: .inspect, formats: [.document, .presentation], profile: .full),
    "profile_table": .init("Profile a CSV table", task: .inspect, formats: [.table]),
    "cross_domain_data_workbench": .init("Inspect a mixed data folder", task: .inspect, formats: [.table, .folder]),
    "inspect_data_container": .init("Inspect a data container", task: .inspect, formats: [.folder]),

    "astrometry_net_workbench.preflight": .init("Check astrometry route", task: .validate, formats: [.fits], profile: .full),
    "astrometry_net_workbench.verify-existing-wcs": .init("Check existing WCS", task: .validate, formats: [.fits], profile: .full),
    "radial_velocity_workbench.validate-manifest": .init("Validate radial-velocity session", task: .validate, formats: [.manifest]),
    "legacy_spectroscopy_envcheck": .init("Check legacy spectroscopy setup", task: .validate, formats: [.folder]),
    "legacy_external_reference_check": .init("Compare a radial-velocity reference", task: .validate, formats: [.fits, .manifest]),
    "presentation_workbench.existing-deck-style-audit": .init("Review slide style", task: .validate, formats: [.presentation], profile: .full),
    "latex_workbench.review": .init("Review LaTeX source", task: .validate, formats: [.document], profile: .fullTested),
    "scientific_writeup_review": .init("Review scientific writing", task: .validate, formats: [.document]),
    "semantic_diff": .init("Compare two versions", task: .validate, formats: [.document, .table]),
    "coursework_notebook_fidelity_check": .init("Check notebook reproducibility", task: .validate, formats: [.notebook]),
    "notebook_branch_compare": .init("Compare notebook results", task: .validate, formats: [.notebook, .folder]),
    "physical_qa": .init("Check physical plausibility", task: .validate, formats: [.fits, .table, .spectrum]),

    "stilts_workbench": .init("Analyze tables with STILTS", task: .analyze, formats: [.table]),
    "fxcor_iraf_workbench.run-auto": .init("Run prepared IRAF FXCOR", task: .analyze, formats: [.spectrum]),
    "legacy_rv_coursework_workbench.analyze": .init("Analyze legacy radial velocities", task: .analyze, formats: [.table, .spectrum]),
    "sb2_double_gaussian_workbench.fit": .init("Fit double-lined CCF", task: .analyze, formats: [.table, .spectrum]),
    "li6708_equivalent_width_workbench.measure": .init("Measure Li 6708 equivalent width", task: .analyze, formats: [.fits, .spectrum]),
    "photometric_solution": .init("Fit photometric calibration", task: .analyze, formats: [.table]),
    "photometry_noise_budget": .init("Estimate photometry noise", task: .analyze),
    "apt_workbench": .init("Run APT photometry", task: .analyze, formats: [.fits], profile: .full),
    "duckdb_workbench": .init("Query tables with DuckDB", task: .analyze, formats: [.table], profile: .full),
    "spectra_ascii_coursework_workbench": .init("Analyze an ASCII spectrum", task: .analyze, formats: [.spectrum, .notebook], profile: .full),
    "timeseries_forecasting_workbench": .init("Forecast a time series", task: .analyze, formats: [.table, .notebook], profile: .fullRecommended),
    "catalog_workbench.crossmatch-sky": .init("Match sky catalogs", task: .analyze, formats: [.table]),

    "fits_rgb_batch": .init("Build a FITS RGB image", task: .prepare, formats: [.fits], profile: .fullRecommended),
    "rgb_visual_fits_export": .init("Export display FITS", task: .prepare, formats: [.fits], profile: .fullRecommended),
    "fxcor_iraf_workbench.prepare-session": .init("Prepare an IRAF working copy", task: .prepare, formats: [.spectrum, .folder]),
    "istarmod_workbench.prepare-copy": .init("Prepare a legacy spectrum copy", task: .prepare, formats: [.spectrum, .folder]),
    "legacy_spectroscopy_report_builder.scaffold": .init("Start a legacy spectroscopy report", task: .prepare, formats: [.document, .spectrum]),
    "legacy_spectroscopy_report_builder.populate": .init("Fill a legacy spectroscopy report", task: .prepare, formats: [.document, .manifest]),
    "office_roundtrip.docx-styled-replace": .init("Replace reviewed Word text", task: .prepare, formats: [.document]),
    "keynote_export": .init("Export Keynote to PDF", task: .prepare, formats: [.presentation, .document]),
    "latex_workbench.scaffold": .init("Start a LaTeX report", task: .prepare, formats: [.document], profile: .fullTested),
    "latex_workbench.compile": .init("Compile a LaTeX report", task: .prepare, formats: [.document], profile: .full),
    "deliverable_factory.scaffold": .init("Prepare a research handoff", task: .prepare, formats: [.document, .folder]),
    "bootstrap_analysis_notebook": .init("Start an analysis notebook", task: .prepare, formats: [.notebook]),
    "notebook_workbench.execute-copy": .init("Run a copied notebook", task: .prepare, formats: [.notebook], profile: .full),
  ]
}

struct CapabilityDiscoveryFilters {
  var task: CapabilityTask?
  var format: CapabilityInputFormat?
  var profile: CapabilityProfileFilter?
  var readiness: CapabilityReadinessFilter?
  var skill: SkillRootRole?
  var level: CapabilityCatalogMode?

  func matches(_ entry: CapabilityEntry, query: String) -> Bool {
    let discovery = CapabilityDiscovery.forEntry(entry)
    if let task, discovery.task != task { return false }
    if let format, !discovery.formats.contains(format) { return false }
    if let profile {
      switch (profile, discovery.profile) {
      case (.core, .core), (.core, .coreRoutingFullNotebook),
           (.full, .full), (.full, .fullRecommended), (.full, .fullTested),
           (.full, .coreRoutingFullNotebook):
        break
      default:
        return false
      }
    }
    if let readiness, CapabilityReadinessFilter.classification(of: entry) != readiness { return false }
    if let skill, entry.owningSkillRole != skill.rawValue { return false }
    if let level, entry.catalogMode != level { return false }

    let terms = query.split(whereSeparator: \.isWhitespace).map(String.init)
    guard !terms.isEmpty else { return true }
    let searchable = [
      discovery.title, discovery.task.title, discovery.profile.title,
      discovery.formats.map(\.title).joined(separator: " "),
      entry.id, entry.label, entry.shortDescription, entry.visibleBlock,
      entry.owningSkillRole ?? ""
    ].joined(separator: " ")
    return terms.allSatisfy { searchable.localizedCaseInsensitiveContains($0) }
  }
}
