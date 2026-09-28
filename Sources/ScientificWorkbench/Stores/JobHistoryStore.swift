import Foundation

struct JobHistoryLoadResult: Sendable {
  var jobs: [JobRecord]
  var diagnostics: PersistenceLoadDiagnostics
}

struct JobHistoryStore {
  static let currentVersion = 2

  func load(from url: URL) throws -> [JobRecord]? {
    try loadRecovering(from: url)?.jobs
  }

  func loadRecovering(from url: URL) throws -> JobHistoryLoadResult? {
    guard let data = try PersistenceFileAccess.readData(from: url) else { return nil }
    let object = try PersistenceFileAccess.jsonObject(from: data, kind: "job history")
    let version = try PersistenceFileAccess.schemaVersion(
      in: object,
      kind: "job history",
      currentVersion: Self.currentVersion
    )
    guard let rawJobs = object["jobs"] as? [Any] else {
      throw PersistenceStoreError.missingCollection("job history")
    }

    var diagnostics = PersistenceLoadDiagnostics(
      kind: "job history",
      sourceVersion: version,
      currentVersion: Self.currentVersion,
      recoveredItemCount: 0,
      discardedItemCount: 0,
      duplicateIdentifierCount: 0,
      normalizedInterruptedCount: 0,
      messages: []
    )
    var jobs: [JobRecord] = []
    var indexesByID: [JobRecord.ID: Int] = [:]

    for (offset, rawJob) in rawJobs.enumerated() {
      do {
        var job = try PersistenceFileAccess.decode(JobRecord.self, from: rawJob)
        let normalization = Self.normalizedLoadedJob(job)
        job = normalization.job
        diagnostics.duplicateIdentifierCount += normalization.removedDuplicateIdentifiers
        diagnostics.normalizedInterruptedCount += normalization.normalizedInterrupted ? 1 : 0

        if let existingIndex = indexesByID[job.id] {
          diagnostics.duplicateIdentifierCount += 1
          if Self.evidenceDate(job) > Self.evidenceDate(jobs[existingIndex]) {
            jobs[existingIndex] = job
          }
        } else {
          indexesByID[job.id] = jobs.count
          jobs.append(job)
        }
      } catch {
        diagnostics.discardedItemCount += 1
        diagnostics.messages.append("Job record \(offset + 1) could not be decoded.")
      }
    }

    jobs.sort { $0.createdAt > $1.createdAt }
    diagnostics.recoveredItemCount = jobs.count
    return JobHistoryLoadResult(jobs: jobs, diagnostics: diagnostics)
  }

  func persist(jobs: [JobRecord], to url: URL) throws {
    try PersistenceFileAccess.validateWriteTarget(url)
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    let normalized = Self.uniqueJobs(jobs).prefix(250).map(\.job)
    let payload = JobHistoryPayload(
      version: Self.currentVersion,
      generatedAt: Date(),
      jobs: Array(normalized)
    )
    let data = try JSONEncoder.scientificWorkbench.encode(payload)
    try data.write(to: url, options: [.atomic])
  }

  private static func uniqueJobs(_ jobs: [JobRecord]) -> [(job: JobRecord, index: Int)] {
    var retained: [(job: JobRecord, index: Int)] = []
    var indexesByID: [JobRecord.ID: Int] = [:]
    for (index, rawJob) in jobs.enumerated() {
      let job = deduplicatedIdentifiers(in: rawJob).job
      if let retainedIndex = indexesByID[job.id] {
        if evidenceDate(job) > evidenceDate(retained[retainedIndex].job) {
          retained[retainedIndex] = (job, index)
        }
      } else {
        indexesByID[job.id] = retained.count
        retained.append((job, index))
      }
    }
    return retained.sorted { $0.index < $1.index }
  }

  private static func normalizedLoadedJob(
    _ source: JobRecord
  ) -> (job: JobRecord, removedDuplicateIdentifiers: Int, normalizedInterrupted: Bool) {
    let deduplication = deduplicatedIdentifiers(in: source)
    var job = deduplication.job

    let wasInterrupted = job.status == .queued || job.status == .running
    if wasInterrupted {
      job.status = .cancelled
      job.finishedAt = job.finishedAt ?? Date()
      job.message = job.message ?? "Run was interrupted before the app closed."
    }
    return (job, deduplication.removed, wasInterrupted)
  }

  private static func deduplicatedIdentifiers(
    in source: JobRecord
  ) -> (job: JobRecord, removed: Int) {
    var job = source
    var removed = 0
    var artifactIDs: Set<Artifact.ID> = []
    job.artifacts = job.artifacts.filter { artifact in
      let inserted = artifactIDs.insert(artifact.id).inserted
      if !inserted { removed += 1 }
      return inserted
    }
    var nextActionIDs: Set<String> = []
    job.nextActions = job.nextActions.filter { action in
      let inserted = nextActionIDs.insert(action.id).inserted
      if !inserted { removed += 1 }
      return inserted
    }
    return (job, removed)
  }

  private static func evidenceDate(_ job: JobRecord) -> Date {
    job.finishedAt ?? job.startedAt ?? job.createdAt
  }
}

private struct JobHistoryPayload: Codable {
  var version: Int
  var generatedAt: Date
  var jobs: [JobRecord]
}
