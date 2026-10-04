import Foundation

enum EnvironmentRepairProfile: String, CaseIterable, Identifiable {
  case core
  case full

  var id: String { rawValue }
  var title: String { rawValue.capitalized }
  var minimumLockedMacOS: Int { self == .core ? 14 : 15 }
  var localDiskMeasurement: String { self == .core ? "455 MiB" : "1.43 GiB" }
  var localTimeMeasurement: String { self == .core ? "18 seconds" : "55 seconds" }
}

struct EnvironmentRepairPlan: Equatable {
  let profile: EnvironmentRepairProfile
  let destination: String
  let previewCommand: String
  let installCommand: String
  let usesReviewedLock: Bool

  static func make(
    profile: EnvironmentRepairProfile,
    identifier: UUID = UUID(),
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
    isAppleSilicon: Bool,
    macOSMajorVersion: Int
  ) -> EnvironmentRepairPlan {
    let directoryName = "\(profile.rawValue)-\(identifier.uuidString.lowercased())"
    let relativeDestination =
      "Library/Application Support/Scientific Workbench/environments/\(directoryName)/datanalysis"
    let destination = homeDirectory.appendingPathComponent(relativeDestination).path
    let locked = isAppleSilicon && macOSMajorVersion >= profile.minimumLockedMacOS
    let lockOption = locked ? " --locked" : ""
    let quotedDestination = "'" + destination.replacingOccurrences(of: "'", with: "'\\''") + "'"
    let preview = "python3 script/setup_environment.py --python python3.11 --profile \(profile.rawValue)\(lockOption) --destination \(quotedDestination)"

    return EnvironmentRepairPlan(
      profile: profile,
      destination: destination,
      previewCommand: preview,
      installCommand: preview + " --install",
      usesReviewedLock: locked
    )
  }
}
