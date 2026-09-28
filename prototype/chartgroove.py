#!/usr/bin/env python3
"""chartgroove — the rhythm section the slashes always meant.

A groove bar prints as slashes because a rhythm player reads chords
and style, not notes. The page keeps that promise. But the LISTENING
document used to keep it too literally — rests — so a chart with a
rhythm section played back as a band with no band. Matthew's ruling
(2026-09-20, with Rocco on the call): realize it. This module writes
what a competent, tasteful player would play — into the listening
document only. The pages never change, and findings name every part
that was realized.

The realization is deterministic on purpose: the same chart builds the
same audio byte for byte, so the regression net keeps meaning
something. Variety comes from the bar number, never from a dice roll.

Roles come from the part's instrument sound id: drums play time
(ride-led swing, backbeat straight, a dotted pulse in compound
meters); bass walks in swing and holds root-and-fifth elsewhere;
chordal instruments comp — Freddie Green quarters on guitar, offbeat
piano voicings, pads on organ. Voicings voice-lead: guide tones (3rd
and 7th) plus a color, each landing in the octave nearest the last
voicing. `hits` bars realize as exactly the kicks the pattern names.

These bars are read by chartaudio only, never engraved, so a note's
<duration> in ticks is the contract; <type> is best-effort cosmetics.
"""
import re

# ---------------------------------------------------------------- chords

_STEP_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
_FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']

# quality -> semitones above the root
_QUAL = {
    'maj': (0, 4, 7), '6': (0, 4, 7, 9), 'maj7': (0, 4, 7, 11),
    'maj9': (0, 4, 7, 11, 14), 'add9': (0, 4, 7, 14),
    'maj7#11': (0, 4, 7, 11, 18), '69': (0, 4, 7, 9, 14),
    'm': (0, 3, 7), 'm6': (0, 3, 7, 9), 'm7': (0, 3, 7, 10),
    'm9': (0, 3, 7, 10, 14), 'm11': (0, 3, 7, 10, 17),
    'madd9': (0, 3, 7, 14), 'mmaj7': (0, 3, 7, 11),
    'm69': (0, 3, 7, 9, 14),
    '7': (0, 4, 7, 10), '9': (0, 4, 7, 10, 14),
    '11': (0, 4, 7, 10, 17), '13': (0, 4, 7, 10, 14, 21),
    '7#9': (0, 4, 7, 10, 15), '7b9': (0, 4, 7, 10, 13),
    '7#11': (0, 4, 7, 10, 18), '7#9#11': (0, 4, 7, 10, 15, 18),
    '13sus': (0, 5, 7, 10, 14, 21), '7#9b13': (0, 4, 10, 15, 20),
    '7b5': (0, 4, 6, 10), '7#5': (0, 4, 8, 10),
    '7b13': (0, 4, 7, 10, 20), '13b9': (0, 4, 7, 10, 13, 21),
    'alt': (0, 4, 8, 10, 13), '7sus4': (0, 5, 7, 10),
    'sus4': (0, 5, 7), 'sus2': (0, 2, 7),
    'dim': (0, 3, 6), 'dim7': (0, 3, 6, 9), 'm7b5': (0, 3, 6, 10),
    'aug': (0, 4, 8),
    '9sus4': (0, 5, 7, 10, 14), '7b9b13': (0, 4, 10, 13, 20),
    '7b9#11': (0, 4, 10, 13, 18), '9#11': (0, 4, 7, 10, 14, 18),
    '13#9': (0, 4, 10, 15, 21), 'm13': (0, 3, 7, 10, 14, 21),
    'maj13': (0, 4, 7, 11, 14, 21), 'maj9#11': (0, 4, 7, 11, 14, 18),
    'm7b9': (0, 3, 7, 10, 13), '5': (0, 7, 12),
    '7#9#5': (0, 4, 8, 10, 15), '7b9#5': (0, 4, 8, 10, 13),
    'maj7#5': (0, 4, 8, 11), 'mb6': (0, 3, 7, 8),
    '7b9sus4': (0, 5, 7, 10, 13), '7b9b5': (0, 4, 6, 10, 13),
    '9#5': (0, 4, 8, 10, 14), '7#9b5': (0, 4, 6, 10, 15),
    'm#5': (0, 3, 8), 'm9b5': (0, 3, 6, 10, 14),
    '9b5': (0, 4, 6, 10, 14), 'mmaj9': (0, 3, 7, 11, 14),
}


def _root_pc(chord):
    return (_STEP_PC[chord[0]] + chord[1]) % 12


def _bass_pc(chord):
    if chord[3]:
        m = re.fullmatch(r'([A-G])([b#]?)', chord[3])
        if m:
            return (_STEP_PC[m.group(1)]
                    + {'b': -1, '#': 1, '': 0}[m.group(2)]) % 12
    return _root_pc(chord)


def _tones(chord):
    return _QUAL.get(chord[2], (0, 4, 7, 10))


def _guide(chord):
    """Comping pitch classes: guide tones plus one color, no root —
    the bass owns the root."""
    root = _root_pc(chord)
    iv = _tones(chord)
    picks = []
    for s in iv:
        if s % 12 in (3, 4, 2, 5) and not picks:
            picks.append(s)
    for s in iv:
        if s % 12 in (9, 10, 11) and len(picks) < 2:
            picks.append(s)
            break
    rest = [s for s in iv if s not in picks and s % 12 != 0]
    if rest:
        picks.append(rest[-1])
    if not picks:
        picks = [s for s in iv if s % 12] or [7]
    return [(root + s) % 12 for s in picks[:3]]


def _near(pc, anchor):
    n = anchor + ((pc - anchor) % 12)
    if n - anchor > 6:
        n -= 12
    return n


# ------------------------------------------------------------ bar model
#
# A bar is built as onsets: {tick: [note, note, ...]} where a note is
# ('p', midi, vel) or ('u', (step, octave, notehead), vel), all notes
# at one tick sharing one duration. Emission stacks them: the first is
# the anchor, the rest carry <chord/>. vel None means the running
# dynamic.


class Bar:
    def __init__(self, div, bmeter, fifths, staves, shift=0):
        self.div = div
        self.num, self.den = bmeter
        self.barlen = div * 4 * self.num // self.den
        self.fifths = fifths
        self.staves = staves
        # the groove thinks in SOUNDING pitches, but this bar lands in
        # a part whose <transpose> the player applies — so pitches are
        # written shifted up by the part's transposition, and playback
        # brings them back down. Found by ear (Matthew, 2026-09-22):
        # the realized bass sounded an octave low, because sounding
        # pitches written into a transposing part transpose twice.
        self.shift = shift
        self.onsets = {}                 # tick -> (ticks, [notes])

    def add(self, tick, ticks, note):
        tick = int(round(tick))
        ticks = max(int(round(ticks)), 1)
        if tick >= self.barlen or tick < 0:
            return
        ticks = min(ticks, self.barlen - tick)
        if tick in self.onsets:
            self.onsets[tick][1].append(note)
        else:
            self.onsets[tick] = (ticks, [note])

    def _type_of(self, ticks):
        q = self.div
        for length, name in ((4 * q, 'whole'), (3 * q, 'half'),
                             (2 * q, 'half'), (3 * q // 2, 'quarter'),
                             (q, 'quarter'), (3 * q // 4, 'eighth'),
                             (q // 2, 'eighth'), (q // 4, '16th')):
            if ticks >= length:
                dot = ticks in (3 * q, 3 * q // 2, 3 * q // 4)
                return name, dot
        return '16th', False

    def _one(self, note, ticks, chorded):
        kind, what, vel = note
        t, dot = self._type_of(ticks)
        out = ['      <note%s>' % (f' dynamics="{vel}"' if vel else '')]
        if chorded:
            out.append('        <chord/>')
        if kind == 'u':
            st, oc, head = what
            out.append(f'        <unpitched><display-step>{st}'
                       f'</display-step><display-octave>{oc}'
                       '</display-octave></unpitched>')
        else:
            what = what + self.shift
            names = _FLAT if self.fifths < 0 else _SHARP
            nm = names[what % 12]
            al = -1 if nm.endswith('b') else (1 if nm.endswith('#')
                                              else 0)
            out.append('        <pitch>'
                       f'<step>{nm[0]}</step>'
                       + (f'<alter>{al}</alter>' if al else '')
                       + f'<octave>{what // 12 - 1}</octave></pitch>')
        out.append(f'        <duration>{ticks}</duration>')
        out.append('        <voice>1</voice>')
        out.append(f'        <type>{t}</type>')
        if dot:
            out.append('        <dot/>')
        if kind == 'u':
            head = what[2]
            if head != 'normal':
                out.append(f'        <notehead>{head}</notehead>')
        if self.staves > 1:
            out.append('        <staff>1</staff>')
        out.append('      </note>')
        return '\n'.join(out) + '\n'

    def _rest(self, ticks):
        t, dot = self._type_of(ticks)
        return ('      <note>\n        <rest/>\n'
                f'        <duration>{ticks}</duration>\n'
                '        <voice>1</voice>\n'
                f'        <type>{t}</type>\n'
                + ('        <dot/>\n' if dot else '')
                + '      </note>\n')

    def xml(self):
        if not self.onsets:
            return None
        out = []
        pos = 0
        for tick in sorted(self.onsets):
            ticks, notes = self.onsets[tick]
            if tick > pos:
                out.append(self._rest(tick - pos))
            elif tick < pos:
                # an overlap: step time back so this onset lands true
                out.append(f'      <backup><duration>{pos - tick}'
                           '</duration></backup>\n')
            for i, note in enumerate(notes):
                out.append(self._one(note, ticks, chorded=i > 0))
            pos = tick + ticks
        if pos < self.barlen:
            out.append(self._rest(self.barlen - pos))
        if self.staves > 1:
            out.append(f'      <backup><duration>{self.barlen}'
                       '</duration></backup>\n')
            out.append('      <note>\n        <rest measure="yes"/>\n'
                       f'        <duration>{self.barlen}</duration>\n'
                       '        <voice>2</voice>\n'
                       '        <staff>2</staff>\n      </note>\n')
        return ''.join(out)


# --------------------------------------------------------------- roles


HAND = ('drum.conga', 'drum.bongo', 'drum.timbale', 'metal.cowbell',
        'wood.claves', 'wood.guiro', 'wood.wood-block', 'rattle.',
        'drum.tambourine', 'metal.triangle', 'metal.bells.agogo')


def role_of(sound_id, clef):
    s = (sound_id or '').lower()
    # a percussionist's own chair plays its own instrument's groove, not
    # the kit's (Matthew, 2026-09-28: "percussion should be able to do
    # all those feels too")
    if any(h in s for h in HAND):
        return 'perc'
    if clef == 'percussion' or 'drum' in s:
        return 'drums'
    if 'bass' in s and 'bassoon' not in s:
        return 'bass'
    if any(w in s for w in ('piano', 'organ', 'keyboard', 'guitar',
                            'vibraphone', 'marimba', 'accordion',
                            'harpsichord', 'clav', 'celesta', 'harp')):
        return 'comp'
    return None


def _is_swing(feel):
    return any(w in (feel or '').lower() for w in ('swing', 'shuffle'))


def style_of(feel):
    """The bandstand's words for a feel -> (style, traits). The style is
    what the rhythm section plays (swing, straight, funk, bossa, samba,
    latin); traits bend it (two, half, double, ballad). Words the
    section doesn't know leave the old straight-or-swing reading alone,
    so 'easy gospel' and every chart built before this keeps its band.
    Matthew, 2026-09-28: two feel, swing, straight eighths, 'all the
    lingo'."""
    f = (feel or '').lower()
    traits = set()
    if re.search(r'\b(?:two|2)[ -]?(?:feel|beat)\b|\bin (?:two|2)\b', f):
        traits.add('two')
    if re.search(r'\b(?:half|1/2)[ -]?time\b', f):
        traits.add('half')
    if re.search(r'\bdouble[ -]?time\b', f):
        traits.add('double')
    if 'ballad' in f:
        traits.add('ballad')
    if 'bossa' in f:
        style = 'bossa'
    elif 'samba' in f:
        style = 'samba'
    elif re.search(r'latin|afro|mambo|songo|salsa|cha[ -]?cha|montuno|'
                   r'guaguanc|rumba|tumbao', f):
        style = 'latin'
    elif 'funk' in f:
        style = 'funk'
    elif re.search(r'straight|even (?:8ths|eighths)|\brock\b|\bpop\b', f):
        style = 'straight'
    elif _is_swing(f) or traits & {'two', 'ballad'}:
        style = 'swing'
    else:
        style = 'straight'
    return style, traits


def _new_style(feel, bar):
    """The styles this module learned 2026-09-28, in 2- and 4-beat
    quarter-note bars only; None leaves the original swing/straight
    reading (and its bytes) exactly as it was."""
    if bar.den != 4 or bar.num not in (2, 4):
        return None
    style, traits = style_of(feel)
    if style in ('bossa', 'samba', 'latin', 'funk'):
        return style, traits
    if traits:
        return style, traits
    return None


def _pattern(bar, beat, pat, sound):
    """[(beat 1-based, length in beats, velocity)] -> hits of one sound,
    kept inside the bar."""
    for b, ln, vel in pat:
        if b > bar.num + 0.99:
            continue
        at = int(round((b - 1) * beat))
        bar.add(at, max(1, int(round(ln * beat))), ('u', sound, vel))


def _chords_in(sec, off, governing):
    listed = [(b, c) for b, c in sec['content'][off] if c is not None]
    if (not listed or listed[0][0] > 1.0) and governing is not None:
        listed = [(1.0, governing)] + listed
    return listed


def _next_root(sec, off, chords):
    for o in range(off + 1, sec['bars']):
        for b, c in sec['content'][o]:
            if c is not None:
                return _bass_pc(c)
    for o in range(0, off + 1):
        for b, c in sec['content'][o]:
            if c is not None:
                return _bass_pc(c)
    return _bass_pc(chords[-1][1]) if chords else 0


def _chord_at(chords, beat):
    cur = chords[0][1] if chords else None
    for b, c in chords:
        if b <= beat + 1e-6:
            cur = c
    return cur


# ------------------------------------------------------------ the bars

# staff positions from instruments.DRUM_MAP, notehead included
_XSTICK = ('C', 5, 'x')
_BELL = ('F', 5, 'diamond')
_COWBELL = ('B', 5, 'triangle')
_RIDE = ('F', 5, 'x')
_HATF = ('D', 4, 'x')
_HAT = ('G', 5, 'x')
_SNARE = ('C', 5, 'normal')
_KICK = ('F', 4, 'normal')
_CRASH = ('A', 5, 'x')


def _drums(bar, absbar, feel, hits):
    beat = bar.div * 4 // bar.den
    half = beat // 2
    if hits is not None:
        for b in hits:
            at = int(round((b - 1) * beat))
            bar.add(at, half, ('u', _CRASH, None))
            bar.add(at, half, ('u', _KICK, None))
        return
    if _new_style(feel, bar):
        _styled_drums(bar, absbar, *_new_style(feel, bar))
        return
    if bar.den == 8 and bar.num % 3 == 0:
        pulse = 3 * (bar.div // 2)
        for p in range(bar.num // 3):
            at = p * pulse
            third = pulse // 3
            bar.add(at, third, ('u', _RIDE, None))
            bar.add(at + third, third, ('u', _RIDE, 58))
            bar.add(at + 2 * third, third, ('u', _RIDE, 66))
            if p % 2 == 0:
                bar.add(at, pulse, ('u', _KICK, 78))
            else:
                bar.add(at, pulse, ('u', _SNARE, 80))
        return
    if _is_swing(feel):
        for b in range(bar.num):
            at = b * beat
            if b % 2 == 1:               # the skip beat: ding, ding-ga
                bar.add(at, half, ('u', _RIDE, None))
                bar.add(at + half, half, ('u', _RIDE, 60))
                bar.add(at, half, ('u', _HATF, 66))
            else:
                bar.add(at, beat, ('u', _RIDE, None))
            bar.add(at, half, ('u', _KICK, 28))   # feathered, felt
        spot = (absbar * 7) % 4
        if spot < 2 and bar.num >= 4:
            bar.add((1 + 2 * spot) * beat + half, half,
                    ('u', _SNARE, 54))
        return
    # straight: backbeat
    for b in range(bar.num):
        at = b * beat
        bar.add(at, half, ('u', _HAT, 66))
        bar.add(at + half, half, ('u', _HAT, 50))
        if b % 2 == 0:
            bar.add(at, half, ('u', _KICK, 85))
        else:
            bar.add(at, half, ('u', _SNARE, 82))
    if bar.num >= 4 and absbar % 4 == 0:
        bar.add((bar.num - 1) * beat + half, half, ('u', _KICK, 68))


def _styled_drums(bar, absbar, style, traits):
    beat = bar.div * 4 // bar.den
    n = bar.num
    eighths = [1 + i / 2 for i in range(2 * n)]
    sixteenths = [1 + i / 4 for i in range(4 * n)]
    back = [b for b in (2, 4) if b <= n]
    if style == 'swing':
        if 'double' in traits:           # the ride skips on every beat
            for b in range(1, n + 1):
                _pattern(bar, beat, [(b, .5, 76), (b + .5, .5, 60)], _RIDE)
        else:
            soft = 'ballad' in traits
            for b in range(1, n + 1):
                _pattern(bar, beat, [(b, 1, 48 if soft else 70)], _RIDE)
                if b % 2 == 0 and not soft:
                    _pattern(bar, beat, [(b + .5, .5, 52)], _RIDE)
        _pattern(bar, beat, [(b, .5, 60) for b in back], _HATF)
        if 'ballad' in traits:           # brushes, felt more than heard
            _pattern(bar, beat, [(b, .5, 30) for b in back], _SNARE)
        else:
            _pattern(bar, beat, [(b, .5, 22) for b in range(1, n + 1)],
                     _KICK)
        return
    if style == 'bossa':
        _pattern(bar, beat, [(b, .5, 60 if b % 1 == 0 else 46)
                             for b in eighths], _RIDE)
        _pattern(bar, beat, [(1, .5, 70), (2.5, .5, 52), (3, .5, 70),
                             (4.5, .5, 52)], _KICK)
        clave = ([(1, .5, 72), (2.5, .5, 72), (4, .5, 72)]
                 if absbar % 2 else [(2, .5, 72), (3.5, .5, 72)])
        _pattern(bar, beat, clave, _XSTICK)
        return
    if style == 'samba':
        _pattern(bar, beat, [(b, .25, 58 if (b * 4) % 4 == 1 else 42)
                             for b in sixteenths], _HAT)
        _pattern(bar, beat, [(1, .5, 58), (2, .5, 88), (3, .5, 58),
                             (4, .5, 88)], _KICK)
        _pattern(bar, beat, [(1.75, .25, 64), (2.5, .25, 64),
                             (3.75, .25, 64), (4.5, .25, 64)], _XSTICK)
        return
    if style == 'latin':
        cascara = ([(1, .5, 72), (2, .5, 60), (3, .5, 72), (3.5, .5, 60),
                    (4.5, .5, 60)] if absbar % 2 else
                   [(1, .5, 72), (2, .5, 60), (2.5, .5, 60),
                    (3.5, .5, 60), (4.5, .5, 60)])
        _pattern(bar, beat, cascara, _BELL)
        _pattern(bar, beat, [(2.5, .5, 60), (4, .5, 72)], _KICK)
        clave = ([(2, .5, 74), (3, .5, 74)] if absbar % 2 else
                 [(1, .5, 74), (2.5, .5, 74), (4, .5, 74)])
        _pattern(bar, beat, clave, _XSTICK)
        return
    # straight and funk, with half time and double time bending them
    hats = sixteenths if (style == 'funk' or 'double' in traits) \
        else eighths
    _pattern(bar, beat, [(b, .25 if len(hats) > 2 * n else .5,
                          70 if b % 1 == 0 else 46) for b in hats], _HAT)
    if 'half' in traits:
        snare = [(3, .5, 94)] if n >= 4 else [(2, .5, 94)]
        kick = [(1, .5, 88)] + ([(2.75, .25, 66), (3.5, .5, 62)]
                                if style == 'funk' and n >= 4 else [])
    elif style == 'funk':
        snare = [(b, .5, 95) for b in back]
        kick = [(1, .5, 90), (2.75, .25, 72), (3.5, .5, 78)]
    else:
        snare = [(b, .5, 84) for b in back]
        kick = [(b, .5, 86) for b in range(1, n + 1, 2)]
    _pattern(bar, beat, snare, _SNARE)
    _pattern(bar, beat, kick, _KICK)
    if style == 'funk':                  # ghosts between the backbeats
        _pattern(bar, beat, [(2.75, .25, 28), (3.25, .25, 26),
                             (4.75, .25, 28)], _SNARE)


# ------------------------------------------------ the percussion section
#
# Each hand instrument's sounds, as staff positions its own part decodes
# (chartaudio.hand_midi), and what it plays in each feel: beat (1-based),
# length in beats, which sound, velocity. Two-bar figures (clave, the
# cascara, the bossa clave) turn on the bar number.
_PERC_SOUNDS = {
    'conga': {'mute': ('A', 4, 'x'), 'open': ('A', 4, 'normal'),
              'low': ('F', 4, 'normal')},
    'bongo': {'hi': ('E', 5, 'normal'), 'lo': ('C', 5, 'normal')},
    'timbale': {'hi': ('D', 5, 'normal'), 'lo': ('B', 4, 'normal')},
    'cowbell': {'main': ('B', 5, 'triangle')},
    'triangle': {'open': ('B', 5, 'triangle'), 'mute': ('B', 5, 'x')},
    'agogo': {'hi': ('A', 5, 'triangle'), 'lo': ('F', 5, 'triangle')},
    'claves': {'main': ('D', 5, 'x')},
    'guiro': {'long': ('C', 5, 'normal'), 'short': ('C', 5, 'x')},
    'woodblock': {'hi': ('E', 5, 'x'), 'lo': ('C', 5, 'x')},
    'shaker': {'main': ('G', 5, 'x')},
    'tambourine': {'main': ('E', 5, 'x')},
}


def _perc_kind(sound_id):
    s = (sound_id or '').lower()
    for key, kind in (('conga', 'conga'), ('bongo', 'bongo'),
                      ('timbale', 'timbale'), ('cowbell', 'cowbell'),
                      ('triangle', 'triangle'), ('agogo', 'agogo'),
                      ('claves', 'claves'), ('guiro', 'guiro'),
                      ('wood-block', 'woodblock'), ('rattle.', 'shaker'),
                      ('tambourine', 'tambourine')):
        if key in s:
            return kind
    return None


def _sixteenths(n, on=64, off=40, sound='main'):
    return [(1 + i / 4, .25, sound, on if i % 4 == 0 else
             (off + 10 if i % 2 == 0 else off)) for i in range(4 * n)]


def _eighths(n, on=66, off=44, sound='main'):
    return [(1 + i / 2, .5, sound, on if i % 2 == 0 else off)
            for i in range(2 * n)]


def _son_clave(absbar):
    # 2-3: the two side, then the three side
    return ([(2, .5, 'main', 80), (3, .5, 'main', 80)] if absbar % 2
            else [(1, .5, 'main', 80), (2.5, .5, 'main', 80),
                  (4, .5, 'main', 80)])


def perc_pattern(kind, style, traits, absbar, n=4):
    """What this instrument plays in this feel, for one bar of n
    beats: [(beat, length, sound, velocity)]."""
    soft = 'ballad' in traits
    if kind == 'conga':
        if style == 'latin':
            last = 'low' if absbar % 2 else 'open'
            return [(1, .5, 'mute', 40), (1.5, .5, 'mute', 30),
                    (2, .5, 'mute', 92), (2.5, .5, 'mute', 30),
                    (3, .5, 'mute', 40), (3.5, .5, 'mute', 30),
                    (4, .5, 'open', 88), (4.5, .5, last, 84)]
        if style == 'bossa':
            return [(1, .5, 'mute', 40), (2, .5, 'open', 68),
                    (2.5, .5, 'mute', 34), (3.5, .5, 'mute', 40),
                    (4, .5, 'open', 68)]
        if style == 'samba':
            return [(1, .5, 'low', 70), (2, .5, 'open', 90),
                    (2.5, .5, 'mute', 45), (3, .5, 'low', 70),
                    (4, .5, 'open', 90), (4.5, .5, 'mute', 45)]
        if style == 'funk':
            return [(1, .5, 'open', 82), (1.75, .25, 'mute', 55),
                    (2.5, .5, 'open', 74), (3.25, .25, 'mute', 50),
                    (3.5, .5, 'low', 80), (4, .5, 'mute', 60),
                    (4.5, .5, 'open', 74)]
        if 'half' in traits:
            return [(1, .5, 'low', 75), (2.5, .5, 'open', 60),
                    (3, .5, 'mute', 86), (4.5, .5, 'open', 60)]
        if style == 'swing':
            if soft or 'two' in traits:
                return [(1, 1, 'low', 44), (3, 1, 'open', 44)]
            return [(2, .5, 'mute', 45), (4, .5, 'open', 64),
                    (4.5, .5, 'low', 58)]
        return [(1, .5, 'low', 70), (2, .5, 'mute', 60),
                (2.5, .5, 'open', 70), (3, .5, 'low', 70),
                (4, .5, 'mute', 60), (4.5, .5, 'open', 70)]
    if kind == 'bongo':
        martillo = [(1, .5, 'hi', 80), (1.5, .5, 'hi', 45),
                    (2, .5, 'hi', 62), (2.5, .5, 'hi', 45),
                    (3, .5, 'hi', 72), (3.5, .5, 'hi', 45),
                    (4, .5, 'lo', 86), (4.5, .5, 'hi', 45)]
        if style in ('latin', 'straight') and not traits:
            return martillo
        if style in ('bossa', 'samba'):
            return [(b, l, snd, int(v * .78)) for b, l, snd, v in martillo]
        if style == 'funk':
            return [(1, .5, 'hi', 82), (1.75, .25, 'lo', 60),
                    (2.5, .5, 'hi', 74), (3.25, .25, 'hi', 55),
                    (3.75, .25, 'lo', 70), (4.5, .5, 'hi', 74)]
        return [(2, .5, 'hi', 48), (4, .5, 'lo', 58)]
    if kind == 'timbale':
        if style == 'latin':
            casc = ([(1, .5, 'hi', 56), (2, .5, 'hi', 44),
                     (3, .5, 'hi', 56), (3.5, .5, 'hi', 44),
                     (4.5, .5, 'hi', 44)] if absbar % 2 else
                    [(1, .5, 'hi', 56), (2, .5, 'hi', 44),
                     (2.5, .5, 'hi', 44), (3.5, .5, 'hi', 44),
                     (4.5, .5, 'hi', 44)])
            return casc + ([(4, .5, 'lo', 84)] if absbar % 4 == 3 else [])
        if style in ('funk', 'straight') and not soft:
            return [(2, .5, 'hi', 80), (4, .5, 'hi', 80)]
        if style == 'samba':
            return [(2, .5, 'lo', 72), (4, .5, 'lo', 72)]
        return [(4, .5, 'lo', 48)]
    if kind == 'cowbell':
        if style == 'latin':
            return [(1, .5, 'main', 92), (2, .5, 'main', 70),
                    (2.5, .5, 'main', 58), (3, .5, 'main', 92),
                    (4, .5, 'main', 70), (4.5, .5, 'main', 58)]
        if style == 'samba':
            return [(1, .5, 'main', 72), (1.75, .25, 'main', 60),
                    (2.5, .5, 'main', 72), (3, .5, 'main', 72),
                    (3.75, .25, 'main', 60), (4.5, .5, 'main', 72)]
        if style == 'funk':
            return _eighths(n, 82, 58)
        if style == 'straight' and not soft:
            return [(b, .5, 'main', 72) for b in range(1, n + 1)]
        return [(b, .5, 'main', 50) for b in (2, 4)]
    if kind == 'claves':
        if style == 'latin':
            return _son_clave(absbar)
        if style == 'bossa':
            return ([(1, .5, 'main', 76), (2.5, .5, 'main', 76),
                     (4, .5, 'main', 76)] if absbar % 2 else
                    [(2, .5, 'main', 76), (3.5, .5, 'main', 76)])
        if style == 'samba':
            return [(1.75, .25, 'main', 70), (2.5, .5, 'main', 70),
                    (3.75, .25, 'main', 70), (4.5, .5, 'main', 70)]
        return [(b, .5, 'main', 60 if soft else 72) for b in (2, 4)]
    if kind in ('shaker',):
        if soft:
            return [(b, 1, 'main', 42) for b in range(1, n + 1)]
        if style == 'latin' or style == 'swing':
            return _eighths(n, 66, 44)
        return _sixteenths(n)
    if kind == 'tambourine':
        if style == 'samba':
            return _sixteenths(n, 70, 38)
        if style in ('latin', 'bossa'):
            return _eighths(n, 50, 34)
        back = [(b, .5, 'main', 92) for b in (2, 4)]
        if 'half' in traits:
            back = [(3, .5, 'main', 94)]
        if style == 'funk' or style == 'straight':
            return back + [(b + .5, .5, 'main', 36)
                           for b in range(1, n + 1)]
        return [(b, l, s_, 64 if soft else v) for b, l, s_, v in back]
    if kind == 'guiro':
        if style in ('latin', 'bossa'):
            v = 60 if style == 'bossa' else 76
            return [(1, 1, 'long', v), (2, .5, 'short', v - 10),
                    (2.5, .5, 'short', v - 16), (3, 1, 'long', v),
                    (4, .5, 'short', v - 10), (4.5, .5, 'short', v - 16)]
        if style == 'swing':
            return [(2, .5, 'short', 52), (4, .5, 'short', 52)]
        return [(1, 1, 'long', 68), (2, .5, 'short', 58),
                (3, 1, 'long', 68), (4, .5, 'short', 58)]
    if kind == 'agogo':
        if style in ('samba', 'latin', 'funk'):
            return [(1, .5, 'hi', 80), (1.5, .5, 'hi', 60),
                    (2, .5, 'lo', 76), (2.75, .25, 'hi', 62),
                    (3.5, .5, 'lo', 76), (4, .5, 'hi', 70),
                    (4.5, .5, 'lo', 64)]
        return [(1, .5, 'hi', 56), (3, .5, 'lo', 56)]
    if kind == 'triangle':
        if style == 'swing':
            return [(b, .5, 'open', 50) for b in (2, 4)]
        return [(1 + i / 2, .5, 'mute' if i % 2 == 0 else 'open',
                 56 if i % 2 == 0 else 70) for i in range(2 * n)]
    if kind == 'woodblock':
        if style == 'latin':
            return [(b, l, 'hi', v) for b, l, _s, v in _son_clave(absbar)]
        return [(b, .5, 'hi' if b % 2 else 'lo', 66)
                for b in range(1, n + 1)]
    return []


def _perc(bar, absbar, feel, sound_id, hits):
    kind = _perc_kind(sound_id)
    if kind is None:
        return
    sounds = _PERC_SOUNDS[kind]
    first = next(iter(sounds.values()))
    beat = bar.div * 4 // bar.den
    if hits is not None:
        for b in hits:
            bar.add(int(round((b - 1) * beat)), beat // 2,
                    ('u', first, 96))
        return
    if bar.den == 8 and bar.num % 3 == 0:
        # compound time: the 6/8 bell for the bells and sticks, a pulse
        # on the drums, eighths on the shakers
        eighth = bar.div // 2
        per = bar.num
        if kind in ('cowbell', 'agogo', 'claves', 'woodblock', 'guiro'):
            hits12 = (0, 2, 4, 5, 7, 9, 11)
            half = [h - (per if absbar % 2 else 0) for h in hits12]
            snd = [k for k in sounds][0]
            for h in half:
                if 0 <= h < per:
                    bar.add(h * eighth, eighth, ('u', sounds[snd],
                                                 84 if h % 3 == 0 else 64))
        elif kind in ('conga', 'bongo', 'timbale'):
            keys = list(sounds)
            for p in range(0, per, 3):
                bar.add(p * eighth, eighth, ('u', sounds[keys[0]], 50))
                bar.add((p + 2) * eighth, eighth,
                        ('u', sounds[keys[-1]], 84))
        else:
            for e in range(per):
                bar.add(e * eighth, eighth, ('u', first,
                                             66 if e % 3 == 0 else 42))
        return
    style, traits = style_of(feel)
    for b, ln, snd, vel in perc_pattern(kind, style, traits, absbar,
                                        bar.num):
        if b > bar.num + 0.99:
            continue
        bar.add(int(round((b - 1) * beat)), max(1, int(round(ln * beat))),
                ('u', sounds.get(snd, first), vel))


def _styled_bass(bar, state, sec, off, absbar, chords, style, traits,
                 put):
    beat = bar.div * 4 // bar.den
    n = bar.num
    prev = state.get('bass', 36)

    def tone(b, what):
        c = _chord_at(chords, b)
        root = _bass_pc(c)
        if what == 'r':
            return _near(root, prev)
        if what == 'o':
            return _near(root, prev) + 12
        if what == 'f':
            return _near((_root_pc(c) + 7) % 12, prev)
        if what == '7':
            ts = _tones(c)
            sev = next((t for t in (10, 11) if t in ts), 7)
            return _near((_root_pc(c) + sev) % 12, prev)
        if what == 'next':
            return _near(_next_root(sec, off, chords), prev)
        return _near(root, prev)

    if style == 'swing' and 'double' in traits:
        for i in range(2 * n):           # walking in eighths
            b = 1 + i / 2
            c = _chord_at(chords, b)
            ts = sorted({(_root_pc(c) + t) % 12 for t in _tones(c)})
            pc = _bass_pc(c) if i % 4 == 0 else ts[(i // 1) % len(ts)]
            prev = put(int(round((b - 1) * beat)), beat // 2,
                       _near(pc, prev))
        return
    if style == 'swing' and 'ballad' in traits:
        marks = sorted({max(1.0, b) for b, c in chords})
        for i, b in enumerate(marks):
            end = marks[i + 1] if i + 1 < len(marks) else n + 1
            prev = put(int(round((b - 1) * beat)),
                       int(round((end - b) * beat)), tone(b, 'r'), 70)
        return
    if style == 'swing':                  # two feel: 1 and 3
        for b in range(1, n + 1, 2):
            last = b + 2 > n
            if last and absbar % 2 == 0 and n >= 4:
                tgt = tone(b, 'next')
                midi = tgt + (1 if absbar % 4 else -1)
            else:
                midi = tone(b, 'r' if b == 1 else 'f')
            prev = put(int(round((b - 1) * beat)), 2 * beat - beat // 4,
                       midi)
        return
    pats = {
        'bossa': [(1, 1.5, 'r'), (2.5, .5, 'r'), (3, 1.5, 'f'),
                  (4.5, .5, 'f')],
        'samba': [(1, 1, 'r', 70), (2, 1, 'f', 92), (3, 1, 'r', 70),
                  (4, 1, 'f', 92)],
        'latin': [(2.5, 1.5, 'f'), (4, 1, 'next')],
        'funk': [(1, .5, 'r'), (1.75, .25, 'r'), (2.5, .5, 'o'),
                 (3.5, .25, 'r'), (3.75, .25, 'r'), (4.5, .5, '7')],
    }
    if 'half' in traits:
        pat = ([(1, 1.5, 'r'), (2.75, .25, 'r'), (3, .5, 'o'),
                (4, .5, 'f'), (4.5, .5, '7')] if style == 'funk' else
               [(1, 2.5, 'r'), (3.5, .5, 'f'), (4, 1, 'r')])
    else:
        pat = pats.get(style) or [(1, 2, 'r'), (3, 2, 'f')]
    for item in pat:
        b, ln, what = item[:3]
        vel = item[3] if len(item) > 3 else None
        if b > n + 0.99:
            continue
        prev = put(int(round((b - 1) * beat)),
                   max(1, int(round(ln * beat)) - beat // 8),
                   tone(b, what), vel)


def _bass(bar, state, sec, off, absbar, feel, chords):
    if not chords:
        return
    beat = bar.div * 4 // bar.den
    lo, hi = 28, 55
    prev = state.get('bass', 36)

    def put(at, ticks, midi, vel=None):
        midi = min(max(midi, lo), hi)
        bar.add(at, ticks, ('p', midi, vel))
        state['bass'] = midi
        return midi

    if state.get('hits') is not None:
        for b in state['hits']:
            c = _chord_at(chords, b)
            prev = put(int(round((b - 1) * beat)), beat // 2,
                       _near(_bass_pc(c), prev))
        return
    if _new_style(feel, bar):
        _styled_bass(bar, state, sec, off, absbar, chords,
                     *_new_style(feel, bar), put)
        return
    if _is_swing(feel) and bar.den == 4:
        target = _near(_next_root(sec, off, chords), prev)
        for b in range(bar.num):
            c = _chord_at(chords, b + 1.0)
            tones = sorted({(_root_pc(c) + s) % 12 for s in _tones(c)})
            if b == 0:
                midi = _near(_bass_pc(c), prev)
            elif b == bar.num - 1:
                midi = target + (1 if absbar % 2 else -1)
            else:
                opts = sorted((_near(pc, prev) for pc in tones),
                              key=lambda o: (o == prev, abs(o - prev)))
                midi = opts[min(b % 2, len(opts) - 1)]
            prev = put(b * beat, beat, midi)
        return
    if bar.den == 8 and bar.num % 3 == 0:
        pulse = 3 * (bar.div // 2)
        for p in range(bar.num // 3):
            c = _chord_at(chords, p * 3 + 1.0)
            pc = _bass_pc(c) if p % 2 == 0 else (_root_pc(c) + 7) % 12
            prev = put(p * pulse, pulse, _near(pc, prev))
        return
    for b in range(bar.num):
        c = _chord_at(chords, b + 1.0)
        if b % 2 == 0:
            prev = put(b * beat, beat * 2 - bar.div // 2,
                       _near(_bass_pc(c), prev))
        elif bar.num >= 4 and b == bar.num - 1 and absbar % 2 == 0:
            prev = put(b * beat + beat // 2, beat // 2,
                       _near((_root_pc(c) + 7) % 12, prev), 60)


_COMP_RHYTHMS = (
    ((2.5, 0.5), (4.0, 1.0)),
    ((1.0, 1.0), (3.5, 0.5)),
    ((2.0, 2.0),),
    ((1.5, 0.5), (4.0, 1.0)),
)


def _comp(bar, state, absbar, feel, chords, sound_id):
    if not chords:
        return
    beat = bar.div * 4 // bar.den
    anchor = state.get('comp', 62)
    s = (sound_id or '').lower()

    def voicing(c):
        v = sorted(_near(pc, anchor) for pc in _guide(c))
        state['comp'] = sum(v) // len(v)
        return v

    def put(at, ticks, notes, vel=None):
        for n in notes:
            bar.add(at, ticks, ('p', n, vel))

    if state.get('hits') is not None:
        for b in state['hits']:
            put(int(round((b - 1) * beat)), beat // 2,
                voicing(_chord_at(chords, b)))
        return
    ns = _new_style(feel, bar)
    if ns and 'organ' not in s:
        style, traits = ns
        rhythm = {
            'bossa': ([(1, 1), (2.5, .5), (3.5, 1)] if absbar % 2 else
                      [(1.5, .5), (3, .5), (4.5, .5)]),
            'samba': [(1, .25), (1.75, .25), (2.5, .25), (3, .25),
                      (3.75, .25), (4.5, .25)],
            'latin': ([(1, .5), (2.5, .5), (4, .5)] if absbar % 2 else
                      [(1.5, .5), (3, .5), (4.5, .5)]),
            'funk': [(1, .25), (1.75, .25), (2.5, .25), (3.75, .25),
                     (4.5, .25)],
        }.get(style)
        if rhythm is None and ('ballad' in traits or 'half' in traits):
            rhythm = []                  # held chords, below
        if rhythm is None and style == 'swing':
            rhythm = ([(2, .5), (4, .5)] if 'two' in traits else
                      [(b + .5, .5) for b in range(1, bar.num + 1)])
        if rhythm:
            for b, ln in rhythm:
                if b > bar.num + 0.99:
                    continue
                put(int(round((b - 1) * beat)),
                    max(1, int(round(ln * beat))),
                    voicing(_chord_at(chords, b)),
                    vel=80 if style == 'funk' else 70)
            return
        marks = sorted({max(1.0, b) for b, c in chords})
        for i, b in enumerate(marks):
            at = int(round((b - 1) * beat))
            end = int(round((marks[i + 1] - 1) * beat)) \
                if i + 1 < len(marks) else bar.barlen
            put(at, end - at, voicing(_chord_at(chords, b)), vel=58)
        return
    if 'guitar' in s and _is_swing(feel) and bar.den == 4:
        for b in range(bar.num):
            put(b * beat, beat,
                voicing(_chord_at(chords, b + 1.0))[:2],
                vel=76 if b % 2 else 66)
        return
    if 'organ' in s or not _is_swing(feel):
        marks = sorted({max(1.0, b) for b, c in chords})
        for i, b in enumerate(marks):
            at = int(round((b - 1) * beat))
            end = int(round((marks[i + 1] - 1) * beat)) \
                if i + 1 < len(marks) else bar.barlen
            put(at, end - at, voicing(_chord_at(chords, b)))
        return
    for b, ticks_beats in _COMP_RHYTHMS[absbar % len(_COMP_RHYTHMS)]:
        if b > bar.num:
            continue
        at = int(round((b - 1) * beat))
        put(at, int(ticks_beats * beat),
            voicing(_chord_at(chords, b)), vel=72)


def _horn_hits(bar, state, chords, hits, bmeter):
    """A horn's kicks, sounding: short guide tones on the named
    beats — a shout chorus must never be silent in the listen
    (Matthew's ear, 2026-09-22: 'do not hear any horns')."""
    if not chords or not hits:
        return
    beat = bar.div * 4 // bar.den
    anchor = state.get('horn', 65)          # around F4, mid-horn
    for b in hits:
        c = _chord_at(chords, b)
        midi = _near(_guide(c)[0], anchor)
        midi = min(max(midi, 55), 79)
        bar.add(int(round((b - 1) * beat)), beat // 2,
                ('p', midi, 90))
        state['horn'] = anchor = midi


def realize(kind, arg, sound_id, clef, staves, fifths, sec, off,
            absbar, bmeter, div, feel, state, governing,
            written_shift=0):
    """One realized bar of the listening document, or None when this
    part has no rhythm-section role. state is per-part and mutable;
    governing is the chord carried in from earlier bars.
    written_shift is the part's transposition: the groove thinks in
    sounding pitches, the bar is written for the part's player."""
    role = role_of(sound_id, clef)
    if role is None and kind != 'hits':
        return None
    chords = _chords_in(sec, off, governing)
    state['hits'] = None
    if kind == 'hits':
        hmap, _words = arg
        state['hits'] = hmap.get(off + 1, hmap.get(None)) or []
    bar = Bar(div, bmeter, fifths, staves, shift=written_shift)
    if role is None:
        # a horn with kicks: the kicks play
        _horn_hits(bar, state, chords, state['hits'], bmeter)
        state['hits'] = None
        return bar.xml() if bar.onsets else None
    if role == 'perc':
        _perc(bar, absbar, feel, sound_id, state['hits'])
    elif role == 'drums':
        _drums(bar, absbar, feel, state['hits'])
    elif role == 'bass':
        _bass(bar, state, sec, off, absbar, feel, chords)
    else:
        _comp(bar, state, absbar, feel, chords, sound_id)
    state['hits'] = None
    return bar.xml()
