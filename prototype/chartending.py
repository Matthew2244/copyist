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
    ('hitheld', r'(?:the )?(?:last |final )?hit,? (?:and )?(?:hold(?: it)?|'
                r'held|let (?:it )?ring|ring)|(?:the )?(?:last |final )?'
                r'hit with a fermata|held (?:last |final )?hit'),
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
    'open hat': ('G', 5, 'circle-x'), 'open hi-hat': ('G', 5, 'circle-x'),
    'open hi hat': ('G', 5, 'circle-x'),
    'hat foot': ('D', 4, 'x'), 'hi-hat foot': ('D', 4, 'x'),
    'hi hat foot': ('D', 4, 'x'), 'foot': ('D', 4, 'x'),
    'pedal': ('D', 4, 'x'),
}
# the Max Roach ending, the drummer's last say: short, always landing
# on the kick; a '+' is strokes together (Matthew, 2026-09-30: "open hat
# with snare, hihat foot then kick, or anything")
_TAGS = [['floor tom', 'floor tom', 'bass drum'],
         ['snare', 'bass drum'],
         ['high tom', 'floor tom', 'bass drum'],
         ['rim', 'floor tom', 'bass drum'],
         ['snare', 'floor tom', 'bass drum'],
         ['floor tom', 'bass drum'],
         ['open hat+snare', 'hat foot', 'bass drum'],
         ['snare', 'snare', 'bass drum'],
         ['snare', 'high tom', 'floor tom', 'bass drum'],
         ['crash+snare', 'bass drum'],
         ['floor tom+snare', 'bass drum'],
         ['open hat+bass drum', 'hat foot', 'snare', 'bass drum'],
         ['rim', 'rim', 'bass drum'],
         ['high tom', 'mid tom', 'floor tom', 'bass drum'],
         ['ride bell', 'bass drum'],
         ['snare', 'hat foot', 'bass drum'],
         ['open hat+snare', 'floor tom', 'bass drum'],
         ['snare+high tom', 'floor tom+snare', 'bass drum']]


def band_tag(d):
    """The drummer's own tag, never the same twice: one to three
    pieces around the kit, always landing on the kick (Matthew,
    2026-09-30: "whatever combo with floor tom and kick, or snare and
    kick ... as long as it ends on the kick")."""
    if d() < 0.45:
        return list(_TAGS[int(d() * len(_TAGS)) % len(_TAGS)])
    pool = ['floor tom', 'snare', 'high tom', 'floor tom', 'mid tom', 'rim',
            'open hat+snare', 'hat foot', 'crash+snare', 'ride bell',
            'floor tom+snare']
    n = 1 + int(d() * 3)
    return [pool[int(d() * len(pool)) % len(pool)] for _ in range(n)] + \
        ['bass drum']


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
        together = []
        # "open hat with snare", "crash + kick": strokes landing together
        for x in re.split(r'\s*(?:\+|\bwith\b)\s*', w):
            x = x.strip()
            if not x:
                continue
            if x not in _KIT and x.endswith('s') and x[:-1] in _KIT:
                x = x[:-1]
            if x not in _KIT:
                raise EndingError(f"'{x}' is not a drum I know for a "
                                  "tag: " + ", ".join(sorted(_KIT)))
            together.append(x)
        got.append('+'.join(together))
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
            if who.lower() in ('drums', 'drum', 'drummer', 'kit') and \
                    re.fullmatch(r"(?:solos?|takes? a solo|plays? alone)"
                                 r"(?: out of time)?", low):
                # the drummer alone, out of time, then the cue
                steps.append(('drumsolo', None))
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
            if re.fullmatch(r'cadenzas?(?: alone)?|plays? alone|'
                            r'alone', low):
                steps.append(('cadenza', who))
                continue
            m = re.fullmatch(r'dictates?(?:\s+"([^"]*)")?|'
                             r'dictated?(?:\s+"([^"]*)")?', rest, re.I)
            if m:
                steps.append(('dictate', (who, m.group(1) or m.group(2))))
                continue
            raise EndingError(f"'{raw.strip()}': a player's step is "
                              f"'{who} fills', '{who} noodles', "
                              f"'{who} falls' or '{who} tag'")
        if re.fullmatch(r"(?:the |a )?(?:max roach(?: ending)?|drummer'?s "
                        r"last say|last say)", w, re.I):
            # the drummer's own last word after everyone's done, always
            # landing on the kick (Matthew's name for it, 2026-09-30)
            steps.append(('tag', ('drums', None)))
            continue
        if re.fullmatch(r"(?:a |the )?(?:drum|drummer'?s|drums) solo"
                        r"(?: out of time)?", w, re.I):
            steps.append(('drumsolo', None))
            continue
        if re.fullmatch(r"(?:(?:everybody|everyone|the band|band|all) )?"
                        r"(?:go(?:es)? crazy|go(?:es)? for it|blows?|"
                        r"wails?)|"
                        r"crazy", w, re.I):
            # the held chord, everybody going for it
            steps.append(('crazy', None))
            continue
        if re.fullmatch(r'(?:a |the )?(?:(?:band )?unison(?: figure| hits?| '
                        r'line| lick)?|band figure|unison band figure)', w,
                        re.I):
            steps.append(('unison', None))
            continue
        if re.fullmatch(r'(?:a |the )?cadenza(?: alone)?', w, re.I):
            steps.append(('cadenza', 'lead'))     # the lead voice's
            continue
        m = re.fullmatch(r'(?:the )?(?:drums?|drummer|kit) dictates?'
                         r'(?:\s+"([^"]*)")?', w, re.I)
        if m:
            # said with no drum chair on the bandstand: the compiler says
            # what's missing
            steps.append(('dictate', ('drums', m.group(1))))
            continue
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
        if re.fullmatch(r'count(?:s)?(?: (?:it|us|the band))? (?:back )?in'
                        r'(?: with (?:the |me|conductor|the conductor)'
                        r'(?:\s*conductor)?)?', w, re.I):
            steps.append(('count', None))
            continue
        if re.fullmatch(r"(?:the )?band'?s choice|in the moment|"
                        r"(?:we'?ll |let'?s )?see what happens|"
                        r"play it by ear|free", w, re.I):
            steps.append(('choice', None))
            continue
        for kind, rx in _STEP_WORDS:
            if re.fullmatch(rx, w, re.I):
                if kind == 'hitheld':
                    steps.append(('hit', 'held'))
                elif kind == 'hold' and steps and steps[-1][0] == 'hit':
                    # 'last hit, hold it': the hit itself rings
                    steps[-1] = ('hit', 'held')
                elif kind == 'watch':
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
                "other, drums tag, drums dictate \"chords\", count in, "
                "unison line, drum solo, go crazy")
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
    dictate = next((a for k, a in steps if k == 'dictate'), None)
    cadenza = next((a for k, a in steps if k == 'cadenza'), None)
    ki = [k for k, _ in steps]
    # a fill named after the cadenza is the drummer bringing the band
    # back in, alone, before the hit
    fill_after = cadenza is not None and 'fill' in ki and \
        ki.index('fill') > ki.index('cadenza')
    if dictate:
        hit = True                   # the band comes back in on a hit
    later = [ki.index(k) for k in ('hold', 'crazy', 'drumsolo', 'roll',
                                   'trash') if k in ki]
    unison_first = 'unison' in ki and (not later or
                                       ki.index('unison') < min(later))
    sequence = not dictate and ('drumsolo' in ki or (
        unison_first and ('crazy' in ki or 'hold' in ki)))
    if sequence:
        hit = True
    return {'held': held, 'hit': hit and 'stop' not in kinds,
            'stop': 'stop' in kinds, 'rit': 'rit' in kinds,
            'fade': 'fade' in kinds, 'trash': 'trash' in kinds,
            'roll': 'roll' in kinds, 'watch': 'watch' in kinds,
            'fill': [w for k, w in steps if k == 'fill'],
            'noodle': [w for k, w in steps if k == 'noodle'],
            'gliss': [w for k, w in steps if k == 'gliss'],
            'arts': arts, 'tag': tag, 'dictate': dictate,
            'cadenza': cadenza, 'fill_after': fill_after,
            'count': 'count' in kinds, 'unison': 'unison' in kinds,
            'sequence': sequence, 'unison_first': unison_first,
            'drumsolo': 'drumsolo' in kinds, 'crazy': 'crazy' in kinds,
            'hit_cue': any(k in ('hit', 'button', 'trash') and a == 'cue'
                           for k, a in steps),
            'hit_held': any(k == 'hit' and a == 'held' for k, a in steps)}


def words(steps):
    """The steps as the page says them, over the last bar."""
    out = []
    for k, a in steps:
        if k in ('rit', 'fade'):
            continue                    # their own words, where they start
        w = {'hold': 'hold', 'roll': 'roll', 'trash': 'trash can ending',
             'drumsolo': 'drum solo, out of time', 'crazy': 'go for it',
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
        elif k == 'dictate':
            who, chs = a
            w = f"{who} dictate" + (f" ({chs})" if chs else
                                    " the band chords")
        elif k == 'cadenza':
            w = "cadenza alone" if a == 'lead' else f"{a} cadenza alone"
        elif k == 'count':
            w = "count in"
        elif k == 'unison':
            w = "unison figure"
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
            w = (f"{who} tag ({', '.join(pieces)})" if pieces else
                 "drummer's last say" if who.lower() in ('drums', 'drummer',
                                                         'kit')
                 else f"{who} tag")
        if k == 'hit' and a == 'held':
            w = 'last hit, held'
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
    if role == 'comp' and sound_id.startswith('pitched-percussion'):
        # four mallets up the middle of the bars, no pianist's left hand
        # (a vibraphone's floor is F3)
        return sorted({max(G._near(pc, 67), 53 + (pc - 53) % 12)
                       for pc in guide})
    if role == 'comp':
        anchor = 57 if 'guitar' in sound_id else 62
        vs = sorted({G._near(pc, anchor) for pc in guide})
        if 'guitar' not in sound_id:
            vs = [G._near(root, 48)] + vs
        return vs
    return [G._near(guide[0], 65)]


_FIG_CELLS = (                 # half-bar rhythm cells, (beat, length)
    ((0, 0.5), (0.5, 0.5), (1.5, 0.5)),
    ((0, 1.0), (1.5, 0.5)),
    ((0.5, 0.5), (1.0, 0.5), (1.5, 0.5)),
    ((0, 0.5), (1.0, 0.5), (1.5, 0.5)),
    ((0, 0.5), (0.5, 1.0)),
    ((0.5, 0.5), (1.5, 0.5)),
)


def unison_figure(song, chord, num):
    """The band's unison figure after a count-off, the same for every
    part: two bars of big band kicks on a line in the key, each note
    [(beat, length, semitones over the last chord's root)], ending on a
    short push into the hit."""
    d = G._Dice(song, 'unison')
    sc = sorted(G._scale(chord)) if chord else [0, 2, 4, 5, 7, 9, 11]
    cells = []
    last = None
    for h in range(2 * num // 2):
        c = _FIG_CELLS[int(d() * len(_FIG_CELLS)) % len(_FIG_CELLS)]
        if c == last:
            c = _FIG_CELLS[(_FIG_CELLS.index(c) + 1) % len(_FIG_CELLS)]
        last = c
        cells += [(h * 2 + a_, ln) for a_, ln in c]
    # the last note a push on the 'and' before the hit
    cells = [x for x in cells if x[0] < 2 * num - 0.5]
    cells.append((2 * num - 0.5, 0.5))
    # a line that starts high in the chord, winds down by steps and the
    # odd leap, then climbs a step into the hit
    idx = sc.index(7) if 7 in sc else len(sc) // 2
    deg = idx + len(sc)                      # the fifth, an octave up
    line = []
    for i, (a_, ln) in enumerate(cells):
        if i == len(cells) - 1:
            deg = max(deg, len(sc)) - 1      # the step under home
        line.append((a_, ln, (deg // len(sc)) * 12 + sc[deg % len(sc)]))
        r = d()
        deg += -1 if r < 0.55 else -2 if r < 0.7 else 1 if r < 0.9 else 2
        deg = max(len(sc) - 2, min(deg, 2 * len(sc) + 2))
    return line


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
    # the count-off, as long as the drummer makes it: 'three, four',
    # a bar, or two bars ('one ... two ... one, two, three, four')
    cd_ = G._Dice(song, 'count length')()
    count_beats = (2 if num >= 4 else num) if cd_ < 0.25 else \
        2 * num if cd_ < 0.55 else num
    clock0 = {'count_beats': count_beats}
    clock = {'beat': beat, 'len': total,
             'breath': int(beat * (0.2 + 0.35 * d())),
             'drummer': d(), 'fill_len': int(beat * (1.5 + 1.5 * d()))}
    clock.update(clock0)
    if sh.get('dictate_chords'):
        # the drummer's show: alone, then a band chord on the drummer's
        # call, over and over; each stretch as long as it feels, the
        # same for every part; then the conductor's count
        dd = G._Dice(song, 'dictate')
        segs = []
        def q16(x):
            return int(round(x * 4 / beat)) * beat // 4
        n_ch = len(sh['dictate_chords'])
        for k in range(n_ch):
            # the drummer takes their time and tells a story: patient
            # early, stretching out as it builds, never the same length
            # twice — nobody knows how long, the cue says when
            arc = k / max(n_ch, 1)
            segs.append(('alone', None,
                         q16(beat * (3 + 4 * arc + 5 * dd() ** 1.3))))
            segs.append(('band', k, q16(beat * (2.5 + 2.5 * dd()))))
        segs.append(('alone', None, q16(beat * (8 + 7 * dd()))))
        if sh.get('count'):
            segs.append(('count', None, clock0['count_beats'] * beat))
            if sh.get('unison'):
                segs.append(('unison', None, 2 * num * beat))
        else:
            # no count: the drummer cues the band onto the last chord,
            # held, everyone going for it, until the drummer cues the hit
            segs.append(('crazy', None, q16(beat * (7 + 4 * dd()))))
        clock['dictate'] = segs
    elif sh.get('sequence'):
        # the band's line together, then (if named) the drummer alone out
        # of time, then the held chord (going crazy, or just ringing, the
        # band's call when unsaid), then the hit on the drummer's cue
        dd = G._Dice(song, 'sequence')

        def q16(x):
            return int(round(x * 4 / beat)) * beat // 4
        segs = []
        if sh.get('unison_first'):
            segs.append(('unison', None, 2 * num * beat))
        if sh.get('drumsolo'):
            segs.append(('alone', None, q16(beat * (10 + 8 * dd()))))
        crazy = sh.get('crazy') or (sh.get('held') and dd() < 0.6)
        if crazy:
            segs.append(('crazy', None, q16(beat * (7 + 4 * dd()))))
        elif sh.get('held'):
            segs.append(('held', None, q16(beat * (5 + 3 * dd()))))
        clock['dictate'] = segs
    return clock


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
    # an unnamed gliss is every keyboard's: piano and organ together
    glissing = label in gl or (None in gl and role == 'comp'
                               and 'guitar' not in sound_id)
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
    def voice_for(ch):
        """This player's note(s) of a band chord: the horns and strings
        spread the voicing top-down across the section, each in their
        own range; keys take the rootless voicing over the root; the
        bass the root."""
        if ch is None:
            return []
        if role == 'bass':
            return [G._fold_bass(G._near(G._bass_pc(ch), 38), 28, 50)
                    + shift]
        if role == 'comp':
            v = G.rootless_voicing(ch, None)
            if 'guitar' in sound_id:
                return [m + shift for m in v]
            return [G._near(G._bass_pc(ch), 43) + shift] + \
                [m + shift for m in v]
        order = [x[0] for x in sh.get('voices', ())]
        if label in order:
            k = order.index(label)
            _l, lo, hi = sh['voices'][k]
            # a section voicing: the four rootless notes, lifted so the
            # lead sits high, one note a chair top-down; past four, the
            # lower chairs double the top voices an octave down
            base = sorted(G.rootless_voicing(ch, None))
            while max(base) < 76:
                base = [m + 12 for m in base]
            stack = sorted(base, reverse=True)
            n_ = len(order)
            for i in range(len(stack), n_):
                stack.append(stack[i - len(stack) if i - len(stack) <
                                   len(base) else 0] - 12)
            m = stack[k] if k < len(stack) else stack[k % len(base)] - 12
            while m > hi:
                m -= 12
            while m < lo:
                m += 12
            return [m + shift]
        return [p + shift for p in _voicing(role, sound_id, ch)]

    def go_for_it(b, vs, land, stop):
        """This player's own call on a held last chord, in the moment:
        hold it, blow over it, or shake it (Matthew, 2026-09-30: "no
        matter if the horns are blowing over top or holding out or one
        is holding while the others are blowing"). Keys tremolo or
        ring; the bass shakes or sits on the root."""
        dm = G._Dice(song, label, 'last chord')
        r = dm()
        order = [x[0] for x in sh.get('voices', ())]
        if role in ('comp', 'bass'):
            if r < 0.55:
                _trash_pitched(b, beat, vs, role, stop)
            else:
                for p in vs:
                    b.add(land, max(1, stop - land), ('p', p, 100))
            return
        lead = bool(order) and label == order[0]
        inst = sh.get('inst', {}).get(label, '')
        # sections mostly hold; the tune's soloists and the lead blow
        # over it; trumpets shake, saxes trill (live, in the moment —
        # the research and Matthew agree)
        soloed = label in sh.get('soloists', ())
        blow_p = 0.6 if soloed else 0.3 if lead else 0.12
        shake_p = 0.35 if 'trumpet' in inst or 'flugel' in inst or \
            'cornet' in inst else 0.25 if 'trombone' in inst else 0.0
        trill_p = 0.3 if 'sax' in inst or 'clarinet' in inst or \
            'flute' in inst else 0.0
        if r < blow_p and chord:
            kind = 'blow'
        elif r < blow_p + shake_p:
            kind = 'shake'
        elif r < blow_p + shake_p + trill_p:
            kind = 'trill'
        else:
            kind = 'hold'
        if kind == 'hold':
            top_up = lead and 'trumpet' in inst and dm() < 0.35
            for p in vs:
                # the lead trumpet may go for a screamer an octave up
                b.add(land, max(1, stop - land),
                      ('p', p + (12 if top_up else 0), 104))
        elif kind == 'trill':
            step = max(beat // 6, 2)
            for p in vs:
                b.add(land, beat // 2, ('p', p, 102))
                up = p + (2 if dm() < 0.6 else 1)
                t, k = land + beat // 2, 0
                while t < stop - step:
                    b.add(t, step, ('p', up if k % 2 == 0 else p, 96))
                    t += step
                    k += 1
        elif kind == 'blow':
            # blowing over it: lines, fast, in this player's range
            for p in vs:
                b.add(land, beat // 2, ('p', p, 104))
            lo_w = (min(vs) - shift) - 5
            nb = beat_bar(stop)
            G.improvise(nb, {'sol_last': max(vs) - shift},
                        [(1.0, chord)], None, '', lo_w, lo_w + 17,
                        9200, 1, 2, seed, mode='solo')
            line = [(t, ln, nn[1] + shift, min(nn[2] + 10, 112))
                    for t, (ln, ns) in sorted(nb.onsets.items())
                    for nn in ns if beat // 2 <= t < stop]
            for at_, ln_, m_, v_ in G._one_voice(line):
                b.add(int(at_), max(int(min(ln_, stop - at_)), 1),
                      ('p', m_, v_))
            _rubato(b, beat // 2, stop, dm)
        else:
            _trash_pitched(b, beat, vs, role, stop)

    def figure_body(length):
        """The unison figure for this part: every pitched chair on the
        line in its own octave, keys in octaves, the bass low; the
        drummer kicks it with the band and goes off in the gaps."""
        b = G.Bar(DIV, (n16(length), 16), fifths, staves)
        fig = unison_figure(song, chord, num)
        if drums:
            dfig = G._Dice(song, label, 'figure')
            ons = [a_ for a_, _l, _s in fig]
            for i, (a_, ln, _s) in enumerate(fig):
                t = int(a_ * beat)
                b.add(t, beat // 2, ('u', G._SNARE, 108 + int(dfig() * 10)))
                b.add(t, beat // 2, ('u', G._KICK, 100))
                if i == 0 or ln >= 1.0:
                    b.add(t, beat, ('u', G._CRASH, 106))
                nxt = ons[i + 1] if i + 1 < len(ons) else 2 * num
                if nxt - a_ >= 1.0 and dfig() < 0.8:
                    # the drummer's own way through the hole
                    _drum_idea(b, beat, t + beat // 2,
                               int(nxt * beat) - beat // 8,
                               _SOLO_IDEAS[int(dfig() * 5) % 5], dfig)
        elif role == 'perc':
            for a_, _ln, _s in fig:
                b.add(int(a_ * beat), beat // 2, ('u', ('C', 5, 'normal'),
                                                  100))
        elif chord:
            root = G._root_pc(chord)
            ref = voice_for(chord)
            mid = (sum(ref) / len(ref) - shift) if ref else 64
            if role == 'bass':
                mid = 40
            for a_, ln, semis in fig:
                pc = (root + semis) % 12
                m = G._near(pc, int(mid))
                ps = [m]
                if role == 'comp' and 'guitar' not in sound_id:
                    ps = [m - 12, m]             # keys in octaves
                for p in ps:
                    b.add(int(a_ * beat) + late(beat * 0.03),
                          max(1, int(ln * beat * 0.85)),
                          ('p', p + shift, 104))
        return b.xml() or rest(length)

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

    def beat_bar(ticks):
        """A scratch bar in the song's own beat, for the improviser —
        in the sixteenths the ending bars are counted in, it took every
        beat for a sixteenth and noodled at thirty-second speed."""
        return G.Bar(DIV, (max(1, int(round(ticks / beat))), den), fifths,
                     staves)

    def rest(ticks):
        ticks = n16(ticks) * beat // 4
        return ('      <note>\n        <rest measure="yes"/>\n'
                f'        <duration>{ticks}</duration>\n'
                '        <voice>1</voice>\n      </note>\n')

    def falls_off():
        """Does this player fall off the last hit? What the roadmap says
        stands; otherwise it's their call in the moment, and once in a
        while the whole band does it (Matthew, 2026-09-30: "someone may
        choose to fall off of whatever the last note ... that could be
        anyone ... everyone might decide in the moment to fall")."""
        if sh['arts'].get(label):
            return sh['arts'][label] == 'falloff'
        if drums or role == 'perc' or sh.get('no_falls'):
            return False
        # a moment, not a habit (Matthew: "every ending does not need
        # to have the max roach thing from everyone"): most endings
        # stay clean; sometimes one or two players fall; rarely all
        m = G._Dice(song, 'falls moment')()
        if m < 0.65 or (sh.get('tag') and m < 0.85):
            return False
        if m > 0.96:
            return True
        p_ = 0.3 if role == 'comp' else 0.15 if role == 'bass' else 0.25
        return G._Dice(song, label, 'falls off')() < p_

    def hit_body(length):
        b = bar_of(length)
        at = late(beat * 0.12)
        # a held hit rings under its fermata, everyone letting go
        # together-ish; a plain one is short
        short = (b.barlen - at - late(beat * 0.3) - beat // 4) \
            if sh.get('hit_held') else beat // 2
        if drums:
            G.final_hit(b, at, beat, G._Dice('last hit', label, at),
                        short)
        elif role == 'perc':
            b.add(at, short, ('u', ('C', 5, 'normal'), 94))
        elif pitches:
            fall = falls_off()
            keys = role == 'comp' and 'guitar' not in sound_id
            fa = arts or (('falloff',) if fall and not keys else ())
            ln_ = max(short, beat) if fa else short
            for p in pitches:
                b.add(at, min(ln_, b.barlen - at), ('p', p, 98, fa))
            if fall and keys:
                _gliss_down(b, beat, at + beat // 3, max(pitches),
                            b.barlen)
        return b.xml() or rest(b.barlen)

    extras = []
    last = None
    hl = int(beat * (4 + 2 * G._Dice(song, 'held hit')())) * 4 // 4 \
        if sh.get('hit_held') else 2 * beat     # how long a held hit rings
    hl = int(round(hl * 4 / beat)) * beat // 4
    if clock.get('dictate'):
        # the tune's last bar plays as it is; then the drummer's show
        dchords = sh.get('dictate_chords') or []
        dd = G._Dice(song, 'drum show')
        last_idea, last_cue, last_under = None, None, None
        for si, (kind, k, length) in enumerate(clock['dictate']):
            b = bar_of(length)
            L = b.barlen
            if kind == 'alone':
                if drums:
                    # whatever the drummer feels, a different idea every
                    # time, then a breath and a cue nobody can miss
                    alone_i = sum(1 for kk, _k, _l in clock['dictate'][:si]
                                  if kk == 'alone')
                    n_alone = sum(1 for kk, _k, _l in clock['dictate']
                                  if kk == 'alone')
                    arc = alone_i / max(n_alone - 1, 1)
                    pool = ('motif', 'space', 'talk', 'groove', 'roll') \
                        if arc < 0.35 else _SOLO_IDEAS if arc < 0.8 else \
                        ('toms', 'triplets', 'poly', 'kick', 'motif')
                    cue, cl, air = _seg_cue(song, si, beat)
                    last_cue = cue
                    end = max(beat, L - cl - beat // 3)
                    # a long stretch moves from one idea to the next
                    cuts = [0, end]
                    if end > 6 * beat:
                        cuts = [0, int(end * (0.4 + 0.2 * dd())) // (
                            beat // 4) * (beat // 4), end]
                    fake = end > 7 * beat and arc > 0.3 and dd() < 0.35
                    if fake:
                        # the fake-out: a cue, a slow-down like the chord
                        # is coming — then off again, and the real cue
                        f0 = int(end * (0.35 + 0.15 * dd())) // (
                            beat // 4) * (beat // 4)
                        fcue = _pick(dd, _CUES, cue)
                        fl = _CUE_LEN[fcue] * beat
                        idea = _pick(dd, pool, last_idea)
                        _drum_idea(b, beat, 0, max(beat, f0 - beat // 3),
                                   idea, dd)
                        _rubato(b, 0, f0, dd)
                        _drum_cue(b, beat, f0, f0 + fl, fcue, dd)
                        # the hang: nothing, a beat and a bit
                        g0 = f0 + fl + beat + beat // 2
                        idea = _pick(dd, ('triplets', 'toms', 'kick',
                                          'poly'), idea)
                        last_idea = idea
                        _drum_idea(b, beat, g0, end, idea, dd)
                        _rubato(b, g0, end, dd)
                        cuts = []
                    for c0, c1 in zip(cuts, cuts[1:]):
                        idea = _pick(dd, pool, last_idea)
                        last_idea = idea
                        _drum_idea(b, beat, c0, c1, idea, dd)
                    if cuts:
                        _rubato(b, 0, end, dd)
                    # soft and patient early, the big one last
                    _scale_vel(b, 0, end, 0.86 + 0.24 * arc)
                    _drum_cue(b, beat, L - cl, L - air, cue, dd)
                elif role == 'perc':
                    _roll(b, beat, 0, L, ('C', 5, 'normal'), 40, 90)
            elif kind == 'crazy':
                # the last chord, held, everybody going for it; then the
                # drummer's cue for the hit
                land = late(beat * 0.08)
                cue, cl, air = _seg_cue(song, si, beat)
                if drums:
                    b.add(land, beat, ('u', G._CRASH, 112))
                    b.add(land, beat, ('u', G._KICK, 104))
                    _trash_drums(b, beat, seed, L - cl - beat // 3)
                    _drum_cue(b, beat, L - cl, L - air, cue, dd)
                elif role == 'perc':
                    _roll(b, beat, beat, L - (cl + beat // 4 if G._Dice(
                        song, 'drop for the cue')() < 0.55 else beat // 6),
                          ('C', 5, 'normal'), 60, 104)
                else:
                    vs = voice_for(chord)
                    if vs:
                        # in the moment: this band lets go as the drummer
                        # cues, so the cue rings in the open — or keeps
                        # going right through it (one call for everyone:
                        # they're watching each other)
                        if G._Dice(song, 'drop for the cue')() < 0.55:
                            stop = L - cl - late(beat * 0.2) - beat // 8
                        else:
                            stop = L - late(beat * 0.25) - beat // 6
                        go_for_it(b, vs, land, stop)
            elif kind == 'held':
                # the last chord held and ringing (not going crazy), the
                # drummer swelling under it, then the cue for the hit
                land = late(beat * 0.08)
                cue, cl, air = _seg_cue(song, si, beat)
                if drums:
                    G.kit_hit(b, land, beat, dd)
                    _roll(b, beat, beat // 2, L - cl - beat // 3,
                          G._RIDE if dd() < 0.5 else G._SNARE, 34, 84)
                    _drum_cue(b, beat, L - cl, L - air, cue, dd)
                elif role == 'perc':
                    _roll(b, beat, beat, L - cl, ('C', 5, 'normal'), 40, 90)
                else:
                    for p in voice_for(chord):
                        b.add(land, max(1, L - cl - land - late(beat * 0.2)),
                              ('p', p, 96))
            elif kind == 'band':
                land = late(beat * 0.08)
                if drums:
                    # the landing, the drummer's pick: a crash, a choke,
                    # a bark, a snare shot...
                    G.kit_hit(b, land, beat, dd)
                    # under the chord: a snare roll, a cymbal swell, a
                    # tom rumble, or just let it ring — not the same
                    # thing under every chord
                    under = _pick(dd, ('roll', 'swell', 'rumble', 'ring',
                                       'ring'), last_under)
                    last_under = under
                    end_u = L - late(beat * 0.2) - 1
                    if under == 'roll':
                        _roll(b, beat, beat // 2, end_u, G._SNARE, 40, 70)
                    elif under == 'swell':
                        _roll(b, beat, beat // 2, end_u, G._RIDE, 30, 84)
                    elif under == 'rumble':
                        _roll(b, beat, beat // 2, end_u, _TOMS[2], 36, 80)
                elif role == 'perc':
                    b.add(land, beat, ('u', ('C', 5, 'normal'), 100))
                else:
                    for p in voice_for(dchords[k]):
                        b.add(land, max(1, L - land - late(beat * 0.3)
                                        - beat // 8), ('p', p, 102))
            elif kind == 'unison':
                extras.append(attrs(L) + figure_body(L))
                continue
            elif kind == 'count' and drums:
                _count_off(b, beat, L // beat, G._Dice(song, 'count off'),
                           num)
            extras.append(attrs(L) + (b.xml() if b.onsets else rest(L)))
        # everyone on the hit: short, or ringing when it's held
        b = bar_of(hl)
        at = late(beat * 0.06)
        ring = (b.barlen - at - late(beat * 0.3) - beat // 4) \
            if sh.get('hit_held') else beat // 2
        if drums:
            G.final_hit(b, at, beat, G._Dice('last hit', label, at), ring)
        elif role == 'perc':
            b.add(at, beat // 2, ('u', ('C', 5, 'normal'), 96))
        else:
            vs = voice_for(chord)
            fall = falls_off()
            keys = role == 'comp' and 'guitar' not in sound_id
            fa = arts or (('falloff',) if fall and not keys else ())
            for p in vs:
                b.add(at, max(ring, beat) if fa else ring, ('p', p, 106, fa))
            if fall and keys and vs:
                _gliss_down(b, beat, at + beat // 3, max(vs), b.barlen)
        extras.append(attrs(hl) + (b.xml() or rest(hl)))
    elif sh['stop']:
        if hitting:
            last = attrs(num * beat) + hit_body(num * beat)
    elif sh['held']:
        b = bar_of(clock['len'])
        L = b.barlen
        land = late(beat * 0.08)
        let_go = L - late(beat * 0.45)              # no hit: loose release
        if sh['hit']:
            let_go = L - clock['breath'] - late(beat * 0.1)
        fill_here = (label in sh['fill'] or (drums and None in sh['fill'])) \
            and not sh.get('fill_after')
        if drums:
            b.add(land, beat, ('u', G._CRASH, 104))
            b.add(land, beat, ('u', G._KICK, 96))
            if sh['trash']:
                _trash_drums(b, beat, seed, let_go)
            elif sh['roll']:
                _roll(b, beat, beat // 2, let_go, G._SNARE, 48, 110)
            elif fill_here:
                _fill(b, beat, let_go - clock['fill_len'], let_go, seed)
                # in the drummer's own time, broadening into the cue
                _rubato(b, let_go - clock['fill_len'], let_go - beat // 8,
                        G._Dice(song, 'fill rubato'))
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
                for p in pitches[:1]:            # a horn lands one note
                    b.add(land, beat * 9 // 10 - land, ('p', p, 94))
                nb = beat_bar(L)
                # improvised at concert pitch, written for the horn (it
                # used to improvise the concert chord in the written
                # range: a transposing horn noodled in the wrong key)
                lo = min(pitches) - shift - 2
                G.improvise(nb, {'sol_last': max(pitches) - shift},
                            [(1.0, chord)] if chord else [], None, '',
                            lo, lo + 19, 9000, 1, 2, seed, mode='solo')
                line = [(t + late(beat * 0.08), min(ln, let_go - t),
                         nn[1] + shift, min(nn[2], 82))
                        for t, (ln, ns) in sorted(nb.onsets.items())
                        if beat <= t < let_go for nn in ns]
                # one horn, one note at a time, over the held chord
                for at_, ln_, m_, v_ in G._one_voice(line):
                    b.add(int(at_), max(int(ln_), 1), ('p', m_, v_))
                _rubato(b, beat, let_go, G._Dice(song, label, 'noodle time'))
            elif sh['trash']:
                go_for_it(b, pitches, land, let_go)
            else:
                for p in pitches:
                    b.add(land, let_go - land, ('p', p, 94, arts))
            if glissing:
                _gliss(b, beat, land, pitches, me, let_go)
        last = attrs(L) + (b.xml() if b.onsets else rest(L))
        if sh['hit']:
            extras.append(attrs(hl) + (hit_body(hl) if hitting
                                       else rest(hl)))
    elif sh['hit']:
        # a button: one short hit straight after the last bar
        extras.append(attrs(hl) + (hit_body(hl) if hitting
                                   else rest(hl)))
    elif arts and pitches:
        # no hold, no hit: the last note carries the fall or doit
        b = bar_of(num * beat)
        for p in pitches:
            b.add(late(beat * 0.05), num * beat - beat // 2,
                  ('p', p, 92, arts))
        last = attrs(num * beat) + b.xml()
    if sh.get('cadenza') and not clock.get('dictate'):
        # the band cuts off; one player alone, free; the drummer may
        # bring everyone back; then the hit (Take Over's ending)
        dd = G._Dice(song, 'cadenza')
        clen = int(round(beat * (6 + 5 * dd()) * 4 / beat)) * beat // 4
        b = bar_of(clen)
        L = b.barlen
        if label == sh['cadenza'] and role not in ('drums', 'perc'):
            src = pitches or voice_for(chord)
            if src:
                top = max(src) - shift          # concert pitch
                nb = beat_bar(L)
                lo = top - 7
                G.improvise(nb, {'sol_last': top},
                            [(1.0, chord)] if chord else [], None, '',
                            lo, lo + 17, 9100, 1, 2, seed, mode='solo')
                raw = sorted((t, ln, nn[1], nn[2])
                             for t, (ln, ns) in nb.onsets.items()
                             for nn in ns if t < L - beat)
                # free time: it takes off, then broadens into a long
                # last note
                line = []
                for t, ln, m, v in raw:
                    x = t / max(L, 1)
                    tt = int(L * (0.08 + 0.72 * x ** 1.25))
                    line.append((tt, max(beat // 3, ln), m + shift,
                                 min(v + 6, 100)))
                line = G._one_voice(line)
                for at_, ln_, m_, v_ in line:
                    b.add(int(at_), max(int(ln_), 1), ('p', m_, v_))
                last_t = (line[-1][0] + line[-1][1]) if line else 0
                end_note = (G._near(G._root_pc(chord), top) if chord
                            else top) + shift
                b.add(min(int(last_t), L - beat), beat,
                      ('p', end_note, 88))
        cad = attrs(L) + (b.xml() if b.onsets else rest(L))
        ins = []
        ins.append(cad)
        if sh.get('fill_after'):
            fb = bar_of(2 * beat)
            if drums:
                _fill(fb, beat, 0, fb.barlen, seed)
            ins.append(attrs(2 * beat) + (fb.xml() if fb.onsets
                                          else rest(2 * beat)))
        # the cadenza goes before the hit, after any hold
        k = len(extras) - (1 if sh['hit'] and extras else 0)
        extras[k:k] = ins
    if not clock.get('dictate') and (sh.get('count') or sh.get('unison')):
        ins = []
        if sh.get('count'):
            cn = clock['count_beats'] * beat
            cb = bar_of(cn)
            if drums:
                _count_off(cb, beat, clock['count_beats'],
                           G._Dice(song, 'count off'), num)
            ins.append(attrs(cn) + (cb.xml() if cb.onsets else rest(cn)))
        if sh.get('unison'):
            ins.append(attrs(2 * num * beat) + figure_body(2 * num * beat))
        k = len(extras) - (1 if sh['hit'] and extras else 0)
        extras[k:k] = ins
    if sh['tag']:
        who, pieces = sh['tag']
        length = 4 * beat
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
    """A drummer's fill down the kit into the cue: even sixteenths,
    strong, the kick under each beat — tight and confident, into the
    hit (Matthew, 2026-09-29)."""
    toms = [G._SNARE, ('E', 5, 'normal'), ('D', 5, 'normal'),
            ('A', 4, 'normal')]
    span = max(t1 - t0, 1)
    step = beat // 4
    n = span // step
    for i in range(n):
        t = max(t0, 0) + i * step
        on_beat = i % 4 == 0
        bar.add(t, step, ('u', toms[min(i * 4 // max(n, 1), 3)],
                          min(84 + int(14 * i / max(n, 1))
                              + (10 if on_beat else 0), 122)))
        if on_beat:
            bar.add(t, step, ('u', G._KICK, 96))


_TOMS = [('E', 5, 'normal'), ('D', 5, 'normal'), ('A', 4, 'normal')]
_SOLO_IDEAS = ('motif', 'roll', 'toms', 'talk', 'space', 'triplets',
               'groove', 'poly', 'kick')
# no stick clicks as a cue: clicks are for a count-off only (Matthew,
# 2026-10-01)
_CUES = ('three', 'count', 'setup', 'flam', 'swell', 'hammer',
         'toms_walk', 'run_up', 'choke', 'flam_triplets')
_CUE_LEN = {'three': 1, 'count': 2, 'setup': 1, 'flam': 1, 'swell': 2,
            'hammer': 2, 'toms_walk': 2, 'run_up': 1,
            'choke': 1, 'flam_triplets': 1}


def _seg_cue(song, si, beat):
    """The drummer's cue for this stretch of an ending, the same for
    every player (they all have to hear the same cue), never the one
    just used, and with air after it: half a beat to a beat and a
    quarter of space before what comes next, so everyone gets ready
    (Matthew, 2026-09-30). Returns (cue, cue length with its air,
    air)."""
    def pick(i):
        d = G._Dice(song, 'seg cue', i)
        return _CUES[int(d() * len(_CUES)) % len(_CUES)], d
    cue, d = pick(si)
    if si > 0 and pick(si - 1)[0] == cue:
        cue = _CUES[(_CUES.index(cue) + 1) % len(_CUES)]
    q = max(beat // 4, 1)
    air = int(beat * (0.5 + 0.75 * d()) / q) * q
    return cue, _CUE_LEN[cue] * beat + air, air


def _pick(d, pool, last):
    """A choice from the pool, never the one just used."""
    got = pool[int(d() * len(pool)) % len(pool)]
    if got == last:
        got = pool[(pool.index(got) + 1 + int(d() * (len(pool) - 1)))
                   % len(pool)]
    return got


def _drum_idea(bar, beat, t0, t1, idea, d):
    """A drummer alone, one idea at a time (Matthew, 2026-09-30: "the
    drummer is not gonna play the same thing ... would do whatever and
    take their time"): a roll that builds, a tom melody, snare and kick
    talking, big hits with space, triplets around the kit."""
    span = max(t1 - t0, 1)
    # how fast this stretch runs: sixteenths, triplets or plain eighths
    r_ = d()
    sub = beat // 4 if r_ < 0.45 else beat // 3 if r_ < 0.7 else beat // 2
    if idea == 'motif':
        # one idea, worked: a short cell stated, said again, then moved
        # around the kit and stretched — not a stream of notes
        q = beat // 4
        cell = sorted({int(d() * 4) * q, int(d() * 4) * q,
                       int(d() * 4) * q})
        voices = [G._SNARE, _TOMS[0], _TOMS[1], _TOMS[2]]
        rep, t = 0, t0
        while t < t1 - q:
            v = voices[(rep // 2) % 4] if rep else G._SNARE
            for c in cell:
                if t + c < t1:
                    bar.add(t + c, q, ('u', v, 92 + 6 * (rep % 3)))
            bar.add(t, q, ('u', G._KICK, 90))
            # the answer leaves space; the development fills a little
            t += beat * (2 if rep % 2 else 1)
            rep += 1
            if rep == 4:
                cell = sorted(set(cell + [cell[-1] + q]))
    elif idea == 'groove':
        # the drummer slides into a groove for a while — any groove, at
        # any speed, the drummer's moment (Matthew, 2026-09-30: "not
        # everything needs to be played fast")
        g = ('swing', 'halfshuffle', 'halftime', 'bossa', 'secondline',
             'funk')[int(d() * 6) % 6]
        for bt in range(t0, t1, beat):
            k = (bt - t0) // beat
            if g == 'funk':
                for h in range(4):
                    bar.add(bt + h * beat // 4, beat // 4,
                            ('u', G._HAT, 70 if h % 2 else 88))
                if k % 2 == 1:
                    bar.add(bt, beat // 2, ('u', G._SNARE, 108))
                if k % 2 == 0 or d() < 0.4:
                    bar.add(bt + (beat // 2 if d() < 0.4 else 0), beat // 2,
                            ('u', G._KICK, 96))
            elif g == 'halftime':
                # slow and heavy: eighth hats, snare on three of the bar
                bar.add(bt, beat // 2, ('u', G._HAT, 76))
                bar.add(bt + beat // 2, beat // 2, ('u', G._HAT, 62))
                if k % 4 == 2:
                    bar.add(bt, beat, ('u', G._SNARE, 112))
                if k % 4 == 0 or (k % 4 == 3 and d() < 0.5):
                    bar.add(bt + (beat // 2 if k % 4 == 3 else 0), beat,
                            ('u', G._KICK, 100))
            elif g == 'halfshuffle':
                bar.add(bt, beat // 3, ('u', G._HAT, 80))
                bar.add(bt + 2 * beat // 3, beat // 3, ('u', G._HAT, 66))
                bar.add(bt + beat // 3, beat // 3, ('u', G._SNARE, 34))
                if k % 4 == 2:
                    bar.add(bt, beat, ('u', G._SNARE, 110))
                if k % 4 == 0:
                    bar.add(bt, beat, ('u', G._KICK, 98))
            elif g == 'bossa':
                # the one place the cross-stick belongs
                bar.add(bt, beat // 2, ('u', G._HAT, 64))
                bar.add(bt + beat // 2, beat // 2, ('u', G._HAT, 54))
                if k % 2 == 0:
                    bar.add(bt, beat // 2, ('u', G._KICK, 80))
                if k % 4 in (0, 3) or (k % 4 == 1 and d() < 0.5):
                    bar.add(bt + (beat // 2 if k % 4 == 1 else 0), beat // 2,
                            ('u', ('C', 5, 'x'), 76))
            elif g == 'secondline':
                bar.add(bt, beat // 4, ('u', G._SNARE, 96 if k % 2 else 70))
                if d() < 0.6:
                    bar.add(bt + 3 * beat // 4, beat // 4,
                            ('u', G._SNARE, 88))
                if k % 2 == 0:
                    bar.add(bt + beat // 2, beat // 2, ('u', G._KICK, 94))
            else:                                   # swing, with space
                bar.add(bt, beat // 2, ('u', G._RIDE, 84))
                if k % 2 == 1:
                    bar.add(bt + 2 * beat // 3, beat // 3,
                            ('u', G._RIDE, 70))
                    bar.add(bt, beat // 2, ('u', G._HATF, 70))
                if d() < 0.35:
                    bar.add(bt + (2 * beat // 3 if d() < 0.6 else 0),
                            beat // 3, ('u', G._SNARE if d() < 0.7
                                        else G._KICK, 60 + int(d() * 50)))
    elif idea == 'poly':
        # three against four: accents every three sixteenths walking
        # around the toms over a steady kick
        q = beat // 4
        kit = [G._SNARE, _TOMS[0], _TOMS[1], _TOMS[2]]
        for i, t in enumerate(range(t0, t1, q)):
            acc = i % 3 == 0
            bar.add(t, q, ('u', kit[(i // 3) % 4] if acc else G._SNARE,
                           110 if acc else 44))
            if (t - t0) % beat == 0:
                bar.add(t, q, ('u', G._KICK, 88))
    elif idea == 'kick':
        # the kick leads: kick figures with the snare and floor tom
        # answering, the feet talking
        q = sub
        for t in range(t0, t1, q):
            r = d()
            if r < 0.34:
                bar.add(t, q, ('u', G._KICK, 96 + int(d() * 20)))
            elif r < 0.46:
                bar.add(t, q, ('u', G._SNARE, 100 + int(d() * 18)))
            elif r < 0.54:
                bar.add(t, q, ('u', _TOMS[2], 104))
    elif idea == 'roll':
        _roll(bar, beat, t0, t1, G._SNARE, 40, 100)
        for t in range(t0 + beat, t1, beat):
            if d() < 0.3:
                bar.add(t, beat // 4, ('u', _TOMS[2], 92))
    elif idea == 'toms':
        step = sub
        t, i = t0, 0
        while t < t1:
            if d() < 0.12:                   # a breath in the line
                t += step * 2
                continue
            drum = _TOMS[(i // 2 + int(d() * 2)) % 3] if d() < 0.8 \
                else G._SNARE
            v = int(70 + 40 * (t - t0) / span + (12 if i % 4 == 0 else 0))
            bar.add(t, step, ('u', drum, min(v, 120)))
            if i % 4 == 0:
                bar.add(t, step, ('u', G._KICK, 88))
            t += step
            i += 1
    elif idea == 'talk':
        step = sub
        for t in range(t0, t1, step):
            r = d()
            if r < 0.28:
                bar.add(t, step, ('u', G._SNARE, 38 + int(d() * 12)))
            elif r < 0.42:
                bar.add(t, step, ('u', G._SNARE, 104 + int(d() * 12)))
            elif r < 0.55:
                bar.add(t, step, ('u', G._KICK, 92 + int(d() * 16)))
    elif idea == 'space':
        # a few big statements, room between, a cymbal breathing
        t = t0
        while t < t1 - beat // 2:
            hit = [G._KICK, _TOMS[2]] if d() < 0.5 else [G._KICK, G._CRASH]
            for dr in hit:
                bar.add(t, beat, ('u', dr, 108))
            t += int(beat * (1.25 + 1.5 * d()))
        _roll(bar, beat, t0 + beat // 2, t1, G._RIDE, 26, 64)
    else:                                     # triplets around the kit
        step = beat // 3
        kit = [G._SNARE, _TOMS[0], _TOMS[1], _TOMS[2]]
        for i, t in enumerate(range(t0, t1, step)):
            bar.add(t, step, ('u', kit[(i + int(d() * 2)) % 4],
                              int(78 + 30 * (t - t0) / span)))
            if i % 3 == 0:
                bar.add(t, step, ('u', G._KICK, 84))


def _rubato(bar, t0, t1, d):
    """Out of time, the way an ending is played unless the chart says
    otherwise (Matthew, 2026-09-30: "an ending is not in time"): the
    notes in the stretch keep their order and their shape, but the
    player pushes and pulls — a curve through the whole stretch and a
    little give on every note."""
    span = t1 - t0
    if span <= 0:
        return
    push = (d() - 0.5) * 0.5                 # ahead early, or held back
    moved = {}
    for t in sorted(bar.onsets):
        if not t0 <= t < t1:
            moved.setdefault(t, bar.onsets[t])
            continue
        x = (t - t0) / span
        y = x + push * x * (1 - x) * 2
        y += (d() - 0.5) * 0.02
        nt = t0 + int(max(0.0, min(0.999, y)) * span)
        ln, ns = bar.onsets[t]
        if nt in moved:
            moved[nt] = (max(moved[nt][0], ln), moved[nt][1] + ns)
        else:
            moved[nt] = (ln, ns)
    bar.onsets.clear()
    bar.onsets.update(moved)


def _count_off(bar, beat, n, d, num=4):
    """The count-off, the drummer's way this time: on the hi-hat foot,
    the closed hat, the rim, the ride bell or the snare; as long as they
    make it — 'three, four', a bar, or two bars with the first one in
    half time (Matthew, 2026-09-30: "can be any drum, hihat, whatever in
    the moment ... could also be whatever how long")."""
    piece = [G._HATF, G._HAT, ('C', 5, 'x'), G._BELL, G._SNARE][
        int(d() * 5) % 5]
    v = 70 + int(d() * 20)
    if n > num:
        # two bars: one ... two ... then one, two, three, four
        for t in range(0, num * beat, 2 * beat):
            bar.add(t, beat // 4, ('u', piece, v))
        for i in range(n - num):
            bar.add((num + i) * beat, beat // 4, ('u', piece, v + 4 * i))
        return
    for i in range(n):
        bar.add(i * beat, beat // 4, ('u', piece, v + 4 * i))


def _scale_vel(bar, t0, t1, k):
    """Softer or louder over a stretch: the story's dynamics."""
    for t in list(bar.onsets):
        if t0 <= t < t1:
            ln, ns = bar.onsets[t]
            bar.onsets[t] = (ln, [n if n[2] is None else
                                  (n[0], n[1], max(1, min(int(n[2] * k),
                                                          124))) + n[3:]
                                  for n in ns])


def _drum_cue(bar, beat, t0, t1, cue, d):
    """The drummer's cue: an unmistakable little figure that tells the
    band the chord is coming — three rising hits, a count on the snare,
    snare and kick together on the 'and', or a big flam — landing the
    band on t1."""
    if cue == 'three':
        step = (t1 - t0) // 3
        for i, dr in enumerate((_TOMS[2], _TOMS[0], G._SNARE)):
            bar.add(t0 + i * step, step, ('u', dr, 96 + 10 * i))
        bar.add(t0 + 2 * step, step, ('u', G._KICK, 104))
    elif cue == 'count':
        step = (t1 - t0) // 4
        for i in range(4):
            bar.add(t0 + i * step, step // 2, ('u', G._SNARE, 80 + 10 * i))
    elif cue == 'setup':
        at = t1 - beat // 2
        bar.add(at, beat // 2, ('u', G._SNARE, 116))
        bar.add(at, beat // 2, ('u', G._KICK, 110))
    elif cue == 'hammer':
        # snare and kick hammering quarters, building: nobody can miss it
        step = (t1 - t0) // 4
        for i in range(4):
            bar.add(t0 + i * step, step // 2, ('u', G._SNARE, 96 + 8 * i))
            bar.add(t0 + i * step, step // 2, ('u', G._KICK, 92 + 8 * i))
        bar.add(t0 + 3 * step, step, ('u', G._CRASH, 116))
    elif cue == 'toms_walk':
        # the toms walking down, the kick under each
        step = (t1 - t0) // 4
        for i, dr in enumerate((_TOMS[0], _TOMS[1], _TOMS[2], _TOMS[2])):
            bar.add(t0 + i * step, step, ('u', dr, 100 + 5 * i))
            bar.add(t0 + i * step, step // 2, ('u', G._KICK, 96))
    elif cue == 'run_up':
        # a fast run up the toms to the snare
        step = max((t1 - t0) // 6, 1)
        seq = (_TOMS[2], _TOMS[2], _TOMS[1], _TOMS[1], _TOMS[0], G._SNARE)
        for i, dr in enumerate(seq):
            bar.add(t0 + i * step, step, ('u', dr, 90 + 5 * i))
        bar.add(t0 + 5 * step, step, ('u', G._KICK, 110))
    elif cue == 'choke':
        # the crash grabbed short, then nothing: the silence is the cue
        bar.add(t0, beat // 2, ('u', G._CRASH, 118, ('staccato',)))
        bar.add(t0, beat // 2, ('u', G._KICK, 110))
        bar.add(t0, beat // 2, ('u', G._SNARE, 104))
    elif cue == 'flam_triplets':
        step = (t1 - t0) // 3
        for i in range(3):
            at = t0 + i * step
            bar.add(at, beat // 12 or 1, ('u', G._SNARE, 66))
            bar.add(at + (beat // 12 or 1), step, ('u', G._SNARE,
                                                   104 + 6 * i))
        bar.add(t0 + 2 * step, step, ('u', G._KICK, 108))
    elif cue == 'swell':
        # a crescendo roll right into the chord
        _roll(bar, beat, t0, t1 - beat // 8, G._SNARE, 50, 120)
        bar.add(t1 - beat // 4, beat // 4, ('u', G._KICK, 108))
    else:                                     # flam
        at = t1 - beat
        bar.add(at, beat // 8, ('u', G._SNARE, 70))
        bar.add(at + beat // 12, beat // 2, ('u', G._SNARE, 118))
        bar.add(at + beat // 12, beat // 2, ('u', G._KICK, 108))


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
    """A keyboard gliss over the held chord into the cue: the palm up
    the white keys, two octaves-ish in under a beat, landing where the
    band lets go."""
    white = (0, 2, 4, 5, 7, 9, 11)
    lo = min(pitches) - 5
    hi = max(pitches) + 14
    keys = [m for m in range(lo, hi + 1) if m % 12 in white]
    # it sets up the last hit: the sweep ends just as the band cuts
    # off for the cue (Matthew, 2026-09-30: while holding the last chord
    # "a gliss from piano or organ ... and drums together can work")
    span = beat * (0.6 + 0.5 * me())
    t = max(land + beat, t1 - span - beat * 0.05)
    step = span / max(len(keys), 1)
    for i, m in enumerate(keys):
        at = int(t + i * step * (1 + 0.4 * i / len(keys)))
        if at >= t1:
            break
        bar.add(at, max(int(step * 2), 2),
                ('p', m, int(60 + 30 * i / len(keys))))


def _gliss_down(bar, beat, t0, top, t1):
    """Keys fall off the last chord: a palm down the white keys from the
    top of the chord, an octave and a half or so, quick and loosening."""
    white = (0, 2, 4, 5, 7, 9, 11)
    keys = [m for m in range(top, top - 20, -1) if m % 12 in white]
    span = beat * 0.7
    step = span / max(len(keys), 1)
    for i, m in enumerate(keys):
        at = int(t0 + i * step * (1 + 0.5 * i / len(keys)))
        if at >= t1:
            break
        bar.add(at, max(int(step * 2), 2),
                ('p', m, int(92 - 40 * i / len(keys))))


def band_choice(feel, song, has_keys, has_horns, written=None,
                has_drums=True):
    """The roadmap says nothing about the ending (or says 'band's
    choice'): the band decides in the moment, the way a group does,
    from the feel, a different call in every tune. Returns steps.

    Holding the last chord before a hit, the setup is in the moment too
    (Matthew, 2026-09-30): the drummer fills into it, or the piano or
    organ glisses into it, or both together, or nobody does anything but
    watch. Now and then, when the tune has the energy, the drummer takes
    the whole ending: alone, then a band chord on the drummer's call,
    back and forth, until the conductor counts everyone in on the last
    hit (the Last Surprise ending)."""
    import chartgroove as _G
    d = G._Dice(song, 'choice')
    style, traits = _G.style_of(feel or '')
    r = d()
    if written == 'long':
        # the written parts hold their last note: the band holds with them
        return [('hold', None)]
    if written == 'short':
        # the written parts end on a short one: the band stops with them
        return [('stop', None)]
    hot = style in ('funk', 'latin', 'samba', 'straight', 'motown',
                    'hiphop', 'secondline', 'rock')
    if 'ballad' in traits or 'ballad' in (feel or '').lower():
        steps = [('rit', None), ('hold', None)]
        if has_horns and r > 0.8:
            # the lead horn takes a cadenza, the band comes back to end
            steps += [('cadenza', 'lead'), ('hit', 'cue')]
    elif not (feel or '').strip():
        # no feel written: the ending any band would reach for — land
        # and hold, maybe a hit — never a funk band's stop
        steps = [('hold', None)] if r < 0.55 else \
            [('hold', None), ('hit', 'cue')]
    elif hot:
        steps = ([('stop', None)] if r < 0.35 else
                 [('hold', None), ('hit', 'cue')] if r < 0.6 else
                 [('trash', None), ('hit', 'cue')] if r < 0.78 else
                 [('hold', None)] if r < 0.9 else
                 [('dictate', ('drums', None))]
                 + ([('count', None)] + ([('unison', None)] if d() < 0.6
                                         else []) if d() < 0.5 else [])
                 + [('hit', 'cue')])
    elif style == 'waltz':
        steps = [('hold', None)]
    else:
        steps = ([('hold', None)] if r < 0.4 else
                 [('hold', None), ('hit', 'cue')] if r < 0.68 else
                 [('button', None)] if r < 0.82 else
                 [('trash', None), ('hit', 'cue')] if r < 0.95 else
                 [('dictate', ('drums', None))]
                 + ([('count', None)] + ([('unison', None)] if d() < 0.6
                                         else []) if d() < 0.5 else [])
                 + [('hit', 'cue')])
    if not has_drums:
        steps = [s_ for s_ in steps if s_[0] != 'dictate'] or \
            [('hold', None), ('hit', 'cue')]
    held = any(k in ('hold', 'roll', 'trash') for k, _ in steps)
    hit = any(k in ('hit', 'button') for k, _ in steps)
    if held and hit:
        # the setup into the last hit, decided in the moment
        at = next(i for i, (k, _) in enumerate(steps)
                  if k in ('hold', 'roll', 'trash')) + 1
        r2 = d()
        trash = any(k == 'trash' for k, _ in steps)
        if r2 < 0.3 and not trash:
            steps.insert(at, ('fill', None))
        elif r2 < 0.5 and has_keys:
            steps.insert(at, ('gliss', None))
        elif r2 < 0.68 and has_keys:
            steps[at:at] = [('gliss', None)] + ([] if trash
                                                else [('fill', None)])
    if held and hit and d() < 0.25:
        # and sometimes the last hit rings, fermata, instead of cutting
        steps = [('hit', 'held') if k == 'hit' else (k, a)
                 for k, a in steps]
    elif hit and d() < (0.5 if any(k == 'dictate' for k, _ in steps)
                        else 0.35):
        steps.append(('tag', ('drums', None)))
    return steps


def _tag(bar, beat, pieces, song):
    """The drummer's little thing after everyone's last note: a breath,
    then the pieces, loose, the last one landing hardest."""
    d = G._Dice(song, 'tag')
    if not pieces:
        pieces = band_tag(d)
    # straight in after the band's hit, committed, each stroke given
    # its room and the last one landing on the kick (Matthew: "relax as
    # in don't rush your ideas ... still go for it")
    t = beat * (0.35 + 0.35 * d())
    n = len(pieces)
    # sometimes a quick lick (sixteenths or triplets), sometimes loose
    quick = n >= 3 and d() < 0.4
    step = (beat // 4 if d() < 0.5 else beat // 3) if quick else None
    for i, p in enumerate(pieces):
        vel = 94 + int(18 * (i + 1) / n) + int((d() - 0.5) * 8)
        for x in p.split('+'):
            v = vel if 'foot' not in x and x not in ('pedal',) else 78
            bar.add(int(t), beat // 2, ('u', _KIT[x], min(v, 124)))
        t += step if step else beat * (0.36 + 0.16 * d()
                                       + (0.18 if i == n - 2 else 0))
    return bar.xml()
