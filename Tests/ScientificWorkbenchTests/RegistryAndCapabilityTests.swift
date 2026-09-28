import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func installedRegistrySurfaceCounts() throws {
    let registryPath = URL(fileURLWithPath: DefaultPaths.motherSkillRoot)
      .appendingPathComponent("public_surface_registry.yaml")
      .path
    #expect(FileManager.default.fileExists(atPath: registryPath))

    let entries = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    #expect(entries.count == 61)
    #expect(entries.userFacing.count == 55)
    #expect(entries.maintainerOnly.count == 6)
    #expect(entries.contains { $0.id == "profile_table" })
    #expect(entries.contains { $0.id == "legacy_spectroscopy_report_builder.populate" })
    #expect(entries.contains { $0.id == "latex_workbench.compile" })
    #expect(entries.contains { $0.id == "portable_smoke_test" && $0.isMaintainerOnly })
    #expect(entries.maintainerOnly.allSatisfy { $0.owningSkillRole == SkillRootRole.maintainer.rawValue })
    #expect(
      entries.first { $0.id == "catalog_workbench.crossmatch-sky" }?.owningSkillRole ==
        SkillRootRole.mother.rawValue
    )
    #expect(
      entries.first { $0.id == "spectra_ascii_coursework_workbench" }?.owningSkillRole ==
        SkillRootRole.astro.rawValue
    )
    #expect(
      entries.first { $0.id == "external_astro_tools_preflight" }?.owningSkillRole ==
        SkillRootRole.astro.rawValue
    )
    #expect(
      entries.first { $0.id == "spectra_ascii_coursework_workbench" }?.owningSkillRole ==
        SkillRootRole.astro.rawValue
    )
  }

  @Test
  func installedRegistryOwnershipMatchesCanonicalModuleMapForAllCapabilities() throws {
    let catalog = SkillRootCatalog.installed()
    let maintainerRoot = try #require(catalog.root(for: .maintainer))
    let moduleMapURL = maintainerRoot.url
      .appendingPathComponent("references/v2-3-mother-router-module-map.json")
    var payload = try #require(
      JSONSerialization.jsonObject(with: Data(contentsOf: moduleMapURL)) as? [String: Any]
    )
    if payload["capabilities"] == nil,
       let canonicalFixture = payload["canonical_fixture"] as? String {
      let canonicalURL = maintainerRoot.url.appendingPathComponent(canonicalFixture)
      payload = try #require(
        JSONSerialization.jsonObject(with: Data(contentsOf: canonicalURL)) as? [String: Any]
      )
    }
    let rows = try #require(payload["capabilities"] as? [[String: Any]])
    let entries = try CapabilityRegistryLoader().load(catalog: catalog)
    let entriesByID = Dictionary(uniqueKeysWithValues: entries.map { ($0.id, $0) })

    #expect(rows.count == 61)
    #expect(entriesByID.count == rows.count)
    for row in rows {
      let id = try #require(row["capability_id"] as? String)
      let owner = try #require(row["owner_module"] as? String)
      let expectedRole = owner == "shared" ? SkillRootRole.mother.rawValue : owner
      #expect(entriesByID[id]?.owningSkillRole == expectedRole)
    }
  }

  @Test
  func installedSkillRootCatalogDeclaresExpectedModularRoots() {
    let catalog = SkillRootCatalog.installed()
    let rootsByRole = Dictionary(uniqueKeysWithValues: catalog.roots.map { ($0.role, $0) })

    #expect(Set(rootsByRole.keys) == Set(SkillRootRole.allCases))
    #expect(rootsByRole[.mother]?.path.hasSuffix("/scientific-data-analysis") == true)
    #expect(rootsByRole[.astro]?.path.hasSuffix("/scientific-data-astro") == true)
    #expect(rootsByRole[.documents]?.path.hasSuffix("/scientific-data-documents") == true)
    #expect(rootsByRole[.notebooks]?.path.hasSuffix("/scientific-data-notebooks") == true)
    #expect(rootsByRole[.maintainer]?.path.hasSuffix("/scientific-data-maintainer") == true)
  }

  @Test
  func registryLoaderResolvesCanonicalRegistryRecursively() throws {
    let root = try makeScenarioFixture(
      name: "canonical-registry",
      files: [
        "public_surface_registry.yaml": "canonical_registry: nested/stub.yaml\n",
        "nested/stub.yaml": "canonical_registry: canonical/public_surface_registry.yaml\n",
        "nested/canonical/public_surface_registry.yaml": """
        entries:
          - id: sample.tool
            label: sample.py tool
            script: scripts/sample.py
            visible_block: core / routing
            kind: supporting_tool
            support_level: stable
            platform: portable
            requires_datanalysis: false
            preflight_mode: none
            smoke_tier: none
            short_description: Sample tool.
        """,
        "scripts/sample.py": "# sample\n"
      ]
    )
    defer { try? FileManager.default.removeItem(at: root) }
    let catalog = SkillRootCatalog(roots: [.init(role: .mother, url: root)])

    let entries = try CapabilityRegistryLoader().load(catalog: catalog)

    #expect(entries.map(\.id) == ["sample.tool"])
    #expect(entries[0].owningSkillRoot == root.path)
    #expect(entries[0].owningSkillRole == SkillRootRole.mother.rawValue)
    #expect(entries[0].registrySourcePath?.hasSuffix("nested/canonical/public_surface_registry.yaml") == true)
    #expect(entries[0].registryFingerprint?.isEmpty == false)
  }

  @Test
  func registryLoaderAssignsOwnersFromModularChildRootsWithoutDuplicatingEntries() throws {
    let fixture = try makeModularRegistryFixture()
    defer { try? FileManager.default.removeItem(at: fixture.root) }

    let entries = try CapabilityRegistryLoader().load(catalog: fixture.catalog)
    let byID = Dictionary(uniqueKeysWithValues: entries.map { ($0.id, $0) })

    #expect(entries.count == 5)
    #expect(byID["datanalysis_env.status"]?.owningSkillRoot == fixture.mother.path)
    #expect(byID["inspect_fits"]?.owningSkillRoot == fixture.astro.path)
    #expect(byID["document_intake_workbench"]?.owningSkillRoot == fixture.documents.path)
    #expect(byID["profile_table"]?.owningSkillRoot == fixture.notebooks.path)
    #expect(byID["portable_smoke_test"]?.owningSkillRoot == fixture.maintainer.path)
    #expect(entries.userFacing.count == 4)
    #expect(entries.maintainerOnly.map(\.id) == ["portable_smoke_test"])
    #expect(entries.maintainerOnly.allSatisfy { entry in
      CapabilityCatalogMode.allCases.allSatisfy { !entry.isVisible(in: $0) }
    })
    #expect(Set(entries.compactMap(\.registryFingerprint)).count == 1)
  }

  @Test
  func registryLoaderRejectsDivergentDuplicateMetadata() throws {
    let fixture = try makeModularRegistryFixture()
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    let divergentRegistry = modularRegistryYAML.replacingOccurrences(
      of: "label: datanalysis_env.py status",
      with: "label: divergent status label"
    )
    try divergentRegistry.write(
      to: fixture.astro.appendingPathComponent(".cache/public_surface_registry.yaml"),
      atomically: true,
      encoding: .utf8
    )

    do {
      _ = try CapabilityRegistryLoader().load(catalog: fixture.catalog)
      Issue.record("Expected divergent duplicate capability metadata to fail registry loading.")
    } catch let error as RegistryError {
      guard case .duplicateCapabilityMetadata(let id, _, _) = error else {
        Issue.record("Unexpected registry error: \(error.localizedDescription)")
        return
      }
      #expect(id == "datanalysis_env.status")
    }
  }

  @Test
  func registryLoaderRejectsDuplicateIDsAcrossDifferentSnapshots() throws {
    let fixture = try makeModularRegistryFixture()
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    try (modularRegistryYAML + "\n# fingerprint drift\n").write(
      to: fixture.astro.appendingPathComponent(".cache/public_surface_registry.yaml"),
      atomically: true,
      encoding: .utf8
    )

    do {
      _ = try CapabilityRegistryLoader().load(catalog: fixture.catalog)
      Issue.record("Expected incompatible registry fingerprints to fail registry loading.")
    } catch let error as RegistryError {
      guard case .incompatibleRegistryFingerprints(let id, _, let first, _, let duplicate) = error else {
        Issue.record("Unexpected registry error: \(error.localizedDescription)")
        return
      }
      #expect(id == "datanalysis_env.status")
      #expect(first != duplicate)
    }
  }

  @Test
  func registryLoaderDegradesWhenOptionalModuleIsAbsent() throws {
    let fixture = try makeModularRegistryFixture()
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    try FileManager.default.removeItem(at: fixture.astro)

    let result = try CapabilityRegistryLoader().loadWithDiagnostics(catalog: fixture.catalog)
    let unavailable = try #require(result.unavailableOptionalRoots.first)
    let inspectFITS = try #require(result.entries.first { $0.id == "inspect_fits" })

    #expect(result.isDegraded)
    #expect(result.entries.count == 5)
    #expect(result.unavailableOptionalRoots.count == 1)
    #expect(unavailable.role == .astro)
    #expect(unavailable.reason == .notInstalled)
    #expect(unavailable.rootPath == fixture.astro.path)
    #expect(inspectFITS.owningSkillRole == SkillRootRole.mother.rawValue)
  }

  @Test
  func registryLoaderDoesNotHideMotherOrInstalledChildRegistryFailures() throws {
    let missingMother = try makeModularRegistryFixture()
    defer { try? FileManager.default.removeItem(at: missingMother.root) }
    try FileManager.default.removeItem(at: missingMother.mother)

    #expect(throws: RegistryError.self) {
      try CapabilityRegistryLoader().loadWithDiagnostics(catalog: missingMother.catalog)
    }

    let brokenChild = try makeModularRegistryFixture()
    defer { try? FileManager.default.removeItem(at: brokenChild.root) }
    try "canonical_registry: missing/public_surface_registry.yaml\n".write(
      to: brokenChild.astro.appendingPathComponent("public_surface_registry.yaml"),
      atomically: true,
      encoding: .utf8
    )

    #expect(throws: RegistryError.self) {
      try CapabilityRegistryLoader().loadWithDiagnostics(catalog: brokenChild.catalog)
    }
  }

  @Test
  func canonicalRegistryCannotEscapeTheConfiguredSkillFamily() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Registry-Escape-\(UUID().uuidString)", isDirectory: true)
    let skills = root.appendingPathComponent("skills", isDirectory: true)
    let mother = skills.appendingPathComponent("scientific-data-analysis", isDirectory: true)
    let outside = root.appendingPathComponent("outside-registry.yaml")
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: mother, withIntermediateDirectories: true)
    try "entries:\n  - id: outside\n    script: scripts/outside.py\n".write(
      to: outside,
      atomically: true,
      encoding: .utf8
    )
    try "canonical_registry: ../../outside-registry.yaml\n".write(
      to: mother.appendingPathComponent("public_surface_registry.yaml"),
      atomically: true,
      encoding: .utf8
    )

    do {
      _ = try CapabilityRegistryLoader().resolveRegistry(
        for: SkillRootCatalog.Root(role: .mother, url: mother)
      )
      Issue.record("Expected a canonical registry outside the skills directory to be rejected.")
    } catch let error as RegistryError {
      guard case .canonicalRegistryOutsideSkillFamily(let path, let allowedRoots) = error else {
        Issue.record("Unexpected registry error: \(error.localizedDescription)")
        return
      }
      #expect(path == outside.path)
      #expect(allowedRoots.allSatisfy { $0.hasPrefix(skills.path + "/") })
    }
  }

  @Test
  func canonicalRegistryCannotResolveIntoUnrelatedSiblingSkill() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Registry-Sibling-\(UUID().uuidString)", isDirectory: true)
    let skills = root.appendingPathComponent("skills", isDirectory: true)
    let mother = skills.appendingPathComponent("scientific-data-analysis", isDirectory: true)
    let unrelated = skills.appendingPathComponent("unrelated-skill", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    try FileManager.default.createDirectory(at: mother, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: unrelated, withIntermediateDirectories: true)
    try "entries:\n".write(
      to: unrelated.appendingPathComponent("public_surface_registry.yaml"),
      atomically: true,
      encoding: .utf8
    )
    try "canonical_registry: ../unrelated-skill/public_surface_registry.yaml\n".write(
      to: mother.appendingPathComponent("public_surface_registry.yaml"),
      atomically: true,
      encoding: .utf8
    )

    #expect(throws: RegistryError.self) {
      try CapabilityRegistryLoader().resolveRegistry(
        for: SkillRootCatalog.Root(role: .mother, url: mother)
      )
    }
  }

  @Test
  func registryLoaderDoesNotFallbackWhenInstalledOwningChildLosesItsScript() throws {
    let fixture = try makeModularRegistryFixture()
    defer { try? FileManager.default.removeItem(at: fixture.root) }
    try FileManager.default.removeItem(at: fixture.astro.appendingPathComponent("scripts/inspect_fits.py"))

    do {
      _ = try CapabilityRegistryLoader().load(catalog: fixture.catalog)
      Issue.record("Expected an installed owning child with a missing script to fail closed.")
    } catch let error as RegistryError {
      guard case .missingCapabilityScript(let entryID, _) = error else {
        Issue.record("Unexpected registry error: \(error.localizedDescription)")
        return
      }
      #expect(entryID == "inspect_fits")
    }
  }

  @Test
  func registryParserReadsRequiredFields() throws {
    let yaml = """
    entries:
      - id: sample.tool
        label: sample.py tool
        script: scripts/sample.py
        visible_block: core / routing
        kind: supporting_tool
        support_level: stable
        platform: portable
        requires_datanalysis: false
        preflight_mode: none
        smoke_tier: none
        short_description: A useful sample.
    """

    let entries = try CapabilityRegistryLoader().parse(yaml)
    #expect(entries.count == 1)
    #expect(entries[0].id == "sample.tool")
    #expect(entries[0].label == "sample.py tool")
    #expect(entries[0].scriptStem == "sample")
    #expect(entries[0].inferredSubcommand == "tool")
    #expect(entries[0].visibleBlock == "core / routing")
    #expect(entries[0].requiresDatanalysis == false)
    #expect(entries[0].allowedEnvironmentKeys.isEmpty)
  }

  @Test
  func registryParserLoadsOptionalCapabilityEnvironmentKeys() throws {
    let yaml = """
    entries:
      - id: external.sample
        label: external sample
        script: scripts/external_sample.py
        visible_block: core / routing
        kind: supporting_tool
        support_level: optional
        platform: portable
        requires_datanalysis: false
        preflight_mode: explicit
        smoke_tier: none
        short_description: External sample.
        allowed_environment_keys: JAVA_COMMAND, STILTS_JAR, JAVA_COMMAND
    """

    let entry = try #require(CapabilityRegistryLoader().parse(yaml).first)
    #expect(entry.allowedEnvironmentKeys == ["JAVA_COMMAND", "STILTS_JAR"])
  }

  @Test
  func registryParserRejectsSensitiveOrInvalidEnvironmentKeys() {
    let sensitive = """
    entries:
      - id: unsafe.sample
        label: unsafe sample
        script: scripts/unsafe.py
        visible_block: core / routing
        kind: supporting_tool
        support_level: optional
        platform: portable
        requires_datanalysis: false
        preflight_mode: explicit
        smoke_tier: none
        short_description: Unsafe sample.
        allowed_environment_keys: ASTROMETRY_NET_API_KEY_FILE
    """
    let invalid = """
    entries:
      - id: invalid.sample
        label: invalid sample
        script: scripts/invalid.py
        visible_block: core / routing
        kind: supporting_tool
        support_level: optional
        platform: portable
        requires_datanalysis: false
        preflight_mode: explicit
        smoke_tier: none
        short_description: Invalid sample.
        allowed_environment_keys: VALID_NAME, NOT-VALID
    """

    #expect(throws: RegistryError.self) {
      try CapabilityRegistryLoader().parse(sensitive)
    }
    #expect(throws: RegistryError.self) {
      try CapabilityRegistryLoader().parse(invalid)
    }
  }

  @Test
  func registryParserRejectsMissingOrUnknownCapabilityKind() {
    let missing = """
    entries:
      - id: missing-kind.sample
        label: missing kind sample
        script: scripts/missing_kind.py
        visible_block: core / routing
        support_level: stable
        platform: portable
        requires_datanalysis: false
        preflight_mode: none
        smoke_tier: none
        short_description: Missing kind sample.
    """
    let unknown = """
    entries:
      - id: unknown-kind.sample
        label: unknown kind sample
        script: scripts/unknown_kind.py
        visible_block: core / routing
        kind: user_visible
        support_level: stable
        platform: portable
        requires_datanalysis: false
        preflight_mode: none
        smoke_tier: none
        short_description: Unknown kind sample.
    """

    #expect(throws: RegistryError.self) {
      try CapabilityRegistryLoader().parse(missing)
    }
    #expect(throws: RegistryError.self) {
      try CapabilityRegistryLoader().parse(unknown)
    }
  }

  @Test
  func registryParserRejectsInvalidSafetyContractValues() {
    let invalid = """
    entries:
      - id: invalid-contract.sample
        label: invalid contract sample
        script: scripts/invalid_contract.py
        visible_block: core / routing
        kind: supporting_tool
        support_level: stable
        platform: portable
        requires_datanalysis: yes
        preflight_mode: none
        smoke_tier: none
        short_description: Invalid contract sample.
    """

    #expect(throws: RegistryError.self) {
      try CapabilityRegistryLoader().parse(invalid)
    }
  }

  @Test
  func guidedRunRequirementsDescribeLaunchReadiness() {
    func entry(_ id: String) -> CapabilityEntry {
      CapabilityEntry(
        id: id,
        label: id,
        script: "scripts/\(id).py",
        visibleBlock: "core / routing",
        kind: "golden_path",
        supportLevel: "stable",
        platform: "portable",
        requiresDatanalysis: false,
        preflightMode: "none",
        smokeTier: "none",
        shortDescription: ""
      )
    }

    #expect(entry("datanalysis_env.status").guidedRunRequirement == .noInput)
    #expect(entry("external_astro_tools_preflight").guidedRunRequirement == .noInput)
    #expect(entry("inspect_fits").guidedRunRequirement == .singleInput)
    #expect(entry("fits_rgb_batch").guidedRunRequirement == .singleInput)
    #expect(entry("rgb_visual_fits_export").guidedRunRequirement == .singleInput)
    #expect(entry("astrometry_net_workbench.preflight").guidedRunRequirement == .singleInput)
    #expect(entry("astrometry_net_workbench.verify-existing-wcs").guidedRunRequirement == .singleInput)
    #expect(entry("radial_velocity_workbench.validate-manifest").guidedRunRequirement == .singleInput)
    #expect(entry("iwork_workbench").guidedRunRequirement == .singleInput)
    #expect(entry("quicklook_bridge").guidedRunRequirement == .singleInput)
    #expect(entry("legacy_external_reference_check").guidedRunRequirement == .singleInput)
    #expect(entry("document_intake_workbench").guidedRunRequirement == .multipleInputs)
    #expect(entry("duckdb_workbench").guidedRunRequirement == .multipleInputs)
    #expect(entry("teareduce_router").guidedRunRequirement == .multipleInputs)
    #expect(entry("spectra_ascii_coursework_workbench").guidedRunRequirement == .multipleInputs)
    #expect(entry("legacy_rv_coursework_workbench.analyze").guidedRunRequirement == .multipleInputs)
    #expect(entry("sb2_double_gaussian_workbench.fit").guidedRunRequirement == .multipleInputs)
    #expect(entry("legacy_spectroscopy_envcheck").guidedRunRequirement == .singleInput)
    #expect(entry("legacy_spectroscopy_report_builder.scaffold").guidedRunRequirement == .noInput)
    #expect(entry("office_roundtrip.docx-style-inventory").guidedRunRequirement == .singleInput)
    #expect(entry("office_roundtrip.docx-styled-replace").guidedRunRequirement == .singleInput)
    #expect(entry("keynote_export").guidedRunRequirement == .singleInput)
    #expect(entry("scientific_writeup_review").guidedRunRequirement == .singleInput)
    #expect(entry("semantic_diff").guidedRunRequirement == .twoInputs)
    #expect(entry("deliverable_factory.scaffold").guidedRunRequirement == .noInput)
    #expect(entry("timeseries_forecasting_workbench").guidedRunRequirement == .singleInput)
    #expect(entry("presentation_workbench.inspect").guidedRunRequirement == .singleInput)
    #expect(entry("latex_workbench.scaffold").guidedRunRequirement == .noInput)
    #expect(entry("latex_workbench.review").guidedRunRequirement == .singleInput)
    #expect(entry("notebook_branch_compare").guidedRunRequirement == .singleInput)
    #expect(GuidedRunRequirement.singleInput.isSatisfied(inputCount: 0) == false)
    #expect(GuidedRunRequirement.singleInput.isSatisfied(inputCount: 1) == true)
    #expect(GuidedRunRequirement.twoInputs.isSatisfied(inputCount: 1) == false)
    #expect(GuidedRunRequirement.twoInputs.isSatisfied(inputCount: 2) == true)
  }

  @Test
  @MainActor
  func publicRegistryGuidedCoverageCoversEveryUserFacingCapability() throws {
    let entries = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
      .userFacing
    let guided = entries.filter {
      $0.supportsGuidedRun || GuidedCapabilityControls.supports($0.id)
    }
    let remaining = Set(entries.filter {
      !$0.supportsGuidedRun && !GuidedCapabilityControls.supports($0.id)
    }.map(\.id))

    #expect(entries.count == 55)
    #expect(guided.count == 55)
    #expect(remaining.isEmpty)
    #expect(GuidedCapabilityControls.supports("catalog_workbench.crossmatch-sky"))
    #expect(GuidedCapabilityControls.supports("legacy_spectroscopy_report_builder.populate"))
  }

  @Test
  func capabilityCatalogSeparatesNormalExpertOptionalLegacyAndMaintenance() throws {
    let entries = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)

    #expect(entries.userFacing.filter { $0.isVisible(in: .normal) }.count == 25)
    #expect(entries.userFacing.filter { $0.isVisible(in: .expert) }.count == 13)
    #expect(entries.userFacing.filter { $0.isVisible(in: .optional) }.count == 8)
    #expect(entries.userFacing.filter { $0.isVisible(in: .legacy) }.count == 9)
    #expect(entries.maintainerOnly.count == 6)
    #expect(entries.maintainerOnly.allSatisfy { entry in
      CapabilityCatalogMode.allCases.allSatisfy { !entry.isVisible(in: $0) }
    })

    let normalIDs = Set(entries.filter { $0.isVisible(in: .normal) }.map(\.id))
    let expertIDs = Set(entries.filter { $0.isVisible(in: .expert) }.map(\.id))
    let optionalIDs = Set(entries.filter { $0.isVisible(in: .optional) }.map(\.id))
    let legacyIDs = Set(entries.filter { $0.isVisible(in: .legacy) }.map(\.id))

    #expect(normalIDs.contains("profile_table"))
    #expect(normalIDs.contains("photometry_noise_budget"))
    #expect(!normalIDs.contains("inspect_fits"))
    #expect(expertIDs.contains("inspect_fits"))
    #expect(expertIDs.contains("li6708_equivalent_width_workbench.measure"))
    #expect(optionalIDs.contains("stilts_workbench"))
    #expect(optionalIDs.contains("keynote_export"))
    #expect(legacyIDs.contains("fxcor_iraf_workbench.run-auto"))
    #expect(legacyIDs.contains("istarmod_workbench.prepare-copy"))

    let dedicatedFormIDs: Set<String> = [
      "photometry_noise_budget",
      "timeseries_forecasting_workbench",
      "deliverable_factory.scaffold",
      "bootstrap_analysis_notebook",
      "companion_route_check",
      "office_roundtrip.docx-style-inventory",
      "office_roundtrip.docx-styled-replace",
    ]
    let unguidedNormal = entries.filter {
      $0.isVisible(in: .normal)
        && !$0.supportsGuidedRun
        && !dedicatedFormIDs.contains($0.id)
    }
    #expect(unguidedNormal.isEmpty)
  }

  @Test
  func aiConnectionStatesExposeBadgeTitles() {
    #expect(AIConnectionState.unknown.badgeTitle == "unknown")
    #expect(AIConnectionState.missingKey.badgeTitle == "missing key")
    #expect(AIConnectionState.testing.badgeTitle == "testing")
    #expect(AIConnectionState.connected.badgeTitle == "connected")
    #expect(AIConnectionState.failed.badgeTitle == "failed")
  }

  @Test
  func aiProvidersCanCoexistWithSeparateDefaults() {
    #expect(AIProvider.ollama.defaultModel == "qwen3:4b-instruct")
    #expect(AIProvider.ollama.requiresAPIKey == false)
    #expect(AIProvider.openAI.defaultModel.hasPrefix("gpt"))
    #expect(AIProvider.grok.defaultModel.hasPrefix("grok"))
    #expect(AIProvider.gemini.defaultModel.hasPrefix("gemini"))
  }

  @Test
  @MainActor
  func userGuideIsResolvableFromDevelopmentBuild() {
    let defaults = UserDefaults(suiteName: "Scientific-Workbench-Tests-\(UUID().uuidString)")!
    let store = WorkbenchStore(loadSecrets: false, defaults: defaults)

    let guideURL = store.userGuideURL

    #expect(guideURL?.lastPathComponent == "Scientific_Workbench_User_Guide.md")
    #expect(guideURL.map { FileManager.default.fileExists(atPath: $0.path) } == true)
  }

}

private struct ModularRegistryFixture {
  var root: URL
  var mother: URL
  var astro: URL
  var documents: URL
  var notebooks: URL
  var maintainer: URL

  var catalog: SkillRootCatalog {
    SkillRootCatalog(roots: [
      .init(role: .mother, url: mother),
      .init(role: .astro, url: astro),
      .init(role: .documents, url: documents),
      .init(role: .notebooks, url: notebooks),
      .init(role: .maintainer, url: maintainer),
    ])
  }
}

private func makeModularRegistryFixture() throws -> ModularRegistryFixture {
  let root = FileManager.default.temporaryDirectory
    .appendingPathComponent("Scientific-Workbench-Modular-Registry-\(UUID().uuidString)", isDirectory: true)
  let mother = root.appendingPathComponent("scientific-data-analysis", isDirectory: true)
  let astro = root.appendingPathComponent("scientific-data-astro", isDirectory: true)
  let documents = root.appendingPathComponent("scientific-data-documents", isDirectory: true)
  let notebooks = root.appendingPathComponent("scientific-data-notebooks", isDirectory: true)
  let maintainer = root.appendingPathComponent("scientific-data-maintainer", isDirectory: true)
  let roots = [mother, astro, documents, notebooks, maintainer]
  for skillRoot in roots {
    try FileManager.default.createDirectory(
      at: skillRoot.appendingPathComponent("scripts", isDirectory: true),
      withIntermediateDirectories: true
    )
    try "canonical_registry: .cache/public_surface_registry.yaml\n".write(
      to: skillRoot.appendingPathComponent("public_surface_registry.yaml"),
      atomically: true,
      encoding: .utf8
    )
    try FileManager.default.createDirectory(
      at: skillRoot.appendingPathComponent(".cache", isDirectory: true),
      withIntermediateDirectories: true
    )
    try modularRegistryYAML.write(
      to: skillRoot.appendingPathComponent(".cache/public_surface_registry.yaml"),
      atomically: true,
      encoding: .utf8
    )
  }

  try "# env\n".write(to: mother.appendingPathComponent("scripts/datanalysis_env.py"), atomically: true, encoding: .utf8)
  try "# fits\n".write(to: astro.appendingPathComponent("scripts/inspect_fits.py"), atomically: true, encoding: .utf8)
  try "# fits compat\n".write(to: mother.appendingPathComponent("scripts/inspect_fits.py"), atomically: true, encoding: .utf8)
  try "# docs\n".write(to: documents.appendingPathComponent("scripts/document_intake_workbench.py"), atomically: true, encoding: .utf8)
  try "# docs compat\n".write(to: mother.appendingPathComponent("scripts/document_intake_workbench.py"), atomically: true, encoding: .utf8)
  try "# table\n".write(to: notebooks.appendingPathComponent("scripts/profile_table.py"), atomically: true, encoding: .utf8)
  try "# table compat\n".write(to: mother.appendingPathComponent("scripts/profile_table.py"), atomically: true, encoding: .utf8)
  try "# smoke\n".write(to: maintainer.appendingPathComponent("scripts/portable_smoke_test.py"), atomically: true, encoding: .utf8)
  try "# smoke compat\n".write(to: mother.appendingPathComponent("scripts/portable_smoke_test.py"), atomically: true, encoding: .utf8)

  return ModularRegistryFixture(
    root: root,
    mother: mother,
    astro: astro,
    documents: documents,
    notebooks: notebooks,
    maintainer: maintainer
  )
}

private let modularRegistryYAML = """
entries:
  - id: datanalysis_env.status
    label: datanalysis_env.py status
    script: scripts/datanalysis_env.py
    visible_block: core / routing
    kind: golden_path
    support_level: stable
    platform: portable
    requires_datanalysis: false
    preflight_mode: none
    smoke_tier: core
    short_description: Check the scientific environment.
  - id: inspect_fits
    label: inspect_fits.py
    script: scripts/inspect_fits.py
    visible_block: astronomy observational
    kind: golden_path
    support_level: stable
    platform: portable
    requires_datanalysis: false
    preflight_mode: none
    smoke_tier: core
    short_description: Inspect FITS metadata and structure.
  - id: document_intake_workbench
    label: document_intake_workbench.py
    script: scripts/document_intake_workbench.py
    visible_block: documents + reporting
    kind: golden_path
    support_level: stable
    platform: portable
    requires_datanalysis: false
    preflight_mode: none
    smoke_tier: core
    short_description: Inspect scientific documents.
  - id: profile_table
    label: profile_table.py
    script: scripts/profile_table.py
    visible_block: notebooks + cross-domain
    kind: golden_path
    support_level: stable
    platform: portable
    requires_datanalysis: false
    preflight_mode: none
    smoke_tier: core
    short_description: Profile a scientific table.
  - id: portable_smoke_test
    label: portable_smoke_test.py
    script: scripts/portable_smoke_test.py
    visible_block: core / routing
    kind: maintainer_only
    support_level: stable
    platform: portable
    requires_datanalysis: false
    preflight_mode: none
    smoke_tier: core
    short_description: Run a portable maintainer smoke test.
"""
