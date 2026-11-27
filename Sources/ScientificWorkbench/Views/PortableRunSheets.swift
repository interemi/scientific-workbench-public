import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct PortableRunExportSheet: View {
  @Environment(\.dismiss) private var dismiss
  let store: WorkbenchStore
  let job: JobRecord
  @State private var fixtures: [PortableRunPackageService.Fixture] = []
  @State private var outputs: Set<UUID> = []
  @State private var includedFixtures: Set<Int> = []
  @State private var exporting = false
  @State private var message: String?
  @State private var saved = false

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("Export Portable Run").font(.title2.weight(.semibold))
      Text(job.capabilityLabel).font(.headline)
      Text("The ZIP includes a shareable summary, hashes, instructions, and verification scripts. Choose any files to share.")
        .foregroundStyle(.secondary)
      ScrollView {
        VStack(alignment: .leading, spacing: 10) {
          let candidates = PortableRunPackageService().outputCandidates(for: job)
          if !candidates.isEmpty {
            Text("Output files").font(.headline)
            Text("Review the content before sharing. Selected tables and images can contain research data.")
              .font(.callout)
            ForEach(candidates) { artifact in
              Toggle(isOn: selectedOutput(artifact.id)) {
                VStack(alignment: .leading) {
                  Text(verbatim: artifact.relativePath).lineLimit(2)
                  Text(artifact.byteCount.formatted(.byteCount(style: .file)))
                    .font(.caption).foregroundStyle(.secondary)
                }
              }
            }
          }
          if !fixtures.isEmpty {
            Text("Synthetic fixtures").font(.headline)
            ForEach(fixtures) { fixture in
              Toggle("Input \(fixture.input) · \(fixture.ext.uppercased())", isOn: selectedFixture(fixture.input))
            }
          }
          if candidates.isEmpty && fixtures.isEmpty {
            Text("Only the run evidence is available for this package.")
              .foregroundStyle(.secondary)
          }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .disabled(exporting)
      }
      if let message {
        Text(message).accessibilityIdentifier("jobs.portable-export.feedback")
      }
      HStack {
        if exporting { ProgressView().controlSize(.small) }
        Spacer()
        Button("Close") { dismiss() }
          .keyboardShortcut(.cancelAction)
          .disabled(exporting)
        Button("Save ZIP…", action: save)
          .disabled(exporting || saved)
          .accessibilityIdentifier("jobs.portable-export.save")
      }
    }
    .padding(24)
    .frame(width: 570, height: 465)
    .interactiveDismissDisabled(exporting)
    .task(id: job.id) {
      let original = job
      fixtures = await Task.detached(priority: .utility) {
        PortableRunPackageService().fixtureCandidates(for: original)
      }.value
    }
  }

  private func selectedOutput(_ id: UUID) -> Binding<Bool> {
    Binding(get: { outputs.contains(id) }, set: { enabled in
      if enabled { outputs.insert(id) } else { outputs.remove(id) }
    })
  }

  private func selectedFixture(_ id: Int) -> Binding<Bool> {
    Binding(get: { includedFixtures.contains(id) }, set: { enabled in
      if enabled { includedFixtures.insert(id) } else { includedFixtures.remove(id) }
    })
  }

  private func save() {
    let panel = NSSavePanel()
    panel.allowedContentTypes = [.zip]
    panel.nameFieldStringValue = "scientific-workbench-run-\(job.id.uuidString.prefix(8).lowercased()).zip"
    guard panel.runModal() == .OK, let url = panel.url else { return }
    let selection = PortableRunPackageService.Selection(outputIDs: outputs, fixtureIDs: includedFixtures)
    exporting = true
    message = nil
    Task {
      defer { exporting = false }
      do {
        let review = try await store.exportPortableRun(job, selection: selection, destination: url)
        message = "Saved ZIP. Verified \(review.entries.count) members."
        saved = true
      } catch {
        message = (error as? LocalizedError)?.errorDescription ?? "The portable ZIP could not be saved."
      }
    }
  }
}

struct PortableRunInspectionSheet: View {
  @Environment(\.dismiss) private var dismiss
  @ObservedObject var store: WorkbenchStore
  @State private var review: PortableRunPackageService.Review?
  @State private var inspecting = false
  @State private var message: String?

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text("Inspect Portable ZIP").font(.title2.weight(.semibold))
      if let review {
        ScrollView {
          VStack(alignment: .leading, spacing: 13) {
            Label("Verified \(review.entries.count) member hashes", systemImage: "checkmark.shield")
              .accessibilityIdentifier("jobs.portable-inspect.verified")
            LabeledContent("Capability", value: review.summary.tool.capabilityID ?? "Unavailable")
            LabeledContent("Original job", value: review.summary.sourceJobID.uuidString)
            if review.includesSelectedData {
              Label("Contains explicitly selected run outputs. Review before sharing.", systemImage: "exclamationmark.triangle")
            }
            ForEach(review.dependencyWarnings(
              capabilities: store.capabilities,
              environment: store.environmentCheckState == .current ? store.environmentDiagnosis : nil
            ), id: \.self) { warning in
              Label(warning, systemImage: "info.circle").font(.callout)
            }
            if let runtime = review.summary.runtime {
              DisclosureGroup("Recorded Python and packages") {
                LabeledContent("Python", value: "\(runtime.pythonVersion) · \(runtime.architecture)")
                ForEach(runtime.profilePackages.sorted { $0.key < $1.key }, id: \.key) { package in
                  LabeledContent(package.key, value: package.value)
                }
              }
            }
            DisclosureGroup("Package files and SHA-256") {
              ForEach(review.entries) { entry in
                VStack(alignment: .leading, spacing: 3) {
                  LabeledContent(entry.name, value: entry.byteCount.formatted(.byteCount(style: .file)))
                  Text(verbatim: entry.sha256).font(.system(.caption, design: .monospaced))
                }
                .textSelection(.enabled)
              }
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
        }
      } else {
        Text("Choose a Scientific Workbench ZIP to inspect its hashes, contents, and recorded dependencies.")
          .foregroundStyle(.secondary)
        Spacer()
      }
      if let message {
        Label(message, systemImage: "exclamationmark.triangle")
          .accessibilityIdentifier("jobs.portable-inspect.feedback")
      }
      HStack {
        if inspecting { ProgressView().controlSize(.small) }
        Spacer()
        Button("Close") { dismiss() }
          .keyboardShortcut(.cancelAction)
          .disabled(inspecting)
        Button("Choose ZIP…", action: choose)
          .disabled(inspecting)
          .accessibilityIdentifier("jobs.portable-inspect.choose")
      }
    }
    .padding(24)
    .frame(width: 570, height: 465)
    .interactiveDismissDisabled(inspecting)
  }

  private func choose() {
    let panel = NSOpenPanel()
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = false
    panel.allowedContentTypes = [.zip]
    guard panel.runModal() == .OK, let url = panel.url else { return }
    inspecting = true
    message = nil
    review = nil
    Task {
      defer { inspecting = false }
      do {
        review = try await Task.detached(priority: .userInitiated) { try PortableRunPackageService().review(at: url) }.value
      } catch {
        message = (error as? LocalizedError)?.errorDescription ?? "The ZIP could not be inspected."
      }
    }
  }
}
