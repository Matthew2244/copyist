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
    '7b5': (0, 4, 6, 10), '7#5': (0, 4, 8, 10),
    '7b13': (0, 4, 7, 10, 20), '13b9': (0, 4, 7, 10, 13, 21),
    'alt': (0, 4, 8, 10, 13), '7sus4': (0, 5, 7, 10),
    'sus4': (0, 5, 7), 'sus2': (0, 2, 7),
    'dim': (0, 3, 6), 'dim7': (0, 3, 6, 9), 'm7b5': (0, 3, 6, 10),
    'aug': (0, 4, 8),
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


def role_of(sound_id, clef):
    s = (sound_id or '').lower()
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
    if role == 'drums':
        _drums(bar, absbar, feel, state['hits'])
    elif role == 'bass':
        _bass(bar, state, sec, off, absbar, feel, chords)
    else:
        _comp(bar, state, absbar, feel, chords, sound_id)
    state['hits'] = None
    return bar.xml()
