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
import json
import math
import os
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


def _next_chord(sec, off, chords):
    """The chord the next bar opens with (round the section's top at
    its end)."""
    for o in list(range(off + 1, sec['bars'])) + list(range(0, off + 1)):
        for _b, c in sec['content'][o]:
            if c is not None:
                return c
    return chords[-1][1] if chords else None


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


_RIDE_BARS = {
    # a drummer's ride vocabulary in swing, beats 1-based; (beat, weight)
    'classic':  [(1, 0), (2, 1), (2.5, -1), (3, 0), (4, 1), (4.5, -1)],
    'quarters': [(1, 0), (2, 1), (3, 0), (4, 1)],
    'skip_all': [(1, 0), (1.5, -1), (2, 1), (2.5, -1), (3, 0), (3.5, -1),
                 (4, 1), (4.5, -1)],
    'lift_3':   [(1, 0), (2, 1), (2.5, -1), (3, 0), (3.5, -1), (4, 1)],
    'lay_2':    [(1, 0), (1.5, -1), (2, 1), (3, 0), (4, 1), (4.5, -1)],
    'triplet4': [(1, 0), (2, 1), (2.5, -1), (3, 0), (4, 1),
                 (4 + 1 / 3, -2), (4 + 2 / 3, -1)],
}


def _swing_time(bar, absbar, heat, busy, feather=True):
    """Swing time the way a drummer keeps it: the ride changes from
    bar to bar (the classic ding, ding-ga, straight quarters, skips on
    every beat when it burns, a triplet into the next bar, the bell now
    and then), the hi-hat foot usually on 2 and 4 but not always, the
    kick feathered or not (Matthew, 2026-09-29: "the ride pattern on the
    drums doesn't have to be the same ... same with the hihat on two and
    four")."""
    beat = bar.div * 4 // bar.den
    half = beat // 2
    d = _Dice('ride', absbar)
    heat = 0.55 if heat is None else heat
    pool = ['classic', 'classic', 'lay_2', 'lift_3', 'quarters']
    if heat > 0.55:
        pool += ['skip_all', 'triplet4', 'lift_3']
    if heat < 0.4 or (busy is not None and busy > 0.7):
        pool += ['quarters', 'classic']
    pick = pool[int(d() * len(pool)) % len(pool)]
    base = int(62 + 16 * heat)
    bell = d() < 0.08 + 0.1 * heat
    for b, w in _RIDE_BARS[pick]:
        if b > bar.num + 0.99:
            continue
        at = int(round((b - 1) * beat))
        # the skip notes sit under the beats; 2 and 4 speak a little
        v = base + (6 if w == 1 else -14 if w < 0 else 0) + \
            int((d() - 0.5) * 8)
        cym = _BELL if bell and b in (1, 3) else _RIDE
        ln = beat // 3 if w < 0 else half
        bar.add(at, ln, ('u', cym, max(30, min(v, 118))))
    # the hi-hat foot: 2 and 4 mostly; sometimes only 4, sometimes all
    # four, a splash on the and of 4 when it's hot, lighter when soft
    r = d()
    if r < 0.12:
        feet = [4]
    elif r < 0.2 and heat > 0.5:
        feet = [1, 2, 3, 4]
    else:
        feet = [2, 4]
    hv = int(54 + 16 * heat)
    for b in feet:
        if b <= bar.num:
            bar.add((b - 1) * beat, half, ('u', _HATF,
                                          hv + int((d() - 0.5) * 8)))
    if heat > 0.65 and d() < 0.2 and bar.num >= 4:
        bar.add(3 * beat + half, half, ('u', ('G', 5, 'circle-x'),
                                        int(56 + 14 * heat)))
    if feather:
        for b in range(bar.num):
            bar.add(b * beat, half, ('u', _KICK, 22 + int(d() * 10)))
    spot = int(d() * 5)
    if spot < 2 and bar.num >= 4:
        bar.add((1 + 2 * spot) * beat + half, half,
                ('u', _SNARE, int(44 + 14 * heat)))


def _drums(bar, absbar, feel, hits, heat=None, busy=None):
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
        _swing_time(bar, absbar, heat, busy, OPTS.get('feather', True))
        return
    # straight: backbeat — the hat varies too: an open hat on the and
    # of four now and then, a lighter bar, the kick moving
    d = _Dice('back', absbar)
    heat = 0.55 if heat is None else heat
    open_at = 3 if d() < 0.15 + 0.2 * heat else None
    for b in range(bar.num):
        at = b * beat
        bar.add(at, half, ('u', _HAT, 62 + int(8 * heat)
                           + int((d() - 0.5) * 8)))
        if open_at == b:
            bar.add(at + half, half, ('u', ('G', 5, 'circle-x'), 62))
        else:
            bar.add(at + half, half, ('u', _HAT, 46 + int((d() - 0.5) * 8)))
        if b % 2 == 0:
            bar.add(at, half, ('u', _KICK, 85))
        else:
            bar.add(at, half, ('u', _SNARE, 82))
    if bar.num >= 4 and d() < 0.25 + 0.3 * heat:
        k = [1.5, 2.5, 3.5][int(d() * 3) % 3]
        bar.add(int(k * beat), half, ('u', _KICK, 68))


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


def _fold_bass(m, lo=31, hi=50):
    """Into the middle of the neck, by octaves."""
    while m < lo:
        m += 12
    while m > hi:
        m -= 12
    return m


def _load_walk():
    """The walking statistics learned from real bassists
    (learn_walking.py over FiloBass, CC BY 4.0); built-in numbers from
    the same run if the file is missing."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'data', 'walking_stats.json')) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'arrival_degree': {'dom': {'0': .68, '7': .13, '4': .08},
                                   'min': {'0': .74, '7': .07, '3': .06},
                                   'maj': {'0': .69, '7': .17, '4': .07},
                                   'half': {'0': .85, '6': .04},
                                   'dim': {'0': .62, '3': .02}},
                'approach_interval': {'-1': .31, '1': .22, '2': .14,
                                      '-5': .11, '7': .06, '-2': .035},
                'middle': {'tone': .62, 'chromatic': .21, 'scale': .17},
                'step': {'1': .2, '-1': .15, '-2': .13, '2': .07, '5': .06,
                         '4': .055, '7': .044, '3': .035, '-3': .033,
                         '-7': .032, '-6': .027, '-4': .026, '-8': .025,
                         '-5': .023, '6': .019, '-12': .019, '12': .011},
                'register_percentiles': {'p5': 31, 'p50': 41, 'p95': 52},
                'bars_with_offbeats': .34}


_WALK = _load_walk()


def _load_solo():
    """How real soloists phrase (learn_solos.py over the Weimar Jazz
    Database, ODbL); the same run's key numbers built in as the floor."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'data', 'solo_stats.json')) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'phrase_beats': {'4': .1, '5': .09, '6': .09, '7': .08,
                                 '8': .07, '3': .08, '2': .06, '10': .05,
                                 '12': .04, '14': .03, '16': .03},
                'gap_half_beats': {'2': .3, '3': .15, '4': .15, '6': .1,
                                   '1': .1, '8': .06},
                'on_beat': {'tone': .54, 'color': .30, 'other': .16},
                'half_step_into_beat_tone': .29,
                'grid': {'triplet': .18},
                'end_position': {'and': .51, 'on': .39},
                'end_len_half_beats': {'1': .55, '2': .21, '3': .1,
                                       '4': .04}}


_SOLO = _load_solo()


def _family(c):
    q = (c[2] if c else '') or 'maj'
    if q in ('m7b5', 'm9b5'):
        return 'half'
    if q.startswith('dim'):
        return 'dim'
    if q.startswith('maj') or q in ('6', '69', '6/9', 'maj'):
        return 'maj'
    if q.startswith('m'):
        return 'min'
    return 'dom'


def _roll(weights, d):
    """A weighted pick: [(item, weight)] -> item."""
    tot = sum(w for _i, w in weights)
    if tot <= 0:
        return weights[0][0]
    r = d() * tot
    for item, w in weights:
        r -= w
        if r <= 0:
            return item
    return weights[-1][0]


def arrival_pc(c, d, root_only=False):
    """The note a bassist lands on when a chord arrives — the root most
    of the time, the fifth or third otherwise, in the proportions real
    players use (FiloBass); an inverted chord's bass note always."""
    if c is None:
        return 0
    if c[3] or root_only:
        return _bass_pc(c)
    tones = {i % 12 for i in _tones(c)}
    dist = _WALK['arrival_degree'].get(_family(c), {'0': 1})
    opts = [(int(k), v) for k, v in dist.items()
            if int(k) == 0 or (int(k) in tones and int(k) in (3, 4, 6, 7))]
    return (_root_pc(c) + _roll(opts, d)) % 12


def walk_bar(beats, prev, d, arrive, next_arrive):
    """One bar of a walking line, a note a beat: [midi]. beats is the
    chord on each beat; arrive is this bar's first note (chosen a bar
    ago, so last bar's lead-in pointed at it), next_arrive the next
    bar's. The beats between are chosen the way real bassists choose
    (learn_walking.py over FiloBass: ~62% chord tones, ~20% chromatic
    passing, ~17% scale; mostly steps, real leaps of a 4th or 5th, the
    direction turning about half the time, a note almost never struck
    twice); the last beat leads in a half step under (31%) or over
    (22%), a whole step over (14%), a fifth under (11%) or over (6%).
    Home is G1-E3 around F2, E1 the floor (Matthew, 2026-09-29:
    "walking bass overall sounds meh ... think professional ... lowest
    range on a bass should be an e")."""
    n = len(beats)
    steps = {int(k): v for k, v in _WALK['step'].items() if k != '0'}
    mid = _WALK['middle']
    appr = [(int(k), v) for k, v in _WALK['approach_interval'].items()
            if int(k) in (-1, 1, 2, -2, -5, 7)]
    reg = _WALK.get('register_percentiles', {})
    centre = reg.get('p50', 41)
    lo_h, hi_h = reg.get('p5', 31), reg.get('p95', 52)
    out = []
    b = 0
    while b < n:
        c = beats[b]
        e = b + 1
        while e < n and beats[e] == c:
            e += 1
        root = _root_pc(c)
        tones = {(root + i) % 12 for i in _tones(c)}
        sc = {(root + i) % 12 for i in _scale(c)}
        anchor = out[-1] if out else prev
        first = arrive if b == 0 else arrival_pc(c, d)
        m0 = _fold_bass(_near(first, anchor), lo_h, hi_h)
        if out and m0 == out[-1]:
            m0 = _fold_bass(m0 + (12 if m0 < centre else -12), lo_h, hi_h)
        seg = [m0]
        last_seg = e == n
        if last_seg:
            goal_pc = next_arrive
            nc = None
        else:
            nc = beats[e]
            goal_pc = arrival_pc(nc, d)
        want = e - b                    # notes this chord gets
        cur = m0
        while len(seg) < want - 1:
            left = want - len(seg)      # beats still to play, lead-in too
            goal = _fold_bass(_near(goal_pc, cur), lo_h, hi_h)
            opts = []
            for m in range(max(28, cur - 9), min(55, cur + 9) + 1):
                if m == cur or (len(seg) > 1 and m == seg[-2]
                                and d() < 0.7):
                    continue
                pc = m % 12
                cat = 'tone' if pc in tones else 'scale' if pc in sc \
                    else 'chromatic'
                w = steps.get(m - cur, 0.004) * mid.get(cat, 0.1)
                if cat == 'chromatic':
                    # chromatic notes pass: they move by a half step on
                    # to something, so keep them a step off the goal path
                    w *= 0.6 if abs(m - cur) <= 2 else 0.15
                gap = abs(goal - m)
                w *= 1.0 / (1.0 + max(0, gap - 4 * (left - 1)) ** 2)
                w *= 1.0 / (1.0 + ((m - centre) / 11.0) ** 4)
                opts.append((m, w))
            cur = _roll(opts, d) if opts else cur + 1
            seg.append(cur)
        if len(seg) < want:
            goal = _fold_bass(_near(goal_pc, cur), lo_h, hi_h)
            opts = []
            for iv, w in appr:
                ap = goal + iv
                if ap == cur or not 28 <= ap <= 55:
                    continue
                opts.append((ap, w))
            seg.append(_roll(opts, d) if opts else goal - 1)
        out += seg[:want]
        b = e
    return [_fold_bass(m, 28, 55) for m in out]


def _bass(bar, state, sec, off, absbar, feel, chords):
    if not chords:
        return
    beat = bar.div * 4 // bar.den
    lo, hi = 28, 55
    prev = state.get('bass', 38)
    # a bassist lives in the middle of the neck: nearest-note walking
    # drifts, so each bar starts from an anchor pulled back toward it
    # (Autumn Leaves climbed to G3 and stayed there, Matthew 2026-09-29)
    if prev > 52:
        prev -= 12
    elif prev < 31:
        prev += 12

    def put(at, ticks, midi, vel=None):
        # out of range moves an octave, never to a different note (a
        # clamp turned Eb into E at the floor)
        while midi < lo:
            midi += 12
        while midi > hi:
            midi -= 12
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
        # the bassist listens too: two feel at the top of a soloist's
        # turn, skips and triplet pickups as it builds, a run into the
        # next bar when the soloist breathes
        d = _Dice('bass', absbar)
        heat = state.get('heat', 0.55)
        busy = state.get('busy')
        turn = state.get('turn')
        target = _near(_next_root(sec, off, chords), prev)
        if turn and turn[0] < 2 and d() < 0.6 and bar.num == 4:
            c1, c3 = _chord_at(chords, 1.0), _chord_at(chords, 3.0)
            prev = put(0, 2 * beat - beat // 8,
                       _fold_bass(_near(_bass_pc(c1), prev)))
            fifth = (_root_pc(c3) + 7) % 12 if c3 == c1 else _bass_pc(c3)
            prev = put(2 * beat, 2 * beat - beat // 8, _near(fifth, prev))
            return
        c1 = _chord_at(chords, 1.0)
        arrive = state.pop('arrive', None)
        if arrive is None or (c1 and (arrive - _root_pc(c1)) % 12 not in
                              {i % 12 for i in _tones(c1)}
                              and arrive != _bass_pc(c1)):
            arrive = arrival_pc(c1, d, root_only=True)
        nxt_c = _next_chord(sec, off, chords)
        # a new section or soloist lands on the root, like anyone would
        next_arrive = arrival_pc(nxt_c, d, root_only=(
            off + 1 >= sec['bars'] or (off + 1) % 4 == 0)) \
            if nxt_c else _next_root(sec, off, chords)
        state['arrive'] = next_arrive
        line = walk_bar([_chord_at(chords, b + 1.0)
                         for b in range(bar.num)],
                        prev, d, arrive, next_arrive)
        target = _fold_bass(_near(_next_root(sec, off, chords), line[-1]),
                            28, 55)
        run = busy is not None and busy < 0.2 and d() < 0.5
        skip = d() < (0.12 + 0.3 * heat) * \
            (_WALK.get('bars_with_offbeats', 0.34) / 0.34)
        for b, midi in enumerate(line):
            last = b == len(line) - 1
            if last and run:
                # a triplet run up or down into the next root
                step = 1 if target > midi else -1
                for k in range(3):
                    put(b * beat + k * beat // 3, beat // 3 - 1,
                        target - step * (3 - k), 70 + 6 * k)
                continue
            put(b * beat, beat, midi)
            if skip and b == 1:
                # the skip: a ghosted triplet note into beat three
                nxt = line[2] if len(line) > 2 else target
                put(b * beat + 2 * beat // 3, beat // 3 - 1, nxt - 1, 50)
        state['bass'] = line[-1] if not run else target
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
    pianist = ('piano' in s or 'keyboard' in s) and 'organ' not in s
    if pianist and ns and ('ballad' in ns[1]
                           or 'ballad' in (feel or '').lower()):
        piano_comp(bar, state, absbar, chords, state.get('next_chord'),
                   heat, sound_id, feel, state.get('busy'))
        return
    if pianist:
        # every other style keeps its pattern, voiced like a pianist
        _plain_voicing = voicing

        def voicing(c, guides_only=False):
            if guides_only:
                return _plain_voicing(c, True)
            v = rootless_voicing(c, state.get('pv'), 3 if heat < 0.45
                                 else 4)
            state['pv'] = v
            return v
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
            busy = state.get('busy') or 0.0
            lift = (0.85 + 0.3 * heat) * (1.0 - 0.18 * busy)
            put(b * beat, beat,
                voicing(_chord_at(chords, b + 1.0), guides_only=True),
                vel=int((76 if b % 2 else 66) * lift), may_rest=False)
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
    if ('piano' in s or 'keyboard' in s) and 'organ' not in s:
        piano_comp(bar, state, absbar, chords, state.get('next_chord'),
                   heat, sound_id, feel, state.get('busy'))
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
    evs = sec.get('events') or []
    brk = {b: t for b, k, t in evs if k == 'break'}
    if off + 1 in brk:
        # a break: the band hits the downbeat together and stops dead;
        # the soloist (or the tune) plays on alone; the drummer brings
        # everyone back in on the bar after with a crash
        beat = bar.div * 4 // bar.den
        c0 = _chord_at(chords, 1.0)
        if brk[off + 1] == 'first':
            if role in ('drums', 'perc'):
                bar.add(0, beat // 2, ('u', _CRASH, 104))
                bar.add(0, beat // 2, ('u', _KICK, 100))
                bar.add(0, beat // 2, ('u', _SNARE, 92))
            elif role == 'bass' and c0:
                m = _fold_bass(_near(_bass_pc(c0), state.get('bass', 38)),
                               28, 55)
                bar.add(0, beat // 2, ('p', m, 100))
                state['bass'] = m
            elif c0:
                for m in rootless_voicing(c0, None):
                    bar.add(0, beat // 2, ('p', m, 92))
        wf = {b: t for b, k, t in evs if k == 'fill'}
        if role == 'drums' and off + 1 in wf:
            # the drummer fills the end of the break, bringing the band
            # back in — the one thing that breaks a break's silence
            at = float(wf[off + 1]) if wf[off + 1] else \
                max(1.0, bar.num - 1.0)
            d = _Dice('written fill', absbar)
            _fill(bar, _FILLS[int(d() * len(_FILLS)) % len(_FILLS)],
                  int(round((at - 1) * beat)), max(heat, 0.6), d)
        if role == 'drums' and off + 2 not in brk:
            state['crash_next'] = True
        state['hits'] = None
        return bar.xml()
    state['busy'] = sec.get('_busy')      # how busy the soloist is here
    state['heat'] = heat
    state['turn'] = sec.get('_turn')
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
            _drums(bar, absbar, feel, state['hits'], heat,
                   state.get('busy'))
        if not OPTS['feather']:
            # no feathered quarters: the kick only where it says
            # something (bombs, setups, fills)
            for tick, (ln, ns) in list(bar.onsets.items()):
                keep = [n for n in ns if not (n[0] == 'u' and n[1] == _KICK
                                              and (n[2] or 99) <= 34)]
                if keep:
                    bar.onsets[tick] = (ln, keep)
                else:
                    del bar.onsets[tick]
        if state['hits'] is None and impl != 'mallets':
            _drummer_marks(bar, sec, off, absbar, heat, state)
        fills = {b: t for b, k, t in evs if k == 'fill'}
        if off + 1 in fills:
            # the roadmap said fill here: it happens, from the beat it
            # names (else the last two beats), and lands on the one
            beat = bar.div * 4 // bar.den
            at = float(fills[off + 1]) if fills[off + 1] else \
                max(1.0, bar.num - 1.0)
            d = _Dice('written fill', absbar)
            kind = _FILLS[int(d() * len(_FILLS)) % len(_FILLS)]
            if kind == state.get('last_fill'):
                kind = _FILLS[(_FILLS.index(kind) + 1) % len(_FILLS)]
            state['last_fill'] = kind
            _fill(bar, kind, int(round((at - 1) * beat)), max(heat, 0.6),
                  d)
            state['crash_next'] = True
        if state['hits'] is None and OPTS['builds']:
            # the whole kit breathes with the band
            k = 0.78 + 0.4 * heat
            for tick, (ln, ns) in bar.onsets.items():
                bar.onsets[tick] = (ln, [
                    n if n[2] is None else
                    (n[0], n[1], max(1, min(int(n[2] * k), 124))) + n[3:]
                    for n in ns])
        if re.search(r'cross[ -]?stick|rim ?click|side ?stick', words):
            # the backbeat on the rim, the way a quiet groove wants it
            for tick, (ln, ns) in bar.onsets.items():
                bar.onsets[tick] = (ln, [('u', _XSTICK, n[2])
                                         if n[0] == 'u' and n[1] == _SNARE
                                         else n for n in ns])
    elif role == 'bass':
        _bass(bar, state, sec, off, absbar, feel, chords)
    else:
        state['next_chord'] = None
        if off + 1 < sec['bars']:
            state['next_chord'] = next((c for _b, c in
                                        sec['content'][off + 1]
                                        if c is not None), None)
        _comp(bar, state, absbar, feel, chords, sound_id, heat)
    state['hits'] = None
    return bar.xml()


# the writer's switches for what the band makes up (chart settings)
OPTS = {'builds': True, 'brushes': True, 'feather': True}

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
    turn = sec.get('_turn')
    if turn:
        # behind a soloist the band drops back as each one starts and
        # builds with them through their turn (Matthew, 2026-09-29:
        # "dynamics ... transitions between soloists")
        at, length = turn[0], turn[1]
        return min(1.0, 0.32 + 0.6 * at / max(length - 1, 1))
    arc = sec.get('_arc', 0.5)
    return min(1.0, 0.3 + 0.55 * arc + 0.12 * off / max(sec['bars'], 1))


_FILLS = ('toms_down', 'triplets_around', 'snare_kick_talk', 'space_hits',
          'buzz_roll', 'flam_setup', 'toms_up')


def _clear_for_fill(bar, start):
    """A drummer stops keeping time to play a fill: the ride, hats and
    snare comping from here to the barline go; the hi-hat foot stays
    (Matthew, 2026-09-29: fills overlapping weirdly)."""
    for tick in [t for t in bar.onsets if t >= start]:
        ln, ns = bar.onsets[tick]
        keep = [n for n in ns if n[0] == 'u' and n[1] == _HATF]
        if keep:
            bar.onsets[tick] = (ln, keep)
        else:
            del bar.onsets[tick]


def _fill(bar, kind, start, heat, d):
    """One fill from a drummer's vocabulary, from `start` to the bar's
    end: time stops for it, every stroke played even and strong, the
    beats accented with the kick under them (Matthew: fills should
    sound tight and confident)."""
    _clear_for_fill(bar, start)
    beat = bar.div * 4 // bar.den
    end = bar.barlen
    span = max(end - start, 1)
    base = int(84 + 14 * heat)
    toms = [_SNARE, ('E', 5, 'normal'), ('D', 5, 'normal'),
            ('A', 4, 'normal')]

    def hit(t, drum, ln, v, kick=False):
        on_beat = (t - start) % beat == 0
        bar.add(t, ln, ('u', drum, min(v + (10 if on_beat else 0), 122)))
        if kick or on_beat:
            bar.add(t, ln, ('u', _KICK, min(base + 6, 118)))
    if kind in ('toms_down', 'toms_up'):
        step = beat // 4
        n = span // step
        order = toms if kind == 'toms_down' else list(reversed(toms))
        for i in range(n):
            hit(start + i * step, order[min(i * 4 // n, 3)], step,
                base - 8 + int(10 * i / n))
    elif kind == 'triplets_around':
        step = beat // 3
        for i in range(span // step):
            hit(start + i * step, [_SNARE, toms[1], toms[3]][i % 3], step,
                base - 6 + int(8 * i * step / span))
    elif kind == 'snare_kick_talk':
        for b, drum in [(0.0, _SNARE), (0.5, _KICK), (1.0, _SNARE),
                        (1.5, _SNARE), (1.75, _KICK)]:
            t = start + int(b * beat)
            if t < end:
                bar.add(t, beat // 4, ('u', drum, base + 4))
    elif kind == 'space_hits':
        for b in (0.5, 1.5):
            t = start + int(b * beat)
            if t < end:
                bar.add(t, beat // 2, ('u', _SNARE, base + 12))
                bar.add(t, beat // 2, ('u', _KICK, base + 8))
    elif kind == 'buzz_roll':
        step = max(beat // 8, 1)
        for t in range(start, end, step):
            bar.add(t, step, ('u', _SNARE,
                              int(56 + (base - 50) * ((t - start) / span))))
        bar.add(end - beat // 2, beat // 2, ('u', _SNARE, base + 12))
        bar.add(end - beat // 2, beat // 2, ('u', _KICK, base + 8))
    else:                                         # flam_setup
        for b in (0.0, 1.0, 1.5):
            t = start + int(b * beat)
            if t < end:
                bar.add(max(t - beat // 12, 0), beat // 12,
                        ('u', _SNARE, base - 30))
                hit(t, _SNARE, beat // 2, base + 4)


def _drummer_marks(bar, sec, off, absbar, heat, state=None):
    """What a drummer does with the form: a crash and kick where a new
    section or soloist starts; at a phrase end a fill from the whole
    vocabulary (never the one just played, so no two handoffs sound
    alike) or just the setup; kick bombs and snare answers in the
    soloist's gaps, less when the soloist is busy."""
    if not OPTS['builds']:
        return
    state = state if state is not None else {}
    beat = bar.div * 4 // bar.den
    half = beat // 2
    d = _Dice('marks', absbar, sec.get('name'))
    turn = sec.get('_turn')
    busy = sec.get('_busy')
    new_turn = turn is not None and turn[0] == 0
    last_of_turn = turn is not None and turn[0] == turn[1] - 1
    landing = state.pop('crash_next', False)
    if (off == 0 and sec.get('_arc', 0) > 0) or new_turn or landing:
        # a new section, a new soloist, or the landing after a fill
        bar.add(0, beat, ('u', _CRASH, int(84 + 24 * heat)))
        bar.add(0, beat, ('u', _KICK, int(82 + 20 * heat)))
    phrase_end = (off + 1) % 4 == 0 or off == sec['bars'] - 1 \
        or last_of_turn
    if any(k == 'fill' and b == off + 1 for b, k, _t in
           sec.get('events') or ()):
        return                     # the roadmap's own fill is coming
    big_end = (off + 1) % 8 == 0 or off == sec['bars'] - 1 or last_of_turn
    if phrase_end and bar.num >= 3:
        r = d()
        if big_end and r < 0.3 + 0.5 * heat or last_of_turn:
            kind = _FILLS[int(d() * len(_FILLS)) % len(_FILLS)]
            if kind == state.get('last_fill'):
                kind = _FILLS[(_FILLS.index(kind) + 1 + int(d() * 3))
                              % len(_FILLS)]
            state['last_fill'] = kind
            beats = 2 if (heat > 0.65 or last_of_turn) and d() < 0.55 \
                else 1
            _fill(bar, kind, (bar.num - beats) * beat, heat, d)
            state['crash_next'] = True     # and land it on the one
        elif r < 0.75:
            # the setup: snare and kick on the and of four
            t = (bar.num - 1) * beat + half
            bar.add(t, half, ('u', _KICK, int(78 + 20 * heat)))
            if d() < 0.6:
                bar.add(t, half, ('u', _SNARE, int(62 + 20 * heat)))
    else:
        # comping: a kick bomb and a snare answer, off the beat — in the
        # soloist's gaps, not on top of a busy line
        want = (heat - 0.35) if busy is None else \
            (0.55 - busy) * (0.6 + heat)
        if bar.num >= 4 and d() < want:
            spots = [1.5, 2.5, 3.5]
            k = spots[int(d() * 3) % 3]
            bar.add(int(k * beat), half, ('u', _KICK,
                                           int(66 + 26 * heat)))
            s2 = spots[int(d() * 3) % 3]
            if s2 != k:
                bar.add(int(s2 * beat), half,
                        ('u', _SNARE, int(48 + 20 * heat)))


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
    if q in ('6', '69', '6/9'):
        return (0, 2, 4, 5, 7, 9, 11)          # a 6 chord is major
    if q[0].isdigit() and '#11' in q:
        return (0, 2, 4, 6, 7, 9, 10)
    if q[0].isdigit() or 'sus' in q:
        return (0, 2, 4, 5, 7, 9, 10)
    if '#11' in q:
        return (0, 2, 4, 6, 7, 9, 11)
    if q == '5':
        return (0, 3, 5, 7, 10)
    return (0, 2, 4, 5, 7, 9, 11)


SALT = ''          # the tune's own name: every tune rolls its own dice


class _Dice:
    """A seeded LCG: the same bar and player always roll the same —
    and a different tune rolls differently (every tune's bar 5 used to
    get the same comping)."""
    def __init__(self, *seed):
        import zlib
        self.s = zlib.crc32(repr((SALT,) + seed).encode()) or 1

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


def comp_shells(bar, state, chords, absbar=0):
    """A pianist soloing still comps under the line: the left hand's
    3rd and 7th on the changes, voiced around C3-D4 and led smoothly,
    in a rhythm that changes bar to bar — on the change, a Charleston,
    a stab on the and of two, now and then a bar of air (Matthew,
    2026-09-29: the left hand "only using one note")."""
    beat = bar.div * 4 // bar.den
    d = _Dice('shells', absbar)
    feel = int(d() * 10)
    for b, c in chords:
        if c is None:
            continue
        root = _root_pc(c)
        iv = _tones(c)
        pcs = [(root + i) % 12 for i in iv if i % 12 in (3, 4)][:1] + \
            [(root + i) % 12 for i in iv if i % 12 in (9, 10, 11)][:1]
        if len(pcs) < 2:
            pcs = (_guide(c) + [(root + 7) % 12])[:2]
        anchor = state.get('shell', 53)
        if not 48 <= anchor <= 58:
            anchor = 53
        # the lower voice nearest the last one, inside C3-Bb3; the other
        # guide tone the next one up, so the shell swaps 3-7 / 7-3
        cands = [_near(pc, anchor) for pc in pcs]
        cands = [m + 12 if m < 48 else m - 12 if m > 58 else m
                 for m in cands]
        low = min(cands, key=lambda m: (abs(m - anchor), m))
        other = [pc for pc in pcs if pc != low % 12][0]
        up = low + 1
        while up % 12 != other:
            up += 1
        v = [low, up]
        state['shell'] = low
        at = int(round((b - 1) * beat))
        span = beat * 2
        nxt = [bb for bb, _c in chords if bb > b]
        if nxt:
            span = int(round((nxt[0] - b) * beat))
        if feel == 0 and b == 1.0:
            continue                           # a bar of air
        if feel in (1, 2, 3) and span >= 3 * beat:
            # Charleston: on the change, again on the and of two
            for m in v:
                bar.add(at, beat // 2, ('p', m, 56))
                bar.add(at + beat + beat // 2, beat // 2, ('p', m, 52))
        elif feel in (4, 5) and span >= 2 * beat:
            # late: the and of the change's first beat
            for m in v:
                bar.add(at + beat // 2, span - beat, ('p', m, 54))
        elif feel in (6, 7) and span >= 2 * beat:
            # a short one on the change, a second on beat three
            for m in v:
                bar.add(at, beat - beat // 4, ('p', m, 56))
                if span >= 3 * beat:
                    bar.add(at + 2 * beat, beat // 2, ('p', m, 50))
        else:
            for m in v:
                bar.add(at, max(beat, span - beat // 3), ('p', m, 56))


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
        shapes = [[(2.5, 0.5, 62), (4.0, 1.0, 66)],
                  [(1.0, 1.5, 64), (3.5, 0.5, 60)],
                  [(1.5, 0.5, 60), (2.5, 1.5, 66)]]
        cycle = shapes[int(d() * len(shapes)) % len(shapes)]
        hits = cycle if off % 2 == 0 else [(1.0, 2.0, 58)]
        hits = [(b, ln, v) for b, ln, v in hits if b <= n + 0.99]
    else:
        hits = []
        for i, (b, c) in enumerate(chords):
            nxt = chords[i + 1][0] if i + 1 < len(chords) else n + 1
            hits.append((b, nxt - b, 48))   # well under the soloist
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
    'horn': (12, True, 1.0), 'voice': (7, False, 0.7),
    'keys': (16, True, 1.0), 'guitar': (14, True, 1.0),
    'bass': (8, False, 0.7),
}


PERSONAS = ('lyrical', 'bebop', 'bluesy', 'modern')
_PERSONA_KINDS = {
    'lyrical': {'state': ['motif', 'answer', 'lifted', 'stretched'],
                'develop': ['sequence', 'stretched', 'line', 'lifted'],
                'peak': ['line', 'sequence', 'stretched']},
    'bebop': {'state': ['line', 'motif', 'line', 'answer'],
              'develop': ['line', 'line', 'sequence', 'displaced'],
              'peak': ['line', 'run', 'line']},
    'bluesy': {'state': ['riff', 'motif', 'answer', 'line'],
               'develop': ['riff', 'line', 'displaced', 'motif'],
               'peak': ['riff', 'line', 'riff']},
    'modern': {'state': ['displaced', 'line', 'lifted', 'motif'],
               'develop': ['line', 'displaced', 'sequence'],
               'peak': ['run', 'line', 'displaced']},
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


def _one_voice(notes):
    """A horn plays one note at a time: phrases planned side by side
    (an arpeggio running into a line, an echo against a spill-over)
    must never sound together. Same onset, the later-planned note
    loses; a note still sounding when the next begins stops just
    before it (Matthew heard the trumpet play two notes at once)."""
    out = []
    for at, ln, m, v in sorted(notes, key=lambda n: (n[0], -n[3])):
        if out and abs(out[-1][0] - at) < 1e-6:
            continue
        if out and out[-1][0] + out[-1][1] > at - 0.02:
            pa, pl, pm, pv = out[-1]
            out[-1] = (pa, max(at - pa - 0.02, 0.05), pm, pv)
        out.append((at, ln, m, v))
    return out


def plan_solo(chord_fn, total_bars, bar_beats, lo, hi, feel, seed,
              voice='horn', echo=None, start_after=0.0,
              next_soloist=False, persona=None, breaks=()):
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
    # who this player is: the lyrical one, the bebopper, the blues
    # player, the modern one — each tells a different kind of story
    persona = persona or PERSONAS[int(d() * len(PERSONAS)) % len(PERSONAS)]
    kinds = _PERSONA_KINDS[persona]
    space = {'lyrical': 1.4, 'bebop': 0.8, 'bluesy': 1.0,
             'modern': 1.0}[persona]
    if voice == 'keys':
        space *= 0.7              # a pianist's lines run on longer
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

    def heatx(a):
        return {'state': 0.2, 'develop': 0.5, 'peak': 0.9, 'home': 0.3}[a]

    def vel(a):
        return {'state': 78, 'develop': 86, 'peak': 96, 'home': 78}[a]

    def eighth_line(t, length, a, cur, v, c0):
        # the bebop way: every downbeat a chord tone of the chord
        # sounding there (at a change, its 3rd or 7th: the guide
        # tones), every offbeat leading into the next target — a
        # half step under or over it, or the scale step between;
        # now and then an arpeggio up the chord
        pickup = None
        if t % 1:
            # an upbeat start is a pickup into the line, whose chord
            # tones stay on the beats
            pickup, t, length = t, math.ceil(t), length - (math.ceil(t) - t)
            if length < 1.0:
                return cur
        start_i = len(notes)
        p_trip = _SOLO['grid'].get('triplet', 0.18) * (0.5 if a == 'state'
                                                       else 0.8)
        half = _SOLO.get('half_step_into_beat_tone', 0.29) + 0.06
        step = 0.5
        n = max(2, int(length / step * dens))
        if n % 2:
            n += 1
        bot, top = bounds(a)
        q = fit(snap(cur, c0, _tones(c0)), a)
        dirn = 1 if q < (lo + hi) / 2 else -1
        targets, prev_c = [], None
        for k in range(n // 2 + 1):
            at = t + k * 1.0
            c = chord_fn(at) or c0
            root = _root_pc(c)
            tones = list(_tones(c))
            changed = prev_c is not None and c != prev_c
            # what a real player puts on the beat (Weimar: about half
            # chord tones, a third colours, the rest passing notes) —
            # the guide tones still mark most changes
            cat = _roll([(k, w) for k, w in
                         _SOLO['on_beat'].items()], d)
            if changed and d() < 0.65:
                pool = [iv for iv in tones if iv % 12 in (3, 4, 10, 11)]
            elif cat == 'color':
                pool = list(_colors(c)) or tones
            elif cat == 'other' and a != 'state':
                pool = [iv for iv in _scale(c) if iv % 12 not in
                        {x % 12 for x in tones}] or tones
            else:
                pool = tones
            # the line moves on, pulled toward the act's register:
            # the climax is played up high, the opening in the middle
            reg = lo + (hi - lo) * {'state': 0.4, 'develop': 0.55,
                                    'peak': 0.85, 'home': 0.5}[a]
            jump = 5 if persona == 'modern' and d() < 0.5 else \
                2 + int(d() * 3)
            aim = 0.55 * (q + dirn * jump) + 0.45 * reg
            cands = [m for m in range(bot, top + 1)
                     if (m - root) % 12 in {iv % 12 for iv in pool}
                     # a line moves on: never the target just played,
                     # nor rocking back to the one before it
                     and m != q
                     and not (len(targets) > 1 and m == targets[-2])]
            if not cands:
                cands = [q]
            nq = min(cands, key=lambda m: (abs(m - aim), m))
            if nq >= top - 1 or nq <= bot + 1:
                dirn = -dirn
            targets.append(nq)
            q, prev_c = nq, c
        arp_at = int(d() * (n // 2)) if d() < 0.35 + 0.2 * heatx(a) \
            else -1
        for k in range(n // 2):
            at = t + k * 1.0
            if at >= min(t + length, total):
                break
            c = chord_fn(at) or c0
            tg, nxt_tg = targets[k], targets[k + 1]
            vv = v + (0 if k % 2 else 3)
            if k == arp_at:
                # up the chord from where the line is
                root = _root_pc(c)
                ivs = sorted({iv % 12 for iv in _tones(c)})
                ups = [m for m in range(tg, min(tg + 13, top + 1))
                       if (m - root) % 12 in ivs][:4]
                for j, m in enumerate(ups):
                    if at + j * step < min(t + length, total):
                        notes.append((at + j * step, step * 0.9, m,
                                      vv + 2 * j))
                targets[k + 1] = ups[-1] if ups else nxt_tg
                continue
            if d() < p_trip and at + 1.0 <= min(t + length, total):
                # a triplet turn: the target, its upper neighbour, and a
                # half step into the next one
                up = scale_move(tg, 1, c)
                for j, m in enumerate((tg, up, nxt_tg - 1 if nxt_tg > tg
                                       else nxt_tg + 1)):
                    notes.append((at + j / 3, 0.3, m, vv - 2 * (j == 1)))
                continue
            notes.append((at, step * 0.92, tg, vv))
            r = d()
            if r < half * 0.6:
                app = nxt_tg - 1                  # from below
            elif r < half:
                app = nxt_tg + 1                  # from above
            else:
                app = scale_move(tg, 1 if nxt_tg > tg else -1, c)
                if app == nxt_tg:
                    app = nxt_tg + (1 if nxt_tg < tg else -1)
            if at + step < min(t + length, total):
                notes.append((at + step, step * 0.92, app,
                              vv + (4 if swingy else 0)))
        if pickup is not None and targets:
            notes.append((pickup, 0.45, targets[0] - 1
                          if d() < 0.6 else targets[0] + 2, v - 4))
        # the end of the phrase: never a lead-in left hanging. Half the
        # time a short chord note on the and ("doo-BAH"); otherwise the
        # line resolves onto its next target and holds it a little
        mine = [i for i in range(start_i, len(notes))
                if notes[i][0] >= t - 1e-6]
        if mine:
            li = max(mine, key=lambda i: notes[i][0])
            la, _ll, lm, lv = notes[li]
            c = chord_fn(la) or c0
            if la % 1 and d() < _SOLO['end_position'].get('and', .5) / \
                    max(1e-6, sum(_SOLO['end_position'].values())):
                pool = list(_tones(c)) + list(_colors(c))[:2]
                notes[li] = (la, 0.4, snap(lm, c, pool), lv + 4)
                return notes[li][2]
            k = min(len(targets) - 1, n // 2)
            land = math.floor(la) + 1.0
            if land < total:
                hb = int(_roll([(int(x), w) for x, w in
                                _SOLO['end_len_half_beats'].items()
                                if 1 <= int(x) <= 4], d))
                cl = chord_fn(land) or c
                goal = targets[k] if (targets[k] - _root_pc(cl)) % 12 in \
                    {i % 12 for i in _tones(cl)} else \
                    snap(targets[k], cl, _tones(cl))
                notes.append((land, 0.47 * hb, goal, v))
                return goal
        return targets[min(len(targets) - 1, n // 2)]

    def phrase_len(lo_b, hi_b):
        """A phrase as long as real players make them (Weimar: half
        under two bars, a quarter past three), inside this act's span."""
        opts = [(int(k), w) for k, w in _SOLO['phrase_beats'].items()
                if lo_b <= int(k) <= hi_b]
        return float(_roll(opts, d)) if opts else float(lo_b)

    def breath():
        """The rest between phrases: mostly one to three beats."""
        opts = [(int(k) / 2, w) for k, w in _SOLO['gap_half_beats'].items()
                if 1 <= int(k) <= 12]
        return _roll(opts, d) if opts else 2.0

    t = t_open or (0.5 if d() < 0.5 else 0.0)   # sometimes a pickup in
    last_kind = None
    told = 0                                 # phrases so far in act one
    while t < total - 0.5:
        # every phrase starts on the grid, however the last one ended
        t = math.ceil(t * 2 - 1e-6) / 2
        if t >= total - 0.5:
            break
        a = act(t)
        if a == 'state':
            # state it, answer it, lift it, stretch it
            ks = kinds['state']
            kind = ks[told % len(ks)]
            told += 1
            length = min(phrase_len(2, 9), max_len)
            rest = breath() * space * 1.2
        elif a == 'develop':
            ks = kinds['develop']
            kind = ks[int(d() * len(ks)) % len(ks)]
            if kind == last_kind:
                kind = ks[(ks.index(kind) + 1) % len(ks)]
            length = min(phrase_len(4, 14), max_len)
            rest = breath() * space
        elif a == 'peak':
            ks = kinds['peak']
            kind = ks[int(d() * len(ks)) % len(ks)]
            if kind == last_kind:
                kind = ks[(ks.index(kind) + 1) % len(ks)]
            if kind == 'run' and not runs_ok:
                kind = 'line'
            length = min(phrase_len(6, 21), max_len)
            rest = breath() * 0.8
        else:
            kind = 'home'
            length = total - t
            rest = 0
        length = max(1.0, min(round(length * 2) / 2, total - t))
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
        if kind in ('motif', 'answer', 'displaced', 'sequence', 'lifted',
                    'stretched'):
            # the idea keeps talking: it grows into a line through the
            # rest of the phrase (early on, sometimes it just breathes)
            said = max(n[0] for n in notes)
            if t + length - said >= 1.5 and (a != 'state' or d() < 0.6):
                at = math.ceil((said + 0.5) * 2 - 1e-6) / 2
                cur = eighth_line(at, t + length - at, a, cur, v,
                                  chord_fn(at) or c0)
        elif kind == 'line':
            cur = eighth_line(t, length, a, cur, v, c0)
        elif kind == 'riff':
            c = c0
            root = _root_pc(c)
            top = fit(snap(cur + 5, c, _tones(c)), a)
            cell = [(0.0, top), (0.5, scale_move(top, -1, c)),
                    (1.0, snap(top - 3, c, _tones(c)))]
            if persona == 'bluesy':
                # the blues lick: the minor third bent up to the major,
                # home to the root
                r0 = fit(_near(root, cur), a)
                cell = [(0.0, r0 + 3), (0.5, r0 + 4), (1.0, r0),
                        (1.5, r0 - 2)]
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
            if total - t > 3 * bar_beats:
                # still talking on the way home; the closing idea comes
                # in the last couple of bars, not five bars early
                cur = eighth_line(t, total - 2 * bar_beats - t - 1.0,
                                  'develop', cur, v, c0)
                t = total - 2 * bar_beats
                c0 = chord_fn(t) or c0
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
        # phrases start on the grid — a downbeat or an upbeat, never a
        # fraction between (lines landed ~a third of a beat late against
        # every change, Matthew 2026-09-29 on Autumn Leaves)
        t = math.ceil(t * 2 - 1e-6) / 2
        # the next phrase usually comes in on an upbeat (Weimar: more
        # than half of all phrases start on an 'and')
        if d() < 0.55 and t % 1 == 0:
            t += 0.5
    for b0, b1 in breaks:
        # a solo break: the band has stopped and the soloist talks
        # through it — a line from the band's hit to the re-entry,
        # played strong, landing where the band comes back
        if b0 >= total:
            continue
        b1 = min(b1, total)
        before = [n for n in notes if n[0] < b0]
        notes = [n for n in notes if not b0 <= n[0] < b1]
        cur = before[-1][2] if before else int(lo + (hi - lo) * 0.6)
        eighth_line(b0 + 0.5, b1 - b0 - 0.5, 'peak', cur, 96,
                    chord_fn(b0 + 0.5) or chord_fn(b0))
    return _one_voice(notes)


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


# ------------------------------------------------ the pianist, properly

# Matthew, 2026-09-29, on Trading Room: "Piano sounds like a young dude
# who doesn't know what to do." A working jazz pianist comps with
# rootless voicings (the bassist has the root) in the A and B forms,
# between about C3 and E5, each chord taking whichever form and octave
# moves least from the last, and places them in a small vocabulary of
# rhythms — Charleston, reverse Charleston, the push on the and of four
# that plays the next bar's chord early, a held chord, space — sparer
# early in the tune, busier as it builds, never the same bar twice.

def _rootless(chord):
    """(A form, B form) as semitones above the root."""
    q = (chord[2] if chord else '') or 'maj'
    if q in ('m7b5', 'm9b5'):
        return (3, 6, 10, 14), (10, 14, 15, 18)
    if q.startswith('dim'):
        return (3, 6, 9, 14), (9, 14, 15, 18)
    if 'sus' in q:
        return (5, 7, 10, 14), (10, 14, 17, 19)
    if q in ('mmaj7', 'mmaj9'):
        return (3, 7, 11, 14), (11, 14, 15, 19)
    if q.startswith('m') and not q.startswith('maj'):
        if q in ('m', 'm6', 'm69'):
            return (3, 7, 9, 14), (9, 14, 15, 19)
        return (3, 7, 10, 14), (10, 14, 15, 19)
    if q == 'alt' or any(t in q for t in ('b9', '#9', 'b13', '#5')) \
            and q[0].isdigit():
        return (4, 8, 10, 15), (10, 13, 16, 20)
    if q in ('6', '69', '6/9'):            # major, no 7th
        return (4, 7, 9, 14), (9, 14, 16, 19)
    if q[0].isdigit():
        if '#11' in q:
            return (4, 6, 10, 14), (10, 14, 16, 18)
        return (4, 9, 10, 14), (10, 14, 16, 21)
    if q in ('6', '69', 'maj'):
        return (4, 7, 9, 14), (9, 14, 16, 19)
    if '#11' in q:
        return (4, 6, 11, 14), (11, 14, 16, 18)
    return (4, 7, 11, 14), (11, 14, 16, 19)


def rootless_voicing(chord, prev, size=4):
    """The chord's rootless voicing nearest the last one: both forms,
    every octave with its bottom between C3 and C4, the least total
    movement winning (a gentle pull toward the middle of the piano)."""
    root = _root_pc(chord)
    best, best_cost = None, None
    for form in _rootless(chord):
        ivs = form[:size] if size < 4 else form
        for base in range(36, 72):
            if base % 12 != root:
                continue
            v = [base + i for i in ivs]
            if not 48 <= v[0] <= 60 or v[-1] > 77:
                continue
            if prev:
                cost = sum(abs(a - b) for a, b in
                           zip(sorted(v), sorted(prev)))
            else:
                cost = 0
            cost += abs(sum(v) / len(v) - 62) * 0.35
            if best_cost is None or cost < best_cost:
                best, best_cost = v, cost
    return best or [_near(pc, 60) for pc in _guide(chord)]


# (beat, length in beats, weight); a length ending past the bar is cut
_PIANO_BARS = {
    'charleston': [(1.0, 0.5, 70), (2.5, 0.7, 66)],
    'reverse':    [(1.5, 0.5, 64), (3.0, 0.7, 68)],
    'push':       [(2.5, 0.5, 62), (4.5, 0.5, 72)],
    'held':       [(1.0, 1.8, 62)],
    'two_four':   [(2.0, 0.4, 60), (4.0, 0.4, 64)],
    'one_three':  [(1.0, 0.6, 66), (3.5, 0.6, 64)],
    'lay_out':    [],
    'answer':     [(2.5, 0.4, 62), (3.5, 0.4, 66), (4.5, 0.5, 70)],
}


def _quartal(chord, prev):
    """Modal comping: fourths stacked on a note of the chord's mode, a
    major third on top (the So What voicing), placed near the last."""
    root = _root_pc(chord)
    sc = sorted({(root + i) % 12 for i in _scale(chord)})
    best, cost = None, None
    for base in range(48, 58):                 # top stays under ~F5
        if base % 12 not in sc:
            continue
        v = [base, base + 5, base + 10, base + 15, base + 19]
        if any((m % 12) not in sc for m in v[:4]):
            continue
        c = sum(abs(a - b) for a, b in zip(v, prev)) if prev and \
            len(prev) == 5 else abs(base - 57)
        if cost is None or c < cost:
            best, cost = v, c
    return best


def piano_comp(bar, state, absbar, chords, next_chord, heat, sound_id,
               feel='', busy=None):
    """One bar of a jazz pianist with two hands: the left holds the
    foundation low, the right plays colour and rhythm above; the
    texture changes every couple of bars and never repeats back to
    back; modal fourths where the harmony sits still; room when the
    soloist is busy, an answer when they breathe (Matthew, 2026-09-29:
    "piano should use both hands ... the whole range ... modal comping,
    everything")."""
    beat = bar.div * 4 // bar.den
    half = beat // 2
    d = _Dice(sound_id, 'piano', absbar)
    style, traits = style_of(feel or '')
    ballad = 'ballad' in traits or 'ballad' in (feel or '').lower()
    c0 = _chord_at(chords, 1.0)
    if c0 is None:
        return
    static = next_chord is not None and next_chord == c0 and \
        len({c for _b, c in chords}) == 1
    modal_ok = static and ((c0[2] or '').startswith(('m7', 'm9', 'm11'))
                           or 'sus' in (c0[2] or '')
                           or (c0[2] or '') in ('maj7', 'maj9', '6', '69'))
    # a new texture every two bars, never the one just played
    if absbar % 2 == 0 or 'tex' not in state:
        if ballad:
            pool = ['ballad_spread', 'ballad_roll', 'ballad_answer']
        else:
            pool = ['stab', 'stab', 'hold_answer', 'lay_out', 'stab',
                    'hold_answer'] if heat < 0.5 else \
                ['stab', 'hold_answer', 'stab', 'push_stab', 'hold_answer']
            if modal_ok:
                pool += ['modal', 'modal']
        if busy is not None and busy > 0.6 and not ballad:
            pool = ['lay_out', 'hold_answer', 'lay_out', 'stab']
        elif busy is not None and busy < 0.15 and not ballad:
            pool = ['hold_answer', 'push_stab', 'hold_answer']
        pick = pool[int(d() * len(pool)) % len(pool)]
        if pick == state.get('tex'):
            pick = pool[(pool.index(pick) + 1) % len(pool)]
        state['tex'] = pick
    # laying out is a bar of air, not two — the band never just stops
    if state['tex'] == 'lay_out' and state.get('laid') == absbar - 1:
        state['tex'] = 'hold_answer'
    if state['tex'] == 'lay_out':
        state['laid'] = absbar
    tex = state['tex']
    # now and then the right hand goes up for sparkle — rarely, and
    # only once the tune has built
    top = 1 if heat > 0.6 and d() < 0.15 else 0

    def lh(c, at, ln, w):
        """The left hand: a two-note shell, 3rd and 7th, around C3."""
        root = _root_pc(c)
        iv = _tones(c)
        pcs = [(root + i) % 12 for i in iv if i % 12 in (3, 4, 10, 11)][:2]
        if len(pcs) < 2:
            pcs = _guide(c)[:2]
        anchor = state.get('lh', 52)
        if not 45 <= anchor <= 57:
            anchor = 52                     # back to the middle, no drift
        v = sorted(_near(pc, anchor) for pc in pcs)
        v = sorted(m + 12 if m < 45 else m - 12 if m > 60 else m
                   for m in v)
        if len(v) == 2 and v[1] - v[0] < 3:
            v[1] += 12
        state['lh'] = v[0]
        state['lh_top'] = v[-1]
        for m in v:
            bar.add(at, ln, ('p', m, w - 6))

    def rh(c, at, ln, w):
        """The right hand: a close three-note grip of the chord's
        colours — 9, 13, 5, the 3rd and 7th, never the root — hung from
        a top note that moves like a little melody from the last one:
        mostly a step or a third, rarely the same note three times
        (Matthew, 2026-09-29: comping "meh" — every Cm7 was the same
        Bb-Eb-D-Eb grip, the top line going nowhere)."""
        root = _root_pc(c)
        ivs = {i % 12 for i in _tones(c)} | {i % 12 for i in _colors(c)}
        pool = {(root + i) % 12 for i in ivs if i != 0}
        cap = 84 if top else 79                      # G5, C6 for sparkle
        last = state.get('top', 72)
        same = state.get('top_same', 0)
        cands = [m for m in range(66, cap + 1) if m % 12 in pool]

        def cost(m):
            mv = abs(m - last)
            k = abs(mv - 2) * 0.8 + (4 if mv > 5 else 0)
            if mv == 0:
                k += 1.5 + 3 * same
            return k + 0.12 * abs(m - (74 + 5 * top)) + d() * 1.2
        t = min(cands, key=cost) if cands else last
        state['top_same'] = same + 1 if t == last else 0
        state['top'] = t
        v = [t]
        floor = max(55, state.get('lh_top', 55) + 2)
        for _ in range(2):
            have = {x % 12 for x in v}
            below = [m for m in range(v[0] - 5, v[0] - 1)
                     if m % 12 in pool and m % 12 not in have
                     and m >= floor]
            if not below:
                break
            # a third or fourth under reads clearer than a second
            v.insert(0, min(below, key=lambda m: (abs(v[0] - m - 3.5),
                                                  m)))
        for i, m in enumerate(v):
            bar.add(at, ln, ('p', m, w + (5 if i == len(v) - 1 else 0)))

    def at_(b):
        return int(round((b - 1) * beat))

    def chord_for(b):
        c = _chord_at(chords, b)
        return next_chord if b >= bar.num + 0.5 and next_chord else c

    w0 = int(62 + 16 * heat)
    if tex == 'lay_out':
        if d() < 0.4:                 # one light touch in the space
            b = [2.5, 3.5, 4.5][int(d() * 3) % 3]
            rh(chord_for(b), at_(b), half, w0 - 8)
        return
    if tex == 'modal':
        v = _quartal(c0, state.get('qv'))
        if v:
            state['qv'] = v
            root = _root_pc(c0)
            sc = sorted({(root + i) % 12 for i in _scale(c0)})
            # the voicing planes up the mode a step and back
            for k, (b, ln) in enumerate([(1.0, 1.4), (2.5, 0.5),
                                         (3.0, 0.9), (4.5, 0.5)]):
                if b > bar.num + 0.99 or d() < 0.2:
                    continue
                shift = 1 if k in (1, 2) else 0
                vv = []
                for m in v:
                    q = m
                    for _ in range(shift):
                        q += 1
                        while q % 12 not in sc:
                            q += 1
                    vv.append(q)
                for m in vv:
                    bar.add(at_(b), max(1, int(ln * beat)), ('p', m, w0))
        return
    if tex.startswith('ballad'):
        # the whole piano: a low root and tenth in the left hand, the
        # rootless colours high in the right, rolled or answered
        for i, (b, c) in enumerate(chords):
            if c is None:
                continue
            end = chords[i + 1][0] if i + 1 < len(chords) else bar.num + 1
            ln = int((end - b) * beat)
            root = _root_pc(c)
            lo_root = _near(root, 40)
            third = next(((root + i2) % 12 for i2 in _tones(c)
                          if i2 % 12 in (3, 4)), root)
            tenth = _near(third, lo_root + 15)
            bar.add(at_(b), ln, ('p', lo_root, w0 - 10))
            bar.add(at_(b), ln, ('p', tenth, w0 - 14))
            v = rootless_voicing(c, state.get('pv'), 4)
            state['pv'] = v
            roll = beat // 10 if tex == 'ballad_roll' else 0
            for k, m in enumerate(v):
                bar.add(at_(b) + k * roll, ln - k * roll,
                        ('p', m + 12 * top if m + 12 * top <= 81 else m,
                         w0 - 4 + (4 if k == len(v) - 1 else 0)))
        if tex == 'ballad_answer' and bar.num >= 4 and d() < 0.6:
            c = _chord_at(chords, 3.5)
            root = _root_pc(c)
            sc = [(root + i) % 12 for i in _scale(c)]
            m = _near(sc[int(d() * len(sc)) % len(sc)], 79)
            for k in range(3):
                bar.add(at_(3.5) + k * half, half, ('p', m, w0 - 6))
                m = next(x for x in range(m - 1, m - 4, -1)
                         if x % 12 in sc)
        return
    if tex == 'hold_answer':
        # left hand holds the change, the right answers off the beat
        for i, (b, c) in enumerate(chords):
            if c is None:
                continue
            end = chords[i + 1][0] if i + 1 < len(chords) else bar.num + 1
            lh(c, at_(b), int((end - b) * beat * 0.9), w0)
        for b in ([2.5, 4.0] if d() < 0.5 else [2.0, 3.5, 4.5]):
            if b <= bar.num + 0.99:
                rh(chord_for(b), at_(b), half, w0 - 4)
        return
    cells = [[(1.0, .5), (2.5, .7)], [(1.5, .5), (3.0, .7)],
             [(1.0, .6), (3.5, .6)], [(2.0, .4), (4.0, .4)],
             [(2.5, .5), (4.5, .5)], [(1.0, 1.5), (3.5, .5)]]
    if tex == 'push_stab':
        cells = [[(2.5, .5), (4.5, .5)], [(1.5, .5), (4.5, .5)]]
    cell = cells[int(d() * len(cells)) % len(cells)]
    if cell == state.get('cell'):
        cell = cells[(cells.index(cell) + 1) % len(cells)]
    state['cell'] = cell
    for b, ln in cell:
        if b > bar.num + 0.99:
            continue
        c = chord_for(b)
        if c is None:
            continue
        lh(c, at_(b), max(1, int(ln * beat)), w0)
        rh(c, at_(b), max(1, int(ln * beat)), w0)
