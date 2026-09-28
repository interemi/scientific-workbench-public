import Foundation

struct AgentStateSnapshot: Sendable {
  var agentPlan: AgentPlan?
  var stepExecutions: [AgentPlanStepExecution]
  var lastWorkflowSummaryPath: String?
  var agentStatusMessage: String
}

struct AgentStateLoadResult: Sendable {
  var snapshot: AgentStateSnapshot
  var diagnostics: PersistenceLoadDiagnostics
}

struct AgentStateStore {
  static let currentVersion = 2

  func load(from url: URL) throws -> AgentStateSnapshot? {
    try loadRecovering(from: url)?.snapshot
  }

  func loadRecovering(from url: URL) throws -> AgentStateLoadResult? {
    guard let data = try PersistenceFileAccess.readData(from: url) else { return nil }
    let object = try PersistenceFileAccess.jsonObject(from: data, kind: "agent state")
    let version = try PersistenceFileAccess.schemaVersion(
      in: object,
      kind: "agent state",
      currentVersion: Self.currentVersion
    )
    var diagnostics = PersistenceLoadDiagnostics(
      kind: "agent state",
      sourceVersion: version,
      currentVersion: Self.currentVersion,
      recoveredItemCount: 0,
      discardedItemCount: 0,
      duplicateIdentifierCount: 0,
      normalizedInterruptedCount: 0,
      messages: []
    )

    var plan: AgentPlan?
    if let rawPlan = object["agentPlan"], !(rawPlan is NSNull) {
      do {
        let decoded = try PersistenceFileAccess.decode(AgentPlan.self, from: rawPlan)
        let normalized = Self.deduplicatedPlan(decoded)
        plan = normalized.plan
        diagnostics.duplicateIdentifierCount += normalized.removed
      } catch {
        diagnostics.discardedItemCount += 1
        diagnostics.messages.append("The active agent plan could not be decoded.")
      }
    }

    var decodedExecutions: [AgentPlanStepExecution] = []
    if let rawExecutions = object["stepExecutions"] as? [Any] {
      for (offset, rawExecution) in rawExecutions.enumerated() {
        do {
          decodedExecutions.append(
            try PersistenceFileAccess.decode(AgentPlanStepExecution.self, from: rawExecution)
          )
        } catch {
          diagnostics.discardedItemCount += 1
          diagnostics.messages.append("Step execution \(offset + 1) could not be decoded.")
        }
      }
    } else {
      diagnostics.discardedItemCount += 1
      diagnostics.messages.append("The agent state had no readable step execution collection.")
    }

    let executionRecovery = Self.deduplicatedExecutions(
      decodedExecutions,
      for: plan,
      normalizeInterrupted: true
    )
    diagnostics.duplicateIdentifierCount += executionRecovery.removedDuplicates
    diagnostics.discardedItemCount += executionRecovery.discarded
    diagnostics.normalizedInterruptedCount += executionRecovery.normalizedInterrupted
    diagnostics.messages += executionRecovery.messages
    diagnostics.recoveredItemCount = executionRecovery.executions.count + (plan == nil ? 0 : 1)

    let lastWorkflowSummaryPath = object["lastWorkflowSummaryPath"] as? String
    let agentStatusMessage = object["agentStatusMessage"] as? String
      ?? "Recovered persisted workflow state. Review it before resuming."
    return AgentStateLoadResult(
      snapshot: AgentStateSnapshot(
        agentPlan: plan,
        stepExecutions: executionRecovery.executions,
        lastWorkflowSummaryPath: lastWorkflowSummaryPath,
        agentStatusMessage: agentStatusMessage
      ),
      diagnostics: diagnostics
    )
  }

  func persist(snapshot: AgentStateSnapshot, to url: URL) throws {
    try PersistenceFileAccess.validateWriteTarget(url)
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    let normalizedPlan = snapshot.agentPlan.map(Self.deduplicatedPlan)?.plan
    let normalizedExecutions = Self.deduplicatedExecutions(
      snapshot.stepExecutions,
      for: normalizedPlan,
      normalizeInterrupted: false
    ).executions
    let payload = AgentStatePayload(
      version: Self.currentVersion,
      generatedAt: Date(),
      agentPlan: normalizedPlan,
      stepExecutions: normalizedExecutions,
      lastWorkflowSummaryPath: snapshot.lastWorkflowSummaryPath,
      agentStatusMessage: snapshot.agentStatusMessage
    )
    let data = try JSONEncoder.scientificWorkbench.encode(payload)
    try data.write(to: url, options: [.atomic])
  }

  private static func deduplicatedPlan(_ source: AgentPlan) -> (plan: AgentPlan, removed: Int) {
    var plan = source
    var seen: Set<AgentPlanStep.ID> = []
    var removed = 0
    plan.steps = source.steps.filter { step in
      let inserted = seen.insert(step.id).inserted
      if !inserted { removed += 1 }
      return inserted
    }
    return (plan, removed)
  }

  private static func deduplicatedExecutions(
    _ source: [AgentPlanStepExecution],
    for plan: AgentPlan?,
    normalizeInterrupted: Bool
  ) -> (
    executions: [AgentPlanStepExecution],
    removedDuplicates: Int,
    discarded: Int,
    normalizedInterrupted: Int,
    messages: [String]
  ) {
    guard let plan else {
      return (
        [],
        0,
        source.count,
        0,
        source.isEmpty ? [] : ["Step executions without a readable active plan were discarded."]
      )
    }
    let stepsByID = Dictionary(uniqueKeysWithValues: plan.steps.map { ($0.id, $0) })
    var retained: [AgentPlanStepExecution] = []
    var indexesByStepID: [AgentPlanStep.ID: Int] = [:]
    var executionIDs: Set<AgentPlanStepExecution.ID> = []
    var removedDuplicates = 0
    var discarded = 0
    var normalizedInterruptedCount = 0
    var messages: [String] = []

    for rawExecution in source {
      guard let step = stepsByID[rawExecution.stepID] else {
        discarded += 1
        messages.append("An execution for a missing plan step was discarded.")
        continue
      }
      guard step.capabilityID == rawExecution.capabilityID else {
        discarded += 1
        messages.append("An execution whose capability did not match its plan step was discarded.")
        continue
      }

      var execution = rawExecution
      if normalizeInterrupted, execution.status == .queued || execution.status == .running {
        execution.status = .cancelled
        execution.finishedAt = execution.finishedAt ?? Date()
        normalizedInterruptedCount += 1
      }

      if let existingIndex = indexesByStepID[execution.stepID] {
        removedDuplicates += 1
        let existing = retained[existingIndex]
        if preferred(execution, over: existing) {
          if execution.id != existing.id, executionIDs.contains(execution.id) {
            continue
          }
          executionIDs.remove(existing.id)
          executionIDs.insert(execution.id)
          retained[existingIndex] = execution
        }
        continue
      }
      guard executionIDs.insert(execution.id).inserted else {
        removedDuplicates += 1
        continue
      }
      indexesByStepID[execution.stepID] = retained.count
      retained.append(execution)
    }

    return (
      retained,
      removedDuplicates,
      discarded,
      normalizedInterruptedCount,
      messages
    )
  }

  private static func preferred(
    _ candidate: AgentPlanStepExecution,
    over existing: AgentPlanStepExecution
  ) -> Bool {
    let candidateDate = candidate.finishedAt ?? .distantPast
    let existingDate = existing.finishedAt ?? .distantPast
    if candidateDate != existingDate { return candidateDate > existingDate }
    let candidateRank = conservativeStatusRank(candidate.status)
    let existingRank = conservativeStatusRank(existing.status)
    if candidateRank != existingRank { return candidateRank > existingRank }
    return candidate.id.uuidString < existing.id.uuidString
  }

  private static func conservativeStatusRank(_ status: JobStatus) -> Int {
    switch status {
    case .failed, .blocked, .timedOut: return 4
    case .cancelled: return 3
    case .running, .queued: return 2
    case .succeeded: return 1
    }
  }
}

private struct AgentStatePayload: Codable {
  var version: Int
  var generatedAt: Date
  var agentPlan: AgentPlan?
  var stepExecutions: [AgentPlanStepExecution]
  var lastWorkflowSummaryPath: String?
  var agentStatusMessage: String
}
