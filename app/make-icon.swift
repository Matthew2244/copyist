// make-icon.swift — draws Copyist's app icon from code, no design
// tool needed: the dark-stage gradient, a faint staff, and a single
// warm note. Run: swift app/make-icon.swift <out.iconset>
import AppKit

let outDir = CommandLine.arguments.count > 1
    ? CommandLine.arguments[1] : "Copyist.iconset"
try? FileManager.default.createDirectory(
    atPath: outDir, withIntermediateDirectories: true)

func draw(_ px: Int) -> NSBitmapImageRep {
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
        isPlanar: false, colorSpaceName: .deviceRGB,
        bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let s = CGFloat(px)
    let inset = s * 0.085
    let rect = NSRect(x: inset, y: inset,
                      width: s - 2 * inset, height: s - 2 * inset)
    let shape = NSBezierPath(roundedRect: rect,
                             xRadius: s * 0.2, yRadius: s * 0.2)
    NSGradient(colors: [
        NSColor(red: 0.16, green: 0.19, blue: 0.30, alpha: 1),
        NSColor(red: 0.05, green: 0.06, blue: 0.10, alpha: 1),
    ])!.draw(in: shape, angle: -65)

    shape.addClip()
    NSColor(white: 1, alpha: 0.20).setStroke()
    for i in 0..<5 {
        let y = rect.minY + rect.height * (0.26 + CGFloat(i) * 0.115)
        let line = NSBezierPath()
        line.move(to: NSPoint(x: rect.minX + rect.width * 0.10, y: y))
        line.line(to: NSPoint(x: rect.maxX - rect.width * 0.10, y: y))
        line.lineWidth = max(0.5, s * 0.010)
        line.stroke()
    }

    let font = NSFont.systemFont(ofSize: s * 0.62, weight: .bold)
    let note = NSAttributedString(string: "♪", attributes: [
        .font: font,
        .foregroundColor: NSColor(red: 1.0, green: 0.71,
                                  blue: 0.33, alpha: 1),
    ])
    let sz = note.size()
    let shadow = NSShadow()
    shadow.shadowColor = NSColor(white: 0, alpha: 0.5)
    shadow.shadowBlurRadius = s * 0.02
    shadow.shadowOffset = NSSize(width: 0, height: -s * 0.008)
    shadow.set()
    note.draw(at: NSPoint(x: rect.midX - sz.width / 2,
                          y: rect.midY - sz.height / 2 + s * 0.015))
    NSGraphicsContext.restoreGraphicsState()
    return rep
}

func write(_ px: Int, _ name: String) {
    let rep = draw(px)
    let data = rep.representation(using: .png, properties: [:])!
    try! data.write(to: URL(fileURLWithPath: outDir + "/" + name))
}

for base in [16, 32, 128, 256, 512] {
    write(base, "icon_\(base)x\(base).png")
    write(base * 2, "icon_\(base)x\(base)@2x.png")
}
print("icon drawn into \(outDir)")
