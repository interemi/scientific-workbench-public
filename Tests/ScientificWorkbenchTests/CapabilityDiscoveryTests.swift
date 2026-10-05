import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func everyInstalledUserCapabilityHasReviewedDiscoveryMetadata() throws {
    let entries = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
      .userFacing
    #expect(entries.count == 55)
    #expect(entries.allSatisfy { CapabilityDiscovery.forEntry($0).task != .other })
    #expect(entries.allSatisfy { CapabilityDiscovery.forEntry($0).profile != .undocumented })
    #expect(Set(entries.map { CapabilityDiscovery.forEntry($0).title }).count == entries.count)

    let counts = Dictionary(grouping: entries, by: { CapabilityDiscovery.forEntry($0).task })
      .mapValues(\.count)
    #expect(counts[.setup] == 6)
    #expect(counts[.inspect] == 12)
    #expect(counts[.validate] == 12)
    #expect(counts[.analyze] == 12)
    #expect(counts[.prepare] == 13)
  }

  @Test
  func commonTaskNamesAndFacetsLeadToReviewedRoutes() throws {
    let entries = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
      .userFacing
    let byID = Dictionary(uniqueKeysWithValues: entries.map { ($0.id, $0) })
    let noFilters = CapabilityDiscoveryFilters()

    #expect(noFilters.matches(try #require(byID["inspect_fits"]), query: "inspect FITS"))
    #expect(noFilters.matches(try #require(byID["profile_table"]), query: "profile CSV"))
    #expect(noFilters.matches(try #require(byID["catalog_workbench.crossmatch-sky"]), query: "match sky catalogs"))

    let coreFITSSearch = CapabilityDiscoveryFilters(
      task: .inspect, format: .fits, profile: .core,
      readiness: .appReady, skill: .astro, level: .expert
    )
    #expect(entries.filter { coreFITSSearch.matches($0, query: "FITS") }.map(\.id) == ["inspect_fits"])

    let fullDocumentSearch = CapabilityDiscoveryFilters(
      task: .prepare, format: .document, profile: .full,
      readiness: .conditional, skill: .documents, level: .normal
    )
    #expect(entries.filter { fullDocumentSearch.matches($0, query: "LaTeX") }
      .map(\.id).sorted() == ["latex_workbench.compile", "latex_workbench.scaffold"])
  }

  @Test
  func profileAndReadinessFacetsDoNotPromiseUnavailableBackends() throws {
    let entries = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
      .userFacing
    let byID = Dictionary(uniqueKeysWithValues: entries.map { ($0.id, $0) })
    let core = CapabilityDiscoveryFilters(profile: .core)
    let full = CapabilityDiscoveryFilters(profile: .full)
    let ready = CapabilityDiscoveryFilters(readiness: .appReady)
    let conditional = CapabilityDiscoveryFilters(readiness: .conditional)
    let cli = CapabilityDiscoveryFilters(readiness: .cli)

    #expect(core.matches(try #require(byID["teareduce_router"]), query: ""))
    #expect(full.matches(try #require(byID["teareduce_router"]), query: ""))
    #expect(!core.matches(try #require(byID["notebook_workbench.execute-copy"]), query: ""))
    #expect(full.matches(try #require(byID["notebook_workbench.execute-copy"]), query: ""))
    #expect(conditional.matches(try #require(byID["teareduce_router"]), query: ""))
    #expect(!ready.matches(try #require(byID["teareduce_router"]), query: ""))
    #expect(cli.matches(try #require(byID["fxcor_iraf_workbench.run-auto"]), query: ""))
    #expect(!ready.matches(try #require(byID["fxcor_iraf_workbench.run-auto"]), query: ""))
    #expect(entries.filter { cli.matches($0, query: "") }.count == 12)
  }
}
