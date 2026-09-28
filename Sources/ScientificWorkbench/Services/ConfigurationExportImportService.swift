import Foundation

struct WorkbenchConfigurationSnapshot {
  var generatedAt: Date
  var appName: String
  var skillRootPath: String
  var outputRootPath: String
  var pythonExecutable: String
  var aiProvider: AIProvider
  var ollamaModel: String
  var ollamaBaseURL: String
  var openAIModel: String
  var grokModel: String
  var geminiModel: String
  var cloudAttachmentContextMode: CloudAttachmentContextMode
  var codexExecutablePath: String
  var codexSandboxMode: String
  var externalProcessTimeoutMinutes: Int
}

struct WorkbenchConfigurationPayload: Codable {
  var version: Int
  var generatedAt: Date
  var appName: String
  var skillRootPath: String
  var outputRootPath: String
  var pythonExecutable: String
  var aiProvider: AIProvider
  var ollamaModel: String
  var ollamaBaseURL: String
  var openAIModel: String
  var grokModel: String
  var geminiModel: String
  var cloudAttachmentContextMode: CloudAttachmentContextMode?
  var codexExecutablePath: String
  var codexSandboxMode: String
  var externalProcessTimeoutMinutes: Int?
}

enum ConfigurationExportImportError: LocalizedError {
  case unsupportedVersion(Int)
  case destinationAlreadyExists(String)

  var errorDescription: String? {
    switch self {
    case .unsupportedVersion(let version):
      return "unsupported version \(version)."
    case .destinationAlreadyExists(let path):
      return "the export destination already exists and will not be overwritten: \(path)"
    }
  }
}

struct ConfigurationExportImportService {
  func export(
    snapshot: WorkbenchConfigurationSnapshot,
    to path: String?,
    configurationDirectory: URL,
    redact: (String) -> String
  ) throws -> URL {
    let url = path.map { URL(fileURLWithPath: $0) } ?? configurationDirectory
      .appendingPathComponent(
        "scientific_workbench_config_\(DateFormatters.runFolder.string(from: snapshot.generatedAt))_\(UUID().uuidString.lowercased()).json"
      )
    let payload = WorkbenchConfigurationPayload(
      version: 1,
      generatedAt: snapshot.generatedAt,
      appName: snapshot.appName,
      skillRootPath: redact(snapshot.skillRootPath),
      outputRootPath: redact(snapshot.outputRootPath),
      pythonExecutable: redact(snapshot.pythonExecutable),
      aiProvider: snapshot.aiProvider,
      ollamaModel: redact(snapshot.ollamaModel),
      ollamaBaseURL: redact(snapshot.ollamaBaseURL),
      openAIModel: redact(snapshot.openAIModel),
      grokModel: redact(snapshot.grokModel),
      geminiModel: redact(snapshot.geminiModel),
      cloudAttachmentContextMode: snapshot.cloudAttachmentContextMode,
      codexExecutablePath: redact(snapshot.codexExecutablePath),
      codexSandboxMode: snapshot.codexSandboxMode,
      externalProcessTimeoutMinutes: snapshot.externalProcessTimeoutMinutes
    )

    guard !FileManager.default.fileExists(atPath: url.path) else {
      throw ConfigurationExportImportError.destinationAlreadyExists(url.path)
    }
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    let data = try JSONEncoder.scientificWorkbench.encode(payload)
    try data.write(to: url, options: [.atomic])
    return url
  }

  func importPayload(from path: String) throws -> WorkbenchConfigurationPayload {
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    let payload = try JSONDecoder.scientificWorkbench.decode(WorkbenchConfigurationPayload.self, from: data)
    guard payload.version == 1 else {
      throw ConfigurationExportImportError.unsupportedVersion(payload.version)
    }
    return payload
  }
}
