import AppKit

let size: CGFloat = 180
let bitmap = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: Int(size),
    pixelsHigh: Int(size),
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0,
    bitsPerPixel: 0
)!
bitmap.size = NSSize(width: size, height: size)
let context = NSGraphicsContext(bitmapImageRep: bitmap)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = context

NSColor(
    calibratedRed: 246 / 255,
    green: 244 / 255,
    blue: 238 / 255,
    alpha: 1
).setFill()
NSRect(x: 0, y: 0, width: size, height: size).fill()

let emoji = "🐹" as NSString
let attributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: 108)
]
let textSize = emoji.size(withAttributes: attributes)
emoji.draw(
    at: NSPoint(
        x: (size - textSize.width) / 2,
        y: (size - textSize.height) / 2
    ),
    withAttributes: attributes
)

context.flushGraphics()
NSGraphicsContext.restoreGraphicsState()
let png = bitmap.representation(using: .png, properties: [:])!
let output = CommandLine.arguments.dropFirst().first ?? "app/static/apple-touch-icon.png"
try png.write(to: URL(fileURLWithPath: output))
