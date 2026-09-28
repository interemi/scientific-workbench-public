#!/usr/bin/env swift
import AppKit
import Foundation

let rootURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true)
let resourcesURL = rootURL.appendingPathComponent("Resources", isDirectory: true)
let iconsetURL = resourcesURL.appendingPathComponent("AppIcon.iconset", isDirectory: true)
let icnsURL = resourcesURL.appendingPathComponent("AppIcon.icns")

try FileManager.default.createDirectory(at: resourcesURL, withIntermediateDirectories: true)
try? FileManager.default.removeItem(at: iconsetURL)
try FileManager.default.createDirectory(at: iconsetURL, withIntermediateDirectories: true)

struct IconOutput {
  let points: Int
  let scale: Int
  let filename: String

  var pixels: Int { points * scale }
}

let outputs = [
  IconOutput(points: 16, scale: 1, filename: "icon_16x16.png"),
  IconOutput(points: 16, scale: 2, filename: "icon_16x16@2x.png"),
  IconOutput(points: 32, scale: 1, filename: "icon_32x32.png"),
  IconOutput(points: 32, scale: 2, filename: "icon_32x32@2x.png"),
  IconOutput(points: 128, scale: 1, filename: "icon_128x128.png"),
  IconOutput(points: 128, scale: 2, filename: "icon_128x128@2x.png"),
  IconOutput(points: 256, scale: 1, filename: "icon_256x256.png"),
  IconOutput(points: 256, scale: 2, filename: "icon_256x256@2x.png"),
  IconOutput(points: 512, scale: 1, filename: "icon_512x512.png"),
  IconOutput(points: 512, scale: 2, filename: "icon_512x512@2x.png")
]

func scaled(_ value: CGFloat, for pixels: Int) -> CGFloat {
  value * CGFloat(pixels) / 1024.0
}

func roundedBar(x: CGFloat, y: CGFloat, width: CGFloat, height: CGFloat, radius: CGFloat) -> NSBezierPath {
  NSBezierPath(roundedRect: NSRect(x: x, y: y, width: width, height: height), xRadius: radius, yRadius: radius)
}

func makeIcon(pixels: Int) throws -> Data {
  let size = NSSize(width: pixels, height: pixels)
  guard let bitmap = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: pixels,
    pixelsHigh: pixels,
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0,
    bitsPerPixel: 0
  ) else {
    throw CocoaError(.featureUnsupported)
  }
  bitmap.size = size

  guard let graphicsContext = NSGraphicsContext(bitmapImageRep: bitmap) else {
    throw CocoaError(.featureUnsupported)
  }

  NSGraphicsContext.saveGraphicsState()
  NSGraphicsContext.current = graphicsContext
  defer { NSGraphicsContext.restoreGraphicsState() }

  guard let context = NSGraphicsContext.current?.cgContext else {
    throw CocoaError(.featureUnsupported)
  }

  context.clear(CGRect(origin: .zero, size: size))

  let inset = scaled(72, for: pixels)
  let corner = scaled(214, for: pixels)
  let iconRect = NSRect(x: inset, y: inset, width: CGFloat(pixels) - inset * 2, height: CGFloat(pixels) - inset * 2)
  let body = NSBezierPath(roundedRect: iconRect, xRadius: corner, yRadius: corner)
  body.addClip()

  let background = NSGradient(colors: [
    NSColor(calibratedRed: 0.055, green: 0.075, blue: 0.105, alpha: 1),
    NSColor(calibratedRed: 0.045, green: 0.20, blue: 0.24, alpha: 1),
    NSColor(calibratedRed: 0.075, green: 0.34, blue: 0.38, alpha: 1)
  ])!
  background.draw(in: iconRect, angle: -35)

  let glow = NSGradient(colors: [
    NSColor(calibratedRed: 0.28, green: 0.95, blue: 0.88, alpha: 0.0),
    NSColor(calibratedRed: 0.28, green: 0.95, blue: 0.88, alpha: 0.28)
  ])!
  glow.draw(fromCenter: NSPoint(x: scaled(720, for: pixels), y: scaled(720, for: pixels)),
            radius: scaled(20, for: pixels),
            toCenter: NSPoint(x: scaled(720, for: pixels), y: scaled(720, for: pixels)),
            radius: scaled(430, for: pixels),
            options: [])

  let orbit = NSBezierPath()
  orbit.move(to: NSPoint(x: scaled(210, for: pixels), y: scaled(435, for: pixels)))
  orbit.curve(
    to: NSPoint(x: scaled(825, for: pixels), y: scaled(600, for: pixels)),
    controlPoint1: NSPoint(x: scaled(350, for: pixels), y: scaled(720, for: pixels)),
    controlPoint2: NSPoint(x: scaled(640, for: pixels), y: scaled(755, for: pixels))
  )
  NSColor(calibratedRed: 0.70, green: 0.98, blue: 0.94, alpha: 0.72).setStroke()
  orbit.lineWidth = scaled(30, for: pixels)
  orbit.lineCapStyle = .round
  orbit.stroke()

  let secondOrbit = NSBezierPath()
  secondOrbit.move(to: NSPoint(x: scaled(260, for: pixels), y: scaled(300, for: pixels)))
  secondOrbit.curve(
    to: NSPoint(x: scaled(782, for: pixels), y: scaled(720, for: pixels)),
    controlPoint1: NSPoint(x: scaled(420, for: pixels), y: scaled(150, for: pixels)),
    controlPoint2: NSPoint(x: scaled(690, for: pixels), y: scaled(190, for: pixels))
  )
  NSColor(calibratedRed: 0.36, green: 0.80, blue: 1.0, alpha: 0.52).setStroke()
  secondOrbit.lineWidth = scaled(22, for: pixels)
  secondOrbit.lineCapStyle = .round
  secondOrbit.stroke()

  let chartColor = NSColor(calibratedRed: 0.92, green: 1.0, blue: 0.98, alpha: 0.92)
  chartColor.setFill()
  let barRadius = scaled(22, for: pixels)
  [
    NSRect(x: scaled(315, for: pixels), y: scaled(282, for: pixels), width: scaled(74, for: pixels), height: scaled(230, for: pixels)),
    NSRect(x: scaled(458, for: pixels), y: scaled(282, for: pixels), width: scaled(74, for: pixels), height: scaled(350, for: pixels)),
    NSRect(x: scaled(601, for: pixels), y: scaled(282, for: pixels), width: scaled(74, for: pixels), height: scaled(470, for: pixels))
  ].forEach { rect in
    roundedBar(x: rect.origin.x, y: rect.origin.y, width: rect.width, height: rect.height, radius: barRadius).fill()
  }

  NSColor(calibratedRed: 0.70, green: 0.98, blue: 0.94, alpha: 0.95).setFill()
  for point in [
    NSPoint(x: scaled(770, for: pixels), y: scaled(598, for: pixels)),
    NSPoint(x: scaled(284, for: pixels), y: scaled(404, for: pixels)),
    NSPoint(x: scaled(708, for: pixels), y: scaled(738, for: pixels))
  ] {
    NSBezierPath(ovalIn: NSRect(x: point.x - scaled(24, for: pixels), y: point.y - scaled(24, for: pixels), width: scaled(48, for: pixels), height: scaled(48, for: pixels))).fill()
  }

  context.resetClip()
  NSColor.white.withAlphaComponent(0.20).setStroke()
  body.lineWidth = scaled(8, for: pixels)
  body.stroke()

  guard let png = bitmap.representation(using: .png, properties: [:]) else {
    throw CocoaError(.fileWriteUnknown)
  }
  return png
}

for output in outputs {
  let data = try makeIcon(pixels: output.pixels)
  try data.write(to: iconsetURL.appendingPathComponent(output.filename))
}

try? FileManager.default.removeItem(at: icnsURL)
let process = Process()
process.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
process.arguments = ["-c", "icns", iconsetURL.path, "-o", icnsURL.path]
try process.run()
process.waitUntilExit()

guard process.terminationStatus == 0 else {
  throw CocoaError(.fileWriteUnknown)
}

print("Wrote \(icnsURL.path)")
