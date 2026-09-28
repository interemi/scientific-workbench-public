// swift-tools-version: 6.0
import Foundation
import PackageDescription

let developerDirectoryCandidates = [
  ProcessInfo.processInfo.environment["DEVELOPER_DIR"],
  "/Library/Developer/CommandLineTools",
  "/Applications/Xcode.app/Contents/Developer",
  "/Applications/Xcode-beta.app/Contents/Developer"
].compactMap(\.self)

let testingFrameworkDirectory = developerDirectoryCandidates
  .map { "\($0)/Library/Developer/Frameworks" }
  .first { FileManager.default.fileExists(atPath: "\($0)/Testing.framework") }

let testingInteropDirectory = developerDirectoryCandidates
  .map { "\($0)/Library/Developer/usr/lib" }
  .first { FileManager.default.fileExists(atPath: "\($0)/lib_TestingInterop.dylib") }

// SwiftPM does not discover Swift Testing from this Command Line Tools install by default.
// These scoped test-target flags expose Testing.framework and its lib_TestingInterop runtime.
let testingSwiftSettings: [SwiftSetting] = testingFrameworkDirectory.map {
  [.unsafeFlags(["-F", $0])]
} ?? []

let testingLinkerFlags: [String] = {
  var flags: [String] = []
  if let testingFrameworkDirectory {
    flags += [
      "-F", testingFrameworkDirectory,
      "-Xlinker", "-rpath",
      "-Xlinker", testingFrameworkDirectory
    ]
  }
  if let testingInteropDirectory {
    flags += [
      "-Xlinker", "-rpath",
      "-Xlinker", testingInteropDirectory
    ]
  }
  return flags
}()

let testingLinkerSettings: [LinkerSetting] = testingLinkerFlags.isEmpty
  ? []
  : [.unsafeFlags(testingLinkerFlags)]

let package = Package(
  name: "ScientificWorkbench",
  platforms: [
    .macOS(.v14)
  ],
  products: [
    .executable(name: "ScientificWorkbench", targets: ["ScientificWorkbench"])
  ],
  targets: [
    .executableTarget(
      name: "ScientificWorkbench"
    ),
    .testTarget(
      name: "ScientificWorkbenchTests",
      dependencies: ["ScientificWorkbench"],
      swiftSettings: testingSwiftSettings,
      linkerSettings: testingLinkerSettings
    )
  ]
)
