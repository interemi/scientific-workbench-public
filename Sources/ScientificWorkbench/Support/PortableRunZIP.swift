import Foundation
import zlib

/// The portable package uses a bounded ZIP with stored regular files.
/// Reading the directory validates the whole archive without extraction.
enum PortableRunZIP {
  enum Invalid: LocalizedError, Equatable {
    case archive
    case size

    var errorDescription: String? {
      switch self {
      case .archive: "The ZIP does not have the Scientific Workbench portable archive structure."
      case .size: "The package exceeds the portable archive size limit."
      }
    }
  }

  static let maximumArchiveBytes = 32 * 1_024 * 1_024
  static let maximumMemberBytes = 8 * 1_024 * 1_024
  static let maximumMembers = 32

  private static let localSignature: UInt32 = 0x04034b50
  private static let centralSignature: UInt32 = 0x02014b50
  private static let endSignature: UInt32 = 0x06054b50
  private static let storedVersion: UInt16 = 20
  private static let dosDate: UInt16 = 33 // 1980-01-01

  static func encode(_ files: [String: Data]) throws -> Data {
    guard !files.isEmpty, files.count <= maximumMembers else { throw Invalid.size }
    let names = files.keys.sorted()
    guard names.allSatisfy(validName), Set(names.map { $0.lowercased() }).count == names.count else { throw Invalid.archive }
    var archive = Data()
    var directory = Data()
    for name in names {
      try Task.checkCancellation()
      guard let data = files[name], data.count <= maximumMemberBytes,
            archive.count + directory.count + data.count + 76 + 2 * name.utf8.count + 22 <= maximumArchiveBytes else {
        throw Invalid.size
      }
      let bytes = Data(name.utf8)
      let offset = UInt32(archive.count)
      let crc = checksum(data)
      let size = UInt32(data.count)

      archive.put(localSignature)
      writeFileFields(to: &archive, crc: crc, size: size, nameLength: bytes.count)
      archive.append(bytes)
      archive.append(data)

      directory.put(centralSignature)
      directory.put(storedVersion)
      writeFileFields(to: &directory, crc: crc, size: size, nameLength: bytes.count)
      directory.put(UInt16(0)) // comment length
      directory.put(UInt16(0)) // disk
      directory.put(UInt16(0)) // internal attributes
      directory.put(UInt32(0)) // platform attributes
      directory.put(offset)
      directory.append(bytes)
    }
    let directoryStart = UInt32(archive.count)
    archive.append(directory)
    archive.put(endSignature)
    archive.put(UInt16(0))
    archive.put(UInt16(0))
    archive.put(UInt16(names.count))
    archive.put(UInt16(names.count))
    archive.put(UInt32(directory.count))
    archive.put(directoryStart)
    archive.put(UInt16(0))
    return archive
  }

  static func decode(_ archive: Data) throws -> [String: Data] {
    guard archive.count <= maximumArchiveBytes else { throw Invalid.size }
    let bytes = Data(archive)
    let end = bytes.count - 22
    guard end >= 0, try bytes.get32(end) == endSignature,
          try bytes.get16(end + 4) == 0, try bytes.get16(end + 6) == 0,
          try bytes.get16(end + 20) == 0 else { throw Invalid.archive }
    let count = Int(try bytes.get16(end + 10))
    let start = Int(try bytes.get32(end + 16))
    guard count > 0, count <= maximumMembers, try bytes.get16(end + 8) == count,
          start <= end, Int(try bytes.get32(end + 12)) == end - start else { throw Invalid.archive }

    var position = start
    var nextLocal = 0
    var names: Set<String> = []
    var files: [String: Data] = [:]
    for _ in 0..<count {
      try Task.checkCancellation()
      guard position + 46 <= end, try bytes.get32(position) == centralSignature,
            try bytes.get16(position + 4) == storedVersion,
            try bytes.get16(position + 32) == 0, try bytes.get16(position + 34) == 0,
            try bytes.get16(position + 36) == 0, try bytes.get32(position + 38) == 0,
            Int(try bytes.get32(position + 42)) == nextLocal else { throw Invalid.archive }
      let fields = try readFileFields(bytes, at: position + 6)
      let nameStart = position + 46
      let nameEnd = nameStart + fields.nameLength
      guard nameEnd <= end,
            let name = String(data: bytes.subdata(in: nameStart..<nameEnd), encoding: .utf8), validName(name),
            names.insert(name.lowercased()).inserted,
            nextLocal + 30 <= start, try bytes.get32(nextLocal) == localSignature,
            try readFileFields(bytes, at: nextLocal + 4) == fields else { throw Invalid.archive }
      let localName = nextLocal + 30
      let payload = localName + fields.nameLength
      let payloadEnd = payload + fields.size
      guard payloadEnd <= start,
            bytes.subdata(in: localName..<payload) == bytes.subdata(in: nameStart..<nameEnd) else { throw Invalid.archive }
      let data = bytes.subdata(in: payload..<payloadEnd)
      guard checksum(data) == fields.crc else { throw Invalid.archive }
      files[name] = data
      nextLocal = payloadEnd
      position = nameEnd
    }
    guard nextLocal == start, position == end else { throw Invalid.archive }
    return files
  }

  private struct FileFields: Equatable {
    let crc: UInt32
    let size: Int
    let nameLength: Int
  }

  private static func writeFileFields(to bytes: inout Data, crc: UInt32, size: UInt32, nameLength: Int) {
    bytes.put(storedVersion)
    bytes.put(UInt16(0)) // flags
    bytes.put(UInt16(0)) // stored
    bytes.put(UInt16(0)) // time
    bytes.put(dosDate)
    bytes.put(crc)
    bytes.put(size)
    bytes.put(size)
    bytes.put(UInt16(nameLength))
    bytes.put(UInt16(0)) // extra length
  }

  private static func readFileFields(_ bytes: Data, at start: Int) throws -> FileFields {
    guard try bytes.get16(start) == storedVersion, try bytes.get16(start + 2) == 0,
          try bytes.get16(start + 4) == 0, try bytes.get16(start + 24) == 0 else { throw Invalid.archive }
    let size = try bytes.get32(start + 14)
    let nameLength = Int(try bytes.get16(start + 22))
    guard size <= maximumMemberBytes, try bytes.get32(start + 18) == size,
          (1...96).contains(nameLength) else { throw Invalid.archive }
    return FileFields(crc: try bytes.get32(start + 10), size: Int(size), nameLength: nameLength)
  }

  private static func validName(_ name: String) -> Bool {
    name.utf8.count <= 96 && name.range(
      of: #"\A[a-z0-9][a-z0-9_.-]*(?:/[a-z0-9][a-z0-9_.-]*)*\z"#,
      options: .regularExpression
    ) != nil
  }

  private static func checksum(_ data: Data) -> UInt32 {
    data.withUnsafeBytes { bytes in
      UInt32(truncatingIfNeeded: crc32(0, bytes.bindMemory(to: UInt8.self).baseAddress, uInt(bytes.count)))
    }
  }
}

private extension Data {
  mutating func put<T: FixedWidthInteger>(_ value: T) {
    var littleEndian = value.littleEndian
    Swift.withUnsafeBytes(of: &littleEndian) { append(contentsOf: $0) }
  }

  func get16(_ offset: Int) throws -> UInt16 { try getInteger(offset) }
  func get32(_ offset: Int) throws -> UInt32 { try getInteger(offset) }

  private func getInteger<T: FixedWidthInteger>(_ offset: Int) throws -> T {
    guard offset >= 0, offset <= count - MemoryLayout<T>.size else { throw PortableRunZIP.Invalid.archive }
    return withUnsafeBytes { T(littleEndian: $0.loadUnaligned(fromByteOffset: offset, as: T.self)) }
  }
}
