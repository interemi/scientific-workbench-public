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

  @Test
  func indexedCatalogSearchPreservesMatchesAndGroupOrder() throws {
    let registry = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot)
    let entries = registry.userFacing
    let index = CapabilitySearchIndex(entries: entries)
    let queries = ["", "  ", "f", "FITS inspect", "profile CSV", "match sky catalogs", "LaTeX", "no-synthetic-match"]
    let facets = [
      CapabilityDiscoveryFilters(),
      CapabilityDiscoveryFilters(task: .inspect, format: .fits, profile: .core, readiness: .appReady),
      CapabilityDiscoveryFilters(task: .prepare, profile: .full, skill: .documents, level: .normal),
      CapabilityDiscoveryFilters(readiness: .cli)
    ]
    for query in queries {
      for filters in facets {
        let expected = entries.filter { filters.matches($0, query: query) }
        let actual = index.matching(query: query, filters: filters)
        #expect(actual.entries.map(\.id) == expected.map(\.id))
        let groups = CapabilityTask.allCases.compactMap { task -> [String]? in
          let members = expected.filter { CapabilityDiscovery.forEntry($0).task == task }
          guard !members.isEmpty else { return nil }
          return members.sorted {
            if $0.isGoldenPath != $1.isGoldenPath { return $0.isGoldenPath }
            return CapabilityDiscovery.forEntry($0).title
              .localizedStandardCompare(CapabilityDiscovery.forEntry($1).title) == .orderedAscending
          }.map(\.id)
        }
        #expect(actual.groups.map { $0.entries.map(\.id) } == groups)
      }
    }

    let maintenance = registry.maintainerOnly
    let maintenanceIndex = CapabilitySearchIndex(entries: maintenance, maintenance: true)
    for query in ["", "  ", "gate", "release readiness", "no-synthetic-match"] {
      let phrase = query.trimmingCharacters(in: .whitespacesAndNewlines)
      let expected = maintenance.filter {
        phrase.isEmpty || [$0.id, $0.label, $0.shortDescription].joined(separator: " ")
          .localizedCaseInsensitiveContains(phrase)
      }
      let actual = maintenanceIndex.matching(query: query, filters: nil)
      #expect(actual.entries.map(\.id) == expected.map(\.id))
      #expect(actual.groups.map { $0.entries.map(\.id) } == expected.groupedByBlock().map { $0.1.map(\.id) })
    }
  }

  @Test
  func indexedCatalogSearchCancelsAnObsoleteQuery() async throws {
    let entries = try CapabilityRegistryLoader().load(skillRoot: DefaultPaths.motherSkillRoot).userFacing
    let index = CapabilitySearchIndex(entries: entries)
    let obsolete = Task {
      try await index.search(query: "inspect FITS", filters: CapabilityDiscoveryFilters(), coalescingTyping: true)
    }
    obsolete.cancel()
    await #expect(throws: CancellationError.self) { try await obsolete.value }

    let latest = try await index.search(
      query: "profile CSV", filters: CapabilityDiscoveryFilters(), coalescingTyping: true
    )
    #expect(latest.entries.map(\.id) == ["profile_table"])
  }
}
