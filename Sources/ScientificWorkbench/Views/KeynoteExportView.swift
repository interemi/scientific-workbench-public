import SwiftUI

struct KeynoteExportView: View {
  @ObservedObject var store: WorkbenchStore
  let capability: CapabilityEntry

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack {
        Text("Keynote GUI Export")
          .font(.headline)
        Spacer()
        if let review = store.keynotePreflightReview {
          StatusBadge(status: review.status.rawValue)
        }
        Button {
          Task { await store.runKeynotePreflight(capability: capability) }
        } label: {
          Label("Run Preflight", systemImage: "checkmark.shield")
        }
        .disabled(store.inputPaths.isEmpty || store.hasActiveJob)
      }

      if store.isCheckingKeynote {
        Label("Checking Keynote and AppleScript readiness...", systemImage: "checkmark.shield")
          .font(.callout)
        ProgressView().controlSize(.small)
      } else if store.isExportingKeynote {
        Label("Keynote automation is running on the copied deck...", systemImage: "rectangle.stack.badge.play")
          .font(.callout)
        ProgressView().controlSize(.small)
      } else if let error = store.keynoteWorkflowError {
        Label(error, systemImage: "exclamationmark.triangle.fill")
          .foregroundStyle(.orange)
      } else if let review = store.keynotePreflightReview {
        readiness(review)
        Text(review.recommendation)
          .font(.callout)
        ForEach(review.findings, id: \.self) { finding in
          Label(finding, systemImage: "exclamationmark.triangle")
            .font(.caption)
            .foregroundStyle(.orange)
        }

        Toggle(
          "I approve opening Keynote with a copied deck and exporting a separate PDF.",
          isOn: $store.keynoteExportConfirmed
        )
        .disabled(!review.canExport)

        HStack {
          Text("The source deck is copied into the run. Keynote closes the copy without saving.")
            .font(.caption)
            .foregroundStyle(.secondary)
          Spacer()
          Button {
            Task { await store.runConfirmedKeynoteExport(capability: capability) }
          } label: {
            Label("Export Copied Deck", systemImage: "doc.richtext")
          }
          .buttonStyle(.borderedProminent)
          .disabled(
            store.hasActiveJob
              || store.isExportingKeynote
              || !review.canExport
              || !store.keynoteExportConfirmed
          )
        }
      } else {
        Text("Add one .key, .pptx, or .pptm deck. Preflight runs on a staged copy before GUI automation is enabled.")
          .font(.callout)
          .foregroundStyle(.secondary)
      }
    }
    .task(id: store.inputPaths.first) {
      store.resetKeynoteWorkflow()
    }
  }

  private func readiness(_ review: KeynotePreflightReview) -> some View {
    Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 7) {
      GridRow {
        Text("macOS")
        StatusBadge(status: review.platform == "darwin" ? "ok" : "blocked")
      }
      GridRow {
        Text("AppleScript")
        StatusBadge(status: review.osascriptAvailable ? "ok" : "blocked")
      }
      GridRow {
        Text("Keynote")
        StatusBadge(status: review.keynoteAvailable ? "ok" : "blocked")
      }
    }
    .font(.caption)
  }
}
