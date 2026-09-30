#!/usr/bin/env python3
"""chartending — how the tune ends, on the page and in the listen.

A chart's last section can say how the band gets off the stage, in the
words a leader uses (Matthew, 2026-09-29):

    ending: hold, drums fill, last hit on cue
    ending: rit, hold, horns fall
    ending: hold, watch each other
    ending: trash can, drums tag
    ending: cold
    ending: button, drums tag "floor tom, floor tom, bass drum"

Steps run in order. The pages print them in words over the last bar of
every part that plays there, with a fermata when the band holds; the
listen performs them.

How it should feel, in his words: "ending should feel natural ... not
quantized ... not every ending needs a last hit ... it should feel
different every time, depending on what's in the roadmap ... a drum
fill doesn't need to happen every time ... everyone could watch each
other." So:

- Only what the roadmap says happens. A hold with no hit rings and the
  band lets go of it together, loosely; nobody adds a hit or a fill.
- Nothing lands on the grid. The hold lasts as long as it feels, a
  little different in every tune; each player lands and lets go a hair
  apart; "watch each other" (or "watch me") tightens that, the way a
  band locked on the leader does. The cue comes after a breath.
- Where the roadmap leaves the drummer free, the drummer chooses
  quietly: nothing, or a soft cymbal swell, and the choice changes
  from tune to tune.
- A fall, doit, scoop or plop can ride the last note: "horns fall",
  "trumpet doit", "everyone falls".
- The drummer can tag it after the very last note: "drums tag" is a
  little something of the drummer's own; spelled out, it is what it
  says.

"Different every time" is from the tune, not a dice roll: the choices
come from the chart's own title and section, so a rebuild sounds the
same and another tune ends its own way. The listening document is not
the page, so the ending can carry bars the page does not.
"""
import re

import chartgroove as G

DIV = 96               # finer than the grid: the ending is played, not placed

_STEP_WORDS = [
    ('trash', r'trash\s*-?\s*can(?: ending)?|big (?:rock )?ending|'
              r'crash ending'),
    ('roll', r'(?:drum |cymbal |snare )?roll'),
    ('stop', r'cold(?: ending)?|dead stop|stop(?: dead)?'),
    ('rit', r'rit\.?|ritard(?:ando)?|rall\.?|slow(?:ing)? down|'
            r'broaden|molto rit\.?'),
    ('fade', r'fade(?: out)?|fade to nothing'),
    ('hold', r'hold(?: it| the (?:last )?chord| out)?|fermata|'
             r'let (?:it )?ring|ring out'),
    ('button', r'button|stinger'),
    ('hit', r'(?:the )?(?:last |final )?(?:hit|cut ?off|cut it off)'),
    ('asis', r'as written|none|no ending|just stop|nothing|'
             r'play it as written'),
    ('watch', r'watch(?: each other| me| the leader| the conductor|'
              r' for (?:the )?cue)?|eyes up|look up'),
]
_ARTS = {'fall': 'falloff', 'falls': 'falloff', 'fall off': 'falloff',
         'falls off': 'falloff', 'doit': 'doit', 'doits': 'doit',
         'scoop': 'scoop', 'scoops': 'scoop', 'plop': 'plop',
         'plops': 'plop'}
_CUE = re.compile(r'\s*(?:on (?:my |the |a )?(?:cue|nod|signal)|'
                  r'on cue|when cued|cued)\s*', re.I)
_EVERYONE = ('everyone', 'everybody', 'all', 'the band', 'band', 'tutti')

# a drummer's tag, piece by piece: staff position and notehead
_KIT = {
    'floor tom': ('A', 4, 'normal'), 'low tom': ('A', 4, 'normal'),
    'mid tom': ('D', 5, 'normal'), 'tom': ('D', 5, 'normal'),
    'rack tom': ('D', 5, 'normal'), 'high tom': ('E', 5, 'normal'),
    'snare': ('C', 5, 'normal'), 'rim': ('C', 5, 'x'),
    'rimshot': ('C', 5, 'x'), 'cross stick': ('C', 5, 'x'),
    'bass drum': ('F', 4, 'normal'), 'kick': ('F', 4, 'normal'),
    'crash': ('A', 5, 'x'), 'ride': ('F', 5, 'x'),
    'ride bell': ('F', 5, 'diamond'), 'bell': ('F', 5, 'diamond'),
    'hat': ('G', 5, 'x'), 'hi-hat': ('G', 5, 'x'),
    'hi hat': ('G', 5, 'x'), 'china': ('A', 5, 'x'),
    'splash': ('A', 5, 'x'),
}
_TAGS = [['floor tom', 'floor tom', 'bass drum'],
         ['snare', 'bass drum'],
         ['high tom', 'floor tom', 'bass drum'],
         ['rim', 'floor tom'],
         ['floor tom', 'bass drum', 'crash']]


class EndingError(Exception):
    pass


def _split(text):
    """Commas and 'then' part the steps, never inside quotes."""
    parts, cur, q = [], '', False
    for ch in text:
        if ch == '"':
            q = not q
        if not q and ch in ',;':
            parts.append(cur)
            cur = ''
            continue
        cur += ch
    parts.append(cur)
    out = []
    for p in parts:
        if '"' in p:
            out.append(p)
        else:
            out += re.split(r'\bthen\b|\band then\b', p, flags=re.I)
    return out


def tag_pieces(spec):
    """'floor tom, floor tom, bass drum' -> the kit pieces, in order."""
    got = []
    for w in re.split(r',|\band\b|\bthen\b', spec):
        w = w.strip().lower()
        if not w:
            continue
        if w not in _KIT and w.endswith('s') and w[:-1] in _KIT:
            w = w[:-1]
        if w not in _KIT:
            raise EndingError(f"'{w}' is not a drum I know for a tag: "
                              + ", ".join(sorted(_KIT)))
        got.append(w)
    return got


def parse(text, labels, groups=None):
    """'hold, drums fill, last hit on cue' -> the steps, in order:
    [('hold', None), ('fill', 'drums'), ('hit', 'cue')]. A player's
    step names the player: '<part> fills', '<part> noodles', '<part>
    falls' (a group or 'everyone' too), 'drums tag "..."'."""
    groups = groups or {}
    names = sorted(list(labels) + [g for g in groups if groups[g]]
                   + list(_EVERYONE), key=len, reverse=True)
    steps = []
    for raw in _split(text):
        w = raw.strip().strip('.').strip()
        if not w:
            continue
        cue = bool(_CUE.search(w))
        w = _CUE.sub(' ', w).strip()
        if not w:
            if steps:
                steps[-1] = (steps[-1][0], 'cue')
            continue
        who = next((n for n in names
                    if re.match(re.escape(n) + r'\b', w, re.I)), None)
        rest = w[len(who):].strip() if who else w
        low = rest.lower()
        if who and low in _ARTS:
            steps.append(('art', (who, _ARTS[low])))
            continue
        if not who and w.lower() in _ARTS:
            steps.append(('art', ('horns', _ARTS[w.lower()])))
            continue
        if who and who.lower() not in _EVERYONE:
            m = re.fullmatch(r'tag(?:\s+"([^"]*)")?|tags? it', low)
            if m:
                pieces = tag_pieces(m.group(1)) if m.group(1) else None
                steps.append(('tag', (who, pieces)))
                continue
            if re.fullmatch(r'fills?(?: it| in| over it)?', low):
                steps.append(('fill', who))
                continue
            if re.fullmatch(r'(?:noodles?|solos?|plays? over it|'
                            r'(?:noodles?|solos?|plays?) over (?:the |that )?'
                            r'(?:last )?chord|ad lib(?:s)?)', low):
                steps.append(('noodle', who))
                continue
            if re.fullmatch(r'rolls?', low):
                steps.append(('roll', who))
                continue
            if re.fullmatch(r'gliss(?:es|andos?)?(?: up)?', low):
                steps.append(('gliss', who))
                continue
            raise EndingError(f"'{raw.strip()}': a player's step is "
                              f"'{who} fills', '{who} noodles', "
                              f"'{who} falls' or '{who} tag'")
        m = re.fullmatch(r'tag(?:\s+"([^"]*)")?', w, re.I)
        if m:
            steps.append(('tag', ('drums', tag_pieces(m.group(1))
                                  if m.group(1) else None)))
            continue
        if re.fullmatch(r'fills?', w, re.I):
            steps.append(('fill', None))
            continue
        if re.fullmatch(r'gliss(?:es|andos?)?(?: up)?', w, re.I):
            steps.append(('gliss', None))
            continue
        if re.fullmatch(r"(?:the )?band'?s choice|in the moment|"
                        r"(?:we'?ll |let'?s )?see what happens|"
                        r"play it by ear|free", w, re.I):
            steps.append(('choice', None))
            continue
        for kind, rx in _STEP_WORDS:
            if re.fullmatch(rx, w, re.I):
                if kind == 'watch':
                    steps.append((kind, w.lower()))
                else:
                    steps.append((kind, 'cue' if cue else None))
                break
        else:
            raise EndingError(
                f"'{raw.strip()}' is not an ending step. The words: "
                "hold, roll, trash can, fill, <part> fills, <part> "
                "noodles, <part> falls (or doits, scoops, plops), last "
                "hit (on cue), button, cold, rit, fade, watch each "
                "other, drums tag")
    if not steps:
        raise EndingError("the ending line names no steps")
    return steps


def shape(steps, labels=(), groups=None):
    """What the steps add up to."""
    groups = groups or {}
    kinds = [k for k, _ in steps]
    held = any(k in ('hold', 'roll', 'trash', 'fill', 'noodle', 'gliss')
               for k in kinds)
    hit = any(k in ('hit', 'button') for k in kinds) or 'trash' in kinds
    arts = {}
    for k, a in steps:
        if k != 'art':
            continue
        who, art = a
        if who.lower() in _EVERYONE:
            members = list(labels)
        else:
            members = groups.get(who) or [who]
        for m in members:
            arts[m] = art
    tag = next((a for k, a in steps if k == 'tag'), None)
    return {'held': held, 'hit': hit and 'stop' not in kinds,
            'stop': 'stop' in kinds, 'rit': 'rit' in kinds,
            'fade': 'fade' in kinds, 'trash': 'trash' in kinds,
            'roll': 'roll' in kinds, 'watch': 'watch' in kinds,
            'fill': [w for k, w in steps if k == 'fill'],
            'noodle': [w for k, w in steps if k == 'noodle'],
            'gliss': [w for k, w in steps if k == 'gliss'],
            'arts': arts, 'tag': tag,
            'hit_cue': any(k in ('hit', 'button', 'trash') and a == 'cue'
                           for k, a in steps)}


def words(steps):
    """The steps as the page says them, over the last bar."""
    out = []
    for k, a in steps:
        if k in ('rit', 'fade'):
            continue                    # their own words, where they start
        w = {'hold': 'hold', 'roll': 'roll', 'trash': 'trash can ending',
             'asis': 'as written',
             'stop': 'cold stop', 'button': 'button',
             'hit': 'last hit'}.get(k)
        if k == 'fill':
            w = f"{a or 'drums'} fill"
        elif k == 'noodle':
            w = f"{a} noodles over the chord"
        elif k == 'gliss':
            w = f"{a or 'keys'} gliss"
        elif k == 'choice':
            w = "band's choice"
        elif k == 'roll' and a:
            w = f"{a} roll"
        elif k == 'watch':
            w = a if a and a not in ('watch', 'cue') else 'watch each other'
        elif k == 'art':
            who, art = a
            w = f"{who} " + {'falloff': 'fall', 'doit': 'doit',
                             'scoop': 'scoop', 'plop': 'plop'}[art]
        elif k == 'tag':
            who, pieces = a
            w = f"{who} tag" + (f" ({', '.join(pieces)})" if pieces
                                else '')
        if a == 'cue' and k in ('hit', 'button', 'trash', 'hold', 'stop'):
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
            if '<chord/>' not in n and '<rest' in n:
                group = []
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


def timing(sh, meter, song):
    """The ending's shared clock, in DIV ticks, from the tune itself:
    how long the band holds, when the cue comes. Every part reads the
    same numbers, so the parts stay together."""
    num, den = meter
    beat = DIV * 4 // den
    d = G._Dice(song, 'ending')
    hold = num * (1.3 + 1.2 * d())              # beats past the last bar
    if sh['fill'] or sh['noodle']:
        hold += num * (0.5 + 0.5 * d())
    if sh['trash']:
        hold += num * 0.5
    total = int(round((num + hold) * 4)) * beat // 4   # to a sixteenth
    return {'beat': beat, 'len': total,
            'breath': int(beat * (0.2 + 0.35 * d())),
            'drummer': d(), 'fill_len': int(beat * (1.5 + 1.5 * d()))}


def listen_bars(measure, role, sound_id, chord, meter, shift, fifths,
                staves, sh, label, is_written, seed, song=''):
    """The last measure's replacement and the bars after it, as measure
    BODIES (no <measure> wrapper): (last_body or None, [extra bodies]).
    None when the ending changes nothing for this part. Every part gets
    the same number of extra bars, so the parts stay lined up."""
    num, den = meter
    clock = timing(sh, meter, song)
    beat = clock['beat']
    me = G._Dice(song, label, 'player')
    # a hair apart: each player lands and lets go on their own; watching
    # each other pulls it in
    spread = 0.25 if sh['watch'] else 1.0

    def late(scale):
        return int(round(me() * scale * spread))

    gl = sh.get('gliss', [])
    glissing = label in gl or (None in gl and role == 'comp'
                               and 'guitar' not in sound_id
                               and label == sh.get('keys'))
    named = label in sh['noodle'] or label in sh['fill'] or glissing
    if not plays(measure) and named and chord and role not in (
            'drums', 'perc'):
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
    art = sh['arts'].get(label)
    arts = (art,) if art and pitches and role not in ('drums', 'perc') \
        else ()
    drums = role == 'drums'
    hitting = pitches is not None or drums or role == 'perc'

    def n16(ticks):
        return max(1, int(round(ticks * 4 / beat)))

    def attrs(ticks):
        return (f'      <attributes><divisions>{DIV}</divisions>'
                f'<time><beats>{n16(ticks)}</beats><beat-type>16'
                '</beat-type></time></attributes>\n')

    def bar_of(ticks):
        return G.Bar(DIV, (n16(ticks), 16), fifths, staves)

    def rest(ticks):
        ticks = n16(ticks) * beat // 4
        return ('      <note>\n        <rest measure="yes"/>\n'
                f'        <duration>{ticks}</duration>\n'
                '        <voice>1</voice>\n      </note>\n')

    def hit_body(length):
        b = bar_of(length)
        at = late(beat * 0.12)
        short = beat // 2
        if drums:
            for dr, v in ((G._CRASH, 100), (G._KICK, 94), (G._SNARE, 86)):
                b.add(at, short, ('u', dr, v))
        elif role == 'perc':
            b.add(at, short, ('u', ('C', 5, 'normal'), 94))
        elif pitches:
            for p in pitches:
                b.add(at, short, ('p', p, 98, arts))
        return b.xml() or rest(b.barlen)

    extras = []
    last = None
    if sh['stop']:
        if hitting:
            last = attrs(num * beat) + hit_body(num * beat)
    elif sh['held']:
        b = bar_of(clock['len'])
        L = b.barlen
        land = late(beat * 0.08)
        let_go = L - late(beat * 0.45)              # no hit: loose release
        if sh['hit']:
            let_go = L - clock['breath'] - late(beat * 0.1)
        fill_here = label in sh['fill'] or (drums and None in sh['fill'])
        if drums:
            b.add(land, beat, ('u', G._CRASH, 104))
            b.add(land, beat, ('u', G._KICK, 96))
            if sh['trash']:
                _trash_drums(b, beat, seed, let_go)
            elif sh['roll']:
                _roll(b, beat, beat // 2, let_go, G._SNARE, 48, 110)
            elif fill_here:
                _fill(b, beat, let_go - clock['fill_len'], let_go, seed)
            elif clock['drummer'] > 0.45:
                # left free, the drummer chooses: here a soft swell on
                # the cymbal, into the cue when there is one
                top = 88 if sh['hit'] else 62
                _roll(b, beat, int(L * 0.35), let_go, G._RIDE, 30, top)
        elif role == 'perc':
            b.add(land, beat, ('u', ('C', 5, 'normal'), 100))
            if sh['trash'] or sh['roll']:
                _roll(b, beat, beat, let_go, ('C', 5, 'normal'), 48, 104)
        elif pitches:
            if label in sh['noodle']:
                for p in pitches:
                    b.add(land, beat, ('p', p, 94))
                nb = bar_of(L)
                lo = min(pitches) - 2
                G.improvise(nb, {'sol_last': max(pitches)},
                            [(1.0, chord)] if chord else [], None, '',
                            lo, lo + 19, 9000, 1, 2, seed, mode='solo')
                for t, (ln, ns) in sorted(nb.onsets.items()):
                    if beat <= t < let_go:
                        for nn in ns:
                            b.add(t + late(beat * 0.08),
                                  min(ln, let_go - t),
                                  ('p', nn[1], min(nn[2], 82)))
            elif sh['trash']:
                _trash_pitched(b, beat, pitches, role, let_go)
            else:
                for p in pitches:
                    b.add(land, let_go - land, ('p', p, 94, arts))
            if glissing:
                _gliss(b, beat, land, pitches, me, let_go)
        last = attrs(L) + (b.xml() if b.onsets else rest(L))
        if sh['hit']:
            extras.append(attrs(2 * beat) + (hit_body(2 * beat) if hitting
                                             else rest(2 * beat)))
    elif sh['hit']:
        # a button: one short hit straight after the last bar
        extras.append(attrs(2 * beat) + (hit_body(2 * beat) if hitting
                                         else rest(2 * beat)))
    elif arts and pitches:
        # no hold, no hit: the last note carries the fall or doit
        b = bar_of(num * beat)
        for p in pitches:
            b.add(late(beat * 0.05), num * beat - beat // 2,
                  ('p', p, 92, arts))
        last = attrs(num * beat) + b.xml()
    if sh['tag']:
        who, pieces = sh['tag']
        length = 3 * beat
        if label == who or (drums and who.lower() in ('drums', 'drummer',
                                                      'kit')):
            extras.append(attrs(length) + _tag(bar_of(length), beat,
                                               pieces, song))
        else:
            extras.append(attrs(length) + rest(length))
    if last is None and not extras:
        return None
    return last, extras


def _roll(bar, beat, t0, t1, drum, v0, v1):
    """A roll: thirty-second strokes swelling from v0 to v1."""
    step = max(beat // 8, 1)
    span = max(t1 - t0, 1)
    for t in range(max(t0, 0), t1, step):
        v = int(v0 + (v1 - v0) * ((t - t0) / span) ** 1.5)
        bar.add(t, step, ('u', drum, v))


def _fill(bar, beat, t0, t1, seed):
    """A drummer's fill down the kit into the cue, pushing a little as
    it goes, never quite on the grid."""
    d = G._Dice(seed, 'fill')
    toms = [G._SNARE, ('E', 5, 'normal'), ('D', 5, 'normal'),
            ('A', 4, 'normal')]
    span = max(t1 - t0, 1)
    t = float(max(t0, 0))
    gap = beat / 4
    while t < t1:
        x = (t - t0) / span
        if d() > 0.12:
            drum = toms[min(int(x * 4), 3)]
            bar.add(int(t), int(gap), ('u', drum, int(68 + 44 * x)))
            if int(t - t0) % beat < gap and d() < 0.6:
                bar.add(int(t), int(gap), ('u', G._KICK, 80))
        t += gap * (1.0 - 0.18 * x) + (d() - 0.5) * gap * 0.15


def _trash_drums(bar, beat, seed, t1):
    """The trash can: everything, loud, all over the kit, crashes on
    the way, until the cue."""
    d = G._Dice(seed, 'trash')
    kit = [G._SNARE, ('E', 5, 'normal'), ('D', 5, 'normal'),
           ('A', 4, 'normal'), G._CRASH]
    t = float(beat)
    while t < t1:
        r = d()
        if r > 0.1:
            drum = kit[int(d() * len(kit)) % len(kit)]
            bar.add(int(t), beat // 4, ('u', drum, int(84 + 30 * d())))
            if r > 0.8:
                bar.add(int(t), beat // 4, ('u', G._KICK, 96))
        t += beat / 4 * (0.7 + 0.6 * d())
    for k in range(0, t1, 2 * beat):
        bar.add(k + int(d() * beat / 3), beat, ('u', G._CRASH, 102))


def _trash_pitched(bar, beat, pitches, role, t1):
    """Over a trash can the band doesn't sit still: keys tremolo the
    chord, the bass shakes the root, a horn shakes its note."""
    step = beat // 4
    lo = min(pitches)
    bar_on = sorted(pitches)
    for t in range(0, t1, step):
        k = (t // step) % 2
        if role == 'comp':
            group = bar_on[k::2] or bar_on
        elif role == 'bass':
            group = [lo if k == 0 else lo + 7]
        else:
            group = [p + (2 if k else 0) for p in pitches]
        v = int(78 + 28 * t / max(t1, 1))
        for p in group:
            bar.add(t, step, ('p', p, v))


def _gliss(bar, beat, land, pitches, me, t1):
    """A keyboard gliss off the landed chord: the palm up the white
    keys, two octaves-ish in well under a beat, loosening at the top."""
    white = (0, 2, 4, 5, 7, 9, 11)
    lo = min(pitches) - 5
    hi = max(pitches) + 14
    keys = [m for m in range(lo, hi + 1) if m % 12 in white]
    t = land + beat * (0.2 + 0.3 * me())
    span = beat * (0.45 + 0.35 * me())
    step = span / max(len(keys), 1)
    for i, m in enumerate(keys):
        at = int(t + i * step * (1 + 0.4 * i / len(keys)))
        if at >= t1:
            break
        bar.add(at, max(int(step * 2), 2),
                ('p', m, int(60 + 30 * i / len(keys))))


def band_choice(feel, song, has_keys, has_horns):
    """The roadmap says nothing about the ending (or says 'band's
    choice'): the band decides in the moment, the way a group does,
    from the feel, a different call in every tune. Returns steps."""
    import chartgroove as _G
    d = G._Dice(song, 'choice')
    style, traits = _G.style_of(feel or '')
    r = d()
    if 'ballad' in traits or 'ballad' in (feel or '').lower():
        steps = [('rit', None), ('hold', None)]
    elif not (feel or '').strip():
        # no feel written: the ending any band would reach for — land
        # and hold, maybe a hit — never a funk band's stop
        steps = [('hold', None)] if r < 0.55 else \
            [('hold', None), ('hit', 'cue')]
    elif style in ('funk', 'latin', 'samba', 'straight', 'motown',
                   'hiphop', 'reggae', 'secondline'):
        steps = ([('stop', None)] if r < 0.5 else
                 [('hold', None), ('hit', 'cue')] if r < 0.8 else
                 [('hold', None)])
    elif style == 'waltz':
        steps = [('hold', None)]
    else:
        steps = ([('hold', None)] if r < 0.5 else
                 [('hold', None), ('hit', 'cue')] if r < 0.8 else
                 [('button', None)])
    held = any(k == 'hold' for k, _ in steps)
    hit = any(k in ('hit', 'button', 'stop') for k, _ in steps)
    if held and has_keys and d() < 0.4:
        steps.append(('gliss', None))
    if hit and d() < 0.3:
        steps.append(('tag', ('drums', None)))
    return steps


def _tag(bar, beat, pieces, song):
    """The drummer's little thing after everyone's last note: a breath,
    then the pieces, loose, the last one landing hardest."""
    d = G._Dice(song, 'tag')
    if not pieces:
        pieces = _TAGS[int(d() * len(_TAGS)) % len(_TAGS)]
    t = beat * (0.35 + 0.3 * d())
    n = len(pieces)
    for i, p in enumerate(pieces):
        vel = 82 + int(22 * (i + 1) / n) + int((d() - 0.5) * 8)
        bar.add(int(t), beat // 2, ('u', _KIT[p], vel))
        # the gaps swing a little and stretch toward the last hit
        t += beat * (0.32 + 0.12 * d() + (0.15 if i == n - 2 else 0))
    return bar.xml()
