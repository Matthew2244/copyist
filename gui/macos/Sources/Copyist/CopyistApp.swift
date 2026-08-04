import SwiftUI
import AppKit
import UniformTypeIdentifiers

// Copyist for macOS — DESIGN.md 5.1.
//
// There is no canvas here, and that is deliberate. Every screen is a list, a
// table, a form or a transport, so VoiceOver gets correct name, role and value
// from native controls without a single custom accessibility implementation.
// The score itself opens in MuseScore; Copyist's job is everything before that.
//
// Two rules this file follows throughout:
//   * every row is ONE accessibility element that says the whole thing, rather
//     than a label and a value VoiceOver reads as two separate stops
//   * anything that finishes without focus moving gets announced, because a
//     result you cannot see and are not told about has not been delivered

enum Launch {
    static let args = CommandLine.arguments
    static var auditing: Bool { args.contains("--audit") }
    static var openPath: String? {
        guard let i = args.firstIndex(of: "--open"), i + 1 < args.count
        else { return nil }
        return args[i + 1]
    }
}

@main
struct CopyistApp: App {
    var body: some Scene {
        WindowGroup("Copyist") {
            ContentView()
                .frame(minWidth: 620, minHeight: 520)
        }
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Open MIDI File…") {
                    NotificationCenter.default.post(name: .copyistOpen, object: nil)
                }
                .keyboardShortcut("o")
            }
        }
    }
}

extension Notification.Name {
    static let copyistOpen = Notification.Name("copyistOpen")
}

// MARK: - Announcements

/// Speak something through VoiceOver without moving focus.
func announce(_ message: String) {
    guard !message.isEmpty else { return }
    NSAccessibility.post(
        element: NSApp as Any,
        notification: .announcementRequested,
        userInfo: [
            .announcement: message,
            .priority: NSAccessibilityPriorityLevel.high.rawValue,
        ]
    )
}

// MARK: - Root

struct ContentView: View {
    @State private var midiPath: String?
    @State private var analysis: Analysis?
    @State private var conversion: Conversion?
    @State private var chosenKey = ""
    @State private var reach = 17
    @State private var comfortable = 14
    @State private var status = "No file open. Press Command O to choose a MIDI file."
    @State private var busy = false
    @State private var errorText: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let a = analysis { AnalysisSection(analysis: a) }
                    if analysis != nil { settingsSection }
                    if let c = conversion { ResultSection(conversion: c) }
                    if analysis == nil && !busy { welcome }
                }
                .padding(20)
            }
            Divider()
            statusBar
        }
        .alert("Copyist could not do that",
               isPresented: .constant(errorText != nil),
               presenting: errorText) { _ in
            Button("OK") { errorText = nil }
        } message: { Text($0) }
        .onReceive(NotificationCenter.default.publisher(for: .copyistOpen)) { _ in
            openFile()
        }
        .onAppear {
            if let path = Launch.openPath { load(path) }
            if Launch.auditing {
                // Give SwiftUI time to build the tree, and time for an
                // auto-opened file to finish analyzing, before inspecting.
                let delay: DispatchTimeInterval =
                    Launch.openPath == nil ? .milliseconds(900) : .seconds(4)
                DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                    Audit.start()
                }
            }
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(spacing: 12) {
            Button("Open MIDI File…") { openFile() }
                .keyboardShortcut("o")
                .accessibilityHint("Choose a MIDI file exported from your DAW.")

            Button("Convert to MusicXML") { convert() }
                .keyboardShortcut("r")
                .disabled(analysis == nil || busy)
                .accessibilityHint(
                    "Writes a MusicXML file you can open in MuseScore.")

            if busy { ProgressView().controlSize(.small).accessibilityHidden(true) }
            Spacer()
        }
        .padding(12)
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Copyist").font(.title).accessibilityAddTraits(.isHeader)
            Text("Open a MIDI file exported from your DAW. Copyist reads what "
                 + "you played, tells you what it found, and writes MusicXML "
                 + "that opens cleanly in MuseScore.")
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }

    // MARK: Settings

    private var settingsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Settings").font(.headline).accessibilityAddTraits(.isHeader)

            Picker("Key", selection: $chosenKey) {
                Text("Let Copyist decide").tag("")
                ForEach(analysis?.keys ?? []) { k in
                    Text("\(k.name) — \(k.confidence)% confident").tag(k.name)
                }
            }
            .accessibilityHint(
                "Copyist guesses the key. When two are close, choose the right one here.")

            Stepper(value: $reach, in: 8...24) {
                Text("Maximum reach: \(reach) semitones")
            }
            .accessibilityValue("\(reach) semitones")
            .accessibilityHint(
                "The widest interval you can play with one hand. Used to decide "
                + "which notes must be two hands.")

            Stepper(value: $comfortable, in: 6...reach) {
                Text("Comfortable reach: \(comfortable) semitones")
            }
            .accessibilityValue("\(comfortable) semitones")
            .accessibilityHint("The widest interval you play without stretching.")
        }
    }

    // MARK: Status

    private var statusBar: some View {
        Text(status)
            .font(.callout)
            .padding(.horizontal, 16).padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityLabel("Status. \(status)")
    }

    // MARK: Actions

    private func openFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "mid"),
                                     UTType(filenameExtension: "midi"),
                                     UTType.midi].compactMap { $0 }
        panel.allowsMultipleSelection = false
        panel.prompt = "Analyze"
        panel.message = "Choose a MIDI file exported from your DAW."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        load(url.path)
    }

    private func load(_ path: String) {
        let url = URL(fileURLWithPath: path)
        midiPath = url.path
        conversion = nil
        chosenKey = ""
        busy = true
        status = "Analyzing \(url.lastPathComponent)…"

        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let a = try Engine.analyze(url.path)
                DispatchQueue.main.async {
                    analysis = a
                    busy = false
                    status = a.headline
                    announce("Analysis finished. " + a.headline)
                }
            } catch {
                DispatchQueue.main.async {
                    busy = false
                    analysis = nil
                    status = "Could not read that file."
                    errorText = error.localizedDescription
                    announce("Copyist could not read that file.")
                }
            }
        }
    }

    private func convert() {
        guard let path = midiPath else { return }
        let out = (path as NSString).deletingPathExtension + ".musicxml"
        busy = true
        status = "Converting…"

        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let c = try Engine.convert(path, to: out,
                                           key: chosenKey.isEmpty ? nil : chosenKey,
                                           reach: reach, comfortable: comfortable)
                DispatchQueue.main.async {
                    conversion = c
                    busy = false
                    status = c.headline
                    announce("Conversion finished. " + c.headline
                             + " Saved as \((c.output as NSString).lastPathComponent).")
                }
            } catch {
                DispatchQueue.main.async {
                    busy = false
                    status = "Conversion failed."
                    errorText = error.localizedDescription
                    announce("Conversion failed.")
                }
            }
        }
    }
}

// MARK: - Analysis

struct AnalysisSection: View {
    let analysis: Analysis

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("What Copyist found").font(.headline)
                .accessibilityAddTraits(.isHeader)

            Row("Timing", analysis.timingExplanation,
                extra: "Grid \(analysis.grid), \(fmt(analysis.onGrid))% of notes "
                     + "exactly on it")
            Row("Note lengths",
                analysis.lengthsQuantized
                    ? "Quantized. No phantom rests to remove."
                    : "Not quantized — median release \(fmt(analysis.lengthMedianMs)) "
                      + "milliseconds early. This is what makes stray rests.")
            Row("Tempo and meter",
                "\(Int(analysis.bpm.rounded())) BPM"
                + (analysis.constantTempo ? ", constant" : ", variable")
                + ", \(analysis.meter)")
            if let top = analysis.keys.first {
                let second = analysis.keys.dropFirst().first
                Row("Key",
                    second.map {
                        "\(top.name) at \(top.confidence)%, "
                        + "or \($0.name) at \($0.confidence)%"
                    } ?? "\(top.name) at \(top.confidence)%",
                    extra: (second?.confidence ?? 0) >= 40
                        ? "Close enough to be worth choosing yourself." : nil)
            }
            Row("Texture",
                "Up to \(analysis.maxSimultaneous) notes at once, "
                + "widest \(analysis.widestName)")
            Row("Velocity",
                "\(analysis.velocityLow) to \(analysis.velocityHigh)")
            Row("Sustain pedal",
                analysis.pedal > 0
                    ? "\(analysis.pedal) depressions, which become pedal marks"
                    : "None in the file")
            Row("Markers",
                analysis.markers > 0
                    ? "\(analysis.markers) found"
                    : "None. In REAPER, project markers survive MIDI export; "
                      + "regions and take markers do not.")
            if !analysis.trackNames.isEmpty {
                Row("Tracks", analysis.trackNames.joined(separator: "; "))
            }
        }
    }

    private func fmt(_ d: Double) -> String { String(format: "%.1f", d) }
}

/// A labelled fact. One accessibility element so VoiceOver reads it as a
/// single sentence rather than stopping twice.
struct Row: View {
    let label: String
    let value: String
    let extra: String?

    init(_ label: String, _ value: String, extra: String? = nil) {
        self.label = label; self.value = value; self.extra = extra
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.subheadline).bold()
            Text(value).fixedSize(horizontal: false, vertical: true)
            if let extra {
                Text(extra).font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(label). \(value). \(extra ?? "")")
    }
}

// MARK: - Result

struct ResultSection: View {
    let conversion: Conversion

    private var grouped: [(String, [Finding])] {
        let order = ["will-look-bad", "uncertain", "fixed-silently"]
        let titles = ["will-look-bad": "Will look bad — needs your judgement",
                      "uncertain": "Unsure — Copyist guessed",
                      "fixed-silently": "Fixed for you"]
        return order.compactMap { key in
            let items = conversion.findings.filter { $0.severity == key }
            return items.isEmpty ? nil : (titles[key] ?? key, items)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Result").font(.headline).accessibilityAddTraits(.isHeader)

            Row("Saved", (conversion.output as NSString).lastPathComponent,
                extra: conversion.output)
            Row("Score",
                "\(conversion.int("measures")) bars of \(conversion.instrument) "
                + "in \(conversion.key)")
            Row("Phantom rests removed", "\(conversion.int("phantomRestsRemoved"))",
                extra: "\(conversion.int("genuineRests")) genuine rests kept")
            Row("Hands",
                "\(conversion.int("handsCertain")) certain, "
                + "\(conversion.int("handsInferred")) inferred",
                extra: conversion.int("handsLowConfidence") > 0
                    ? "\(conversion.int("handsLowConfidence")) low confidence — "
                      + "listen to those and lock them"
                    : "None low confidence.")

            Button("Reveal in Finder") {
                NSWorkspace.shared.activateFileViewerSelecting(
                    [URL(fileURLWithPath: conversion.output)])
            }
            .accessibilityHint("Shows the MusicXML file so you can open it in MuseScore.")

            ForEach(grouped, id: \.0) { title, items in
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(title) (\(items.count))")
                        .font(.subheadline).bold()
                        .accessibilityAddTraits(.isHeader)
                    ForEach(items) { f in
                        FindingRow(finding: f)
                    }
                }
            }
        }
    }
}

struct FindingRow: View {
    let finding: Finding

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(finding.id): \(finding.what)")
                .fixedSize(horizontal: false, vertical: true)
            if !finding.why.isEmpty {
                Text("Why: \(finding.why)").font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !finding.suggestion.isEmpty {
                Text("Fix: \(finding.suggestion)").font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.leading, 8)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(finding.spoken)
    }
}
