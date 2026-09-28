import Foundation

enum SkillRootRole: String, CaseIterable, Codable, Sendable {
  case mother
  case astro
  case documents
  case notebooks
  case maintainer

  var defaultDirectoryName: String {
    switch self {
    case .mother: return "scientific-data-analysis"
    case .astro: return "scientific-data-astro"
    case .documents: return "scientific-data-documents"
    case .notebooks: return "scientific-data-notebooks"
    case .maintainer: return "scientific-data-maintainer"
    }
  }
}

struct SkillRootCatalog: Sendable {
  private static let explicitExecutionRoles: [String: SkillRootRole] = [
    "catalog_workbench.crossmatch-sky": .mother,
    // This cross-domain capability is implemented by the astronomy child; the
    // notebook-oriented visible block describes UI placement, not ownership.
    "spectra_ascii_coursework_workbench": .astro,
  ]
  private static let explicitlyAstroRoutedCapabilityIDs: Set<String> = [
    "external_astro_tools_preflight",
    "spectra_ascii_coursework_workbench",
  ]

  struct Root: Identifiable, Hashable, Sendable {
    var role: SkillRootRole
    var url: URL

    var id: SkillRootRole { role }
    var path: String { url.path }
    var registryStubURL: URL {
      url.appendingPathComponent("public_surface_registry.yaml")
    }
  }

  var roots: [Root]

  init(roots: [Root]) {
    self.roots = roots
  }

  static func installed(motherRootPath: String = DefaultPaths.motherSkillRoot) -> SkillRootCatalog {
    let motherURL = URL(fileURLWithPath: motherRootPath, isDirectory: true)
    let skillsDirectory = motherURL.deletingLastPathComponent()
    return SkillRootCatalog(
      roots: SkillRootRole.allCases.map { role in
        let url = role == .mother
          ? motherURL
          : skillsDirectory.appendingPathComponent(role.defaultDirectoryName, isDirectory: true)
        return Root(role: role, url: url)
      }
    )
  }

  func root(for role: SkillRootRole) -> Root? {
    roots.first { $0.role == role }
  }

  func executionRoot(
    for rawEntry: CapabilityRegistryRawEntry
  ) throws -> Root {
    let rootsWithScript = roots.filter { root in
      FileManager.default.fileExists(atPath: root.url.appendingPathComponent(rawEntry.script).path)
    }
    guard !rootsWithScript.isEmpty else {
      throw RegistryError.missingCapabilityScript(entryID: rawEntry.id, script: rawEntry.script)
    }

    let expectedRole = expectedExecutionRole(for: rawEntry)
    if let expectedRoot = roots.first(where: { $0.role == expectedRole }) {
      guard rootsWithScript.contains(where: { $0.role == expectedRole }) else {
        throw RegistryError.missingCapabilityScript(entryID: rawEntry.id, script: rawEntry.script)
      }
      return expectedRoot
    }

    // Optional modules may be genuinely absent. Only in that degraded case may
    // a compatibility wrapper in the loaded mother root own execution.
    if let motherRoot = rootsWithScript.first(where: { $0.role == .mother }) {
      return motherRoot
    }
    guard rootsWithScript.count == 1, let root = rootsWithScript.first else {
      throw RegistryError.ambiguousCapabilityOwner(
        entryID: rawEntry.id,
        roles: rootsWithScript.map(\.role)
      )
    }
    return root
  }

  private func expectedExecutionRole(for rawEntry: CapabilityRegistryRawEntry) -> SkillRootRole {
    if rawEntry.kind == "maintainer_only" {
      return .maintainer
    }
    if let explicitRole = Self.explicitExecutionRoles[rawEntry.id] {
      return explicitRole
    }
    if Self.explicitlyAstroRoutedCapabilityIDs.contains(rawEntry.id) {
      return .astro
    }
    switch rawEntry.visibleBlock {
    case "astronomy observational":
      return .astro
    case "documents + reporting":
      return .documents
    case "notebooks + cross-domain":
      return .notebooks
    case "core / routing":
      return .mother
    default:
      return .mother
    }
  }
}
