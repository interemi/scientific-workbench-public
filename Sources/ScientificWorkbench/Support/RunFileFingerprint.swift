import CryptoKit
import Darwin
import Foundation

struct RunFileFingerprint: Codable, Equatable, Sendable {
  static let defaultReadBudget: Int64 = 64 * 1_024 * 1_024

  enum State: String, Codable, Sendable {
    case recorded, missing, directory, unsupported, unreadable, changed
    case overBudget = "over_budget"
  }

  let state: State
  let byteCount: Int64?
  let sha256: String?

  static func read(_ url: URL, maximumBytes: Int64) -> Self {
    measure(url, maximumBytes: maximumBytes, observe: nil)
  }

  static func readSample(
    _ url: URL, maximumBytes: Int64, range: Range<Int64>
  ) -> (fingerprint: Self, bytes: Data, information: stat?) {
    var sample = Data()
    var information: stat?
    let fingerprint = measure(url, maximumBytes: maximumBytes, capturedInformation: { information = $0 }) { offset, data in
      try Task.checkCancellation()
      let lower = max(range.lowerBound, offset)
      let upper = min(range.upperBound, offset + Int64(data.count))
      if lower < upper {
        sample.append(data[Int(lower - offset)..<Int(upper - offset)])
      }
    }
    return (fingerprint, fingerprint.state == .recorded ? sample : Data(), information)
  }

  private static func measure(
    _ url: URL, maximumBytes: Int64, capturedInformation: ((stat) -> Void)? = nil,
    observe: ((Int64, Data) throws -> Void)?
  ) -> Self {
    var before = stat()
    guard lstat(url.path, &before) == 0 else {
      return Self(state: errno == ENOENT ? .missing : .unreadable, byteCount: nil, sha256: nil)
    }
    let fileType = before.st_mode & S_IFMT
    guard fileType == S_IFREG else {
      return Self(state: fileType == S_IFDIR ? .directory : .unsupported, byteCount: nil, sha256: nil)
    }
    let size = before.st_size
    guard size >= 0, size <= maximumBytes else {
      return Self(state: .overBudget, byteCount: size, sha256: nil)
    }

    let descriptor = open(url.path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)
    guard descriptor >= 0 else {
      return Self(state: .unreadable, byteCount: size, sha256: nil)
    }
    let file = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
    defer { try? file.close() }
    var opened = stat()
    guard fstat(descriptor, &opened) == 0, matches(before, opened) else {
      return Self(state: .changed, byteCount: size, sha256: nil)
    }

    var hasher = SHA256()
    var consumed: Int64 = 0
    do {
      while consumed < size {
        let count = Int(min(65_536, size - consumed))
        guard let data = try file.read(upToCount: count), !data.isEmpty else { break }
        hasher.update(data: data)
        try observe?(consumed, data)
        consumed += Int64(data.count)
      }
    } catch {
      return Self(state: .unreadable, byteCount: size, sha256: nil)
    }
    var after = stat()
    var retained = stat()
    guard consumed == size, fstat(descriptor, &after) == 0, lstat(url.path, &retained) == 0,
          matches(before, after), matches(before, retained) else {
      return Self(state: .changed, byteCount: size, sha256: nil)
    }

    capturedInformation?(before)
    return Self(
      state: .recorded, byteCount: consumed,
      sha256: hasher.finalize().map { String(format: "%02x", $0) }.joined()
    )
  }

  private static func matches(_ first: stat, _ second: stat) -> Bool {
    first.st_dev == second.st_dev && first.st_ino == second.st_ino
      && first.st_mode == second.st_mode && first.st_size == second.st_size
      && first.st_mtimespec.tv_sec == second.st_mtimespec.tv_sec
      && first.st_mtimespec.tv_nsec == second.st_mtimespec.tv_nsec
      && first.st_ctimespec.tv_sec == second.st_ctimespec.tv_sec
      && first.st_ctimespec.tv_nsec == second.st_ctimespec.tv_nsec
  }
}
