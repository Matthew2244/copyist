#!/usr/bin/env python3
"""
Corpus regression runner.

Asserts the invariants recorded in each fixture's README. Runs anywhere on
stock Python 3; the round-trip check is skipped when MuseScore is not present,
because it needs `mscore` to render MusicXML back to MIDI.

Usage:  python3 test_corpus.py
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CORPUS = os.path.join(ROOT, "corpus")
sys.path.insert(0, HERE)

import analyze                                    # noqa: E402
import convert                                    # noqa: E402

MSCORE_CANDIDATES = [
    "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
    "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
    shutil.which("mscore") or "",
    shutil.which("musescore") or "",
]

passed = failed = skipped = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def skip(name, why):
    global skipped
    skipped += 1
    print(f"  SKIP  {name} — {why}")


def find_mscore():
    for c in MSCORE_CANDIDATES:
        if c and os.path.exists(c):
            return c
    return None


def convert_to(src, out, key):
    buf = io.StringIO()
    with redirect_stdout(buf):
        convert.convert(src, out, key, 17, 14)
    return buf.getvalue()


def verdict(path):
    mid = analyze.parse_midi(path)
    x = analyze.extract(mid)
    bpm = 60_000_000 / x["tempos"][0][1] if x["tempos"] else 120.0
    _, st = analyze.classify_timing(x["notes"], mid["division"], bpm)
    if not st:
        return "UNKNOWN"
    if st["exact"] > 0.95 or st["peak"] < 1.0:
        return "HARD QUANTIZED"
    if abs(st["r1"]) < 0.20 and st["pct"] < 95:
        return "QUANTIZED THEN HUMANIZED"
    if st["r1"] > 0.25 or st["pct"] >= 95:
        return "LIVE PLAYING"
    return "AMBIGUOUS"


def note_set(path):
    mid = analyze.parse_midi(path)
    x = analyze.extract(mid)
    d = mid["division"]
    return {(round(n.on / d, 4), n.pitch) for n in x["notes"]}


def check_spelling(d, key):
    """Fixtures carrying expected-spelling.json assert per-note spelling."""
    truth_path = os.path.join(d, "expected-spelling.json")
    if not os.path.exists(truth_path):
        return
    import json
    truth = json.load(open(truth_path))
    mid = analyze.parse_midi(os.path.join(d, "clean.mid"))
    notes = analyze.extract(mid)["notes"]
    from spelling import ps13, double_accidentals
    got = ps13(notes)
    if len(got) != len(truth):
        check("spelling: note count matches ground truth", False,
              f"{len(got)} vs {len(truth)}")
        return
    ok = sum(1 for g, t in zip(got, truth)
             if g[0] == t["step"] and g[1] == t["alter"])
    pct = ok / len(truth) * 100
    check(f"spelling accuracy >= 95% (got {pct:.1f}%)", pct >= 95.0)
    check("no double accidentals", double_accidentals(got) == 0)

    # The point of a modulating fixture: pitches that must be spelled two ways.
    want_two = {t["pitch"] for t in truth
                if len({(u["step"], u["alter"]) for u in truth
                        if u["pitch"] == t["pitch"]}) > 1}
    if want_two:
        bad = [p for p in want_two
               if len({(g[0], g[1]) for g, n in zip(got, notes)
                       if n.pitch == p}) < 2]
        check(f"{len(want_two)} pitch(es) spelled both ways as required",
              not bad, f"single-spelled: {bad}")


def check_detail_levels(d, key):
    """11 — reduction must actually reduce, and keep the harmony."""
    import xml.etree.ElementTree as ET
    src = os.path.join(d, "clean.mid")
    tmp = tempfile.mkdtemp()
    counts = {}
    for level in ("full", "slashes", "symbols"):
        out = os.path.join(tmp, f"{level}.musicxml")
        buf = io.StringIO()
        with redirect_stdout(buf):
            convert.convert(src, out, key, 17, 14, level)
        r = ET.parse(out).getroot()
        notes = r.findall(".//note")
        slashes = [n for n in notes if (n.findtext("notehead") or "") == "slash"]
        counts[level] = {
            "pitched": len(notes) - len(slashes),
            "slashes": len(slashes),
            "harmony": len(r.findall(".//harmony")),
            "staves": int(r.findtext(".//attributes/staves") or 1),
        }
    shutil.rmtree(tmp, ignore_errors=True)

    check("full detail notates pitches", counts["full"]["pitched"] > 0)
    check("full detail uses two staves", counts["full"]["staves"] == 2)
    check("slashes level notates no pitches", counts["slashes"]["pitched"] == 0)
    check("slashes level emits slashes", counts["slashes"]["slashes"] > 0)
    check("symbols level is sparser than slashes",
          counts["symbols"]["slashes"] < counts["slashes"]["slashes"])
    check("reduced levels use one staff",
          counts["slashes"]["staves"] == 1 and counts["symbols"]["staves"] == 1)
    for level in ("full", "slashes", "symbols"):
        check(f"{level} carries chord symbols", counts[level]["harmony"] > 0)


def check_duration_algebra():
    """
    Time must be conserved for EVERY duration, not just tidy ones.

    A remainder smaller than the shortest notatable value used to be dropped,
    which left measures a few ticks short — silently, and only on material
    whose final chord does not land on the grid. Nine of twenty-five real
    files hit it; not one synthetic fixture did.
    """
    from convert import decompose
    bad = []
    for div in (384, 480, 960):
        for t in range(1, 4 * div + 1):
            if sum(x[0] for x in decompose(t, div)) != t:
                bad.append((div, t))
    check(f"decompose conserves time for all durations at 3 divisions",
          not bad, f"{len(bad)} failures, e.g. {bad[:3]}")


def check_key_names_are_usable():
    """
    Every key estimate_key can produce must be one convert() accepts.

    These were two different vocabularies: the estimator named keys with
    sharps only, so it emitted 'A# major' and 'D# major', which the converter
    could not look up. It then printed a message and RETURNED, leaving the
    caller believing it had succeeded. Six of twenty-five real files came out
    empty and reported success.
    """
    from convert import KEYS
    import analyze
    class FakeNote:
        def __init__(self, p): self.pitch, self.dur = p, 480
    missing = []
    for pc in range(12):
        for chord in ([0, 4, 7], [0, 3, 7]):
            notes = [FakeNote(60 + (pc + i) % 12) for i in chord] * 4
            for name, _ in analyze.estimate_key(notes):
                if name not in KEYS:
                    missing.append(name)
    check("every estimated key name is one the converter accepts",
          not missing, f"unusable: {sorted(set(missing))}")


def check_parts(d):
    """
    10 — multi-part. The fixture has NO track names on purpose: every real
    file that prompted this work was labelled entirely by GM program, and
    name-only resolution identified none of them.
    """
    import json
    import xml.etree.ElementTree as ET
    want_path = os.path.join(d, "expected-parts.json")
    if not os.path.exists(want_path):
        return
    want = json.load(open(want_path))
    r = ET.parse(os.path.join(d, "expected.musicxml")).getroot()

    got = [sp.findtext("part-name") for sp in r.findall(".//score-part")]
    check(f"{len(want)} parts detected from GM programs alone",
          got == [w["name"] for w in want], f"got {got}")

    for sp, w in zip(r.findall(".//score-part"), want):
        pid = sp.get("id")
        part = [p for p in r.findall("part") if p.get("id") == pid][0]
        t = part.find(".//transpose")
        chromatic = int(t.findtext("chromatic")) if t is not None else 0
        # MusicXML <transpose> is written -> sounding, the opposite direction
        check(f"{w['name']} transposes correctly",
              chromatic == -w["transpose"],
              f"expected {-w['transpose']}, got {chromatic}")

    # All three pedals, not just sustain. Sostenuto is the one that lets a
    # bass note ring under a dry passage; dropping it asks the player to do
    # what the composer specifically avoided.
    ptypes = {p.get("type") for p in r.findall(".//pedal")}
    words = {w.text for w in r.findall(".//words")}
    check("sustain pedal written", "start" in ptypes and "stop" in ptypes)
    check("sostenuto pedal written", "sostenuto" in ptypes)
    check("una corda written as text",
          "una corda" in words and "tre corde" in words)

    drums = [w for w in want if "Drum" in w["name"]]
    if drums:
        check("percussion is written unpitched",
              len(r.findall(".//unpitched")) > 0)
        check("percussion carries noteheads",
              len(r.findall(".//notehead")) > 0)


def check_organ(d):
    """
    8 / 10 — an organ is ONE player at ONE instrument on THREE staves.
    Copyist's generic one-part-per-channel rule gets this exactly wrong.
    """
    import json
    import xml.etree.ElementTree as ET
    want_path = os.path.join(d, "expected-organ.json")
    if not os.path.exists(want_path):
        return
    want = json.load(open(want_path))
    r = ET.parse(os.path.join(d, "expected.musicxml")).getroot()

    names = [sp.findtext("part-name") for sp in r.findall(".//score-part")]
    check("three organ channels become ONE part",
          names == [want["name"]], f"got {names}")
    check(f"organ part has {want['staves']} staves",
          r.findtext(".//attributes/staves") == str(want["staves"]))
    clefs = [c.findtext("sign") for c in r.findall(".//clef")]
    check("pedal staff is bass clef",
          len(clefs) == want["staves"] and clefs[-1] == "F", f"got {clefs}")
    words = {w.text for w in r.findall(".//words")}
    check("drawbar registration written",
          any("drawbars" in w for w in words), f"got {sorted(words)}")


def check_tuplet_ladder():
    """
    7.2 — the escalation ladder as a regression test.

    Four attempts at tuplets failed because they measured a symptom on real
    repertoire across dozens of confounded differences. The ladder adds one
    complication at a time to a case known to work, and it found all three
    real bugs — brackets not spanning rests, beats containing anything the
    tuplet cannot express, and ties across a tuplet beat boundary — in
    minutes. Every rung must keep producing valid, balanced MusicXML.
    """
    import xml.etree.ElementTree as ET
    import tuplet_ladder as TL
    import multipart as MP
    tmp = tempfile.mkdtemp()
    bad = []
    for name, fn in TL.RUNGS:
        src = TL.write(name, fn())
        out = os.path.join(tmp, name + ".musicxml")
        try:
            with redirect_stdout(io.StringIO()):
                MP.convert(src, out, "C major", 17, 14)
            r = ET.parse(out).getroot()
        except Exception as e:
            bad.append(f"{name}: {type(e).__name__}")
            continue
        div = int(r.findtext(".//divisions"))
        expect = None
        for part in r.findall("part"):
            for m in part.findall("measure"):
                t = m.find(".//time")
                if t is not None:
                    expect = (int(t.findtext("beats"))
                              * (4 / int(t.findtext("beat-type"))) * div)
                per = {}
                for e in m:
                    if e.tag != "note" or e.find("chord") is not None:
                        continue
                    v = e.findtext("voice")
                    per[v] = per.get(v, 0) + int(e.findtext("duration"))
                if per and not all(abs(x - expect) < 1e-6 for x in per.values()):
                    bad.append(f"{name}: measure {m.get('number')} unbalanced")
                    break
        # every tuplet group must total a whole number of beats
        for part in r.findall("part"):
            run, inside = 0, False
            for n in part.iter("note"):
                tup = n.find(".//tuplet")
                if tup is not None and tup.get("type") == "start":
                    inside, run = True, 0
                # Chord members share a tick — counting each one double-counts
                # the group, which is what this assertion got wrong first.
                if inside and n.find("chord") is None:
                    run += int(n.findtext("duration"))
                if tup is not None and tup.get("type") == "stop":
                    if run % div != 0:
                        bad.append(f"{name}: tuplet group {run} ticks, "
                                   f"not a whole beat ({div})")
                    inside = False
    shutil.rmtree(tmp, ignore_errors=True)
    check(f"all {len(TL.RUNGS)} tuplet ladder rungs valid and balanced",
          not bad, "; ".join(bad[:3]))


def check_meter_charts():
    """
    CHART-FORMAT.md 3.6 — per-bar meter changes, end to end: printed time
    signatures at the change bars in every part, chords spread against the
    bar's own meter, multirests breaking where a player must look up, the
    demo door reading the file's own signatures, the listen-trim walk, and
    every refusal in one sentence.
    """
    import xml.etree.ElementTree as ET
    import chartc
    import chartdemo
    import smf
    from chart import verify_measures
    tmp = tempfile.mkdtemp()

    def compile_chart(name, text):
        p = os.path.join(tmp, name)
        open(p, "w").write(text)
        out = os.path.join(tmp, name + ".build")
        buf = io.StringIO()
        with redirect_stdout(buf):
            files = chartc.compile_chart(p, out)
        return out, buf.getvalue(), files

    def refusal(name, text):
        p = os.path.join(tmp, name)
        open(p, "w").write(text)
        try:
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(p, os.path.join(tmp, "x"))
        except SystemExit as e:
            return str(e)
        return ""

    HEAD = ("title: T\nkey: C\nmeter: 4/4\ntempo: 120\n\n"
            "band:\n  piano\n  trumpet\n\n")
    MIX = (HEAD + "section A, 8 bars\n"
           "  at bar 3: meter 5/4\n  at bar 5: meter 4/4\n"
           "  chords: C F, Dm7 G7, C7 F7, C F G, C x4\n"
           "  piano: groove\n  trumpet: tacet\n")

    out, log, files = compile_chart("mixed.chart", MIX)
    check("mixed-meter chart: every measure sums to its own bar",
          not verify_measures(files))
    for part in ("piano", "trumpet"):
        r = ET.parse(os.path.join(out, f"T — {part}.musicxml")).getroot()
        times = {m.get("number"): (t.findtext("beats"), t.findtext("beat-type"))
                 for m in r.iter("measure")
                 for t in m.iter("time")}
        check(f"{part} part restates the time at bars 3 and 5 only",
              times == {"1": ("4", "4"), "3": ("5", "4"), "5": ("4", "4")},
              f"got {times}")
    r = ET.parse(os.path.join(out, "T — piano.musicxml")).getroot()
    bar3 = next(m for m in r.iter("measure") if m.get("number") == "3")
    offs = [h.findtext("offset") for h in bar3.iter("harmony")]
    check("two chords in a 5/4 bar split at beat 3.5",
          offs == [None, "60"], f"got {offs}")
    r = ET.parse(os.path.join(out, "T — trumpet.musicxml")).getroot()
    multi = [m.get("number") for m in r.iter("measure")
             if m.find(".//multiple-rest") is not None]
    check("a resting part's multirests break at each meter change",
          multi == ["6"] or multi == ["1", "6"], f"got {multi}")

    # the demo door: a figure inside a changed region, located by the
    # file's own time signatures
    div = 480
    ts = [(0, 4, 4), (2 * 4 * div, 3, 4)]
    notes = [(i * div, i * div + div - 40, 60 + i, 90) for i in range(8)]
    notes += [(3840 + i * div, 3840 + i * div + div - 40, 72 - i, 96)
              for i in range(3)]
    notes.append((5280, 6680, 67, 100))
    demo = os.path.join(tmp, "mix.mid")
    smf.write(demo, notes, div, 100, ts=ts, name="lead")
    DEMO_HEAD = ("title: D\nkey: C\nmeter: 4/4\ntempo: 100\n"
                 "demo: mix.mid\n\nband:\n  trumpet\n  piano\n\n")
    out, log, files = compile_chart(
        "demo.chart", DEMO_HEAD +
        "section A, 6 bars\n  at bar 3: meter 3/4\n"
        "  chords: C, F, G, C, G, C\n"
        "  trumpet: from demo bars 3-4 at bar 3\n  piano: groove\n")
    check("demo figure in a changed region: measures sum",
          not verify_measures(files))
    r = ET.parse(os.path.join(out, "D — trumpet.musicxml")).getroot()
    bar3 = next(m for m in r.iter("measure") if m.get("number") == "3")
    steps = [n.findtext(".//step") for n in bar3.iter("note")
             if n.find("rest") is None]
    check("the figure's notes land in the right printed bar, written pitch",
          steps == ["D", "C", "C"], f"got {steps}")

    # the listen trim: a cumulative walk, not one multiplication
    chart = chartc.parse_chart(os.path.join(tmp, "mixed.chart"))
    s = chartc.seconds_before(chart, 5)
    check("seconds_before walks 4/4 and 5/4 bars at their own lengths",
          abs(s - (2 * 2.0 + 2 * 2.5)) < 1e-9, f"got {s}")

    # refusals, each in one sentence
    for name, text, want in (
        ("r1.chart", HEAD + "section A, 4 bars\n  at bar 9: meter 3/4\n"
         "  chords: C x4\n", "outside its 4 bars"),
        ("r2.chart", HEAD + "section A, 4 bars\n  at bar 2: meter 3/4\n"
         "  at bar 2: meter 5/4\n  chords: C x4\n", "declares two meters"),
        ("r3.chart", HEAD + "section A, 4 bars\n  at bar 2: meter 9/x\n"
         "  chords: C x4\n", "cannot read meter"),
        ("r4.chart", DEMO_HEAD + "section A, 6 bars\n"
         "  at bar 3: meter 3/4\n  chords: C, F, G, C, G, C\n"
         "  trumpet: from demo bars 2-3\n  piano: groove\n",
         "crossing the meter change"),
        ("r5.chart", DEMO_HEAD + "section A, 6 bars\n"
         "  at bar 2: meter 5/4\n  chords: C, F, G, C, G, C\n"
         "  trumpet: from demo bars 3-4 at bar 2\n  piano: groove\n",
         "must agree where a figure lands"),
    ):
        got = refusal(name, text)
        check(f"refused with '{want}'", want in got, f"got: {got}")

    # findings that speak
    out, log, _ = compile_chart(
        "single.chart", "title: S\nkey: C\nmeter: 6/8\ntempo: 60\n"
        "demo: mix.mid\n\nband:\n  trumpet\n  piano\n\n"
        "section A, 4 bars\n  chords: C, F, G, C\n"
        "  trumpet: from demo bars 1-2\n  piano: groove\n")
    check("single-meter mismatch is a finding, not a failure",
          "trusting the chart" in log, f"got: {log}")
    out, log, _ = compile_chart(
        "compound.chart", "title: X\nkey: C\nmeter: 6/8\ntempo: 60\n\n"
        "band:\n  piano\n\nsection A, 8 bars\n"
        "  at bar 3: meter 4/4\n  at bar 5: meter 4/4\n  chords: C x8\n")
    check("compound-to-simple change without a tempo says so",
          "carries the quarter note" in log, f"got: {log}")
    check("a meter that changes nothing says so",
          "nothing changes" in log, f"got: {log}")

    shutil.rmtree(tmp, ignore_errors=True)


def run_fixture(name, key, expect_verdicts):
    print(f"\n{name}")
    d = os.path.join(CORPUS, name)
    expected = os.path.join(d, "expected.musicxml")
    golden = open(expected, "rb").read()

    tmp = tempfile.mkdtemp()
    outputs = {}
    for src, label in (("clean.mid", "clean"), ("humanized.mid", "humanized")):
        path = os.path.join(d, src)
        if not os.path.exists(path):
            continue
        out = os.path.join(tmp, f"{label}.musicxml")
        if os.path.exists(os.path.join(d, "expected-parts.json")) or \
                os.path.exists(os.path.join(d, "expected-organ.json")):
            import multipart
            with redirect_stdout(io.StringIO()):
                multipart.convert(path, out, key, 17, 14)
        else:
            convert_to(path, out, key)
        outputs[label] = out
        check(f"{label}.mid converts byte-identical to expected.musicxml",
              open(out, "rb").read() == golden)

    for src, want in expect_verdicts.items():
        got = verdict(os.path.join(d, src))
        check(f"{src} classifies as {want}", got == want, f"got {got}")

    check_spelling(d, key)
    check_parts(d)
    check_organ(d)
    if not any(os.path.exists(os.path.join(d, f))
               for f in ('expected-parts.json', 'expected-organ.json')):
        check_detail_levels(d, key)

    ms = find_mscore()
    if not ms:
        skip("round-trip note accuracy", "MuseScore not installed")
    else:
        rt = os.path.join(tmp, "rt.mid")
        subprocess.run([ms, "-o", rt, expected],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(rt):
            check("round-trip note accuracy", False, "mscore produced no output")
        else:
            orig = note_set(os.path.join(d, "clean.mid"))
            back = note_set(rt)
            acc = len(orig & back) / len(orig) * 100
            check(f"round-trip note accuracy 100% (got {acc:.1f}%)", acc == 100.0)

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("\ninvariants")
    check_duration_algebra()
    check_key_names_are_usable()
    check_tuplet_ladder()
    check_meter_charts()

    run_fixture("two-hand-piano", "C# minor",
                {"clean.mid": "HARD QUANTIZED",
                 "humanized.mid": "QUANTIZED THEN HUMANIZED"})
    run_fixture("spelling-modulation", "Eb major",
                {"clean.mid": "HARD QUANTIZED"})
    run_fixture("small-ensemble", None, {})
    run_fixture("hammond-organ", None, {})

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    sys.exit(1 if failed else 0)
