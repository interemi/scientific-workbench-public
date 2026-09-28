import SwiftUI

struct RadialVelocityInspectionView: View {
  @ObservedObject var store: WorkbenchStore
  let capability: CapabilityEntry

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack {
        Text("RV Column Review")
          .font(.headline)
        Spacer()
        if let review = store.radialVelocityReview {
          StatusBadge(status: store.radialVelocitySelectionValidation?.status.rawValue ?? review.status.rawValue)
        }
        Button {
          store.reviewRadialVelocityInput()
        } label: {
          Label("Inspect Columns", systemImage: "tablecells")
        }
        .disabled(store.inputPaths.isEmpty || store.hasActiveJob)
      }

      if store.isReviewingRadialVelocityInput {
        ProgressView()
          .controlSize(.small)
      } else if let error = store.radialVelocityReviewError {
        Label(error, systemImage: "exclamationmark.triangle.fill")
          .foregroundStyle(.orange)
      } else if let review = store.radialVelocityReview {
        columnInventory(review)
        selectors(review)
        validationPanel

        HStack {
          Text("\(review.rows.count) rows · \(review.separatorLabel) separated · original read-only")
            .font(.caption)
            .foregroundStyle(.secondary)
          Spacer()
          Button {
            Task {
              await store.runReviewedRadialVelocityInspection(capability: capability)
            }
          } label: {
            Label("Run Reviewed Inspection", systemImage: "play.fill")
          }
          .buttonStyle(.borderedProminent)
          .disabled(
            store.hasActiveJob
              || store.radialVelocitySelectionValidation?.canRun != true
          )
        }
      } else {
        Text("Add one RV table, then inspect its columns.")
          .font(.callout)
          .foregroundStyle(.secondary)
      }
    }
    .task(id: store.inputPaths.first) {
      store.reviewRadialVelocityInput()
    }
  }

  private func columnInventory(_ review: RadialVelocityTableReview) -> some View {
    Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 6) {
      GridRow {
        Text("Column").fontWeight(.semibold)
        Text("Numeric").fontWeight(.semibold)
        Text("Candidates").fontWeight(.semibold)
      }
      Divider().gridCellColumns(3)
      ForEach(review.columns) { column in
        GridRow {
          Text(column.name)
            .lineLimit(1)
            .truncationMode(.middle)
          Text("\(column.numericCount)/\(column.rowCount)")
            .monospacedDigit()
          Text(candidateLabels(column).joined(separator: ", "))
            .foregroundStyle(.secondary)
        }
        .font(.caption)
      }
    }
  }

  private func selectors(_ review: RadialVelocityTableReview) -> some View {
    Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 10) {
      GridRow {
        Picker("Time column", selection: $store.radialVelocityTimeColumn) {
          Text("Select").tag(Int?.none)
          ForEach(review.columns) { column in
            Text(column.name).tag(Optional(column.index))
          }
        }
        Picker("Time system", selection: $store.radialVelocityTimeSystem) {
          ForEach(RadialVelocityTimeSystem.allCases) { system in
            Text(system.title).tag(system)
          }
        }
      }
      GridRow {
        Picker("RV column", selection: $store.radialVelocityValueColumn) {
          Text("Select").tag(Int?.none)
          ForEach(review.columns) { column in
            Text(column.name).tag(Optional(column.index))
          }
        }
        Picker("Velocity units", selection: $store.radialVelocityUnit) {
          ForEach(RadialVelocityUnit.allCases) { unit in
            Text(unit.title).tag(unit)
          }
        }
      }
      GridRow {
        Picker("Uncertainty", selection: $store.radialVelocityUncertaintyColumn) {
          Text("None").tag(Int?.none)
          ForEach(review.columns) { column in
            Text(column.name).tag(Optional(column.index))
          }
        }
        Spacer()
      }
    }
    .pickerStyle(.menu)
  }

  private var validationPanel: some View {
    VStack(alignment: .leading, spacing: 6) {
      if let validation = store.radialVelocitySelectionValidation {
        ForEach(validation.findings, id: \.self) { finding in
          Label(finding, systemImage: "exclamationmark.triangle")
            .font(.caption)
            .foregroundStyle(validation.status == .blocked ? Color.red : Color.orange)
        }
        if !validation.nextActions.isEmpty {
          Text("Next actions")
            .font(.caption)
            .fontWeight(.semibold)
          ForEach(validation.nextActions, id: \.self) { action in
            Label(action, systemImage: "arrow.right")
              .font(.caption)
              .foregroundStyle(.secondary)
          }
        }
      }
    }
  }

  private func candidateLabels(_ column: RadialVelocityColumn) -> [String] {
    var labels: [String] = []
    if column.timeScore > 0 { labels.append("time") }
    if column.velocityScore > 0 { labels.append("RV") }
    if column.uncertaintyScore > 0 { labels.append("uncertainty") }
    return labels.isEmpty ? ["-"] : labels
  }
}
