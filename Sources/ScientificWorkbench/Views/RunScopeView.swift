import SwiftUI

struct RunScopeView: View {
  let summary: RunScopeSummary

  var body: some View {
    VStack(alignment: .leading, spacing: 9) {
      Text("Before you run: execution scope")
        .font(.headline)
      row("Inputs", summary.inputDetail)
      if !summary.inputPaths.isEmpty {
        ForEach(summary.inputPaths, id: \.self) { path in
          Text(path)
            .font(.system(.caption, design: .monospaced))
        }
      }
      row("New output folder", summary.outputPathPreview + "\n" + summary.outputDetail)
      row("Path safety", summary.outputSafetyDetail)
      row("Backend", summary.backendDetail)
      row("Network", summary.networkDetail)
      row("Review and consent", summary.consentDetail)
      row("Dependencies", summary.dependencyDetail)
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
  }

  private func row(_ label: String, _ detail: String) -> some View {
    VStack(alignment: .leading, spacing: 2) {
      Text(label)
        .font(.caption)
        .fontWeight(.semibold)
      Text(detail)
        .font(.caption)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
  }
}
