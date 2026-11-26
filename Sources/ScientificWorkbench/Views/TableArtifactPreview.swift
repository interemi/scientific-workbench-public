import SwiftUI

struct TableArtifactPreview: View {
  let store: WorkbenchStore
  let job: JobRecord
  let artifact: Artifact
  let allowsSynthesis: Bool

  @State private var cursor = TablePreviewService.Cursor.first
  @State private var loaded: (cursor: TablePreviewService.Cursor, page: TablePreviewPage)?
  @State private var failure: String?
  @State private var showingSynthesis = false
  @State private var selectedScope: TableSynthesisScope?

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack {
        Text("Table preview")
          .font(.headline)
        Spacer()
        Button("First page") { cursor = .first }
          .disabled(cursor == .first)
          .accessibilityIdentifier("results.table.first-page")
        Button("Next page") {
          if let next = loaded?.page.next {
            cursor = next
          }
        }
        .disabled(loaded?.cursor != cursor || loaded?.page.next == nil)
        .accessibilityIdentifier("results.table.next-page")
      }

      if let loaded, loaded.cursor == cursor {
        let page = loaded.page
        if page.rows.isEmpty {
          Text("No records in this file.")
            .foregroundStyle(.secondary)
        } else {
          table(page)
        }
      } else if let failure {
        Text(failure)
          .foregroundStyle(.secondary)
      } else {
        ProgressView("Loading table page…")
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    .sheet(isPresented: $showingSynthesis, onDismiss: { selectedScope = nil }) {
      if let selectedScope {
        MeasurementSynthesisSheet(store: store, jobID: job.id, artifact: artifact, tableScope: selectedScope)
      } else if let loaded, loaded.cursor == cursor, !loaded.page.rows.isEmpty {
        TableSynthesisRangePicker(cursor: loaded.cursor, page: loaded.page) { selectedScope = $0 }
      }
    }
    .task(id: cursor) {
      let requested = cursor
      failure = nil
      do {
        let page = try await TablePreviewService.shared.load(
          artifact, in: job, from: requested, redact: store.previewRedactor()
        )
        try Task.checkCancellation()
        loaded = (requested, page)
      } catch is CancellationError {
        return
      } catch {
        guard !Task.isCancelled else { return }
        failure = (error as? TablePreviewService.PreviewError)?.errorDescription ?? "The table could not be read."
      }
    }
  }

  private func table(_ page: TablePreviewPage) -> some View {
    let last = page.firstRecord + page.rows.count - 1
    let columns = min(page.widestRecord, TablePreviewService.maximumColumns)
    return VStack(alignment: .leading, spacing: 8) {
      HStack {
        Text("Records \(page.firstRecord)–\(last) · \(page.next == nil ? "End of file" : "Sequential sample")")
          .accessibilityIdentifier("results.table.record-range")
        Spacer(minLength: 8)
        if allowsSynthesis {
          Button("Summarize range") { showingSynthesis = true }
            .fixedSize(horizontal: true, vertical: false)
            .accessibilityIdentifier("results.table.synthesize")
        }
      }
      Text("Record numbers include any column header. Use the workflow result for full data-row counts.")
      if page.widestRecord > columns {
        Text("Showing the first \(columns) columns. The widest record on this page has \(page.widestRecord).")
      }
      if page.hasOmittedCellText {
        Text("Some cell text exceeds the display limit. Review the complete file for exact values.")
      }
      if let header = page.ecsvHeader {
        DisclosureGroup("ECSV metadata as stored") {
          ScrollView {
            Text(header)
              .font(.system(.caption, design: .monospaced))
              .textSelection(.enabled)
          }
          .frame(maxHeight: 120)
        }
      }
      ScrollView([.horizontal, .vertical]) {
        LazyVStack(alignment: .leading, spacing: 0) {
          HStack(spacing: 0) {
            cell("Record", width: 76)
            ForEach(0..<columns, id: \.self) { index in
              cell("Column \(index + 1)")
            }
          }
          .fontWeight(.semibold)
          ForEach(page.rows.indices, id: \.self) { index in
            let row = page.rows[index]
            HStack(alignment: .top, spacing: 0) {
              cell(String(page.firstRecord + index), width: 76)
              ForEach(0..<columns, id: \.self) { column in
                cell(row.indices.contains(column) ? row[column] : "—")
              }
            }
            .background(index.isMultiple(of: 2) ? Color.clear : Color.secondary.opacity(0.07))
          }
        }
        .font(.system(.caption, design: .monospaced))
        .textSelection(.enabled)
      }
      .id(page.firstRecord)
    }
    .font(.caption)
  }

  private func cell(_ text: String, width: CGFloat = 156) -> some View {
    Text(text)
      .frame(width: width, alignment: .leading)
      .padding(4)
  }
}

private struct TableSynthesisRangePicker: View {
  @Environment(\.dismiss) private var dismiss
  let cursor: TablePreviewService.Cursor
  let page: TablePreviewPage
  let review: (TableSynthesisScope) -> Void

  @State private var recordOffset = 0
  @State private var columnOffset = 0
  @State private var recordCount = 1
  @State private var columnCount = 1

  var body: some View {
    let columns = max(1, min(page.widestRecord, TablePreviewService.maximumColumns))
    let first = page.firstRecord + recordOffset
    let records = min(recordCount, page.rows.count - recordOffset)
    let selectedColumns = min(columnCount, columns - columnOffset)
    let scope = TableSynthesisScope(
      cursor: cursor, rows: first...(first + records - 1),
      columns: (columnOffset + 1)...(columnOffset + selectedColumns)
    )
    VStack(alignment: .leading, spacing: 15) {
      Text("Select a table range").font(.title2.weight(.semibold))
      Text("Record numbers follow the preview and include any column header. The review includes finite numeric cells from this range.")
        .foregroundStyle(.secondary)
      Stepper("First record \(first)", value: $recordOffset, in: 0...(page.rows.count - 1))
      Stepper("Through record \(scope.rows.upperBound)", value: $recordCount, in: 1...min(24, page.rows.count))
      Stepper("First column \(scope.columns.lowerBound)", value: $columnOffset, in: 0...(columns - 1))
      Stepper("Through column \(scope.columns.upperBound)", value: $columnCount, in: 1...columns)
      Text("Select up to \(TableSynthesisScope.maximumCells) cells.")
        .foregroundStyle(.secondary)
      HStack {
        Spacer()
        Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
        Button("Review data") { review(scope) }
          .disabled(records * selectedColumns > TableSynthesisScope.maximumCells)
          .keyboardShortcut(.defaultAction)
          .accessibilityIdentifier("results.table.review-synthesis")
      }
    }
    .padding(24)
    .frame(width: 440)
  }
}
