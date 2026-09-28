import SwiftUI

struct CapabilityTimeoutControl: View {
  @Binding var minutes: Int

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(alignment: .firstTextBaseline) {
        Text("Capability timeout (minutes)")
        Spacer()
        Text("\(normalizedMinutes)")
          .font(.system(.body, design: .rounded).weight(.semibold))
          .monospacedDigit()
          .padding(.horizontal, 10)
          .padding(.vertical, 4)
          .background(.thinMaterial, in: Capsule())
          .accessibilityLabel("Selected capability timeout")
          .accessibilityValue("\(normalizedMinutes) minutes")
      }

      Slider(
        value: sliderValue,
        in: Double(ExternalProcessTimeoutPolicy.minimumMinutes)...Double(ExternalProcessTimeoutPolicy.maximumMinutes),
        step: Double(ExternalProcessTimeoutPolicy.stepMinutes)
      ) {
        Text("Capability timeout")
      }
      .labelsHidden()
      .frame(maxWidth: .infinity)
      .tint(.accentColor)
      .accessibilityLabel("Capability timeout (minutes)")
      .accessibilityValue("\(normalizedMinutes)")

      VStack(spacing: 3) {
        HStack(spacing: 0) {
          ForEach(ExternalProcessTimeoutPolicy.options, id: \.self) { value in
            Capsule()
              .fill(tickColor(for: value))
              .frame(width: 1, height: value == normalizedMinutes ? 7 : 4)
              .frame(maxWidth: .infinity)
          }
        }

        HStack(spacing: 0) {
          ForEach(ExternalProcessTimeoutPolicy.options, id: \.self) { value in
            Text("\(value)")
              .font(.caption2.monospacedDigit())
              .fontWeight(value == normalizedMinutes ? .semibold : .regular)
              .foregroundStyle(tickColor(for: value))
              .lineLimit(1)
              .minimumScaleFactor(0.55)
              .frame(maxWidth: .infinity)
          }
        }
      }
      .accessibilityHidden(true)
    }
    .padding(.vertical, 4)
  }

  private var normalizedMinutes: Int {
    ExternalProcessTimeoutPolicy.normalized(minutes: minutes)
  }

  private var sliderValue: Binding<Double> {
    Binding(
      get: { Double(normalizedMinutes) },
      set: { newValue in
        minutes = ExternalProcessTimeoutPolicy.normalized(minutes: Int(newValue.rounded()))
      }
    )
  }

  private func tickColor(for value: Int) -> Color {
    if value == normalizedMinutes {
      return .accentColor
    }
    if value == ExternalProcessTimeoutPolicy.defaultMinutes {
      return .secondary
    }
    return .secondary.opacity(0.55)
  }
}
