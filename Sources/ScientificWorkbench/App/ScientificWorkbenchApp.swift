import AppKit
import SwiftUI

@MainActor
final class ScientificWorkbenchAppDelegate: NSObject, NSApplicationDelegate {
  weak var store: WorkbenchStore?
  private var terminationRequested = false

  func applicationDidFinishLaunching(_ notification: Notification) {
    NSApp.setActivationPolicy(.regular)
    NSApp.activate(ignoringOtherApps: true)
  }

  func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
    guard let store else { return .terminateNow }
    if !terminationRequested {
      terminationRequested = true
      Task {
        await store.prepareToQuit()
        sender.reply(toApplicationShouldTerminate: true)
      }
    }
    return .terminateLater
  }
}

struct ScientificWorkbenchApp: App {
  @NSApplicationDelegateAdaptor(ScientificWorkbenchAppDelegate.self) private var appDelegate
  @StateObject private var store: WorkbenchStore

  init() {
    let launchOptions = LaunchAutomationOptions.parse(CommandLine.arguments)
    let store = LaunchSessionStoreFactory.makeStore(options: launchOptions, deferJobHistoryHydration: true)
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
        .onAppear { appDelegate.store = store }
        .disabled(store.isPreparingToQuit)
    }
    .commands {
      CommandGroup(replacing: .newItem) {
        Button("New Workflow") { store.beginNewWorkflow() }
          .keyboardShortcut("n")
          .disabled(!store.canChangeWorkflowContext)
      }

      CommandMenu("Workbench") {
        Button("Restore Previous Workflow Draft") { store.restorePreviousWorkflowDraft() }
          .disabled(!store.canChangeWorkflowContext || store.previousWorkflowDraft == nil)

        Divider()

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
        .disabled(store.isPreparingToQuit)
    }
  }
}
