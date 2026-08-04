#!/usr/bin/env python3
"""
Detail level — DESIGN.md 11.

The section the whole product argument rests on. Every other MIDI-to-notation
tool maximizes fidelity; that is the wrong goal when the reader is a
collaborator who will interpret the part rather than reproduce it. A part that
notates every 32nd of a placeholder groove is *actively worse* for that reader
than one saying "Cm7, four bars, groove as demo" — it over-specifies, and
over-specification reads as instruction.

So Copyist can deliberately throw information away, and that is the feature.

Reduction runs LATE in the pipeline, after everything is understood, because
you cannot decide a bar becomes four slashes until you know what is in it —
and the chord symbol above those slashes comes from that same understanding.

Levels implemented here:

    full      everything notated (no reduction)
    slashes   chord symbols above, one slash per beat
    symbols   chord symbols and bar count only

Not yet implemented: `simplified` and `rhythmic-slashes`. Two working levels
beat four half-working ones, and the two here are the ends of the range.
"""

LEVELS = ("full", "slashes", "symbols")


def describe(level):
    return {
        "full": "everything notated",
        "slashes": "chord symbols with one slash per beat",
        "symbols": "chord symbols and bar count only",
    }.get(level, level)


def reduce_streams(streams, level, measure_ticks, div, ts_num, ts_den,
                   n_measures, find=None):
    """
    Returns (streams, slash_bars).

    At a reduced level the notated content is replaced by slash events on the
    upper staff and the lower staff is emptied — a rhythm-section chart has one
    line of slashes, not two staves of them.
    """
    if level == "full":
        return streams, set()

    beat = int(div * 4 / ts_den)
    per_bar = max(int(ts_num), 1)
    bars = range(int(n_measures))

    slashes = []
    for m in bars:
        base = m * measure_ticks
        if level == "symbols":
            slashes.append({"on": base, "dur": measure_ticks, "notes": [],
                            "artic": None, "slash": True, "whole": True})
        else:
            for b in range(per_bar):
                slashes.append({"on": base + b * beat, "dur": beat, "notes": [],
                                "artic": None, "slash": True, "whole": False})

    if find is not None:
        kept = sum(len(s) for s in streams.values())
        find.add("fixed-silently",
                 f"Reduced to {describe(level)}",
                 why=f"{kept} notated event(s) replaced by {len(slashes)} "
                     f"slash(es) across {int(n_measures)} bars",
                 suggestion="DESIGN 11 — the demo is source material a "
                            "collaborator interprets, not a part to reproduce")

    return {1: slashes, 2: []}, {m for m in bars}


def filter_findings(findings, level):
    """
    11.1 — a complaint about material that is about to become four slashes is
    noise. Drop notation-quality findings at reduced levels; keep everything
    about harmony, instrument identification and the file itself.
    """
    if level == "full":
        return findings

    NOISE = ("phantom rest", "chords printed on the other staff",
             "shattered onsets", "Articulation", "hand", "double accidental",
             "Widest simultaneity")
    kept, dropped = [], 0
    for f in findings:
        text = f.get("what", "")
        if any(k.lower() in text.lower() for k in NOISE):
            dropped += 1
            continue
        kept.append(f)
    if dropped:
        kept.append({
            "id": f"F{len(kept) + 1}",
            "severity": "fixed-silently",
            "location": "",
            "what": f"{dropped} finding(s) hidden as irrelevant at this "
                    f"detail level",
            "why": "they describe notation that is now slashes",
            "suggestion": "Convert at full detail to see them",
        })
    return kept
