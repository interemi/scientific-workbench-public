enum WorkflowJourneyStage: String, CaseIterable, Identifiable {
  case inputs
  case review
  case plan
  case run
  case results

  var id: String { rawValue }

  var title: String {
    switch self {
    case .inputs: return "Inputs"
    case .review: return "Preflight & Scope"
    case .plan: return "Plan"
    case .run: return "Run & Logs"
    case .results: return "Results"
    }
  }

  var section: AppSection {
    switch self {
    case .inputs: return .home
    case .review: return .capabilities
    case .plan: return .agent
    case .run: return .jobs
    case .results: return .results
    }
  }

  var previous: WorkflowJourneyStage? {
    guard let index = Self.allCases.firstIndex(of: self), index > 0 else { return nil }
    return Self.allCases[index - 1]
  }

  static func forSection(_ section: AppSection?) -> WorkflowJourneyStage? {
    Self.allCases.first { $0.section == (section ?? .agent) }
  }
}
