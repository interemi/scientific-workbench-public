import Foundation
import Network

enum JobRecoveryNetworkPath: Sendable {
  case available
  case unavailable
  case requiresConnection
  case notVerified

  var summary: String {
    let finding: String
    switch self {
    case .available: finding = "macOS reports an available network path."
    case .unavailable: finding = "macOS reports no available network path. Check the network connection and any VPN."
    case .requiresConnection: finding = "macOS reports that a connection must be established. Review the network and any VPN."
    case .notVerified: finding = "No current network-path result was received; retry the check."
    }
    return "Current network check: \(finding) No server request was sent. "
      + "This does not verify the job's endpoint, credentials, model, or service availability."
  }
}

struct JobRecoveryNetworkProbe: Sendable {
  func inspect(timeout: Duration = .seconds(5)) async -> JobRecoveryNetworkPath {
    guard !Task.isCancelled else { return .notVerified }
    let monitor = NWPathMonitor()
    let (stream, continuation) = AsyncStream<JobRecoveryNetworkPath>.makeStream()
    monitor.pathUpdateHandler = { path in
      let result: JobRecoveryNetworkPath
      switch path.status {
      case .satisfied: result = .available
      case .unsatisfied: result = .unavailable
      case .requiresConnection: result = .requiresConnection
      @unknown default: result = .notVerified
      }
      continuation.yield(result)
      continuation.finish()
    }
    continuation.onTermination = { _ in monitor.cancel() }
    monitor.start(queue: DispatchQueue(label: "scientific-workbench.recovery-network"))
    let deadline = Task {
      do {
        try await Task.sleep(for: timeout)
        continuation.finish()
      } catch { }
    }
    defer {
      deadline.cancel()
      monitor.cancel()
      continuation.finish()
    }
    for await result in stream { return result }
    return .notVerified
  }
}
