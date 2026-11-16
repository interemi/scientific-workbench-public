import SwiftUI

struct RasterPreviewCacheControls: View {
  @State private var usage: RasterPreviewLoader.CacheUsage?
  @State private var reviewed: RasterPreviewLoader.CacheUsage?
  @State private var isConfirming = false
  @State private var isUpdating = false
  @State private var message: String?

  var body: some View {
    LabeledContent("Preview cache in memory", value: usage.map { size($0.bytes) } ?? "Measuring…")
      .accessibilityIdentifier("settings.storage.preview-cache-size")
    Button("Clear Cached Preview…") {
      Task {
        isUpdating = true
        defer { isUpdating = false }
        let current = await ArtifactPreviewService.rasterLoader.cacheUsage()
        usage = current
        message = nil
        guard current.bytes > 0 else { return }
        reviewed = current
        isConfirming = true
      }
    }
    .disabled(isUpdating || usage?.bytes == 0 || usage == nil)
    .accessibilityIdentifier("settings.storage.clear-preview-cache")
    .task { usage = await ArtifactPreviewService.rasterLoader.cacheUsage() }
    .alert("Clear the cached preview?", isPresented: $isConfirming, presenting: reviewed) { entry in
      Button("Clear Cached Preview", role: .destructive) { Task { await clear(entry) } }
      Button("Cancel", role: .cancel) {}
    } message: { entry in
      Text("This releases \(size(entry.bytes)) of cached thumbnail data. The app will recreate the thumbnail when you reopen the preview. Saved files stay with their runs.")
    }
    if let message {
      Text(message)
        .font(.caption)
        .foregroundStyle(.secondary)
        .accessibilityIdentifier("settings.storage.preview-cache-result")
    }
  }

  private func clear(_ entry: RasterPreviewLoader.CacheUsage) async {
    isUpdating = true
    defer { isUpdating = false }
    let loader = ArtifactPreviewService.rasterLoader
    if let after = await loader.clearCache(reviewed: entry) {
      usage = after
      message = "Preview cache reduced from \(size(entry.bytes)) to \(size(after.bytes))."
    } else {
      usage = await loader.cacheUsage()
      message = "The cached preview changed. Review its current size before clearing it."
    }
  }

  private func size(_ bytes: Int) -> String {
    ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .memory)
  }
}
