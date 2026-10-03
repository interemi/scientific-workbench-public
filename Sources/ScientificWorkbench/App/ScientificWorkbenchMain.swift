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
