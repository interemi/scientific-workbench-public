import Foundation
import ImageIO
import UniformTypeIdentifiers

enum PortableRunContent {
  enum Format: String, Codable, Sendable {
    case csv, tsv, ecsv, png
  }

  static func isShareableText(_ data: Data, secrets: [String]) -> Bool {
    guard let text = String(data: data, encoding: .utf8), !text.contains("\0"),
          SecretsRedactor.redact(text, secrets: secrets) == text else { return false }
    let privatePatterns = [
      #"(?m)(?:^|[\s"'\[({=,;])(?:~?/|file:/|[A-Za-z]:[\\/]|\\\\|\.{1,2}/)"#,
      #"(?i)\b(?:api[_ -]?key|authorization|access[_ -]?token|password|system[_ -]?prompt|user[_ -]?prompt|private[_ -]?prompt|prompt)\b["'\s,:=]"#,
      #"(?i)\b(?:bearer\s+\S+|sk-[a-z0-9_-]{12,}|gh[pousr]_[a-z0-9]{12,}|xox[baprs]-[a-z0-9-]{12,}|AIza[a-z0-9_-]{30,}|AKIA[A-Z0-9]{16})"#,
      #"(?i)-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----|://[^\s/@:]+:[^\s/@]+@"#,
    ]
    return privatePatterns.allSatisfy { text.range(of: $0, options: .regularExpression) == nil }
  }

  static func publicPNG(_ data: Data) -> Data? {
    guard let source = CGImageSourceCreateWithData(data as CFData, nil),
          CGImageSourceGetType(source) == UTType.png.identifier as CFString,
          CGImageSourceGetCount(source) == 1,
          let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
          let width = properties[kCGImagePropertyPixelWidth] as? Int, (1...4_096).contains(width),
          let height = properties[kCGImagePropertyPixelHeight] as? Int, (1...4_096).contains(height),
          width * height <= 8_388_608,
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { return nil }
    let output = NSMutableData()
    guard let destination = CGImageDestinationCreateWithData(output, UTType.png.identifier as CFString, 1, nil) else {
      return nil
    }
    // A new image starts with pixels and color information, without source metadata.
    CGImageDestinationAddImage(destination, image, nil)
    return CGImageDestinationFinalize(destination) ? output as Data : nil
  }
}
