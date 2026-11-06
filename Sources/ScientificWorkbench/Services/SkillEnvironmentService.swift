import Foundation

struct SkillEnvironmentService {
  var runner = ProcessRunner()

  func refresh(skillRoot: String, pythonExecutable: String) async -> EnvironmentStatus {
    let envScript = URL(fileURLWithPath: skillRoot)
      .appendingPathComponent("scripts/datanalysis_env.py")
      .path
    let command = ProcessCommand(
      executable: pythonExecutable.isEmpty ? DefaultPaths.systemPython : pythonExecutable,
      arguments: [envScript, "status"],
      workingDirectory: skillRoot,
      environmentOverrides: SkillPythonEnvironment.overrides(forSkillRoot: skillRoot)
    )

    do {
      let result = try await runner.run(command)
      let combined = [result.stdout, result.stderr].filter { !$0.isEmpty }.joined(separator: "\n")
      let status = result.exitCode == 0 ? "ok" : "blocked"
      return EnvironmentStatus(
        status: status,
        skillRoot: skillRoot,
        datanalysisPython: extractString("selected_python", from: result.stdout),
        datanalysisRoot: extractString("selected_env_root", from: result.stdout),
        details: combined.isEmpty ? "No output." : combined,
        warnings: result.exitCode == 0 ? [] : ["datanalysis_env.py status returned \(result.exitCode)."],
        refreshedAt: Date()
      )
    } catch {
      return EnvironmentStatus(
        status: "failed",
        skillRoot: skillRoot,
        datanalysisPython: nil,
        datanalysisRoot: nil,
        details: error.localizedDescription,
        warnings: [error.localizedDescription],
        refreshedAt: Date()
      )
    }
  }

  func diagnose(
    skillRoot: String,
    pythonExecutable: String,
    selectedPython: String?
  ) async -> EnvironmentDiagnosis {
    let envScript = URL(fileURLWithPath: skillRoot)
      .appendingPathComponent("scripts/datanalysis_env.py")
      .path
    let command = ProcessCommand(
      executable: pythonExecutable.isEmpty ? DefaultPaths.systemPython : pythonExecutable,
      arguments: [envScript, "doctor"],
      workingDirectory: skillRoot,
      timeoutSeconds: 30,
      environmentOverrides: SkillPythonEnvironment.overrides(forSkillRoot: skillRoot),
      redirectStandardInputToNull: true
    )

    do {
      let result = try await runner.run(command)
      guard result.exitCode == 0 else {
        let reason = result.stderr.trimmingCharacters(in: .whitespacesAndNewlines)
        return .unavailable(
          reason.isEmpty
            ? "The environment diagnostic exited with code \(result.exitCode). Review the skill root and Python path."
            : reason,
          selectedPython: selectedPython
        )
      }
      if let diagnosis = EnvironmentDiagnosis.parse(
        result.stdout,
        selectedPython: selectedPython
      ) {
        return diagnosis
      }
      let reason = result.stderr.trimmingCharacters(in: .whitespacesAndNewlines)
      return .unavailable(
        reason.isEmpty ? "The environment diagnostic returned no readable report." : reason,
        selectedPython: selectedPython
      )
    } catch {
      return .unavailable(error.localizedDescription, selectedPython: selectedPython)
    }
  }

  private func extractString(_ key: String, from jsonText: String) -> String? {
    guard let payload = JSONOutputExtractor.lastObject(
      in: jsonText,
      matching: { $0[key] != nil }
    ) else { return nil }
    return payload[key] as? String
  }
}
