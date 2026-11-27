import SwiftUI

struct CatalogCrossmatchView: View {
  private struct ReviewRequest: Equatable {
    let path: String
    let attachments: [String]
  }

  private typealias Inspection = (
    request: ReviewRequest, result: Result<CatalogCrossmatchTableReview, any Error>
  )

  @ObservedObject var store: WorkbenchStore
  let capability: CapabilityEntry

  @State private var leftPath = ""
  @State private var rightPath = ""
  @State private var inspectedAttachments: (paths: [String], files: [String])?
  @State private var leftInspection: Inspection?
  @State private var rightInspection: Inspection?
  @State private var runError: String?
  @State private var leftMapping = CatalogCrossmatchMapping()
  @State private var rightMapping = CatalogCrossmatchMapping()
  @State private var radiusText = "1"
  @State private var sharedICRSConfirmed = false
  @State private var coordinateEpochText = ""

  private let inspectionService = CatalogCrossmatchInspectionService()

  var body: some View {
    let attachments = store.inputPaths
    let leftRequest = request(for: leftPath)
    let rightRequest = request(for: rightPath)
    return VStack(alignment: .leading, spacing: 14) {
      HStack {
        VStack(alignment: .leading, spacing: 4) {
          Text("Sky Crossmatch Review")
            .font(.headline)
          Text("Map the coordinates in both catalogs and confirm their frame and epoch before matching.")
            .font(.callout)
            .foregroundStyle(.secondary)
        }
        Spacer()
        if let validation {
          StatusBadge(status: validation.status.rawValue)
        }
      }

      if let fileCandidates {
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
      } else {
        ProgressView("Checking attached files…")
          .controlSize(.small)
      }

      HStack(alignment: .top, spacing: 24) {
        catalogMapping(
          title: "Left catalog",
          result: result(of: leftInspection, for: leftRequest),
          hasSelection: leftRequest != nil,
          mapping: $leftMapping
        )
        catalogMapping(
          title: "Right catalog",
          result: result(of: rightInspection, for: rightRequest),
          hasSelection: rightRequest != nil,
          mapping: $rightMapping
        )
      }

      VStack(alignment: .leading, spacing: 8) {
        HStack(alignment: .top, spacing: 12) {
          VStack(alignment: .leading, spacing: 4) {
            Text("Search radius (arcsec)").font(.caption)
            TextField("Search radius (arcsec)", text: $radiusText)
              .labelsHidden()
          }
          VStack(alignment: .leading, spacing: 4) {
            Text("Common coordinate epoch (Julian year)").font(.caption)
            TextField("Common coordinate epoch (Julian year)", text: $coordinateEpochText, prompt: Text("2016.0"))
              .labelsHidden()
          }
        }
        .textFieldStyle(.roundedBorder)
        .frame(maxWidth: 460, alignment: .leading)
        Toggle("Both catalogs use ICRS at the coordinate epoch entered above.", isOn: $sharedICRSConfirmed)
          .toggleStyle(.checkbox)
          .disabled(leftReview == nil || rightReview == nil)
        Text("Use the epoch of the supplied positions. Convert frames and propagate positions to a common epoch before attaching catalogs if needed.")
          .font(.caption)
          .foregroundStyle(.secondary)
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
    .task(id: attachments) {
      await reconcileInputs(attachments)
    }
    .task(id: leftRequest) {
      guard !Task.isCancelled, leftRequest == request(for: leftPath) else { return }
      leftInspection = nil
      leftMapping = CatalogCrossmatchMapping()
      resetSharedConvention()
      guard let leftRequest, let result = await inspect(leftRequest),
            leftRequest == request(for: leftPath) else { return }
      leftInspection = (leftRequest, result)
    }
    .task(id: rightRequest) {
      guard !Task.isCancelled, rightRequest == request(for: rightPath) else { return }
      rightInspection = nil
      rightMapping = CatalogCrossmatchMapping()
      resetSharedConvention()
      guard let rightRequest, let result = await inspect(rightRequest),
            rightRequest == request(for: rightPath) else { return }
      rightInspection = (rightRequest, result)
    }
  }

  private var fileCandidates: [String]? {
    guard let inspectedAttachments, inspectedAttachments.paths == store.inputPaths else { return nil }
    return inspectedAttachments.files
  }

  private func request(for path: String) -> ReviewRequest? {
    guard fileCandidates?.contains(path) == true else { return nil }
    return ReviewRequest(path: path, attachments: store.inputPaths)
  }

  private func result(of inspection: Inspection?, for request: ReviewRequest?)
    -> Result<CatalogCrossmatchTableReview, any Error>? {
    guard let inspection, inspection.request == request else { return nil }
    return inspection.result
  }

  private var leftReview: CatalogCrossmatchTableReview? {
    try? result(of: leftInspection, for: request(for: leftPath))?.get()
  }

  private var rightReview: CatalogCrossmatchTableReview? {
    try? result(of: rightInspection, for: request(for: rightPath))?.get()
  }

  private var selection: CatalogCrossmatchSelection {
    CatalogCrossmatchSelection(
      left: leftMapping,
      right: rightMapping,
      radiusArcseconds: decimalNumber(radiusText),
      sharedICRSConfirmed: sharedICRSConfirmed,
      coordinateEpochJulianYear: decimalNumber(coordinateEpochText)
    )
  }

  private func decimalNumber(_ text: String) -> Double? {
    let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
    let separator = Locale.current.decimalSeparator ?? "."
    return Double(value.replacingOccurrences(of: separator, with: "."))
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
    result: Result<CatalogCrossmatchTableReview, any Error>?,
    hasSelection: Bool,
    mapping: Binding<CatalogCrossmatchMapping>
  ) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(title)
        .font(.subheadline)
        .fontWeight(.semibold)
      if case .failure(let error) = result {
        Label(error.localizedDescription, systemImage: "exclamationmark.triangle.fill")
          .font(.caption)
          .foregroundStyle(.orange)
      } else if case .success(let review) = result {
        Text("\(review.sampledRowCount) sampled row(s) · \(review.formatLabel) separated")
          .font(.caption)
          .foregroundStyle(.secondary)
        Picker("RA column", selection: mapping.raColumn) {
          Text("Select").tag(Int?.none)
          ForEach(review.columns) { column in
            Text(columnLabel(column)).tag(Optional(column.index))
          }
        }
        .accessibilityLabel("\(title) RA column")
        unitPicker("RA unit", catalog: title, selection: mapping.raUnit, allowHours: true)
        Picker("Dec column", selection: mapping.decColumn) {
          Text("Select").tag(Int?.none)
          ForEach(review.columns) { column in
            Text(columnLabel(column)).tag(Optional(column.index))
          }
        }
        .accessibilityLabel("\(title) Dec column")
        unitPicker("Dec unit", catalog: title, selection: mapping.decUnit)
      } else if hasSelection {
        ProgressView("Inspecting catalog…")
          .controlSize(.small)
      } else {
        Text("Select a supported text catalog to inspect its header.")
          .font(.caption)
          .foregroundStyle(.secondary)
      }
    }
    .pickerStyle(.menu)
    .frame(maxWidth: .infinity, alignment: .leading)
    .onChange(of: mapping.wrappedValue.raColumn) { _, _ in
      mapping.raUnit.wrappedValue = nil
      sharedICRSConfirmed = false
    }
    .onChange(of: mapping.wrappedValue.decColumn) { _, _ in
      mapping.decUnit.wrappedValue = nil
      sharedICRSConfirmed = false
    }
  }

  private func unitPicker(
    _ label: String,
    catalog: String,
    selection: Binding<CatalogCrossmatchCoordinateUnit?>,
    allowHours: Bool = false
  ) -> some View {
    Picker(label, selection: selection) {
      Text("Select").tag(CatalogCrossmatchCoordinateUnit?.none)
      ForEach(CatalogCrossmatchCoordinateUnit.allCases.filter { allowHours || $0 != .hours }, id: \.self) { unit in
        Text(unit.label).tag(Optional(unit))
      }
    }
    .accessibilityLabel("\(catalog) \(label)")
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
    } else if let fileCandidates, fileCandidates.count < 2 {
      Text("Attach at least two CSV, TSV, ECSV, or delimited text catalogs.")
        .font(.caption)
        .foregroundStyle(.orange)
    }
  }

  private func reconcileInputs(_ attachments: [String]) async {
    guard let candidates = try? await GuidedInputReviewLoader.shared.catalogFiles(in: attachments),
          !Task.isCancelled, attachments == store.inputPaths else { return }
    if !candidates.contains(leftPath) {
      leftPath = candidates.first ?? ""
    }
    if !candidates.contains(rightPath) || rightPath == leftPath {
      rightPath = candidates.first(where: { $0 != leftPath }) ?? ""
    }
    resetSharedConvention()
    runError = nil
    inspectedAttachments = (attachments, candidates)
  }

  private func resetSharedConvention() {
    sharedICRSConfirmed = false
    coordinateEpochText = ""
  }

  private func inspect(_ request: ReviewRequest) async -> Result<CatalogCrossmatchTableReview, any Error>? {
    do {
      let review = try await GuidedInputReviewLoader.shared.inspectCatalog(at: request.path)
      return Task.isCancelled ? nil : .success(review)
    } catch {
      return Task.isCancelled ? nil : .failure(error)
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
        inputPathsOverride: [prepared.leftPath, prepared.rightPath],
        appliedApproval: .capabilityAccess
      ) { runURL in
        prepared.arguments(runURL: runURL)
      }
    } catch {
      runError = error.localizedDescription
    }
  }
}
