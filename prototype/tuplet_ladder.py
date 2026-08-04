#!/usr/bin/env python3
"""
Escalation ladder for tuplet notation — DESIGN.md 22.5.

Four attempts at tuplets were measured on real repertoire and each was worse
than not having the feature. That was the wrong method: it measured a symptom
across dozens of confounded differences at once. This adds ONE complication at
a time to a case that is known to work, and reports the first rung that
breaks.

It found the two real bugs immediately — rests inside a tuplet, and a tuplet
beat containing anything the tuplet cannot express — after four rounds of
guessing had found neither.

All eight rungs pass. Real piano repertoire still does not, so whatever is
left is not on this ladder yet. Add a rung when you learn what it is.

    python3 tuplet_ladder.py            (needs multipart.EMIT_TUPLETS = True)
"""
import os, struct, subprocess, sys, io, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contextlib import redirect_stdout

DIV = 384
BPM = 120
OUT = os.path.join(tempfile.gettempdir(), "copyist-tuplet-ladder")
MS = "/Applications/MuseScore 4.app/Contents/MacOS/mscore"
os.makedirs(OUT, exist_ok=True)


def vlq(n):
    o = bytearray([n & 0x7F]); n >>= 7
    while n:
        o.insert(0, (n & 0x7F) | 0x80); n >>= 7
    return bytes(o)


def track(ev):
    ev = sorted(ev, key=lambda e: (e[0], (e[1][0] & 0xF0) == 0x90))
    body, last = bytearray(), 0
    for t, d in ev:
        body += vlq(t - last) + d; last = t
    return b"MTrk" + struct.pack(">I", len(body) + 4) + bytes(body) + b"\x00\xFF\x2F\x00"


def write(name, tracks_notes):
    cond = track([(0, b"\xFF\x51\x03" + struct.pack(">I", int(60_000_000 / BPM))[1:]),
                  (0, b"\xFF\x58\x04\x04\x02\x18\x08")])
    chunks = [cond]
    for ch, notes in tracks_notes:
        ev = [(0, bytes([0xC0 | ch, 0]))]
        for on, off, p, v in sorted(notes):
            ev.append((on, bytes([0x90 | ch, p, v])))
            ev.append((max(off, on + 1), bytes([0x80 | ch, p, 0])))
        chunks.append(track(ev))
    path = os.path.join(OUT, name + ".mid")
    with open(path, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), DIV) + b"".join(chunks))
    return path


BAR = 4 * DIV
T = DIV // 3            # triplet eighth
S = DIV // 6            # sextuplet 16th
EI = DIV // 2            # straight eighth
SC = [60, 62, 64, 65, 67, 69, 71, 72]


def rung_01_pure_triplets():
    n = []
    for b in range(4):
        for i in range(12):
            on = b * BAR + i * T
            n.append((on, on + T - 4, SC[i % 8], 80))
    return [(0, n)]


def rung_02_triplets_with_chords():
    n = []
    for b in range(4):
        for i in range(12):
            on = b * BAR + i * T
            for p in (SC[i % 8], SC[i % 8] + 4):
                n.append((on, on + T - 4, p, 80))
    return [(0, n)]


def rung_03_triplets_with_rests():
    """Every third triplet is silent — rests must live inside the tuplet."""
    n = []
    for b in range(4):
        for i in range(12):
            if i % 3 == 2:
                continue
            on = b * BAR + i * T
            n.append((on, on + T - 4, SC[i % 8], 80))
    return [(0, n)]


def rung_04_mixed_bars():
    """Bar 1 and 3 triplets, bar 2 and 4 straight eighths."""
    n = []
    for b in range(4):
        if b % 2 == 0:
            for i in range(12):
                on = b * BAR + i * T
                n.append((on, on + T - 4, SC[i % 8], 80))
        else:
            for i in range(8):
                on = b * BAR + i * EI
                n.append((on, on + EI - 4, SC[i % 8], 80))
    return [(0, n)]


def rung_05_mixed_within_bar():
    """Beats 1 and 3 triplets, beats 2 and 4 straight — same bar."""
    n = []
    for b in range(4):
        for beat in range(4):
            base = b * BAR + beat * DIV
            if beat % 2 == 0:
                for i in range(3):
                    n.append((base + i * T, base + i * T + T - 4, SC[i % 8], 80))
            else:
                for i in range(2):
                    n.append((base + i * EI, base + i * EI + EI - 4, SC[i % 8], 80))
    return [(0, n)]


def rung_06_three_against_two():
    """The real case: one hand triplets, the other straight, simultaneously."""
    hi, lo = [], []
    for b in range(4):
        for i in range(12):
            on = b * BAR + i * T
            hi.append((on, on + T - 4, SC[i % 8] + 12, 80))
        for i in range(8):
            on = b * BAR + i * EI
            lo.append((on, on + EI - 4, SC[i % 8] - 12, 70))
    return [(0, hi), (1, lo)]


def rung_07_sextuplets():
    n = []
    for b in range(4):
        for i in range(24):
            on = b * BAR + i * S
            n.append((on, on + S - 2, SC[i % 8], 80))
    return [(0, n)]


def rung_08_long_notes_over_triplets():
    """A held note spanning a whole tuplet beat, plus triplets under it."""
    hi, lo = [], []
    for b in range(4):
        for i in range(12):
            on = b * BAR + i * T
            hi.append((on, on + T - 4, SC[i % 8] + 12, 80))
        lo.append((b * BAR, b * BAR + BAR - 8, 48, 70))
    return [(0, hi), (1, lo)]


def rung_09_tie_across_tuplet_beat():
    """
    A note that STARTS inside a tuplet beat and ends inside the next one.

    Its duration is not a whole number of that beat's subdivisions, so it has
    to be split and tied across the boundary — and the two halves may belong
    to beats with different subdivisions.
    """
    n = []
    for b in range(4):
        base = b * BAR
        # beat 1: three triplets, the last held over into beat 2
        n.append((base, base + T - 4, 60, 80))
        n.append((base + T, base + 2 * T - 4, 62, 80))
        n.append((base + 2 * T, base + DIV + T - 4, 64, 80))     # ties over
        # beat 3-4: straight eighths
        for i in range(4):
            on = base + 2 * DIV + i * EI
            n.append((on, on + EI - 4, SC[i % 8], 80))
    return [(0, n)]


def rung_10_two_voices_one_staff():
    """
    Two independent lines on ONE channel: a triplet line above a held pedal
    tone. Hand separation must not split them and both must share a staff.
    """
    n = []
    for b in range(4):
        base = b * BAR
        for i in range(12):
            on = base + i * T
            n.append((on, on + T - 4, SC[i % 8] + 12, 80))
        n.append((base, base + BAR - 8, 55, 60))                 # held under
    return [(0, n)]


def rung_11_tie_across_barline():
    """A tuplet note held over the bar line."""
    n = []
    for b in range(4):
        base = b * BAR
        for i in range(11):
            on = base + i * T
            n.append((on, on + T - 4, SC[i % 8], 80))
        # last triplet of the bar spills into the next
        n.append((base + 11 * T, base + BAR + T - 4, 72, 80))
    return [(0, n)]


def rung_12_arabesque_texture():
    """
    The real thing, in miniature: right hand in triplets, left hand in
    straight eighths, both hands sustaining across beats, on two channels.
    """
    hi, lo = [], []
    for b in range(4):
        base = b * BAR
        for i in range(12):
            on = base + i * T
            hi.append((on, on + T - 4, SC[i % 8] + 12, 80))
        for i in range(8):
            on = base + i * EI
            dur = EI * 2 if i % 4 == 0 else EI - 4      # some held over beats
            lo.append((on, on + dur - 4, SC[i % 8] - 12, 68))
    return [(0, hi), (1, lo)]


RUNGS = [(k, v) for k, v in sorted(globals().items()) if k.startswith("rung_")]


def nset(p):
    import analyze as A
    d = A.parse_midi(p); x = A.extract(d)
    return {(round(n.on / d["division"], 4), n.pitch) for n in x["notes"]}


if __name__ == "__main__":
    import multipart as MP
    tmp = tempfile.mkdtemp()
    print(f"{'rung':<34}{'notes':>7}{'match':>9}   result")
    print("-" * 68)
    for name, fn in RUNGS:
        src = write(name, fn())
        out = os.path.join(tmp, name + ".musicxml")
        rt = os.path.join(tmp, name + ".mid")
        for q in (out, rt):
            if os.path.exists(q):
                os.remove(q)
        try:
            with redirect_stdout(io.StringIO()):
                MP.convert(src, out, "C major", 17, 14)
        except Exception as ex:
            print(f"{name:<34}{'':>7}{'':>9}   EXCEPTION {type(ex).__name__}"); continue
        p = subprocess.run([MS, "-o", rt, out], capture_output=True)
        if not os.path.exists(rt):
            err = p.stderr.decode("utf-8", "replace")
            crash = "mutex" in err or "libc++abi" in err
            print(f"{name:<34}{len(nset(src)):>7}{'':>9}   "
                  f"{'MUSESCORE CRASH' if crash else 'no render'}")
            continue
        a, b = nset(src), nset(rt)
        m = len(a & b) / len(a) * 100
        flag = "ok" if m >= 99 else ("degraded" if m >= 80 else "BROKEN")
        print(f"{name:<34}{len(a):>7}{m:>8.1f}%   {flag}")
