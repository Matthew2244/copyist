#!/usr/bin/env python3
"""
Generate the two-hand-piano fixture.

Synthetic on purpose — no copyrighted or private material — but it reproduces
every pathology the real-world case exhibits:

  * onsets exactly on an 8th grid (hard quantized)
  * note releases 5-25% early, which is what produces phantom rests
  * simultaneities wider than a player's reach, forcing certain hand splits
  * chromatic notes that exercise pitch spelling in a sharp key
  * a sustain pedal track
  * a wide velocity range so dynamics have something to normalize against
  * a humanized variant: per-note gaussian jitter, which shatters the chords

Deterministic: same seed, same bytes. Run it to regenerate the fixture.

Usage:  python3 make.py
"""

import math
import os
import random
import struct

DIV = 480                      # ticks per quarter
BPM = 72
BEATS_PER_BAR = 4
JITTER_MS = 12.7               # matches REAPER humanize as measured
SEED = 20260803

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ SMF write

def vlq(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def track(events):
    """events: list of (abs_tick, bytes). Returns a full MTrk chunk."""
    events = sorted(events, key=lambda e: (e[0], e[1][0] & 0xF0 == 0x90))
    body, last = bytearray(), 0
    for t, data in events:
        body += vlq(t - last) + data
        last = t
    body += vlq(0) + b"\xFF\x2F\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def meta_name(name):
    b = name.encode("latin-1")
    return b"\xFF\x03" + vlq(len(b)) + b


def write_midi(path, note_events, cc_events, name):
    conductor = track([
        (0, meta_name("two-hand-piano")),
        (0, b"\xFF\x51\x03" + struct.pack(">I", int(60_000_000 / BPM))[1:]),
        (0, b"\xFF\x58\x04\x04\x02\x18\x08"),
    ])
    perf = track([(0, meta_name(name))] + note_events + cc_events)
    header = b"MThd" + struct.pack(">IHHH", 6, 1, 2, DIV)
    with open(path, "wb") as f:
        f.write(header + conductor + perf)


# ------------------------------------------------------------------ the music

# i - VI - III - VII in C# minor, two bars each. Chosen so the left hand sits
# low and the right hand sits high, guaranteeing simultaneities past an 11th.
PROGRESSION = [
    # (left-hand root, left-hand chord tones, right-hand scale degrees)
    (37, [37, 44, 49], [61, 64, 68, 71, 73]),      # C#m
    (33, [33, 40, 45], [57, 61, 64, 69, 73]),      # A
    (40, [40, 47, 52], [56, 59, 64, 68, 71]),      # E
    (35, [35, 42, 47], [59, 63, 66, 71, 75]),      # B
]

# Deliberate chromatic passing tones, to give the speller something to do.
PASSING = {3: 1, 7: -1, 11: 1, 15: -1}


def build():
    rng = random.Random(SEED)
    notes = []                                  # (on_tick, off_tick, pitch, vel)
    eighth = DIV // 2
    bar_ticks = BEATS_PER_BAR * DIV

    for bar in range(8):
        chord = PROGRESSION[(bar // 2) % 4]
        root, tones, rh = chord
        base = bar * bar_ticks

        # Left hand: the chord on beat 1, held; a single low root on beat 3.
        gate = int(bar_ticks * rng.uniform(0.80, 0.94))     # early release
        for p in tones:
            notes.append((base, base + gate, p, rng.randint(38, 56)))
        g2 = int(DIV * 2 * rng.uniform(0.75, 0.90))
        notes.append((base + DIV * 2, base + DIV * 2 + g2, root - 12,
                      rng.randint(34, 48)))

        # Right hand: running eighths, occasionally two notes together.
        for i in range(8):
            on = base + i * eighth
            deg = rh[i % len(rh)]
            step = bar * 8 + i
            if step in PASSING:
                deg += PASSING[step]
            gate = int(eighth * rng.uniform(0.72, 0.95))    # <- phantom rests
            vel = rng.randint(52, 88) + (10 if i % 4 == 0 else 0)
            notes.append((on, on + gate, deg, min(vel, 96)))
            if i in (0, 5) and bar % 2 == 1:                 # a two-note chord
                notes.append((on, on + gate, deg + 5, max(vel - 8, 40)))

    # Final chord, wide, held.
    end = 8 * bar_ticks
    for p in (25, 37, 44, 49, 61, 68):
        notes.append((end, end + bar_ticks * 2 - 40, p, rng.randint(30, 44)))

    # Sustain pedal: down on each bar, up just before the next.
    cc = []
    for bar in range(9):
        b = bar * bar_ticks
        cc.append((b + 20, bytes([0xB0, 64, 100])))
        cc.append((b + bar_ticks - 30, bytes([0xB0, 64, 0])))
    return notes, cc


def note_events(notes):
    ev = []
    for on, off, p, v in notes:
        ev.append((on, bytes([0x90, p, v])))
        ev.append((off, bytes([0x80, p, 0])))
    return ev


def humanize(notes):
    """Per-note gaussian jitter. This is what shatters chords."""
    rng = random.Random(SEED + 1)
    sd = JITTER_MS * BPM / 60000.0 * DIV
    out = []
    for on, off, p, v in notes:
        d = int(round(rng.gauss(0, sd)))
        out.append((max(on + d, 0), max(off + d, 1), p, v))
    return out


if __name__ == "__main__":
    notes, cc = build()
    write_midi(os.path.join(HERE, "clean.mid"),
               note_events(notes), cc, "Pianoteq 9")
    write_midi(os.path.join(HERE, "humanized.mid"),
               note_events(humanize(notes)), cc, "Pianoteq 9")
    print(f"wrote clean.mid and humanized.mid — {len(notes)} notes, "
          f"{len({n[0] for n in notes})} unique onsets")
