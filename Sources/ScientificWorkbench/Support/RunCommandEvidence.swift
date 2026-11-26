import Foundation

struct RunCommandEvidence: Codable, Equatable, Sendable {
  struct Argument: Codable, Equatable, Sendable {
    let option: String?
    let kind: Kind
    var reference: String?
    var choice: String?
    var integers: [Int64]?
    var numbers: [Double]?
  }

  enum Kind: String, Codable, Sendable {
    case flag, input, choice, integer, number, boundary, withheld
    case runLocation = "run_location"
  }

  let operation: String?
  let arguments: [Argument]

  var requiresLocalArguments: Bool {
    arguments.contains { $0.kind == .withheld }
  }

  static func capture(
    command: ProcessCommand, capability: CapabilityEntry, inputURLs: [URL], runRoot: URL, secrets: [String]
  ) -> (evidence: Self, runLocations: [URL: String])? {
    let wrapperArguments = command.arguments
    guard wrapperArguments.count >= 3, wrapperArguments[1] == "run-tool",
          wrapperArguments[2] == capability.scriptStem else { return nil }
    let values = Array(wrapperArguments.dropFirst(3))
    let rootContract = capability.ioContract
    let knownModes = Set(rootContract?.subcommands?.keys.map { $0 } ?? [])
      .union([capability.inferredSubcommand, rootContract?.summary.mode].compactMap { $0 })
    let operation = values.first.flatMap { value in
      knownModes.contains(value)
        && value.range(of: #"\A[a-z][a-z0-9-]{0,63}\z"#, options: .regularExpression) != nil
        && SecretsRedactor.redact(value, secrets: secrets) == value ? value : nil
    }
    let contract = operation.flatMap { rootContract?.subcommands?[$0] } ?? rootContract
    let declaredOptions = Set(((contract?.inputs ?? []) + (contract?.outputs ?? [])).map(\.argument))

    var inputReferences: [URL: String] = [:]
    for (index, url) in inputURLs.enumerated() where inputReferences[url] == nil {
      inputReferences[url] = "input-\(index + 1)"
    }
    var runLocations: [URL: String] = [:]
    let runPrefix = runRoot.path.hasSuffix("/") ? runRoot.path : runRoot.path + "/"
    func reference(for value: String, option: String?) -> Argument {
      guard value.hasPrefix("/") else { return Argument(option: option, kind: .withheld) }
      let url = FilesystemPath.canonicalURL(value)
      if let input = inputReferences[url] {
        return Argument(option: option, kind: .input, reference: input)
      }
      if url == runRoot || url.path.hasPrefix(runPrefix) {
        let name = runLocations[url] ?? "run-location-\(runLocations.count + 1)"
        runLocations[url] = name
        return Argument(option: option, kind: .runLocation, reference: name)
      }
      return Argument(option: option, kind: .withheld)
    }

    let policy = FilesystemSafetyPolicy()
    var parts: [Argument] = []
    var index = operation == nil ? 0 : 1
    var positionalOnly = false
    while index < values.count {
      let value = values[index]
      if !positionalOnly && value == "--" {
        parts.append(Argument(option: nil, kind: .boundary))
        positionalOnly = true
        index += 1
        continue
      }
      guard !positionalOnly && value.hasPrefix("-") && Double(value) == nil else {
        parts.append(reference(for: value, option: nil))
        index += 1
        continue
      }

      let split = value.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
      let option = String(split[0])
      let rule = policy.commandEvidenceOption(option, capabilityID: capability.id)
      guard rule != .unknown, SecretsRedactor.redact(option, secrets: secrets) == option else {
        // The arity of an unknown option is unavailable. Leave the remaining tokens private.
        parts.append(Argument(option: nil, kind: .withheld))
        break
      }
      if rule == .flag && split.count == 1 {
        parts.append(Argument(option: option, kind: .flag))
        index += 1
        continue
      }

      let count = Self.numericPairs.contains(option) ? 2 : 1
      let assigned: [String]
      if split.count == 2 {
        assigned = [String(split[1])]
        index += 1
      } else {
        let following = values.dropFirst(index + 1).prefix(count).prefix { !$0.hasPrefix("--") }
        assigned = Array(following)
        index += 1 + assigned.count
      }
      guard assigned.count == count,
            assigned.allSatisfy({ SecretsRedactor.redact($0, secrets: secrets) == $0 }) else {
        parts.append(Argument(option: option, kind: .withheld))
        continue
      }
      if rule == .path, let value = assigned.first {
        parts.append(reference(for: value, option: option))
      } else if rule == .value, declaredOptions.contains(option) {
        parts.append(Self.shareableValue(for: option, assigned: assigned))
      } else {
        parts.append(Argument(option: option, kind: .withheld))
      }
    }
    return (Self(operation: operation, arguments: parts), runLocations)
  }

  private static func shareableValue(for option: String, assigned: [String]) -> Argument {
    if let width = coordinateWidths[option], let value = assigned.first {
      let coordinates = value.split(separator: ",", omittingEmptySubsequences: false)
      let integers = coordinates.compactMap { Int64($0.trimmingCharacters(in: .whitespaces)) }
      if coordinates.count == width, integers.count == width {
        return Argument(option: option, kind: .integer, integers: integers)
      }
    } else if integerOptions.contains(option) {
      let integers = assigned.compactMap { Int64($0) }
      if integers.count == assigned.count {
        return Argument(option: option, kind: .integer, integers: integers)
      }
    } else if numberOptions.contains(option) || numericPairs.contains(option) {
      let numbers = assigned.compactMap { Double($0) }.filter(\.isFinite)
      if numbers.count == assigned.count {
        return Argument(option: option, kind: .number, numbers: numbers)
      }
    } else if let value = assigned.first, choices[option]?.contains(value) == true {
      return Argument(option: option, kind: .choice, choice: value)
    }
    return Argument(option: option, kind: .withheld)
  }

  private static let integerOptions: Set<String> = [
    "--continuum-degree", "--extension", "--head", "--lazy-threshold-mb", "--max-columns", "--max-files",
    "--max-per-ext", "--maxrepeat", "--n-frames", "--order", "--passes", "--preview-rows",
    "--sample-size", "--size", "--test-horizon", "--verbosity",
  ]

  private static let numberOptions: Set<String> = [
    "--coordinate-epoch-jyear", "--dark-per-pixel", "--gain", "--line-center", "--literature-ew-ma",
    "--min-separation", "--n-pixels", "--qa-residual-threshold", "--radius-arcsec", "--radius-deg",
    "--read-noise", "--scale-err", "--scale-est", "--scale-lower", "--scale-upper",
    "--sky-estimate-pixels", "--sky-per-pixel", "--source", "--timeout-sec", "--zero-point",
  ]

  private static let numericPairs: Set<String> = ["--continuum-window", "--integration-window", "--stretch-percentiles"]
  private static let coordinateWidths = ["--crop": 4, "--pixel": 2]

  private static let choices: [String: Set<String>] = [
    "--alignment-mode": ["auto", "none", "phase", "wcs"],
    "--backend": ["auto", "soffice", "keynote", "local", "web"],
    "--coordinate-frame": ["icrs"],
    "--domain": ["general", "applied", "astronomy"],
    "--format": ["markdown", "latex", "html", "csv", "tsv", "ecsv"],
    "--header-key": ["CUNIT1", "CUNIT2", "RADESYS", "CDELT1", "CDELT2"],
    "--join": ["1and2", "1or2", "all1", "all2", "1not2", "2not1", "1xor2"],
    "--kind": ["academic-report", "article", "executive-summary", "minutes", "presentation",
               "project-brief", "proposal", "qa-summary", "report", "status-report"],
    "--language": ["en", "es", "english", "spanish", "bilingual"],
    "--left-dec-unit": ["deg", "rad"],
    "--left-format": ["comma", "semicolon", "tab", "whitespace", "ecsv"],
    "--left-ra-unit": ["deg", "rad", "hourangle"],
    "--prefer": ["auto", "astropy", "pandas"],
    "--profile": ["core", "full"],
    "--right-dec-unit": ["deg", "rad"],
    "--right-format": ["comma", "semicolon", "tab", "whitespace", "ecsv"],
    "--right-ra-unit": ["deg", "rad", "hourangle"],
    "--runtime-profile": ["local", "colab"],
    "--tool": ["all", "stilts", "apt"],
    "--units": ["electrons", "adu"],
    "--validation-profile": ["quick", "deep"],
  ]
}
