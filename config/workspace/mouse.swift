import AppKit
import CoreGraphics

// Usage: mouse click X Y | rclick X Y | drag X1 Y1 X2 Y2 | cmddrag X1 Y1 X2 Y2 | screen | find OWNER left|right|any
let a = CommandLine.arguments
let post = { (t: CGEventType, p: CGPoint) in
  CGEvent(mouseEventSource: nil, mouseType: t, mouseCursorPosition: p, mouseButton: .left)?.post(tap: .cghidEventTap)
}
let n = a.dropFirst(2).compactMap { Double($0) }
let screen = NSScreen.main!.frame.size
switch a.count > 1 ? a[1] : "" {
case "click":
  let p = CGPoint(x: n[0], y: n[1])
  post(.mouseMoved, p); usleep(150000); post(.leftMouseDown, p); usleep(80000); post(.leftMouseUp, p)
case "rclick":
  // Right-click, which opens menu bar icon menus
  let p = CGPoint(x: n[0], y: n[1])
  let r = { (t: CGEventType) in CGEvent(mouseEventSource: nil, mouseType: t, mouseCursorPosition: p, mouseButton: .right)?.post(tap: .cghidEventTap) }
  post(.mouseMoved, p); usleep(150000); r(.rightMouseDown); usleep(80000); r(.rightMouseUp)
case "drag":
  let s = CGPoint(x: n[0], y: n[1]), e = CGPoint(x: n[2], y: n[3])
  post(.mouseMoved, s); usleep(200000); post(.leftMouseDown, s); usleep(200000)
  for i in 1...30 {
    let f = Double(i) / 30
    post(.leftMouseDragged, CGPoint(x: s.x + (e.x - s.x) * f, y: s.y + (e.y - s.y) * f)); usleep(20000)
  }
  usleep(200000); post(.leftMouseUp, e)
case "cmddrag":
  // Command-drag, which rearranges menu bar icons
  let s = CGPoint(x: n[0], y: n[1]), e = CGPoint(x: n[2], y: n[3])
  let ev = { (t: CGEventType, p: CGPoint) in
    let m = CGEvent(mouseEventSource: nil, mouseType: t, mouseCursorPosition: p, mouseButton: .left)
    m?.flags = .maskCommand; m?.post(tap: .cghidEventTap)
  }
  ev(.mouseMoved, s); usleep(200000); ev(.leftMouseDown, s); usleep(300000)
  for i in 1...40 {
    let f = Double(i) / 40
    ev(.leftMouseDragged, CGPoint(x: s.x + (e.x - s.x) * f, y: s.y + (e.y - s.y) * f)); usleep(25000)
  }
  usleep(300000); ev(.leftMouseUp, e)
  CGEvent(keyboardEventSource: nil, virtualKey: 0x37, keyDown: false)?.post(tap: .cghidEventTap)
case "screen":
  print(Int(screen.width), Int(screen.height))
case "find":
  // Print bounds of the largest visible normal window of OWNER in the given half of the screen
  let side = a.count > 3 ? a[3] : "any"
  let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
  var best: (Double, Double, Double, Double)? = nil
  for w in list {
    guard (w[kCGWindowOwnerName as String] as? String) == a[2], (w[kCGWindowLayer as String] as? Int) == 0,
          let b = w[kCGWindowBounds as String] as? [String: Double], let x = b["X"], let y = b["Y"],
          let wd = b["Width"], let h = b["Height"], wd > 60, h > 60 else { continue }
    let mid = x + wd / 2
    if side == "left" && mid > screen.width / 2 { continue }
    if side == "right" && mid < screen.width / 2 { continue }
    if best == nil || wd * h > best!.2 * best!.3 { best = (x, y, wd, h) }
  }
  guard let f = best else { exit(1) }
  print(Int(f.0), Int(f.1), Int(f.2), Int(f.3))
default:
  print("usage: mouse click|drag|screen|find"); exit(2)
}
