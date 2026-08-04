import AppKit
import ApplicationServices
import Foundation

// axaudit — inspect a running app's accessibility tree the way a screen
// reader does, and report anything a screen reader could not name.
//
// Why this exists as a SEPARATE program:
//
// Copyist's in-process `--audit` can only see the window and its title-bar
// buttons. SwiftUI does not expose its accessibility tree through the AppKit
// object graph you can walk from inside your own process; the tree VoiceOver
// reads is constructed on the far side of the accessibility API, so you have
// to ask for it as a CLIENT, not as the app itself. Trying to enable it from
// inside fails too — AXUIElementSetAttributeValue aimed at your own process
// returns an error unless the process is already trusted.
//
// Being a client requires the macOS Accessibility permission. That permission
// cannot be granted programmatically, by design: TCC requires a human at the
// keyboard with the account password. So this tool asks for it politely, says
// exactly what to do if it is missing, and never pretends an un-inspected tree
// is a clean one.
//
//   axaudit [process-name]        default: Copyist
//
// Exit codes:  0 clean   1 unlabelled controls found   2 could not inspect

let processName = CommandLine.arguments.dropFirst().first ?? "Copyist"

// MARK: - Permission

let trusted = AXIsProcessTrustedWithOptions(
    ["AXTrustedCheckOptionPrompt": true] as CFDictionary)

if !trusted {
    print("""
    axaudit cannot inspect anything without the Accessibility permission.

    macOS has just shown a prompt, or you can grant it directly:

        System Settings -> Privacy & Security -> Accessibility
        then enable the app running this command (your terminal).

    This permission needs your password and a physical toggle. It cannot be
    granted by a script, and it should not be possible to — that is the point
    of it.

    Nothing was inspected. This is a failure to audit, not a pass.
    """)
    exit(2)
}

// MARK: - Find the app

guard let app = NSWorkspace.shared.runningApplications.first(where: {
    $0.localizedName == processName || $0.executableURL?.lastPathComponent == processName
}) else {
    print("No running process named \(processName). Start it first, then run this.")
    exit(2)
}

let root = AXUIElementCreateApplication(app.processIdentifier)
AXUIElementSetAttributeValue(root, "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
Thread.sleep(forTimeInterval: 0.8)

// MARK: - Walk

func attr(_ e: AXUIElement, _ name: String) -> String {
    var v: CFTypeRef?
    guard AXUIElementCopyAttributeValue(e, name as CFString, &v) == .success,
          let v else { return "" }
    if let s = v as? String { return s }
    if let n = v as? NSNumber { return n.stringValue }
    return ""
}

func children(_ e: AXUIElement) -> [AXUIElement] {
    var v: CFTypeRef?
    guard AXUIElementCopyAttributeValue(e, kAXChildrenAttribute as CFString, &v) == .success
    else { return [] }
    return (v as? [AXUIElement]) ?? []
}

struct Node {
    let depth: Int, role: String, label: String, value: String, help: String
    let chrome: Bool
    var interactive: Bool {
        ["Button", "PopUpButton", "ComboBox", "TextField", "CheckBox",
         "RadioButton", "Slider", "Incrementor", "Link", "MenuItem"].contains(role)
    }
}

// AppKit supplies some controls itself and VoiceOver names them itself; their
// AX title is empty by design. Counting those as failures buries the ones that
// are actually mine, and an audit that cries wolf gets ignored.
//
// But the exclusion has to be surgical. An earlier version listed ScrollArea
// here, which excluded EVERYTHING inside the scroll view — that is to say most
// of the app — and then printed PASS. An audit that passes by inspecting
// nothing is worse than no audit, so:
//
//   SELF_AND_CHILDREN  the control and everything under it is AppKit's
//   CHILDREN_ONLY      the control is mine, its internal parts are AppKit's
let SELF_AND_CHILDREN: Set<String> = ["ScrollBar", "Splitter"]
let CHILDREN_ONLY: Set<String> = ["Incrementor", "ComboBox", "PopUpButton"]

var nodes: [Node] = []

func walk(_ e: AXUIElement, _ depth: Int, chrome: Bool = false) {
    guard depth < 30 else { return }
    let role = attr(e, kAXRoleAttribute as String).replacingOccurrences(of: "AX", with: "")
    var label = attr(e, kAXDescriptionAttribute as String)
    if label.isEmpty { label = attr(e, kAXTitleAttribute as String) }
    let value = attr(e, kAXValueAttribute as String)
    let help = attr(e, kAXHelpAttribute as String)

    // Depth 0 is the window itself; its direct unnamed buttons are the
    // traffic lights.
    let isChrome = chrome || SELF_AND_CHILDREN.contains(role)
        || (depth <= 1 && role == "Button" && label.isEmpty)

    let n = Node(depth: depth, role: role, label: label, value: value,
                 help: help, chrome: isChrome)
    let worth = !label.isEmpty || !value.isEmpty || n.interactive
        || role == "StaticText" || role == "Window"
    if worth { nodes.append(n) }
    let childChrome = isChrome || CHILDREN_ONLY.contains(role)
    for c in children(e) {
        walk(c, depth + (worth ? 1 : 0), chrome: childChrome)
    }
}

for w in children(root) where attr(w, kAXRoleAttribute as String) == "AXWindow" {
    walk(w, 0)
}

// MARK: - Report

print("ACCESSIBILITY AUDIT — \(processName)")
print(String(repeating: "=", count: 62))
print("VoiceOver running: \(NSWorkspace.shared.isVoiceOverEnabled ? "yes" : "no")")
print("")

let contentful = nodes.filter { $0.role != "Window" && !($0.label + $0.value).isEmpty }
if contentful.isEmpty {
    print("The tree contains no labelled content — nothing was inspected.")
    print("This is a failure to audit, not a pass.")
    exit(2)
}

for n in nodes {
    let pad = String(repeating: "  ", count: n.depth)
    var line = "\(pad)[\(n.role)] \(n.label)"
    if !n.value.isEmpty && n.value != n.label { line += "  = \(n.value)" }
    print(line)
    if !n.help.isEmpty { print("\(pad)      hint: \(n.help)") }
}

let interactive = nodes.filter { $0.interactive && !$0.chrome }
let chromeCount = nodes.filter { $0.interactive && $0.chrome }.count
let unlabelled = interactive.filter { $0.label.isEmpty && $0.value.isEmpty }
let unhinted = interactive.filter { $0.help.isEmpty }
let unknownRole = nodes.filter { $0.role == "Unknown" && !$0.label.isEmpty }

print("")
print(String(repeating: "-", count: 62))
print("elements reported      \(nodes.count)")
print("text elements          \(nodes.filter { $0.role == "StaticText" }.count)")
print("app controls           \(interactive.count)")
print("  without a name       \(unlabelled.count)\(unlabelled.isEmpty ? "" : "   <- FAIL")")
print("  without a hint       \(unhinted.count)")
print("AppKit chrome ignored  \(chromeCount)   (window buttons, scroll bar, stepper +/-)")
if !unknownRole.isEmpty {
    print("")
    print("\(unknownRole.count) named element(s) report role Unknown. VoiceOver will")
    print("read the text but announce no useful role. Prefer a real trait:")
    for n in unknownRole.prefix(3) {
        print("  \(String(n.label.prefix(60)))…")
    }
}

if !unlabelled.isEmpty {
    print("")
    print("A screen reader would announce these by role only:")
    for n in unlabelled { print("  [\(n.role)] at depth \(n.depth)") }
    exit(1)
}
// A pass that inspected almost nothing is the failure mode this tool exists
// to prevent, so make it impossible to report one.
if interactive.count < 3 {
    print("")
    print("Only \(interactive.count) app control(s) were inspected. That is too")
    print("few to be a real result — the walk is probably excluding content it")
    print("should be checking. Refusing to report a pass.")
    exit(2)
}
print("")
print("PASS — every interactive control has a name a screen reader can speak.")
exit(0)
