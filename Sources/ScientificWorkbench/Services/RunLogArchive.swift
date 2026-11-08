import Darwin
import Foundation

struct RunLogArchive: Sendable {
  static let chunkBytes = 64 * 1024

  private let directory: FileHandle?
  private let initialSecrets: [String]
  let currentSecrets: @Sendable () async -> [String]

  init(
    runDirectory: String, secrets: [String],
    currentSecrets: @escaping @Sendable () async -> [String] = { [] }
  ) {
    let descriptor = open(runDirectory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
    directory = descriptor >= 0 ? FileHandle(fileDescriptor: descriptor, closeOnDealloc: true) : nil
    initialSecrets = secrets
    self.currentSecrets = currentSecrets
  }

  func retain(
    from source: URL, stream: RunLogStream, maximumInputBytes: Int, maximumExcerptBytes: Int,
    additionalSecrets: [String]
  ) -> BoundedProcessOutput? {
    guard let directory else { return nil }
    let inputDescriptor = open(source.path, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC)
    guard inputDescriptor >= 0 else { return nil }
    let input = FileHandle(fileDescriptor: inputDescriptor, closeOnDealloc: true)
    defer { try? input.close() }
    var info = stat()
    guard fstat(inputDescriptor, &info) == 0, info.st_mode & S_IFMT == S_IFREG else { return nil }
    let root = directory.fileDescriptor
    let temporaryName = ".run-log-\(UUID().uuidString).tmp"
    let descriptor = openat(root, temporaryName, O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC, 0o600)
    guard descriptor >= 0 else { return nil }
    let output = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
    defer {
      try? output.close()
      _ = unlinkat(root, temporaryName, 0)
    }

    do {
      let sourceSize = try input.seekToEnd()
      try input.seek(toOffset: 0)
      let limit = Int(min(sourceSize, UInt64(maximumInputBytes)))
      let inputWasLimited = sourceSize > limit
      var remaining = limit
      var redactor = ChunkedLogRedactor(secrets: initialSecrets + additionalSecrets)
      while remaining > 0 {
        let read = try autoreleasepool {
          guard let block = try input.read(upToCount: min(remaining, Self.chunkBytes)), !block.isEmpty else {
            return 0
          }
          try output.write(contentsOf: redactor.consume(block))
          return block.count
        }
        guard read > 0 else { return nil }
        remaining -= read
      }
      if inputWasLimited {
        // Keep the withheld boundary bytes private when a secret could cross the capture limit.
        let notice = "\n[Scientific Workbench retained a bounded prefix because this stream exceeded its output limit.]\n"
        try output.write(contentsOf: Data(notice.utf8))
      } else {
        try output.write(contentsOf: redactor.consume(Data(), final: true))
      }

      guard let excerpt = BoundedProcessOutput.read(from: output, maximumBytes: maximumExcerptBytes),
            renameat(root, temporaryName, root, stream.fileName) == 0 else { return nil }
      return BoundedProcessOutput(
        text: excerpt.text,
        totalBytes: Int(sourceSize),
        wasTruncated: excerpt.wasTruncated || inputWasLimited
      )
    } catch {
      return nil
    }
  }
}

private struct ChunkedLogRedactor {
  private let patterns: [String]
  private let lookahead: Int
  private var pending = Data()

  init(secrets: [String]) {
    patterns = Array(Set(SecretsRedactor.applicableSecrets(secrets)))
    // A canonical spelling can use different scalars and UTF-8 widths.
    let longest = patterns.map { $0.decomposedStringWithCanonicalMapping.unicodeScalars.count }.max() ?? 0
    lookahead = max(0, longest * 4 - 1)
  }

  mutating func consume(_ block: Data, final: Bool = false) -> Data {
    if patterns.isEmpty { return block }
    pending.append(block)
    let undecoded = final ? Data() : Data(pending.suffix(incompleteScalarBytes()))
    let text = String(decoding: pending.dropLast(undecoded.count), as: UTF8.self)
    let bytes = text.utf8
    var boundary = final ? bytes.endIndex
      : bytes.index(bytes.endIndex, offsetBy: -lookahead, limitedBy: bytes.startIndex) ?? bytes.startIndex
    while boundary != bytes.startIndex, boundary != bytes.endIndex, bytes[boundary] & 0xC0 == 0x80 {
      bytes.formIndex(before: &boundary)
    }
    var cursor = bytes.startIndex
    var matches = patterns.map { text.range(of: $0) }
    var output = Data()

    while let match = matches.compactMap({ $0 }).min(by: { lhs, rhs in
      lhs.lowerBound == rhs.lowerBound ? lhs.upperBound > rhs.upperBound : lhs.lowerBound < rhs.lowerBound
    }), match.lowerBound < boundary {
      output.append(contentsOf: bytes[cursor..<match.lowerBound])
      output.append(contentsOf: SecretsRedactor.replacement.utf8)
      cursor = match.upperBound
      for index in matches.indices {
        if let next = matches[index], next.lowerBound < cursor {
          matches[index] = text.range(of: patterns[index], range: cursor..<text.endIndex)
        }
      }
    }
    let consumed = max(cursor, boundary)
    output.append(contentsOf: bytes[cursor..<consumed])
    pending = Data(bytes[consumed...])
    pending.append(undecoded)
    return output
  }

  private func incompleteScalarBytes() -> Int {
    guard !pending.isEmpty else { return 0 }
    var lead = pending.endIndex - 1
    while lead > pending.startIndex, pending.endIndex - lead < 4, pending[lead] & 0xC0 == 0x80 {
      lead -= 1
    }
    let width: Int
    switch pending[lead] {
    case 0xC2...0xDF: width = 2
    case 0xE0...0xEF: width = 3
    case 0xF0...0xF4: width = 4
    default: return 0
    }
    let available = pending.endIndex - lead
    return available < width ? available : 0
  }
}
