import AppKit
import Dispatch

@main
enum ScientificWorkbenchMain {
  static func main() {
    #if SWB_STARTUP_BUDGET
    StartupBudgetProbe.record("swift_entry", value: String(ProcessInfo.processInfo.processIdentifier))
    #endif
    if let smokeOptions = ProcessGroupSmokeOptions.parse(CommandLine.arguments) {
      Task {
        let exitCode = await ProcessGroupSmokeService().run(options: smokeOptions)
        exit(exitCode)
      }
      dispatchMain()
    }

    let launchOptions = LaunchAutomationOptions.parse(CommandLine.arguments)
    #if SWB_STARTUP_BUDGET
    StartupBudgetProbe.validate(launchOptions)
    #endif
    if launchOptions.exitAfterRun, launchOptions.shouldRun {
      DispatchQueue.main.async {
        Task { @MainActor in
          let store = LaunchSessionStoreFactory.makeStore(options: launchOptions)
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
