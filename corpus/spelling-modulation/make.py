#!/usr/bin/env python3
"""
Generate the spelling-modulation fixture.

Eight bars that modulate from E-flat major to E major. Three MIDI pitches
appear in BOTH halves and must be spelled differently in each:

    MIDI 68   A-flat in bars 1-4, G-sharp in bars 5-8
    MIDI 75   E-flat in bars 1-4, D-sharp in bars 5-8
    MIDI 73   D-flat in bars 1-4, C-sharp in bars 5-8

A single key signature cannot get both halves right, so any spelling approach
that picks one key for the whole piece scores at most about 80% here by
construction. That is the point of the fixture.

Ground truth is written alongside as `expected-spelling.json` — it is stated
here, not derived from the tool, so the test cannot pass by agreeing with
itself.

Usage:  python3 make.py
"""

import json
import os
import struct

DIV = 480
BPM = 80
HERE = os.path.dirname(os.path.abspath(__file__))

# (bar, beat, pitch, step, alter, is_left_hand)
# The step/alter columns are the CORRECT engraving, written by hand.
MUSIC = [
    # --- E-flat major -------------------------------------------------------
    (0, 0, 63, "E", -1, 0), (0, 1, 65, "F", 0, 0),
    (0, 2, 67, "G", 0, 0), (0, 3, 68, "A", -1, 0),
    (0, 0, 39, "E", -1, 1), (0, 2, 46, "B", -1, 1),

    (1, 0, 70, "B", -1, 0), (1, 1, 72, "C", 0, 0),
    (1, 2, 74, "D", 0, 0), (1, 3, 75, "E", -1, 0),
    (1, 0, 44, "A", -1, 1), (1, 2, 51, "E", -1, 1),

    (2, 0, 74, "D", 0, 0), (2, 1, 73, "D", -1, 0),      # chromatic descent
    (2, 2, 72, "C", 0, 0), (2, 3, 70, "B", -1, 0),
    (2, 0, 46, "B", -1, 1), (2, 2, 53, "F", 0, 1),

    (3, 0, 69, "A", 0, 0),                              # natural: V/V
    (3, 1, 70, "B", -1, 0), (3, 2, 67, "G", 0, 0),
    (3, 3, 63, "E", -1, 0),
    (3, 0, 39, "E", -1, 1), (3, 2, 46, "B", -1, 1),

    # --- E major ------------------------------------------------------------
    (4, 0, 64, "E", 0, 0), (4, 1, 66, "F", 1, 0),
    (4, 2, 68, "G", 1, 0), (4, 3, 69, "A", 0, 0),       # 68 flips to G-sharp
    (4, 0, 40, "E", 0, 1), (4, 2, 47, "B", 0, 1),

    (5, 0, 71, "B", 0, 0), (5, 1, 73, "C", 1, 0),       # 73 flips to C-sharp
    (5, 2, 75, "D", 1, 0), (5, 3, 76, "E", 0, 0),       # 75 flips to D-sharp
    (5, 0, 45, "A", 0, 1), (5, 2, 52, "E", 0, 1),

    (6, 0, 75, "D", 1, 0), (6, 1, 74, "D", 0, 0),
    (6, 2, 73, "C", 1, 0), (6, 3, 71, "B", 0, 0),
    (6, 0, 47, "B", 0, 1), (6, 2, 54, "F", 1, 1),

    (7, 0, 68, "G", 1, 0), (7, 1, 69, "A", 0, 0),
    (7, 2, 66, "F", 1, 0), (7, 3, 64, "E", 0, 0),
    (7, 0, 40, "E", 0, 1), (7, 2, 47, "B", 0, 1),
]


def vlq(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def track(events):
    events = sorted(events, key=lambda e: (e[0], e[1][0] & 0xF0 == 0x90))
    body, last = bytearray(), 0
    for t, data in events:
        body += vlq(t - last) + data
        last = t
    return b"MTrk" + struct.pack(">I", len(body) + 4) + bytes(body) + b"\x00\xFF\x2F\x00"


def meta_name(name):
    b = name.encode("latin-1")
    return b"\xFF\x03" + vlq(len(b)) + b


def build():
    notes, truth = [], []
    for bar, beat, pitch, step, alter, lh in MUSIC:
        on = bar * 4 * DIV + beat * DIV
        length = DIV * 2 if lh else DIV
        gate = int(length * 0.92)               # slightly early, as played
        notes.append((on, on + gate, pitch, 62 if lh else 74))
        truth.append({"on": on, "pitch": pitch, "step": step, "alter": alter})
    notes.sort(key=lambda n: (n[0], n[2]))
    truth.sort(key=lambda t: (t["on"], t["pitch"]))
    return notes, truth


if __name__ == "__main__":
    notes, truth = build()
    ev = []
    for on, off, p, v in notes:
        ev.append((on, bytes([0x90, p, v])))
        ev.append((off, bytes([0x80, p, 0])))

    conductor = track([
        (0, meta_name("spelling-modulation")),
        (0, b"\xFF\x51\x03" + struct.pack(">I", int(60_000_000 / BPM))[1:]),
        (0, b"\xFF\x58\x04\x04\x02\x18\x08"),
    ])
    perf = track([(0, meta_name("Pianoteq 9"))] + ev)
    with open(os.path.join(HERE, "clean.mid"), "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 1, 2, DIV) + conductor + perf)

    with open(os.path.join(HERE, "expected-spelling.json"), "w") as f:
        json.dump(truth, f, indent=1)

    flips = {}
    for t in truth:
        flips.setdefault(t["pitch"], set()).add((t["step"], t["alter"]))
    both = {p: v for p, v in flips.items() if len(v) > 1}
    print(f"wrote clean.mid — {len(notes)} notes")
    print(f"pitches requiring two spellings: "
          + ", ".join(f"{p} ({'/'.join(s + ('#' if a > 0 else 'b' if a < 0 else '') for s, a in sorted(v))})"
                      for p, v in sorted(both.items())))
