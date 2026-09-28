import SwiftUI

struct SidebarView: View {
  @ObservedObject var store: WorkbenchStore

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Text("Workbench")
        .font(.caption)
        .fontWeight(.semibold)
        .foregroundStyle(.secondary)
        .padding(.horizontal, 18)
        .padding(.top, 18)
        .padding(.bottom, 6)

      ScrollView {
        VStack(alignment: .leading, spacing: 4) {
          ForEach(AppSection.allCases) { section in
            Button {
              store.selectedSection = section
            } label: {
              SidebarRow(
                section: section,
                detail: detail(for: section),
                isSelected: store.selectedSection == section
              )
            }
            .buttonStyle(.plain)
            .accessibilityLabel(section.title)
            .accessibilityHint(detail(for: section))
            .accessibilityIdentifier("sidebar.section.\(section.rawValue)")
            .accessibilityAddTraits(store.selectedSection == section ? .isSelected : [])
          }
        }
        .padding(.horizontal, 10)
      }

      Spacer(minLength: 0)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(.bar)
  }

  private func detail(for section: AppSection) -> String {
    switch section {
    case .capabilities:
      return "Browse \(store.userCapabilities.count) tools"
    case .maintenance:
      return "\(store.maintainerCapabilities.count) advanced gates"
    default:
      return section.detail
    }
  }
}

private struct SidebarRow: View {
  let section: AppSection
  let detail: String
  let isSelected: Bool

  var body: some View {
    HStack(spacing: 10) {
      Image(systemName: section.iconName)
        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
        .frame(width: 16)
      VStack(alignment: .leading, spacing: 2) {
        Text(section.title)
          .fontWeight(isSelected ? .semibold : .regular)
          .lineLimit(1)
        Text(detail)
          .font(.caption)
          .foregroundStyle(.secondary)
          .lineLimit(1)
      }
      Spacer(minLength: 0)
    }
    .contentShape(Rectangle())
    .padding(.horizontal, 8)
    .padding(.vertical, 6)
    .background(
      isSelected ? Color.accentColor.opacity(0.14) : Color.clear,
      in: RoundedRectangle(cornerRadius: 8)
    )
  }
}
