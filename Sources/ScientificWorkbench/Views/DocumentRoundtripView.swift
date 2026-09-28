import SwiftUI

struct DocumentRoundtripView: View {
  @ObservedObject var store: WorkbenchStore
  let capability: CapabilityEntry

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack {
        Text(capability.id.hasSuffix("style-inventory") ? "DOCX Style Inventory" : "DOCX Reviewed Replacement")
          .font(.headline)
        Spacer()
        if let review = store.documentStyleReview {
          StatusBadge(status: review.status.rawValue)
        }
        Button {
          Task { await store.reviewDOCXStyles() }
        } label: {
          Label("Inspect Copy", systemImage: "text.magnifyingglass")
        }
        .disabled(store.inputPaths.isEmpty || store.hasActiveJob)
      }

      styleSelector

      if store.isReviewingDocumentStyles {
        ProgressView().controlSize(.small)
      } else if let error = store.documentStyleError {
        Label(error, systemImage: "exclamationmark.triangle.fill")
          .foregroundStyle(.orange)
      } else if let review = store.documentStyleReview {
        styleCountSummary(review)
        matchPreview(review)
        findings(review)
        if capability.id.hasSuffix("styled-replace") {
          replacementPanel
        } else {
          HStack {
            Text("\(review.matchCount) matching runs · source copied into run · original read-only")
              .font(.caption)
              .foregroundStyle(.secondary)
            Spacer()
            Button {
              store.showLatestDocumentStyleResults()
            } label: {
              Label("Open Inventory Results", systemImage: "doc.text.magnifyingglass")
            }
          }
        }
      } else {
        Text("Add one DOCX file. The app copies it into a run before inspecting explicit run-level styles.")
          .font(.callout)
          .foregroundStyle(.secondary)
      }
    }
    .task(id: store.inputPaths.first) {
      store.resetDocumentWorkflow()
    }
    .onChange(of: store.docxRequireBold) {
      store.resetDocumentWorkflow()
    }
    .onChange(of: store.docxRequireItalic) {
      store.resetDocumentWorkflow()
    }
    .onChange(of: store.docxRequireUnderline) {
      store.resetDocumentWorkflow()
    }
    .onChange(of: store.docxFindText) {
      store.docxReplacementConfirmed = false
    }
    .onChange(of: store.docxReplacementText) {
      store.docxReplacementConfirmed = false
    }
  }

  private func styleCountSummary(_ review: DOCXStyleReview) -> some View {
    let counts = review.styleCounts
    return LazyVGrid(
      columns: [GridItem(.adaptive(minimum: 105, maximum: 150), spacing: 10)],
      alignment: .leading,
      spacing: 8
    ) {
      styleMetric("Matches", count: review.matchCount, systemImage: "text.magnifyingglass")
      styleMetric("Bold", count: counts.bold, systemImage: "bold")
      styleMetric("Italic", count: counts.italic, systemImage: "italic")
      styleMetric("Underline", count: counts.underline, systemImage: "underline")
      styleMetric("Body", count: counts.body, systemImage: "doc.text")
      styleMetric("Table", count: counts.table, systemImage: "tablecells")
    }
  }

  private func styleMetric(_ label: String, count: Int, systemImage: String) -> some View {
    HStack(spacing: 8) {
      Image(systemName: systemImage)
        .foregroundStyle(.secondary)
        .frame(width: 16)
      Text(label)
        .lineLimit(1)
      Spacer(minLength: 6)
      Text(count, format: .number)
        .fontWeight(.semibold)
        .monospacedDigit()
    }
    .font(.caption)
    .padding(.horizontal, 9)
    .frame(height: 32)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
  }

  private var styleSelector: some View {
    VStack(alignment: .leading, spacing: 7) {
      Text("Required explicit formatting")
        .font(.subheadline)
        .fontWeight(.semibold)
      HStack(spacing: 18) {
        Toggle("Bold", isOn: $store.docxRequireBold)
        Toggle("Italic", isOn: $store.docxRequireItalic)
        Toggle("Underline", isOn: $store.docxRequireUnderline)
        Spacer()
      }
      Text("With no toggles selected, the inventory includes any explicitly bold, italic, or underlined run.")
        .font(.caption)
        .foregroundStyle(.secondary)
    }
  }

  private func matchPreview(_ review: DOCXStyleReview) -> some View {
    VStack(alignment: .leading, spacing: 7) {
      Text("Matching Runs")
        .font(.subheadline)
        .fontWeight(.semibold)
      if review.matches.isEmpty {
        ContentUnavailableView("No matching runs", systemImage: "text.badge.xmark")
          .frame(maxHeight: 120)
      } else {
        ScrollView {
          LazyVStack(alignment: .leading, spacing: 8) {
            ForEach(review.matches.prefix(80)) { match in
              HStack(alignment: .top, spacing: 10) {
                Text(match.text)
                  .textSelection(.enabled)
                  .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 3) {
                  Text(match.locationLabel)
                    .foregroundStyle(.secondary)
                  Text(match.styleLabels.joined(separator: " + "))
                    .foregroundStyle(.secondary)
                }
                .font(.caption)
              }
              .padding(9)
              .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
            }
          }
        }
        .frame(maxHeight: 220)
      }
    }
  }

  private func findings(_ review: DOCXStyleReview) -> some View {
    VStack(alignment: .leading, spacing: 5) {
      ForEach(review.findings + review.limitations, id: \.self) { finding in
        Label(finding, systemImage: "info.circle")
          .font(.caption)
          .foregroundStyle(.secondary)
      }
    }
  }

  private var replacementPanel: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Replacement Preview")
        .font(.subheadline)
        .fontWeight(.semibold)
      Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 8) {
        GridRow {
          Text("Find")
          TextField("Exact text inside matching runs", text: $store.docxFindText)
        }
        GridRow {
          Text("Replace")
          TextField("Replacement text", text: $store.docxReplacementText)
        }
      }
      diffPreview
      Toggle(
        "I reviewed the matches and approve writing a separate edited DOCX copy.",
        isOn: $store.docxReplacementConfirmed
      )
      .disabled(store.documentStyleDiff.isEmpty)

      HStack {
        Text("\(store.documentStyleDiff.reduce(0) { $0 + $1.replacementCount }) replacement(s) previewed · original remains untouched")
          .font(.caption)
          .foregroundStyle(.secondary)
        Spacer()
        Button {
          Task {
            await store.runReviewedDOCXReplacement(capability: capability)
          }
        } label: {
          Label("Create Edited Copy", systemImage: "doc.badge.plus")
        }
        .buttonStyle(.borderedProminent)
        .disabled(
          store.hasActiveJob
            || !store.docxReplacementConfirmed
            || store.documentStyleDiff.isEmpty
        )
      }
    }
  }

  private var diffPreview: some View {
    Group {
      if store.documentStyleDiff.isEmpty {
        Text("Enter exact find and replacement text to preview changes before writing a copy.")
          .font(.caption)
          .foregroundStyle(.secondary)
      } else {
        ScrollView {
          LazyVStack(alignment: .leading, spacing: 8) {
            ForEach(store.documentStyleDiff) { row in
              VStack(alignment: .leading, spacing: 5) {
                Text(row.match.locationLabel)
                  .font(.caption)
                  .foregroundStyle(.secondary)
                LabeledContent("Before", value: row.before)
                LabeledContent("After", value: row.after)
              }
              .padding(9)
              .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
            }
          }
        }
        .frame(maxHeight: 210)
      }
    }
  }
}
