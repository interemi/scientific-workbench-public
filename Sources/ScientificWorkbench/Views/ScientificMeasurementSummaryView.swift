import SwiftUI

struct ScientificMeasurementSummaryView: View {
  let summary: ScientificMeasurementSummary
  let redact: (String) -> String

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        HStack(alignment: .firstTextBaseline) {
          Text("Measurements and quality")
            .font(.headline)
          Spacer()
          StatusBadge(status: redact(summary.quality.status))
            .accessibilityLabel("Quality status: \(redact(summary.quality.status))")
        }
        Text(redact(summary.method))
          .foregroundStyle(.secondary)
        if summary.measurements.isEmpty {
          Text("No measurements were reported.")
        } else {
          quantities(summary.measurements, title: "Measurements", reportUncertainty: true)
        }
        if !summary.quality.findings.isEmpty {
          section("Quality findings", lines: summary.quality.findings)
        }
        if !summary.diagnostics.isEmpty {
          quantities(summary.diagnostics, title: "Fit diagnostics", reportUncertainty: false)
        }
        if !summary.assumptions.isEmpty {
          section("Method and assumptions", lines: summary.assumptions)
        }
      }
      .textSelection(.enabled)
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(12)
    }
    .accessibilityIdentifier("results.measurement-summary")
  }

  private func quantities(
    _ values: [ScientificMeasurementSummary.Quantity], title: String, reportUncertainty: Bool
  ) -> some View {
    VStack(alignment: .leading, spacing: 7) {
      Text(title).font(.subheadline.weight(.semibold))
      Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 7) {
        ForEach(Array(values.enumerated()), id: \.offset) { _, quantity in
          GridRow(alignment: .firstTextBaseline) {
            Text(redact(quantity.label))
            VStack(alignment: .leading, spacing: 2) {
              Text(valueText(quantity)).monospacedDigit()
              if reportUncertainty && quantity.uncertainty == nil {
                Text("Uncertainty unavailable")
                  .font(.caption)
                  .foregroundStyle(.secondary)
              }
            }
          }
          .accessibilityElement(children: .combine)
        }
      }
    }
  }

  private func valueText(_ quantity: ScientificMeasurementSummary.Quantity) -> String {
    let unit = quantity.unit == "dimensionless" ? "" : " " + redact(quantity.unit)
    let value = formatted(quantity.value, significantDigits: 6)
    if let uncertainty = quantity.uncertainty {
      let error = formatted(uncertainty, significantDigits: 3)
      return "\(value) ± \(error)\(unit)"
    }
    return value + unit
  }

  private func formatted(_ value: Double, significantDigits: Int) -> String {
    let style = FloatingPointFormatStyle<Double>.number.precision(.significantDigits(1...significantDigits))
    let useScientificNotation = (value != 0 && abs(value) < 0.001) || abs(value) >= 1_000_000
    return value.formatted(useScientificNotation ? style.notation(.scientific) : style)
  }

  private func section(_ title: String, lines: [String]) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title).font(.subheadline.weight(.semibold))
      ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
        Text(redact(line))
          .font(.callout)
      }
    }
  }
}
