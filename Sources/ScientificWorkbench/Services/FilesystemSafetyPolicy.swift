import Foundation

enum FilesystemRisk: Equatable, Sendable {
  case safe
  case requiresConfirmation(String)
  case blocked(String)
}

enum FilesystemSafetyError: LocalizedError, Equatable {
  case blocked(String)
  case unsafeRawArgument(argument: String, reason: String)

  var errorDescription: String? {
    switch self {
    case .blocked(let reason):
      return reason
    case .unsafeRawArgument(let argument, let reason):
      return "Unsafe raw path argument \(argument): \(reason)"
    }
  }
}

struct FilesystemSafetyPolicy {
  var homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser

  func assessOutputRoot(_ path: String, inputPaths: [String]) -> FilesystemRisk {
    guard !path.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return .blocked("Choose a dedicated output folder before running a capability.")
    }

    let output = canonicalURL(path)
    let home = canonicalURL(homeDirectory.path)
    if output.path == "/" || output.path == home.path {
      return .blocked("The filesystem root and home folder cannot be used directly as an output root.")
    }

    for protected in protectedRoots(home: home) {
      if contains(protected, output) {
        return .blocked("The selected output root is inside protected location \(protected.path).")
      }
      if contains(output, protected) {
        return .blocked(
          "The selected output root is an overly broad ancestor of protected location \(protected.path)."
        )
      }
    }

    for inputPath in inputPaths {
      let input = canonicalURL(inputPath)
      if contains(input, output) {
        return .blocked("The output root overlaps an original input: \(displayName(input)).")
      }
    }

    let confirmationRoots = [
      home.appendingPathComponent("Desktop", isDirectory: true),
      home.appendingPathComponent("Documents", isDirectory: true),
      home.appendingPathComponent("Downloads", isDirectory: true),
    ].map { canonicalURL($0.path) }
    if confirmationRoots.contains(where: { $0.path == output.path }) {
      return .requiresConfirmation(
        "Use a dedicated Scientific Workbench subfolder instead of writing directly into \(displayName(output))."
      )
    }

    return .safe
  }

  func validateRunDirectory(
    _ runDirectory: String,
    inputPaths: [String],
    allowedRoots: [String]
  ) throws {
    let run = canonicalURL(runDirectory)
    let roots = allowedRoots.map(canonicalURL)
    guard roots.contains(where: { contains($0, run) && $0.path != run.path }) else {
      throw FilesystemSafetyError.blocked(
        "The run folder must be a child of the configured Scientific Workbench output root."
      )
    }

    if case .blocked(let reason) = assessOutputRoot(run.path, inputPaths: inputPaths) {
      throw FilesystemSafetyError.blocked(reason)
    }

    for inputPath in inputPaths {
      let input = canonicalURL(inputPath)
      if contains(input, run) {
        throw FilesystemSafetyError.blocked(
          "The run folder overlaps original input \(displayName(input)); choose a separate output root."
        )
      }
    }
  }

  func validateRawArguments(
    _ arguments: [String],
    inputPaths: [String],
    runDirectory: String,
    capabilityID: String? = nil,
    skillRoot: String? = nil
  ) throws {
    let run = canonicalURL(runDirectory)
    let derivedRoot = run.deletingLastPathComponent()
    var inputs = inputPaths.map(canonicalURL)
    if let skillRoot, capabilityAllowsSkillRootReads(capabilityID) {
      inputs.append(canonicalURL(skillRoot))
    }

    var index = 0
    var positionalIndex = 0
    var subcommand: String?
    while index < arguments.count {
      let token = arguments[index]
      if token == "--" {
        index += 1
        while index < arguments.count {
          if positionalIndex == 0 { subcommand = arguments[index] }
          try validatePositionalArgument(
            arguments[index],
            position: positionalIndex,
            capabilityID: capabilityID,
            subcommand: subcommand,
            inputs: inputs,
            derivedRoot: derivedRoot,
            runDirectory: run
          )
          positionalIndex += 1
          index += 1
        }
        continue
      }

      if let (option, value) = splitOption(token) {
        try validateOptionValue(
          value,
          option: option,
          capabilityID: capabilityID,
          inputs: inputs,
          derivedRoot: derivedRoot,
          runDirectory: run
        )
        index += 1
        continue
      }

      if isOptionToken(token) {
        let kind = optionKind(token, capabilityID: capabilityID)
        switch kind {
        case .flag:
          index += 1
        case .blocked:
          throw FilesystemSafetyError.unsafeRawArgument(
            argument: token,
            reason: "this option can access or write data outside attached inputs and is disabled in raw arguments"
          )
        case .outputPath, .readPath, .hybridReadPath, .externalReadPath,
          .hybridExternalReadPath, .safeFileName, .scalar:
          let value = try requiredValue(after: token, at: index, in: arguments)
          try validateKnownValue(
            value,
            option: token,
            kind: kind,
            inputs: inputs,
            derivedRoot: derivedRoot,
            runDirectory: run
          )
          index += 2
        case .unknown:
          if index + 1 < arguments.count, !arguments[index + 1].hasPrefix("--") {
            let value = arguments[index + 1]
            if looksPathLike(value) {
              try rejectUnknownPath(value, option: token)
            }
            index += 2
          } else {
            index += 1
          }
        }
        continue
      }

      if positionalIndex == 0 { subcommand = token }
      try validatePositionalArgument(
        token,
        position: positionalIndex,
        capabilityID: capabilityID,
        subcommand: subcommand,
        inputs: inputs,
        derivedRoot: derivedRoot,
        runDirectory: run
      )
      positionalIndex += 1
      index += 1
    }
  }

  private enum OptionKind {
    case outputPath
    case readPath
    case hybridReadPath
    case externalReadPath
    case hybridExternalReadPath
    case safeFileName
    case scalar
    case flag
    case blocked
    case unknown
  }

  private func validateOptionValue(
    _ value: String,
    option: String,
    capabilityID: String?,
    inputs: [URL],
    derivedRoot: URL,
    runDirectory: URL
  ) throws {
    let kind = optionKind(option, capabilityID: capabilityID)
    switch kind {
    case .outputPath, .readPath, .hybridReadPath, .externalReadPath,
      .hybridExternalReadPath, .safeFileName, .scalar:
      try validateKnownValue(
        value,
        option: option,
        kind: kind,
        inputs: inputs,
        derivedRoot: derivedRoot,
        runDirectory: runDirectory
      )
    case .blocked:
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: "\(option)=\(value)",
        reason: "this option can access or write data outside attached inputs and is disabled in raw arguments"
      )
    case .flag:
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: "\(option)=\(value)",
        reason: "this capability flag does not accept a value"
      )
    case .unknown:
      if looksPathLike(value) {
        try rejectUnknownPath(value, option: option)
      }
    }
  }

  private func validateKnownValue(
    _ value: String,
    option: String,
    kind: OptionKind,
    inputs: [URL],
    derivedRoot: URL,
    runDirectory: URL
  ) throws {
    switch kind {
    case .outputPath:
      try validateRawOutputPath(
        value,
        option: option,
        runDirectory: runDirectory,
        inputPaths: inputs
      )
    case .readPath:
      try validateRawReadPath(value, option: option, inputs: inputs, derivedRoot: derivedRoot)
    case .hybridReadPath:
      if looksDirectoryQualifiedPath(value) {
        try validateRawReadPath(value, option: option, inputs: inputs, derivedRoot: derivedRoot)
      }
    case .externalReadPath:
      try validateExternalReadPath(value, option: option)
    case .hybridExternalReadPath:
      if looksDirectoryQualifiedPath(value) {
        try validateExternalReadPath(value, option: option)
      }
    case .safeFileName:
      try validateSafeFileName(value, option: option)
    case .scalar, .flag, .blocked, .unknown:
      break
    }
  }

  private func validatePositionalArgument(
    _ value: String,
    position: Int,
    capabilityID: String?,
    subcommand: String?,
    inputs: [URL],
    derivedRoot: URL,
    runDirectory: URL
  ) throws {
    if positionalOutputIndices(for: capabilityID, subcommand: subcommand).contains(position) {
      try validateRawOutputPath(
        value,
        option: "positional output",
        runDirectory: runDirectory,
        inputPaths: inputs
      )
    } else {
      guard looksPathLike(value) else { return }
      try validateRawReadPath(value, option: "positional input", inputs: inputs, derivedRoot: derivedRoot)
    }
  }

  private func validateRawOutputPath(
    _ value: String,
    option: String,
    runDirectory: URL,
    inputPaths: [URL]
  ) throws {
    guard let path = absolutePath(in: value) else {
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: "\(option) \(value)",
        reason: "output paths must be absolute and located inside the current run folder"
      )
    }
    let destination = canonicalURL(path)
    guard contains(runDirectory, destination) else {
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: "\(option) \(value)",
        reason: "output paths must stay inside the current run folder"
      )
    }
    guard !inputPaths.contains(where: {
      contains($0, destination)
        || contains(destination, $0)
        || outputAliasesProtectedInput(destination, protectedInput: $0)
    }) else {
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: "\(option) \(value)",
        reason: "output paths cannot overlap an attached input"
      )
    }
  }

  private func validateRawReadPath(
    _ value: String,
    option: String,
    inputs: [URL],
    derivedRoot: URL
  ) throws {
    guard let path = absolutePath(in: value) else {
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: "\(option) \(value)",
        reason: "input paths must be absolute and explicitly attached"
      )
    }
    let candidate = canonicalURL(path)
    let allowedRead = inputs.contains(where: { contains($0, candidate) })
      || contains(derivedRoot, candidate)
    guard allowedRead else {
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: "\(option) \(value)",
        reason: "attach this path as an input or keep it inside the Scientific Workbench runs root"
      )
    }
  }

  private func validateSafeFileName(_ value: String, option: String) throws {
    let invalid = value.isEmpty
      || value == "."
      || value == ".."
      || value.contains("/")
      || value.contains("\\")
      || value.contains("\0")
    guard !invalid else {
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: "\(option) \(value)",
        reason: "use a filename only, without directory traversal"
      )
    }
  }

  private func validateExternalReadPath(_ value: String, option: String) throws {
    guard absolutePath(in: value) != nil else {
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: "\(option) \(value)",
        reason: "configured external paths must be absolute"
      )
    }
  }

  private func requiredValue(after option: String, at index: Int, in arguments: [String]) throws -> String {
    guard index + 1 < arguments.count, !arguments[index + 1].hasPrefix("--") else {
      throw FilesystemSafetyError.unsafeRawArgument(
        argument: option,
        reason: "this option requires a value"
      )
    }
    return arguments[index + 1]
  }

  private func rejectUnknownPath(_ value: String, option: String) throws -> Never {
    throw FilesystemSafetyError.unsafeRawArgument(
      argument: "\(option) \(value)",
      reason: "unrecognized path-bearing options are blocked; use a registered capability argument"
    )
  }

  private func absolutePath(in token: String) -> String? {
    if token.hasPrefix("/") {
      return token
    }
    if token == "~" || token.hasPrefix("~/") {
      return NSString(string: token).expandingTildeInPath
    }
    return nil
  }

  private func looksPathLike(_ value: String) -> Bool {
    if looksDirectoryQualifiedPath(value) {
      return true
    }

    let pathExtensions: Set<String> = [
      "csv", "db", "docx", "ecsv", "fit", "fits", "fts", "h5", "hdf5", "ipynb",
      "jar", "json", "log", "md", "parquet", "pdf", "png", "pptx", "py", "sav",
      "sqlite", "tex", "toml", "txt", "xlsx", "yaml", "yml", "zip",
    ]
    return pathExtensions.contains(URL(fileURLWithPath: value).pathExtension.lowercased())
  }

  private func looksDirectoryQualifiedPath(_ value: String) -> Bool {
    absolutePath(in: value) != nil
      || value.hasPrefix("./")
      || value.hasPrefix("../")
      || value.contains("/")
  }

  private func splitOption(_ token: String) -> (String, String)? {
    guard token.hasPrefix("--"), let separator = token.firstIndex(of: "=") else { return nil }
    let option = String(token[..<separator])
    let value = String(token[token.index(after: separator)...])
    return (option, value)
  }

  private func isOptionToken(_ token: String) -> Bool {
    guard token.hasPrefix("-") else { return false }
    return Double(token) == nil
  }

  private func optionKind(_ option: String, capabilityID: String?) -> OptionKind {
    let normalized = option.lowercased()

    if blockedOptions(for: capabilityID).contains(where: {
      $0 == normalized || $0.hasPrefix(normalized)
    }) {
      return .blocked
    }
    if capabilityAllowsAPTConfiguration(capabilityID) {
      if normalized == "--apt-command" {
        return .hybridExternalReadPath
      }
      if normalized == "--apt-preferences" {
        return .externalReadPath
      }
    }
    if normalized == "--report-md", capabilityID == "echelle_multispec_inventory" {
      return .flag
    }
    if Self.outputPathOptions.contains(normalized) {
      return .outputPath
    }
    if Self.readPathOptions.contains(normalized) {
      return .readPath
    }
    if Self.hybridReadPathOptions.contains(normalized) {
      return .hybridReadPath
    }
    if Self.safeFileNameOptions.contains(normalized) {
      return .safeFileName
    }
    if Self.scalarOptions.contains(normalized) {
      return .scalar
    }
    if Self.flagOptions.contains(normalized) {
      return .flag
    }
    return .unknown
  }

  private func blockedOptions(for capabilityID: String?) -> Set<String> {
    var options: Set<String> = [
      "--api-base", "--api-key", "--force", "--overwrite", "--run-from-source-dir",
    ]
    if capabilityID == "duckdb_workbench" || capabilityID == "cross_domain_data_workbench" {
      options.insert("--sql")
    }
    if capabilityID == "notebook_workbench.execute-copy" {
      options.formUnion(["--append-code", "--replace-text"])
    }
    return options
  }

  private static let outputPathOptions: Set<String> =
    [
      "--coefficients-csv", "--comparison-png", "--contact-sheet", "--cwd", "--destination",
      "--diff-json", "--export", "--export-preview-pdf", "--html-report", "--log", "--log-dir",
      "--log-txt", "--manifest", "--manifest-json", "--native-preview", "--out", "--output",
      "--output-csv", "--output-dir", "--output-file", "--output-json", "--output-md",
      "--output-path", "--output-root", "--output-table", "--output-zip", "--preview",
      "--query-output", "--report", "--report-md", "--residual-csv", "--residual-plot", "--save",
      "--summary-json",
    ]

  private static let readPathOptions: Set<String> =
    [
      "--append-code-file", "--apt-preferences", "--assignment-file", "--backend-config",
      "--calibration-csv", "--data-path", "--envcheck", "--examples-dir",
      "--external-reference-summary", "--fits-root", "--fxcor-csv", "--fxcor-summary",
      "--gzleo-fits", "--image", "--index-dir", "--index-file", "--input", "--input-file",
      "--input-root", "--inventory-summary", "--istarmod-summary", "--li-summary", "--manual-csv",
      "--notebook", "--previous-png", "--registry", "--root", "--rv-summary", "--sm-file",
      "--source", "--source-list", "--stage-extra", "--stilts-jar", "--topcat-jar", "--verify-wcs",
    ]

  private static let hybridReadPathOptions: Set<String> =
    ["--file", "--java-command", "--latexmk-path", "--python-bin", "--solve-field-bin"]

  private static let safeFileNameOptions: Set<String> =
    ["--notebook-name", "--output-dir-name"]

  private static let scalarOptions: Set<String> =
    [
      "--airmass-col", "--alignment-mode", "--allow-commercial-use", "--allow-modifications",
      "--api-base", "--api-key", "--append-code", "--append-markdown", "--author", "--backend",
      "--branch-token", "--cache-policy", "--case-id", "--cell", "--cell-range", "--center-dec",
      "--center-ra", "--color-col", "--confirmation-id", "--continuum-degree",
      "--continuum-window", "--cpulimit-sec", "--crop", "--dark-per-pixel", "--date-column",
      "--depth", "--domain", "--download-product", "--downsample-factor", "--error-col",
      "--expression", "--extension", "--fallback-scale-err", "--fallback-scale-est", "--find",
      "--fixed-rv", "--format", "--frequency", "--gain", "--hdu", "--head", "--header-key",
      "--how", "--id-col", "--ifmt", "--ifmt1", "--ifmt2", "--input-format", "--input-value",
      "--inst-mag-col", "--integration-window", "--intent", "--join", "--kernel-name", "--kind",
      "--kinematics-mode", "--language", "--lazy-threshold-mb", "--left-dec", "--left-key",
      "--left-ra", "--line-center", "--line-label", "--line-window", "--literature-ew-ma",
      "--max-columns", "--max-files", "--max-per-ext", "--max-separation-index", "--maxrepeat",
      "--min-separation", "--n-frames", "--n-pixels", "--new-label", "--nsigma", "--object-name",
      "--objs", "--ofmt", "--order", "--parity", "--passes", "--peer-count", "--peer-strategy",
      "--planet-count", "--poll-sec", "--prefer", "--preview-rows", "--previous-label", "--profile",
      "--publicly-visible", "--qa-residual-threshold", "--radius-arcsec", "--radius-deg",
      "--read-noise", "--reason", "--reference-slides", "--replace", "--replace-text",
      "--report-author", "--report-title", "--right-dec", "--right-key", "--right-ra", "--rule",
      "--run-id", "--runtime-profile", "--sample-size", "--scale-err", "--scale-est",
      "--scale-lower", "--scale-type", "--scale-units", "--scale-upper", "--sheet", "--size",
      "--sky-estimate-pixels", "--sky-per-pixel", "--std-mag-col", "--stretch-percentiles",
      "--system-name", "--target-name", "--task", "--test-horizon", "--timeout-sec", "--title",
      "--tool", "--tweak-order", "--unit", "--units", "--validation-profile", "--value",
      "--value-column", "--verbosity", "--wall-timeout-sec", "--x-col", "--y-col", "--zero-point",
    ]

  private static let flagOptions: Set<String> =
    [
      "--check", "--clean-derived", "--compile-report", "--continue-run", "--crpix-center",
      "--deep-pdf", "--dry-run", "--enable-ocr", "--execute-notebook", "--export-pdf", "--force",
      "--force-simple-fallback", "--include-apt-batch", "--include-color-term",
      "--include-maintainer-help", "--include-system-iwork-samples", "--lazy", "--no-plots",
      "--no-stacks", "--no-verify", "--overwrite", "--preflight-only", "--probe", "--require-apt",
      "--require-bold", "--require-confirmation", "--require-italic", "--require-stilts",
      "--require-underline", "--same-exptime", "--same-object", "--skip-hygiene",
      "--skip-notebook-exec", "--skip-report-project", "--skip-solved", "--skip-systematic-grid",
      "--strict-core", "--use-sextractor",
      "--ucd", "--no-ucd", "--validate", "--no-validate",
    ]

  private func positionalOutputIndices(for capabilityID: String?, subcommand: String?) -> Set<Int> {
    switch capabilityID {
    case "stilts_workbench":
      switch subcommand {
      case "convert", "filter", "votlint": return [2]
      case "crossmatch-sky": return [3]
      default: return []
      }
    case "bootstrap_analysis_notebook", "deliverable_factory.scaffold", "latex_workbench.scaffold",
      "legacy_spectroscopy_report_builder.populate", "legacy_spectroscopy_report_builder.scaffold":
      return [0]
    case "keynote_export", "office_roundtrip.docx-styled-replace",
      "presentation_workbench.existing-deck-style-audit", "rgb_visual_fits_export":
      return [1]
    case "catalog_workbench.crossmatch-sky":
      return [2]
    default:
      return []
    }
  }

  private func capabilityAllowsAPTConfiguration(_ capabilityID: String?) -> Bool {
    capabilityID == "apt_workbench" || capabilityID == "external_astro_tools_preflight"
  }

  private func capabilityAllowsSkillRootReads(_ capabilityID: String?) -> Bool {
    let capabilityIDs: Set<String> = [
      "legacy_external_reference_check",
      "legacy_spectroscopy_envcheck",
      "legacy_spectroscopy_report_builder.populate",
      "legacy_spectroscopy_report_builder.scaffold",
      "portable_smoke_test",
    ]
    guard let capabilityID else { return false }
    return capabilityIDs.contains(capabilityID)
  }

  private func protectedRoots(home: URL) -> [URL] {
    let system = [
      "/System", "/Library", "/Applications", "/bin", "/sbin", "/usr", "/etc"
    ].map(canonicalURL)
    let user = [".ssh", ".gnupg", ".aws", ".codex", "Library"]
      .map { canonicalURL(home.appendingPathComponent($0, isDirectory: true).path) }
    return system + user
  }

  private func canonicalURL(_ path: String) -> URL {
    FilesystemPath.canonicalURL(path)
  }

  private struct FileIdentity: Equatable {
    let device: UInt64
    let inode: UInt64
  }

  private func fileIdentity(_ url: URL) -> FileIdentity? {
    guard
      let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
      let device = attributes[.systemNumber] as? NSNumber,
      let inode = attributes[.systemFileNumber] as? NSNumber
    else {
      return nil
    }
    return FileIdentity(device: device.uint64Value, inode: inode.uint64Value)
  }

  private func hardLinkCount(_ url: URL) -> UInt64? {
    guard
      let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
      let count = attributes[.referenceCount] as? NSNumber
    else {
      return nil
    }
    return count.uint64Value
  }

  private func outputAliasesProtectedInput(_ output: URL, protectedInput input: URL) -> Bool {
    guard let outputIdentity = fileIdentity(output) else { return false }
    if outputIdentity == fileIdentity(input) {
      return true
    }

    var isDirectory: ObjCBool = false
    guard
      FileManager.default.fileExists(atPath: input.path, isDirectory: &isDirectory),
      isDirectory.boolValue,
      (hardLinkCount(output) ?? 1) > 1,
      let descendants = FileManager.default.enumerator(
        at: input,
        includingPropertiesForKeys: nil,
        options: [],
        errorHandler: { _, _ in true }
      )
    else {
      return false
    }

    for case let candidate as URL in descendants {
      if fileIdentity(candidate) == outputIdentity {
        return true
      }
    }
    return false
  }

  private func contains(_ parent: URL, _ child: URL) -> Bool {
    if parent.path == child.path { return true }
    let prefix = parent.path == "/" ? "/" : parent.path + "/"
    return child.path.hasPrefix(prefix)
  }

  private func displayName(_ url: URL) -> String {
    url.lastPathComponent.isEmpty ? url.path : url.lastPathComponent
  }
}
