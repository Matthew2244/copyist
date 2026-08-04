#!/usr/bin/env python3
"""
Minimal Standard MIDI File writer.

Exists so Copyist can render **what the score says** back to MIDI without
depending on MuseScore being installed — see DESIGN.md 16, the A/B audition.

That is the point of the audition and the reason it matters more here than in
any other notation tool: you cannot check whether a page looks right, but you
can absolutely check whether it still SOUNDS like what you meant. Playing the
notated version means playing the quantized onsets, the notated durations and
the articulations Copyist decided on — not the performance it started from.
If those two disagree in a way you can hear, Copyist got something wrong.
"""

import struct


def vlq(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def _track(events):
    """events: [(abs_tick, bytes)]. Note-offs sort before note-ons at a tick."""
    events = sorted(events, key=lambda e: (e[0], (e[1][0] & 0xF0) == 0x90))
    body, last = bytearray(), 0
    for t, data in events:
        body += vlq(t - last) + data
        last = t
    body += vlq(0) + b"\xFF\x2F\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def write(path, notes, division, bpm, ts=(4, 4), name="Copyist"):
    """
    notes: iterable of (on_tick, off_tick, pitch, velocity).
    """
    conductor = _track([
        (0, b"\xFF\x03" + vlq(len(name)) + name.encode("latin-1", "replace")),
        (0, b"\xFF\x51\x03" + struct.pack(">I", int(60_000_000 / bpm))[1:]),
        (0, b"\xFF\x58\x04" + bytes([ts[0], max(ts[1].bit_length() - 1, 0),
                                     0x18, 0x08])),
    ])
    ev = []
    for on, off, pitch, vel in notes:
        off = max(off, on + 1)
        ev.append((int(on), bytes([0x90, int(pitch) & 0x7F, max(1, min(127, int(vel)))])))
        ev.append((int(off), bytes([0x80, int(pitch) & 0x7F, 0])))
    with open(path, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 1, 2, division)
                + conductor + _track(ev))


# How long a note actually sounds for a given articulation, as a fraction of
# its notated value. These are playback conventions, not engraving ones.
ARTIC_GATE = {
    "staccatissimo": 0.25,
    "staccato": 0.50,
    "tenuto": 1.00,
    "accent": 0.90,
    "strong-accent": 0.85,
    None: 0.92,
}

ARTIC_VELOCITY = {
    "accent": 14,
    "strong-accent": 24,
    "tenuto": 0,
    "staccato": 0,
    "staccatissimo": -4,
    None: 0,
}


def notes_from_streams(streams):
    """Turn Copyist's notated chords into playable notes."""
    out = []
    for seq in streams.values():
        for ch in seq:
            artic = ch.get("artic")
            gate = ARTIC_GATE.get(artic, 0.92)
            bump = ARTIC_VELOCITY.get(artic, 0)
            dur = max(int(ch["dur"] * gate), 1)
            for n in ch["notes"]:
                out.append((ch["on"], ch["on"] + dur, n.pitch, n.vel + bump))
    return sorted(out)
