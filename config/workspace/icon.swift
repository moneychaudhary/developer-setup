import AppKit

// Usage: icon SYMBOL R G B OUT.png — draws a 1024px rounded-square icon with a white SF Symbol
let a = CommandLine.arguments
let size: CGFloat = 1024
let img = NSImage(size: NSSize(width: size, height: size))
img.lockFocus()
let rect = NSRect(x: 100, y: 100, width: 824, height: 824)
let base = NSColor(srgbRed: CGFloat(Double(a[2])!), green: CGFloat(Double(a[3])!), blue: CGFloat(Double(a[4])!), alpha: 1)
NSGradient(starting: base.blended(withFraction: 0.25, of: .white)!, ending: base.blended(withFraction: 0.2, of: .black)!)!
  .draw(in: NSBezierPath(roundedRect: rect, xRadius: 185, yRadius: 185), angle: -90)
let cfg = NSImage.SymbolConfiguration(pointSize: 440, weight: .semibold).applying(.init(paletteColors: [.white]))
let sym = NSImage(systemSymbolName: a[1], accessibilityDescription: nil)!.withSymbolConfiguration(cfg)!
let s = sym.size
sym.draw(in: NSRect(x: (size - s.width) / 2, y: (size - s.height) / 2, width: s.width, height: s.height))
img.unlockFocus()
let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: a[5]))
