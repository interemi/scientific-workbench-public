import CryptoKit
import Foundation

struct CapabilityRegistryRawEntry: Hashable, Sendable {
  var id: String
  var label: String
  var script: String
  var visibleBlock: String
  var kind: String
  var supportLevel: String
  var platform: String
  var requiresDatanalysis: Bool
  var preflightMode: String
  var smokeTier: String
  var shortDescription: String
  var allowedEnvironmentKeys: Set<String>
}

struct CapabilityRegistryResolution: Hashable, Sendable {
  var role: SkillRootRole
  var rootPath: String
  var stubPath: String
  var resolvedPath: String
  var fingerprint: String
}

enum CapabilityRegistryDegradationReason: String, Hashable, Sendable {
  case notConfigured = "not_configured"
  case notInstalled = "not_installed"
}

struct CapabilityRegistryUnavailableRoot: Hashable, Sendable {
  var role: SkillRootRole
  var rootPath: String
  var reason: CapabilityRegistryDegradationReason
}

struct CapabilityRegistryLoadResult: Hashable, Sendable {
  var entries: [CapabilityEntry]
  var unavailableOptionalRoots: [CapabilityRegistryUnavailableRoot]

  var isDegraded: Bool {
    !unavailableOptionalRoots.isEmpty
  }
}

private struct LoadedCapabilityRegistry {
  var root: SkillRootCatalog.Root
  var resolution: CapabilityRegistryResolution
  var rawEntries: [CapabilityRegistryRawEntry]
}

private struct RegisteredCapability {
  var rawEntry: CapabilityRegistryRawEntry
  var resolution: CapabilityRegistryResolution
}

struct CapabilityRegistryLoader {
  private let maximumCanonicalDepth = 8
  private let allowedCapabilityKinds: Set<String> = [
    "golden_path",
    "supporting_tool",
    "maintainer_only",
  ]
  private let allowedVisibleBlocks: Set<String> = [
    "core / routing",
    "astronomy observational",
    "documents + reporting",
    "notebooks + cross-domain",
  ]
  private let allowedSupportLevels: Set<String> = ["stable", "narrow", "optional", "platform_bound"]
  private let allowedPlatforms: Set<String> = ["portable", "datanalysis", "macos"]
  private let allowedPreflightModes: Set<String> = ["none", "inline", "explicit"]
  private let allowedSmokeTiers: Set<String> = ["none", "core", "full"]
  private let allowedBooleanValues: Set<String> = ["true", "false"]

  func load(skillRoot: String) throws -> [CapabilityEntry] {
    try loadWithDiagnostics(skillRoot: skillRoot).entries
  }

  func load(catalog: SkillRootCatalog) throws -> [CapabilityEntry] {
    try loadWithDiagnostics(catalog: catalog).entries
  }

  func loadWithDiagnostics(skillRoot: String) throws -> CapabilityRegistryLoadResult {
    try loadWithDiagnostics(catalog: SkillRootCatalog.installed(motherRootPath: skillRoot))
  }

  func loadWithDiagnostics(catalog: SkillRootCatalog) throws -> CapabilityRegistryLoadResult {
    let rootsByRole = try indexRootsByRole(catalog.roots)
    guard let motherRoot = rootsByRole[.mother] else {
      throw RegistryError.missingRequiredSkillRoot(.mother)
    }

    var unavailableOptionalRoots: [CapabilityRegistryUnavailableRoot] = []
    var loadedRegistries = [try loadRegistry(for: motherRoot)]
    for role in SkillRootRole.allCases where role != .mother {
      guard let root = rootsByRole[role] else {
        unavailableOptionalRoots.append(
          CapabilityRegistryUnavailableRoot(
            role: role,
            rootPath: inferredRootPath(for: role, relativeTo: motherRoot),
            reason: .notConfigured
          )
        )
        continue
      }
      guard FileManager.default.fileExists(atPath: root.path) else {
        unavailableOptionalRoots.append(
          CapabilityRegistryUnavailableRoot(
            role: role,
            rootPath: root.path,
            reason: .notInstalled
          )
        )
        continue
      }
      // A configured child that exists but has a broken registry is drift, not
      // an optional-module absence. Let resolution/parsing errors propagate.
      loadedRegistries.append(try loadRegistry(for: root))
    }

    var registeredByID: [String: RegisteredCapability] = [:]
    var orderedIDs: [String] = []
    for loadedRegistry in loadedRegistries {
      for rawEntry in loadedRegistry.rawEntries {
        if let registered = registeredByID[rawEntry.id] {
          try validateDuplicate(
            rawEntry,
            resolution: loadedRegistry.resolution,
            against: registered
          )
          continue
        }
        registeredByID[rawEntry.id] = RegisteredCapability(
          rawEntry: rawEntry,
          resolution: loadedRegistry.resolution
        )
        orderedIDs.append(rawEntry.id)
      }
    }

    let availableCatalog = SkillRootCatalog(roots: loadedRegistries.map(\.root))
    let entries = try orderedIDs.compactMap { id -> CapabilityEntry? in
      guard let registered = registeredByID[id] else { return nil }
      let owner = try availableCatalog.executionRoot(for: registered.rawEntry)
      let ownerResolution = loadedRegistries.first { loadedRegistry in
        loadedRegistry.root.role == owner.role &&
          loadedRegistry.rawEntries.contains(registered.rawEntry)
      }?.resolution
      return buildEntry(
        from: registered.rawEntry,
        owningRoot: owner,
        registryResolution: ownerResolution ?? registered.resolution
      )
    }
    return CapabilityRegistryLoadResult(
      entries: entries,
      unavailableOptionalRoots: unavailableOptionalRoots
    )
  }

  private func indexRootsByRole(
    _ roots: [SkillRootCatalog.Root]
  ) throws -> [SkillRootRole: SkillRootCatalog.Root] {
    var rootsByRole: [SkillRootRole: SkillRootCatalog.Root] = [:]
    for root in roots {
      guard rootsByRole[root.role] == nil else {
        throw RegistryError.duplicateSkillRootRole(root.role)
      }
      rootsByRole[root.role] = root
    }
    return rootsByRole
  }

  private func inferredRootPath(
    for role: SkillRootRole,
    relativeTo motherRoot: SkillRootCatalog.Root
  ) -> String {
    motherRoot.url.deletingLastPathComponent()
      .appendingPathComponent(role.defaultDirectoryName, isDirectory: true)
      .path
  }

  private func loadRegistry(
    for root: SkillRootCatalog.Root
  ) throws -> LoadedCapabilityRegistry {
    let resolution = try resolveRegistry(for: root)
    let text = try String(
      contentsOf: URL(fileURLWithPath: resolution.resolvedPath),
      encoding: .utf8
    )
    return LoadedCapabilityRegistry(
      root: root,
      resolution: resolution,
      rawEntries: try parseRawEntries(text)
    )
  }

  private func validateDuplicate(
    _ duplicate: CapabilityRegistryRawEntry,
    resolution: CapabilityRegistryResolution,
    against registered: RegisteredCapability
  ) throws {
    guard duplicate == registered.rawEntry else {
      throw RegistryError.duplicateCapabilityMetadata(
        id: duplicate.id,
        firstRegistry: registered.resolution.resolvedPath,
        duplicateRegistry: resolution.resolvedPath
      )
    }
    guard resolution.fingerprint == registered.resolution.fingerprint else {
      throw RegistryError.incompatibleRegistryFingerprints(
        id: duplicate.id,
        firstRegistry: registered.resolution.resolvedPath,
        firstFingerprint: registered.resolution.fingerprint,
        duplicateRegistry: resolution.resolvedPath,
        duplicateFingerprint: resolution.fingerprint
      )
    }
  }

  func parse(_ text: String) throws -> [CapabilityEntry] {
    var uniqueByID: [String: CapabilityRegistryRawEntry] = [:]
    var orderedEntries: [CapabilityRegistryRawEntry] = []
    for rawEntry in try parseRawEntries(text) {
      if let existing = uniqueByID[rawEntry.id] {
        guard existing == rawEntry else {
          throw RegistryError.duplicateCapabilityMetadata(
            id: rawEntry.id,
            firstRegistry: "<inline>",
            duplicateRegistry: "<inline>"
          )
        }
        continue
      }
      uniqueByID[rawEntry.id] = rawEntry
      orderedEntries.append(rawEntry)
    }
    return orderedEntries.map { rawEntry in
      buildEntry(
        from: rawEntry,
        owningRoot: nil,
        registryResolution: nil
      )
    }
  }

  func resolveRegistry(for root: SkillRootCatalog.Root) throws -> CapabilityRegistryResolution {
    var registryURL = root.registryStubURL
    var visited: Set<String> = []
    var depth = 0
    let skillsDirectory = root.url.deletingLastPathComponent()
    let allowedFamilyRoots = ([root.url] + SkillRootRole.allCases.map { role in
      skillsDirectory.appendingPathComponent(role.defaultDirectoryName, isDirectory: true)
    })
    .map { $0.standardizedFileURL.resolvingSymlinksInPath() }
    .reduce(into: [URL]()) { roots, candidate in
      guard !roots.contains(where: { $0.path == candidate.path }) else { return }
      roots.append(candidate)
    }

    while true {
      let canonicalRegistryURL = registryURL.standardizedFileURL.resolvingSymlinksInPath()
      guard allowedFamilyRoots.contains(where: { contains($0, canonicalRegistryURL) }) else {
        throw RegistryError.canonicalRegistryOutsideSkillFamily(
          path: canonicalRegistryURL.path,
          allowedRoots: allowedFamilyRoots.map(\.path).sorted()
        )
      }
      registryURL = canonicalRegistryURL
      guard FileManager.default.fileExists(atPath: registryURL.path) else {
        throw RegistryError.missingRegistry(registryURL.path)
      }
      let standardizedPath = registryURL.path
      guard visited.insert(standardizedPath).inserted else {
        throw RegistryError.canonicalRegistryCycle(standardizedPath)
      }
      let text = try String(contentsOf: registryURL, encoding: .utf8)
      if let canonical = canonicalRegistryPath(in: text) {
        depth += 1
        guard depth <= maximumCanonicalDepth else {
          throw RegistryError.canonicalRegistryTooDeep(root.registryStubURL.path)
        }
        registryURL = registryURL.deletingLastPathComponent()
          .appendingPathComponent(canonical)
          .standardizedFileURL
        continue
      }
      guard text.split(separator: "\n").contains(where: { $0.trimmingCharacters(in: .whitespaces) == "entries:" }) else {
        throw RegistryError.registryHasNoEntries(registryURL.path)
      }
      return CapabilityRegistryResolution(
        role: root.role,
        rootPath: root.path,
        stubPath: root.registryStubURL.path,
        resolvedPath: registryURL.path,
        fingerprint: stableFingerprint(for: text)
      )
    }
  }

  private func parseRawEntries(_ text: String) throws -> [CapabilityRegistryRawEntry] {
    var rawEntries: [[String: String]] = []
    var current: [String: String]?

    for rawLine in text.split(separator: "\n", omittingEmptySubsequences: false) {
      let line = String(rawLine)
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      guard !trimmed.isEmpty, !trimmed.hasPrefix("#") else { continue }
      guard trimmed != "entries:" else { continue }

      if trimmed.hasPrefix("- ") {
        if let current {
          rawEntries.append(current)
        }
        current = [:]
        let rest = String(trimmed.dropFirst(2))
        if let pair = parseKeyValue(rest) {
          current?[pair.key] = pair.value
        }
        continue
      }

      guard var entry = current, let pair = parseKeyValue(trimmed) else { continue }
      entry[pair.key] = pair.value
      current = entry
    }

    if let current {
      rawEntries.append(current)
    }

    return try rawEntries.map(buildRawEntry)
  }

  private func canonicalRegistryPath(in text: String) -> String? {
    for rawLine in text.split(separator: "\n", omittingEmptySubsequences: false) {
      let line = String(rawLine).trimmingCharacters(in: .whitespaces)
      guard line.hasPrefix("canonical_registry:") else { continue }
      let value = String(line.dropFirst("canonical_registry:".count))
        .trimmingCharacters(in: .whitespacesAndNewlines)
      return unquote(value)
    }
    return nil
  }

  private func parseKeyValue(_ line: String) -> (key: String, value: String)? {
    guard let separator = line.firstIndex(of: ":") else { return nil }
    let key = String(line[..<separator]).trimmingCharacters(in: .whitespaces)
    let valueStart = line.index(after: separator)
    let rawValue = String(line[valueStart...]).trimmingCharacters(in: .whitespaces)
    return (key, unquote(rawValue))
  }

  private func unquote(_ value: String) -> String {
    guard value.count >= 2 else { return value }
    if (value.hasPrefix("\"") && value.hasSuffix("\"")) ||
      (value.hasPrefix("'") && value.hasSuffix("'")) {
      return String(value.dropFirst().dropLast())
    }
    return value
  }

  private func buildRawEntry(from raw: [String: String]) throws -> CapabilityRegistryRawEntry {
    guard
      let id = raw["id"],
      let label = raw["label"],
      let script = raw["script"],
      let visibleBlock = raw["visible_block"],
      let kind = raw["kind"],
      let supportLevel = raw["support_level"],
      let platform = raw["platform"],
      let requiresDatanalysis = raw["requires_datanalysis"],
      let preflightMode = raw["preflight_mode"],
      let smokeTier = raw["smoke_tier"],
      let shortDescription = raw["short_description"]
    else {
      throw RegistryError.missingRequiredField(raw)
    }
    try validateRegistryValue(kind, field: "kind", entryID: id, allowed: allowedCapabilityKinds)
    try validateRegistryValue(
      visibleBlock,
      field: "visible_block",
      entryID: id,
      allowed: allowedVisibleBlocks
    )
    try validateRegistryValue(
      supportLevel,
      field: "support_level",
      entryID: id,
      allowed: allowedSupportLevels
    )
    try validateRegistryValue(platform, field: "platform", entryID: id, allowed: allowedPlatforms)
    try validateRegistryValue(
      requiresDatanalysis,
      field: "requires_datanalysis",
      entryID: id,
      allowed: allowedBooleanValues
    )
    try validateRegistryValue(
      preflightMode,
      field: "preflight_mode",
      entryID: id,
      allowed: allowedPreflightModes
    )
    try validateRegistryValue(smokeTier, field: "smoke_tier", entryID: id, allowed: allowedSmokeTiers)
    let allowedEnvironmentKeys = try parseAllowedEnvironmentKeys(
      raw["allowed_environment_keys"] ?? "",
      entryID: id
    )

    return CapabilityRegistryRawEntry(
      id: id,
      label: label,
      script: script,
      visibleBlock: visibleBlock,
      kind: kind,
      supportLevel: supportLevel,
      platform: platform,
      requiresDatanalysis: requiresDatanalysis == "true",
      preflightMode: preflightMode,
      smokeTier: smokeTier,
      shortDescription: shortDescription,
      allowedEnvironmentKeys: allowedEnvironmentKeys
    )
  }

  private func validateRegistryValue(
    _ value: String,
    field: String,
    entryID: String,
    allowed: Set<String>
  ) throws {
    guard allowed.contains(value) else {
      throw RegistryError.invalidCapabilityField(
        entryID: entryID,
        field: field,
        value: value,
        allowed: allowed.sorted()
      )
    }
  }

  private func buildEntry(
    from raw: CapabilityRegistryRawEntry,
    owningRoot: SkillRootCatalog.Root?,
    registryResolution: CapabilityRegistryResolution?
  ) -> CapabilityEntry {
    CapabilityEntry(
      id: raw.id,
      label: raw.label,
      script: raw.script,
      visibleBlock: raw.visibleBlock,
      kind: raw.kind,
      supportLevel: raw.supportLevel,
      platform: raw.platform,
      requiresDatanalysis: raw.requiresDatanalysis,
      preflightMode: raw.preflightMode,
      smokeTier: raw.smokeTier,
      shortDescription: raw.shortDescription,
      allowedEnvironmentKeys: raw.allowedEnvironmentKeys,
      owningSkillRoot: owningRoot?.path,
      owningSkillRole: owningRoot?.role.rawValue,
      registrySourcePath: registryResolution?.resolvedPath,
      registryFingerprint: registryResolution?.fingerprint
    )
  }

  private func parseAllowedEnvironmentKeys(
    _ rawValue: String,
    entryID: String
  ) throws -> Set<String> {
    let keys = rawValue.split(separator: ",", omittingEmptySubsequences: false)
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }

    for key in keys {
      guard ProcessEnvironmentKeyPolicy.isValidName(key) else {
        throw RegistryError.invalidEnvironmentKey(entryID: entryID, key: key)
      }
      guard !ProcessEnvironmentKeyPolicy.isSensitive(key) else {
        throw RegistryError.sensitiveEnvironmentKey(entryID: entryID, key: key)
      }
    }
    return Set(keys)
  }

  private func stableFingerprint(for text: String) -> String {
    SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
  }

  private func contains(_ parent: URL, _ child: URL) -> Bool {
    if parent.path == child.path { return true }
    let prefix = parent.path == "/" ? "/" : parent.path + "/"
    return child.path.hasPrefix(prefix)
  }
}

enum RegistryError: LocalizedError {
  case missingRequiredField([String: String])
  case invalidCapabilityField(entryID: String, field: String, value: String, allowed: [String])
  case invalidEnvironmentKey(entryID: String, key: String)
  case sensitiveEnvironmentKey(entryID: String, key: String)
  case missingRequiredSkillRoot(SkillRootRole)
  case duplicateSkillRootRole(SkillRootRole)
  case missingRegistry(String)
  case canonicalRegistryCycle(String)
  case canonicalRegistryTooDeep(String)
  case canonicalRegistryOutsideSkillFamily(path: String, allowedRoots: [String])
  case registryHasNoEntries(String)
  case missingCapabilityScript(entryID: String, script: String)
  case ambiguousCapabilityOwner(entryID: String, roles: [SkillRootRole])
  case duplicateCapabilityMetadata(id: String, firstRegistry: String, duplicateRegistry: String)
  case incompatibleRegistryFingerprints(
    id: String,
    firstRegistry: String,
    firstFingerprint: String,
    duplicateRegistry: String,
    duplicateFingerprint: String
  )

  var errorDescription: String? {
    switch self {
    case .missingRequiredField(let raw):
      return "A registry entry is missing one or more required contract fields: \(raw)"
    case .invalidCapabilityField(let entryID, let field, let value, let allowed):
      return "Capability \(entryID) declares unsupported \(field)=\(value); expected one of: " +
        allowed.joined(separator: ", ")
    case .invalidEnvironmentKey(let entryID, let key):
      return "Capability \(entryID) declares an invalid environment variable name: \(key)"
    case .sensitiveEnvironmentKey(let entryID, let key):
      return "Capability \(entryID) cannot allow a sensitive environment variable: \(key)"
    case .missingRequiredSkillRoot(let role):
      return "The required \(role.rawValue) skill root is not configured."
    case .duplicateSkillRootRole(let role):
      return "The skill root catalog configures the \(role.rawValue) role more than once."
    case .missingRegistry(let path):
      return "Could not find public surface registry at \(path)."
    case .canonicalRegistryCycle(let path):
      return "The public surface registry canonical_registry chain contains a cycle at \(path)."
    case .canonicalRegistryTooDeep(let path):
      return "The public surface registry canonical_registry chain is too deep from \(path)."
    case .canonicalRegistryOutsideSkillFamily(let path, let allowedRoots):
      return "The public surface registry resolves outside the configured skill family " +
        "(\(allowedRoots.joined(separator: ", "))): \(path)."
    case .registryHasNoEntries(let path):
      return "The public surface registry at \(path) does not contain entries."
    case .missingCapabilityScript(let entryID, let script):
      return "Capability \(entryID) declares \(script), but no configured skill root contains that script."
    case .ambiguousCapabilityOwner(let entryID, let roles):
      let roleNames = roles.map(\.rawValue).sorted().joined(separator: ", ")
      return "Capability \(entryID) has ambiguous execution ownership across: \(roleNames)."
    case .duplicateCapabilityMetadata(let id, let firstRegistry, let duplicateRegistry):
      return "Capability \(id) has divergent metadata in \(firstRegistry) and \(duplicateRegistry)."
    case .incompatibleRegistryFingerprints(
      let id,
      let firstRegistry,
      let firstFingerprint,
      let duplicateRegistry,
      let duplicateFingerprint
    ):
      return "Capability \(id) is duplicated across incompatible registry snapshots: " +
        "\(firstRegistry) (\(firstFingerprint)) and \(duplicateRegistry) (\(duplicateFingerprint))."
    }
  }
}
