import Foundation

struct CapabilitySearchResult: Sendable {
  struct Group: Identifiable, Sendable {
    let id: String
    let title: String
    let entries: [CapabilityEntry]
  }

  let entries: [CapabilityEntry]
  let groups: [Group]
}

struct CapabilitySearchIndex: Sendable {
  private struct IndexedEntry: Sendable {
    let entry: CapabilityEntry
    let discovery: CapabilityDiscovery
    let text: String

    func matches(terms: [String], filters: CapabilityDiscoveryFilters?) -> Bool {
      (filters?.matchesFacets(entry, discovery: discovery) ?? true)
        && terms.allSatisfy { text.localizedCaseInsensitiveContains($0) }
    }
  }

  private let indexed: [IndexedEntry]
  private let maintenance: Bool
  let all: CapabilitySearchResult

  init(entries: [CapabilityEntry], maintenance: Bool = false) {
    self.maintenance = maintenance
    let indexed = entries.map { entry in
      let discovery = CapabilityDiscovery.forEntry(entry)
      let text = maintenance
        ? [entry.id, entry.label, entry.shortDescription].joined(separator: " ")
        : CapabilityDiscoveryFilters.searchableText(for: entry, discovery: discovery)
      return IndexedEntry(entry: entry, discovery: discovery, text: text.precomposedStringWithCanonicalMapping)
    }
    self.indexed = indexed
    let groups: [CapabilitySearchResult.Group]
    if maintenance {
      groups = entries.groupedByBlock().map { .init(id: $0.0, title: $0.0, entries: $0.1) }
    } else {
      let byTask = Dictionary(grouping: indexed, by: \.discovery.task)
      groups = CapabilityTask.allCases.compactMap { task in
        guard let matches = byTask[task] else { return nil }
        let sorted = matches.sorted {
          if $0.entry.isGoldenPath != $1.entry.isGoldenPath { return $0.entry.isGoldenPath }
          return $0.discovery.title.localizedStandardCompare($1.discovery.title) == .orderedAscending
        }
        return .init(id: task.rawValue, title: task.title, entries: sorted.map(\.entry))
      }
    }
    all = CapabilitySearchResult(entries: entries, groups: groups)
  }

  func matching(query: String, filters: CapabilityDiscoveryFilters?) -> CapabilitySearchResult {
    let terms = queryTerms(query)
    let matches = indexed.filter { $0.matches(terms: terms, filters: filters) }.map(\.entry)
    let ids = Set(matches.map(\.id))
    let groups = all.groups.compactMap { group -> CapabilitySearchResult.Group? in
      let entries = group.entries.filter { ids.contains($0.id) }
      guard !entries.isEmpty else { return nil }
      return .init(id: group.id, title: group.title, entries: entries)
    }
    return CapabilitySearchResult(entries: matches, groups: groups)
  }

  func search(
    query: String, filters: CapabilityDiscoveryFilters?, coalescingTyping: Bool
  ) async throws -> CapabilitySearchResult {
    if coalescingTyping { try await Task.sleep(for: .milliseconds(75)) }
    try Task.checkCancellation()
    return matching(query: query, filters: filters)
  }

  func matches(id: String, query: String, filters: CapabilityDiscoveryFilters?) -> Bool? {
    indexed.first { $0.entry.id == id }?.matches(terms: queryTerms(query), filters: filters)
  }

  private func queryTerms(_ query: String) -> [String] {
    let normalized = query.precomposedStringWithCanonicalMapping
    if maintenance {
      let phrase = normalized.trimmingCharacters(in: .whitespacesAndNewlines)
      return phrase.isEmpty ? [] : [phrase]
    }
    return normalized.split(whereSeparator: \.isWhitespace).map(String.init)
  }
}
