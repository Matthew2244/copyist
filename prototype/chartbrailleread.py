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
        self.keyboard = False      # 29.3 (a): every bar marks its octave
        self.perc = False          # 34.4 (b): a head sign is the note's own
        self.link = False          # the next note is bound to the last
        self.double = False        # a doubled slur is running (35.2)
        self.joins = []            # per note: sung on the last syllable?
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
            if not self.perc:
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
        self.joins.append(self.link)
        self.link = self.double
        self._record(step, octave, cls, dots, acc)
        self.prev = (step, octave)
        self.event = (step, octave, cls, dots)
        self.cprev = (step, octave)


def decode(brf):
    """BRF text -> (notes, errors): notes as (pitch, value pair, dots),
    pitch like 'Bb4'; the value pair a letter: W (whole or 16th),
    H (half or 32nd), Q (quarter or 64th), E (eighth or 128th)."""
    pages = brf.replace('\r\n', '\n').split('\f')
    lines, in_tn, head, raw = [], False, None, []
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
            if head is None or head == '':
                # 1.7 (c): a heading too wide for one line puts its
                # metronome and signatures on a second; it ends at the
                # time signature
                if _signatures(t) or head == '':
                    head = t.split()[-1]
                else:
                    head = ''
                continue
            raw.append(l.rstrip())
            if re.fullmatch(r'>,.*>', t):
                continue                          # a rehearsal letter
            if all(re.match(r',[A-Z]', w) for w in t.split()):
                continue                          # chord symbols (27)
            lines.append(re.sub(r'^#[A-J]+ ', '', t))
    perc = 'STAFF POSITIONS' in ' '.join(brf.split())
    if any(re.match(r">[A-Z0-9]+' ", l) for l in raw):
        return _ensemble(raw, head, brf)
    if any(re.match(r"\s*[A-J]+[ ']\.>", l) for l in lines):
        return _keyboard(lines, head)
    if _is_vocal(raw):
        return _vocal(raw, head)[:2]
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
    r.down = not ('READING UPWARD' in ' '.join(brf.split())
                  or 'READ UPWARD' in ' '.join(brf.split()))
    r.perc = perc
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
                m = re.match(r"[A-Z0-9]+'", line[i + 1:])
                if m:                     # a short word, closed by dot 3
                    i += 1 + m.end()
                    continue
                j = line.find('>', i + 1)
                rest = line[i + 1:] if j == -1 else line[i + 1:j]
                words = re.fullmatch(r"[A-Z0-9#',.\-7 ;]+", rest)
                if j == -1 and words:
                    return True           # still running at the line end
                if ' ' in rest and words:
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
            if r.keyboard:
                r.fresh()
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
        if two in ('<C', '*C'):                    # 29.10 pedal down, up
            i += 2
            continue
        if two == '<L':                            # fermata
            i += 2
            continue
        if two == '@C':                            # tie
            r.tie()
            r.link = True
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
        if two == 'CC':                            # doubled slur (35.2)
            r.double = r.link = True
            i += 2
            continue
        if c == 'C':                               # short slur
            r.link = True
            r.double = False
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
            r.link = r.double = False
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



def _signatures(t):
    """Does this heading line end with the key and time signatures?"""
    return bool(re.fullmatch(r'(?:[%<*]*|#[A-J]+[%<])#[A-J]+[0-9]+',
                             t.split()[-1]))


def _keyboard(lines, head):
    """Bar-over-bar keyboard braille (29.3): each parallel's right-hand
    line (and its run-overs) joins one stream, the left hand's another;
    each is read in its own direction for intervals (29.2)."""
    hands = {'r': [], 'l': []}
    cur = None
    for l in lines:
        m = re.match(r"\s*[A-J]+[ ']\.>'?(.*)$", l)
        if m:
            cur = 'r'
            hands['r'].append(m.group(1))
            continue
        m = re.match(r"\s*_>'?(.*)$", l)
        if m:
            cur = 'l'
            hands['l'].append(m.group(1))
            continue
        if cur:
            hands[cur].append(l.strip())            # a run-over line
    notes, errors = [], []
    km = re.match(r'(#[A-J][%<]|[%<*]*)#', head or '')
    for hand, down in (('r', True), ('l', False)):
        text = ''
        for seg in hands[hand]:
            if text.endswith('"'):
                text = text[:-1] + seg.strip()
            else:
                text += (' ' if text else '') + seg.strip()
        r = Reader(parse_key(km.group(1)) if km else 0)
        r.down = down
        r.keyboard = True
        read_line(r, text)
        notes += r.notes
        errors += [f"{'right' if down else 'left'} hand: {e}"
                   for e in r.errors]
    return notes, errors



def _chordline(t):
    return all(re.match(r'-?,[A-Z]', w) for w in t.split())


def _is_vocal(raw):
    """Line-by-line vocal format (35.1): word lines at the margin. A
    single-line part's margin lines always open with a measure number."""
    for l in raw:
        if not l or l[0] == ' ' or re.fullmatch(r'>,.*>', l) or \
                _chordline(l):
            continue
        if not re.match(r'#[A-J]+( |$)', l):
            return True
    return False


def _vocal(raw, head):
    """Words and music in parallels: the music read line by line, each
    line's first note needing its mark; the words gathered whole."""
    km = re.match(r'(#[A-J][%<]|[%<*]*)#', head or '')
    r = Reader(parse_key(km.group(1)) if km else 0)
    r.down = 'READING UPWARD' not in ' '.join(raw)
    words, kind, music = [], None, []
    for l in raw:
        if re.fullmatch(r'>,.*>', l) or (l.strip() and _chordline(l)):
            continue
        if not l.startswith(' '):
            kind = 'w'
            words.append(('new', l))
        elif l.startswith('    '):
            if kind == 'w':
                words.append(('run', l.strip()))
            elif music[-1].endswith('"'):
                music[-1] = music[-1][:-1] + l.strip()   # 1.11 hyphen
            else:
                music[-1] += ' ' + l.strip()
        else:
            kind = 'm'
            music.append(l.strip())
    for li, line in enumerate(music):
        r.fresh()                                  # 35.1.2
        r.bar()
        if line.startswith('@C'):                  # 35.3.2 restated tie
            line = line[2:]
        read_line(r, line)
    text = ''
    for how, w in words:
        if re.fullmatch(r'#[A-J]+', w):
            continue                               # a bar number
        if text.endswith('-'):
            text = text[:-1] + w                   # a word carried over
        else:
            text += (' ' if text else '') + w
    r.errors += []
    _vocal.joins = r.joins
    return r.notes, r.errors, back_translate(text)


def decode_words(brf):
    """The words of a vocal part, back in print."""
    pages = brf.replace('\r\n', '\n').split('\f')
    raw, in_tn, head = [], False, None
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
            if head is None or head == '':
                if _signatures(t) or head == '':
                    head = t.split()[-1]
                else:
                    head = ''
                continue
            raw.append(l.rstrip())
    return _vocal(raw, head)[2] if _is_vocal(raw) else ''


def decode_joins(brf):
    """For each note of a vocal part: is it sung on the syllable before
    (bound by a slur or tie) rather than starting a new one?"""
    decode_words(brf)
    return list(getattr(_vocal, 'joins', []))


_PUNCT_BACK = {'1': ',', '4': '.', '8': '?', '6': '!', '2': ';', '3': ':',
               "'": "'", '-': '-'}


def back_translate(text):
    """Uncontracted UEB back to print: letters, the capital signs, the
    numeric indicator, the common punctuation."""
    out, i, word_caps, num = [], 0, False, False
    while i < len(text):
        c = text[i]
        if c == ' ':
            out.append(' ')
            word_caps = num = False
            i += 1
            continue
        if text.startswith(',,', i):
            word_caps = True
            i += 2
            continue
        if c == ',' and i + 1 < len(text) and text[i + 1].isalpha():
            out.append(text[i + 1].upper())
            i += 2
            continue
        if c == '#':
            num = True
            i += 1
            continue
        if num and c in UPPER:
            out.append(str(UPPER.index(c)))
            i += 1
            continue
        num = False
        if c.isalpha():
            out.append(c.upper() if word_caps else c.lower())
        elif c in _PUNCT_BACK:
            out.append(_PUNCT_BACK[c])
        else:
            out.append('?')
        i += 1
    return ''.join(out)



def _ensemble(raw, head, brf):
    """An ensemble score (33), as a percussion part is written: each
    instrument's lines, found by the abbreviation at the margin, read as
    one stream in the table's order; free lines, guide dots and the
    transcriber's rests pass by."""
    table = []
    for l in brf.replace('\r\n', '\n').split('\n'):
        if l.startswith('@.<'):
            break
        m = re.search(r">([A-Z0-9]+)'", l)
        if m and m.group(1) not in table:
            table.append(m.group(1))
    streams, last = {}, None
    for l in raw:
        m = re.match(r">([A-Z0-9]+)' +(.*)$", l)
        if m:
            last = m.group(1)
            streams.setdefault(last, []).append(m.group(2))
            continue
        t = l.strip()
        if not t or re.fullmatch(r'#[A-J]+|>,.*>', t):
            continue
        if last and l.startswith(' '):
            prev = streams[last][-1]
            streams[last][-1] = (prev[:-1] + '\n' + t if prev.endswith('"')
                                 else prev + '\n ' + t)  # a run-over
    notes, errors = [], []
    km = re.match(r'(#[A-J][%<]|[%<*]*)#', head or '')
    for ab in table or list(streams):
        for line in streams.get(ab, []):
            line = re.sub(r"(?<= )'{3,}(?= )", '', line)   # guide dots
            r = Reader(parse_key(km.group(1)) if km else 0)
            r.down = False
            r.perc = True
            # each braille line, run-overs too, marks its first octave
            for k, part in enumerate(line.split('\n')):
                r.fresh()
                if not part.startswith(' '):
                    r.bar()
                read_line(r, part.strip())
            notes += r.notes
            errors += [f"{ab}: {e}" for e in r.errors]
    return notes, errors
