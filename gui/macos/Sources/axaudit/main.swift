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
    var interactive: Bool {
        ["Button", "PopUpButton", "ComboBox", "TextField", "CheckBox",
         "RadioButton", "Slider", "Incrementor", "Link", "MenuItem"].contains(role)
    }
}

var nodes: [Node] = []

func walk(_ e: AXUIElement, _ depth: Int) {
    guard depth < 30 else { return }
    let role = attr(e, kAXRoleAttribute as String).replacingOccurrences(of: "AX", with: "")
    var label = attr(e, kAXDescriptionAttribute as String)
    if label.isEmpty { label = attr(e, kAXTitleAttribute as String) }
    let value = attr(e, kAXValueAttribute as String)
    let help = attr(e, kAXHelpAttribute as String)

    let n = Node(depth: depth, role: role, label: label, value: value, help: help)
    let worth = !label.isEmpty || !value.isEmpty || n.interactive
        || role == "StaticText" || role == "Window"
    if worth { nodes.append(n) }
    for c in children(e) { walk(c, depth + (worth ? 1 : 0)) }
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

let interactive = nodes.filter(\.interactive)
let unlabelled = interactive.filter { $0.label.isEmpty && $0.value.isEmpty }
let unhinted = interactive.filter { $0.help.isEmpty }

print("")
print(String(repeating: "-", count: 62))
print("elements reported      \(nodes.count)")
print("text elements          \(nodes.filter { $0.role == "StaticText" }.count)")
print("interactive controls   \(interactive.count)")
print("  without a name       \(unlabelled.count)\(unlabelled.isEmpty ? "" : "   <- FAIL")")
print("  without a hint       \(unhinted.count)")

if !unlabelled.isEmpty {
    print("")
    print("A screen reader would announce these by role only:")
    for n in unlabelled { print("  [\(n.role)] at depth \(n.depth)") }
    exit(1)
}
print("")
print("PASS — every interactive control has a name a screen reader can speak.")
exit(0)
