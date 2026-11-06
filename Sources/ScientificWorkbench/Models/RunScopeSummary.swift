import Foundation

struct RunScopeSummary {
  let inputPaths: [String]
  let inputDetail: String
  let outputRoot: String
  let outputPathPreview: String
  let outputDetail: String
  let outputSafetyDetail: String
  let backendDetail: String
  let networkDetail: String
  let consentDetail: String
  let dependencyDetail: String

  init(
    capability: CapabilityEntry,
    step: AgentPlanStep,
    availableInputPaths: [String],
    configuredOutputRoot: String,
    pythonExecutable: String,
    skillRoot: String
  ) {
    inputPaths = step.usesInputs ? availableInputPaths : []
    var parts: [String] = []
    if step.usesInputs {
      parts.append("\(availableInputPaths.count) current attachment(s)")
    }
    if step.usesPreviousOutput {
      parts.append("the prior step's new output folder, resolved at run time")
    }
    inputDetail = parts.isEmpty
      ? "No attached inputs selected for this step. Review its raw arguments."
      : parts.joined(separator: " plus ") + ". Review raw arguments in Dry Run."

    outputRoot = LegacyWorkspacePolicy.shared.runRoot(
      for: capability.id,
      preferredOutputRoot: configuredOutputRoot
    )
    outputPathPreview = RunDirectoryFactory().previewPath(
      root: outputRoot,
      capabilityID: capability.id
    )
    outputDetail = outputRoot == configuredOutputRoot
      ? "A fresh child run folder will be created at execution; the timestamp and unique ID are assigned then."
      : "Legacy path rules redirect this route from the configured output root. A fresh child folder is created at execution."

    let safetyPolicy = FilesystemSafetyPolicy()
    switch safetyPolicy.assessOutputRoot(
      configuredOutputRoot,
      inputPaths: inputPaths
    ) {
    case .safe:
      switch safetyPolicy.assessOutputRoot(outputRoot, inputPaths: inputPaths) {
      case .safe:
        outputSafetyDetail = "The configured and effective roots pass the baseline path check for listed inputs; the final run validates exact paths again."
      case .requiresConfirmation(let reason):
        outputSafetyDetail = "Effective root needs review before writing: \(reason)"
      case .blocked(let reason):
        outputSafetyDetail = "Effective root is blocked until corrected: \(reason)"
      }
    case .requiresConfirmation(let reason):
      outputSafetyDetail = "Settings confirmation required before writing: \(reason)"
    case .blocked(let reason):
      outputSafetyDetail = "Blocked until the output root is corrected: \(reason)"
    }

    let interpreter = pythonExecutable.isEmpty ? DefaultPaths.systemPython : pythonExecutable
    let wrapper = URL(fileURLWithPath: capability.resolvedSkillRoot(fallback: skillRoot))
      .appendingPathComponent("scripts/datanalysis_env.py").path
    backendDetail = "Launcher: \(interpreter) \(wrapper) run-tool \(capability.scriptStem). The wrapper selects the tool environment; Dry Run previews the command with a provisional output path."

    if capability.id == "notebook_workbench.execute-copy" {
      networkDetail = "This runs copied notebook code with your macOS user permissions. Its cells may contact the network or use extra services; inspect them first."
    } else {
      networkDetail = "This Run action starts a local process and makes no new cloud-AI request. The script or an external tool may still use the network; no OS network block is imposed."
    }

    consentDetail = capability.requiresPlannerConfirmation
      ? "This restricted route requires explicit plan review and may be disabled or blocked in ordinary plans. Cloud-AI planning uses separate consent."
      : "A workflow run executes this step locally. Cloud-AI planning uses separate consent."

    let profile = CapabilityDiscovery.forEntry(capability).profile.title
    let optionalBackend: String
    switch capability.id {
    case "external_astro_tools_preflight":
      optionalBackend = "Optional Java/STILTS, TOPCAT, or APT checks; install only what the chosen route needs."
    case "stilts_workbench":
      optionalBackend = "Java and a separately obtained STILTS command or JAR."
    case "apt_workbench":
      optionalBackend = "A separately installed APT application."
    case "teareduce_router":
      optionalBackend = "A separate TEAREDUCE kernel for actual reduction; this route first checks routing and backend status."
    case "iwork_workbench":
      optionalBackend = "Bundle inventory can start locally; export paths may need Pages, Keynote, or Quick Look."
    case "keynote_export":
      optionalBackend = "Keynote and macOS Apple Events permission for the requested export."
    case "latex_workbench.compile":
      optionalBackend = "A separate TeX compiler for actual compilation."
    case "duckdb_workbench":
      optionalBackend = "DuckDB is included in the Full Python profile."
    default:
      optionalBackend = capability.appReadiness == .blockedOptional
        ? "A separate optional backend may be required; check the setup matrix and preflight."
        : "Check current packages and any route-specific preflight in Settings."
    }
    dependencyDetail = "Starting profile: \(profile). \(optionalBackend)"
  }
}
