import SwiftUI

struct FITSInspectionView: View {
  let summary: FITSInspectionSummary
  let redact: (String) -> String
  let canLookup: Bool
  let canCrop: Bool
  let busy: Bool
  let onAction: (Int, FITSInspectionAction) -> Void
  @State private var selectedIndex: Int

  init(summary: FITSInspectionSummary, redact: @escaping (String) -> String, canLookup: Bool,
       canCrop: Bool, busy: Bool, onAction: @escaping (Int, FITSInspectionAction) -> Void) {
    self.summary = summary
    self.redact = redact
    self.canLookup = canLookup
    self.canCrop = canCrop
    self.busy = busy
    self.onAction = onAction
    _selectedIndex = State(initialValue: summary.pixelLookup?.hduIndex ?? summary.preview?.hduIndex ?? summary.previewExtension
                           ?? summary.hdus.first?.index ?? 0)
  }

  private var selectedHDU: FITSInspectionSummary.HDU? {
    summary.hdus.first { $0.index == selectedIndex } ?? summary.hdus.first
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        if let hdu = selectedHDU {
          Picker("HDU", selection: $selectedIndex) {
            ForEach(summary.hdus) { item in
              Text("\(item.index) · \(redact(item.name))").tag(item.index)
            }
          }
          .accessibilityIdentifier("results.fits.hdu")

          if let pixel = summary.pixelLookup, pixel.hduIndex == hdu.index {
            pixelDetails(pixel)
          }
          if (canLookup || canCrop), hdu.dataKind == "image", let shape = hdu.dataSummary?.shape,
             shape.count >= 2 {
            let region = summary.preview?.hduIndex == hdu.index ? summary.preview?.regionXywh : nil
            let lastPixel = summary.pixelLookup?.hduIndex == hdu.index ? summary.pixelLookup?.imageXy : nil
            FITSInspectionControls(
              imageWidth: shape[shape.count - 1], imageHeight: shape[shape.count - 2],
              region: region, lastPixel: lastPixel, canLookup: canLookup, canCrop: canCrop
            ) { action in
              onAction(hdu.index, action)
            }
            .id(hdu.index)
            .disabled(busy)
          }

          GroupBox("HDU details") {
            VStack(alignment: .leading, spacing: 6) {
              LabeledContent("Type", value: redact(hdu.type))
              if let data = hdu.dataSummary {
                dataDetails(data)
              } else if !hdu.hasData {
                Text("Header only")
                  .foregroundStyle(.secondary)
              }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
          }
          wcsDetails(hdu.wcs)
          if !hdu.header.isEmpty {
            GroupBox("Header cards") {
              VStack(alignment: .leading, spacing: 6) {
                ForEach(hdu.header.keys.sorted(), id: \.self) { key in
                  if let value = hdu.header[key] {
                    LabeledContent(redact(key), value: redact(value.text))
                  }
                }
              }
            }
          }
        }
        if let preview = summary.preview {
          previewDetails(preview)
        }
      }
      .textSelection(.enabled)
      .padding(.trailing, 8)
    }
    .accessibilityIdentifier("results.fits.inspection")
  }

  @ViewBuilder
  private func dataDetails(_ data: FITSInspectionSummary.DataSummary) -> some View {
    if let shape = data.shape {
      LabeledContent("Dimensions (FITS axis order)", value: shape.reversed().map(String.init).joined(separator: " × "))
    }
    if let dtype = data.dtype {
      LabeledContent("Pixel type", value: redact(dtype))
    }
    if let total = data.totalPixels, let sampled = data.sampledPixels {
      LabeledContent("Pixels sampled", value: "\(sampled.formatted()) of \(total.formatted())")
    }
    if let nonfinite = data.nonfiniteSampledPixels {
      LabeledContent("Nonfinite in sample (NaN or infinity)", value: nonfinite.formatted())
    }
    if let samplingReason = data.samplingReason {
      Text(redact(samplingReason)).foregroundStyle(.secondary)
    }
    if let rows = data.rows, let columns = data.columns {
      LabeledContent("Rows", value: rows.formatted())
      LabeledContent("Columns", value: columns.formatted())
    }
    if let names = data.columnNames, !names.isEmpty {
      LabeledContent("Column sample", value: names.map(redact).joined(separator: ", "))
    }
  }

  private func wcsDetails(_ wcs: FITSInspectionSummary.WCS?) -> some View {
    GroupBox("World coordinate system") {
      VStack(alignment: .leading, spacing: 6) {
        if let wcs {
          if let status = wcs.status {
            Text(redact(status)).foregroundStyle(.secondary)
          }
          if let axes = wcs.ctype, !axes.isEmpty {
            LabeledContent("Axes", value: axes.map(redact).joined(separator: ", "))
          }
          if let reference = wcs.referenceFrame {
            LabeledContent("Reference frame", value: redact(reference))
          }
          if let pixel = wcs.crpix, !pixel.isEmpty {
            LabeledContent("CRPIX (one-based FITS pixels)", value: numbers(pixel))
          }
          if let values = wcs.crval, !values.isEmpty {
            let units = wcs.axisUnits?.prefix(values.count).map(redact).joined(separator: ", ")
            LabeledContent("CRVAL", value: [numbers(values), units].compactMap { $0 }.joined(separator: " · "))
          }
          if let scale = wcs.projectionPlaneScaleArcsec {
            LabeledContent("Projection-plane scale (arcsec/pixel)", value: numbers(scale))
          }
        } else {
          Text("No WCS recorded for this HDU.").foregroundStyle(.secondary)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  private func previewDetails(_ preview: FITSInspectionSummary.Preview) -> some View {
    GroupBox("Display-only quicklook") {
      VStack(alignment: .leading, spacing: 6) {
        if let index = preview.hduIndex {
          LabeledContent("Preview HDU", value: String(index))
        }
        if let region = preview.regionXywh, region.count == 4 {
          LabeledContent("Origin (zero-based x, y)", value: "\(region[0]), \(region[1])")
          LabeledContent("Region (pixels)", value: "\(region[2]) × \(region[3])")
        }
        if let plane = preview.planeIndices, !plane.isEmpty {
          LabeledContent("Leading-axis indices (zero-based)", value: plane.map(String.init).joined(separator: ", "))
        }
        if let coordinates = preview.coordinates {
          LabeledContent("Axes", value: coordinates == "wcs" ? "WCS" : "Image pixels")
        }
        if let reason = preview.reason {
          Text(redact(reason)).foregroundStyle(.secondary)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  private func pixelDetails(_ pixel: FITSInspectionSummary.PixelLookup) -> some View {
    GroupBox("Pixel lookup") {
      VStack(alignment: .leading, spacing: 6) {
        LabeledContent("Source pixel (zero-based x, y)", value: pixel.imageXy.map(String.init).joined(separator: ", "))
        if !pixel.planeIndices.isEmpty {
          LabeledContent("Leading-axis indices (zero-based)", value: pixel.planeIndices.map(String.init).joined(separator: ", "))
        }
        if let value = pixel.pixelValue {
          let unit = pixel.pixelUnit.map(redact)
          LabeledContent("Pixel value", value: [redact(value.text), unit].compactMap { $0 }.joined(separator: " "))
        } else if pixel.pixelStatus == "nonfinite" {
          LabeledContent("Pixel value", value: "Nonfinite or undefined")
        }
        if let frame = pixel.referenceFrame {
          LabeledContent("Reference frame", value: redact(frame))
        }
        ForEach(pixel.worldAxes.indices, id: \.self) { index in
          let axis = pixel.worldAxes[index]
          let name = axis.name.isEmpty ? "Axis \(index + 1)" : redact(axis.name)
          LabeledContent(name, value: [numbers([axis.value]), redact(axis.unit)].filter { !$0.isEmpty }.joined(separator: " "))
        }
        if let reason = pixel.worldReason {
          Text(redact(reason)).foregroundStyle(.secondary)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("results.fits.pixel-result")
  }

  private func numbers(_ values: [Double]) -> String {
    values.map { $0.formatted(.number.precision(.significantDigits(1...10))) }.joined(separator: ", ")
  }
}

private struct FITSInspectionControls: View {
  let imageWidth: Int
  let imageHeight: Int
  let canLookup: Bool
  let canCrop: Bool
  let onAction: (FITSInspectionAction) -> Void
  @State private var xText: String
  @State private var yText: String
  @State private var widthText: String
  @State private var heightText: String

  init(imageWidth: Int, imageHeight: Int, region: [Int]?, lastPixel: [Int]?, canLookup: Bool, canCrop: Bool,
       onAction: @escaping (FITSInspectionAction) -> Void) {
    self.imageWidth = imageWidth
    self.imageHeight = imageHeight
    self.canLookup = canLookup
    self.canCrop = canCrop
    self.onAction = onAction
    let initial = region?.count == 4 ? region : nil
    let coordinates = lastPixel?.count == 2 ? lastPixel : nil
    _xText = State(initialValue: String(coordinates?[0] ?? initial?[0] ?? 0))
    _yText = State(initialValue: String(coordinates?[1] ?? initial?[1] ?? 0))
    _widthText = State(initialValue: String(min(initial?[2] ?? imageWidth, 1_024)))
    _heightText = State(initialValue: String(min(initial?[3] ?? imageHeight, 1_024)))
  }

  private var pixel: (x: Int, y: Int)? {
    guard let x = Int(xText), let y = Int(yText), x >= 0, x < imageWidth, y >= 0, y < imageHeight else {
      return nil
    }
    return (x, y)
  }

  private var crop: FITSInspectionAction? {
    guard let pixel, let width = Int(widthText), let height = Int(heightText),
          (1...1_024).contains(width), (1...1_024).contains(height) else { return nil }
    return .crop(x: pixel.x, y: pixel.y, width: width, height: height)
  }

  var body: some View {
    GroupBox("Inspect source image") {
      VStack(alignment: .leading, spacing: 8) {
        Text("Use zero-based coordinates in this HDU. Each action reads the recorded source path and creates a new run.")
          .font(.caption)
          .foregroundStyle(.secondary)
        HStack(alignment: .bottom) {
          inputField("X", text: $xText, identifier: "results.fits.x")
          inputField("Y", text: $yText, identifier: "results.fits.y")
          if canLookup {
            Button("Look up pixel") {
              if let pixel { onAction(.lookup(x: pixel.x, y: pixel.y)) }
            }
            .disabled(pixel == nil)
            .accessibilityIdentifier("results.fits.lookup")
          }
        }
        if canCrop {
          HStack(alignment: .bottom) {
            inputField("Width", text: $widthText, identifier: "results.fits.width")
            inputField("Height", text: $heightText, identifier: "results.fits.height")
            Button("Render crop") {
              if let crop { onAction(crop) }
            }
            .disabled(crop == nil)
            .accessibilityIdentifier("results.fits.crop")
          }
          Text("Crop size is capped at 1,024 pixels per side and clips at the image edge.")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
      }
      .textFieldStyle(.roundedBorder)
    }
  }

  private func inputField(_ title: String, text: Binding<String>, identifier: String) -> some View {
    VStack(alignment: .leading, spacing: 3) {
      Text(title).font(.caption)
        .accessibilityHidden(true)
      TextField(title, text: text)
        .accessibilityLabel(title)
        .accessibilityIdentifier(identifier)
    }
  }
}
