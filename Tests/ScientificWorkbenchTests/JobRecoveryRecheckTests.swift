import Foundation
@testable import ScientificWorkbench
import Testing

extension ScientificWorkbenchTests {
  @Test
  func recoveryDependencyCheckUsesActualModuleFindingsRatherThanFullReadiness() throws {
    let report = """
    {
      "capabilities": {"core_ready": true, "full_ready": false},
      "environment": {"python_version": "3.11"},
      "core_modules": {"modules": {"pypdf": {"installed": true}}},
      "optional_groups": {
        "data": {"missing": ["duckdb"], "modules": {
          "duckdb": {"installed": false}, "pyarrow": {"installed": true}
        }}
      }
    }
    """
    let diagnosis = try #require(EnvironmentDiagnosis.parse(report, selectedPython: "/test/python"))
    #expect(diagnosis.inspectedModules == ["pypdf": true, "duckdb": false, "pyarrow": true])
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/test-run")
    job.structuredErrors = [
      JobStructuredError(kind: "missing_optional_backend", message: "DuckDB and pyarrow are needed.", recoveryHint: nil)
    ]
    let result = JobRecoveryEnvironmentCheck.summary(diagnosis: diagnosis, job: job)
    #expect(result.contains("duckdb: not located"))
    #expect(result.contains("pyarrow: located"))
    #expect(!result.contains("pypdf: located"))
    #expect(result.contains("does not test imports"))
    #expect(result.contains("Full incomplete"))
  }

  @Test
  func recoveryDependencyCheckDoesNotGuessUnreportedModulesOrReadStdout() throws {
    let report = """
    {
      "capabilities": {"core_ready": true, "full_ready": true},
      "environment": {},
      "optional_groups": {"data": {"modules": {
        "duckdb": {"installed": true}, "unknown": {"installed": "yes"}
      }}}
    }
    """
    let diagnosis = try #require(EnvironmentDiagnosis.parse(report, selectedPython: nil))
    #expect(diagnosis.inspectedModules["unknown"] == nil)
    var job = JobRecord(capability: sampleCapability(), runDirectory: "/tmp/test-run")
    job.stderr = "The myduckdbadapter external tool was not found."
    job.stdout = "Example: DuckDB is available."
    let result = JobRecoveryEnvironmentCheck.summary(diagnosis: diagnosis, job: job)
    #expect(result.contains("No dependency named in this error could be matched"))
    #expect(!result.contains("duckdb: located"))

    job.stderr = "DuckDB unavailable."
    let failed = JobRecoveryEnvironmentCheck.summary(diagnosis: .unknown, job: job)
    #expect(failed.contains("Core not verified"))
    #expect(!failed.contains("duckdb: located"))
  }

  @Test
  func cancelledRecoveryNetworkCheckCannotClaimConnectivity() async {
    let task = Task {
      withUnsafeCurrentTask { $0?.cancel() }
      return await JobRecoveryNetworkProbe().inspect()
    }
    let result = await task.value
    #expect(result == .notVerified)
    #expect(result.summary.contains("No current network-path result"))
  }

  @Test
  func networkPathRecoveryKeepsServerAvailabilityUnverifiedForEveryPathState() {
    for result in [JobRecoveryNetworkPath.available, .unavailable, .requiresConnection, .notVerified] {
      #expect(result.summary.contains("No server request was sent"))
      #expect(result.summary.contains("does not verify the job's endpoint"))
    }
  }
}
