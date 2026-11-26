import Darwin
import Foundation

struct RunRuntimeEvidence: Codable, Equatable, Sendable {
  let pythonImplementation: String
  let pythonVersion: String
  let architecture: String
  let profilePackages: [String: String]

  static let environmentKey = "SCIENTIFIC_WORKBENCH_RUNTIME_EVIDENCE"
  // Direct requirements documented by the bundled Core and Full profiles.
  static let profilePackageNames = """
    numpy scipy pandas matplotlib astropy pypdf python-docx python-pptx openpyxl PyYAML xarray h5py requests
    duckdb pyarrow fastparquet statsmodels scikit-learn photutils ccdproc specutils astroquery reproject regions
    plotly nbclient nbformat nbconvert jupyter_client ipykernel notebook pypdfium2 pdfplumber rapidocr-onnxruntime
    python-calamine pyxlsb pyxlsbwriter numbers-parser olefile tifffile zarr
    """.split(whereSeparator: \.isWhitespace).map(String.init)

  func validated() -> Self? {
    guard ["cpython", "pypy", "graalpy"].contains(pythonImplementation),
          ["arm64", "aarch64", "x86_64", "amd64", "i386", "i686"].contains(architecture),
          Self.isVersion(pythonVersion) else { return nil }
    let names = Set(Self.profilePackageNames)
    return Self(pythonImplementation: pythonImplementation, pythonVersion: pythonVersion, architecture: architecture,
                profilePackages: profilePackages.filter { names.contains($0.key) && Self.isVersion($0.value) })
  }

  private static func isVersion(_ value: String) -> Bool {
    value.utf8.count <= 48 && value.range(
      of: #"\A(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?\z"#,
      options: .regularExpression
    ) != nil
  }

  struct Channel: Sendable {
    let url: URL
    let tool: String

    private struct Request: Encodable {
      let destination: String
      let tool: String
      let packages: [String]
    }

    private struct Observation: Decodable {
      let schemaVersion: Int
      let tool: String
      let implementation: String
      let version: String
      let architecture: String
      let packages: [String: String]
    }

    init(runRoot: URL, tool: String) {
      url = runRoot.appendingPathComponent(".swb-runtime-\(UUID().uuidString.lowercased()).json")
      self.tool = tool
    }

    var request: String? {
      let request = Request(destination: url.path, tool: tool, packages: RunRuntimeEvidence.profilePackageNames)
      guard let data = try? JSONEncoder().encode(request) else { return nil }
      return String(decoding: data, as: UTF8.self)
    }

    func consume() -> RunRuntimeEvidence? {
      let descriptor = open(url.path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)
      guard descriptor >= 0 else { return nil }
      let file = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
      defer { try? file.close() }
      var fileStatus = stat()
      guard fstat(descriptor, &fileStatus) == 0, (fileStatus.st_mode & S_IFMT) == S_IFREG,
            fileStatus.st_nlink == 1, fileStatus.st_uid == getuid() else { return nil }
      defer {
        var current = stat()
        if lstat(url.path, &current) == 0, current.st_dev == fileStatus.st_dev, current.st_ino == fileStatus.st_ino {
          _ = unlink(url.path)
        }
      }

      let maximumBytes = 32_768
      guard fileStatus.st_size <= maximumBytes,
            let data = try? file.read(upToCount: maximumBytes + 1), data.count <= maximumBytes,
            let observed = try? JSONDecoder().decode(Observation.self, from: data),
            observed.schemaVersion == 1, observed.tool == tool else { return nil }
      return RunRuntimeEvidence(
        pythonImplementation: observed.implementation, pythonVersion: observed.version,
        architecture: observed.architecture, profilePackages: observed.packages
      ).validated()
    }
  }
}
