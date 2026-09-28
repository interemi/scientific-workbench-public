import Foundation

enum ExternalProcessTimeoutPolicy {
  static let defaultMinutes = 30
  static let minimumMinutes = 5
  static let maximumMinutes = 120
  static let stepMinutes = 5

  static let options = Array(
    stride(
      from: minimumMinutes,
      through: maximumMinutes,
      by: stepMinutes
    )
  )

  static func normalized(minutes: Int) -> Int {
    let clamped = min(max(minutes, minimumMinutes), maximumMinutes)
    let roundedSteps = Int(
      (Double(clamped) / Double(stepMinutes)).rounded()
    )
    return min(
      max(roundedSteps * stepMinutes, minimumMinutes),
      maximumMinutes
    )
  }

  static func seconds(for minutes: Int) -> TimeInterval {
    TimeInterval(normalized(minutes: minutes) * 60)
  }
}
