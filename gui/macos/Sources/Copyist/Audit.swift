import AppKit
import ApplicationServices
import Foundation

/// Accessibility self-audit — run with `--audit`.
///
/// Inspecting another app's accessibility tree needs the macOS Accessibility
/// permission, which by design cannot be granted programmatically. A process
/// inspecting ITSELF needs no permission at all, so Copyist audits its own
/// tree from inside its own process and prints it.
///
/// That makes the thing this project actually cares about — whether every
/// element has a usable name, role and value — automatable and CI-checkable,
/// rather than something only a human with a screen reader can confirm.
///
///     Copyist --audit [--open FILE.mid]
///
/// Exits non-zero if any interactive element is missing a label.
enum Audit {

    struct Node {
        let depth: Int
        let role: String
        let label: String
        let value: String
        let help: String
        let interactive: Bool
    }

    static func walk(_ element: Any, depth: Int = 0, into out: inout [Node]) {
        guard depth < 24, let e = element as? NSAccessibilityProtocol else { return }

        let role = (e.accessibilityRole()?.rawValue ?? "").replacingOccurrences(
            of: "AX", with: "")
        let label = e.accessibilityLabel() ?? ""
        let title = e.accessibilityTitle() ?? ""
        let value = String(describing: e.accessibilityValue() ?? "")
        let help = e.accessibilityHelp() ?? ""

        let interactiveRoles: Set<String> = [
            "Button", "PopUpButton", "ComboBox", "TextField", "CheckBox",
            "RadioButton", "Slider", "Incrementor", "Link", "MenuItem",
        ]
        let isInteractive = interactiveRoles.contains(role)

        // Skip pure layout containers with nothing to say.
        let interesting = !label.isEmpty || !title.isEmpty || isInteractive
            || role == "StaticText" || role == "Window"
        if interesting {
            out.append(Node(depth: depth, role: role,
                            label: label.isEmpty ? title : label,
                            value: value == "nil" ? "" : value,
                            help: help, interactive: isInteractive))
        }

        for child in (e.accessibilityChildren() ?? []) {
            walk(child, depth: depth + (interesting ? 1 : 0), into: &out)
        }
    }

    /// AppKit builds the full accessibility tree lazily — it only materializes
    /// once an assistive client attaches and asks for it. With no screen
    /// reader running, a walk finds the window and its title-bar buttons and
    /// nothing else, which would read as "no problems found" when in fact
    /// nothing was inspected.
    ///
    /// Setting enhanced-user-interface on ourselves is what VoiceOver does to
    /// an app when it attaches, and a process may do it to itself without the
    /// Accessibility permission.
    /// MUST NOT run on the main thread. An AXUIElement call aimed at your own
    /// process round-trips through the accessibility server and back into your
    /// main run loop; issuing it FROM the main thread deadlocks, and the app
    /// simply hangs with no output at all.
    @discardableResult
    static func enableFullTree() -> Bool {
        let app = AXUIElementCreateApplication(getpid())
        let r = AXUIElementSetAttributeValue(
            app, "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
        Thread.sleep(forTimeInterval: 0.8)     // let the tree materialize
        return r == .success
    }

    /// Entry point. Call from anywhere; it moves itself off the main thread.
    static func start() {
        setbuf(stdout, nil)          // never lose output to a hang
        FileHandle.standardError.write("audit: starting\n".data(using: .utf8)!)
        DispatchQueue.global(qos: .userInitiated).async {
            FileHandle.standardError.write("audit: enabling tree\n".data(using: .utf8)!)
            let enhanced = enableFullTree()
            FileHandle.standardError.write("audit: enabled=\(enhanced)\n".data(using: .utf8)!)
            var nodes: [Node] = []
            FileHandle.standardError.write("audit: walking\n".data(using: .utf8)!)
            DispatchQueue.main.sync {
                for window in NSApp.windows where window.isVisible {
                    walk(window, into: &nodes)
                }
            }
            let vo = DispatchQueue.main.sync {
                NSWorkspace.shared.isVoiceOverEnabled
            }
            report(nodes, enhanced: enhanced, voiceOver: vo)
        }
    }

    static func report(_ nodes: [Node], enhanced: Bool, voiceOver: Bool) {

        print("COPYIST ACCESSIBILITY AUDIT")
        print(String(repeating: "=", count: 60))
        print("enhanced user interface: \(enhanced ? "on" : "COULD NOT ENABLE")")
        print("VoiceOver running:       " + (voiceOver ? "yes" : "no"))
        print("")

        // Window plus title-bar buttons and nothing else means the tree never
        // materialized. Reporting that as a pass would be worse than useless.
        let contentful = nodes.filter { $0.role != "Window" && !$0.label.isEmpty }
        if nodes.isEmpty || contentful.isEmpty {
            print("The accessibility tree contains no labelled content.")
            print("Nothing was inspected, so this is a FAILURE to audit, not a")
            print("pass. Run again with VoiceOver on.")
            exit(2)
        }

        for n in nodes {
            let pad = String(repeating: "  ", count: n.depth)
            var line = "\(pad)[\(n.role)] \(n.label)"
            if !n.value.isEmpty { line += "  = \(n.value)" }
            print(line)
            if !n.help.isEmpty {
                print("\(pad)      hint: \(n.help)")
            }
        }

        let interactive = nodes.filter(\.interactive)
        let unlabelled = interactive.filter { $0.label.isEmpty }
        let unhinted = interactive.filter { $0.help.isEmpty && !$0.label.isEmpty }
        let statics = nodes.filter { $0.role == "StaticText" }

        print("")
        print(String(repeating: "-", count: 60))
        print("elements reported      \(nodes.count)")
        print("interactive controls   \(interactive.count)")
        print("  without a label      \(unlabelled.count)"
              + (unlabelled.isEmpty ? "" : "   <- FAIL"))
        print("  without a hint       \(unhinted.count)")
        print("text elements          \(statics.count)")

        if !unlabelled.isEmpty {
            print("")
            print("Unlabelled controls a screen reader would announce by role only:")
            for n in unlabelled { print("  [\(n.role)] at depth \(n.depth)") }
            exit(1)
        }
        print("")
        print("PASS — every interactive control has a name.")
        exit(0)
    }
}
