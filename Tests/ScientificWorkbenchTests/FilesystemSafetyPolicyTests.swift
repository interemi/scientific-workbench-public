import Foundation
import Testing
@testable import ScientificWorkbench

@Suite("Filesystem safety policy")
struct FilesystemSafetyPolicyTests {
  @Test
  func stiltsPositionalDestinationsCannotOverwriteInputsOrEscapeTheRun() throws {
    let policy = FilesystemSafetyPolicy()
    let input = "/tmp/scientific-stilts-input.csv"
    let run = "/tmp/scientific-stilts-run"
    for command in ["convert", "filter", "votlint", "crossmatch-sky"] {
      let reads = command == "crossmatch-sky" ? [input, input] : [input]
      for destination in [input, "/tmp/unattached-output.csv", "relative-output"] {
        #expect(throws: FilesystemSafetyError.self) {
          try policy.validateRawArguments(
            [command] + reads + [destination], inputPaths: [input], runDirectory: run,
            capabilityID: "stilts_workbench"
          )
        }
      }
      try policy.validateRawArguments(
        [command] + reads + [run + "/result.csv"], inputPaths: [input], runDirectory: run,
        capabilityID: "stilts_workbench"
      )
    }
  }

  @Test
  func outputRootCannotOverlapOriginalInput() {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))

    #expect(
      policy.assessOutputRoot(
        "/Users/researcher/Desktop/DOCUS/results",
        inputPaths: ["/Users/researcher/Desktop/DOCUS"]
      ) == .blocked("The output root overlaps an original input: DOCUS.")
    )
  }

  @Test
  func directDesktopOutputRequiresDedicatedFolder() {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))

    #expect(
      policy.assessOutputRoot(
        "/Users/researcher/Desktop",
        inputPaths: []
      ) == .requiresConfirmation(
        "Use a dedicated Scientific Workbench subfolder instead of writing directly into Desktop."
      )
    )
  }

  @Test
  func protectedCredentialFoldersAreBlocked() {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))

    #expect(
      policy.assessOutputRoot(
        "/Users/researcher/.ssh/scientific-run",
        inputPaths: []
      ) == .blocked("The selected output root is inside protected location /Users/researcher/.ssh.")
    )
  }

  @Test
  func runDirectoryMustStayUnderAllowedRootAndAwayFromInputs() throws {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))
    let run = "/Users/researcher/Documents/Scientific Workbench Runs/run-1"
    try policy.validateRunDirectory(
      run,
      inputPaths: ["/Users/researcher/Desktop/DOCUS"],
      allowedRoots: ["/Users/researcher/Documents/Scientific Workbench Runs"]
    )
    try policy.validateRunDirectory(
      run,
      inputPaths: ["\(run)/staged/source.docx"],
      allowedRoots: ["/Users/researcher/Documents/Scientific Workbench Runs"]
    )

    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRunDirectory(
        "/Users/researcher/Desktop/DOCUS/generated",
        inputPaths: ["/Users/researcher/Desktop/DOCUS"],
        allowedRoots: ["/Users/researcher/Desktop/DOCUS"]
      )
    }
  }

  @Test
  func rawOutputsMustStayInsideCurrentRun() throws {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))
    let run = "/Users/researcher/Documents/Scientific Workbench Runs/run-1"

    try policy.validateRawArguments(
      [
        "--source", "/Users/researcher/Desktop/DOCUS/input.fits",
        "--report-md", "\(run)/reports/result.md",
      ],
      inputPaths: ["/Users/researcher/Desktop/DOCUS/input.fits"],
      runDirectory: run
    )

    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        ["--report-md", "/Users/researcher/Desktop/DOCUS/result.md"],
        inputPaths: ["/Users/researcher/Desktop/DOCUS"],
        runDirectory: run
      )
    }
  }

  @Test
  func rawReadsMustBeAttachedOrDerived() {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))

    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        ["--source", "/Users/researcher/Desktop/unattached.csv"],
        inputPaths: [],
        runDirectory: "/Users/researcher/Documents/Scientific Workbench Runs/run-1"
      )
    }
  }

  @Test
  func unknownOptionCannotHideAbsoluteOrRelativePaths() {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))
    let run = "/Users/researcher/Documents/Scientific Workbench Runs/run-1"

    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        ["--foo=/Users/researcher/Desktop/unattached.csv"],
        inputPaths: [],
        runDirectory: run
      )
    }
    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        ["--foo=../relative-escape.csv"],
        inputPaths: [],
        runDirectory: run
      )
    }
    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        ["--foo", "/Users/researcher/Desktop/unattached.csv"],
        inputPaths: [],
        runDirectory: run
      )
    }
    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        ["-o", "/Users/researcher/Desktop/attached.csv"],
        inputPaths: ["/Users/researcher/Desktop/attached.csv"],
        runDirectory: run
      )
    }
  }

  @Test
  func confirmedOutputOptionsCannotTargetInputsOrEscapeRun() throws {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))
    let input = "/Users/researcher/Desktop/DOCUS/source.docx"
    let run = "/Users/researcher/Documents/Scientific Workbench Runs/run-1"

    for option in ["--output-csv", "--output-path", "--diff-json"] {
      #expect(throws: FilesystemSafetyError.self) {
        try policy.validateRawArguments(
          [option, input],
          inputPaths: [input],
          runDirectory: run
        )
      }
      #expect(throws: FilesystemSafetyError.self) {
        try policy.validateRawArguments(
          ["\(option)=../relative-escape.json"],
          inputPaths: [input],
          runDirectory: run
        )
      }
    }

    try policy.validateRawArguments(
      [
        "--output-csv", "\(run)/tables/result.csv",
        "--output-path=\(run)/artifacts/result.fits",
        "--diff-json", "\(run)/artifacts/diff.json",
      ],
      inputPaths: [input],
      runDirectory: run
    )
  }

  @Test
  func hardlinkedOutputCannotAliasAnAttachedFile() throws {
    let fixture = try makeFilesystemFixture(
      name: "hardlink-file-output",
      files: ["inputs/source.csv": "wavelength,flux\n6707.8,1.0\n"]
    )
    let input = fixture.appendingPathComponent("inputs/source.csv")
    let run = fixture.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
    let alias = run.appendingPathComponent("summary.json")
    try FileManager.default.linkItem(at: input, to: alias)

    #expect(throws: FilesystemSafetyError.self) {
      try FilesystemSafetyPolicy().validateRawArguments(
        ["--summary-json", alias.path],
        inputPaths: [input.path],
        runDirectory: run.path
      )
    }
  }

  @Test
  func hardlinkedOutputCannotAliasAFileBelowAnAttachedDirectory() throws {
    let fixture = try makeFilesystemFixture(
      name: "hardlink-directory-output",
      files: ["raw/source.fits": "FITS sentinel"]
    )
    let inputRoot = fixture.appendingPathComponent("raw", isDirectory: true)
    let source = inputRoot.appendingPathComponent("source.fits")
    let run = fixture.appendingPathComponent("run", isDirectory: true)
    try FileManager.default.createDirectory(at: run, withIntermediateDirectories: true)
    let alias = run.appendingPathComponent("preview.png")
    try FileManager.default.linkItem(at: source, to: alias)

    #expect(throws: FilesystemSafetyError.self) {
      try FilesystemSafetyPolicy().validateRawArguments(
        ["--preview", alias.path],
        inputPaths: [inputRoot.path],
        runDirectory: run.path
      )
    }
  }

  @Test
  func attachedFileDoesNotAuthorizeReadingItsParent() {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))
    let input = "/Users/researcher/Desktop/DOCUS/attached.csv"

    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        ["--data-path", "/Users/researcher/Desktop/DOCUS"],
        inputPaths: [input],
        runDirectory: "/Users/researcher/Documents/Scientific Workbench Runs/run-1"
      )
    }
  }

  @Test
  func scalarRawValuesRemainAllowed() throws {
    try FilesystemSafetyPolicy().validateRawArguments(
      [
        "--max-files=12",
        "--title", "Scientific report",
        "--line-center", "6707.8",
        "--find", "https://example.invalid/reference.pdf",
      ],
      inputPaths: [],
      runDirectory: "/tmp/ScientificWorkbenchRuns/run-1"
    )
  }

  @Test
  func capabilityPositionalOutputsCannotOverwriteAttachedInputs() throws {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))
    let input = "/Users/researcher/Desktop/talk.key"
    let run = "/Users/researcher/Documents/Scientific Workbench Runs/run-1"

    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        [input, input, "--preflight-only"],
        inputPaths: [input],
        runDirectory: run,
        capabilityID: "keynote_export"
      )
    }

    try policy.validateRawArguments(
      [input, "\(run)/previews/talk.pdf", "--preflight-only"],
      inputPaths: [input],
      runDirectory: run,
      capabilityID: "keynote_export"
    )
  }

  @Test
  func aptConfigurationPathsAreScopedToAPTCapabilities() throws {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))
    let arguments = [
      "preflight",
      "--apt-command", "/Applications/APT/bin/apt",
      "--apt-preferences", "/Users/researcher/.config/apt/preferences.xml",
      "--summary-json", "/Users/researcher/Documents/Scientific Workbench Runs/run-1/summary.json",
    ]
    let run = "/Users/researcher/Documents/Scientific Workbench Runs/run-1"

    try policy.validateRawArguments(
      arguments,
      inputPaths: [],
      runDirectory: run,
      capabilityID: "apt_workbench"
    )
    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        arguments,
        inputPaths: [],
        runDirectory: run,
        capabilityID: "profile_table"
      )
    }
  }

  @Test
  func skillResourcesAreReadableOnlyByContractedCapabilities() throws {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))
    let skillRoot = "/Users/researcher/.codex/skills/scientific-data-analysis"
    let bundledFixture = "\(skillRoot)/examples/science/legacy_spectroscopy_mini/mini_template.fits"
    let run = "/Users/researcher/Documents/Scientific Workbench Runs/run-1"

    try policy.validateRawArguments(
      [bundledFixture, "--summary-json", "\(run)/summary.json"],
      inputPaths: [],
      runDirectory: run,
      capabilityID: "legacy_spectroscopy_envcheck",
      skillRoot: skillRoot
    )
    #expect(throws: FilesystemSafetyError.self) {
      try policy.validateRawArguments(
        [bundledFixture, "--summary-json", "\(run)/summary.json"],
        inputPaths: [],
        runDirectory: run,
        capabilityID: "profile_table",
        skillRoot: skillRoot
      )
    }
  }

  @Test
  func rawArgumentsCannotRequestWritesBesideSources() {
    #expect(throws: FilesystemSafetyError.self) {
      try FilesystemSafetyPolicy().validateRawArguments(
        ["--run-from-source-dir"],
        inputPaths: [],
        runDirectory: "/tmp/ScientificWorkbenchRuns/run-1",
        capabilityID: "notebook_workbench.execute-copy"
      )
    }
  }

  @Test
  func arbitraryDuckDBSQLIsBlockedBecauseItCanEscapeAttachedInputs() {
    let run = "/tmp/ScientificWorkbenchRuns/duckdb-run"
    for capabilityID in ["duckdb_workbench", "cross_domain_data_workbench"] {
      for sqlOption in ["--sql", "--sq", "--sq=COPY source0 TO 'outside.csv'"] {
        #expect(throws: FilesystemSafetyError.self) {
          try FilesystemSafetyPolicy().validateRawArguments(
            [
              "/tmp/attached.csv",
              sqlOption, "COPY (SELECT * FROM source0) TO 'outside.csv'",
              "--summary-json", "\(run)/summary.json",
            ],
            inputPaths: ["/tmp/attached.csv"],
            runDirectory: run,
            capabilityID: capabilityID
          )
        }
      }
    }
  }

  @Test
  func sensitiveNetworkAndOverwriteRawOptionsAreBlocked() {
    let run = "/tmp/ScientificWorkbenchRuns/unsafe-options"
    for arguments in [
      ["solve", "--api-key", "private-astrometry-key"],
      ["solve", "--api-k", "private-astrometry-key"],
      ["solve", "--api-base=https://collector.example.invalid"],
      ["solve", "--api-b=https://collector.example.invalid"],
      ["--overwrite"],
      ["--overw"],
      ["--force"],
      ["--forc"],
    ] {
      #expect(throws: FilesystemSafetyError.self) {
        try FilesystemSafetyPolicy().validateRawArguments(
          arguments,
          inputPaths: [],
          runDirectory: run,
          capabilityID: "astrometry_net_workbench.solve"
        )
      }
    }

    #expect(throws: Never.self) {
      try FilesystemSafetyPolicy().validateRawArguments(
        ["--force-simple-fallback"],
        inputPaths: [],
        runDirectory: run,
        capabilityID: "document_intake_workbench"
      )
    }
  }

  @Test
  func notebookExecutionRejectsInlineCodeMutationButAllowsAttachedCodeFile() throws {
    let run = "/tmp/ScientificWorkbenchRuns/notebook-run"
    let notebook = "/tmp/attached.ipynb"
    let codeFile = "/tmp/reviewed-code.py"
    for arguments in [
      [notebook, "--output-dir", "\(run)/artifacts/notebook", "--append-code", "open('/tmp/original', 'w').write('x')"],
      [notebook, "--output-dir", "\(run)/artifacts/notebook", "--append-c", "print('unsafe')"],
      [notebook, "--output-dir", "\(run)/artifacts/notebook", "--replace-text", "safe", "malicious"],
      [notebook, "--output-dir", "\(run)/artifacts/notebook", "--replace-t", "safe", "malicious"],
      [notebook, "--output-dir", "\(run)/artifacts/notebook", "--replace-t=safe", "malicious"],
      [notebook, "--output-dir", "\(run)/artifacts/notebook", "--run-f"],
    ] {
      #expect(throws: FilesystemSafetyError.self) {
        try FilesystemSafetyPolicy().validateRawArguments(
          arguments,
          inputPaths: [notebook, codeFile],
          runDirectory: run,
          capabilityID: "notebook_workbench.execute-copy"
        )
      }
    }

    try FilesystemSafetyPolicy().validateRawArguments(
      [
        notebook,
        "--output-dir", "\(run)/artifacts/notebook",
        "--append-code-file", codeFile,
      ],
      inputPaths: [notebook, codeFile],
      runDirectory: run,
      capabilityID: "notebook_workbench.execute-copy"
    )
  }

  @Test
  func stiltsFilterCommandDSLRemainsAvailableWithinPathBoundaries() throws {
    let run = "/tmp/ScientificWorkbenchRuns/stilts-run"
    try FilesystemSafetyPolicy().validateRawArguments(
      [
        "filter", "/tmp/attached.csv", "\(run)/artifacts/filtered.csv",
        "--cmd", "keepcols ra dec mag",
        "--summary-json", "\(run)/summary.json",
      ],
      inputPaths: ["/tmp/attached.csv"],
      runDirectory: run,
      capabilityID: "stilts_workbench"
    )
  }

  @Test
  func overlyBroadAncestorsOfProtectedLocationsAreBlocked() {
    let policy = FilesystemSafetyPolicy(homeDirectory: URL(fileURLWithPath: "/Users/researcher"))

    #expect(
      policy.assessOutputRoot("/Users", inputPaths: []) ==
        .blocked("The selected output root is an overly broad ancestor of protected location /Users/researcher/.ssh.")
    )
    #expect(
      policy.assessOutputRoot(
        "/Users/researcher/Documents/Scientific Workbench Runs",
        inputPaths: []
      ) == .safe
    )
    #expect(
      policy.assessOutputRoot(
        "/private/var/folders/zz/scientific-workbench/run-1",
        inputPaths: []
      ) == .safe
    )
  }

  @Test
  func runDirectoryFactoryAddsCollisionResistantSuffix() {
    let fixedDate = Date(timeIntervalSince1970: 1_735_689_600)
    let factory = RunDirectoryFactory(
      date: { fixedDate },
      nonce: { "12345678-abcd-ef00-1234-56789abcdef0" }
    )

    let path = factory.makePath(root: "/runs", capabilityID: "profile/table")

    #expect(path.hasPrefix("/runs/"))
    #expect(path.contains("profile_table"))
    #expect(path.hasSuffix("12345678-abcd-ef00-1234-56789abcdef0"))
  }

  private func makeFilesystemFixture(name: String, files: [String: String]) throws -> URL {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("Scientific-Workbench-Filesystem-\(name)-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    for (relativePath, contents) in files {
      let url = root.appendingPathComponent(relativePath)
      try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
      )
      try contents.write(to: url, atomically: true, encoding: .utf8)
    }
    return root
  }
}
