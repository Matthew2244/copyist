#!/usr/bin/env python3
"""
Corpus regression runner.

Asserts the invariants recorded in each fixture's README. Runs anywhere on
stock Python 3; the round-trip check is skipped when MuseScore is not present,
because it needs `mscore` to render MusicXML back to MIDI.

Usage:  python3 test_corpus.py
"""

import io
import re
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
          multi == ["1", "3", "5"], f"got {multi}")
    # each change starts its own counted rest, signature above the
    # count — the working-book grouping (Victory's intro, 2026-09-22)

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
          and re.search(r'<first>\d+</first><second>\d+</second>',
                        listen))
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
        "  flute: from demo bars 1-3\n  drums: groove\n"
        "  ending: as written\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "a.chart"),
                             os.path.join(tmp, "ab"))
    listen = os.path.join(tmp, "ab", "A — for listening.musicxml")
    plan = chartaudio.parse_score(listen)
    fl = next(p for p in plan['parts'] if p['name'] == 'flute')
    check("a tie across the barline is one event",
          len(fl['events']) == 2 and abs(fl['events'][0][1] - 8.0) < 1e-9,
          f"got {fl['events']}")
    # the 2026-09-20 ruling: groove bars realize into a real rhythm
    # section in the LISTENING document (the pages keep their slashes)
    drum_ev = next(p for p in plan['parts']
                   if p['name'] == 'drums')['events']
    check("groove parts play a realized rhythm section in the listen",
          len(drum_ev) >= 6, f"got {len(drum_ev)} events")
    check("the realized drums stay inside the chart",
          max(e[0] + e[1] for e in drum_ev) <= 12.0 + 1e-6)
    page = open(os.path.join(tmp, "ab", "A — drums.musicxml"),
                encoding="utf-8").read()
    check("the drums PAGE still prints slashes, not the realization",
          '<notehead>slash</notehead>' in page
          and '<unpitched><display-step>F</display-step>'
              '<display-octave>5' not in page)

    wav = os.path.join(tmp, "a.wav")
    secs, n_parts, n_notes, _ = chartaudio.render(listen, wav)
    # the realized drums play to the end of bar 3 (12 quarters, 6.0s
    # at 120), and the render adds its 1.5s tail
    check("the render ends after the last release plus the tail",
          abs(secs - 7.5) < 0.6, f"got {secs}")
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
    fr = sorted({round((a % beat) / beat, 2) for a, _, _, _, _ in sched
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


def check_voltas():
    """
    CHART-FORMAT.md 3.6 — volta endings. The declared section length is
    one pass (the body plus one ending), the page carries the body and
    every ending with the right brackets and repeats, and Copyist's own
    player takes ending K on pass K — including the trim math, which is
    the player's walk, not printed-bar arithmetic.
    """
    import re
    import chartaudio
    import chartc
    from chart import verify_measures
    tmp = tempfile.mkdtemp()

    HEAD = ("title: V\nkey: C\nmeter: 4/4\ntempo: 120\n\n"
            "band:\n  piano\n  trumpet\n\n")
    p = os.path.join(tmp, "v.chart")
    open(p, "w").write(HEAD +
        "section A, 4 bars, repeat 2x\n  chords: C, F\n"
        "  ending 1, 2 bars: chords: G7, C\n"
        "  ending 2, 2 bars: chords: G7 C@3, C\n"
        "  piano: groove\n  trumpet: tacet\n"
        "section B, 2 bars\n  chords: F, C\n  piano: groove\n")
    out = os.path.join(tmp, "vb")
    with redirect_stdout(io.StringIO()):
        files = chartc.compile_chart(p, out)
    check("volta chart: measures sum", not verify_measures(files))
    xml = open(os.path.join(out, "V — piano.musicxml")).read()
    marks = {num: re.findall(r'<ending [^/]*/>|<repeat [^/]*/>', m)
             for num, m in re.findall(
                 r'<measure [^>]*number="(\d+)"[^>]*>(.*?)</measure>',
                 xml, re.S) if '<ending' in m or '<repeat' in m}
    check("the page carries the brackets and repeats where a player looks",
          marks == {'1': ['<repeat direction="forward"/>'],
                    '3': ['<ending number="1" type="start"/>'],
                    '4': ['<ending number="1" type="stop"/>',
                          '<repeat direction="backward"/>'],
                    '5': ['<ending number="2" type="start"/>'],
                    '6': ['<ending number="2" type="discontinue"/>']},
          f"got {marks}")

    listen = os.path.join(out, "V — for listening.musicxml")
    plan = chartaudio.parse_score(listen)
    check("the player takes ending two on pass two",
          plan['bars'] == {1: 0.0, 2: 4.0, 3: 8.0, 4: 12.0,
                           5: 24.0, 6: 28.0, 7: 32.0, 8: 36.0},
          f"got {plan['bars']}")
    check("the trim math is the player's walk",
          abs(chartaudio.first_bar_seconds(listen, 7) - 16.0) < 1e-9)

    for name, text, want in (
        ("r1", HEAD + "section A, 4 bars\n  chords: C, F\n"
         "  ending 1, 2 bars: chords: G7, C\n  piano: groove\n",
         "no repeat"),
        ("r2", HEAD + "section A, 4 bars, repeat 3x\n  chords: C, F\n"
         "  ending 1, 2 bars: chords: G7, C\n"
         "  ending 2, 2 bars: chords: G7, C\n  piano: groove\n",
         "numbered from 1"),
        ("r3", HEAD + "section A, 4 bars, repeat 2x\n  chords: C, F\n"
         "  ending 1, 2 bars: chords: G7, C\n"
         "  ending 2, 1 bars: chords: C\n  piano: groove\n",
         "same length"),
        ("r4", HEAD + "section A, 4 bars, repeat 2x\n  chords: C, F, G\n"
         "  ending 1, 2 bars: chords: G7, C\n"
         "  ending 2, 2 bars: chords: G7, C\n  piano: groove\n",
         "chords cover 3"),
    ):
        pp = os.path.join(tmp, name + ".chart")
        open(pp, "w").write(text)
        try:
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(pp, os.path.join(tmp, "x"))
            got = ""
        except SystemExit as e:
            got = str(e)
        check(f"refused with '{want}'", want in got, f"got: {got}")

    import chartread
    chart = chartc.parse_chart(p)
    sec = chart['sections'][0]
    heading = chartread.section_heading(sec)
    changes = chartread.say_changes(sec)
    check("the read speaks passes and endings",
          "4 bars a pass, with 2 endings" in heading
          and "First ending: G seven; C." in changes
          and "Second ending:" in changes,
          f"got: {heading} / {changes}")

    shutil.rmtree(tmp, ignore_errors=True)


def check_figures():
    """
    CHART-FORMAT.md 3.4 — named figures: defined once, placed by name.
    A from-midi figure rides the demo pipeline with the part's own
    transposition; a from-xml figure lifts written bars verbatim and
    carries its source's divisions per measure, restating the part's own
    after. Unused definitions are a finding; every mistake is a sentence.
    """
    import re
    import chartc
    import smf
    from chart import verify_measures
    tmp = tempfile.mkdtemp()

    div = 480
    notes = [(i * div, i * div + 400, 60 + i, 90) for i in range(8)]
    smf.write(os.path.join(tmp, "d.mid"), notes, div, 100)
    open(os.path.join(tmp, "lick.musicxml"), "w").write(
        '<?xml version="1.0"?>\n<score-partwise version="3.1">\n'
        '  <part-list>\n    <score-part id="P1">'
        '<part-name>Lick</part-name></score-part>\n  </part-list>\n'
        '  <part id="P1">\n    <measure number="1">\n'
        '      <attributes><divisions>8</divisions>'
        '<key><fifths>0</fifths></key>'
        '<time><beats>4</beats><beat-type>4</beat-type></time>'
        '<clef><sign>G</sign><line>2</line></clef></attributes>\n'
        '      <note><pitch><step>C</step><octave>5</octave></pitch>'
        '<duration>16</duration><voice>1</voice><type>half</type></note>\n'
        '      <note><pitch><step>G</step><octave>5</octave></pitch>'
        '<duration>16</duration><voice>1</voice><type>half</type></note>\n'
        '    </measure>\n  </part>\n</score-partwise>\n')

    HEAD = ('title: F\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
            'band:\n  trumpet\n  flute\n  piano\n\n'
            'figure lift, 1 bars:\n'
            '  from xml "lick.musicxml", part "Lick", bars 1-1\n'
            'figure line, 2 bars:\n'
            '  from midi "d.mid", bars 1-2\n'
            'figure inline lick, 1 bars:\n'
            '  notes: rest e, C5 e, A4 q, triplet( F4 e, A4 e, C5 e ), '
            'F4 q\n'
            'figure spare, 2 bars:\n'
            '  from midi "d.mid", bars 1-2\n\n')
    p = os.path.join(tmp, "f.chart")
    open(p, "w").write(HEAD +
        'section A, 4 bars\n  chords: C, F, G, C\n'
        '  trumpet: figure line, figure inline lick at bar 4, legato\n'
        '  flute: figure lift at bar 3\n'
        '  piano: groove\n')
    out = os.path.join(tmp, "fb")
    buf = io.StringIO()
    with redirect_stdout(buf):
        files = chartc.compile_chart(p, out)
    log = buf.getvalue()
    check("figure chart: measures sum through the divisions change",
          not verify_measures(files))
    xml = open(os.path.join(out, "F — flute.musicxml")).read()
    bars = dict(re.findall(r'<measure [^>]*number="(\d+)"[^>]*>(.*?)'
                           r'</measure>', xml, re.S))
    check("the lifted bar carries its source divisions",
          '<divisions>8</divisions>' in bars['3']
          and '<step>C</step>' in bars['3'])
    check("the bar after the figure restates the part's own divisions",
          '<divisions>24</divisions>' in bars['4'])
    xml = open(os.path.join(out, "F — trumpet.musicxml")).read()
    check("a midi figure lands written for its part",
          '<step>D</step>' in xml)          # concert C, trumpet up a tone
    check("an unplaced figure is a finding",
          "'spare' is defined and never used" in log)
    bars = dict(re.findall(r'<measure [^>]*number="(\d+)"[^>]*>(.*?)'
                           r'</measure>', xml, re.S))
    check("an inline figure prints with tuplet math and the slur asked",
          '<actual-notes>3</actual-notes>' in bars['4']
          and 'slur number="1" type="start"' in bars['4'])

    for name, text, want in (
        ("r1", HEAD + "section A, 4 bars\n  chords: C, F, G, C\n"
         "  trumpet: figure nothing\n  piano: groove\n",
         "is not defined"),
        ("r2", 'title: X\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
         'band:\n  piano\n\nfigure short, 3 bars:\n'
         '  from midi "d.mid", bars 1-2\n\n'
         'section A, 2 bars\n  chords: C, F\n  piano: groove\n',
         "declares 3 bars but references 2"),
        ("r3", 'title: X\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
         'band:\n  piano\n\nfigure quick, 3 beats:\n'
         '  from midi "d.mid", bars 1-1\n\n'
         'section A, 2 bars\n  chords: C, F\n  piano: groove\n',
         "inline"),
        ("r5", 'title: X\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
         'band:\n  trumpet\n  piano\n\nfigure lick, 1 bars:\n'
         '  notes: C5 q, D5 q, E5 q\n\n'
         'section A, 2 bars\n  chords: C, F\n'
         '  trumpet: figure lick\n  piano: groove\n',
         "fill 3 beats but 1 bar(s) of 4/4 hold 4"),
        ("r6", 'title: X\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
         'band:\n  piano\n\nfigure lick, 1 bars:\n'
         '  notes: C5 q, triplet( D5 e, E5 q, F5 e )\n\n'
         'section A, 2 bars\n  chords: C, F\n  piano: groove\n',
         "one kind per group"),
        ("r4", HEAD.replace('part "Lick"', 'part "Nobody"') +
         "section A, 4 bars\n  chords: C, F, G, C\n"
         "  flute: figure lift\n  piano: groove\n",
         "is not a part of"),
    ):
        pp = os.path.join(tmp, name + ".chart")
        open(pp, "w").write(text)
        try:
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(pp, os.path.join(tmp, "x"))
            got = ""
        except SystemExit as e:
            got = str(e)
        check(f"refused with '{want}'", want in got, f"got: {got}")

    shutil.rmtree(tmp, ignore_errors=True)


def check_lyrics():
    """
    CHART-FORMAT.md 3.4 lyrics: hyphens split syllables, underscores hold
    a melisma, and the alignment is one syllable per sung note or a
    refusal carrying both counts — misaligned words are the one failure
    a singer cannot proofread past.
    """
    import re
    import chartc
    import chartdemo
    from chart import verify_measures
    tmp = tempfile.mkdtemp()

    phrases, autos = chartdemo.parse_lyrics("To-mor-row, to-mor-row_ _")
    toks = phrases[0]
    check("hyphens, punctuation and melisma parse",
          [t[:2] if t else None for t in toks] ==
          [['begin', 'To'], ['middle', 'mor'], ['end', 'row,'],
           ['begin', 'to'], ['middle', 'mor'], ['end', 'row'],
           None, None] and not autos, f"got {toks}")
    phrases, autos = chartdemo.parse_lyrics("windows shine / uptown")
    check("unhyphenated words split themselves and say so",
          [len(p) for p in phrases] == [3, 2]
          and autos == ['win-dows', 'up-town'],
          f"got {phrases} / {autos}")

    HEAD = ('title: L\nkey: C\nmeter: 4/4\ntempo: 90\n\n'
            'band:\n  singer = voice\n  piano\n\n'
            'figure hook, 1 bars:\n'
            '  notes: C5 q, D5 q, E5 q, G5 q\n'
            '  lyrics: Morn-ing train_\n\n')
    p = os.path.join(tmp, "l.chart")
    open(p, "w").write(HEAD +
        'section A, 2 bars\n  chords: C, G7\n'
        '  singer: figure hook\n  piano: groove\n')
    out = os.path.join(tmp, "lb")
    with redirect_stdout(io.StringIO()):
        files = chartc.compile_chart(p, out)
    check("a sung figure sums", not verify_measures(files))
    xml = open(os.path.join(out, "L — singer.musicxml")).read()
    lyr = re.findall(r'<lyric>(.*?)</lyric>', xml, re.S)
    check("syllabics and the melisma extend land on the page",
          len(lyr) == 3
          and '<syllabic>begin</syllabic><text>Morn</text>' in lyr[0]
          and '<syllabic>end</syllabic><text>ing</text>' in lyr[1]
          and '<text>train</text><extend/>' in lyr[2], f"got {lyr}")

    open(os.path.join(tmp, "bad.chart"), "w").write(HEAD.replace(
        "Morn-ing train_", "Morn-ing train") +
        'section A, 2 bars\n  chords: C, G7\n'
        '  singer: figure hook\n  piano: groove\n')
    try:
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "bad.chart"),
                                 os.path.join(tmp, "x"))
        got = ""
    except SystemExit as e:
        got = str(e)
    check("a syllable count that misses refuses with both counts",
          "sings 4 note(s)" in got and "3 syllable(s)" in got,
          f"got: {got}")

    # phrase-anchored words: the refusal names the phrase and its bar
    open(os.path.join(tmp, "ph.chart"), "w").write(
        'title: P\nkey: C\nmeter: 4/4\ntempo: 90\n\n'
        'band:\n  singer = voice\n  piano\n\n'
        'figure tune, 2 bars:\n'
        '  notes: C5 q, D5 q, rest h, E5 q, G5 q, rest h\n'
        '  lyrics: morning train / gone now\n\n'
        'section A, 2 bars\n  chords: C, G7\n'
        '  singer: figure tune\n  piano: groove\n')
    try:
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "ph.chart"),
                                 os.path.join(tmp, "x"))
        got = ""
    except SystemExit as e:
        got = str(e)
    check("a phrase mismatch names the phrase and the bar",
          "the phrase at bar 1 has 2 note(s)" in got
          and "'mor-ning train'" in got, f"got: {got}")
    open(os.path.join(tmp, "ph2.chart"), "w").write(
        'title: P\nkey: C\nmeter: 4/4\ntempo: 90\n\n'
        'band:\n  singer = voice\n  piano\n\n'
        'figure tune, 2 bars:\n'
        '  notes: C5 q, D5 q, rest h, E5 q, G5 q, rest h\n'
        '  lyrics: sunrise / gone_\n\n'
        'section A, 2 bars\n  chords: C, G7\n'
        '  singer: figure tune\n  piano: groove\n')
    out2 = os.path.join(tmp, "phb")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(os.path.join(tmp, "ph2.chart"), out2)
    xml = open(os.path.join(out2, "P — singer.musicxml")).read()
    check("phrase-anchored words land, melisma included",
          "<text>gone</text><extend/>" in xml
          and "<text>sun</text>" in xml, "xml missed")
    check("auto-splits are reported for the writer's veto",
          "I split these words myself — sun-rise" in buf.getvalue(),
          f"log: {buf.getvalue()[:200]}")

    shutil.rmtree(tmp, ignore_errors=True)


def check_directive_family():
    """
    CHART-FORMAT.md 3.6, the last of the directive table: `double` joins
    another part's resolved line re-rendered for the TARGET's
    transposition; `cue` prints it small, labelled, and never played —
    honored by Copyist's own player, which MuseScore never did; `build:`
    fans "+who" entrance cues to every part; `on pass N:` tags its words;
    `as demo` is symbols-level slashes wearing the words.
    """
    import re
    import chartaudio
    import chartc
    import smf
    from chart import verify_measures
    tmp = tempfile.mkdtemp()
    div = 480
    notes = [(i * div, i * div + 400, 60 + i, 90) for i in range(8)]
    smf.write(os.path.join(tmp, "d.mid"), notes, div, 100)
    open(os.path.join(tmp, "f.chart"), "w").write(
        'title: D\nkey: C\nmeter: 4/4\ntempo: 100\n'
        'demo: d.mid\n\nband:\n  trumpet\n  alto = alto sax\n'
        '  flute\n  piano\n\n'
        'section A, 4 bars, repeat 2x\n  chords: C, F, G, C\n'
        '  trumpet: from demo bars 1-2, on pass 2: mute cup\n'
        '  alto: double trumpet\n  flute: cue trumpet\n'
        '  piano: as demo\n  build: add alto at 3\n')
    out = os.path.join(tmp, "b")
    with redirect_stdout(io.StringIO()):
        files = chartc.compile_chart(os.path.join(tmp, "f.chart"), out)
    check("directive family: measures sum", not verify_measures(files))
    alto = open(os.path.join(out, "D — alto.musicxml")).read()
    flute = open(os.path.join(out, "D — flute.musicxml")).read()
    tpt = open(os.path.join(out, "D — trumpet.musicxml")).read()
    piano = open(os.path.join(out, "D — piano.musicxml")).read()
    check("a double re-renders for the target's transposition",
          '<step>A</step>' in alto and '<cue/>' not in alto)
    check("a cue prints small, labelled, and unplayed",
          flute.count('<cue/>') > 0 and '(trumpet cue)' in flute
          and '<tie ' not in flute)
    plan = chartaudio.parse_score(
        os.path.join(out, "D — for listening.musicxml"))
    fl = next(p for p in plan['parts'] if p['name'] == 'flute')
    al = next(p for p in plan['parts'] if p['name'] == 'alto')
    check("the player skips the cue and plays the double",
          not fl['events'] and al['events'])
    check("on pass tags its words", 'cup mute (2x only)' in tpt)
    check("as demo wears the words over slashes", 'as demo' in piano)
    check("build fans entrance cues to the band",
          all('+alto' in x for x in (alto, flute, tpt, piano)))

    for name, text, want in (
        ("r1", 'title: X\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
         'band:\n  piano\n  flute\n\n'
         'section A, 2 bars\n  chords: C, F\n'
         '  flute: double piano\n  piano: groove\n',
         "has no played or figured line"),
        ("r2", 'title: X\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
         'band:\n  piano\n  flute\n\n'
         'section A, 2 bars\n  chords: C, F\n'
         '  flute: on pass 2: mute cup\n  piano: groove\n',
         "only means something in a repeated section"),
        ("r3", 'title: X\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
         'band:\n  piano\n\n'
         'section A, 2 bars\n  chords: C, F\n  piano: groove\n'
         '  build: add nobody at 1\n',
         "not a band part or group"),
    ):
        pp = os.path.join(tmp, name + ".chart")
        open(pp, "w").write(text)
        try:
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(pp, os.path.join(tmp, "x"))
            got = ""
        except SystemExit as e:
            got = str(e)
        check(f"refused with '{want}'", want in got, f"got: {got}")

    shutil.rmtree(tmp, ignore_errors=True)


def check_build_entrance():
    """
    `build: add bass at 5` is an entrance: the bass rests bars 1-4 and
    comes in at 5 — on the page, in the listen, in the findings and in
    the read-aloud. It used to print the +bass cue over slashes that
    started at bar 1, and the listen walked a bass line from the top.
    """
    import re
    import subprocess
    import chartaudio
    import chartc
    tmp = tempfile.mkdtemp()
    cp = os.path.join(tmp, "e.chart")
    open(cp, "w").write(
        'title: E\nkey: C\nmeter: 4/4\ntempo: 120\nfeel: swing\n\n'
        'band:\n  piano\n  bass\n  drums\n  trumpet\n\n'
        'section A, 8 bars\n  chords: C7 x4, F7 x4\n'
        '  build: add bass at 5, add trumpet at 7\n'
        '  at bar 3: text "Swing--"\n')
    out = os.path.join(tmp, "b")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(cp, out)
    bass = open(os.path.join(out, "E — bass.musicxml")).read()
    bars = re.findall(r'<measure [^>]*>(.*?)</measure>', bass, re.S)
    check("an entrance rests the bars before it",
          len(bars) == 8 and all('<rest' in b and 'slash' not in b
                                 for b in bars[:4]), str(len(bars)))
    check("and slashes from the entrance on",
          all('slash' in b for b in bars[4:]))
    check("the part still carries its own +cue", '+bass' in bass)
    piano = open(os.path.join(out, "E — piano.musicxml")).read()
    pbars = re.findall(r'<measure [^>]*>(.*?)</measure>', piano, re.S)
    check("a part not named keeps its slashes from bar 1",
          'slash' in pbars[0])
    texts = {}
    for name in ("piano", "bass", "drums", "trumpet"):
        x = open(os.path.join(out, f"E — {name}.musicxml")).read()
        texts[name] = re.findall(r'<words[^>]*>([^<]*)</words>', x)
    check("timed text reaches every part, and nothing stray does",
          all(t.count('Swing--') == 1 and 'bass' not in t
              and 'trumpet' not in t for t in texts.values()),
          str(texts))
    plan = chartaudio.parse_score(
        os.path.join(out, "E — for listening.musicxml"))
    bs = next(p for p in plan['parts'] if p['name'] == 'bass')
    pn = next(p for p in plan['parts'] if p['name'] == 'piano')
    check("the listen's bass waits for bar 5",
          bs['events'] and min(e[0] for e in bs['events']) >= 16,
          str(min(e[0] for e in bs['events']) if bs['events'] else None))
    check("the listen's piano plays from the top",
          pn['events'] and min(e[0] for e in pn['events']) < 4)
    fnd = open(os.path.join(out, "E — findings.txt")).read()
    check("findings name the entrance", 'slashes from bar 5' in fnd, fnd)
    check("an entrance with nothing to play says so",
          'brought in at bar 7, but nothing is written' in fnd, fnd)
    said = subprocess.run(
        [sys.executable, os.path.join(HERE, "chartread.py"), cp,
         "--part", "bass"], capture_output=True, text=True).stdout
    tp = os.path.join(tmp, "t.chart")
    open(tp, "w").write(
        'title: T\nkey: G\nmeter: 4/4\ntempo: 120\n\n'
        'band:\n  piano\n  bass\n\n'
        'section intro, 4 bars\n  chords: Gmaj7, Cmaj7, Gmaj7, D7\n'
        '  bass: tacet\n\n'
        'section A, 4 bars\n  chords: G7 x4\n')
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(tp, os.path.join(tmp, "t"))
    tb = open(os.path.join(tmp, "t", "T — bass.musicxml")).read()
    tbars = re.findall(r'<measure [^>]*>(.*?)</measure>', tb, re.S)
    tpn = open(os.path.join(tmp, "t", "T — piano.musicxml")).read()
    check("a tacet section is rests with no changes over them",
          not any('<harmony' in b for b in tbars[:4])
          and '<harmony' in tbars[4] and '<harmony' in tpn.split(
              '</measure>')[0], str([('<harmony' in b) for b in tbars]))
    check("the read-aloud says when to come in",
          'Bars 1 to 4: rest' in said and 'from bar 5' in said, said)
    shutil.rmtree(tmp, ignore_errors=True)


def check_trills_and_tremolos():
    """
    Trills of every size and tremolos of both kinds, for any instrument
    that can play them: typed (`E5 h tr`, `tr minor 3rd`, `tr to D#5`,
    `trem`, `roll`, `trem to C5`), spoken at the desk, and PLAYED — a
    fast alternation or re-strike in the demo becomes one note with its
    ornament. The page, the read-aloud and the listen agree on the
    exact upper note; a bare `tr` follows the key (E in C is a half
    step), and a transposing part spells its own written target.
    """
    import re
    import chartaudio
    import chartc
    import chartedit
    import chartengrave
    import smf
    tmp = tempfile.mkdtemp()
    cp = os.path.join(tmp, "t.chart")
    open(cp, "w").write(
        'title: T\nkey: C\nmeter: 4/4\ntempo: 80\n\nband:\n'
        '  flute\n  trumpet\n  violin\n\n'
        'figure all, 5 bars:\n'
        '  notes: E5 h tr, D5 h tr, C5 h tr half, C5 h tr whole, '
        'C5 h tr aug 2nd, C5 h tr minor 3rd, C5 h tr major 3rd, '
        'G4 h tr to D#5, C5 h trem, A4 h trem to C5\n\n'
        'section A, 5 bars\n  chords: C x5\n'
        '  flute: figure all\n  trumpet: figure all\n'
        '  violin: figure all\n')
    out = os.path.join(tmp, "b")
    with redirect_stdout(io.StringIO()):
        files = chartc.compile_chart(cp, out)
    from chart import verify_measures
    check("trills and tremolos keep the measures whole",
          not verify_measures(files))

    def orns(name):
        x = open(os.path.join(out, f"T — {name}.musicxml")).read()
        return [re.sub(r'<wavy-line[^>]*/>', '', o) for o in
                re.findall(r'<ornaments>(.*?)</ornaments>', x)]
    fl = orns("flute")
    check("a bare tr follows the key; half, whole and augmented stay "
          "seconds with their accidental",
          fl[:5] == ['<trill-mark/>', '<trill-mark/>',
                     '<trill-mark/><accidental-mark>flat</accidental-mark>',
                     '<trill-mark/>',
                     '<trill-mark/><accidental-mark>sharp'
                     '</accidental-mark>'], str(fl[:5]))
    check("wider trills name their target, spelled as asked",
          fl[5:8] == ['<trill-mark/><other-ornament>(Eb5)'
                      '</other-ornament>',
                      '<trill-mark/><other-ornament>(E5)'
                      '</other-ornament>',
                      '<trill-mark/><other-ornament>(D#5)'
                      '</other-ornament>'], str(fl[5:8]))
    check("tremolo strokes and a fingered tremolo pair",
          '<tremolo type="single">3</tremolo>' in fl
          and '<tremolo type="start">3</tremolo>' in fl
          and '<tremolo type="stop">3</tremolo>' in fl, str(fl[8:]))
    tp = orns("trumpet")
    check("a Bb trumpet spells its own written targets",
          '<trill-mark/><other-ornament>(F5)</other-ornament>' in tp
          and '<trill-mark/><other-ornament>(E#5)</other-ornament>'
          in tp, str(tp))
    plan = chartaudio.parse_score(
        os.path.join(out, "T — for listening.musicxml"))
    for part in plan['parts']:
        steps = [e[4].get('trill_step') for e in part['events']]
        check(f"the {part['name']} plays every trill to its exact note",
              steps == [1, 2, 1, 2, 3, 3, 4, 8, None, 3]
              and part['events'][8][4].get('trem') == 3, str(steps))
    said = subprocess.run(
        [sys.executable, os.path.join(HERE, "chartread.py"), cp,
         "--part", "violin"], capture_output=True, text=True).stdout
    for phrase in ("trill a half step up, to F",
                   "trill a half step up, to D flat",
                   "trill an augmented second up, to D sharp",
                   "trill a minor third up, to E flat",
                   "trill an augmented fifth up, to D sharp",
                   "tremolo", "fingered tremolo with C, a minor third up"):
        check(f"the read-aloud says '{phrase}'", phrase in said, said)
    pdf = os.path.join(tmp, "v.pdf")
    ok, why = chartengrave.engrave(
        os.path.join(out, "T — violin.musicxml"), pdf)
    ms, _ = chartengrave.parse_part(
        open(os.path.join(out, "T — violin.musicxml")).read(),
        re.search(r'<part id="([^"]+)"', open(
            os.path.join(out, "T — violin.musicxml")).read()).group(1))
    check("the page engraves, and bars that differ only in their "
          "trills never print as a repeat sign",
          ok and not any(m.get('simile') for m in ms), str(why))

    # played: a trill, a measured figure that must stay notes, a bowed
    # tremolo and a fingered one, all on the same violin line
    d, n, t32 = 480, [], 60
    for i in range(16):
        n.append((i * t32, i * t32 + 55, 64 if i % 2 == 0 else 65, 90))
    n.append((2 * d, 3 * d - 20, 67, 90))
    b2 = 4 * d
    for i in range(4):
        n.append((b2 + i * 120, b2 + i * 120 + 110,
                  72 if i % 2 == 0 else 74, 90))
    n.append((b2 + d, b2 + 2 * d - 20, 72, 90))
    for i in range(16):
        n.append((b2 + 2 * d + i * t32, b2 + 2 * d + i * t32 + 55, 69, 85))
    b3 = 8 * d
    for i in range(32):
        n.append((b3 + i * t32, b3 + i * t32 + 55,
                  65 if i % 2 == 0 else 72, 80))
    smf.write(os.path.join(tmp, "p.mid"), n, d, 72)
    for word, want in (("", True), (", no trills", False)):
        pc = os.path.join(tmp, "p.chart")
        open(pc, "w").write(
            'title: P\nkey: C\nmeter: 4/4\ntempo: 72\n\nband:\n'
            '  violin, demo "p.mid"\n\nsection A, 3 bars\n'
            f'  chords: C x3\n  violin: from demo bars 1-3{word}\n')
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(pc, os.path.join(tmp, "pb"))
        vx = open(os.path.join(tmp, "pb", "P — violin.musicxml")).read()
        fnd = open(os.path.join(tmp, "pb", "P — findings.txt")).read()
        if want:
            check("a played trill becomes one note with a trill",
                  'a played trill, 16 notes a half step apart' in fnd
                  and vx.count('<trill-mark/>') == 1, fnd)
            check("a played re-strike becomes a tremolo, a wide "
                  "alternation a fingered tremolo",
                  'one note struck 16 times' in fnd
                  and 'two notes a fifth apart' in fnd
                  and '<tremolo type="single">' in vx
                  and '<tremolo type="start">' in vx, fnd)
            check("measured sixteenths stay notes",
                  vx.count('<type>16th</type>') == 4)
        else:
            check("`no trills` keeps the played notes",
                  '<trill-mark' not in vx and '<tremolo' not in vx)

    lx = os.path.join(tmp, "lift.musicxml")
    open(lx, "w").write(
        '<score-partwise><part-list><score-part id="P1"><part-name>cl'
        '</part-name></score-part></part-list><part id="P1">'
        '<measure number="1"><attributes><divisions>256</divisions>'
        '<key><fifths>-2</fifths></key><time><beats>4</beats>'
        '<beat-type>4</beat-type></time><clef><sign>G</sign>'
        '<line>2</line></clef></attributes>'
        '<note><pitch><step>B</step><alter>-1</alter><octave>4</octave>'
        '</pitch><duration>512</duration><voice>1</voice><type>whole'
        '</type><time-modification><actual-notes>2</actual-notes>'
        '<normal-notes>1</normal-notes></time-modification><notations>'
        '<ornaments><tremolo type="start">2</tremolo></ornaments>'
        '</notations></note>'
        '<note><pitch><step>E</step><alter>-1</alter><octave>5</octave>'
        '</pitch><duration>512</duration><voice>1</voice><type>whole'
        '</type><time-modification><actual-notes>2</actual-notes>'
        '<normal-notes>1</normal-notes></time-modification><notations>'
        '<ornaments><tremolo type="stop">2</tremolo></ornaments>'
        '</notations></note></measure>'
        '<measure number="2"><note><pitch><step>D</step><octave>5'
        '</octave></pitch><duration>1024</duration><voice>1</voice>'
        '<type>whole</type><notations><ornaments><trill-mark/>'
        '<wavy-line type="start"/></ornaments></notations></note>'
        '</measure></part></score-partwise>')
    lev = chartaudio.parse_score(lx)['parts'][0]['events']
    check("a lifted fingered tremolo plays as one alternation for "
          "both notes' time",
          len(lev) == 2 and abs(lev[0][1] - 4.0) < 1e-6
          and lev[0][4].get('trill_step') == 5, str(lev))
    check("a lifted bare trill reads the key: D in B-flat trills to "
          "E-flat, a half step",
          lev[1][4].get('trill_step') == 1, str(lev[1]))
    ok, why = chartengrave.engrave(lx, os.path.join(tmp, "l.pdf"))
    check("and the lifted tremolo engraves with no tuplet number",
          ok, str(why))
    check("a drum note off the map finds its nearest neighbour, not a "
          "crash", isinstance(chartaudio.drum_midi('G', 3, 'normal'), int)
          and isinstance(chartaudio.drum_midi('B', 6, 'x', hand=True),
                         int))
    check("the desk hears trills and tremolos spoken",
          chartedit.notes_from_words(
              "e5 half trill, c quarter trill minor third, "
              "a4 half tremolo, g4 half trill to d sharp 5") ==
          "E5 h tr, C5 q tr minor 3rd, A4 h trem, G4 h tr to D#5")
    shutil.rmtree(tmp, ignore_errors=True)


def check_sibelius_style_files():
    """
    Every file in his book is a Sibelius export: pretty-printed, tags
    written `<chord />`, marks carrying attributes, dynamics on their
    own line, chord members with no voice, pedal and 8va directions.
    Each of those once went silently missing from the page or the
    listen (2026-09-27 survey of his 52 files). Pinned here, read the
    way both the engraver and the player read them.
    """
    import re
    import chartaudio
    import chartengrave
    tmp = tempfile.mkdtemp()
    xml = """<?xml version="1.0"?>
<score-partwise><part-list><score-part id="P1"><part-name>Piano</part-name>
</score-part></part-list><part id="P1">
<measure number="1" width="300">
 <attributes><divisions>256</divisions><key><fifths>0</fifths></key>
  <time><beats>4</beats><beat-type>4</beat-type></time>
  <clef number="1" color="#000000">
   <sign>F</sign>
   <line>4</line>
  </clef></attributes>
 <direction placement="below"><direction-type>
  <dynamics default-x="1">
   <sf />
  </dynamics></direction-type></direction>
 <direction><direction-type><pedal type="start" line="no" /></direction-type></direction>
 <note color="#000000"><pitch><step>C</step><octave>3</octave></pitch>
  <duration>256</duration><voice>4</voice><type>quarter</type>
  <notations><tied type="start" orientation="under" />
   <articulations><accent default-x="0" /><staccato default-y="5" /></articulations>
   <arpeggiate /></notations>
  <lyric number="1" default-y="-80"><syllabic>single</syllabic><text>Hey</text></lyric></note>
 <note><chord /><pitch><step>E</step><octave>3</octave></pitch>
  <duration>256</duration><type>quarter</type><notations><arpeggiate /></notations></note>
 <note><chord /><pitch><step>G</step><octave>3</octave></pitch>
  <duration>256</duration><type>quarter</type><notations><arpeggiate /></notations></note>
 <note><pitch><step>C</step><octave>3</octave></pitch>
  <duration>256</duration><voice>4</voice><type>quarter</type>
  <notations><tied type="stop" orientation="under" /></notations></note>
 <direction><direction-type><octave-shift type="down" size="8" number="1" /></direction-type></direction>
 <note><pitch><step>C</step><octave>5</octave></pitch>
  <duration>256</duration><voice>4</voice><type>quarter</type><dot /></note>
 <direction><direction-type><octave-shift type="stop" size="8" number="1" /></direction-type></direction>
 <note><pitch><step>D</step><octave>5</octave></pitch>
  <duration>256</duration><voice>4</voice><type>quarter</type></note>
</measure></part></score-partwise>"""
    xp = os.path.join(tmp, "sib.musicxml")
    open(xp, "w").write(xml)
    body = open(xp).read()
    ms, why = chartengrave.parse_part(body, "P1")
    evs = ms[0]['events']
    first = evs[0][1]
    check("a chord member with no voice joins the note before it",
          len(first) == 3 and first[0].arp, str([len(e[1]) for e in evs]))
    check("marks with attributes all read, stacked",
          first[0].marks == ['accent', 'staccato'], str(first[0].marks))
    check("ties, dots and lyrics with attributes read",
          first[0].tie_start and evs[1][1][0].tie_stop
          and evs[2][1][0].dots == 1 and first[0].lyric
          and first[0].lyric[1] == 'Hey')
    check("the clef with a colour and line breaks reads as bass",
          ms[0]['state']['clefs'][1] == 'F')
    check("a pretty-printed dynamic reads", ms[0]['dyn'] == [(0, 'sf')],
          str(ms[0]['dyn']))
    check("under an 8va the head sits an octave down, and the stop "
          "still covers the note at its own position",
          evs[2][1][0].octave == 4 and evs[2][1][0].ott == '8va'
          and evs[3][1][0].octave == 4 and evs[3][1][0].ott,
          str([(e[1][0].octave, e[1][0].ott) for e in evs]))
    check("pedal marks read", ms[0]['pedals'] == [(0, 'start')])
    ok, why = chartengrave.engrave(xp, os.path.join(tmp, "s.pdf"))
    check("and the whole Sibelius-style page engraves", ok, str(why))
    plan = chartaudio.parse_score(xp)
    ev = plan['parts'][0]['events']
    check("the player hears the chord together, not in a row",
          sorted(round(e[0], 2) for e in ev[:3]) == [0.0, 0.0, 0.0],
          str([(round(e[0], 2), e[2]) for e in ev]))
    check("an sf with no playback value lands as an accent",
          ev[0][4].get('acc'))
    check("marks with attributes perform",
          ev[0][4].get('stac'))
    check("the sustain pedal holds what it catches",
          all(e[4].get('ped') and abs(e[0] + e[1] - 4.0) < 1e-6
              for e in ev[:-1]), str([(e[0], e[1]) for e in ev]))
    shutil.rmtree(tmp, ignore_errors=True)


def check_score_import():
    """
    `chart import` turns a score into a chart that compiles on the first
    try (27 of 27 of his book, 25 of 25 Sibelius examples, 2026-09-27).
    Pinned here on one synthetic score carrying every trap those files
    taught: an alto's written key is not the chart's key, "Alto" alone
    is a saxophone by its transposition, chord text beats chord kind,
    a short first bar is a pickup whatever it is numbered, the
    numbering may jump, two versions of one tune never overwrite, and
    what cannot be read is refused in one sentence.
    """
    import zipfile
    import chartimport
    from chart import verify_measures
    import chartc
    tmp = tempfile.mkdtemp()

    def bar(num, body, attrs=''):
        return f'<measure number="{num}">{attrs}{body}</measure>'
    whole = ('<note><pitch><step>C</step><octave>5</octave></pitch>'
             '<duration>4</duration><voice>1</voice><type>whole</type>'
             '</note>')
    pick = ('<note><pitch><step>G</step><octave>4</octave></pitch>'
            '<duration>1</duration><voice>1</voice><type>quarter</type>'
            '</note>')

    def harm(step, kind, text='', alter=None, beat_off=0):
        return ('<harmony><root><root-step>' + step + '</root-step>'
                + (f'<root-alter>{alter}</root-alter>' if alter else '')
                + '</root><kind' + (f' text="{text}"' if text else '')
                + f'>{kind}</kind>'
                + (f'<offset>{beat_off}</offset>' if beat_off else '')
                + '</harmony>')
    att = lambda fifths, tr='': (
        '<attributes><divisions>1</divisions><key><fifths>' + str(fifths)
        + '</fifths></key><time><beats>4</beats><beat-type>4</beat-type>'
        '</time><clef><sign>G</sign><line>2</line></clef>' + tr
        + '</attributes>')
    reh = lambda t: ('<direction><direction-type><rehearsal>' + t
                     + '</rehearsal></direction-type></direction>')
    nums = ['1', '2', '3', '4', '5', '9', '10']
    piano = [bar(nums[0], pick, att(-1))]
    alto = [bar(nums[0], pick, att(2, '<transpose><diatonic>-5'
                                 '</diatonic><chromatic>-9</chromatic>'
                                 '</transpose>'))]
    for k, n in enumerate(nums[1:]):
        h = (harm('F', 'dominant') if k == 0 else
             harm('B', 'minor-seventh', 'm7b5', alter=-1)
             + harm('E', 'dominant', '7#9', beat_off=2)
             if k == 1 else '')
        mark = reh('A') if k == 0 else reh('B') if k == 3 else ''
        piano.append(bar(n, mark + h + whole))
        alto.append(bar(n, mark + whole))
    xml = ('<?xml version="1.0"?><score-partwise><work><work-title>'
           'Test &amp; Tune</work-title></work><identification><creator '
           'type="composer">Matthew Whitaker\narr. Somebody</creator>'
           '</identification><part-list><score-part id="P1"><part-name>'
           'Alto</part-name></score-part><score-part id="P2"><part-name>'
           'Piano</part-name></score-part></part-list>'
           '<part id="P1">' + "".join(alto) + '</part>'
           '<part id="P2">' + "".join(piano) + '</part></score-partwise>')
    src = os.path.join(tmp, "Test.musicxml")
    open(src, "w").write(xml)
    out = os.path.join(tmp, "charts")
    chart, find = chartimport.import_file(src, out)
    text = open(chart).read()
    check("the chart's key is concert, not the alto's written D",
          "key: F" in text, text[:400])
    check("a bare 'Alto' is an alto sax, by its transposition",
          "alto = alto sax" in text, text)
    check("titles and credits come in clean",
          "title: Test & Tune" in text
          and "composer: Matthew Whitaker" in text
          and "arranger: Somebody" in text, text[:300])
    check("a short first bar is a pickup, whatever its number",
          "pickup 1 beats, as engraved" in text, text)
    import re as _re
    h = ('<harmony><root><root-step>A</root-step><root-alter>-1'
         '</root-alter></root><kind text="13">dominant-13th</kind>'
         '<degree><degree-value>9</degree-value><degree-alter>-1'
         '</degree-alter><degree-type>alter</degree-type></degree>'
         '</harmony>')
    check("a chord's text keeps the alterations stored beside it "
          "(Ab13 with a flat nine is Ab13b9)",
          chartimport.harmony_symbol(h, []) == 'Ab13b9',
          chartimport.harmony_symbol(h, []))
    check("the chord text wins, and beats land where the score put them",
          "Bbm7b5 E7#9@3" in text, text)
    check("sections cut at the marks and split where numbering jumps",
          "section A, 3 bars" in text and "all: as engraved bars 2-4"
          in text and "as engraved bars 9-10" in text, text)
    files = chartc.compile_chart(chart, os.path.join(tmp, "b"))
    check("and the imported chart compiles with every bar whole",
          files and not verify_measures(files))
    chart2, find2 = chartimport.import_file(src, out)
    check("a second import of the same tune never overwrites the first",
          chart2 != chart and os.path.exists(chart)
          and "already there" in " ".join(find2), str(find2))
    z = os.path.join(tmp, "Zipped.mxl")
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("META-INF/container.xml",
                    '<container><rootfiles><rootfile full-path="s.xml"/>'
                    '</rootfiles></container>')
        zz.writestr("s.xml", xml.replace("Test &amp; Tune", "Zipped"))
    chart3, _ = chartimport.import_file(z, out)
    check("compressed MusicXML comes in the same way",
          os.path.exists(chart3) and "Zipped" in chart3)
    for ext, word in ((".sib", "Sibelius"), (".mp3", "audio"),
                      (".gp5", "Guitar Pro"), (".png", "picture")):
        f = os.path.join(tmp, "x" + ext)
        open(f, "w").write("x")
        try:
            chartimport.import_file(f, out)
            got = ""
        except chartimport.ImportTrouble as e:
            got = str(e)
        check(f"a {ext} file is refused in a sentence naming the way in",
              word in got and "\n" not in got, got)
    # what building his own "Never Be Defeated" from its score taught
    check("'trumpet in bb' finds 'Trumpet in Bb' (transposition words "
          "drop from both sides)",
          chartc.match_part("trumpet in bb", ["Trumpet in Bb", "Alto"])
          == "Trumpet in Bb")
    check("a lifted bar of nothing but rests can join a multirest",
          chartc.lifted_rest('<note default-x="1"><rest/><duration>1024'
                             '</duration><voice>1</voice></note>')
          and not chartc.lifted_rest('<direction><direction-type><words>'
                                     'x</words></direction-type>'
                                     '</direction><note><rest/></note>'))
    import chartengrave as _ce
    def _width(div):
        m = {'multi': 0, 'show': {}, 'chords': [], 'texts': [], 'dyn': [],
             'metronome': None, 'rehearsal': None, 'events': [],
             'state': {'div': div}}
        n = _ce.Note()
        for a in _ce.Note.__slots__:
            setattr(n, a, None)
        n.dur, n.rest, n.ntype, n.dots, n.cue, n.artic = \
            div * 3, True, 'half', 1, False, None
        n.graces, n.marks, n.slash, n.trill_to = [], [], False, None
        n.step, n.octave, n.alter = 'B', 4, 0
        m['events'] = [(0, [n], 1, 1)]
        return _ce.measure_width(m)
    check("a bar's width does not depend on the file's resolution "
          "(256 a quarter spaced ten times too wide)",
          abs(_width(256) - _width(24)) < 1.0, f"{_width(256)} {_width(24)}")
    class _P:
        def __init__(self):
            self.drawn = []
        def tw(self, s_, size, font):
            return 0.55 * size * len(s_)
        def text(self, x, y, s_, size=9, font='H', right=False):
            self.drawn.append((x, s_, size))
    pp = _P()
    _ce.draw_part_name(pp, 42, 100, "Trumpet in Bb")
    check("a long part name wraps inside the margin, 'in Bb' together",
          [d[1] for d in pp.drawn] == ["Trumpet", "in Bb"]
          and all(pp.tw(d[1], d[2], 'H') <= 36 for d in pp.drawn),
          str(pp.drawn))
    midi = os.path.join(tmp, "d.mid")
    open(midi, "wb").write(b"MThd")
    check("a MIDI demo goes to the interview",
          chartimport.import_file(midi, out)[0] == "interview")
    shutil.rmtree(tmp, ignore_errors=True)


def check_text_import():
    """
    Words and chords from any text format: the readers' own self-test,
    then real-shaped files through `chart import` to a chart that
    compiles — a ChordPro song, a chord sheet saved as Word, lyrics in
    a PDF, an ABC reel, a Markdown chart — plus the chords real lead
    sheets use that once got simplified away, and a read-aloud that can
    say any quality the page can print.
    """
    import subprocess as sp
    import textformats
    import chartimport
    import chartread
    import chartc
    from chart import verify_measures
    for name, ok, detail in textformats.selftest():
        check("text: " + name, ok, detail)
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, "out")
    files = {
        "Porch Song.cho": "{title: Porch Song}\n{key: G}\n"
                          "{start_of_chorus}\n[C]Stay a little [G]longer,"
                          " [Am7]let the night go [D9sus]by\n"
                          "{end_of_chorus}\n",
        "Late Train.md": "# Late Train\n\n**Key:** Bb\n\n## Head\n"
                         "| Bb7 | Eb9#11 | Bb7 | Bb7 |\n"
                         "| Eb7 | Eb7 | Bb7 | G7b9b13 |\n"
                         "| Cm13 | F13#9 | Bb7 G7 | Cm7 F7 |\n",
        "Reel.abc": "X:1\nT:Reel\nM:4/4\nL:1/8\nK:D\n"
                    "\"D\"DFAF dFAF|\"G\"G2BG \"D\"FDAF|\n",
        "words.txt": "Rain Walk\n\nWalking through the rain\ncounting "
                     "every light\n\nHold on, hold on\nmorning's coming"
                     "\n\nThe corner store is closing\n\nHold on, hold on"
                     "\nmorning's coming\n",
    }
    for fn, body in files.items():
        open(os.path.join(tmp, fn), "w").write(body)
    have_textutil = os.path.exists("/usr/bin/textutil")
    if have_textutil:
        sp.run(["/usr/bin/textutil", "-convert", "docx", "-output",
                os.path.join(tmp, "Sheet.docx"),
                os.path.join(tmp, "Late Train.md")], capture_output=True)
    made = {}
    for fn in sorted(os.listdir(tmp)):
        if fn == "out" or fn == "words.txt":
            continue
        chart, find = chartimport.import_file(os.path.join(tmp, fn), out)
        made[fn] = chart
        with redirect_stdout(io.StringIO()):
            built = chartc.compile_chart(chart,
                                         os.path.join(tmp, "b", fn))
        check(f"text: {fn} becomes a chart that compiles whole",
              built and not verify_measures(built), str(find))
    late = open(made["Late Train.md"]).read()
    check("text: lead-sheet chords come in as written, not simplified",
          all(c in late for c in ("Eb9#11", "G7b9b13", "Cm13", "F13#9"))
          and "D9sus4" in open(made["Porch Song.cho"]).read(), late)
    # a real iReal quirk: the first title can open with an apostrophe
    # ('S Wonderful) — that once cut a 233-tune link down to nothing
    from urllib.parse import quote as _q
    link = "irealb://" + _q(
        "'S Wonderful=Gershwin George==Medium Swing=Eb=="
        + textformats.IREAL_PREFIX + textformats.ireal_scramble(
            "{*AT44Eb^7XyQ|C-7XyQ|F-7XyQ|Bb7 Z") + "==Jazz=120=3",
        safe='')
    if link:
        songs = textformats.parse_all("see " + link + "' for more")
        check("text: an iReal link survives an apostrophe title",
              len(songs) == 1 and songs[0]['title'].startswith("'S")
              and sum(len(x['bars']) for x in songs[0]['sections']) == 4,
              str([s_['title'] for s_ in songs]))
    check("text: ABC brings its melody as a figure",
          "figure melody" in open(made["Reel.abc"]).read())
    chart, find = chartimport.import_file(os.path.join(tmp, "words.txt"),
                                          out)
    wtext = open(chart).read()
    check("text: words alone wait for their tune, the repeat named "
          "Chorus", "# Chorus:" in wtext and "voice" in wtext
          and any(f.startswith("words only") for f in find), wtext)
    # once the tune has a form, the waiting words move beside it
    wchart = os.path.join(tmp, "w.chart")
    open(wchart, "w").write(
        "title: W\nmeter: 4/4\n\nband:\n  voice\n  piano\n\n"
        "# Verse 1:\n#   first words\n\n# Chorus:\n#   hold on\n\n"
        "# Verse 2:\n#   second words\n\n"
        "section verse, 2 bars\n  chords: C x2\n\n"
        "section chorus, 2 bars\n  chords: F x2\n\n"
        "section verse 2, 2 bars\n  chords: C x2\n")
    moved = chartimport.place_waiting_words(wchart)
    wt = open(wchart).read()
    check("text: waiting words move beside their sections once the "
          "tune has a form",
          moved == 3 and "section verse, 2 bars\n  # first words" in wt
          and "section verse 2, 2 bars\n  # second words" in wt
          and "# Verse 1:" not in wt, wt)
    with redirect_stdout(io.StringIO()):
        wb = chartc.compile_chart(wchart, os.path.join(tmp, "wb"))
    check("text: and the chart still compiles", bool(wb))
    tgt = made["Late Train.md"]
    chartimport.import_file(os.path.join(tmp, "words.txt"), out, into=tgt)
    check("text: --into adds words to a chart without changing a note",
          "Walking through the rain" in open(tgt).read())
    for q in list(chartc.CHORD_KINDS):
        said = chartread.say_quality(q)
        if not isinstance(said, str) or '#' in said:
            check(f"every quality speaks: {q}", False, repr(said))
            break
    else:
        check("every quality the compiler accepts can be spoken", True)
    shutil.rmtree(tmp, ignore_errors=True)


def check_road_maps():
    """
    D.S. al Coda, D.C. al Fine and friends: his own "I Thought About
    You" arrangement walks segno 9, To Coda 36, D.S. al Coda 58, coda
    59. The listen follows the walk for the whole band (repeats the
    first time, none after the jump, the last ending), the page draws
    the signs, a lift keeps the road-map words, the read-aloud says
    them in words, and a road map that goes nowhere is refused.
    """
    import re
    import chartaudio
    import chartc
    import chartengrave
    tmp = tempfile.mkdtemp()
    cp = os.path.join(tmp, "r.chart")
    body = ('title: R\nkey: F\nmeter: 4/4\ntempo: 120\n\nband:\n'
            '  trumpet\n  piano\n\n'
            'section intro, 4 bars\n  chords: F x4\n\n'
            'section A, 8 bars\n  chords: F7 x8\n  at bar 1: segno\n'
            '  at bar 6: to coda\n\n'
            'section B, 8 bars, repeat 2x\n  chords: Bb7 x8\n'
            '  at bar 8: d.s. al coda\n\n'
            'section coda, 4 bars\n  chords: F7 x4\n  at bar 1: coda\n'
            '  ending: as written\n')
    open(cp, "w").write(body)
    out = os.path.join(tmp, "b")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(cp, out)
    listen = os.path.join(out, "R — for listening.musicxml")
    plan = chartaudio.parse_score(listen)
    for part in plan['parts']:
        check(f"the {part['name']} walks the road map with the band: "
              "1-20, the repeat, back to the sign, the coda",
              abs(part['length_q'] - (20 + 8 + 6 + 4) * 4) < 1e-6,
              str(part['length_q']))
    fnd = open(os.path.join(out, "R — findings.txt")).read()
    check("the findings read the walk back",
          "bars 1-20, then 13-20, then 5-10, then 21-24" in fnd, fnd)
    x = open(os.path.join(out, "R — piano.musicxml")).read()
    ms, _ = chartengrave.parse_part(x, re.search(r'<part id="([^"]+)"',
                                                 x).group(1))
    check("the page carries the sign and the coda",
          'segno' in ms[4]['signs'] and 'coda' in ms[20]['signs'])
    ok, why = chartengrave.engrave(os.path.join(out, "R — piano.musicxml"),
                                   os.path.join(tmp, "p.pdf"))
    check("and engraves", ok, str(why))
    said = subprocess.run([sys.executable, os.path.join(HERE,
                                                        "chartread.py"),
                           cp, "--part", "piano"], capture_output=True,
                          text=True).stdout
    check("the read-aloud says the road map in words",
          "back to the sign, then take the coda" in said.lower()
          and "('road'" not in said, said)
    for drop, want in (("  at bar 1: segno\n", "no sign to go back to"),
                       ("  at bar 6: to coda\n", "needs 'to coda'")):
        bp = os.path.join(tmp, "bad.chart")
        open(bp, "w").write(body.replace(drop, ""))
        try:
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(bp, os.path.join(tmp, "x"))
            got = ""
        except SystemExit as e:
            got = str(e)
        check(f"a road map missing its {drop.split(':')[1].strip()} is "
              "refused in a sentence", want in got, got)
    check("a lift keeps the road-map words the compiler would strip",
          "To Coda" in chartc.strip_lifted(
              '<direction><direction-type><words>To Coda</words>'
              '</direction-type></direction><note><rest/></note>')
          and "Swing" not in chartc.strip_lifted(
              '<direction><direction-type><words>Swing</words>'
              '</direction-type></direction><note><rest/></note>'))
    # D.C. al Fine, and endings on the way back take the last one
    def bar(n, extra='', bl=''):
        return (n, extra + '<note><rest/><duration>4</duration></note>'
                + bl)
    words = lambda w: ('<direction><direction-type><words>' + w
                       + '</words></direction-type></direction>')
    ms2 = [bar('1'), bar('2', words('Fine')), bar('3'),
           bar('4', words('D.C. al Fine'))]
    walk = [n for n, _ in chartaudio.expand_roadmap(ms2)]
    check("D.C. al Fine plays through, back to the top, ends at Fine",
          walk == ['1', '2', '3', '4', '1', '2'], str(walk))
    shutil.rmtree(tmp, ignore_errors=True)


def check_keyswitches():
    """
    Keyswitches in a played demo (his ask, 2026-09-27): keys far outside
    the instrument's range that change the patch's articulation are taken
    out of the notes, and their names — from the chart's keyswitches
    block, a saved library map, or Logic Pro's own articulation sets —
    become the page's marks, words and slurs, the read-aloud's words and
    the listen's samples. A key with no name yet is named in findings.
    """
    import plistlib
    import re
    import chart as chartmod
    import chartaudio
    import chartc
    import chartdemo
    import smf
    tmp = tempfile.mkdtemp()
    old_dir = chartc.KS_DIR
    chartc.KS_DIR = os.path.join(tmp, "ks")
    try:
        d, n = 480, []

        def ks(t, p):
            n.append((t - 20, t - 5, p, 100))   # a hair early, as played
        ks(0, 24)
        n += [(i * d, (i + 1) * d, 67 + i * 2, 90) for i in range(4)]
        ks(4 * d, 26)
        n += [(4 * d + i * d // 2, 4 * d + i * d // 2 + 100, 74, 90)
              for i in range(8)]
        ks(8 * d, 28)
        n += [(8 * d + i * d, 8 * d + i * d + 200, 62 + i, 90)
              for i in range(4)]
        ks(12 * d, 24)
        n += [(12 * d + i * d, 12 * d + (i + 1) * d, 72 - i, 90)
              for i in range(4)]
        ks(16 * d, 30)
        n.append((16 * d, 20 * d - 20, 67, 90))
        smf.write(os.path.join(tmp, "v.mid"), n, d, 100)
        check("the MIDI writer takes a time before the start as the start "
              "(it used to loop forever)",
              os.path.getsize(os.path.join(tmp, "v.mid")) > 50)
        cp = os.path.join(tmp, "v.chart")
        open(cp, "w").write(
            'title: V\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
            'keyswitches "My Violins":\n  C1 legato\n  D1 Staccato\n'
            '  E1 Pizzicato\n\nband:\n'
            '  violin, demo "v.mid", keyswitches "My Violins"\n\n'
            'section A, 5 bars\n  chords: C x5\n'
            '  violin: from demo bars 1-5\n')
        out = os.path.join(tmp, "b")
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(cp, out)
        vx = open(os.path.join(out, "V — violin.musicxml")).read()
        fnd = open(os.path.join(out, "V — findings.txt")).read()
        check("keyswitches leave the notes (no low C1 on the page)",
              '<octave>1</octave>' not in vx and 'moved up' not in fnd,
              fnd)
        check("findings name each key by note and MIDI number, and the "
              "unnamed one with its bars",
              "E1 (MIDI 28) is Pizzicato" in fnd
              and "F#1 (MIDI 30) governs bars 5" in fnd, fnd)
        check("staccato keys print staccato, pizz. prints once, arco "
              "comes back, legato slurs",
              vx.count('<staccato/>') == 8 and vx.count('>pizz.<') == 1
              and vx.count('>arco<') == 1
              and 'slur number="1" type="start"' in vx, vx[:200])
        said = subprocess.run([sys.executable,
                               os.path.join(HERE, "chartread.py"), cp,
                               "--part", "violin"], capture_output=True,
                              text=True).stdout
        check("the read-aloud says each change once",
              "staccato from here" in said and "pizz. from here" in said
              and "legato from here" in said, said)
        plan = chartaudio.parse_score(os.path.join(
            out, "V — for listening.musicxml"))
        ev = plan['parts'][0]['events']
        check("the listen plucks the pizzicato bars and bows the rest",
              [bool(e[4].get('pizz')) for e in ev].count(True) == 4
              and not ev[-1][4].get('pizz'))
        check("library names read like a copyist reads them",
              chartdemo.ks_meaning("Fall Short")[0] is None
              and chartdemo.ks_meaning("Fall Short")[3] == 'falloff'
              and chartdemo.ks_meaning("Trill Semi")[3] == 'trill_half'
              and chartdemo.ks_meaning("Expressive Long") ==
              (None, None, False, None)
              and chartdemo.ks_meaning("Violins - Spiccato")[0] ==
              'spiccato')
        # a saved library map, used by name from any chart
        os.makedirs(chartc.KS_DIR)
        open(os.path.join(chartc.KS_DIR, "Saved Violins.txt"), "w").write(
            "C1 legato\n26 staccato\nE1 pizzicato\nF#1 tremolo\n")
        body_ = open(cp).read().replace(
            'demo "v.mid", keyswitches "My Violins"',
            'demo "v.mid", keyswitches "saved violins"')
        open(cp, "w").write(body_)
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(cp, out)
        vx2 = open(os.path.join(out, "V — violin.musicxml")).read()
        check("a saved map is found by name, and names the last key too",
              '<tremolo type="single">' in vx2 and vx2.count(
                  '<staccato/>') == 8)
        # Logic Pro's articulation sets come in as saved maps
        lg = os.path.join(tmp, "Logic", "Studio Strings")
        os.makedirs(lg)
        plistlib.dump({'Articulations': [
            {'ID': 1001, 'Name': 'Sustain'},
            {'ID': 1002, 'Name': 'Staccato'}],
            'Switches': [{'ID': 1001, 'MB1': 24, 'Status': 'NoteOn'},
                         {'ID': 1002, 'MB1': 30, 'Status': 'NoteOn'}],
            'OctaveOffset': 0}, open(os.path.join(lg, "Studio Violins.plist"),
                                     "wb"))
        old_logic = chartmod.LOGIC_ARTIC
        chartmod.LOGIC_ARTIC = os.path.join(tmp, "Logic")
        try:
            with redirect_stdout(io.StringIO()):
                chartmod.run_keyswitches(['from-logic'])
        finally:
            chartmod.LOGIC_ARTIC = old_logic
        lm = chartc.keyswitch_map({'keyswitches': {}},
                                  "Logic Studio Strings - Studio Violins")
        check("Logic's articulation sets import as maps",
              lm == {24: 'Sustain', 30: 'Staccato'}, str(lm))
        # naming the unnamed keys, once, in a conversation
        import chartkeys
        cp3 = os.path.join(tmp, "v3.chart")
        open(cp3, "w").write(body_.replace(
            ', keyswitches "saved violins"', ''))
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("staccato\n\npizzicato\ntremolo\n")
        try:
            with redirect_stdout(io.StringIO()) as talk:
                chartkeys.name_keys(cp3)
        finally:
            sys.stdin = old_stdin
        linked = open(cp3).read()
        saved = chartc.keyswitch_map({'keyswitches': {}}, "V violin")
        check("naming keys saves a map, links the part, skips on Enter",
              'keyswitches "V violin"' in linked
              and saved == {24: 'staccato', 28: 'pizzicato', 30: 'tremolo'}
              and "Named 3 of 4" in talk.getvalue(), str(saved))
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(cp3, os.path.join(tmp, "b3"))
        f3 = open(os.path.join(tmp, "b3", "V — findings.txt")).read()
        check("and the next build knows them (only the skipped key is "
              "still asked about)", f3.count("has no name yet") == 1
              and "D1 (MIDI 26)" in f3, f3)
        # a named key just below the range (Cuba's trumpet sits its
        # switches at MIDI 48-51) is a switch; the same key unnamed is
        # a note, so a low note really played is never eaten
        tp = []
        tp.append((0, 30, 48, 100))
        tp += [(i * 480, i * 480 + 120, 72, 90) for i in range(1, 4)]
        smf.write(os.path.join(tmp, "t.mid"), tp, 480, 100)
        for mapped, want_notes in ((True, 3), (False, 4)):
            tc = os.path.join(tmp, "t.chart")
            open(tc, "w").write(
                'title: T\nkey: C\nmeter: 4/4\ntempo: 100\n\n'
                + ('keyswitches "Cuba":\n  48 Staccato (short)\n\n'
                   if mapped else '')
                + 'band:\n  trumpet, demo "t.mid"'
                + (', keyswitches "Cuba"' if mapped else '') + '\n\n'
                'section A, 1 bars\n  chords: C\n'
                '  trumpet: from demo bars 1-1\n')
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(tc, os.path.join(tmp, "tb"))
            tx = open(os.path.join(tmp, "tb", "T — trumpet.musicxml")).read()
            got = len(re.findall(r'<note>(?:(?!</note>).)*<pitch>', tx,
                                 re.S))
            check("a mapped key just below the range is a switch"
                  if mapped else "the same key unmapped stays a note",
                  got == want_notes
                  and (tx.count('<staccato/>') == 3) == mapped, str(got))
        check("a key's velocity picks its half of a split map line",
              chartdemo.ks_word_for("low velo: mute | high velo: x-note",
                                    60) == "mute"
              and chartdemo.ks_word_for("low velo: mute | high velo: "
                                        "x-note", 120) == "x-note"
              and chartdemo.ks_meaning("x-note")[1] == "dead notes"
              and chartdemo.ks_meaning("select string E low") ==
              (None, None, False, None))
        # a Toontrack (EZdrummer / Superior Drummer) take: its own map
        dn = [(i * 240, i * 240 + 60, [36, 24, 39, 32][i % 4], 100)
              for i in range(16)]
        smf.write(os.path.join(tmp, "d.mid"), dn, 480, 100)
        for mapped in (False, True):
            dc = os.path.join(tmp, "d.chart")
            open(dc, "w").write(
                'title: D\nkey: C\nmeter: 4/4\ntempo: 100\n\nband:\n'
                '  drums = drum set, demo "d.mid"'
                + (', drummap "Toontrack"' if mapped else '') + '\n\n'
                'section A, 2 bars\n  chords: C x2\n'
                '  drums: from demo bars 1-2\n')
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(dc, os.path.join(tmp, "db"))
            dfind = open(os.path.join(tmp, "db", "D — findings.txt")).read()
            said = subprocess.run(
                [sys.executable, os.path.join(HERE, "chartread.py"), dc,
                 "--part", "drums"], capture_output=True, text=True).stdout
            if mapped:
                check("a Toontrack take reads as the kit it played: open "
                      "hat, snare, crash — no claps, no mystery drums",
                      "clap" not in said and "drum 32" not in said
                      and "open hat" in said and "crash" in said, said)
            else:
                check("an unmapped take with non-GM drum notes says so",
                      "drummap \"Toontrack\"" in dfind, dfind)
        # XLN Addictive Drums 2: its own keymap; its Flexi percussion
        # is never read as the GM piece that shares its number
        an = [(i * 240, i * 240 + 60, [36, 37, 49, 47][i % 4], 100)
              for i in range(16)]
        smf.write(os.path.join(tmp, "a.mid"), an, 480, 100)
        ac = os.path.join(tmp, "a.chart")
        open(ac, "w").write(
            'title: A\nkey: C\nmeter: 4/4\ntempo: 100\n\nband:\n'
            '  drums = drum set, demo "a.mid", drummap "Addictive Drums 2"'
            '\n\nsection A, 2 bars\n  chords: C x2\n'
            '  drums: from demo bars 1-2\n')
        with redirect_stdout(io.StringIO()):
            ab = chartc.compile_chart(ac, os.path.join(tmp, "ab"))
        said = subprocess.run(
            [sys.executable, os.path.join(HERE, "chartread.py"), ac,
             "--part", "drums"], capture_output=True, text=True).stdout
        aplan = chartaudio.parse_score(os.path.join(
            tmp, "ab", "A — for listening.musicxml"))
        check("an Addictive Drums 2 take reads as its kit: rimshot is "
              "snare, 49 is a closed hat, Flexi is kit percussion",
              "closed hat" in said and "snare" in said
              and "kit percussion (note 47)" in said and "mid tom" not in
              said and "crash" not in said and aplan['parts'][0]['events'],
              said)
        # any other kit, named once: the drums conversation
        import chartdrums
        old_dd = chartdrums.DRUM_DIR
        chartdrums.DRUM_DIR = os.path.join(tmp, "dm")
        try:
            dc2 = os.path.join(tmp, "d2.chart")
            open(dc2, "w").write(
                'title: D\nkey: C\nmeter: 4/4\ntempo: 100\n\nband:\n'
                '  drums = drum set, demo "d.mid"\n\nsection A, 2 bars\n'
                '  chords: C x2\n  drums: from demo bars 1-2\n')
            # notes 24, 32, 36, 39 in order: name the library, then each
            old_stdin = sys.stdin
            sys.stdin = io.StringIO("Royster Kit\nhi-hat open\ncrash 2\n"
                                    "\nsnare roll\n")
            try:
                with redirect_stdout(io.StringIO()):
                    chartdrums.name_drums(dc2)
            finally:
                sys.stdin = old_stdin
            check("the drums conversation saves the kit's words and links "
                  "the part", 'drummap "Royster Kit"' in open(dc2).read()
                  and chartdrums.load_saved("Royster Kit") ==
                  {24: 'hi-hat open', 32: 'crash 2', 39: 'snare roll'},
                  str(chartdrums.load_saved("Royster Kit")))
            said = subprocess.run(
                [sys.executable, os.path.join(HERE, "chartread.py"), dc2,
                 "--part", "drums"], capture_output=True, text=True,
                env=dict(os.environ, HOME=tmp)).stdout
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(dc2, os.path.join(tmp, "d2b"))
            d2x = open(os.path.join(tmp, "d2b", "D — drums.musicxml")).read()
            check("and the next build reads the kit it played: no claps, "
                  "no mystery drums",
                  'circle-x' in d2x and '<display-step>A</display-step>'
                  '<display-octave>5' in d2x, d2x[:120])
            # a built-in map plus the writer's own additions: once a
            # crash (note numbers passed as keywords), now layered
            os.makedirs(chartdrums.DRUM_DIR, exist_ok=True)
            open(os.path.join(chartdrums.DRUM_DIR, "Addictive Drums 2.txt"),
                 "w").write("47 open conga\n")
            try:
                with redirect_stdout(io.StringIO()):
                    chartc.compile_chart(ac, os.path.join(tmp, "ab2"))
                ax2 = open(os.path.join(tmp, "ab2", "A — drums.musicxml")
                           ).read()
                layered = "<display-step>" in ax2
            except Exception as e:
                layered = repr(e)
            check("a built-in drum map takes the writer's additions on top",
                  layered is True, str(layered))
            import re as _rg
            import smf as _smg
            import instruments as _ig
            # a stroke named with its piece: "snare ghost" prints in
            # parentheses on that note alone, not on the kick beside it
            gn = []
            for b in (0, 1920):
                gn += [(b, b + 200, 36, 100), (b + 960, b + 1160, 36, 100),
                       (b + 480, b + 680, 100, 100),
                       (b + 1440, b + 1640, 100, 100),
                       (b + 720, b + 820, 101, 100),
                       (b + 960, b + 1060, 101, 100)]
                gn += [(b + i * 240, b + i * 240 + 100, 42, 80)
                       for i in range(8)]
            _smg.write(os.path.join(tmp, "g.mid"), gn, 480, 100)
            open(os.path.join(chartdrums.DRUM_DIR, "Ghost Kit.txt"),
                 "w").write("100 snare\n101 snare ghost\n")
            gc = os.path.join(tmp, "g.chart")
            open(gc, "w").write(
                'title: G\nmeter: 4/4\ntempo: 100\n\nband:\n  drums, '
                'demo "g.mid", drummap "Ghost Kit"\n\nsection A, 2 bars\n'
                '  chords: C x2\n  drums: from demo bars 1-2\n')
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(gc, os.path.join(tmp, "gb"))
            gx = open(os.path.join(tmp, "gb", "G — drums.musicxml")).read()
            m1 = _rg.search(r'<measure.*?</measure>', gx, _rg.S).group(0)
            hits = [(_rg.search(r'<display-step>(\w)', n_).group(1),
                     'parentheses' in n_)
                    for n_ in _rg.findall(r'<note>(.*?)</note>', m1, _rg.S)
                    if '<unpitched>' in n_ and 'voice>2' in n_]
            check("a note named 'snare ghost' prints ghosted, alone",
                  hits == [('F', False), ('C', False), ('C', True),
                           ('F', False), ('C', True), ('C', False)],
                  str(hits))
            # every named stroke, on the page and in the read-aloud
            sn = [(i * 240, i * 240 + 100, 42, 80) for i in range(8)]
            sn += [(0, 200, 36, 100), (480, 680, 102, 100),
                   (960, 1160, 103, 100), (1440, 1640, 104, 100),
                   (1680, 1780, 105, 100)]
            _smg.write(os.path.join(tmp, "s.mid"), sn, 480, 100)
            open(os.path.join(chartdrums.DRUM_DIR, "Stroke Kit.txt"),
                 "w").write("102 snare flam\n103 snare rim shot\n"
                            "104 snare drag\n105 crash choke\n")
            sc = os.path.join(tmp, "s.chart")
            open(sc, "w").write(
                'title: S\nmeter: 4/4\ntempo: 100\n\nband:\n  drums, '
                'demo "s.mid", drummap "Stroke Kit"\n\nsection A, 1 bars\n'
                '  chords: C\n  drums: from demo bar 1\n')
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(sc, os.path.join(tmp, "sb"))
            sx = open(os.path.join(tmp, "sb", "S — drums.musicxml")).read()
            check("flam, drag, rimshot and choke print as drum books do",
                  sx.count('<grace slash="yes"/>') == 1
                  and sx.count('<grace/>') == 2
                  and '>slashed</notehead>' in sx
                  and sx.count('<breath-mark/>') == 1, sx[-300:])
            fh = os.path.join(tmp, "fh", ".config", "copyist",
                              "drummaps")
            os.makedirs(fh, exist_ok=True)
            shutil.copy(os.path.join(chartdrums.DRUM_DIR, "Stroke Kit.txt"),
                        fh)
            ssaid = subprocess.run(
                [sys.executable, os.path.join(HERE, "chartread.py"), sc,
                 "--part", "drums"], capture_output=True, text=True,
                env=dict(os.environ, HOME=os.path.join(tmp, "fh"),
                         USERPROFILE=os.path.join(tmp, "fh"))).stdout
            check("the read-aloud names each stroke the way a drummer does",
                  all(w in ssaid for w in ("flam on the snare",
                                           "rimshot on the snare",
                                           "drag on the snare",
                                           "crash choked")), ssaid)
            import chartengrave as _ceg
            nn = _ceg._parse_note('<note><unpitched><display-step>C'
                                  '</display-step><display-octave>5'
                                  '</display-octave></unpitched></note>')
            check("the engraver puts a drum note where display-step says "
                  "(it had piled every kit piece on the middle line)",
                  (nn.step, nn.octave) == ('C', 5))
            import chartdemo as _cdm
            check("drum lanes keep the beat: an offbeat hit stops at it",
                  [_cdm._beat_end(t_, 24, 96) for t_ in (0, 12, 36, 90)]
                  == [24, 24, 48, 96]
                  and _cdm._beat_end(84, 24, 60) == 108
                  and _cdm._beat_end(108, 24, 60) == 120)
            check("compound time beams by the dotted beat, simple by "
                  "the bottom note",
                  [_ceg.beam_beat(t_, 24) for t_ in
                   ((12, 8), (6, 8), (3, 8), (4, 4), (7, 8), (2, 2))]
                  == [36, 36, 36, 24, 12, 48])
            check("the first system clears the credits it sits under",
                  _ceg.under_credits(700, None) == 700
                  and _ceg.under_credits(700, 690) == 690 - _ceg.HEAD_CLEAR)
            check("bar ranges as people write them",
                  [chartc.bar_words(t_) for t_ in (
                      'from demo bar 3', 'from demo bars 1 to 4',
                      'from demo bars 2\u20135 at bar 9',
                      'from demo "Take 2 to 3" bars 1 through 2')]
                  == ['from demo bars 3', 'from demo bars 1-4',
                      'from demo bars 2-5 at bars 9',
                      'from demo "Take 2 to 3" bars 1-2'])
            check("a drummer's words for strokes and hand percussion",
                  [_ig.gm_for_words(w) for w in
                   ("rim shot", "snare flam", "conga slap", "low bongo",
                    "shaker", "crash choke", "ride sizzle", "woodblock")]
                  == [38, 38, 62, 61, 82, 49, 51, 76]
                  and [_ig.drum_artic(w) for w in
                       ("snare ghost", "flam", "rim shot", "crash choke",
                        "snare")] == ['ghost', 'flam', 'rimshot', 'choke',
                                      None])
        finally:
            chartdrums.DRUM_DIR = old_dd
        try:
            chartc.keyswitch_map({'keyswitches': {}}, "Nobody's Map")
            got = ""
        except SystemExit as e:
            got = str(e)
        check("an unknown map is refused in a sentence", "no keyswitch "
              "map called" in got, got)
    finally:
        chartc.KS_DIR = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


def check_detail_and_look():
    """
    DESIGN.md 11's last two levels through the chart door — `simplified`
    smooths a played line to the eighth and absorbs ornament noise;
    `rhythmic slashes` prints the rhythm on slash noteheads, chords
    above, silent in playback like every slash. And the look: header
    dresses the pages (validated in check; applied at render via -S).
    """
    import re
    import chartaudio
    import chartc
    import smf
    from chart import verify_measures, parse_look, write_style
    tmp = tempfile.mkdtemp()
    div = 480
    notes = [(0, 460, 65, 88), (480, 40, 66, 70), (520, 420, 67, 88),
             (960, 940, 70, 90), (1920, 460, 72, 88), (2400, 50, 71, 70),
             (2450, 45, 72, 72), (2500, 380, 70, 86), (2880, 940, 67, 88)]
    smf.write(os.path.join(tmp, "o.mid"), notes, div, 100)
    open(os.path.join(tmp, "d.chart"), "w").write(
        'title: D\nkey: F\nmeter: 4/4\ntempo: 100\ndemo: o.mid\n\n'
        'band:\n  tenor = tenor sax\n  guitar\n  piano\n\n'
        'section A, 2 bars\n  chords: F7, Bb7\n'
        '  tenor: from demo bars 1-2, simplified\n'
        '  guitar: from demo bars 1-2, rhythmic slashes\n'
        '  piano: groove\n')
    out = os.path.join(tmp, "b")
    buf = io.StringIO()
    with redirect_stdout(buf):
        files = chartc.compile_chart(os.path.join(tmp, "d.chart"), out)
    check("detail levels: measures sum", not verify_measures(files))
    ten = open(os.path.join(out, "D — tenor.musicxml")).read()
    gtr = open(os.path.join(out, "D — guitar.musicxml")).read()
    check("simplified absorbs ornaments and says so",
          '<type>32nd' not in ten
          and "ornament(s) absorbed" in buf.getvalue())
    check("rhythmic slashes print slash noteheads, no accidentals",
          gtr.count('<notehead>slash</notehead>') >= 6
          and '<accidental>' not in gtr)
    plan = chartaudio.parse_score(
        os.path.join(out, "D — for listening.musicxml"))
    g = next(p for p in plan['parts'] if p['name'] == 'guitar')
    check("a slash rhythm never sounds", not g['events'])
    check("the range report skips a part that prints no pitches",
          "guitar: written peak" not in buf.getvalue())

    o = parse_look("jazz, landscape, staff 2.0, measure numbers")
    check("look: parses its whole vocabulary",
          o == {'preset': 'jazz', 'landscape': True, 'staff': 2.0,
                'numbers': True}, f"got {o}")
    p = write_style("jazz, measure numbers", tmp)
    mss = open(p).read()
    check("the style file carries the jazz face and the numbers",
          '<musicalSymbolFont>MuseJazz</musicalSymbolFont>' in mss
          and '<measureNumberInterval>1</measureNumberInterval>' in mss)
    try:
        parse_look("disco")
        got = ""
    except SystemExit as e:
        got = str(e)
    check("an unknown look refuses with the vocabulary",
          "jazz, handwritten and engraved" in got, f"got: {got}")

    shutil.rmtree(tmp, ignore_errors=True)


def check_user_chair():
    """
    The safety nets and the session feel: every part's fate per section
    is a finding (the spec's day-one promise — an accidental chart-long
    rest is read back, loudly), and the count-in prepends real clicks
    that shift the whole schedule.
    """
    import chartaudio
    import chartc
    import smf
    tmp = tempfile.mkdtemp()
    div = 480
    notes = [(i * div, i * div + 400, 60 + i, 90) for i in range(4)]
    smf.write(os.path.join(tmp, "d.mid"), notes, div, 120)
    open(os.path.join(tmp, "f.chart"), "w").write(
        'title: U\nkey: C\nmeter: 4/4\ntempo: 120\ndemo: d.mid\n\n'
        'band:\n  flute\n  horn = french horn\n  piano\n\n'
        'section A, 2 bars, label "Top"\n  chords: C, F\n'
        '  flute: from demo bars 1-1\n  piano: groove\n'
        'section B, 2 bars\n  chords: G, C\n  piano: groove\n')
    out = os.path.join(tmp, "b")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(os.path.join(tmp, "f.chart"), out)
    log = buf.getvalue()
    check("every part's fate is a finding",
          "flute — Top: your line; B: rest" in log
          and "piano — Top: slashes; B: slashes" in log, log[:300])
    check("a part that never plays is called out loudly",
          "horn NEVER PLAYS A BAR IN THIS CHART" in log)

    listen = os.path.join(out, "U — for listening.musicxml")
    plain = chartaudio.render(listen, os.path.join(tmp, "a.wav"))
    counted = chartaudio.render(listen, os.path.join(tmp, "c.wav"),
                                count_in=2)
    check("the count-in shifts the schedule by its own bars",
          abs(counted[3] - 4.0) < 1e-9
          and abs(counted[0] - plain[0] - 4.0) < 1e-6,
          f"lead {counted[3]}, ends {plain[0]} vs {counted[0]}")

    shutil.rmtree(tmp, ignore_errors=True)


def check_engraver():
    """
    Stage two of the MuseScore exit: Copyist draws its own single-staff
    pages — a real PDF from pure stdlib — and declines, in a sentence,
    what still belongs to MuseScore (grand staves, the score page).
    """
    import chartc
    import chartengrave
    import smf
    tmp = tempfile.mkdtemp()
    div = 480
    notes = [(i * div, i * div + 440, 65 + i, 88) for i in range(8)]
    smf.write(os.path.join(tmp, "d.mid"), notes, div, 116)
    open(os.path.join(tmp, "e.chart"), "w").write(
        'title: E\nkey: F\nmeter: 4/4\ntempo: 116\nfeel: shuffle\n'
        'demo: d.mid\n\nband:\n  tenor = tenor sax\n  guitar\n\n'
        'section A, 2 bars, repeat 2x\n  chords: F7\n'
        '  ending 1, 1 bars: chords: C7\n'
        '  ending 2, 1 bars: chords: F7\n'
        '  tenor: from demo bars 1-2, legato\n  guitar: groove\n\n'
        'section B, 2 bars\n  chords: F7, C7\n'
        '  tenor: solo\n  guitar: groove\n')
    out = os.path.join(tmp, "b")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "e.chart"), out)
    txml = open(os.path.join(out, "E — tenor.musicxml")).read()
    check("a Bb horn's changes print transposed (F7 reads G7)",
          '<root-step>G</root-step>' in txml
          and '<root-step>F</root-step>' not in txml,
          "concert roots leaked onto the tenor part")
    pdf = os.path.join(tmp, "t.pdf")
    ok, why = chartengrave.engrave(
        os.path.join(out, "E — tenor.musicxml"), pdf)
    head = open(pdf, "rb").read(5)
    check("the engraver draws a real single-part PDF",
          ok and head == b"%PDF-" and os.path.getsize(pdf) > 2500,
          f"{ok} {why} {os.path.getsize(pdf) if ok else 0}")

    spdf = os.path.join(tmp, "s.pdf")
    ok, why = chartengrave.engrave(
        os.path.join(out, "E — score.musicxml"), spdf)
    check("the conductor score engraves, stacked and scaled",
          ok and os.path.getsize(spdf) > 2500, f"{ok} {why}")
    # the grand staff engraves — the last MuseScore borrow, retired
    open(os.path.join(tmp, "g.chart"), "w").write(
        'title: G\nkey: F\nmeter: 4/4\ntempo: 116\n\n'
        'band:\n  piano\n  flute\n\n'
        'section A, 2 bars\n  chords: F7, Bb7\n  piano: groove\n')
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "g.chart"),
                             os.path.join(tmp, "gb"))
    gp = os.path.join(tmp, "gp.pdf")
    ok, why = chartengrave.engrave(
        os.path.join(tmp, "gb", "G — piano.musicxml"), gp)
    check("the grand staff engraves",
          ok and os.path.getsize(gp) > 2000, f"{ok} {why}")
    gs = os.path.join(tmp, "gs.pdf")
    ok, why = chartengrave.engrave(
        os.path.join(tmp, "gb", "G — score.musicxml"), gs)
    check("a score holding a grand staff engraves too",
          ok and os.path.getsize(gs) > 2000, f"{ok} {why}")
    # grace notes, the last thing that used to decline: a crushed
    # grace leans on beat 2, a run of three sixteenths on beat 3
    gx = os.path.join(tmp, "grace.musicxml")
    open(gx, "w").write(
        '<score-partwise><part-list><score-part id="P1">'
        '<part-name>x</part-name></score-part></part-list>'
        '<part id="P1"><measure number="1">'
        '<attributes><divisions>24</divisions><key><fifths>-1</fifths>'
        '</key><time><beats>4</beats><beat-type>4</beat-type></time>'
        '<clef><sign>G</sign><line>2</line></clef></attributes>'
        '<note><pitch><step>C</step><octave>5</octave></pitch>'
        '<duration>24</duration><voice>1</voice><type>quarter</type>'
        '</note>'
        '<note><grace slash="yes"/><pitch><step>D</step><alter>1</alter>'
        '<octave>5</octave></pitch><voice>1</voice><type>eighth</type>'
        '</note>'
        '<note><pitch><step>E</step><octave>5</octave></pitch>'
        '<duration>24</duration><voice>1</voice><type>quarter</type>'
        '</note>'
        + ''.join('<note><grace/><pitch><step>%s</step><octave>4</octave>'
                  '</pitch><voice>1</voice><type>16th</type></note>' % st
                  for st in 'GAB') +
        '<note><pitch><step>C</step><octave>5</octave></pitch>'
        '<duration>48</duration><voice>1</voice><type>half</type>'
        '</note></measure></part></score-partwise>')
    gxml = open(gx).read()
    gms, why = chartengrave.parse_part(gxml, "P1")
    mains = [ns[0] for _p, ns, _s, _v in gms[0]['events']]
    check("graces take no time and wait for their note",
          len(mains) == 3 and len(mains[1].graces) == 1
          and mains[1].graces[0][0].grace_slash
          and len(mains[2].graces) == 3, str(why))
    check("a grace's accidental follows the key",
          mains[1].graces[0][0].show_acc == 1
          and mains[2].graces[2][0].show_acc == 0)
    ok, why = chartengrave.engrave(gx, os.path.join(tmp, "g.pdf"))
    check("grace notes engrave, where they used to decline",
          ok and os.path.getsize(os.path.join(tmp, "g.pdf")) > 2000,
          f"{ok} {why}")
    import chartaudio as _ga
    gev = _ga.parse_score(gx)['parts'][0]['events']
    ons = [(round(e[0], 2), e[2]) for e in gev]
    check("the listen plays graces just ahead of the beat",
          (0.9, 75) in ons and (2.0, 72) in ons
          and [(1.7, 67), (1.8, 69), (1.9, 71)]
          == [o for o in ons if 1.5 < o[0] < 2.0], str(ons))

    # the music font: Leland loads, knows its glyphs, and is embedded
    m = chartengrave.music_font()
    check("Leland loads with the glyphs the pages need",
          m is not None and all(
              n in m.gids for n in ('gClef', 'fClef', 'sharp', 'flat',
                                    'blackHead', 'restQ', 'flag8U',
                                    'ts4', 'dynF', 'marcato')),
          "font missing" if m is None else "glyph gap")
    raw = open(pdf, "rb").read()
    check("the part PDF embeds the font (Type0 + FontFile3)",
          b"/FM" in raw and b"/FontFile3" in raw
          and b"/Identity-H" in raw, "no embedded font in t.pdf")
    check("the default pages carry a text face beside Leland",
          raw.count(b"/FontFile3") >= 2 and b"/FE0" in raw,
          "no embedded text face in t.pdf")

    # each look dresses the words in its own face; plain stays built-in
    for look, want in (('handwritten', True), ('jazz', True),
                       ('plain', False)):
        lp = os.path.join(tmp, f"l-{look}.pdf")
        ok, why = chartengrave.engrave(
            os.path.join(out, "E — tenor.musicxml"), lp, look=look)
        lraw = open(lp, "rb").read()
        got = b"/FE0" in lraw
        check(f"look: {look} {'uses' if want else 'skips'} a text face",
              ok and got == want, f"{ok} {why} face={got}")

    # the alto clef engraves (viola and friends)
    cxml = os.path.join(tmp, "c.musicxml")
    open(cxml, "w").write(
        '<score-partwise><work><work-title>C</work-title></work>'
        '<part-list><score-part id="P1">'
        '<part-name>viola</part-name></score-part></part-list>'
        '<part id="P1"><measure number="1">'
        '<attributes><divisions>24</divisions>'
        '<time><beats>4</beats><beat-type>4</beat-type></time>'
        '<clef><sign>C</sign><line>3</line></clef></attributes>'
        '<note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>96</duration><voice>1</voice><type>whole</type>'
        '</note></measure></part></score-partwise>')
    ok, why = chartengrave.engrave(cxml, os.path.join(tmp, "c.pdf"))
    check("the alto clef engraves", ok and
          os.path.getsize(os.path.join(tmp, "c.pdf")) > 2000,
          f"{ok} {why}")

    # accidentals follow the key: in key G, an F# is bare, an F prints
    # the natural, a Bb prints one flat and its repeat prints none
    def note(step, alter, octv):
        alt = f'<alter>{alter}</alter>' if alter else ''
        return (f'<note><pitch><step>{step}</step>{alt}'
                f'<octave>{octv}</octave></pitch><duration>24</duration>'
                '<voice>1</voice><type>quarter</type></note>')
    axml = os.path.join(tmp, "a.musicxml")
    open(axml, "w").write(
        '<score-partwise><part-list><score-part id="P1">'
        '<part-name>x</part-name></score-part></part-list>'
        '<part id="P1"><measure number="1">'
        '<attributes><divisions>24</divisions>'
        '<key><fifths>1</fifths></key>'
        '<time><beats>4</beats><beat-type>4</beat-type></time>'
        '<clef><sign>G</sign><line>2</line></clef></attributes>'
        + note('F', 1, 5) + note('F', 0, 5)
        + note('B', -1, 4) + note('B', -1, 4)
        + '</measure></part></score-partwise>')
    apdf = os.path.join(tmp, "a.pdf")
    ok, why = chartengrave.engrave(axml, apdf)
    m = chartengrave.music_font()
    raw = open(apdf, "rb").read()
    import re
    import zlib as _z
    parts = []
    for s in re.findall(rb'stream\r?\n(.*?)\r?\nendstream', raw, re.S):
        try:
            parts.append(_z.decompress(s))
        except Exception:
            parts.append(s)
    stream = b"".join(parts)
    def glyphs(name):
        return stream.count(b"<%04X> Tj" % m.gids[name])
    check("in key G: one sharp (the signature), one natural, one flat",
          ok and glyphs('sharp') == 1 and glyphs('natural') == 1
          and glyphs('flat') == 1,
          f"{ok} {why} s={glyphs('sharp')} n={glyphs('natural')} "
          f"f={glyphs('flat')}" if ok else f"{ok} {why}")
    shutil.rmtree(tmp, ignore_errors=True)


def check_settings():
    """The defaults desk: set reads back, every value survives the
    round trip, and nothing touches the real config."""
    import chart
    tmp = tempfile.mkdtemp()
    real = chart.CONFIG
    chart.CONFIG = os.path.join(tmp, "config.json")
    try:
        with redirect_stdout(io.StringIO()) as out:
            chart.run_settings(['set', 'look=jazz'])
        check("set writes and reads back",
              'jazz' in out.getvalue()
              and chart.load_cfg()['look'] == 'jazz', out.getvalue())
        with redirect_stdout(io.StringIO()) as out:
            chart.run_settings(['settings'])
        check("every setting states its current value",
              'look (now: jazz)' in out.getvalue()
              and 'composer (now: not set)' in out.getvalue(),
              out.getvalue())
        bad = False
        try:
            with redirect_stdout(io.StringIO()):
                chart.run_settings(['set', 'look=cursive'])
        except SystemExit:
            bad = True
        check("a look nobody has refuses in a sentence", bad, "accepted")
        with redirect_stdout(io.StringIO()) as out:
            chart.run_settings(['set', 'exports=pdf and brf'])
        check("exports takes plain words and says what a build makes",
              chart.load_cfg()['exports'] == 'pages, braille'
              and 'makes pages and braille' in out.getvalue(),
              out.getvalue())
        check("exports: all is every one",
              chart.parse_exports('all') == {k for k, _ in chart.EXPORTS})
        bad = False
        try:
            with redirect_stdout(io.StringIO()):
                chart.run_settings(['set', 'exports=pages, tuba'])
        except SystemExit:
            bad = True
        check("an export nobody makes refuses in a sentence", bad,
              "accepted")
    finally:
        chart.CONFIG = real
        shutil.rmtree(tmp, ignore_errors=True)


def check_roadmap():
    """chartedit — the roadmap conversation: the form parser, spoken
    chords, played-chord naming, and a whole scripted session."""
    print("\nroadmap conversation (chartedit)")
    import collections
    import chartedit

    plans, gaps = chartedit.parse_form(
        "8 bar intro, head is 32 AABA, solos over the head twice, "
        "out on the last A")
    check("the breath parses whole", not gaps and len(plans) == 4)
    check("intro is 8 plain bars",
          plans[0]["name"] == "intro" and plans[0]["bars"] == 8)
    check("the head carries its shape",
          plans[1]["bars"] == 32 and plans[1]["shape"] == "aaba")
    check("solos borrow the head twice",
          plans[2]["kind"] == "solos" and plans[2]["use"] == "head"
          and plans[2]["repeat"] == 2)
    check("the out names its source",
          plans[3]["kind"] == "out" and plans[3]["source"] == "last a")

    check("number words digitize",
          chartedit.digitize("thirty two bars of head") ==
          "32 bars of head")
    sp = chartedit.parse_spoken_chords
    check("bandstand chords speak",
          sp("b flat seven 4 bars, e flat seven") == "Bb7 x4, Eb7")
    check("placement speaks",
          sp("c nine f seven at 3, b flat seven at the and of 4") ==
          "C9 F7@3, Bb7@4+")
    check("qualities speak",
          sp("F minor seven flat five, a half diminished") ==
          "Fm7b5, Am7b5")
    check("slash bass speaks",
          sp("e flat minor over b flat") == "Ebm/Bb")
    check("typed symbols pass through", sp("Bb7 x4, F7@3") ==
          "Bb7 x4, F7@3")
    try:
        sp("b flat burner")
        check("an unknown word names itself", False, "no error")
    except chartedit.SpokenError as e:
        check("an unknown word names itself", e.word == "burner")
    check("the vocabulary applies his words",
          sp("b flat burner", {"burner": "seven sharp nine"}) ==
          "Bb7#9")

    check("a played Bb7 names itself",
          chartedit.name_chord({46, 58, 62, 65, 68}) == "Bb7")
    check("a rootless bass note names the slash",
          chartedit.name_chord({40, 48, 55, 58, 62}) == "C9/E")
    check("nothing nameable stays honest",
          chartedit.name_chord({48, 49, 50, 51}) is None)

    N = collections.namedtuple("N", "on off pitch")
    div = 480
    Bb7 = [46, 58, 62, 65, 68]
    Cm7 = [48, 58, 63, 67]
    G7 = [43, 55, 59, 65]
    notes = [N(0, div * 4, p) for p in Bb7]            # bar 1, held whole
    notes += [N(div * 4, div * 8, p) for p in Bb7]     # bar 2 restates
    notes += [N(div * 8, div * 10, p) for p in Cm7]    # bar 3 beat 1
    notes += [N(div * 10, div * 12, p) for p in G7]    # bar 3 beat 3
    barof = lambda t: t // (div * 4) + 1
    bars, misses = chartedit.detect_bars(
        notes, barof, 1, 3, half_beat=3, half_ticks=div * 2)
    check("played bars name themselves, split lands at 3",
          bars == ["Bb7", "Bb7", "Cm7 G7@3"] and not misses, str(bars))
    bars, _ = chartedit.detect_bars(notes[:5], barof, 1, 2,
                                    half_beat=3, half_ticks=div * 2)
    check("a held chord restates, never splits",
          bars == ["Bb7", "Bb7"], str(bars))
    check("compress speaks runs",
          chartedit.compress(["Bb7", "Bb7", "Eb7"]) == "Bb7 x2, Eb7")

    line, fb, spoken = chartedit.known_changes("blues", "f", "Bb")
    check("it knows the blues, transposed",
          fb == 12 and line.startswith("F7, Bb7") and
          "Gm7, C7" in line, line)
    check("sharp keys spell sharp",
          "F#7" in chartedit.known_changes("blues", "b", "C")[0])
    check("minor blues in the chart's own key",
          chartedit.known_changes("minor blues", None,
                                  "Eb minor")[0].startswith("Ebm7 x4"))
    plans, gaps = chartedit.parse_form(
        "12 bar blues in b flat, solos over the blues 5 times")
    check("a blues clause arrives with its form",
          not gaps and plans[0]["form"] == ("blues", "b flat")
          and plans[0]["bars"] == 12 and plans[1]["use"] == "blues")

    t, g = chartedit.extract_globals(
        "swing at 160, 8 bar intro, in the key of e flat minor")
    check("tune-level words leave the breath",
          g["tempo"] == "160" and g["key"] == "Eb minor"
          and "swing" in t and "160" not in t, str((t, g)))
    plans, gaps = chartedit.parse_form(
        "8 bar intro in two feel, 16 bar head bossa, solos over the "
        "head latin, head out")
    check("a feel said in a section's words is that section's feel",
          [(p["name"], p.get("feel")) for p in plans[:3]]
          == [("intro", "two feel"), ("head", "bossa"), ("solos", "latin")]
          and plans[2]["use"] == "head" and not gaps, str(plans))
    plans, _ = chartedit.parse_form("8 bar intro with a latin feel, head "
                                    "is 32 AABA swing")
    import chartnew
    band, _ = chartnew.band_from_words("congas, bongos, bell, bells")
    check("band words: 'bell' is the cowbell, 'bells' the glockenspiel",
          ("bell", "cowbell") in band and band[-1][1] == "glockenspiel",
          str(band))
    ctx_ = {"perc_labels": ["congas", "bell"]}
    with redirect_stdout(io.StringIO()):
        got = chartedit._perc_plays(ctx_, ["piano: solo", "congas: tacet"])
    check("the desk keeps the percussion playing unless it was named",
          got == ["bell: groove"], str(got))
    check("'with a latin feel' and a feel after the form name read too",
          plans[0]["feel"] == "latin" and plans[1]["feel"] == "swing"
          and plans[1]["bars"] == 32)
    plans, gaps = chartedit.parse_form("i got rhythm, solos over "
                                       "the form twice")
    check("rhythm changes answers to its aliases",
          not gaps and plans[0]["form"][0] == "rhythm changes"
          and plans[0]["bars"] == 32)
    secs, spoken = chartedit.form_carve_sections("rhythm changes",
                                                 None, "Bb")
    check("rhythm changes carves lettered eights",
          [n for n, _ in secs] == ["A", "A2", "B", "A3"]
          and secs[2][1] == "D7 x2, G7 x2, C7 x2, F7 x2")

    check("degrees speak in the key",
          sp("two five one in c") == "Dm7 G7 Cmaj7")
    check("degrees follow the chart's key",
          chartedit.parse_spoken_chords("1, 4, 5, 1", key="Eb") ==
          "Ebmaj7, Abmaj7, Bb7, Ebmaj7")
    check("minor keys get minor degrees",
          chartedit.parse_spoken_chords("two five one",
                                        key="Eb minor") ==
          "Fm7b5 Bb7 Ebm7")
    check("borrowed flat seven arrives dominant",
          chartedit.parse_spoken_chords("one, flat seven", key="C") ==
          "Cmaj7, Bb7")
    check("a quality word overrides the diatonic default",
          chartedit.parse_spoken_chords("four minor, one", key="C") ==
          "Fm, Cmaj7")
    check("triads speak", sp("C triad, F, G triad") == "C, F, G")

    who2 = chartedit.parse_who(
        "everybody in; bass walks, piano comps; trumpet lays out",
        ["trumpet", "piano", "bass"], ["all"], {})
    check("bandstand who-plays speaks",
          who2 == ["all: groove", "bass: groove", "piano: groove",
                   "trumpet: tacet"], str(who2))
    who2 = chartedit.parse_who("horns hits on 1, 2+, 4; voice sings "
                               "the melody", ["voice"], ["horns"], {},
                               melody_range=(9, 20))
    check("hits keep their commas, the melody knows its bars",
          who2 == ["horns: hits on 1, 2+, 4",
                   "voice: from demo bars 9-20"], str(who2))

    plans, gaps = chartedit.parse_form(
        "it opens quiet with a 4 bar piano intro, then a blues in g, "
        "big shout 16, ends on the head")
    check("a story parses whole",
          not gaps and [p["name"] for p in plans] ==
          ["piano intro", "head", "shout", "out"], str(plans))
    check("moods become labels",
          plans[0].get("mood") == "quiet"
          and plans[2].get("mood") == "big")
    check("solos over the form prefer the form",
          chartedit._resolve_family("form", plans, {})[0]["name"] ==
          "head")

    nl = chartedit.notes_from_words(
        "c5 quarter, down a eighth, g eighth, e half tied to quarter")
    check("a spoken line becomes the notes grammar",
          nl == "C5 q, A4 e, G4 e, E4 h+q", nl)
    ticks, err = chartedit.notes_ticks(nl)
    check("the compiler's own parser counts it",
          err is None and ticks == 120)
    check("octaves follow the line",
          chartedit.notes_from_words("f4 quarter, g eighth, "
                                     "b flat half") ==
          "F4 q, G4 e, Bb4 h")
    check("rests square a line to the barline",
          chartedit._rest_pieces(36) == "rest q, rest e")
    check("dominant is a word",
          chartedit.parse_spoken_chords("one dominant x4", key="G")
          == "G7 x4")
    who3 = chartedit.parse_who("bass in at 5", ["bass"], [], {})
    check("a story entrance becomes a build cue",
          who3 == ["build: add bass at 5"], str(who3))

    # the audit's three features: key changes, hairpins, swing 16ths
    import chartc as _cc
    tmp3 = tempfile.mkdtemp()
    kpath = os.path.join(tmp3, "k.chart")
    with open(kpath, "w", encoding="utf-8") as f:
        f.write("title: K\nkey: Db\nmeter: 4/4\ntempo: 100\n"
                "feel: swing 16ths\n\nband:\n  trumpet\n  piano\n\n"
                "section A, 8 bars\n"
                "  chords: Db7 x4, Gb7 x4\n"
                "  at bar 5: key D\n"
                "  piano: groove, cresc bars 2-4, dim bars 6-8\n")
    kchart = _cc.parse_chart(kpath)
    check("a key event lands in the key map",
          kchart["keys"] == [(1, (-5, "major")), (5, (2, "major"))],
          str(kchart.get("keys")))
    with redirect_stdout(io.StringIO()):
        _cc.compile_chart(kpath, tmp3)
    tp = open(os.path.join(tmp3, "K — trumpet.musicxml"),
              encoding="utf-8").read()
    pn = open(os.path.join(tmp3, "K — piano.musicxml"),
              encoding="utf-8").read()
    # played material across a modulation spells each side in its key
    import re as _re
    kn = [(0, 400, 61, 90), (480, 880, 65, 90), (960, 1360, 68, 90),
          (1920, 2300, 66, 90), (2400, 2800, 73, 90)]
    import smf as _smf
    _smf.write(os.path.join(tmp3, "km.mid"), kn, 480, 100)
    kc = os.path.join(tmp3, "km.chart")
    open(kc, "w").write('title: KM\nkey: Db\nmeter: 4/4\ntempo: 100\n\n'
                        'band:\n  flute, demo "km.mid"\n\nsection A, 2 '
                        'bars\n  chords: Db, D\n  at bar 2: key D\n'
                        '  flute: from demo bars 1-2\n')
    kbuf = io.StringIO()
    with redirect_stdout(kbuf):
        _cc.compile_chart(kc, os.path.join(tmp3, "kmb"))
    kx = open(os.path.join(tmp3, "kmb", "KM — flute.musicxml")).read()
    sp_ = _re.findall(r'<step>(\w)</step>(?:<alter>(-?\d)</alter>)?'
                     r'<octave>', kx)
    ksaid = subprocess.run([sys.executable, os.path.join(HERE,
                                                         "chartread.py"),
                            kc, "--part", "flute"], capture_output=True,
                           text=True).stdout
    check("a figure crossing a key change spells each side in its key",
          sp_ == [('D', '-1'), ('F', ''), ('A', '-1'), ('F', '1'),
                  ('C', '1')]
          and "F sharp 4" in ksaid and "G flat" not in ksaid
          and "peak C#5 at bar 2" in kbuf.getvalue(),
          str(sp_) + ksaid[-200:])
    check("the restated key is each part's own written key",
          "<key><fifths>4</fifths>" in tp
          and "<key><fifths>2</fifths>" in pn)
    import chartengrave as _ce
    import re as _re
    check("a key change cancels what the new key drops",
          _ce.cancelled(-5, 0) == 5 and _ce.cancelled(3, 2) == 1
          and _ce.cancelled(-5, 2) == 0 and _ce.cancelled(0, 3) == 0
          and _ce.cancelled(2, 4) == 0)
    cpath = os.path.join(tmp3, "c.chart")
    with open(cpath, "w", encoding="utf-8") as f:
        f.write("title: C\nkey: Db\nmeter: 4/4\ntempo: 100\n\n"
                "band:\n  piano\n\nsection A, 8 bars\n"
                "  chords: Db7 x4, C7 x4\n  at bar 5: key C\n"
                "  piano: groove\n")
    with redirect_stdout(io.StringIO()):
        _cc.compile_chart(cpath, tmp3)
    cx = open(os.path.join(tmp3, "C — piano.musicxml"),
              encoding="utf-8").read()
    cms, why = _ce.parse_part(cx, _re.search(r'<part id="([^"]+)"',
                                            cx).group(1))
    check("the page cancels Db's five flats going to C",
          cms and cms[4]['show'].get('cancel') == (-5, 5)
          and 'cancel' not in cms[0]['show'], str(why))
    ok, why = _ce.engrave(os.path.join(tmp3, "C — piano.musicxml"),
                          os.path.join(tmp3, "c.pdf"))
    check("and the cancelling page draws", ok, str(why))
    check("hairpins land as wedges",
          pn.count('<wedge type="crescendo"') == 1
          and pn.count('<wedge type="diminuendo"') == 1
          and pn.count('<wedge type="stop"') == 2)
    listen = open(os.path.join(tmp3, "K — for listening.musicxml"),
                  encoding="utf-8").read()
    check("swing 16ths reaches the listening document",
          "<swing-type>16th</swing-type>" in listen)
    import chartaudio as _ca
    sw = [(0.0, (2 / 3, 0.5))]
    check("the 16th swing warp swings the half-beat",
          abs(_ca._warp(0.25, sw) - (2 / 3) * 0.5) < 1e-9
          and abs(_ca._warp(0.5, sw) - 0.5) < 1e-9)
    shutil.rmtree(tmp3, ignore_errors=True)

    bars = _cc.parse_bars("D9, /C, Bmi9, Ami7, D7(#9) x2, "
                          "( F7, Bb7 ) x2", "the 8BBB spellings")
    check("compact minor keys read",
          _cc.parse_key("Bm") == (2, "minor")
          and _cc.parse_key("Ebmin") == (-6, "minor"))
    plans, gaps = chartedit.parse_form("intro 4, pre-chorus 4, "
                                       "chorus 8")
    check("hyphenated section names speak",
          not gaps and plans[1]["name"] == "pre-chorus")
    check("a groove phrase is feel-shaped",
          chartedit._feelish("heavy rock disco")
          and chartedit._feelish("modal bop")
          and not chartedit._feelish("intro"))
    tmp4 = tempfile.mkdtemp()
    dpath = os.path.join(tmp4, "d.chart")
    with open(dpath, "w", encoding="utf-8") as f:
        f.write("title: D\nkey: Bm\nmeter: 4/4\n\nband:\n  piano\n\n"
                "section P.C., 4 bars\n  chords: Bm x4\n")
    dc = _cc.parse_chart(dpath)
    check("P.C. is a legal section name in a Bm chart",
          dc["sections"][0]["name"] == "P.C.")
    with open(dpath, "w", encoding="utf-8") as f:
        f.write("title: T\nlyricist: Linda Hennrick\n"
                "from: Mother/Earthbound\nrev: 12/18/24\n"
                "number: 5\nkey: C\nmeter: 4/4\n\nband:\n"
                "  piano\n\nsection A, 2 bars\n  chords: C x2\n")
    with redirect_stdout(io.StringIO()):
        _cc.compile_chart(dpath, tmp4)
    px = open(os.path.join(tmp4, "T — piano.musicxml"),
              encoding="utf-8").read()
    with open(dpath, "w", encoding="utf-8") as f:
        f.write("title: H\nkey: C\nmeter: 4/4\ntempo: 120\n\n"
                "band:\n  trumpet\n  piano\n\n"
                "figure line, 1 bars:\n  notes: C5 w\n\n"
                "section A, 2 bars\n  chords: C, G7\n"
                "  at bar 2: fermata\n"
                "  trumpet: figure line, dyn subito p\n")
    with redirect_stdout(io.StringIO()):
        _cc.compile_chart(dpath, tmp4)
    hx = open(os.path.join(tmp4, "H — trumpet.musicxml"),
              encoding="utf-8").read()
    check("a fermata event lands on every part's last note",
          hx.count("<fermata/>") == 1 and "subito" in hx)
    import chartaudio as _ca2
    hplan = _ca2.parse_score(
        os.path.join(tmp4, "H — for listening.musicxml"))
    check("the hold reaches playback, rests included",
          hplan["holds"] and abs(hplan["holds"][0][0] - 8.0) < 0.01,
          str(hplan["holds"]))

    import re
    import chartengrave as _cg
    sx = open(os.path.join(tmp4, "T — score.musicxml"),
              encoding="utf-8").read()
    spids = re.findall(r'<score-part id="([^"]+)"', sx)
    spdf = os.path.join(tmp4, "score.pdf")
    ok, why = _cg.engrave_score(sx, spids,
                                {p: p for p in spids}, spdf)
    whole = open(spdf, "rb").read().decode("latin-1", "replace")
    check("a conductor's page is landscape",
          ok and f"/MediaBox [0 0 {_cg.PAGE_H} {_cg.PAGE_W}]" in whole,
          why or "no landscape MediaBox")
    check("families and abbreviations read",
          _cg._score_family("brass.trombone.bass") == "brass"
          and _cg._score_family("pluck.bass.electric") == "rhythm"
          and _cg._abbrev("bass trombone 2") == "Bass Trom. 2")

    check("the pro title block reaches the page's XML",
          "<work-number>5</work-number>" in px
          and '<creator type="lyricist">Linda Hennrick</creator>' in px
          and "<source>Mother/Earthbound</source>" in px
          and '<creator type="revision">12/18/24</creator>' in px)
    shutil.rmtree(tmp4, ignore_errors=True)

    more = _cc.parse_bars("C7sus, Gb13(#11), Fmi11",
                          "the Life Will Change page")
    pb = _cc.parse_bars("Db13sus, F7(#9b13), D/F",
                        "the praise break")
    check("the Grammy chart's spellings parse",
          pb[0][0][1][2] == "13sus"
          and pb[1][0][1][2] == "7#9b13"
          and pb[2][0][1] == ("D", 0, "maj", "F"), str(pb))
    check("the P5 keyboard book's spellings parse",
          more[0][0][1][2] == "7sus4"
          and more[1][0][1][2] == "13#11"
          and more[2][0][1][2] == "m11", str(more))

    import chartengrave as _ce
    faces = _ce.text_faces("")
    if faces:
        pdf = _ce.Pdf(faces=faces)
        w = pdf.tw("ばか", 9, "H")
        check("kana lyrics find the fallback face and a real width",
              w > 5 and "JPFALL" in pdf.faces, str(w))
    else:
        skip("kana fallback face", "no embedded faces available")
    check("the working book's chord spellings parse",
          bars[1][0][1] == ("D", 0, "9", "C")
          and bars[2][0][1] == ("B", 0, "m9", None)
          and bars[3][0][1] == ("A", 0, "m7", None)
          and bars[4][0][1] == ("D", 0, "7#9", None)
          and len(bars) == 10, str(bars))

    tmp2 = tempfile.mkdtemp()
    tpath = os.path.join(tmp2, "t.chart")
    with open(tpath, "w", encoding="utf-8") as f:
        f.write("title: T\nkey: Bb\nmeter: 4/4\n\nband:\n  piano\n\n"
                "chords head: Bb7, Eb7\n\nsection head, 2 bars\n"
                "  use chords head\n")
    chartedit.transpose_chart(tpath, "c", "Bb")
    moved = open(tpath, encoding="utf-8").read()
    check("transpose moves key and every chords line",
          "key: C" in moved and "chords head: C7, F7" in moved
          and "use chords head" in moved, moved)
    lines = chartedit._lines(tpath)
    span = chartedit._section_span(lines, "head")
    check("a section's span finds its block",
          span is not None and "section head" in lines[span[0]])
    chartedit._save_lines(
        tpath, chartedit._set_section_chords(lines, span, "G7 x2"))
    check("section chords replace in place",
          "  chords: G7 x2" in open(tpath, encoding="utf-8").read())
    shutil.rmtree(tmp2, ignore_errors=True)

    who = chartedit.parse_who("horns tacet; trumpet from demo bars "
                              "5-12, piano grooves",
                              ["trumpet", "piano"], ["horns"], {})
    check("who plays parses to directives",
          who == ["horns: tacet", "trumpet: from demo bars 5-12",
                  "piano: groove"], str(who))

    # the whole conversation, scripted: breath, carve, spoken blues,
    # same-as, solos over the form, out on the last A
    tmp = tempfile.mkdtemp()
    chart_path = os.path.join(tmp, "t.chart")
    with open(chart_path, "w", encoding="utf-8") as f:
        f.write("title: T\nkey: Bb\nmeter: 4/4\ntempo: 160\n\nband:\n"
                "  trumpet\n  piano\n  bass = electric bass\n"
                "  drums = drum set\n\nsection A, 40 bars\n"
                "  chords: nc x40\n")
    real_vocab = chartedit.VOCAB_PATH
    real_dir = chartedit.CONFIG_DIR
    real_stdin = sys.stdin
    chartedit.CONFIG_DIR = tmp
    chartedit.VOCAB_PATH = os.path.join(tmp, "vocab.json")
    sys.stdin = io.StringIO(
        "8 bar intro, head is 32 AABA, solos over the head twice, "
        "out on the last A\n"          # the breath
        "\n"                           # carve (default)
        "\n"                           # intro chords: none yet
        "piano grooves\n"              # intro who
        "b flat seven 2 bars, e flat seven 2 bars, b flat seven "
        "2 bars, f seven, b flat seven\n"   # A chords
        "\n"                           # A who: defaults
        "\n"                           # A2 same as A (yes)
        "\n"                           # A2 who
        "e flat seven 4 bars, b flat seven 2 bars, f seven 2 bars\n"
        "\n"                           # B who
        "\n"                           # A3 same as A
        "\n"                           # A3 who
        "trumpet, piano\n"             # who solos
        "\n")                          # out who
    try:
        with redirect_stdout(io.StringIO()) as out:
            chartedit.edit(chart_path)
    finally:
        sys.stdin = real_stdin
        chartedit.VOCAB_PATH = real_vocab
        chartedit.CONFIG_DIR = real_dir
    said = out.getvalue()
    check("the session ends written and checked",
          "Written and checked: 7 section(s), 112 bars" in said, said)
    import chartc
    final = chartc.parse_chart(chart_path)
    names = [s["name"] for s in final["sections"]]
    check("the form landed in order",
          names == ["intro", "A", "A2", "B", "A3", "solos", "out"],
          str(names))
    check("solos ride the named head progression",
          "head" in final["chords"] and
          len(final["chords"]["head"]) == 32)
    solos = final["sections"][5]
    check("solos repeat and resolve",
          solos["repeat"] == 2 and solos["bars"] == 32
          and len(solos["content"]) == 32)
    check("the out plays the last A's changes",
          final["sections"][6]["content"] ==
          final["sections"][4]["content"])
    check("who landed as directives",
          ("piano", "groove") in [(t, i) for t, i, _ in
                                  final["sections"][0]["directives"]]
          and [(t, i) for t, i, _ in solos["directives"]] ==
          [("trumpet", "solo"), ("piano", "solo")])
    check("the scaffold section is gone", "A, 40 bars" not in
          open(chart_path, encoding="utf-8").read())

    # re-saying a line replaces the figure instead of stacking one
    sys.stdin = io.StringIO(
        "notes for piano in the intro\n"
        "c4 quarter, d quarter, e quarter, f quarter, g whole\n"
        "\n\n"          # bar 1, write it
        "notes for piano in the intro\n"
        "c3 quarter, d quarter, e quarter, f quarter, g whole\n"
        "\n\n"          # bar 1, write it (replaces)
        "\n")
    try:
        with redirect_stdout(io.StringIO()) as out:
            chartedit.edit(chart_path)
    finally:
        sys.stdin = real_stdin
    said = out.getvalue()
    final = chartc.parse_chart(chart_path)
    check("a re-said line replaces its figure",
          "Replaced piano's old line" in said
          and len(final["figures"]) == 1
          and "C3 q" in open(chart_path, encoding="utf-8").read(),
          said)
    # a stdin that answers forever without ever ending: on 2026-09-25
    # this exact shape wrote 2.4 TB of one prompt into a log and
    # filled the disk, because ask.eof only ever catches a real end
    class _Endless:
        def readline(self):
            return "\n"

    sys.stdin = _Endless()
    chartedit.ask.same, chartedit.ask.repeats = None, 0
    chartedit.ask.eof = False
    try:
        with redirect_stdout(io.StringIO()) as out:
            try:
                chartedit._ask_bars({"name": "heavy disco",
                                     "bars": None})
                ended = "it kept going"
            except SystemExit as e:
                ended = str(e)
    finally:
        sys.stdin = real_stdin
        chartedit.ask.same, chartedit.ask.repeats = None, 0
    said = out.getvalue()
    check("a question that never gets through stops the run",
          "runs away" in ended and "nothing written" in ended, ended)
    check("and it stops after a handful of tries, not a terabyte",
          said.count("heavy disco") <=
          2 * (chartedit.ASK_REPEAT_LIMIT + 1)
          and len(said) < 4000, f"{len(said)} bytes")

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


_DUR = {'w': 96, 'h': 48, 'q': 24, 'e': 12, 's': 6, 't': 3}
_TYPE = {'w': 'whole', 'h': 'half', 'q': 'quarter', 'e': 'eighth',
         's': '16th', 't': '32nd'}


def _mx(bars, fifths=0, time=(4, 4), clef='G', title='Test', perc=None):
    """A one-part MusicXML score from compact bars, for the braille tests
    (made-up material; nobody's music). A bar is a list of tokens, or a
    tuple of two lists for two voices on the staff. Tokens:
      "C5 q"  "Bb4 e."  "C5+E5+G5 h" (a chord)  "r q"  "r w" (whole bar)
      "C5 q ~" (tied into the next note of that pitch)  "D4 q slash"
      "C5 q cue"  "t3 C5 e" (triplet)  "t6 C5 s" (sextuplet)
      "{C7}" a chord symbol   '"words"' a direction   "#A" rehearsal
      "|:" ":|" "||" "|]" bar lines   "[1" "[2" voltas   "segno" "coda"
    """
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<score-partwise version="3.1"><part-list>',
           '<score-part id="P1"><part-name>Test part</part-name>'
           + (f'<score-instrument id="P1-I1"><instrument-name>{perc}'
              '</instrument-name></score-instrument>' if perc else '')
           + '</score-part></part-list><part id="P1">']
    beats, unit = time
    full = beats * 96 // unit
    held = {}
    grand = any(isinstance(b, dict) for b in bars)
    for bi, bar in enumerate(bars):
        out.append(f'<measure number="{bi + 1}">')
        if bi == 0:
            sign, line = (('percussion', 2) if perc else
                          ('G', 2) if clef == 'G' else ('F', 4))
            clefs = (f'<clef><sign>{sign}</sign><line>{line}</line></clef>'
                     if not grand else
                     '<staves>2</staves><clef number="1"><sign>G</sign>'
                     '<line>2</line></clef><clef number="2"><sign>F</sign>'
                     '<line>4</line></clef>')
            out.append(f'<attributes><divisions>24</divisions><key>'
                       f'<fifths>{fifths}</fifths></key><time><beats>'
                       f'{beats}</beats><beat-type>{unit}</beat-type></time>'
                       f'{clefs}</attributes>')
        if isinstance(bar, dict):
            voices = (bar['r'], bar['l'])
        else:
            voices = bar if isinstance(bar, tuple) else (bar,)
        right = ''
        for vi, toks in enumerate(voices):
            if vi:
                out.append(f'<backup><duration>{full}</duration></backup>')
            for t in toks:
                if t in ('ped', '*'):
                    out.append('<direction placement="below"><direction-'
                               'type><pedal type="'
                               + ('start' if t == 'ped' else 'stop') +
                               '"/></direction-type></direction>')
                    continue
                if t.startswith('{'):
                    root, kind = t[1], t[2:-1]
                    out.append(f'<harmony><root><root-step>{root}'
                               f'</root-step></root><kind text="{kind}">'
                               f'dominant</kind></harmony>')
                    continue
                if t.startswith('"'):
                    out.append('<direction placement="above"><direction-'
                               f'type><words>{t[1:-1]}</words></direction-'
                               'type></direction>')
                    continue
                if t.startswith('#'):
                    out.append('<direction placement="above"><direction-'
                               f'type><rehearsal>{t[1:]}</rehearsal>'
                               '</direction-type></direction>')
                    continue
                if t in ('segno', 'coda'):
                    out.append('<direction placement="above"><direction-'
                               f'type><{t}/></direction-type></direction>')
                    continue
                if t == '|:':
                    out.append('<barline location="left"><bar-style>heavy-'
                               'light</bar-style><repeat direction="forward"'
                               '/></barline>')
                    continue
                if t in ('[1', '[2'):
                    out.append('<barline location="left"><ending number="'
                               f'{t[1]}" type="start"/></barline>')
                    continue
                if t in (':|', '||', '|]'):
                    right = t
                    continue
                parts = t.split()
                stf = f'<staff>{vi + 1}</staff>' if grand else ''
                tmod = None
                if parts[0] in ('t3', 't6'):
                    tmod = int(parts[0][1])
                    parts = parts[1:]
                pitch, dur = parts[0], parts[1]
                flags = parts[2:]
                d = _DUR[dur[0]]
                dots = dur.count('.')
                d = d * (2 - 1 / 2 ** dots)
                if tmod:
                    d = d * (2 if tmod == 3 else 4) / tmod
                d = int(d)
                tm = ('' if not tmod else
                      f'<time-modification><actual-notes>{tmod}</actual-'
                      f'notes><normal-notes>{2 if tmod == 3 else 4}</normal-'
                      f'notes></time-modification>')
                if pitch == 'r':
                    whole = ' measure="yes"' if dur == 'w' and \
                        len(toks) == 1 else ''
                    out.append(f'<note><rest{whole}/><duration>{d}</duration>'
                               f'<voice>{vi + 1}</voice>{stf}<type>{_TYPE[dur[0]]}'
                               f'</type>{"<dot/>" * dots}{tm}</note>')
                    continue
                for k, p in enumerate(pitch.split('+')):
                    step, octv = p[0], p[-1]
                    alter = {'b': -1, '#': 1}.get(p[1], 0) if len(p) > 2 \
                        else 0
                    key = (vi, p)
                    stop = held.pop(key, False)
                    start = '~' in flags
                    if start:
                        held[key] = True
                    ties = ('<tie type="stop"/>' if stop else '') + \
                        ('<tie type="start"/>' if start else '')
                    tied = ('<tied type="stop"/>' if stop else '') + \
                        ('<tied type="start"/>' if start else '')
                    ly = [f for f in flags if f.startswith('ly=')]
                    lyric = ''
                    if ly and k == 0:
                        word, _, kind = ly[0][3:].partition('/')
                        lyric = (f'<lyric><syllabic>{kind or "single"}'
                                 f'</syllabic><text>{word}</text></lyric>')
                    head = next((f[2:] for f in flags if f.startswith('h=')),
                                None) if k == 0 else None
                    where = (f'<unpitched><display-step>{step}</display-step>'
                             f'<display-octave>{octv}</display-octave>'
                             '</unpitched>' if perc else
                             f'<pitch><step>{step}</step>' +
                             (f'<alter>{alter}</alter>' if alter else '') +
                             f'<octave>{octv}</octave></pitch>')
                    out.append(
                        '<note>' + ('<cue/>' if 'cue' in flags else '') +
                        ('<chord/>' if k else '') + where +
                        f'<duration>{d}'
                        f'</duration>{ties}<voice>{vi + 1}</voice>{stf}<type>'
                        f'{_TYPE[dur[0]]}</type>{"<dot/>" * dots}{tm}' +
                        ('<notehead>slash</notehead>' if 'slash' in flags
                         else f'<notehead>{head}</notehead>' if head
                         else '') +
                        (f'<notations>{tied}</notations>' if tied else '') +
                        lyric + '</note>')
        if right == ':|':
            out.append('<barline location="right"><bar-style>light-heavy'
                       '</bar-style><repeat direction="backward"/></barline>')
        elif right == '||':
            out.append('<barline location="right"><bar-style>light-light'
                       '</bar-style></barline>')
        elif right == '|]':
            out.append('<barline location="right"><bar-style>light-heavy'
                       '</bar-style></barline>')
        out.append('</measure>')
    out.append('</part></score-partwise>')
    return '\n'.join(out)


def check_braille():
    """BRF output (BANA Music Braille Code 2015): exact forms for the
    rules, then every part read back by the separate proofreader."""
    import chartbraille as cb
    import chartbrailleread as rd
    import chartengrave as ce

    check("proofreader: a short word closed by dot 3 (>OUT') doesn't "
          "hide a long expression wrapping onto the next line",
          rd._open_expr(">OUT'M     M  M >HOLD1 THEN HORNS FALL1 THEN")
          and not rd._open_expr(">OUT'M  M  M"))

    def brf(bars, chords=True, **kw):
        text, why = cb.part_to_brf(_mx(bars, **kw), 'P1', 'Test',
                                   'Test part', chords=chords)
        return text

    def music(text):
        """The music lines, page furniture and heading gone."""
        lines = text.replace('\r\n', '\n').replace('\f', '').split('\n')
        return [l for l in lines[lines.index('') + 2:] if l.strip()]

    def score_notes(bars, **kw):
        xml = _mx(bars, **kw)
        ms, _ = ce.parse_part(xml, 'P1')
        out = []
        for m in ms:
            ev = sorted((e for e in m['events'] if e[2] == 1),
                        key=lambda e: e[0])
            for side in cb._sides(m, ev):
                for _p, ns, _s, _v in side:
                    pitched = [x for x in ns if not x.rest and not x.slash]
                    if not pitched:
                        continue
                    w = (max if cb._down(m) else min)(pitched, key=cb._dia)
                    rest = sorted((x for x in pitched if x is not w),
                                  key=lambda x: abs(cb._dia(x) - cb._dia(w)))
                    for x in [w] + rest:
                        a = x.alter or 0
                        out.append((x.step + ('#' * a if a > 0 else 'b' * -a)
                                    + str(x.octave), {
                                        'whole': 'W', '16th': 'W',
                                        'half': 'H', '32nd': 'H',
                                        'quarter': 'Q', '64th': 'Q',
                                        'eighth': 'E', '128th': 'E'}[x.ntype],
                                    x.dots))
        return out

    # BANA 5.3-1, the music line: plain rests for two bars, the numbered
    # form for four, an octave mark only after the number
    bars = [['F2 h', 'r q'], ['r w'], ['r w'], ['G2 h', 'r q'], ['r w'],
            ['r w'], ['r w'], ['r w'], ['C2 h.', '|]']]
    got = music(brf(bars, time=(3, 4), clef='F'))
    check("braille: BANA 5.3-1 multi-measure rests",
          got == ['#A ^QV MM RV #DM ^N\'<K'], repr(got))

    # 3.2: octave marks by the interval rule, first note of a line marked
    got = music(brf([['C4 q', 'E4 q', 'G4 q', 'C5 q'],
                     ['G4 q', 'C4 q', 'B3 q', 'C4 q', '|]']]))
    check("braille: octave marks follow 3.2.2",
          got == ['#A "?$\\.? "\\?W?<K'], repr(got))

    # 17.1 / 17.1.1: repeat and voltas touch the measure's first sign
    got = ' '.join(music(brf([['|:', 'C5 w'], ['[1', 'D5 w', ':|'],
                              ['[2', 'E5 w', '|]']])))
    check("braille: repeat and voltas attach (17.1)",
          '<7.Y' in got and '#1' in got and "<2" in got and '#2' in got,
          got)

    # 6.5 / 7.1 heading: key and time together, no space
    text = brf([['C5 w', '|]']], fifths=-3, time=(3, 4))
    check("braille: heading carries key and time as one sign",
          '<<<#C4' in text.replace('\r\n', '\n'), text)

    # 9.1: a chord from its top note, intervals downward, nearest first;
    # the transcriber's note says which way they read (9.2)
    text = brf([['D5+Ab4+F4+Bb3 q', 'r q', 'r h', '|]']])
    m = ' '.join(music(text))
    check("braille: chord as written note and intervals (9.1)",
          '.:<#0<+' in m, m)
    check("braille: interval direction stated (9.2)",
          'INTERVALS READING DOWNWARD' in ' '.join(text.split()))
    text = brf([['Bb2+F3+D4 q', 'r q', 'r h', '|]']], clef='F')
    check("braille: a bass part writes the bottom note, reading up",
          'READING UPWARD' in ' '.join(text.split()) and
          '^W9' in ' '.join(music(text)), ' '.join(music(text)))

    # 11.1.1: two voices on one staff, the higher first, in-accord
    got = ' '.join(music(brf([(['A4 h', 'G4 h'], ['D5 w']), ['C5 w', '|]']])))
    check("braille: two voices written as a full-measure in-accord",
          '<>' in got and got.index('.Z') < got.index('<>'), got)

    # 10.1.3 and Gould: a flat tied over the bar is not restated there,
    # but a later note of that pitch in the new bar shows it again
    got = ' '.join(music(brf([['r h', 'r q', 'Ab4 q ~'],
                              ['Ab4 q', 'Bb4 q', 'Ab4 q', 'r q', '|]']])))
    check("braille: accidental after a held-over tie shows again",
          '@C [<W<[' in got, got)

    # 2.4: a bar that reads two ways takes value signs
    got = ' '.join(music(brf([['r h', 'G5 s', 'F5 t', 'E5 t', 'C5 s',
                               'F5 e.', 'C5 s', 'D5 s', '|]']])))
    check("braille: value signs where a bar is ambiguous (2.4)",
          ',<1' in got and '^<1' in got, got)
    got = ' '.join(music(brf([['C5 e.', 'D5 s', 'E5 q', 'F5 h', '|]']])))
    check("braille: no value signs where only one reading fits",
          ',<1' not in got and '^<1' not in got, got)

    # 8.5: sextuplets, doubled for a run of four, single on the last
    six = ['t6 C5 s'] * 24
    got = ' '.join(music(brf([six + ['|]']])))
    check("braille: a run of sextuplets doubles its sign (8.5)",
          got.count("_6_6'") == 1 and got.count("_6'") == 2, got)

    # 21.6: a cue note is marked small
    got = ' '.join(music(brf([['C5 q cue', 'D5 q cue', 'r h', '|]']])))
    check("braille: cue notes carry the small-type sign (21.6)",
          got.count(',5') == 2, got)

    # slashes inside a bar: rests under the word, never pitched notes
    got = ' '.join(music(brf([['{C7}', 'B4 q slash', 'B4 q slash',
                               'E5 q', 'F5 q', '|]']])))
    check("braille: part-bar slashes are rests under 'slashes'",
          '>SLASHES' in got and "'VV" in got and '?' not in
          got.split('>SLASHES')[1][:4], got)

    # 20.2: road-map words after the bar they close
    got = ' '.join(music(brf([['C5 w', '"To Coda"'], ['D5 w', '||',
                              '"D.S. al Coda"'], ['coda', 'E5 w', '|]']])))
    check("braille: To Coda follows its measure with the coda sign",
          "+L >TO CODA>" in got, got)
    check("braille: D.S. follows the bar line, closed",
          "<K' >D'S' AL CODA>" in got, got)

    # page layout: 40 cells, 25 lines, form feeds between pages
    long_bars = [['C5 e', 'D5 e', 'E5 e', 'F5 e', 'G5 e', 'A5 e', 'B5 e',
                  'C6 e']] * 120 + [['C5 w', '|]']]
    text = brf(long_bars)
    pages = text.split('\f')
    lines = [l for p in pages for l in p.split('\r\n')]
    check("braille: no line wider than 40 cells",
          max(len(l) for l in lines) <= 40)
    check("braille: pages of at most 25 lines",
          all(len([l for l in p.split('\r\n') if l != '']) <= 25
              for p in pages) and len(pages) > 1)

    # the build path: a made-up chart, compiled, brailled, proofread
    import chart
    import chartc
    tmp = tempfile.mkdtemp()
    try:
        cp = os.path.join(tmp, "b.chart")
        open(cp, "w").write(
            'title: Braille Test\nkey: Bb\nmeter: 4/4\ntempo: 120\n\n'
            'band:\n  trumpet\n  piano\n\n'
            'figure line, 2 bars:\n'
            '  notes: Bb4 q, D5 e, F5 e, triplet( G5 e, F5 e, Eb5 e ), '
            'D5 q, C5 h+q, rest q\n\n'
            'section A, 2 bars\n  chords: Bb, Eb7\n'
            '  trumpet: figure line\n  piano: groove\n')
        with redirect_stdout(io.StringIO()):
            files = chartc.compile_chart(cp, os.path.join(tmp, "build"))
        with redirect_stdout(io.StringIO()) as out:
            chart.make_braille([f for f in files
                                if f.endswith('.musicxml')
                                and 'for listening' not in f],
                               'Braille Test', tmp,
                               {'braille', 'braille pages'})
        said = out.getvalue()
        brf_path = os.path.join(tmp, "Braille Test — trumpet.brf")
        check("a build writes the part's braille and its dots",
              os.path.exists(brf_path) and os.path.exists(os.path.join(
                  tmp, "Braille Test — trumpet (braille view).pdf")),
              said)
        check("the build proofreads the braille and says so",
              "read back note for note" in said, said)
        check("the build brailles the piano part too, bar over bar",
              os.path.exists(os.path.join(tmp, "Braille Test — piano.brf")),
              said)
        raw = open(brf_path, 'rb').read()
        check("a BRF is plain ASCII with CRLF lines",
              raw.isascii() and b'\r\n' in raw and b'\n\n' not in
              raw.replace(b'\r\n', b''))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 29.3: keyboard parallels — number, hand signs, bars aligned
    kbars = [{'r': ['{C7}', 'E5+C5 h', 'G5+E5 h'],
              'l': ['ped', 'C3 w', '*']},
             {'r': ['F5+C5+A4 q', 'r q', 'D5 h'],
              'l': ['F2+C3 h', 'G2 h']},
             {'r': ['C5 w', '|]'], 'l': ['C3 w', '|]']}]
    got = music(brf(kbars))
    check("braille: keyboard parallel opens with number and hand signs",
          got[0].startswith(' A .>') or got[0].startswith('A .>'), got)
    check("braille: the left hand sits under the right hand sign",
          got[1].index('_>') == got[0].index('.>'), got)
    check("braille: right hand reads intervals down, left hand up",
          '.Q+' in got[0] and '_Q9' in got[1] or '^Q9' in got[1], got)
    check("braille: pedal down before, up after, in the left hand",
          '<C' in got[1] and '*C' in got[1], got)
    check("braille: chord symbols make the parallel's third line",
          any(l.strip().startswith(',C') for l in got), got)
    check("braille: no interval note for keyboard (the hand signs say it)",
          'READING' not in ' '.join(brf(kbars).split()))

    # 35: words over music, syllabic slurs; 36: chords placed by time
    song = [['r h', 'C5 q ly=Twin/begin', 'C5 q ly=kle/end'],
            ['G5 q ly=lit/begin', 'A5 e ly=tle/end', 'B5 e', 'C6 e', 'B5 e',
             'A5 e', 'G5 e'],
            ['F5 q ly=star,', 'F5 q ly=how', 'E5 h ly=I ~'],
            ['E5 h', 'D5 q ly=won/begin', 'E5 e ly=der/end', 'D5 e'],
            ['r w'], ['r w'],
            ['C5 w ly=Up/begin'], ['D5 w ly=above/end'],
            ['G4 w ly=the ~'], ['G4 h', 'r h', '|]']]
    text = brf(song)
    lines = music(text)
    check("braille: a song's words sit at the margin, music from cell 3",
          lines[0].startswith(',TWINKLE') and lines[1].startswith('  '),
          lines)
    m = ' '.join(lines)
    check("braille: a short melisma takes single slurs (35.2)",
          'C' in m.split('"')[1] if '"' in m else False, m)
    check("braille: a long melisma takes the doubled slur (35.2)",
          'CC' in m, m)
    got = cb.proofread(_mx(song), 'P1', text)
    check("braille: the song's words, notes and syllables read back",
          not got, got)
    chord_song = [['{C}', 'C5 q ly=Twin/begin', 'C5 q ly=kle/end',
                   '{G}', 'G5 q ly=twin/begin', 'G5 q ly=kle/end'],
                  ['A5 q ly=lit/begin', '{F}', 'A5 q', 'G5 h ly=tle/end'],
                  ['F5 h ly=star', 'r q', '{C}', 'r q', '|]']]
    text = brf(chord_song)
    lines = music(text)
    check("braille: chords with lyrics form a three-line parallel (36.1)",
          any(l.startswith(',C') or l.startswith(' ,C') for l in lines[:3])
          and lines[2].startswith('  '), lines)
    check("braille: a chord during a syllable takes a hyphen (36.3.3)",
          '-,F' in ' '.join(lines), lines)
    check("braille: chords with lyrics read back",
          not cb.proofread(_mx(chord_song), 'P1', text),
          cb.proofread(_mx(chord_song), 'P1', text))

    # 34: percussion — a kit as an ensemble score, a hand drum single-line
    kit = [['G5+F4 e h=x', 'G5 e h=x', 'G5+C5 e h=x', 'G5 e h=x',
            'G5+F4 e h=x', 'G5 e h=x', 'G5+C5 e h=x', 'G5 e h=circle-x'],
           ['F5 q h=x', 'F5 q h=diamond', 'C5 q h=x', 'C5 q'],
           ['A5+F4 w h=x', '|]']]
    text = brf(kit, perc='Drum Set')
    flat = ' '.join(text.split())
    check("braille: a kit lists its instruments with their notes (33.2)",
          ">HH'" in text and ">SD'" in text and ">BD'" in text, text)
    check("braille: each kit instrument has its own line (34.7)",
          any(l.startswith(">HH'") for l in text.split('\r\n')) and
          any(l.startswith(">BD'") for l in text.split('\r\n')), text)
    check("braille: a meaningful note head gets its sign and a key "
          "(34.4)", 'SIDE STICK' in flat and 'OPEN' in flat, flat)
    check("braille: the kit reads back instrument by instrument",
          not cb.proofread(_mx(kit, perc='Drum Set'), 'P1', text),
          cb.proofread(_mx(kit, perc='Drum Set'), 'P1', text))
    congas = [['A4 q h=x', 'A4 e', 'A4 e', 'F4 q', 'A4 q h=x'],
              ['A4 e', 'A4 e h=x', 'F4 h', 'r q', '|]']]
    text = brf(congas, perc='Congas')
    flat = ' '.join(text.split())
    check("braille: congas read single-line with a key to the drums",
          'LOW CONGA' in flat and 'MUTE' in flat and ">CGA'" not in text,
          flat)
    check("braille: congas read back",
          not cb.proofread(_mx(congas, perc='Congas'), 'P1', text))
    time_ = [['B4 q slash', 'B4 q slash', 'B4 q slash', 'B4 q slash'],
             ['B4 q slash', 'B4 q slash', 'B4 q slash', 'B4 q slash', '|]']]
    text = brf(time_, perc='Drum Set')
    check("braille: time slashes on drums say keep time",
          'KEEP TIME' in ' '.join(text.split()), text)

    # everything above, read back by the proofreader, note for note
    cases = {
        'rests': (bars, {'time': (3, 4), 'clef': 'F'}),
        'chords': ([['D5+Ab4+F4+Bb3 q', 'C5+G4+E4 q', 'r h'],
                    ['B5+G5+D5+A4 h', 'r h', '|]']], {}),
        'bass chords': ([['Bb2+F3+D4 q', 'C3+G3+E4 q', 'r h', '|]']],
                        {'clef': 'F'}),
        'voices': ([(['A4 h', 'G4 h'], ['D5 w']), ['C5 w', '|]']], {}),
        'ties': ([['r h', 'r q', 'Ab4 q ~'],
                  ['Ab4 q', 'Bb4 q', 'Ab4 q', 'r q', '|]']], {}),
        'values': ([['r h', 'G5 s', 'F5 t', 'E5 t', 'C5 s', 'F5 e.',
                     'C5 s', 'D5 s', '|]']], {}),
        'sextuplets': ([six + ['|]']], {}),
        'flats': ([['Bb4 q', 'Eb5 q', 'Ab4 q', 'Db5 q'],
                   ['Gb4 w', '|]']], {'fifths': -6}),
        'long': (long_bars, {}),
        'keyboard': (kbars, {}),
        'song': (song, {}),
        'song with chords': (chord_song, {}),
        'keyboard, long': ([{'r': ['C5+E5+G5 e', 'D5+F5 e'] * 4,
                             'l': ['C3+G3 q'] * 4}] * 40 +
                           [{'r': ['C5 w', '|]'], 'l': ['C3 w', '|]']}], {}),
    }
    for name, (bs, kw) in cases.items():
        for chords in (True, False):
            got, errs = rd.decode(cb.part_to_brf(_mx(bs, **kw), 'P1', 'T',
                                                 'Test part',
                                                 chords=chords)[0])
            want = cb.score_notes(_mx(bs, **kw), 'P1')
            check(f"braille reads back note for note: {name}"
                  f"{'' if chords else ', melody only'}",
                  got == want and not errs,
                  f"{errs[:2]} {[(i, a, b) for i, (a, b) in enumerate(zip(want, got)) if a != b][:3]} {len(want)} vs {len(got)}")


def check_note_off_wins():
    """A note shorter than its instrument's hold or decay ends when it
    ends: the release starts at note-off from wherever the sound is,
    with no one-sample drop later (the Weresax click, 2026-09-28)."""
    import sfz
    import wave as _w
    tmp = tempfile.mkdtemp()
    sr = 44100
    path = os.path.join(tmp, 'tone.wav')
    with _w.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        import array as _a
        import math as _m
        w.writeframes(_a.array('h', [int(12000 * _m.sin(2 * _m.pi * 220 *
                                                        i / sr))
                                     for i in range(sr * 3)]).tobytes())
    open(os.path.join(tmp, 't.sfz'), 'w').write(
        '<region> sample=tone.wav pitch_keycenter=57 ampeg_attack=0.001 '
        'ampeg_hold=1 ampeg_decay=2 ampeg_sustain=0 ampeg_release=0.2\n')
    inst = sfz.SfzInstrument(os.path.join(tmp, 't.sfz'))
    L = inst.render_note(57, 100, 0.25, sr)[0]
    after = L[int(0.25 * sr) + int(0.2 * sr) + 50:]
    check("a short note is silent once its release is done",
          not after or max(abs(x) for x in after) < 1e-3,
          max(abs(x) for x in after) if after else 0)
    worst = max(abs(L[i] - L[i - 1]) for i in range(1, len(L)))
    peak = max(abs(x) for x in L)
    check("no sample-to-sample drop anywhere near the note's size",
          worst < 0.2 * peak, (worst, peak))
    shutil.rmtree(tmp, ignore_errors=True)


def check_fall_keyswitch_any_timing():
    """A fall or doit keyswitch marks the same note whenever the key
    goes down: before the note, while it is held, held across it, or
    just after it ends (Logic's Studio Horns attach it on the fly).
    It never latches onto the notes after (Matthew, 2026-09-28)."""
    import chartdemo as cd
    beat = 480
    notes = [(0, 400, 60, 90), (480, 900, 62, 90), (960, 1400, 64, 90),
             (1440, 1900, 65, 90)]
    fall = lambda sp, sv: sp == 24
    stac = (10, 30, 25, 90)                      # latched staccato first

    def fell(switches):
        gov = cd.assign_keyswitches(notes, [stac] + switches, beat, fall)
        return [on for on, (sp, _v) in sorted(gov.items()) if sp == 24], gov
    f, _ = fell([(420, 440, 24, 90)])
    check("a fall pressed just before a note marks that note",
          f == [480], f)
    f, gov = fell([(700, 720, 24, 90)])
    check("a fall pressed while the note is held marks the held note",
          f == [480], f)
    check("and the notes after keep the latched articulation",
          gov.get(960) == (25, 90) and gov.get(1440) == (25, 90), gov)
    f, _ = fell([(470, 1000, 24, 90)])
    check("a fall key held down marks every note started under it",
          f == [480, 960], f)
    f, _ = fell([(905, 915, 24, 90)])
    check("a fall pressed right after a note ends marks the note it "
          "followed", f == [480], f)
    f, gov = fell([])
    late = cd.assign_keyswitches(notes, [(10, 30, 25, 90),
                                         (560, 580, 26, 90)], beat, fall)
    check("any switch pressed a little late counts for the note it "
          "meant, and latches on", late.get(480) == (26, 90)
          and late.get(960) == (26, 90) and late.get(0) == (25, 90), late)
    mid = cd.assign_keyswitches(notes, [(10, 30, 25, 90),
                                        (800, 820, 26, 90)], beat, fall)
    check("a switch pressed deep into a held note waits for the next",
          mid.get(480) == (25, 90) and mid.get(960) == (26, 90), mid)
    long_note = [(0, 3800, 60, 90), (3840, 4200, 62, 90)]
    trill = lambda sp, sv: sp == 27
    held = cd.assign_keyswitches(long_note, [(10, 30, 25, 90),
                                             (2900, 2920, 27, 90)],
                                 beat, trill)
    check("a gesture fired late in a long held note marks that note, "
          "and the next note keeps its own", held.get(0) == (27, 90)
          and held.get(3840) == (25, 90), held)
    check("a library's fall or doit reads as a one-note gesture",
          cd.ks_meaning('Fall Short')[3] == 'falloff'
          and cd.ks_meaning('Doit')[3] == 'doit')


def check_new_feels():
    """Shuffle, second line, reggae, Motown, hip-hop and the waltz each
    play their own drums, bass and comping (2026-09-28)."""
    import chartgroove as g
    for feel, style, n in (('blues shuffle', 'shuffle', 4),
                           ('second line', 'secondline', 4),
                           ('reggae one drop', 'reggae', 4),
                           ('Motown', 'motown', 4),
                           ('boom bap hip hop', 'hiphop', 4),
                           ('jazz waltz', 'waltz', 3),
                           ('waltz', 'waltz', 3)):
        check(f"'{feel}' reads as {style}", g.style_of(feel)[0] == style,
              g.style_of(feel))
        bar = g.Bar(24, (n, 4), 0, 1)
        got = g._new_style(feel, bar)
        g._styled_drums(bar, 1, *got)
        drums = len(bar.onsets)
        notes = []

        def put(at, ticks, midi, vel=None):
            notes.append(midi)
            return midi
        c = ('C', 0, '7', None)
        sec = {'bars': 2, 'content': [[(1, c)], [(1, ('F', 0, '7', None))]]}
        g._styled_bass(g.Bar(24, (n, 4), 0, 1), {}, sec, 0, 1, [(1, c)],
                       *got, put)
        check(f"'{feel}' plays drums and a bass line",
              drums >= n and len(notes) >= 1
              and all(24 <= m <= 60 for m in notes), (drums, notes))
    reg = g.Bar(24, (4, 4), 0, 1)
    g._styled_drums(reg, 1, 'reggae', set())
    check("one drop leaves beat 1 empty of kick",
          not any(x[1] == g._KICK for x in reg.onsets.get(0, (0, []))[1]))


def check_slashes_play_whats_written():
    """Slashes on the page, the source's notes in the listen: a part
    that prints `groove` plays what the source writes for it there,
    and a section with no lifted part (an open solo) is placed by the
    sections either side (Matthew, 2026-09-28: "keep the slashes, I'm
    just saying extra notes was being played")."""
    import chartc as _cc
    tmp = tempfile.mkdtemp()

    def part(pid, bars):
        out = [f'<part id="{pid}">']
        for i, notes in enumerate(bars):
            out.append(f'<measure number="{i + 1}">')
            if i == 0:
                out.append('<attributes><divisions>2</divisions><key>'
                           '<fifths>0</fifths></key><time><beats>4</beats>'
                           '<beat-type>4</beat-type></time><clef><sign>F'
                           '</sign><line>4</line></clef></attributes>')
            for step in notes:
                out.append('<note><rest/><duration>8</duration><type>whole'
                           '</type></note>' if step == 'r' else
                           f'<note><pitch><step>{step}</step><octave>2'
                           '</octave></pitch><duration>2</duration><type>'
                           'quarter</type></note>')
            out.append('</measure>')
        return ''.join(out) + '</part>'
    bass = [['C', 'D', 'E', 'F'], ['G', 'A', 'B', 'C'], ['D', 'E', 'F', 'G'],
            ['A', 'B', 'C', 'D'], ['E', 'F', 'G', 'A'], ['B', 'C', 'D', 'E']]
    tpt = [['r'], ['r'], ['r'], ['r'], ['r'], ['r']]
    src = ('<?xml version="1.0" encoding="UTF-8"?><score-partwise '
           'version="3.1"><part-list><score-part id="P1"><part-name>Trumpet'
           '</part-name></score-part><score-part id="P2"><part-name>Bass'
           '</part-name></score-part></part-list>'
           + part('P1', tpt) + part('P2', bass) + '</score-partwise>')
    open(os.path.join(tmp, 'src.musicxml'), 'w').write(src)
    c = os.path.join(tmp, 's.chart')
    open(c, 'w').write(
        'title: S\nkey: C\nmeter: 4/4\ntempo: 120\n'
        'source: "src.musicxml"\n\nband:\n  trumpet\n  bass\n\n'
        'section A, 2 bars\n  chords: C7 x2\n'
        '  trumpet: as engraved bars 1-2\n  bass: groove\n\n'
        'section B, 2 bars\n  chords: F7 x2\n  bass: groove\n'
        '  trumpet: solo open\n\n'
        'section C, 2 bars\n  chords: C7 x2\n'
        '  trumpet: as engraved bars 5-6\n  bass: groove\n')
    with redirect_stdout(io.StringIO()):
        _cc.compile_chart(c, tmp)
    import re
    lx = open(os.path.join(tmp, 'S — for listening.musicxml'),
              encoding='utf-8').read()
    pb = re.findall(r'<part id="[^"]+">(.*?)</part>', lx, re.S)[1]
    steps = ''.join(re.findall(r'<step>(\w)</step>', pb))
    check("the listen plays the bass the source writes, solo included",
          steps == 'CDEFGABCDEFGABCDEFGABCDE', steps)
    pg = [f for f in os.listdir(tmp) if f.endswith('Bass.musicxml')]
    page = open(os.path.join(tmp, pg[0]), encoding='utf-8').read() \
        if pg else ''
    check("while the bass page keeps its slashes",
          'slash' in page, pg)
    shutil.rmtree(tmp, ignore_errors=True)


def check_swung_and_straight_funk():
    """Swung funk is its own feel: the funk band with its subdivision
    swung — the eighths in half time, the sixteenths at full time.
    Plain funk stays straight, even in a swing tune (Matthew,
    2026-09-28: "Matt's Blues is swung funk")."""
    import chartgroove as g
    import chartc as _cc
    so = g.style_of
    check("'1/2 Time Swung Funk' is half-time funk, swung",
          so('1/2 Time Swung Funk') == ('funk', {'half', 'swung'}))
    check("'funk shuffle' is swung funk",
          so('funk shuffle') == ('funk', {'swung'}))
    check("plain funk and straight funk are straight",
          so('funk') == ('funk', set())
          and so('straight funk') == ('funk', set()))
    tmp = tempfile.mkdtemp()
    for feel, want in (('1/2 Time Swung Funk', 'eighth'),
                       ('Swung Funk', '16th'), ('Funk', None)):
        c = os.path.join(tmp, 'f.chart')
        open(c, 'w').write("title: F\nkey: Bb\nmeter: 4/4\ntempo: 200\n"
                           "feel: swing\n\nband:\n  bass\n  drums\n\n"
                           "section A, 4 bars\n  feel: " + feel + "\n"
                           "  chords: Bb7 x4\n  rhythm: groove\n")
        with redirect_stdout(io.StringIO()):
            _cc.compile_chart(c, tmp)
        lx = open(os.path.join(tmp, "F — for listening.musicxml"),
                  encoding="utf-8").read()
        import re
        got = re.search(r"<swing-type>(\w+)</swing-type>", lx)
        straight = '<straight/>' in lx or got is None
        check(f"'{feel}' in a swing tune plays "
              + (f"swung {want}s" if want else "straight"),
              (got and got.group(1) == want) if want else straight,
              got.group(1) if got else 'straight')
    shutil.rmtree(tmp, ignore_errors=True)


def check_half_time_funk():
    """Half-time funk halves the hats with the pulse: eighths, not
    sixteenths, and the bass lays four notes down — sixteenths played
    Matt's Blues' funk head at double speed (2026-09-28)."""
    import chartgroove as g
    bar = g.Bar(24, (4, 4), 0, 1)
    g._styled_drums(bar, 1, 'funk', {'half'})
    hats = sorted(t for t, (_n, notes) in bar.onsets.items()
                  if any(x[1] == g._HAT for x in notes))
    check("half-time funk hats move in eighths",
          hats == [i * 12 for i in range(8)], hats)
    bar = g.Bar(24, (4, 4), 0, 1)
    g._styled_drums(bar, 1, 'funk', set())
    hats = [t for t, (_n, notes) in bar.onsets.items()
            if any(x[1] == g._HAT for x in notes)]
    check("full-time funk keeps its sixteenths", len(hats) == 16, len(hats))
    bar = g.Bar(24, (4, 4), 0, 1)
    got = []

    def put(at, ticks, midi, vel=None):
        got.append(at)
        return midi
    bb7 = ('B', -1, '7', None)
    sec = {'bars': 2, 'content': [[(1, bb7)], [(1, ('E', -1, '7', None))]]}
    g._styled_bass(bar, {}, sec, 0, 1, [(1, bb7)], 'funk', {'half'}, put)
    check("half-time funk bass lays down four notes", len(got) == 4, got)


def check_cc_gates():
    """A region's CC gates choose what a note plays: a unison layer,
    an extra microphone or an open hi-hat stays off unless its
    controller is up (every one sounded at once until 2026-09-28 — the
    guitar's buzz). A gate that would leave a note silent is ignored."""
    import sfz
    import chartband
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, 'g.sfz'), 'w').write(
        '<control> set_cc101=127\n'
        '<region> key=60 sample=*sine\n'
        '<region> key=60 sample=*saw locc100=1\n'
        '<region> key=60 sample=*square locc101=1\n'
        '<region> key=42 sample=*sine locc4=96 hicc4=127\n'
        '<region> key=42 sample=*saw locc4=0 hicc4=31\n'
        '<region> key=62 sample=*sine locc70=1\n')
    inst = sfz.SfzInstrument(os.path.join(tmp, 'g.sfz'))
    got = sorted(r['sample'] for r in inst.regions_for(60, 100))
    check("an off switch keeps its layer out, an on switch lets it in",
          got == ['*sine', '*square'], got)
    closed = [r['sample'] for r in inst.regions_for(42, 100, {4: 127})]
    opened = [r['sample'] for r in inst.regions_for(42, 100, {4: 0})]
    check("the hi-hat pedal chooses closed or open",
          closed == ['*sine'] and opened == ['*saw'], (closed, opened))
    check("a gate that would silence a note is ignored",
          len(inst.regions_for(62, 100)) == 1)
    check("GM 42 plays the kit's hat pedal down, 46 pedal up",
          chartband._kit_key(inst, 42) == (42, {4: 127.0}) and
          chartband._kit_key(inst, 46) == (42, {4: 0.0}) and
          chartband._kit_key(inst, 38) == (38, None))
    shutil.rmtree(tmp, ignore_errors=True)


def check_tempo_in_the_bar():
    """A tempo that stands in the bar itself, outside any direction, is
    the tempo — engravings put it there (Matt's Blues played at 120
    instead of 210 until 2026-09-28)."""
    import chartaudio
    tmp = tempfile.mkdtemp()
    xml = _mx([['C5 w'], ['C5 w'], ['C5 w'], ['C5 w', '|]']])
    xml = xml.replace('</attributes>', '</attributes><sound tempo="210"/>',
                      1)
    p = os.path.join(tmp, 't.musicxml')
    open(p, 'w').write(xml)
    plan = chartaudio.parse_score(p)
    check("a bare <sound tempo> sets the listen's tempo",
          plan['tempos'] and plan['tempos'][0][1] == 210.0, plan['tempos'])
    bar3 = chartaudio.first_bar_seconds(p, 3)
    check("bars fall where 210 puts them",
          bar3 is not None and abs(bar3 - 2 * 4 * 60 / 210) < 0.05, bar3)
    shutil.rmtree(tmp, ignore_errors=True)


def check_export_picker():
    """Bars from any bar to any bar, parts by name, score or not."""
    import chart
    import chartexcerpt as ex
    import chartengrave as ce
    import chartbraille as cb
    check("bars: '9-24' reads as a range", ex.bar_range('9-24') == (9, 24))
    check("bars: 'from 9 to 24' too", ex.bar_range('from 9 to 24')
          == (9, 24))
    check("bars: all is the whole song", ex.bar_range('all') is None)
    bad = False
    try:
        ex.bar_range('24-9')
    except ValueError:
        bad = True
    check("bars: a backwards range refuses", bad)
    bars = [['r w'], ['r w'], ['r w'], ['r w'], ['C5 w'], ['D5 w'],
            ['E5 w'], ['F5 w', '|]']]
    xml = _mx(bars, fifths=-2, time=(3, 4))
    xml = xml.replace('<measure number="1">', '<measure number="1">'
                      '<attributes><measure-style><multiple-rest>4'
                      '</multiple-rest></measure-style></attributes>', 1)
    cut = ex.excerpt(xml, 3, 6)
    ms, _ = ce.parse_part(cut, 'P1')
    check("excerpt keeps just the bars asked for, numbered as printed",
          [m['num'] for m in ms] == ['3', '4', '5', '6'],
          [m['num'] for m in ms])
    check("excerpt carries the key and time into its first bar",
          ms[0]['state']['fifths'] == -2 and ms[0]['state']['time'] == (3, 4),
          ms[0]['state'])
    check("excerpt shortens a multirest it cuts to what it keeps",
          ms[0]['multi'] == 2, ms[0]['multi'])
    brf, _ = cb.part_to_brf(cut, 'P1', 'T', 'Test part')
    check("an excerpt brailles and reads back", not cb.proofread(
        cut, 'P1', brf))
    labels = ['alto 1', 'trumpet 1', 'trumpet 2', 'piano']
    check("parts: names pick parts, score picks the score",
          chart.select_parts('trumpet 1, score', labels)
          == {'score': True, 'labels': ['trumpet 1']})
    check("parts: a unique piece of a name is enough",
          chart.select_parts('piano', labels)['labels'] == ['piano'])
    check("parts: 'parts' is every part and no score",
          chart.select_parts('parts', labels)
          == {'score': False, 'labels': None})
    bad = False
    try:
        with redirect_stdout(io.StringIO()):
            chart.select_parts('trumpet', labels)
    except SystemExit:
        bad = True
    check("parts: an ambiguous name refuses and lists the band", bad)

    # braille paper: the layout reflows to the page it is given
    check("paper: letter is 34 by 25", cb.paper('letter') == (34, 25))
    check("paper: cells x lines", cb.paper('32x25') == (32, 25))
    bad = False
    try:
        cb.paper('napkin')
    except ValueError:
        bad = True
    check("paper: an unknown size refuses", bad)
    long = [['C5 e', 'D5 e', 'E5 e', 'F5 e', 'G5 e', 'A5 e', 'B5 e',
             'C6 e']] * 60 + [['C5 w', '|]']]
    x = _mx(long)
    for size in ((34, 25), (28, 20)):
        text, _ = cb.part_to_brf(x, 'P1', 'T', 'Test part', page=size)
        pages = text.split('\f')
        lines = [l for p_ in pages for l in p_.split('\r\n')]
        check(f"paper {size[0]}x{size[1]}: every line fits",
              max(len(l) for l in lines) <= size[0])
        check(f"paper {size[0]}x{size[1]}: every page fits",
              all(len([l for l in p_.split('\r\n') if l]) <= size[1]
                  for p_ in pages))
        check(f"paper {size[0]}x{size[1]}: reads back",
              not cb.proofread(x, 'P1', text))
    check("the standard page is back after a narrow one",
          cb.LINE == 40 and cb.PAGE == 25)


def check_drum_kit():
    """
    Kit notation from a played demo: hits keep their chords, spacing
    becomes the printed duration (capped at a beat), cymbals get their
    x-family heads, nothing ever ties, and the read-aloud speaks
    drummer — kick and snare, never F4 and C5.
    """
    import re
    import chartc
    import chartdemo
    import smf
    from chart import verify_measures
    tmp = tempfile.mkdtemp()

    div = 480
    kit = []
    # bar 1: eighth-note closed hats played short, kick on 1 and 3,
    # snare on 2 and 4 — the classic page is eighths, not 16th+rest
    for i in range(8):
        kit.append((i * 240, i * 240 + 90, 42, 80))
    kit.append((0, 100, 36, 96))
    kit.append((960, 1060, 36, 96))
    kit.append((480, 580, 38, 92))
    kit.append((480, 580, 41, 92))       # snare + floor tom together
    kit.append((1440, 1540, 38, 92))
    # bar 2: one crash alone — prints a beat and rests, never a whole note
    kit.append((1920, 3800, 49, 100))
    smf.write(os.path.join(tmp, "k.mid"), kit, div, 96)

    open(os.path.join(tmp, "kit.chart"), "w").write(
        "title: K\nkey: C\nmeter: 4/4\ntempo: 96\n\nband:\n"
        '  drums = drum set, demo "k.mid"\n\n'
        "section A, 2 bars\n  chords: nc x2\n"
        "  drums: from demo bars 1-2\n")
    out = os.path.join(tmp, "build")
    buf = io.StringIO()
    with redirect_stdout(buf):
        files = chartc.compile_chart(os.path.join(tmp, "kit.chart"), out)
    log = buf.getvalue()
    check("kit chart: measures sum", not verify_measures(files))
    check("kit chart: the range report steps aside for the kit",
          "kit notation" in log and "written peak" not in log)

    xml = open(os.path.join(out, "K — drums.musicxml")).read()
    bars = dict(re.findall(r'<measure [^>]*number="(\d+)"[^>]*>(.*?)'
                           r'</measure>', xml, re.S))
    check("kit: unpitched heads, no written pitch",
          "<unpitched>" in bars["1"] and "<pitch>" not in bars["1"])
    check("kit: two voices, cymbals over drums, stitched with a backup",
          "<backup>" in bars["1"] and "<voice>2</voice>" in bars["1"])
    check("kit: same-voice hits stack as a chord", "<chord/>" in bars["1"])
    check("kit: the drum voice keeps its own duration under the hats",
          re.search(r'<voice>2</voice>\s*<type>quarter</type>',
                    bars["1"]))
    check("kit: cymbals wear x heads",
          "<notehead>x</notehead>" in bars["1"])
    check("kit: a drum hit never ties",
          "<tie " not in bars["1"] and "<tie " not in bars["2"])
    check("kit: short hat gates print as eighths",
          bars["1"].count("<type>eighth</type>") >= 8)
    check("kit: a one-family bar folds to a single voice, no backup",
          "<backup>" not in bars["2"])
    check("kit: a lone crash is a beat and rests, not a whole note",
          "<type>quarter</type>" in bars["2"]
          and "<type>whole</type>" not in bars["2"]
          and "<rest/>" in bars["2"])

    # the spoken half: drummer words, no note names
    d = chartdemo.load_demo(os.path.join(tmp, "k.mid"))
    res = chartdemo.resolve_range(d, None, 1, 2, 1, meter=(4, 4),
                                  drums=True, part_label="drums",
                                  findings=chartdemo.Findings())
    prose = " ".join(chartdemo.say_range(res, 0).values())
    check("kit: the read-aloud says kick, snare and closed hat",
          "kick" in prose and "snare" in prose and "closed hat" in prose)
    check("kit: together, not chord, and no spelled pitches",
          "together," in prose and "chord " not in prose
          and not re.search(r'\b[A-G] [0-9]\b', prose))

    # the drawn half: the engraver reads the head and knows the glyphs
    import chartengrave
    n = chartengrave._parse_note(
        "<note><unpitched><display-step>G</display-step>"
        "<display-octave>5</display-octave></unpitched>"
        "<duration>12</duration><voice>1</voice><type>eighth</type>"
        "<notehead>circle-x</notehead></note>")
    check("engraver parses the head kind", n.head == "circle-x")

    # identical groove bars earn the one-bar repeat sign
    two = []
    for b in range(4):
        t0 = b * 1920
        for i in range(4):
            two.append((t0 + i * 480, t0 + i * 480 + 90, 42, 80))
        two.append((t0, t0 + 100, 36, 96))
        two.append((t0 + 960, t0 + 1060, 38, 92))
    two.append((3 * 1920 + 1440, 3 * 1920 + 1540, 49, 100))  # bar 4 differs
    smf.write(os.path.join(tmp, "g.mid"), two, div, 96)
    open(os.path.join(tmp, "gv.chart"), "w").write(
        "title: G\nkey: C\nmeter: 4/4\ntempo: 96\n\nband:\n"
        '  drums = drum set, demo "g.mid"\n\n'
        "section A, 4 bars\n  chords: nc x4\n"
        "  drums: from demo bars 1-4\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "gv.chart"),
                             os.path.join(tmp, "gb"))
    gx = open(os.path.join(tmp, "gb", "G — drums.musicxml")).read()
    pid = re.search(r'<score-part id="([^"]+)"', gx).group(1)
    ms, why = chartengrave.parse_part(gx, pid)
    sim = [m.get('simile') for m in ms]
    check("simile: identical bars two and three take the repeat sign",
          sim[1] == 2 and sim[2] == 3)
    check("simile: a differing bar breaks the run",
          sim[0] is None and sim[3] is None)
    check("simile: a repeat bar is narrow",
          chartengrave.measure_width(ms[1])
          < chartengrave.measure_width(ms[0]) / 2)
    check("engraver's font table knows the kit heads",
          all(k in chartengrave.SMUFL for k in
              ("xHead", "circleXHead", "diamondHead", "triangleHead")))


def check_minor_and_chord_spelling():
    """
    A minor key's leading tone is a sharp or a natural, never the flat the
    closest-on-the-circle rule falls to on a tie: every lifted page in D, G,
    A, E and B minor printed Db, Gb, Ab, Eb and Bb for it (Victory, in G
    minor, carried 405 Gb until 2026-09-28). Chord symbols then spell what
    the signature does not: G# under E7 in C. A note the signature already
    spells keeps its spelling whatever chord sits in the bar.
    """
    import convert, chartc, chartdemo, smf, tempfile
    from contextlib import redirect_stdout
    tonic_pc = {"C": 0, "C#": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
                "F#": 6, "G": 7, "G#": 8, "A": 9, "Bb": 10, "B": 11}
    wrong = []
    for key in ("A", "E", "B", "F#", "C#", "G#", "D#", "D", "G", "C",
                "F", "Bb", "Eb"):
        fifths, _ = chartc.parse_key(key + " minor")
        t = convert.spelling_table(fifths, chartdemo.Findings(),
                                   minor=True)
        tonic = tonic_pc[key]
        step, alter = t[(tonic - 1) % 12]
        letter = "ABCDEFG"[("ABCDEFG".index(key[0]) - 1) % 7]
        if step != letter or alter < 0:
            wrong.append(f"{key} minor: {step}{alter:+d}")
    check("every minor key spells its leading tone on the letter below "
          "the tonic, never flat", not wrong, "; ".join(wrong))
    t = convert.spelling_table(-1, chartdemo.Findings(), minor=True)
    check("D minor: raised sixth B natural, leading tone C#",
          t[11] == ("B", 0) and t[1] == ("C", 1))
    t = convert.spelling_table(0, chartdemo.Findings(),
                               chords=chartc.chord_spelling(["E7"]))
    check("E7 in C spells G#", t[8] == ("G", 1))
    t = convert.spelling_table(-6, chartdemo.Findings(), minor=True,
                               chords=chartc.chord_spelling(["Bm11"]))
    check("a signature note keeps its spelling under a foreign chord "
          "(Gb in Eb minor over Bm11)", t[6] == ("G", -1))
    check("chord degrees: m7b5, dim7, 7sus4, alt",
          chartc.chord_degrees("m7b5") == {"b3", "b5", "b7"}
          and chartc.chord_degrees("dim7") == {"b3", "b5", "bb7"}
          and chartc.chord_degrees("7sus4") == {"4", "5", "b7"}
          and "b13" in chartc.chord_degrees("alt"))
    check("a transposing part spells the chord in its own frame "
          "(A7 for Bb trumpet: D#)",
          chartc.chord_spelling(["A7"], 2).get(3) == ("D", 1))

    # end to end: D minor, C# under A7, trumpet and flute
    tmp = tempfile.mkdtemp()
    div = 480
    ev = [(0, 900, 73, 90), (960, 1800, 74, 90), (1920, 2800, 73, 90),
          (2880, 3700, 74, 90)]
    smf.write(os.path.join(tmp, "m.mid"), ev, div, 100)
    open(os.path.join(tmp, "m.chart"), "w").write(
        "title: M\nkey: D minor\nmeter: 4/4\ntempo: 100\n\nband:\n"
        '  flute, demo "m.mid"\n  trumpet, demo "m.mid"\n\n'
        "section A, 1 bars\n  chords: A7 Dm@3\n"
        "  flute: from demo bars 1-1\n  trumpet: from demo bars 1-1\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "m.chart"),
                             os.path.join(tmp, "b"))
    fx = open(os.path.join(tmp, "b", "M — flute.musicxml")).read()
    tx = open(os.path.join(tmp, "b", "M — trumpet.musicxml")).read()
    check("D minor page: the flute reads C#, the trumpet D#",
          "<step>C</step><alter>1</alter>" in fx.replace("\n", "")
          .replace(" ", "") and "<step>D</step><alter>1</alter>"
          in tx.replace("\n", "").replace(" ", "")
          and "<alter>-1</alter>" not in fx)

    # the interview's defaults read the demo
    import chartnew
    check("interview: key signature event named like the header takes it",
          chartnew.key_name(-1, 1) == "D minor"
          and chartnew.key_name(3, 0) == "A")
    check("interview: compound meters offer the dotted-quarter tempo",
          chartnew.compound((6, 8)) and chartnew.compound((12, 8))
          and not chartnew.compound((4, 4)))
    import subprocess as _sp
    out = _sp.run([sys.executable, os.path.join(HERE, "chart.py"),
                   os.path.join(tmp, "m.chart"), "parts", "--labels"],
                  capture_output=True, text=True).stdout.split()
    check("parts --labels: one chair per line for the apps' pick lists",
          out == ["flute", "trumpet"], repr(out))
    check("interview: a track named for its instrument offers it",
          chartnew.track_instrument("Trumpet 1") == "trumpet"
          and chartnew.track_instrument("congas") == "congas"
          and chartnew.track_instrument("track 3") == "")


def check_hand_percussion_parts():
    """
    A conga, bongo or bell player reads ONE voice: the kit's
    cymbals-up/drums-down split is for the drum set (and the aux table),
    and applied to congas it turned every mute into a stems-up dotted
    quarter over a line of rests (Sundown Bembe, 2026-09-28). The listen
    reads a hand-percussion staff by the part's instrument sound as well
    as its name, so a cowbell labelled "bell" still plays the bell.
    """
    import chartc, chartaudio, smf, tempfile
    from contextlib import redirect_stdout
    tmp = tempfile.mkdtemp()
    ev = []
    for b in range(2):
        t0 = b * 1920
        ev += [(t0, t0 + 200, 62, 80), (t0 + 480, t0 + 680, 63, 90),
               (t0 + 960, t0 + 1160, 62, 80), (t0 + 1440, t0 + 1640, 64, 96)]
    smf.write(os.path.join(tmp, "c.mid"), ev, 480, 100)
    kit = []
    for b in range(2):
        t0 = b * 1920
        kit += [(t0 + i * 480, t0 + i * 480 + 100, 42, 80) for i in range(4)]
        kit += [(t0, t0 + 100, 36, 96), (t0 + 960, t0 + 1060, 38, 90)]
    smf.write(os.path.join(tmp, "k.mid"), kit, 480, 100)
    open(os.path.join(tmp, "h.chart"), "w").write(
        "title: H\nkey: C\nmeter: 4/4\ntempo: 100\n\nband:\n"
        '  congas, demo "c.mid"\n  drums, demo "k.mid"\n\n'
        "section A, 2 bars\n  chords: nc x2\n"
        "  congas: from demo bars 1-2\n  drums: from demo bars 1-2\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "h.chart"),
                             os.path.join(tmp, "b"))
    cx = open(os.path.join(tmp, "b", "H — congas.musicxml")).read()
    dx = open(os.path.join(tmp, "b", "H — drums.musicxml")).read()
    check("congas: one voice, mutes and open tones together",
          "<backup>" not in cx and "<voice>2</voice>" not in cx
          and "<notehead>x</notehead>" in cx)
    check("drums: the kit still splits cymbals from drums",
          "<voice>2</voice>" in dx)
    t = ('<note><unpitched><display-step>E</display-step><display-octave>'
         '5</display-octave></unpitched><duration>1</duration></note>')
    check("listen: a cowbell part labelled 'bell' plays the cowbell",
          chartaudio._note_midi(t, {'name': 'bell',
                                    'sound': 'metal.cowbell',
                                    'percussion': True}, 0) == 56
          and chartaudio._note_midi(t, {'name': 'drums',
                                        'sound': 'drum.group.set',
                                        'percussion': True}, 0) != 60)


def check_circle_of_fifths():
    """
    Every key, all the way sharp and all the way flat, major and minor,
    through every kind of transposition: a scale, the dominant seventh, a
    secondary dominant and (in minor) the raised sixth and seventh, each
    note checked against its line-of-fifths spelling. The sweep that
    became this test (2026-09-28) found written keys of eight, nine and
    ten sharps on alto and bari (now respelled in flats, as publishers
    do), F double-sharp printing as G in C# major's D#7, and the alto
    flute and Eb clarinet transposing their key signatures the wrong way
    round the circle.
    """
    import re, chartc, smf, tempfile
    from contextlib import redirect_stdout
    bad = [k for k, v in chartc.HORNS.items()
           if v['clef'] != 'percussion'
           and ((7 * v['transpose']) % 12 + 6) % 12 - 6 != v['foff']]
    check("every instrument's key offset follows from its transposition",
          not bad, f"wrong: {bad}")
    STEPS = "FCGDAEB"
    BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

    def sp(f):
        return STEPS[f % 7], f // 7

    def nm(f):
        s_, a_ = sp(f)
        return s_ + {-2: 'bb', -1: 'b', 0: '', 1: '#', 2: '##'}[a_]
    MAJ, MIN = [0, 2, 4, -1, 1, 3, 5], [0, 2, -3, -1, 1, -4, -2]
    wrong, keysigs, total = [], [], 0
    tmp = tempfile.mkdtemp()
    for kf in range(-7, 8):
        for minor in (False, True):
            tonic = kf + 1 + (3 if minor else 0)
            sc, q = (MIN, 'm') if minor else (MAJ, '')
            bars = [([tonic + d for d in (sc[0], sc[2], sc[4], sc[0])],
                     nm(tonic) + q),
                    ([tonic + d for d in (sc[4:] if not minor
                                          else [1, 3, 5])] + [tonic],
                     nm(tonic) + q),
                    ([tonic + 1, tonic + 5, tonic + 2, tonic - 1],
                     nm(tonic + 1) + '7'),
                    ([tonic + 2, tonic + 6, tonic + 3, tonic],
                     nm(tonic + 2) + '7')]
            for inst in ('flute', 'trumpet', 'alto sax', 'french horn',
                         'alto flute', 'eb clarinet', 'a clarinet'):
                h = chartc.HORNS[inst]
                ev, t = [], 0
                for fifs, _ in bars:
                    ps, prev = [], None
                    for f in fifs:
                        s_, a_ = sp(f)
                        p = 60 + BASE[s_] + a_
                        if prev is not None:
                            while p < prev - 6:
                                p += 12
                            while p > prev + 6:
                                p -= 12
                        ps.append(p)
                        prev = p
                    lo, hi = h['fold']
                    while min(ps) < lo + 2:
                        ps = [p + 12 for p in ps]
                    while max(ps) > hi - 2:
                        ps = [p - 12 for p in ps]
                    ev += [(t + i * 480, t + i * 480 + 400, p, 90)
                           for i, p in enumerate(ps)]
                    t += 1920
                smf.write(os.path.join(tmp, "d.mid"), ev, 480, 100)
                key = nm(tonic) + (" minor" if minor else "")
                open(os.path.join(tmp, "t.chart"), "w").write(
                    f"title: T\nkey: {key}\nmeter: 4/4\ntempo: 100\n\n"
                    f'band:\n  p = {inst}, demo "d.mid"\n\n'
                    f"section A, 4 bars\n  chords: "
                    + ", ".join(c for _, c in bars)
                    + "\n  p: from demo bars 1-4, eighths\n")
                with redirect_stdout(io.StringIO()):
                    chartc.compile_chart(os.path.join(tmp, "t.chart"),
                                         os.path.join(tmp, "b"))
                x = open(os.path.join(tmp, "b", "T — p.musicxml")).read()
                wf = int(re.search(r'<fifths>(-?\d+)</fifths>', x).group(1))
                if not -7 <= wf <= 7 or (h['foff'] and abs(wf) > 6):
                    keysigs.append(f"{key} {inst}: {wf}")
                shift = wf - kf
                got = [(s_, int(a_ or 0)) for s_, a_ in re.findall(
                    r'<pitch><step>(\w)</step>(?:<alter>(-?\d)</alter>)?',
                    x)]
                want = [sp(f + shift) for fifs, _ in bars for f in fifs]
                total += len(want)
                if got != want:
                    wrong.append(f"{key} {inst}")
    check(f"circle of fifths: {total} notes in 30 keys and 7 "
          "transpositions spell by the book", not wrong,
          "; ".join(wrong[:8]))
    check("circle of fifths: every written key signature is a real key, "
          "a transposing part never past six", not keysigs,
          "; ".join(keysigs[:8]))


def check_starting_from_nothing():
    """
    A tune started with no demo, the way a writer describes one
    (2026-09-28, driven through the app with VoiceOver): "12 bar blues,
    head twice, solos, head out" once read as two heads, one with no
    length, and then asked its bars forever; the band could not be
    named at all; "trumpet and saxes play the melody, bone tacet" lost
    the bone; a yes/no question took a stray sentence as yes.
    """
    import chartedit, chartnew, io
    from contextlib import redirect_stdout
    p, g = chartedit.parse_form("12 bar blues, head twice, solos, "
                                "head out")
    check("form: 'head twice' repeats the blues head, 'head out' is the out",
          [(x["name"], x["bars"], x["repeat"], x["kind"]) for x in p]
          == [("head", 12, 2, "plain"), ("solos", None, 1, "solos"),
              ("out", None, 1, "out")] and p[2]["source"] == "head"
          and not g)
    p, _ = chartedit.parse_form("intro 4, verse 16, chorus 8, verse, "
                                "chorus twice")
    check("form: a section named again keeps its length",
          [(x["name"], x["bars"], x["repeat"]) for x in p][3:]
          == [("verse", 16, 1), ("chorus", 8, 2)])
    band, unknown = chartnew.band_from_words(
        "trumpet, 2 tenors, piano, bass and drums, kazoo")
    check("band from words: counts, plurals, nicknames, the writer's labels",
          band == [("trumpet", "trumpet"), ("tenor 1", "tenor sax"),
                   ("tenor 2", "tenor sax"), ("piano", "piano"),
                   ("bass", "bass"), ("drums", "drums")]
          and unknown == ["kazoo"], repr((band, unknown)))
    import chartc
    check("a bare bass follows the feel: upright on swing, a waltz, a "
          "ballad, bossa or nothing said; electric on funk, rock, R&B",
          all(chartc.bass_for_feel(f) == 'double bass' for f in
              ('swing', 'jazz waltz', 'ballad', 'bossa nova', ''))
          and all(chartc.bass_for_feel(f) == 'electric bass' for f in
                  ('funk', '1/2 time swung funk', 'rock', 'R&B', 'Motown',
                   'reggae', 'hip hop')))
    L = ["trumpet", "alto", "tenor 1", "tenor 2", "bone", "piano",
         "bass", "drums"]
    G = ["horns", "saxes", "rhythm", "all"]
    check("who: players joined by 'and', and a plural meaning every chair",
          chartedit.parse_who("trumpet and piano groove, tenors tacet",
                              L, G) == ["trumpet: groove", "piano: groove",
                                        "tenor 1: tacet", "tenor 2: tacet"])
    try:
        chartedit.parse_who("trumpet and saxes play the melody, bone "
                            "tacet", L, G)
        got = None
    except chartedit.MelodyLater as e:
        got = (e.targets, e.lines)
    check("who: the melody with no demo waits, the rest of the answer stays",
          got == (["trumpet", "saxes"], ["bone: tacet"]), repr(got))
    old_in = sys.stdin
    try:
        sys.stdin = io.StringIO("the head sounds good\nyes\n")
        with redirect_stdout(io.StringIO()) as out:
            a = chartedit.ask("Take those changes? yes or no", "yes")
    finally:
        sys.stdin = old_in
    check("yes/no: a stray sentence is asked again, never read as yes",
          a == "yes" and "needs a yes or a no" in out.getvalue())


def check_bow_and_chord_room():
    """
    Matthew, 2026-09-28: "anything that says for an upright bass player
    to switch to bow and switch back?" There was not, outside a demo's
    keyswitches, and the upright only had a plucked sound. Found on the
    way: a chord symbol drawn on top of a note climbing over the staff.
    """
    import chartc, chartband, chartengrave, tempfile
    from contextlib import redirect_stdout
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "a.chart"), "w").write(
        "title: A\nkey: D minor\nmeter: 4/4\ntempo: 60\n\nband:\n"
        "  bass = upright bass\n\nfigure line, 6 bars:\n"
        "  notes: D3 w, A2 w, D3 w, A2 w, D3 w, A2 w\n\n"
        "section A, 6 bars\n  chords: Dm x6\n"
        "  bass: figure line, arco at bar 3, pizz at bar 5\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "a.chart"),
                             os.path.join(tmp, "b"))
    x = open(os.path.join(tmp, "b", "A — bass.musicxml")).read()
    check("bow: 'arco at bar 3' and 'pizz at bar 5' print on the part",
          "<words>arco</words>" in x.replace(' font-style="italic"', '')
          or ">arco<" in x)
    check("bow: pizz. prints where the bow goes down", ">pizz.<" in x)
    voice = next(v for keys, v in chartband._SFZ_VOICES
                 if 'strings.contrabass' in keys)
    check("bow: the upright plays plucked, bowed under arco, short "
          "bowed under a staccato",
          chartband._variant(voice, {}) == voice['sus']
          and chartband._variant(voice, {'arco': True}) == voice['arco']
          and chartband._variant(voice, {'arco': True, 'stac': True})
          == voice['arco_stac'] and 'Contrabass' in voice['arco'])
    import chartread
    check("bow: the read-aloud says what arco and pizz. mean",
          chartread.TECHNIQUE_SAID["arco"] == ", with the bow"
          and chartread.TECHNIQUE_SAID["pizz."] == ", plucked")

    class N:
        def __init__(self, step, octave, marks=()):
            self.step, self.octave, self.rest = step, octave, False
            self.marks = list(marks)
    meas = {'chords': [(0, 'Dm')],
            'events': [(0, [N('D', 4)], 1, 1)]}
    state = {'clefs': {1: 'F'}}
    base = chartengrave.chord_height({'chords': [(0, 'Dm')],
                                      'events': []}, 100.0, state)
    high = chartengrave.chord_height(meas, 100.0, state)
    check("engraver: a chord symbol rises over a note above the staff",
          high > base + 2 * chartengrave.SP, f"{base} -> {high}")
    top = N('A', 5)
    low = N('C', 5, marks=['strong-accent'])
    plain = chartengrave.chord_height(
        {'chords': [(0, 'E13')], 'events': [(0, [N('A', 5)], 1, 1)]},
        100.0, {'clefs': {1: 'G'}})
    marked = chartengrave.chord_height(
        {'chords': [(0, 'E13')], 'events': [(0, [top, low], 1, 1)]},
        100.0, {'clefs': {1: 'G'}})
    check("engraver: a chord's accent lifts the changes, whichever note "
          "carries it", marked > plain + chartengrave.SP)


def check_feels_and_technique_for_every_part():
    """
    Matthew, 2026-09-28 (through Faith on iMessage): "two feel, swing,
    straight eighths... make sure it can understand all the lingo."
    Only swing and shuffle had ever changed what the band played; a
    two feel printed and the bass walked in four regardless. Same
    night: a technique mark (arco, pizz.) on any part but the top one
    reached neither the conductor score nor the listen, so a bowed
    bass played plucked.
    """
    import chartgroove, chartc, tempfile, re as _re
    from contextlib import redirect_stdout
    so = chartgroove.style_of
    check("feel words: two feel, ballad, double time read as swing feels",
          so("two feel") == ("swing", {"two"})
          and so("ballad") == ("swing", {"ballad"})
          and so("double time swing") == ("swing", {"double"}))
    check("feel words: half time funk, bossa, samba, afro-cuban, rock",
          so("1/2 Time Funk") == ("funk", {"half"})
          and so("bossa nova")[0] == "bossa" and so("samba")[0] == "samba"
          and so("afro-cuban")[0] == "latin"
          and so("rock") == ("straight", set())
          and so("easy gospel") == ("straight", set()))
    tmp = tempfile.mkdtemp()
    feels = ["swing walking", "two feel", "ballad", "bossa nova",
             "afro-cuban", "funk"]
    L = ["title: F", "key: F", "meter: 4/4", "tempo: 120", "", "band:",
         "  piano", "  bass = upright bass", "  drums", "  cello", ""]
    for i, f in enumerate(feels):
        L += [f"section {chr(65 + i)}, 2 bars", f"  feel: {f}",
              "  chords: F7, Bb7", "  all: groove"]
        if i == 1:
            L += ["  cello: pizz"]
        L += [""]
    open(os.path.join(tmp, "f.chart"), "w").write("\n".join(L) + "\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "f.chart"),
                             os.path.join(tmp, "b"))
    x = open(os.path.join(tmp, "b", "F — for listening.musicxml")).read()
    parts = _re.findall(r'<part id="P\d">(.*?)</part>', x, _re.S)
    ms = _re.findall(r'<measure number="\d+"[^>]*>(.*?)</measure>',
                     parts[1], _re.S)
    counts = [len([n for n in _re.findall(r'<note\b.*?</note>', ms[2 * i],
                                          _re.S) if '<rest' not in n])
              for i in range(len(feels))]
    check("feel: the bass walks 4 in swing, 2 in two feel, 1 in a ballad, "
          "and the latin tumbao is 2",
          counts[0] in (4, 5) and counts[1] == 2 and counts[2] == 1
          and counts[4] == 2, repr(dict(zip(feels, counts))))
    check("feel: bossa, afro-cuban and funk each play their own bass",
          len({counts[3], counts[4], counts[5]}) == 3,
          repr(dict(zip(feels, counts))))
    check("technique: a lower part's pizz. reaches the listen",
          "pizz." in parts[3])
    sc = open(os.path.join(tmp, "b", "F — score.musicxml")).read()
    sparts = _re.findall(r'<part id="P\d">(.*?)</part>', sc, _re.S)
    check("technique: and the conductor score shows it on that staff",
          "pizz." in sparts[3] and "two feel" not in sparts[3])
    check("bow: 'fingered' is the bass player's word for pizz",
          chartc.TECHNIQUE_RE.match("pizz.") is not None)
    open(os.path.join(tmp, "g.chart"), "w").write(
        "title: G\nkey: C\nmeter: 4/4\ntempo: 60\n\nband:\n"
        "  bass = upright bass\n\nsection A, 2 bars\n  chords: C x2\n"
        "  bass: groove, arco, fingered at bar 2\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "g.chart"),
                             os.path.join(tmp, "gb"))
    gx = open(os.path.join(tmp, "gb", "G — bass.musicxml")).read()
    check("bow: 'fingered at bar 2' prints pizz.",
          gx.count("pizz.") == 1 and "arco" in gx)


def check_mutes_sound():
    """
    Mutes printed and never sounded (no muted brass exists openly), and
    a mute could only go on at a section's first bar. Now 'harmon mute
    at bar 3' / 'open at bar 7' place anywhere, and the listen plays the
    open horn through the shape each mute cuts.
    """
    import chartband, chartc, tempfile, math
    from array import array
    from contextlib import redirect_stdout
    check("mutes: the page's words name the mute",
          chartband.mute_kind("harmon mute - stem out") == "harmon"
          and chartband.mute_kind("cup mute") == "cup"
          and chartband.mute_kind("con sord.") == "straight"
          and chartband.mute_kind("open") is None)
    sr = 22050
    tone = array('f', [sum(math.sin(2 * math.pi * 440 * k * i / sr) / k
                           for k in (1, 2, 3, 4, 5, 6))
                       for i in range(sr // 4)])

    def amp(seg, f):
        c = 2 * math.cos(2 * math.pi * f / sr)
        s1 = s2 = 0.0
        for x in seg:
            s1, s2 = x + c * s1 - s2, s1
        return math.sqrt(max(s1 * s1 + s2 * s2 - c * s1 * s2, 0))
    cup = chartband.apply_mute((tone, None), "cup", sr)[0]
    har = chartband.apply_mute((tone, None), "harmon", sr)[0]
    check("mutes: a cup darkens the top, a harmon thins the bottom",
          amp(cup, 2640) / amp(cup, 440) < amp(tone, 2640) / amp(tone, 440)
          / 2.5 and amp(har, 440) / amp(har, 1760)
          < amp(tone, 440) / amp(tone, 1760) / 2)
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "m.chart"), "w").write(
        "title: M\nkey: C\nmeter: 4/4\ntempo: 90\n\nband:\n  trumpet\n"
        "\nsection A, 4 bars\n  chords: C x4\n"
        "  trumpet: groove, harmon mute at bar 2, open at bar 4\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "m.chart"),
                             os.path.join(tmp, "b"))
    x = open(os.path.join(tmp, "b", "M — trumpet.musicxml")).read()
    check("mutes: 'harmon mute at bar 2' and 'open at bar 4' print there",
          "harmon mute" in x and "<words>open</words>" in x)


def check_cues_and_cuts():
    """Matthew, 2026-09-30: "say vamp for x number of times ... repeat
    any section x number of times ... cut to here ... repeat until cue
    from anywhere: drums, any instrument or vocalist ... live in the
    moment", then "also add a cut back to here". Who cues a till-cue
    section plays the cue on the last time round; a cut jumps forward,
    a cut back plays from there once more; every chair's read-aloud
    says who to listen for."""
    import chartaudio
    import chartc
    import chartread
    import chartband
    check("voices sing on the synth voice, not sampled choir (Matthew, "
          "2026-09-30: 'I just don't like them at all')",
          chartband.SYNTH_VOICE == 55 and not any(
              f.startswith('voice') for frags, _v in chartband._SFZ_VOICES
              for f in frags)
          and any(fr == 'voice' and db <= -5 for fr, db, _p in
                  chartband._SEATS))
    sec = chartc.section_header(
        "solos", ", 8 bars, till cue, drums cue, on cue, cut to shout", "t")
    check("header: till cue, drums cue, on cue cut to shout",
          sec['open'] and sec['cue_from'] == 'drums'
          and sec['cut_to'] == 'shout' and not sec['cut_back'])
    sec = chartc.section_header("shout", ", 8 bars, then cut back", "t")
    check("header: then cut back (to the nearest mark)",
          sec['cut'] and sec['cut_back'] and sec['cut_to'] is None)
    ms = [(str(n), '') for n in range(1, 9)]
    marks = [set() for _ in ms]
    marks[2].add('cut:6')           # bar 3 cuts to 6
    marks[6].add('cut:2')           # bar 7 cuts back to 2, once
    got = [n for n, _ in chartaudio.walk_cuts(ms, ms, marks)]
    check("the walk: forward past 4-5, back to 2 once, cutting again",
          got == ['1', '2', '3', '6', '7', '2', '3', '6', '7', '8'],
          str(got))
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "c.chart")
    open(path, "w").write(
        "title: C\nkey: F\nmeter: 4/4\ntempo: 130\nfeel: swing\n\n"
        "band:\n  singer = voice\n  trumpet\n  piano\n  bass\n  drums\n"
        "\nsection head, 4 bars\n  chords: F, F, C7, F\n"
        "  at bar 1: cut back to here\n\n"
        "section tag, 2 bars, vamp till cue, the singer cues\n"
        "  chords: Gm7, C7\n\n"
        "section skip, 2 bars\n  chords: Bb, Bb\n\n"
        "section out, 2 bars, then cut back\n  chords: F, F\n\n"
        "section end, 1 bars\n  chords: F\n")
    # the tag cuts nowhere: out is reached by walking; so make one
    open(path, "a").write("")
    src = open(path).read().replace(
        "vamp till cue, the singer cues",
        "vamp till cue, the singer cues, on cue, cut to out")
    open(path, "w").write(src)
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(path, os.path.join(tmp, "b"))
    out = buf.getvalue()
    check("findings: the singer cues the tag, and the walk takes both cuts",
          "the singer cues it on the last time round" in out
          and "bars 1-6, then 9-10, then 1-6, then 9-11" in out,
          out[-900:])
    x = open(os.path.join(tmp, "b", "C — for listening.musicxml")).read()
    sing = re.search(r'<part id="P1">(.*?)</part>', x, re.S).group(1)
    last = [m for n, m in re.findall(
        r'<measure number="([^"]*)">(.*?)</measure>', sing, re.S)
        if n.startswith('6')][-1]
    check("the singer sings a pickup on the tag's last time round, and "
          "only then", last.count('<pitch>') == 3 and all(
              '<pitch>' not in m for n, m in re.findall(
                  r'<measure number="([^"]*)">(.*?)</measure>', sing,
                  re.S) if n.startswith('6') and m != last))
    old = sys.argv
    sys.argv = ["chartread", path, "--part", "drums"]
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            chartread.main()
    finally:
        sys.argv = old
    said = buf.getvalue()
    sys.argv = ["chartread", path, "--part", "singer", "--section", "tag"]
    buf2 = io.StringIO()
    try:
        with redirect_stdout(buf2):
            chartread.main()
    finally:
        sys.argv = old
    check("read-aloud: the singer who cues rests till the last time round, "
          "never told tacet", "Rest until the last time round" in
          buf2.getvalue() and "Tacet" not in buf2.getvalue(),
          buf2.getvalue())
    check("read-aloud: the drummer hears who cues and where the band goes",
          "till the singer cues it" in said and '"Back to bar 1"' in said
          and '"On cue, to out"' in said, said)


def check_band_hears_the_lead():
    """Matthew, 2026-09-30, after the Lantern Waltz listen: "vibes play
    lines, not chords when a vibes player solos ... sounded like it
    didn't know any of the chord changes ... make sure everyone is
    context aware and knows what to play and what not to play." The
    compers and background horns hear the melody and the soloist and
    leave out a note a half step from it; a vibes soloist plays the line
    alone; vibes the chart gave nothing leave the comping to the piano;
    and the section header takes the band's own words for the form."""
    import chartc
    import chartgroove
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    b.add(0, 48, ('p', 57, 80))
    b.add(0, 48, ('p', 69, 80))
    b.add(0, 48, ('p', 62, 80))
    b._hear_the_lead([(0.0, 2.0, 70)])
    got = sorted(n[1] for n in b.onsets[0][1])
    check("a comper leaves out the A under the melody's Bb, keeps the rest",
          got == [62], str(got))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    chartgroove._catch(b, [(0.0, 0.5, 0.5), (1.5, 2.0, 0.5)], 0.6,
                       chartgroove._Dice('t'))
    got = {t: sorted(n[1][0] + str(n[1][1]) for n in ns)
           for t, (_l, ns) in b.onsets.items()}
    check("the drummer catches the section's hits: kick and snare on a "
          "short one, a big hit of their own choosing on a held one out "
          "of space", got.get(0) == ['C5', 'F4'] and bool(got.get(36)),
          str(got))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    chartgroove._catch(b, [(0.0, 0.5, 0.5, 77), (1.0, 0.5, 0.5, 72),
                           (2.0, 0.5, 1.5, 65)], 0.6, lambda: 0.1)
    toms = [n[1][:2] for t in sorted(b.onsets) for n in b.onsets[t][1]
            if n[1] not in (chartgroove._KICK, chartgroove._CRASH)]
    check("a melodic drummer plays the figure's shape on the toms: high "
          "tom on its top note, floor tom on its lowest",
          toms == [('E', 5), ('D', 5), ('A', 4)], str(toms))
    import chartband
    ev = [(0.5, 0.5, 70, 1, None), (1.0, 0.5, 72, 1, None),
          (1.5, 0.5, 74, 1, None), (2.0, 0.5, 77, 1, None),
          (2.5, 0.5, 74, 1, None), (3.0, 1.0, 72, 1, None),
          (5.5, 0.5, 79, 1, None)]
    w = chartband._phrasing(ev, [(0, (2 / 3, 1.0))])
    check("a written line phrased like a player: the peak leaned on, the "
          "swing's on-beat eighth lighter, the off-beat into a held note "
          "pushed, the end eased, a lone off-beat hit leaned on",
          w[3] > 1.0 and w[1] < w[2] and w[4] > 1.1 and w[5] < 1.0
          and w[6] > 1.1, str([round(x, 2) for x in w]))
    ev2 = [(0.0, 0.5, 70, 1, {'lead': True}), (0.5, 0.5, 72, 1,
                                                {'lead': True})]
    check("a made-up solo is left to shape itself",
          chartband._phrasing(ev2, []) == [1.0, 1.0])
    import chartending
    check("every Max Roach tag lands on the kick",
          all(t[-1] == 'bass drum' for t in chartending._TAGS)
          and all(chartending.band_tag(chartgroove._Dice('tag', k))[-1]
                  == 'bass drum' for k in range(30)))
    got = chartending.tag_pieces("open hat with snare, hat foot, kick")
    check("a written tag reads strokes together: 'open hat with snare'",
          got == ['open hat+snare', 'hat foot', 'kick'], str(got))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    chartending._tag(b, 24, got, 'song')
    first = b.onsets[min(b.onsets)][1]
    check("and plays them together, the kick last",
          {n[1] for n in first} == {('G', 5, 'circle-x'), ('C', 5, 'normal')}
          and b.onsets[max(b.onsets)][1][-1][1] == ('F', 4, 'normal'))
    def bass_counts(feel):
        out = set()
        tmp_ = tempfile.mkdtemp()
        cp = os.path.join(tmp_, "t.chart")
        open(cp, "w").write(
            "title: T\nkey: F\nmeter: 4/4\ntempo: 140\nfeel: " + feel +
            "\n\nband:\n  trumpet\n  piano\n  bass\n  drums\n\n"
            "section head, 4 bars\n  chords: F, Gm7 C7, F, C7\n")
        was = chartc.TAKE
        try:
            for tk in range(1, 9):
                chartc.TAKE = tk
                with redirect_stdout(io.StringIO()):
                    chartc.compile_chart(cp, os.path.join(tmp_, str(tk)))
                x = open(os.path.join(tmp_, str(tk),
                                      "T — for listening.musicxml")).read()
                bp = re.search(r'<part id="P3">(.*?)</part>', x, re.S)
                ms = re.findall(r'<measure number="1">(.*?)</measure>',
                                bp.group(1), re.S)
                out.add(ms[0].count('<pitch>'))
        finally:
            chartc.TAKE = was
        return out
    got = bass_counts("swing")
    check("on a head the bassist chooses in the moment: some takes in two, "
          "some walking", 2 in got and max(got) >= 4, str(got))
    got = bass_counts("swing, walking")
    check("the chart says walk: every take walks", min(got) >= 4, str(got))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    b.add(0, 24, ('u', chartgroove._RIDE, 80))
    b.add(24, 24, ('u', chartgroove._HATF, 60))
    b.add(24, 24, ('u', chartgroove._RIDE, 80))
    chartgroove._hat_time(b, True)
    pieces = [n[1] for _t, (_l, ns) in sorted(b.onsets.items()) for n in ns]
    check("time on the closed hi-hat: the ride moves to the hat, the foot "
          "holds it shut, the kick feathers the quarters",
          chartgroove._RIDE not in pieces and chartgroove._HATF not in pieces
          and pieces.count(chartgroove._HAT) == 2
          and pieces.count(chartgroove._KICK) == 4, str(pieces))
    tmp_s = tempfile.mkdtemp()
    sp_ = os.path.join(tmp_s, "sh.chart")
    open(sp_, "w").write(
        "title: Sh\nkey: F\nmeter: 4/4\ntempo: 140\nfeel: swing\n\n"
        "band:\n  trumpet\n  piano\n  bass\n  drums\n\n"
        "section head, 4 bars\n  chords: F x4\n\n"
        "section solos, 4 bars\n  chords: F x4\n  trumpet: solo\n\n"
        "section shout, 4 bars\n  chords: F x4\n\n"
        "section out, 4 bars\n  chords: F x4\n\n"
        "section tag, 2 bars, label \"soft tag\"\n  chords: F x2\n")
    ch_ = chartc.parse_chart(sp_)
    bd_ = ch_['band']
    lb_ = [x['label'] for x in bd_]
    pl_, _t = chartc.build_plans(ch_, bd_, chartc.resolve_groups(
        bd_, ch_.get('groups')), lb_)
    chartc.tune_shape(pl_, lb_)
    e_ = {p['sec']['name']: p['sec']['_energy'] for p in pl_}
    check("the tune has a shape: settled head, the shout at the peak, the "
          "out-head back down from it, a section's own 'soft' honoured",
          e_['head'] < e_['out'] < e_['shout'] and e_['tag'] < 0.4,
          str({k: round(v, 2) for k, v in e_.items()}))
    import chartedit
    import chartnew
    p_ = chartedit._clause_core("solos for everybody", 1, False)
    p2 = chartedit._clause_core("solos over the head for trumpet and tenor",
                                1, False)
    check("the form hears 'solos for everybody' and 'solos over the head "
          "for trumpet and tenor' as solo sections with their players",
          p_["kind"] == "solos" and p_["solo_who"] == "everybody"
          and p2["kind"] == "solos" and p2["use"] == "head"
          and p2["solo_who"] == "trumpet and tenor", repr((p_, p2)))
    answers = iter(["swing", "4/4"])
    real_ask, real_say = chartnew.ask, chartnew.say
    said_ = []
    try:
        chartnew.ask = lambda q, d="": next(answers)
        chartnew.ask.eof = False
        chartnew.say = said_.append
        got = chartnew.ask_until("Meter", "4/4", chartc.parse_meter,
                                 "A meter is two numbers")
    finally:
        chartnew.ask, chartnew.say = real_ask, real_say
    check("a beginner's wrong answer asks again instead of ending the "
          "interview", got == "4/4" and said_ and "'swing'" in said_[0],
          repr((got, said_)))
    tmp_c = tempfile.mkdtemp()
    cc = os.path.join(tmp_c, "c.chart")
    body = ("key: F\nmeter: 4/4\ntempo: 120\n\nband:\n  trumpet\n"
            "  alto = alto sax\n  piano\n  bass\n  drums\n\n"
            "figure line, 8 bars:\n  notes: F4 w, G4 w, A4 w, Bb4 w, C5 w, "
            "D5 w, E5 w, F5 w\n\n"
            "section A, 8 bars, repeat 2x\n  chords: F x8\n"
            "  alto: figure line\n\n"
            "section B, 8 bars\n  chords: F x8\n  trumpet: figure line\n")
    open(cc, "w").write("title: C\n" + body)
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(cc, os.path.join(tmp_c, "b"))
    x = open(os.path.join(tmp_c, "b", "C — trumpet.musicxml")).read()
    check("a horn back after a long rest gets the phrase before its "
          "entrance cued small (one to four bars, the copyist's call), and "
          "the page says whose",
          "back in at bar 9 after 16 bars rest" in buf.getvalue()
          and "(alto cue)" in x and 1 <= x.count("<cue/>") <= 4,
          buf.getvalue()[-300:])
    open(cc, "w").write("title: C\n" + body.replace(
        "C5 w, D5 w, E5 w, F5 w", "C5 w, rest w, E5 w, F5 w"))
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(cc, os.path.join(tmp_c, "b3"))
    x3 = open(os.path.join(tmp_c, "b3", "C — trumpet.musicxml")).read()
    cue_notes = len(re.findall(r'<cue/>(?:(?!</note>).)*<pitch>', x3,
                               re.S))
    check("the cue starts where the melody last breathed: the two-bar "
          "phrase before the entrance", cue_notes == 2, str(cue_notes))
    open(cc, "w").write("title: C\ncues: no\n" + body)
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(cc, os.path.join(tmp_c, "b2"))
    check("'cues: no' in the header: no automatic cues",
          "cued small" not in buf.getvalue())
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    chartgroove.backgrounds(b, {}, [(1.0, ('F', 0, '7', None)),
                                    (3.0, ('B', -1, '7', None))],
                            0, 3, 60, 79, 'punch', 0, 'song')
    ns = [(t, ln, n) for t, (ln, ns_) in b.onsets.items() for n in ns_]
    check("backgrounds as punches: short accented hits on the changes",
          ns and all(ln <= 12 and n[3] == ('accent',) for _t, ln, n in ns),
          str(ns))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    for m in (41, 53, 57):
        b.add(0, 48, ('p', m, 70))
    b._above_the_bass(48)
    got = sorted(n[1] for n in b.onsets[0][1])
    check("with the bass playing, the piano's left hand stays above C3 "
          "(an F2 goes up to F3, not doubling the one already there)",
          got == [53, 57], str(got))
    tmp_b = tempfile.mkdtemp()
    cb = os.path.join(tmp_b, "b.chart")
    open(cb, "w").write(
        "title: B\nkey: F\nmeter: 4/4\ntempo: 100\n\nband:\n  trumpet\n"
        "\nfigure long, 8 bars:\n  notes: F4 w, G4 w, A4 w, Bb4 w, C5 w, "
        "D5 w, E5 w, F5 w\n\nsection A, 8 bars\n  chords: F x8\n"
        "  trumpet: figure long\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(cb, os.path.join(tmp_b, "o"))
    check("a written horn line with nowhere to breathe is named, with its "
          "bars and seconds", "bars 1-8 run 19 seconds with nowhere to "
          "breathe" in buf.getvalue(), buf.getvalue()[-400:])
    tmp_t = tempfile.mkdtemp()
    ct = os.path.join(tmp_t, "t.chart")
    open(ct, "w").write(
        "title: T\nkey: Bb\nmeter: 4/4\ntempo: 170\nfeel: swing\n\n"
        "band:\n  trumpet\n  tenor = tenor sax\n  piano\n  bass\n"
        "  drums\n\nsection solos, 12 bars\n  chords: Bb7 x12\n"
        "  trade 4s: trumpet, tenor, drums\n"
        "  ending: unison line, drum solo, go crazy, last hit\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(ct, os.path.join(tmp_t, "b"))
    x = open(os.path.join(tmp_t, "b", "T — for listening.musicxml")).read()
    names_ = dict(re.findall(r'<score-part id="([^"]+)"><part-name>([^<]*)',
                             x))
    who_ = {}
    for pid, body in re.findall(r'<part id="([^"]+)">(.*?)</part>', x, re.S):
        for n, m in re.findall(r'<measure number="(\d+)"[^>]*>(.*?)'
                               r'</measure>', body, re.S):
            if '<pitch>' in m or '<unpitched>' in m:
                who_.setdefault(int(n), set()).add(names_[pid])
    check("trading fours: trumpet 1-4, tenor 5-8, the drummer alone 9-12 "
          "with the band out",
          sum('trumpet' in who_.get(b, ()) for b in range(1, 5)) >= 3
          and not any('tenor' in who_.get(b, ()) for b in range(1, 5))
          and sum('tenor' in who_.get(b, ()) for b in range(5, 9)) >= 3
          and not any('trumpet' in who_.get(b, ()) for b in range(5, 9))
          and all(who_.get(b) == {'drums'} for b in range(9, 12)),
          str(sorted(who_.items())))
    ext = re.findall(r'<measure number="12e(\d)"', x)
    check("the ending plays unison, drum solo, the held chord, the hit",
          len(set(ext)) == 4 and "drum solo, out of time" in buf.getvalue(),
          str(ext))
    modes = set()
    for k in range(40):
        b = chartgroove.Bar(24, (4, 4), 0, 1)
        chartgroove.drum_solo(b, 100 + k * 4, 1, 4, 'drums%d' % k)
        foot = sum(1 for _l, ns in b.onsets.values() for n in ns
                   if n[1] == chartgroove._HATF)
        feath = sum(1 for _l, ns in b.onsets.values() for n in ns
                    if n[1] == chartgroove._KICK and n[2] == 30)
        modes.add((foot >= 3, 0 < foot <= 2, feath > 0))
    check("a drum solo's time is the drummer's call: the foot on 2 and 4, "
          "on all four, a feathered kick, or none",
          len(modes) >= 3, str(modes))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    b.add(24, 12, ('u', chartgroove._SNARE, 60))
    b.add(0, 24, ('u', chartgroove._RIDE, 80))
    chartgroove._chop_wood(b, '2tom')
    got = {t: [n[1] for n in ns] for t, (_l, ns) in b.onsets.items()}
    check("chopping wood on a shout: cross-stick on 2, high tom on 4 and "
          "its and, the ride still going, the comping snare out",
          got.get(24) == [chartgroove._XSTICK]
          and got.get(72) == [chartgroove._HI_TOM]
          and got.get(84) == [chartgroove._HI_TOM]
          and chartgroove._RIDE in got.get(0, []), str(got))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    b.add(0, 12, ('u', chartgroove._SNARE, 100))
    b.add(6, 6, ('u', chartgroove._SNARE, 90))
    chartgroove._chopping_hand(b, '24')
    got = {t: [n[1] for n in ns] for t, (_l, ns) in b.onsets.items()}
    check("chopping wood is solid: the cross-stick exactly on 2 and 4; "
          "the hand on the rim sends a stray snare to the kick, a fast "
          "one to the high tom",
          got.get(24) == [chartgroove._XSTICK]
          and got.get(72) == [chartgroove._XSTICK]
          and got.get(0) == [chartgroove._KICK]
          and got.get(6) == [chartgroove._HI_TOM]
          and sum(v.count(chartgroove._XSTICK) for v in got.values()) == 2,
          str(got))
    shapes = {}
    for how in ('copy', 'quarters', 'chick', 'skip'):
        b = chartgroove.Bar(24, (4, 4), 0, 1)
        for t in (0, 24, 40, 48, 72, 88):
            b.add(t, 12, ('u', chartgroove._RIDE, 76))
        chartgroove._hat_time(b, False, how)
        shapes[how] = tuple(sorted((t, n[1][0] + str(n[1][1]))
                                   for t, (_l, ns) in b.onsets.items()
                                   for n in ns))
        vels = [n[2] for _l, ns in b.onsets.values() for n in ns]
    check("the hi-hat swing has its ways (the ride's pattern, quarters, "
          "tsss-chick, skips), all different, none quiet",
          len(set(shapes.values())) == 4 and min(vels) >= 60, str(shapes))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    for t in (0, 24, 48, 72):
        b.add(t, 12, ('u', chartgroove._FLOOR_TOM, 90))
    chartgroove.solo_accents(b, chartgroove._Dice('acc'), 1.5)
    cym = [t for t, (_l, ns) in b.onsets.items() for n in ns
           if n[1] in (chartgroove._CRASH, chartgroove._OPEN_HAT)]
    check("a drum solo's crashes and open hats land on its own strokes, "
          "never a crash with the floor tom",
          cym and all(t in (0, 24, 48, 72) for t in cym)
          and not any(n[1] == chartgroove._CRASH
                      for _t, (_l, ns) in b.onsets.items() for n in ns),
          str(cym))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    chartgroove.drum_solo(b, 200, 0, 4, 'drums', echo=[
        (0.0, 0.5, 72), (0.5, 0.5, 76), (1.0, 1.0, 79)])
    first = [n[1] for t in sorted(b.onsets) for n in b.onsets[t][1]
             if n[1] in (chartgroove._FLOOR_TOM, chartgroove._MID_TOM,
                         chartgroove._HI_TOM, chartgroove._SNARE)]
    check("trading, the drummer opens answering the last phrase: its "
          "rhythm on the drums, its rising shape up the toms",
          first[:3] == [chartgroove._FLOOR_TOM, chartgroove._MID_TOM,
                        chartgroove._HI_TOM], str(first))
    import chartaudio
    import chartband
    tmp_k = tempfile.mkdtemp()
    ck = os.path.join(tmp_k, "k.chart")
    open(ck, "w").write(
        "title: K\nkey: F\nmeter: 4/4\ntempo: 140\nfeel: swing\n"
        "countoff: yes\n\nband:\n  trumpet\n  piano\n  bass\n  drums\n"
        "\nsection A, 2 bars\n  chords: F7, C7\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(ck, os.path.join(tmp_k, "b"))
    plan_k = chartaudio.parse_score(os.path.join(
        tmp_k, "b", "K — for listening.musicxml"))
    try:
        res_k = chartband.render_plan(plan_k, os.path.join(tmp_k, "k.wav"),
                                      tempfile.mkdtemp())
        err_k = None
    except Exception as e:          # the build would fall to the synth
        res_k, err_k = None, repr(e)
    check("the sample renderer plays a counted-off tune without falling "
          "back to the synth, the count in front of bar one",
          err_k is None and plan_k['count_off'] and res_k[3] > 0.5,
          str((err_k, plan_k['count_off'])))
    was_bpm = chartgroove.BPM
    try:
        chartgroove.BPM = 176.0
        so = chartgroove.roll_step(24) / 24 * 60 / 176
        sb = chartgroove.roll_step(24, buzz=True) / 24 * 60 / 176
        chartgroove.BPM = 70.0
        slow = chartgroove.roll_step(24, buzz=True)
    finally:
        chartgroove.BPM = was_bpm
    check("rolls stay inside real hands: at 176 an open roll no faster "
          "than ~13 strokes a second, a buzz roll the fastest, ~20; at a "
          "ballad the buzz is thirty-seconds",
          so >= 1 / 13.5 and 1 / 20.5 <= sb < so and slow == 3,
          str((so, sb, slow)))
    import chartending
    cues_, airs = set(), []
    for si in range(30):
        c, cl, air = chartending._seg_cue('song', si, 24)
        cues_.add(c)
        airs.append(air)
        assert (c, cl, air) == chartending._seg_cue('song', si, 24)
    check("a drummer's ending cue: many kinds, the same for everyone, and "
          "always half a beat or more of air before what comes next",
          len(cues_) >= 7 and min(airs) >= 12, str((cues_, min(airs))))
    kinds_ = set()
    for k in range(60):
        b = chartgroove.Bar(24, (4, 4), 0, 1)
        kinds_.add(chartgroove.land_hit(b, 0, 24, chartgroove._Dice(
            'land', k)))
    check("a fill lands the drummer's way: crash and snare, open hat and "
          "snare, open hat and kick, not only crash and kick",
          {'crash_snare', 'hat_snare', 'hat_kick', 'crash_kick'} <= kinds_,
          str(kinds_))
    tmp_f = tempfile.mkdtemp()
    cf = os.path.join(tmp_f, "f.chart")
    open(cf, "w").write(
        "title: F\nkey: F\nmeter: 4/4\ntempo: 130\nfeel: swing\n\n"
        "band:\n  trumpet\n  piano\n  bass\n  drums\n\n"
        "section A, 4 bars\n  chords: F x4\n  at bar 1: segno\n"
        "  at bar 3: to coda\n\nsection B, 4 bars\n  chords: Bb7 x4\n"
        "  at bar 4: d.s. al coda\n\nsection coda, 2 bars\n"
        "  chords: F x2\n  at bar 1: coda\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(cf, os.path.join(tmp_f, "b"))
    dp = open(os.path.join(tmp_f, "b", "F — drums.musicxml")).read()
    check("the drummer knows the form: a fill before the To Coda and the "
          "D.S., printed on the drum part",
          "fill before each road-map jump (bar 3, 8)" in buf.getvalue()
          and dp.count(">Fill<") >= 2, buf.getvalue()[-300:])
    strolled_ = []
    tmp_st = tempfile.mkdtemp()
    cs_ = os.path.join(tmp_st, "s.chart")
    open(cs_, "w").write(
        "title: Stroll\nkey: F\nmeter: 4/4\ntempo: 150\nfeel: swing\n\n"
        "band:\n  tenor = tenor sax\n  piano\n  bass\n  drums\n\n"
        "section solos, 12 bars, repeat 2x\n  chords: F7 x12\n"
        "  tenor: solo\n")
    was_take = chartc.TAKE
    try:
        for tk in range(1, 16):
            chartc.TAKE = tk
            o_ = os.path.join(tmp_st, str(tk))
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(cs_, o_)
            x_ = open(os.path.join(o_, "Stroll — for listening.musicxml")).read()
            pp = re.search(r'<part id="P2">(.*?)</part>', x_, re.S).group(1)
            first = [m for n, m in re.findall(
                r'<measure number="([^"]*)"[^>]*>(.*?)</measure>', pp, re.S)
                if n.isdigit() and 2 <= int(n) <= 10]
            strolled_.append(all('<pitch>' not in m for m in first))
    finally:
        chartc.TAKE = was_take
    check("the pianist strolls under a horn solo now and then, not always",
          any(strolled_) and sum(strolled_) <= len(strolled_) // 2,
          sum(strolled_))
    import chartband
    _d, _v, _b, bend, _a = chartband._shape({'shake': True}, 1.0, 90,
                                            'brass')
    ups = [p for _t, p in bend if p > 2]
    check("a lead trumpet's shake: the note wobbling up about a minor "
          "third and back, quickly, after the attack",
          len(ups) >= 4 and bend[1][0] >= 0.1, str(bend[:6]))
    seen = set()
    for k in range(40):
        b = chartgroove.Bar(24, (4, 4), 0, 1)
        kind = chartgroove.final_hit(b, 48, 24, chartgroove._Dice(
            'final', k), 60)
        seen.add(kind)
        rings = any(n[1] in (chartgroove._CRASH, chartgroove._OPEN_HAT)
                    and ln >= 48 for _t, (ln, ns) in b.onsets.items()
                    for n in ns)
        if not rings:
            break
    check("the last hit is the drummer's choice every take, and a held "
          "last chord always rings (crash or open hat)",
          rings and len(seen) >= 5, str(seen))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    k0 = chartgroove.final_hit(b, 0, 24, lambda: 0.99, 12)
    check("no lick lands late: a hit on the downbeat never starts one",
          k0 not in ('ssk', 'shfk') and min(b.onsets) == 0, k0)
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    for m in (60, 64, 70, 74):
        b.add(0, 48, ('p', m, 80))
    b._hear_the_lead([(0.0, 2.0, 67)])
    got = sorted(n[1] for n in b.onsets[0][1])
    check("a comper stays under the melody: the voicing's top moves down "
          "an octave under a G4 lead", max(got) < 67 and 62 in got, str(got))
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    b.add(0, 48, ('p', 64, 80))
    b._hear_the_lead([(0.0, 2.0, 58)])
    check("a low lead (a tenor down at Bb3) is voiced over, as usual",
          [n[1] for n in b.onsets[0][1]] == [64])
    b = chartgroove.Bar(24, (4, 4), 0, 1)
    b.add(0, 48, ('p', 69, 80))
    b._hear_the_lead([(0.5, 1.0, 70)])
    fn = lambda t: ('B', -1, 'maj7', None) if t < 3 else \
        ('A', 0, 'm7', None)
    got = chartgroove._knows_the_changes(
        [(0.0, 1.0, 68, 80), (3.0, 0.5, 70, 80), (3.5, 0.5, 69, 80)], fn)
    check("a soloist's Ab over Bbmaj7 moves to a note that fits; a Bb "
          "stepping into the A over Am7 stays, it's an approach",
          got[0][2] in (67, 69) and [n[2] for n in got[1:]] == [70, 69],
          str(got))
    check("the blues lick waits for a chord it belongs on",
          chartgroove._blue_ok(('B', -1, '7', None))
          and chartgroove._blue_ok(('C', 0, 'm7', None))
          and not chartgroove._blue_ok(('B', -1, 'maj7', None)))
    check("a passing eighth off the beat is not voiced around",
          [n[1] for n in b.onsets[0][1]] == [69])
    import chartdemo
    tmp0 = tempfile.mkdtemp()
    sp = os.path.join(tmp0, "s.chart")
    open(sp, "w").write(
        "title: S\nkey: Bb\nmeter: 4/4\ntempo: 120\n\nband:\n  trumpet\n"
        "  alto = alto sax\n  tenor = tenor sax\n  bone = trombone\n"
        "  bari = baritone sax\n\ngroup section: trumpet, alto, tenor, "
        "bone, bari\n\nfigure f, 2 bars:\n  notes: D5 q, F5 q, A5 q, F5 q,"
        " D5 w\n\nsection A, 2 bars\n  chords: Bbmaj7, Cm7 F7\n"
        "  trumpet: figure f\n  section: soli on trumpet\n")
    ch = chartc.parse_chart(sp)
    bd = ch['band']
    gr = chartc.resolve_groups(bd, ch.get('groups'))
    lb = [x['label'] for x in bd]
    pl, _t = chartc.build_plans(ch, bd, gr, lb)
    rs, _h, _k = chartc.resolve_demo(ch, pl, bd, lb, sp,
                                     chartdemo.Findings(), (4, 4))
    col = [[rs[l][0]['res']['timeline'][i][2][0] for l in lb]
           for i in range(5)]
    check("soli: the trumpet's D over Bbmaj7 voiced D G F D (a sixth, "
          "drop 2, the lead doubled below) with the bari on the root, low",
          col[0] == [74, 67, 65, 62, 46], str(col[0]))
    check("soli: the lead on the major seventh keeps it (A F... over "
          "Bbmaj7)", col[2][0] == 81 and 69 in col[2], str(col[2]))
    check("soli: every chair a different note, top to bottom",
          all(c == sorted(c, reverse=True) and len(set(c)) == 5
              for c in col), str(col))
    sec = chartc.section_header("vamp", ", 2 bars, vamp 4 times", "t")
    check("header: vamp 4 times", sec['repeat'] == 4 and sec['vamp']
          and not sec['open'])
    sec = chartc.section_header(
        "vamp", ', label "Vamp", 4 bars, vamp till cue', "t")
    check("header: label, bars, vamp till cue in any order",
          sec['open'] and sec['vamp'] and sec['bars'] == 4
          and sec['label'] == 'Vamp')
    sec = chartc.section_header("A", ", 8 bars, play 3 times", "t")
    sec2 = chartc.section_header("A", ", 8 bars, x3", "t")
    check("header: play 3 times and x3", sec['repeat'] == 3
          and sec2['repeat'] == 3)
    try:
        chartc.section_header("A", ", 8 bars, wiggle", "t")
        said = ""
    except SystemExit as e:
        said = str(e.code)
    check("header: an unknown word says what a section takes",
          "cannot read 'wiggle'" in said, said)
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "v.chart"), "w").write(
        "title: V\nkey: F\nmeter: 4/4\ntempo: 140\nfeel: swing\n\n"
        "band:\n  vibes\n  piano\n  bass\n  drums\n\n"
        "section head, 4 bars\n  chords: Fmaj7, Bbmaj7, Gm7 C7, Fmaj7\n\n"
        "section solos, 8 bars\n  chords: Fmaj7, Bbmaj7, Gm7, C7, Am7, "
        "D7, Gm7, C7\n  vibes: solo\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(os.path.join(tmp, "v.chart"),
                             os.path.join(tmp, "b"))
    out = buf.getvalue()
    check("vibes the chart gave nothing leave the comping to the piano",
          "vibes leaves the comping to the piano or guitar in head" in out,
          out[-600:])
    x = open(os.path.join(tmp, "b", "V — for listening.musicxml")).read()
    vib = re.search(r'<part id="P1">(.*?)</part>', x, re.S).group(1)
    solo = "".join(m for n, m in re.findall(
        r'<measure number="(\d+)">(.*?)</measure>', vib, re.S)
        if 5 <= int(n) <= 11)
    last = "".join(m for n, m in re.findall(
        r'<measure number="(\d+)">(.*?)</measure>', vib, re.S)
        if int(n) == 12)
    lows = [12 * (int(o) + 1) + "C D EF G A B".index(st) + int(a or 0)
            for st, a, o in re.findall(
                r'<step>(\w)</step>(?:<alter>(-?\d)</alter>)?'
                r'<octave>(\d)</octave>', last)]
    check("the vibes' last chord sits on the bars (F3 and up), four "
          "mallets, no pianist's low root", lows and min(lows) >= 53,
          str(lows))
    head = "".join(m for n, m in re.findall(
        r'<measure number="(\d+)">(.*?)</measure>', vib, re.S)
        if int(n) <= 4)
    check("a vibes solo is a line: no chords stacked under it",
          "<pitch>" in solo and "<chord/>" not in solo)
    check("vibes lay out while the piano comps the head",
          "<pitch>" not in head)


def check_bandleader_round():
    """Faith as bandleader, 2026-09-30, writing Lantern Waltz by hand:
    a double harmonized in scale steps ('alto: double flugel a sixth
    below'), a bare 'alto' on the band list meaning the sax, tempo words
    said bare after 'at bar N:', plain sentences where the writer's
    first instinct is wrong, and the read-aloud giving printed bars."""
    import chartc
    import chartread
    check("harmony phrase: a third below, in sixths above, a 10th under",
          chartc.harmony_phrase("flugel a third below") == ("flugel", -2)
          and chartc.harmony_phrase("trumpet 1 in sixths above")
          == ("trumpet 1", 5)
          and chartc.harmony_phrase("alto a 10th under") == ("alto", -9)
          and chartc.harmony_phrase("alto an octave down")
          == ("alto an octave down", 0))
    res = {'at': 1, 'timeline': [(0, 1, [72]), (1, 2, [69]), (2, 3, [66]),
                                 (3, 4, [62])]}
    got = [ps[0] for _, _, ps in
           chartc.harmonize_res(res, -5, (-1, 'major'))['timeline']]
    # in F: C5->E4, A4->C4, F#4 (bent from F) ->A3, D4->F3
    check("harmonize: sixths below in F, a chromatic note from its scale "
          "tone", got == [64, 60, 57, 53], str(got))
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "w.chart"), "w").write(
        "title: W\nkey: F\nmeter: 3/4\ntempo: 150\nfeel: jazz waltz\n\n"
        "band:\n  flugel = flugelhorn\n  alto\n  bass\n  drums\n\n"
        "figure f, 2 bars:\n  notes: C5 h., A4 q, G4 q, F4 q\n\n"
        "section A, 4 bars\n  chords: F, F, C7, F\n  at bar 1: segno\n"
        "  at bar 3: rit.\n  flugel: figure f\n"
        "  alto: double flugel a third below\n\n"
        "section B, 2 bars\n  chords: C7, F\n  at bar 1: key G\n"
        "  flugel: figure f\n  alto: double flugel\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(os.path.join(tmp, "w.chart"),
                             os.path.join(tmp, "b"))
    out = buf.getvalue()
    check("band: a bare 'alto' is the alto sax; the double says its third",
          "doubles the flugel a third below" in out, out[-400:])
    x = open(os.path.join(tmp, "b", "W — score.musicxml")).read()
    check("at bar N: rit. prints the word", ">rit.<" in x)
    old = sys.argv
    sys.argv = ["chartread", os.path.join(tmp, "w.chart"), "--part", "alto"]
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            chartread.main()
    finally:
        sys.argv = old
    said = buf.getvalue()
    check("read-aloud: marks at printed bars, a first-bar key change "
          "says here", "At bar 3: \"rit.\"" in said
          and "the key changes to G here" in said
          and "You double the flugel a third below" in said, said)

    def refusal(body):
        open(os.path.join(tmp, "r.chart"), "w").write(
            "title: R\nkey: C\nmeter: 4/4\ntempo: 100\n\nband:\n"
            + body)
        try:
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(os.path.join(tmp, "r.chart"),
                                     os.path.join(tmp, "rb"))
        except SystemExit as e:
            return str(e.code)
        return ""
    import chartbraille
    import chartbrailleread
    check("braille: 'rit.' ends on its own dot 3, no second one after it",
          not chartbraille._ends_in_word(
              chartbraille.Words(chartbraille.expression("rit.")))
          and chartbraille._ends_in_word(
              chartbraille.Words(chartbraille.expression("big"))))
    check("braille proofreader: a short word and a space is not a longer "
          "expression, so one wrapping after it is still open",
          chartbrailleread._open_expr("#BI <7\" >SHOUT CHORUS> >BIG "
                                      ">OPEN1 TILL"))
    said = refusal("  kazoo\n\nsection A, 1 bars\n  chords: C\n")
    check("band: an unknown instrument asks what it is, no traceback",
          "'kazoo' is not an instrument Copyist knows" in said, said)
    said = refusal("  trumpet\n\nsection A, 1 bars\n  chords: C\n"
                   "  trumpet: notes: C5 w\n")
    check("notes: on a part's line points at a figure",
          "notes: goes in a figure" in said, said)
    said = refusal("  trumpet\n\nsection A, 1 bars\n  chords: C\n"
                   "  at bar 1: wobble\n")
    check("at bar N: an unknown word lists what it takes",
          "After 'at bar N:' Copyist takes" in said, said)


def check_double_an_octave_off():
    """An arranger's double sits an octave off as often as not: 'tenor:
    double trumpet an octave down', '8vb', 'two octaves up'. The line
    moves by the octave on the page, in the listen and in the words
    (findings and the read-aloud say it), and the verb can come first on
    the command line: 'chart check song.chart'."""
    import subprocess
    import chartaudio
    import chartc
    import smf
    check("octave phrase: an octave down",
          chartc.octave_phrase("trumpet an octave down") == ("trumpet", -12))
    check("octave phrase: 8va, two octaves, bare name",
          chartc.octave_phrase("trumpet 1 8va") == ("trumpet 1", 12)
          and chartc.octave_phrase("flute two octaves lower")
          == ("flute", -24)
          and chartc.octave_phrase("alto") == ("alto", 0))
    tmp = tempfile.mkdtemp()
    div = 480
    smf.write(os.path.join(tmp, "d.mid"),
              [(i * div, i * div + 400, 60 + i, 90) for i in range(8)],
              div, 100)
    chart = os.path.join(tmp, "f.chart")
    open(chart, "w").write(
        'title: D\nkey: C\nmeter: 4/4\ntempo: 100\ndemo: d.mid\n\n'
        'band:\n  trumpet\n  tenor = tenor sax\n  flute\n\n'
        'section A, 4 bars\n  chords: C, F, G, C\n'
        '  trumpet: from demo bars 1-2\n'
        '  tenor: double trumpet an octave down\n'
        '  flute: double trumpet 8va\n')
    out = os.path.join(tmp, "b")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(chart, out)
    plan = chartaudio.parse_score(
        os.path.join(out, "D — for listening.musicxml"))
    ev = {p['name']: [e[2] for e in p['events']] for p in plan['parts']}
    check("an octave down plays an octave down",
          ev['tenor'] == [n - 12 for n in ev['trumpet']] and ev['tenor'])
    check("8va plays an octave up",
          ev['flute'] == [n + 12 for n in ev['trumpet']])
    check("the findings say the octave",
          "doubles the trumpet an octave down" in buf.getvalue())
    env = dict(os.environ, HOME=tmp, USERPROFILE=tmp)
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "chart.py"),
                        "check", chart], capture_output=True, text=True,
                       env=env, cwd=tmp)
    check("the verb can come first", r.returncode == 0
          and "compiles" in r.stdout + r.stderr)
    r = subprocess.run([sys.executable, os.path.join(here, "chart.py"),
                        chart, "read", "--part", "tenor"],
                       capture_output=True, text=True, env=env, cwd=tmp)
    check("the read-aloud says the octave",
          "double the trumpet an octave down" in r.stdout)
    shutil.rmtree(tmp, ignore_errors=True)


def check_head_out_plays_the_head():
    """Harbor Lights, a tune told from nothing (2026-09-29): "upright"
    dropped the bass player; "head out" over a head carved AABA asked
    its bars (the out could borrow only one section); naming the alto
    in the head printed slashes on a horn page and sent the congas out;
    the out went tacet on the horns; and the same A melody had to be
    said three times. Now the out plays the head's lineup and melody,
    A2 and A3 offer A's tune, and a horn named alone has the tune."""
    import subprocess
    import chartedit, chartnew
    band, unknown = chartnew.band_from_words("upright, stand-up bass")
    check("upright is the bass player",
          [i for _, i in band] == ["double bass", "double bass"]
          and not unknown, repr((band, unknown)))
    L = ["alto", "trumpet", "piano", "congas"]
    try:
        chartedit.parse_who("alto", L, [], tune_labels=["alto", "trumpet"])
        got = None
    except chartedit.MelodyLater as e:
        got = e.targets
    check("a horn named alone has the tune", got == ["alto"], repr(got))
    check("a rhythm player named alone still grooves",
          chartedit.parse_who("piano", L, [], tune_labels=["alto"])
          == ["piano: groove"])
    tmp = tempfile.mkdtemp()
    chart = os.path.join(tmp, "h.chart")
    open(chart, "w").write("title: H\nkey: F\nmeter: 4/4\ntempo: 120\n\n"
                           "band:\n  alto = alto sax\n  piano\n"
                           "  bass\n  drums\n  congas\n")
    A = "F4 w, G4 w, A4 w, C5 w"
    B = "Bb4 w, A4 w, G4 w, F4 w"
    answers = ["head is 16 bars AABA, solos over the head, head out",
               "carve", "F, Gm7, C7, F", "alto", "yes", "alto",
               "Bb, Bbm, F, C7", "alto", "yes", "alto", "alto", "",
               A, "1", "yes", "yes", B, "1", "yes", "yes", "", "", ""]
    env = dict(os.environ, HOME=tmp, USERPROFILE=tmp)
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "chart.py"),
                        chart, "edit"], input="\n".join(answers) + "\n",
                       capture_output=True, text=True, env=env, cwd=tmp)
    txt = open(chart).read()
    out = txt[txt.index("section out"):]
    check("the head out plays the head's figures, bar for bar",
          "alto: figure alto A bar 1 at bar 1" in out
          and "alto: figure alto B bar 1 at bar 9" in out
          and "alto: figure alto A bar 1 at bar 13" in out,
          r.stdout[-400:] + r.stderr[-400:])
    a2 = txt[txt.index("section A2"):txt.index("section B")]
    check("A2 offers A's melody", "alto: figure alto A bar 1" in a2)
    a1 = txt[txt.index("section A,"):txt.index("section A2")]
    check("naming the alto keeps the congas in",
          "congas: groove" in a1 and "alto: groove" not in txt)
    shutil.rmtree(tmp, ignore_errors=True)


def check_words_perform():
    """A word on the page is an instruction to the band, so the listen
    does it (Matthew, 2026-09-29: "if you type text in notation software
    there's generally silence"): rit. and rall. slow down to the next
    a tempo or the end, molto more and poco less, accel. speeds up,
    fade out turns the band down to nothing by the last note."""
    import chartaudio
    import chartc
    pw = chartaudio.perform_word
    check("words that perform are read",
          pw("rit.") == ("rit", 0.7) and pw("molto rit.")[1] < 0.7
          and pw("poco rall.")[1] > 0.7 and pw("a tempo")[0] == "atempo"
          and pw("Fade out")[0] == "fade" and pw("accel.")[0] == "accel"
          and pw("riff") is None and pw("crit") is None)
    tmp = tempfile.mkdtemp()

    def listen(extra):
        open(os.path.join(tmp, "t.chart"), "w").write(
            "title: T\nkey: C\nmeter: 4/4\ntempo: 120\n\nband:\n"
            "  piano\n  bass\n  drums\n\nsection A, 8 bars\n"
            "  chords: C, F, G, C, C, F, G7, C\n"
            "  ending: as written\n" + extra)
        out = os.path.join(tmp, "b")
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
        pl = chartaudio.parse_score(
            os.path.join(out, "T — for listening.musicxml"))
        return pl, chartaudio._sec_of(pl["end_q"], pl["tempos"],
                                      pl.get("holds", ()))
    _, plain = listen("")
    _, rit = listen('  all: text "rit." at bar 7\n')
    _, back = listen('  all: text "rit." at bar 5\n'
                     '  all: text "a tempo" at bar 7\n')
    fpl, _ = listen('  all: text "fade out" at bar 5\n')
    check("rit. at bar 7 stretches the last two bars",
          abs(plain - 16.0) < 0.01 and 16.4 < rit < 17.2, (plain, rit))
    check("a tempo puts the tempo back",
          fpl["fade"] == 16.0 and chartaudio._sec_of(
              32, listen('  all: text "rit." at bar 5\n'
                         '  all: text "a tempo" at bar 7\n')[0]["tempos"])
          - chartaudio._sec_of(24, listen(
              '  all: text "rit." at bar 5\n'
              '  all: text "a tempo" at bar 7\n')[0]["tempos"]) < 4.01,
          back)
    shutil.rmtree(tmp, ignore_errors=True)


def check_solos_and_endings():
    """The page says solo and nothing was played in: the soloist plays
    over the changes in the listen, soloists named together take turns,
    a played-in solo still wins. An ending line performs: hold, fills,
    noodling over the last chord, the hit on the cue, cold, button,
    trash can (Matthew, 2026-09-29)."""
    import re as _re
    import chartaudio
    import chartc
    import chartending
    st = chartending.parse("hold, drums fill, last hit on cue",
                           ["drums", "tenor"])
    check("ending steps read in order, the cue on the hit",
          st == [("hold", None), ("fill", "drums"), ("hit", "cue")])
    try:
        chartending.parse("hold, kazoo solo", ["drums"])
        bad = None
    except chartending.EndingError as e:
        bad = str(e)
    check("an unknown ending step is named", bad and "kazoo" in bad)
    tmp = tempfile.mkdtemp()

    def build(sections):
        open(os.path.join(tmp, "t.chart"), "w").write(
            "title: T\nkey: F\nmeter: 4/4\ntempo: 120\n\nband:\n"
            "  tenor = tenor sax\n  trumpet\n  piano\n  bass\n"
            "  drums\n\nfigure mel, 4 bars:\n"
            "  notes: F4 w, G4 w, A4 w, F4 w\n\n" + sections)
        out = os.path.join(tmp, "b")
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
        return out, chartaudio.parse_score(
            os.path.join(out, "T — for listening.musicxml"))
    out, pl = build("section A, 8 bars\n  chords: F, Bb7, F, C7, "
                    "F, Bb7, C7, F\n  tenor: solo\n  trumpet: solo\n")
    ev = {p["name"]: p["events"] for p in pl["parts"]}
    check("soloists play over the changes, taking turns",
          ev["tenor"] and ev["trumpet"]
          # the first may spill into the next player's first bar
          and max(e[0] for e in ev["tenor"]) < 20
          and min(e[0] for e in ev["trumpet"]) >= 16
          and all(min(abs(e[0] * 2 - round(e[0] * 2)),
                      abs(e[0] * 3 - round(e[0] * 3))) < 0.03
                  for n in ("tenor", "trumpet") for e in ev[n]
                  if e[0] < 28),     # the ending's hit lands a hair apart
          {n: [round(e[0], 2) for e in ev[n]] for n in ("tenor",
                                                         "trumpet")})
    tpage = open(os.path.join(out, "T — tenor.musicxml")).read()
    check("the page keeps its slashes and the word",
          "slash" in tpage and ">Solo<" in tpage)
    out, pl = build("section A, 4 bars\n  chords: F, Bb7, C7, F\n"
                    "  tenor: figure mel\n  ending: hold, trumpet "
                    "noodles, drums fill, last hit on cue\n")
    ev = {p["name"]: p["events"] for p in pl["parts"]}
    tp = open(os.path.join(out, "T — tenor.musicxml")).read()
    hit_at = max(e[0] for e in ev["drums"])
    check("the hold rings past the last bar, then one hit, off the grid",
          16.0 < hit_at < 28.0 and pl["end_q"] > hit_at
          and len({round(e[0], 3) for e in ev["drums"]
                   if e[0] >= hit_at - 0.01}) == 1, hit_at)
    check("the tenor holds its own written last note",
          any(e[2] == 65 and e[1] >= 11 for e in ev["tenor"]))
    check("a player the ending names comes in for it",
          any(e[0] > 12.5 for e in ev["trumpet"]))
    check("the page says the ending and holds",
          "last hit on cue" in tp and "<fermata" in tp)
    out, pl = build("section A, 4 bars\n  chords: F, Bb7, C7, F\n"
                    "  ending: cold\n")
    check("cold: one hit on the last downbeat",
          all(e[0] <= 12.2 for p in pl["parts"]
              for e in p["events"] if e[0] >= 12))
    try:
        build("section A, 4 bars\n  chords: F, Bb7, C7, F\n"
              "  ending: cold\nsection B, 4 bars\n  chords: F x4\n")
        wrong = None
    except SystemExit as e:
        wrong = str(e.code)
    check("an ending must sit on the last section",
          wrong and "last section" in wrong)
    shutil.rmtree(tmp, ignore_errors=True)


def check_backgrounds_and_vamps():
    """Backgrounds with no notes are made up behind the soloist, the
    horns voicing each chord top-down (pads, or a riff, 'on cue' from
    halfway); the page prints slashes and changes. An open section or
    'vamp till cue' prints once between repeat signs and goes round a
    few times in the listen, the solo over it new each pass."""
    import chartaudio
    import chartc
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "t.chart"), "w").write(
        "title: T\nkey: F\nmeter: 4/4\ntempo: 120\n\nband:\n"
        "  tenor = tenor sax\n  trumpet\n  alto = alto sax\n"
        "  bone = trombone\n  piano\n  bass\n  drums\n\n"
        "section A, 8 bars\n  chords: F7, Bb7, F7, C7, F7, Bb7, C7, F7\n"
        "  tenor: solo\n  trumpet: backgrounds\n  alto: backgrounds\n"
        "  bone: backgrounds\n\nsection vamp, 2 bars, vamp till cue\n"
        "  chords: Gm7, C7\n  tenor: solo\n  ending: as written\n")
    out = os.path.join(tmp, "b")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
    pl = chartaudio.parse_score(os.path.join(out,
                                             "T — for listening.musicxml"))
    ev = {p["name"]: p["events"] for p in pl["parts"]}
    # the first background chord (they wait while the soloist is busy)
    t0 = min((e[0] for n in ("trumpet", "alto", "bone") for e in ev[n]
              if e[0] < 32), default=0)
    first = {n: [e[2] for e in ev[n] if abs(e[0] - t0) < 0.05] for n in
             ("trumpet", "alto", "bone")}
    check("backgrounds voice the chord across the horns, top horn on top",
          all(first.values()) and first["trumpet"][0] > first["alto"][0]
          > first["bone"][0], first)
    check("no false 'never plays' alarm for backgrounds",
          "NEVER PLAYS" not in buf.getvalue())
    tp = open(os.path.join(out, "T — trumpet.musicxml")).read()
    check("backgrounds print slashes under the changes",
          "slash" in tp and "<harmony" in tp)
    tn = open(os.path.join(out, "T — tenor.musicxml")).read()
    check("a vamp prints once between repeat signs, till cue",
          'repeat direction="forward"' in tn and "vamp till cue" in tn)
    n_pass = round((pl["end_q"] - 32) / 8)
    check("the vamp goes round in the listen, a different number of times "
          "each take", abs(pl["end_q"] - 32 - 8 * n_pass) < .01
          and 2 <= n_pass <= 5, pl["end_q"])
    passes = [[e[2] for e in ev["tenor"] if 32 + 8 * k <= e[0] < 40 + 8 * k]
              for k in range(n_pass)]
    check("each pass round the vamp is new", len(
        {tuple(p) for p in passes}) == n_pass, passes)
    shutil.rmtree(tmp, ignore_errors=True)


def check_explode():
    """Explode, the way MuseScore and Sibelius do it (Matthew,
    2026-09-29: from anything — a piano track, a horn part played in
    chords, strings — or divisi): top note to the highest-reaching
    chair, the next down; a short chord doubles evenly or repeats its
    lowest note; each chair written for its own horn."""
    import chartaudio
    import chartc
    import smf
    er = chartc.explode_res
    one = {"timeline": [(0, 96, [60, 64, 67, 71])]}
    check("explode: four notes to four chairs, top down",
          [er(one, k, 4)["timeline"][0][2][0] for k in range(4)]
          == [71, 67, 64, 60])
    two = {"timeline": [(0, 96, [60, 67])]}
    check("explode: a two-note chord on four chairs doubles evenly",
          [er(two, k, 4)["timeline"][0][2][0] for k in range(4)]
          == [67, 67, 60, 60])
    three = {"timeline": [(0, 96, [60, 64, 67])]}
    check("explode: three on four repeats the lowest",
          [er(three, k, 4)["timeline"][0][2][0] for k in range(4)]
          == [67, 64, 60, 60])
    check("explode: a note under the floor moves up an octave",
          er({"timeline": [(0, 96, [40])]}, 0, 1, fold=(52, 80))
          ["timeline"][0][2][0] == 52)
    tmp = tempfile.mkdtemp()
    div = 480
    notes = []
    for i, ch in enumerate([[65, 69, 72, 76], [65, 70, 74, 77]]):
        notes += [(i * 4 * div, i * 4 * div + 4 * div - 40, p, 90)
                  for p in ch]
    smf.write(os.path.join(tmp, "keys.mid"), notes, div, 100)
    open(os.path.join(tmp, "t.chart"), "w").write(
        "title: T\nkey: F\nmeter: 4/4\ntempo: 100\n\nband:\n"
        "  trumpet\n  alto = alto sax\n  bone = trombone\n"
        '  piano, demo "keys.mid"\n\n'
        "group section: bone, alto, trumpet\n\n"
        "section A, 2 bars\n  chords: Fmaj7, Bb\n"
        "  piano: from demo bars 1-2\n  section: explode piano\n")
    out = os.path.join(tmp, "b")
    buf = io.StringIO()
    with redirect_stdout(buf):
        chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
    pl = chartaudio.parse_score(os.path.join(out,
                                             "T — for listening.musicxml"))
    ev = {p["name"]: [e[2] for e in p["events"]] for p in pl["parts"]}
    check("explode in a chart: the highest horn takes the top voice, "
          "whatever order the group was typed in",
          ev["trumpet"] == [76, 77] and ev["alto"] == [72, 74]
          and ev["bone"] == [69, 70], ev)
    check("the findings say where the line came from",
          "exploded from the piano" in buf.getvalue())
    shutil.rmtree(tmp, ignore_errors=True)


def check_endings_feel_natural():
    """Endings played, not placed (Matthew, 2026-09-29): only what the
    roadmap says; where it says nothing the band chooses from the feel,
    differently in every tune, never rewriting a written ending; hits
    land a hair apart; 'as written' adds nothing; a drummer's tag and a
    keys gliss are steps; the band's choice never contradicts what the
    roadmap already said."""
    import chartaudio
    import chartc
    import chartending
    st = chartending.parse('button, drums tag "floor tom, floor tom, '
                           'bass drum"', ["drums"])
    check("a drummer's tag spelled out, commas inside the quotes",
          st[1] == ("tag", ("drums", ["floor tom", "floor tom",
                                      "bass drum"])))
    check("a keys gliss and horns falling are steps",
          chartending.parse("hold, piano gliss, horns fall",
                            ["piano"], {"horns": ["trumpet"]})
          == [("hold", None), ("gliss", "piano"),
              ("art", ("horns", "falloff"))])
    picks = {tuple(k for k, _ in chartending.band_choice(
        "swing", (t, "A"), True, True)) for t in
        ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot")}
    check("left to the band, swing tunes end in different ways",
          len(picks) >= 3, picks)
    tmp = tempfile.mkdtemp()

    def build(ending, title="T"):
        open(os.path.join(tmp, "t.chart"), "w").write(
            f"title: {title}\nkey: F\nmeter: 4/4\ntempo: 120\n\nband:\n"
            "  tenor = tenor sax\n  piano\n  bass\n  drums\n\n"
            "figure mel, 4 bars:\n  notes: F4 w, G4 w, A4 w, F4 w\n\n"
            "section A, 4 bars\n  chords: F, Bb7, C7, F\n"
            "  tenor: figure mel\n" + (f"  ending: {ending}\n"
                                        if ending else ""))
        out = os.path.join(tmp, "b")
        buf = io.StringIO()
        with redirect_stdout(buf):
            chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
        return buf.getvalue(), out, chartaudio.parse_score(os.path.join(
            out, f"{title} — for listening.musicxml"))
    said, out, pl = build("")
    tn = open(os.path.join(out, "T — tenor.musicxml")).read()
    ev = {p["name"]: p["events"] for p in pl["parts"]}
    check("no ending in the roadmap: the band's choice is said, the page "
          "untouched", "the band chose one" in said
          and "<fermata" not in tn)
    check("the band's choice leaves a written last note as written",
          [e[1] for e in ev["tenor"]][-1] < 4.01)
    _, _, pl = build("as written")
    check("'as written' ends where the notes end",
          abs(pl["end_q"] - 16) < 0.01)
    _, _, pl = build("hold, last hit")
    hits = sorted(e[0] for p in pl["parts"] for e in p["events"]
                  if e[0] > 16)
    _, _, plw = build("hold, watch each other, last hit")
    hitsw = sorted(e[0] for p in plw["parts"] for e in p["events"]
                   if e[0] > 16)
    check("the last hit lands a hair apart, tighter when they watch",
          hits and hits[-1] - hits[0] > 0
          and hitsw[-1] - hitsw[0] < hits[-1] - hits[0], (hits, hitsw))
    _, _, pl = build("hold, piano gliss")
    pn = [e for e in {p["name"]: p["events"] for p in pl["parts"]}
          ["piano"] if e[0] > 12]
    check("the piano glisses up off the last chord",
          len(pn) > 10 and pn[-1][2] > pn[5][2])
    shutil.rmtree(tmp, ignore_errors=True)


def check_solos_tell_a_story():
    """A solo is planned whole and tells a story (Matthew, 2026-09-29):
    space around the idea early, higher and busier at the peak, home to
    a long last note held over the barlines; a repeated solo section is
    one story across every chorus. Comping grows through the tune, two
    notes early, the extensions later."""
    import chartaudio
    import chartc
    import chartgroove as G
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "t.chart"), "w").write(
        "title: Story\nkey: F\nmeter: 4/4\ntempo: 140\nfeel: swing\n\n"
        "band:\n  tenor = tenor sax\n  piano\n  bass\n  drums\n\n"
        "chords blues: F7, Bb7, F7, Cm7 F7, Bb7, Bdim7, F7, Am7 D7, "
        "Gm7, C7, F7 D7, Gm7 C7\n\n"
        "section solos, 12 bars, repeat 3x\n  use chords blues\n"
        "  tenor: solo\n  ending: as written\n")
    out = os.path.join(tmp, "b")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
    pl = chartaudio.parse_score(os.path.join(out,
                                             "Story — for listening.musicxml"))
    t = next(p for p in pl["parts"] if p["name"] == "tenor")["events"]
    early = [e for e in t if e[0] < 40]
    peak = [e for e in t if 96 <= e[0] < 128]
    check("the solo spans every chorus of a repeated section",
          max(e[0] for e in t) > 120 and abs(pl["end_q"] - 144) < .01)
    builds = []
    was_take = chartc.TAKE
    try:
        for tk in range(1, 7):
            chartc.TAKE = tk
            o_ = os.path.join(tmp, "tk%d" % tk)
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(os.path.join(tmp, "t.chart"), o_)
            t_ = next(p for p in chartaudio.parse_score(os.path.join(
                o_, "Story — for listening.musicxml"))["parts"]
                if p["name"] == "tenor")["events"]
            builds.append(len([e for e in t_ if e[0] < 40])
                          < len([e for e in t_ if 96 <= e[0] < 128]))
    finally:
        chartc.TAKE = was_take
    check("early on there is space: fewer notes than at the peak (most "
          "takes; a take may start hot)", sum(builds) >= 4, builds)
    check("the peak sits higher than the opening",
          sum(e[2] for e in peak) / len(peak)
          > sum(e[2] for e in early) / len(early) + 3)
    check("it comes home at the end, long or short, not trailing off",
          t[-1][0] > 132)
    got = {}
    for heat in (0.3, 0.9):
        b = G.Bar(24, (4, 4), 0, 1)
        G._comp(b, {}, 5, "bossa", [(1.0, ("F", 0, "7", None))],
                "keyboard.piano", heat)
        got[heat] = max(len(n) for _, n in b.onsets.values())
    check("comping grows: three notes early, four with extensions later",
          got[0.3] == 3 and got[0.9] == 4, got)
    shutil.rmtree(tmp, ignore_errors=True)


def check_players_listen_to_each_other():
    """Players react (Matthew, 2026-09-29): a soloist's end may spill
    into the next one's first bar, and the next opens by answering the
    phrase it heard; drummers change implements (brushes on a ballad or
    when the chart says, stirs on the brush kit, sticks back); brass
    reach for mutes on made-up parts when the chart leaves it to them,
    and a mute the chart names always wins."""
    import chartaudio
    import chartc
    import chartgroove as G
    import sfz
    plan = [(0, .5, 60, 70), (0.5, .5, 62, 70), (4, .5, 65, 70),
            (4.5, .5, 67, 70), (5, 1, 69, 70)]
    ph = G.last_phrase(plan, 8)
    check("the next soloist hears the last phrase, after the breath",
          [m for _a, _l, m in ph] == [65, 67, 69] and ph[0][0] == 0)
    check("brushes on a ballad, sticks when the chart says",
          G.implement("", "ballad") == "brushes"
          and G.implement('sticks', "ballad") == "sticks"
          and G.implement("", "swing") == "sticks")
    inst = sfz.SfzInstrument.__new__(sfz.SfzInstrument)
    inst.cc = {55: 63.5}
    check("SFZ 1 envelope CCs are read (the brush stirs' length)",
          abs(inst._mod({"ampeg_attackcc55": "2"}, "ampeg_attack", 0)
              - 1.0) < 0.01)
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "t.chart"), "w").write(
        "title: Trade Test\nkey: F\nmeter: 4/4\ntempo: 140\n"
        "feel: swing\n\nband:\n  tenor = tenor sax\n  trumpet\n"
        "  piano\n  bass\n  drums\n\nchords blues: F7, Bb7, F7, "
        "Cm7 F7, Bb7, Bdim7, F7, Am7 D7, Gm7, C7, F7 D7, Gm7 C7\n\n"
        "section solos, 12 bars, repeat 4x\n  use chords blues\n"
        "  tenor: solo\n  trumpet: solo\n  ending: as written\n\n"
        "section ballad, 4 bars\n  chords: Fmaj7, Gm7, C7, Fmaj7\n"
        "  feel: ballad\n  ending: as written\n")
    out = os.path.join(tmp, "b")
    try:
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
        ok = True
    except SystemExit as e:
        ok = str(e.code)
    check("two ending lines: only the last section may carry one",
          ok is not True and "last section" in ok)
    txt = open(os.path.join(tmp, "t.chart")).read().replace(
        "  tenor: solo\n  trumpet: solo\n  ending: as written\n",
        "  tenor: solo\n  trumpet: solo\n")
    open(os.path.join(tmp, "t.chart"), "w").write(txt)
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
    pl = chartaudio.parse_score(os.path.join(
        out, "Trade Test — for listening.musicxml"))
    ev = {p["name"]: p["events"] for p in pl["parts"]}
    tr = ev["trumpet"]
    first = min(e[0] for e in tr)
    check("the second soloist waits its turn",
          first >= 96 - 1e-6, first)
    dr = [e for e in ev["drums"] if e[0] >= 192]
    check("the ballad's drummer picks up brushes, stirs and all",
          dr and all(e[4].get("brush") for e in dr)
          and any(e[2] == 60 for e in dr))
    check("the swing choruses stay on sticks",
          not any(e[4].get("brush") for e in ev["drums"] if e[0] < 192))
    shutil.rmtree(tmp, ignore_errors=True)


def check_listen_switches():
    """What the listen makes up is the writer's to turn off (Matthew,
    2026-09-29: "what if the user doesn't wanna hear soloing
    automatically ... give the user the option"): with a switch off the
    band leaves it out and the findings say so."""
    import chartaudio
    import chartc
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "t.chart"), "w").write(
        "title: Sw\nkey: F\nmeter: 4/4\ntempo: 120\n\nband:\n"
        "  tenor = tenor sax\n  piano\n  bass\n  drums\n\n"
        "section A, 4 bars\n  chords: F7, Bb7, C7, F7\n  tenor: solo\n")
    saved = dict(chartc.LISTEN_OPTS)
    try:
        def build():
            out = os.path.join(tmp, "b")
            buf = io.StringIO()
            with redirect_stdout(buf):
                chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
            pl = chartaudio.parse_score(os.path.join(
                out, "Sw — for listening.musicxml"))
            return buf.getvalue(), {p["name"]: p["events"]
                                    for p in pl["parts"]}, pl
        _, ev, pl_on = build()
        chartc.LISTEN_OPTS.update(solos=False, endings=False)
        said, ev_off, pl_off = build()
        check("solos off: the soloist rests", ev["tenor"]
              and not ev_off["tenor"])
        check("endings off: no band's choice, the notes stop at the end",
              abs(pl_off["end_q"] - 16) < 0.01
              and "band chose" not in said)
        check("the findings say what was turned off",
              "turned off in settings" in said and "solos" in said)
        chartc.LISTEN_OPTS.update(grooves=False)
        _, ev_g, _ = build()
        check("grooves off: slash bars stay silent",
              not ev_g["piano"] and not ev_g["drums"])
    finally:
        chartc.LISTEN_OPTS.clear()
        chartc.LISTEN_OPTS.update(saved)
    shutil.rmtree(tmp, ignore_errors=True)


def check_plays_like_pros():
    """Professional players (Matthew, 2026-09-29, on Trading Room): the
    pianist comps with rootless A/B voicings that move least, in a
    vocabulary of rhythms, never the same bar twice; soloists land chord
    tones on the beat; the drummer feathers the kick or not (a switch),
    and the band drops back when a new soloist starts, then builds."""
    import chartgroove as G
    v1 = G.rootless_voicing(("C", 0, "m7", None), None)
    v2 = G.rootless_voicing(("F", 0, "7", None), v1)
    check("ii-V rootless: Cm7 B form into F7 A form, one voice moving",
          v1 == [58, 62, 63, 67] and v2 == [57, 62, 63, 67], (v1, v2))
    st, picks, both = {}, [], 0
    for ab in range(24):
        b = G.Bar(24, (4, 4), 0, 1)
        G.piano_comp(b, st, ab, [(1.0, ("F", 0, "7", None))],
                     ("B", -1, "7", None), 0.8, "keyboard.piano", "swing")
        if ab % 2 == 0:
            picks.append(st["tex"])
        ns = [n[1] for _t, (_l, nn) in b.onsets.items() for n in nn]
        if ns and min(ns) < 57 and max(ns) > 62:
            both += 1
    check("the pianist changes texture, never the same one twice running",
          all(a != b for a, b in zip(picks, picks[1:]))
          and len(set(picks)) >= 3, picks)
    check("two hands: a low left hand under a higher right", both >= 6,
          both)
    sec = {"bars": 12, "_turn": (0, 24, 0)}
    lo = G._heat(sec, 0)
    sec["_turn"] = (23, 24, 0)
    hi = G._heat(sec, 11)
    check("behind a soloist the band starts low and builds", hi > lo + 0.4)
    G.OPTS["feather"] = False
    try:
        b = G.Bar(24, (4, 4), 0, 1)
        G._drums(b, 3, "swing", None)
        kicks_off = [n for _t, (_l, ns) in b.onsets.items() for n in ns
                     if n[1] == G._KICK]
        st2 = {"hits": None}
        made = G.realize("groove", "", "drum.group.set", "percussion", 1,
                         0, {"bars": 8, "content": [[(1.0, None)]] * 8,
                             "feel": None}, 1, 3, (4, 4), 24, "swing",
                         st2, None)
        quiet_kicks = made.count("<display-step>F</display-step>"
                                 "<display-octave>4") if made else 0
    finally:
        G.OPTS["feather"] = True
    check("feather off: no quiet kick on every beat",
          len([n for n in kicks_off if (n[2] or 99) <= 34]) == 0
          and quiet_kicks <= 2, quiet_kicks)


def check_band_reacts():
    """Nothing repeats and the band reacts (Matthew, 2026-09-29): fills
    come from a vocabulary and never twice running, so no two soloist
    handoffs sound alike; the pianist leaves room over a busy soloist
    and answers when they breathe; each soloist has a personality."""
    import chartgroove as G
    st, kinds = {}, []
    for ab in range(8):
        b = G.Bar(24, (4, 4), 0, 1)
        G._drummer_marks(b, {"bars": 4, "name": "solos",
                             "_turn": (3, 4, ab)}, 3, ab * 4 + 3, 0.8, st)
        kinds.append(st.get("last_fill"))
    check("handoff fills never repeat back to back",
          all(k for k in kinds) and all(a != b for a, b in
                                        zip(kinds, kinds[1:]))
          and len(set(kinds)) >= 4, kinds)

    def notes_with(busy):
        tot, st2 = 0, {}
        for ab in range(16):
            b = G.Bar(24, (4, 4), 0, 1)
            G.piano_comp(b, st2, ab, [(1.0, ("F", 0, "7", None))],
                         ("B", -1, "7", None), 0.7, "keyboard.piano",
                         "swing", busy)
            tot += sum(len(n) for _t, (_l, n) in b.onsets.items())
        return tot
    check("the pianist leaves room over a busy soloist",
          notes_with(0.9) < notes_with(0.05))
    check("four soloist personalities", len(G.PERSONAS) == 4)


def check_sound_shelf_installer():
    """The sample shelf installs itself where the writer says (Matthew,
    2026-09-29): a catalog of every library the band plays with its
    source, size and licence; unpacking into the named folder, Mac junk
    dropped; 24-bit WAVs brought to 16-bit in pure Python; credits
    written; nothing fetched unasked. Offline here: no downloads."""
    import struct
    import wave as wv
    import zipfile as zf
    import chartsounds as cs
    check("the catalog covers the band, each with a source and licence",
          all(e.get("url") and e.get("license") for e in cs.CATALOG)
          and {"piano", "kit", "brushes", "upright", "floor"}
          <= {e["key"] for e in cs.find("band")})
    try:
        cs.find("kazoo")
        bad = None
    except SystemExit as e:
        bad = str(e.code)
    check("an unknown library is named", bad and "kazoo" in bad)
    tmp = tempfile.mkdtemp()
    w24 = os.path.join(tmp, "a.wav")
    with wv.open(w24, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(44100)
        w.writeframes(b"".join(struct.pack("<i", v << 8)[:3]
                               for v in (0, 1000, -1000, 8388607 // 256)))
    ok = cs.to_16bit(w24)
    with wv.open(w24) as w:
        sw, frames = w.getsampwidth(), w.readframes(4)
    vals = struct.unpack("<4h", frames)
    check("a 24-bit WAV becomes 16-bit, keeping the top bytes",
          ok and sw == 2 and vals == (0, 1000, -1000, 32767), vals)
    z = os.path.join(tmp, "lib.zip")
    with zf.ZipFile(z, "w") as zz:
        zz.writestr("lib-main/Programs/x.sfz", "<region> sample=a.wav")
        zz.writestr("lib-main/.DS_Store", "junk")
        zz.writestr("__MACOSX/lib-main/._x.sfz", "junk")
    home = os.path.join(tmp, "shelf")
    os.makedirs(home)
    entry = {"key": "t", "name": "Test", "folder": "TestLib",
             "plays": "a test", "license": "CC0", "mb": 1}
    dest = cs._extract(z, home, entry)
    names = sorted(os.listdir(dest))
    check("unpacks into the catalog's folder, the archive's top folder "
          "and the Mac junk gone", names == ["Programs"]
          and os.path.exists(os.path.join(dest, "Programs", "x.sfz")),
          names)
    bomb = os.path.join(tmp, "bad.zip")
    with zf.ZipFile(bomb, "w") as zz:
        zz.writestr("../escape.txt", "no")
    try:
        cs._extract(bomb, home, dict(entry, folder="Bad"))
        esc = False
    except ValueError:
        esc = True
    check("an archive reaching outside its folder is refused", esc)
    cs.CATALOG.append(dict(entry, credit="Test by Someone, CC0",
                           url="x"))
    try:
        cs.write_credits(home)
        cr = open(os.path.join(home, "CREDITS.txt")).read()
    finally:
        cs.CATALOG.pop()
    check("the credits name who made what's installed",
          "Test by Someone" in cr)
    shutil.rmtree(tmp, ignore_errors=True)


def check_shelf_drive_missing():
    """The shelf can live on another drive (Matthew's is on his VST
    drive, 2026-09-29); when that drive isn't mounted the listen says so
    once and plays the plain synth, and the build still lands."""
    import chart
    chart._SHELF_WARNED = False
    buf = io.StringIO()
    with redirect_stdout(buf):
        got = chart.resolve_sounds({"sounds_dir": "/Volumes/NoSuchDrive/x",
                                    "sounds": "", "use_samples": "yes"})
        chart.resolve_sounds({"sounds_dir": "/Volumes/NoSuchDrive/x",
                              "sounds": "", "use_samples": "yes"})
    said = buf.getvalue()
    check("a missing shelf drive: the synth, said once",
          got is None and said.count("isn't there") == 1, said)
    check("use_samples=no plays the synth without a word",
          chart.resolve_sounds({"use_samples": "no"}) is None)


def check_melody_in_the_breath():
    """'alto takes the melody' said in the breath gives the head's
    sections the alto on the tune by default (Harbor Lights, 2026-09-29:
    the breath gave up on it); an intro or tag never gets it."""
    import chartedit
    ctx = {"labels": ["alto", "trumpet", "piano"], "groupnames": ["horns"]}
    with redirect_stdout(io.StringIO()):
        rest = chartedit._melody_in_breath(
            ctx, ["alto takes the melody", "kazoo takes the melody",
                  "melody on trumpet in the bridge"])
    check("the breath's melody words are read, a stranger is not",
          rest == ["kazoo takes the melody"]
          and ctx["breath_melody"] == [(["alto"], None),
                                       (["trumpet"], "bridge")])
    head = {"name": "A2", "kind": "plain", "family": "head"}
    intro = {"name": "intro", "kind": "plain"}
    bridge = {"name": "bridge", "kind": "plain"}
    check("the head's sections default to the tune, the intro does not",
          chartedit._melody_default(head, ctx) == ["alto"]
          and chartedit._melody_default(intro, ctx) == []
          and chartedit._melody_default(bridge, ctx) == ["alto",
                                                         "trumpet"])


def check_playlist_picking():
    """A real iReal Pro link is a whole playlist (the Jazz 1460 is one
    link): a song is picked by name, loosely, or number; a near miss
    names the closest; repeated section names come in numbered; a
    style with no tempo gets its usual one, said."""
    import re
    import chartimport
    import textformats as tf
    songs = [{"title": "Autumn Leaves"}, {"title": "All The Things You Are"},
             {"title": "Autumn in New York"}]
    check("a song picked by name, loosely, or by number",
          tf.pick_song(songs, "autumn leaves")["title"] == "Autumn Leaves"
          and tf.pick_song(songs, "all the things")["title"]
          == "All The Things You Are"
          and tf.pick_song(songs, "#3")["title"] == "Autumn in New York")
    try:
        tf.pick_song(songs, "autum leavs")
        near = ""
    except tf.ImportTrouble as e:
        near = str(e)
    check("a near miss names the closest", "Autumn Leaves" in near, near)
    check("styles read as their usual tempos",
          chartimport.style_tempo("Medium Up Swing") == 180
          and chartimport.style_tempo("Ballad") == 68
          and chartimport.style_tempo("Medium Swing") == 140)
    song = {"title": "T", "meter": (4, 4), "style": "Medium Swing",
            "sections": [{"name": "A", "bars": [[(1, "C")]] * 2},
                         {"name": "A", "bars": [[(1, "F")]] * 2},
                         {"name": "B", "bars": [[(1, "G")]] * 2},
                         {"name": "A", "bars": [[(1, "C")]] * 2}]}
    text, _t, find, _w = chartimport.song_to_chart(song, "x")
    names = re.findall(r"^section (\S+),", text, re.M)
    check("repeated section names come in numbered, the tempo said",
          names == ["A", "A2", "B", "A3"] and "tempo: 140" in text
          and any("about 140" in f for f in find), names)


def check_band_ending_follows_the_writing():
    """Left to the band, the ending follows what the written parts do:
    a long last note means the band holds with it, short last notes
    mean it stops with them; the findings say why."""
    import chartc
    tmp = tempfile.mkdtemp()

    def said(notes):
        open(os.path.join(tmp, "t.chart"), "w").write(
            "title: W\nkey: F\nmeter: 4/4\ntempo: 120\nfeel: swing\n\n"
            "band:\n  tenor = tenor sax\n  piano\n  bass\n  drums\n\n"
            f"figure end, 2 bars:\n  notes: {notes}\n\n"
            "section A, 2 bars\n  chords: F7, F7\n  tenor: figure end\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            chartc.compile_chart(os.path.join(tmp, "t.chart"),
                                 os.path.join(tmp, "b"))
        return buf.getvalue()
    long_ = said("F4 w, A4 w")
    short = said("F4 w, A4 q, rest q, rest h")
    check("a long written last note: the band holds with it",
          "band chose one: hold" in long_ and "long last note" in long_)
    check("short written last notes: the band stops with them",
          "cold stop" in short and "short last notes" in short)
    shutil.rmtree(tmp, ignore_errors=True)


def check_everyone_listens():
    """Everyone reacts and nothing is stamped out (Matthew, 2026-09-29):
    the ride and the hi-hat foot vary bar to bar; the bass lays down two
    at the top of a turn and runs into the next bar when the soloist
    breathes; backgrounds wait while the soloist is busy; every tune
    rolls its own dice; a head played twice is comped two ways; a solo
    line is one note at a time; a fill stops the time and lands."""
    import chartaudio
    import chartc
    import chartgroove as G
    rides, feet = set(), set()
    for ab in range(24):
        b = G.Bar(24, (4, 4), 0, 1)
        G._swing_time(b, ab, 0.8, 0.3)
        rides.add(tuple(sorted(t for t, (_l, ns) in b.onsets.items()
                               if any(n[1] in (G._RIDE, G._BELL)
                                      for n in ns))))
        feet.add(tuple(sorted(t for t, (_l, ns) in b.onsets.items()
                              if any(n[1] == G._HATF for n in ns))))
    check("the ride and the hi-hat foot change from bar to bar",
          len(rides) >= 3 and len(feet) >= 2, (len(rides), len(feet)))
    G.SALT = "Tune One"
    a = G._Dice("piano", 5)()
    G.SALT = "Tune Two"
    b_ = G._Dice("piano", 5)()
    G.SALT = ""
    check("every tune rolls its own dice", a != b_)
    notes = G._one_voice([(0, 1, 60, 70), (0, 1, 64, 60), (0.5, 1, 62, 70)])
    check("a solo line is one note at a time",
          len(notes) == 2 and notes[0][1] < 0.5)
    b = G.Bar(24, (4, 4), 0, 1)
    G._swing_time(b, 3, 0.7, 0.3)
    G._fill(b, "toms_down", 3 * 24, 0.7, G._Dice("t"))
    late = [n[1] for t, (_l, ns) in b.onsets.items() if t >= 72
            for n in ns]
    check("a fill stops the ride under it",
          G._RIDE not in late and G._BELL not in late and late)
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "t.chart"), "w").write(
        "title: Twice\nkey: F\nmeter: 4/4\ntempo: 140\nfeel: swing\n\n"
        "band:\n  piano\n  bass\n  drums\n\n"
        "section A, 4 bars, repeat 2x\n  chords: F7, Bb7, F7, C7\n"
        "  ending: as written\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "t.chart"),
                             os.path.join(tmp, "b"))
    pl = chartaudio.parse_score(os.path.join(tmp, "b",
                                             "Twice — for listening.musicxml"))
    pn = next(p for p in pl["parts"] if p["name"] == "piano")["events"]
    one = [(round(e[0], 2), e[2]) for e in pn if e[0] < 16]
    two = [(round(e[0] - 16, 2), e[2]) for e in pn if 16 <= e[0] < 32]
    check("a head played twice is comped two ways",
          one and two and one != two and abs(pl["end_q"] - 32) < 0.01)
    shutil.rmtree(tmp, ignore_errors=True)


def check_exports_ireal_midi_chords():
    """Out to what musicians pass around (Matthew, 2026-09-29): an
    iReal Pro link that Copyist's own importer reads back bar for bar
    (repeats, first and second endings, a meter change, a split bar,
    key, tempo, style); the listen as a type-1 MIDI file, a track per
    player, drums on channel 10; a plain chord sheet."""
    import chartc
    import chartexport
    import chartdemo
    import textformats
    tmp = tempfile.mkdtemp()
    cp = os.path.join(tmp, "x.chart")
    open(cp, "w").write(
        "title: Out\ncomposer: Jane Writer\nkey: G minor\nmeter: 4/4\n"
        "tempo: 132\nfeel: bossa nova\n\nband:\n  piano\n  bass\n"
        "  drums\n\n"
        "section A, 6 bars, repeat 2x\n  chords: Gm7, C7 F7, Bbmaj7, D7\n"
        "  ending 1, 2 bars: chords: Am7b5, D7b9\n"
        "  ending 2, 2 bars: chords: Gm6, Gm6\n"
        "section B, 4 bars\n  at bar 1: meter 3/4\n"
        "  chords: Ebmaj7, Am7b5, D7alt, Gm\n")
    ch = chartc.parse_chart(cp)
    song = textformats.parse_all(chartexport.ireal_link(ch))[0]
    got = [[sym for _b, sym in bar] for sec in song["sections"]
           for bar in sec["bars"]]
    want = [["Gm7"], ["C7", "F7"], ["Bbmaj7"], ["D7"], ["Am7b5"],
            ["D7b9"], ["Gm7"], ["C7", "F7"], ["Bbmaj7"], ["D7"], ["Gm6"],
            ["Gm6"], ["Ebmaj7"], ["Am7b5"], ["Dalt"], ["Gm"]]
    check("an iReal Pro link reads back bar for bar", got == want, got)
    check("the link keeps title, key, tempo and style",
          song["title"] == "Out" and song["key"] == "Gm"
          and song.get("tempo") == 132 and "Bossa" in song["style"],
          (song["key"], song.get("tempo"), song["style"]))
    out = os.path.join(tmp, "b")
    with redirect_stdout(io.StringIO()):
        files = chartc.compile_chart(cp, out)
    listen = next(f for f in files if f.endswith("for listening.musicxml"))
    mid = chartexport.write_midi(listen, tmp, "Out")[0]
    raw = open(mid, "rb").read()
    dm = chartdemo.load_demo(mid)
    check("the band as MIDI: type 1, a track per player, notes in it",
          raw[:4] == b"MThd" and raw[8:10] == b"\x00\x01"
          and len(dm.tracks) == 3 and all(len(v) for v in
                                          dm.tracks.values()))
    check("the drums sit on channel 10", b"\x99" in raw)
    sheet = open(chartexport.write_chords(ch, tmp, "Out")[0]).read()
    check("a chord sheet with barlines, the key said in words",
          "key of G minor" in sheet and "| C7 F7 |" in sheet, sheet[:200])
    # a fermata held in the listen is held in the MIDI too
    fp = os.path.join(tmp, "f.chart")
    open(fp, "w").write(
        "title: Held\nkey: C\nmeter: 4/4\ntempo: 120\n\nband:\n"
        "  piano\n  bass\n\nsection A, 4 bars\n  chords: C, F, G, C\n"
        "  at bar 2: fermata\n")
    with redirect_stdout(io.StringIO()):
        ff = chartc.compile_chart(fp, os.path.join(tmp, "fb"))
    fl = next(f for f in ff if f.endswith("for listening.musicxml"))
    fr = open(chartexport.write_midi(fl, tmp, "Held")[0], "rb").read()
    tempos = [int.from_bytes(fr[i + 3:i + 6], "big")
              for i in range(len(fr) - 6) if fr[i:i + 3] == b"\xff\x51\x03"]
    check("a fermata slows the MIDI tempo map, then it's back in time",
          len(tempos) >= 3 and max(tempos) > tempos[0]
          and tempos[-1] == tempos[0], tempos)
    shutil.rmtree(tmp, ignore_errors=True)


def check_band_plays_like_pros():
    """Matthew, 2026-09-29, on Autumn Leaves and Late Set: the walking
    bass "gets stuck to a high g"; lowest note an E; the piano solo
    "not following the chords"; the left hand "only using one note";
    comping "meh". The bass walks the whole form in the middle of the
    neck, no note held over four beats in a row, E1 the floor, every
    lead-in a step or a fifth from the next root; the solo's notes sit
    on the eighth grid (or its triplets) and fill the chorus; the
    soloing pianist's left hand plays two different notes; a 6 chord is
    major (no b7 in the scale or the voicing)."""
    import chartaudio
    import chartc
    import chartgroove as G
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "t.chart"), "w").write(
        "title: Leaves\nkey: Gm\nmeter: 4/4\ntempo: 140\n"
        "feel: medium swing\n\nband:\n  piano\n  bass\n  drums\n\n"
        "section A, 16 bars, repeat 2x\n  chords: Cm7, F7, Bbmaj7, "
        "Ebmaj7, Am7b5, D7b13, Gm6, Gm6, Cm7, F7, Bbmaj7, Ebmaj7, "
        "Am7b5, D7b13, Gm6, Gm6\n  piano: solo\n  ending: as written\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "t.chart"),
                             os.path.join(tmp, "b"))
    pl = chartaudio.parse_score(os.path.join(
        tmp, "b", "Leaves — for listening.musicxml"))
    ev = {p["name"]: sorted(p["events"], key=lambda e: e[0])
          for p in pl["parts"]}
    bass = [e[2] for e in ev["bass"]]
    runs = max(len(list(g)) for _k, g in __import__("itertools")
               .groupby(bass))
    check("the walking bass never sticks: no note struck 5 times running, "
          "E1 the floor, nothing over G3",
          runs < 5 and min(bass) >= 28 and max(bass) <= 55,
          (runs, min(bass), max(bass)))
    # measured against real bassists (FiloBass): mostly roots when a
    # chord arrives, lead-ins a step or a fifth from where it lands
    roots = "C F Bb Eb A D G G C F Bb Eb A D G G".split()
    pcs = {"C": 0, "F": 5, "Bb": 10, "Eb": 3, "A": 9, "D": 2, "G": 7}
    on = {round(e[0]): e[2] for e in ev["bass"]
          if abs(e[0] - round(e[0])) < 0.02}
    arr = [(on[4 * b] - pcs[roots[b % 16]]) % 12 for b in range(2, 30)
           if 4 * b in on]
    check("the bass lands on the root most of the time, else 5th or 3rd",
          0.5 <= arr.count(0) / len(arr) <= 0.95
          and all(a in (0, 3, 4, 6, 7) for a in arr), arr)
    # the note right before each downbeat (a triplet run's last note,
    # else beat four) against where the bass lands
    def before(t):
        got = [e for e in ev["bass"] if t - 1.01 < e[0] < t - 0.01]
        return max(got, key=lambda e: e[0])[2] if got else None
    leads = [before(4 * b + 4) - on[4 * b + 4] for b in range(2, 29)
             if 4 * b + 4 in on and before(4 * b + 4) is not None]
    good = sum(1 for x in leads if x in (-1, 1, 2, -2, -5, 7, 5, -7))
    check("every lead-in is a step or a fifth from where the bass lands",
          good >= 0.9 * len(leads), leads)
    pn = ev["piano"]
    rh = [e for e in pn if e[2] >= 64]
    lh = [e for e in pn if e[2] < 64]
    grid = sum(1 for e in rh if min(abs(e[0] * 2 - round(e[0] * 2)),
                                    abs(e[0] * 3 - round(e[0] * 3)))
               < 0.03)
    check("the piano solo sits on the eighth (or triplet) grid",
          grid >= 0.95 * len(rh), (grid, len(rh)))
    empty = sum(1 for b in range(32)
                if not any(4 * b <= e[0] < 4 * b + 4 for e in rh))
    check("the solo fills the choruses (a few bars of air, not a third)",
          empty <= 6, empty)
    chords = {}
    for e in lh:
        chords.setdefault(round(e[0], 2), set()).add(e[2])
    check("the soloing pianist's left hand plays two different notes",
          sum(len(v) >= 2 for v in chords.values()) >= 0.8 * len(chords),
          list(chords.values())[:6])
    r = [G.swing_ratio(b) for b in (100, 180, 260)]
    check("swing is wider slow and flatter fast, like real trios "
          "(about a triplet near 180)",
          r[0] > r[1] > r[2] and 1.8 <= r[1] <= 2.3, r)
    # the drummer's ride, from real drummers' vocabulary: the classic
    # ding, ding-ga the most common bar, never the only one
    import collections as _co
    rides = _co.Counter()
    for b in range(2, 30):
        on = tuple(sorted({round(e[0] - 4 * b, 2) for e in ev["drums"]
                           if e[2] in (51, 53) and 4 * b <= e[0]
                           < 4 * b + 4}))
        rides[on] += 1
    classic = [k for k in rides if {0.0, 1.0, 2.0, 3.0} <= set(k)
               and len(k) == 6]
    check("the ride plays the real drummers' vocabulary: ding, ding-ga "
          "most, and at least three different bars",
          len(rides) >= 3 and classic and rides.most_common(1)[0][0]
          in classic, rides.most_common(4))
    # a chart with no feel: a two-feel that moves — root then fifth,
    # or a step into a new chord; never the root struck twice a bar
    open(os.path.join(tmp, "n.chart"), "w").write(
        "title: Plain\nkey: Bb\nmeter: 4/4\ntempo: 126\n\nband:\n"
        "  bass\n  drums\n\nsection A, 12 bars\n  chords: Bb7, Eb7, Bb7 "
        "x2, Eb7 x2, Bb7 x2, F7, Eb7, Bb7, F7\n  ending: as written\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "n.chart"),
                             os.path.join(tmp, "nb"))
    nb = chartaudio.parse_score(os.path.join(
        tmp, "nb", "Plain — for listening.musicxml"))
    bn = {round(e[0], 2): e[2] for p in nb["parts"] if p["name"] == "bass"
          for e in p["events"]}
    same = [b + 1 for b in range(12) if 4 * b in bn and 4 * b + 2 in bn
            and bn[4 * b] == bn[4 * b + 2]]
    check("a two-feel bass never strikes one note on 1 and 3", not same,
          same)
    # a fresh take every build: another take plays the made-up parts
    # differently; the same take plays them the same
    lp = os.path.join(tmp, "b", "Leaves — for listening.musicxml")

    def take(t):
        chartc.TAKE = t
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "t.chart"),
                                 os.path.join(tmp, "b"))
        return open(lp).read()
    try:
        t1, t2, t1b = take("11"), take("12"), take("11")
    finally:
        chartc.TAKE = ''
    check("another take plays it new; the same take plays it the same",
          t1 != t2 and t1 == t1b)
    # feel words: where the band sits against the time
    check("feel words read the way players say them",
          chartaudio.feel_word("medium swing, laid back") == "back"
          and chartaudio.feel_word("lay it back") == "back"
          and chartaudio.feel_word("play loose") == "loose"
          and chartaudio.feel_word("on top of the beat") == "push"
          and chartaudio.feel_word("tight") == "tight"
          and chartaudio.feel_word("back to comping") is None)
    open(os.path.join(tmp, "f.chart"), "w").write(
        "title: Feel\nkey: F\nmeter: 4/4\ntempo: 120\nfeel: swing\n\n"
        "band:\n  bass\n  drums\n\nsection A, 2 bars\n  chords: F7, C7\n"
        "section B, 2 bars\n  feel: swing, laid back\n  chords: F7, C7\n"
        "section C, 2 bars\n  chords: F7, F7\n  ending: as written\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "f.chart"),
                             os.path.join(tmp, "fb"))
    fp = chartaudio.parse_score(os.path.join(
        tmp, "fb", "Feel — for listening.musicxml"))
    check("a laid-back section lays back, and the next one is tight again",
          fp["feels"] == [(8.0, "back"), (16.0, "tight")], fp["feels"])
    # the conversation: when the soloist breathes, someone picks up the
    # phrase they just played — the piano's comping on their rhythm
    open(os.path.join(tmp, "c.chart"), "w").write(
        "title: Talk\nkey: F\nmeter: 4/4\ntempo: 140\nfeel: swing\n\n"
        "band:\n  tenor = tenor sax\n  piano\n  bass\n  drums\n\n"
        "section A, 16 bars, repeat 2x\n  chords: F7, Bb7, F7, F7, Bb7, "
        "Bb7, F7, D7, Gm7, C7, F7, C7, F7, Bb7, F7, C7\n  tenor: solo\n"
        "  ending: as written\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "c.chart"),
                             os.path.join(tmp, "cb"))
    cp_ = chartaudio.parse_score(os.path.join(
        tmp, "cb", "Talk — for listening.musicxml"))
    ce = {p["name"]: p["events"] for p in cp_["parts"]}
    answered = 0
    for b in range(1, 32):
        said = {round(e[0] - 4 * (b - 1), 2) for e in ce["tenor"]
                if 4 * (b - 1) <= e[0] < 4 * b}
        now_t = [e for e in ce["tenor"] if 4 * b <= e[0] < 4 * b + 4]
        rh = {round(e[0] - 4 * b, 2) for e in ce["piano"]
              if 4 * b <= e[0] < 4 * b + 4 and e[2] >= 60}
        if len(now_t) <= 2 and len(said & rh) >= 2:
            answered += 1
    check("the piano picks up the soloist's phrase when they breathe",
          answered >= 1, answered)
    # a singer's leaps: real tenor and trumpet solos leap past a sixth
    # inside a phrase about 1% of the time (Weimar); ours stays near it
    tn = sorted(ce["tenor"])
    wide = sum(1 for a_, b_ in zip(tn, tn[1:])
               if abs(b_[2] - a_[2]) > 9 and b_[0] - (a_[0] + a_[1]) < 0.75)
    check("the tenor doesn't leap octaves mid-phrase (about as rarely "
          "as real tenor players do)", wide <= max(2, len(tn) // 50),
          (wide, len(tn)))
    # the drummer's comping: one idea across each two-bar phrase
    sn = {}
    for e in ce["drums"]:
        if e[2] == 38:
            b = int(e[0] // 4)
            sn.setdefault(b, set()).add(round(e[0] - 4 * b, 2))
    pairs = [(sn.get(b, set()), sn.get(b + 1, set()))
             for b in range(4, 30, 2)]
    kept = sum(1 for x, y in pairs if x and y and x & y)
    check("the drummer's comping idea carries across its phrase",
          kept >= len([1 for x, y in pairs if x and y]) // 2, pairs[:4])
    # a solo break's hit is the drummer's pick each time
    hits = set()
    for n in range(12):
        open(os.path.join(tmp, "k.chart"), "w").write(
            f"title: Break {n}\nkey: F\nmeter: 4/4\ntempo: 150\n"
            "feel: swing\n\nband:\n  tenor = tenor sax\n  bass\n"
            "  drums\n\nsection A, 8 bars\n  chords: F7, Bb7, F7, C7, F7,"
            " Bb7, C7, F7\n  tenor: solo\n  at bar 5: break, 2 bars\n"
            "  ending: as written\n")
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "k.chart"),
                                 os.path.join(tmp, "kb"))
        kp = chartaudio.parse_score(os.path.join(
            tmp, "kb", f"Break {n} — for listening.musicxml"))
        hits.add(tuple(sorted({e[2] for p in kp["parts"]
                               if p["name"] == "drums" for e in p["events"]
                               if 16 <= e[0] < 17})))
    check("a solo break's hit is different from tune to tune (crash, "
          "choke, snare, hi-hat bark...)", len(hits) >= 3, hits)
    # a comping guitar stays home over a long tune (it drifted into the
    # sixth octave on Harbor Lights)
    open(os.path.join(tmp, "g.chart"), "w").write(
        "title: Long\nkey: Eb\nmeter: 4/4\ntempo: 140\nfeel: swing\n\n"
        "band:\n  guitar\n  vibes\n  bass\n  drums\n\n"
        "section A, 32 bars, repeat 3x\n  chords: Ebmaj7, Fm7, Gm7, Abmaj7,"
        " Bb7, Cm7, Fm7, Bb7, Ebmaj7, Ab7, Gm7, C7, Fm7, Bb7, Ebmaj7, Bb7,"
        " Ebmaj7, Fm7, Gm7, Abmaj7, Bb7, Cm7, Fm7, Bb7, Ebmaj7, Ab7, Gm7, C7,"
        " Fm7, Bb7, Ebmaj7, Ebmaj7\n  ending: as written\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "g.chart"),
                             os.path.join(tmp, "gb"))
    gp = chartaudio.parse_score(os.path.join(
        tmp, "gb", "Long — for listening.musicxml"))
    gtr = [e[2] for p in gp["parts"] if p["name"] == "guitar"
           for e in p["events"]]
    vib = [e[2] for p in gp["parts"] if p["name"] == "vibes"
           for e in p["events"]]
    check("a comping guitar stays in its home, the vibes above their low F",
          gtr and max(gtr) <= 76 and min(gtr) >= 40
          and (not vib or min(vib) >= 53), (min(gtr), max(gtr),
                                            vib and min(vib)))
    six = ("B", 0, "6", None)
    check("a 6 chord is major: no b7 in its scale or rootless voicing",
          10 not in G._scale(six)
          and all(10 not in f for f in G._rootless(six)))
    shutil.rmtree(tmp, ignore_errors=True)


def check_roadmap_fills_and_breaks():
    """Matthew, 2026-09-29: "if you say in the roadmap fill into
    whatever bar or beat, that should happen ... or fill into a break."
    'fill into bar N (from beat B)', 'at bar N beat B: fill', 'fill into
    the next section', 'at bar N: break, K bars, fill into it', 'fill
    into the break': the drummer fills where it says (time stops for
    it) and lands on the one; in a break the band hits the downbeat and
    stops, the soloist plays through it alone; the pages say Fill and
    Break."""
    import chartaudio
    import chartc
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "t.chart"), "w").write(
        "title: Road\nkey: F\nmeter: 4/4\ntempo: 160\nfeel: swing\n\n"
        "band:\n  tenor = tenor sax\n  piano\n  bass\n  drums\n\n"
        "section A, 8 bars\n  chords: F7, Bb7, F7, C7, F7, Bb7, C7, F7\n"
        "  tenor: solo\n  fill into bar 3 from beat 3\n"
        "  at bar 6: break, 2 bars, fill into it\n"
        "  fill into the next section\n"
        "section B, 4 bars\n  chords: F7 x4\n  ending: as written\n")
    out = os.path.join(tmp, "b")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(os.path.join(tmp, "t.chart"), out)
    pl = chartaudio.parse_score(os.path.join(out,
                                             "Road — for listening.musicxml"))
    ev = {p["name"]: p["events"] for p in pl["parts"]}

    def inbar(n, name, a=0.0, b=4.0):
        return [e for e in ev[name] if 4 * (n - 1) + a <= e[0]
                < 4 * (n - 1) + b]
    dr = inbar(2, "drums", 2.0)
    check("fill into bar 3 from beat 3: time stops, the fill plays",
          len(dr) >= 3 and not any(e[2] in (51, 53, 59, 42) for e in dr),
          sorted({e[2] for e in dr}))
    check("the break: bass and piano hit the downbeat and stop",
          inbar(6, "bass", 0.1) == [] and inbar(6, "piano", 0.1) == []
          and inbar(7, "bass") == [] and inbar(7, "piano") == []
          and inbar(6, "bass", 0, 0.1) != [])
    check("the soloist plays through the break",
          len(inbar(6, "tenor") + inbar(7, "tenor")) >= 8)
    check("fill into the break: the bar before it ends in a fill",
          len(inbar(5, "drums", 2.0)) >= 3)
    check("the band is back after the break, crash on the one",
          any(e[2] == 49 for e in inbar(8, "drums", 0, 0.1)))
    dx = open(os.path.join(out, "Road — drums.musicxml")).read()
    px = open(os.path.join(out, "Road — piano.musicxml")).read()
    check("the pages say Fill (drums) and Break (everyone)",
          "Fill from beat 3" in dx and "Break (2 bars)" in px)
    try:
        open(os.path.join(tmp, "x.chart"), "w").write(
            "title: X\nkey: F\nmeter: 4/4\ntempo: 120\n\nband:\n"
            "  drums\n\nsection A, 4 bars\n  chords: F x4\n"
            "  fill into the break\n")
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "x.chart"),
                                 os.path.join(tmp, "xb"))
        wrong = None
    except SystemExit as e:
        wrong = str(e.code)
    check("'fill into the break' with no break says so",
          wrong and "at bar N: break" in wrong, wrong)
    shutil.rmtree(tmp, ignore_errors=True)


def check_band_leader_order_and_roadmap_exports():
    """The band leader's calls carry: soloists go in the order the chart
    names them, whatever order the band was listed in; the iReal link
    gives every section a letter and carries its name and the roadmap
    (vamp, fills, breaks, the ending) as chart text; the chord sheet
    says who solos, what plays behind them, the fills and breaks and
    how it ends."""
    import chartaudio
    import chartc
    import chartexport
    import textformats
    tmp = tempfile.mkdtemp()
    cp = os.path.join(tmp, "r.chart")
    open(cp, "w").write(
        "title: Road Map\nkey: F\nmeter: 4/4\ntempo: 150\nfeel: swing\n\n"
        "band:\n  trumpet\n  tenor = tenor sax\n  bone = trombone\n"
        "  piano\n  bass\n  drums\n\n"
        "section Intro, 2 bars, vamp till cue\n  chords: F7, C7\n"
        "section A, 4 bars\n  chords: F7, Bb7, F7, C7\n"
        "section Solos, 8 bars\n  chords: F7, Bb7, F7, F7, Bb7, Bb7, F7, "
        "C7\n  tenor: solo\n  trumpet: solo\n  bone: backgrounds\n"
        "  at bar 7: break, 2 bars, fill into it\n"
        "section Out, 4 bars\n  chords: F7, Bb7, C7, F7\n"
        "  ending: hold, last hit\n")
    with redirect_stdout(io.StringIO()):
        chartc.compile_chart(cp, os.path.join(tmp, "b"))
    pl = chartaudio.parse_score(os.path.join(
        tmp, "b", "Road Map — for listening.musicxml"))
    ev = {p["name"]: p["events"] for p in pl["parts"]}
    # the intro vamps twice (8 beats x 2), then A: solos start at beat 32
    first_t = min(e[0] for e in ev["tenor"])
    first_tp = min(e[0] for e in ev["trumpet"])
    check("soloists go in the order the chart calls them, tenor then "
          "trumpet, though the trumpet is listed first",
          first_t < first_tp, (first_t, first_tp))
    ch = chartc.parse_chart(cp)
    music = chartexport.ireal_music(ch)
    check("iReal: every section gets a letter, its name and the roadmap "
          "ride along as chart text",
          "*B<Solos>" in music and "<Vamp till cue>" in music
          and "<Break 2 bars>" in music and "<Fill>" in music
          and "<hold, last hit>" in music and "*C<Out>" in music, music)
    song = textformats.parse_all(chartexport.ireal_link(ch))[0]
    check("iReal: the link still reads back section by section",
          [sec.get("name") for sec in song["sections"]][:3]
          == ["Intro", "A", "B"], [sec.get("name")
                                   for sec in song["sections"]])
    # a mistyped export stops the build before anything is written
    fresh = os.path.join(tmp, "typo")
    os.makedirs(fresh)
    shutil.copy(cp, os.path.join(fresh, "r.chart"))
    said = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(
            os.path.abspath(__file__)), "chart.py"), "build",
         os.path.join(fresh, "r.chart"), "--exports", "pages, readalowd"],
        capture_output=True, text=True, env=dict(os.environ,
                                                 COPYIST_NO_SAY="1"))
    check("a mistyped export is named, and nothing is built",
          "'readalowd' is not an export" in (said.stderr + said.stdout)
          and not os.path.exists(os.path.join(fresh, "build")),
          (said.stderr + said.stdout)[-200:])
    sheet = open(chartexport.write_chords(ch, tmp, "Road Map")[0]).read()
    check("the chord sheet carries the road map",
          "Vamp till cue." in sheet and "Solos: tenor, then trumpet." in sheet
          and "Backgrounds: bone." in sheet and "Bars 7 to 8: break" in sheet
          and "Bar 6: drum fill" in sheet
          and "Ending: hold, last hit." in sheet, sheet)
    shutil.rmtree(tmp, ignore_errors=True)


def check_endings_in_the_moment():
    """Matthew, 2026-09-30: a gliss is a way INTO the last hit while the
    band holds the last chord — piano, organ, or both with the drums —
    in the moment; and the Last Surprise ending: the drummer alone, a
    band chord on the drummer's call, back and forth, the conductor's
    count, everyone in on the hit. Band chords voice across the
    section, a different note a chair."""
    import chartaudio
    import chartc
    import chartending
    st = chartending.parse('drums dictate "Bb13(#11), A13b9", count in, '
                           'last hit', ["drums", "piano"])
    check("drums dictate reads its chords and the count",
          st[0] == ("dictate", ("drums", "Bb13(#11), A13b9"))
          and ("count", None) in st)
    # the band's own call: a gliss or fill only ever sets up a hit
    setups = []
    for n in range(60):
        steps = chartending.band_choice("swing", ("T", str(n)), True, True)
        kinds = [k for k, _ in steps]
        if "gliss" in kinds or "fill" in kinds:
            setups.append(kinds)
    check("the band's gliss or fill always sets up a last hit",
          setups and all(any(k in ("hit", "button") for k in ks)
                         for ks in setups), setups[:3])
    check("sometimes a gliss, sometimes a fill, sometimes both",
          any("gliss" in k and "fill" not in k for k in setups)
          and any("fill" in k and "gliss" not in k for k in setups)
          and any("gliss" in k and "fill" in k for k in setups))
    tmp = tempfile.mkdtemp()

    def build(ending, band="  trumpet\n  alto = alto sax\n  tenor = tenor "
                           "sax\n  bone = trombone\n  piano\n  organ\n"
                           "  bass\n  drums\n"):
        open(os.path.join(tmp, "e.chart"), "w").write(
            "title: E\nkey: Bb\nmeter: 4/4\ntempo: 160\nfeel: swing\n\n"
            "band:\n" + band + "\nsection A, 4 bars\n"
            "  chords: Bb6, G7, Cm7 F7, Bb6\n  ending: " + ending + "\n")
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "e.chart"),
                                 os.path.join(tmp, "b"))
        return chartaudio.parse_score(os.path.join(
            tmp, "b", "E — for listening.musicxml"))
    pl = build("hold, piano gliss, organ gliss, drums fill, last hit on cue")
    ev = {p["name"]: p["events"] for p in pl["parts"]}
    hit = max(e[0] for e in ev["drums"])
    for who in ("piano", "organ"):
        runs = sorted(e[0] for e in ev[who] if e[0] > 12.5)
        gl = [t for t in runs if t < hit - 0.1]
        check(f"the {who} gliss runs up into the cue, not off the landing",
              len(gl) >= 8 and gl[-1] > hit - 1.8 and gl[0] > 13.0,
              (gl[:2], gl[-2:], hit))
    pl = build("drums dictate, count in, last hit")
    ev = {p["name"]: sorted(p["events"]) for p in pl["parts"]}
    horns = {n: [e[2] for e in ev[n] if e[0] >= 16] for n in
             ("trumpet", "alto", "tenor", "bone")}
    chords = list(zip(*horns.values()))
    check("dictated: four band chords and the hit, every horn on its own "
          "note, top horn on top",
          len(chords) == 5 and all(len(set(c)) == 4 and c[0] == max(c)
                                   for c in chords), horns)
    solo = [e[0] for e in ev["drums"] if e[0] >= 16]
    first_band = min(e[0] for e in ev["trumpet"] if e[0] >= 16)
    check("dictated: the drummer is alone before the first band chord",
          any(t < first_band - 1 for t in solo)
          and not any(16 <= e[0] < first_band - 0.2 for n in horns
                      for e in ev[n]))
    pl = build("hold, alto cadenza, drums fill, last hit")
    ev = {p["name"]: sorted(p["events"]) for p in pl["parts"]}
    hit_t = max(e[0] for e in ev["bass"])
    cad = [e[0] for e in ev["alto"] if 16 < e[0] < hit_t - 0.1]
    others = [e[0] for n in ("piano", "organ", "bass")
              for e in ev[n] if cad and min(cad) + 0.5 < e[0] < max(cad)]
    fill = [e[0] for e in ev["drums"] if cad and max(cad) < e[0] < hit_t]
    check("a cadenza: the alto alone, the band out, then the drum fill "
          "and everyone on the hit",
          len(cad) >= 6 and not others and len(fill) >= 4,
          (len(cad), others[:3], len(fill)))
    pl = build("hold, drums fill, last hit, hold it")
    ev = {p["name"]: sorted(p["events"]) for p in pl["parts"]}
    last = max(ev["bass"], key=lambda e: e[0])
    check("a held last hit rings under its fermata", last[1] >= 3.0,
          last[:2])
    # anyone may fall off the last hit, in the moment: across tunes the
    # piano sometimes hits and slides off, sometimes doesn't
    slid = []
    for n in range(30):
        open(os.path.join(tmp, "e.chart"), "w").write(
            f"title: Fall {n}\nkey: Bb\nmeter: 4/4\ntempo: 160\n"
            "feel: swing\n\nband:\n  piano\n  bass\n  drums\n\n"
            "section A, 4 bars\n  chords: Bb6, G7, Cm7 F7, Bb6\n"
            "  ending: hold, last hit\n")
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(os.path.join(tmp, "e.chart"),
                                 os.path.join(tmp, "fb"))
        fl = chartaudio.parse_score(os.path.join(
            tmp, "fb", f"Fall {n} — for listening.musicxml"))
        pn = sorted(e for p in fl["parts"] if p["name"] == "piano"
                    for e in p["events"])
        hit_t = max(e[0] for p in fl["parts"] if p["name"] == "bass"
                    for e in p["events"])
        after = [e[2] for e in pn if e[0] > hit_t + 0.2]
        slid.append(len(after) >= 5 and after[0] > after[-1])
    check("in the moment, the keys sometimes fall off the last hit — a "
          "moment, not a habit",
          any(slid) and sum(slid) <= len(slid) // 3, sum(slid))
    # a transposing horn noodles and takes its cadenza in the tune's
    # key, at a speed a player plays (both were a major sixth off on
    # alto, and in thirty-seconds)
    bb = {10, 0, 2, 3, 5, 7, 9}           # B flat major, the last chord Bb6
    for ending, who in (("hold, alto noodles, last hit", "alto"),
                        ("hold, trumpet cadenza, drums fill, last hit",
                         "trumpet")):
        pl = build(ending)
        ev = sorted(e for p in pl["parts"] if p["name"] == who
                    for e in p["events"] if e[0] > 13)
        inkey = sum(1 for e in ev if e[2] % 12 in bb)
        gaps = [b[0] - a[0] for a, b in zip(ev, ev[1:])]
        check(f"{who}'s ending line sounds in B flat, at a player's speed",
              len(ev) >= 5 and inkey >= 0.85 * len(ev)
              and sorted(gaps)[len(gaps) // 2] >= 0.15,
              ([e[2] % 12 for e in ev][:10], sorted(gaps)[:3]))
    # the drummer takes their time and never plays the same thing twice;
    # with no count, the band holds the last chord hard until the cue
    pl = build("drums dictate, last hit, drums tag")
    ev = {p["name"]: sorted(p["events"]) for p in pl["parts"]}
    tr = sorted({round(e[0], 2) for e in ev["trumpet"] if e[0] >= 16})
    # a band chord starts after a stretch of silence (the held last
    # chord shakes, so its notes run together)
    band_on = [t for i, t in enumerate(tr) if i == 0 or t - tr[i - 1] > 0.8]
    if band_on[-1] != tr[-1]:
        band_on.append(tr[-1])     # the band played on through the cue
    edges = [16.0] + band_on[:5]
    shapes = []
    for a_, b_ in zip(edges, edges[1:]):
        seg = [e for e in ev["drums"] if a_ + 1.2 < e[0] < b_ - 0.2]
        shapes.append(tuple(sorted({e[2] for e in seg})) +
                      (len(seg) // 6,))
    loose = [e[0] for e in ev["drums"]
             if 16 < e[0] < band_on[0] - 1.2
             and abs(e[0] * 4 - round(e[0] * 4)) > 0.06]
    check("the drummer's solo is out of time, the way an ending is played",
          len(loose) >= 3, len(loose))
    check("the drummer's stretches alone are all different",
          len(shapes) >= 4 and len(set(shapes)) >= len(shapes) - 1,
          shapes)
    # in the moment the piano may just hold it: across takes it goes for
    # it at least sometimes
    tails = []
    was_take = chartc.TAKE
    try:
        for tk in range(1, 7):
            chartc.TAKE = tk
            pl_t = build("drums dictate, last hit, drums tag")
            ev_t = {p["name"]: sorted(p["events"]) for p in pl_t["parts"]}
            tr_t = sorted({round(e[0], 2) for e in ev_t["trumpet"]
                           if e[0] >= 16})
            on_t = [t for i, t in enumerate(tr_t)
                    if i == 0 or t - tr_t[i - 1] > 0.8]
            if len(on_t) > 4:
                tails.append(len([e for e in ev_t["piano"]
                                  if on_t[4] + 0.5 < e[0] < on_t[-1] - 0.1]))
    finally:
        chartc.TAKE = was_take
    check("no count: everyone goes for it on the held last chord (the "
          "piano, in at least some takes)", any(t >= 12 for t in tails),
          tails)
    kit = [e for e in ev["drums"] if e[0] > band_on[-1] + 0.3]
    check("the drummer's tag after the hit lands on the kick",
          kit and kit[-1][2] == 36, [e[2] for e in kit][-4:])
    import chartending as _ce
    import chartgroove as _cg
    dd = _cg._Dice("tags")
    check("every tag the band makes ends on the kick",
          all(_ce.band_tag(dd)[-1] == "bass drum" for _ in range(40)))
    # a count-off and a unison figure: everyone on the same line, each
    # in their own octave; the drummer kicks it and goes off in the gaps
    pl = build("hold, count in, unison figure, last hit, max roach ending")
    ev = {p["name"]: sorted(p["events"]) for p in pl["parts"]}
    hit_t = max(e[0] for e in ev["bass"])

    def fig(n):
        return [e for e in ev[n] if hit_t - 8.2 < e[0] < hit_t - 0.1]
    rhythm = {n: [round(e[0], 1) for e in fig(n)] for n in ("bass", "bone")}
    pcs = {n: [e[2] % 12 for e in fig(n)] for n in ("bass", "bone")}
    check("the unison figure: the bass and trombone play one line, "
          "together", len(rhythm["bass"]) >= 5 and pcs["bass"] == pcs["bone"]
          and all(abs(a - b) < 0.1 for a, b in zip(rhythm["bass"],
                                                  rhythm["bone"])),
          (rhythm, pcs))
    kit = [e for e in ev["drums"] if e[0] > hit_t + 0.3]
    check("'max roach ending' is the drummer's last say, on the kick",
          kit and kit[-1][2] == 36)
    try:
        build("drums dictate, last hit", band="  piano\n  bass\n")
        wrong = None
    except SystemExit as e:
        wrong = str(e.code)
    check("a dictated ending with no drummer says so",
          wrong and "drum chair" in wrong, wrong)
    shutil.rmtree(tmp, ignore_errors=True)


def check_percussion_section_grooves():
    """
    Matthew, 2026-09-28: "percussion should be able to do all those
    feels too." Every percussion chair grooved as a drum kit (kick,
    snare and hat positions on a conga staff), hand percussion played
    through the kit's samples, and one shared table decoded a triangle
    part's triangle head as the cowbell.
    """
    import chartgroove, chartaudio, chartband, chartc, tempfile, re as _re
    from contextlib import redirect_stdout
    check("perc: a conga, bell or shaker chair grooves as itself; the kit "
          "and cajon stay kits",
          chartgroove.role_of("drum.conga", "percussion") == "perc"
          and chartgroove.role_of("metal.cowbell", "percussion") == "perc"
          and chartgroove.role_of("rattle.shaker", "percussion") == "perc"
          and chartgroove.role_of("drum.group.set", "percussion") == "drums"
          and chartgroove.role_of("drum.cajon", "percussion") == "drums")
    check("perc: each part's staff decodes by its own instrument",
          chartaudio.hand_midi("metal.triangle", "B", 5, "triangle") == 81
          and chartaudio.hand_midi("metal.cowbell", "B", 5, "triangle") == 56
          and chartaudio.hand_midi("drum.conga", "A", 4, "x") == 62
          and chartaudio.hand_midi("drum.conga", "F", 4, "normal") == 64
          and chartaudio.hand_midi("wood.guiro", "C", 5, "normal") == 74)
    pp = chartgroove.perc_pattern
    tum = pp("conga", "latin", set(), 1)
    check("perc: the conga tumbao opens on 4 and the and of 4",
          [(b, s_) for b, _l, s_, _v in tum if s_ in ("open", "low")]
          == [(4, "open"), (4.5, "low")])
    check("perc: son clave alternates the two side and the three side",
          len(pp("claves", "latin", set(), 1)) == 2
          and len(pp("claves", "latin", set(), 2)) == 3)
    check("perc: a ballad is light, samba shakes sixteenths",
          len(pp("shaker", "swing", {"ballad"}, 1)) == 4
          and len(pp("shaker", "samba", set(), 1)) == 16)
    keys = [k for k, _f, _p in chartband.HAND_KEYS]
    check("perc: the sampler maps congas, bongos, bells, claves, shakers, "
          "tambourine, guiro, triangle",
          all(k in keys for k in (54, 56, 60, 61, 62, 63, 64, 70, 73, 74,
                                  75, 80, 81, 82)))


if __name__ == "__main__":
    print("\ninvariants")
    check_duration_algebra()
    check_key_names_are_usable()
    check_minor_and_chord_spelling()
    check_hand_percussion_parts()
    check_circle_of_fifths()
    check_starting_from_nothing()
    check_bow_and_chord_room()
    check_feels_and_technique_for_every_part()
    check_mutes_sound()
    check_percussion_section_grooves()
    check_double_an_octave_off()
    check_head_out_plays_the_head()
    check_words_perform()
    check_solos_and_endings()
    check_backgrounds_and_vamps()
    check_explode()
    check_endings_feel_natural()
    check_solos_tell_a_story()
    check_players_listen_to_each_other()
    check_listen_switches()
    check_plays_like_pros()
    check_band_reacts()
    check_sound_shelf_installer()
    check_shelf_drive_missing()
    check_melody_in_the_breath()
    check_playlist_picking()
    check_band_ending_follows_the_writing()
    check_everyone_listens()
    check_exports_ireal_midi_chords()
    check_band_plays_like_pros()
    check_roadmap_fills_and_breaks()
    check_band_leader_order_and_roadmap_exports()
    check_endings_in_the_moment()
    check_tuplet_ladder()
    check_meter_charts()
    check_poly_charts()
    check_phrasing_charts()
    check_audio()
    check_voltas()
    check_figures()
    check_lyrics()
    check_directive_family()
    check_build_entrance()
    check_trills_and_tremolos()
    check_sibelius_style_files()
    check_score_import()
    check_text_import()
    check_road_maps()
    check_keyswitches()
    check_detail_and_look()
    check_user_chair()
    check_engraver()
    check_settings()
    check_roadmap()
    check_drum_kit()
    check_braille()
    check_export_picker()
    check_tempo_in_the_bar()
    check_note_off_wins()
    check_cc_gates()
    check_half_time_funk()
    check_slashes_play_whats_written()
    check_new_feels()
    check_fall_keyswitch_any_timing()
    check_swung_and_straight_funk()
    check_bandleader_round()
    check_band_hears_the_lead()
    check_cues_and_cuts()

    run_fixture("two-hand-piano", "C# minor",
                {"clean.mid": "HARD QUANTIZED",
                 "humanized.mid": "QUANTIZED THEN HUMANIZED"})
    run_fixture("spelling-modulation", "Eb major",
                {"clean.mid": "HARD QUANTIZED"})
    run_fixture("small-ensemble", None, {})
    run_fixture("hammond-organ", None, {})

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    sys.exit(1 if failed else 0)
