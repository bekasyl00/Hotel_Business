import AppKit

// The website SVG is the only source of logo geometry for both applications.
let logoSVG = try String(contentsOfFile: "public/assets/logo.svg", encoding: .utf8)

enum RenderError: Error {
    case invalidSVG, unavailableContext, unavailablePNG
}

func color(_ hex: UInt32) -> CGColor {
    CGColor(
        srgbRed: CGFloat((hex >> 16) & 255) / 255,
        green: CGFloat((hex >> 8) & 255) / 255,
        blue: CGFloat(hex & 255) / 255,
        alpha: 1
    )
}

func render(staff: Bool, splash: Bool) throws {
    let size = splash ? 2732 : 1024
    let svg = staff
        ? logoSVG
            .replacingOccurrences(of: "#53694A", with: "#DFE6D0")
            .replacingOccurrences(of: "#344A35", with: "#F4F3ED")
            .replacingOccurrences(of: "#A87A46", with: "#D9B88B")
        : logoSVG
    guard let image = NSImage(data: Data(svg.utf8)) else { throw RenderError.invalidSVG }
    guard let context = CGContext(
        data: nil, width: size, height: size, bitsPerComponent: 8,
        bytesPerRow: size * 4,
        space: CGColorSpace(name: CGColorSpace.sRGB)!,
        bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
    ) else { throw RenderError.unavailableContext }

    context.setFillColor(color(staff ? 0x344A35 : 0xF4F3ED))
    context.fill(CGRect(x: 0, y: 0, width: size, height: size))
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: false)
    NSGraphicsContext.current?.imageInterpolation = .high
    let markSize: CGFloat = splash ? 560 : 880
    let inset = (CGFloat(size) - markSize) / 2
    image.draw(in: NSRect(x: inset, y: inset, width: markSize, height: markSize))
    NSGraphicsContext.restoreGraphicsState()

    guard let rendered = context.makeImage(),
          let png = NSBitmapImageRep(cgImage: rendered).representation(using: .png, properties: [:])
    else { throw RenderError.unavailablePNG }
    let root = staff ? "ios-staff" : "ios"
    let assetRoot = "\(root)/App/App/Assets.xcassets/"
    let filenames = splash
        ? ["splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"].map { "Splash.imageset/\($0)" }
        : ["AppIcon.appiconset/AppIcon-512@2x.png"]
    for filename in filenames {
        try png.write(to: URL(fileURLWithPath: assetRoot + filename), options: .atomic)
    }
}

for staff in [false, true] {
    try render(staff: staff, splash: false)
    try render(staff: staff, splash: true)
}
print("Both iOS icons and launch images rendered from public/assets/logo.svg")
