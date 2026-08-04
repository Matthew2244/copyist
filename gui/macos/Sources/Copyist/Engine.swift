import Foundation

/// Talks to the Python engine over the JSON protocol in prototype/engine.py.
///
/// Everything the UI knows comes through here. The UI holds no music logic of
/// its own — see DESIGN.md 5.2. When the engine is ported to Rust this is the
/// only file that changes.
enum Engine {

    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    /// prototype/engine.py, found next to the binary, up the source tree, or
    /// named explicitly by COPYIST_ENGINE.
    static func locate() -> String? {
        let fm = FileManager.default
        if let env = ProcessInfo.processInfo.environment["COPYIST_ENGINE"],
           fm.isReadableFile(atPath: env) { return env }

        // Inside a built .app the engine ships in Resources.
        if let res = Bundle.main.resourceURL?
            .appendingPathComponent("prototype/engine.py"),
           fm.isReadableFile(atPath: res.path) { return res.path }

        var dir = URL(fileURLWithPath: CommandLine.arguments[0])
            .resolvingSymlinksInPath()
            .deletingLastPathComponent()
        for _ in 0..<8 {
            let candidate = dir.appendingPathComponent("prototype/engine.py")
            if fm.isReadableFile(atPath: candidate.path) { return candidate.path }
            dir = dir.deletingLastPathComponent()
        }
        return nil
    }

    static func run(_ args: [String]) throws -> [String: Any] {
        guard let engine = locate() else {
            throw Failure(message:
                "Could not find prototype/engine.py. Set COPYIST_ENGINE to its path.")
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments = ["python3", engine] + args
        let out = Pipe(), err = Pipe()
        p.standardOutput = out
        p.standardError = err
        try p.run()

        let data = out.fileHandleForReading.readDataToEndOfFile()
        let errText = String(data: err.fileHandleForReading.readDataToEndOfFile(),
                             encoding: .utf8) ?? ""
        p.waitUntilExit()

        guard let obj = try? JSONSerialization.jsonObject(with: data),
              let dict = obj as? [String: Any] else {
            throw Failure(message: errText.isEmpty
                ? "The engine returned nothing readable."
                : String(errText.prefix(400)))
        }
        if dict["ok"] as? Bool != true {
            throw Failure(message: dict["error"] as? String ?? "Unknown engine error.")
        }
        return dict
    }

    static func analyze(_ path: String) throws -> Analysis {
        Analysis(try run(["analyze", path]))
    }

    static func convert(_ path: String, to out: String, key: String?,
                        reach: Int, comfortable: Int,
                        detail: String = "full") throws -> Conversion {
        var args = ["convert", path, "--out", out, "--detail", detail,
                    "--reach", String(reach), "--comfortable", String(comfortable)]
        if let key, !key.isEmpty { args += ["--key", key] }
        return Conversion(try run(args))
    }
}

// MARK: - Models

struct KeyGuess: Identifiable {
    let name: String
    let confidence: Int
    var id: String { name }
}

struct Analysis {
    let notes: Int
    let bpm: Double
    let constantTempo: Bool
    let meter: String
    let grid: String
    let timingKind: String
    let timingExplanation: String
    let onGrid: Double
    let deviationSD: Double
    let lengthsQuantized: Bool
    let lengthMedianMs: Double
    let keys: [KeyGuess]
    let maxSimultaneous: Int
    let widestName: String
    let velocityLow: Int
    let velocityHigh: Int
    let pedal: Int
    let markers: Int
    let trackNames: [String]

    init(_ d: [String: Any]) {
        notes = d["notes"] as? Int ?? 0
        let tempo = d["tempo"] as? [String: Any] ?? [:]
        bpm = tempo["bpm"] as? Double ?? 0
        constantTempo = tempo["constant"] as? Bool ?? true
        let m = d["meter"] as? [String: Any] ?? [:]
        meter = "\(m["beats"] as? Int ?? 4)/\(m["beatType"] as? Int ?? 4)"
        let t = d["timing"] as? [String: Any] ?? [:]
        grid = t["grid"] as? String ?? "unknown"
        timingKind = t["kind"] as? String ?? "unknown"
        timingExplanation = t["explanation"] as? String ?? ""
        onGrid = t["onGrid"] as? Double ?? 0
        deviationSD = t["sd"] as? Double ?? 0
        let l = d["lengths"] as? [String: Any] ?? [:]
        lengthsQuantized = l["quantized"] as? Bool ?? false
        lengthMedianMs = l["medianMs"] as? Double ?? 0
        keys = (d["keys"] as? [[String: Any]] ?? []).map {
            KeyGuess(name: $0["name"] as? String ?? "?",
                     confidence: $0["confidence"] as? Int ?? 0)
        }
        let tex = d["texture"] as? [String: Any] ?? [:]
        maxSimultaneous = tex["maxSimultaneous"] as? Int ?? 0
        widestName = tex["widestName"] as? String ?? "—"
        let v = d["velocity"] as? [String: Any] ?? [:]
        velocityLow = v["low"] as? Int ?? 0
        velocityHigh = v["high"] as? Int ?? 0
        pedal = d["pedal"] as? Int ?? 0
        markers = (d["markers"] as? [[String: Any]] ?? []).count
        trackNames = (d["tracks"] as? [[String: Any]] ?? []).compactMap {
            let name = $0["name"] as? String ?? ""
            let n = $0["notes"] as? Int ?? 0
            return n > 0 ? "\(name.isEmpty ? "unnamed" : name) — \(n) notes" : nil
        }
    }

    /// Written for a screen reader: one sentence that says the important thing.
    var headline: String {
        let tempoText = constantTempo
            ? "\(Int(bpm.rounded())) BPM"
            : "variable tempo around \(Int(bpm.rounded())) BPM"
        return "\(notes) notes, \(meter), \(tempoText). \(timingExplanation)"
    }
}

struct Finding: Identifiable {
    let id: String
    let severity: String
    let what: String
    let why: String
    let suggestion: String
    let location: String

    init(_ d: [String: Any]) {
        id = d["id"] as? String ?? "?"
        severity = d["severity"] as? String ?? "fixed-silently"
        what = d["what"] as? String ?? ""
        why = d["why"] as? String ?? ""
        suggestion = d["suggestion"] as? String ?? ""
        location = d["location"] as? String ?? ""
    }

    var severityLabel: String {
        switch severity {
        case "will-look-bad": return "Will look bad"
        case "uncertain": return "Unsure"
        default: return "Fixed"
        }
    }

    /// Everything VoiceOver should say for this row, in one utterance.
    var spoken: String {
        var s = "\(severityLabel). \(what)."
        if !location.isEmpty { s += " At \(location)." }
        if !why.isEmpty { s += " Because \(why)." }
        if !suggestion.isEmpty { s += " Fix: \(suggestion)." }
        return s
    }
}

struct Conversion {
    let output: String
    let notatedMidi: String?
    let summary: [String: Any]
    let findings: [Finding]

    init(_ d: [String: Any]) {
        output = d["output"] as? String ?? ""
        notatedMidi = d["notatedMidi"] as? String
        summary = d["summary"] as? [String: Any] ?? [:]
        findings = (d["findings"] as? [[String: Any]] ?? []).map(Finding.init)
    }

    func int(_ k: String) -> Int { summary[k] as? Int ?? 0 }
    var key: String { summary["key"] as? String ?? "—" }
    var instrument: String { summary["instrument"] as? String ?? "—" }

    var headline: String {
        "\(int("measures")) bars of \(instrument) in \(key). "
        + "\(int("phantomRestsRemoved")) phantom rests removed, "
        + "\(int("pedalMarks")) pedal marks written, "
        + "\(int("handsLowConfidence")) notes need your ear."
    }
}
