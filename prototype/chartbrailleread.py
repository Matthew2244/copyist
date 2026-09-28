#!/usr/bin/env python3
"""
chartbrailleread — the proofreader for Copyist's braille.

Reads a single-line part's .brf back into notes the way a braille music
reader does, by the rules of BANA's Music Braille Code 2015: octave marks
and the interval rule (3.2), accidentals carried through the bar and
held by ties (10.1.3), chords as intervals (9.1), in-accords (11.1),
the value range of each cell. It is written apart from chartbraille, on
purpose — a reader that shares the writer's code shares its mistakes.

The suite reads every braille part back with it and compares note by
note with the score; any note that needed an octave mark and lacks one
(3.2.1) is an error on its own. Values come back as the cell's pair
(whole or 16th, half or 32nd, quarter or 64th, eighth or 128th): the
cell is all a reader has, and value signs settle the rest where needed.
"""

import re

ROW = 'CDEFGAB'
NOTE = {}
for cls, cells in (('E', 'DEFGHIJ'), ('Q', '?:$]\\[W'), ('H', 'NOPQRST'),
                   ('W', 'YZ&=(!)')):
    for step, c in zip(ROW, cells):
        NOTE[c] = (step, cls)
RESTS = {'M': 'W', 'U': 'H', 'V': 'Q', 'X': 'E'}
OCT = {'@': 1, '^': 2, '_': 3, '"': 4, '.': 5, ';': 6, ',': 7}
ACCS = {'%': 1, '<': -1, '*': 0}
UPPER = 'JABCDEFGHI'           # 0-9 upper-cell digits
LOWER = '0123456789'           # lower-cell ASCII: dots 356 .. 35
SHARPS, FLATS = 'FCGDAEB', 'BEADGCF'


def key_base(fifths):
    if fifths > 0:
        return {s: 1 for s in SHARPS[:fifths]}
    if fifths < 0:
        return {s: -1 for s in FLATS[:-fifths]}
    return {}


def parse_key(tok):
    """'%%', '<<<', '#D<' (4 flats), '*' -> fifths."""
    m = re.fullmatch(r'#([A-J])([%<])', tok)
    if m:
        k = UPPER.index(m.group(1))
        return k if m.group(2) == '%' else -k
    if tok and set(tok) <= {'%'}:
        return len(tok)
    if tok and set(tok) <= {'<'}:
        return -len(tok)
    return 0


class Reader:
    def __init__(self, fifths):
        self.base = key_base(fifths)
        self.prev = None           # (step, octave)
        self.carry = {}            # (step, octave) -> alter in this bar
        self.notes = []
        self.errors = []
        self.event_notes = []
        self.down = True           # intervals read downward (9.2)
        self.event = None          # (step, octave, cls, dots) written
        self.cprev = None          # (step, octave) last note of chord
        self.held = {}             # (step, octave) -> alter tied in
        self.pending = {}          # ties this event sends on
        self.last_key = None

    def bar(self):
        self.carry = {}

    def fresh(self):
        self.prev = None

    def interval(self, num, octave, acc):
        """9.1: a chord note num steps from the written note, placed
        just past the chord's previous note unless its octave is marked."""
        ws, wo, cls, dots = self.event
        w = wo * 7 + ROW.index(ws)
        tgt = w - num if self.down else w + num
        step = ROW[tgt % 7]
        if octave is None:
            ps, po = self.cprev
            p = po * 7 + ROW.index(ps)
            cand = [o * 7 + ROW.index(step) for o in range(0, 9)]
            if self.down:
                below = [c for c in cand if 1 <= p - c <= 7]
                pos = max(below)
            else:
                above = [c for c in cand if 1 <= c - p <= 7]
                pos = min(above)
            octave = pos // 7
        self._record(step, octave, cls, dots, acc)
        self.cprev = (step, octave)

    def _record(self, step, octave, cls, dots, acc):
        k = (step, octave)
        if acc is not None:
            alter = acc
            self.carry[k] = acc
        elif self.held.get(k):
            alter = self.held[k].pop(0)
        else:
            alter = self.carry.get(k, self.base.get(step, 0))
        self.notes.append((f'{step}{"#" * alter if alter > 0 else "b" * -alter}'
                           f'{octave}', cls, dots))
        self.last_key = (k, alter)
        self.event_notes.append((k, alter))

    def tie(self, chord=False):
        if chord:
            for (k, a) in self.event_notes:
                self.pending.setdefault(k, []).append(a)
        elif self.last_key:
            self.pending.setdefault(self.last_key[0], []).append(
                self.last_key[1])

    def note(self, step, cls, octave, acc, dots):
        if octave is None:
            if self.prev is None:
                self.errors.append(f'note {len(self.notes) + 1} '
                                   f'({step}) has no octave mark where one '
                                   f'is required (3.2.1)')
                octave = 4
            else:
                ps, po = self.prev
                here = po * 7 + ROW.index(ps)
                best = None
                for o in (po - 1, po, po + 1):
                    d = o * 7 + ROW.index(step) - here
                    if best is None or abs(d) < abs(best[1]):
                        best = (o, d)
                if abs(best[1]) <= 2:
                    octave = best[0]
                else:
                    octave = po            # an unmarked 4th or 5th
        self.held, self.pending = self.pending, {}
        self.event_notes = []
        self._record(step, octave, cls, dots, acc)
        self.prev = (step, octave)
        self.event = (step, octave, cls, dots)
        self.cprev = (step, octave)


def decode(brf):
    """BRF text -> (notes, errors): notes as (pitch, value pair, dots),
    pitch like 'Bb4'; the value pair a letter: W (whole or 16th),
    H (half or 32nd), Q (quarter or 64th), E (eighth or 128th)."""
    pages = brf.replace('\r\n', '\n').split('\f')
    lines, in_tn, head = [], False, None
    for pi, page in enumerate(pages):
        ls = page.split('\n')[1:]
        if pi == 0:
            ls = ls[ls.index('') + 1:] if '' in ls else ls
        for l in ls:
            t = l.strip()
            if not t:
                continue
            if t.startswith('@.<'):
                in_tn = True
            if in_tn:
                in_tn = not t.endswith('@.>')
                continue
            if head is None:
                head = t.split()[-1]
                continue
            if re.fullmatch(r'>,.*>', t):
                continue                          # a rehearsal letter
            if all(re.match(r',[A-Z]', w) for w in t.split()):
                continue                          # chord symbols (27)
            lines.append(re.sub(r'^#[A-J]+ ', '', t))
    # a longer expression broken between lines runs on (22.3.8)
    joined = []
    for l in lines:
        if joined and _open_expr(joined[-1]):
            joined[-1] += ' ' + l
        else:
            joined.append(l)
    lines = joined
    m = re.match(r'(#[A-J][%<]|[%<*]*)#', head)
    r = Reader(parse_key(m.group(1)) if m else 0)
    # 9.2: the transcriber's note says which way intervals read
    r.down = 'READING UPWARD' not in ' '.join(brf.split())
    for li, line in enumerate(lines):
        r.fresh()                                  # 3.2.1: a new line
        cont = li > 0 and lines[li - 1].endswith('"')
        if not cont:
            r.bar()
        read_line(r, line[:-1] if line.endswith('"') else line)
    return r.notes, r.errors


def _open_expr(line):
    """Does this line end inside a longer expression?"""
    i, inside = 0, False
    while i < len(line):
        if line[i] == '>':
            if inside:
                inside = False
            else:
                j = line.find('>', i + 1)
                rest = line[i + 1:] if j == -1 else line[i + 1:j]
                if ' ' in rest and re.fullmatch(r"[A-Z0-9#',.\-7 ;]+", rest):
                    if j == -1:
                        return True
                    inside = True
        i += 1
    return False


def read_line(r, s):
    i, n = 0, len(s)
    acc, octave = None, None
    in_event, in_accord = False, False
    IV = {'/': 1, '+': 2, '#': 3, '9': 4, '0': 5, '3': 6, '-': 7}

    def take_word(i):
        """At a word sign: skip the expression, return the new index."""
        j = s.find('>', i + 1)
        if j != -1 and (j + 1 == n or s[j + 1] in ' "<'):
            # a longer expression, or a closed one (">FINE>")
            if ' ' in s[i:j] or j + 1 == n or s[j + 1] in ' "<':
                return j + 1
        k = i + 1
        while k < n and (s[k].isalpha() or s[k] in "'7-"):
            if s[k] == "'":
                return k + 1                        # dot 3 ends the word
            k += 1
        return k
    while i < n:
        c = s[i]
        two = s[i:i + 2]
        if two == '" ':                            # a gap inside a bar
            i += 2                                 # (27.4), all its spaces
            while s[i:i + 1] == ' ':
                i += 1
            continue
        if c == ' ':
            i += 1
            # a space divides measures unless inside a word group
            r.bar()
            in_event = False
            if in_accord:                          # 11.1
                r.fresh()
                in_accord = False
            continue
        if in_event and c in IV:                   # 9.1: an interval
            r.interval(IV[c], octave, acc)
            acc, octave = None, None
            i += 1
            continue
        if two == '<>':                            # 11.1.1 in-accord
            r.bar()
            r.fresh()
            in_event, in_accord = False, True
            i += 2
            continue
        if two == '.C':                            # 10.2 chord tie
            r.tie(chord=True)
            i += 2
            continue
        if c == '"' and s[i + 1:i + 2] in ACCS:     # 10.1.3, 11.2
            acc = ACCS[s[i + 1]]
            i += 2
            continue
        if c == '"' and s[i + 1:i + 2] in RESTS:    # 11.1.1 added rest
            i += 2
            in_event = False
            continue
        if c == '>':
            i = take_word(i)
            r.fresh()                              # 22.3 (e)
            continue
        if two in ('<K', '<7', '<2'):
            i += 2
            if s[i:i + 1] == "'":
                i += 1
            r.fresh()
            r.bar()
            continue
        if two == '<L':                            # fermata
            i += 2
            continue
        if two == '@C':                            # tie
            r.tie()
            i += 2
            continue
        if s.startswith(',<1', i) or s.startswith('^<1', i):
            i += 3
            continue
        if two == ',5':                            # 21.6 small type
            i += 2
            continue
        if two == '+L':
            i += 2
            r.fresh()
            continue
        if c == '+':
            i += 1
            r.fresh()
            continue
        if c == '#':
            m = re.match(r'#([A-J]+)M', s[i:])
            if m:                                   # multi-measure rest
                i += m.end()
                r.fresh()
                r.bar()
                continue
            m = re.match(r'#([A-J]+)([%<])', s[i:])
            if m:                                   # key by number
                r.base = key_base(parse_key(m.group(0)))
                i += m.end()
                r.fresh()
                continue
            m = re.match(r'#([A-J]+)([0-9]+)', s[i:])
            if m:                                   # time signature
                i += m.end()
                r.fresh()
                continue
            m = re.match(r"#([0-9]+)'?", s[i:])
            if m:                                   # volta
                i += m.end()
                r.fresh()
                continue
            i += 1
            continue
        if c in '%<*' and re.match(r'[%<*]+(#|\s|$)', s[i:]) and \
                (i == 0 or s[i - 1] == ' '):
            m = re.match(r'([%<*]+)', s[i:])      # key signature
            r.base = key_base(parse_key(m.group(1)) if '*' not in m.group(1)
                              else 0)
            i += m.end()
            r.fresh()
            continue
        if two in (';B', '^2'):                     # bracket slur
            i += 2
            continue
        if c in ',"_.^@;' and s[i + 1:i + 2] == '8':
            i += 2                                 # an articulation
            continue
        if c == '8':
            i += 1
            continue
        m = re.match(r"(?:_[0-9]+)+'", s[i:])
        if m:                                      # tuplet group
            i += m.end()
            continue
        if c == '2':                               # triplet
            i += 1
            continue
        if c == 'C':                               # short slur
            i += 1
            continue
        if c in ACCS:
            acc = ACCS[c]
            i += 1
            continue
        if c in OCT:
            octave = OCT[c]
            i += 1
            continue
        if c in RESTS:
            i += 1
            while s[i:i + 1] == "'":
                i += 1
            acc, octave = None, None
            in_event = False
            continue
        if c in NOTE:
            step, cls = NOTE[c]
            i += 1
            dots = 0
            while s[i:i + 1] == "'":
                dots += 1
                i += 1
            r.note(step, cls, octave, acc, dots)
            acc, octave = None, None
            in_event = True
            continue
        r.errors.append(f'unread sign {c!r} at {s[max(0, i - 8):i + 8]!r}')
        i += 1
