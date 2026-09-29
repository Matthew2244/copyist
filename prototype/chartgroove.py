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
        kind, what, vel = note[:3]
        arts = note[3] if len(note) > 3 else ()
        ties = note[4] if len(note) > 4 else ()
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
        for tt in ties:                  # a long note over the barline
            out.append(f'        <tie type="{tt}"/>')
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
        if arts:
            # a fall, doit or scoop the listen performs (endings)
            out.append('        <notations><articulations>'
                       + ''.join(f'<{a}/>' for a in arts)
                       + '</articulations></notations>')
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
    # swung funk is its own feel, not swing: the funk band with its
    # subdivision swung — Purdie's half-time shuffle, Matt's Blues'
    # head (Matthew, 2026-09-28: "straight funk, swung funk ... Matt's
    # Blues is swung funk"). Plain "funk" stays straight, even in a
    # swing tune.
    if 'funk' in f and re.search(r'\bswung\b|\bswing(?:ing)?\b|'
                                 r'\bshuffle\b', f) and \
            not re.search(r'\bstraight\b', f):
        traits.add('swung')
    if re.search(r'\bjazz waltz\b', f) or ('waltz' in f and _is_swing(f)):
        traits.add('swung')
    if 'waltz' in f:
        style = 'waltz'
    elif re.search(r'second[ -]?line|new orleans|nola\b', f):
        style = 'secondline'
    elif re.search(r'reggae|one[ -]?drop|rocksteady|ska\b', f):
        style = 'reggae'
    elif 'motown' in f:
        style = 'motown'
    elif re.search(r'hip[ -]?hop|boom[ -]?bap|\bdilla\b', f):
        style = 'hiphop'
        if re.search(r'\bswung\b|\bswing(?:ing)?\b|\bdilla\b', f):
            traits.add('swung')
    elif 'bossa' in f:
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
    elif re.search(r'\bshuffle\b', f) and not traits & {'two', 'ballad',
                                                         'double'}:
        # a shuffle is not swing: the triplet pattern on the hats and
        # snare, the bass rocking root-3-5-6. Its eighths swing.
        style = 'shuffle'
    elif _is_swing(f) or traits & {'two', 'ballad'}:
        style = 'swing'
    else:
        style = 'straight'
    return style, traits


def _new_style(feel, bar):
    """The styles this module learned 2026-09-28, in 2- and 4-beat
    quarter-note bars only; None leaves the original swing/straight
    reading (and its bytes) exactly as it was."""
    style, traits = style_of(feel)
    if style == 'waltz' and bar.den == 4 and bar.num == 3:
        return style, traits
    if bar.den != 4 or bar.num not in (2, 4):
        return None
    if style in ('bossa', 'samba', 'latin', 'funk', 'shuffle',
                 'secondline', 'reggae', 'motown', 'hiphop'):
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
    if style == 'waltz':
        if 'swung' in traits:            # jazz waltz: ding, ding-ga ding
            _pattern(bar, beat, [(1, 1, 72), (2, .5, 60), (2.5, .5, 54),
                                 (3, 1, 64)], _RIDE)
            _pattern(bar, beat, [(2, .5, 58), (3, .5, 50)], _HATF)
            _pattern(bar, beat, [(1, .5, 30)], _KICK)
            if absbar % 4 == 3:
                _pattern(bar, beat, [(3.5, .5, 48)], _SNARE)
        else:                            # oom-pah-pah
            _pattern(bar, beat, [(1, .5, 80)], _KICK)
            _pattern(bar, beat, [(2, .5, 60), (3, .5, 56)], _XSTICK)
            _pattern(bar, beat, [(b, .5, 58) for b in (1, 2, 3)], _HAT)
        return
    if style == 'shuffle':
        # the eighths swing in the listen; hats ride every one, the
        # snare's ghost on each "let" and the backbeat on 2 and 4
        _pattern(bar, beat, [(b, .5, 72 if b % 1 == 0 else 52)
                             for b in eighths], _HAT)
        _pattern(bar, beat, [(b, .5, 90) for b in back], _SNARE)
        _pattern(bar, beat, [(b + .5, .5, 30) for b in range(1, n + 1)
                             if b not in back], _SNARE)
        _pattern(bar, beat, [(1, .5, 86), (3, .5, 80)]
                 + ([(2.5, .5, 60)] if absbar % 2 else []), _KICK)
        return
    if style == 'secondline':
        # the parade: snare rolling off the and of 1 into 2 and 4, the
        # bass drum and its cymbal on the push beats
        _pattern(bar, beat, [(1.5, .5, 68), (2, .5, 92), (2.75, .25, 46),
                             (3.5, .5, 70), (4, .5, 92), (4.5, .5, 58),
                             (4.75, .25, 50)], _SNARE)
        kick = [(1, .5, 88), (2.5, .5, 72), (3, .5, 66), (4.5, .5, 74)]
        _pattern(bar, beat, kick, _KICK)
        _pattern(bar, beat, [(b, ln, v - 20) for b, ln, v in kick], _RIDE)
        return
    if style == 'reggae':
        # one drop: nothing on 1, kick and rim together on 3
        _pattern(bar, beat, [(b, .5, 62 if b % 1 == 0 else 44)
                             for b in eighths], _HAT)
        _pattern(bar, beat, [(3, .5, 90)], _KICK)
        _pattern(bar, beat, [(3, .5, 86)], _XSTICK)
        if absbar % 4 == 0:
            _pattern(bar, beat, [(4.5, .5, 52)], _XSTICK)
        return
    if style == 'motown':
        # the snare on all four, 2 and 4 on top; eighth hats
        _pattern(bar, beat, [(b, .5, 64 if b % 1 == 0 else 46)
                             for b in eighths], _HAT)
        _pattern(bar, beat, [(b, .5, 92 if b in back else 64)
                             for b in range(1, n + 1)], _SNARE)
        _pattern(bar, beat, [(1, .5, 84), (2.5, .5, 58), (3, .5, 78),
                             (4.5, .5, 56)], _KICK)
        return
    if style == 'hiphop':
        # boom bap: the kick off 1, the and-a of 1, the and of 3
        _pattern(bar, beat, [(b, .5, 66 if b % 1 == 0 else 48)
                             for b in eighths], _HAT)
        _pattern(bar, beat, [(b, .5, 96) for b in back], _SNARE)
        _pattern(bar, beat, [(1, .5, 96), (1.75, .25, 70), (3.5, .5, 86)]
                 + ([(4.75, .25, 60)] if absbar % 2 else []), _KICK)
        return
    # straight and funk, with half time and double time bending them.
    # Half time halves the hats too: sixteenths of the half-time pulse
    # are eighths of the written bar — sixteenths here played the funk
    # at double speed (Matt's Blues at 210, 2026-09-28: "the drums in
    # the funky section are playing double time")
    hats = sixteenths if ((style == 'funk' or 'double' in traits)
                          and 'half' not in traits) else eighths
    _pattern(bar, beat, [(b, .25 if len(hats) > 2 * n else .5,
                          70 if b % 1 == 0 else 46) for b in hats], _HAT)
    if 'half' in traits:
        snare = [(3, .5, 94)] if n >= 4 else [(2, .5, 94)]
        kick = [(1, .5, 88)] + ([(2.5, .5, 66), (4.5, .5, 62)]
                                if style == 'funk' and n >= 4 else [])
    elif style == 'funk':
        snare = [(b, .5, 95) for b in back]
        kick = [(1, .5, 90), (2.75, .25, 72), (3.5, .5, 78)]
    else:
        snare = [(b, .5, 84) for b in back]
        kick = [(b, .5, 86) for b in range(1, n + 1, 2)]
    _pattern(bar, beat, snare, _SNARE)
    _pattern(bar, beat, kick, _KICK)
    if style == 'funk' and 'half' in traits:
        _pattern(bar, beat, [(4, .5, 28)], _SNARE)   # one ghost, felt
    elif style == 'funk':                # ghosts between the backbeats
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
        if what == 'appr':               # a half step into the next root
            nxt = _near(_next_root(sec, off, chords), prev)
            return nxt + (1 if nxt <= prev else -1)
        return _near(root, prev)

    if style == 'shuffle':
        # the boogie: root, 3, 5, 6 up one bar, b7, 6, 5, 3 down the next
        c = _chord_at(chords, 1)
        root = _near(_bass_pc(c), prev)
        if root > 43:
            root -= 12
        third = 3 if 3 in _tones(c) and 4 not in _tones(c) else 4
        up = [0, third, 7, 9]
        line = up if absbar % 2 else [10, 9, 7, third]
        for i, iv in enumerate(line[:n]):
            put(int(i * beat), beat - beat // 8, root + iv)
        state['bass'] = root
        return
    if style == 'waltz':
        if 'swung' in traits:            # walking in three
            c = _chord_at(chords, 1)
            ts = sorted({(_root_pc(c) + t) % 12 for t in _tones(c)})
            got = put(0, beat - beat // 8, tone(1, 'r'))
            prev = got
            mid = _near(ts[(absbar % (len(ts) - 1)) + 1], prev)
            prev = put(beat, beat - beat // 8, mid)
            prev = put(2 * beat, beat - beat // 8, tone(3, 'appr'))
        else:                            # the oom, on 1
            prev = put(0, beat - beat // 8, tone(1, 'r' if absbar % 2
                                               else 'f'))
        state['bass'] = prev
        return
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
        # the sousaphone's parade line
        'secondline': [(1, 1.5, 'r'), (2.5, .5, 'f'), (3, 1, 'f'),
                       (4, .5, 'r'), (4.5, .5, 'appr')],
        # one drop: the bass carries the tune, leaves room on 1
        'reggae': [(1, 1.5, 'r', 84), (2.5, .5, 'r'), (3.5, .5, 'f'),
                   (4, 1, '7')],
        'motown': [(1, 1, 'r'), (2, .5, 'r'), (2.5, .5, 'f'), (3, 1, 'o'),
                   (4, .5, 'f'), (4.5, .5, 'appr')],
        'hiphop': [(1, .75, 'r', 92), (1.75, .25, 'r'), (3.5, 1, 'f')],
    }
    if 'half' in traits:
        # four notes, the way a player lays half time down: the root
        # held, the fifth on the and of 2, the root on 3, a half step
        # into the next bar (the shape of Jeremy Hegg's funk head)
        pat = ([(1, 1.5, 'r'), (2.5, .5, 'f'), (3, 1, 'r'),
                (4, 1, 'appr')] if style == 'funk' else
               [(1, 2.5, 'r'), (3.5, .5, 'f'), (4, 1, 'r')])
    else:
        pat = pats.get(style) or [(1, 2, 'r'), (3, 2, 'f')]
    for item in pat:
        b, ln, what = item[:3]
        vel = item[3] if len(item) > 3 else None
        if b > n + 0.99:
            continue
        got = put(int(round((b - 1) * beat)),
                  max(1, int(round(ln * beat)) - beat // 8),
                  tone(b, what), vel)
        # the octave pop is a pop: the line stays anchored on the root,
        # or every bar starts an octave higher until the bass pins at
        # the top of its range (Matt's Blues, 2026-09-28: stuck on G)
        if what != 'o':
            prev = got
    state['bass'] = prev


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


def _comp(bar, state, absbar, feel, chords, sound_id, heat=None):
    if not chords:
        return
    beat = bar.div * 4 // bar.den
    anchor = state.get('comp', 62)
    s = (sound_id or '').lower()
    # the tune's arc: early on the comping says less (two-note shells,
    # a hit left out now and then), later it opens into rootless
    # voicings with the extensions (Matthew, 2026-09-29: "don't put
    # everything in all at once ... same for the comping")
    heat = 0.6 if heat is None else heat
    d = _Dice(sound_id, absbar, 'comp')

    def voicing(c, guides_only=False):
        if not guides_only:
            root = _root_pc(c)
            iv = _tones(c)
            third = next((i for i in iv if i % 12 in (3, 4)), None)
            sev = next((i for i in iv if i % 12 in (9, 10, 11)), None)
            pcs = [(root + i) % 12 for i in (third, sev) if i is not None]
            size = 2 if heat < 0.45 else 3 if heat < 0.72 else 4
            if 'guitar' in s:
                size = min(size, 3)
            for extra in list(_colors(c)) + [7]:
                if len(pcs) >= size:
                    break
                pc = (root + extra) % 12
                if pc not in pcs:
                    pcs.append(pc)
            if len(pcs) < 2:
                pcs = _guide(c)
            v = sorted(_near(pc, anchor) for pc in pcs)
            # no half-step rub at the bottom of the hand
            if len(v) > 1 and v[1] - v[0] == 1:
                v[1] += 12
                v.sort()
            state['comp'] = sum(v) // len(v)
            return v
        pcs = _guide(c)
        if guides_only:
            # two notes a guitar can ring four to the bar: the 3rd and
            # the 7th. The two lowest of a three-note voicing could be
            # the 13th and the 7th a half step apart — a buzzing cluster
            # on every beat (Matthew heard it, Matt's Blues 2026-09-28)
            pcs = pcs[:2]
        v = sorted(_near(pc, anchor) for pc in pcs)
        if guides_only and len(v) == 2 and v[1] - v[0] <= 2:
            v = [v[1], v[0] + 12]      # open a step into a 7th or 9th
        state['comp'] = sum(v) // len(v)
        return v

    def put(at, ticks, notes, vel=None, may_rest=True):
        # a comper early in the tune leaves space: some hits go unplayed
        if may_rest and d() < max(0.0, 0.5 - heat) * 0.8:
            return
        if vel is not None:
            vel = int(vel * (0.85 + 0.25 * heat))
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
            'shuffle': [(2, .25), (4, .25)],
            'secondline': [(1, .5), (2.5, .5), (3.5, .5)],
            'reggae': [(2, .25), (4, .25)],          # the skank
            'motown': [(2, .5), (4, .5)],
            'waltz': ([(1, .5), (2.5, .5)] if 'swung' in traits else
                      [(2, .5), (3, .5)]),
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
                    vel=80 if style == 'funk' else 70,
                    may_rest=style == 'swing')   # an ostinato IS the groove
            return
        marks = sorted({max(1.0, b) for b, c in chords})
        for i, b in enumerate(marks):
            at = int(round((b - 1) * beat))
            end = int(round((marks[i + 1] - 1) * beat)) \
                if i + 1 < len(marks) else bar.barlen
            put(at, end - at, voicing(_chord_at(chords, b)), vel=58,
                may_rest=False)
        return
    if 'guitar' in s and _is_swing(feel) and bar.den == 4:
        for b in range(bar.num):
            put(b * beat, beat,
                voicing(_chord_at(chords, b + 1.0), guides_only=True),
                vel=76 if b % 2 else 66, may_rest=False)
        return
    if 'organ' in s or not _is_swing(feel):
        marks = sorted({max(1.0, b) for b, c in chords})
        for i, b in enumerate(marks):
            at = int(round((b - 1) * beat))
            end = int(round((marks[i + 1] - 1) * beat)) \
                if i + 1 < len(marks) else bar.barlen
            put(at, end - at, voicing(_chord_at(chords, b)),
                may_rest=False)
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
    heat = _heat(sec, off)
    if role == 'perc':
        _perc(bar, absbar, feel, sound_id, state['hits'])
    elif role == 'drums':
        words = ((arg if isinstance(arg, str) else '') + ' ' + (feel or '')
                 ).lower()
        impl = implement(words, feel)
        state['impl'] = impl
        if state['hits'] is None and impl == 'brushes':
            _brush_drums(bar, absbar, feel, heat)
        elif state['hits'] is None and impl == 'mallets':
            _mallet_drums(bar, absbar, heat)
        else:
            _drums(bar, absbar, feel, state['hits'])
        if state['hits'] is None and impl != 'mallets':
            _drummer_marks(bar, sec, off, absbar, heat)
        if re.search(r'cross[ -]?stick|rim ?click|side ?stick', words):
            # the backbeat on the rim, the way a quiet groove wants it
            for tick, (ln, ns) in bar.onsets.items():
                bar.onsets[tick] = (ln, [('u', _XSTICK, n[2])
                                         if n[0] == 'u' and n[1] == _SNARE
                                         else n for n in ns])
    elif role == 'bass':
        _bass(bar, state, sec, off, absbar, feel, chords)
    else:
        _comp(bar, state, absbar, feel, chords, sound_id, heat)
    state['hits'] = None
    return bar.xml()


# the writer's switches for what the band makes up (chart settings)
OPTS = {'builds': True, 'brushes': True}

_STIR_LONG = ('C', 5, 'circle-x')       # brush stirs, read by the listen
_STIR_SHORT = ('C', 5, 'diamond')


def implement(words, feel):
    """What's in the drummer's hands: what the chart says ('brushes',
    'sticks', 'mallets'), else what the feel asks for — a ballad gets
    brushes, the way most drummers would play it."""
    w = (words or '').lower()
    if re.search(r'\bsticks?\b', w):
        return 'sticks'
    if re.search(r'\bbrush(?:es)?\b', w):
        return 'brushes'
    if re.search(r'\bmallets?\b', w):
        return 'mallets'
    style, traits = style_of(feel or '')
    if OPTS['brushes'] and ('ballad' in traits
                            or 'ballad' in (feel or '').lower()):
        return 'brushes'
    return 'sticks'


def _brush_drums(bar, absbar, feel, heat):
    """Brushes: the left hand stirs circles on the snare, the right
    taps the time on it (the ride pattern, or straight eighths), the hat
    foot on 2 and 4, the kick barely there."""
    beat = bar.div * 4 // bar.den
    half = beat // 2
    n = bar.num if bar.den == 4 else max(bar.num // 3, 1)
    style, traits = style_of(feel or '')
    ballad = 'ballad' in traits or 'ballad' in (feel or '').lower()
    if bar.den == 8:
        beat = 3 * (bar.div // 2)
        half = beat // 3
    # the stir: one circle a bar in a ballad, one every two beats else
    if ballad or n < 4:
        bar.add(0, bar.barlen, ('u', _STIR_LONG, int(56 + 20 * heat)))
    else:
        for b in range(0, n, 2):
            bar.add(b * beat, 2 * beat,
                    ('u', _STIR_LONG, int(52 + 20 * heat)))
    swingy = style in ('swing', 'shuffle', 'waltz') or 'swung' in traits
    for b in range(n):
        at = b * beat
        back = b % 2 == 1
        if ballad:
            if back:
                bar.add(at, half, ('u', _SNARE, int(34 + 16 * heat)))
            continue
        bar.add(at, half, ('u', _SNARE, int((50 if back else 40)
                                           + 18 * heat)))
        if swingy and back:
            bar.add(at + beat * 2 // 3, beat // 3,
                    ('u', _SNARE, int(32 + 14 * heat)))
        elif not swingy:
            bar.add(at + half, half, ('u', _SNARE, int(30 + 14 * heat)))
        if back:
            bar.add(at, half, ('u', _HATF, 52))
        bar.add(at, half, ('u', _KICK, 20))
    if heat > 0.7 and n >= 4:
        # a short stir to lift the phrase as the tune builds
        bar.add((n - 1) * beat + half, half,
                ('u', _STIR_SHORT, int(60 + 20 * heat)))


def _mallet_drums(bar, absbar, heat):
    """Mallets: cymbal swells and soft toms, colour more than time —
    an intro, a rubato verse."""
    beat = bar.div * 4 // bar.den
    step = max(beat // 4, 1)
    span = bar.barlen
    for t in range(0, span, step):
        v = int(24 + (36 + 20 * heat) * (t / span) ** 1.6)
        bar.add(t, step, ('u', _RIDE, v))
    bar.add(0, beat, ('u', ('A', 4, 'normal'), int(50 + 20 * heat)))
    if bar.num >= 4 and absbar % 2:
        bar.add(2 * beat, beat, ('u', ('D', 5, 'normal'),
                                 int(44 + 16 * heat)))


def _heat(sec, off):
    """How far the tune has built, 0 to 1: where this section sits in
    the tune, plus a little across the section itself."""
    if not OPTS['builds']:
        return 0.6                  # even all the way: nothing builds
    arc = sec.get('_arc', 0.5)
    return min(1.0, 0.3 + 0.55 * arc + 0.12 * off / max(sec['bars'], 1))


def _drummer_marks(bar, sec, off, absbar, heat):
    """What a drummer does with the form: a crash where a new section
    starts, and now and then a short fill into the next phrase — more
    as the tune builds, never every time."""
    if not OPTS['builds']:
        return
    beat = bar.div * 4 // bar.den
    d = _Dice('marks', absbar)
    if off == 0 and sec.get('_arc', 0) > 0:
        bar.add(0, beat, ('u', _CRASH, int(80 + 25 * heat)))
    phrase_end = (off + 1) % 8 == 0 or off == sec['bars'] - 1
    if phrase_end and bar.num >= 3 and d() < 0.25 + 0.45 * heat:
        start = (bar.num - (2 if heat > 0.7 and d() < 0.5 else 1)) * beat
        toms = [_SNARE, ('E', 5, 'normal'), ('D', 5, 'normal'),
                ('A', 4, 'normal')]
        step = beat // 4
        n = (bar.barlen - start) // step
        for i in range(n):
            if d() < 0.15:
                continue
            bar.add(start + i * step, step,
                    ('u', toms[min(i * 4 // n, 3)], int(62 + 38 * i / n)))


# ------------------------------------------------------------ the solo

# A chart that says "solo" used to leave the soloist silent in the
# listen: notation software's silence, the gap Matthew named
# (2026-09-29). The soloist plays now, over the changes, in the
# listening document only; the page keeps its slashes and the word.
# Deterministic like every other realized bar: the notes come from the
# bar number and the player's name, never a dice roll.

def _scale(chord):
    """The chord-scale a player reaches for, as semitones above the
    root."""
    q = (chord[2] if chord else '') or 'maj'
    if q in ('m7b5', 'm9b5'):
        return (0, 1, 3, 5, 6, 8, 10)
    if q.startswith('dim'):
        return (0, 2, 3, 5, 6, 8, 9, 11)
    if q in ('aug', 'maj7#5', 'm#5'):
        return (0, 2, 4, 6, 8, 10)
    if q in ('mmaj7', 'mmaj9'):
        return (0, 2, 3, 5, 7, 9, 11)
    if q.startswith('m') and not q.startswith('maj'):
        return (0, 2, 3, 5, 7, 8, 10) if q == 'mb6' else \
            (0, 2, 3, 5, 7, 9, 10)
    if q == 'alt' or any(t in q for t in ('b9', '#9', 'b13', '#5')) \
            and q[0].isdigit():
        return (0, 1, 3, 4, 6, 8, 10)
    if q[0].isdigit() and '#11' in q:
        return (0, 2, 4, 6, 7, 9, 10)
    if q[0].isdigit() or 'sus' in q:
        return (0, 2, 4, 5, 7, 9, 10)
    if '#11' in q:
        return (0, 2, 4, 6, 7, 9, 11)
    if q == '5':
        return (0, 3, 5, 7, 10)
    return (0, 2, 4, 5, 7, 9, 11)


class _Dice:
    """A seeded LCG: the same bar and player always roll the same."""
    def __init__(self, *seed):
        import zlib
        self.s = zlib.crc32(repr(seed).encode()) or 1

    def __call__(self):
        self.s = (self.s * 1103515245 + 12345) & 0x7fffffff
        return self.s / 0x7fffffff


def _pcs_near(pcs, anchor, lo, hi):
    """Every pitch of these pitch classes inside lo..hi, nearest to the
    anchor first."""
    got = [m for m in range(lo, hi + 1) if m % 12 in pcs]
    return sorted(got, key=lambda m: (abs(m - anchor), m)) or [anchor]


def improvise(bar, state, chords, next_chord, feel, lo, hi, absbar,
              pos, total, seed, mode='solo'):
    """One bar of a soloist over these chords. pos/total place the bar
    in its solo, so the line breathes in two-bar phrases and builds
    through the solo; 'noodle' is the quiet version, a few notes in the
    gaps, for fills and noodling over a held chord."""
    import math
    beat = bar.div * 4 // bar.den
    half = beat // 2
    n = bar.num if bar.den == 4 else max(bar.num // 2, 1)
    if bar.den == 8:
        beat = 3 * (bar.div // 2)
        half = beat // 3
    d = _Dice(seed, absbar)
    x = (pos + 0.5) / max(total, 1)
    heat = 0.3 + 0.55 * math.sin(math.pi * min(x, 1.0)) ** 0.8
    if mode == 'noodle':
        heat *= 0.45
    style, traits = style_of(feel)
    sixteenths = style in ('funk', 'samba', 'hiphop') and heat > 0.55 \
        and bar.den == 4
    center = lo + (hi - lo) * (0.35 + 0.35 * heat)
    last = state.get('sol_last') or int(center)
    direction = state.get('sol_dir', 1)
    phrase_bar = pos % 2
    # where this bar plays: the first bar of a phrase from beat 1 (or a
    # pickup), the second until its line lands; noodling only answers
    if mode == 'noodle':
        if phrase_bar == 0 and d() < 0.6:
            return
        start = int(n * 0.5) + (1 if d() < 0.5 else 0)
        stop = n
    elif phrase_bar == 0:
        start = 0 if d() < 0.7 else 1
        stop = n
    else:
        start = 0
        stop = max(2, int(round(n * (0.55 + 0.3 * heat))))
    base_vel = 58 if mode == 'noodle' else int(70 + 22 * heat)
    slots = []
    for b in range(start, min(stop, n)):
        t0 = b * beat
        r = d()
        if bar.den == 8:
            cell = [(0, half), (half, half), (2 * half, half)] if \
                r < heat else [(0, beat)]
        elif sixteenths and r < heat * 0.6:
            q = beat // 4
            cell = [(i * q, q) for i in range(4)]
        elif style == 'swing' and r < heat * 0.25:
            t = beat // 3
            cell = [(0, t), (t, t), (2 * t, t)]
        elif r < 0.25 + heat * 0.6:
            cell = [(0, half), (half, half)]
        elif r < 0.25 + heat * 0.75:
            cell = [(half, half)]           # an anticipation
        else:
            cell = [(0, beat)]
        slots += [(t0 + a, ln) for a, ln in cell]
    if not slots:
        return
    # the phrase's last note lands long, on a chord tone
    ends_phrase = mode == 'noodle' or phrase_bar == 1 or stop < n
    for i, (tick, ln) in enumerate(slots):
        c = _chord_at(chords, tick / beat + 1) or (chords[0][1]
                                                   if chords else None)
        if c is None:
            continue
        root = _root_pc(c)
        tones = {(root + t) % 12 for t in _tones(c)}
        scale = {(root + t) % 12 for t in _scale(c)}
        strong = tick % beat == 0 and (tick // beat) % 2 == 0
        final = i == len(slots) - 1
        if last > hi - 3:
            direction = -1
        elif last < lo + 3:
            direction = 1
        elif d() < 0.18:
            direction = -direction
        if final and not ends_phrase and next_chord is not None:
            # lead into the next bar's chord from a half step away
            nroot = _root_pc(next_chord)
            target = _pcs_near({(nroot + t) % 12 for t in
                                _tones(next_chord)[1:3]},
                               last + direction, lo, hi)[0]
            m = target - direction
        elif strong or final:
            ahead = [p for p in _pcs_near(tones, last + 2 * direction,
                                          lo, hi)
                     if (p - last) * direction > 0] or \
                _pcs_near(tones, last, lo, hi)
            m = ahead[0]
        elif d() < 0.12 + 0.2 * heat:
            # a leap up the chord, the arpeggio
            ahead = [p for p in _pcs_near(tones, last + 4 * direction,
                                          lo, hi)
                     if (p - last) * direction >= 3]
            m = ahead[0] if ahead else last
        else:
            ahead = [p for p in range(last + direction,
                                      last + 3 * direction, direction)
                     if p % 12 in scale and lo <= p <= hi]
            m = ahead[0] if ahead else last - direction
        m = min(max(m, lo), hi)
        if final and ends_phrase:
            ln = max(ln, min(beat * 2, bar.barlen - tick))
        vel = base_vel + (6 if tick % beat and style in (
            'swing', 'shuffle') else 0) + int((d() - 0.5) * 10)
        if final and ends_phrase:
            vel -= 4
        bar.add(tick, ln, ('p', m, max(30, min(vel, 118))))
        last = m
    state['sol_last'] = last
    state['sol_dir'] = direction


def comp_shells(bar, state, chords):
    """A pianist soloing still comps under the line: left-hand guide
    tones on the chord changes."""
    beat = bar.div * 4 // bar.den
    for b, c in chords:
        if c is None:
            continue
        root = _root_pc(c)
        g = _guide(c)
        anchor = state.get('shell', 53)
        for pc in g[:2]:
            m = _near(pc, anchor)
            m = min(max(m, 45), 62)
            bar.add(int(round((b - 1) * beat)), beat * 2, ('p', m, 58))
        state['shell'] = _near(g[0], anchor)


def drum_solo(bar, absbar, pos, total, seed):
    """A drummer's solo chorus: two-bar phrases of snare and tom
    figures over the kick, the hat foot keeping 2 and 4, a crash where
    each four-bar phrase starts."""
    import math
    beat = bar.div * 4 // bar.den
    q = beat // 4
    n = bar.num
    d = _Dice(seed, 'drums', absbar)
    heat = 0.4 + 0.5 * math.sin(math.pi * min((pos + 0.5) /
                                              max(total, 1), 1.0))
    toms = [('E', 5, 'normal'), ('D', 5, 'normal'), ('A', 4, 'normal')]
    if pos % 4 == 0:
        bar.add(0, beat, ('u', _CRASH, 100))
        bar.add(0, beat, ('u', _KICK, 96))
    for b in range(n):
        if b % 2 == 1:
            bar.add(b * beat, beat // 2, ('u', _HATF, 60))
    fill_bar = pos % 2 == 1
    for b in range(n):
        if b == 0 and pos % 4 == 0:
            continue
        r = d()
        dense = fill_bar and b >= n - 2 or r < heat * 0.5
        step = q if dense and r < heat else 2 * q
        for k in range(0, beat, step):
            t = b * beat + k
            if fill_bar and b >= n - 2:
                drum = toms[min(int((t - (n - 2) * beat) /
                                    (2 * beat / 3)), 2)]
            else:
                drum = _SNARE if d() < 0.6 else toms[int(d() * 3) % 3]
            vel = 70 + int(30 * heat) - (18 if k else 0) + \
                int((d() - 0.5) * 12)
            bar.add(t, step, ('u', drum, max(30, min(vel, 120))))
        if b % 2 == 0 and d() < 0.7:
            bar.add(b * beat, beat // 2, ('u', _KICK, 84))


def backgrounds(bar, state, chords, voice, voices, lo, hi, style, off,
                seed):
    """One horn's share of made-up backgrounds: each chord voiced across
    the section top-down (voice 0 highest), every horn near its last
    note so the lines move smoothly. Pads hold through each change,
    soft; a riff is one two-bar figure the whole section plays."""
    beat = bar.div * 4 // bar.den
    n = bar.num if bar.den == 4 else max(bar.num // 2, 1)
    if bar.den == 8:
        beat = 3 * (bar.div // 2)
    if style == 'riff':
        d = _Dice(seed, 'riff')
        shapes = [[(2.5, 0.5, 74), (4.0, 1.0, 78)],
                  [(1.0, 1.5, 76), (3.5, 0.5, 72)],
                  [(1.5, 0.5, 72), (2.5, 1.5, 78)]]
        cycle = shapes[int(d() * len(shapes)) % len(shapes)]
        hits = cycle if off % 2 == 0 else [(1.0, 2.0, 70)]
        hits = [(b, ln, v) for b, ln, v in hits if b <= n + 0.99]
    else:
        hits = []
        for i, (b, c) in enumerate(chords):
            nxt = chords[i + 1][0] if i + 1 < len(chords) else n + 1
            hits.append((b, nxt - b, 60))
    for b, ln, vel in hits:
        c = _chord_at(chords, b)
        if c is None:
            continue
        root = _root_pc(c)
        pcs = _guide(c)
        for t in _tones(c):
            pc = (root + t) % 12
            if pc not in pcs and pc != root:
                pcs.append(pc)
        pcs = pcs + [root]
        # top voice takes the first colour, each next voice the next
        # tone down the stack
        pc = pcs[voice % len(pcs)]
        anchor = state.get('bg_last') or int(lo + (hi - lo) * (
            0.7 - 0.5 * voice / max(voices, 1)))
        m = _near(pc, anchor)
        while m > hi:
            m -= 12
        while m < lo:
            m += 12
        bar.add(int(round((b - 1) * beat)),
                max(1, int(round(ln * beat)) - (beat // 8 if style ==
                                                'riff' else 0)),
                ('p', m, vel))
        state['bg_last'] = m


# ------------------------------------------------- the solo as a story

# Matthew, 2026-09-29: "for soloing, tell a story... don't put
# everything in all at once... you got extensions with those chords...
# think from every instrument's and singer's point of view." So a solo
# is planned whole before its first note: a motif stated with space
# around it, developed (answered, sequenced, displaced), built to a
# peak (higher, busier, a riff, a run), then brought home to a long
# last note. Phrases cross barlines and breathe; a horn or a singer
# never plays longer than a breath; the color tones arrive as it
# develops.

def _colors(chord):
    """The extensions a player reaches for over this chord, as
    semitones above the root."""
    q = (chord[2] if chord else '') or 'maj'
    if q in ('m7b5', 'm9b5'):
        return (5, 8)                    # 11, b13
    if q.startswith('dim'):
        return (2, 5, 11)
    if q.startswith('m') and not q.startswith('maj'):
        return (2, 5)                    # 9, 11
    if q == 'alt' or any(t in q for t in ('b9', '#9', 'b13', '#5')) \
            and q[0].isdigit():
        return (1, 3, 8)                 # b9, #9, b13
    if q[0].isdigit() or 'sus' in q:
        return (2, 9) + ((6,) if '#11' in q else ())   # 9, 13
    return (2, 6, 9)                     # maj: 9, #11, 13


_VOICES = {
    # most beats a phrase may run, runs allowed, eighth-line density
    'horn': (10, True, 0.85), 'voice': (7, False, 0.6),
    'keys': (16, True, 1.0), 'guitar': (12, True, 0.9),
    'bass': (8, False, 0.55),
}


def last_phrase(plan, total):
    """The soloist's closing phrase, as the next player heard it:
    the notes after its last real breath, [(beat from the phrase's
    start, length, midi)]."""
    if not plan:
        return None
    notes = sorted(plan)
    start = len(notes) - 1
    while start > 0 and notes[start][0] - (notes[start - 1][0]
                                           + notes[start - 1][1]) < 0.9:
        start -= 1
    got = notes[start:start + 6]
    t0 = got[0][0]
    return [(at - t0, min(ln, 1.0), m) for at, ln, m, _v in got]


def plan_solo(chord_fn, total_bars, bar_beats, lo, hi, feel, seed,
              voice='horn', echo=None, start_after=0.0,
              next_soloist=False):
    """The whole solo, before its first note: [(beat, length, midi,
    velocity)], beats counted from the solo's first downbeat.
    chord_fn(beat) is the chord sounding there. echo is how the soloist
    before ended, which this one answers first; start_after keeps clear
    of a line still spilling over from them. With a soloist after it,
    the end may spill over the barline into their first bar (Matthew,
    2026-09-29: "a phrase that goes over into the next soloist, the
    next soloist could react ... by playing that same phrase")."""
    d = _Dice(seed, 'story')
    max_len, runs_ok, dens = _VOICES.get(voice, _VOICES['horn'])
    style, traits = style_of(feel)
    swingy = style in ('swing', 'shuffle', 'waltz') or 'swung' in traits
    total = total_bars * bar_beats
    notes = []
    # the motif: three to five notes inside two beats, a shape in scale
    # steps the rest of the solo keeps coming back to
    n_mot = 3 + int(d() * 3)
    cells = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    onsets = sorted(set([0.0] + [cells[1 + int(d() * 4)]
                                 for _ in range(n_mot - 1)]))
    shape = [0] + [int(d() * 5) - 2 or 1 for _ in onsets[1:]]
    motif = list(zip(onsets, shape))
    cur = int(lo + (hi - lo) * 0.4)
    t_open = 0.0
    if echo:
        # the answer: the last player's closing phrase, in this
        # player's own register, and it becomes this solo's idea
        mid = sum(m for _a, _l, m in echo) / len(echo)
        aim = lo + (hi - lo) * 0.45
        shift = 12 * round((aim - mid) / 12)
        base = max(start_after, 0.0)
        base = float(int(base * 2 + 0.999)) / 2          # to an eighth
        for at, ln, m in echo:
            q = m + shift
            while q > hi:
                q -= 12
            while q < lo:
                q += 12
            notes.append((base + at, ln * 0.9, q, 74))
            cur = q
        t_open = base + echo[-1][0] + echo[-1][1] + bar_beats * 0.5
        if len(echo) >= 3:
            ons = [a for a, _l, _m in echo[:5] if a < 2.5]
            if len(ons) >= 3:
                motif = [(a, 0 if i == 0 else
                          (1 if echo[i][2] > echo[i - 1][2] else -1)
                          * (1 + (abs(echo[i][2] - echo[i - 1][2]) > 3)))
                         for i, a in enumerate(ons)]

    def act(t):
        x = t / max(total, 1)
        return ('state' if x < 0.3 else 'develop' if x < 0.72 else
                'peak' if x < 0.9 else 'home')

    def scale_move(p, steps, c):
        root = _root_pc(c)
        sc = sorted({(root + i) % 12 for i in _scale(c)})
        m, left = p, abs(steps)
        dirn = 1 if steps > 0 else -1
        while left:
            m += dirn
            if m % 12 in sc:
                left -= 1
        return m

    def snap(p, c, pool):
        root = _root_pc(c)
        pcs = {(root + i) % 12 for i in pool}
        cands = [m for m in range(p - 6, p + 7) if m % 12 in pcs]
        return min(cands, key=lambda m: (abs(m - p), m)) if cands else p

    def bounds(a):
        top = hi if a == 'peak' else hi - (hi - lo) // 5
        bot = lo + (hi - lo) // 6 if a == 'state' else lo
        return bot, top

    def fit(p, a):
        bot, top = bounds(a)
        while p > top:
            p -= 12
        while p < bot:
            p += 12
        return p

    def vel(a):
        return {'state': 72, 'develop': 80, 'peak': 92, 'home': 72}[a]

    t = t_open or (0.5 if d() < 0.5 else 0.0)   # sometimes a pickup in
    last_kind = None
    told = 0                                 # phrases so far in act one
    while t < total - 0.5:
        a = act(t)
        if a == 'state':
            # state it, answer it, lift it, stretch it
            kind = ['motif', 'answer', 'lifted', 'stretched'][told % 4]
            told += 1
            length = min(bar_beats * (1 + 0.5 * d()), max_len)
            rest = bar_beats * (1.0 + 0.8 * d())
        elif a == 'develop':
            kind = ['sequence', 'line', 'displaced', 'line'][
                int(d() * 4) % 4]
            length = min(bar_beats * (1.5 + d()), max_len)
            rest = bar_beats * (0.4 + 0.6 * d())
        elif a == 'peak':
            kind = ['riff', 'line', 'run'][int(d() * 3) % 3]
            if kind == 'run' and not runs_ok:
                kind = 'line'
            length = min(bar_beats * (2 + d()), max_len)
            rest = bar_beats * (0.25 + 0.35 * d())
        else:
            kind = 'home'
            length = total - t
            rest = 0
        length = max(1.0, min(length, total - t))
        # each act has its register, chosen, not drifted into
        aim = lo + (hi - lo) * {'state': 0.45, 'develop': 0.55,
                                'peak': 0.78, 'home': 0.5}[a]
        cur = int(round(cur + (aim - cur) * 0.6))
        c0 = chord_fn(t)
        if c0 is None:
            t += length + rest
            continue
        v = vel(a)
        if kind in ('motif', 'answer', 'displaced', 'sequence', 'lifted',
                    'stretched'):
            reps = 3 if kind == 'sequence' else 1
            shift = 0.5 if kind == 'displaced' else 0.0
            flip = -1 if kind == 'answer' else 1
            p = fit(snap(cur, c0, _tones(c0)), a)
            if kind == 'lifted':
                p = fit(snap(scale_move(p, 2, c0), c0, _tones(c0)), a)
            for r in range(reps):
                base = t + r * 2.0 + shift
                if base >= t + length:
                    break
                q = p
                for i, (on, stp) in enumerate(motif):
                    at = base + on
                    if at >= min(t + length, total):
                        break
                    c = chord_fn(at) or c0
                    q = fit(scale_move(q, stp * flip, c) if i else q, a)
                    if at % 1 == 0 and a != 'state':
                        q = snap(q, c, _tones(c) + _colors(c))
                    nxt = motif[i + 1][0] if i + 1 < len(motif) else 2.0
                    notes.append((at, (nxt - on) * 0.9, q, v))
                # a sequence climbs a step each time round
                p = fit(scale_move(p, 1, chord_fn(base + 2.0) or c0), a)
            if kind == 'stretched':
                # the idea again, then it keeps talking: a short tail
                tail = t + motif[-1][0] + 0.5
                for i in range(3):
                    at = tail + 0.5 * i
                    if at >= min(t + length, total):
                        break
                    c = chord_fn(at) or c0
                    q = fit(scale_move(q, -1 if i < 2 else 2, c), a)
                    notes.append((at, 0.45 if i < 2 else 1.2, q, v))
            cur = q
        elif kind == 'line':
            step = 0.5
            n = int(length / step * dens) or 1
            q = fit(snap(cur, c0, _tones(c0)), a)
            dirn = 1 if q < (lo + hi) / 2 else -1
            for i in range(n):
                at = t + i * step
                c = chord_fn(at) or c0
                bot, top = bounds(a)
                nq = scale_move(q, dirn, c)
                if not bot <= nq <= top:
                    # a player turns the line around at the edge of the
                    # horn, never jumps an octave to stay inside it
                    dirn = -dirn
                    nq = scale_move(q, dirn, c)
                if at % 1 == 0:
                    pool = _tones(c) + (_colors(c) if a != 'state' else ())
                    nq = snap(nq, c, pool)
                q = nq
                if d() < 0.15:
                    dirn = -dirn
                notes.append((at, step * 0.95, q, v + (4 if at % 1 else 0)
                              if swingy else v))
            cur = q
        elif kind == 'riff':
            c = c0
            root = _root_pc(c)
            top = fit(snap(cur + 5, c, _tones(c)), a)
            cell = [(0.0, top), (0.5, scale_move(top, -1, c)),
                    (1.0, snap(top - 3, c, _tones(c)))]
            for r in range(3):
                for on, q in cell:
                    at = t + r * 2.0 + on
                    if at < min(t + length, total):
                        notes.append((at, 0.45, q, v + 4))
            cur = top
        elif kind == 'run':
            step = 1 / 3 if swingy else 0.25
            n = int(min(length, 2.0) / step)
            bot, top = bounds(a)
            # the run climbs to the top of the horn from wherever it
            # has room to start
            q = max(bot, min(cur - 5, top - 2 * n))
            for i in range(n):
                at = t + i * step
                c = chord_fn(at) or c0
                q = min(scale_move(q, 1, c), top)
                notes.append((at, step * 0.9, q, v + int(8 * i / n)))
            land = t + n * step
            if land < total:
                c = chord_fn(land) or c0
                notes.append((land, 1.5, snap(q, c, _tones(c)), v + 6))
            cur = q
        else:                                    # home
            p = fit(snap(cur, c0, _tones(c0)), 'home')
            r_end = d()
            if next_soloist and r_end < 0.4:
                # the line keeps going over the barline, into the next
                # player's first bar
                at = max(t, total - bar_beats * 0.75)
                q = fit(snap(cur, c0, _tones(c0)), 'develop')
                dirn = -1 if q > (lo + hi) / 2 else 1
                i = 0
                while at < total + bar_beats * (0.75 + 0.5 * d()):
                    c = chord_fn(at) or c0
                    bot, top = bounds('develop')
                    nq = scale_move(q, dirn, c)
                    if not bot + 2 <= nq <= top:
                        dirn = -dirn
                        nq = scale_move(q, dirn, c)
                    q = nq
                    if at % 1 == 0:
                        q = snap(q, c, _tones(c) + _colors(c))
                    notes.append((at, 0.47, q, 78))
                    at += 0.5
                    i += 1
                c = chord_fn(at) or c0
                notes.append((at, 0.9, snap(q, c, _tones(c)), 74))
                break
            if r_end < 0.7:
                # short: the idea once more, clipped off, then air
                for i, (on, stp) in enumerate(motif):
                    at = t + on
                    if at >= total - 0.5:
                        break
                    c = chord_fn(at) or c0
                    p = scale_move(p, stp, c) if i else p
                    notes.append((at, 0.45, fit(p, 'home'), 72))
                at = min(t + motif[-1][0] + 0.5, total - 0.5)
                c = chord_fn(at) or c0
                notes.append((at, 0.35, fit(snap(p, c, _tones(c)), 'home'),
                              76))
                break
            for i, (on, stp) in enumerate(motif):
                at = t + on
                if at >= total - 1:
                    break
                c = chord_fn(at) or c0
                p = scale_move(p, stp, c) if i else p
                notes.append((at, 0.45, fit(p, 'home'), 70))
            at = min(t + 2.5, total - 1.0)
            if at > t:
                c = chord_fn(at) or c0
                root = _root_pc(c)
                goal = snap(p, c, (0, 4 if 4 in _tones(c) else 3))
                notes.append((at, total - at, fit(goal, 'home'), 68))
            break
        last_kind = kind
        t += length + rest
        # the next phrase may come in on an upbeat
        if d() < 0.4:
            t += 0.5
    return notes


def play_planned(bar, plan, pos, bar_beats):
    """This bar's share of a planned solo; a note that would ring over
    the barline stops at it."""
    beat = bar.div * 4 // bar.den
    if bar.den == 8:
        beat = bar.div // 2
    t0, t1 = pos * bar_beats, (pos + 1) * bar_beats
    for at, ln, m, v in plan:
        end = at + ln
        if end <= t0 + 1e-6 or at >= t1:
            continue
        # a note that rings over a barline is tied, never re-struck
        ties = (('stop',) if at < t0 - 1e-6 else ()) + \
            (('start',) if end > t1 + 1e-6 else ())
        a, e = max(at, t0), min(end, t1)
        bar.add(int(round((a - t0) * beat)),
                max(1, int(round((e - a) * beat))),
                ('p', m, max(30, min(v, 118)), (), ties))
