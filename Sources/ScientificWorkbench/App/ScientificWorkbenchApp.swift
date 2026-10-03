import AppKit
import SwiftUI

final class ScientificWorkbenchAppDelegate: NSObject, NSApplicationDelegate {
  func applicationDidFinishLaunching(_ notification: Notification) {
    NSApp.setActivationPolicy(.regular)
    NSApp.activate(ignoringOtherApps: true)
  }
}

struct ScientificWorkbenchApp: App {
  @NSApplicationDelegateAdaptor(ScientificWorkbenchAppDelegate.self) private var appDelegate
  @StateObject private var store: WorkbenchStore

  init() {
    let launchOptions = LaunchAutomationOptions.parse(CommandLine.arguments)
    let store = LaunchSessionStoreFactory.makeStore(options: launchOptions)
    _store = StateObject(wrappedValue: store)
    Task { @MainActor in
      await store.startupRefresh()
      await store.runLaunchAutomation(launchOptions)
    }
  }

  var body: some Scene {
    WindowGroup("Scientific Workbench", id: "main") {
      ContentView(store: store)
        .frame(minWidth: 1120, minHeight: 720)
    }
    .commands {
      CommandMenu("Workbench") {
        Button("Reload Registry") {
          Task { await store.reloadRegistry() }
        }
        .keyboardShortcut("r", modifiers: [.command, .shift])

        Button("Refresh Environment") {
          Task { await store.refreshEnvironment() }
        }
        .keyboardShortcut("e", modifiers: [.command, .shift])

        Divider()

        Button("Export Configuration") {
          store.exportConfiguration()
        }

        Button("Import Configuration") {
          store.chooseConfigurationFile()
        }

        Divider()

        Button("Export Support Bundle") {
          store.exportSupportBundle()
        }
      }

      CommandGroup(replacing: .help) {
        Button("Scientific Workbench Guide") {
          store.openUserGuide()
        }
        .keyboardShortcut("/", modifiers: [.command, .shift])

        Button("Reveal Output Folder") {
          store.revealOutputRoot()
        }
      }
    }

    Settings {
      SettingsView(store: store)
        .frame(width: 680, height: 500)
    }
  }
}
