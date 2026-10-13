import Foundation

enum JobRecoveryEnvironmentCheck {
  static func summary(diagnosis: EnvironmentDiagnosis, job: JobRecord? = nil) -> String {
    let core = diagnosis.coreReady.map { $0 ? "ready" : "blocked" } ?? "not verified"
    let full = diagnosis.fullReady.map { $0 ? "ready" : "incomplete" } ?? "not verified"
    let readiness = "Current Python check: Core \(core), Full \(full)."
    guard let job else {
      return readiness + " Open Settings for the detailed diagnosis."
    }

    let evidence = ([job.message, job.stderr] + job.structuredErrors.map(\.message))
      .compactMap { $0 }.joined(separator: "\n").lowercased()
    let words = Set(evidence.components(separatedBy: CharacterSet.alphanumerics
      .union(CharacterSet(charactersIn: "_")).inverted))
    let namedModules = diagnosis.inspectedModules.keys.filter { words.contains($0.lowercased()) }.sorted()
    guard !namedModules.isEmpty else {
      return readiness + " No dependency named in this error could be matched to the module diagnostic. "
        + "Review the capability's setup and preflight for external tools or unverified modules."
    }
    let findings = namedModules.map {
      "\($0): \(diagnosis.inspectedModules[$0] == true ? "located" : "not located")"
    }.joined(separator: "; ")
    return readiness + " Named dependencies: \(findings). "
      + "Module discovery does not test imports, external executables, or the capability's execution. Review its preflight before a new run."
  }
}
