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

struct Palette {
    let bg: Color, card: Color, edge: Color
    let text: Color, sub: Color
    let accent: Color, accentText: Color

    static let stage = Palette(
        bg: Color(hex: 0x0E1117), card: Color(hex: 0x1A2130),
        edge: Color(hex: 0x2A3350),
        text: Color(hex: 0xEDF1F7), sub: Color(hex: 0x9AA7BD),
        accent: Color(hex: 0xFFB454), accentText: Color(hex: 0x1A1205))

    static let manuscript = Palette(
        bg: Color(hex: 0xF7F2E7), card: Color(hex: 0xFFFDF7),
        edge: Color(hex: 0xE2D9C6),
        text: Color(hex: 0x232018), sub: Color(hex: 0x6B655B),
        accent: Color(hex: 0xA22C29), accentText: Color(hex: 0xFFF8F0))
}

// MARK: - Talking to VoiceOver

func announce(_ text: String) {
    if #available(macOS 14.0, *) {
        AccessibilityNotification.Announcement(text).post()
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
    enum Screen { case home, run, talk, settings }

    @Published var screen: Screen = .home
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

    func run(_ title: String, args: [String], needsChart: Bool = true) {
        guard let tool = Tool.find() else {
            runTitle = title
            runOutput = "I can't find the Copyist engine. There's no "
                + "~/copyist checkout and no copy inside the app, "
                + "which shouldn't happen. Reinstall with app/build.sh."
            screen = .run
            return
        }
        if running {
            screen = .run
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
        running = true
        playURL = nil
        progressPct = nil
        progressWhat = ""
        runBuffer = ""
        let wantsPlay = args.contains("build") || args.contains("listen")
        screen = .run
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
        p.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self else { return }
                self.running = false
                self.stopFlavor()
                pipe.fileHandleForReading.readabilityHandler = nil
                if wantsPlay {
                    self.playURL = self.newestMP3()
                }
                let last = self.runOutput.split(separator: "\n")
                    .last.map(String.init) ?? "Done."
                announce("\(title) finished. \(last)"
                         + (self.playURL != nil
                            ? " Play it is on screen." : ""))
            }
        }
        proc = p
        do { try p.run() } catch {
            running = false
            stopFlavor()
            runOutput = "The engine would not start: "
                + error.localizedDescription
        }
    }

    func stopRun() {
        proc?.terminate()
        running = false
        stopFlavor()
        progressPct = nil
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
                }
                continue
            }
            runOutput += line + "\n"
        }
    }

    func newestMP3() -> URL? {
        guard let c = chart else { return nil }
        let dir = URL(fileURLWithPath: c).deletingLastPathComponent()
            .appendingPathComponent("build")
        guard let items = try? FileManager.default
            .contentsOfDirectory(at: dir, includingPropertiesForKeys:
                [.contentModificationDateKey]) else { return nil }
        return items.filter { $0.pathExtension == "mp3" }
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
        talk = []
        question = ""
        questionDefault = ""
        talkBuffer = ""
        talking = true
        screen = .talk
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool.python)
        p.arguments = [tool.script, c] + args
        var env = ProcessInfo.processInfo.environment
        env["COPYIST_PORCELAIN"] = "1"
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:"
            + (env["PATH"] ?? "/usr/bin:/bin")
        env["COPYIST_PROGRESS"] = "1"
        p.environment = env
        let out = Pipe(), inp = Pipe()
        p.standardOutput = out
        p.standardError = Pipe()      // tracebacks stay out of the room
        p.standardInput = inp
        talkStdin = inp.fileHandleForWriting
        out.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            guard !d.isEmpty else { return }
            let s = String(decoding: d, as: UTF8.self)
            DispatchQueue.main.async { self?.receive(s) }
        }
        p.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self else { return }
                self.talking = false
                out.fileHandleForReading.readabilityHandler = nil
                self.question = ""
                self.questionDefault = ""
                let last = self.talk.last(where: { !$0.mine })?.text
                    ?? "That's the conversation."
                announce(last)
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
                announce(text)
            } else if type == "ask" {
                question = text
                questionDefault = obj["default"] as? String ?? ""
                let hint = questionDefault.isEmpty ? "" :
                    " Return keeps \(questionDefault)."
                announce(text + hint)
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
    var body: some Scene {
        // each window is its own desk: its own chart, its own build —
        // File > New Window works on a second chart while the first
        // one cooks
        WindowGroup("Copyist") {
            ContentView()
                .frame(minWidth: 780, minHeight: 560)
        }
        .windowResizability(.contentMinSize)
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
                Divider().overlay(pal.edge)
                switch model.screen {
                case .home: HomeView(pal: pal)
                case .run: RunView(pal: pal)
                case .talk: TalkView(pal: pal)
                case .settings: SettingsView(pal: pal)
                }
            }
        }
        .preferredColorScheme(model.vibe == .stage ? .dark :
                              model.vibe == .manuscript ? .light : nil)
        .foregroundStyle(pal.text)
        .environmentObject(model)
    }
}

// MARK: - Header

struct HeaderBar: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "music.quarternote.3")
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(pal.accent)
                .accessibilityHidden(true)
            Text("Copyist")
                .font(.system(size: 22, weight: .bold, design: .serif))
            Spacer()
            if model.screen != .home {
                // going Home leaves a build or conversation alive —
                // Home shows a chip to come back to it
                Button("Home") { model.screen = .home }
                    .buttonStyle(.bordered)
            }
            Button {
                pickChart(model)
            } label: {
                Label(model.chartName, systemImage: "doc.text")
                    .lineLimit(1)
            }
            .buttonStyle(.bordered)
            .accessibilityLabel("Current chart: \(model.chartName). "
                                + "Choose another")
            Button {
                model.screen = .settings
            } label: {
                Image(systemName: "gearshape")
            }
            .buttonStyle(.bordered)
            .accessibilityLabel("Settings")
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
    }
}

// MARK: - Home

struct ActionSpec: Identifiable {
    let id: String
    let icon: String
    let title: String
    let line: String
    let needsChart: Bool
    let act: (AppModel) -> Void
}

struct RunChip: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette

    var body: some View {
        let pct: Int? = model.progressPct.map { Int($0) }
        let head: String = model.runTitle + " is still going"
            + (pct.map { " — \($0)%" } ?? "") + ". Check on it."
        let sub = "A new window (File menu) works on another chart "
            + "meanwhile."
        let spoken: String = model.runTitle + " is still going"
            + (pct.map { ", \($0) percent, " + model.progressWhat }
               ?? "")
            + ". Check on it. A new window from the File menu works "
            + "on another chart meanwhile."
        Button {
            model.screen = .run
        } label: {
            HStack(spacing: 10) {
                if let p = model.progressPct {
                    ProgressView(value: p, total: 100)
                        .frame(width: 110)
                        .tint(pal.accent)
                } else {
                    ProgressView().controlSize(.small)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(head)
                        .font(.system(size: 13, weight: .semibold))
                    Text(sub)
                        .font(.system(size: 11))
                        .foregroundStyle(pal.sub)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12)
                .fill(pal.card))
            .overlay(RoundedRectangle(cornerRadius: 12)
                .stroke(pal.accent, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(spoken)
    }
}

struct HomeView: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette
    @State private var partAsk = false
    @State private var partName = ""
    @State private var listenAsk = false
    @State private var fromBar = ""
    @State private var soloParts = ""

    var actions: [ActionSpec] {
        [
            ActionSpec(id: "talk", icon: "bubble.left.and.bubble.right",
                       title: "Tell me the tune",
                       line: "Describe it in one breath. I write the sections.",
                       needsChart: false) { m in
                if m.chart == nil && !newChart(m) { return }
                m.startTalk(["edit"])
            },
            ActionSpec(id: "build", icon: "hammer",
                       title: "Build it",
                       line: "Pages, read-alouds, findings, and the band plays it.",
                       needsChart: true) { $0.run("Build", args: ["build"]) },
            ActionSpec(id: "listen", icon: "headphones",
                       title: "Listen",
                       line: "The whole band, or just your chair, from any bar.",
                       needsChart: true) { _ in listenAsk = true },
            ActionSpec(id: "check", icon: "checkmark.seal",
                       title: "Check it",
                       line: "Prove every bar adds up. Nothing rendered.",
                       needsChart: true) { $0.run("Check", args: ["check"]) },
            ActionSpec(id: "read", icon: "text.book.closed",
                       title: "Read a part",
                       line: "Spoken the way a player would read it.",
                       needsChart: true) { _ in partAsk = true },
            ActionSpec(id: "diff", icon: "arrow.triangle.2.circlepath",
                       title: "What changed",
                       line: "Since the last build, by part and by bar.",
                       needsChart: true) { $0.run("What changed", args: ["diff"]) },
            ActionSpec(id: "parts", icon: "person.3",
                       title: "The band",
                       line: "Who's on this chart.",
                       needsChart: true) { $0.run("The band", args: ["parts"]) },
            ActionSpec(id: "sounds", icon: "pianokeys",
                       title: "The sounds",
                       line: "The shelf the band plays on.",
                       needsChart: false) { $0.run("The sounds",
                                                   args: ["sounds"],
                                                   needsChart: false) },
        ]
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(model.chart == nil
                     ? "What are we writing today?"
                     : "Working on \(model.chartName).")
                    .font(.system(size: 17, design: .serif))
                    .foregroundStyle(pal.sub)
                    .padding(.top, 18)
                if model.running {
                    RunChip(pal: pal)
                }
                if model.talking {
                    Button {
                        model.screen = .talk
                    } label: {
                        Label("The conversation is waiting on you.",
                              systemImage: "bubble.left.and.bubble.right")
                            .font(.system(size: 13, weight: .semibold))
                            .padding(12)
                            .frame(maxWidth: .infinity,
                                   alignment: .leading)
                            .background(RoundedRectangle(
                                cornerRadius: 12).fill(pal.card))
                            .overlay(RoundedRectangle(cornerRadius: 12)
                                .stroke(pal.accent, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                }
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 330),
                                             spacing: 14)],
                          spacing: 14) {
                    ForEach(actions) { a in
                        Button {
                            a.act(model)
                        } label: {
                            HStack(spacing: 14) {
                                Image(systemName: a.icon)
                                    .font(.system(size: 24, weight: .semibold))
                                    .foregroundStyle(pal.accent)
                                    .frame(width: 34)
                                    .accessibilityHidden(true)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(a.title)
                                        .font(.system(size: 16,
                                                      weight: .semibold))
                                    Text(a.line)
                                        .font(.system(size: 12))
                                        .foregroundStyle(pal.sub)
                                }
                                Spacer(minLength: 0)
                            }
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(
                                RoundedRectangle(cornerRadius: 12)
                                    .fill(pal.card))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(pal.edge, lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                        .disabled(a.needsChart && model.chart == nil)
                        .opacity(a.needsChart && model.chart == nil
                                 ? 0.45 : 1)
                        .accessibilityElement(children: .combine)
                    }
                }
                if !model.recents.isEmpty {
                    Text("Recent charts")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(pal.sub)
                        .padding(.top, 6)
                    ForEach(model.recents, id: \.self) { r in
                        Button {
                            model.choose(r)
                        } label: {
                            Label(URL(fileURLWithPath: r)
                                    .deletingPathExtension()
                                    .lastPathComponent,
                                  systemImage: "clock")
                        }
                        .buttonStyle(.link)
                        .foregroundStyle(pal.text)
                    }
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 24)
        }
        .sheet(isPresented: $listenAsk) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Return plays the whole thing from the top.")
                    .font(.headline)
                TextField("Start at bar (your DAW's number)",
                          text: $fromBar)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { runListen() }
                TextField("Solo who? Like bari, bone. Empty is everyone.",
                          text: $soloParts)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { runListen() }
                HStack {
                    Spacer()
                    Button("Back") { listenAsk = false }
                        .keyboardShortcut(.cancelAction)
                    Button("Listen") { runListen() }
                        .keyboardShortcut(.defaultAction)
                }
            }
            .padding(20)
            .frame(width: 440)
        }
        .sheet(isPresented: $partAsk) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Which part? Leave it empty for the whole chart.")
                    .font(.headline)
                TextField("Part name, like trumpet 1", text: $partName)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { readPart() }
                HStack {
                    Spacer()
                    Button("Back") { partAsk = false }
                        .keyboardShortcut(.cancelAction)
                    Button("Read it") { readPart() }
                        .keyboardShortcut(.defaultAction)
                }
            }
            .padding(20)
            .frame(width: 420)
        }
    }

    func runListen() {
        listenAsk = false
        var args = ["listen"]
        var what = "Listen"
        let b = fromBar.trimmingCharacters(in: .whitespaces)
        if Int(b) != nil {
            args += ["--from-bar", b]
            what += " from bar \(b)"
        }
        let sp = soloParts.trimmingCharacters(in: .whitespaces)
        if !sp.isEmpty {
            args += ["--solo", sp]
            what += ", just \(sp)"
        }
        model.run(what, args: args)
    }

    func readPart() {
        partAsk = false
        var args = ["read"]
        let p = partName.trimmingCharacters(in: .whitespaces)
        if !p.isEmpty { args += ["--part", p] }
        model.run(p.isEmpty ? "Read the chart" : "Read \(p)", args: args)
    }
}

// MARK: - Runner

struct RunView: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(model.runTitle)
                    .font(.system(size: 18, weight: .bold, design: .serif))
                if model.running {
                    if let pct = model.progressPct {
                        ProgressView(value: pct, total: 100)
                            .frame(width: 150)
                            .padding(.leading, 6)
                            .tint(pal.accent)
                            .accessibilityLabel(
                                "\(Int(pct)) percent — "
                                + model.progressWhat)
                        Text("\(Int(pct))% — \(model.progressWhat)")
                            .font(.system(size: 12))
                            .foregroundStyle(pal.sub)
                            .accessibilityHidden(true)
                    } else {
                        ProgressView().controlSize(.small)
                            .padding(.leading, 6)
                        Text(model.flavor)
                            .font(.system(size: 12))
                            .foregroundStyle(pal.sub)
                            .accessibilityHidden(true)
                    }
                }
                Spacer()
                if let u = model.playURL, !model.running {
                    Button {
                        NSWorkspace.shared.open(u)
                    } label: {
                        Label("Play it", systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(pal.accent)
                    .accessibilityLabel("Play the listen MP3")
                }
                if model.running {
                    Button("Stop") { model.stopRun() }
                        .buttonStyle(.bordered)
                }
            }
            ScrollViewReader { proxy in
                ScrollView {
                    Text(model.runOutput.isEmpty && model.running
                         ? "On it…" : model.runOutput)
                        .font(.system(size: 13, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14)
                        .id("out")
                }
                .background(RoundedRectangle(cornerRadius: 12)
                    .fill(pal.card))
                .overlay(RoundedRectangle(cornerRadius: 12)
                    .stroke(pal.edge, lineWidth: 1))
                .onChange(of: model.runOutput) { _ in
                    proxy.scrollTo("out", anchor: .bottom)
                }
            }
        }
        .padding(20)
    }
}

// MARK: - The conversation

struct TalkView: View {
    @EnvironmentObject var model: AppModel
    let pal: Palette
    @State private var draft = ""
    @FocusState private var focused: Bool

    var body: some View {
        VStack(spacing: 12) {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(model.talk) { line in
                            HStack {
                                if line.mine { Spacer(minLength: 60) }
                                Text(line.text)
                                    .font(.system(size: 14))
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
            if !model.question.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text(model.question)
                        .font(.system(size: 15, weight: .semibold))
                    if !model.questionDefault.isEmpty {
                        Text("Return keeps: \(model.questionDefault)")
                            .font(.system(size: 12))
                            .foregroundStyle(pal.sub)
                    }
                    HStack(spacing: 8) {
                        TextField("Your answer", text: $draft)
                            .textFieldStyle(.roundedBorder)
                            .focused($focused)
                            .onSubmit { send() }
                            .accessibilityLabel("Answer. \(model.question)")
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
                            .buttonStyle(.borderedProminent)
                            .tint(pal.accent)
                    }
                }
                .padding(14)
                .background(RoundedRectangle(cornerRadius: 12)
                    .fill(pal.card))
                .overlay(RoundedRectangle(cornerRadius: 12)
                    .stroke(pal.accent.opacity(0.6), lineWidth: 1))
                .onAppear { focused = true }
            } else if model.talking {
                HStack {
                    ProgressView().controlSize(.small)
                    Text("Copyist is thinking…")
                        .font(.system(size: 12))
                        .foregroundStyle(pal.sub)
                }
            } else {
                HStack(spacing: 10) {
                    Button {
                        model.run("Build", args: ["build"])
                    } label: {
                        Label("Build it and hear it",
                              systemImage: "hammer")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(pal.accent)
                    Button("Back home") { model.screen = .home }
                        .buttonStyle(.bordered)
                }
            }
        }
        .padding(16)
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

    let looks = ["", "jazz", "handwritten", "engraved", "plain"]
    let quants = ["", "eighths", "straight", "sixteenths", "triplets"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Settings")
                    .font(.system(size: 18, weight: .bold, design: .serif))
                    .padding(.top, 16)
                Text("Every control says what it is set to. Nothing "
                     + "here needs saving twice.")
                    .font(.system(size: 12))
                    .foregroundStyle(pal.sub)
                group("The app") {
                    Picker("Appearance", selection: Binding(
                        get: { model.vibe },
                        set: { model.vibe = $0 })) {
                        ForEach(Vibe.allCases) { v in
                            Text(v.label).tag(v)
                        }
                    }
                    .pickerStyle(.segmented)
                    .tint(pal.accent)
                }
                group("Your charts") {
                    Text("The name on every new chart, and how the "
                         + "pages dress.")
                        .font(.system(size: 11))
                        .foregroundStyle(pal.sub)
                    HStack {
                        TextField("Composer", text: $composer)
                            .textFieldStyle(.roundedBorder)
                            .onSubmit { set("composer", composer) }
                            .accessibilityLabel("Composer, now "
                                + (cfg["composer"] ?? "not set"))
                        Button("Save") { set("composer", composer) }
                    }
                    Picker("Look", selection: bind("look")) {
                        ForEach(looks, id: \.self) {
                            Text($0.isEmpty ? "each chart decides" : $0)
                        }
                    }
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
                        .font(.system(size: 11))
                        .foregroundStyle(pal.sub)
                    pathRow("PDF pages", key: "pages_to")
                    pathRow("Listen MP3s", key: "listens_to")
                    pathRow("Spoken read-alouds", key: "spoken_to")
                }
                group("MIDI and demos") {
                    Text("Where your played files come from, and how "
                         + "lifts read them.")
                        .font(.system(size: 11))
                        .foregroundStyle(pal.sub)
                    pathRow("Your DAW's export folder", key: "midi")
                    Picker("Feel for every from-demo lift",
                           selection: bind("quant")) {
                        ForEach(quants, id: \.self) {
                            Text($0.isEmpty ? "each line decides" : $0)
                        }
                    }
                    HStack {
                        TextField("Count-in bars", text: $countin)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 120)
                            .onSubmit { set("countin", countin) }
                            .accessibilityLabel("Count-in bars, now "
                                + (cfg["countin"]?.isEmpty == false
                                   ? cfg["countin"]! : "read from the demo"))
                        Button("Save") { set("countin", countin) }
                        Text("offered when the demo itself says nothing")
                            .font(.system(size: 11))
                            .foregroundStyle(pal.sub)
                    }
                }
                group("Sounds") {
                    pathRow("Where sample libraries live",
                            key: "sounds_dir")
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
                Text(status)
                    .font(.system(size: 13))
                    .foregroundStyle(pal.sub)
                    .padding(.bottom, 20)
                    .accessibilityAddTraits(.updatesFrequently)
            }
            .padding(.horizontal, 20)
        }
        .onAppear {
            cfg = loadConfig()
            composer = cfg["composer"] ?? ""
            countin = cfg["countin"] ?? ""
        }
    }

    @ViewBuilder
    func group(_ title: String,
               @ViewBuilder _ content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(pal.sub)
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
                 + ((cfg[key]?.isEmpty == false) ? cfg[key]! : "not set"))
                .lineLimit(1)
            Spacer()
            Button("Choose…") {
                if let f = pickFile(start: cfg[key], dirs: true) {
                    set(key, f)
                }
            }
            if cfg[key]?.isEmpty == false {
                Button("Clear") { set(key, "") }
            }
        }
    }

    func bind(_ key: String) -> Binding<String> {
        Binding(get: { cfg[key] ?? "" },
                set: { set(key, $0) })
    }

    func yesno(_ key: String) -> Binding<Bool> {
        Binding(get: { cfg[key] == "yes" },
                set: { set(key, $0 ? "yes" : "no") })
    }

    func set(_ key: String, _ value: String) {
        guard let tool = Tool.find() else {
            status = "I can't find the Copyist engine."
            return
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool.python)
        p.arguments = [tool.script, "set", "\(key)=\(value)"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        try? p.run()
        p.waitUntilExit()
        let d = pipe.fileHandleForReading.readDataToEndOfFile()
        let line = String(decoding: d, as: UTF8.self)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        status = line.isEmpty ? "Saved." : line
        cfg = loadConfig()
        announce(status)
    }
}
