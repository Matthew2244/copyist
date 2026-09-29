#!/usr/bin/env python3
"""chartending — how the tune ends, on the page and in the listen.

A chart's last section can say how the band gets off the stage, in the
words a leader uses (Matthew, 2026-09-29: "if it's a roll, a trash can
ending, a fade out, a stop, a slow down, a short hit wherever the chart
says ... we are holding that last chord, and on my head nod I cue the
last hit of the chord or the drummer does some fill, then I cue"):

    ending: hold, drums fill, last hit on cue
    ending: trash can
    ending: rit, hold
    ending: cold
    ending: button
    ending: fade

Steps run in order. The pages print them in words over the last bar of
every part that plays there, with a fermata when the band holds; the
listen performs them. In the listen the last bar becomes one long held
measure (the band lands on the final chord and holds it, a written part
holding its own last note), whatever plays over the hold plays in it
(a roll, a fill, a trash can, someone noodling over the last chord),
and a hit, on the cue, is one short bar after it. The listening
document is not the page, so it may carry bars the page does not.

Deterministic like the rest of the band: the same chart ends the same
way every build.
"""
import re

import chartgroove as G

HOLD_BARS = 2          # how long a hold rings past the last bar, in bars

_STEP_WORDS = [
    ('trash', r'trash\s*-?\s*can(?: ending)?|big (?:rock )?ending|'
              r'crash ending'),
    ('roll', r'(?:drum |cymbal |snare )?roll'),
    ('stop', r'cold(?: ending)?|dead stop|stop(?: dead)?|stop time'),
    ('rit', r'rit\.?|ritard(?:ando)?|rall\.?|slow(?:ing)? down|'
            r'broaden|molto rit\.?'),
    ('fade', r'fade(?: out)?|fade to nothing'),
    ('hold', r'hold(?: it| the (?:last )?chord| out)?|fermata|'
             r'let (?:it )?ring|ring out'),
    ('button', r'button|stinger'),
    ('hit', r'(?:the )?(?:last |final )?(?:hit|cut ?off|cut it off|'
            r'chord)'),
]
_CUE = re.compile(r'\s*(?:on (?:my |the |a )?(?:cue|nod|signal)|'
                  r'on cue|when cued|cued)\s*', re.I)


class EndingError(Exception):
    pass


def parse(text, labels):
    """'hold, drums fill, last hit on cue' -> the steps, in order:
    [('hold', None), ('fill', 'drums'), ('hit', 'cue')]. A player's
    step names the player: '<part> fill(s)', '<part> noodles' (or
    solos, plays over it, noodles over the last chord)."""
    steps = []
    low_labels = sorted(labels, key=len, reverse=True)
    for raw in re.split(r',|;|\bthen\b|\band then\b', text, flags=re.I):
        w = raw.strip().strip('.').strip()
        if not w:
            continue
        cue = bool(_CUE.search(w))
        w = _CUE.sub(' ', w).strip()
        if not w:
            if steps:
                steps[-1] = (steps[-1][0], 'cue')
            continue
        who = next((l for l in low_labels
                    if re.match(re.escape(l) + r'\b', w, re.I)), None)
        if who:
            rest = w[len(who):].strip().lower()
            if re.fullmatch(r'fills?(?: it| in| over it)?', rest):
                steps.append(('fill', who))
                continue
            if re.fullmatch(r'(?:noodles?|solos?|plays? over it|'
                            r'noodles? over (?:the |that )?(?:last )?'
                            r'chord|solos? over (?:the |that )?(?:last )?'
                            r'chord|plays? over (?:the |that )?(?:last )?'
                            r'chord|ad lib(?:s)?)', rest):
                steps.append(('noodle', who))
                continue
            if re.fullmatch(r'rolls?', rest):
                steps.append(('roll', who))
                continue
            raise EndingError(f"'{raw.strip()}': a player's step is "
                              f"'{who} fills' or '{who} noodles'")
        if re.fullmatch(r'fills?', w, re.I):
            steps.append(('fill', None))
            continue
        for kind, rx in _STEP_WORDS:
            if re.fullmatch(rx, w, re.I):
                steps.append((kind, 'cue' if cue else None))
                break
        else:
            raise EndingError(
                f"'{raw.strip()}' is not an ending step. The words: "
                "hold, roll, trash can, fill, <part> fills, <part> "
                "noodles, last hit (on cue), button, cold, rit, fade")
    if not steps:
        raise EndingError("the ending line names no steps")
    return steps


def shape(steps):
    """What the steps add up to."""
    kinds = [k for k, _ in steps]
    held = any(k in ('hold', 'roll', 'trash', 'fill', 'noodle')
               for k in kinds)
    hit = any(k in ('hit', 'button') for k in kinds) or 'trash' in kinds
    return {'held': held, 'hit': hit and 'stop' not in kinds,
            'stop': 'stop' in kinds, 'rit': 'rit' in kinds,
            'fade': 'fade' in kinds, 'trash': 'trash' in kinds,
            'roll': 'roll' in kinds,
            'fill': [w for k, w in steps if k == 'fill'],
            'noodle': [w for k, w in steps if k == 'noodle'],
            'hit_cue': any(k in ('hit', 'button') and a == 'cue'
                           for k, a in steps) or any(
                               k == 'trash' and a == 'cue'
                               for k, a in steps)}


def words(steps):
    """The steps as the page says them, over the last bar."""
    out = []
    for k, a in steps:
        if k in ('rit', 'fade'):
            continue                    # their own words, where they start
        w = {'hold': 'hold', 'roll': 'roll', 'trash': 'trash can ending',
             'stop': 'cold stop', 'button': 'button',
             'hit': 'last hit'}.get(k)
        if k == 'fill':
            w = f"{a or 'drums'} fill"
        elif k == 'noodle':
            w = f"{a} noodles over the chord"
        elif k == 'roll' and a:
            w = f"{a} roll"
        if a == 'cue' and k not in ('fill', 'noodle', 'roll'):
            w += ' on cue'
        out.append(w)
    return ', then '.join(out) if len(out) > 1 else (out[0] if out else '')


# ------------------------------------------------------------ the listen

_PITCH = re.compile(r'<pitch><step>([A-G])</step>(?:<alter>(-?\d+)</alter>)?'
                    r'<octave>(-?\d+)</octave></pitch>')
_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def written_last(measure):
    """The written pitches of a measure's last sounding onset (a chord
    counts whole), or [] when it only rests."""
    notes = re.findall(r'<note[ >].*?</note>', measure, re.S)
    group = []
    for n in notes:
        if '<rest' in n or '<cue/>' in n or '<grace' in n:
            if '<chord/>' not in n:
                group = [] if '<rest' in n else group
            continue
        m = _PITCH.search(re.sub(r'\s+', '', n))
        if not m:
            continue
        midi = (int(m.group(3)) + 1) * 12 + _PC[m.group(1)] + \
            int(m.group(2) or 0)
        if '<chord/>' in n:
            group.append(midi)
        else:
            group = [midi]
    return group


def plays(measure):
    return any('<rest' not in n for n in
               re.findall(r'<note[ >].*?</note>', measure, re.S))


def _voicing(role, sound_id, chord):
    """Sounding pitches for a realized chair's final chord."""
    root = G._root_pc(chord)
    if role == 'bass':
        return [G._near(root, 36)]
    guide = G._guide(chord)
    if role == 'comp':
        anchor = 57 if 'guitar' in sound_id else 62
        vs = sorted({G._near(pc, anchor) for pc in guide})
        if 'guitar' not in sound_id:
            vs = [G._near(root, 48)] + vs
        return vs
    return [G._near(guide[0], 65)]


def listen_bars(measure, role, sound_id, chord, meter, shift, fifths,
                staves, sh, label, is_written, seed):
    """The last measure's replacement and the bars after it, as measure
    BODIES (no <measure> wrapper): (last_body, [extra bodies]). None
    when the ending changes nothing for this part."""
    num, den = meter
    div = 24
    attrs_div = f'      <attributes><divisions>{div}</divisions>'
    named = label in sh['noodle'] or label in sh['fill']
    if not plays(measure) and named and chord and role not in (
            'drums', 'perc'):
        # the ending names this player: they come in for it, landing
        # on a note of the last chord
        pitches = [p + shift for p in _voicing(role, sound_id, chord)]
    elif not plays(measure) and named:
        pitches = []
    elif not plays(measure):
        pitches = None
    elif role in ('drums', 'perc'):
        pitches = []
    elif is_written:
        pitches = written_last(measure) or None
    else:
        pitches = [p + shift for p in _voicing(role, sound_id, chord)] \
            if chord else None

    def time_attr(n):
        return (f'{attrs_div}<time><beats>{n}</beats>'
                f'<beat-type>{den}</beat-type></time></attributes>\n')

    def hit_bar():
        bar = G.Bar(div, (num, den), fifths, staves)
        beat = div * 4 // den
        if role == 'drums':
            # an accent, not a jump scare: the mix is normalized
            # to its loudest moment, so a hit at full tilt would
            # turn the whole song down under it
            for d, v in ((G._CRASH, 100), (G._KICK, 96), (G._SNARE, 88)):
                bar.add(0, beat // 2, ('u', d, v))
        elif role == 'perc':
            bar.add(0, beat // 2, ('u', ('C', 5, 'normal'), 96))
        elif pitches:
            for p in pitches:
                bar.add(0, beat // 2, ('p', p, 100))
        return bar.xml() or _rest(div, num, den, staves)

    extras = []
    if sh['stop']:
        # a cold stop: the last bar is one hit on 1, then nothing
        if pitches is None and role not in ('drums', 'perc'):
            return None
        return attrs_div + '</attributes>\n' + hit_bar(), []
    if not sh['held']:
        if sh['hit'] and (pitches or role in ('drums', 'perc')):
            extras.append(hit_bar())
        elif sh['hit']:
            extras.append(_rest(div, num, den, staves))
        return (None, extras) if extras else None

    long_n = num * (1 + HOLD_BARS)
    bar = G.Bar(div, (long_n, den), fifths, staves)
    beat = div * 4 // den
    whole = bar.barlen
    fill_here = label in sh['fill'] or (role == 'drums' and None in
                                        sh['fill'])
    noodle_here = label in sh['noodle']
    if role == 'drums':
        bar.add(0, beat, ('u', G._CRASH, 112))
        bar.add(0, beat, ('u', G._KICK, 104))
        if sh['trash']:
            _trash_drums(bar, beat, seed)
        elif sh['roll']:
            _roll(bar, beat, 0, whole, G._SNARE, 50, 112)
        elif fill_here:
            _roll(bar, beat, beat, whole - 2 * num * beat, G._RIDE, 40,
                  60)
            _fill(bar, beat, whole - num * beat, whole, seed)
        elif sh['hit']:
            # a cymbal swell under the hold, into the cue
            _roll(bar, beat, 2 * beat, whole, G._RIDE, 36, 84)
    elif role == 'perc':
        bar.add(0, beat, ('u', ('C', 5, 'normal'), 104))
        if sh['trash'] or sh['roll']:
            _roll(bar, beat, beat, whole, ('C', 5, 'normal'), 50, 108)
    elif pitches is not None:
        if noodle_here and pitches:
            # the chord lands, then the player noodles over it
            for p in pitches:
                bar.add(0, beat, ('p', p, 96))
            nb = G.Bar(div, (long_n, den), fifths, staves)
            lo = min(pitches) - 2
            G.improvise(nb, {'sol_last': max(pitches)},
                        [(1.0, chord)] if chord else [], None, '',
                        lo, lo + 19, 9000, 1, 2, seed, mode='solo')
            for t, (ln, ns) in nb.onsets.items():
                if t >= beat:
                    for nn in ns:
                        bar.add(t, ln, ('p', nn[1], min(nn[2], 84)))
        elif sh['trash'] and pitches:
            _trash_pitched(bar, beat, pitches, role, whole)
        else:
            for p in pitches:
                bar.add(0, whole, ('p', p, 96))
    else:
        bar = None
    last_body = time_attr(long_n) + (bar.xml() if bar and bar.onsets
                                     else _rest(div, long_n, den, staves))
    if sh['hit']:
        extras.append(time_attr(num)
                      + (hit_bar() if pitches or role in ('drums', 'perc')
                         else _rest(div, num, den, staves)))
    return last_body, extras


def _rest(div, num, den, staves):
    bl = div * 4 * num // den
    body = ('      <note>\n        <rest measure="yes"/>\n'
            f'        <duration>{bl}</duration>\n'
            '        <voice>1</voice>\n      </note>\n')
    return body


def _roll(bar, beat, t0, t1, drum, v0, v1):
    """A roll: thirty-second strokes swelling from v0 to v1."""
    step = max(beat // 8, 1)
    span = max(t1 - t0, 1)
    for t in range(t0, t1, step):
        v = int(v0 + (v1 - v0) * ((t - t0) / span) ** 1.5)
        bar.add(t, step, ('u', drum, v))


def _fill(bar, beat, t0, t1, seed):
    """A drummer's fill down the kit into the cue."""
    d = G._Dice(seed, 'fill')
    toms = [G._SNARE, ('E', 5, 'normal'), ('D', 5, 'normal'),
            ('A', 4, 'normal')]
    step = beat // 4
    span = max(t1 - t0, 1)
    for t in range(t0, t1, step):
        x = (t - t0) / span
        drum = toms[min(int(x * 4), 3)]
        if d() < 0.15:
            continue
        bar.add(t, step, ('u', drum, int(70 + 45 * x)))
        if (t - t0) % beat == 0:
            bar.add(t, step, ('u', G._KICK, 80))


def _trash_drums(bar, beat, seed):
    """The trash can: everything, loud, all over the kit, crashes on
    the way, until the cue."""
    d = G._Dice(seed, 'trash')
    kit = [G._SNARE, ('E', 5, 'normal'), ('D', 5, 'normal'),
           ('A', 4, 'normal'), G._CRASH]
    step = beat // 4
    for t in range(beat, bar.barlen, step):
        r = d()
        if r < 0.1:
            continue
        drum = kit[int(d() * len(kit)) % len(kit)]
        bar.add(t, step, ('u', drum, int(84 + 30 * d())))
        if r > 0.8:
            bar.add(t, step, ('u', G._KICK, 96))
    for t in range(0, bar.barlen, 2 * beat):
        bar.add(t, beat, ('u', G._CRASH, 104))


def _trash_pitched(bar, beat, pitches, role, whole):
    """Over a trash can the band doesn't sit still: keys tremolo the
    chord, the bass shakes the root, a horn shakes its note."""
    step = beat // 4
    lo, hi = min(pitches), max(pitches)
    bar_on = sorted(pitches)
    for t in range(0, whole, step):
        k = (t // step) % 2
        if role == 'comp':
            group = bar_on[k::2] or bar_on
        elif role == 'bass':
            group = [lo if k == 0 else lo + 7]
        else:
            group = [p + (2 if k else 0) for p in pitches]
        v = int(80 + 30 * t / whole)
        for p in group:
            bar.add(t, step, ('p', p, v))
