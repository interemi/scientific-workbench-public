import Darwin
import Foundation

struct BoundedProcessOutput: Sendable {
  let text: String
  let totalBytes: Int
  let wasTruncated: Bool

  static let empty = BoundedProcessOutput(text: "", totalBytes: 0, wasTruncated: false)

  static func read(at url: URL, maximumBytes: Int) -> BoundedProcessOutput? {
    let descriptor = open(url.path, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC)
    guard descriptor >= 0 else { return nil }
    let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
    defer { try? handle.close() }
    return read(from: handle, maximumBytes: maximumBytes)
  }

  static func read(from handle: FileHandle, maximumBytes: Int) -> BoundedProcessOutput? {
    var info = stat()
    guard fstat(handle.fileDescriptor, &info) == 0, info.st_mode & S_IFMT == S_IFREG else { return nil }
    let byteCount = Int(info.st_size)
    guard byteCount > 0 else { return .empty }

    do {
      try handle.seek(toOffset: 0)
      if byteCount <= maximumBytes {
        let data = try handle.read(upToCount: byteCount) ?? Data()
        return BoundedProcessOutput(
          text: String(decoding: data, as: UTF8.self), totalBytes: byteCount, wasTruncated: false
        )
      }

      let headBytes = maximumBytes / 4
      let tailBytes = maximumBytes - headBytes
      let head = try handle.read(upToCount: headBytes) ?? Data()
      try handle.seek(toOffset: UInt64(byteCount - tailBytes))
      let tail = try handle.read(upToCount: tailBytes) ?? Data()
      let omittedBytes = byteCount - maximumBytes
      let marker = "\n\n[Scientific Workbench truncated \(omittedBytes) output bytes; showing the beginning and end.]\n\n"
      return BoundedProcessOutput(
        text: String(decoding: head, as: UTF8.self) + marker + String(decoding: tail, as: UTF8.self),
        totalBytes: byteCount,
        wasTruncated: true
      )
    } catch {
      return nil
    }
  }
}
