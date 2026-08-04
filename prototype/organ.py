#!/usr/bin/env python3
"""
Organ — DESIGN.md 8 and 10.

An organ is not three instruments that happen to play together. It is one
player at one instrument, and it is notated as one part on THREE staves:

    upper manual   (Swell / Great)
    lower manual   (Great / Choir)
    pedals         played with the feet, own staff, bass clef

Copyist's generic rule — one part per (track, channel) — gets this exactly
wrong, producing three separate "Organ" instruments in the part list and a
score no organist would accept.

## Hammond

Matthew's convention, which is also Hammond's own default:

    channel 1   upper manual
    channel 2   lower manual
    channel 3   pedals

Registration is drawbars, and Hammond assigns:

    CC 80   upper drawbars
    CC 81   lower drawbars
    CC 82   pedal drawbars
    CC 11   swell (expression)

## What is deliberately NOT inferred

Leslie speed, chorus/vibrato, percussion on/off and drawbar detail are
model-specific and largely NRPN. There is no portable mapping, and inventing
one would put confident nonsense on the page — the exact failure mode this
project exists to avoid. So Copyist reports the controller data it can see,
names what it cannot interpret, and leaves the decision to a human.

That turns out to be the musically right answer too. Registration is one of
the things a composer either specifies or deliberately leaves to the player,
so it belongs on the same axis as everything else in DESIGN 11: at full detail
write what was played, at reduced detail write "registration ad lib." and let
the performer be a musician.
"""

ORGAN_PROGRAMS = set(range(16, 21))          # GM 16-20 are the organs

UPPER_DRAWBARS, LOWER_DRAWBARS, PEDAL_DRAWBARS = 80, 81, 82
SWELL = 11

# Staff order in an organ score, top to bottom.
STAFF_UPPER, STAFF_LOWER, STAFF_PEDAL = 1, 2, 3

DIVISION_NAMES = {STAFF_UPPER: "upper manual",
                  STAFF_LOWER: "lower manual",
                  STAFF_PEDAL: "pedals"}


def looks_like_organ(parts):
    """
    True when the parts are divisions of one organ rather than an ensemble.

    Requires organ programs on two or three consecutive channels, with the
    lowest-sounding division actually low enough to be feet. Two organ patches
    in a rock band are not an organ score, and the pedal test is what keeps
    them apart.
    """
    organ = [p for p in parts
             if p.program in ORGAN_PROGRAMS and not p.info.get("drums")]
    if len(organ) < 2:
        return None

    organ.sort(key=lambda p: p.chan)
    chans = [p.chan for p in organ]
    if chans != list(range(chans[0], chans[0] + len(chans))):
        return None                       # not consecutive: probably an ensemble
    if len(organ) > 3:
        return None

    lowest = min(min(n.pitch for n in p.notes) for p in organ)
    if len(organ) == 3 and lowest > 52:
        return None                       # nothing down where feet play

    return organ


def assign_divisions(organ):
    """
    Map the parts onto staves. Channel order is the convention and is trusted
    when it is available; range is the fallback, because a file that ignores
    the convention still has feet at the bottom.
    """
    organ = sorted(organ, key=lambda p: p.chan)
    if len(organ) == 3:
        return {STAFF_UPPER: organ[0], STAFF_LOWER: organ[1],
                STAFF_PEDAL: organ[2]}

    # Two divisions: is the second one a pedalboard or a second manual?
    a, b = organ
    b_low = min(n.pitch for n in b.notes)
    b_high = max(n.pitch for n in b.notes)
    if b_high < 60 and b_low < 48:
        return {STAFF_UPPER: a, STAFF_PEDAL: b}
    return {STAFF_UPPER: a, STAFF_LOWER: b}


def registration(tracks, channel):
    """Drawbar and swell activity on one channel, as raw observations."""
    seen = {}
    for events in tracks:
        for e in events:
            if e[1] != "chan" or e[2] != 0xB0 or e[3] != channel:
                continue
            cc, val = e[4], e[5]
            if cc in (UPPER_DRAWBARS, LOWER_DRAWBARS, PEDAL_DRAWBARS, SWELL):
                seen.setdefault(cc, []).append((e[0], val))
    return seen


def describe(divisions, tracks, level, find=None):
    """
    Returns {staff: [(tick, text)]} of registration directions.

    At reduced detail this says "registration ad lib." once and stops, because
    a chart that tells a Hammond player exactly which drawbars to pull is
    usually telling them something they did not want to be told.
    """
    out = {}
    unknown_ccs = set()

    for staff, part in divisions.items():
        reg = registration(tracks, part.chan)
        marks = []

        if level != "full":
            marks.append((0, "registration ad lib."))
        else:
            for cc in (UPPER_DRAWBARS, LOWER_DRAWBARS, PEDAL_DRAWBARS):
                for tick, val in reg.get(cc, [])[:8]:
                    marks.append((tick, f"drawbars {val}"))
            for tick, val in reg.get(SWELL, [])[:1]:
                marks.append((tick, "swell"))
        if marks:
            out[staff] = sorted(marks)

        for events in tracks:
            for e in events:
                if (e[1] == "chan" and e[2] == 0xB0 and e[3] == part.chan
                        and e[4] not in (UPPER_DRAWBARS, LOWER_DRAWBARS,
                                         PEDAL_DRAWBARS, SWELL, 7, 64, 66, 67,
                                         121, 123)):
                    unknown_ccs.add(e[4])

    if find is not None:
        find.add("fixed-silently",
                 f"Organ: {len(divisions)} divisions on one part "
                 f"({', '.join(DIVISION_NAMES[s] for s in sorted(divisions))})",
                 why="an organ is one player at one instrument, notated on "
                     "three staves, not three instruments in the part list")
        if unknown_ccs:
            find.add("uncertain",
                     f"{len(unknown_ccs)} organ controller(s) not interpreted",
                     why="CC " + ", ".join(str(c) for c in sorted(unknown_ccs))
                         + " — Leslie, chorus and percussion are model-specific "
                           "and largely NRPN, with no portable mapping",
                     suggestion="Add them by hand, or leave them to the "
                                "player. Copyist will not guess.")
    return out
