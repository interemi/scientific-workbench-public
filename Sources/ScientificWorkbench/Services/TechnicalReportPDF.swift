import CoreGraphics
import CoreText
import Foundation

enum TechnicalReportPDF {
  enum Unavailable: LocalizedError {
    case source, rendering

    var errorDescription: String? {
      switch self {
      case .source: "Choose a supported Scientific Workbench report Markdown source."
      case .rendering: "The report could not be laid out within the PDF page limit."
      }
    }
  }

  static let heading = "# Scientific Workbench technical report"
  static let maximumSourceBytes = 160 * 1_024

  static func render(markdown: String) throws -> Data {
    guard markdown.hasPrefix(heading + "\n"), markdown.utf8.count <= maximumSourceBytes,
          !markdown.contains("\0") else { throw Unavailable.source }
    let result = NSMutableData()
    guard let consumer = CGDataConsumer(data: result) else { throw Unavailable.rendering }
    var pageBounds = CGRect(x: 0, y: 0, width: 595.28, height: 841.89)
    let metadata = [
      kCGPDFContextTitle as String: "Scientific Workbench technical report",
      kCGPDFContextCreator as String: "Scientific Workbench",
    ]
    guard let context = CGContext(consumer: consumer, mediaBox: &pageBounds, metadata as CFDictionary) else {
      throw Unavailable.rendering
    }
    let (document, headings) = styled(markdown)
    let frameSetter = CTFramesetterCreateWithAttributedString(document)
    let body = CGPath(rect: pageBounds.insetBy(dx: 48, dy: 56), transform: nil)

    var offset = 0
    var page = 1
    while offset < document.length {
      try Task.checkCancellation()
      guard page <= 24 else { throw Unavailable.rendering }
      var frame = CTFramesetterCreateFrame(frameSetter, CFRange(location: offset, length: 0), body, nil)
      var visible = CTFrameGetVisibleStringRange(frame)
      let end = visible.location + visible.length
      if let orphan = headings.first(where: { $0.heading > offset && $0.heading < end && $0.content >= end }) {
        frame = CTFramesetterCreateFrame(frameSetter, CFRange(location: offset, length: orphan.heading - offset), body, nil)
        visible = CTFrameGetVisibleStringRange(frame)
      }
      guard visible.length > 0 else { throw Unavailable.rendering }
      context.beginPDFPage(nil)
      context.textMatrix = .identity
      context.saveGState()
      CTFrameDraw(frame, context)
      context.restoreGState()
      context.textMatrix = .identity

      context.setStrokeColor(CGColor(gray: 0.79, alpha: 1))
      context.setLineWidth(0.5)
      context.move(to: CGPoint(x: 48, y: 42))
      context.addLine(to: CGPoint(x: pageBounds.width - 48, y: 42))
      context.strokePath()
      let footer = NSAttributedString(string: "Scientific Workbench  |  \(page)", attributes: attributes(font: regular, size: 8, ink: muted))
      context.textPosition = CGPoint(x: 48, y: 28)
      CTLineDraw(CTLineCreateWithAttributedString(footer), context)
      context.endPDFPage()
      page += 1
      offset = visible.location + visible.length
    }
    context.closePDF()
    return result as Data
  }

  private static let regular = "Helvetica"
  private static let bold = "Helvetica-Bold"
  private static let ink = CGColor(red: 0.10, green: 0.14, blue: 0.19, alpha: 1)
  private static let accent = CGColor(red: 0.06, green: 0.31, blue: 0.34, alpha: 1)
  private static let muted = CGColor(red: 0.28, green: 0.34, blue: 0.39, alpha: 1)

  private static func attributes(font: String, size: CGFloat, ink: CGColor) -> [NSAttributedString.Key: Any] {
    [
      NSAttributedString.Key(kCTFontAttributeName as String): CTFontCreateWithName(font as CFString, size, nil),
      NSAttributedString.Key(kCTForegroundColorAttributeName as String): ink,
    ]
  }

  private static func styled(_ markdown: String) -> (NSAttributedString, [(heading: Int, content: Int)]) {
    let text = NSMutableAttributedString(string: "")
    var pending: [Int] = []
    var headings: [(heading: Int, content: Int)] = []
    for line in markdown.split(separator: "\n", omittingEmptySubsequences: false) {
      let content: String
      let style: [NSAttributedString.Key: Any]
      if line.hasPrefix("# ") {
        pending.append(text.length)
        content = String(line.dropFirst(2))
        style = attributes(font: bold, size: 19, ink: ink)
      } else if line.hasPrefix("## ") {
        pending.append(text.length)
        content = String(line.dropFirst(3))
        style = attributes(font: bold, size: 13, ink: accent)
      } else if line.hasPrefix("### ") {
        pending.append(text.length)
        content = String(line.dropFirst(4))
        style = attributes(font: bold, size: 10.5, ink: accent)
      } else {
        if !line.isEmpty && !pending.isEmpty {
          headings += pending.map { ($0, text.length) }
          pending.removeAll(keepingCapacity: true)
        }
        content = String(line)
        style = attributes(font: regular, size: line.isEmpty ? 5 : 10.5, ink: ink)
      }
      text.append(NSAttributedString(string: content + "\n", attributes: style))
    }
    return (text, headings)
  }
}
