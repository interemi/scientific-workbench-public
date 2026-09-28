import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func cloudAIClientBuildsOllamaChatRequestWithoutAPIKey() async throws {
    let recorder = RequestRecorder(
      responseBody: #"{"message":{"role":"assistant","content":"ollama-ok"},"done":true}"#
    )
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    let text = try await client.generateText(
      provider: AIProvider.ollama,
      apiKey: "",
      model: "llama-test",
      baseURL: "http://localhost:11434",
      system: "System",
      user: "Hello",
      temperature: 0.3,
      maxOutputTokens: 10
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let canonicalBody = try canonicalJSONBody(from: request)
    let messages = try #require(body["messages"] as? [[String: String]])
    let options = try #require(body["options"] as? [String: Any])
    #expect(text == "ollama-ok")
    #expect(request.url?.absoluteString == "http://localhost:11434/api/chat")
    #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
    #expect(request.timeoutInterval == 60)
    #expect(body["model"] as? String == "llama-test")
    #expect(body["stream"] as? Bool == false)
    #expect(messages.map { $0["role"] } == ["system", "user"])
    #expect(options["num_predict"] as? Int == 10)
    #expect(canonicalBody == #"{"messages":[{"content":"System","role":"system"},{"content":"Hello","role":"user"}],"model":"llama-test","options":{"num_predict":10,"temperature":0.3},"stream":false}"#)
  }

  @Test
  func cloudAIClientIncludesWorkflowRecoveryContextInChatRequest() async throws {
    let recorder = RequestRecorder(
      responseBody: #"{"message":{"role":"assistant","content":"recovery-ok"},"done":true}"#
    )
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    let text = try await client.respond(
      prompt: "Que hago ahora?",
      history: [AgentChatMessage(role: .assistant, text: "Workflow stopped.")],
      inputPaths: ["/tmp/input"],
      workflowRecoveryContext: "Workflow recovery state:\n- Resume capability: profile_table\n- Stopped status: Blocked",
      provider: .ollama,
      apiKey: "",
      model: "llama-test",
      baseURL: "http://localhost:11434"
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let messages = try #require(body["messages"] as? [[String: String]])
    let system = try #require(messages.first { $0["role"] == "system" }?["content"])
    let user = try #require(messages.first { $0["role"] == "user" }?["content"])
    #expect(text == "recovery-ok")
    #expect(system.contains("workflow recovery context"))
    #expect(user.contains("Workflow recovery state"))
    #expect(user.contains("Resume capability: profile_table"))
    #expect(user.contains("Stopped status: Blocked"))
  }

  @Test
  func cloudAIConnectionTestAcceptsAnyNonEmptyOllamaText() async throws {
    let recorder = RequestRecorder(
      responseBody: #"{"message":{"role":"assistant","content":"<think>checking</think>\nListo, el modelo responde."},"done":true}"#
    )
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    let text = try await client.testConnection(
      provider: .ollama,
      apiKey: "",
      model: "qwen3:1.7b",
      baseURL: "http://localhost:11434"
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let options = try #require(body["options"] as? [String: Any])
    #expect(text.contains("modelo responde"))
    #expect(request.url?.absoluteString == "http://localhost:11434/api/chat")
    #expect(body["model"] as? String == "qwen3:1.7b")
    #expect(options["num_predict"] as? Int == 128)
  }

  @Test
  func cloudAIClientBuildsOpenAIResponsesRequest() async throws {
    let recorder = RequestRecorder(responseBody: #"{"output_text":"openai-ok"}"#)
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    let text = try await client.generateText(
      provider: AIProvider.openAI,
      apiKey: "sk-test-secret",
      model: "gpt-test",
      system: "System",
      user: "Hello",
      temperature: 0,
      maxOutputTokens: 12
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let canonicalBody = try canonicalJSONBody(from: request)
    #expect(text == "openai-ok")
    #expect(request.url?.absoluteString == "https://api.openai.com/v1/responses")
    #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer sk-test-secret")
    #expect(body["model"] as? String == "gpt-test")
    #expect(body["instructions"] as? String == "System")
    #expect(body["input"] as? String == "Hello")
    #expect(body["max_output_tokens"] as? Int == 12)
    #expect(canonicalBody == #"{"input":"Hello","instructions":"System","max_output_tokens":12,"model":"gpt-test","temperature":0}"#)
  }

  @Test
  func cloudAIClientParsesNestedOpenAIResponsesOutputContent() async throws {
    let recorder = RequestRecorder(
      responseBody: #"{"output":[{"content":[{"type":"output_text","text":"openai-nested-ok"}]}]}"#
    )
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    let text = try await client.generateText(
      provider: AIProvider.openAI,
      apiKey: "sk-test-secret",
      model: "gpt-test",
      system: "System",
      user: "Hello"
    )

    #expect(text == "openai-nested-ok")
  }

  @Test
  func cloudAIClientBuildsGrokChatCompletionsRequest() async throws {
    let recorder = RequestRecorder(responseBody: #"{"choices":[{"message":{"content":"grok-ok"}}]}"#)
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    let text = try await client.generateText(
      provider: AIProvider.grok,
      apiKey: "xai-test-secret",
      model: "grok-test",
      system: "System",
      user: "Hello",
      temperature: 0.1,
      maxOutputTokens: 8
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let canonicalBody = try canonicalJSONBody(from: request)
    let messages = try #require(body["messages"] as? [[String: String]])
    #expect(text == "grok-ok")
    #expect(request.url?.absoluteString == "https://api.x.ai/v1/chat/completions")
    #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer xai-test-secret")
    #expect(body["model"] as? String == "grok-test")
    #expect(body["max_tokens"] as? Int == 8)
    #expect(messages.map { $0["role"] } == ["system", "user"])
    #expect(canonicalBody == #"{"max_tokens":8,"messages":[{"content":"System","role":"system"},{"content":"Hello","role":"user"}],"model":"grok-test","temperature":0.1}"#)
  }

  @Test
  func cloudAIClientBuildsGeminiGenerateContentRequest() async throws {
    let recorder = RequestRecorder(
      responseBody: #"{"candidates":[{"content":{"parts":[{"text":"gemini-ok"}]}}]}"#
    )
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    let text = try await client.generateText(
      provider: AIProvider.gemini,
      apiKey: "gemini-test-secret",
      model: "models/gemini-test",
      system: "System",
      user: "Hello",
      temperature: 0.2,
      maxOutputTokens: 6
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let canonicalBody = try canonicalJSONBody(from: request)
    let generationConfig = try #require(body["generationConfig"] as? [String: Any])
    #expect(text == "gemini-ok")
    #expect(request.url?.absoluteString == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent")
    #expect(request.url?.query == nil)
    #expect(request.value(forHTTPHeaderField: "x-goog-api-key") == "gemini-test-secret")
    #expect(generationConfig["maxOutputTokens"] as? Int == 6)
    #expect(canonicalBody == #"{"contents":[{"parts":[{"text":"Hello"}],"role":"user"}],"generationConfig":{"maxOutputTokens":6,"temperature":0.2},"systemInstruction":{"parts":[{"text":"System"}]}}"#)
  }

  @Test
  func cloudAIClientTestsFreshGeminiDefaultWithoutLegacySamplingSettings() async throws {
    let recorder = RequestRecorder(
      responseBody: #"{"candidates":[{"content":{"parts":[{"text":"Scientific Workbench AI connection OK"}]}}]}"#
    )
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    let reply = try await client.testConnection(
      provider: .gemini,
      apiKey: "gemini-test-secret",
      model: AIProvider.gemini.defaultModel
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let generationConfig = try #require(body["generationConfig"] as? [String: Any])
    #expect(reply == "Scientific Workbench AI connection OK")
    #expect(request.url?.absoluteString == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent")
    #expect(request.url?.query == nil)
    #expect(request.value(forHTTPHeaderField: "x-goog-api-key") == "gemini-test-secret")
    #expect(generationConfig["temperature"] == nil)
    #expect(generationConfig["maxOutputTokens"] as? Int == 512)
  }

  @Test
  func cloudAIClientRejectsInvalidResponseShapesForAllProviders() async throws {
    let scenarios: [(provider: AIProvider, body: String, apiKey: String, model: String)] = [
      (.ollama, #"{"message":{"role":"assistant"},"done":true}"#, "", "qwen3:4b-instruct"),
      (.openAI, #"{"output":[{"content":[{"type":"output_text"}]}]}"#, "sk-test", "gpt-test"),
      (.grok, #"{"choices":[{"message":{}}]}"#, "xai-test", "grok-test"),
      (.gemini, #"{"candidates":[{"content":{"parts":[{}]}}]}"#, "gemini-test", "gemini-test")
    ]

    for scenario in scenarios {
      let recorder = RequestRecorder(responseBody: scenario.body)
      let client = CloudAIClient(dataLoader: { request in
        try await recorder.load(request)
      })

      do {
        _ = try await client.generateText(
          provider: scenario.provider,
          apiKey: scenario.apiKey,
          model: scenario.model,
          baseURL: scenario.provider == .ollama ? "http://localhost:11434" : nil,
          system: "System",
          user: "Hello"
        )
        Issue.record("Expected invalid response for \(scenario.provider.title).")
      } catch CloudAIError.invalidResponse {
        // Expected.
      } catch {
        Issue.record("Unexpected error for \(scenario.provider.title): \(error)")
      }
    }
  }

  @Test
  func cloudAIClientAttachmentContextPreviewsIncludesReadableText() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Cloud-Attachments-\(UUID().uuidString)", isDirectory: true)
    let file = root.appendingPathComponent("notes.txt")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try "PRIVATE_PREVIEW_TEXT\nsource=/Users/researcher/private/raw.csv\nInput: `/Users/researcher/private/markdown.csv`".write(
      to: file,
      atomically: true,
      encoding: .utf8
    )
    defer { try? FileManager.default.removeItem(at: root) }

    let recorder = RequestRecorder(responseBody: #"{"output_text":"ok"}"#)
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    _ = try await client.respond(
      prompt: "Analyze attached notes.",
      history: [],
      inputPaths: [file.path],
      attachmentContextMode: .previews,
      provider: .openAI,
      apiKey: "sk-test",
      model: "gpt-test"
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let user = try #require(body["input"] as? String)
    #expect(user.contains("notes.txt"))
    #expect(user.contains("text preview"))
    #expect(user.contains("PRIVATE_PREVIEW_TEXT"))
    #expect(user.contains("[local path withheld]"))
    #expect(!user.contains(root.path))
    #expect(!user.contains(file.path))
    #expect(!user.contains("/Users/researcher/private/raw.csv"))
    #expect(!user.contains("/Users/researcher/private/markdown.csv"))
  }

  @Test
  func cloudAIClientAttachmentContextFilenamesOnlyWithholdsFileContentsAndFullPaths() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Cloud-Attachments-\(UUID().uuidString)", isDirectory: true)
    let file = root.appendingPathComponent("notes.txt")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try "PRIVATE_PREVIEW_TEXT".write(to: file, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: root) }

    let recorder = RequestRecorder(responseBody: #"{"output_text":"ok"}"#)
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    _ = try await client.respond(
      prompt: "Analyze attached notes.",
      history: [],
      inputPaths: [file.path],
      attachmentContextMode: .filenamesOnly,
      provider: .openAI,
      apiKey: "sk-test",
      model: "gpt-test"
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let user = try #require(body["input"] as? String)
    #expect(user.contains("notes.txt"))
    #expect(user.contains("preview withheld"))
    #expect(!user.contains(root.path))
    #expect(!user.contains(file.path))
    #expect(!user.contains("PRIVATE_PREVIEW_TEXT"))
  }

  @Test
  func cloudAIClientAttachmentContextNoneWithholdsNamesPathsAndContents() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Cloud-Attachments-\(UUID().uuidString)", isDirectory: true)
    let file = root.appendingPathComponent("notes.txt")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try "PRIVATE_PREVIEW_TEXT".write(to: file, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: root) }

    let recorder = RequestRecorder(responseBody: #"{"output_text":"ok"}"#)
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    _ = try await client.respond(
      prompt: "Analyze attached notes.",
      history: [],
      inputPaths: [file.path],
      attachmentContextMode: .none,
      provider: .openAI,
      apiKey: "sk-test",
      model: "gpt-test"
    )

    let request = try #require(await recorder.requests.first)
    let body = try jsonBody(from: request)
    let user = try #require(body["input"] as? String)
    #expect(user.contains("withheld by privacy setting"))
    #expect(user.contains("1 attachment selected"))
    #expect(!user.contains("notes.txt"))
    #expect(!user.contains(root.path))
    #expect(!user.contains(file.path))
    #expect(!user.contains("PRIVATE_PREVIEW_TEXT"))
  }

  @Test
  func cloudAIClientEnforcesRecoveryPrivacyModeAtPayloadBoundary() async throws {
    let recoveryContext = """
    Workflow recovery state:
    - Completed enabled steps: 1/3
    - Resume step index: 2
    - Can use Run Remaining: yes
    - Stopped status: Failed
    - Resume capability: private_capability
    - Stopped job: private-job
    - Exit code: 2
    - Run folder name: private-run
    - Latest workflow summary filename: private-summary.md
    - Resume step summary: PRIVATE_RECOVERY_CONTENT
    - Job message: PRIVATE_JOB_MESSAGE
    - stderr excerpt: PRIVATE_LOG at /Users/researcher/private/trace.log
    """

    for mode in CloudAttachmentContextMode.allCases {
      let recorder = RequestRecorder(responseBody: #"{"output_text":"ok"}"#)
      let client = CloudAIClient(dataLoader: recorder.load)

      _ = try await client.respond(
        prompt: "What should I do next?",
        history: [],
        inputPaths: [],
        workflowRecoveryContext: recoveryContext,
        attachmentContextMode: mode,
        provider: .openAI,
        apiKey: "sk-test",
        model: "gpt-test"
      )

      let request = try #require(await recorder.requests.first)
      let body = try jsonBody(from: request)
      let user = try #require(body["input"] as? String)
      #expect(user.contains("Completed enabled steps: 1/3"))
      #expect(user.contains("Stopped status: Failed"))
      #expect(!user.contains("/Users/researcher/private/trace.log"))

      switch mode {
      case .previews:
        #expect(user.contains("private_capability"))
        #expect(user.contains("PRIVATE_RECOVERY_CONTENT"))
        #expect(user.contains("PRIVATE_JOB_MESSAGE"))
        #expect(user.contains("PRIVATE_LOG at[local path withheld]"))
      case .filenamesOnly:
        #expect(user.contains("private_capability"))
        #expect(user.contains("private-run"))
        #expect(user.contains("private-summary.md"))
        #expect(!user.contains("PRIVATE_RECOVERY_CONTENT"))
        #expect(!user.contains("PRIVATE_JOB_MESSAGE"))
        #expect(!user.contains("PRIVATE_LOG"))
      case .none:
        #expect(!user.contains("private_capability"))
        #expect(!user.contains("private-job"))
        #expect(!user.contains("private-run"))
        #expect(!user.contains("private-summary.md"))
        #expect(!user.contains("PRIVATE_RECOVERY_CONTENT"))
        #expect(!user.contains("PRIVATE_JOB_MESSAGE"))
        #expect(!user.contains("PRIVATE_LOG"))
      }
    }
  }

  @Test
  func cloudAIConnectionTestRejectsUnexpectedProviderText() async throws {
    let recorder = RequestRecorder(responseBody: #"{"output_text":"wrong text"}"#)
    let client = CloudAIClient(dataLoader: { request in
      try await recorder.load(request)
    })

    do {
      _ = try await client.testConnection(provider: AIProvider.openAI, apiKey: "sk-test", model: "gpt-test")
      Issue.record("Expected the connection test to reject unexpected text.")
    } catch CloudAIError.unexpectedTestResponse(let text) {
      #expect(text == "wrong text")
    } catch {
      Issue.record("Unexpected error: \(error)")
    }
  }

  @Test
  func cloudAIClientClassifiesProviderHTTPFailures() async throws {
    let scenarios: [(name: String, statusCode: Int, body: String, state: AIConnectionState, text: String)] = [
      (
        name: "invalid-key",
        statusCode: 401,
        body: #"{"error":{"message":"Incorrect API key provided.","type":"invalid_request_error","code":"invalid_api_key"}}"#,
        state: .invalidKey,
        text: "credentials"
      ),
      (
        name: "quota",
        statusCode: 429,
        body: #"{"error":{"message":"You exceeded your current quota.","type":"insufficient_quota","code":"insufficient_quota"}}"#,
        state: .quotaOrRateLimit,
        text: "quota"
      ),
      (
        name: "model-missing",
        statusCode: 404,
        body: #"{"error":{"message":"The model gpt-missing does not exist.","code":"model_not_found"}}"#,
        state: .modelUnavailable,
        text: "model"
      ),
      (
        name: "server",
        statusCode: 503,
        body: #"{"error":{"message":"Provider temporarily unavailable."}}"#,
        state: .networkIssue,
        text: "503"
      )
    ]

    for scenario in scenarios {
      let recorder = RequestRecorder(responseBody: scenario.body, statusCode: scenario.statusCode)
      let client = CloudAIClient(dataLoader: { request in
        try await recorder.load(request)
      })

      do {
        _ = try await client.generateText(
          provider: AIProvider.openAI,
          apiKey: "sk-test",
          model: "gpt-test",
          system: "System",
          user: "Hello"
        )
        Issue.record("Expected \(scenario.name) to throw.")
      } catch let error as CloudAIError {
        #expect(error.connectionState == scenario.state, "\(scenario.name) should map to \(scenario.state)")
        #expect(error.localizedDescription.localizedLowercase.contains(scenario.text))
      } catch {
        Issue.record("Unexpected error for \(scenario.name): \(error)")
      }
    }
  }

  @Test
  func cloudAIClientClassifiesProviderHTTPFailuresAcrossErrorSchemas() async throws {
    let scenarios: [(provider: AIProvider, statusCode: Int, body: String, state: AIConnectionState, text: String)] = [
      (
        provider: .gemini,
        statusCode: 400,
        body: #"{"error":{"code":400,"message":"API key not valid. Please pass a valid API key.","status":"INVALID_ARGUMENT"}}"#,
        state: .invalidKey,
        text: "credentials"
      ),
      (
        provider: .gemini,
        statusCode: 404,
        body: #"{"error":{"code":404,"message":"models/gemini-2.5-pro is not found for API version v1beta.","status":"NOT_FOUND"}}"#,
        state: .modelUnavailable,
        text: "model"
      ),
      (
        provider: .grok,
        statusCode: 429,
        body: #"{"errors":[{"detail":"rate_limit reached for this account"}]}"#,
        state: .quotaOrRateLimit,
        text: "quota"
      ),
      (
        provider: .ollama,
        statusCode: 504,
        body: "upstream timeout while waiting for local model",
        state: .timedOut,
        text: "timed out"
      )
    ]

    for scenario in scenarios {
      let recorder = RequestRecorder(responseBody: scenario.body, statusCode: scenario.statusCode)
      let client = CloudAIClient(dataLoader: { request in
        try await recorder.load(request)
      })

      do {
        _ = try await client.generateText(
          provider: scenario.provider,
          apiKey: "provider-test-key",
          model: scenario.provider.defaultModel,
          baseURL: scenario.provider == .ollama ? "http://localhost:11434" : nil,
          system: "System",
          user: "Hello"
        )
        Issue.record("Expected \(scenario.provider.title) HTTP failure to throw.")
      } catch let error as CloudAIError {
        #expect(error.connectionState == scenario.state)
        #expect(error.localizedDescription.localizedLowercase.contains(scenario.text))
      } catch {
        Issue.record("Unexpected error for \(scenario.provider.title): \(error)")
      }
    }
  }

  @Test
  func cloudAIClientClassifiesTransportFailures() async {
    let timeoutClient = CloudAIClient(dataLoader: { _ in
      throw URLError(.timedOut)
    })
    let offlineClient = CloudAIClient(dataLoader: { _ in
      throw URLError(.cannotConnectToHost)
    })

    do {
      _ = try await timeoutClient.testConnection(provider: .ollama, apiKey: "", model: "qwen3:4b-instruct")
      Issue.record("Expected timeout to throw.")
    } catch let error as CloudAIError {
      #expect(error.connectionState == .timedOut)
    } catch {
      Issue.record("Unexpected timeout error: \(error)")
    }

    do {
      _ = try await offlineClient.testConnection(provider: .ollama, apiKey: "", model: "qwen3:4b-instruct")
      Issue.record("Expected network failure to throw.")
    } catch let error as CloudAIError {
      #expect(error.connectionState == .networkIssue)
    } catch {
      Issue.record("Unexpected network error: \(error)")
    }
  }

}

extension ScientificWorkbenchTests {
  @Test
  func cloudAIClientAcceptsExplicitOllamaLoopbackEndpoints() async throws {
    let scenarios = [
      ("http://localhost:11434/", "http://localhost:11434/api/chat"),
      ("http://127.42.1.9:11434/api", "http://127.42.1.9:11434/api/chat"),
      ("http://[::1]:11434/api/chat/", "http://[::1]:11434/api/chat"),
    ]

    for (baseURL, expectedURL) in scenarios {
      let recorder = RequestRecorder(
        responseBody: #"{"message":{"role":"assistant","content":"local-ok"},"done":true}"#
      )
      let client = CloudAIClient(dataLoader: recorder.load)

      let text = try await client.generateText(
        provider: .ollama,
        apiKey: "",
        model: "qwen-test",
        baseURL: baseURL,
        system: "System",
        user: "Hello"
      )

      #expect(text == "local-ok")
      #expect(await recorder.requests.first?.url?.absoluteString == expectedURL)
    }
  }

  @Test
  func cloudAIClientRejectsRemoteAndNonHTTPOllamaEndpointsBeforeNetwork() async throws {
    let rejectedEndpoints = [
      "http://192.168.1.20:11434",
      "https://ollama.example/api",
      "ftp://localhost:11434",
      "file:///tmp/fake-ollama",
      "http://localhost.example:11434",
    ]

    for endpoint in rejectedEndpoints {
      let recorder = RequestRecorder(
        responseBody: #"{"message":{"role":"assistant","content":"unexpected"},"done":true}"#
      )
      let client = CloudAIClient(dataLoader: recorder.load)

      do {
        _ = try await client.generateText(
          provider: .ollama,
          apiKey: "",
          model: "qwen-test",
          baseURL: endpoint,
          system: "System",
          user: "Sensitive preview"
        )
        Issue.record("Expected Ollama endpoint to be rejected: \(endpoint)")
      } catch CloudAIError.unsafeOllamaEndpoint(let rejected) {
        #expect(rejected == endpoint)
      } catch {
        Issue.record("Unexpected Ollama endpoint error for \(endpoint): \(error)")
      }

      #expect(await recorder.requests.isEmpty)
    }
  }
}
