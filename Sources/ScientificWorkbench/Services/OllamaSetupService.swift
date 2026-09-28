import Foundation

struct OllamaSetupService: Sendable {
  static let defaultPullTimeoutSeconds: TimeInterval = 2 * 60 * 60

  var pathEnvironment: String
  var fileExists: @Sendable (String) -> Bool
  var dataLoader: @Sendable (URLRequest) async throws -> (Data, URLResponse)
  private let runner: ProcessRunner
  private let pullTimeoutSeconds: TimeInterval

  init(
    pathEnvironment: String = ProcessInfo.processInfo.environment["PATH"] ?? "",
    fileExists: @escaping @Sendable (String) -> Bool = { path in
      FileManager.default.isExecutableFile(atPath: path)
    },
    dataLoader: @escaping @Sendable (URLRequest) async throws -> (Data, URLResponse) = { request in
      try await SafeURLSessionTransport.data(for: request)
    },
    runner: ProcessRunner = ProcessRunner(),
    pullTimeoutSeconds: TimeInterval = OllamaSetupService.defaultPullTimeoutSeconds
  ) {
    self.pathEnvironment = pathEnvironment
    self.fileExists = fileExists
    self.dataLoader = dataLoader
    self.runner = runner
    self.pullTimeoutSeconds = pullTimeoutSeconds
  }

  func status(baseURL: String?, model: String) async -> OllamaSetupStatus {
    let cliPath = locateCLI()
    do {
      let models = try await fetchInstalledModels(baseURL: baseURL)
      return OllamaSetupStatus(
        cliPath: cliPath,
        serverReachable: true,
        installedModels: models,
        targetModel: model,
        message: statusMessage(cliPath: cliPath, serverReachable: true, models: models, model: model),
        checkedAt: Date()
      )
    } catch {
      let message: String
      if let setupError = error as? OllamaSetupError {
        switch setupError {
        case .invalidBaseURL, .unsafeEndpoint:
          message = setupError.localizedDescription
        default:
          message = statusMessage(cliPath: cliPath, serverReachable: false, models: [], model: model)
        }
      } else {
        message = statusMessage(cliPath: cliPath, serverReachable: false, models: [], model: model)
      }
      return OllamaSetupStatus(
        cliPath: cliPath,
        serverReachable: false,
        installedModels: [],
        targetModel: model,
        message: message,
        checkedAt: Date()
      )
    }
  }

  func locateCLI() -> String? {
    let pathCandidates = pathEnvironment
      .split(separator: ":")
      .map { String($0) }
      .map { URL(fileURLWithPath: $0).appendingPathComponent("ollama").path }

    let commonCandidates = [
      "/opt/homebrew/bin/ollama",
      "/usr/local/bin/ollama",
      "/Applications/Ollama.app/Contents/Resources/ollama"
    ]

    return (pathCandidates + commonCandidates).first(where: fileExists)
  }

  func pullModel(_ model: String) async throws -> OllamaCommandResult {
    guard let cliPath = locateCLI() else {
      throw OllamaSetupError.cliMissing
    }
    return try await run(executable: cliPath, arguments: ["pull", model])
  }

  private func fetchInstalledModels(baseURL: String?) async throws -> [String] {
    var request = URLRequest(url: try apiURL(baseURL: baseURL, path: "tags"))
    request.httpMethod = "GET"
    request.timeoutInterval = 3

    let (data, response) = try await dataLoader(request)
    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
      throw OllamaSetupError.serverUnavailable
    }

    let tags = try JSONDecoder().decode(OllamaTagsResponse.self, from: data)
    return tags.models.map(\.name).sorted()
  }

  private func apiURL(baseURL: String?, path: String) throws -> URL {
    do {
      return try OllamaEndpointPolicy.apiURL(baseURL: baseURL, endpoint: path)
    } catch OllamaEndpointPolicyError.invalidBaseURL(let raw) {
      throw OllamaSetupError.invalidBaseURL(raw)
    } catch OllamaEndpointPolicyError.unsafeEndpoint(let raw) {
      throw OllamaSetupError.unsafeEndpoint(raw)
    } catch {
      throw OllamaSetupError.invalidBaseURL(baseURL ?? "http://localhost:11434")
    }
  }

  private func run(executable: String, arguments: [String]) async throws -> OllamaCommandResult {
    var command = ProcessCommand(
      executable: executable,
      arguments: arguments,
      workingDirectory: nil
    )
    command.timeoutSeconds = pullTimeoutSeconds > 0
      ? pullTimeoutSeconds
      : Self.defaultPullTimeoutSeconds
    command.environmentPolicy = .strict
    command.redirectStandardInputToNull = true

    let result: ProcessResult
    do {
      result = try await runner.run(command)
    } catch ProcessRunnerError.cancelled {
      throw OllamaSetupError.cancelled
    } catch ProcessRunnerError.timedOut(let seconds) {
      throw OllamaSetupError.timedOut(seconds)
    }

    return OllamaCommandResult(
      exitCode: result.exitCode,
      stdout: result.stdout,
      stderr: result.stderr
    )
  }

  private func statusMessage(
    cliPath: String?,
    serverReachable: Bool,
    models: [String],
    model: String
  ) -> String {
    guard cliPath != nil else {
      return "Install Ollama first, then come back here to download the compact local model."
    }
    guard serverReachable else {
      return "Ollama CLI is installed. Open Ollama so the local server starts, then check again."
    }
    guard models.contains(model) else {
      return "Ollama is running. Download \(model) to enable local AI chat and planning."
    }
    return "Ollama is ready with \(model). Local AI can be tested now."
  }
}

private struct OllamaTagsResponse: Decodable {
  struct Model: Decodable {
    var name: String
  }

  var models: [Model]
}

enum OllamaSetupError: LocalizedError {
  case cliMissing
  case invalidBaseURL(String)
  case unsafeEndpoint(String)
  case serverUnavailable
  case timedOut(TimeInterval)
  case cancelled

  var errorDescription: String? {
    switch self {
    case .cliMissing:
      return "Ollama CLI was not found. Install Ollama first."
    case .invalidBaseURL(let url):
      return "Ollama base URL is invalid: \(url)"
    case .unsafeEndpoint(let url):
      return "Ollama setup checks are restricted to an HTTP(S) loopback endpoint: \(url)"
    case .serverUnavailable:
      return "Ollama server is not reachable."
    case .timedOut(let seconds):
      return "Ollama model download timed out after \(max(1, Int(seconds.rounded(.up)))) seconds. Try again when the connection is stable."
    case .cancelled:
      return "Ollama model download was cancelled."
    }
  }
}
