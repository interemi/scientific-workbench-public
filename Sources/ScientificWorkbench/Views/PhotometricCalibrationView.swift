import SwiftUI

struct PhotometricCalibrationView: View {
  @ObservedObject var store: WorkbenchStore
  let capability: CapabilityEntry

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack {
        Text("Photometric Calibration Review")
          .font(.headline)
        Spacer()
        if let review = store.photometricCalibrationReview {
          StatusBadge(
            status: store.photometricCalibrationValidation?.status.rawValue
              ?? review.status.rawValue
          )
        }
        Button {
          store.reviewPhotometricCalibrationInput()
        } label: {
          Label("Inspect Columns", systemImage: "tablecells")
        }
        .disabled(store.inputPaths.isEmpty || store.hasActiveJob)
      }

      if store.isReviewingPhotometricCalibration {
        ProgressView().controlSize(.small)
      } else if let error = store.photometricCalibrationError {
        Label(error, systemImage: "exclamationmark.triangle.fill")
          .foregroundStyle(.orange)
      } else if let review = store.photometricCalibrationReview {
        preview(review)
        selectors(review)
        rangeSummary
        findings

        HStack {
          Text("\(review.rows.count) source rows · original read-only")
            .font(.caption)
            .foregroundStyle(.secondary)
          Spacer()
          Button {
            Task {
              await store.runReviewedPhotometricCalibration(capability: capability)
            }
          } label: {
            Label("Fit Reviewed Calibration", systemImage: "function")
          }
          .buttonStyle(.borderedProminent)
          .disabled(
            store.hasActiveJob
              || store.photometricCalibrationValidation?.canRun != true
          )
        }
      } else {
        Text("Add one standard-star table, then inspect its columns and ranges.")
          .font(.callout)
          .foregroundStyle(.secondary)
      }
    }
    .task(id: store.inputPaths.first) {
      store.reviewPhotometricCalibrationInput()
    }
  }

  private func preview(_ review: PhotometricCalibrationReview) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text("Table Preview")
        .font(.subheadline)
        .fontWeight(.semibold)
      ScrollView(.horizontal) {
        Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 5) {
          GridRow {
            ForEach(review.columns) { column in
              Text(column.name)
                .fontWeight(.semibold)
                .frame(minWidth: 80, alignment: .leading)
            }
          }
          Divider().gridCellColumns(max(review.columns.count, 1))
          ForEach(Array(review.rows.prefix(6).enumerated()), id: \.offset) { _, row in
            GridRow {
              ForEach(review.columns) { column in
                Text(row.indices.contains(column.index) ? row[column.index] : "")
                  .lineLimit(1)
                  .frame(minWidth: 80, alignment: .leading)
              }
            }
          }
        }
        .font(.caption)
      }
      .frame(maxHeight: 170)
    }
  }

  private func selectors(_ review: PhotometricCalibrationReview) -> some View {
    Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 10) {
      GridRow {
        columnPicker("Instrumental mag", selection: $store.photometricInstrumentalColumn, review: review)
        columnPicker("Catalog mag", selection: $store.photometricCatalogColumn, review: review)
      }
      GridRow {
        columnPicker("Airmass", selection: $store.photometricAirmassColumn, review: review)
        columnPicker("Uncertainty", selection: $store.photometricUncertaintyColumn, review: review, allowNone: true)
      }
      GridRow {
        columnPicker("Filter column", selection: $store.photometricFilterColumn, review: review, allowNone: true)
          .onChange(of: store.photometricFilterColumn) {
            store.refreshPhotometricFilterValues()
          }
        Picker("Filter value", selection: $store.photometricFilterValue) {
          Text("All / one band").tag(String?.none)
          ForEach(store.photometricFilterValues, id: \.self) { value in
            Text(value).tag(Optional(value))
          }
        }
        .disabled(store.photometricFilterColumn == nil)
      }
      GridRow {
        columnPicker("Color index", selection: $store.photometricColorColumn, review: review, allowNone: true)
        Toggle("Include color term", isOn: $store.photometricIncludeColorTerm)
      }
    }
    .pickerStyle(.menu)
  }

  private func columnPicker(
    _ title: String,
    selection: Binding<Int?>,
    review: PhotometricCalibrationReview,
    allowNone: Bool = false
  ) -> some View {
    Picker(title, selection: selection) {
      Text(allowNone ? "None" : "Select").tag(Int?.none)
      ForEach(review.columns) { column in
        Text(column.name).tag(Optional(column.index))
      }
    }
  }

  private var rangeSummary: some View {
    Group {
      if let validation = store.photometricCalibrationValidation {
        HStack(spacing: 18) {
          rangeItem("Usable", "\(validation.usableRowCount)/\(validation.selectedRowCount)")
          rangeItem("Airmass", rangeText(validation.airmassRange))
          rangeItem("Catalog mag", rangeText(validation.catalogMagnitudeRange))
          if store.photometricIncludeColorTerm {
            rangeItem("Color", rangeText(validation.colorRange))
          }
        }
      }
    }
  }

  private var findings: some View {
    VStack(alignment: .leading, spacing: 6) {
      if let validation = store.photometricCalibrationValidation {
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

  private func rangeItem(_ label: String, _ value: String) -> some View {
    VStack(alignment: .leading, spacing: 2) {
      Text(label).font(.caption).foregroundStyle(.secondary)
      Text(value).font(.caption).monospacedDigit()
    }
  }

  private func rangeText(_ range: ClosedRange<Double>?) -> String {
    guard let range else { return "-" }
    return String(format: "%.3f – %.3f", range.lowerBound, range.upperBound)
  }
}
