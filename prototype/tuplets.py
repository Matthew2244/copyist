#!/usr/bin/env python3
"""
Per-beat grid selection, with tuplets — DESIGN.md 7.2, 7.2.1.

Measured cost of not having this, on public-domain classical repertoire where
Copyist had already declared the grid exact and was therefore CONFIDENT:

    mostly binary   n=16   mean round-trip 98.1%
    mostly triplet  n=16   mean round-trip 64.5%

33.5 points, on 21% of that corpus. Confident and wrong is the worst
combination a tool can offer, and one file — Debussy's first Arabesque, which
is triplets end to end — came back at 11.1%.

The fix is the one §7.2.1 always described: **choose the grid per beat, not
per piece.** A piece can be straight eighths in bar 1 and triplets in bar 12,
and forcing one subdivision on the whole file is why every existing tool
mangles one or the other.

Each beat is scored against candidate subdivisions. Cost combines how far the
onsets have to move with how expensive the notation is to read — a triplet
carries a real setup cost, so it only wins when it genuinely explains the
beat — plus a consistency bonus for agreeing with the previous beat, because
established patterns should be sticky.
"""

# subdivisions-per-beat -> (label, notated type, actual, normal, complexity)
#
# `actual`/`normal` are the MusicXML time-modification. The conventions are
# the standard ones: triplet eighths are 3 in the time of 2, sextuplets and
# quintuplets and septuplets are counted against 4 sixteenths.
CANDIDATES = {
    1:  ("quarter", "quarter", 1, 1, 0.0),
    2:  ("8th", "eighth", 1, 1, 0.5),
    4:  ("16th", "16th", 1, 1, 1.4),
    8:  ("32nd", "32nd", 1, 1, 3.0),
    3:  ("triplet 8th", "eighth", 3, 2, 2.2),
    6:  ("sextuplet", "16th", 6, 4, 3.4),
    5:  ("quintuplet", "16th", 5, 4, 6.0),
    7:  ("septuplet", "16th", 7, 4, 7.0),
}

CONSISTENCY_BONUS = 1.6      # keeping the previous beat's subdivision

# Fidelity is SQUARED and weighted heavily, and that is the whole cost model.
#
# A linear term with a modest weight looked reasonable and was badly wrong: on
# Debussy's first Arabesque the sextuplet grid fits with residual 0.0000 and
# still lost to plain sixteenths, because moving every note by a sixteenth
# only cost about one unit. Moving a note by a sixteenth is not a small
# change; it is the difference between the piece and a different piece.
#
# Squaring makes near-misses cheap and real misses ruinous, so a subdivision
# that actually fits nearly always wins, and complexity only decides between
# candidates that ALL fit — which is exactly when "prefer the simpler
# notation" is the right instinct.
FIDELITY_WEIGHT = 2000.0


def _beat_cost(offsets, beat_ticks, n):
    """Mean distance from the onsets in one beat to an n-way subdivision."""
    if not offsets:
        return 0.0
    step = beat_ticks / n
    total = 0.0
    for o in offsets:
        nearest = round(o / step) * step
        total += abs(o - nearest)
    return (total / len(offsets)) / beat_ticks


def choose(onsets, beat_ticks, allow=None):
    """
    onsets: absolute tick positions, sorted.
    Returns [(beat_index, subdivision)] for every beat that has notes.
    """
    allow = allow or CANDIDATES
    by_beat = {}
    for t in onsets:
        by_beat.setdefault(int(t // beat_ticks), []).append(t % beat_ticks)

    out = {}
    previous = None
    for b in sorted(by_beat):
        offsets = by_beat[b]
        best, best_cost = None, None
        for n, (_, _, _, _, complexity) in allow.items():
            # A single onset on the beat explains nothing; do not let it vote
            # for an exotic subdivision.
            if len(offsets) == 1 and abs(offsets[0]) < beat_ticks * 0.02 and n > 2:
                continue
            residual = _beat_cost(offsets, beat_ticks, n)
            cost = residual * residual * FIDELITY_WEIGHT + complexity
            if previous == n:
                cost -= CONSISTENCY_BONUS
            if best_cost is None or cost < best_cost:
                best, best_cost = n, cost
        out[b] = best
        previous = best
    return out


def snap(notes, beat_ticks, grids):
    """
    Move every note onto the subdivision chosen for its beat, keeping gate
    length. Returns how many beats ended up on a tuplet grid.
    """
    tuplet_beats = 0
    for n in notes:
        b = int(n.on // beat_ticks)
        sub = grids.get(b, 2)
        step = beat_ticks / sub
        within = n.on % beat_ticks
        snapped = int(b * beat_ticks + round(within / step) * step)
        n.off += snapped - n.on
        n.on = snapped
    for sub in grids.values():
        if CANDIDATES[sub][2] != CANDIDATES[sub][3]:
            tuplet_beats += 1
    return tuplet_beats


def modification(sub):
    """MusicXML time-modification for a subdivision, or None if it is binary."""
    _, ntype, actual, normal, _ = CANDIDATES[sub]
    if actual == normal:
        return None
    return {"type": ntype, "actual": actual, "normal": normal}


# Note-value ladder, shortest first. Used to name a duration that spans
# several subdivisions of one tuplet: two triplet eighths make a triplet
# quarter, three make a dotted triplet quarter, and so on.
LADDER = ["64th", "32nd", "16th", "eighth", "quarter", "half", "whole"]


def notated(ticks, beat_ticks, sub):
    """
    (type, dots) for a duration inside a tuplet beat, or None if the duration
    is not a whole number of subdivisions — in which case the caller should
    fall back to ordinary binary decomposition rather than force it.
    """
    step = beat_ticks / sub
    k = ticks / step
    if abs(k - round(k)) > 1e-6 or round(k) < 1:
        return None
    k = int(round(k))
    base = LADDER.index(CANDIDATES[sub][1])
    for extra, (mult, dots) in enumerate(((1, 0), (2, 0), (3, 1), (4, 0),
                                          (6, 1), (8, 0))):
        if k == mult:
            idx = base + (0 if mult == 1 else
                          1 if mult in (2, 3) else
                          2 if mult in (4, 6) else 3)
            if idx < len(LADDER):
                return LADDER[idx], dots
            return None
    return None


def summarize(grids):
    from collections import Counter
    c = Counter(CANDIDATES[s][0] for s in grids.values())
    return ", ".join(f"{v} {k}" for k, v in c.most_common())
