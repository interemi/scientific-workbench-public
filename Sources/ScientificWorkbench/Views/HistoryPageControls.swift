import SwiftUI

struct HistoryPageControls: View {
  let page: HistoryPage
  let identifier: String
  @Binding var index: Int

  var body: some View {
    if page.pageCount > 1 {
      HStack(spacing: 8) {
        Button("Previous Page", systemImage: "chevron.left") { index = page.index - 1 }
          .labelStyle(.iconOnly)
          .accessibilityIdentifier("\(identifier).previous")
          .disabled(page.index == 0)
        Text("\(page.range.lowerBound + 1)–\(page.range.upperBound) of \(page.total)")
          .monospacedDigit()
          .accessibilityIdentifier("\(identifier).range")
        Button("Next Page", systemImage: "chevron.right") { index = page.index + 1 }
          .labelStyle(.iconOnly)
          .accessibilityIdentifier("\(identifier).next")
          .disabled(page.index + 1 == page.pageCount)
      }
      .font(.caption)
      .controlSize(.small)
    }
  }
}
