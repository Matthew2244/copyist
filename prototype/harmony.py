#!/usr/bin/env python3
"""
Chord detection — DESIGN.md 12.1.

Needed before detail levels (§11) can mean anything: "four bars of slashes" is
only useful if there is a chord symbol above the slashes. The design's primary
source is a dedicated chord MIDI track, which is unambiguous. This is the
fallback for when there isn't one — inferring harmony from the arrangement
itself, which is meaningfully less reliable and therefore always reports a
confidence and files a finding.

Template matching over duration-weighted pitch-class profiles. Deliberately
not a deep model: the point is a chord symbol a musician reads and interprets,
not a theoretically complete analysis, and a wrong-but-plausible symbol on a
chart is worse than a plainer right one.
"""

from collections import defaultdict

PC_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
PC_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# (suffix, intervals, MusicXML kind). Ordered richest-first so a seventh is
# preferred over the triad hiding inside it when the seventh is really there.
TEMPLATES = [
    ("m7b5", (0, 3, 6, 10), "half-diminished"),
    ("maj7", (0, 4, 7, 11), "major-seventh"),
    ("m7",   (0, 3, 7, 10), "minor-seventh"),
    ("7",    (0, 4, 7, 10), "dominant"),
    ("6",    (0, 4, 7, 9),  "major-sixth"),
    ("m6",   (0, 3, 7, 9),  "minor-sixth"),
    ("dim7", (0, 3, 6, 9),  "diminished-seventh"),
    ("sus4", (0, 5, 7),     "suspended-fourth"),
    ("aug",  (0, 4, 8),     "augmented"),
    ("dim",  (0, 3, 6),     "diminished"),
    ("m",    (0, 3, 7),     "minor"),
    ("",     (0, 4, 7),     "major"),
    ("5",    (0, 7),        "power"),
]

# A chord needs to explain most of what is sounding before it is worth naming.
MIN_CONFIDENCE = 0.55


def segments(notes, measure_ticks, per_bar=1):
    """Group notes into harmonic windows. per_bar=2 gives half-bar resolution."""
    span = measure_ticks // per_bar
    buckets = defaultdict(list)
    for n in notes:
        buckets[n.on // span].append(n)
    return span, buckets


def profile(notes):
    """Duration-weighted pitch-class mass, normalized."""
    w = [0.0] * 12
    for n in notes:
        w[n.pitch % 12] += max(n.dur, 1)
    total = sum(w)
    return [x / total for x in w] if total else w


def best_chord(notes):
    """Returns (root_pc, suffix, kind, confidence, bass_pc) or None."""
    if len(notes) < 2:
        return None
    p = profile(notes)
    bass = min(notes, key=lambda n: n.pitch).pitch % 12

    # Two things have to be true at once for a template to be the right name:
    # it must account for most of what is sounding, AND all of its own notes
    # must actually be there. Scoring on coverage alone picks the largest
    # template that fits; dividing by template size picks the smallest, which
    # names every triad as a power chord. Multiplying the two is what makes a
    # seventh win only when the seventh is genuinely present.
    PRESENT = 0.02          # pitch-class mass that counts as "sounding"
    best = None
    for root in range(12):
        for suffix, ivs, kind in TEMPLATES:
            explained = sum(p[(root + i) % 12] for i in ivs)
            present = sum(1 for i in ivs
                          if p[(root + i) % 12] > PRESENT) / len(ivs)
            score = explained * present + 0.15 * p[root]
            if best is None or score > best[0]:
                best = (score, root, suffix, kind)

    score, root, suffix, kind = best
    return (root, suffix, kind, min(score, 1.0), bass)


def name_of(root_pc, suffix, fifths, bass_pc=None):
    names = PC_FLAT if fifths < 0 else PC_SHARP
    s = names[root_pc] + suffix
    if bass_pc is not None and bass_pc != root_pc:
        s += "/" + names[bass_pc]
    return s


def detect(notes, measure_ticks, fifths, per_bar=1, find=None):
    """
    Returns a list of dicts, one per harmonic window that could be named:
        {tick, measure, root, suffix, kind, bass, confidence, name}
    """
    span, buckets = segments(notes, measure_ticks, per_bar)
    out, weak = [], 0
    prev_name = None

    for idx in sorted(buckets):
        got = best_chord(buckets[idx])
        if not got:
            continue
        root, suffix, kind, conf, bass = got
        if conf < MIN_CONFIDENCE:
            weak += 1
            continue
        name = name_of(root, suffix, fifths, bass)
        if name == prev_name:
            continue                      # do not repeat an unchanged symbol
        prev_name = name
        out.append({
            "tick": idx * span,
            "measure": (idx * span) // measure_ticks,
            "root": root, "suffix": suffix, "kind": kind,
            "bass": bass if bass != root else None,
            "confidence": round(conf, 2),
            "name": name,
        })

    if find is not None and out:
        avg = sum(c["confidence"] for c in out) / len(out)
        find.add("uncertain" if avg < 0.72 else "fixed-silently",
                 f"{len(out)} chord symbol(s) inferred from the arrangement",
                 why=f"no dedicated chord track; mean confidence "
                     f"{avg * 100:.0f}%"
                     + (f", {weak} window(s) too ambiguous to name" if weak else ""),
                 suggestion="A chord track would make these exact (DESIGN 12.1)")
    return out
