import AppKit

func render(staff: Bool, splash: Bool) throws {
    let size = splash ? 2732 : 1024
    let context = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: size * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: false)
    let color = staff ? NSColor(srgbRed: 0.15, green: 0.22, blue: 0.32, alpha: 1) : NSColor(srgbRed: 0.14, green: 0.36, blue: 0.29, alpha: 1)
    (splash ? NSColor(srgbRed: 0.973, green: 0.977, blue: 0.961, alpha: 1) : color).setFill()
    NSBezierPath(rect: NSRect(x: 0, y: 0, width: size, height: size)).fill()
    let transform = AffineTransform(translationByX: CGFloat(size) / 2, byY: CGFloat(size) / 2)
    var t = transform
    let scale: CGFloat = splash ? 14 : 25.6
    t.scale(x: scale, y: -scale)
    t.translate(x: -20, y: -20)
    NSAffineTransform(transform: t).concat()
    if splash { color.setFill(); NSBezierPath(roundedRect: NSRect(x: 0, y: 0, width: 40, height: 40), xRadius: 13, yRadius: 13).fill() }
    let leaf = NSBezierPath()
    leaf.move(to: NSPoint(x: 12,y: 27))
    leaf.curve(to: NSPoint(x:29,y:11), controlPoint1:NSPoint(x:12,y:17), controlPoint2:NSPoint(x:17,y:12))
    leaf.curve(to: NSPoint(x:12,y:27), controlPoint1:NSPoint(x:29,y:22), controlPoint2:NSPoint(x:23,y:28))
    leaf.close(); NSColor(srgbRed:0.91,green:0.94,blue:0.79,alpha:1).setFill(); leaf.fill()
    color.setStroke(); let stem=NSBezierPath(); stem.move(to:NSPoint(x:12,y:29));stem.line(to:NSPoint(x:24,y:16));stem.lineWidth=2;stem.stroke()
    if staff { NSColor.white.setFill(); NSBezierPath(roundedRect:NSRect(x:26,y:27,width:5,height:5),xRadius:1,yRadius:1).fill() }
    NSGraphicsContext.restoreGraphicsState()
    let root = staff ? "ios-staff" : "ios"
    let filename = splash ? "Splash.imageset/splash-2732x2732.png" : "AppIcon.appiconset/AppIcon-512@2x.png"
    let path = "\(root)/App/App/Assets.xcassets/\(filename)"
    let bitmap = NSBitmapImageRep(cgImage: context.makeImage()!)
    let png = bitmap.representation(using:.png, properties:[:])!
    try png.write(to:URL(fileURLWithPath:path))
    if splash {
        for suffix in ["-1", "-2"] {
            try png.write(to:URL(fileURLWithPath:path.replacingOccurrences(of: "splash-2732x2732.png", with: "splash-2732x2732\(suffix).png")))
        }
    }
}
for staff in [false,true] { try render(staff: staff,splash:false); try render(staff:staff,splash:true) }
