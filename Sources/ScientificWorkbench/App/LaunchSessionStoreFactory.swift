import Foundation

enum LaunchSessionStoreFactory {
  @MainActor
  static func makeStore(options: LaunchAutomationOptions) -> WorkbenchStore {
    if let name = options.persistentIsolatedSessionName {
      precondition(!options.isolatedSession, "Persistent and one-shot isolation cannot be combined.")
      precondition(
        name.range(of: #"\A[A-Za-z0-9_-]{1,64}\z"#, options: .regularExpression) != nil,
        "Persistent session name must be 1–64 letters, digits, underscores, or hyphens."
      )
      guard let outputRoot = options.outputRootPath, outputRoot.hasPrefix("/"),
            let skillRoot = options.skillRootPath, skillRoot.hasPrefix("/"),
            let python = options.pythonExecutable, python.hasPrefix("/") else {
        preconditionFailure("Persistent isolated sessions require absolute output, skill, and Python paths.")
      }

      let suiteName = "com.interemi.scientific-workbench.acceptance.\(name)"
      guard let defaults = UserDefaults(suiteName: suiteName) else {
        preconditionFailure("Could not create isolated Scientific Workbench preferences.")
      }
      if let previousRoot = defaults.string(forKey: "outputRootPath") {
        precondition(previousRoot == outputRoot, "Session name is already associated with another output root.")
      }
      defaults.set(outputRoot, forKey: "outputRootPath")
      defaults.set(skillRoot, forKey: "skillRootPath")
      defaults.set(python, forKey: "pythonExecutable")
      defaults.set(AIProvider.ollama.rawValue, forKey: "aiProvider")

      let outputURL = URL(fileURLWithPath: outputRoot, isDirectory: true)
      let exampleRoot = outputURL.deletingLastPathComponent()
        .appendingPathComponent("\(outputURL.lastPathComponent)-examples", isDirectory: true)
      return WorkbenchStore(
        loadSecrets: false,
        defaults: defaults,
        loadPersistedState: true,
        firstRunExampleLibraryRoot: exampleRoot
      )
    }

    if options.isolatedSession {
      guard let defaults = UserDefaults(suiteName: "Scientific-Workbench-Isolated-\(UUID().uuidString)") else {
        preconditionFailure("Could not create isolated Scientific Workbench preferences.")
      }
      return WorkbenchStore(
        loadSecrets: options.aiProvider?.requiresAPIKey ?? true,
        defaults: defaults,
        loadPersistedState: false
      )
    }

    return WorkbenchStore(loadSecrets: options.aiProvider?.requiresAPIKey ?? true)
  }
}
