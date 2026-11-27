import SwiftUI

struct MeasurementSynthesisSheet: View {
  @Environment(\.dismiss) private var dismiss
  @ObservedObject var store: WorkbenchStore
  let jobID: UUID
  let artifact: Artifact
  var tableScope: TableSynthesisScope? = nil

  @State private var review: MeasurementSynthesisReview?
  @State private var highlights: [MeasurementSynthesisReview.Fact]?
  @State private var error: String?
  @State private var isSending = false

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      Text(highlights == nil ? "Review evidence synthesis" : "Verified highlights")
        .font(.title2.weight(.semibold))
      if let review, let highlights {
        summary(review, highlights: highlights)
      } else if let error {
        ContentUnavailableView("Synthesis unavailable", systemImage: "doc.badge.ellipsis",
                               description: Text(verbatim: error))
          .accessibilityIdentifier("results.measurements.synthesis-unavailable")
      } else if let review {
        request(review)
      } else {
        ProgressView("Verifying the recorded evidence…")
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }

      HStack {
        Spacer()
        Button(isSending || (review != nil && highlights == nil) ? "Cancel" : "Close") { dismiss() }
          .keyboardShortcut(.cancelAction)
        if review != nil && highlights == nil && error == nil {
          Button("Send and summarize") { isSending = true }
            .keyboardShortcut(.defaultAction)
            .disabled(isSending)
            .accessibilityIdentifier("results.measurements.send-synthesis")
        }
      }
    }
    .padding(24)
    .frame(width: 610, height: 505)
    .task {
      do {
        review = try await store.prepareMeasurementSynthesis(artifact: artifact, jobID: jobID, tableScope: tableScope)
      } catch {
        guard !Task.isCancelled else { return }
        self.error = store.redactedPreviewText(error.localizedDescription)
      }
    }
    .task(id: isSending) {
      guard isSending, let review else { return }
      do {
        let response = try await store.confirmMeasurementSynthesis(review)
        guard !Task.isCancelled else { return }
        highlights = response
      } catch {
        guard !Task.isCancelled else { return }
        self.review = nil
        self.error = store.redactedPreviewText(error.localizedDescription)
      }
      isSending = false
    }
  }

  private func request(_ review: MeasurementSynthesisReview) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text("\(review.destination.provider.title) · \(store.redactedPreviewText(review.destination.model))")
        .font(.headline)
      Text("Review the data below before sending it to the selected model.")
        .foregroundStyle(.secondary)
      GroupBox("Data sent to the model") {
        ScrollView {
          Text(verbatim: review.userMessage)
            .font(.system(.caption, design: .monospaced))
            .textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(6)
      }
      if isSending { ProgressView("Selecting highlights…").controlSize(.small) }
    }
  }

  private func summary(
    _ review: MeasurementSynthesisReview, highlights: [MeasurementSynthesisReview.Fact]
  ) -> some View {
    return ScrollView {
      VStack(alignment: .leading, spacing: 12) {
        Text("Highlights selected by \(review.destination.provider.title)")
          .foregroundStyle(.secondary)
        Text("Job \(review.jobID.uuidString)").font(.caption.monospaced())
        if review.measurementSummary?.evidenceOutcome == .warning {
          Label("The tool reported warnings.", systemImage: "exclamationmark.triangle")
        }
        if let scope = review.tableScope {
          Text("Records \(scope.rows.lowerBound)–\(scope.rows.upperBound), columns \(scope.columns.lowerBound)–\(scope.columns.upperBound)")
        }
        if let summary = review.measurementSummary {
          Text(verbatim: store.redactedPreviewText(summary.method))
        }
        ForEach(highlights) { fact in
          VStack(alignment: .leading, spacing: 3) {
            Text(verbatim: store.redactedPreviewText(fact.label)).font(.headline)
            switch fact.value {
            case .measurement(let quantity):
              let uncertainty = quantity.uncertainty.map { " ± \($0)" } ?? ""
              Text(verbatim: "\(quantity.value)\(uncertainty) \(store.redactedPreviewText(quantity.unit))")
                .monospacedDigit()
              if quantity.uncertainty == nil && fact.id.hasPrefix("measurements-") {
                Text("Uncertainty unavailable").font(.caption).foregroundStyle(.secondary)
              }
            case .tableCell(let text):
              Text(verbatim: text).monospacedDigit()
            }
            Text(verbatim: "\(store.redactedPreviewText(review.source))#\(fact.pointer)")
              .font(.caption.monospaced())
          }
          .accessibilityElement(children: .combine)
        }
        if let summary = review.measurementSummary {
          ForEach(Array(summary.quality.findings.prefix(12).enumerated()), id: \.offset) { _, finding in
            Text(verbatim: "QA finding — \(store.redactedPreviewText(finding))")
          }
          ForEach(Array(summary.assumptions.prefix(12).enumerated()), id: \.offset) { _, assumption in
            Text(verbatim: "Assumption — \(store.redactedPreviewText(assumption))")
          }
        }
        Text("SHA-256 \(review.sha256)").font(.caption.monospaced())
      }
      .textSelection(.enabled)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("results.measurements.synthesis")
  }
}
