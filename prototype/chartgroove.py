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
    '13#11': (0, 4, 7, 10, 14, 18, 21), 'maj13#11': (0, 4, 7, 11, 14, 18, 21),
    '13#9': (0, 4, 7, 10, 15, 21),
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


# What the lead is playing in the bar being made (the melody, a written
# line, the soloist): [(start, end, midi)] in quarters from the bar's
# start, concert pitch. The chart compiler sets it for a chair that is
# making something up (comping, backgrounds), and that chair leaves out
# any note a half step from a lead note it would sound against — the
# pianist who hears the melody's Bb and drops the A from a Bbmaj7
# (Matthew, 2026-09-30: "make sure everyone is context aware and knows
# what to play and what not to play").
LEAD_NOW = None


# The horn section's written hits in the bar being made, for the
# drummer: [(start, length, air after)] in quarters from the bar's start,
# only where two or more horns or voices strike together.
ENSEMBLE_NOW = None
# The lowest a chord player makes up in this bar: set when the bass is
# playing, so the piano's left hand stays out of its register (below
# C3 a piano under a walking bass is mud).
FLOOR_NOW = None


def _catch(bar, hits, heat, d):
    """The drummer catches the band's figures: a short hit with air after
    it gets kick and snare, a held one or one after space gets crash and
    kick, and a hit coming out of a rest often gets its set-up, the snare
    on the eighth before. A busy line is caught at its accents, not note
    by note."""
    beat = bar.div * 4 // bar.den
    half = beat // 2
    # a hit is a short note with air after it, or a held note that comes
    # out of space; a long note ending a moving phrase is a phrase end,
    # and the drummer fills that space instead of slamming it
    marks, pe = [], 0.0
    for h in sorted(hits):
        if (h[1] <= 0.75 and h[2] >= 0.5) or (h[1] >= 1.5 and h[0] - pe
                                               >= 1.0):
            marks.append(h)
        pe = h[0] + h[1]
    if len(marks) > 4:
        marks = [marks[0], marks[-1]]
    # some bars the drummer plays the figure's shape on the toms: high
    # tom for its highest notes, the floor for its lowest
    melodic = len(marks) >= 2 and d() < 0.35 and all(
        len(h) > 3 for h in marks)
    if melodic:
        lo_p = min(h[3] for h in marks)
        hi_p = max(h[3] for h in marks)
    prev_end = 0.0            # space counts from the bar's start
    # one crash a bar at most, and none on top of the drummer's own
    crashed = any(n[1] == _CRASH for _l, ns in bar.onsets.values()
                  for n in ns if n[0] == 'u')
    for hit in sorted(hits):
        s, ln, air = hit[:3]
        if hit not in marks:
            prev_end = s + ln
            continue
        t = int(round(s * beat))
        big = ln >= 1.5 or s - prev_end >= 1.5 or air >= 1.5
        vel = int(92 + 12 * min(heat, 1.0))
        if melodic:
            f = (hit[3] - lo_p) / max(hi_p - lo_p, 1)
            drum = _HI_TOM if f > 0.66 else _MID_TOM if f > 0.33 \
                else _FLOOR_TOM
            bar.add(t, half, ('u', drum, vel + 8))
            bar.add(t, half, ('u', _KICK, vel))
            if big and not crashed and d() < 0.5:
                bar.add(t, beat, ('u', _CRASH, vel + 4))   # and ring it
                crashed = True
        elif big and not crashed:
            # the big one, the drummer's own way: often a crash, but a
            # choke, a bark or snare and kick as often
            if kit_hit(bar, t, beat, d, big=True) == 'crash':
                crashed = True
        else:
            bar.add(t, half, ('u', _SNARE, vel if not big else vel + 6))
            bar.add(t, half, ('u', _KICK, vel))
        if s - prev_end >= 1.0 and t >= half and d() < 0.55:
            bar.add(t - half, half, ('u', _SNARE, vel - 14))   # set-up
        prev_end = s + ln


def _heard(s, e):
    """A lead note the band would voice around: on a beat or held."""
    return e - s >= 0.75 or abs(s - round(s)) < 0.01


def hands_can_play(bar, fastest=0.055):
    """No drum struck again before a hand could really strike it: a
    second stroke on the same drum within `fastest` seconds of the last
    (a buzz roll's speed) goes, unless it's a flam (a soft grace right
    against a loud stroke). Samples retrigger into each other there and
    it sounds like a double trigger, not a drummer."""
    gap = max(1, -int(-(bar.div * BPM / 60.0 * fastest) // 1))
    last = {}                     # drum -> (tick, velocity)
    for t in sorted(bar.onsets):
        ln, ns = bar.onsets[t]
        keep = []
        for n in ns:
            if n[0] == 'u':
                k, v = n[1], (n[2] if len(n) > 2 and n[2] else 80)
                # the bell is the ride cymbal too: one cymbal, one stroke
                same = [j for j, o in enumerate(keep)
                        if o[0] == 'u' and (o[1] == k or {o[1], k} == {
                            _RIDE, _BELL})]
                if same:
                    # one foot, one kick: the same drum twice at once is
                    # one stroke, the louder
                    j = same[0]
                    if v > (keep[j][2] or 0):
                        keep[j] = n
                        last[k] = (t, v)
                    continue
                if k in last and t - last[k][0] < gap:
                    pv = last[k][1]
                    if not (min(v, pv) <= 0.65 * max(v, pv)):
                        continue          # too fast, and not a flam
                last[k] = (t, v)
            keep.append(n)
        if keep:
            bar.onsets[t] = (ln, keep)
        else:
            del bar.onsets[t]


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
            ns = self.onsets[tick][1]
            if note[0] == 'p':
                # one key can't be struck twice at once (both hands on
                # the same note flammed in the listen): keep the louder
                for k, n in enumerate(ns):
                    if n[0] == 'p' and n[1] == note[1]:
                        if (note[2] or 0) > (n[2] or 0):
                            ns[k] = note
                        return
            ns.append(note)
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

    def _two_hands(self):
        """A drummer has two hands and two feet: at one instant at most
        two things struck by hand (drums, cymbals, the hat with a
        stick), plus the kick and the hi-hat foot. Never three drums or
        cymbals at once (Matthew, 2026-10-01: "no matter what ... think
        realistically"). The two that matter most stay: a crash or an
        open hat, then the snare, the toms, the cross-stick, the ride,
        the closed hat. And the hat can't be open and shut by the foot
        at the same instant."""
        rank = {_CRASH: 0, _OPEN_HAT: 1, _SNARE: 2, _HI_TOM: 3,
                _MID_TOM: 3, _FLOOR_TOM: 3, _XSTICK: 4, _BELL: 5,
                _RIDE: 6, _HAT: 7}
        for t in list(self.onsets):
            ln, ns = self.onsets[t]
            hands = [n for n in ns if n[0] == 'u' and n[1] not in
                     (_KICK, _HATF)]
            feet = [n for n in ns if not (n[0] == 'u' and n[1] not in
                                          (_KICK, _HATF))]
            if any(n[1] == _OPEN_HAT for n in hands):
                feet = [n for n in feet if not (n[0] == 'u'
                                                and n[1] == _HATF)]
            seen, uniq = set(), []
            for n in sorted(hands, key=lambda n: rank.get(n[1], 3)):
                if n[1] not in seen:
                    seen.add(n[1])
                    uniq.append(n)
            self.onsets[t] = (ln, uniq[:2] + feet)

    def _above_the_bass(self, floor):
        """Up an octave for anything under the floor; a note the chord
        already has there is not doubled."""
        for t in list(self.onsets):
            ln, ns = self.onsets[t]
            out, seen = [], set()
            for n in ns:
                if n[0] == 'p':
                    m = n[1]
                    while m < floor:
                        m += 12
                    if m in seen:
                        continue
                    seen.add(m)
                    n = (n[0], m) + tuple(n[2:])
                out.append(n)
            self.onsets[t] = (ln, out)

    def _hear_the_lead(self, lead):
        """Drop every pitched note a half step (or a minor ninth, or
        more octaves) from a lead note it overlaps by an eighth or more,
        so a voicing never rubs against the melody or the soloist."""
        q = float(self.div)
        heard = [(s, e, m) for s, e, m in lead if _heard(s, e)]
        if not heard:
            return
        for tick in list(self.onsets):
            ticks, notes = self.onsets[tick]
            a, b = tick / q, (tick + ticks) / q
            over = [m for s, e, m in heard if min(b, e) - max(a, s)
                    >= 0.5 - 1e-6]
            top = max(over) if over else None
            moved = []
            for n in notes:
                if n[0] == 'p' and top is not None and top >= 64 and \
                        n[1] > top:
                    # stay under the melody: a voicing on top of the
                    # lead masks it — down an octave, or out if that
                    # would be mud
                    m_ = n[1] - 12
                    while m_ > top:
                        m_ -= 12
                    if m_ < 50:
                        continue
                    n = (n[0], m_) + tuple(n[2:])
                moved.append(n)
            # out of the lead's own spot: a comping note on the melody
            # note or a step off it, in the same octave, crowds the
            # voice (a singer hears it as pitch to fight) — it moves an
            # octave, up over a low voice (comping above a baritone is
            # home), down under a high one, out if that would be mud
            # (2026-10-01, measured on a baritone tune: the guitar sat on
            # the sung note or a step off it 13% of the time). The bass
            # is the floor and keeps its notes.
            near = [m for s, e, m in heard
                    if min(b, e) - max(a, s) >= 0.5 - 1e-6]

            def crowds(x):
                return any(abs(x - m) <= 2 for m in near)
            spaced = []
            for n in moved:
                if n[0] == 'p' and near and n[1] >= 50 and crowds(n[1]):
                    up = min(near) < 60
                    for x in ((n[1] + 12, n[1] - 12) if up else
                              (n[1] - 12, n[1] + 12)):
                        if 50 <= x <= 84 and not crowds(x) and (
                                x < max(near) or min(near) < 64):
                            n = (n[0], x) + tuple(n[2:])
                            break
                    else:
                        continue
                spaced.append(n)
            moved = spaced
            keep = [n for n in moved if n[0] != 'p' or not any(
                min(b, e) - max(a, s) >= 0.5 - 1e-6
                and (n[1] - m) % 12 in (1, 11) for s, e, m in heard)]
            seen, uniq = set(), []
            for n in keep:            # an octave move can double a note
                k_ = (n[0], n[1]) if n[0] == 'p' else id(n)
                if k_ not in seen:
                    seen.add(k_)
                    uniq.append(n)
            keep = uniq
            if keep:
                self.onsets[tick] = (ticks, keep)
            else:
                del self.onsets[tick]

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
        had = bool(self.onsets)
        self._two_hands()
        hands_can_play(self)
        if FLOOR_NOW:
            self._above_the_bass(FLOOR_NOW)
        if LEAD_NOW:
            self._hear_the_lead(LEAD_NOW)
        if not self.onsets:
            # the filters can empty a bar; it is then a rest, never None
            # to a caller that already saw notes in it
            return self._rest(self.barlen) if had else None
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
_HI_TOM = ('E', 5, 'normal')
_MID_TOM = ('D', 5, 'normal')
_FLOOR_TOM = ('A', 4, 'normal')
_COWBELL = ('B', 5, 'triangle')
_RIDE = ('F', 5, 'x')
_HATF = ('D', 4, 'x')
_HAT = ('G', 5, 'x')
_SNARE = ('C', 5, 'normal')
_KICK = ('F', 4, 'normal')
_CRASH = ('A', 5, 'x')


def _load_drums():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'data', 'drum_stats.json')) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


_DRUM = _load_drums()
_SLOT_NAMES = ['1', '1t', '1&', '2', '2t', '2&', '3', '3t', '3&', '4',
               '4t', '4&']


def _slot_beat(sl):
    """A swing-grid slot -> the beat it's written on: a swung 'and' as
    the half (the warp swings it), a middle triplet as the third."""
    return sl // 3 + 1 + (0, 1 / 3, 0.5)[sl % 3]


def _swing_time(bar, absbar, heat, busy, feather=True):
    """Swing time the way real drummers keep it (learn_drums.py over the
    Groove MIDI Dataset's jazz drummers): the ride from their own
    vocabulary at their own frequencies — the classic ding, ding-ga in
    two bars of five, the rest its variations; the snare comping in
    ghosts and the odd accent, busier as the band heats up and quieter
    under a busy soloist; the kick feathered or dropping on 1, 3 and the
    ands; the hi-hat foot on 2 and 4, an 'and' now and then (Matthew,
    2026-09-29: "the ride pattern on the drums doesn't have to be the
    same ... same with the hihat on two and four ... everyone should be
    able to react")."""
    beat = bar.div * 4 // bar.den
    half = beat // 2
    d = _Dice('ride', absbar)
    heat = 0.55 if heat is None else heat
    stats = _DRUM or {}
    pats = [(tuple(p['slots']), p['share']) for p in
            stats.get('ride_patterns', []) if 0 in p['slots']]
    if not pats:
        pats = [((0, 3, 5, 6, 9, 11), 0.5), ((0, 3, 6, 9), 0.1)]
    weights = []
    for sl, w in pats:
        n = len(sl)
        if heat > 0.6 and n >= 7:
            w *= 2.5                     # it burns: skips everywhere
        if (heat < 0.4 or (busy is not None and busy > 0.7)) and n <= 5:
            w *= 1.8                     # it lays back
        weights.append((sl, w))
    pick = _roll(weights, d)
    base = int(62 + 16 * heat)
    bell = d() < 0.06 + 0.08 * heat
    for sl in pick:
        b = _slot_beat(sl)
        if b > bar.num + 0.99:
            continue
        at = int(round((b - 1) * beat))
        on2_4 = sl % 3 == 0 and (sl // 3) % 2 == 1
        v = base + (6 if on2_4 else -14 if sl % 3 else 0) + \
            int((d() - 0.5) * 8)
        cym = _BELL if bell and sl in (0, 6) else _RIDE
        ln = beat // 3 if sl % 3 else half
        bar.add(at, ln, ('u', cym, max(30, min(v, 118))))
    # the hi-hat foot: 2 and 4 mostly; sometimes only 4, all four when
    # it's hot, and now and then an 'and' dropped in
    r = d()
    if r < 0.1:
        feet = [4]
    elif r < 0.18 and heat > 0.5:
        feet = [1, 2, 3, 4]
    else:
        feet = [2, 4]
    if d() < 0.15 and bar.num >= 4:
        feet.append(1.5 if d() < 0.5 else 3.5)
    hv = int(54 + 16 * heat)
    for b in feet:
        if b <= bar.num + 0.5:
            bar.add(int(round((b - 1) * beat)), half,
                    ('u', _HATF, hv + int((d() - 0.5) * 8)))
    if heat > 0.65 and d() < 0.2 and bar.num >= 4:
        bar.add(3 * beat + half, half, ('u', ('G', 5, 'circle-x'),
                                        int(56 + 14 * heat)))
    # the kick: feathered quarters, or a few placed kicks
    if feather and d() < 0.35:
        for b in range(bar.num):
            bar.add(b * beat, half, ('u', _KICK, 26 + int(d() * 12)))
    else:
        kn = _roll([(0, 0.33 + 0.2 * (1 - heat)), (1, 0.2), (2, 0.25 * heat
                                                           + 0.1),
                    (3, 0.15 * heat)], d)
        ks = [(_SLOT_NAMES.index(k), w) for k, w in
              stats.get('kick_slot', {'1': .22, '3': .18, '3&': .11,
                                      '4&': .1}).items()
              if _SLOT_NAMES.index(k) % 3 != 1]
        used = set()
        for _ in range(kn):
            sl = _roll(ks, d)
            if sl in used or _slot_beat(sl) > bar.num + 0.99:
                continue
            used.add(sl)
            bar.add(int(round((_slot_beat(sl) - 1) * beat)), half,
                    ('u', _KICK, int(50 + 18 * heat + (d() - 0.5) * 10)))
    # the snare comps: ghosts, and an accent now and then
    sn = _roll([(int(k), w) for k, w in stats.get(
        'snare_per_bar', {'0': .25, '1': .11, '2': .17, '3': .12,
                          '4': .1}).items() if int(k) <= 5], d)
    sn = int(round(sn * (0.4 + 0.9 * heat)))
    if busy is not None and busy > 0.6:
        sn //= 2                         # the soloist is talking
    ss = [(_SLOT_NAMES.index(k), w) for k, w in
          stats.get('snare_slot', {'2&': .1, '4&': .1, '1&': .1,
                                   '3&': .1, '2': .1}).items()]
    # one comping idea across the two-bar phrase, the way a drummer
    # talks: stated in the first bar, varied in the second — not a new
    # scatter every bar (Matthew, 2026-09-30: "the ideas are also
    # telling a story and not running into each other")
    pd = _Dice('comp idea', absbar // 2)
    cell = set()
    for _ in range(max(sn, 1) + 1):
        sl = _roll(ss, pd)
        if _slot_beat(sl) <= bar.num + 0.99:
            cell.add(sl)
    cell = sorted(cell)[:max(sn, 0)]
    if absbar % 2 == 1 and cell:
        # the answer: one moved to a neighbouring partial, one maybe
        # dropped or added
        r = pd()
        if r < 0.4:
            cell[-1] = min(cell[-1] + 1, 3 * bar.num - 1)
        elif r < 0.7 and len(cell) > 1:
            cell = cell[:-1]
        else:
            extra = _roll(ss, pd)
            if _slot_beat(extra) <= bar.num + 0.99:
                cell = sorted(set(cell) | {extra})
    accent_at = cell[int(pd() * len(cell)) % len(cell)] if cell and \
        pd() < 0.25 + 0.25 * heat else None
    for sl in cell:
        v = int(64 + 20 * heat) if sl == accent_at else int(32 + 14 * d())
        bar.add(int(round((_slot_beat(sl) - 1) * beat)),
                beat // 3 if sl % 3 else half, ('u', _SNARE, v))


def _chop_wood(bar, how):
    """Chopping wood on a shout: the comping snare gives way to the
    cross-stick on the backbeat (2 and 4, or just 4), or a cross-stick
    on 2 answered by the high tom on 4 and its 'and'; the ride and the
    hat foot keep going."""
    beat = bar.div * 4 // bar.den
    half = beat // 2
    for t in list(bar.onsets):
        ln, ns = bar.onsets[t]
        keep = [n for n in ns if not (n[0] == 'u' and n[1] == _SNARE)]
        if keep:
            bar.onsets[t] = (ln, keep)
        else:
            del bar.onsets[t]
    if how in ('24', '24kick'):
        for b in (1, 3):
            bar.add(b * beat, half, ('u', _XSTICK, 96))
        if how == '24kick':
            for b in (0, 2):
                bar.add(b * beat, half, ('u', _KICK, 78))
    elif how == '4':
        bar.add(3 * beat, half, ('u', _XSTICK, 100))
    else:                                    # 2, then the tom on 4 and &
        bar.add(beat, half, ('u', _XSTICK, 96))
        bar.add(3 * beat, half, ('u', _HI_TOM, 100))
        bar.add(3 * beat + half, half, ('u', _HI_TOM, 92))


def _chopping_hand(bar, how='24'):
    """Chopping wood is the foundation, so it's solid (Matthew,
    2026-10-01): the cross-stick pattern exactly, every bar, at one
    weight. The left hand lies across the snare on the rim, so there's
    no time to get back to the snare head: whatever else the bar would
    have put on the snare goes to the kick, or in a fast run the high
    tom, and no stray cross-stick muddies the pattern."""
    beat = bar.div * 4 // bar.den
    q = max(beat // 2, 1)
    for t in list(bar.onsets):
        ln, ns = bar.onsets[t]
        out, seen = [], set()
        for n in ns:
            if n[0] == 'u' and n[1] == _XSTICK:
                continue                      # the pattern goes back below
            if n[0] == 'u' and n[1] == _SNARE:
                n = ('u', _KICK if t % q == 0 else _HI_TOM) + tuple(n[2:])
            k = (n[0], n[1])
            if k in seen:
                continue
            seen.add(k)
            out.append(n)
        if out:
            bar.onsets[t] = (ln, out)
        else:
            del bar.onsets[t]
    beats = {'24': (1, 3), '24kick': (1, 3), '4': (3,), '2tom': (1,)}.get(
        how, (1, 3))
    for b in beats:
        if b < bar.num:
            bar.add(b * beat, beat // 2, ('u', _XSTICK, 100))


def unison_strokes(bar, fig, beat, d, end_beats):
    """The drummer playing a line with the whole band, musically
    (Matthew, 2026-10-01: "hihat barks with the snare or kick or both
    depending on the line and what's being played before and after ...
    open hat or crash with kick or snare"): fig is [(beat, length,
    semitones)]. Big out of a rest; a held note rings (a crash or open
    hat, the snare up high in the line, the kick down low); a short note
    with air after it barks (the hat opened with the kick, the snare or
    both, the foot shutting it); a run is the snare, the kick on the
    beats; the last note pushes into the hit."""
    if not fig:
        return
    half = beat // 2
    semis = [x for _a, _l, x in fig]
    lo_s, hi_s = min(semis), max(semis)
    prev_end = -9.0
    for i, (a, ln, x) in enumerate(fig):
        t = int(round(a * beat))
        nxt = fig[i + 1][0] if i + 1 < len(fig) else end_beats
        before, after = a - prev_end, nxt - (a + ln)
        high = (x - lo_s) / max(hi_s - lo_s, 1) > 0.5
        last = i == len(fig) - 1
        if last:
            bar.add(t, half, ('u', _SNARE, 112))
            bar.add(t, half, ('u', _KICK, 106))
        elif i == 0 or before >= 1.0:
            r = d()
            if r < 0.5:
                bar.add(t, beat, ('u', _CRASH, 110))
                bar.add(t, half, ('u', _KICK, 104))
            elif r < 0.75:
                bar.add(t, beat, ('u', _OPEN_HAT, 106))
                bar.add(t, half, ('u', _KICK, 104))
            else:
                bar.add(t, beat, ('u', _CRASH, 110))
                bar.add(t, half, ('u', _SNARE, 106))
        elif ln >= 1.0:
            bar.add(t, beat, ('u', _CRASH if d() < 0.55 else _OPEN_HAT,
                              106))
            bar.add(t, half, ('u', _SNARE if high else _KICK, 104))
        elif after >= 0.5:
            r = d()
            bar.add(t, half, ('u', _OPEN_HAT, 104))
            if r < 0.4 or r >= 0.75:
                bar.add(t, half, ('u', _KICK, 100))
            if r >= 0.4:
                bar.add(t, half, ('u', _SNARE, 104))
            if t + half < bar.barlen:
                bar.add(t + half, half, ('u', _HATF, 74))   # the bark
        else:
            bar.add(t, half, ('u', _SNARE, 100 + int(8 * d())))
            if abs(a - round(a)) < 0.01:
                bar.add(t, half, ('u', _KICK, 94))
        prev_end = a + ln


def _with_the_kicks(bar, state, chords, hits, who):
    """The rhythm section on the horns' kicks, the band as one: on each
    hit the piano punches a voicing, the bass the root, held as long as
    the hit, nothing in between, so the kicks have air."""
    beat = bar.div * 4 // bar.den
    hits = _kicks_of(hits)
    if not hits:
        return False                  # a line, not kicks: play as usual
    for s0, ln, _air, *_r in hits:
        c = _chord_at(chords, s0 + 1.0)
        if c is None:
            continue
        t = int(round(s0 * beat))
        dur = max(int(round(min(ln, 2.0) * beat)) - beat // 8, beat // 4)
        if who == 'bass':
            m = _fold_bass(_near(_bass_pc(c), state.get('bass', 38)), 28, 55)
            bar.add(t, dur, ('p', m, 104))
            state['bass'] = m
        else:
            for m in rootless_voicing(c, None):
                bar.add(t, dur, ('p', m, 100, ('accent',)))
    return True


def _kicks_of(hits):
    """The section's kicks among its notes together: a short hit with
    air after it, or a held one coming out of space (the drummer's own
    test, _catch). A soli line moving together is not kicks."""
    out, pe = [], 0.0
    for h in sorted(hits):
        if (h[1] <= 0.75 and h[2] >= 0.5) or (h[1] >= 1.5 and h[0] - pe
                                               >= 1.0):
            out.append(h)
        pe = h[0] + h[1]
    return out if len(out) <= 4 and len(out) * 2 >= len(hits) else []


def _hat_time(bar, feather, how='copy'):
    """Swing time on the hi-hat instead of the ride, one of the ways a
    drummer plays it (Matthew, 2026-10-01: "look up other hihat swing
    patterns"): the ride's pattern on the closed hat ('copy'); quarter
    notes leaning on 2 and 4 ('quarters'); "tsss-chick", the hat open on
    1 and 3 and shut by the foot on 2 and 4 ('chick'); or quarters with
    the swung skip notes into 2 and 4 ('skip'). Firm enough to carry
    the band. The kick may feather light quarters under it."""
    beat = bar.div * 4 // bar.den
    half = beat // 2
    rides = sorted(t for t, (_l, ns) in bar.onsets.items()
                   if any(n[0] == 'u' and n[1] == _RIDE for n in ns))
    for t in list(bar.onsets):
        ln, ns = bar.onsets[t]
        keep = [n for n in ns if not (n[0] == 'u' and n[1] in (_RIDE,
                                                               _HATF))]
        if keep:
            bar.onsets[t] = (ln, keep)
        else:
            del bar.onsets[t]
    if how == 'copy':
        for t in rides:
            back = (t // beat) % 2 == 1 and t % beat == 0
            bar.add(t, half, ('u', _HAT, 84 if back else 74))
    else:
        for b in range(bar.num):
            t = b * beat
            if how == 'chick':
                if b % 2 == 0:
                    bar.add(t, beat, ('u', _OPEN_HAT, 78))
                else:
                    bar.add(t, half, ('u', _HATF, 92))
                    bar.add(t, half, ('u', _HAT, 80))
            else:
                bar.add(t, half, ('u', _HAT, 86 if b % 2 else 72))
                if how == 'skip' and b % 2 == 0:
                    bar.add(t + 2 * beat // 3, beat // 3, ('u', _HAT, 62))
    if feather:
        for b in range(bar.num):
            t = b * beat
            if not any(n[1] == _KICK for n in bar.onsets.get(t, (0, ()))[1]):
                bar.add(t, beat // 2, ('u', _KICK, 30))


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


def swing_ratio(bpm):
    """How long the swung eighth is against the short one at this
    tempo, the way real trios play it (learn_timing.py over the Jazz
    Trio Database, MIT): wider than a triplet when it's slow (about
    2.4:1 under 160), a triplet around 180, flattening past 200 (about
    1.7:1 at 240). The rhythm section's three players averaged."""
    fits = {'piano': (1.19969, -0.0026772), 'bass': (1.11168, -0.0019385),
            'drums': (1.41205, -0.0038055)}
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'data', 'timing_stats.json')) as f:
            got = json.load(f)['ratio_fit']
        fits = {k: (v['a'], v['b']) for k, v in got.items()}
    except (OSError, ValueError, KeyError):
        pass
    r = sum(math.exp(a + b * bpm) for a, b in fits.values()) / len(fits)
    return max(1.4, min(2.8, r))


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


def walk_bar(beats, prev, d, arrive, next_arrive, home=None):
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
    walk_bar.goal = None
    steps = {int(k): v for k, v in _WALK['step'].items() if k != '0'}
    mid = _WALK['middle']
    appr = [(int(k), v) for k, v in _WALK['approach_interval'].items()
            if int(k) in (-1, 1, 2, -2, -5, 7)]
    reg = _WALK.get('register_percentiles', {})
    centre = reg.get('p50', 41)
    lo_h, hi_h = reg.get('p5', 31), reg.get('p95', 52)
    if home:
        # an electric bass lives higher than an upright: the low string
        # is a place to visit, not to walk on
        lo_h, centre, hi_h = home
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
        # the avoid notes: a scale tone a half step over a chord tone
        # (the 4th over a dominant or a major chord) sounds like a sus
        # nobody wrote when it's leaned on (chord-scale theory, checked
        # against PyTheory's avoid_notes, 2026-10-01)
        avoid = {pc for pc in sc - tones if (pc - 1) % 12 in tones}
        anchor = out[-1] if out else prev
        first = arrive if b == 0 else arrival_pc(c, d)
        # the downbeat lands where last bar's lead-in pointed: folding it
        # into the home range here made the lead-in leap an octave and a
        # step into it; the line walks back home over the bar instead
        m0 = _fold_bass(_near(first, anchor), 28, 55) if b == 0 and out == [] \
            else _fold_bass(_near(first, anchor), lo_h, hi_h)
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
            # beat 3 of four is the other strong beat: a bassist lands a
            # chord tone there and passes on 2 and 4
            strong = n == 4 and b + len(seg) == 2
            opts = []
            for m in range(max(28, cur - 9), min(55, cur + 9) + 1):
                if m == cur or (len(seg) > 1 and m == seg[-2]
                                and d() < 0.7):
                    continue
                pc = m % 12
                cat = 'tone' if pc in tones else 'scale' if pc in sc \
                    else 'chromatic'
                w = steps.get(m - cur, 0.004) * mid.get(cat, 0.1)
                if strong:
                    w *= 2.0 if cat == 'tone' else 0.08 if pc in avoid \
                        else 0.6
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
            walk_bar.goal = goal
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
    land_at = state.pop('land_at', None)
    # a bassist lives in the middle of the neck: nearest-note walking
    # drifts, so each bar starts from an anchor pulled back toward it
    # (Autumn Leaves climbed to G3 and stayed there, Matthew 2026-09-29)
    # — unless last bar's lead-in or run aimed at a note: then the
    # downbeat lands right there, and the line comes home from it
    if land_at is not None:
        prev = land_at
    elif prev > 52:
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
    two_now = False
    if _is_swing(feel) and bar.den == 4 and not state.get('turn') and \
            not re.search(r'\bwalk|\bin (?:4|four)\b|\bfour[ -]?feel',
                          (feel or '').lower()):
        # the bassist's own call on a head, in the moment (Matthew,
        # 2026-09-30: "two feel ... decided live and in the moment, or if
        # it's written in the chart or roadmap"): often in two the first
        # time through, less later on, sometimes two for the first half
        # and walking into the second
        lap = absbar // 1000
        key = (sec.get('name'), lap)
        got = state.setdefault('two', {})
        if key not in got:
            d2 = _Dice('two feel', sec.get('name'), lap)
            first = sec.get('_arc', 0) == 0
            if d2() < (0.55 if first else 0.25):
                got[key] = sec['bars'] if d2() < 0.65 else \
                    max(sec['bars'] // 2, 1)
            else:
                got[key] = 0
        two_now = off < got[key]
    if _is_swing(feel) and bar.den == 4 and not two_now:
        # the bassist listens too: two feel at the top of a soloist's
        # turn, skips and triplet pickups as it builds, a run into the
        # next bar when the soloist breathes
        d = _Dice('bass', absbar)
        heat = state.get('heat', 0.55)
        busy = state.get('busy')
        turn = state.get('turn')
        target = _near(_next_root(sec, off, chords), prev)
        # behind a soloist the bass walks (Matthew, 2026-10-01: "bass
        # should be walking all the time for solos unless being told to
        # play two feel, or decides in the moment"): two at the top of a
        # turn is a rare call of the moment, made once for the whole
        # turn, and never in a trade
        top_two = bool(turn) and turn[0] < 2 and turn[1] >= 8 and \
            _Dice('two at the top', sec.get('name'),
                  absbar - turn[0])() < 0.12
        if top_two and bar.num == 4:
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
                        prev, d, arrive, next_arrive,
                        home=(33, 43, 53) if 'electric' in
                        state.get('sound', '') else None)
        target = _fold_bass(_near(next_arrive if next_arrive is not None
                                  else _next_root(sec, off, chords),
                                  line[-1]), 28, 55)
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
        # where the next downbeat lands: the run's target, or the note
        # the lead-in approached
        state['land_at'] = target if run else walk_bar.goal
        return
    if bar.den == 8 and bar.num % 3 == 0:
        pulse = 3 * (bar.div // 2)
        for p in range(bar.num // 3):
            c = _chord_at(chords, p * 3 + 1.0)
            pc = _bass_pc(c) if p % 2 == 0 else (_root_pc(c) + 7) % 12
            prev = put(p * pulse, pulse, _near(pc, prev))
        return
    nxt_pc = _next_root(sec, off, chords)
    for b in range(bar.num):
        c = _chord_at(chords, b + 1.0)
        if b % 2 == 0:
            # a two-feel: the root, then the fifth — or, with a new
            # chord coming, a step into it (never the root twice)
            pc = _bass_pc(c)
            if b > 0 and _chord_at(chords, float(b)) == c:
                if b + 2 >= bar.num and nxt_pc != _bass_pc(c):
                    tgt = _fold_bass(_near(nxt_pc, prev), 28, 55)
                    m = tgt - 1 if (absbar + b) % 3 else tgt + 2
                    prev = put(b * beat, beat * 2 - bar.div // 2, m)
                    continue
                pc = (_root_pc(c) + 7) % 12
            prev = put(b * beat, beat * 2 - bar.div // 2,
                       _fold_bass(_near(pc, prev),
                                  33 if 'electric' in state.get('sound', '')
                                  else 28, 55))
        elif bar.num >= 4 and b == bar.num - 1 and absbar % 2 == 0:
            # the pickup approaches the next downbeat the way a bassist
            # does: a half step under or over, a step above, or a fifth;
            # chosen near the last note it could leap a ninth into it
            tgt = _fold_bass(_near(nxt_pc, prev), 28, 55)
            dp = _Dice('two pickup', absbar)
            m = tgt + (-1, -1, 1, 2, -5, 7)[int(dp() * 6) % 6]
            if m == prev or not 28 <= m <= 55:
                m = tgt - 1
            prev = put(b * beat + beat // 2, beat // 2, m, 60)


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
    s = (sound_id or '').lower()
    # every comper has a home on the instrument: nearest-note voice
    # leading drifted a guitar up into the sixth octave over a long tune
    home_lo, home_hi = (50, 64) if 'guitar' in s else (53, 67)
    ceiling = 76 if 'guitar' in s else 81
    floor = 53 if 'vibraphone' in s else 40   # the vibes stop at F3
    anchor = state.get('comp', 60 if 'guitar' in s else 62)
    while anchor > home_hi:
        anchor -= 12
    while anchor < home_lo:
        anchor += 12
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
            while v and max(v) > ceiling:
                v = sorted(m - 12 if m > ceiling else m for m in v)
            v = sorted(m + 12 if m < floor else m for m in v)
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
        while v and max(v) > ceiling:
            v = sorted(m - 12 if m > ceiling else m for m in v)
        v = sorted(m + 12 if m < floor else m for m in v)
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
    if 'guitar' in s and _is_swing(feel) and bar.den == 4 and \
            not state.get('big_band'):
        # a small group's guitarist decides per section in the moment:
        # comp in spots like a pianist's left hand, or four to the bar
        key = (state.get('sec_name'), absbar // 1000)
        got = state.setdefault('fg', {})
        if key not in got:
            got[key] = _Dice('guitar feel', key[0], key[1])() < 0.4
        if not got[key]:
            comp_shells(bar, state, chords, absbar,
                        state.get('next_chord'))
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
            if role == 'drums':
                kit_hit(bar, 0, beat, _Dice('break hit', absbar))
            elif role == 'perc':
                bar.add(0, beat // 2, ('u', ('C', 5, 'normal'), 100))
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
            state['crash_next'] = 'break'      # the band is back: commit
        state['hits'] = None
        return bar.xml()
    state['busy'] = sec.get('_busy')      # how busy the soloist is here
    state['answer'] = sec.get('_answer')  # the soloist's phrase, to pick up
    state['heat'] = heat
    state['turn'] = sec.get('_turn')
    state['sec_name'] = sec.get('name')
    if role == 'perc':
        _perc(bar, absbar, feel, sound_id, state['hits'])
    elif role == 'drums':
        # swing time: the snare comps (a backbeat groove's snare is the
        # time itself, never cleared for a bigger idea)
        state['swing_time'] = _is_swing(feel) and not _new_style(feel, bar)
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
            if state['hits'] is None and _is_swing(feel) and \
                    not _new_style(feel, bar):
                # the time on the ride or on a closed hi-hat with the kick
                # feathering, the drummer's call per section (Matthew,
                # 2026-09-30); the chart's own words settle it
                if re.search(r'\b(?:on (?:the )?hats?|closed hi-?hat|'
                             r'hi-?hat time)\b', words):
                    on_hat, feath = True, True
                elif re.search(r'\bride\b', words):
                    on_hat, feath = False, False
                else:
                    key = (sec.get('name'), absbar // 1000)
                    ht = state.setdefault('hat_time', {})
                    if key not in ht:
                        d3 = _Dice('hat time', *key)
                        # a shout stays on the ride
                        # behind somebody else's solo the drummer sticks
                        # to the ride, the hat a rare choice (Matthew,
                        # 2026-10-01: "when others are soloing, drummer
                        # should stay on the ride ... stick to the ride")
                        p = 0.0 if sec.get('_energy', 0) >= 0.8 else \
                            0.04 if sec.get('_turn') or \
                            sec.get('_busy') is not None else \
                            0.45 if sec.get('_arc', 0) == 0 else 0.25
                        ht[key] = (d3() < p, d3() < 0.7,
                                   ('copy', 'copy', 'quarters', 'chick',
                                    'skip')[int(d3() * 5) % 5])
                    on_hat, feath = ht[key][:2]
                if on_hat:
                    _hat_time(bar, feath, (state.get('hat_time', {}).get(
                        (sec.get('name'), absbar // 1000)) or
                        (0, 0, 'copy'))[2])
                elif sec.get('_energy', 0) >= 0.8 and bar.num == 4 and \
                        not re.search(r'\bride only\b', words):
                    # a shout on the ride; the drummer may chop wood too
                    # (Matthew, 2026-09-30): the cross-stick on 2 and 4,
                    # on 4 alone, or a cross-stick on 2 with the high tom
                    # on 4 and its 'and' — the drummer's call per shout
                    ck = (sec.get('name'), absbar // 1000)
                    chop = state.setdefault('chop', {})
                    if ck not in chop:
                        dc = _Dice('chop wood', *ck)
                        chop[ck] = None if dc() < 0.45 else \
                            ('24', '4', '2tom', '24kick')[int(dc() * 4) % 4]
                    if chop[ck]:
                        _chop_wood(bar, chop[ck])
                    state['chopping'] = chop[ck]
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
        if ENSEMBLE_NOW and impl not in ('brushes', 'mallets'):
            _catch(bar, ENSEMBLE_NOW, heat, _Dice('catch', absbar))
        chopping = state.pop('chopping', None)
        if chopping:
            _chopping_hand(bar, chopping)
        fills = {b: t for b, k, t in evs if k == 'fill'}
        if state.pop('cue_fill', False):
            fills[off + 1] = ''       # the drummer cues the band out
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
    elif role == 'bass' and ENSEMBLE_NOW and _with_the_kicks(
            bar, state, chords, ENSEMBLE_NOW, 'bass'):
        state['sound'] = sound_id
    elif role == 'bass':
        state['sound'] = sound_id
        _bass(bar, state, sec, off, absbar, feel, chords)
    elif ENSEMBLE_NOW and _with_the_kicks(bar, state, chords,
                                          ENSEMBLE_NOW, 'comp'):
        pass
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
    if '_energy' in sec:
        e = sec['_energy'] + 0.1 * off / max(sec['bars'], 1)
        nxt = sec.get('_next_energy')
        left = sec['bars'] - off
        if nxt is not None and nxt - e > 0.2 and left <= 2:
            # the last two bars build into a bigger section, the whole
            # band leaning in together instead of jumping at the barline
            e += (nxt - e) * (0.35 if left == 2 else 0.7)
        return min(1.0, e)
    arc = sec.get('_arc', 0.5)
    return min(1.0, 0.3 + 0.55 * arc + 0.12 * off / max(sec['bars'], 1))


_FILLS = ('toms_down', 'triplets_around', 'snare_kick_talk', 'space_hits',
          'buzz_roll', 'flam_setup', 'toms_up')


# the tune's tempo, for anything with a speed limit in real hands
BPM = 120.0


def roll_step(beat, buzz=False):
    """The fastest a drummer's hands really go, in ticks per stroke, at
    this tempo: an open roll about 12 strokes a second, a buzz roll (the
    stick pressed into the head) the fastest, about 18 (faster than
    that the samples retrigger into each other). Thirty-seconds at
    176 is 23 a second, faster than hands, and the samples retrigger into
    each other (Matthew heard it, 2026-10-01: "double triggering ... a
    buzz roll should be fastest")."""
    rate = 18.0 if buzz else 12.0
    need = beat * BPM / 60.0 / rate
    for div in (8, 6, 4, 3, 2):
        st = beat // div
        if st >= need:
            return max(st, 1)
    return max(beat // 2, 1)


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
        step = roll_step(beat, buzz=True)
        for i, t in enumerate(range(start, end, step)):
            bar.add(t, step, ('u', _SNARE,
                              int(56 + (base - 50) * ((t - start) / span))
                              + (3 if i % 2 else -3)))
        bar.add(end - beat // 2, beat // 2, ('u', _SNARE, base + 12))
        bar.add(end - beat // 2, beat // 2, ('u', _KICK, base + 8))
    else:                                         # flam_setup
        for b in (0.0, 1.0, 1.5):
            t = start + int(b * beat)
            if t < end:
                bar.add(max(t - beat // 12, 0), beat // 12,
                        ('u', _SNARE, base - 30))
                hit(t, _SNARE, beat // 2, base + 4)


_OPEN_HAT = ('G', 5, 'circle-x')


def _lick(bar, t, beat, strokes, vel):
    """A quick lick of sixteenths landing its last stroke on t (or,
    with no room before t, starting there). Returns where it lands."""
    u = max(beat // 4, 1)
    start = t - (len(strokes) - 1) * u
    if start < 0:
        start = t
    for i, dr in enumerate(strokes):
        tt = start + i * u
        if tt < bar.barlen:
            bar.add(tt, u, ('u', dr, min(vel - 8 + 5 * i, 122)))
    return min(start + (len(strokes) - 1) * u, bar.barlen - 1)


def land_hit(bar, t, beat, d, crash_only=False):
    """Where a fill lands, the drummer's way (Matthew, 2026-09-30: "not
    need to end with crash cymbal and kick... crash cymbal and snare,
    open hat and snare, open hat and kick, etc")."""
    kinds = ['crash_kick', 'crash_snare', 'hat_snare', 'hat_kick',
             'crash_snare_kick', 'hat_crash_kick', 'choke_snare',
             'snare_kick']
    if crash_only:
        kinds = ['crash_kick', 'crash_snare', 'crash_snare_kick',
                 'hat_crash_kick']
    k = kinds[int(d() * len(kinds)) % len(kinds)]
    h = beat // 2
    if 'crash' in k and 'choke' not in k:
        bar.add(t, beat, ('u', _CRASH, 108))
    if k.startswith('hat'):
        bar.add(t, beat, ('u', _OPEN_HAT, 104))
    if k == 'choke_snare':
        bar.add(t, h, ('u', _CRASH, 110, ('staccato',)))
    if 'snare' in k:
        bar.add(t, h, ('u', _SNARE, 108))
    if 'kick' in k:
        bar.add(t, h, ('u', _KICK, 102))
    return k


def final_hit(bar, t, beat, d, ring):
    """The band's last hit, the drummer's way in the moment (Matthew,
    2026-09-30: "open hat and kick, or open hat, crash cymbal and kick
    ... a short snare snare kick ... snare high tom floor tom kick, or
    whatever"), always making sense: a held last chord gets something
    that rings; a short button may be choked or dry."""
    kinds = ['classic', 'hat_crash', 'crash_kick', 'crash_floor',
             'hat_kick']
    if t >= 3 * max(beat // 4, 1):
        kinds += ['ssk', 'shfk']        # a lick needs room to land on it
    if ring <= beat:
        kinds += ['choke', 'snare_kick']
    k = kinds[int(d() * len(kinds)) % len(kinds)]
    h = beat // 2
    land = t
    if k in ('ssk', 'shfk'):
        strokes = (_SNARE, _SNARE, _KICK) if k == 'ssk' else \
            (_SNARE, _HI_TOM, _FLOOR_TOM, _KICK)
        # the ringing cymbal goes down first: a bar keeps one length per
        # stroke, and the lick's short kick would clip it
        bar.add(t, ring, ('u', _CRASH, 110))
        land = _lick(bar, t, beat, strokes, 110)
    elif k == 'classic':
        bar.add(t, ring, ('u', _CRASH, 110))
        bar.add(t, h, ('u', _KICK, 104))
        bar.add(t, h, ('u', _SNARE, 94))
    elif k == 'hat_crash':
        bar.add(t, ring, ('u', _CRASH, 108))
        bar.add(t, ring, ('u', _OPEN_HAT, 104))
        bar.add(t, h, ('u', _KICK, 104))
    elif k == 'crash_kick':
        bar.add(t, ring, ('u', _CRASH, 110))
        bar.add(t, h, ('u', _KICK, 106))
    elif k == 'crash_floor':
        bar.add(t, ring, ('u', _CRASH, 108))
        bar.add(t, beat, ('u', _FLOOR_TOM, 112))
        bar.add(t, h, ('u', _KICK, 104))
    elif k == 'hat_kick':
        bar.add(t, ring, ('u', _OPEN_HAT, 108))
        bar.add(t, h, ('u', _KICK, 106))
    elif k == 'choke':
        bar.add(t, h, ('u', _CRASH, 112, ('staccato',)))
        bar.add(t, h, ('u', _KICK, 106))
        bar.add(t, h, ('u', _SNARE, 100))
    else:                                   # snare and kick, dry
        bar.add(t, h, ('u', _SNARE, 114))
        bar.add(t, h, ('u', _KICK, 108))
    return k


def kit_hit(bar, t, beat, d, big=True):
    """One hit the drummer's own way, in the moment (Matthew,
    2026-09-30: "a choke with the cymbal and kick, a snare hit, a hihat
    bark with the kick, snare or both, anything"): a crash and kick that
    ring, a choked cymbal, a lone snare, a hi-hat bark (open, then shut
    with the foot) with the kick, the snare or both, or snare and kick."""
    # and the toms and the bell (Matthew, 2026-09-30: "or just a tom hit
    # as well... anything. Drummers create melody too")
    kinds = ('crash', 'crash', 'choke', 'snare', 'bark_k', 'bark_s',
             'bark_ks', 'snare_kick', 'floor', 'toms', 'bell', 'hat_crash',
             'ssk', 'shfk') if big else \
        ('choke', 'snare', 'bark_k', 'bark_s', 'bark_ks', 'snare_kick',
         'crash', 'floor', 'hi_tom', 'toms', 'bell', 'ssk', 'shfk')
    k = kinds[int(d() * len(kinds)) % len(kinds)]
    if k in ('ssk', 'shfk') and t < 3 * max(beat // 4, 1):
        k = 'snare_kick'                # no room for a lick into it
    h = beat // 2
    if k == 'crash':
        bar.add(t, beat, ('u', _CRASH, 108))
        bar.add(t, beat, ('u', _KICK, 100))
    elif k == 'choke':
        bar.add(t, h, ('u', _CRASH, 110, ('staccato',)))
        bar.add(t, h, ('u', _KICK, 102))
    elif k == 'snare':
        bar.add(t, h, ('u', _SNARE, 116))
    elif k == 'snare_kick':
        bar.add(t, h, ('u', _SNARE, 110))
        bar.add(t, h, ('u', _KICK, 104))
    elif k == 'floor':
        bar.add(t, beat, ('u', _FLOOR_TOM, 112))
        bar.add(t, h, ('u', _KICK, 104))
    elif k == 'hi_tom':
        bar.add(t, h, ('u', _HI_TOM, 108))
    elif k == 'toms':                       # high, then down to the floor
        bar.add(t, h // 2 or 1, ('u', _HI_TOM, 106))
        if t + h // 2 < bar.barlen:
            bar.add(t + h // 2, h, ('u', _FLOOR_TOM, 112))
            bar.add(t + h // 2, h, ('u', _KICK, 102))
    elif k == 'bell':
        bar.add(t, beat, ('u', _BELL, 104))
        bar.add(t, h, ('u', _KICK, 100))
    elif k == 'hat_crash':                  # open hat, crash and kick
        bar.add(t, beat, ('u', _OPEN_HAT, 104))
        bar.add(t, beat, ('u', _CRASH, 106))
        bar.add(t, h, ('u', _KICK, 102))
    elif k in ('ssk', 'shfk'):   # "snare snare kick", "snare hi floor kick"
        if big and d() < 0.5 and t not in bar.onsets:
            bar.add(t, beat, ('u', _CRASH, 104))     # rings: first down
        _lick(bar, t, beat, (_SNARE, _SNARE, _KICK) if k == 'ssk' else
              (_SNARE, _HI_TOM, _FLOOR_TOM, _KICK), 108)
    else:
        bar.add(t, h, ('u', _OPEN_HAT, 104))
        if t + h < bar.barlen:
            bar.add(t + h, h, ('u', _HATF, 70))     # the foot shuts it
        if k in ('bark_k', 'bark_ks'):
            bar.add(t, h, ('u', _KICK, 102))
        if k in ('bark_s', 'bark_ks'):
            bar.add(t, h, ('u', _SNARE, 108))
    return k


def _clear_comp(bar, t0=0, t1=None):
    """The comping snare and the placed kicks step aside (the feathered
    kick and the hat foot stay) so a bigger idea — a bomb, an answer, a
    set-up — isn't played on top of them."""
    for t in [t for t in bar.onsets if t >= t0 and (t1 is None or t < t1)]:
        ln, ns = bar.onsets[t]
        keep = [n for n in ns if not (n[0] == 'u' and (
            n[1] == _SNARE or (n[1] == _KICK and (n[2] or 99) > 40)))]
        if keep:
            bar.onsets[t] = (ln, keep)
        else:
            del bar.onsets[t]


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
    quiet = state.pop('quiet_comp', None)
    if quiet:
        _clear_comp(bar, 0, quiet)
    # a vamp or a written-out repeat's later laps (absbar carries 1000
    # per lap) keep going: the crash is for the first time in
    lap = absbar >= 1000
    if (off == 0 and sec.get('_arc', 0) > 0 and not lap) or new_turn \
            or landing:
        # a new section, a new soloist, or the landing after a fill,
        # marked the drummer's own way in the moment: a crash is only
        # one choice (Matthew, 2026-09-30: "a drummer may not crash per
        # se") — a choke, a snare, a hi-hat bark, the kick alone, or
        # nothing but the change in what they play
        md = _Dice('mark', absbar, sec.get('name'))
        r = md()
        late = state.pop('land_late', None)
        if landing:
            # a fill that ended on the snare: the comping gives it room
            # before coming back in (Matthew, 2026-10-01)
            _clear_comp(bar, (late or 0) + 1, (late or 0) + int(1.5 * beat))
        if landing and late:
            # the fill carried over the barline: it keeps going to its
            # landing on the 'and' of one or on two
            time_after = {t: v for t, v in bar.onsets.items() if t > late}
            _fill(bar, state.get('last_fill') or 'toms_down', 0, 0.8, md)
            for t in [t for t in bar.onsets if t >= late]:
                del bar.onsets[t]
            bar.onsets.update(time_after)     # and the time picks up
            land_hit(bar, late, beat, md)
            landing, r = False, 1.0
        elif landing and landing != 'break' and r < 0.8:
            land_hit(bar, 0, beat, md)
            landing, r = False, 1.0
        elif landing == 'break':
            land_hit(bar, 0, beat, md, crash_only=True)
            landing, r = False, 1.0
        crash = 1.0 if landing == 'break' else 0.55 if landing else 0.45
        if r < crash:
            bar.add(0, beat, ('u', _CRASH, int(88 + 20 * heat)))
            bar.add(0, beat, ('u', _KICK, int(84 + 18 * heat)))
        elif r < crash + 0.25:
            kit_hit(bar, 0, beat, md, big=heat > 0.5)
        elif r < crash + 0.4:
            bar.add(0, beat, ('u', _KICK, int(82 + 20 * heat)))
    # welcoming a new soloist, like the audience clapping them in —
    # right away, a bar later, or not at all, any phrasing (Matthew,
    # 2026-09-30)
    if new_turn and not sec.get('trade'):
        wd = _Dice('welcome', absbar, sec.get('name'))
        r = wd()
        if r < 0.45:
            state['welcome'] = (absbar, wd())
        elif r < 0.8:
            state['welcome'] = (absbar + 1, wd())
    elif off == 0 and not lap and sec.get('_arc', 0) > 0:
        # a new section gets its welcome too, like the audience going up
        # for a shout chorus (Matthew, 2026-09-30): more likely the
        # bigger the band's arrival, never automatic
        wd = _Dice('section welcome', absbar, sec.get('name'))
        if wd() < (0.6 if sec.get('_energy', 0.5) >= 0.8 else 0.25):
            state['welcome'] = (absbar if wd() < 0.6 else absbar + 1,
                                wd())
    wel = state.get('welcome')
    if wel and wel[0] == absbar and bar.num >= 4:
        state.pop('welcome', None)
        wd = _Dice('welcome hits', absbar)
        shape = int(wel[1] * 5) % 5
        if shape == 0:          # crashes with the kick after the one
            for bt in (1.5, 3.0):
                bar.add(int(bt * beat), beat, ('u', _CRASH, 100))
                bar.add(int(bt * beat), beat // 2, ('u', _KICK, 96))
        elif shape == 1:        # a hit, a little fill, a hit
            kit_hit(bar, int(0.5 * beat), beat, wd)
            _clear_comp(bar, beat) if state.get('swing_time') else None
            for i, t in enumerate(range(beat, 3 * beat, beat // 4)):
                bar.add(t, beat // 4, ('u', (('E', 5, 'normal'),
                                             ('D', 5, 'normal'),
                                             ('A', 4, 'normal'))[i // 3 % 3],
                                        90 + i))
            kit_hit(bar, 3 * beat, beat, wd)
        elif shape == 2:        # on one and three, big
            for bt in (0, 2):
                bar.add(bt * beat, beat, ('u', _CRASH, 104))
                bar.add(bt * beat, beat // 2, ('u', _KICK, 98))
        elif shape == 3:        # the push: the 'and' of one, then four
            kit_hit(bar, beat // 2, beat, wd)
            kit_hit(bar, 3 * beat, beat, wd, big=False)
        else:                   # a run of kicks under a crash
            bar.add(beat, beat, ('u', _CRASH, 100))
            for t in (beat, beat + beat // 3, 2 * beat):
                bar.add(t, beat // 3, ('u', _KICK, 94))
    phrase_end = (off + 1) % 4 == 0 or off == sec['bars'] - 1 \
        or last_of_turn
    if any(k == 'fill' and b == off + 1 for b, k, _t in
           sec.get('events') or ()):
        return                     # the roadmap's own fill is coming
    big_end = (off + 1) % 8 == 0 or off == sec['bars'] - 1 or last_of_turn
    if phrase_end and bar.num >= 3:
        r = d()
        # the end of a soloist's turn usually gets a fill; trading, the
        # drummer only fills into the next player when it feels right
        # (Matthew, 2026-10-01: "does not have to give a fill into the
        # next soloist, unless written or wants to")
        into_next = last_of_turn and (not sec.get('trade') or d() < 0.3)
        if big_end and r < 0.3 + 0.5 * heat and not (
                last_of_turn and sec.get('trade')) or into_next:
            kind = _FILLS[int(d() * len(_FILLS)) % len(_FILLS)]
            if kind == state.get('last_fill'):
                kind = _FILLS[(_FILLS.index(kind) + 1 + int(d() * 3))
                              % len(_FILLS)]
            state['last_fill'] = kind
            beats = 2 if (heat > 0.65 or last_of_turn) and d() < 0.55 \
                else 1
            # it starts where it starts: on a beat, or on the 'and'
            # (Matthew, 2026-10-01: "not everything has to start on the
            # down beat")
            f0 = (bar.num - beats) * beat + (half if d() < 0.35 else 0)
            _fill(bar, kind, f0, heat, d)
            # where it lands is the drummer's call: on the one, early on
            # the 'and' of four, or late into the next bar (Matthew,
            # 2026-09-30: "not every fill needs to end on the downbeat")
            wl = d()
            if wl < 0.25:
                t_ = bar.barlen - half
                for t in [t for t in bar.onsets if t >= t_]:
                    del bar.onsets[t]
                land_hit(bar, t_, beat, d)
                state['quiet_comp'] = beat     # the next bar breathes too
            else:
                state['crash_next'] = True     # and land it
                if wl > 0.72:
                    state['land_late'] = half if d() < 0.5 else beat
        elif r < 0.75:
            # the setup: snare and kick on the and of four
            t = (bar.num - 1) * beat + half
            if state.get('swing_time'):
                _clear_comp(bar, (bar.num - 1) * beat)
            bar.add(t, half, ('u', _KICK, int(78 + 20 * heat)))
            if d() < 0.6:
                bar.add(t, half, ('u', _SNARE, int(62 + 20 * heat)))
    elif state.get('answer') and d() < 0.4:
        # the drummer picks up the soloist's phrase: its rhythm on the
        # snare, the kick under the first of it
        if state.get('swing_time'):
            _clear_comp(bar)
        for i, b_ in enumerate(state['answer']):
            t = int(round(b_ * beat))
            if 0 <= t < bar.barlen:
                bar.add(t, half, ('u', _SNARE, int(70 + 20 * heat)))
                if i == 0:
                    bar.add(t, half, ('u', _KICK, int(72 + 20 * heat)))
    else:
        # comping: a kick bomb and a snare answer, off the beat — in the
        # soloist's gaps, not on top of a busy line
        want = (heat - 0.35) if busy is None else \
            (0.55 - busy) * (0.6 + heat)
        if bar.num >= 4 and d() < want:
            if state.get('swing_time'):
                _clear_comp(bar)        # the bomb is the idea this bar
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
    if q.startswith('13') and 'b13' not in q:
        # a 13 keeps its 13: b9 or #9 -> half-whole diminished, #11 ->
        # lydian dominant
        if '#11' in q and 'b9' not in q:
            return (0, 2, 4, 6, 7, 9, 10)
        if 'b9' in q or '#9' in q:
            return (0, 1, 3, 4, 6, 7, 9, 10)
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
        # a real hash: crc32 of seeds differing in one character (take 1,
        # take 2 ...) landed the first roll in nearly the same place, so
        # a "fresh take" kept making the same first choice (the shout
        # chopped wood in one take of eight, 2026-10-01)
        import hashlib
        self.s = int.from_bytes(hashlib.blake2s(
            repr((SALT,) + seed).encode(), digest_size=4).digest(),
            'big') & 0x7fffffff or 1

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


def _load_lh():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'data', 'lefthand_stats.json')) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'position': {'4&': .15, '2&': .147, '3&': .136, '1&': .122,
                             '1': .115, '3': .113, '4': .109, '2': .108}}


_LH = _load_lh()


def comp_shells(bar, state, chords, absbar=0, next_chord=None):
    """A pianist soloing still comps under the line — sparingly, the way
    trio pianists do it (learn_lefthand.py over the Jazz Trio Database:
    under one left-hand chord a bar on average, more than half of them
    on an 'and', the and of four reaching ahead to the next chord): the
    3rd and 7th around C3-Bb3, led smoothly, a bar of air now and then
    (Matthew, 2026-09-29: the left hand "only using one note ... not
    natural at all")."""
    beat = bar.div * 4 // bar.den
    d = _Dice('shells', absbar)
    # how many this bar: none, one, or two — about 0.9 on average
    k = _roll([(0, 0.22), (1, 0.62), (2, 0.16)], d)
    if k == 0:
        return
    pos = {'1': 1.0, '1&': 1.5, '2': 2.0, '2&': 2.5, '3': 3.0, '3&': 3.5,
           '4': 4.0, '4&': 4.5}
    opts = [(pos[p], w) for p, w in _LH['position'].items()
            if p in pos and pos[p] < bar.num + 1]
    # a new chord in the bar wants touching near where it arrives
    changes = [b for b, c in chords if c is not None and b > 1.0]
    picks = []
    for _ in range(k):
        if changes and not picks and d() < 0.5:
            at = changes[0] - (0.5 if d() < 0.5 else 0.0)
        else:
            at = _roll(opts, d)
        if all(abs(at - p) >= 1.0 for p in picks):
            picks.append(at)
    picks.sort()
    for n_, at in enumerate(picks):
        # the chord it belongs to: the one sounding, or on the and of
        # four the next bar's, played early
        c = _chord_at(chords, at)
        if at >= bar.num + 0.5 - 1e-6 and next_chord is not None:
            c = next_chord
        else:
            ahead = [cc for b, cc in chords if cc is not None and
                     at < b <= at + 0.5 + 1e-6]
            if ahead:
                c = ahead[0]
        if c is None:
            continue
        root = _root_pc(c)
        iv = _tones(c)
        pcs = [(root + i) % 12 for i in iv if i % 12 in (3, 4)][:1] + \
            [(root + i) % 12 for i in iv if i % 12 in (9, 10, 11)][:1]
        if len(pcs) < 2:
            pcs = (_guide(c) + [(root + 7) % 12])[:2]
        anchor = state.get('shell', 52)
        if not 47 <= anchor <= 57:
            anchor = 52
        cands = [_near(pc, anchor) for pc in pcs]
        cands = [m + 12 if m < 46 else m - 12 if m > 58 else m
                 for m in cands]
        low = min(cands, key=lambda m: (abs(m - anchor), m))
        other = [pc for pc in pcs if pc != low % 12][0]
        up = low + 1
        while up % 12 != other:
            up += 1
        v = [low, up]
        state['shell'] = low
        nxt = picks[n_ + 1] if n_ + 1 < len(picks) else bar.num + 1
        ln = max(beat // 2, int(round(min(nxt - at, 1.6) * beat)) - 20)
        t0 = int(round((at - 1) * beat))
        if t0 >= bar.barlen:
            continue
        w = 58 if at % 1 == 0 else 62            # the and speaks a touch
        for m in v:
            bar.add(t0, min(ln, bar.barlen - t0), ('p', m, w))


def solo_accents(bar, d, amount=1.0, end=None):
    """A drum solo's colour (Matthew, 2026-10-01: "more crashes with
    drums, like with any tom, snare, kick ... same goes for open hats"):
    a crash or an open hat on top of a stroke already there, never on an
    empty spot, mostly where a phrase starts or a beat lands, so it
    says something with what the drummer is playing."""
    beat = bar.div * 4 // bar.den
    end = bar.barlen if end is None else end
    strong = [t for t, (_l, ns) in bar.onsets.items() if t < end and any(
        n[0] == 'u' and n[1] in (_KICK, _SNARE, _HI_TOM, _MID_TOM,
                                 _FLOOR_TOM) for n in ns)]
    if not strong:
        return
    on_beat = [t for t in strong if t % beat == 0] or strong
    n_acc = int(amount * 1.5 + d() * 1.2)
    for _ in range(n_acc):
        pool = on_beat if d() < 0.7 else strong
        t = pool[int(d() * len(pool)) % len(pool)]
        if any(n[1] in (_CRASH, _OPEN_HAT) for n in bar.onsets[t][1]):
            continue
        tom = any(n[1] in (_FLOOR_TOM, _MID_TOM, _HI_TOM)
                  for n in bar.onsets[t][1])
        # no crash with any tom in a solo (Matthew, 2026-10-01: "take out
        # the crash and floor tom hit ... the crash with toms as well"):
        # the crash goes with the kick or the snare
        cym = _OPEN_HAT if tom or d() >= 0.6 else _CRASH
        bar.add(t, beat, ('u', cym, 100 + int(14 * d())))


def drum_solo(bar, absbar, pos, total, seed, echo=None):
    """A drummer's solo chorus, in time, told as a story (Matthew,
    2026-09-30: "drum solos can be anything ... go into whatever groove,
    have a theme and develop it ... use the kick more ... poly rhythms"):
    each two-bar phrase one idea from the same vocabulary the ending
    drummer uses, the ideas growing across the chorus; the hat foot
    keeps the form audible, a crash marks each four-bar phrase, and the
    last bar sets the band up to come back in."""
    import chartending as E
    beat = bar.div * 4 // bar.den
    n = bar.num
    arc = (pos + 0.5) / max(total, 1)
    # one idea a phrase, stated then developed (a short trade turn is one
    # phrase), not a new idea every two bars (Matthew, 2026-10-01:
    # "musicality is important")
    pd = _Dice(seed, 'solo phrase', absbar - pos, pos // 4)
    pool = ('motif', 'space', 'groove', 'talk') if arc < 0.3 else \
        ('talk', 'toms', 'poly', 'kick', 'groove', 'motif') if arc < 0.75 \
        else ('triplets', 'toms', 'poly', 'kick', 'roll')
    idea = pool[int(pd() * len(pool)) % len(pool)]
    d = _Dice(seed, 'drums', absbar)
    if pos % 4 == 0:
        # each four-bar phrase marked the drummer's way, or not at all
        r = d()
        if r < 0.45:
            bar.add(0, beat, ('u', _CRASH, 100))
            bar.add(0, beat, ('u', _KICK, 96))
        elif r < 0.75:
            kit_hit(bar, 0, beat, d)
    # the time under the solo, the drummer's call for the whole turn
    # (Matthew, 2026-09-30: "two and four with the hihat foot or all 4
    # quarter notes, or feather, or not"): the foot on two and four, the
    # foot on every beat, a feathered kick, foot and feather, or nothing
    td = _Dice(seed, 'solo time', absbar - pos)()
    keep = 'foot24' if td < 0.35 else 'foot4' if td < 0.55 else \
        'feather' if td < 0.7 else 'both' if td < 0.8 else 'none'
    if idea != 'groove' and keep != 'none':
        for b in range(n):
            if keep in ('foot4', 'both') or (keep == 'foot24' and b % 2):
                if d() < 0.92:
                    bar.add(b * beat, beat // 2, ('u', _HATF, 60))
            if keep in ('feather', 'both') and OPTS.get('feather', True):
                bar.add(b * beat, beat // 2, ('u', _KICK, 30))
    # the set-up into the next player at the end of the drummer's turn is
    # the drummer's call, not a rule
    start = beat // 2 if pos % 4 == 0 else 0
    if pos == 0 and echo:
        # trading: the turn opens answering what the last player just
        # played, its rhythm on the drums, its shape on the toms
        a0 = min(a for a, _l, _m in echo)
        ps = [m for _a, _l, m in echo]
        lo_p, hi_p = min(ps), max(ps)
        last_t = 0
        for a, _l, m in echo:
            t = int(round((a - a0) * beat))
            if t >= bar.barlen - beat:
                break
            f = (m - lo_p) / max(hi_p - lo_p, 1)
            drum = _HI_TOM if f > 0.66 else _MID_TOM if f > 0.33 else \
                _SNARE if f > 0.15 else _FLOOR_TOM
            bar.add(t, beat // 2, ('u', drum, 92 + int(14 * f)))
            last_t = t
        bar.add(0, beat // 2, ('u', _KICK, 94))
        start = min(bar.barlen - beat, last_t + beat)
    last = pos == total - 1 and _Dice(seed, 'hand back', absbar)() < 0.55
    end = bar.barlen - (beat if last else 0)
    # the thought finishes and breathes: the end of each four-bar phrase
    # leaves a beat or so of air after a closing stroke, the middle of it
    # a little, so ideas never run into each other (Matthew, 2026-10-01)
    breath = 0
    if not last and pos != total - 1:
        bd = _Dice(seed, 'breath', absbar)()
        if pos % 4 == 3:
            breath = beat * (1 if bd < 0.6 else 2) if n >= 4 else beat
        elif pos % 2 == 1 and bd < 0.5:
            breath = beat // 2
    if start < end:
        E._drum_idea(bar, beat, start, end - breath, idea, d)
        if breath:
            E.finish_thought(bar, beat, end - breath, end, d)
    # the second half of a phrase develops the first: stronger, busier
    E._scale_vel(bar, 0, end, 0.85 + 0.3 * arc + (0.08 if pos % 4 >= 2
                                                   else 0))
    solo_accents(bar, d, 0.6 + 0.8 * arc, end)
    if last:
        # the set-up that brings the band back in
        E._drum_cue(bar, beat, end, bar.barlen,
                    ('setup', 'three', 'flam')[int(d() * 3) % 3], d)


def section_voicing(pcs, root, ranges, last=None):
    """One chord voiced for a whole horn section, top down, the way an
    arranger writes backgrounds: the lead takes the colour nearest
    where it just was (so the top line moves by step), each chair below
    takes the next chord tone down, never crossing the chair above, and
    with five or more the bottom chair (the bari, the bass bone) holds
    the root underneath. ranges is each chair's comfortable (low, high),
    top chair first. Returns one MIDI note per chair, top first."""
    n = len(ranges)
    lo0, hi0 = ranges[0]
    anchor = last[0] if last else int(lo0 + (hi0 - lo0) * 0.65)
    # the lead: a guide tone or colour nearest the last lead note
    cands = []
    for pc in pcs[:-1] or pcs:
        m = _near(pc, anchor)
        while m > hi0:
            m -= 12
        while m < lo0:
            m += 12
        cands.append((abs(m - anchor), m, pc))
    cands.sort()
    top, top_pc = cands[0][1], cands[0][2]
    out = [top]
    stack = [pc for pc in pcs[:-1] if pc != top_pc] or [root]
    for i in range(1, n):
        lo_i, hi_i = ranges[i]
        if n >= 5 and i == n - 1:
            want = [root]                  # the bottom chair on the root
        else:
            want = stack[(i - 1) % len(stack):] + stack[:(i - 1) % len(
                stack)]
        got = None
        for pc in want:
            # the highest note of this tone at least a step below the
            # chair above, inside this chair's range
            m = out[-1] - 2 - ((out[-1] - 2 - pc) % 12)
            while m > hi_i:
                m -= 12
            if m >= lo_i - 2:
                got = m
                break
        if got is None:
            # nothing fits under the chair above: double the chair above
            # an octave down if it can, else the lowest fit
            got = out[-1] - 12
            while got < lo_i - 2:
                got += 12
            got = min(got, out[-1] - 1)
        out.append(got)
    return out


def backgrounds(bar, state, chords, voice, voices, lo, hi, style, off,
                seed, ranges=None):
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
    elif style == 'punch':
        # short punches on the changes, now and then pushed to the 'and'
        # before: the brass kicks behind a soloist
        d = _Dice(seed, 'punch', off)
        hits = []
        for b, c in chords:
            at = b - 0.5 if b > 1.0 and d() < 0.35 else b
            if d() < 0.85:
                hits.append((at, 0.5, 66))
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
        if ranges:
            # the section voiced as one: every chair computes the same
            # voicing from the same last one, and reads its own note
            vs = section_voicing(pcs, root, ranges, state.get('bg_voicing'))
            state['bg_voicing'] = vs
            m = vs[voice]
        else:
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
                ('p', m, vel) if style != 'punch' else
                ('p', m, vel, ('accent',)))
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
    if q.startswith('13') and 'b13' not in q:
        if '#11' in q:
            return (2, 6, 9)                 # 9, #11, 13
        if 'b9' in q:
            return (1, 9)                    # b9, 13
        if '#9' in q:
            return (3, 9)                    # #9, 13
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
    'mallets': (14, True, 1.0),
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
    return [(n[0] - t0, min(n[1], 1.0), n[2]) for n in got]


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


def _sing(notes, voice, d, lo=0, hi=127):
    """Play it like a singer (Matthew, 2026-09-30: "all instruments when
    soloing, think like a singer ... articulations"): each phrase —
    notes between breaths — swells up through a rising line and tapers
    at its end; its peak is leaned on; a long note that opens a phrase
    is scooped into, a long note that ends one may fall off or doit up.
    Horns and voices get the bends; keys, guitar and bass the shape and
    the accents."""
    if not notes:
        return notes
    bends = voice in ('horn', 'voice')
    phrases, cur = [], [0]
    for i in range(1, len(notes)):
        gap = notes[i][0] - (notes[i - 1][0] + notes[i - 1][1])
        if gap >= 0.75:
            phrases.append(cur)
            cur = []
        cur.append(i)
    phrases.append(cur)
    out = [list(n) + [()] for n in notes]
    # a singer doesn't leap an octave and more mid-phrase unless they
    # feel it (Matthew, 2026-09-30, on a tenor solo): a leap wider than a
    # sixth comes back an octave toward the line — once in a long while
    # one is kept, at the top of a phrase, on purpose
    for ph in phrases:
        for k in range(1, len(ph)):
            i, j = ph[k - 1], ph[k]
            iv = out[j][2] - out[i][2]
            if abs(iv) <= 9:
                continue
            keep = iv > 0 and k == len(ph) // 2 and d() < 0.08
            if keep:
                continue
            m = out[j][2] - 12 * (1 if iv > 0 else -1)
            while abs(m - out[i][2]) > 9 and lo <= m - 12 * (
                    1 if m > out[i][2] else -1) <= hi:
                m -= 12 * (1 if m > out[i][2] else -1)
            if lo <= m <= hi:
                out[j][2] = m
    notes = [tuple(n[:4]) for n in out]
    for ph in phrases:
        if not ph:
            continue
        top = max(ph, key=lambda i: notes[i][2])
        n_ = len(ph)
        for k, i in enumerate(ph):
            at, ln, m, v = notes[i]
            x = k / max(n_ - 1, 1)
            rising = k and m > notes[ph[k - 1]][2]
            # up through the line, easing at the end of the breath
            v2 = v + (3 if rising else -1) + int(6 * (1 - abs(2 * x - 0.8)))
            if k == n_ - 1 and n_ > 2:
                v2 -= 6
            arts = []
            if i == top and n_ > 2:
                arts.append('accent')
                v2 += 6
            if bends and ln >= 0.9:
                if k == 0 and d() < 0.35:
                    arts.append('scoop')
                elif k == n_ - 1:
                    r = d()
                    if r < 0.22:
                        arts.append('falloff')
                    elif r < 0.34:
                        arts.append('doit')
            out[i][3] = max(30, min(v2, 118))
            out[i][4] = tuple(arts)
    return [tuple(n) for n in out]


def cue_bar(role, div, bmeter, fifths, staves, shift, now, nxt, lo, hi,
            seed):
    """The bar a player cues the band out of a till-cue section with,
    the last time round (Matthew, 2026-09-30: "repeat until cue from
    anywhere ... drums, any instrument or vocalist"). A chord player
    holds the chord then runs up the next one, the bass walks up into
    the next root, a horn or a singer plays a pickup into the downbeat.
    The drummer's cue is a fill, played inside the groove itself."""
    bar = Bar(div, bmeter, fifths, staves, shift=shift)
    beat = div * 4 // bar.den
    n = bar.num
    tgt = nxt or now
    if tgt is None:
        return None
    root = _root_pc(tgt)
    run_at = max(n - 2, 0) * beat
    d = _Dice(seed, 'cue')
    if role == 'comp':
        if now is not None and run_at:
            for m in rootless_voicing(now, None):
                bar.add(0, run_at, ('p', m, 72))
        pcs = sorted({(root + i) % 12 for i in _tones(tgt)})
        cur = _near(pcs[0], lo + 3)
        steps = 6 if d() < 0.5 else 4
        run = []
        while len(run) < steps:
            run.append(cur)
            cur += 1
            while cur % 12 not in pcs:
                cur += 1
        span = n * beat - run_at
        for k, m in enumerate(run):
            bar.add(run_at + k * span // steps, span // steps,
                    ('p', min(m, hi), 78 + 4 * k))
        return bar.xml()
    if role == 'bass':
        if now is not None and run_at:
            bar.add(0, run_at, ('p', _near(_root_pc(now), 38), 90))
        goal = _near(root, 40)
        half = (n * beat - run_at) // 4
        for k in range(4):
            bar.add(run_at + k * half, half,
                    ('p', goal - 4 + k, 88 + 3 * k))
        return bar.xml()
    # a horn or a singer: three eighths climbing the next chord's scale
    # into its third, on the downbeat the band comes in on
    third = (root + (3 if 3 in _tones(tgt) else 4)) % 12
    goal = _near(third, (lo + hi) // 2)
    sc = {(root + i) % 12 for i in _scale(tgt)}
    below, m = [], goal - 1
    while len(below) < 3:
        if m % 12 in sc:
            below.append(m)
        m -= 1
    e = beat // 2
    for k, m in enumerate(reversed(below)):
        bar.add(n * beat - (3 - k) * e, e,
                ('p', max(min(m, hi), lo), 92 + 6 * k,
                 ('accent',) if k == 2 else ()))
    return bar.xml()


def _blue_ok(c):
    """Where a blue note belongs: a dominant, a minor, a plain triad."""
    q = c[2] or 'maj'
    return not (q.startswith('maj') and q != 'maj' or q in ('6', '69'))


def _knows_the_changes(notes, chord_fn):
    """The last word on a made-up solo: every note fits the chord under
    it (its scale, its tones, a blue note where the blues belongs) or is
    a chromatic approach, a step from where the line goes next. Anything
    else moves to the nearest note that fits."""
    out = []
    for i, n in enumerate(notes):
        at, p = n[0], n[2]
        c = chord_fn(at)
        if c is None:
            out.append(n)
            continue
        root = _root_pc(c)
        ok = {x % 12 for x in _scale(c)} | {x % 12 for x in _tones(c)}
        if _blue_ok(c):
            q = c[2] or 'maj'
            minor = q.startswith('m') and not q.startswith('maj')
            ok |= {6} if minor else {3, 6}
        rel = (p - root) % 12
        nxt = notes[i + 1] if i + 1 < len(notes) else None
        if rel in ok or (nxt is not None and 0 < abs(nxt[2] - p) <= 2
                         and nxt[0] - at <= 1.0):
            out.append(n)
            continue
        cands = [m for m in range(p - 2, p + 3)
                 if (m - root) % 12 in ok]
        q_ = min(cands, key=lambda m: (abs(m - p), m)) if cands else p
        out.append((n[0], n[1], q_) + tuple(n[3:]))
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

        def on_grid(x):
            return min(abs(x * 2 - round(x * 2)),
                       abs(x * 3 - round(x * 3))) < 0.02
        # the phrase was heard against the beat: if it began on an 'and',
        # its triplets only sit right shifted back by that eighth — so
        # the answer starts where the grid agrees with every note
        f0 = next((f for f in (0.0, 0.5)
                   if all(on_grid(at + f) for at, _l, _m in echo)), 0.0)
        while abs(base % 1 - f0) > 1e-6:
            base += 0.5
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
            # the motif keeps the answer's eighth-note shape: onsets
            # re-read against the beat, triplets left out
            ons = [(a, m) for a, _l, m in echo[:5] if a < 2.5
                   and abs((a + f0) * 2 - round((a + f0) * 2)) < 0.02]
            if len(ons) >= 3:
                a0 = ons[0][0]
                motif = [(a - a0, 0 if i == 0 else
                          (1 if m > ons[i - 1][1] else -1)
                          * (1 + (abs(m - ons[i - 1][1]) > 3)))
                         for i, (a, m) in enumerate(ons)]

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
            # the opening leaves room: short ideas, real air after them
            length = min(phrase_len(2, 7), max_len)
            rest = breath() * space * 1.6
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
            rest = breath() * 0.55
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
            if t + length - said >= 1.5 and (a != 'state' or d() < 0.3):
                at = math.ceil((said + 0.5) * 2 - 1e-6) / 2
                cur = eighth_line(at, t + length - at, a, cur, v,
                                  chord_fn(at) or c0)
        elif kind == 'line':
            cur = eighth_line(t, length, a, cur, v, c0)
        elif kind == 'riff':
            top = fit(snap(cur + 5, c0, _tones(c0)), a)
            for r in range(3):
                # the riff follows the changes: each time round it sits
                # on the chord sounding then (it used to keep the first
                # chord's notes over the next one — "it didn't know any
                # of the chord changes", Matthew, 2026-09-30)
                c = chord_fn(t + r * 2.0) or c0
                root = _root_pc(c)
                top = fit(snap(top, c, _tones(c)), a)
                cell = [(0.0, top), (0.5, scale_move(top, -1, c)),
                        (1.0, snap(top - 3, c, _tones(c)))]
                if persona == 'bluesy' and _blue_ok(c):
                    # the blues lick: the minor third bent up to the
                    # major, home to the root — over a dominant, a minor
                    # or a plain triad, never over a major seventh
                    r0 = fit(_near(root, cur), a)
                    cell = [(0.0, r0 + 3), (0.5, r0 + 4), (1.0, r0),
                            (1.5, r0 - 2)]
                for on, q in cell:
                    at = t + r * 2.0 + on
                    if at < min(t + length, total):
                        notes.append((at, 0.45, q, v + 4))
            cur = top
        elif kind == 'run':
            step = 1 / 3 if swingy else 0.25
            if t % 1 and swingy:
                # triplets live on the beat: a run begun on an 'and'
                # waits for the next beat (an offset triplet is nobody's)
                length -= math.ceil(t) - t
                t = float(math.ceil(t))
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
    return _sing(_knows_the_changes(_one_voice(notes), chord_fn),
                 voice, d, lo, hi)


def play_planned(bar, plan, pos, bar_beats):
    """This bar's share of a planned solo; a note that would ring over
    the barline stops at it."""
    beat = bar.div * 4 // bar.den
    if bar.den == 8:
        beat = bar.div // 2
    t0, t1 = pos * bar_beats, (pos + 1) * bar_beats
    for n_ in plan:
        at, ln, m, v = n_[:4]
        arts = n_[4] if len(n_) > 4 else ()
        end = at + ln
        if end <= t0 + 1e-6 or at >= t1:
            continue
        # a note that rings over a barline is tied, never re-struck
        ties = (('stop',) if at < t0 - 1e-6 else ()) + \
            (('start',) if end > t1 + 1e-6 else ())
        a, e = max(at, t0), min(end, t1)
        # the articulation sits on the note's attack, not its tied tail
        bar.add(int(round((a - t0) * beat)),
                max(1, int(round((e - a) * beat))),
                ('p', m, max(30, min(v, 118)),
                 arts if at >= t0 - 1e-6 else (), ties))


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
    if q.startswith('13') and 'b13' not in q:
        # a 13 keeps its natural 13 whatever else it carries
        if '#11' in q:
            return (4, 6, 9, 14), (10, 14, 18, 21)
        if 'b9' in q:
            return (4, 9, 10, 13), (10, 13, 16, 21)
        if '#9' in q:
            return (4, 9, 10, 15), (10, 15, 16, 21)
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
    ans = state.get('answer')
    if ans and d() < 0.5:
        # the soloist just said something and breathed: the piano says
        # it back, their rhythm on the chord
        lh(c0, 0, beat * 2, w0 - 4)
        for b_ in ans:
            b = 1.0 + b_
            if b < bar.num + 1:
                rh(chord_for(b), at_(b), half, w0 + 2)
        return
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
