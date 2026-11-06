import SwiftUI

struct TableArtifactPreview: View {
  let store: WorkbenchStore
  let job: JobRecord
  let artifact: Artifact

  @State private var cursor = TablePreviewService.Cursor.first
  @State private var loaded: (cursor: TablePreviewService.Cursor, page: TablePreviewPage)?
  @State private var failure: String?

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
      Text("Records \(page.firstRecord)–\(last) · \(page.next == nil ? "End of file" : "Sequential sample")")
        .accessibilityIdentifier("results.table.record-range")
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
