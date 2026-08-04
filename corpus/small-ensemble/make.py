#!/usr/bin/env python3
"""
Generate the small-ensemble fixture — DESIGN.md 10.

Four parts chosen so that each one exercises a different thing multi-part
support has to get right, and all of it synthetic so the corpus stays
publishable:

    ch 1  Piano (GM 0)            two staves, hand separation runs
    ch 2  Trumpet (GM 56)         transposing, written a major 2nd up
    ch 3  Electric Bass (GM 33)   transposing, written an octave up
    ch 10 Drum Kit                percussion staff, unpitched, noteheads

Track names are deliberately EMPTY. Every one of the 25 real files that
prompted this work had empty names and correct GM programs, and Copyist
identified none of them because it only looked at names. If a future change
regresses GM resolution, this fixture is where it shows up.

Usage:  python3 make.py
"""

import json
import os
import struct

DIV = 480
BPM = 96
BARS = 8
HERE = os.path.dirname(os.path.abspath(__file__))

# (channel, GM program, expected part name, expected transpose-to-written)
PARTS = [
    (0, 0,  "Piano", 0),
    (1, 56, "Trumpet", 2),
    (2, 33, "Electric Bass", 12),
    (9, 0,  "Drum Kit", 0),
]

# i - VI - III - VII in A minor, two bars each
CHORDS = [(57, [57, 60, 64]), (53, [53, 57, 60]),
          (60, [60, 64, 67]), (55, [55, 59, 62])]

MELODY = [72, 74, 76, 79, 76, 74, 72, 69]
KICK, SNARE, HAT = 36, 38, 42


def vlq(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def track(events):
    events = sorted(events, key=lambda e: (e[0], (e[1][0] & 0xF0) == 0x90))
    body, last = bytearray(), 0
    for t, data in events:
        body += vlq(t - last) + data
        last = t
    body += vlq(0) + b"\xFF\x2F\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def build():
    per_part = {ch: [] for ch, _, _, _ in PARTS}
    beat, bar_ticks = DIV, 4 * DIV

    for bar in range(BARS):
        root, tones = CHORDS[(bar // 2) % 4]
        base = bar * bar_ticks

        # Piano: chord on 1, held; second inversion on 3. Two hands by span.
        for p in tones + [root - 24]:
            per_part[0].append((base, base + int(bar_ticks * 0.9), p, 58))
        for p in [t + 12 for t in tones]:
            per_part[0].append((base + 2 * beat, base + 2 * beat + int(beat * 1.8), p, 52))

        # Trumpet: melody in half notes, one octave, clearly treble
        for i in range(2):
            n = MELODY[(bar * 2 + i) % len(MELODY)]
            on = base + i * 2 * beat
            per_part[1].append((on, on + int(2 * beat * 0.88), n, 78))

        # Bass: root on 1 and 3, low
        for i in (0, 2):
            per_part[2].append((base + i * beat,
                                base + i * beat + int(beat * 0.85),
                                root - 24, 70))

        # Drums: kick 1 and 3, snare 2 and 4, hats on eighths
        for b in range(4):
            on = base + b * beat
            per_part[3 if False else 9].append(
                (on, on + 60, KICK if b % 2 == 0 else SNARE, 90))
            for h in (0, 1):
                ho = on + h * (beat // 2)
                per_part[9].append((ho, ho + 40, HAT, 64))
    return per_part


if __name__ == "__main__":
    per_part = build()

    conductor = track([
        (0, b"\xFF\x03" + vlq(len("small-ensemble")) + b"small-ensemble"),
        (0, b"\xFF\x51\x03" + struct.pack(">I", int(60_000_000 / BPM))[1:]),
        (0, b"\xFF\x58\x04\x04\x02\x18\x08"),
    ])

    chunks = [conductor]
    for ch, prog, _, _ in PARTS:
        ev = [(0, bytes([0xC0 | ch, prog]))]     # program change, no track name
        if ch == 0:                              # piano: exercise all 3 pedals
            for bar in range(BARS):
                b = bar * 4 * DIV
                ev.append((b + 10, bytes([0xB0, 64, 100])))          # sustain
                ev.append((b + 4 * DIV - 20, bytes([0xB0, 64, 0])))
                if bar % 4 == 0:                                     # sostenuto
                    ev.append((b + 5, bytes([0xB0, 66, 110])))
                    ev.append((b + 8 * DIV - 30, bytes([0xB0, 66, 0])))
                if bar in (2, 3):                                    # una corda
                    ev.append((b, bytes([0xB0, 67, 90])))
                    ev.append((b + 4 * DIV - 10, bytes([0xB0, 67, 0])))
        for on, off, p, v in sorted(per_part[ch]):
            ev.append((on, bytes([0x90 | ch, p, v])))
            ev.append((off, bytes([0x80 | ch, p, 0])))
        chunks.append(track(ev))

    with open(os.path.join(HERE, "clean.mid"), "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), DIV)
                + b"".join(chunks))

    with open(os.path.join(HERE, "expected-parts.json"), "w") as f:
        json.dump([{"channel": ch, "program": prog, "name": name,
                    "transpose": tr} for ch, prog, name, tr in PARTS],
                  f, indent=1)

    total = sum(len(v) for v in per_part.values())
    print(f"wrote clean.mid — {total} notes, {len(PARTS)} parts, "
          f"{BARS} bars, no track names")
