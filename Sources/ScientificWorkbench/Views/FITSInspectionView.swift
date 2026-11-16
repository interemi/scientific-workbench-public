import SwiftUI

struct FITSInspectionView: View {
  let summary: FITSInspectionSummary
  let redact: (String) -> String
  @State private var selectedIndex: Int

  init(summary: FITSInspectionSummary, redact: @escaping (String) -> String) {
    self.summary = summary
    self.redact = redact
    _selectedIndex = State(initialValue: summary.preview?.hduIndex ?? summary.previewExtension
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

  private func numbers(_ values: [Double]) -> String {
    values.map { $0.formatted(.number.precision(.significantDigits(1...10))) }.joined(separator: ", ")
  }
}
