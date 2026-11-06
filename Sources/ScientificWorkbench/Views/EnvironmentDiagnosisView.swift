import AppKit
import SwiftUI

struct EnvironmentDiagnosisView: View {
  @ObservedObject var store: WorkbenchStore
  @State private var repairProfile: EnvironmentRepairProfile = .core
  @State private var repairPlan: EnvironmentRepairPlan?

  private var diagnosis: EnvironmentDiagnosis { store.environmentDiagnosis }

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack {
        Label("Python environment", systemImage: "stethoscope")
          .font(.headline)
        Spacer()
        if store.isCheckingEnvironment {
          ProgressView()
            .controlSize(.small)
            .accessibilityLabel("Checking Python environment")
        } else {
          StatusBadge(status: diagnosis.status)
        }
      }

      LabeledContent("Selected Python") {
        Text(diagnosis.selectedPython ?? store.environmentStatus.datanalysisPython ?? "Not selected")
          .font(.system(.caption, design: .monospaced))
          .lineLimit(2)
          .truncationMode(.middle)
          .textSelection(.enabled)
      }
      LabeledContent("Python version") {
        Text(diagnosis.pythonVersion ?? "Not verified")
      }

      Divider()

      if diagnosis.coreReady == true {
        Label("Core: required Python packages verified.", systemImage: "checkmark.circle")
          .foregroundStyle(.green)
          .accessibilityIdentifier("settings.environment-core-state")
      } else if diagnosis.coreReady == false {
        Label("Blocks Core: the scientific environment or required packages need attention.", systemImage: "xmark.octagon")
          .foregroundStyle(.orange)
          .accessibilityIdentifier("settings.environment-core-state")
        if !diagnosis.missingCoreModules.isEmpty {
          Text("Missing Core modules: \(diagnosis.missingCoreModules.joined(separator: ", ")).")
            .font(.caption)
        }
      } else {
        Label("Core has not been verified. Refresh before running a workflow.", systemImage: "questionmark.circle")
          .foregroundStyle(.secondary)
          .accessibilityIdentifier("settings.environment-core-state")
      }

      if let message = diagnosis.message {
        Text(message)
          .font(.caption)
          .foregroundStyle(.secondary)
          .textSelection(.enabled)
      }

      if diagnosis.fullReady == true {
        Label("Full: additional Python package groups verified.", systemImage: "checkmark.circle")
          .foregroundStyle(.green)
      } else if diagnosis.fullReady == false {
        Label("Optional Full packages are incomplete; Core routes can still work when Core is ready.", systemImage: "puzzlepiece.extension")
          .foregroundStyle(.secondary)
        ForEach(diagnosis.missingOptionalGroups) { group in
          Text("\(group.label): \(group.modules.joined(separator: ", "))")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .accessibilityIdentifier("settings.environment-optional-groups")
      }

      Label("Recommended: choose a workflow first, then run its own preflight. If Python packages are missing, create a separate new environment with the source installer; do not update an existing environment or infer that an external app is installed.", systemImage: "arrow.right.circle")
        .font(.caption)
        .foregroundStyle(.secondary)

      Button("Prepare a new environment") {
        repairPlan = makeRepairPlan()
      }
      .accessibilityIdentifier("settings.environment-plan-repair")

      if let plan = repairPlan {
        VStack(alignment: .leading, spacing: 10) {
          Picker("New profile", selection: $repairProfile) {
            ForEach(EnvironmentRepairProfile.allCases) { profile in
              Text(profile.title).tag(profile)
            }
          }
          .pickerStyle(.segmented)
          .onChange(of: repairProfile) { _, _ in repairPlan = makeRepairPlan() }

          Text("Destination (must not already exist)")
            .font(.headline)
          Text(plan.destination)
            .font(.system(.caption, design: .monospaced))
            .textSelection(.enabled)
          Text("Measured once on the development Mac: about \(plan.profile.localDiskMeasurement) installed and \(plan.profile.localTimeMeasurement) for setup. Network, cache, and another Mac can change both figures.")
            .font(.caption)
          if !plan.usesReviewedLock {
            Text("This Mac/profile does not meet the reviewed Apple Silicon lock. The plan uses current package-index resolution, so versions may differ. Read the installation guide before installing.")
              .font(.caption)
              .foregroundStyle(.orange)
          }
          Text("From the cloned source repository root, preview first. This command does not create an environment:")
            .font(.caption)
          Text("The commands require a Python 3.11 executable named python3.11. If yours has a different name, replace the value after --python with its absolute path as explained in the installation guide.")
            .font(.caption)
            .foregroundStyle(.secondary)
          Text(plan.previewCommand)
            .font(.system(.caption, design: .monospaced))
            .textSelection(.enabled)
          Button("Copy preview command") {
            copyToPasteboard(plan.previewCommand)
          }
          Text("After reviewing the destination and plan, run the install command yourself. It downloads packages only into that new destination. The installer rejects an existing directory and retains scientific-workbench-setup/installation.log and its failure details there.")
            .font(.caption)
          Text(plan.installCommand)
            .font(.system(.caption, design: .monospaced))
            .textSelection(.enabled)
          Button("Copy install command") {
            copyToPasteboard(plan.installCommand)
          }
          .accessibilityIdentifier("settings.environment-copy-install-command")
        }
        .padding(12)
        .background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 10))
        .accessibilityIdentifier("settings.environment-repair-plan")
      }

      HStack {
        Button("Recheck Environment") {
          Task { await store.refreshEnvironment() }
        }
        .disabled(store.isCheckingEnvironment)
        .accessibilityIdentifier("settings.environment-recheck")

        Button("Open Installation Guide") {
          store.openUserGuide()
        }
        .disabled(store.userGuideURL == nil)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .accessibilityIdentifier("settings.environment-diagnosis")
  }

  private func makeRepairPlan() -> EnvironmentRepairPlan {
    #if arch(arm64)
    let isAppleSilicon = true
    #else
    let isAppleSilicon = false
    #endif
    return EnvironmentRepairPlan.make(
      profile: repairProfile,
      isAppleSilicon: isAppleSilicon,
      macOSMajorVersion: ProcessInfo.processInfo.operatingSystemVersion.majorVersion
    )
  }

  private func copyToPasteboard(_ command: String) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(command, forType: .string)
  }
}
