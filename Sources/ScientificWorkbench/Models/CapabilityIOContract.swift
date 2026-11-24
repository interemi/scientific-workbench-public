import Foundation

struct CapabilityIOContract: Decodable, Hashable, Sendable {
  struct Argument: Decodable, Hashable, Sendable {
    let argument: String
    let format: String?
    let unit: String?
    let detail: String
  }

  struct Summary: Decodable, Hashable, Sendable {
    let container: String?
    let rejectedContainer: String?
    let tool: String?
    let mode: String?
    let version: String
    let complete: [String: String]
    let rejected: [String: String]
  }

  let revision: Int
  let backend: String
  let inputs: [Argument]
  let outputs: [Argument]
  let warnings: String
  let failure: String
  let summary: Summary
  let defaultSubcommand: String?
  let subcommands: [String: CapabilityIOContract]?

  fileprivate var hasValidArguments: Bool {
    let names = (inputs + outputs).map(\.argument)
    return revision > 0 && Set(names).count == names.count
  }
}

struct CapabilityIOContractCatalog: Decodable {
  let schemaVersion: Int
  let capabilities: [String: CapabilityIOContract]

  static func load(besideRegistryAt path: String, knownIDs: Set<String>) throws -> [String: CapabilityIOContract] {
    let directory = URL(fileURLWithPath: path).deletingLastPathComponent()
    let source = directory.appendingPathComponent("capability_io_contracts.json")
    let data: Data
    do {
      let properties = try source.resourceValues(forKeys: [.isSymbolicLinkKey, .isRegularFileKey])
      guard properties.isSymbolicLink != true, properties.isRegularFile == true else {
        throw CapabilityIOContractError.invalidSource(source.path)
      }
      data = try Data(contentsOf: source)
    } catch let error as CocoaError where error.code == .fileReadNoSuchFile || error.code == .fileNoSuchFile {
      // Installed registry snapshots from before the I/O contract remain usable.
      return [:]
    }

    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    let catalog = try decoder.decode(Self.self, from: data)
    guard catalog.schemaVersion == 1 else {
      throw CapabilityIOContractError.unsupportedSchema(catalog.schemaVersion)
    }
    for (id, contract) in catalog.capabilities {
      guard knownIDs.contains(id), contract.hasValidArguments else {
        throw CapabilityIOContractError.invalidEntry(id)
      }
      if let commands = contract.subcommands {
        guard let defaultName = contract.defaultSubcommand,
              commands[defaultName] != nil,
              commands.allSatisfy({ name, mode in
                !name.isEmpty && mode.hasValidArguments && mode.subcommands == nil && mode.defaultSubcommand == nil
              }) else {
          throw CapabilityIOContractError.invalidEntry(id)
        }
      } else if contract.defaultSubcommand != nil {
        throw CapabilityIOContractError.invalidEntry(id)
      }
    }
    return catalog.capabilities
  }
}

private enum CapabilityIOContractError: LocalizedError {
  case invalidSource(String)
  case unsupportedSchema(Int)
  case invalidEntry(String)

  var errorDescription: String? {
    switch self {
    case .invalidSource(let path):
      return "The capability I/O contracts must be a regular file at \(path)."
    case .unsupportedSchema(let version):
      return "Capability I/O contract schema \(version) is unsupported. This build supports version 1."
    case .invalidEntry(let id):
      return "Invalid capability I/O contract for \(id)."
    }
  }
}
