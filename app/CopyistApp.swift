// CopyistApp.swift — Copyist as an actual Mac app.
//
// Matthew's ask (2026-09-22): "the look and feel of the actual app
// should be like an actual app... both accessible and visually", both
// vibes shipped and the user decides, nothing limited. So: a real
// SwiftUI app, two designed themes (Dark Stage and Manuscript) plus
// match-the-system, every control labeled and stating its value, and
// the roadmap conversation held over the porcelain door — the same
// engine the terminal uses, JSON line in, JSON line out.
//
// The compiler itself is bundled into Resources/prototype (with
// fonts/), so the app is self-contained; a checkout at ~/copyist wins
// when present so development stays live. Build: app/build.sh.

import SwiftUI
import PDFKit
import AppKit
import UniformTypeIdentifiers

// MARK: - Colors and vibes

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255)
    }
}

enum Vibe: String, CaseIterable, Identifiable {
    case system, stage, manuscript
    var id: String { rawValue }
    var label: String {
        switch self {
        case .system: return "Match the system"
        case .stage: return "Dark stage"
        case .manuscript: return "Manuscript"
        }
    }
}

/// Every size in the app, times the writer's text size (Settings, or
/// View > Bigger Text, Command =): 100 to 200 percent. Nothing in the
/// app is drawn at a fixed size any more (2026-10-17, low vision).
func ts(_ size: CGFloat) -> CGFloat {
    let k = UserDefaults.standard.double(forKey: "textScale")
    return size * CGFloat(min(max(k == 0 ? 1.0 : k, 1.0), 2.0))
}

let textSizes: [Double] = [1.0, 1.15, 1.3, 1.5, 1.75, 2.0]

/// Lays its children out left to right and wraps to a new row when the
/// window is too narrow: result buttons, at any text size, never clip.
/// Reading order stays the order they are written in.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews,
                      cache: inout ()) -> CGSize {
        rows(subviews, width: proposal.width ?? .infinity).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                       subviews: Subviews, cache: inout ()) {
        for (i, p) in rows(subviews, width: bounds.width).places
            .enumerated() {
            subviews[i].place(at: CGPoint(x: bounds.minX + p.x,
                                          y: bounds.minY + p.y),
                              proposal: .unspecified)
        }
    }

    private func rows(_ subviews: Subviews, width: CGFloat)
        -> (size: CGSize, places: [CGPoint]) {
        var x: CGFloat = 0, y: CGFloat = 0, rowH: CGFloat = 0
        var widest: CGFloat = 0
        var places: [CGPoint] = []
        for v in subviews {
            let sz = v.sizeThatFits(.unspecified)
            if x > 0 && x + sz.width > width {
                x = 0
                y += rowH + spacing
                rowH = 0
            }
            places.append(CGPoint(x: x, y: y))
            x += sz.width + spacing
            rowH = max(rowH, sz.height)
            widest = max(widest, x - spacing)
        }
        return (CGSize(width: widest, height: y + rowH), places)
    }
}

/// The Mac's bordered buttons keep the system's own small label
/// whatever the text size, so past 100 percent the desk draws its own:
/// the same shape, the label at the writer's size. At 100 percent
/// everything is the system's, focus ring and all.
struct DeskButtonStyle: ButtonStyle {
    var fill: Color? = nil
    var ink: Color? = nil

    func makeBody(configuration: Configuration) -> some View {
        DeskButtonBody(configuration: configuration, fill: fill, ink: ink)
    }
}

private struct DeskButtonBody: View {
    let configuration: ButtonStyleConfiguration
    let fill: Color?
    let ink: Color?
    @Environment(\.isEnabled) private var enabled

    var body: some View {
        configuration.label
            .font(.system(size: ts(13), weight: fill == nil ? .regular
                                                             : .semibold))
            .foregroundStyle(ink ?? Color.primary)
            .padding(.horizontal, ts(10))
            .padding(.vertical, ts(4))
            .background(RoundedRectangle(cornerRadius: ts(6))
                .fill(fill ?? Color.secondary.opacity(0.18)))
            .overlay(RoundedRectangle(cornerRadius: ts(6))
                .stroke(Color.secondary.opacity(fill == nil ? 0.45 : 0),
                        lineWidth: 1))
            .opacity(configuration.isPressed ? 0.7 : (enabled ? 1 : 0.55))
            .contentShape(RoundedRectangle(cornerRadius: ts(6)))
    }
}

extension View {
    /// .bordered (or, given a fill, .borderedProminent) at 100 percent;
    /// the desk's own scaled button above it.
    @ViewBuilder
    func deskButton(fill: Color? = nil, ink: Color? = nil) -> some View {
        let k = UserDefaults.standard.double(forKey: "textScale")
        if k > 1.01 {
            self.buttonStyle(DeskButtonStyle(fill: fill, ink: ink))
        } else if fill != nil {
            self.buttonStyle(.borderedProminent)
        } else {
            self.buttonStyle(.bordered)
        }
    }

    /// Every button that names no style of its own, at the text size.
    @ViewBuilder
    func deskButtons() -> some View {
        let k = UserDefaults.standard.double(forKey: "textScale")
        if k > 1.01 {
            self.buttonStyle(DeskButtonStyle())
        } else {
            self
        }
    }
}

struct Palette {
    let bg: Color, card: Color, edge: Color
    let text: Color, sub: Color
    let accent: Color, accentText: Color

    static let stage = Palette(
        bg: Color(hex: 0x0E1117), card: Color(hex: 0x1A2130),
        edge: Color(hex: 0x626E8C),
        text: Color(hex: 0xEDF1F7), sub: Color(hex: 0x9AA7BD),
        accent: Color(hex: 0xFFB454), accentText: Color(hex: 0x1A1205))

    static let manuscript = Palette(
        bg: Color(hex: 0xF7F2E7), card: Color(hex: 0xFFFDF7),
        edge: Color(hex: 0x877C67),
        text: Color(hex: 0x232018), sub: Color(hex: 0x6B655B),
        accent: Color(hex: 0xA22C29), accentText: Color(hex: 0xFFF8F0))
}

// MARK: - Running the engine without freezing the window

/// Run a program in the background and hand its output (stdout, and
/// stderr too when asked) and exit status back on the main thread. A
/// toggle in Settings used to wait for Python to start and finish
/// before the window would answer again.
func runInBackground(_ exe: String, _ args: [String], stderr: Bool = false,
                     done: @escaping (String, Int32) -> Void) {
    DispatchQueue.global(qos: .userInitiated).async {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = args
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = stderr ? pipe : Pipe()
        guard (try? p.run()) != nil else {
            DispatchQueue.main.async { done("", -1) }
            return
        }
        // read before waiting: a full pipe never deadlocks this way
        let d = pipe.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        let out = String(decoding: d, as: UTF8.self)
        let st = p.terminationStatus
        DispatchQueue.main.async { done(out, st) }
    }
}

// MARK: - Talking to VoiceOver

func announce(_ text: String, queued: Bool = false) {
    if #available(macOS 14.0, *) {
        var a = AttributedString(text)
        // a queued line waits for VoiceOver to finish the one it is on
        // (the tab heading it just landed on); the rest speak now
        a.accessibilitySpeechAnnouncementPriority = queued ? .default : .high
        AccessibilityNotification.Announcement(a).post()
    }
}

// MARK: - The tabs

enum Tab: Int, CaseIterable, Identifiable {
    case chart = 1, build, listen, talk, settings
    var id: Int { rawValue }
    var title: String {
        switch self {
        case .chart: return "Chart"
        case .build: return "Build"
        case .listen: return "Listen and read"
        case .talk: return "Conversation"
        case .settings: return "Settings"
        }
    }
    var icon: String {
        switch self {
        case .chart: return "doc.text"
        case .build: return "hammer"
        case .listen: return "headphones"
        case .talk: return "bubble.left.and.bubble.right"
        case .settings: return "gearshape"
        }
    }
    /// what the tab holds, said once on arrival
    var blurb: String {
        switch self {
        case .chart: return "Choose, start or bring in a chart."
        case .build: return "Build, check, and what changed."
        case .listen: return "Hear the band from any bar, or have a part read aloud."
        case .talk: return "Tell Copyist the tune, or teach it your keyswitches and drums."
        case .settings: return "Every setting says what it is set to."
        }
    }
    var key: KeyEquivalent { KeyEquivalent(Character(String(rawValue))) }
    var spokenPlace: String {
        "\(title), tab \(rawValue) of \(Tab.allCases.count)"
    }
}

// MARK: - Where the tool lives

struct Tool {
    let python: String
    let script: String

    static func find() -> Tool? {
        let fm = FileManager.default
        var candidates: [String] = []
        if let home = ProcessInfo.processInfo.environment["COPYIST_HOME"] {
            candidates.append(home + "/prototype/chart.py")
        }
        candidates.append(NSHomeDirectory() + "/copyist/prototype/chart.py")
        if let res = Bundle.main.resourcePath {
            candidates.append(res + "/prototype/chart.py")
        }
        for c in candidates where fm.fileExists(atPath: c) {
            return Tool(python: "/usr/bin/python3", script: c)
        }
        return nil
    }
}

func chartsFolder() -> URL {
    let icloud = NSHomeDirectory() +
        "/Library/Mobile Documents/com~apple~CloudDocs/Copyist Charts"
    var isDir: ObjCBool = false
    if FileManager.default.fileExists(atPath: icloud, isDirectory: &isDir),
       isDir.boolValue {
        return URL(fileURLWithPath: icloud)
    }
    return FileManager.default.urls(for: .documentDirectory,
                                    in: .userDomainMask).first!
}

func loadConfig() -> [String: String] {
    let p = NSHomeDirectory() + "/.config/copyist/config.json"
    guard let d = FileManager.default.contents(atPath: p),
          let j = try? JSONSerialization.jsonObject(with: d),
          let dict = j as? [String: Any] else { return [:] }
    var out: [String: String] = [:]
    for (k, v) in dict { out[k] = "\(v)" }
    return out
}

// MARK: - What the porcelain door says

struct TalkLine: Identifiable, Equatable {
    let id = UUID()
    let mine: Bool
    let text: String
}

// MARK: - The app's one model

final class AppModel: ObservableObject {
    @Published var tab: Tab = .chart
    /// bumps on every tab key press, even for the tab already showing,
    /// so the heading can take VoiceOver back to the top of it
    @Published var tabPing = 0

    /// true while the last tab change was the writer's own key or
    /// click; a switch the app makes (a build, a conversation starting)
    /// leaves VoiceOver where the work is — the question, the progress
    @Published var userSwitch = false

    func go(_ t: Tab) {
        userSwitch = true
        tab = t
        tabPing += 1
    }
    /// which tab the current run's transcript belongs on
    @Published var runTab: Tab = .build
    @Published var parts: [String] = []
    @Published var showExport = false
    @Published var askEmboss = false
    /// set when Emboss finds no embosser: Settings puts VoiceOver on
    /// the Embosser picker itself, not the top of the window
    @Published var wantEmbosser = false

    /// Emboss, from the Build tab or the Chart menu: ask first, or say
    /// what is missing and take VoiceOver to where it gets fixed.
    func emboss() {
        if embosser().isEmpty {
            userSwitch = false
            wantEmbosser = true
            tab = .settings
        } else {
            askEmboss = true
        }
    }

    /// The embosser setting, if one is chosen.
    func embosser() -> String {
        let cfgURL = URL(fileURLWithPath: NSHomeDirectory()
            + "/.config/copyist/config.json")
        if let d = try? Data(contentsOf: cfgURL),
           let j = try? JSONSerialization.jsonObject(with: d)
                as? [String: Any], let e = j["embosser"] as? String {
            return e
        }
        return ""
    }
    @AppStorage("speakSteps") var speakSteps: Bool = true
    @AppStorage("speakTabs") var speakTabs: Bool = true
    @AppStorage("textScale") var textScale: Double = 1.0

    /// One step bigger or smaller (or back to 100), said aloud.
    func textSize(_ step: Int) {
        let now = textSizes.firstIndex(where: { $0 >= textScale - 0.001 })
            ?? 0
        let next = step == 0 ? 0
            : min(max(now + step, 0), textSizes.count - 1)
        textScale = textSizes[next]
        announce("Text size \(Int((textScale * 100).rounded())) percent.")
    }
    private var lastSpokenStep = ""
    private var lastSpokenPct = 0.0
    private var lastSpokenAt = Date.distantPast
    @AppStorage("vibe") var vibeRaw: String = Vibe.system.rawValue
    @AppStorage("lastChart") var lastChart: String = ""
    @AppStorage("recentCharts") var recentRaw: String = "[]"

    // the runner (build / check / listen / read ...)
    @Published var runTitle = ""
    @Published var runOutput = ""
    @Published var running = false
    @Published var flavor = ""
    @Published var playURL: URL?
    @Published var progressPct: Double?
    @Published var progressWhat = ""
    private var runBuffer = ""
    /// how the last run ended when it did not simply finish: "stopped"
    /// (the writer said so) or "failed" (the engine stopped on a
    /// problem); shown and said, never dressed as finished
    @Published var runEnded = ""
    /// the last run was one that writes pages and files (a build or an
    /// export), finished, so its results get their buttons
    var madeFiles: Bool {
        (runTitle == "Build" || runTitle == "Export") && runEnded.isEmpty
            && !running
    }
    /// each run's number: a late handler from a run already replaced
    /// must never touch the one now going
    private var runID = 0
    private var runStarted = Date()
    private var userStopped = false
    private var talkID = 0
    /// the chart an import just made, from the engine's "chart:" line
    private var importedChart: String?
    private var flavorTimer: Timer?
    private var proc: Process?

    // the conversation (roadmap / interview over porcelain)
    @Published var talk: [TalkLine] = []
    @Published var question = ""
    @Published var questionDefault = ""
    @Published var talking = false
    private var talkProc: Process?
    private var talkStdin: FileHandle?
    private var talkBuffer = ""
    /// lines said in a burst, spoken as one announcement: sent one by
    /// one, each cut off the last ("The band: ..." never got heard)
    private var speechQueue: [String] = []
    private var speechFlush: DispatchWorkItem?

    private func queueSpeech(_ text: String, now: Bool = false) {
        speechQueue.append(text)
        speechFlush?.cancel()
        let w = DispatchWorkItem { [weak self] in
            guard let self, !self.speechQueue.isEmpty else { return }
            announce(self.speechQueue.joined(separator: " "))
            self.speechQueue = []
        }
        speechFlush = w
        DispatchQueue.main.asyncAfter(deadline: .now() + (now ? 0.05 : 0.4),
                                      execute: w)
    }

    var vibe: Vibe {
        get { Vibe(rawValue: vibeRaw) ?? .system }
        set { vibeRaw = newValue.rawValue }
    }

    var chart: String? {
        lastChart.isEmpty ? nil : lastChart
    }

    var chartName: String {
        chart.map { URL(fileURLWithPath: $0)
            .deletingPathExtension().lastPathComponent } ?? "No chart yet"
    }

    var recents: [String] {
        get {
            (try? JSONDecoder().decode([String].self,
                from: Data(recentRaw.utf8))) ?? []
        }
        set {
            if let d = try? JSONEncoder().encode(newValue) {
                recentRaw = String(decoding: d, as: UTF8.self)
            }
        }
    }

    func choose(_ path: String) {
        lastChart = path
        var r = recents.filter { $0 != path }
        r.insert(path, at: 0)
        recents = Array(r.prefix(8))
        loadParts()
    }

    /// The band, one chair per line, for the pick lists.
    func loadParts() {
        guard let tool = Tool.find(), let c = chart,
              FileManager.default.fileExists(atPath: c) else {
            parts = []
            return
        }
        runInBackground(tool.python, [tool.script, c, "parts", "--labels"])
        { [weak self] out, st in
            guard let self, self.chart == c else { return }
            self.parts = st == 0
                ? out.split(separator: "\n").map(String.init)
                    .filter { !$0.isEmpty }
                : []
        }
    }

    /// The transcript, one line per thing said.
    var runLines: [String] {
        runOutput.split(separator: "\n", omittingEmptySubsequences: true)
            .map(String.init)
    }

    // ---------------------------------------------------- the runner

    private static let flavorLines = [
        "Counting every bar twice…",
        "Inking the parts…",
        "Warming up the rhythm section…",
        "Teaching the band the road map…",
        "Listening back so you don't have to guess…",
        "Dotting the ties, tying the dots…",
    ]

    func run(_ title: String, args: [String], needsChart: Bool = true,
             on where_: Tab = .build) {
        guard let tool = Tool.find() else {
            runTitle = title
            runOutput = "I can't find the Copyist engine. There's no "
                + "~/copyist checkout and no copy inside the app, "
                + "which shouldn't happen. Reinstall with app/build.sh."
            runTab = where_
            tab = where_
            return
        }
        if running {
            tab = runTab
            announce("Still working on \(runTitle)"
                     + (progressPct.map { " — \(Int($0)) percent" }
                        ?? "")
                     + ". To work on another chart meanwhile, open a "
                     + "new window from the File menu.")
            return
        }
        var full = [tool.script]
        if needsChart {
            guard let c = chart else { return }
            full.append(c)
        }
        full += args
        runTitle = title
        runOutput = ""
        runEnded = ""
        runID += 1
        let myRun = runID
        runStarted = Date()
        userStopped = false
        running = true
        playURL = nil
        progressPct = nil
        progressWhat = ""
        runBuffer = ""
        let wantsPlay = args.contains("build") || args.contains("listen")
        lastSpokenStep = ""
        lastSpokenPct = 0
        runTab = where_
        userSwitch = false
        tab = where_
        announce("\(title) started.")
        startFlavor()
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool.python)
        p.arguments = full
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:"
            + (env["PATH"] ?? "/usr/bin:/bin")
        env["COPYIST_PROGRESS"] = "1"
        p.environment = env
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            guard !d.isEmpty else { return }
            let s = String(decoding: d, as: UTF8.self)
            DispatchQueue.main.async { self?.take(s) }
        }
        p.terminationHandler = { [weak self] proc_ in
            // whatever is still in the pipe is the run's last word — the
            // line that says what happened; read it before letting go
            pipe.fileHandleForReading.readabilityHandler = nil
            let rest = pipe.fileHandleForReading.readDataToEndOfFile()
            let status = proc_.terminationStatus
            DispatchQueue.main.async {
                guard let self, myRun == self.runID else { return }
                if !rest.isEmpty {
                    self.take(String(decoding: rest, as: UTF8.self) + "\n")
                }
                self.running = false
                self.stopFlavor()
                self.progressPct = nil
                if self.userStopped {
                    self.runEnded = "stopped"
                    self.importedChart = nil
                    announce("\(title) stopped. Nothing after the last line "
                             + "shown was made.")
                    return
                }
                if status != 0 {
                    self.runEnded = "failed"
                    self.importedChart = nil
                    let why = self.runOutput.split(separator: "\n")
                        .last.map(String.init) ?? ""
                    announce("\(title) stopped on a problem. " + why)
                    return
                }
                if wantsPlay {
                    self.playURL = self.newestMP3(since: self.runStarted)
                }
                let last = self.runOutput.split(separator: "\n")
                    .last.map(String.init) ?? "Done."
                var opened = ""
                if let made = self.importedChart {
                    self.importedChart = nil
                    self.choose(made)
                    opened = " Now working on "
                        + URL(fileURLWithPath: made)
                            .deletingPathExtension().lastPathComponent
                        + "."
                }
                announce("\(title) finished. \(last)" + opened
                         + (self.playURL != nil
                            ? " The listen is ready: Command P plays it." : ""))
            }
        }
        proc = p
        do { try p.run() } catch {
            running = false
            stopFlavor()
            runOutput = "Copyist's engine would not start: "
                + error.localizedDescription
        }
    }

    /// Anything a writer has, in: a MIDI demo goes to the interview in
    /// the conversation; words or a chord sheet with a chart open asks
    /// whether they belong to it; everything else is imported as a new
    /// tune and opened when it lands.
    /// Several files at once: MIDI demos together are one tune (a DAW
    /// often exports one file per instrument); anything else comes in
    /// one at a time, the first now.
    func bringIn(_ paths: [String]) {
        let midis = paths.filter { Self.isMIDI($0) }
        if midis.count > 1 {
            bringInDemos(midis)
        } else if let first = paths.first {
            bringIn(first)
        }
    }

    static func isMIDI(_ path: String) -> Bool {
        ["mid", "midi", "kar", "smf"].contains(
            URL(fileURLWithPath: path).pathExtension.lowercased())
    }

    /// The words every demo's name starts with: "it takes faith drums"
    /// and "it takes faith piano" are "it takes faith".
    static func sharedName(_ paths: [String]) -> String {
        let stems = paths.map { URL(fileURLWithPath: $0)
            .deletingPathExtension().lastPathComponent }
        guard stems.count > 1 else { return stems.first ?? "New Tune" }
        let words = stems.map { $0.split(whereSeparator: {
            $0 == " " || $0 == "_" || $0 == "-" }).map(String.init) }
        var out: [String] = []
        for i in 0..<(words.map(\.count).min() ?? 0) {
            let w = Set(words.map { $0[i].lowercased() })
            if w.count != 1 { break }
            out.append(words[0][i])
        }
        return out.isEmpty ? stems[0] : out.joined(separator: " ")
    }

    /// One or more played demos become one chart: the interview asks
    /// about each track, then the chart builds at once.
    func bringInDemos(_ paths: [String]) {
        var base = Self.sharedName(paths)
        var folder = chartsFolder().appendingPathComponent(base)
        var chartURL = folder.appendingPathComponent(base + ".chart")
        if FileManager.default.fileExists(atPath: chartURL.path) {
            let a = NSAlert()
            a.messageText = "There is already a chart called \(base)."
            a.informativeText = "Keep both, naming this one with a "
                + "number, or replace the old chart with one from "
                + (paths.count > 1 ? "these \(paths.count) demos"
                   : "this demo")
                + " (it goes to the Trash, so nothing is lost). Return "
                + "keeps both."
            // Return is the safe answer: nothing of his moves
            a.addButton(withTitle: "Keep both")
            a.addButton(withTitle: "Replace it")
            a.addButton(withTitle: "Cancel")
            switch a.runModal() {
            case .alertSecondButtonReturn:
                try? FileManager.default.trashItem(at: chartURL,
                                                   resultingItemURL: nil)
            case .alertFirstButtonReturn:
                var n = 2
                while FileManager.default.fileExists(atPath:
                    chartsFolder().appendingPathComponent("\(base) \(n)")
                        .path) { n += 1 }
                base = "\(base) \(n)"
                folder = chartsFolder().appendingPathComponent(base)
                chartURL = folder.appendingPathComponent(base + ".chart")
            default:
                return
            }
        }
        try? FileManager.default.createDirectory(
            at: folder, withIntermediateDirectories: true)
        choose(chartURL.path)
        startTalk(["new"] + paths.flatMap { ["--demo", $0] })
    }

    func bringIn(_ path: String) {
        let url = URL(fileURLWithPath: path)
        let ext = url.pathExtension.lowercased()
        if Self.isMIDI(path) {
            bringInDemos([path])
            return
        }
        let wordsLike = ["txt", "text", "md", "markdown", "rtf", "rtfd",
                         "doc", "docx", "odt", "pages", "pdf", "html",
                         "htm"].contains(ext)
        if wordsLike, let c = chart {
            let a = NSAlert()
            a.messageText = "Where do these words go?"
            a.informativeText = "Add them to \(chartName), beside the "
                + "sections they belong to, or start a new tune from "
                + "this file."
            a.addButton(withTitle: "Add to \(chartName)")
            a.addButton(withTitle: "Start a new tune")
            a.addButton(withTitle: "Cancel")
            switch a.runModal() {
            case .alertFirstButtonReturn:
                run("Bring in a file", args: ["import", path, "--into", c],
                    needsChart: false)
                return
            case .alertSecondButtonReturn:
                break
            default:
                return
            }
        }
        var args = ["import", path]
        if wordsLike || ext.isEmpty, let n = songsIn(path), n > 1 {
            // a playlist (an iReal Pro link is often the whole Jazz
            // 1460): ask which song, by name or number
            let a = NSAlert()
            a.messageText = "This file holds \(n) songs. Which one?"
            a.informativeText = "Type a song's name, or its number from 1 "
                + "to \(n). Leave it empty for the first song."
            let f = NSTextField(frame: NSRect(x: 0, y: 0, width: 280,
                                              height: 24))
            f.placeholderString = "Song name or number"
            f.setAccessibilityLabel("Song name or number")
            a.accessoryView = f
            a.window.initialFirstResponder = f
            a.addButton(withTitle: "Bring it in")
            a.addButton(withTitle: "Cancel")
            if a.runModal() != .alertFirstButtonReturn { return }
            let pick = f.stringValue.trimmingCharacters(in: .whitespaces)
            if !pick.isEmpty { args += ["--song", pick] }
        }
        run("Bring in a file", args: args, needsChart: false)
    }

    /// How many songs a text file holds ('chart import FILE --list'),
    /// or nil when it can't tell.
    func songsIn(_ path: String) -> Int? {
        guard let tool = Tool.find() else { return nil }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool.python)
        p.arguments = [tool.script, "import", path, "--list"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = Pipe()
        guard (try? p.run()) != nil else { return nil }
        p.waitUntilExit()
        let out = String(decoding: pipe.fileHandleForReading
            .readDataToEndOfFile(), as: UTF8.self)
        guard let first = out.split(separator: " ").first else { return nil }
        return Int(first)
    }

    /// Stop the run going. It stays "running" until the engine has
    /// really gone, so a new run can't start under it; the end is then
    /// said as stopped, never as finished.
    func stopRun() {
        guard running else { return }
        userStopped = true
        proc?.terminate()
    }

    /// Split the engine's stream into lines; a "progress:" line moves
    /// the bar and never clutters the transcript.
    private func take(_ chunk: String) {
        runBuffer += chunk
        while let nl = runBuffer.firstIndex(of: "\n") {
            let line = String(runBuffer[..<nl])
            runBuffer = String(runBuffer[runBuffer.index(after: nl)...])
            if line.hasPrefix("progress: ") {
                let body = line.dropFirst("progress: ".count)
                if let cut = body.range(of: "% — ") {
                    progressPct = Double(body[..<cut.lowerBound])
                    progressWhat = String(body[cut.upperBound...])
                    speakStep()
                }
                continue
            }
            if line.hasPrefix("chart: ") {
                // the engine names the chart it made; the app opens it
                // rather than reading a path aloud. Only a real .chart
                // file counts: an error line starts "chart: " too, and
                // used to become the chart being worked on
                let made = String(line.dropFirst("chart: ".count))
                    .trimmingCharacters(in: .whitespaces)
                if made.hasSuffix(".chart")
                    && FileManager.default.fileExists(atPath: made) {
                    importedChart = made
                    continue
                }
            }
            runOutput += line + "\n"
        }
    }

    /// Each new build step, said aloud — but never more often than
    /// every six seconds, so the voice never becomes a ticker.
    private func speakStep() {
        // a new step, or twenty points further on the same long one
        // (the band's render is one step for a minute or more)
        let pct = progressPct ?? 0
        guard speakSteps,
              progressWhat != lastSpokenStep || pct - lastSpokenPct >= 20,
              Date().timeIntervalSince(lastSpokenAt) >= 6 else { return }
        lastSpokenStep = progressWhat
        lastSpokenPct = pct
        lastSpokenAt = Date()
        announce("\(Int(progressPct ?? 0)) percent. \(progressWhat)",
                 queued: true)
    }

    /// Where the PDF pages land: the "pages_to" setting, else the
    /// chart's own build folder — the same rule the engine follows.
    func pagesFolder() -> URL? {
        guard let c = chart else { return nil }
        let cfgURL = URL(fileURLWithPath: NSHomeDirectory()
            + "/.config/copyist/config.json")
        if let d = try? Data(contentsOf: cfgURL),
           let j = try? JSONSerialization.jsonObject(with: d)
                as? [String: Any],
           let to = (j["pages_to"] as? String)?
                .trimmingCharacters(in: .whitespaces), !to.isEmpty {
            return URL(fileURLWithPath:
                (to as NSString).expandingTildeInPath)
        }
        return URL(fileURLWithPath: c).deletingLastPathComponent()
            .appendingPathComponent("build")
    }

    /// Where braille lands: the "braille_to" setting, else the build
    /// folder — the engine's rule.
    func brailleFolder() -> URL? {
        guard let c = chart else { return nil }
        let cfgURL = URL(fileURLWithPath: NSHomeDirectory()
            + "/.config/copyist/config.json")
        if let d = try? Data(contentsOf: cfgURL),
           let j = try? JSONSerialization.jsonObject(with: d)
                as? [String: Any],
           let to = (j["braille_to"] as? String)?
                .trimmingCharacters(in: .whitespaces), !to.isEmpty {
            return URL(fileURLWithPath:
                (to as NSString).expandingTildeInPath)
        }
        return URL(fileURLWithPath: c).deletingLastPathComponent()
            .appendingPathComponent("build")
    }

    /// This chart's braille: the .brf files, or the dot pages.
    func brailleFiles(views: Bool) -> [URL] {
        guard let dir = brailleFolder() else { return [] }
        let title = chartName.replacingOccurrences(of: "/", with: " - ")
        let items = (try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: nil)) ?? []
        return items.filter {
            let n = $0.lastPathComponent
            return n.hasPrefix(title + " —") && (views
                ? n.hasSuffix("(braille view).pdf") : n.hasSuffix(".brf"))
        }.sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    /// The MusicXML the last build wrote (score and parts), for
    /// MuseScore, Sibelius, Dorico or Finale. The listening copy is the
    /// engine's own and stays out of the list.
    func musicXMLFiles() -> [URL] {
        guard let c = chart else { return [] }
        let dir = URL(fileURLWithPath: c).deletingLastPathComponent()
            .appendingPathComponent("build")
        let items = (try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: nil)) ?? []
        return items.filter {
            $0.pathExtension == "musicxml"
                && !$0.lastPathComponent.contains("for listening")
        }.sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    /// The conductor score this chart's last build drew, if any.
    func scorePDF() -> URL? {
        guard let dir = pagesFolder(), let c = chart else { return nil }
        let title = chartName
        let items = (try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: nil)) ?? []
        return items.first { $0.lastPathComponent.hasSuffix(
            "— score.pdf") && $0.lastPathComponent.hasPrefix(
                title.replacingOccurrences(of: "/", with: " - ")) }
            ?? items.first { $0.lastPathComponent.hasSuffix(
                "— score.pdf") && c.contains(dir.deletingLastPathComponent()
                    .path) }
    }

    /// A folder setting ("pages_to", "listens_to", "braille_to"), or
    /// the chart's own build folder — the engine's rule.
    func settingFolder(_ key: String) -> URL? {
        guard let c = chart else { return nil }
        let cfgURL = URL(fileURLWithPath: NSHomeDirectory()
            + "/.config/copyist/config.json")
        if let d = try? Data(contentsOf: cfgURL),
           let j = try? JSONSerialization.jsonObject(with: d)
                as? [String: Any],
           let to = (j[key] as? String)?
                .trimmingCharacters(in: .whitespaces), !to.isEmpty {
            return URL(fileURLWithPath:
                (to as NSString).expandingTildeInPath)
        }
        return URL(fileURLWithPath: c).deletingLastPathComponent()
            .appendingPathComponent("build")
    }

    /// This chart's newest listen, where the listens land; with since,
    /// only one made after it (a run that made no listen offers none).
    func newestMP3(since: Date? = nil) -> URL? {
        guard chart != nil, let dir = settingFolder("listens_to") else {
            return nil
        }
        let title = chartName.replacingOccurrences(of: "/", with: " - ")
        guard let items = try? FileManager.default
            .contentsOfDirectory(at: dir, includingPropertiesForKeys:
                [.contentModificationDateKey]) else { return nil }
        return items.filter { $0.pathExtension == "mp3"
            && (dir.lastPathComponent == "build"
                || $0.lastPathComponent.hasPrefix(title))
            && (since == nil || ((try? $0.resourceValues(forKeys:
                [.contentModificationDateKey]).contentModificationDate)
                ?? .distantPast) >= since!.addingTimeInterval(-1)) }
            .max { a, b in
                let da = (try? a.resourceValues(forKeys:
                    [.contentModificationDateKey])
                    .contentModificationDate) ?? .distantPast
                let db = (try? b.resourceValues(forKeys:
                    [.contentModificationDateKey])
                    .contentModificationDate) ?? .distantPast
                return da < db
            }
    }

    private func startFlavor() {
        flavor = Self.flavorLines.randomElement() ?? ""
        flavorTimer = Timer.scheduledTimer(withTimeInterval: 4,
                                           repeats: true) { [weak self] _ in
            self?.flavor = Self.flavorLines.randomElement() ?? ""
        }
    }

    private func stopFlavor() {
        flavorTimer?.invalidate()
        flavorTimer = nil
        flavor = ""
    }

    // ---------------------------------------------- the conversation

    func startTalk(_ args: [String]) {
        guard let tool = Tool.find(), let c = chart else { return }
        let fromDemo = args.first == "new"
        // one conversation at a time: a new one ends the old, whose
        // late ending must not close this one
        if talking { talkProc?.terminate() }
        talkID += 1
        let myTalk = talkID
        talk = []
        question = ""
        questionDefault = ""
        talkBuffer = ""
        talking = true
        userSwitch = false
        tab = .talk
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool.python)
        p.arguments = [tool.script, c] + args
        var env = ProcessInfo.processInfo.environment
        env["COPYIST_PORCELAIN"] = "1"
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:"
            + (env["PATH"] ?? "/usr/bin:/bin")
        env["COPYIST_PROGRESS"] = "1"
        p.environment = env
        let out = Pipe(), inp = Pipe(), err = Pipe()
        p.standardOutput = out
        // tracebacks stay out of the room, but a "chart: ..." line is
        // the engine telling the writer why it stopped — that is shown
        // and spoken, never swallowed
        p.standardError = err
        p.standardInput = inp
        talkStdin = inp.fileHandleForWriting
        out.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            guard !d.isEmpty else { return }
            let s = String(decoding: d, as: UTF8.self)
            DispatchQueue.main.async { self?.receive(s) }
        }
        p.terminationHandler = { [weak self] _ in
            out.fileHandleForReading.readabilityHandler = nil
            let rest = out.fileHandleForReading.readDataToEndOfFile()
            let errText = String(decoding: err.fileHandleForReading
                .readDataToEndOfFile(), as: UTF8.self)
            DispatchQueue.main.async {
                guard let self, myTalk == self.talkID else { return }
                if !rest.isEmpty {
                    self.receive(String(decoding: rest, as: UTF8.self)
                                 + "\n")
                }
                self.talking = false
                self.question = ""
                self.questionDefault = ""
                let why = errText.split(separator: "\n")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .last { $0.hasPrefix("chart") }
                if let why {
                    let t = why.replacingOccurrences(
                        of: #"^chartc?:\s*"#, with: "",
                        options: .regularExpression)
                    self.talk.append(TalkLine(mine: false, text: t))
                }
                let last = self.talk.last(where: { !$0.mine })?.text
                    ?? "That's the conversation."
                // a chart from a demo is ready to build as written: build
                // it now, so the pages and MusicXML are there without
                // another step
                if fromDemo, last.contains("ready to build"),
                   FileManager.default.fileExists(atPath: c) {
                    self.speechFlush?.cancel()
                    self.speechQueue = []
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                        self.run("Build", args: ["build"])
                    }
                    return
                }
                // the answer box just went away and VoiceOver moves to
                // the window; speak once it has settled, or it is lost
                self.speechFlush?.cancel()
                self.speechQueue = []
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                    announce("The conversation ended. " + last
                             + " Build it and hear it, Command B, is next.")
                }
            }
        }
        talkProc = p
        do { try p.run() } catch {
            talking = false
            talk.append(TalkLine(mine: false,
                text: "The conversation would not start: "
                    + error.localizedDescription))
        }
    }

    private func receive(_ chunk: String) {
        talkBuffer += chunk
        while let nl = talkBuffer.firstIndex(of: "\n") {
            let line = String(talkBuffer[..<nl])
            talkBuffer.removeSubrange(...nl)
            guard let d = line.data(using: .utf8),
                  let j = try? JSONSerialization.jsonObject(with: d),
                  let obj = j as? [String: Any],
                  let type = obj["type"] as? String,
                  let text = obj["text"] as? String else {
                // a stray plain line still gets shown, never eaten
                let t = line.trimmingCharacters(in: .whitespaces)
                if !t.isEmpty {
                    talk.append(TalkLine(mine: false, text: t))
                }
                continue
            }
            if type == "say" {
                talk.append(TalkLine(mine: false, text: text))
                queueSpeech(text)
            } else if type == "ask" {
                question = text
                questionDefault = obj["default"] as? String ?? ""
                let hint = questionDefault.isEmpty ? "" :
                    " Return keeps \(questionDefault)."
                // what was said, then the question — one breath
                queueSpeech(text + hint, now: true)
            }
        }
    }

    func answer(_ text: String) {
        guard talking, let h = talkStdin else { return }
        let shown = text.isEmpty
            ? (questionDefault.isEmpty ? "(skipped)"
               : "(kept: \(questionDefault))")
            : text
        talk.append(TalkLine(mine: true, text: shown))
        question = ""
        questionDefault = ""
        h.write(Data((text + "\n").utf8))
    }

    func stopTalk() {
        talkProc?.terminate()
        talking = false
    }
}

// MARK: - Panels (real ones, started where his files are)

func pickChart(_ model: AppModel) {
    let p = NSOpenPanel()
    p.title = "Choose a chart"
    p.directoryURL = chartsFolder()
    p.allowedContentTypes = [UTType(filenameExtension: "chart") ?? .data]
    p.allowsOtherFileTypes = true
    if p.runModal() == .OK, let u = p.url {
        model.choose(u.path)
    }
}

func newChart(_ model: AppModel) -> Bool {
    let p = NSSavePanel()
    p.title = "Name the new chart"
    p.directoryURL = chartsFolder()
    p.nameFieldStringValue = "New Tune.chart"
    if p.runModal() == .OK, let u = p.url {
        model.choose(u.path)
        return true
    }
    return false
}

/// A tune from nothing: name it, then the conversation — the demo is
/// asked for, and Return means none (you name the band instead).
func startNewChart(_ model: AppModel) {
    let p = NSSavePanel()
    p.title = "Name the new tune"
    p.message = "Then describe it. A played demo is welcome but not "
        + "needed."
    p.prompt = "Start"
    p.directoryURL = chartsFolder()
    p.nameFieldStringValue = "New Tune"
    p.allowedContentTypes = [UTType(filenameExtension: "chart") ?? .data]
    guard p.runModal() == .OK, var u = p.url else { return }
    if u.pathExtension != "chart" { u.appendPathExtension("chart") }
    // each tune gets its own folder, the Copyist Charts way
    let name = u.deletingPathExtension().lastPathComponent
    if u.deletingLastPathComponent().lastPathComponent != name {
        let folder = u.deletingLastPathComponent()
            .appendingPathComponent(name)
        try? FileManager.default.createDirectory(
            at: folder, withIntermediateDirectories: true)
        u = folder.appendingPathComponent(name + ".chart")
    }
    if FileManager.default.fileExists(atPath: u.path) {
        announce("There is already a chart called \(name). Opening it.")
        model.choose(u.path)
        return
    }
    model.choose(u.path)
    model.startTalk(["edit"])
}

func pickAnything(_ model: AppModel) {
    let p = NSOpenPanel()
    p.title = "Bring in a file"
    p.message = "A score (MusicXML), a MIDI demo, or words and chords "
        + "in any format. Several MIDI files at once make one chart."
    p.prompt = "Bring In"
    p.canChooseFiles = true
    p.canChooseDirectories = false
    p.allowsOtherFileTypes = true
    // a DAW's one-file-per-instrument export: pick them all, one chart
    p.allowsMultipleSelection = true
    p.directoryURL = FileManager.default.urls(
        for: .downloadsDirectory, in: .userDomainMask).first
    if p.runModal() == .OK, !p.urls.isEmpty {
        model.bringIn(p.urls.map(\.path))
    }
}

func pickFile(start: String?, dirs: Bool = false) -> String? {
    let p = NSOpenPanel()
    p.canChooseDirectories = dirs
    p.canChooseFiles = !dirs
    if let s = start, FileManager.default.fileExists(atPath: s) {
        p.directoryURL = URL(fileURLWithPath: s)
    }
    return p.runModal() == .OK ? p.url?.path : nil
}

// MARK: - The app

@main
struct CopyistApp: App {
    init() {
        // Copyist's own tabs are the tabs; the system's window tabs
        // would put a second "Show Tab Bar" in View beside them
        NSWindow.allowsAutomaticWindowTabbing = false
    }

    var body: some Scene {
        // each window is its own desk: its own chart, its own build —
        // File > New Window works on a second chart while the first
        // one cooks
        WindowGroup("Copyist") {
            ContentView()
                .frame(minWidth: 820, minHeight: 600)
        }
        .windowResizability(.contentMinSize)
        .commands { DeskCommands() }
    }
}

/// The menu bar is where a VoiceOver user goes looking for what an app
/// can do, so everything lives there with its key: the tabs in View
/// (Command 1 to 5), the work in a Chart menu, Settings on Command
/// comma like every Mac app. Each acts on the window in front.
struct DeskCommands: Commands {
    @FocusedObject var model: AppModel?

    var body: some Commands {
        CommandGroup(after: .newItem) {
            Button("New Chart…") {
                if let m = model { startNewChart(m) }
            }
            .keyboardShortcut("n", modifiers: [.command, .shift])
            .disabled(model == nil)
            Button("Open a Chart…") {
                if let m = model { pickChart(m) }
            }
            .keyboardShortcut("o", modifiers: .command)
            .disabled(model == nil)
            Button("Bring In a File…") {
                if let m = model { pickAnything(m) }
            }
            .keyboardShortcut("i", modifiers: [.command, .shift])
            .disabled(model == nil)
        }
        CommandGroup(replacing: .appSettings) {
            Button("Settings…") { model?.go(.settings) }
                .keyboardShortcut(",", modifiers: .command)
                .disabled(model == nil)
        }
        CommandGroup(before: .toolbar) {
            ForEach(Tab.allCases) { t in
                Button(t.title) { model?.go(t) }
                    .keyboardShortcut(t.key, modifiers: .command)
                    .disabled(model == nil)
            }
            Divider()
            Button("Bigger Text") { model?.textSize(1) }
                .keyboardShortcut("=", modifiers: .command)
                .disabled(model == nil)
            Button("Smaller Text") { model?.textSize(-1) }
                .keyboardShortcut("-", modifiers: .command)
                .disabled(model == nil)
            Button("Actual Size Text") { model?.textSize(0) }
                .keyboardShortcut("0", modifiers: .command)
                .disabled(model == nil)
            Divider()
        }
        CommandMenu("Chart") {
            Button("Build") { model?.run("Build", args: ["build"]) }
                .keyboardShortcut("b", modifiers: .command)
                .disabled(model?.chart == nil)
            Button("Check") { model?.run("Check", args: ["check"]) }
                .keyboardShortcut("k", modifiers: .command)
                .disabled(model?.chart == nil)
            Button("What Changed") {
                model?.run("What changed", args: ["diff"])
            }
            .keyboardShortcut("d", modifiers: .command)
            .disabled(model?.chart == nil)
            Button("Export…") { model?.showExport = true }
                .keyboardShortcut("e", modifiers: .command)
                .disabled(model?.chart == nil)
            Button("Braille") { model?.run("Braille", args: ["braille"]) }
                .keyboardShortcut("b", modifiers: [.command, .shift])
                .disabled(model?.chart == nil)
            Button("Emboss…") { model?.emboss() }
                .disabled(model?.chart == nil)
            Divider()
            Button("Listen") { model?.go(.listen) }
                .keyboardShortcut("l", modifiers: .command)
                .disabled(model?.chart == nil)
            Button("Play the Last Listen") {
                if let u = model?.newestMP3() {
                    NSWorkspace.shared.open(u)
                } else {
                    announce("No listen yet. Build it first, Command B.")
                }
            }
            .keyboardShortcut("p", modifiers: .command)
            .disabled(model?.chart == nil)
            Button("Open the Score") {
                if let u = model?.scorePDF() {
                    NSWorkspace.shared.open(u)
                } else {
                    announce("No score pages yet. Build it first, "
                             + "Command B.")
                }
            }
            .keyboardShortcut("e", modifiers: [.command, .shift])
            .disabled(model?.chart == nil)
            Button("Show the MusicXML") {
                if let xml = model?.musicXMLFiles(), !xml.isEmpty {
                    NSWorkspace.shared.activateFileViewerSelecting(xml)
                } else {
                    announce("No MusicXML yet. Build it first, Command B.")
                }
            }
            .keyboardShortcut("x", modifiers: [.command, .shift])
            .disabled(model?.chart == nil)
            Divider()
            Button("Tell Me the Tune") {
                if let m = model {
                    if m.chart == nil && !newChart(m) { return }
                    m.startTalk(["edit"])
                }
            }
            .keyboardShortcut("t", modifiers: [.command, .shift])
            .disabled(model == nil)
            Divider()
            Button("Stop") {
                model?.stopRun()
            }
            .keyboardShortcut(".", modifiers: .command)
            .disabled(model?.running != true)
        }
    }
}

struct ContentView: View {
    @StateObject private var model = AppModel()
    @Environment(\.colorScheme) var scheme

    var pal: Palette {
        switch model.vibe {
        case .stage: return .stage
        case .manuscript: return .manuscript
        case .system: return scheme == .dark ? .stage : .manuscript
        }
    }

    var body: some View {
        ZStack {
            pal.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                HeaderBar(pal: pal)
                TabStrip(pal: pal)
                Divider().overlay(pal.edge)
                Group {
                    switch model.tab {
                    case .chart: ChartTab(pal: pal)
                    case .build: BuildTab(pal: pal)
                    case .listen: ListenTab(pal: pal)
                    case .talk: TalkView(pal: pal)
                    case .settings: SettingsView(pal: pal)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity,
                       alignment: .topLeading)
            }
            // every control's own words (buttons, toggles, pickers) take
            // the text size too, not just the text the app styles itself
            .font(.system(size: ts(13)))
            .deskButtons()
            // a new text size redraws everything at it; controls grow too
            .id(model.textScale)
            .controlSize(model.textScale >= 1.4 ? .large : .regular)
        }
        // each window is named for its chart, so the Window menu and
        // Command backtick can tell two desks apart
        .navigationTitle(model.chart == nil ? "Copyist"
                         : "Copyist — \(model.chartName)")
        .preferredColorScheme(model.vibe == .stage ? .dark :
                              model.vibe == .manuscript ? .light : nil)
        .foregroundStyle(pal.text)
        // Export and Emboss belong to the window, not one tab: Command E
        // from the Chart tab used to do nothing, then pop the sheet up
        // later, the moment the Build tab appeared
        .sheet(isPresented: $model.showExport) {
            ExportSheet(pal: pal).environmentObject(model)
                // a sheet is its own window: it takes the text size too
                .font(.system(size: ts(13)))
                .deskButtons()
                .controlSize(model.textScale >= 1.4 ? .large : .regular)
        }
        .confirmationDialog("Emboss every part's braille on "
                            + model.embosser() + "?",
                            isPresented: $model.askEmboss) {
            Button("Emboss") { model.run("Emboss", args: ["emboss"]) }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Each part the braille covers goes to the embosser, "
                 + "on the paper size in Settings. Anything the "
                 + "proofreader disagrees with is held back.")
        }
        .environmentObject(model)
        .focusedSceneObject(model)
        .onAppear { model.loadParts() }
        // a .chart opened from the Finder (double-click, Open With)
        // lands in the window in front, like File > Open a Chart
        .handlesExternalEvents(preferring: ["*"], allowing: ["*"])
        .onOpenURL { url in
            guard url.isFileURL else { return }
            if url.pathExtension.lowercased() == "chart" {
                model.choose(url.path)
                announce("Working on "
                         + url.deletingPathExtension().lastPathComponent
                         + ".")
            } else {
                model.bringIn(url.path)
            }
        }
        .onChange(of: model.tab) { t in
            guard model.userSwitch else { return }
            // the heading takes VoiceOver there and says the tab's name;
            // what the tab holds follows, once, after it
            // (measured: posted at once, or at low priority, VoiceOver
            // drops it under the heading; a beat later it follows it)
            if model.speakTabs {
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.1) {
                    if model.tab == t { announce(t.blurb, queued: true) }
                }
            }
        }
        .onDrop(of: [.fileURL], isTargeted: nil) { items in
            // any file dropped on the window comes in the same door;
            // several MIDI demos dropped together are one chart
            guard !items.isEmpty else { return false }
            let group = DispatchGroup()
            var urls: [Int: URL] = [:]
            let lock = NSLock()
            for (i, item) in items.enumerated() {
                group.enter()
                _ = item.loadObject(ofClass: URL.self) { url, _ in
                    if let url {
                        lock.lock(); urls[i] = url; lock.unlock()
                    }
                    group.leave()
                }
            }
            group.notify(queue: .main) {
                let got = urls.keys.sorted().compactMap { urls[$0] }
                guard !got.isEmpty else { return }
                // no "bringing in" line of its own: the run's "started"
                // or the interview's first words follow at once, and
                // two at the same moment cut each other off
                model.bringIn(got.map(\.path))
            }
            return true
        }
    }
}

// MARK: - Header and tabs

struct HeaderBar: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "music.quarternote.3")
                .font(.system(size: ts(22), weight: .bold))
                .foregroundStyle(pal.accent)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 1) {
                Text("Copyist")
                    .font(.system(size: ts(20), weight: .bold, design: .serif))
                Text(model.chart == nil ? "No chart open"
                     : "Working on \(model.chartName)")
                    .font(.system(size: ts(12)))
                    .foregroundStyle(pal.sub)
                    .lineLimit(1)
            }
            .accessibilityElement(children: .combine)
            Spacer()
            if model.running && model.tab != model.runTab {
                // a build going elsewhere stays one click away
                Button {
                    model.tab = model.runTab
                } label: {
                    HStack(spacing: 8) {
                        if let p = model.progressPct {
                            ProgressView(value: p, total: 100)
                                .frame(width: 80)
                                .tint(pal.accent)
                        } else {
                            ProgressView().controlSize(.small)
                        }
                        Text(model.runTitle
                             + (model.progressPct.map { " \(Int($0))%" }
                                ?? ""))
                            .font(.system(size: ts(12), weight: .semibold))
                    }
                }
                .deskButton()
                .accessibilityLabel("\(model.runTitle) is still going"
                    + (model.progressPct.map { ", \(Int($0)) percent" }
                       ?? "") + ". Go to it.")
            }
            Button {
                pickChart(model)
            } label: {
                Label("Open a chart", systemImage: "folder")
            }
            .deskButton()
            .help("Open a chart (Command O)")
            .accessibilityHint("Command O")
        }
        .padding(.horizontal, 20)
        .padding(.top, 14)
        .padding(.bottom, 10)
    }
}

/// Five tabs across the top, each saying where it sits and its key.
struct TabStrip: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette

    var body: some View {
        // wraps to a second row at a big text size; a tab's name never
        // breaks mid-word ("Cha / rt" at 200 percent, 2026-10-17)
        FlowLayout(spacing: 6) {
            ForEach(Tab.allCases) { t in
                let on = model.tab == t
                Button {
                    model.go(t)
                } label: {
                    HStack(spacing: 7) {
                        Image(systemName: t.icon)
                            .font(.system(size: ts(13), weight: .semibold))
                        Text(t.title)
                            .font(.system(size: ts(13), weight: on ? .bold
                                                              : .medium))
                            .lineLimit(1)
                            .fixedSize()
                        Text("⌘\(t.rawValue)")
                            .font(.system(size: ts(10), weight: .medium,
                                          design: .rounded))
                            .foregroundStyle(on ? pal.accentText
                                                  .opacity(0.75)
                                             : pal.sub)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .foregroundStyle(on ? pal.accentText : pal.text)
                    .background(Capsule().fill(on ? pal.accent : pal.card))
                    .overlay(Capsule().stroke(on ? pal.accent : pal.edge,
                                              lineWidth: 1))
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(t.title)
                .accessibilityValue("tab \(t.rawValue) of "
                                    + "\(Tab.allCases.count)")
                .accessibilityHint("Command \(t.rawValue)")
                .accessibilityAddTraits(on ? [.isSelected] : [])
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20)
        .padding(.bottom, 10)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Tabs")
    }
}

/// Every tab opens on its heading. VoiceOver lands there on arrival,
/// so switching tabs always says where you are.
struct TabHeading: View {
    @EnvironmentObject var model: AppModel
    let tab: Tab
    let pal: Palette
    @AccessibilityFocusState private var here: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(tab.title)
                .font(.system(size: ts(22), weight: .bold, design: .serif))
                .accessibilityLabel(tab.spokenPlace)
                .accessibilityAddTraits(.isHeader)
                .accessibilityFocused($here)
            Text(tab.blurb)
                .font(.system(size: ts(13)))
                .foregroundStyle(pal.sub)
                .accessibilityHidden(true)   // said on arrival already
        }
        .padding(.top, 16)
        .onAppear {
            guard model.userSwitch else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                here = true
            }
        }
        .onChange(of: model.tabPing) { _ in
            // the key for the tab already showing: back to its top
            here = false
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                here = true
            }
        }
    }
}

/// A group of related controls on a card, its title a heading.
struct Card<Content: View>: View {
    let title: String
    let pal: Palette
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.system(size: ts(14), weight: .semibold))
                .foregroundStyle(pal.sub)
                .accessibilityAddTraits(.isHeader)
            content
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(pal.card))
        .overlay(RoundedRectangle(cornerRadius: 12)
            .stroke(pal.edge, lineWidth: 1))
    }
}

/// A big labelled action: icon, name, one line, and its key.
struct ActionButton: View {
    let icon: String
    let title: String
    let line: String
    var keys: String = ""
    let pal: Palette
    var enabled: Bool = true
    let act: () -> Void

    var body: some View {
        Button(action: act) {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.system(size: ts(20), weight: .semibold))
                    .foregroundStyle(pal.accent)
                    .frame(width: ts(28))       // grows with its icon
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: ts(15), weight: .semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Text(line)
                        .font(.system(size: ts(12)))
                        .foregroundStyle(pal.sub)
                        // wraps, never "fr…": the rest of it is the point
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                if !keys.isEmpty {
                    Text(keys)
                        .font(.system(size: ts(11), weight: .medium,
                                      design: .rounded))
                        .foregroundStyle(pal.sub)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(RoundedRectangle(cornerRadius: 5)
                            .stroke(pal.edge, lineWidth: 1))
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, maxHeight: .infinity,
                   alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 10)
                .fill(pal.bg.opacity(0.5)))
            .overlay(RoundedRectangle(cornerRadius: 10)
                .stroke(pal.edge, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.6)
        // label the Button itself: wrapping it in a combined element
        // hides its press action, and VoiceOver's press does nothing
        .accessibilityLabel(title)
        .accessibilityHint(keys.isEmpty ? line
            : (line.hasSuffix(".") ? String(line.dropLast()) : line)
              + ". " + spokenKeys(keys))
    }
}

/// "⇧⌘I" (the Mac's printed order) said the way VoiceOver users say
/// it: "Command Shift I", Command first, whatever the order on screen.
func spokenKeys(_ k: String) -> String {
    let names: [Character: String] = ["⌘": "Command", "⇧": "Shift",
                                      "⌥": "Option", "⌃": "Control"]
    let mods = "⌘⇧⌥⌃".filter { k.contains($0) }.map { names[$0]! }
    let rest = k.filter { names[$0] == nil }.map(String.init)
    return (mods + rest).joined(separator: " ")
}

// MARK: - Chart tab

struct ChartTab: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                TabHeading(tab: .chart, pal: pal)
                Card(title: model.chart == nil ? "No chart open yet"
                     : "Open now: \(model.chartName)", pal: pal) {
                    if let c = model.chart {
                        Text(URL(fileURLWithPath: c)
                                .deletingLastPathComponent().path)
                            .font(.system(size: ts(11)))
                            .foregroundStyle(pal.sub)
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .accessibilityLabel("In the folder "
                                + URL(fileURLWithPath: c)
                                    .deletingLastPathComponent()
                                    .lastPathComponent)
                        if !model.parts.isEmpty {
                            Text("The band, \(model.parts.count) chairs: "
                                 + model.parts.joined(separator: ", "))
                                .font(.system(size: ts(13)))
                        }
                    }
                    ActionButton(icon: "plus.square", title: "New chart",
                                 line: "Name it, then describe the tune. "
                                     + "A demo is welcome, not needed.",
                                 keys: "⇧⌘N", pal: pal) {
                        startNewChart(model)
                    }
                    ActionButton(icon: "folder", title: "Open a chart",
                                 line: "From your Copyist Charts folder.",
                                 keys: "⌘O", pal: pal) { pickChart(model) }
                    ActionButton(icon: "tray.and.arrow.down",
                                 title: "Bring in a file",
                                 line: "A score, a MIDI demo, or words and "
                                     + "chords in any format. Or drop it "
                                     + "on the window.",
                                 keys: "⇧⌘I", pal: pal) {
                        pickAnything(model)
                    }
                    ActionButton(icon: "bubble.left.and.bubble.right",
                                 title: "Tell me the tune",
                                 line: "Describe it in one breath. Copyist "
                                     + "writes the sections.",
                                 keys: "⇧⌘T", pal: pal) {
                        if model.chart == nil && !newChart(model) { return }
                        model.startTalk(["edit"])
                    }
                }
                if !model.recents.isEmpty {
                    Card(title: "Recent charts", pal: pal) {
                        ForEach(model.recents, id: \.self) { r in
                            let name = URL(fileURLWithPath: r)
                                .deletingPathExtension().lastPathComponent
                            let on = r == model.chart
                            Button {
                                model.choose(r)
                                announce("Now working on \(name).")
                            } label: {
                                HStack {
                                    Image(systemName: on ? "checkmark.circle.fill"
                                                         : "clock")
                                        .foregroundStyle(on ? pal.accent
                                                            : pal.sub)
                                    Text(name)
                                        .font(.system(size: ts(14),
                                                      weight: on ? .semibold
                                                                 : .regular))
                                    Spacer()
                                }
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel(name)
                            .accessibilityValue(on ? "open now" : "")
                        }
                    }
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 24)
        }
    }
}

// MARK: - Build tab

struct DeskAction: Identifiable {
    var id: String { title }
    let icon: String, title: String, line: String, keys: String
    let act: () -> Void
}

struct BuildTab: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette

    var columns: Int {
        model.textScale >= 1.75 ? 1 : model.textScale >= 1.3 ? 2 : 3
    }

    var actions: [DeskAction] {
        let m = model
        return [
            DeskAction(icon: "hammer", title: "Build it",
                       line: "Pages, read-alouds, findings, and the band "
                           + "plays it.", keys: "⌘B") {
                m.run("Build", args: ["build"]) },
            DeskAction(icon: "checkmark.seal", title: "Check it",
                       line: "Prove every bar adds up. Nothing rendered.",
                       keys: "⌘K") { m.run("Check", args: ["check"]) },
            DeskAction(icon: "arrow.triangle.2.circlepath",
                       title: "What changed",
                       line: "Since the last build, by part and bar.",
                       keys: "⌘D") { m.run("What changed", args: ["diff"]) },
            DeskAction(icon: "square.and.arrow.up", title: "Export…",
                       line: "Choose the bars, the parts, the look and "
                           + "what to make.", keys: "⌘E") {
                m.showExport = true },
            DeskAction(icon: "hand.point.up.braille", title: "Braille",
                       line: "Just the braille: a file for each part, read "
                           + "back against the score.", keys: "⇧⌘B") {
                m.run("Braille", args: ["braille"]) },
            DeskAction(icon: "printer", title: "Emboss",
                       line: "Send the braille to your embosser, after you "
                           + "say yes.", keys: "") { m.emboss() },
        ]
    }

    var desk: some View {
        VStack(alignment: .leading, spacing: 14) {
            TabHeading(tab: .build, pal: pal)
            // three across, two at a bigger text size, one at the
            // biggest: six in one row left each a sliver, and at 200
            // percent even three were towers of broken words
            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(stride(from: 0, to: actions.count,
                                     by: columns)), id: \.self) { i in
                    HStack(alignment: .top, spacing: 10) {
                        ForEach(actions[i..<min(i + columns,
                                                actions.count)]) { d in
                            ActionButton(icon: d.icon, title: d.title,
                                         line: d.line, keys: d.keys,
                                         pal: pal,
                                         enabled: model.chart != nil,
                                         act: d.act)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
            RunPanel(pal: pal, tab: .build,
                     transcriptHeight: scrolls ? ts(300) : nil)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 20)
    }

    /// past a little bigger the tab is taller than the window (a 1080
    /// screen at 200 percent): it scrolls, so the results stay reachable
    var scrolls: Bool { model.textScale > 1.15 }

    var body: some View {
        if scrolls {
            ScrollView { desk }
        } else {
            desk
        }
    }
}

/// The export picker: which bars, which parts, what to make, and how
/// the pages look — with a real sample page to choose the look by.
struct ExportSheet: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) var dismiss
    let pal: Palette
    @State private var whole = true
    @State private var fromBar = ""
    @State private var toBar = ""
    @State private var score = true
    @State private var chosen: Set<String> = []
    @State private var makes: Set<String> = []
    @State private var look = ""
    @State private var sample: URL?
    @State private var sampling = false
    @State private var note = ""

    let formats = [("pages", "Pages — the PDF charts"),
                   ("listen", "Listen — the MP3"),
                   ("braille", "Braille — a file for each part"),
                   ("braille pages", "Braille pages — the dots drawn"),
                   ("read-alouds", "Read-alouds — each part as text"),
                   ("ireal", "iReal Pro — a link that opens in the app"),
                   ("midi", "MIDI — the band, one track per player"),
                   ("chords", "Chord sheet — plain text with barlines")]
    let looks = [("", "The chart's own"), ("jazz", "Jazz"),
                 ("handwritten", "Handwritten"), ("engraved", "Engraved"),
                 ("plain", "Plain")]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Export")
                    .font(.system(size: ts(22), weight: .bold, design: .serif))
                    .accessibilityAddTraits(.isHeader)
                box("Bars") {
                    Toggle("The whole song", isOn: $whole)
                    if !whole {
                        HStack {
                            // the field speaks its own contents; a
                            // placeholder AND a label said the name twice
                            TextField("", text: $fromBar,
                                      prompt: Text("From bar"))
                                .frame(width: 90)
                                .accessibilityLabel("From bar")
                            TextField("", text: $toBar,
                                      prompt: Text("To bar"))
                                .frame(width: 90)
                                .accessibilityLabel("To bar")
                            Text("as printed on the pages")
                                .font(.system(size: ts(11)))
                                .foregroundStyle(pal.sub)
                        }
                        .textFieldStyle(.roundedBorder)
                    }
                }
                box("Parts") {
                    Toggle("The score", isOn: $score)
                    HStack {
                        // seven boxes changing at once must say so
                        Button("Every part") {
                            chosen = Set(model.parts)
                            announce("All \(model.parts.count) parts "
                                     + "picked.")
                        }
                        Button("No parts") {
                            chosen = []
                            announce("No parts picked. The score is "
                                     + (score ? "still on." : "off too."))
                        }
                    }
                    ForEach(model.parts, id: \.self) { p in
                        Toggle(p, isOn: Binding(
                            get: { chosen.contains(p) },
                            set: { on in
                                if on { chosen.insert(p) }
                                else { chosen.remove(p) } }))
                    }
                }
                box("What to make") {
                    ForEach(formats, id: \.0) { key, label in
                        Toggle(label, isOn: Binding(
                            get: { makes.contains(key) },
                            set: { on in
                                if on { makes.insert(key) }
                                else { makes.remove(key) } }))
                    }
                }
                box("How the pages look") {
                    Picker("Look", selection: $look) {
                        ForEach(looks, id: \.0) { key, label in
                            Text(label).tag(key)
                        }
                    }
                        .accessibilityLabel("Look")
                    .pickerStyle(.segmented)
                    .onChange(of: look) { _ in sample = nil }
                    HStack {
                        Button(sampling ? "Drawing a sample…"
                                        : "Show a sample page") {
                            drawSample()
                        }
                        .disabled(sampling)
                        Text("The first bars of the first thing picked, "
                             + "in this look.")
                            .font(.system(size: ts(11)))
                            .foregroundStyle(pal.sub)
                    }
                    if let u = sample {
                        PDFPreview(url: u)
                            .frame(height: 420)
                            .accessibilityLabel("Sample page in the "
                                + (looks.first { $0.0 == look }?.1
                                   ?? "chart's own") + " look")
                        Button("Open the sample in Preview") {
                            NSWorkspace.shared.open(u)
                        }
                    }
                }
                if !note.isEmpty {
                    Text(note).foregroundStyle(pal.sub)
                        .accessibilityAddTraits(.updatesFrequently)
                }
                HStack {
                    Spacer()
                    Button("Cancel") { dismiss() }
                        .keyboardShortcut(.cancelAction)
                    Button("Export") { export() }
                        .keyboardShortcut(.defaultAction)
                        .deskButton(fill: pal.accent, ink: pal.accentText)
                        .tint(pal.accent)
                        // the label in the accent's own ink: white on amber read at 1.6:1
                        .foregroundStyle(pal.accentText)
                }
            }
            .padding(24)
        }
        .frame(minWidth: 560, minHeight: 620)
        .onAppear {
            chosen = Set(model.parts)
            let cfgURL = URL(fileURLWithPath: NSHomeDirectory()
                + "/.config/copyist/config.json")
            var ex = "pages, listen, braille, read-alouds"
            if let d = try? Data(contentsOf: cfgURL),
               let j = try? JSONSerialization.jsonObject(with: d)
                    as? [String: Any], let e = j["exports"] as? String {
                ex = e
            }
            makes = Set(ex.split(separator: ",").map {
                $0.trimmingCharacters(in: .whitespaces) })
        }
    }

    @ViewBuilder
    func box(_ title: String,
             @ViewBuilder _ content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: ts(14), weight: .semibold))
                .foregroundStyle(pal.sub)
                .accessibilityAddTraits(.isHeader)
            content()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(pal.card))
    }

    /// The picker as engine words.
    func pick() -> [String] {
        var a: [String] = []
        if !whole {
            let f = fromBar.trimmingCharacters(in: .whitespaces)
            let t = toBar.trimmingCharacters(in: .whitespaces)
            a += ["--bars", t.isEmpty ? f : "\(f)-\(t)"]
        }
        if !(score && chosen.count == model.parts.count) {
            var who = Array(chosen).sorted {
                (model.parts.firstIndex(of: $0) ?? 0)
                    < (model.parts.firstIndex(of: $1) ?? 0) }
            if score { who.insert("score", at: 0) }
            if !score && chosen.count == model.parts.count {
                who = ["parts"]
            }
            a += ["--parts", who.joined(separator: ", ")]
        }
        if !look.isEmpty { a += ["--look", look] }
        return a
    }

    func export() {
        let f = fromBar.trimmingCharacters(in: .whitespaces)
        let t = toBar.trimmingCharacters(in: .whitespaces)
        if !whole && (Int(f) == nil || !(t.isEmpty || Int(t) != nil)) {
            // left empty, the engine quietly made the whole song
            note = f.isEmpty
                ? "Type the bar to start from, or check The whole song."
                : "Bars are numbers, like 9 and 24."
            say(note)
            return
        }
        if !score && chosen.isEmpty {
            note = "Pick the score or at least one part."
            say(note)
            return
        }
        if makes.isEmpty {
            note = "Pick at least one thing to make."
            say(note)
            return
        }
        let order = formats.map { $0.0 }.filter { makes.contains($0) }
        dismiss()
        model.run("Export", args: ["build", "--exports",
                                   order.joined(separator: ", ")] + pick())
    }

    /// A warning in the sheet: the note text appears, and the spoken line
    /// follows a beat later so VoiceOver does not lose it under the
    /// note's own arrival.
    func say(_ text: String) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
            announce(text)
        }
    }

    func drawSample() {
        guard let tool = Tool.find(), let c = model.chart else { return }
        sampling = true
        note = "Drawing a sample page…"
        let args = [tool.script, c, "preview"] + pick()
        DispatchQueue.global().async {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: tool.python)
            p.arguments = args
            let pipe = Pipe()
            p.standardOutput = pipe
            p.standardError = pipe
            try? p.run()
            p.waitUntilExit()
            let out = String(decoding: pipe.fileHandleForReading
                .readDataToEndOfFile(), as: UTF8.self)
            let line = out.split(separator: "\n").last {
                $0.contains("Sample page in the") } ?? ""
            let path = line.components(separatedBy: " look: ").last ?? ""
            DispatchQueue.main.async {
                sampling = false
                if !path.isEmpty, FileManager.default.fileExists(
                    atPath: String(path)) {
                    sample = URL(fileURLWithPath: String(path))
                    note = "Sample page drawn."
                } else {
                    note = out.split(separator: "\n").last
                        .map(String.init) ?? "No sample page."
                }
                announce(note)
            }
        }
    }
}

/// A PDF page shown in place.
struct PDFPreview: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.displayMode = .singlePage
        v.document = PDFDocument(url: url)
        return v
    }

    func updateNSView(_ v: PDFView, context: Context) {
        if v.document?.documentURL != url {
            v.document = PDFDocument(url: url)
        }
    }
}

/// The run's progress, its result buttons and its transcript. The
/// transcript is one element per line, so VoiceOver walks it line by
/// line instead of reading a wall.
struct RunPanel: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette
    let tab: Tab
    /// inside a scrolling tab the transcript needs a height of its own
    /// (a scroll view in a scroll view otherwise folds to nothing)
    var transcriptHeight: CGFloat? = nil
    /// a run the app started (not a tab the writer chose) takes
    /// VoiceOver to its title, so the cursor is never left on a button
    /// that just went away with the old tab
    @AccessibilityFocusState private var onTitle: Bool

    var emptyLine: String {
        if model.chart == nil {
            return "Open or start a chart first: the Chart tab, Command 1."
        }
        if !model.runTitle.isEmpty && model.runTab != tab {
            return "The last run, \(model.runTitle), is on the "
                + "\(model.runTab.title) tab."
        }
        return tab == .build
            ? "Nothing built yet in this window. Build it, Command B."
            : "Nothing played or read yet in this window."
    }

    var body: some View {
        if model.runTab != tab || (model.runTitle.isEmpty
                                   && !model.running) {
            Text(emptyLine)
                .font(.system(size: ts(13)))
                .foregroundStyle(pal.sub)
        } else {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Text(model.runTitle)
                        .font(.system(size: ts(17), weight: .bold,
                                      design: .serif))
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityFocused($onTitle)
                        .onAppear {
                            guard !model.userSwitch else { return }
                            DispatchQueue.main.asyncAfter(
                                deadline: .now() + 0.3) { onTitle = true }
                        }
                    if model.running {
                        if let pct = model.progressPct {
                            ProgressView(value: pct, total: 100)
                                .frame(width: 160)
                                .tint(pal.accent)
                                .accessibilityLabel("Progress")
                                .accessibilityValue("\(Int(pct)) percent, "
                                                    + model.progressWhat)
                            Text("\(Int(pct))% — \(model.progressWhat)")
                                .font(.system(size: ts(12)))
                                .foregroundStyle(pal.sub)
                                .accessibilityHidden(true)
                        } else {
                            ProgressView().controlSize(.small)
                                .accessibilityLabel("Working")
                            Text(model.flavor)
                                .font(.system(size: ts(12)))
                                .foregroundStyle(pal.sub)
                                .accessibilityHidden(true)
                        }
                        Spacer()
                        Button("Stop") { model.stopRun() }
                            .deskButton()
                            .accessibilityHint("Command period")
                    } else {
                        Spacer()
                    }
                }
                if !model.runEnded.isEmpty {
                    // not finished: said in words and drawn, never by
                    // colour alone
                    HStack(spacing: 8) {
                        Image(systemName: model.runEnded == "stopped"
                              ? "stop.circle" : "exclamationmark.triangle")
                            .font(.system(size: ts(15)))
                            .foregroundStyle(pal.accent)
                            .accessibilityHidden(true)
                        Text(model.runEnded == "stopped"
                             ? "Stopped. Nothing after the last line below "
                               + "was made."
                             : "This stopped on a problem. The last lines "
                               + "below say why.")
                            .font(.system(size: ts(14), weight: .semibold))
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 10)
                        .stroke(pal.accent, lineWidth: 2))
                    .accessibilityElement(children: .combine)
                }
                if !model.running { ResultButtons(pal: pal) }
                ScrollViewReader { proxy in
                    ScrollView {
                        // a plain stack, not a lazy one: VoiceOver cannot
                        // move into a lazy list's lines (measured 2026-09-28)
                        VStack(alignment: .leading, spacing: 3) {
                            if model.runLines.isEmpty {
                                Text(model.running ? "On it…" : "Done.")
                                    .foregroundStyle(pal.sub)
                            }
                            ForEach(Array(model.runLines.enumerated()),
                                    id: \.offset) { i, line in
                                TranscriptLine(line: line, pal: pal)
                                    .id(i)
                            }
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .background(RoundedRectangle(cornerRadius: 12)
                        .fill(pal.card))
                    .overlay(RoundedRectangle(cornerRadius: 12)
                        .stroke(pal.edge, lineWidth: 1))
                    .accessibilityLabel("Transcript, \(model.runLines.count) "
                                        + "lines")
                    .onChange(of: model.runOutput) { _ in
                        proxy.scrollTo(model.runLines.count - 1,
                                       anchor: .bottom)
                    }
                }
                .frame(minHeight: transcriptHeight,
                       maxHeight: transcriptHeight)
            }
        }
    }
}

/// One line of what the engine said. Findings read as findings, dressed
/// quieter on screen; the words are exactly what the engine wrote.
struct TranscriptLine: View {
    let line: String
    let pal: Palette

    var body: some View {
        let finding = line.hasPrefix("finding: ")
        let body = finding ? String(line.dropFirst("finding: ".count))
                           : line
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            if finding {
                // a finding is the line most worth reading: full
                // contrast, full size, marked by its icon, not by fading
                Image(systemName: "exclamationmark.circle")
                    .font(.system(size: ts(12)))
                    .foregroundStyle(pal.accent)
                    .accessibilityHidden(true)
            }
            Text(body)
                // the engine speaks prose: drawn in the reading face,
                // not a typewriter's
                .font(.system(size: ts(13)))
                .foregroundStyle(pal.text)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(finding ? "Finding: " + body : body)
        .accessibilityAddTraits(.isStaticText)
    }
}

/// What a finished run offers next, each only when it applies.
struct ResultButtons: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette

    var body: some View {
        // wraps onto a second row rather than squeezing six buttons
        // into one at a big text size
        FlowLayout(spacing: 8) {
            if let u = model.playURL {
                Button {
                    NSWorkspace.shared.open(u)
                } label: {
                    Label("Play the listen", systemImage: "play.fill")
                }
                .deskButton(fill: pal.accent, ink: pal.accentText)
                .tint(pal.accent)
                // the label in the accent's own ink: white on amber read at 1.6:1
                .foregroundStyle(pal.accentText)
                .accessibilityHint("Command P")
            }
            if model.chart != nil {
                if model.runOutput.contains("Braille files")
                    || model.runOutput.contains("Braille views") {
                    let brf = model.brailleFiles(views: false)
                    let views = model.brailleFiles(views: true)
                    if !brf.isEmpty {
                        Button {
                            NSWorkspace.shared
                                .activateFileViewerSelecting(brf)
                        } label: {
                            Label("Show the braille files",
                                  systemImage: "hand.point.up.braille")
                        }
                        .deskButton()
                        .accessibilityHint("\(brf.count) files, selected "
                                           + "in the Finder")
                    }
                    if !views.isEmpty {
                        Button {
                            views.forEach { NSWorkspace.shared.open($0) }
                        } label: {
                            Label("See the braille as dots",
                                  systemImage: "circle.grid.3x3")
                        }
                        .deskButton()
                        .accessibilityHint("Opens \(views.count) page "
                                           + "file(s), drawn for sighted "
                                           + "eyes")
                    } else {
                        Button {
                            model.run("Braille", args: [
                                "braille", "--exports",
                                "braille, braille pages"])
                        } label: {
                            Label("Draw the braille as dots",
                                  systemImage: "circle.grid.3x3")
                        }
                        .deskButton()
                        .accessibilityHint("For a sighted teacher or "
                                           + "bandmate: every braille page "
                                           + "drawn as dots")
                    }
                }
                if model.runOutput.contains("aren't General MIDI drums") {
                    Button {
                        model.startTalk(["drums"])
                    } label: {
                        Label("Name the drum notes",
                              systemImage: "circle.grid.cross")
                    }
                    .deskButton()
                }
                if model.runOutput.contains("has no name yet") {
                    Button {
                        model.startTalk(["keys"])
                    } label: {
                        Label("Name the keyswitches",
                              systemImage: "pianokeys.inverse")
                    }
                    .deskButton()
                }
                if model.runTitle == "Bring in a file"
                    && model.runOutput.contains("tell me the tune.") {
                    Button {
                        model.startTalk(["edit"])
                    } label: {
                        Label("Tell me the tune",
                              systemImage: "bubble.left.and.bubble.right")
                    }
                    .deskButton()
                } else if model.runTitle == "Bring in a file" {
                    Button {
                        model.run("Build", args: ["build"])
                    } label: {
                        Label("Build it now", systemImage: "hammer")
                    }
                    .deskButton()
                }
                if model.playURL != nil || model.madeFiles,
                   let score = model.scorePDF() {
                    Button {
                        NSWorkspace.shared.open(score)
                    } label: {
                        Label("Open the score", systemImage: "doc.richtext")
                    }
                    .deskButton()
                    .accessibilityHint("Command Shift E")
                }
                if model.madeFiles {
                    let xml = model.musicXMLFiles()
                    if !xml.isEmpty {
                        Button {
                            NSWorkspace.shared
                                .activateFileViewerSelecting(xml)
                        } label: {
                            Label("Show the MusicXML",
                                  systemImage: "doc.text")
                        }
                        .deskButton()
                        .accessibilityHint("\(xml.count) files, selected "
                                           + "in the Finder, for "
                                           + "MuseScore, Sibelius, Dorico "
                                           + "or Finale")
                    }
                }
                if model.madeFiles,
                   let dir = model.pagesFolder(),
                   FileManager.default.fileExists(atPath: dir.path) {
                    Button {
                        NSWorkspace.shared.activateFileViewerSelecting([dir])
                    } label: {
                        Label("Show the pages", systemImage: "folder")
                    }
                    .deskButton()
                    .accessibilityHint("Opens the folder with every "
                                       + "part's PDF in Finder")
                }
            }
        }
    }
}

// MARK: - Listen and read tab

struct ListenTab: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette
    @State private var fromBar = ""
    @State private var solo: Set<String> = []
    @State private var readWho = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                TabHeading(tab: .listen, pal: pal)
                // one card above the other: side by side, VoiceOver reads
                    // across them row by row and the two interleave
                VStack(alignment: .leading, spacing: 14) {
                    Card(title: "Listen", pal: pal) {
                        HStack {
                            Text("Start at bar")
                                .accessibilityHidden(true)  // the field says it
                            TextField("the top", text: $fromBar)
                                .textFieldStyle(.roundedBorder)
                                .frame(width: 90)
                                .accessibilityLabel("Start at bar, your "
                                    + "DAW's number")
                                .accessibilityValue(fromBar.isEmpty
                                    ? "empty, from the top" : fromBar)
                                .onSubmit { listen() }
                        }
                        Text(solo.isEmpty
                             ? "Who plays: the whole band."
                             : "Who plays: just "
                               + solo.sorted().joined(separator: ", ") + ".")
                            .font(.system(size: ts(12)))
                            .foregroundStyle(pal.sub)
                        if model.parts.isEmpty {
                            Text("Open a chart to pick players.")
                                .font(.system(size: ts(12)))
                                .foregroundStyle(pal.sub)
                        }
                        // plain rows, not a grid: a grid is a container
                        // VoiceOver makes you interact with first
                        let rows = stride(from: 0, to: model.parts.count,
                                          by: 5).map {
                            Array(model.parts[$0..<min($0 + 5,
                                                       model.parts.count)])
                        }
                        ForEach(rows, id: \.self) { row in
                            HStack(spacing: 14) {
                                ForEach(row, id: \.self) { p in
                                    Toggle(p, isOn: Binding(
                                        get: { solo.contains(p) },
                                        set: { on in
                                            if on { solo.insert(p) }
                                            else { solo.remove(p) }
                                        }))
                                        .toggleStyle(.checkbox)
                                        .accessibilityLabel("Solo \(p)")
                                        .frame(minWidth: 110,
                                               alignment: .leading)
                                }
                                Spacer(minLength: 0)
                            }
                        }
                        HStack {
                            Button {
                                listen()
                            } label: {
                                Label(solo.isEmpty ? "Listen to the band"
                                      : "Listen to just these",
                                      systemImage: "headphones")
                            }
                            .deskButton(fill: pal.accent, ink: pal.accentText)
                            .tint(pal.accent)
                            // the label in the accent's own ink: white on amber read at 1.6:1
                            .foregroundStyle(pal.accentText)
                            .disabled(model.chart == nil)
                            if !solo.isEmpty {
                                Button("Everyone") { solo = [] }
                                    .deskButton()
                                    .accessibilityLabel("Clear the solo, "
                                        + "back to everyone")
                            }
                            Spacer()
                            Button {
                                if let u = model.newestMP3() {
                                    NSWorkspace.shared.open(u)
                                } else {
                                    announce("No listen yet. Build it or "
                                             + "listen first.")
                                }
                            } label: {
                                Label("Play the last listen",
                                      systemImage: "play.fill")
                            }
                            .deskButton()
                            .disabled(model.chart == nil)
                            .accessibilityHint("Command P")
                        }
                    }
                    Card(title: "Read aloud", pal: pal) {
                        Picker("Which part", selection: $readWho) {
                            Text("The whole chart").tag("")
                            ForEach(model.parts, id: \.self) { p in
                                Text(p).tag(p)
                            }
                        }
                            .accessibilityLabel("Which part")
                        Text("Spoken the way a player would read it.")
                            .font(.system(size: ts(12)))
                            .foregroundStyle(pal.sub)
                        Button {
                            var args = ["read"]
                            if !readWho.isEmpty { args += ["--part", readWho] }
                            model.run(readWho.isEmpty ? "Read the chart"
                                      : "Read \(readWho)",
                                      args: args, on: .listen)
                        } label: {
                            Label("Read it", systemImage: "text.book.closed")
                        }
                        .deskButton()
                        .disabled(model.chart == nil)
                        Divider()
                        Button {
                            model.run("The sounds", args: ["sounds"],
                                      needsChart: false, on: .listen)
                        } label: {
                            Label("The sound shelf", systemImage: "pianokeys")
                        }
                        .deskButton()
                        .accessibilityHint("What the band plays on")
                    }
                }
                RunPanel(pal: pal, tab: .listen, transcriptHeight: ts(300))
                    .frame(minHeight: model.runTab == .listen ? 260 : 0)
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 20)
        }
    }

    func listen() {
        var args = ["listen"]
        var what = "Listen"
        let b = fromBar.trimmingCharacters(in: .whitespaces)
        if Int(b) != nil {
            args += ["--from-bar", b]
            what += " from bar \(b)"
        } else if !b.isEmpty {
            // never quietly play from the top when a bar was asked for
            announce("'\(b)' isn't a bar number. Type a number like 17, "
                     + "or leave it empty for the top.")
            return
        }
        if !solo.isEmpty {
            let who = solo.sorted().joined(separator: ",")
            args += ["--solo", who]
            what += ", just " + solo.sorted().joined(separator: " and ")
        }
        model.run(what, args: args, on: .listen)
    }
}

// MARK: - The conversation

struct TalkView: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette
    @State private var draft = ""
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            TabHeading(tab: .talk, pal: pal)
            if model.talk.isEmpty && !model.talking {
                Card(title: "Start a conversation", pal: pal) {
                    ActionButton(icon: "bubble.left.and.bubble.right",
                                 title: "Tell me the tune",
                                 line: "Describe it in one breath. Copyist "
                                     + "writes the sections.",
                                 keys: "⇧⌘T", pal: pal) {
                        if model.chart == nil && !newChart(model) { return }
                        model.startTalk(["edit"])
                    }
                    ActionButton(icon: "pianokeys.inverse",
                                 title: "Name the keyswitches",
                                 line: "Say once what each key in your demo "
                                     + "does; the page marks it from then on.",
                                 pal: pal, enabled: model.chart != nil) {
                        model.startTalk(["keys"])
                    }
                    ActionButton(icon: "circle.grid.cross",
                                 title: "Name the drum notes",
                                 line: "Your drum library's note map, said "
                                     + "once and kept for every take.",
                                 pal: pal, enabled: model.chart != nil) {
                        model.startTalk(["drums"])
                    }
                }
            }
            if !model.talk.isEmpty || model.talking {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(model.talk) { line in
                            HStack {
                                if line.mine { Spacer(minLength: 60) }
                                Text(line.text)
                                    .font(.system(size: ts(14)))
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background(RoundedRectangle(
                                        cornerRadius: 10)
                                        .fill(line.mine
                                              ? pal.accent.opacity(0.25)
                                              : pal.card))
                                    .overlay(RoundedRectangle(
                                        cornerRadius: 10)
                                        .stroke(pal.edge, lineWidth: 1))
                                    .accessibilityLabel(
                                        (line.mine ? "You: " : "Copyist: ")
                                        + line.text)
                                if !line.mine { Spacer(minLength: 60) }
                            }
                            .id(line.id)
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .onChange(of: model.talk) { _ in
                    if let last = model.talk.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
            } else {
                Spacer()
            }
            if !model.question.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text(model.question)
                        .font(.system(size: ts(15), weight: .semibold))
                    if !model.questionDefault.isEmpty {
                        Text("Return keeps: \(model.questionDefault)")
                            .font(.system(size: ts(12)))
                            .foregroundStyle(pal.sub)
                    }
                    HStack(spacing: 8) {
                        TextField("Your answer", text: $draft)
                            .textFieldStyle(.roundedBorder)
                            .focused($focused)
                            .onSubmit { send() }
                            // the question was just said; focus landing
                            // here says only where you are
                            .accessibilityLabel("Your answer")
                        Button {
                            let cfg = loadConfig()
                            if let f = pickFile(start: cfg["midi"]) {
                                draft = draft.isEmpty &&
                                    model.question.hasPrefix("Chords")
                                    ? "play \(f)" : draft + f
                            }
                        } label: {
                            Image(systemName: "paperclip")
                        }
                        .accessibilityLabel("Attach a file into the answer")
                        Button("Send") { send() }
                            .keyboardShortcut(.defaultAction)
                            .deskButton(fill: pal.accent, ink: pal.accentText)
                            .tint(pal.accent)
                            // the label in the accent's own ink: white on amber read at 1.6:1
                            .foregroundStyle(pal.accentText)
                    }
                }
                .padding(14)
                .background(RoundedRectangle(cornerRadius: 12)
                    .fill(pal.card))
                .overlay(RoundedRectangle(cornerRadius: 12)
                    .stroke(pal.accent.opacity(0.6), lineWidth: 1))
                .onAppear { focused = true }
                .onChange(of: model.question) { _ in focused = true }
            } else if model.talking {
                HStack {
                    ProgressView().controlSize(.small)
                    Text("Copyist is thinking…")
                        .font(.system(size: ts(12)))
                        .foregroundStyle(pal.sub)
                }
            } else if !model.talk.isEmpty {
                HStack(spacing: 10) {
                    Button {
                        model.run("Build", args: ["build"])
                    } label: {
                        Label("Build it and hear it",
                              systemImage: "hammer")
                    }
                    .deskButton(fill: pal.accent, ink: pal.accentText)
                    .tint(pal.accent)
                    // the label in the accent's own ink: white on amber read at 1.6:1
                    .foregroundStyle(pal.accentText)
                    .accessibilityHint("Command B")
                    Button("New conversation") { model.talk = [] }
                        .deskButton()
                }
            }
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 16)
    }

    func send() {
        model.answer(draft)
        draft = ""
        focused = true
    }
}

// MARK: - Settings

struct SettingsView: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette
    @State private var cfg: [String: String] = [:]
    @State private var status = "Every setting says what it is set to."
    @State private var composer = ""
    @State private var countin = ""
    @State private var printers: [String] = []
    @AccessibilityFocusState private var onEmbosser: Bool
    /// the sound catalog as the engine reads it: (key, what it says,
    /// installed) — one source for the terminal and the app
    @State private var soundRows: [(String, String, Bool)] = []
    @State private var pickedSounds: Set<String> = []

    let looks = ["", "jazz", "handwritten", "engraved", "plain"]
    let quants = ["", "eighths", "straight", "sixteenths", "triplets"]

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                TabHeading(tab: .settings, pal: pal)
                group("The app") {
                    Picker("Appearance", selection: Binding(
                        get: { model.vibe },
                        set: { model.vibe = $0 })) {
                        ForEach(Vibe.allCases) { v in
                            Text(v.label).tag(v)
                        }
                    }
                        .accessibilityLabel("Appearance")
                    .pickerStyle(.segmented)
                    .tint(pal.accent)
                    Picker("Text size", selection: $model.textScale) {
                        ForEach(textSizes, id: \.self) { k in
                            Text("\(Int((k * 100).rounded())) percent")
                                .tag(k)
                        }
                    }
                        .accessibilityLabel("Text size")
                    .accessibilityHint("Command equals is bigger, "
                                       + "Command minus smaller, Command "
                                       + "zero back to 100 percent")
                    Toggle("Say each build step aloud as it happens",
                           isOn: $model.speakSteps)
                        .accessibilityHint("Off, you hear only when it "
                                           + "finishes")
                    Toggle("Say what a tab holds when you switch to it",
                           isOn: $model.speakTabs)
                        .accessibilityHint("The tab's name is always said")
                }
                group("Your charts") {
                    Text("The name on every new chart, and how the "
                         + "pages dress.")
                        .font(.system(size: ts(11)))
                        .foregroundStyle(pal.sub)
                    HStack {
                        TextField("Composer", text: $composer)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit { set("composer", composer) }
                            // typed and moved on is saved, not dropped
                            .onDisappear {
                                if composer != (cfg["composer"] ?? "") {
                                    set("composer", composer)
                                }
                            }
                            .accessibilityLabel("Composer, now "
                                + (cfg["composer"] ?? "not set"))
                        Button("Save") { set("composer", composer) }
                            .accessibilityLabel("Save the composer")
                    }
                    Picker("Look", selection: bind("look")) {
                        ForEach(looks, id: \.self) {
                            Text($0.isEmpty ? "each chart decides" : $0)
                        }
                    }
                        .accessibilityLabel("Look")
                }
                group("What a build makes") {
                    Text("Any mix. Listen and Braille on the Build tab "
                         + "make just their one thing.")
                        .font(.system(size: ts(11)))
                        .foregroundStyle(pal.sub)
                    ForEach(exportChoices, id: \.0) { key, label in
                        Toggle(label, isOn: export(key))
                    }
                }
                group("Braille") {
                    Picker("Braille paper", selection: bind("braille_page")) {
                        Text("Standard, 40 cells by 25 lines "
                             + "(11 by 11.5 inch)").tag("standard")
                        Text("Letter, 34 by 25").tag("letter")
                        Text("A4, 35 by 28").tag("a4")
                    }
                        .accessibilityLabel("Braille paper")
                    // the label drawn beside the popup, not inside it:
                    // VoiceOver focus on a labelled Picker lands on the
                    // word, one step short of the control
                    HStack {
                        Text("Embosser").accessibilityHidden(true)
                        Picker("Embosser", selection: bind("embosser")) {
                            Text("None chosen").tag("")
                            ForEach(printers, id: \.self) {
                                Text($0).tag($0)
                            }
                        }
                        .labelsHidden()
                        .accessibilityFocused($onEmbosser)
                    }
                    .id("embosser")
                    Text("An embosser shows up here once it is added in "
                         + "System Settings, Printers and Scanners.")
                        .font(.system(size: ts(11)))
                        .foregroundStyle(pal.sub)
                        .fixedSize(horizontal: false, vertical: true)
                }
                group("When a build lands") {
                    Toggle("Ping my phone",
                           isOn: yesno("notify"))
                    Toggle("Pop the score open",
                           isOn: yesno("open"))
                }
                group("Where finished files go") {
                    Text("Empty keeps everything with the build, "
                         + "next to the chart.")
                        .font(.system(size: ts(11)))
                        .foregroundStyle(pal.sub)
                    pathRow("PDF pages", key: "pages_to")
                    pathRow("Listen MP3s", key: "listens_to")
                    pathRow("Spoken read-alouds", key: "spoken_to")
                    pathRow("Braille files", key: "braille_to")
                }
                group("MIDI and demos") {
                    Text("The folder your playing comes from, and how "
                         + "Copyist reads its rhythms.")
                        .font(.system(size: ts(11)))
                        .foregroundStyle(pal.sub)
                    pathRow("Your DAW's export folder", key: "midi")
                    Picker("How Copyist reads your played rhythms",
                           selection: bind("quant")) {
                        ForEach(quants, id: \.self) {
                            Text($0.isEmpty ? "the chart decides" : $0)
                        }
                    }
                        .accessibilityLabel("How Copyist reads your played rhythms")
                    HStack {
                        // placeholder as a prompt only: the label below
                        // says the name once, with what it's set to
                        TextField("", text: $countin,
                                  prompt: Text("Count-in bars"))
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 120)
                            .onSubmit { set("countin", countin) }
                            .onDisappear {
                                if countin != (cfg["countin"] ?? "") {
                                    set("countin", countin)
                                }
                            }
                            .accessibilityLabel("Count-in bars, now "
                                + (cfg["countin"]?.isEmpty == false
                                   ? cfg["countin"]! : "read from the demo"))
                        Button("Save") { set("countin", countin) }
                            .accessibilityLabel("Save the count-in")
                        Text("offered when the demo itself says nothing")
                            .font(.system(size: ts(11)))
                            .foregroundStyle(pal.sub)
                    }
                }
                group("Sounds") {
                    Toggle("Play the recorded instruments (off plays the "
                           + "plain built-in synth)",
                           isOn: onUnlessNo("use_samples"))
                    pathRow("Where sample libraries live",
                            key: "sounds_dir")
                    Text("The band's recorded instruments, each with what "
                         + "it plays, its size and its license. Pick "
                         + "what to install; nothing downloads until you "
                         + "press Install.")
                        .font(.system(size: ts(11)))
                        .foregroundStyle(pal.sub)
                    ForEach(soundRows, id: \.0) { row in
                        if row.2 {
                            Text(row.1 + " — installed")
                        } else {
                            Toggle(row.1, isOn: Binding(
                                get: { pickedSounds.contains(row.0) },
                                set: { on in
                                    if on { pickedSounds.insert(row.0) }
                                    else { pickedSounds.remove(row.0) }
                                }))
                        }
                    }
                    HStack {
                        Button("Install the chosen sounds") {
                            let keys = soundRows.map { $0.0 }
                                .filter { pickedSounds.contains($0) }
                            model.run("Installing sounds",
                                      args: ["sounds", "install",
                                             keys.joined(separator: ", ")],
                                      needsChart: false, on: .settings)
                        }
                        .disabled(pickedSounds.isEmpty)
                        Button("Install everything the band plays") {
                            model.run("Installing sounds",
                                      args: ["sounds", "install", "band"],
                                      needsChart: false, on: .settings)
                        }
                        .disabled(soundRows.allSatisfy { $0.2 })
                    }
                    // the install's progress and transcript, here where
                    // it was started (it used to jump to the Build tab)
                    if model.runTab == .settings
                        && (model.running || !model.runTitle.isEmpty) {
                        RunPanel(pal: pal, tab: .settings,
                                 transcriptHeight: ts(220))
                    }
                }
                group("What the listen makes up") {
                    Text("Where the page leaves it to the band. Turn any "
                         + "of these off and the next listen leaves it "
                         + "out, and says so.")
                        .font(.system(size: ts(11)))
                        .foregroundStyle(pal.sub)
                    Toggle("The rhythm section plays the slashes",
                           isOn: onUnlessNo("listen_grooves"))
                    Toggle("Made-up solos where a line says solo",
                           isOn: onUnlessNo("listen_solos"))
                    Toggle("Made-up backgrounds behind a solo",
                           isOn: onUnlessNo("listen_backgrounds"))
                    Toggle("The band's own ending when the chart names "
                           + "none", isOn: onUnlessNo("listen_endings"))
                    Toggle("Mutes on the spot for the brass",
                           isOn: onUnlessNo("listen_mutes"))
                    Toggle("Brushes on a ballad",
                           isOn: onUnlessNo("listen_brushes"))
                    Toggle("The band builds through the tune",
                           isOn: onUnlessNo("listen_builds"))
                    Toggle("Feathered kick when swinging",
                           isOn: onUnlessNo("listen_feather"))
                    // off keeps one take for every build; a number set
                    // at the terminal plays that take and reads as off
                    Toggle("A fresh take every build",
                           isOn: Binding(
                               get: { (cfg["listen_take"] ?? "new")
                                   == "new" },
                               set: { set("listen_take",
                                          $0 ? "new" : "same") }))
                }
                group("Your words") {
                    let vp = NSHomeDirectory()
                        + "/.config/copyist/vocabulary.json"
                    let count = (try? JSONSerialization.jsonObject(
                        with: Data(contentsOf: URL(
                            fileURLWithPath: vp))) as? [String: Any])
                        .map { $0.count } ?? 0
                    HStack {
                        Text(count == 0
                             ? "No words taught yet. When Copyist "
                               + "doesn't know one, it asks once and "
                               + "remembers forever."
                             : "Words you've taught Copyist: \(count)."
                               + " Your slang, its vocabulary.")
                        Spacer()
                        if count > 0 {
                            Button("Open the list") {
                                NSWorkspace.shared.open(
                                    URL(fileURLWithPath: vp))
                            }
                        }
                    }
                }
                Spacer(minLength: 40)
            }
            .padding(.horizontal, 20)
        }
        // what the last change did, pinned where a sighted eye finds it
        // whatever is scrolled into view (it sat at the very bottom)
        .safeAreaInset(edge: .bottom) {
            if !status.isEmpty {
                Text(status)
                    .font(.system(size: ts(13), weight: .semibold))
                    .foregroundStyle(pal.text)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(pal.card)
                    .overlay(Rectangle().frame(height: 1)
                        .foregroundStyle(pal.edge), alignment: .top)
                    .accessibilityAddTraits(.updatesFrequently)
            }
        }
        .onChange(of: model.running) { going in
            // a sound install finished here: the list says what is in
            if !going && model.runTitle == "Installing sounds" {
                loadSounds()
            }
        }
        .onAppear {
            cfg = loadConfig()
            composer = cfg["composer"] ?? ""
            countin = cfg["countin"] ?? ""
            if cfg["braille_page"] == nil { cfg["braille_page"] = "standard" }
            runInBackground("/usr/bin/lpstat", ["-e"]) { out, _ in
                printers = out.split(separator: "\n").map(String.init)
            }
            showEmbosser(proxy)
            loadSounds()
        }
        .onChange(of: model.wantEmbosser) { _ in showEmbosser(proxy) }
        }
    }

    /// The catalog from the engine: 'chart sounds list', one library a
    /// line, "  key: name — plays; size, license; installed".
    func loadSounds() {
        guard let tool = Tool.find() else { return }
        runInBackground(tool.python, [tool.script, "sounds", "list"]) {
            out, _ in
        soundRows = out.split(separator: "\n").compactMap { line in
            let t = line.trimmingCharacters(in: .whitespaces)
            guard let colon = t.firstIndex(of: ":"),
                  t.hasSuffix("installed") else { return nil }
            let key = String(t[..<colon])
            var body = String(t[t.index(after: colon)...])
                .trimmingCharacters(in: .whitespaces)
            let isIn = !body.hasSuffix("not installed")
            if let semi = body.range(of: "; ", options: .backwards) {
                body = String(body[..<semi.lowerBound])
            }
            return (key, body, isIn)
        }
        }
    }

    /// Emboss with no embosser chosen lands here: the picker takes
    /// VoiceOver (it says "None chosen, Embosser"), then the reason
    /// follows a beat later — posted with the focus move, VoiceOver
    /// drops it.
    func showEmbosser(_ proxy: ScrollViewProxy) {
        guard model.wantEmbosser else { return }
        model.wantEmbosser = false
        proxy.scrollTo("embosser", anchor: .center)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            onEmbosser = true
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) {
            // no printer count: an ordinary printer in this list is
            // not an embosser, and raw braille must never go to one
            announce("Choose the embosser here, then Emboss again."
                     + (printers.isEmpty
                        ? " No printers are set up on this Mac yet."
                        : ""), queued: true)
        }
    }

    @ViewBuilder
    func group(_ title: String,
               @ViewBuilder _ content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.system(size: ts(14), weight: .semibold))
                .foregroundStyle(pal.sub)
                .accessibilityAddTraits(.isHeader)
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12).fill(pal.card))
        .overlay(RoundedRectangle(cornerRadius: 12)
            .stroke(pal.edge, lineWidth: 1))
    }

    func pathRow(_ label: String, key: String) -> some View {
        HStack {
            Text(label + ": "
                 + ((cfg[key]?.isEmpty == false) ? cfg[key]!
                    : key == "sounds_dir"
                    // unset means the standard place: say where it is
                    ? "the standard place, ~/Library/Application Support/"
                      + "Copyist/Sounds"
                    : "not set"))
                .lineLimit(1)
                // the folder's own name is the end of the path: keep it
                .truncationMode(.middle)
                .help(cfg[key] ?? "")
            Spacer()
            Button("Choose…") {
                if let f = pickFile(start: cfg[key], dirs: true) {
                    set(key, f)
                }
            }
            .accessibilityLabel("Choose \(label)")
            if cfg[key]?.isEmpty == false {
                Button("Clear") { set(key, "") }
                    .accessibilityLabel("Clear \(label)")
            }
        }
    }

    func bind(_ key: String) -> Binding<String> {
        Binding(get: { cfg[key] ?? "" },
                set: { set(key, $0) })
    }

    let exportChoices = [
        ("pages", "Pages — the PDF charts"),
        ("listen", "Listen — the MP3"),
        ("braille", "Braille — a file for each part"),
        ("braille pages", "Braille pages — the braille drawn as dots"),
        ("read-alouds", "Read-alouds — each part spoken as text"),
        ("ireal", "iReal Pro — a link that opens in the app"),
        ("midi", "MIDI — the band, one track per player, for your DAW"),
        ("chords", "Chord sheet — plain text with barlines")]

    /// The exports setting as a set of words; unset means the default.
    func exportsNow() -> [String] {
        let v = cfg["exports"] ?? "pages, listen, braille, read-alouds"
        return v.split(separator: ",").map {
            $0.trimmingCharacters(in: .whitespaces) }
    }

    func export(_ key: String) -> Binding<Bool> {
        Binding(get: { exportsNow().contains(key) },
                set: { on in
                    var now = exportsNow().filter { $0 != key }
                    if on { now.append(key) }
                    set("exports", now.joined(separator: ", "))
                })
    }

    func yesno(_ key: String) -> Binding<Bool> {
        Binding(get: { cfg[key] == "yes" },
                set: { set(key, $0 ? "yes" : "no") })
    }

    /// A switch that is on until the writer turns it off: a setting
    /// never touched has no entry in the file, and must still read on.
    func onUnlessNo(_ key: String) -> Binding<Bool> {
        Binding(get: { cfg[key] != "no" },
                set: { set(key, $0 ? "yes" : "no") })
    }

    func set(_ key: String, _ value: String) {
        guard let tool = Tool.find() else {
            status = "I can't find the Copyist engine."
            return
        }
        // the control shows its new value at once; the engine checks
        // and saves it in the background, and what it says is shown
        // and spoken (a refusal puts the old value back)
        cfg[key] = value
        status = "Saving…"
        runInBackground(tool.python, [tool.script, "set", "\(key)=\(value)"],
                        stderr: true) { out, _ in
            let line = out.trimmingCharacters(in: .whitespacesAndNewlines)
            status = line.isEmpty ? "Saved." : line
            cfg = loadConfig()
            announce(status)
        }
    }
}
