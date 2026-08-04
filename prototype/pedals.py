#!/usr/bin/env python3
"""
All three piano pedals — DESIGN.md 10, pipeline step 10.

Copyist handled sustain and nothing else, which is the same mistake every MIDI
importer makes. A grand has three, they do genuinely different things, and two
of them were being thrown away:

    CC 64  sustain / damper     raises all dampers
    CC 66  sostenuto            holds only what is already down
    CC 67  soft / una corda     shifts the action

Sostenuto especially matters: it is the pedal that lets a bass note ring under
a passage played dry above it, and a score that silently drops it asks the
player to do something the composer specifically avoided.

MusicXML has a first-class `sostenuto` pedal type. Una corda has no element —
it is conventionally text, so it is emitted as a direction reading "una corda"
and "tre corde", which is what an engraver writes.

Half-pedalling is not modelled. A continuous controller sweep is real
technique, but notating it needs graphical pedal lines with depth, and a
tool that cannot yet write a triplet has no business there.
"""

SUSTAIN, SOSTENUTO, SOFT = 64, 66, 67
DOWN = 64                       # controller value at or above this is "on"

NAMES = {SUSTAIN: "sustain", SOSTENUTO: "sostenuto", SOFT: "una corda"}


def spans(tracks, controller, channel=None):
    """Every (down_tick, up_tick) for one controller."""
    out = []
    for events in tracks:
        down = None
        for e in events:
            if e[1] != "chan" or e[2] != 0xB0 or e[4] != controller:
                continue
            if channel is not None and e[3] != channel:
                continue
            if e[5] >= DOWN and down is None:
                down = e[0]
            elif e[5] < DOWN and down is not None:
                out.append((down, e[0]))
                down = None
        if down is not None:                 # held to the end of the track
            out.append((down, down + 1))
    return sorted(out)


def collect(tracks, channel=None, find=None):
    """
    Returns {controller: [(on, off), ...]} for whichever pedals appear.
    """
    got = {}
    for cc in (SUSTAIN, SOSTENUTO, SOFT):
        s = spans(tracks, cc, channel)
        if s:
            got[cc] = s

    if find is not None and got:
        parts = ", ".join(f"{len(v)} {NAMES[k]}" for k, v in sorted(got.items()))
        extra = [NAMES[k] for k in got if k != SUSTAIN]
        find.add("fixed-silently",
                 f"Pedal marks written: {parts}",
                 why=("all three pedals are read, not just sustain"
                      if extra else "CC64 spans, normally discarded on import"),
                 suggestion=("Sostenuto and una corda are dropped by every "
                             "other MIDI import" if extra else ""))
    return got


def directions_for_measure(got, m_start, m_end, staff_hint=2):
    """
    MusicXML directions for whatever happens inside one measure.

    Sustain and sostenuto are <pedal> elements; una corda is text, because
    MusicXML has no element for it and text is what an engraver writes.
    """
    out = []

    def block(inner):
        out.extend(['      <direction placement="below">',
                    '        <direction-type>' + inner + '</direction-type>',
                    f'        <staff>{staff_hint}</staff>',
                    '      </direction>'])

    for on, off in got.get(SUSTAIN, []):
        if m_start <= on < m_end:
            block('<pedal type="start" line="yes"/>')
        if m_start <= off < m_end:
            block('<pedal type="stop" line="yes"/>')

    for on, off in got.get(SOSTENUTO, []):
        if m_start <= on < m_end:
            block('<pedal type="sostenuto" line="yes"/>')
        if m_start <= off < m_end:
            block('<pedal type="stop" line="yes"/>')

    for on, off in got.get(SOFT, []):
        if m_start <= on < m_end:
            block('<words>una corda</words>')
        if m_start <= off < m_end:
            block('<words>tre corde</words>')

    return out
