import SwiftUI

struct CatalogCrossmatchView: View {
  @ObservedObject var store: WorkbenchStore
  let capability: CapabilityEntry

  @State private var leftPath = ""
  @State private var rightPath = ""
  @State private var leftReview: CatalogCrossmatchTableReview?
  @State private var rightReview: CatalogCrossmatchTableReview?
  @State private var leftError: String?
  @State private var rightError: String?
  @State private var runError: String?
  @State private var leftRAColumn: Int?
  @State private var leftDecColumn: Int?
  @State private var rightRAColumn: Int?
  @State private var rightDecColumn: Int?
  @State private var radiusArcseconds = 1.0
  @State private var coordinateUnitsConfirmed = false

  private let inspectionService = CatalogCrossmatchInspectionService()

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack {
        VStack(alignment: .leading, spacing: 4) {
          Text("Sky Crossmatch Review")
            .font(.headline)
          Text("Choose both catalogs, map decimal-degree coordinates, and review the angular radius before matching.")
            .font(.callout)
            .foregroundStyle(.secondary)
        }
        Spacer()
        if let validation {
          StatusBadge(status: validation.status.rawValue)
        }
      }

      Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 10) {
        GridRow {
          Picker("Left catalog", selection: $leftPath) {
            Text("Select").tag("")
            ForEach(fileCandidates, id: \.self) { path in
              Text(URL(fileURLWithPath: path).lastPathComponent).tag(path)
            }
          }
          Picker("Right catalog", selection: $rightPath) {
            Text("Select").tag("")
            ForEach(fileCandidates, id: \.self) { path in
              Text(URL(fileURLWithPath: path).lastPathComponent).tag(path)
            }
          }
        }
      }
      .pickerStyle(.menu)

      HStack(alignment: .top, spacing: 24) {
        catalogMapping(
          title: "Left catalog",
          review: leftReview,
          error: leftError,
          raColumn: $leftRAColumn,
          decColumn: $leftDecColumn
        )
        catalogMapping(
          title: "Right catalog",
          review: rightReview,
          error: rightError,
          raColumn: $rightRAColumn,
          decColumn: $rightDecColumn
        )
      }

      HStack(spacing: 12) {
        TextField("Radius (arcsec)", value: $radiusArcseconds, format: .number)
          .textFieldStyle(.roundedBorder)
          .frame(maxWidth: 220)
        Toggle(
          "I reviewed the mapping and confirm all four coordinate columns are decimal degrees.",
          isOn: $coordinateUnitsConfirmed
        )
        .toggleStyle(.checkbox)
      }

      validationPanel

      HStack {
        Text("The output table, summary, and manifest are written to a new run folder. Both catalogs remain read-only.")
          .font(.caption)
          .foregroundStyle(.secondary)
        Spacer()
        Button {
          Task { await runReviewedCrossmatch() }
        } label: {
          Label("Run Reviewed Crossmatch", systemImage: "point.3.connected.trianglepath.dotted")
        }
        .buttonStyle(.borderedProminent)
        .disabled(validation?.canRun != true || store.hasActiveJob)
      }
    }
    .task(id: store.inputPaths) {
      reconcileInputs()
    }
    .onChange(of: leftPath) {
      reviewLeftCatalog()
    }
    .onChange(of: rightPath) {
      reviewRightCatalog()
    }
  }

  private var fileCandidates: [String] {
    store.inputPaths.filter { path in
      var isDirectory: ObjCBool = false
      return FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
        && !isDirectory.boolValue
    }
  }

  private var selection: CatalogCrossmatchSelection {
    CatalogCrossmatchSelection(
      leftRAColumn: leftRAColumn,
      leftDecColumn: leftDecColumn,
      rightRAColumn: rightRAColumn,
      rightDecColumn: rightDecColumn,
      radiusArcseconds: radiusArcseconds,
      coordinateUnitsConfirmed: coordinateUnitsConfirmed
    )
  }

  private var validation: CatalogCrossmatchValidation? {
    guard let leftReview, let rightReview else { return nil }
    return inspectionService.validate(
      left: leftReview,
      right: rightReview,
      selection: selection
    )
  }

  private func catalogMapping(
    title: String,
    review: CatalogCrossmatchTableReview?,
    error: String?,
    raColumn: Binding<Int?>,
    decColumn: Binding<Int?>
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(title)
        .font(.subheadline)
        .fontWeight(.semibold)
      if let error {
        Label(error, systemImage: "exclamationmark.triangle.fill")
          .font(.caption)
          .foregroundStyle(.orange)
      } else if let review {
        Text("\(review.sampledRowCount) sampled row(s) · \(review.formatLabel) separated")
          .font(.caption)
          .foregroundStyle(.secondary)
        Picker("RA column", selection: raColumn) {
          Text("Select").tag(Int?.none)
          ForEach(review.columns) { column in
            Text(columnLabel(column)).tag(Optional(column.index))
          }
        }
        Picker("Dec column", selection: decColumn) {
          Text("Select").tag(Int?.none)
          ForEach(review.columns) { column in
            Text(columnLabel(column)).tag(Optional(column.index))
          }
        }
        .pickerStyle(.menu)
      } else {
        Text("Select a supported text catalog to inspect its header.")
          .font(.caption)
          .foregroundStyle(.secondary)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  @ViewBuilder
  private var validationPanel: some View {
    if let runError {
      Label(runError, systemImage: "exclamationmark.triangle.fill")
        .font(.caption)
        .foregroundStyle(.red)
    }
    if let validation {
      ForEach(validation.findings, id: \.self) { finding in
        Label(finding, systemImage: "exclamationmark.triangle")
          .font(.caption)
          .foregroundStyle(validation.status == .blocked ? Color.red : Color.orange)
      }
      ForEach(validation.nextActions, id: \.self) { action in
        Label(action, systemImage: "arrow.right")
          .font(.caption)
          .foregroundStyle(.secondary)
      }
    } else if fileCandidates.count < 2 {
      Text("Attach at least two CSV, TSV, ECSV, or delimited text catalogs.")
        .font(.caption)
        .foregroundStyle(.orange)
    }
  }

  private func reconcileInputs() {
    let candidates = fileCandidates
    if !candidates.contains(leftPath) {
      leftPath = candidates.first ?? ""
    }
    if !candidates.contains(rightPath) || rightPath == leftPath {
      rightPath = candidates.first(where: { $0 != leftPath }) ?? ""
    }
    coordinateUnitsConfirmed = false
    runError = nil
    reviewLeftCatalog()
    reviewRightCatalog()
  }

  private func reviewLeftCatalog() {
    leftReview = nil
    leftError = nil
    leftRAColumn = nil
    leftDecColumn = nil
    coordinateUnitsConfirmed = false
    guard !leftPath.isEmpty else { return }
    do {
      leftReview = try inspectionService.inspect(path: leftPath)
    } catch {
      leftError = error.localizedDescription
    }
  }

  private func reviewRightCatalog() {
    rightReview = nil
    rightError = nil
    rightRAColumn = nil
    rightDecColumn = nil
    coordinateUnitsConfirmed = false
    guard !rightPath.isEmpty else { return }
    do {
      rightReview = try inspectionService.inspect(path: rightPath)
    } catch {
      rightError = error.localizedDescription
    }
  }

  private func columnLabel(_ column: CatalogCrossmatchColumn) -> String {
    let rangeText = column.finiteRange.map {
      let locale = Locale(identifier: "en_US_POSIX")
      let lower = String(format: "%.6g", locale: locale, $0.lowerBound)
      let upper = String(format: "%.6g", locale: locale, $0.upperBound)
      return "\(lower)...\(upper)"
    } ?? "no numeric range"
    return "\(column.name) · \(column.numericCount)/\(column.sampledRowCount) numeric · \(rangeText)"
  }

  @MainActor
  private func runReviewedCrossmatch() async {
    runError = nil
    guard let leftReview, let rightReview else {
      runError = "Inspect both catalogs before running."
      return
    }
    do {
      let prepared = try inspectionService.prepare(
        left: leftReview,
        right: rightReview,
        selection: selection
      )
      await store.runGuided(
        capability: capability,
        inputPathsOverride: [prepared.leftPath, prepared.rightPath]
      ) { runURL in
        prepared.arguments(runURL: runURL)
      }
    } catch {
      runError = error.localizedDescription
    }
  }
}
