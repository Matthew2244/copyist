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

    run_fixture("two-hand-piano", "C# minor",
                {"clean.mid": "HARD QUANTIZED",
                 "humanized.mid": "QUANTIZED THEN HUMANIZED"})
    run_fixture("spelling-modulation", "Eb major",
                {"clean.mid": "HARD QUANTIZED"})
    run_fixture("small-ensemble", None, {})
    run_fixture("hammond-organ", None, {})

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    sys.exit(1 if failed else 0)
