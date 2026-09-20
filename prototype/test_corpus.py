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


def check_poly_charts():
    """
    DESIGN.md 8 married to the chart door: a keyboard-family part from a
    demo prints on the grand staff (hands split by physics), a note that
    keeps ringing under later movement becomes its own voice instead of
    being cut at the next onset, and the measure arithmetic survives the
    backups. A poly figure with nothing genuinely polyphonic must keep
    taking the old flat path.
    """
    import re
    import chartc
    import chartdemo
    import smf
    from chart import verify_measures
    tmp = tempfile.mkdtemp()

    div = 480
    piano = []
    for bar in range(2):
        t0 = bar * 1920
        piano.append((t0, t0 + 1900, 36 + bar * 5, 80))     # held LH root
        for i, tri in enumerate(((60, 64, 67), (60, 64, 67),
                                 (59, 62, 67), (60, 64, 67))):
            for p in tri:
                piano.append((t0 + i * 480, t0 + i * 480 + 430, p, 88))
    smf.write(os.path.join(tmp, "p.mid"), piano, div, 90)
    gtr = [(0, 1900, 40, 84)]                               # low E rings
    for i, dy in enumerate(((64, 67), (64, 69), (64, 67))):
        for p in dy:
            gtr.append((480 + i * 480, 480 + i * 480 + 430, p, 82))
    # bar 2: plain dyads, nothing held — must stay on the flat path
    for i in range(4):
        gtr.append((1920 + i * 480, 1920 + i * 480 + 430, 64, 82))
        gtr.append((1920 + i * 480, 1920 + i * 480 + 430, 67, 82))
    smf.write(os.path.join(tmp, "g.mid"), gtr, div, 90)

    open(os.path.join(tmp, "poly.chart"), "w").write(
        "title: P\nkey: C\nmeter: 4/4\ntempo: 90\n\nband:\n"
        '  piano, demo "p.mid"\n  guitar, demo "g.mid"\n\n'
        "section A, 2 bars\n  chords: C, F\n"
        "  piano: from demo bars 1-2\n  guitar: from demo bars 1-2\n")
    out = os.path.join(tmp, "build")
    buf = io.StringIO()
    with redirect_stdout(buf):
        files = chartc.compile_chart(os.path.join(tmp, "poly.chart"), out)
    log = buf.getvalue()
    check("poly chart: every measure sums through the backups",
          not verify_measures(files))

    xml = open(os.path.join(out, "P — piano.musicxml")).read()
    check("piano part declares the grand staff",
          "<staves>2</staves>" in xml and '<clef number="2"><sign>F' in xml)
    bars = dict(re.findall(r'<measure [^>]*number="(\d+)"[^>]*>(.*?)'
                           r'</measure>', xml, re.S))
    lh = re.findall(r'<note>(?:(?!</note>).)*?<octave>2</octave>'
                    r'(?:(?!</note>).)*?</note>', bars["1"], re.S)
    check("the held left-hand root lives on staff 2, voice 5",
          lh and all("<voice>5</voice>" in n and "<staff>2</staff>" in n
                     for n in lh), f"got {len(lh)} notes")
    check("hands split without inventing a held-voice finding for piano",
          "keep ringing" not in "".join(
              l for l in log.splitlines() if "piano" in l))

    xml = open(os.path.join(out, "P — guitar.musicxml")).read()
    bars = dict(re.findall(r'<measure [^>]*number="(\d+)"[^>]*>(.*?)'
                           r'</measure>', xml, re.S))
    check("the guitar's ringing low E is its own voice",
          "<backup>" in bars["1"] and "<voice>2</voice>" in bars["1"])
    check("a bar with nothing held stays one voice",
          "<backup>" not in bars["2"])
    check("the held voice announces itself in the findings",
          "keep ringing" in log and "guitar" in log)

    # the arpeggio degeneracy: a wash of let-ring must not empty the line
    arp = [(i * 480, 1920, 48 + iv, 80)
           for i, iv in enumerate((0, 4, 7, 12))]
    smf.write(os.path.join(tmp, "a.mid"), arp, div, 90)
    open(os.path.join(tmp, "arp.chart"), "w").write(
        "title: R\nkey: C\nmeter: 4/4\ntempo: 90\n\nband:\n"
        '  guitar, demo "a.mid"\n  piano\n\n'
        "section A, 1 bars\n  chords: C\n"
        "  guitar: from demo bars 1-1\n  piano: groove\n")
    with redirect_stdout(io.StringIO()):
        files = chartc.compile_chart(os.path.join(tmp, "arp.chart"),
                                     os.path.join(tmp, "abuild"))
    check("let-ring arpeggio: measures still sum", not verify_measures(files))
    xml = open(os.path.join(tmp, "abuild", "R — guitar.musicxml")).read()
    v1 = xml.count("<voice>1</voice>")
    check("of a wash of sustain, the first note rings and the line survives",
          xml.count("<voice>2</voice>") >= 1 and v1 >= 3,
          f"v1 {v1}, v2 {xml.count('<voice>2</voice>')}")

    # the prose speaks the layers
    dm = chartdemo.load_demo(os.path.join(tmp, "p.mid"))
    res = chartdemo.resolve_range(dm, None, 1, 2, 1, poly=True, grand=True,
                                  part_label="piano")
    said = " ".join(chartdemo.say_range(res, 0).values())
    check("the read-aloud names the hands",
          "Right hand:" in said and "Left hand:" in said, said[:120])

    shutil.rmtree(tmp, ignore_errors=True)


def check_phrasing_charts():
    """
    Phrasing is the writer's word, never unasked: `legato` reads the
    played gates into slurs, `ghosts` reads velocities into parenthesized
    noteheads, `straight` puts onsets on the eighth grid while durations
    stay as played. Swing feel makes the LISTENING document actually
    swing (via the measured MuseScore <sound><swing> encoding, riding a
    hidden words element); pages never carry the element. Asking for
    phrasing that the playing does not support is a finding, not a
    silent no-op.
    """
    import re
    import chartc
    import smf
    from chart import verify_measures
    tmp = tempfile.mkdtemp()

    div = 480
    # a legato phrase, a breath, a detached repeat; last two notes are
    # the same pitch — a slur onto a repeated note reads as a tie
    ten = [(0, 468, 65, 86), (480, 948, 68, 84), (960, 1420, 70, 88),
           (1920, 2200, 72, 85), (2400, 2870, 72, 85),
           (2880, 3200, 70, 84)]
    smf.write(os.path.join(tmp, "t.mid"), ten, div, 116)
    # a walking bass with one very soft pickup
    bs = [(0, 400, 41, 90), (480, 880, 45, 92), (960, 1060, 45, 34),
          (1440, 1840, 48, 88), (1920, 2320, 45, 90), (2400, 2800, 41, 88),
          (2880, 3280, 48, 91), (3360, 3760, 45, 89)]
    smf.write(os.path.join(tmp, "b.mid"), bs, div, 116)

    def build(name, text):
        p = os.path.join(tmp, name)
        open(p, "w").write(text)
        out = os.path.join(tmp, name + ".build")
        buf = io.StringIO()
        with redirect_stdout(buf):
            files = chartc.compile_chart(p, out)
        return out, buf.getvalue(), files

    HEAD = ('title: G\nkey: F\nmeter: 4/4\ntempo: 116\nfeel: shuffle\n\n'
            'band:\n  tenor = tenor sax, demo "t.mid"\n'
            '  bass = electric bass, demo "b.mid"\n  drums\n\n')
    out, log, files = build(
        "ph.chart", HEAD +
        'section A, 2 bars\n  chords: F7, Bb7\n'
        '  tenor: from demo bars 1-2, legato, straight\n'
        '  bass: from demo bars 1-2, ghosts, straight\n  drums: groove\n'
        'section B, 2 bars, label "no swing"\n  feel: straight ballad\n'
        '  chords: F7, Bb7\n  drums: groove\n')
    check("phrasing chart: measures sum", not verify_measures(files))

    xml = open(os.path.join(out, "G — tenor.musicxml")).read()
    starts = xml.count('<slur number="1" type="start"/>')
    stops = xml.count('<slur number="1" type="stop"/>')
    check("legato slurs the played phrases, breaths and repeats break",
          starts == 2 and stops == 2, f"{starts} starts, {stops} stops")
    check("straight keeps a played quarter a quarter under the hint",
          "<type>quarter</type>" in xml)
    check("the slur run is spoken",
          "slurred phrase(s) from the played legato" in log)

    xml = open(os.path.join(out, "G — bass.musicxml")).read()
    check("a ghost prints in parentheses",
          xml.count('parentheses="yes"') == 1)
    check("the ghost bars are named", "ghost notes in parentheses" in log)

    listen = open(os.path.join(out, "G — for listening.musicxml")).read()
    check("the listening document swings, on a hidden words element",
          '<words print-object="no">Swing</words>' in listen
          and '<first>2</first><second>1</second>' in listen)
    check("a straight section turns the swing off",
          "<straight/>" in listen)
    score = open(os.path.join(out, "G — score.musicxml")).read()
    check("the page never carries the swing element",
          "<swing>" not in score and "<swing>" not in xml)

    # opt-in: without the words, no slurs, no ghosts, no findings
    out, log, files = build(
        "plain.chart", HEAD +
        'section A, 2 bars\n  chords: F7, Bb7\n'
        '  tenor: from demo bars 1-2\n'
        '  bass: from demo bars 1-2\n  drums: groove\n')
    xml = open(os.path.join(out, "G — tenor.musicxml")).read()
    bxml = open(os.path.join(out, "G — bass.musicxml")).read()
    check("phrasing never happens unasked",
          "<slur" not in xml and "parentheses" not in bxml
          and "slurred" not in log and "ghost" not in log)

    # asked with nothing to find: a finding, never a silent no-op
    stac = [(0, 120, 65, 86), (480, 600, 68, 86), (960, 1080, 70, 86),
            (1440, 1560, 72, 86)]
    smf.write(os.path.join(tmp, "s.mid"), stac, div, 116)
    out, log, files = build(
        "dry.chart", 'title: D\nkey: F\nmeter: 4/4\ntempo: 116\n\n'
        'band:\n  tenor = tenor sax, demo "s.mid"\n  drums\n\n'
        'section A, 1 bars\n  chords: F7\n'
        '  tenor: from demo bars 1-1, legato, ghosts\n  drums: groove\n')
    check("legato asked on detached playing says so",
          "legato asked, but the playing is detached" in log, log[:200])
    check("ghosts asked with none found says so",
          "ghosts asked, but no note" in log)

    # a comma inside quoted directive text is text, not a separator
    out, log, files = build(
        "comma.chart", 'title: C\nkey: F\nmeter: 4/4\ntempo: 116\n\n'
        'band:\n  drums\n\nsection A, 1 bars\n  chords: F7\n'
        '  drums: groove "shuffle, ride heavy"\n')
    check("a comma inside quoted groove words parses",
          'shuffle, ride heavy' in
          open(os.path.join(out, "C — drums.musicxml")).read())

    shutil.rmtree(tmp, ignore_errors=True)


def check_audio():
    """
    Copyist's own ears: the listening document synthesized without
    MuseScore. The parser reads only what our emitter writes, so these
    hold the two ends of that contract together — and the schedule must
    agree with chartc.seconds_before, two independent walks of the same
    meter and tempo maps.
    """
    import cmath
    import wave as wavemod
    import chartaudio
    import chartc
    import smf
    tmp = tempfile.mkdtemp()

    div = 480
    # one bar: concert A4 half tied into bar 2, then A5 quarter
    notes = [(0, 1920 * 2 - 40, 69, 90), (1920 * 2, 1920 * 2 + 440, 81, 90)]
    smf.write(os.path.join(tmp, "a.mid"), notes, div, 120)
    open(os.path.join(tmp, "a.chart"), "w").write(
        "title: A\nkey: C\nmeter: 4/4\ntempo: 120\n\nband:\n"
        '  flute, demo "a.mid"\n  drums\n\n'
        "section A, 3 bars\n  chords: C, C, C\n"
        "  flute: from demo bars 1-3\n  drums: groove\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "a.chart"),
                             os.path.join(tmp, "ab"))
    listen = os.path.join(tmp, "ab", "A — for listening.musicxml")
    plan = chartaudio.parse_score(listen)
    fl = next(p for p in plan['parts'] if p['name'] == 'flute')
    check("a tie across the barline is one event",
          len(fl['events']) == 2 and abs(fl['events'][0][1] - 8.0) < 1e-9,
          f"got {fl['events']}")
    check("groove parts are silent in the listen",
          not next(p for p in plan['parts']
                   if p['name'] == 'drums')['events'])

    wav = os.path.join(tmp, "a.wav")
    secs, n_parts, n_notes = chartaudio.render(listen, wav)
    # the tied note spans bars 1-2 (8 quarters), the last quarter ends
    # at 4.5s, and the render adds its 1.5s tail
    check("the render ends after the last release plus the tail",
          abs(secs - 6.0) < 0.6, f"got {secs}")
    # the held A4 must actually BE 440 Hz: a small DFT over one second
    with wavemod.open(wav) as w:
        raw = w.readframes(int(1.0 * chartaudio.SR))
    import struct as st
    mono = [st.unpack_from('<h', raw, 4 * i)[0]
            for i in range(int(0.8 * chartaudio.SR))]
    off = int(0.2 * chartaudio.SR)
    mono = mono[off:]
    n = len(mono)
    best = max(range(400, 481, 5),
               key=lambda f: abs(sum(
                   m * cmath.exp(-2j * cmath.pi * f * i / chartaudio.SR)
                   for i, m in enumerate(mono[:8000]))))
    check(f"the held concert A renders at 440 Hz (peak at {best})",
          435 <= best <= 445)

    # swing warps the schedule; a repeat doubles it
    notes = [(0, 420, 60, 90), (480, 660, 62, 90), (720, 900, 64, 90),
             (960, 1880, 65, 90)]
    smf.write(os.path.join(tmp, "s.mid"), notes, div, 120)
    open(os.path.join(tmp, "s.chart"), "w").write(
        "title: S\nkey: C\nmeter: 4/4\ntempo: 120\nfeel: shuffle\n\n"
        'band:\n  flute, demo "s.mid"\n  drums\n\n'
        "section A, 1 bars, repeat 2x\n  chords: C\n"
        "  flute: from demo bars 1-1, straight\n  drums: groove\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "s.chart"),
                             os.path.join(tmp, "sb"))
    plan = chartaudio.parse_score(
        os.path.join(tmp, "sb", "S — for listening.musicxml"))
    fl = next(p for p in plan['parts'] if p['name'] == 'flute')
    check("a repeated section plays twice", len(fl['events']) == 8,
          f"got {len(fl['events'])}")
    sched = chartaudio._seconds(plan)[0]
    beat = 0.5
    fr = sorted({round((a % beat) / beat, 2) for a, _, _, _ in sched
                 if (a % beat) / beat > 0.1})
    check("the swung offbeat plays at two-thirds", fr == [0.67],
          f"got {fr}")

    # two independent walks of the meter and tempo maps must agree
    open(os.path.join(tmp, "m.chart"), "w").write(
        "title: M\nkey: C\nmeter: 4/4\ntempo: 96\n\nband:\n  piano\n\n"
        "section A, 6 bars\n  at bar 3: meter 6/8\n  at bar 3: tempo 64\n"
        "  at bar 5: meter 4/4\n  at bar 5: tempo 88\n  chords: C x6\n"
        "  piano: groove\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "m.chart"),
                             os.path.join(tmp, "mb"))
    chart = chartc.parse_chart(os.path.join(tmp, "m.chart"))
    plan = chartaudio.parse_score(
        os.path.join(tmp, "mb", "M — for listening.musicxml"))
    # bar starts in quarters, walked from the parsed document
    tempos = plan['tempos']
    q_starts = [0.0, 4.0, 8.0, 11.0, 14.0, 18.0]

    def sec_of(q):
        ts = tempos if tempos and tempos[0][0] == 0 else \
            [(0.0, 96.0)] + tempos
        s, pq, bpm = 0.0, 0.0, ts[0][1]
        for at, t in ts:
            if at >= q:
                break
            s += (at - pq) * 60.0 / bpm
            pq, bpm = at, t
        return s + (q - pq) * 60.0 / bpm
    bad = [b for b, q in enumerate(q_starts, 1)
           if abs(sec_of(q) - chartc.seconds_before(chart, b)) > 1e-6]
    check("chartaudio and seconds_before walk the maps identically",
          not bad, f"bars {bad}")

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
    check_poly_charts()
    check_phrasing_charts()
    check_audio()

    run_fixture("two-hand-piano", "C# minor",
                {"clean.mid": "HARD QUANTIZED",
                 "humanized.mid": "QUANTIZED THEN HUMANIZED"})
    run_fixture("spelling-modulation", "Eb major",
                {"clean.mid": "HARD QUANTIZED"})
    run_fixture("small-ensemble", None, {})
    run_fixture("hammond-organ", None, {})

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    sys.exit(1 if failed else 0)
