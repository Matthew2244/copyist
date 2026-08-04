using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace Copyist;

/// <summary>
/// Talks to the Python engine over the JSON protocol in prototype/engine.py.
/// The UI holds no music logic — see DESIGN.md 5.2. This is the Windows twin
/// of gui/macos/Sources/Copyist/Engine.swift and must stay behaviourally
/// identical to it.
/// </summary>
public static class Engine
{
    public sealed class EngineException : Exception
    {
        public EngineException(string message) : base(message) { }
    }

    /// prototype/engine.py, beside the binary, up the tree, or COPYIST_ENGINE.
    public static string? Locate()
    {
        var env = Environment.GetEnvironmentVariable("COPYIST_ENGINE");
        if (!string.IsNullOrEmpty(env) && File.Exists(env)) return env;

        var dir = AppContext.BaseDirectory;
        for (var i = 0; i < 8 && dir is not null; i++)
        {
            var candidate = Path.Combine(dir, "prototype", "engine.py");
            if (File.Exists(candidate)) return candidate;
            dir = Path.GetDirectoryName(dir.TrimEnd(Path.DirectorySeparatorChar));
        }
        return null;
    }

    private static JsonElement Run(IEnumerable<string> args)
    {
        var engine = Locate() ?? throw new EngineException(
            "Could not find prototype/engine.py. Set COPYIST_ENGINE to its path.");

        var psi = new ProcessStartInfo
        {
            FileName = "python",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        psi.ArgumentList.Add(engine);
        foreach (var a in args) psi.ArgumentList.Add(a);

        using var p = Process.Start(psi)
            ?? throw new EngineException("Could not start Python.");
        var stdout = p.StandardOutput.ReadToEnd();
        var stderr = p.StandardError.ReadToEnd();
        p.WaitForExit();

        JsonDocument doc;
        try { doc = JsonDocument.Parse(stdout); }
        catch
        {
            throw new EngineException(string.IsNullOrWhiteSpace(stderr)
                ? "The engine returned nothing readable."
                : stderr[..Math.Min(400, stderr.Length)]);
        }

        var root = doc.RootElement.Clone();
        doc.Dispose();
        if (!root.TryGetProperty("ok", out var ok) || !ok.GetBoolean())
        {
            throw new EngineException(
                root.TryGetProperty("error", out var e)
                    ? e.GetString() ?? "Unknown engine error."
                    : "Unknown engine error.");
        }
        return root;
    }

    public static Analysis Analyze(string path) =>
        new(Run(new[] { "analyze", path }));

    public static Conversion Convert(string path, string outPath, string? key,
                                     int reach, int comfortable)
    {
        var args = new List<string>
        {
            "convert", path, "--out", outPath,
            "--reach", reach.ToString(), "--comfortable", comfortable.ToString(),
        };
        if (!string.IsNullOrWhiteSpace(key)) { args.Add("--key"); args.Add(key!); }
        return new Conversion(Run(args));
    }
}

// ---------------------------------------------------------------- models

public static class Json
{
    public static JsonElement Obj(this JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) ? v : default;

    public static int Int(this JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number
            ? v.GetInt32() : 0;

    public static double Num(this JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number
            ? v.GetDouble() : 0;

    public static string Str(this JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) ? v.GetString() ?? "" : "";

    public static bool Bool(this JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.True;
}

public sealed record KeyGuess(string Name, int Confidence)
{
    public string Display => $"{Name} — {Confidence}% confident";
}

public sealed class Analysis
{
    public int Notes { get; }
    public double Bpm { get; }
    public bool ConstantTempo { get; }
    public string Meter { get; }
    public string Grid { get; }
    public string TimingExplanation { get; }
    public double OnGrid { get; }
    public bool LengthsQuantized { get; }
    public double LengthMedianMs { get; }
    public List<KeyGuess> Keys { get; } = new();
    public int MaxSimultaneous { get; }
    public string WidestName { get; }
    public int VelocityLow { get; }
    public int VelocityHigh { get; }
    public int Pedal { get; }
    public int Markers { get; }
    public List<string> TrackNames { get; } = new();

    public Analysis(JsonElement d)
    {
        Notes = d.Int("notes");
        var tempo = d.Obj("tempo");
        Bpm = tempo.Num("bpm");
        ConstantTempo = tempo.Bool("constant");
        var m = d.Obj("meter");
        Meter = $"{m.Int("beats")}/{m.Int("beatType")}";
        var t = d.Obj("timing");
        Grid = t.Str("grid");
        TimingExplanation = t.Str("explanation");
        OnGrid = t.Num("onGrid");
        var l = d.Obj("lengths");
        LengthsQuantized = l.Bool("quantized");
        LengthMedianMs = l.Num("medianMs");
        if (d.TryGetProperty("keys", out var keys))
            foreach (var k in keys.EnumerateArray())
                Keys.Add(new KeyGuess(k.Str("name"), k.Int("confidence")));
        var tex = d.Obj("texture");
        MaxSimultaneous = tex.Int("maxSimultaneous");
        WidestName = tex.Str("widestName");
        var v = d.Obj("velocity");
        VelocityLow = v.Int("low");
        VelocityHigh = v.Int("high");
        Pedal = d.Int("pedal");
        if (d.TryGetProperty("markers", out var mk)) Markers = mk.GetArrayLength();
        if (d.TryGetProperty("tracks", out var tr))
            foreach (var x in tr.EnumerateArray())
            {
                var n = x.Int("notes");
                if (n <= 0) continue;
                var name = x.Str("name");
                TrackNames.Add($"{(name.Length == 0 ? "unnamed" : name)} — {n} notes");
            }
    }

    /// Written for a screen reader: one sentence saying the important thing.
    public string Headline =>
        $"{Notes} notes, {Meter}, " +
        (ConstantTempo ? $"{Math.Round(Bpm)} BPM" : $"variable tempo around {Math.Round(Bpm)} BPM") +
        $". {TimingExplanation}";
}

public sealed class Finding
{
    public string Id { get; }
    public string Severity { get; }
    public string What { get; }
    public string Why { get; }
    public string Suggestion { get; }
    public string Location { get; }

    public Finding(JsonElement d)
    {
        Id = d.Str("id");
        Severity = d.Str("severity");
        What = d.Str("what");
        Why = d.Str("why");
        Suggestion = d.Str("suggestion");
        Location = d.Str("location");
    }

    public string SeverityLabel => Severity switch
    {
        "will-look-bad" => "Will look bad",
        "uncertain" => "Unsure",
        _ => "Fixed",
    };

    /// Everything a screen reader should say for this row, in one utterance.
    public string Spoken
    {
        get
        {
            var s = $"{SeverityLabel}. {What}.";
            if (Location.Length > 0) s += $" At {Location}.";
            if (Why.Length > 0) s += $" Because {Why}.";
            if (Suggestion.Length > 0) s += $" Fix: {Suggestion}.";
            return s;
        }
    }

    public string Display =>
        $"{Id}: {What}" +
        (Why.Length > 0 ? $"\nWhy: {Why}" : "") +
        (Suggestion.Length > 0 ? $"\nFix: {Suggestion}" : "");
}

public sealed class Conversion
{
    public string Output { get; }
    public string Key { get; }
    public string Instrument { get; }
    private readonly Dictionary<string, int> _ints = new();
    public List<Finding> Findings { get; } = new();

    public Conversion(JsonElement d)
    {
        Output = d.Str("output");
        var s = d.Obj("summary");
        Key = s.Str("key");
        Instrument = s.Str("instrument");
        foreach (var name in new[]
                 {
                     "measures", "notes", "handsCertain", "handsInferred",
                     "handsLowConfidence", "phantomRestsRemoved", "genuineRests",
                     "pedalMarks", "doubleAccidentals",
                 })
            _ints[name] = s.Int(name);

        if (d.TryGetProperty("findings", out var f))
            foreach (var x in f.EnumerateArray()) Findings.Add(new Finding(x));
    }

    public int Int(string k) => _ints.TryGetValue(k, out var v) ? v : 0;

    public string Headline =>
        $"{Int("measures")} bars of {Instrument} in {Key}. " +
        $"{Int("phantomRestsRemoved")} phantom rests removed, " +
        $"{Int("pedalMarks")} pedal marks written, " +
        $"{Int("handsLowConfidence")} notes need your ear.";
}
