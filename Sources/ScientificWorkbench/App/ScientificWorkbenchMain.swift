import AppKit
import Dispatch

@main
enum ScientificWorkbenchMain {
  static func main() {
    if let smokeOptions = ProcessGroupSmokeOptions.parse(CommandLine.arguments) {
      Task {
        let exitCode = await ProcessGroupSmokeService().run(options: smokeOptions)
        exit(exitCode)
      }
      dispatchMain()
    }

    let launchOptions = LaunchAutomationOptions.parse(CommandLine.arguments)
    if launchOptions.exitAfterRun, launchOptions.shouldRun {
      DispatchQueue.main.async {
        Task { @MainActor in
          let defaults = launchOptions.isolatedSession
            ? UserDefaults(suiteName: "Scientific-Workbench-Headless-\(UUID().uuidString)") ?? .standard
            : .standard
          let store = WorkbenchStore(
            loadSecrets: launchOptions.aiProvider?.requiresAPIKey ?? true,
            defaults: defaults,
            loadPersistedState: !launchOptions.isolatedSession
          )
          await store.startupRefresh()
          await store.runLaunchAutomation(launchOptions)
        }
      }
      dispatchMain()
    } else {
      ScientificWorkbenchApp.main()
    }
  }
}
