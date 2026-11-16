import Foundation

enum RunLogStream: String, Sendable {
  case stdout
  case stderr

  var fileName: String { "\(rawValue).txt" }

  func output(in job: JobRecord) -> String {
    switch self {
    case .stdout: job.stdout
    case .stderr: job.stderr
    }
  }
}

struct RunLogExcerpt {
  static let maximumBytes = 16 * 1024
  static let maximumLines = 120

  let text: String
  let isTruncated: Bool

  init(_ output: String) {
    let bytes = output.utf8
    var start = bytes.index(bytes.endIndex, offsetBy: -Self.maximumBytes, limitedBy: bytes.startIndex)
      ?? bytes.startIndex
    let clippedBytes = start != bytes.startIndex
    while start != bytes.endIndex, bytes[start] & 0xC0 == 0x80 {
      bytes.formIndex(after: &start)
    }
    let tail = String(decoding: bytes[start...], as: UTF8.self)
    let lines = tail.split(omittingEmptySubsequences: false, whereSeparator: \.isNewline)
    let end = lines.last?.isEmpty == true ? lines.count - 1 : lines.count
    let startLine = max(clippedBytes && end > 1 ? 1 : 0, end - Self.maximumLines)
    isTruncated = clippedBytes || startLine > 0
    text = isTruncated && startLine < lines.count ? String(tail[lines[startLine].startIndex...]) : tail
  }
}
