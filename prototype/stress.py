#!/usr/bin/env python3
"""
Stress-test Copyist against a folder of real MIDI files.

The corpus fixtures are synthetic and small on purpose — they isolate one
pathology each and they are safe to publish. They are also, for exactly those
reasons, gentle. A folder of real files written by other people for other
purposes finds things the corpus structurally cannot.

    python3 stress.py ~/some/folder/of/midi [--roundtrip]

For each file it converts, checks that every measure's durations add up, and
with --roundtrip renders the MusicXML back to MIDI through MuseScore and
diffs against the source. Then it groups the results by the timing verdict,
which is the interesting part: how well Copyist reproduces a piece should
depend on whether it found a grid, and if that relationship ever breaks the
classifier has stopped being trustworthy.

Nothing here is committed as a fixture. Point it at material you already have.
"""

import argparse
import glob
import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analyze as A                                    # noqa: E402
import convert as C                                    # noqa: E402
import engine as E                                     # noqa: E402
import xml.etree.ElementTree as ET                     # noqa: E402

MSCORE = [
    "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
    "/Applications/MuseScore 3.app/Contents/MacOS/mscore",
    shutil.which("mscore") or "",
]


class TimeUp(Exception):
    pass


def _alarm(*_):
    raise TimeUp("exceeded the per-file time limit")


def note_set(path, pitched_only=True):
    """
    Percussion is excluded by default, and that is not a convenience.

    A percussion staff conflates instruments by position on purpose — an
    acoustic and an electric snare are the same line — so the GM-pitch-to-staff
    map is many-to-one and cannot be inverted. Comparing sounding pitch after a
    round-trip therefore scores correct drum notation as loss. Measuring it
    that way once suggested multi-part support had made things 4 points worse,
    when pitched notes were in fact byte-for-byte identical.
    """
    mid = A.parse_midi(path)
    x = A.extract(mid)
    d = mid["division"]
    return {(round(n.on / d, 4), n.pitch) for n in x["notes"]
            if not (pitched_only and n.chan == 9)}


def unbalanced_measures(path):
    """Durations in every voice must sum to the measure length. Always."""
    r = ET.parse(path).getroot()
    div = int(r.findtext(".//divisions"))
    expect, bad = None, 0
    for m in r.findall(".//measure"):
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
            bad += 1
    return bad


def find_mscore():
    for c in MSCORE:
        if c and os.path.exists(c):
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--roundtrip", action="store_true",
                    help="render back through MuseScore and diff (slow)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.folder, "**", "*.mid"),
                             recursive=True)
                   + glob.glob(os.path.join(a.folder, "**", "*.MID"),
                               recursive=True))
    if a.limit:
        files = files[:a.limit]
    if not files:
        print(f"No MIDI files under {a.folder}")
        return 2

    ms = find_mscore() if a.roundtrip else None
    if a.roundtrip and not ms:
        print("MuseScore not found; running without --roundtrip.")
    tmp = tempfile.mkdtemp()
    signal.signal(signal.SIGALRM, _alarm)

    print(f"{len(files)} file(s)\n")
    print(f"{'file':<38}{'notes':>7}{'bars':>6}{'bad':>5}  {'verdict':<15}"
          + ("  match" if ms else ""))
    print("-" * (74 + (7 if ms else 0)))

    rows, failed = [], []
    for f in files:
        name = os.path.basename(f)[:36]
        out = os.path.join(tmp, os.path.basename(f).rsplit(".", 1)[0] + ".musicxml")
        signal.alarm(a.timeout)
        try:
            info = E.do_analyze(f)
            if not info.get("ok"):
                raise ValueError(info.get("error", "analyze failed"))
            with redirect_stdout(io.StringIO()):
                C.convert(f, out, None, 17, 14)
            signal.alarm(0)
        except Exception as ex:
            signal.alarm(0)
            print(f"{name:<38}  {type(ex).__name__}: {str(ex)[:40]}")
            failed.append((name, f"{type(ex).__name__}: {ex}"))
            continue

        s = C.LAST_SUMMARY or {}
        bad = unbalanced_measures(out)
        kind = info["timing"]["kind"]
        match = None
        if ms:
            rt = os.path.join(tmp, "rt.mid")
            subprocess.run([ms, "-o", rt, out],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(rt):
                try:
                    src, back = note_set(f), note_set(rt)
                    match = len(src & back) / len(src) * 100 if src else 0.0
                except Exception:
                    match = None
                os.remove(rt)

        rows.append((name, kind, info["timing"]["grid"], bad, match))
        line = (f"{name:<38}{s.get('notes', 0):>7}{s.get('measures', 0):>6}"
                f"{bad:>5}  {kind:<15}")
        if ms:
            line += f"{match:>6.1f}%" if match is not None else "     —"
        print(line)

    shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"converted            {len(rows)}/{len(files)}")
    print(f"failed               {len(failed)}")
    unb = [r for r in rows if r[3]]
    print(f"unbalanced measures  {len(unb)} file(s)"
          + ("   <- FAIL" if unb else ""))
    for n, _, _, b, _ in unb:
        print(f"    {n}: {b} bar(s)")

    if ms and rows:
        print()
        print("Round-trip accuracy by timing verdict — this relationship is the")
        print("point. Copyist should reproduce a piece well exactly when it")
        print("found a grid, and poorly when it did not (DESIGN 7.6).")
        print()
        print(f"  {'verdict':<16}{'files':>6}{'mean':>9}{'range':>18}")
        for kind in ("hard-quantized", "humanized", "ambiguous", "live"):
            g = [r[4] for r in rows if r[1] == kind and r[4] is not None]
            if not g:
                continue
            print(f"  {kind:<16}{len(g):>6}{sum(g) / len(g):>8.1f}%"
                  f"{f'{min(g):.1f} – {max(g):.1f}%':>18}")

    for n, e in failed:
        print(f"\nFAILED {n}\n  {e}")
    return 1 if (failed or unb) else 0


if __name__ == "__main__":
    sys.exit(main())
