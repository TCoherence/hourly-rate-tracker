import AppKit
import ImageIO
import UniformTypeIdentifiers

// A conceptual illustration, not a screen recording. All figures are fictional.
let width = 960, height = 540
let destination = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "docs/assets/how-it-works.gif")
func color(_ hex: UInt32) -> NSColor {
    NSColor(calibratedRed: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255, blue: CGFloat(hex & 255) / 255, alpha: 1)
}
// Match the app's dark theme so the animation sits naturally beside the screenshot.
let paper = color(0x201E1A), ink = color(0xEEE8DD), muted = color(0xAAA397)
let red = color(0xF3A08B), border = color(0x484137), card = color(0x28251F)
let highlight = color(0x362621), highlightBorder = color(0x69433B)
func box(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ radius: CGFloat, _ fill: NSColor, _ stroke: NSColor? = nil) {
    let path = NSBezierPath(roundedRect: NSRect(x: x, y: y, width: w, height: h), xRadius: radius, yRadius: radius)
    fill.setFill(); path.fill()
    if let stroke { stroke.setStroke(); path.lineWidth = 1.2; path.stroke() }
}
func txt(_ text: String, _ x: CGFloat, _ y: CGFloat, _ size: CGFloat, _ c: NSColor, _ weight: NSFont.Weight = .regular) {
    let font = NSFont.systemFont(ofSize: size, weight: weight)
    (text as NSString).draw(at: NSPoint(x:x, y:y), withAttributes: [.font:font, .foregroundColor:c])
}
func render(_ hours: Int) -> CGImage {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    rep.size = NSSize(width: width, height: height)
    NSGraphicsContext.saveGraphicsState(); let ctx = NSGraphicsContext(bitmapImageRep: rep)!; NSGraphicsContext.current = ctx
    paper.setFill(); NSRect(x:0,y:0,width:width,height:height).fill()
    box(32, 31, 896, 478, 18, card, border)
    box(57, 456, 14, 14, 4, red); txt("工作占用", 82, 450, 19, ink, .bold)
    txt("LOCAL FIRST  ·  CONCEPT DEMO", 618, 454, 11, muted, .medium)
    box(57, 411, 846, 1, 0, border)
    txt("感觉这周没怎么加班？", 57, 357, 29, ink, .bold)
    txt("让数据帮你回忆一下。", 57, 327, 15, muted)
    box(57, 111, 413, 185, 12, highlight, highlightBorder)
    txt("实际时薪", 79, 257, 15, muted, .semibold)
    let rate = hours == 8 ? "$100" : "$80"
    txt(rate, 75, 181, 56, red, .bold); txt("/ 小时", 245, 186, 13, muted)
    txt("$800 ÷ \(hours) 小时", 79, 137, 15, red, .medium)
    box(488, 111, 415, 185, 12, card, border)
    txt("记录的工时", 511, 257, 15, muted, .semibold)
    txt("\(hours)", 506, 181, 56, ink, .bold); txt("小时", 589, 186, 13, muted)
    txt(hours == 8 ? "工作日 8 小时" : "工作日 8 小时 + 周末 2 小时", 511, 137, 14, muted)
    txt("纯属虚构的示意动画 · VPN 连接不等于正在工作", 57, 65, 12, muted)
    NSGraphicsContext.restoreGraphicsState()
    return rep.cgImage!
}
guard let gif = CGImageDestinationCreateWithURL(destination as CFURL, UTType.gif.identifier as CFString, 2, nil) else { fatalError("Cannot create GIF") }
CGImageDestinationSetProperties(gif, [kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFLoopCount: 0]] as CFDictionary)
for h in [8, 10] {
    CGImageDestinationAddImage(gif, render(h), [kCGImagePropertyGIFDictionary: [kCGImagePropertyGIFDelayTime: 2.5]] as CFDictionary)
}
guard CGImageDestinationFinalize(gif) else { fatalError("Cannot write GIF") }
print("Created \(destination.path) (fictional concept animation)")
