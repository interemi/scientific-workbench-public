import Foundation

private struct CloudAIChatMessagePayload: Encodable {
  var role: String
  var content: String
}

private struct OllamaChatRequestPayload: Encodable {
  var model: String
  var messages: [CloudAIChatMessagePayload]
  var stream: Bool
  var options: Options

  struct Options: Encodable {
    var temperature: Double
    var numPredict: Int?

    enum CodingKeys: String, CodingKey {
      case temperature
      case numPredict = "num_predict"
    }
  }
}

private struct OpenAIResponsesRequestPayload: Encodable {
  var model: String
  var instructions: String
  var input: String
  var temperature: Double
  var maxOutputTokens: Int?

  enum CodingKeys: String, CodingKey {
    case model
    case instructions
    case input
    case temperature
    case maxOutputTokens = "max_output_tokens"
  }
}

private struct ChatCompletionsRequestPayload: Encodable {
  var model: String
  var messages: [CloudAIChatMessagePayload]
  var temperature: Double
  var maxTokens: Int?

  enum CodingKeys: String, CodingKey {
    case model
    case messages
    case temperature
    case maxTokens = "max_tokens"
  }
}

private struct GeminiGenerateContentRequestPayload: Encodable {
  var systemInstruction: Instruction
  var contents: [Content]
  var generationConfig: GenerationConfig

  struct Instruction: Encodable {
    var parts: [Part]
  }

  struct Content: Encodable {
    var role: String
    var parts: [Part]
  }

  struct Part: Encodable {
    var text: String
  }

  struct GenerationConfig: Encodable {
    var temperature: Double?
    var maxOutputTokens: Int?
  }
}

private struct OpenAIResponsesResponsePayload: Decodable {
  var outputText: String?
  var output: [OutputItem]?

  struct OutputItem: Decodable {
    var content: [ContentPart]?
  }

  struct ContentPart: Decodable {
    var text: String?
  }

  enum CodingKeys: String, CodingKey {
    case outputText = "output_text"
    case output
  }

  var readableText: String? {
    if let outputText {
      return outputText
    }
    return output?
      .lazy
      .compactMap { item in
        item.content?.lazy.compactMap(\.text).first
      }
      .first
  }
}

private struct ChatCompletionsResponsePayload: Decodable {
  var choices: [Choice]

  struct Choice: Decodable {
    var message: Message?
  }

  struct Message: Decodable {
    var content: String?
  }

  var readableText: String? {
    choices.first?.message?.content
  }
}

private struct OllamaChatResponsePayload: Decodable {
  var message: Message?

  struct Message: Decodable {
    var content: String?
  }

  var readableText: String? {
    message?.content
  }
}

private struct GeminiGenerateContentResponsePayload: Decodable {
  var candidates: [Candidate]

  struct Candidate: Decodable {
    var content: Content?
  }

  struct Content: Decodable {
    var parts: [Part]?
  }

  struct Part: Decodable {
    var text: String?
  }

  var readableText: String? {
    guard let parts = candidates.first?.content?.parts else { return nil }
    let text = parts.compactMap(\.text).joined()
    return text.isEmpty ? nil : text
  }
}

private struct ProviderErrorPayload: Decodable {
  var root: JSONFragment

  init(from decoder: Decoder) throws {
    root = try JSONFragment(from: decoder)
  }

  var message: String? {
    let fragments = root.stringFragments()
    guard !fragments.isEmpty else { return nil }
    return fragments.joined(separator: " ")
  }

  enum JSONFragment: Decodable {
    case string(String)
    case number(String)
    case bool(Bool)
    case object([String: JSONFragment])
    case array([JSONFragment])
    case null

    init(from decoder: Decoder) throws {
      if let container = try? decoder.container(keyedBy: DynamicCodingKey.self) {
        var values: [String: JSONFragment] = [:]
        for key in container.allKeys {
          values[key.stringValue] = try container.decode(JSONFragment.self, forKey: key)
        }
        self = .object(values)
        return
      }

      if var container = try? decoder.unkeyedContainer() {
        var values: [JSONFragment] = []
        while !container.isAtEnd {
          values.append(try container.decode(JSONFragment.self))
        }
        self = .array(values)
        return
      }

      let container = try decoder.singleValueContainer()
      if container.decodeNil() {
        self = .null
      } else if let string = try? container.decode(String.self) {
        self = .string(string)
      } else if let bool = try? container.decode(Bool.self) {
        self = .bool(bool)
      } else if let integer = try? container.decode(Int64.self) {
        self = .number(String(integer))
      } else if let double = try? container.decode(Double.self) {
        self = .number(String(double))
      } else {
        self = .null
      }
    }

    func stringFragments() -> [String] {
      switch self {
      case .string(let string):
        return [string]
      case .number(let number):
        return [number]
      case .bool(let bool):
        return [String(bool)]
      case .object(let dictionary):
        return dictionary.keys.sorted().flatMap { key in
          dictionary[key]?.stringFragments() ?? []
        }
      case .array(let array):
        return array.flatMap { $0.stringFragments() }
      case .null:
        return []
      }
    }
  }
}

private struct DynamicCodingKey: CodingKey {
  var stringValue: String
  var intValue: Int?

  init?(stringValue: String) {
    self.stringValue = stringValue
  }

  init?(intValue: Int) {
    self.stringValue = String(intValue)
    self.intValue = intValue
  }
}

struct CloudAIClient: Sendable {
  var dataLoader: @Sendable (URLRequest) async throws -> (Data, URLResponse)

  init(dataLoader: @escaping @Sendable (URLRequest) async throws -> (Data, URLResponse) = { request in
    try await SafeURLSessionTransport.data(for: request)
  }) {
    self.dataLoader = dataLoader
  }

  func respond(
    prompt: String,
    history: [AgentChatMessage],
    inputPaths: [String],
    workflowRecoveryContext: String? = nil,
    attachmentContextMode: CloudAttachmentContextMode = .previews,
    provider: AIProvider,
    apiKey: String,
    model: String,
    baseURL: String? = nil
  ) async throws -> String {
    // Validate Ollama before reading any attachment preview. A remote endpoint
    // must never inherit the trust boundary of the local provider label.
    if provider == .ollama {
      _ = try ollamaChatURL(from: normalizedBaseURL(baseURL, provider: provider))
    }

    let transcript = history.suffix(12).map { message in
      "\(message.role.rawValue): \(message.text)"
    }.joined(separator: "\n\n")

    let user = """
    Recent conversation:
    \(transcript.isEmpty ? "(empty)" : transcript)

    Current user message:
    \(prompt)

    Attached inputs:
    \(attachmentInputSummary(for: inputPaths, mode: attachmentContextMode))

    Attachment context:
    \(attachmentContext(for: inputPaths, mode: attachmentContextMode))

    Workflow recovery context:
    \(privacyFilteredRecoveryContext(workflowRecoveryContext, mode: attachmentContextMode))
    """

    return try await generateText(
      provider: provider,
      apiKey: apiKey,
      model: normalizedModel(model, provider: provider),
      baseURL: normalizedBaseURL(baseURL, provider: provider),
      system: """
      You are Scientific Workbench, a concise local scientific/coding assistant inside a macOS app.
      Be direct and practical. If the user is asking to operate on local files, recommend a workflow rather than pretending you can see file contents.
      If workflow recovery context is present, treat it as the source of truth. Explain exactly where the workflow stopped, what to inspect, and whether to use Dry Run, Open Job, or Run Remaining.
      Never claim to have modified files unless a local tool or Codex bridge actually did it.
      """,
      user: user,
      temperature: 0.2
    )
  }

  func generateText(
    provider: AIProvider,
    apiKey: String,
    model: String,
    baseURL: String? = nil,
    system: String,
    user: String,
    temperature: Double = 0.2,
    maxOutputTokens: Int? = nil
  ) async throws -> String {
    switch provider {
    case .ollama:
      return try await generateOllamaChat(
        baseURL: normalizedBaseURL(baseURL, provider: provider),
        model: model,
        system: system,
        user: user,
        temperature: temperature,
        maxOutputTokens: maxOutputTokens
      )
    case .openAI:
      return try await generateOpenAI(
        apiKey: apiKey,
        model: model,
        system: system,
        user: user,
        temperature: temperature,
        maxOutputTokens: maxOutputTokens
      )
    case .grok:
      return try await generateOpenAICompatibleChat(
        apiKey: apiKey,
        baseURL: "https://api.x.ai/v1/chat/completions",
        model: model,
        system: system,
        user: user,
        temperature: temperature,
        maxOutputTokens: maxOutputTokens
      )
    case .gemini:
      return try await generateGemini(
        apiKey: apiKey,
        model: model,
        system: system,
        user: user,
        temperature: temperature,
        maxOutputTokens: maxOutputTokens
      )
    }
  }

  func testConnection(
    provider: AIProvider,
    apiKey: String,
    model: String,
    baseURL: String? = nil
  ) async throws -> String {
    if provider == .ollama {
      let output = try await generateText(
        provider: provider,
        apiKey: apiKey,
        model: normalizedModel(model, provider: provider),
        baseURL: normalizedBaseURL(baseURL, provider: provider),
        system: "You are a local connection test endpoint. Reply briefly.",
        user: "Reply with OK.",
        temperature: 0,
        maxOutputTokens: 128
      )
      let trimmed = output.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !trimmed.isEmpty else {
        throw CloudAIError.unexpectedTestResponse(trimmed)
      }
      return trimmed
    }

    let output = try await generateText(
      provider: provider,
      apiKey: apiKey,
      model: normalizedModel(model, provider: provider),
      baseURL: normalizedBaseURL(baseURL, provider: provider),
      system: "You are a connection test endpoint. Reply only with the requested text.",
      user: "Reply with exactly: Scientific Workbench AI connection OK",
      temperature: 0,
      maxOutputTokens: provider == .gemini ? 512 : 32
    )
    let trimmed = output.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.localizedCaseInsensitiveContains("Scientific Workbench AI connection OK") else {
      throw CloudAIError.unexpectedTestResponse(trimmed)
    }
    return trimmed
  }

  private func generateOllamaChat(
    baseURL: String?,
    model: String,
    system: String,
    user: String,
    temperature: Double,
    maxOutputTokens: Int?
  ) async throws -> String {
    var request = URLRequest(url: try ollamaChatURL(from: baseURL))
    request.httpMethod = "POST"
    request.timeoutInterval = 60
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body = OllamaChatRequestPayload(
      model: model,
      messages: [
        CloudAIChatMessagePayload(role: "system", content: system),
        CloudAIChatMessagePayload(role: "user", content: user)
      ],
      stream: false,
      options: OllamaChatRequestPayload.Options(
        temperature: temperature,
        numPredict: maxOutputTokens
      )
    )
    request.httpBody = try encodeRequestBody(body)

    let data = try await checkedData(for: request)
    return try extractOllamaChatText(from: data)
  }

  private func generateOpenAI(
    apiKey: String,
    model: String,
    system: String,
    user: String,
    temperature: Double,
    maxOutputTokens: Int?
  ) async throws -> String {
    var request = URLRequest(url: URL(string: "https://api.openai.com/v1/responses")!)
    request.httpMethod = "POST"
    request.timeoutInterval = 60
    request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body = OpenAIResponsesRequestPayload(
      model: model,
      instructions: system,
      input: user,
      temperature: temperature,
      maxOutputTokens: maxOutputTokens
    )
    request.httpBody = try encodeRequestBody(body)

    let data = try await checkedData(for: request)
    return try extractOpenAIResponsesText(from: data)
  }

  private func generateOpenAICompatibleChat(
    apiKey: String,
    baseURL: String,
    model: String,
    system: String,
    user: String,
    temperature: Double,
    maxOutputTokens: Int?
  ) async throws -> String {
    var request = URLRequest(url: URL(string: baseURL)!)
    request.httpMethod = "POST"
    request.timeoutInterval = 60
    request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    let body = ChatCompletionsRequestPayload(
      model: model,
      messages: [
        CloudAIChatMessagePayload(role: "system", content: system),
        CloudAIChatMessagePayload(role: "user", content: user)
      ],
      temperature: temperature,
      maxTokens: maxOutputTokens
    )
    request.httpBody = try encodeRequestBody(body)

    let data = try await checkedData(for: request)
    return try extractChatCompletionsText(from: data)
  }

  private func generateGemini(
    apiKey: String,
    model: String,
    system: String,
    user: String,
    temperature: Double,
    maxOutputTokens: Int?
  ) async throws -> String {
    let cleanModel = model.replacingOccurrences(of: "models/", with: "")
    let encodedModel = cleanModel.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? cleanModel
    let endpoint = URL(
      string: "https://generativelanguage.googleapis.com/v1beta/models/\(encodedModel):generateContent"
    )!
    var request = URLRequest(url: endpoint)
    request.httpMethod = "POST"
    request.timeoutInterval = 60
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    // Keep credentials out of URLs, which may be recorded in diagnostics.
    request.setValue(apiKey, forHTTPHeaderField: "x-goog-api-key")

    let body = GeminiGenerateContentRequestPayload(
      systemInstruction: GeminiGenerateContentRequestPayload.Instruction(
        parts: [GeminiGenerateContentRequestPayload.Part(text: system)]
      ),
      contents: [
        GeminiGenerateContentRequestPayload.Content(
          role: "user",
          parts: [GeminiGenerateContentRequestPayload.Part(text: user)]
        )
      ],
      generationConfig: GeminiGenerateContentRequestPayload.GenerationConfig(
        temperature: cleanModel.hasPrefix("gemini-3") ? nil : temperature,
        maxOutputTokens: maxOutputTokens
      )
    )
    request.httpBody = try encodeRequestBody(body)

    let data = try await checkedData(for: request)
    return try extractGeminiText(from: data)
  }

  private func checkedData(for request: URLRequest) async throws -> Data {
    let data: Data
    let response: URLResponse
    do {
      (data, response) = try await dataLoader(request)
    } catch let error as CancellationError {
      throw error
    } catch let error as CloudAIError {
      throw error
    } catch let error as URLError {
      throw CloudAIError.transport(error)
    } catch {
      throw CloudAIError.networkUnavailable(error.localizedDescription)
    }

    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
      let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
      throw CloudAIError.httpFailure(statusCode: statusCode, data: data)
    }
    return data
  }

  private func encodeRequestBody<T: Encodable>(_ payload: T) throws -> Data {
    try JSONEncoder().encode(payload)
  }

  private func extractOpenAIResponsesText(from data: Data) throws -> String {
    let payload: OpenAIResponsesResponsePayload = try decodeResponsePayload(from: data)
    guard let text = payload.readableText else { throw CloudAIError.invalidResponse }
    return text
  }

  private func extractChatCompletionsText(from data: Data) throws -> String {
    let payload: ChatCompletionsResponsePayload = try decodeResponsePayload(from: data)
    guard let text = payload.readableText else { throw CloudAIError.invalidResponse }
    return text
  }

  private func extractOllamaChatText(from data: Data) throws -> String {
    let payload: OllamaChatResponsePayload = try decodeResponsePayload(from: data)
    guard let text = payload.readableText else { throw CloudAIError.invalidResponse }
    return text
  }

  private func extractGeminiText(from data: Data) throws -> String {
    let payload: GeminiGenerateContentResponsePayload = try decodeResponsePayload(from: data)
    guard let text = payload.readableText else { throw CloudAIError.invalidResponse }
    return text
  }

  private func decodeResponsePayload<T: Decodable>(from data: Data) throws -> T {
    do {
      return try JSONDecoder().decode(T.self, from: data)
    } catch {
      throw CloudAIError.invalidResponse
    }
  }

  private func normalizedModel(_ model: String, provider: AIProvider) -> String {
    let trimmed = model.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? provider.defaultModel : trimmed
  }

  private func normalizedBaseURL(_ baseURL: String?, provider: AIProvider) -> String? {
    let trimmed = baseURL?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !trimmed.isEmpty {
      return trimmed
    }
    return provider.defaultBaseURL
  }

  private func ollamaChatURL(from baseURL: String?) throws -> URL {
    do {
      return try OllamaEndpointPolicy.apiURL(baseURL: baseURL, endpoint: "chat")
    } catch OllamaEndpointPolicyError.invalidBaseURL(let raw) {
      throw CloudAIError.invalidBaseURL(raw)
    } catch OllamaEndpointPolicyError.unsafeEndpoint(let raw) {
      throw CloudAIError.unsafeOllamaEndpoint(raw)
    } catch {
      throw CloudAIError.invalidBaseURL(baseURL ?? "http://localhost:11434")
    }
  }

  private func attachmentInputSummary(for inputPaths: [String], mode: CloudAttachmentContextMode) -> String {
    guard !inputPaths.isEmpty else { return "(none)" }
    switch mode {
    case .previews:
      return inputPaths.map { CloudPrivacySanitizer.filename(for: $0) }.joined(separator: "\n")
    case .filenamesOnly:
      return inputPaths.map { CloudPrivacySanitizer.filename(for: $0) }.joined(separator: "\n")
    case .none:
      return "(withheld by privacy setting; \(inputPaths.count) attachment\(inputPaths.count == 1 ? "" : "s") selected)"
    }
  }

  private func attachmentContext(for inputPaths: [String], mode: CloudAttachmentContextMode) -> String {
    guard !inputPaths.isEmpty else { return "(none)" }
    switch mode {
    case .previews:
      break
    case .filenamesOnly:
      return inputPaths.map { path in
        var isDirectory: ObjCBool = false
        if FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory), isDirectory.boolValue {
          return "\(CloudPrivacySanitizer.filename(for: path))\n  folder name only; contents withheld by privacy setting"
        }
        return "\(CloudPrivacySanitizer.filename(for: path))\n  file name only; preview withheld by privacy setting"
      }.joined(separator: "\n\n---\n\n")
    case .none:
      return "(withheld by privacy setting)"
    }

    return inputPaths.map { path in
      let url = URL(fileURLWithPath: path)
      let displayName = CloudPrivacySanitizer.filename(for: path)
      var isDirectory: ObjCBool = false
      guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) else {
        return "\(displayName)\n  missing"
      }

      if isDirectory.boolValue {
        let children = ((try? FileManager.default.contentsOfDirectory(atPath: path)) ?? [])
          .sorted()
          .prefix(40)
          .joined(separator: "\n  - ")
        return """
        \(displayName)
          directory preview:
          - \(children.isEmpty ? "(empty)" : children)
        """
      }

      let attributes = (try? FileManager.default.attributesOfItem(atPath: path)) ?? [:]
      let byteCount = attributes[.size] as? Int64 ?? 0
      let textExtensions: Set<String> = ["txt", "md", "csv", "tsv", "json", "jsonl", "yaml", "yml", "tex", "py", "swift", "ipynb", "log", "dat"]
      let ext = url.pathExtension.localizedLowercase
      guard textExtensions.contains(ext) else {
        return "\(displayName)\n  binary or rich file, \(ByteCountFormatter.string(fromByteCount: byteCount, countStyle: .file))"
      }

      guard let data = try? Data(contentsOf: url, options: [.mappedIfSafe]) else {
        return "\(displayName)\n  could not read preview"
      }
      let previewData = data.prefix(16_000)
      let preview = CloudPrivacySanitizer.withholdingAbsolutePaths(
        in: String(data: previewData, encoding: .utf8) ?? "(not valid UTF-8 preview)"
      )
      return """
      \(displayName)
        text preview, \(ByteCountFormatter.string(fromByteCount: byteCount, countStyle: .file)):
      \(preview)
      """
    }.joined(separator: "\n\n---\n\n")
  }

  private func privacyFilteredRecoveryContext(
    _ context: String?,
    mode: CloudAttachmentContextMode
  ) -> String {
    guard let context, !context.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return "(none)"
    }

    switch mode {
    case .previews:
      return CloudPrivacySanitizer.withholdingAbsolutePaths(in: context)
    case .filenamesOnly:
      let allowedPrefixes = [
        "Workflow recovery state:",
        "- Completed enabled steps:",
        "- Resume step index:",
        "- Can use Run Remaining:",
        "- Stopped status:",
        "- Resume capability:",
        "- Stopped job:",
        "- Exit code:",
        "- Run folder name:",
        "- Latest workflow summary filename:"
      ]
      let safeLines = context
        .split(separator: "\n", omittingEmptySubsequences: false)
        .map(String.init)
        .filter { line in allowedPrefixes.contains(where: { line.hasPrefix($0) }) }
        .map(CloudPrivacySanitizer.withholdingAbsolutePaths)
      return safeLines.isEmpty
        ? "(workflow recovery content withheld by filenames-only privacy setting)"
        : safeLines.joined(separator: "\n")
    case .none:
      let allowedPrefixes = [
        "Workflow recovery state:",
        "- Completed enabled steps:",
        "- Resume step index:",
        "- Can use Run Remaining:",
        "- Stopped status:"
      ]
      let safeLines = context
        .split(separator: "\n", omittingEmptySubsequences: false)
        .map(String.init)
        .filter { line in allowedPrefixes.contains(where: { line.hasPrefix($0) }) }
        .map(CloudPrivacySanitizer.withholdingAbsolutePaths)
      return safeLines.isEmpty
        ? "(workflow recovery content withheld by privacy setting)"
        : safeLines.joined(separator: "\n")
    }
  }
}

enum CloudAIError: LocalizedError {
  case requestFailed(String)
  case invalidKey(String)
  case quotaOrRateLimit(String)
  case modelUnavailable(String)
  case networkUnavailable(String)
  case timedOut(String)
  case serverUnavailable(Int, String)
  case invalidResponse
  case invalidJSON(String)
  case emptyPlan
  case unexpectedTestResponse(String)
  case invalidBaseURL(String)
  case unsafeOllamaEndpoint(String)

  var errorDescription: String? {
    switch self {
    case .requestFailed(let message):
      return "AI provider request failed: \(message)"
    case .invalidKey(let message):
      return "AI provider rejected the credentials: \(message)"
    case .quotaOrRateLimit(let message):
      return "AI provider quota or rate limit was reached: \(message)"
    case .modelUnavailable(let message):
      return "AI model is unavailable: \(message)"
    case .networkUnavailable(let message):
      return "AI provider is unreachable: \(message)"
    case .timedOut(let message):
      return "AI provider request timed out: \(message)"
    case .serverUnavailable(let statusCode, let message):
      return "AI provider service is unavailable (\(statusCode)): \(message)"
    case .invalidResponse:
      return "AI provider returned a response without readable text."
    case .invalidJSON(let text):
      return "AI provider returned text that could not be parsed as JSON: \(text)"
    case .emptyPlan:
      return "AI provider returned a plan with no runnable steps."
    case .unexpectedTestResponse(let text):
      return "AI provider connection test returned unexpected text: \(text)"
    case .invalidBaseURL(let url):
      return "AI provider base URL is invalid: \(url)"
    case .unsafeOllamaEndpoint(let url):
      return "Ollama is restricted to an HTTP(S) loopback endpoint (localhost, 127.0.0.0/8, or ::1). Remote and non-HTTP endpoints are rejected: \(url)"
    }
  }

  var connectionState: AIConnectionState {
    switch self {
    case .invalidKey:
      return .invalidKey
    case .quotaOrRateLimit:
      return .quotaOrRateLimit
    case .modelUnavailable:
      return .modelUnavailable
    case .networkUnavailable:
      return .networkIssue
    case .timedOut:
      return .timedOut
    case .serverUnavailable:
      return .networkIssue
    case .requestFailed, .invalidResponse, .invalidJSON, .emptyPlan, .unexpectedTestResponse,
         .invalidBaseURL, .unsafeOllamaEndpoint:
      return .failed
    }
  }

  static func transport(_ error: URLError) -> CloudAIError {
    switch error.code {
    case .timedOut:
      return .timedOut(error.localizedDescription)
    case .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed, .internationalRoamingOff,
         .networkConnectionLost, .notConnectedToInternet, .secureConnectionFailed:
      return .networkUnavailable(error.localizedDescription)
    default:
      return .networkUnavailable(error.localizedDescription)
    }
  }

  static func httpFailure(statusCode: Int, data: Data) -> CloudAIError {
    let message = providerErrorMessage(from: data)
    let lower = message.localizedLowercase

    if statusCode == 408 || statusCode == 504 || lower.contains("timed out") || lower.contains("timeout") {
      return .timedOut(message)
    }

    if isModelUnavailable(statusCode: statusCode, message: lower) {
      return .modelUnavailable(message)
    }

    if statusCode == 402 || statusCode == 429 || isQuotaOrRateLimit(message: lower) {
      return .quotaOrRateLimit(message)
    }

    if statusCode == 401 || statusCode == 403 || isInvalidCredential(message: lower) {
      return .invalidKey(message)
    }

    if (500...599).contains(statusCode) {
      return .serverUnavailable(statusCode, message)
    }

    if statusCode > 0 {
      return .requestFailed("HTTP \(statusCode): \(message)")
    }

    return .requestFailed(message)
  }

  private static func providerErrorMessage(from data: Data) -> String {
    let fallback = String(data: data, encoding: .utf8) ?? "No response body."
    guard !data.isEmpty else {
      return clipped(fallback)
    }

    // Provider error bodies are intentionally parsed as arbitrary JSON: OpenAI,
    // xAI, Gemini, and local gateways use different nested error schemas.
    if let payload = try? JSONDecoder().decode(ProviderErrorPayload.self, from: data),
       let message = payload.message {
      return clipped(message)
    }
    return clipped(fallback)
  }

  private static func clipped(_ message: String) -> String {
    let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.count > 1_200 else { return trimmed.isEmpty ? "No response body." : trimmed }
    let index = trimmed.index(trimmed.startIndex, offsetBy: 1_200)
    return "\(trimmed[..<index])..."
  }

  private static func isInvalidCredential(message: String) -> Bool {
    message.contains("invalid api key") ||
      message.contains("api key not valid") ||
      message.contains("incorrect api key") ||
      message.contains("unauthorized") ||
      message.contains("permission_denied") ||
      message.contains("invalid authentication")
  }

  private static func isQuotaOrRateLimit(message: String) -> Bool {
    message.contains("insufficient_quota") ||
      message.contains("quota") ||
      message.contains("rate limit") ||
      message.contains("rate_limit") ||
      message.contains("billing") ||
      message.contains("resource_exhausted")
  }

  private static func isModelUnavailable(statusCode: Int, message: String) -> Bool {
    statusCode == 404 ||
      message.contains("model_not_found") ||
      message.contains("model not found") ||
      message.contains("model_not_available") ||
      (message.contains("model") && message.contains("not found")) ||
      (message.contains("model") && message.contains("does not exist")) ||
      (message.contains("model") && message.contains("not available"))
  }
}
