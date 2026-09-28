import Foundation

enum CapabilityCatalogMode: String, CaseIterable, Codable, Sendable, Identifiable {
  case normal
  case expert
  case optional
  case legacy

  var id: String { rawValue }

  var title: String {
    switch self {
    case .normal: return "Normal"
    case .expert: return "Expert"
    case .optional: return "Optional"
    case .legacy: return "Legacy"
    }
  }

  var detail: String {
    switch self {
    case .normal:
      return "General and adaptable workflows suitable for daily work."
    case .expert:
      return "Scientific and domain-specific workflows that require informed review."
    case .optional:
      return "Workflows backed by optional applications, services, or platform features."
    case .legacy:
      return "Narrow coursework and legacy environments kept out of normal workflows."
    }
  }

  var iconName: String {
    switch self {
    case .normal: return "checkmark.circle"
    case .expert: return "scope"
    case .optional: return "puzzlepiece.extension"
    case .legacy: return "clock.arrow.circlepath"
    }
  }

  var requiresRunConfirmation: Bool {
    self == .expert || self == .legacy
  }
}

enum CapabilityWorkflowMode: String, CaseIterable, Codable, Sendable {
  case normal
  case expert
  case optional
  case legacy
  case maintainer

  var title: String {
    switch self {
    case .normal: return "Normal"
    case .expert: return "Expert"
    case .optional: return "Optional"
    case .legacy: return "Legacy"
    case .maintainer: return "Maintainer"
    }
  }

  var requiresExplicitConfirmation: Bool {
    self != .normal
  }
}

enum CapabilityAppReadiness: String, CaseIterable, Codable, Sendable {
  case appReady = "app_ready"
  case appReadyPartial = "app_ready_partial"
  case cliOnly = "cli_only"
  case blockedOptional = "blocked_optional"
  case maintainerOnly = "maintainer_only"
  case notApplicableToApp = "not_applicable_to_app"

  var title: String {
    switch self {
    case .appReady: return "App ready"
    case .appReadyPartial: return "Partial"
    case .cliOnly: return "CLI only"
    case .blockedOptional: return "Optional backend"
    case .maintainerOnly: return "Maintainer"
    case .notApplicableToApp: return "Not app-facing"
    }
  }

  var allowsAutomaticEnablement: Bool {
    self == .appReady
  }

  var isPlannerVisible: Bool {
    switch self {
    case .appReady, .appReadyPartial, .blockedOptional:
      return true
    case .cliOnly, .maintainerOnly, .notApplicableToApp:
      return false
    }
  }
}

enum GuidedRunRequirement: Equatable, Sendable {
  case noInput
  case singleInput
  case twoInputs
  case multipleInputs
  case rawArguments

  var title: String {
    switch self {
    case .noInput: return "Guided run"
    case .singleInput: return "Needs one input"
    case .twoInputs: return "Needs two inputs"
    case .multipleInputs: return "Needs inputs"
    case .rawArguments: return "Needs CLI arguments"
    }
  }

  var detail: String {
    switch self {
    case .noInput:
      return "Ready without dropped files."
    case .singleInput:
      return "Add one file or folder before running."
    case .twoInputs:
      return "Add a baseline and a candidate before running."
    case .multipleInputs:
      return "Add one or more files or folders before running."
    case .rawArguments:
      return "Use Advanced CLI Arguments for this capability."
    }
  }

  func isSatisfied(inputCount: Int) -> Bool {
    switch self {
    case .noInput:
      return true
    case .singleInput, .multipleInputs:
      return inputCount > 0
    case .twoInputs:
      return inputCount >= 2
    case .rawArguments:
      return false
    }
  }
}

struct CapabilityEntry: Identifiable, Hashable, Sendable {
  let id: String
  let label: String
  let script: String
  let visibleBlock: String
  let kind: String
  let supportLevel: String
  let platform: String
  let requiresDatanalysis: Bool
  let preflightMode: String
  let smokeTier: String
  let shortDescription: String
  let allowedEnvironmentKeys: Set<String>
  let owningSkillRoot: String?
  let owningSkillRole: String?
  let registrySourcePath: String?
  let registryFingerprint: String?

  init(
    id: String,
    label: String,
    script: String,
    visibleBlock: String,
    kind: String,
    supportLevel: String,
    platform: String,
    requiresDatanalysis: Bool,
    preflightMode: String,
    smokeTier: String,
    shortDescription: String,
    allowedEnvironmentKeys: Set<String> = [],
    owningSkillRoot: String? = nil,
    owningSkillRole: String? = nil,
    registrySourcePath: String? = nil,
    registryFingerprint: String? = nil
  ) {
    self.id = id
    self.label = label
    self.script = script
    self.visibleBlock = visibleBlock
    self.kind = kind
    self.supportLevel = supportLevel
    self.platform = platform
    self.requiresDatanalysis = requiresDatanalysis
    self.preflightMode = preflightMode
    self.smokeTier = smokeTier
    self.shortDescription = shortDescription
    self.allowedEnvironmentKeys = allowedEnvironmentKeys
    self.owningSkillRoot = owningSkillRoot
    self.owningSkillRole = owningSkillRole
    self.registrySourcePath = registrySourcePath
    self.registryFingerprint = registryFingerprint
  }

  var isMaintainerOnly: Bool {
    kind == "maintainer_only"
  }

  var isGoldenPath: Bool {
    kind == "golden_path"
  }

  var workflowMode: CapabilityWorkflowMode {
    if isMaintainerOnly {
      return .maintainer
    }
    if Self.legacyCapabilityIDs.contains(id) {
      return .legacy
    }
    if supportLevel == "optional" || Self.optionalCapabilityIDs.contains(id) {
      return .optional
    }
    if Self.expertCapabilityIDs.contains(id) {
      return .expert
    }
    if visibleBlock == "astronomy observational" && !Self.normalScientificCapabilityIDs.contains(id) {
      return .expert
    }
    return .normal
  }

  var appReadiness: CapabilityAppReadiness {
    if isMaintainerOnly {
      return .maintainerOnly
    }
    if Self.notApplicableCapabilityIDs.contains(id) {
      return .notApplicableToApp
    }
    if Self.cliOnlyCapabilityIDs.contains(id) {
      return .cliOnly
    }
    if Self.blockedOptionalCapabilityIDs.contains(id) {
      return .blockedOptional
    }
    if Self.appReadyPartialCapabilityIDs.contains(id) {
      return .appReadyPartial
    }
    return .appReady
  }

  var catalogMode: CapabilityCatalogMode? {
    switch workflowMode {
    case .normal: return .normal
    case .expert: return .expert
    case .optional: return .optional
    case .legacy: return .legacy
    case .maintainer: return nil
    }
  }

  func isVisible(in mode: CapabilityCatalogMode) -> Bool {
    !isMaintainerOnly && catalogMode == mode
  }

  var requiresPlannerConfirmation: Bool {
    workflowMode.requiresExplicitConfirmation ||
      !appReadiness.allowsAutomaticEnablement ||
      Self.confirmationRequiredCapabilityIDs.contains(id)
  }

  var scriptStem: String {
    URL(fileURLWithPath: script).deletingPathExtension().lastPathComponent
  }

  func resolvedSkillRoot(fallback: String) -> String {
    let trimmed = owningSkillRoot?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return trimmed.isEmpty ? fallback : trimmed
  }

  var inferredSubcommand: String? {
    let prefix = scriptStem + "."
    guard id.hasPrefix(prefix) else { return nil }
    return String(id.dropFirst(prefix.count))
  }

  var guidedRunRequirement: GuidedRunRequirement {
    switch id {
    case "datanalysis_env.status", "datanalysis_healthcheck", "env_doctor", "portable_smoke_test",
      "external_astro_tools_preflight", "stilts_workbench", "apt_workbench", "deliverable_factory.scaffold",
      "bootstrap_analysis_notebook", "latex_workbench.scaffold":
      return .noInput
    case "profile_table", "inspect_fits", "fits_rgb_batch", "rgb_visual_fits_export",
      "astrometry_net_workbench.preflight", "astrometry_net_workbench.verify-existing-wcs",
      "echelle_multispec_inventory", "inspect_data_container",
      "radial_velocity_workbench.inspect", "radial_velocity_workbench.validate-manifest",
      "photometric_solution", "iwork_workbench", "quicklook_bridge",
      "office_roundtrip.docx-style-inventory", "office_roundtrip.docx-styled-replace",
      "keynote_export", "notebook_workbench.execute-copy", "coursework_notebook_fidelity_check",
      "scientific_writeup_review", "physical_qa", "timeseries_forecasting_workbench",
      "presentation_workbench.inspect", "presentation_workbench.existing-deck-style-audit",
      "latex_workbench.review", "latex_workbench.compile", "notebook_branch_compare",
      "legacy_external_reference_check":
      return .singleInput
    case "semantic_diff":
      return .twoInputs
    case "document_intake_workbench", "cross_domain_data_workbench", "duckdb_workbench",
      "teareduce_router", "spectra_ascii_coursework_workbench",
      "legacy_rv_coursework_workbench.analyze", "sb2_double_gaussian_workbench.fit":
      return .multipleInputs
    case "legacy_spectroscopy_envcheck",
      "fxcor_iraf_workbench.prepare-session",
      "fxcor_iraf_workbench.run-auto",
      "istarmod_workbench.inspect-tree",
      "istarmod_workbench.prepare-copy",
      "li6708_equivalent_width_workbench.measure":
      return .singleInput
    case "legacy_spectroscopy_report_builder.scaffold":
      return .noInput
    case "legacy_spectroscopy_report_builder.populate":
      return .rawArguments
    default:
      return .rawArguments
    }
  }

  var supportsGuidedRun: Bool {
    guidedRunRequirement != .rawArguments
  }

  var blockIconName: String {
    switch visibleBlock {
    case "core / routing":
      return "switch.2"
    case "astronomy observational":
      return "sparkles"
    case "documents + reporting":
      return "doc.text"
    case "notebooks + cross-domain":
      return "tablecells"
    default:
      return "shippingbox"
    }
  }

  private static let legacyCapabilityIDs: Set<String> = [
    "legacy_spectroscopy_envcheck",
    "fxcor_iraf_workbench.prepare-session",
    "fxcor_iraf_workbench.run-auto",
    "legacy_rv_coursework_workbench.analyze",
    "legacy_external_reference_check",
    "istarmod_workbench.inspect-tree",
    "istarmod_workbench.prepare-copy",
    "legacy_spectroscopy_report_builder.scaffold",
    "legacy_spectroscopy_report_builder.populate",
  ]

  private static let optionalCapabilityIDs: Set<String> = [
    "iwork_workbench",
    "quicklook_bridge",
    "keynote_export",
  ]

  private static let normalScientificCapabilityIDs: Set<String> = [
    "photometry_noise_budget",
    "physical_qa",
  ]

  private static let expertCapabilityIDs: Set<String> = [
    "catalog_workbench.crossmatch-sky",
    "spectra_ascii_coursework_workbench",
  ]

  private static let confirmationRequiredCapabilityIDs: Set<String> = [
    "notebook_workbench.execute-copy",
    "office_roundtrip.docx-styled-replace",
  ]

  private static let blockedOptionalCapabilityIDs: Set<String> = [
    "external_astro_tools_preflight",
    "stilts_workbench",
    "apt_workbench",
    "teareduce_router",
    "iwork_workbench",
    "keynote_export",
    "duckdb_workbench",
  ]

  private static let cliOnlyCapabilityIDs: Set<String> = [
    "legacy_spectroscopy_envcheck",
    "fxcor_iraf_workbench.prepare-session",
    "fxcor_iraf_workbench.run-auto",
    "legacy_rv_coursework_workbench.analyze",
    "sb2_double_gaussian_workbench.fit",
    "istarmod_workbench.inspect-tree",
    "istarmod_workbench.prepare-copy",
    "legacy_spectroscopy_report_builder.scaffold",
    "legacy_spectroscopy_report_builder.populate",
    "spectra_ascii_coursework_workbench",
  ]

  private static let notApplicableCapabilityIDs: Set<String> = [
    "li6708_equivalent_width_workbench.measure",
    "legacy_external_reference_check",
  ]

  private static let appReadyPartialCapabilityIDs: Set<String> = [
    "fits_rgb_batch",
    "rgb_visual_fits_export",
    "astrometry_net_workbench.preflight",
    "astrometry_net_workbench.verify-existing-wcs",
    "radial_velocity_workbench.inspect",
    "radial_velocity_workbench.validate-manifest",
    "echelle_multispec_inventory",
    "photometric_solution",
    "presentation_workbench.inspect",
    "presentation_workbench.existing-deck-style-audit",
    "office_roundtrip.docx-style-inventory",
    "office_roundtrip.docx-styled-replace",
    "quicklook_bridge",
    "latex_workbench.scaffold",
    "latex_workbench.review",
    "latex_workbench.compile",
    "coursework_notebook_fidelity_check",
    "notebook_branch_compare",
    "catalog_workbench.crossmatch-sky",
  ]
}

extension Array where Element == CapabilityEntry {
  var userFacing: [CapabilityEntry] {
    filter { !$0.isMaintainerOnly }
  }

  var maintainerOnly: [CapabilityEntry] {
    filter(\.isMaintainerOnly)
  }

  var plannerVisible: [CapabilityEntry] {
    filter { $0.appReadiness.isPlannerVisible }
  }

  func groupedByBlock() -> [(String, [CapabilityEntry])] {
    let order = [
      "core / routing",
      "astronomy observational",
      "documents + reporting",
      "notebooks + cross-domain"
    ]
    let grouped = Dictionary(grouping: self, by: \.visibleBlock)
    return order.compactMap { block in
      guard let entries = grouped[block] else { return nil }
      return (block, entries.sorted { lhs, rhs in
        if lhs.kind != rhs.kind {
          return lhs.kind == "golden_path"
        }
        return lhs.label.localizedStandardCompare(rhs.label) == .orderedAscending
      })
    }
  }
}
