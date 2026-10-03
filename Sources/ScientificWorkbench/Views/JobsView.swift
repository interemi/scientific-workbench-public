import SwiftUI

struct JobsView: View {
  @ObservedObject var store: WorkbenchStore

  var body: some View {
    HStack(spacing: 0) {
      jobList
        .frame(width: 360)

      Divider()

      if let job = store.selectedJob {
        JobDetailView(store: store, job: job)
          .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity)
      } else {
        ContentUnavailableView {
          Label("No Jobs Yet", systemImage: "list.bullet.rectangle")
        } description: {
          Text("Plan a workflow in Chat or run a capability. Its logs, recovery advice, and artifacts will appear here.")
        } actions: {
          Button("Open Chat") {
            store.selectedSection = .agent
          }
          .accessibilityIdentifier("jobs.empty.open-chat")
        }
        .frame(minWidth: 0, maxWidth: .infinity, maxHeight: .infinity)
      }
    }
  }

  private var jobList: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(alignment: .leading, spacing: 6) {
        Text("Jobs")
          .font(.title2)
          .fontWeight(.semibold)
        Text("Queue, logs, and status")
          .foregroundStyle(.secondary)
      }
      .padding(.horizontal, 16)
      .padding(.top, 18)

      HStack(spacing: 8) {
        Button {
          store.reloadJobHistory()
        } label: {
          Label("Reload", systemImage: "arrow.clockwise")
        }
        .labelStyle(.iconOnly)
        .accessibilityLabel("Reload job history")
        .accessibilityIdentifier("jobs.reload-history")
        .help("Reload persisted job history from disk.")

        Button {
          store.revealJobHistory()
        } label: {
          Label("Reveal History", systemImage: "folder")
        }
        .labelStyle(.iconOnly)
        .accessibilityLabel("Reveal job history")
        .accessibilityIdentifier("jobs.reveal-history")
        .help("Reveal the persisted job history JSON.")

        Button(role: .destructive) {
          store.clearJobHistory()
        } label: {
          Label("Clear History", systemImage: "trash")
        }
        .labelStyle(.iconOnly)
        .accessibilityLabel("Clear job history")
        .accessibilityHint("Removes the visible persisted history after all active jobs have finished.")
        .accessibilityIdentifier("jobs.clear-history")
        .help("Clear the visible and persisted job history.")
        .disabled(store.jobs.isEmpty || store.hasActiveJob)
      }
      .padding(.horizontal, 16)

      if let notice = store.persistenceRecoveryNotice {
        VStack(alignment: .leading, spacing: 6) {
          Label("Persisted state recovered", systemImage: "externaldrive.badge.checkmark")
            .font(.caption)
            .fontWeight(.semibold)
          Text(notice)
            .font(.caption2)
            .textSelection(.enabled)
          if store.lastPersistenceRecoveryArchivePath != nil {
            Button("Reveal preserved original") {
              store.revealPersistenceRecoveryArchive()
            }
            .font(.caption)
          }
        }
        .foregroundStyle(.orange)
        .padding(.horizontal, 16)
      }

      if store.jobs.isEmpty {
        Text("No jobs have run yet. Open Chat or Capabilities to start a reproducible run.")
          .foregroundStyle(.secondary)
          .padding(.horizontal, 16)
      } else {
        List(selection: $store.selectedJobID) {
          ForEach(store.jobs) { job in
            VStack(alignment: .leading, spacing: 5) {
              HStack {
                Text(job.capabilityLabel)
                  .lineLimit(1)
                Spacer()
                StatusBadge(status: job.displaySeverity)
              }
              Text(DateFormatters.timestamp.string(from: job.createdAt))
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
            .tag(Optional(job.id))
            .accessibilityElement(children: .combine)
            .accessibilityLabel("\(job.capabilityLabel), \(job.displaySeverity)")
            .accessibilityHint("Created \(DateFormatters.timestamp.string(from: job.createdAt)). Select to review logs and artifacts.")
          }
        }
        .listStyle(.sidebar)
      }
    }
    .frame(maxHeight: .infinity, alignment: .top)
    .background(.bar)
  }
}

struct JobDetailView: View {
  @ObservedObject var store: WorkbenchStore
  let job: JobRecord

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 18) {
        HStack {
          VStack(alignment: .leading, spacing: 4) {
            Text(job.capabilityLabel)
              .font(.title2)
              .fontWeight(.semibold)
            Text(job.capabilityID)
              .font(.caption)
              .foregroundStyle(.secondary)
          }
          Spacer()
          StatusBadge(status: job.displaySeverity)
        }

      if job.status == .running {
        Button(role: .cancel) {
          store.cancelActiveRun()
          } label: {
            Label(store.isCancellationRequested ? "Cancelling..." : "Cancel Run", systemImage: "xmark.circle")
          }
        .disabled(store.isCancellationRequested)
      }

        HStack(spacing: 10) {
        if job.status != .queued && job.status != .running {
          Button {
            Task { await store.retryJob(job) }
          } label: {
            Label("Retry Job", systemImage: "arrow.counterclockwise")
          }
          .disabled(store.hasActiveJob)
        }

        if store.workflowRecoveryState?.stoppedJobID == job.id, store.canResumeAgentPlan {
          Button {
            Task { await store.resumeAgentPlanFromLastSuccess() }
          } label: {
            Label("Run Remaining", systemImage: "play.forward")
          }
          .disabled(store.hasActiveJob)
          .help("Resume the workflow after its last successful step.")
        }

        Button {
          store.refreshRunBundle(for: job)
        } label: {
          Label("Refresh Bundle", systemImage: "arrow.clockwise")
        }
        .help("Re-read summary, manifest, logs, next steps, and artifacts from the run folder.")

        Button {
          store.exportJobSupportBundle(job)
        } label: {
          Label("Support Bundle", systemImage: "lifepreserver")
        }
        .help("Export a redacted diagnostic bundle for this job.")
      }

        Grid(alignment: .leading, horizontalSpacing: 18, verticalSpacing: 10) {
          GridRow {
            MetadataPill(label: "Exit Code", value: job.exitCode.map(String.init) ?? "-")
            MetadataPill(label: "Duration", value: job.durationText)
          }
          GridRow {
            MetadataPill(label: "Parsed Tool", value: job.parsedTool ?? "-")
            MetadataPill(label: "Parsed Status", value: job.parsedStatus ?? "-")
          }
          GridRow {
            MetadataPill(label: "Inputs", value: "\(job.requestInputPaths.count)")
            MetadataPill(label: "Retry Of", value: job.retryOfJobID?.uuidString.prefix(8).description ?? "-")
          }
          GridRow {
            MetadataPill(label: "Contract", value: job.contractVersion ?? "-")
            MetadataPill(label: "Original Modified", value: job.originalModified ?? "unknown")
          }
        }

        JobEvidenceStagesView(job: job)

        if let shortSummary = job.shortSummary {
          Text(shortSummary)
            .font(.headline)
            .textSelection(.enabled)
        }

        if let message = job.message {
          Text(message)
            .foregroundStyle((job.status == .blocked || job.status == .timedOut) ? .orange : .red)
            .textSelection(.enabled)
        }

        RecoveryAdviceView(advice: job.recoveryAdvice)
        JobFindingsView(
          warnings: job.warnings,
          errors: job.structuredErrors,
          nextActions: job.nextActions
        )

        VStack(alignment: .leading, spacing: 8) {
          Text("Command")
            .font(.headline)
          Text(job.command.isEmpty ? "Command was not built." : job.command)
            .font(.system(.caption, design: .monospaced))
            .textSelection(.enabled)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }

        LogBlock(title: "stdout", text: job.stdout)
        LogBlock(title: "stderr", text: job.stderr)

        HStack {
          Button {
            store.revealRunDirectory(job)
          } label: {
            Label("Reveal Run Folder", systemImage: "folder")
          }
          Spacer()
        }
      }
      .padding(24)
    }
  }
}

struct RecoveryAdviceView: View {
  let advice: [String]

  var body: some View {
    if !advice.isEmpty {
      VStack(alignment: .leading, spacing: 8) {
        Text("Recovery")
          .font(.headline)
        VStack(alignment: .leading, spacing: 6) {
          ForEach(advice, id: \.self) { line in
            Label(line, systemImage: "lightbulb")
              .font(.caption)
              .foregroundStyle(.secondary)
              .textSelection(.enabled)
          }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
      }
    }
  }
}

struct JobFindingsView: View {
  let warnings: [String]
  let errors: [JobStructuredError]
  let nextActions: [JobNextAction]

  var body: some View {
    if !warnings.isEmpty || !errors.isEmpty || !nextActions.isEmpty {
      VStack(alignment: .leading, spacing: 12) {
        if !warnings.isEmpty {
          findingSection(
            title: "Warnings",
            systemImage: "exclamationmark.triangle",
            lines: warnings
          )
        }
        if !errors.isEmpty {
          findingSection(
            title: "Errors",
            systemImage: "xmark.octagon",
            lines: errors.map { error in
              [error.kind, error.message, error.recoveryHint].compactMap(\.self).joined(separator: ": ")
            }
          )
        }
        if !nextActions.isEmpty {
          findingSection(
            title: "Next Actions",
            systemImage: "arrow.right.circle",
            lines: nextActions.map(\.label)
          )
        }
      }
    }
  }

  private func findingSection(title: String, systemImage: String, lines: [String]) -> some View {
    VStack(alignment: .leading, spacing: 7) {
      Text(title)
        .font(.headline)
      ForEach(lines, id: \.self) { line in
        Label(line, systemImage: systemImage)
          .font(.caption)
          .foregroundStyle(.secondary)
          .textSelection(.enabled)
      }
    }
  }
}

struct LogBlock: View {
  let title: String
  let text: String

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(title)
        .font(.headline)
      ScrollView {
        Text(text.isEmpty ? "-" : text)
          .font(.system(.caption, design: .monospaced))
          .textSelection(.enabled)
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(10)
      }
      .frame(minHeight: 120, maxHeight: 220)
      .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }
  }
}
