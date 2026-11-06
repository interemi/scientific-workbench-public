import Foundation

struct WorkflowExecutionIdentity {
  let id = UUID()
  let planID: UUID
  var jobIDs: Set<UUID> = []
}
