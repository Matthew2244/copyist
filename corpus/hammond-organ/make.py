#!/usr/bin/env python3
"""
Generate the hammond-organ fixture — DESIGN.md 8, 10.

Matthew's own rig convention, which is also Hammond's default:

    channel 1   upper manual   GM 16 (drawbar organ)
    channel 2   lower manual   GM 16
    channel 3   pedals         GM 16, played with the feet

The point of the fixture is that Copyist's generic rule — one part per
(track, channel) — gets an organ exactly wrong, listing three separate "Organ"
instruments. An organ is ONE player at ONE instrument on THREE staves, and if
that regresses this is where it shows.

Controllers included:

    CC 80 / 81 / 82   drawbar registration, upper / lower / pedal
    CC 11             swell
    CC 68             stands in for something model-specific. Copyist must
                      REPORT it as uninterpreted rather than guess — Leslie,
                      chorus and percussion have no portable MIDI mapping.

Usage:  python3 make.py
"""

import json
import os
import struct

DIV = 480
BPM = 84
BARS = 8
HERE = os.path.dirname(os.path.abspath(__file__))

UPPER_CH, LOWER_CH, PEDAL_CH = 0, 1, 2
ORGAN_PROGRAM = 16

# i - iv - V - i in D minor, gospel-ish
CHORDS = [(50, [62, 65, 69]), (55, [67, 70, 74]),
          (57, [69, 73, 76]), (50, [62, 65, 69])]

UPPER_LINE = [74, 76, 77, 76, 74, 72, 70, 69]


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
    beat, bar_ticks = DIV, 4 * DIV
    upper, lower, pedal = [], [], []

    for bar in range(BARS):
        root, tones = CHORDS[bar % 4]
        base = bar * bar_ticks

        # Upper manual: a line in the right hand, two notes per bar
        for i in range(2):
            n = UPPER_LINE[(bar * 2 + i) % len(UPPER_LINE)]
            on = base + i * 2 * beat
            upper.append((on, on + int(2 * beat * 0.9), n, 88))

        # Lower manual: the chord, held
        for p in tones:
            lower.append((base, base + int(bar_ticks * 0.95), p - 12, 70))

        # Pedals: root, long, low — feet do not play fast
        pedal.append((base, base + int(bar_ticks * 0.92), root - 24, 80))

    return upper, lower, pedal


if __name__ == "__main__":
    upper, lower, pedal = build()

    conductor = track([
        (0, b"\xFF\x03" + vlq(len("hammond-organ")) + b"hammond-organ"),
        (0, b"\xFF\x51\x03" + struct.pack(">I", int(60_000_000 / BPM))[1:]),
        (0, b"\xFF\x58\x04\x04\x02\x18\x08"),
    ])

    chunks = [conductor]
    for ch, notes, drawbar_cc in ((UPPER_CH, upper, 80),
                                  (LOWER_CH, lower, 81),
                                  (PEDAL_CH, pedal, 82)):
        ev = [(0, bytes([0xC0 | ch, ORGAN_PROGRAM])),
              (0, bytes([0xB0 | ch, drawbar_cc, 88 if ch == UPPER_CH else 40]))]
        if ch == UPPER_CH:
            ev.append((0, bytes([0xB0 | ch, 11, 100])))          # swell
            ev.append((4 * DIV, bytes([0xB0 | ch, 68, 127])))    # unmappable
            ev.append((16 * DIV, bytes([0xB0 | ch, 68, 0])))
            ev.append((8 * DIV, bytes([0xB0 | ch, drawbar_cc, 118])))
        for on, off, p, v in sorted(notes):
            ev.append((on, bytes([0x90 | ch, p, v])))
            ev.append((off, bytes([0x80 | ch, p, 0])))
        chunks.append(track(ev))

    with open(os.path.join(HERE, "clean.mid"), "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), DIV)
                + b"".join(chunks))

    json.dump({"parts": 1, "name": "Organ", "staves": 3,
               "divisions": ["upper manual", "lower manual", "pedals"],
               "uninterpreted_cc": [68]},
              open(os.path.join(HERE, "expected-organ.json"), "w"), indent=1)

    print(f"wrote clean.mid — {len(upper)+len(lower)+len(pedal)} notes, "
          f"3 divisions on channels 1/2/3, {BARS} bars")
