#!/usr/bin/env python3
"""chartbraille — a part in braille music, as a BRF file.

Matthew, 2026-09-28: BRF support. Copyist writes braille music itself,
from the same parse the engraver draws the pages from, following the
Braille Authority of North America's Music Braille Code 2015 (BANA).
The rules are cited by paragraph where they are applied, and the
manual's own examples are the test fixtures: the braille must match
them cell for cell.

Single-line format (BANA 24): segments of a few lines, each opening at
the margin with its first measure's number, continuation lines
indented to cell 3; a new segment at every rehearsal mark, its letter
between word signs on a line of its own (24.2). Chord symbols ride a
second line beneath the music, aligned under the notes they begin with
(BANA 27). Slash measures, which the code has no sign for, are shown
as one print slash per beat under a word-sign "slashes", with the
changes beneath, and a transcriber's note on page 1 says so.

Output is North American braille ASCII (BRF): 40 cells by 25 lines,
the running page number at the right of each page's top line (1.5),
the title centered on page 1 (1.6.1), the music heading centered
(1.7). Stdlib only, like the rest of Copyist.
"""
import re

import chartengrave as ce

# ------------------------------------------------------------- the cells

_BRF = (" A1B'K2L@CIF/MSP\"E3H9O6R^DJG>NTQ,*5<-U8V.%[$+X!&;:4\\0Z7(_?W]#Y)=")


def cell(*dots):
    """A braille cell from its dot numbers, as a Unicode character."""
    v = 0
    for d in dots:
        v |= 1 << (d - 1)
    return chr(0x2800 + v)


def brf(text):
    """Unicode braille (and spaces) -> North American braille ASCII."""
    out = []
    for ch in text:
        o = ord(ch)
        if 0x2800 <= o <= 0x283F:
            out.append(_BRF[o - 0x2800])
        else:
            out.append(' ' if ch == ' ' else ch)
    return ''.join(out)


def from_brf(text):
    """Braille ASCII -> Unicode braille (the manual's examples)."""
    out = []
    for ch in text:
        i = _BRF.find(ch.upper())
        out.append(' ' if ch == ' ' else chr(0x2800 + i) if i >= 0 else ch)
    return ''.join(out)


def dots_of(ch):
    o = ord(ch) - 0x2800
    return {d for d in range(1, 7) if o & (1 << (d - 1))}


# notes (2.1): the pitch shape, with dots 3 and 6 for the value
PITCH = {'C': (1, 4, 5), 'D': (1, 5), 'E': (1, 2, 4), 'F': (1, 2, 4, 5),
         'G': (1, 2, 5), 'A': (2, 4), 'B': (2, 4, 5)}
VALUE = {'eighth': (), '128th': (), 'quarter': (6,), '64th': (6,),
         'half': (3,), '32nd': (3,), 'whole': (3, 6), '16th': (3, 6),
         'breve': (3, 6)}
REST = {'whole': cell(1, 3, 4), '16th': cell(1, 3, 4),
        'half': cell(1, 3, 6), '32nd': cell(1, 3, 6),
        'quarter': cell(1, 2, 3, 6), '64th': cell(1, 2, 3, 6),
        'eighth': cell(1, 3, 4, 6), '128th': cell(1, 3, 4, 6),
        'breve': cell(1, 3, 4)}
DOT = cell(3)
# octave marks (3.1): octaves 1-7, the one-line octave from middle C
OCTAVE = {1: cell(4), 2: cell(4, 5), 3: cell(4, 5, 6), 4: cell(5),
          5: cell(4, 6), 6: cell(5, 6), 7: cell(6)}
SHARP, FLAT, NATURAL = cell(1, 4, 6), cell(1, 2, 6), cell(1, 6)
ACC = {1: SHARP, -1: FLAT, 0: NATURAL, 2: SHARP + SHARP,
       -2: FLAT + FLAT}
NUM = cell(3, 4, 5, 6)                       # numeric indicator
UPPER = dict(zip('1234567890', (cell(1), cell(1, 2), cell(1, 4),
                                cell(1, 4, 5), cell(1, 5), cell(1, 2, 4),
                                cell(1, 2, 4, 5), cell(1, 2, 5),
                                cell(2, 4), cell(2, 4, 5))))
LOWER = dict(zip('1234567890', (cell(2), cell(2, 3), cell(2, 5),
                                cell(2, 5, 6), cell(2, 6), cell(2, 3, 5),
                                cell(2, 3, 5, 6), cell(2, 3, 6),
                                cell(3, 5), cell(3, 5, 6))))
WORD = cell(3, 4, 5)                         # the word sign (22.3)
HYPHEN = cell(5)                             # the music hyphen (1.11)
TIE = cell(4) + cell(1, 4)                   # Table 10
SLUR = cell(1, 4)                            # Table 13, short slur
SLUR_OPEN, SLUR_CLOSE = cell(5, 6) + cell(1, 2), cell(4, 5) + cell(2, 3)
TRIPLET = cell(2, 3)                         # Table 8, single-cell
FERMATA = cell(1, 2, 6) + cell(1, 2, 3)      # Table 22(B)
FINAL_BAR = cell(1, 2, 6) + cell(1, 3)       # 1.10.3
SECTION_BAR = FINAL_BAR + cell(3)
REPEAT_FWD = cell(1, 2, 6) + cell(2, 3, 5, 6)   # Table 17
REPEAT_BACK = cell(1, 2, 6) + cell(2, 3)
SEGNO = cell(3, 4, 6)                        # Table 20
CODA = cell(3, 4, 6) + cell(1, 2, 3)
CAPITAL = cell(6)
# Table 22(A), in the order 22.1 gives them: staccato, accents, tenuto
ARTIC = (('staccatissimo', cell(6) + cell(2, 3, 6)),
         ('staccato', cell(2, 3, 6)),
         ('detached-legato', cell(5) + cell(2, 3, 6)),
         ('accent', cell(4, 6) + cell(2, 3, 6)),
         ('strong-accent', cell(5, 6) + cell(2, 3, 6)),
         ('tenuto', cell(4, 5, 6) + cell(2, 3, 6)))
LINE = 40                                    # cells a line
PAGE = 25                                    # lines a page

_DIA = {s: i for i, s in enumerate('CDEFGAB')}


def number(n, lower=False):
    """A numeral with its numeric indicator: #d in upper cells."""
    table = LOWER if lower else UPPER
    return NUM + ''.join(table[d] for d in str(n))


# ------------------------------------------------ literary text (UEB g1)

_LETTER = {c: cell(*d) for c, d in zip(
    'abcdefghijklmnopqrstuvwxyz',
    ((1,), (1, 2), (1, 4), (1, 4, 5), (1, 5), (1, 2, 4), (1, 2, 4, 5),
     (1, 2, 5), (2, 4), (2, 4, 5), (1, 3), (1, 2, 3), (1, 3, 4),
     (1, 3, 4, 5), (1, 3, 5), (1, 2, 3, 4), (1, 2, 3, 4, 5), (1, 2, 3, 5),
     (2, 3, 4), (2, 3, 4, 5), (1, 3, 6), (1, 2, 3, 6), (2, 4, 5, 6),
     (1, 3, 4, 6), (1, 3, 4, 5, 6), (1, 3, 5, 6)))}
_PUNCT = {'.': cell(2, 5, 6), ',': cell(2), '-': cell(3, 6),
          "'": cell(3), ':': cell(2, 5), ';': cell(2, 3),
          '?': cell(2, 3, 6), '!': cell(2, 3, 5), '/': cell(4, 5, 6) +
          cell(3, 4), '(': cell(5) + cell(1, 2, 6),
          ')': cell(5) + cell(3, 4, 5), '&': cell(4) + cell(1, 2, 3, 4, 6),
          '"': cell(2, 3, 6)}


def literary(text, caps=True, music=False):
    """Uncontracted literary braille. caps=False drops capitals, as
    word-sign expressions do (22.3 b); music=True writes a period as
    dot 3 and parentheses as the special parenthesis (22.3 c)."""
    out, in_num, word_caps = [], False, False
    for k, ch in enumerate(text):
        if k == 0 or text[k - 1] == ' ':
            word = text[k:].split(' ', 1)[0]
            letters = [c for c in word if c.isalpha()]
            # UEB 8.4: a word in capitals takes the capitalized-word
            # indicator once, not a capital sign on every letter
            word_caps = caps and len(letters) > 1 and all(
                c.isupper() for c in letters)
            if word_caps:
                out.append(CAPITAL * 2)
        if ch.isdigit():
            if not in_num:
                out.append(NUM)
                in_num = True
            out.append(UPPER[ch])
            continue
        if ch.isalpha():
            low = ch.lower()
            if low not in _LETTER:
                continue
            if in_num and low in 'abcdefghij':
                out.append(cell(5, 6))          # grade 1 after a number
            in_num = False
            if caps and ch.isupper() and not word_caps:
                out.append(CAPITAL)
            out.append(_LETTER[low])
            continue
        in_num = False
        if ch == ' ':
            out.append(' ')
        elif music and ch == '.':
            out.append(cell(3))
        elif music and ch in '()':
            out.append(cell(2, 3, 5, 6))
        elif ch == '#':
            out.append(SHARP)
        elif ch in _PUNCT:
            out.append(_PUNCT[ch])
    return ''.join(out)


def expression(text):
    """A word-sign expression (22.3): lowercase, uncontracted; a longer
    expression (one with spaces) between a pair of word signs."""
    body = literary(text.strip(), caps=False, music=True)
    if ' ' in body:
        return WORD + body + WORD
    return WORD + body


def _join_expr(exprs, first):
    """Expressions before one note. Single words run together (22.3);
    a longer expression stands between spaces, with a music hyphen
    before its space when it falls inside a measure (22.3.8). Two
    longer expressions in a row are separate pairs of word signs with
    only a space between them (22.3.8)."""
    out = ''
    for e in exprs:
        if ' ' in e:
            if not out and not first:
                out += HYPHEN + ' '
            elif out and not out.endswith(' '):
                out += ' '
            out += e + ' '
        else:
            out += e
    return out


class Words(str):
    """A unit that is only word-sign expressions (it ends on a word, so
    22.3 (d) may need a dot 3 before whatever comes next)."""


def _ends_in_word(text):
    return isinstance(text, Words) and not text.endswith(' ')


def needs_dot3(next_sign):
    """22.3 (d): an expression is followed by dot 3 when the next sign
    contains dot 1, 2 or 3."""
    return bool(next_sign) and bool(dots_of(next_sign[0]) & {1, 2, 3})


# ---------------------------------------------------------- chord symbols

def chord_braille(sym):
    """A chord symbol (23.1): capital letters for note names, music
    accidentals, numerals with numeric indicators, the rest in
    lowercase uncontracted letters, a slash bass as '/' and its note."""
    out = []
    s = sym.strip()
    bass = None
    if '/' in s:
        s, bass = s.split('/', 1)
    m = re.match(r'([A-G])([b#]?)(.*)$', s)
    if not m:
        return literary(sym)
    out.append(CAPITAL + _LETTER[m.group(1).lower()])
    if m.group(2):
        out.append(FLAT if m.group(2) == 'b' else SHARP)
    rest, in_num = m.group(3), False
    i = 0
    while i < len(rest):
        ch = rest[i]
        if ch.isdigit():
            if not in_num:
                out.append(NUM)
                in_num = True
            out.append(UPPER[ch])
        elif ch in 'b#' and i + 1 < len(rest) and rest[i + 1].isdigit():
            out.append(FLAT if ch == 'b' else SHARP)
            in_num = False
        elif ch.isalpha():
            if in_num and ch.lower() in 'abcdefghij':
                out.append(cell(5, 6))
            out.append(_LETTER[ch.lower()])
            in_num = False
        elif ch in '()':
            out.append(cell(2, 3, 5, 6))
            in_num = False
        elif ch == '+':
            out.append(cell(2, 3, 5))
            in_num = False
        elif ch == '-':
            out.append(cell(3, 6))
            in_num = False
        i += 1
    if bass:
        mb = re.match(r'([A-G])([b#]?)', bass)
        if mb:
            out.append(cell(3, 4) + CAPITAL + _LETTER[mb.group(1).lower()])
            if mb.group(2):
                out.append(FLAT if mb.group(2) == 'b' else SHARP)
    return ''.join(out)


# --------------------------------------------------------------- notes

class Voice:
    """The running state of one line of music: the previous note for the
    octave rule, slur and triplet bookkeeping."""

    def __init__(self):
        self.prev = None          # (step, octave) of the last note
        self.slur_open = None     # 'long' while a bracket slur runs
        self.trip_left = 0
        self.at_line = False      # nothing written yet on this line
        self.tied = {}            # id(note) -> accidental a tie carries
        self.loose_ties = set()   # ties that reach no note of their pitch
        self.added = {}           # id(note) -> accidental braille adds
        self.ped_down = {}        # id(note) -> pedal goes down before it
        self.ped_up = {}          # id(note) -> pedal comes up after it

    def fresh(self):
        """3.2.1: the next note is marked — a new line, after a word
        sign or a numeric indicator, a double bar, a segno."""
        self.prev = None


def needs_octave(prev, step, octave):
    """3.2.2: under a fourth, never; over a fifth, always; a fourth or
    fifth only into another octave."""
    if prev is None:
        return True
    ps, po = prev
    dist = abs((octave * 7 + _DIA[step]) - (po * 7 + _DIA[ps]))
    if dist <= 2:
        return False
    if dist >= 5:
        return True
    return octave != po


def octave_sign(octave):
    if octave < 1:
        return cell(4) + cell(4)
    if octave > 7:
        return cell(6) + cell(6)
    return OCTAVE[octave]


def _loose_ties(measures, staff=1):
    """Ties whose next note is not the same pitch: a braille tie joins
    two notes of one pitch, so a dangling print tie is left out rather
    than read as joining two different notes."""
    seq = [n for m in measures
           for _p, ns, _s, _v in sorted((e for e in m['events']
                                         if e[2] == staff),
                                        key=lambda e: e[0])
           for n in ns[:1] if not n.rest and not n.slash]
    return {id(a) for a, b in zip(seq, seq[1:] + [None])
            if a.tie_start and (b is None or (b.step, b.octave, b.alter or 0)
                                != (a.step, a.octave, a.alter or 0))}


def _mark_tied_accidentals(m, tied):
    """Which tied-over notes carry an accidental the key does not (for
    10.1.3's restatement at the start of a braille line)."""
    f = m['state']['fifths']
    base = ({s: 1 for s in ce.KEY_STEPS_SHARP[:f]} if f > 0 else
            {s: -1 for s in ce.KEY_STEPS_FLAT[:-f]} if f < 0 else {})
    for _p, ns, _s, _v in m['events']:
        for n in ns:
            if n.rest or n.slash or not n.tie_stop or n.show_acc is not None:
                continue
            alter = n.alter or 0
            if alter != base.get(n.step, 0):
                tied[id(n)] = alter


IN_ACCORD = cell(1, 2, 6) + cell(3, 4, 5)   # table 11: <>
SMALL = cell(6) + cell(2, 6)            # 21.6: smaller print (cues)


INTERVAL = {1: cell(3, 4), 2: cell(3, 4, 6), 3: cell(3, 4, 5, 6),
            4: cell(3, 5), 5: cell(3, 5, 6), 6: cell(2, 5),
            0: cell(3, 6)}                    # table 9: 2nd .. 7th, octave
CHORD_TIE = cell(4, 6) + cell(1, 4)        # table 10: .c
ADDED = cell(5)                            # before a transcriber's sign


def _dia(n):
    return n.octave * 7 + _DIA[n.step]


def _acc_of(n, voice):
    """The accidental a note shows: print's, or one the braille needs
    that print did not (11.2), after dot 5."""
    if getattr(n, 'show_acc', None) is not None:
        return ACC[n.show_acc]
    if id(n) in voice.added:
        return ADDED + ACC[voice.added[id(n)]]
    return ''


def _intervals(w, members, voice, tie_ids):
    """9.1: the other notes of a chord as intervals from the written
    note, nearest first, each after its accidental and, where 9.1.1
    asks, its octave mark."""
    out, prev, seen = [], None, set()
    for k, x in enumerate(sorted(members, key=lambda x: abs(_dia(x) -
                                                             _dia(w)))):
        d = abs(_dia(x) - _dia(w))
        mark = (d == 0 or (k == 0 and d > 7) or
                (prev is not None and abs(_dia(x) - _dia(prev)) >= 7) or
                _dia(x) in seen)
        out.append(_acc_of(x, voice) +
                   (octave_sign(x.octave) if mark else '') +
                   INTERVAL[d % 7] + (TIE if id(x) in tie_ids else ''))
        prev = x
        seen.add(_dia(x))
    return ''.join(out)


def note_braille(n, voice, members=(), lead=None):
    """One note or rest -> its braille, everything that precedes and
    follows it included (22.1 before, 22.2 after). A cue note carries
    the small-type sign ahead of everything else (21.6) — the reader
    must know not to play it. members are the rest of a chord, written
    as intervals from n (9.1); lead is the event's first note, which
    carries its articulation and fermata."""
    lead = lead or n
    out = [SMALL] if getattr(lead, 'cue', False) else []
    if n.rest:
        out.append(REST.get(n.ntype, REST['quarter']))
        out.append(DOT * n.dots)
        if n.fermata:
            out.append(FERMATA)
        return ''.join(out)
    marks = set(lead.marks or [])
    if lead.artic:
        marks.add(lead.artic)
    for name, sign in ARTIC:
        if name in marks:
            out.append(sign)
    if _acc_of(n, voice):
        out.append(_acc_of(n, voice))
    elif voice.at_line and id(n) in voice.tied:
        # 10.1.3: a tie carries an accidental over the bar unprinted,
        # but a new braille line restates it, after dot 5
        out.append(cell(5) + ACC[voice.tied[id(n)]])
    if needs_octave(voice.prev, n.step, n.octave):
        out.append(octave_sign(n.octave))
    out.append(cell(*(PITCH[n.step] + VALUE.get(n.ntype, (6,)))))
    out.append(DOT * n.dots)
    tied = {id(x) for x in (n,) + tuple(members)
            if x.tie_start and id(x) not in voice.loose_ties}
    chord_tie = bool(members) and len(tied) >= 2        # 10.2
    if id(n) in tied and not chord_tie:
        out.append(TIE)
    if members:
        out.append(_intervals(n, members, voice,
                              set() if chord_tie else tied))
    if lead.fermata or n.fermata:
        out.append(FERMATA)
    if chord_tie:
        out.append(CHORD_TIE)
    voice.prev = (n.step, n.octave)
    voice.at_line = False
    return ''.join(out)


# ------------------------------------------------------------ measures

def _key_sign(fifths):
    """6.5: up to three sharps or flats written out, more by number."""
    if fifths == 0:
        return NATURAL
    sign = SHARP if fifths > 0 else FLAT
    k = abs(fifths)
    return sign * k if k <= 3 else NUM + UPPER[str(k)] + sign


def _time_sign(t):
    """7.1: the numeric indicator, the upper figure in upper cells and
    the lower in lower cells."""
    beats, unit = t
    return NUM + ''.join(UPPER[d] for d in str(beats)) + \
        ''.join(LOWER[d] for d in str(unit))


def _slur_plan(meas_list, staff=1):
    """Which notes open and close slurs, and whether each slur is short
    (the single slur after every note but the last) or long (the
    bracket slur, 13.3), decided by how many notes it covers."""
    notes = [n for m in meas_list for _p, ns, st, _v in
             sorted(m['events'], key=lambda e: e[0]) if st == staff
             for n in ns[:1] if not n.rest]
    plan, start = {}, None
    for i, n in enumerate(notes):
        if n.slur_start and start is None:
            start = i
        if n.slur_stop and start is not None and i > start:
            length = i - start + 1
            if length <= 4:
                for j in range(start, i):
                    plan[id(notes[j])] = 'short'
            else:
                plan[id(notes[start])] = 'open'
                plan[id(notes[i])] = 'close'
            start = None
    return plan


def measure_units(meas, slurs, staff=1, down=None, words=True):
    """One measure -> units in time order: (render, chord). render(voice)
    writes the unit's braille against the running voice, so a unit that
    has to move to a new line can be written again there with the octave
    mark 3.2.1 asks for; chord is the symbol that begins with it (27.1).
    Returns (units, slashed)."""
    units = []
    chords = sorted(meas['chords']) if words else []
    dyns = sorted(meas['dyn']) if words else []
    texts = sorted(meas['texts']) if words else []
    events = sorted((e for e in meas['events'] if e[2] == staff),
                    key=lambda e: e[0])
    if down is None:
        down = _down(meas)
    full = _bar_length(meas)
    slashed = bool(events) and all(n.slash for _p, ns, _s, _v in events
                                   for n in ns)
    first_ch = chords[0][1] if chords else None

    def fixed(text, fresh_after=False, words=False):
        def render(voice):
            if fresh_after:
                voice.fresh()
            return Words(text) if words else text
        return render

    if meas['multi'] and meas['multi'] > 1:
        k = meas['multi']
        tok = (REST['whole'] * k) if k <= 3 else number(k) + REST['whole']
        # 5.3: after the numbered form the next note takes an octave
        # mark (3.2.1, a numeric indicator); after plain rests it does not
        units.append((fixed(tok, k > 3), first_ch))
        return units, False
    if not events or all(n.rest and (n.measure_rest or n.dur >= full)
                         for _p, ns, _s, _v in events for n in ns[:1]):
        f = any(n.fermata for _p, ns, _s, _v in events for n in ns)
        words = [expression(t) for _p, t in texts]
        tok = (_join_expr(words, True) if words else '') + \
            REST['whole'] + (FERMATA if f else '')
        units.append((fixed(tok, bool(words)), first_ch))
        return units, False
    if slashed:
        # no sign exists: one print slash a beat, the changes beneath
        words = [expression(t) for _p, t in texts] + [expression('slashes')]
        for k in range(len(words)):          # each can take a line break
            piece = _join_expr(words[:k + 1], True)[
                len(_join_expr(words[:k], True)):]
            units.append((fixed(piece, True, True), None))
        # each slash measure is a measure of silence in the braille, its
        # changes beneath, the passage named by the word "slashes" — only
        # real signs; an invented slash sign read as an octave mark and
        # an interval (the round-trip check caught it, 2026-09-28)
        units.append((fixed(REST['whole']), ' '.join(c for p, c in chords)
                      or None))
        return units, True
    sides = _sides(meas, events, down)
    added = _side_accidentals(meas, sides) if len(sides) > 1 else {}
    for k, evs in enumerate(sides):
        if k:
            # 11.1.1: the next part of the bar, joined by the full-
            # measure in-accord; its first note takes an octave mark
            units.append((fixed(IN_ACCORD, True), None))
        units.extend(_side_units(evs, texts if k == 0 else [],
                                 dyns if k == 0 else [],
                                 chords if k == 0 else [], slurs, added,
                                 down, first=not units))
    if len(sides) > 1:
        # 11.1: the bar after an in-accord marks its first octave
        units.append((fixed('', True), None))
    return units, False


def _down(meas):
    """9.2: treble and alto parts write a chord's top note and read
    down; bass and tenor parts write the bottom note and read up."""
    return meas['state']['clefs'].get(1, 'G') != 'F'


def _bar_length(meas):
    st = meas['state']
    beats, unit = st['time']
    return round(beats * 4 / unit * st['div'])


def _sides(meas, events, down=None):
    """The parts of a bar, one per voice: highest first in a treble
    part, lowest first in a bass part (11.1). Where two voices share a
    staff, each side is filled to a whole bar with the rests print
    leaves implied, marked as the transcriber's (11.1.1)."""
    by = {}
    for e in events:
        by.setdefault(e[3], []).append(e)
    if len(by) < 2:
        return [events]

    def height(evs):
        ps = [_dia(n) for _p, ns, _s, _v in evs for n in ns if not n.rest]
        return sum(ps) / len(ps) if ps else 0
    order = sorted(by.values(), key=height,
                   reverse=_down(meas) if down is None else down)
    full = _bar_length(meas)
    return [_fill(evs, full, meas['state']['div']) for evs in order]


class _Gap:
    """A rest print leaves implied, added by the transcriber."""
    __slots__ = ('rest', 'ntype', 'dots', 'dur', 'tmod', 'slash', 'cue',
                 'fermata', 'marks', 'artic', 'added', 'tie_start',
                 'tie_stop', 'step', 'octave', 'alter')

    def __init__(self, ntype, dur):
        self.rest, self.ntype, self.dots, self.dur = True, ntype, 0, dur
        self.tmod = None
        self.slash = self.cue = self.fermata = False
        self.marks, self.artic, self.added = [], None, True
        self.tie_start = self.tie_stop = False
        self.step, self.octave, self.alter = 'B', 4, 0


def _fill(evs, full, div):
    out, at = [], 0
    for e in sorted(evs, key=lambda e: e[0]):
        out += _gaps(at, e[0], div, e[2], e[3])
        out.append(e)
        at = e[0] + max(n.dur for n in e[1])
    out += _gaps(at, full, div, evs[0][2], evs[0][3])
    return out


def _gaps(start, end, div, staff, v):
    out = []
    for name, beats in (('whole', 4), ('half', 2), ('quarter', 1),
                        ('eighth', 0.5), ('16th', 0.25), ('32nd', 0.125)):
        size = round(beats * div)
        while size and end - start >= size:
            out.append((start, [_Gap(name, size)], staff, v))
            start += size
    return out


def _side_accidentals(meas, sides):
    """11.2: an accidental does not carry across an in-accord sign, so
    each side keeps its own; where print relied on the other side, the
    braille adds the sign."""
    f = meas['state']['fifths']
    base = ({s: 1 for s in ce.KEY_STEPS_SHARP[:f]} if f > 0 else
            {s: -1 for s in ce.KEY_STEPS_FLAT[:-f]} if f < 0 else {})
    added = {}
    for evs in sides:
        cur = {}
        for _p, ns, _s, _v in evs:
            for x in ns:
                if x.rest or x.slash:
                    continue
                k = (x.step, x.octave)
                want = x.alter or 0
                if x.tie_stop and k not in cur:
                    cur[k] = want
                    continue
                if want != cur.get(k, base.get(x.step, 0)) and \
                        x.show_acc is None:
                    added[id(x)] = want
                cur[k] = want
    return added


def _side_units(events, texts, dyns, chords, slurs, added, down,
                first=True):
    """One side of a bar (or the whole bar) -> units in time order."""
    units = []
    pending_ch = list(chords)
    lead = [ns[0] for _p, ns, _s, _v in events]
    groups = _tuplet_starts(lead)
    vsigns = _value_signs(lead)
    was_slash = False
    for pos, ns, _s, _v in events:
        n = ns[0]
        pre = [expression(t) for p, t in texts if p == pos] + \
            [expression(d) for p, d in dyns if p == pos]
        if n.slash and not was_slash:
            pre.append(expression('slashes'))
        was_slash = n.slash
        is_first = first and not units
        ch = []
        while pending_ch and pending_ch[0][0] <= pos:
            ch.append(pending_ch.pop(0)[1])

        def render(voice, n=n, ns=ns, pre=pre, first=is_first):
            voice.added = added
            if pre:
                voice.fresh()                # 22.3 (e)
            trip = vsigns.get(id(n), '') + groups.get(id(n), '')
            opener = SLUR_OPEN if slurs.get(id(n)) == 'open' else ''
            if n.slash:
                # a print slash beat: a rest of its value under the word
                # "slashes" (see the transcriber's note)
                body = REST.get(n.ntype, REST['quarter']) + DOT * n.dots
                tok = _join_expr(pre, first=first) if pre else ''
                if pre and not tok.endswith(' ') and needs_dot3(body):
                    tok += cell(3)
                return tok + trip + body
            if getattr(n, 'added', False):
                return ADDED + REST[n.ntype]                # 11.1.1
            pitched = [x for x in ns if not x.rest]
            if len(pitched) > 1:
                w = (max if down else min)(pitched, key=_dia)
                body = note_braille(w, voice,
                                    [x for x in pitched if x is not w], n)
            else:
                body = note_braille(n, voice)
            if slurs.get(id(n)) == 'short':
                body += SLUR
            if slurs.get(id(n)) == 'double':
                body += SLUR + SLUR                        # 35.2
            if slurs.get(id(n)) == 'close':
                body += SLUR_CLOSE
            # 29.10: pedal down before the note, up after it
            if id(n) in voice.ped_up:
                body += PED_UP
            if id(n) in voice.ped_down:
                trip = PED_DOWN + trip
            tok = _join_expr(pre, first=first) if pre else ''
            if pre and not tok.endswith(' ') and \
                    needs_dot3(trip + opener + body):
                tok += cell(3)
            return tok + trip + opener + body
        units.append((render, ' '.join(ch) or None))
    return units


def _tuplet_sign(k, doubled=False):
    """8.4 / 8.5: the triplet cell, or dots 456, the lower-cell number
    and dot 3 for any other group; doubled, it runs until a single sign
    marks the last of four or more like groups."""
    if k == 3:
        return TRIPLET * (2 if doubled else 1)
    num = cell(4, 5, 6) + ''.join(LOWER[d] for d in str(k))
    return num * (2 if doubled else 1) + cell(3)


def _tuplet_starts(notes):
    """id(note) -> the group sign it opens. A run of notes under one
    time modification is cut into groups by duration, so a triplet of
    a quarter and an eighth is one group of three (each note counts
    its length in the run's smallest value)."""
    out, i = {}, 0
    while i < len(notes):
        k = notes[i].tmod
        if not k:
            i += 1
            continue
        j = i
        while j < len(notes) and notes[j].tmod == k:
            j += 1
        unit = min(n.dur for n in notes[i:j] if n.dur) or 1
        acc, starts = 0, []
        for n in notes[i:j]:
            if acc == 0:
                starts.append(n)
            acc += max(round(n.dur / unit), 1)
            if acc >= k:
                acc = 0
        if len(starts) >= 4:                       # 8.4, 8.5: doubled
            out[id(starts[0])] = _tuplet_sign(k, doubled=True)
            out[id(starts[-1])] = _tuplet_sign(k)
        else:
            for n in starts:
                out[id(n)] = _tuplet_sign(k)
        i = j
    return out


_BEATS = {'whole': 4, 'half': 2, 'quarter': 1, 'eighth': 0.5,
          '16th': 0.25, '32nd': 0.125, '64th': 0.0625, '128th': 0.03125}
_TWIN = {'whole': '16th', 'half': '32nd', 'quarter': '64th',
         'eighth': '128th'}
_TWIN.update({v: k for k, v in _TWIN.items()})
LARGER = cell(4, 5) + cell(1, 2, 6) + cell(2)   # 2.4: ^<1
SMALLER = cell(6) + cell(1, 2, 6) + cell(2)     # 2.4: ,<1


def _value_signs(notes):
    """2.4: a braille note cell is one of two values (an eighth or a
    128th, a whole or a 16th). Where another reading of the cells adds
    up to the same bar, the reader cannot tell which: then a larger or
    smaller value sign goes before each change between the two ranges.
    Where only the written reading fits, nothing is added."""
    from fractions import Fraction as F

    def length(ntype, n):
        v = F(_BEATS[ntype]).limit_denominator(64)
        v *= 2 - F(1, 2 ** n.dots)
        if n.tmod:
            v *= F(_normal(n.tmod), n.tmod)
        return v
    if any(n.ntype not in _BEATS for n in notes) or len(notes) < 2:
        return {}
    true = sum(length(n.ntype, n) for n in notes)
    ways = {F(0): 1}
    for n in notes:
        nxt = {}
        for tot, c in ways.items():
            for t in (n.ntype, _TWIN[n.ntype]):
                v = tot + length(t, n)
                if v <= true:
                    nxt[v] = min(nxt.get(v, 0) + c, 2)
        ways = nxt
    if ways.get(true, 0) < 2:
        return {}
    out, prev = {}, None
    for k, n in enumerate(notes):
        small = _BEATS[n.ntype] < 0.5
        if (prev is not None and small != prev) or (k == 0 and small):
            out[id(n)] = SMALLER if small else LARGER
        prev = small
    return out


def _normal(k):
    """The normal count a group of k plays in the time of: 3 in 2,
    5, 6 and 7 in 4, 9 in 8."""
    m = 1
    while m * 2 < k:
        m *= 2
    return m


class Line:
    """A braille line of music with its chord line beneath (27): each
    chord's capital under the first sign of its note, a gap inside a
    measure opened with a music hyphen (27.4), measures separated by
    aligned blank cells (27.2)."""

    def __init__(self, head):
        self.head = head
        self.music = head
        self.chord = ' ' * len(head)
        self.chord_end = None        # where this measure's last chord ends
        self.chords = True
        self.in_measure = False
        self.after_word = False

    def width_with(self, text, ch):
        ch = ch if self.chords else None
        at = len(self.music)
        if self.after_word and text and not text.startswith(WORD) and \
                not text.startswith(' ') and needs_dot3(text):
            at += 1                                       # 22.3 (d)
        if ch and self.chord_end is not None:
            at = max(at, self.chord_end + 1)
        cw = len(' '.join(chord_braille(c) for c in ch.split())) if ch else 0
        return max(at + len(text), at + cw)

    def add(self, text, ch):
        ch = ch if self.chords else None
        # 22.3 (d): a word-sign expression ending the line so far is
        # followed by dot 3 when this sign has dot 1, 2 or 3 — unless
        # this is another word sign
        if self.after_word and text and not text.startswith(WORD) and \
                not text.startswith(' ') and needs_dot3(text):
            self.music += cell(3)
        self.after_word = _ends_in_word(text)
        at = len(self.music)
        if ch:
            cb = ' '.join(chord_braille(c) for c in ch.split())
            if self.chord_end is not None:
                at = max(at, self.chord_end + 1)
            if at > len(self.music):
                gap = at - len(self.music)
                self.music += (HYPHEN + ' ' * (gap - 1)) \
                    if gap > 1 and self.in_measure else ' ' * gap
            self.chord = self.chord.ljust(at) + cb
            self.chord_end = len(self.chord)
        self.music += text
        self.in_measure = True

    def end_measure(self, end=''):
        self.after_word = False
        self.music += end
        w = max(len(self.music), len(self.chord))
        self.music = self.music.ljust(w) + ' '
        self.chord = self.chord.ljust(w) + ' '
        self.chord_end = None
        self.in_measure = False

    def bare(self):
        """Nothing on the line yet but its margin number or indent."""
        return self.music == self.head

    def lines(self):
        out = [self.music.rstrip()]
        if self.chords and self.chord.strip():
            out.append(self.chord.rstrip())
        return out


# ---------------------------------------------------------------- pages

def _center(text, width=LINE):
    pad = max(0, (width - len(text)) // 2)
    return ' ' * pad + text


class Pager:
    """Lines onto 25-line pages, the page number at the right of each
    top line (1.5); a parallel (music line plus its chord line) never
    splits across pages."""

    def __init__(self, title):
        self.title = title
        self.pages = [[]]
        self.num = 1
        self._head()

    def _head(self):
        n = number(self.num)
        if self.num == 1:
            t = literary(self.title)
            line = _center(t)
        else:
            t = literary(self.title)[:LINE - len(n) - 6]
            line = _center(t)
        line = line[:LINE - len(n) - 1].ljust(LINE - len(n)) + n
        self.pages[-1].append(line)

    def add(self, *lines):
        if len(self.pages[-1]) + len(lines) > PAGE:
            self.pages.append([])
            self.num += 1
            self._head()
        self.pages[-1].extend(lines)

    def text(self):
        return '\f'.join('\r\n'.join(brf(l.rstrip()) for l in page) +
                         '\r\n' for page in self.pages)


def _heading(measures, xml):
    """The music heading (1.7): the style and pace words, the metronome,
    then key and time — centered."""
    first = measures[0]
    words = [t for p, t in first['texts'] if p == 0]
    parts = []
    if words:
        parts.append(literary(words[0].capitalize(), music=True)
                     + cell(2, 5, 6))
    met = first.get('metronome')
    if met:
        dotted, per = met
        parts.append(cell(1, 4, 5, 6) + (DOT if dotted else '') +
                     cell(2, 3, 5, 6) + number(int(float(per))))
    st = first['state']
    parts.append(_key_sign(st['fifths']) + _time_sign(st['time'])
                 if st['fifths'] else _time_sign(st['time']))
    line = ' '.join(parts)
    if len(line) + 6 > LINE and len(parts) > 1:
        return [_center(parts[0]), _center(' '.join(parts[1:]))], words[1:]
    return [_center(line)], words[1:]


def part_to_brf(xml, pid, title, part_name, chords=True):
    """A part of a Copyist MusicXML document -> (BRF text, notes about
    anything the braille could not carry). chords=False leaves out the
    chord-symbol lines: the melody alone, for a reader who wants it."""
    measures, why = ce.parse_part(xml, pid)
    if measures is None:
        return None, [f"{part_name}: {why}"]
    unsupported = []
    tied = {}
    for m in measures:
        ce.mark_accidentals(m, m['state'])
        _mark_tied_accidentals(m, tied)
        if m['state'].get('staves', 1) > 2:
            unsupported.append("a third staff, like an organ's pedal "
                               "line, is still to come")
            break
        if 'percussion' in m['state']['clefs'].values():
            unsupported.append("percussion is still to come")
            break
    if unsupported:
        return None, unsupported

    pager = Pager(title)
    pager.add(_center(literary(part_name)))
    has_slash = chords and any(n.slash for m in measures for _p, ns, _s, _v in
                    m['events'] for n in ns)
    keys = any(m['state'].get('staves', 1) > 1 for m in measures)
    # 29.2: in keyboard music the hand signs say which way intervals read
    has_chords = not keys and any(
        sum(1 for x in ns if not x.rest) > 1
        for m in measures for _p, ns, st, _v in m['events'] if st == 1)
    notes = []
    if has_chords:
        # 9.2: the direction intervals read in is stated for the reader
        notes.append("Chords are written from the top note, the "
                     "intervals reading downward." if _down(measures[0])
                     else "Chords are written from the bottom note, the "
                     "intervals reading upward.")
    if has_slash:
        notes.append("Where the word slashes appears, the rests that "
                     "follow it, up to the next note, stand for print "
                     "slashes: play or improvise on the chord symbols in "
                     "the line below. A rest anywhere else is a real rest.")
    paras = [' '.join(notes)] if notes else []
    if chords and _sings(measures) and any(m['chords'] for m in measures):
        # 36.1.1: the notes a reader needs for chords set against words
        paras += [
            "The chord symbols in this song relate to the words; where "
            "each chord's first capital sign sits says whether it is "
            "played before, with, during, or after its word or syllable.",
            "Punctuation in the word line has no bearing on where a chord "
            "sits. When a word is capitalized, the capital sign is its "
            "first character.",
            "Some words are spaced unusually, or split between syllables, "
            "to make room for the chord symbols.",
            "A chord played before a syllable starts two cells to the left "
            "of the syllable's first character.",
            "A chord played with a syllable starts under its first "
            "character.",
            "A chord played during a syllable starts with a hyphen; the "
            "first hyphen sits under the syllable's first character.",
            "A chord played after a syllable is released starts one cell "
            "to the right of its last letter."]
    if paras:
        # 1.4: a transcriber's note, in UEB transcriber's-note indicators
        tn_open = cell(4) + cell(4, 6) + cell(1, 2, 6)
        tn_close = cell(4) + cell(4, 6) + cell(3, 4, 5)
        for k, para in enumerate(paras):
            text = ((tn_open if k == 0 else '') + literary(para) +
                    (tn_close if k == len(paras) - 1 else ''))
            for ln in _wrap(text, LINE):
                pager.add(ln)
    pager.add('')
    head, extra_words = _heading(measures, xml)
    for ln in head:
        pager.add(ln)
    # the first measure's words that went into the heading are spent
    measures[0]['texts'] = [(p, t) for p, t in measures[0]['texts']
                            if p != 0 or t in extra_words]

    for m in measures:
        # a rehearsal mark that is a name, not a letter, is said as a
        # longer expression over its measure (22.3.8)
        if m['rehearsal'] and not _is_letter(m['rehearsal']):
            m['texts'] = [(0, m['rehearsal'])] + list(m['texts'])
            m['rehearsal'] = ''
    _merge_rests(measures)
    if any(m['state'].get('staves', 1) > 1 for m in measures):
        _keyboard(pager, measures, tied, chords)
        return pager.text(), _later(measures)
    if _sings(measures):
        _vocal(pager, measures, tied, chords)
        body = re.search(r'<part id="%s">(.*?)</part>' % re.escape(pid),
                         xml, re.S)
        more = body and re.search(r'<lyric[^>]*number="[2-9]"', body.group(1))
        return pager.text(), (["verses after the first are still to come"]
                              if more else [])
    voice = Voice()
    voice.tied = tied
    voice.loose_ties = _loose_ties(measures)
    slurs = _slur_plan(measures)
    pending = []                  # a rehearsal line waiting for its music
    state = {'line': None, 'lines_in_seg': 0}

    def flush():
        ln = state['line']
        if ln is None or ln.bare():
            return
        pager.add(*(pending + ln.lines()))
        pending.clear()
        state['line'] = None
        state['lines_in_seg'] += 1

    def new_line(head):
        flush()
        state['line'] = Line(head)
        state['line'].chords = chords
        voice.fresh()                                  # 3.2.1
        voice.at_line = True

    in_slash = False
    skip = 0
    for i, m in enumerate(measures):
        if skip:
            skip -= 1
            continue
        if m['multi'] and m['multi'] > 1:
            skip = m['multi'] - 1
        num = int(m['num']) if str(m['num']).isdigit() else i + 1
        new_seg = (i == 0 or bool(m['rehearsal']) or bool(m['signs']) or
                   (m['left'] or {}).get('repeat') == 'forward' or
                   state['lines_in_seg'] >= 4)
        if m['rehearsal']:
            # 24.2: the letter between word signs on its own line, kept
            # on the page with the segment it heads
            flush()
            pending.append(WORD + literary(m['rehearsal'], music=True)
                           + WORD)
        if new_seg:
            flush()
            state['lines_in_seg'] = 0
            new_line(number(num) + ' ')            # 24.1.1
        units, slashed, tail = _measure_frame(m, i, slurs, in_slash)
        in_slash = slashed
        _lay(state, units, tail, voice, new_line)
        if tail:
            voice.fresh()                          # 1.10.3, 22.3 (e)
    flush()
    return pager.text(), _later(measures)


def _later(measures):
    later = []
    if any(n.lyric for m in measures for _p, ns, _s, _v in m['events']
           for n in ns):
        later.append("its lyrics are still to come; the notes are all "
                     "there")
    return later


def _measure_frame(m, i, slurs, in_slash):
    """One measure's units with the signs that frame it, and what
    follows its music: (units, slashed, tail)."""
    # signs before the measure. Segno, coda and signatures stand
    # apart, spaced (20.2, 6.5, 7.1; a key runs straight into a
    # time signature); the repeat and the volta belong to the
    # measure and touch its first sign (17.1, 17.1.1)
    pre = [SEGNO if sgn == 'segno' else CODA for sgn in m['signs']]
    st = m['state']
    sig = ''
    if i > 0 and 'key' in m['show']:
        sig += _key_sign(st['fifths'])
    if i > 0 and 'time' in m['show']:
        sig += _time_sign(st['time'])
    if sig:
        pre.append(sig)
    attach, volta = '', False
    if (m['left'] or {}).get('repeat') == 'forward':
        attach += REPEAT_FWD
    for enum, etype, _left in m.get('ending') or []:
        if etype == 'start':                         # table 17
            attach += NUM + ''.join(LOWER[d] for d in str(enum))
            volta = True
    # 20.2: the road map follows the measure it closes — "To Coda"
    # as the coda sign and its words after the music, D.S., D.C.
    # and Fine after the bar line, each a closed word-sign group
    road = [t for _p, t in m['texts'] if _is_road(t)]
    m['texts'] = [(p, t) for p, t in m['texts'] if not _is_road(t)]
    post = ''
    for t in road:
        w = expression(t)
        w = w if w.endswith(WORD) else w + WORD
        post += ' ' + ((CODA + ' ') if t.lower().startswith('to coda')
                       else '') + w
    units, slashed = measure_units(m, slurs)
    if slashed and in_slash:
        # "slashes" is said once a passage; later bars keep only
        # their own words
        nw = len(m['texts']) + 1
        units = units[:nw - 1] + units[nw:]
    in_slash = slashed
    if pre or attach:
        head = ' '.join(pre) + (' ' if pre else '') + attach
        first_render, first_ch = units[0]

        def joined(v, head=head, r=first_render, attach=attach,
                   volta=volta):
            v.fresh()                         # 6.5, 7.1, 17.1
            text = r(v)
            keep = Words if isinstance(text, Words) else str
            if not attach:
                return keep(head + text)
            if _starts_longer(text):
                return keep(head + HYPHEN + ' ' + text)  # 17.1
            if volta and needs_dot3(text):
                return keep(head + cell(3) + text)       # 17.1.1
            return keep(head + text)
        units[0] = (joined, first_ch)
    right = m['right'] or {}
    end = ''
    if right.get('repeat') == 'backward':
        end = REPEAT_BACK
    elif right.get('style') == 'light-heavy':
        end = FINAL_BAR
    elif right.get('style') == 'light-light':
        end = SECTION_BAR
    return units, slashed, end + post


_ROAD = ('d.s', 'd. s', 'd.c', 'd. c', 'dal segno', 'da capo', 'fine',
         'to coda')


def _plain_rest(m, first=False):
    """A measure that is only silence: nothing said, no sign (the first
    of a run may carry signs and a letter; they come before it)."""
    return (not m['texts'] and not m['dyn'] and not m['chords'] and
            (first or (not m['signs'] and not m['rehearsal'])) and
            all(sum(1 for e in m['events'] if e[2] == st) <= 1
                for st in {e[2] for e in m['events']}) and
            all(n.rest for _p, ns, _s, _v in m['events'] for n in ns))


def _merge_rests(measures):
    """Rest measures in a row are one multi-measure rest (5.3), as a
    player counts them: print breaks them at systems, braille need not.
    A run ends at anything the player must see — words, signs, a
    signature, a repeat or volta, a bar line other than a plain one."""
    i = 0
    while i < len(measures):
        m = measures[i]
        if not _plain_rest(m, first=True):
            i += 1
            continue
        total = max(m['multi'] or 1, 1)
        j = i + total
        while j < len(measures) and not _ends_run(measures[j - 1]):
            n = measures[j]
            if (not _plain_rest(n) or (n['left'] or {}).get('repeat') or
                    n.get('ending') or
                    {'key', 'time'} & set(n.get('show') or ())):
                break
            k = max(n['multi'] or 1, 1)
            total += k
            j += k
        if total > 1:
            m['multi'] = total
            m['right'] = measures[j - 1]['right']
        i = j


def _ends_run(m):
    right = m['right'] or {}
    return bool(right.get('repeat') or right.get('style') not in
                (None, '', 'regular') or m.get('ending'))


def _starts_longer(text):
    """Does this unit open with a longer expression (22.3.8)?"""
    if not text.startswith(WORD):
        return False
    close = text.find(WORD, 1)
    return close > 0 and ' ' in text[:close]


def _is_letter(mark):
    """A rehearsal letter or number (24.2), as against a section name."""
    return bool(re.fullmatch(r'[A-Za-z]{1,2}\d{0,3}|\d{1,4}', mark.strip()))


def _is_road(text):
    return text.strip().lower().startswith(_ROAD)


def _word_pieces(text, width):
    """Split a long word-sign run at spaces into pieces no wider than
    width, each keeping its trailing space."""
    words = text.split(' ')
    pieces, cur = [], ''
    for w in words[:-1]:
        if cur and len(cur) + len(w) + 1 > width:
            pieces.append(cur)
            cur = ''
        cur += w + ' '
    if cur and len(cur) + len(words[-1]) > width:
        pieces.append(cur)
        cur = ''
    cur += words[-1]
    pieces.append(cur)
    return [Words(p) if isinstance(text, Words) else p for p in pieces]


def _trial(line, units, end, voice):
    """How wide the line would be with this whole measure on it."""
    import copy
    v = copy.deepcopy(voice)
    ln = copy.deepcopy(line)
    for render, ch in units:
        ln.add(render(v), ch)
    ln.music += end
    return max(len(ln.music), len(ln.chord))


def _lay(state, units, end, voice, new_line):
    """A measure onto lines: whole on this line if it fits, else whole
    on the next, else unit by unit with the music hyphen where it breaks
    (1.11) — every unit written against the voice as it stands, so the
    first note of a line always carries its octave mark (3.2.1)."""
    import copy
    ln = state['line']
    if _trial(ln, units, end, voice) > LINE and not ln.bare():
        new_line('  ')                                    # 24.1.1
        ln = state['line']
    if _trial(ln, units, end, voice) <= LINE:
        for render, ch in units:
            ln.add(render(voice), ch)
        ln.end_measure(end)
        return
    for k, (render, ch) in enumerate(units):
        snap = copy.deepcopy(voice)
        text = render(voice)
        if len(text) > LINE - 4 and ' ' in text.strip():
            # a direction longer than a line runs on like prose, broken
            # between its words — no music hyphen inside words (22.3.8)
            for pi, piece in enumerate(_word_pieces(text, LINE - 4)):
                c = ch if pi == 0 else None
                if ln.width_with(piece, c) > LINE - 1 and not ln.bare():
                    if pi == 0 and ln.in_measure:
                        ln.music += HYPHEN                 # 1.11
                    new_line('  ')
                    ln = state['line']
                    voice.fresh()
                ln.add(piece, c)
            continue
        room = LINE - (1 if k < len(units) - 1 else len(end))
        if ln.width_with(text, ch) > room and ln.in_measure:
            ln.music = ln.music.rstrip() + HYPHEN        # 1.11
            new_line('  ')
            ln = state['line']
            voice.__dict__.update(snap.__dict__)
            voice.fresh()
            voice.at_line = True
            text = render(voice)
        ln.add(text, ch)
    ln.end_measure(end)


def _wrap(text, width):
    words, lines, cur = text.split(' '), [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w) if cur else w
    if cur:
        lines.append(cur)
    return lines


def document_parts(xml):
    """[(pid, part name)] of a MusicXML document."""
    return [(pid, re.sub(r'<[^>]+>', '', name).strip())
            for pid, name in re.findall(
                r'<score-part id="([^"]+)">.*?<part-name[^>]*>(.*?)'
                r'</part-name>', xml, re.S)]


# ------------------------------------------------------------ the view

def _disc(pdf, x, y, r, gray):
    """A filled circle, four curves, in this gray (0 black, 1 white)."""
    k = 0.5523 * r
    pdf._w(f"{gray:.2f} g {x + r:.2f} {y:.2f} m "
           f"{x + r:.2f} {y + k:.2f} {x + k:.2f} {y + r:.2f} "
           f"{x:.2f} {y + r:.2f} c "
           f"{x - k:.2f} {y + r:.2f} {x - r:.2f} {y + k:.2f} "
           f"{x - r:.2f} {y:.2f} c "
           f"{x - r:.2f} {y - k:.2f} {x - k:.2f} {y - r:.2f} "
           f"{x:.2f} {y - r:.2f} c "
           f"{x + k:.2f} {y - r:.2f} {x + r:.2f} {y - k:.2f} "
           f"{x + r:.2f} {y:.2f} c f 0 g")


def brf_pages_pdf(brf_text, path, caption):
    """The braille drawn for sighted eyes: each embossed page as a page
    of dots — 40 cells by 25 lines, raised dots solid, the empty places
    of each cell faint so the grid reads — with the Braille ASCII
    beneath each line in small gray type for a transcriber. A teacher,
    a sighted bandmate or a proofreader sees exactly what the reader's
    fingers meet."""
    pdf = ce.Pdf()
    pw, ph = ce.PAGE_W, ce.PAGE_H
    left, top = 36.0, ph - 54.0
    cw = (pw - 2 * left) / LINE              # one cell's width
    lh = (top - 40.0) / PAGE                 # one braille line's height
    dx, dy, r = cw * 0.34, lh * 0.19, min(cw, lh) * 0.1
    pages = brf_text.replace('\r\n', '\n').split('\f')
    for pn, page in enumerate(p for p in pages if p.strip()):
        if pn:
            pdf.new_page()
        # the page's own fonts are Latin-1: a dash, not an em dash
        pdf.text(left, ph - 30, f"{caption} - braille page {pn + 1} "
                 f"of {len([p for p in pages if p.strip()])}"
                 .replace('\u2014', '-'), size=9)
        for li, line in enumerate(page.split('\n')[:PAGE]):
            base = top - li * lh
            for ci, ch in enumerate(line[:LINE]):
                raised = dots_of(from_brf(ch)) if ch != ' ' else set()
                x0 = left + ci * cw + cw * 0.28
                for d in range(1, 7):
                    col, row = (0 if d <= 3 else 1), (d - 1) % 3
                    x = x0 + col * dx
                    y = base - row * dy
                    if d in raised:
                        _disc(pdf, x, y, r, 0.0)
                    elif raised:
                        _disc(pdf, x, y, r * 0.45, 0.82)
                if ch != ' ':
                    # the Braille ASCII of this cell, under it
                    pdf._w("0.55 g")
                    pdf.text(x0 + dx / 2, base - 3 * dy - 2.5, ch, size=5.5,
                             center=True)
                    pdf._w("0 g")
    pdf.save(path)


# ------------------------------------------------------------ proofing

_PAIR = {'whole': 'W', '16th': 'W', 'half': 'H', '32nd': 'H',
         'quarter': 'Q', '64th': 'Q', 'eighth': 'E', '128th': 'E'}


def score_notes(xml, pid):
    """The part's notes in the order its braille writes them — each
    bar's sides as the in-accord takes them, each chord's written note
    then its intervals outward — as (pitch, value pair, dots). Rests
    and slashes are left out; cue notes stay."""
    ms, _ = ce.parse_part(xml, pid)
    out = []
    keys = any(m['state'].get('staves', 1) > 1 for m in ms or [])
    # keyboard braille is read hand by hand: the right hand's whole
    # part, intervals down, then the left's, intervals up (29.2)
    for staff, kdown in (((1, True), (2, False)) if keys else ((1, None),)):
      for m in ms or []:
        down = _down(m) if kdown is None else kdown
        ev = sorted((e for e in m['events'] if e[2] == staff),
                    key=lambda e: e[0])
        for side in _sides(m, ev, down):
            for _p, ns, _s, _v in side:
                pitched = [x for x in ns if not x.rest and not x.slash]
                if not pitched:
                    continue
                w = (max if down else min)(pitched, key=_dia)
                rest = sorted((x for x in pitched if x is not w),
                              key=lambda x: abs(_dia(x) - _dia(w)))
                for x in [w] + rest:
                    a = x.alter or 0
                    out.append((x.step + ('#' * a if a > 0 else 'b' * -a)
                                + str(x.octave),
                                _PAIR.get(x.ntype, x.ntype), x.dots))
    return out


def proofread(xml, pid, brf_text):
    """Read the braille back with the separate reader and compare it
    with the score, note for note. Returns sentences, empty when every
    note, octave mark and accidental reads back as written."""
    import chartbrailleread
    got, errors = chartbrailleread.decode(brf_text)
    want = score_notes(xml, pid)
    out = list(errors)
    for i, (a, b) in enumerate(zip(want, got)):
        if a != b:
            out.append(f"note {i + 1} is {a[0]} in the score but reads "
                       f"as {b[0]}" if a[0] != b[0] else
                       f"note {i + 1} ({a[0]}) reads with the wrong "
                       "value or dot")
    if len(want) != len(got):
        out.append(f"the score has {len(want)} notes and the braille "
                   f"reads {len(got)}")
    ms, _ = ce.parse_part(xml, pid)
    if ms and _sings(ms):
        sung = score_words(ms)
        read = chartbrailleread.decode_words(brf_text)
        if read != sung:
            k = next((i for i, (a, b) in enumerate(zip(sung, read))
                      if a != b), min(len(sung), len(read)))
            out.append(f"the words read '{read[max(0, k - 12):k + 12]}' "
                       f"where the score sings '{sung[max(0, k - 12):k + 12]}'")
        want_j = score_joins(ms)
        got_j = chartbrailleread.decode_joins(brf_text)
        if want_j != got_j:
            k = next((i for i, (a, b) in enumerate(zip(want_j, got_j))
                      if a != b), min(len(want_j), len(got_j)))
            out.append(f"note {k + 1} is paired with the wrong syllable "
                       "(a slur or tie where the words need a new one, or "
                       "the other way round)")
    return out


def score_joins(measures):
    """Per sung note: bound to the syllable before it (a melisma note
    or a tied-on note) rather than starting its own."""
    out, in_group = [], False
    for n in _lead_seq(measures):
        if n.rest or n.slash:
            in_group = False
            continue
        if n.lyric:
            out.append(False)
            in_group = True
        else:
            out.append(in_group or bool(n.tie_stop))
    return out


def score_words(measures):
    """The sung text, syllables joined into words."""
    out = ''
    for m in measures:
        for text, joins in _syllables(m):
            out += text + ('' if joins else ' ')
    return ' '.join(out.split())



# ------------------------------------------------------------ keyboard

RIGHT_HAND = cell(4, 6) + cell(3, 4, 5)       # 29.2: .>
LEFT_HAND = cell(4, 5, 6) + cell(3, 4, 5)     # 29.2: _>
PED_DOWN = cell(1, 2, 6) + cell(1, 4)         # 29.10: <c
PED_UP = cell(1, 6) + cell(1, 4)              # 29.10: *c


def _run(units, voice):
    """Units written one after another, with 22.3 (d)'s dot 3 between
    a word-sign expression and a sign carrying dot 1, 2 or 3."""
    out, after_word = '', False
    for render, _ch in units:
        t = render(voice)
        if after_word and t and not t.startswith(WORD) and \
                not t.startswith(' ') and needs_dot3(t):
            out += cell(3)
        after_word = _ends_in_word(t)
        out += t
    return out


def _mark_pedals(m, lh):
    """29.10: pedal down before the note it goes with, up after the
    note it ends on, both in the left hand; a change is a new down."""
    down, up = {}, {}
    evs = sorted((e for e in m['events'] if e[2] == lh), key=lambda e: e[0])
    for pos, kind in m.get('pedals', ()):
        if kind in ('start', 'change'):
            at = [e for e in evs if e[0] <= pos]
            if at:
                down[id(at[-1][1][0])] = True
        elif kind == 'stop':
            at = [e for e in evs if e[0] < pos]
            if at:
                up[id(at[-1][1][0])] = True
    return down, up


def _keyboard(pager, measures, tied, chords_on):
    """Keyboard music in bar-over-bar parallels (28, 29.3): the right
    hand's line over the left hand's, the chord symbols beneath when
    there are any (29.17). Each parallel opens with its measure number
    in upper cells, no numeric indicator, then the hand signs; each
    bar's parts start aligned, the next bar one space past the longer;
    every bar's first note in each hand takes an octave mark."""
    rh, lh = Voice(), Voice()
    rh.tied = lh.tied = tied
    rh.loose_ties = _loose_ties(measures, 1)
    lh.loose_ties = _loose_ties(measures, 2)
    slurs = {**_slur_plan(measures, 1), **_slur_plan(measures, 2)}
    nums = [int(m['num']) if str(m['num']).isdigit() else i + 1
            for i, m in enumerate(measures)]
    nw = max(len(str(n)) for n in nums)
    par = {'lines': None}
    pending = []

    def upper(n):
        return ''.join(UPPER[d] for d in str(n))

    def flush():
        p = par['lines']
        if p is None:
            return
        out = [p['r'].rstrip()] + p['rx'] + [p['l'].rstrip()] + p['lx']
        if p['c'].strip():
            out.append(p['c'].rstrip())
        pager.add(*(pending + out))
        pending.clear()
        par['lines'] = None

    def start(num, cont=False):
        flush()
        head = upper(num).rjust(nw) + (cell(3) if cont else ' ')
        par['lines'] = {'r': head, 'l': ' ' * len(head), 'c': '',
                        'rx': [], 'lx': [], 'first': True,
                        'music': len(head) + 2}

    skip = 0
    for i, m in enumerate(measures):
        if skip:
            skip -= 1
            continue
        if m['multi'] and m['multi'] > 1:
            skip = m['multi'] - 1
        num = nums[i]
        if m['rehearsal']:
            flush()
            pending.append(WORD + literary(m['rehearsal'], music=True) + WORD)
        if m['rehearsal'] or m['signs'] or par['lines'] is None:
            start(num)
        st = m['state']
        sig = ''
        if i > 0 and 'key' in m['show']:
            sig += _key_sign(st['fifths'])
        if i > 0 and 'time' in m['show']:
            sig += _time_sign(st['time'])
        signs = [SEGNO if s_ == 'segno' else CODA for s_ in m['signs']]
        attach = ''
        if (m['left'] or {}).get('repeat') == 'forward':
            attach += REPEAT_FWD
        for enum, etype, _left in m.get('ending') or []:
            if etype == 'start':
                attach += NUM + ''.join(LOWER[d] for d in str(enum))
        road = [t for _p, t in m['texts'] if _is_road(t)]
        m['texts'] = [(p_, t) for p_, t in m['texts'] if not _is_road(t)]
        post = ''
        for t in road:
            w = expression(t)
            w = w if w.endswith(WORD) else w + WORD
            post += ' ' + ((CODA + ' ') if t.lower().startswith('to coda')
                           else '') + w
        right = m['right'] or {}
        end = (REPEAT_BACK if right.get('repeat') == 'backward' else
               FINAL_BAR if right.get('style') == 'light-heavy' else
               SECTION_BAR if right.get('style') == 'light-light' else '')
        lh.ped_down, lh.ped_up = _mark_pedals(m, 2)
        ur, slashed = measure_units(m, slurs, staff=1, down=True)
        if slashed and par.get('in_slash'):
            wn = len(m['texts']) + 1        # "slashes" once a passage
            ur = ur[:wn - 1] + ur[wn:]
        par['in_slash'] = slashed
        ul, _ = measure_units(m, slurs, staff=2, down=False, words=False)

        def write(units, voice, lead):
            voice.fresh()                                     # 29.3 (a)
            text = _run(units, voice)
            head = ' '.join(signs) + (' ' if signs else '') if lead else ''
            if sig:
                head += sig + ' '
            if attach:
                if _starts_longer(text):
                    text = HYPHEN + ' ' + text
                elif needs_dot3(text) and attach[-1] in LOWER.values():
                    text = cell(3) + text                  # 17.1.1
            return head + attach + text + end
        snap = (dict(rh.__dict__), dict(lh.__dict__))
        tr = write(ur, rh, True) + post
        tl = write(ul, lh, False)
        ch = ''.join(chord_braille(c) for _p, c in sorted(m['chords'])) \
            if chords_on else ''
        p = par['lines']

        def fits(p):
            col = _col(p)
            return col + max(len(tr), len(tl), len(ch)) <= LINE
        if not p['first'] and not fits(p):
            rh.__dict__.update(snap[0])
            lh.__dict__.update(snap[1])
            start(num)
            tr = write(ur, rh, True) + post
            tl = write(ul, lh, False)
            p = par['lines']
        if p['first']:
            r = RIGHT_HAND + (cell(3) if needs_dot3(tr) else '')
            l_ = LEFT_HAND + (cell(3) if needs_dot3(tl) else '')
            p['r'] += r
            p['l'] += l_
            p['c'] = ' ' * len(p['r'])
            p['first'] = False
            col = len(p['r'])
        else:
            col = _col(p)
            p['r'] = p['r'].ljust(col)
            p['l'] = p['l'].ljust(col)
            p['c'] = p['c'].ljust(col)
        runover = False
        for key, text, extra in (('r', tr, 'rx'), ('l', tl, 'lx')):
            room = LINE - len(p[key])
            if len(text) <= room:
                p[key] += text
                continue
            # 29.3.2: a run-over line, two cells in from the alignment
            runover = True
            pieces = _split_music(text, room, LINE - (len(p[key]) + 2))
            p[key] += pieces[0]
            p[extra] += [' ' * (len(p['r']) - len(pieces[0]) + 2) + x
                         for x in pieces[1:]]
        p['c'] = p['c'].ljust(max(len(p['c']), col)) + ch
        if runover or end in (FINAL_BAR,):
            flush()
    flush()


def _col(p):
    """Where the next bar starts: one space past the longest line."""
    return max(len(p['r']), len(p['l']), len(p['c'])) + 1


def _split_music(text, first, rest):
    """Break a hand's bar between signs at spaces or, failing that,
    anywhere a music hyphen can stand, into pieces that fit."""
    out, cur = [], text
    room = first
    while len(cur) > room:
        cut = cur.rfind(' ', 0, room)
        if cut <= 0:
            cut = room - 1
            out.append(cur[:cut] + HYPHEN)
            cur = cur[cut:]
        else:
            out.append(cur[:cut])
            cur = cur[cut + 1:]
        room = rest
    out.append(cur)
    return out




# ------------------------------------------------------------ voice

def _sings(measures):
    return any(n.lyric for m in measures for _p, ns, st, _v in m['events']
               if st == 1 for n in ns[:1])


def _lead_seq(measures):
    return [ns[0] for m in measures
            for _p, ns, st, _v in sorted(m['events'], key=lambda e: e[0])
            if st == 1]


def _syllabic_slurs(measures):
    """35.2: the notes sung to one syllable are slurred — a single slur
    after each but the last, or for more than four notes a doubled slur
    after the first and a single one after the next to last. A note
    tied on needs no slur beside its tie."""
    plan, group = {}, []

    def close():
        notes = [x for x in group]
        if len(notes) >= 2:
            if len(notes) > 4:
                plan[id(notes[0])] = 'double'
                if not notes[-2].tie_start:
                    plan[id(notes[-2])] = 'short'
            else:
                for x in notes[:-1]:
                    if not x.tie_start:
                        plan[id(x)] = 'short'
        group.clear()
    for n in _lead_seq(measures):
        if n.rest or n.slash:
            close()
        elif n.lyric:
            close()
            group.append(n)
        elif group:
            group.append(n)
    close()
    return plan


def _syllables(m):
    """The measure's sung syllables in time order: (text, joins on)."""
    out = []
    for _p, ns, st, _v in sorted(m['events'], key=lambda e: e[0]):
        n = ns[0]
        if st == 1 and n.lyric:
            kind, text, _ext = n.lyric
            out.append((text, kind in ('begin', 'middle')))
    return out


def _spans(measures):
    """Every sung syllable with its time: {id(note): (start, end)}, the
    end running through its melisma and ties up to the next syllable or
    rest; times count from the top of the part in divisions."""
    out, at, cur = {}, 0, None
    for m in measures:
        for pos, ns, st, _v in sorted(m['events'], key=lambda e: e[0]):
            if st != 1:
                continue
            n, t = ns[0], at + pos
            if cur is not None and (n.rest or n.slash or n.lyric):
                out[cur[0]] = (cur[1], t)
                cur = None
            if n.lyric and not n.rest:
                cur = (id(n), t)
        at += max(m.get('len') or 0, 1) or _bar_length(m)
    if cur is not None:
        out[cur[0]] = (cur[1], at)
    return out


def _vocal(pager, measures, tied, chords_on=True):
    """Line-by-line format (35.1): each parallel is a line of words at
    the margin and, beneath it from the third cell, the music they are
    sung to, the syllables and notes paired exactly. Words are written
    whole, uncontracted; a word carried into the next parallel ends its
    line with a hyphen. Every music line's first note takes its octave
    mark. Parallels break where a phrase ends when there is a choice,
    so a phrase of words stays together for memorizing (35.1.3). With
    chord symbols the parallel grows a chord line between the words
    and the music, each chord placed by when it sounds (36)."""
    import copy
    voice = Voice()
    voice.tied = tied
    voice.loose_ties = _loose_ties(measures)
    slurs = _syllabic_slurs(measures)
    spans = _spans(measures)
    nums = [int(m['num']) if str(m['num']).isdigit() else i + 1
            for i, m in enumerate(measures)]
    starts, at = [], 0
    for m in measures:
        starts.append(at)
        at += max(m.get('len') or 0, 1) or _bar_length(m)
    par = {'syl': [], 'ch': [], 'm': '', 'first': None}
    pending = []

    def layout(syl, chs, split):
        if chs:
            return _lay_words(syl, chs, split, number(par['first'] or 1))
        if not syl:
            return [number(par['first'] or 1)], None
        text = words_line(syl, split)
        return _prose_lines(text, LINE, 4), None

    def flush():
        if par['first'] is None:
            return
        syl = par['syl']
        split = bool(syl) and syl[-1]['joins']
        words, chord = layout(syl, par['ch'], split)
        music = _music_lines(par['m'].rstrip())
        pager.add(*(pending + words + ([chord] if chord else []) + music))
        pending.clear()
        par.update(syl=[], ch=[], m='', first=None)

    in_slash = False
    skip = 0
    for i, m in enumerate(measures):
        if skip:
            skip -= 1
            continue
        if m['multi'] and m['multi'] > 1:
            skip = m['multi'] - 1
        if m['rehearsal']:
            flush()
            pending.append(WORD + literary(m['rehearsal'], music=True) + WORD)
        units, slashed, tail = _measure_frame(m, i, slurs, in_slash)
        in_slash = slashed
        syl = []
        for pos, ns, st, _v in sorted(m['events'], key=lambda e: e[0]):
            n = ns[0]
            if st == 1 and n.lyric and not n.rest:
                kind, text, _ext = n.lyric
                a, b = spans.get(id(n), (starts[i] + pos, starts[i] + pos))
                syl.append({'t': text, 'joins': kind in ('begin', 'middle'),
                            'start': a, 'end': b})
        chs = ([(starts[i] + p_, c) for p_, c in sorted(m['chords'])]
               if chords_on else [])
        trial = copy.deepcopy(voice)
        if par['first'] is None:
            trial.fresh()
        mtext = _run(units, trial) + tail
        room_m = LINE - 2 - (len(par['m']) + 1 if par['m'] else 0)
        if par['first'] is not None:
            w, c = layout(par['syl'] + syl, par['ch'] + chs, False)
            too_wide = (len(w) > 1 or max(len(x) for x in w) > LINE or
                        (c is not None and len(c) > LINE))
            if too_wide or len(mtext) > room_m:
                flush()
        if par['first'] is None:
            par['first'] = nums[i]
            voice.fresh()                               # 35.1.2
            first = _lead_seq([m])
            if first and first[0].tie_stop:
                par['m'] = TIE                          # 35.3.2
        text = _run(units, voice) + tail
        if tail:
            voice.fresh()
        par['m'] += (' ' if par['m'] and par['m'] != TIE else '') + text
        par['syl'] += syl
        par['ch'] += chs
        # a phrase ends here: words that end with punctuation, or the
        # bar ends in a rest after singing — break if the line is full
        # enough to be worth it
        seq = _lead_seq([m])
        ends = (syl and syl[-1]['t'][-1:] in ',.;:!?') or \
            (syl and seq and seq[-1].rest)
        if ends and len(words_line(par['syl'], False)) >= LINE // 2:
            flush()
    flush()


def words_line(syl, split):
    out = ''
    for k, s_ in enumerate(syl):
        out += s_['t']
        if not s_['joins'] and k < len(syl) - 1:
            out += ' '
    return literary(' '.join(out.split())) + ('-' if split else '')


DOTS36 = cell(3, 6) * 2                    # 36.1, 36.2: the spacer


def _lay_words(syl, chs, split, num):
    """36.3: the words and, beneath, each chord's capital placed by when
    it sounds — under the syllable's first cell when with it, two cells
    left when before it, after a hyphen under the syllable when during
    it, one cell past the syllable's last letter when after it. The
    words spread where chords need room (36.2): a word split between
    syllables takes a hyphen, and a gap of four cells or more carries a
    run of dots 3-6."""
    plan = []                                   # (syllable index, kind)
    for t, sym in chs:
        kind, k = None, None
        for j, s_ in enumerate(syl):
            if s_['start'] == t:
                kind, k = 'with', j
                break
            if s_['start'] < t < s_['end']:
                kind, k = 'during', j
                break
        if kind is None:
            later = [j for j, s_ in enumerate(syl) if s_['start'] > t]
            if later:
                kind, k = 'before', later[0]
            elif syl:
                kind, k = 'after', len(syl) - 1
            else:
                kind, k = 'bare', None
        plan.append((kind, k, chord_braille(sym)))
    words, chord = '', ''
    placed = 0
    if not syl:
        words = num
        for kind, k, cb_ in plan:
            chord = chord.ljust(max(len(chord) + (1 if chord else 0), 0))
            chord += cb_
        return [words], chord
    for j, s_ in enumerate(syl):
        text = literary(s_['t']) if j == 0 or not syl[j - 1]['joins'] \
            else literary(s_['t'], caps=True)
        here = [(kind, cb_) for kind, k, cb_ in plan if k == j]
        need = len(words) + (0 if j == 0 or syl[j - 1]['joins'] else 1)
        natural = need
        for kind, cb_ in here:
            lead = {'with': 0, 'during': 0, 'before': 2, 'after': 0}[kind]
            if kind == 'after':
                continue
            need = max(need, len(chord) + (1 if chord else 0) + lead)
        if j == 0 and need >= 2 and need > natural:
            words = DOTS36.ljust(need)             # 36.1 opening spacer
        elif need > natural:
            gap = need - len(words)
            if j and syl[j - 1]['joins']:
                words += '-'                        # 36.2 split word
                gap -= 1
                need = max(need, len(words))
            if gap >= 4:
                words += ' ' + DOTS36 + ' ' * (gap - len(DOTS36) - 1)
            else:
                words += ' ' * max(gap, 0)
        else:
            words += ' ' if j and not syl[j - 1]['joins'] else ''
        col = len(words)
        words += text
        during = False
        for kind, cb_ in here:
            if kind == 'with':
                chord = chord.ljust(col) + cb_
            elif kind == 'before':
                chord = chord.ljust(col - 2) + cb_
            elif kind == 'during':
                if not during:
                    chord = chord.ljust(col) + '-' + cb_
                    during = True
                else:
                    chord += ' -' + cb_
            else:                                   # after
                chord = chord.ljust(max(len(words) + 1,
                                        len(chord) + 1)) + cb_
    if split:
        words += '-'
    return _prose_lines(words, 10 ** 6, 4), chord


def _prose_lines(text, width, indent):
    """Words at the margin, run over from cell 5 when too long (35.1)."""
    out, cur = [], ''
    for w in text.split(' '):
        lim = width if not out else width - indent
        if cur and len(cur) + 1 + len(w) > lim:
            out.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w) if cur else w
    out.append(cur)
    return [out[0]] + [' ' * indent + x for x in out[1:]]


def _music_lines(text):
    """Music from cell 3, run over from cell 5 at a space or, inside a
    bar, with the music hyphen (35.1, 1.11)."""
    if 2 + len(text) <= LINE:
        return ['  ' + text]
    pieces = _split_music(text, LINE - 2, LINE - 4)
    return ['  ' + pieces[0]] + ['    ' + x for x in pieces[1:]]
