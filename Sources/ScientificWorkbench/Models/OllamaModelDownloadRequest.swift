import Foundation

struct OllamaModelDownloadRequest: Identifiable, Equatable, Sendable {
  let id = UUID()
  let model: String
  let baseURL: String

  init(model: String, baseURL: String?) throws {
    let model = model.trimmingCharacters(in: .whitespacesAndNewlines)
    guard model.range(of: #"^[A-Za-z0-9][A-Za-z0-9._:/-]*$"#, options: .regularExpression) != nil else {
      throw OllamaSetupError.invalidModel
    }
    self.model = model
    do {
      self.baseURL = try OllamaEndpointPolicy.commandBaseURL(baseURL: baseURL)
    } catch OllamaEndpointPolicyError.invalidBaseURL(let raw) {
      throw OllamaSetupError.invalidBaseURL(raw)
    } catch OllamaEndpointPolicyError.unsafeEndpoint(let raw) {
      throw OllamaSetupError.unsafeEndpoint(raw)
    }
  }

  var reviewDetail: String {
    let profile = OllamaModelProfile.matching(model: model)
    let size = profile?.diskEstimate ?? "size unknown for this custom model"
    return """
    Model: \(model)
    Local server: \(baseURL)
    Model file estimate: \(size); extra disk space and runtime RAM are needed.
    Ollama will fetch model data over the network and store it in its model directory. No scientific inputs or chat messages are part of this download request.
    Deterministic planning and Core workflows remain available without downloading a model.
    """
  }
}
