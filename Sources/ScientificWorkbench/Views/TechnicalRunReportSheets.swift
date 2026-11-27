import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct TechnicalRunReportSheet: View {
  @Environment(\.dismiss) private var dismiss
  let store: WorkbenchStore
  let job: JobRecord
  @State private var question = ""
  @State private var running = false
  @State private var output: URL?
  @State private var message: String?

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("Technical Report").font(.title2.weight(.semibold))
      Text(job.capabilityLabel).font(.headline)
      Text("Save a PDF and its Markdown source in a new folder. The report cites retained outputs that match their recorded SHA-256.")
        .foregroundStyle(.secondary)
      TextField("Research question or technical objective", text: $question, axis: .vertical)
        .textFieldStyle(.roundedBorder)
        .lineLimit(4...7)
        .disabled(running)
        .accessibilityIdentifier("jobs.report.question")
      if let message { Text(message).accessibilityIdentifier("jobs.report.feedback") }
      if let output {
        Button("Show Report Folder", systemImage: "folder") {
          NSWorkspace.shared.activateFileViewerSelecting([output])
        }
      }
      HStack {
        if running { ProgressView().controlSize(.small) }
        Spacer()
        Button("Close") { dismiss() }
          .keyboardShortcut(.cancelAction)
          .disabled(running)
        Button("Save Report…", action: save)
          .disabled(running || question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
          .accessibilityIdentifier("jobs.report.save")
      }
    }
    .padding(24)
    .frame(width: 520)
    .interactiveDismissDisabled(running)
  }

  private func save() {
    let panel = NSOpenPanel()
    panel.canChooseFiles = false
    panel.canChooseDirectories = true
    panel.canCreateDirectories = true
    panel.allowsMultipleSelection = false
    panel.prompt = "Choose Folder"
    guard panel.runModal() == .OK, let parent = panel.url else { return }
    let objective = question
    running = true
    output = nil
    message = nil
    Task {
      defer { running = false }
      do {
        output = try await store.exportTechnicalRunReport(job, question: objective, parent: parent)
        message = "Saved report.pdf and report.md."
      } catch {
        message = (error as? LocalizedError)?.errorDescription ?? "The technical report could not be saved."
      }
    }
  }
}

struct TechnicalRunReportRegenerationSheet: View {
  @Environment(\.dismiss) private var dismiss
  @State private var running = false
  @State private var message: String?

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("Regenerate Report PDF").font(.title2.weight(.semibold))
      Text("Choose the Markdown source from a Scientific Workbench technical report and save a new PDF. The source and evidence remain available for independent review.")
        .foregroundStyle(.secondary)
      if let message { Text(message).accessibilityIdentifier("jobs.report.regenerate-feedback") }
      HStack {
        if running { ProgressView().controlSize(.small) }
        Spacer()
        Button("Close") { dismiss() }
          .keyboardShortcut(.cancelAction)
          .disabled(running)
        Button("Choose Report Source…", action: choose)
          .disabled(running)
          .accessibilityIdentifier("jobs.report.regenerate-source")
      }
    }
    .padding(24)
    .frame(width: 520)
    .interactiveDismissDisabled(running)
  }

  private func choose() {
    let input = NSOpenPanel()
    input.canChooseDirectories = false
    input.allowsMultipleSelection = false
    input.allowedContentTypes = [UTType(filenameExtension: "md") ?? .plainText]
    guard input.runModal() == .OK, let source = input.url else { return }
    let panel = NSSavePanel()
    panel.allowedContentTypes = [.pdf]
    panel.nameFieldStringValue = "report-regenerated.pdf"
    guard panel.runModal() == .OK, let destination = panel.url else { return }
    running = true
    message = nil
    Task {
      defer { running = false }
      do {
        try await Task.detached(priority: .userInitiated) {
          try TechnicalRunReportService().regenerate(source: source, destination: destination)
        }.value
        message = "Saved the regenerated PDF."
      } catch {
        message = (error as? LocalizedError)?.errorDescription ?? "The report PDF could not be regenerated."
      }
    }
  }
}
