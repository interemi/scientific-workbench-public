#if SWB_STARTUP_BUDGET
import AppKit
import Dispatch
import Foundation

enum StartupBudgetProbe {
  private static let active = ProcessInfo.processInfo.environment["SWB_STARTUP_BUDGET"] == "1"
  private static let origin = DispatchTime.now().uptimeNanoseconds
  @MainActor private static weak var store: WorkbenchStore?
  @MainActor private static var windowReady = false
  @MainActor private static var setupReady = false
  @MainActor private static var finishing = false

  static func record(_ event: String, value: String = "") {
    guard active else { return }
    let start = origin
    let elapsed = DispatchTime.now().uptimeNanoseconds - start
    FileHandle.standardOutput.write(Data("SWB_STARTUP\t\(elapsed)\t\(event)\t\(value)\n".utf8))
  }

  static func validate(_ options: LaunchAutomationOptions) {
    guard active else { return }
    precondition(options.persistentIsolatedSessionName?.hasPrefix("SWB_STARTUP_") == true
      && !options.shouldRun && !options.exitAfterRun,
      "Startup measurement requires its own persistent isolated session without automation.")
  }

  @MainActor
  static func observe(_ store: WorkbenchStore) {
    guard active else { return }
    self.store = store
    _ = NotificationCenter.default.addObserver(
      forName: NSWindow.didBecomeKeyNotification, object: nil, queue: .main
    ) { notification in
      guard let window = notification.object as? NSWindow else { return }
      MainActor.assumeIsolated {
        guard !windowReady, window.isVisible, window.canBecomeMain,
              window.identifier?.rawValue.hasPrefix("main-") == true else { return }
        record("key_window", value: window.title)
        windowReady = true
        finishIfReady()
      }
    }
  }

  @MainActor
  static func checkSetup(_ store: WorkbenchStore) async {
    guard active else { return }
    record("environment", value: store.environmentStatus.status)
    await store.waitForJobHistoryRestore()
    record("history", value: "\(store.jobs.count)|\(store.selectedJobID?.uuidString ?? "")")
    setupReady = true
    finishIfReady()
  }

  @MainActor
  private static func finishIfReady() {
    guard windowReady, setupReady, !finishing, let store else { return }
    finishing = true
    Task { @MainActor in
      await store.prepareToQuit()
      record("finished")
      exit(EXIT_SUCCESS)
    }
  }
}
#endif
