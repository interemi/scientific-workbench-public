import Foundation

struct WorkflowPlanningEvidence: Codable, Equatable, Sendable {
  enum Outcome: String, Codable, Sendable {
    case usedForPlan = "used_for_plan"
    case fellBack = "fell_back"
  }

  struct Consent: Codable, Equatable, Sendable {
    enum Scope: String, Codable, Sendable {
      case requestOnly = "request_only"
      case sessionGranted = "session_granted"
      case sessionReused = "session_reused"
    }

    let scope: Scope
    let attachmentContext: CloudAttachmentContextMode
    let categories: [CloudDataCategory]
  }

  let planID: UUID
  let provider: AIProvider
  let outcome: Outcome
  let requestedModel: String?
  let reportedModel: String?
  let consent: Consent?

  init(plan: AgentPlan, attempt: AgentPlanningResult.ModelAttempt, consent: Consent?, secrets: [String]) {
    self.init(
      planID: plan.id, provider: attempt.provider, outcome: attempt.outcome,
      requestedModel: attempt.requestedModel, reportedModel: attempt.reportedModel, consent: consent, secrets: secrets
    )
  }

  private init(
    planID: UUID, provider: AIProvider, outcome: Outcome, requestedModel: String?,
    reportedModel: String?, consent: Consent?, secrets: [String]
  ) {
    self.planID = planID
    self.provider = provider
    self.outcome = outcome
    self.requestedModel = Self.shareableModel(requestedModel, provider: provider, secrets: secrets)
    self.reportedModel = Self.shareableModel(reportedModel, provider: provider, secrets: secrets)
    self.consent = consent
  }

  func applies(to plan: AgentPlan) -> Bool {
    guard plan.id == planID else { return false }
    switch outcome {
    case .usedForPlan:
      return plan.source == AgentPlanSource(provider: provider)
    case .fellBack:
      return plan.source == .local || plan.source == .skillRouter
    }
  }

  func sanitized(secrets: [String]) -> Self {
    Self(
      planID: planID, provider: provider, outcome: outcome,
      requestedModel: requestedModel, reportedModel: reportedModel, consent: consent, secrets: secrets
    )
  }

  private static func shareableModel(_ raw: String?, provider: AIProvider, secrets: [String]) -> String? {
    guard let raw else { return nil }
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    let value = provider == .gemini && trimmed.hasPrefix("models/") ? String(trimmed.dropFirst(7)) : trimmed
    guard !value.isEmpty, value.utf8.count <= 80,
          !secrets.contains(where: { !$0.isEmpty && value.contains($0) }) else { return nil }
    if value == provider.defaultModel { return value }

    let pattern: String
    switch provider {
    case .ollama:
      return OllamaModelProfile.allCases.contains(where: { $0.model == value }) ? value : nil
    case .openAI:
      pattern = #"\A(?:gpt-[0-9](?:\.[0-9]{1,2}|o)?|o[0-9])(?:-(?:mini|nano|pro))?(?:-\d{4}-\d{2}-\d{2})?\z"#
    case .grok:
      pattern = #"\Agrok-[0-9](?:\.[0-9]{1,2})?(?:-(?:mini|fast|reasoning|non-reasoning|latest))*\z"#
    case .gemini:
      pattern = #"\Agemini-[0-9](?:\.[0-9]{1,2})?-(?:flash-lite|flash|pro)(?:-preview)?(?:-\d{2}-\d{2}|-\d{3})?\z"#
    }
    return value.range(of: pattern, options: .regularExpression) == nil ? nil : value
  }
}
