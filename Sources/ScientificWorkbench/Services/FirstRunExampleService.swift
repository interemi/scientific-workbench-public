import CryptoKit
import Foundation

enum FirstRunExampleError: LocalizedError {
  case destinationExists

  var errorDescription: String? {
    switch self {
    case .destinationExists:
      return "The example folder already exists. Try again for a fresh folder; no file was replaced."
    }
  }
}

struct FirstRunExampleService {
  var fileManager = FileManager.default

  func create(_ kind: FirstRunExampleKind, at directory: URL) throws -> PreparedFirstRunExample {
    guard !fileManager.fileExists(atPath: directory.path) else {
      throw FirstRunExampleError.destinationExists
    }
    try fileManager.createDirectory(
      at: directory.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    try fileManager.createDirectory(at: directory, withIntermediateDirectories: false)

    let inputDirectory = directory.appendingPathComponent("input", isDirectory: true)
    try fileManager.createDirectory(at: inputDirectory, withIntermediateDirectories: false)
    var inputs: [URL] = []
    var generated: [URL] = []

    func add(_ name: String, data: Data, in folder: URL = inputDirectory) throws -> URL {
      let destination = folder.appendingPathComponent(name)
      try data.write(to: destination, options: .atomic)
      generated.append(destination)
      return destination
    }

    switch kind {
    case .table:
      inputs = [try add("ops.csv", data: Data(Self.tableCSV.utf8))]
    case .fits:
      inputs = [try add("synthetic_wcs_8x8.fits", data: Self.makeFITS())]
    case .spectrum:
      inputs = [try add("spectrum.csv", data: Data(Self.spectrumCSV.utf8))]
    case .document:
      inputs = [try add("observing_note.pdf", data: Self.makePDF())]
    case .mixed:
      let bundle = inputDirectory.appendingPathComponent("mixed_bundle", isDirectory: true)
      try fileManager.createDirectory(at: bundle, withIntermediateDirectories: false)
      _ = try add("measurements.csv", data: Data(Self.measurementsCSV.utf8), in: bundle)
      _ = try add("notes.md", data: Data(Self.observingNote.utf8), in: bundle)
      _ = try add("observing_note.pdf", data: Self.makePDF(), in: bundle)
      inputs = [bundle]
    }

    let records = try generated.sorted { $0.path < $1.path }.map { file in
      let data = try Data(contentsOf: file)
      return [
        "path": file.path.replacingOccurrences(of: directory.path + "/", with: ""),
        "sha256": Self.sha256(data),
      ]
    }
    let manifest: [String: Any] = [
      "schema_version": 1,
      "synthetic": true,
      "example": kind.rawValue,
      "generator": "FirstRunExampleService",
      "files": records,
      "expected_result": kind.expectedResult,
    ]
    let manifestData = try JSONSerialization.data(
      withJSONObject: manifest,
      options: [.prettyPrinted, .sortedKeys]
    )
    try manifestData.write(to: directory.appendingPathComponent("expected.json"), options: .atomic)
    let readme = """
    # Scientific Workbench synthetic example

    Example: \(kind.title)

    \(kind.expectedResult)

    These inputs were generated locally by Scientific Workbench. They contain no
    observations or private data. Select the input under `input/` in the app;
    keep the app's output root separate from this example folder. A fresh copy
    creates a new folder and leaves earlier copies unchanged.

    The generated examples are project-authored synthetic material. You may use
    them to test Scientific Workbench under the project's PolyForm Noncommercial
    1.0.0 license; see LICENSE in the source checkout. They are not calibrated
    scientific reference data.
    """
    try Data(readme.utf8).write(to: directory.appendingPathComponent("README.md"), options: .atomic)

    return PreparedFirstRunExample(
      kind: kind,
      directory: directory,
      inputPaths: inputs.map(\.path)
    )
  }

  private static let tableCSV = """
  team,tasks_open,tasks_closed,owner
  alpha,5,12,ops
  beta,2,9,qa
  gamma,4,7,coordination

  """

  private static let spectrumCSV = """
  wavelength_nm,flux_relative,error_relative
  670.70,1.00,0.03
  670.74,0.91,0.03
  670.78,0.64,0.04
  670.82,0.90,0.03
  670.86,1.01,0.03

  """

  private static let measurementsCSV = """
  wavelength_nm,flux_relative,error_relative
  670.70,0.82,0.03
  670.78,0.64,0.04
  670.84,0.91,0.03

  """

  private static let observingNote = """
  # Synthetic observing note

  The adjacent table is an illustrative first-pass input. Its values are not
  calibrated observations. Review the table profile and document intake as
  separate results before drawing any scientific conclusion.
  """

  private static func makeFITS() -> Data {
    func card(_ key: String, _ value: String) -> String {
      let field = String(repeating: " ", count: max(0, 20 - value.count)) + value
      return (key.padding(toLength: 8, withPad: " ", startingAt: 0) + "= " + field)
        .padding(toLength: 80, withPad: " ", startingAt: 0)
    }

    let cards = [
      card("SIMPLE", "T"),
      card("BITPIX", "-32"),
      card("NAXIS", "2"),
      card("NAXIS1", "8"),
      card("NAXIS2", "8"),
      card("EXTEND", "T"),
      card("OBJECT", "'SYNTHETIC_WCS'"),
      card("BUNIT", "'adu'"),
      card("CTYPE1", "'RA---TAN'"),
      card("CTYPE2", "'DEC--TAN'"),
      card("CUNIT1", "'deg'"),
      card("CUNIT2", "'deg'"),
      card("RADESYS", "'ICRS'"),
      card("CRPIX1", "4.5"),
      card("CRPIX2", "4.5"),
      card("CRVAL1", "150.0"),
      card("CRVAL2", "-30.0"),
      card("CDELT1", "-0.0002777777777778"),
      card("CDELT2", "0.0002777777777778"),
      "END".padding(toLength: 80, withPad: " ", startingAt: 0),
    ]
    var header = Data(cards.joined().utf8)
    header.append(Data(repeating: 32, count: (2880 - header.count % 2880) % 2880))

    var pixels = Data()
    for index in 0..<64 {
      var bits = (index == 9 ? UInt32(0x7fc00000) : Float(index).bitPattern).bigEndian
      withUnsafeBytes(of: &bits) { pixels.append(contentsOf: $0) }
    }
    pixels.append(Data(repeating: 0, count: (2880 - pixels.count % 2880) % 2880))
    return header + pixels
  }

  private static func makePDF() -> Data {
    let content = """
    BT /F1 18 Tf 72 760 Td (Synthetic observing note) Tj
    /F1 11 Tf 0 -30 Td (Example only. No real observation or calibrated measurement.) Tj
    0 -20 Td (Inspect the extracted text before using a document result.) Tj ET
    """
    let stream = "<< /Length \(content.utf8.count) >>\nstream\n\(content)\nendstream"
    let objects = [
      "<< /Type /Catalog /Pages 2 0 R >>",
      "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
      stream,
      "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    var data = Data("%PDF-1.4\n".utf8)
    var offsets: [Int] = []
    for (index, object) in objects.enumerated() {
      offsets.append(data.count)
      data.append(Data("\(index + 1) 0 obj\n\(object)\nendobj\n".utf8))
    }
    let xrefOffset = data.count
    data.append(Data("xref\n0 \(objects.count + 1)\n0000000000 65535 f \n".utf8))
    for offset in offsets {
      data.append(Data(String(format: "%010d 00000 n \n", offset).utf8))
    }
    data.append(Data("trailer\n<< /Size \(objects.count + 1) /Root 1 0 R >>\nstartxref\n\(xrefOffset)\n%%EOF\n".utf8))
    return data
  }

  private static func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }
}
