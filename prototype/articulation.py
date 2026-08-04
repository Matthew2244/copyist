#!/usr/bin/env python3
"""
Articulation from relative velocity — DESIGN.md O10.

Gate time gives you staccato and staccatissimo, and nothing else. Accent,
marcato and tenuto are not durations at all — they are a note being louder or
more deliberate than the notes AROUND it. The reference chart studied in
DESIGN 11.3 uses 120 marcato and 68 accent marks; Copyist could produce
neither, because it computed dynamics from velocity and then discarded the
signal.

Everything here is relative to local context, never to absolute MIDI values,
for the same reason dynamics are (a piece topping out at velocity 84 is not
therefore quiet). Thresholds are z-scores against the piece's own velocity
spread rather than constants — see CONTRIBUTING rule 3.
"""

import math

# z-score above the local mean. Chosen so that, on normally distributed
# velocities, roughly 7% of notes accent and 1% take marcato — matching the
# proportions in real engraved parts rather than a number picked by feel.
ACCENT_Z = 1.5
MARCATO_Z = 2.5

# A note has to be nearly fully held AND unemphatic to read as tenuto.
TENUTO_GATE = 0.95
TENUTO_Z = 0.25

WINDOW = 8                     # notes either side that define "local"


def local_stats(vels, i, window=WINDOW):
    lo, hi = max(0, i - window), min(len(vels), i + window + 1)
    ctx = vels[lo:hi]
    if len(ctx) < 3:
        return None, None
    mean = sum(ctx) / len(ctx)
    sd = math.sqrt(sum((v - mean) ** 2 for v in ctx) / len(ctx))
    return mean, sd


def annotate(chords):
    """
    chords: list of dicts with 'notes' (having .vel), 'gate' and 'dur',
    in time order, for ONE staff. Sets chord['artic'] to a MusicXML
    articulation element name, or None.

    Gate-derived marks win over velocity-derived ones: a note released at 20%
    of its slot is staccato whatever its velocity, and stacking staccato with
    marcato on the same note is noise on the page.
    """
    vels = [max(n.vel for n in c["notes"]) for c in chords]
    counts = {}
    for i, c in enumerate(chords):
        ratio = c["gate"] / c["dur"] if c.get("dur") else 1.0

        if ratio < 0.25:
            c["artic"] = "staccatissimo"
        elif ratio < 0.45:
            c["artic"] = "staccato"
        else:
            mean, sd = local_stats(vels, i)
            z = (vels[i] - mean) / sd if sd and sd > 1e-6 else 0.0
            if z >= MARCATO_Z:
                c["artic"] = "strong-accent"
            elif z >= ACCENT_Z:
                c["artic"] = "accent"
            elif ratio >= TENUTO_GATE and abs(z) <= TENUTO_Z:
                c["artic"] = "tenuto"
            else:
                c["artic"] = None

        if c["artic"]:
            counts[c["artic"]] = counts.get(c["artic"], 0) + 1
    return counts


def summarize(counts):
    if not counts:
        return "none"
    order = ["strong-accent", "accent", "tenuto", "staccato", "staccatissimo"]
    return ", ".join(f"{counts[k]} {k}" for k in order if k in counts)
