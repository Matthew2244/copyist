#!/usr/bin/env python3
"""chartengrave — Copyist draws its own pages.

Stage two of the MuseScore exit: a PDF engraver for the bounded
MusicXML subset Copyist itself emits. Version one takes every
single-staff part — clefs, keys, meters and their mid-chart changes,
beams, ties, slurs, tuplets, articulations, ghosts in parentheses,
slash and kick notation, cue-size notes, lyrics with melisma lines,
chord symbols, dynamics, texts, rehearsal boxes, repeats with volta
brackets, multirests with their counts — and declines, in a sentence,
what it cannot yet draw (grand staves, and material lifted from someone
else's engraving). Pure stdlib; the PDF is written by hand, words in
the PDF's own standard fonts, music glyphs as vector paths.

The quality bar is a page a player reads without comment. The beauty
bar comes with iteration — this file is where fonts, spacing and every
"how it looks" question become Copyist settings instead of another
program's style sheet.
"""
import os
import re
import zlib

# ------------------------------------------------------------ geometry

SP = 5.0                    # spatium: half the gap ladder of everything
STAFF = 4 * SP              # five lines
PAGE_W, PAGE_H = 612, 792   # letter, points
MARGIN = 46
SYS_GAP = 13 * SP           # lyrics below one staff, headers above the next
TITLE_H = 70

STEPS = {'C': 0, 'D': 1, 'E': 2, 'F': 3, 'G': 4, 'A': 5, 'B': 6}

# staff position (line/space index from bottom line, in half-spaces) of
# middle C for each clef
CLEF_C4 = {'G': -2, 'F': 10, 'C': 4, 'percussion': -2}

DUR_HEADS = {'whole': 'open', 'half': 'open'}
FLAGS = {'eighth': 1, '16th': 2, '32nd': 3, '64th': 4}
TYPE_ORDER = ['whole', 'half', 'quarter', 'eighth', '16th', '32nd', '64th']


def step_pos(step, octave, clef):
    """Vertical position in half-spaces above the bottom line."""
    return CLEF_C4.get(clef, -2) + (octave - 4) * 7 + STEPS[step]


# ------------------------------------------------------------ pdf bones


class Pdf:
    """A hand-rolled multi-page PDF: standard fonts, path graphics."""

    FONTS = {'H': 'Helvetica', 'HB': 'Helvetica-Bold',
             'HO': 'Helvetica-Oblique', 'TI': 'Times-Italic',
             'TB': 'Times-Bold', 'TBI': 'Times-BoldItalic'}

    def __init__(self):
        self.pages = []
        self.buf = []

    def new_page(self):
        if self.buf:
            self.pages.append("".join(self.buf))
        self.buf = []

    def _w(self, s):
        self.buf.append(s + "\n")

    def line(self, x1, y1, x2, y2, w=1.0):
        self._w(f"{w:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def poly(self, pts, close=True, fill=True, w=1.0):
        ops = [f"{pts[0][0]:.2f} {pts[0][1]:.2f} m"]
        for x, y in pts[1:]:
            ops.append(f"{x:.2f} {y:.2f} l")
        ops.append("f" if fill else ("s" if close else "S"))
        self._w(f"{w:.2f} w " + " ".join(ops))

    def bez(self, segs, fill=False, w=1.1):
        """segs: [(x, y), (c1, c2, end), ...] — a path of curves."""
        x, y = segs[0]
        ops = [f"{x:.2f} {y:.2f} m"]
        for c1, c2, e in segs[1:]:
            ops.append(f"{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} "
                       f"{e[0]:.2f} {e[1]:.2f} c")
        ops.append("f" if fill else "S")
        self._w(f"{w:.2f} w " + " ".join(ops))

    def text(self, x, y, s, size=9, font='H', center=False, right=False):
        s = s.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')
        if center or right:
            est = 0.52 * size * len(s)
            x -= est / 2 if center else est
        self._w(f"BT /{'F' + font} {size:.1f} Tf "
                f"{x:.2f} {y:.2f} Td ({s}) Tj ET")
        return x

    def save(self, path):
        self.new_page()
        objs = []

        def add(body):
            objs.append(body)
            return len(objs)

        font_ids = {}
        for tag, name in self.FONTS.items():
            font_ids[tag] = add(f"<< /Type /Font /Subtype /Type1 "
                                f"/BaseFont /{name} >>")
        res = ("<< /Font << "
               + " ".join(f"/F{t} {i} 0 R" for t, i in font_ids.items())
               + " >> >>")
        page_ids = []
        kids_id = len(objs) + 2 * len(self.pages) + 1
        for content in self.pages:
            data = zlib.compress(content.encode('latin-1', 'replace'))
            cid = add(f"<< /Length {len(data)} /Filter /FlateDecode >>"
                      + "\nstream\n" + data.decode('latin-1')
                      + "\nendstream")
            page_ids.append(add(
                f"<< /Type /Page /Parent {kids_id} 0 R "
                f"/MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                f"/Resources {res} /Contents {cid} 0 R >>"))
        pages_id = add("<< /Type /Pages /Kids ["
                       + " ".join(f"{i} 0 R" for i in page_ids)
                       + f"] /Count {len(page_ids)} >>")
        assert pages_id == kids_id
        cat_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
        out = ["%PDF-1.4"]
        offsets = [0]
        pos = len(out[0]) + 1
        for i, body in enumerate(objs, 1):
            obj = f"{i} 0 obj\n{body}\nendobj"
            offsets.append(pos)
            out.append(obj)
            pos += len(obj.encode('latin-1', 'replace')) + 1
        xref = pos
        out.append(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f ")
        for o in offsets[1:]:
            out.append(f"{o:010d} 00000 n ")
        out.append(f"trailer\n<< /Size {len(objs) + 1} "
                   f"/Root {cat_id} 0 R >>\nstartxref\n{xref}\n%%EOF")
        with open(path, 'wb') as f:
            f.write("\n".join(out).encode('latin-1', 'replace'))


# ------------------------------------------------------------ glyphs


def notehead(pdf, x, y, kind='black', scale=1.0, parens=False):
    """An oval head, slightly tilted; open for halves and wholes,
    a parallelogram for slashes."""
    rx, ry = 1.28 * SP * scale, 0.92 * SP * scale
    if kind == 'slash':
        s = SP * scale
        pdf.poly([(x - 0.9 * s, y - s), (x + 0.35 * s, y + s),
                  (x + 0.9 * s, y + s), (x - 0.35 * s, y - s)], fill=True)
        return
    tilt = 0.35 * ry
    segs = [(x - rx, y - tilt),
            ((x - rx, y + ry - tilt), (x - 0.3 * rx, y + ry + tilt * 0.6),
             (x + 0.35 * rx, y + ry * 0.55 + tilt * 0.4)),
            ((x + rx * 1.05, y + ry * 0.1), (x + rx, y - ry + tilt),
             (x + 0.3 * rx, y - ry - tilt * 0.4)),
            ((x - 0.5 * rx, y - ry - tilt * 0.2), (x - rx, y - ry + tilt),
             (x - rx, y - tilt))]
    pdf.bez(segs, fill=(kind == 'black'), w=1.35)
    if kind == 'open' and False:
        pass
    if parens:
        for sx, side in ((x - rx - 2.4, 1), (x + rx + 2.4, -1)):
            pdf.bez([(sx + side * 1.2, y + 1.7 * SP),
                     ((sx - side * 0.8, y + 0.8 * SP),
                      (sx - side * 0.8, y - 0.8 * SP),
                      (sx + side * 1.2, y - 1.7 * SP))], w=0.9)


def draw_flag(pdf, x, y, up, n):
    for i in range(n):
        dy = -i * 2.4 * (1 if up else -1)
        y0 = y + dy
        d = 1 if up else -1
        pdf.bez([(x, y0),
                 ((x + 0.2 * SP, y0 - d * 1.2 * SP),
                  (x + 1.7 * SP, y0 - d * 1.6 * SP),
                  (x + 1.1 * SP, y0 - d * 3.2 * SP)),
                 ((x + 1.5 * SP, y0 - d * 1.9 * SP),
                  (x + 0.4 * SP, y0 - d * 1.5 * SP),
                  (x, y0 - d * 0.9 * SP))], fill=True)


def draw_clef(pdf, x, top, clef):
    mid = top - STAFF / 2
    if clef == 'G':
        b = top - 3 * SP        # the G line
        s = SP
        pdf.bez([(x + 0.4 * s, b + 5.6 * s),
                 ((x - 1.6 * s, b + 4.2 * s), (x - 0.4 * s, b + 2.2 * s),
                  (x + 0.9 * s, b + 1.6 * s)),
                 ((x + 2.4 * s, b + 1.0 * s), (x + 2.6 * s, b - 0.8 * s),
                  (x + 1.1 * s, b - 1.1 * s)),
                 ((x - 0.5 * s, b - 1.4 * s), (x - 0.9 * s, b + 0.4 * s),
                  (x + 0.5 * s, b + 0.7 * s)),
                 ((x + 1.5 * s, b + 0.9 * s), (x + 1.7 * s, b - 0.1 * s),
                  (x + 1.0 * s, b - 0.5 * s))], w=1.6)
        pdf.line(x + 0.4 * SP, b + 5.6 * SP, x + 0.55 * SP, b - 2.6 * SP,
                 w=1.3)
        pdf.bez([(x + 0.55 * SP, b - 2.6 * SP),
                 ((x + 0.5 * SP, b - 3.6 * SP), (x - 1.0 * SP, b - 3.6 * SP),
                  (x - 1.0 * SP, b - 2.7 * SP))], w=1.3)
    elif clef == 'F':
        s = SP
        b = top - SP            # the F line
        pdf.bez([(x - 0.6 * s, b - 2.6 * s),
                 ((x + 1.6 * s, b - 1.2 * s), (x + 1.8 * s, b + 0.8 * s),
                  (x + 0.4 * s, b + 1.0 * s)),
                 ((x - 0.8 * s, b + 1.2 * s), (x - 1.0 * s, b - 0.2 * s),
                  (x - 0.1 * s, b - 0.1 * s))], w=1.7)
        for dy in (0.4, -0.9):
            yy = b + dy * s
            pdf.poly([(x + 2.4 * s, yy), (x + 3.1 * s, yy),
                      (x + 3.1 * s, yy + 0.6 * s),
                      (x + 2.4 * s, yy + 0.6 * s)], fill=True)
    elif clef == 'percussion':
        for dx in (0, 1.5 * SP):
            pdf.poly([(x + dx, mid - SP), (x + dx + 0.8 * SP, mid - SP),
                      (x + dx + 0.8 * SP, mid + SP),
                      (x + dx, mid + SP)], fill=True)
    else:                       # C clef: two bold verticals + curls, plain
        pdf.line(x, top, x, top - STAFF, w=2.4)
        pdf.line(x + 1.2 * SP, top, x + 1.2 * SP, top - STAFF, w=1.0)
        pdf.text(x + 1.6 * SP, mid - 3, "C", size=2.4 * SP, font='TB')


def draw_accidental(pdf, x, y, alter, scale=1.0):
    s = SP * scale
    if alter == 1:              # sharp
        for dx in (-0.45 * s, 0.45 * s):
            pdf.line(x + dx, y - 1.5 * s, x + dx, y + 1.5 * s, w=0.9)
        for dy in (-0.55 * s, 0.55 * s):
            pdf.line(x - s, y + dy - 0.2 * s, x + s, y + dy + 0.2 * s,
                     w=1.8)
    elif alter == -1:           # flat
        pdf.line(x - 0.4 * s, y + 2.4 * s, x - 0.4 * s, y - 0.9 * s, w=1.0)
        pdf.bez([(x - 0.4 * s, y + 0.7 * s),
                 ((x + 1.1 * s, y + 0.9 * s), (x + 1.2 * s, y - 0.2 * s),
                  (x - 0.4 * s, y - 0.9 * s))], w=1.4)
    else:                       # natural
        pdf.line(x - 0.5 * s, y + 1.7 * s, x - 0.5 * s, y - 0.9 * s, w=0.9)
        pdf.line(x + 0.5 * s, y + 0.9 * s, x + 0.5 * s, y - 1.7 * s, w=0.9)
        for dy in (0.55 * s, -0.55 * s):
            pdf.line(x - 0.5 * s, y + dy - 0.15 * s,
                     x + 0.5 * s, y + dy + 0.15 * s, w=1.6)


def draw_rest(pdf, x, top, rtype):
    mid = top - STAFF / 2
    if rtype in ('whole', 'measure'):
        pdf.poly([(x - 1.4 * SP, top - SP), (x + 1.4 * SP, top - SP),
                  (x + 1.4 * SP, top - 1.55 * SP),
                  (x - 1.4 * SP, top - 1.55 * SP)], fill=True)
    elif rtype == 'half':
        pdf.poly([(x - 1.4 * SP, top - 2 * SP + 0.55 * SP),
                  (x + 1.4 * SP, top - 2 * SP + 0.55 * SP),
                  (x + 1.4 * SP, top - 2 * SP),
                  (x - 1.4 * SP, top - 2 * SP)], fill=True)
    elif rtype == 'quarter':
        pdf.bez([(x - 0.5 * SP, mid + 1.9 * SP),
                 ((x + 1.1 * SP, mid + 0.6 * SP),
                  (x - 1.0 * SP, mid + 0.7 * SP),
                  (x + 0.8 * SP, mid - 0.8 * SP)),
                 ((x - 0.9 * SP, mid - 0.4 * SP),
                  (x - 0.2 * SP, mid - 1.9 * SP),
                  (x + 0.7 * SP, mid - 2.0 * SP))], w=2.2)
    else:
        n = FLAGS.get(rtype, 1)
        for i in range(n):
            yy = mid + SP - i * 2 * SP
            pdf.bez([(x + 0.8 * SP, yy + 0.8 * SP),
                     ((x + 0.1 * SP, yy - 0.1 * SP),
                      (x - 0.5 * SP, yy + 0.9 * SP),
                      (x - 0.9 * SP, yy + 0.4 * SP))], w=1.2)
            pdf.bez([(x - 0.9 * SP, yy + 0.4 * SP),
                     ((x - 0.5 * SP, yy + 0.2 * SP),
                      (x - 0.4 * SP, yy + 0.2 * SP),
                      (x - 0.75 * SP, yy + 0.55 * SP))], fill=True)
        pdf.line(x + 0.8 * SP, mid + 1.2 * SP,
                 x - 0.1 * SP - 0.3 * SP * n, mid - 1.4 * SP, w=1.1)


# ------------------------------------------------------------ parsing


class Note:
    __slots__ = ('rest', 'step', 'alter', 'octave', 'dur', 'ntype',
                 'dots', 'chord', 'tie_start', 'tie_stop', 'slur_start',
                 'slur_stop', 'artic', 'slash', 'parens', 'cue', 'lyric',
                 'tmod', 'measure_rest')


def _parse_note(t):
    n = Note()
    n.rest = '<rest' in t
    n.measure_rest = 'rest measure="yes"' in t
    n.chord = '<chord/>' in t
    m = re.search(r'<step>(\w)</step>', t)
    n.step = m.group(1) if m else 'B'
    m = re.search(r'<alter>(-?\d+)</alter>', t)
    n.alter = int(m.group(1)) if m else 0
    m = re.search(r'<octave>(\d+)</octave>', t)
    n.octave = int(m.group(1)) if m else 4
    m = re.search(r'<duration>(\d+)</duration>', t)
    n.dur = int(m.group(1)) if m else 0
    m = re.search(r'<type[^>]*>([\w]+)</type>', t)
    n.ntype = m.group(1) if m else 'quarter'
    n.dots = t.count('<dot/>')
    n.tie_start = '<tied type="start"/>' in t
    n.tie_stop = '<tied type="stop"/>' in t
    n.slur_start = 'slur number="1" type="start"' in t
    n.slur_stop = 'slur number="1" type="stop"' in t
    n.artic = None
    for a in ('strong-accent', 'accent', 'staccato', 'tenuto',
              'falloff', 'doit', 'scoop', 'plop'):
        if f'<{a}/>' in t:
            n.artic = a
            break
    n.slash = '<notehead>slash</notehead>' in t
    n.parens = 'parentheses="yes"' in t
    n.cue = '<cue/>' in t
    m = re.search(r'<lyric><syllabic>(\w+)</syllabic>'
                  r'<text>([^<]*)</text>(<extend/>)?</lyric>', t)
    n.lyric = (m.group(1), m.group(2), bool(m.group(3))) if m else None
    m = re.search(r'<actual-notes>(\d+)</actual-notes>', t)
    n.tmod = int(m.group(1)) if m else None
    return n


REFUSE = ('<staves>', '<backup>', '<grace')


def parse_part(xml, pid):
    """One part of our own document -> measures ready to draw, or a
    sentence naming why this part still needs MuseScore."""
    body = re.search(r'<part id="%s">(.*?)</part>' % pid, xml, re.S)
    body = body.group(1)
    for tag in REFUSE:
        if tag in body:
            what = {'<staves>': 'a grand staff',
                    '<backup>': 'multiple voices',
                    '<grace': 'grace notes'}[tag]
            return None, f"{what} (still MuseScore's for now)"
    measures = []
    state = {'clef': 'G', 'fifths': 0, 'time': (4, 4), 'div': 24}
    for num, m in re.findall(r'<measure [^>]*?number="([^"]+)"[^>]*>(.*?)'
                             r'</measure>', body, re.S):
        meas = {'num': num, 'events': [], 'show': dict(),
                'texts': [], 'chords': [], 'dyn': [], 'metronome': None,
                'rehearsal': None, 'left': None, 'right': None,
                'ending': [], 'multi': 0}
        mm = re.search(r'<multiple-rest>(\d+)</multiple-rest>', m)
        if mm:
            meas['multi'] = int(mm.group(1))
        dv = re.search(r'<divisions>(\d+)</divisions>', m)
        if dv and int(dv.group(1)) != state['div']:
            state['div'] = int(dv.group(1))
        ts = re.search(r'<beats>(\d+)</beats>\s*'
                       r'<beat-type>(\d+)</beat-type>', m)
        if ts:
            new = (int(ts.group(1)), int(ts.group(2)))
            if new != state['time'] or not measures:
                meas['show']['time'] = new
            state['time'] = new
        ky = re.search(r'<fifths>(-?\d+)</fifths>', m)
        if ky:
            state['fifths'] = int(ky.group(1))
            meas['show']['key'] = state['fifths']
        cl = re.search(r'<clef[^>]*><sign>(\w+)</sign>', m)
        if cl:
            state['clef'] = ('percussion' if cl.group(1) == 'percussion'
                             else cl.group(1))
            meas['show']['clef'] = state['clef']
        pos = 0
        for el in re.finditer(r'<note[ >].*?</note>|<forward>.*?</forward>'
                              r'|<direction[ >].*?</direction>'
                              r'|<harmony[^>]*>.*?</harmony>'
                              r'|<barline[^>]*>.*?</barline>', m, re.S):
            t = el.group(0)
            if t.startswith('<forward'):
                pos += int(re.search(r'<duration>(\d+)</duration>',
                                     t).group(1))
                continue
            if t.startswith('<harmony'):
                r = re.search(r'<root-step>(\w)</root-step>', t)
                a = re.search(r'<root-alter>(-?\d+)</root-alter>', t)
                kd = re.search(r'<kind text="([^"]*)"', t)
                off = re.search(r'<offset>(-?\d+)</offset>', t)
                bs = re.search(r'<bass-step>(\w)</bass-step>', t)
                ba = re.search(r'<bass-alter>(-?\d+)</bass-alter>', t)
                if r:
                    sym = r.group(1) + acc_text(a) + (
                        kd.group(1) if kd else '')
                    if bs:
                        sym += "/" + bs.group(1) + acc_text(ba)
                    meas['chords'].append(
                        (pos + (int(off.group(1)) if off else 0), sym))
                continue
            if t.startswith('<barline'):
                left = 'location="left"' in t
                style = re.search(r'<bar-style>([\w-]+)</bar-style>', t)
                rep = re.search(r'<repeat direction="(\w+)"', t)
                end = re.search(r'<ending number="(\d+)" type="(\w+)"', t)
                d = {'style': style.group(1) if style else None,
                     'repeat': rep.group(1) if rep else None}
                if end:
                    meas['ending'].append((int(end.group(1)), end.group(2),
                                           left))
                if d['style'] or d['repeat']:
                    meas['left' if left else 'right'] = d
                continue
            if t.startswith('<direction'):
                rh = re.search(r'<rehearsal[^>]*>([^<]+)</rehearsal>', t)
                if rh:
                    meas['rehearsal'] = rh.group(1)
                w = re.search(r'<words[^>]*>([^<]+)</words>', t)
                if w and 'print-object="no"' not in t:
                    meas['texts'].append((pos, w.group(1)))
                dyn = re.search(r'<dynamics><(\w+)/></dynamics>', t)
                if dyn:
                    off = re.search(r'<offset>(-?\d+)</offset>', t)
                    meas['dyn'].append(
                        (pos + (int(off.group(1)) if off else 0),
                         dyn.group(1)))
                met = re.search(r'<beat-unit>quarter</beat-unit>'
                                r'(<beat-unit-dot/>)?'
                                r'<per-minute>([\d.]+)</per-minute>', t)
                if met:
                    meas['metronome'] = (bool(met.group(1)), met.group(2))
                continue
            n = _parse_note(t)
            if n.chord and meas['events'] and \
                    meas['events'][-1][1] and not meas['events'][-1][1][-1].rest:
                meas['events'][-1][1].append(n)
                continue
            meas['events'].append((pos, [n]))
            pos += n.dur
        meas['state'] = dict(state)
        meas['len'] = pos
        measures.append(meas)
    return measures, None


def acc_text(m):
    if not m:
        return ''
    return {'-1': 'b', '1': '#', '0': ''}.get(m.group(1), '')


# ------------------------------------------------------------ layout


KEY_SHARPS = [8, 5, 9, 6, 3, 7, 4]      # F C G D A E B, treble positions
KEY_FLATS = [4, 7, 3, 6, 2, 5, 1]


def measure_width(meas):
    w = 3.2 * SP
    if meas['multi']:
        return 16 * SP
    if 'clef' in meas['show']:
        w += 7 * SP
    if 'key' in meas['show']:
        w += abs(meas['show']['key']) * 2 * SP + SP
    if 'time' in meas['show']:
        w += 5 * SP
    for pos, notes in meas['events']:
        n = notes[0]
        w += 2.4 * SP + 1.15 * SP * (max(n.dur, 2) ** 0.5)
        if any(x.alter and not x.rest for x in notes):
            w += 1.6 * SP
    return max(w, 12 * SP)


def engrave(xml_path, pdf_path):
    """One of our part documents -> a PDF, or (False, why)."""
    xml = open(xml_path, encoding='utf-8').read()
    pids = re.findall(r'<score-part id="([^"]+)">', xml)
    names = dict(re.findall(r'<score-part id="([^"]+)">.*?<part-name[^>]*>'
                            r'([^<]*)</part-name>', xml, re.S))
    if len(pids) != 1:
        return False, "one part at a time for now — the score page is next"
    measures, why = parse_part(xml, pids[0])
    if measures is None:
        return False, why
    title = re.search(r'<work-title>([^<]*)</work-title>', xml)
    composer = re.search(r'<creator type="composer">([^<]*)</creator>', xml)

    pdf = Pdf()
    top_y = PAGE_H - MARGIN - TITLE_H
    first_page = True

    # skip the hidden bars a multirest already counts
    seq, skip = [], 0
    for meas in measures:
        if skip:
            skip -= 1
            continue
        if meas['multi']:
            skip = meas['multi'] - 1
        seq.append(meas)

    avail = PAGE_W - 2 * MARGIN
    systems, cur, cur_w = [], [], 0.0
    for meas in seq:
        w = measure_width(meas)
        if cur and cur_w + w > avail:
            systems.append(cur)
            cur, cur_w = [], 0.0
        cur.append((meas, w))
        cur_w += w
    if cur:
        systems.append(cur)

    y = top_y
    pdf.text(PAGE_W / 2, PAGE_H - MARGIN - 14,
             title.group(1) if title else '', size=19, font='HB',
             center=True)
    if composer:
        pdf.text(PAGE_W - MARGIN, PAGE_H - MARGIN - 32, composer.group(1),
                 size=9.5, font='H', right=True)
    pname = names.get(pids[0], '')

    for si, system in enumerate(systems):
        need = STAFF + SYS_GAP
        if y - need < MARGIN:
            pdf.new_page()
            y = PAGE_H - MARGIN - 2 * SP
            first_page = False
        top = y
        for i in range(5):
            pdf.line(MARGIN, top - i * SP, PAGE_W - MARGIN, top - i * SP,
                     w=0.7)
        if si == 0:
            pdf.text(MARGIN - 4, top - STAFF / 2 - 3, pname, size=9,
                     font='H', right=True)
        x = MARGIN
        state = system[0][0]['state']
        # every system restates clef and key
        draw_clef(pdf, x + 1.2 * SP, top, state['clef'])
        x += 6.5 * SP
        x = draw_key(pdf, x, top, state['fifths'], state['clef'],
                     system[0][0])
        stretch = (PAGE_W - MARGIN - x) / sum(w for _, w in system)
        if si == len(systems) - 1:
            stretch = min(stretch, 1.15)   # the last system never gapes
        for mi, (meas, w) in enumerate(system):
            x = draw_measure(pdf, meas, x, top, w * stretch,
                             first_in_system=(mi == 0))
        y = top - STAFF - SYS_GAP
    pdf.save(pdf_path)
    return True, None


def draw_key(pdf, x, top, fifths, clef, meas):
    order = KEY_SHARPS if fifths > 0 else KEY_FLATS
    base = {'G': 0, 'F': -2, 'C': -1, 'percussion': None}[
        clef if clef in ('G', 'F', 'C') else 'percussion']
    if base is None or fifths == 0:
        return x + SP
    for i in range(abs(fifths)):
        p = order[i] + base
        yy = top - STAFF + p * SP / 2
        draw_accidental(pdf, x, yy, 1 if fifths > 0 else -1, scale=0.9)
        x += 2 * SP
    return x + SP


def draw_measure(pdf, meas, x0, top, width, first_in_system=False):
    mid = top - STAFF / 2
    x = x0 + 1.2 * SP
    state = meas['state']
    div = state['div']
    num, den = state['time']

    if 'clef' in meas['show'] and not first_in_system:
        draw_clef(pdf, x, top, meas['show']['clef'])
        x += 6 * SP
    if 'time' in meas['show']:
        n, d = meas['show']['time']
        pdf.text(x, top - 1.9 * SP, str(n), size=2.6 * SP, font='TB',
                 center=True)
        pdf.text(x, top - 3.9 * SP, str(d), size=2.6 * SP, font='TB',
                 center=True)
        x += 3.4 * SP

    tx = x0 + 2
    if meas['rehearsal']:
        pdf.text(x0 + 3, top + 4.6 * SP, meas['rehearsal'], size=11,
                 font='HB')
        est = 11 * 0.62 * len(meas['rehearsal']) + 6
        pdf.poly([(x0 - 1, top + 4.2 * SP), (x0 + est, top + 4.2 * SP),
                  (x0 + est, top + 4.6 * SP + 11),
                  (x0 - 1, top + 4.6 * SP + 11)], close=True, fill=False,
                 w=0.9)
        tx = x0 + est + 6
    if meas['metronome']:
        dot, per = meas['metronome']
        notehead(pdf, tx + SP, top + 5.2 * SP, 'black', scale=0.5)
        pdf.line(tx + 1.6 * SP, top + 5.2 * SP, tx + 1.6 * SP,
                 top + 6.8 * SP, w=0.8)
        pdf.text(tx + 2.2 * SP, top + 4.8 * SP,
                 ("." if dot else "") + " = " + per, size=8.5, font='HB')
        tx += 2.2 * SP + 8.5 * 0.55 * (len(per) + 4)
    ty = top + 4.8 * SP
    for pos, words in meas['texts']:
        frac = pos / max(meas['len'], 1)
        wx = x + frac * (x0 + width - x - 2 * SP)
        pdf.text(max(wx, tx), ty, words, size=8.5, font='HO')
        tx = max(wx, tx) + 8.5 * 0.55 * len(words) + 6

    if (meas.get('left') or {}).get('repeat') == 'forward':
        x += 2.4 * SP
    if meas['multi']:
        pdf.line(x + SP, mid, x0 + width - 2 * SP, mid, w=4.5)
        for xx in (x + SP, x0 + width - 2 * SP):
            pdf.line(xx, mid - 1.2 * SP, xx, mid + 1.2 * SP, w=1.2)
        pdf.text((x + x0 + width) / 2, top + 1.2 * SP,
                 str(meas['multi']), size=12, font='HB', center=True)
        draw_barline(pdf, meas, x0, top, width)
        draw_measure_number(pdf, meas, x0, top)
        return x0 + width

    span = max(x0 + width - x - 2.2 * SP, 4 * SP)
    total = max(meas['len'], 1)

    def xat(pos, extra=0.0):
        return x + 1.2 * SP + (pos / total) * (span - 2.4 * SP) + extra

    # chord symbols above
    for pos, sym in meas['chords']:
        draw_chord_symbol(pdf, xat(pos), top + 1.5 * SP, sym)
    for pos, mark in meas['dyn']:
        pdf.text(xat(pos), top - STAFF - 2.6 * SP, mark, size=11,
                 font='TBI')

    # notes — beams grouped per beat
    beat_len = div * 4 // den
    pend_beam = []
    slur_open = []
    drawn = []
    events = meas['events']
    for ei, (pos, notes) in enumerate(events):
        n0 = notes[0]
        cx = xat(pos)
        if n0.rest:
            flush_beam(pdf, pend_beam)
            pend_beam = []
            if not n0.measure_rest or True:
                draw_rest(pdf, cx,
                          top, 'measure' if n0.measure_rest else n0.ntype)
                dot_x = cx + 1.6 * SP
                for _ in range(n0.dots):
                    pdf.text(dot_x, mid, ".", size=11, font='HB')
                    dot_x += 3
            continue
        scale = 0.68 if n0.cue else 1.0
        ps = [step_pos(n.step, n.octave, state['clef']) for n in notes]
        ys = [top - STAFF + p * SP / 2 for p in ps]
        up = (sum(ps) / len(ps)) < 4
        # ledger lines
        for p, yy in zip(ps, ys):
            if p < -1:
                for lp in range(-2, p - 1, -2):
                    pdf.line(cx - 1.9 * SP, top - STAFF + lp * SP / 2,
                             cx + 1.9 * SP, top - STAFF + lp * SP / 2,
                             w=0.8)
            if p > 9:
                for lp in range(10, p + 1, 2):
                    pdf.line(cx - 1.9 * SP, top - STAFF + lp * SP / 2,
                             cx + 1.9 * SP, top - STAFF + lp * SP / 2,
                             w=0.8)
        ax = cx - 2.1 * SP
        for n, yy in zip(notes, ys):
            if n.alter or (state['fifths'] and False):
                if n.alter:
                    draw_accidental(pdf, ax, yy, n.alter, scale=scale)
                    ax -= 1.7 * SP
        head = ('slash' if n0.slash else
                DUR_HEADS.get(n0.ntype, 'black'))
        for n, yy in zip(notes, ys):
            notehead(pdf, cx, yy, head, scale=scale, parens=n.parens)
        dot_x = cx + 1.9 * SP
        for _ in range(n0.dots):
            for yy in ys:
                pdf.text(dot_x, yy - 1, ".", size=11, font='HB')
            dot_x += 3
        # stem
        stem_x = cx + (1.15 * SP if up else -1.15 * SP) * scale
        if n0.ntype != 'whole' and not n0.slash or (n0.slash and False):
            lo, hi = min(ys), max(ys)
            tip = (hi + 3.4 * SP * scale) if up else (lo - 3.4 * SP * scale)
            pdf.line(stem_x, (lo if up else hi), stem_x, tip,
                     w=1.1 * scale)
        else:
            tip = max(ys) if up else min(ys)
        if n0.slash and n0.ntype != 'whole':
            lo, hi = min(ys), max(ys)
            tip = (hi + 3.2 * SP) if up else (lo - 3.2 * SP)
            pdf.line(stem_x, (lo if up else hi), stem_x, tip, w=1.1)
        nflags = FLAGS.get(n0.ntype, 0)
        if nflags:
            same_beat = [e for e in events
                         if e[0] // beat_len == pos // beat_len
                         and not e[1][0].rest
                         and FLAGS.get(e[1][0].ntype, 0)]
            if len(same_beat) > 1:
                pend_beam.append((stem_x, tip, up, nflags))
                if pos == max(e[0] for e in same_beat):
                    flush_beam(pdf, pend_beam)
                    pend_beam = []
            else:
                draw_flag(pdf, stem_x, tip, up, nflags)
        else:
            flush_beam(pdf, pend_beam)
            pend_beam = []
        # articulation
        if n0.artic:
            if n0.artic in ('strong-accent', 'accent'):
                # accents read above the staff, whatever the stem does
                ay = max(top + 0.6 * SP, max(ys) + 1.8 * SP)
            else:
                ay = (min(ys) - 2.2 * SP) if up else (max(ys) + 1.6 * SP)
            draw_artic(pdf, cx, ay, n0.artic)
        # ties and slurs
        if n0.tie_stop or n0.slur_stop:
            if slur_open:
                sx, sy, sup = slur_open.pop()
                ey = (max(ys) if sup else min(ys))
                arc = 2.2 * SP * (1 if sup else -1)
                mx_ = (sx + cx) / 2
                pdf.bez([(sx, sy + 0.6 * arc / 2.2),
                         ((mx_, sy + arc), (mx_, ey + arc),
                          (cx, ey + 0.6 * arc / 2.2))], w=1.1)
        if n0.tie_start or n0.slur_start:
            sup = not up
            slur_open.append((cx + SP,
                              (max(ys) if sup else min(ys)), sup))
        # lyric
        if n0.lyric:
            syl, txt, ext = n0.lyric
            shown = txt + ("" if syl in ('single', 'end') else " -")
            lx = pdf.text(cx, top - STAFF - 4.6 * SP, shown, size=8.5,
                          font='H', center=True)
            if ext:
                pdf.line(lx + 0.55 * 8.5 * len(shown) + 2,
                         top - STAFF - 4.6 * SP,
                         xat(pos + n0.dur * 0.9),
                         top - STAFF - 4.6 * SP, w=0.8)
        # tuplet number
        if n0.tmod and (not drawn or drawn[-1] != pos // beat_len):
            pdf.text(xat(pos + beat_len / 2 - n0.dur / 2),
                     (tip + (1.6 * SP if up else -2.6 * SP)),
                     str(n0.tmod), size=8, font='HO', center=True)
            drawn.append(pos // beat_len)
    flush_beam(pdf, pend_beam)
    # an open slur at the barline carries to... close at bar end
    while slur_open:
        sx, sy, sup = slur_open.pop()
        arc = 2 * SP * (1 if sup else -1)
        pdf.bez([(sx, sy), ((sx + 3 * SP, sy + arc),
                            (x0 + width - SP, sy + arc),
                            (x0 + width - 0.5 * SP, sy))], w=1.1)

    draw_barline(pdf, meas, x0, top, width)
    draw_ending(pdf, meas, x0, top, width)
    draw_measure_number(pdf, meas, x0, top)
    return x0 + width


def _dot(pdf, x, y):
    r = 1.6
    pdf.bez([(x - r, y),
             ((x - r, y + 1.35 * r), (x + r, y + 1.35 * r), (x + r, y)),
             ((x + r, y - 1.35 * r), (x - r, y - 1.35 * r), (x - r, y))],
            fill=True)


def draw_measure_number(pdf, meas, x0, top):
    if meas['num'].isdigit() and meas['num'] != '1' \
            and not meas['rehearsal']:
        pdf.text(x0 + 1, top + 0.9 * SP, meas['num'], size=6.5, font='HO')


def draw_artic(pdf, x, y, artic):
    if artic == 'staccato':
        pdf.text(x - 1, y, ".", size=12, font='HB')
    elif artic == 'accent':
        pdf.poly([(x - 1.3 * SP, y + 0.9 * SP), (x + 1.3 * SP, y + 0.35 * SP),
                  (x - 1.3 * SP, y - 0.2 * SP)], close=False, fill=False,
                 w=1.3)
    elif artic == 'strong-accent':
        pdf.poly([(x - 1.1 * SP, y), (x, y + 1.5 * SP),
                  (x + 1.1 * SP, y)], close=False, fill=False, w=1.5)
    elif artic == 'tenuto':
        pdf.line(x - 1.2 * SP, y + 0.4 * SP, x + 1.2 * SP, y + 0.4 * SP,
                 w=1.6)
    elif artic in ('falloff', 'doit'):
        d = -1 if artic == 'falloff' else 1
        pdf.bez([(x + SP, y), ((x + 2.4 * SP, y + d * 0.4 * SP),
                               (x + 3.0 * SP, y + d * 1.2 * SP),
                               (x + 3.6 * SP, y + d * 2.4 * SP))], w=1.4)
    elif artic in ('scoop', 'plop'):
        d = 1 if artic == 'scoop' else -1
        pdf.bez([(x - 3.4 * SP, y - d * 2 * SP),
                 ((x - 2.8 * SP, y - d * 0.8 * SP),
                  (x - 2.2 * SP, y - d * 0.3 * SP),
                  (x - 1.4 * SP, y))], w=1.4)


def draw_chord_symbol(pdf, x, y, sym):
    # F7, Bbm7b5, F#7#9, C/E — flats and sharps stay text, bold and clear
    pdf.text(x, y, sym, size=10.5, font='HB')


def flush_beam(pdf, group):
    if len(group) < 2:
        if group:
            x, tip, up, n = group[0]
            draw_flag(pdf, x, tip, up, n)
        return
    up = group[0][2]
    tip = (max if up else min)(g[1] for g in group)
    x1, x2 = group[0][0], group[-1][0]
    levels = max(g[3] for g in group)
    for g in group:                       # stems reach the beam
        pdf.line(g[0], g[1], g[0], tip, w=1.1)
    for i in range(levels):
        yy = tip - i * 2.6 * (1 if up else -1)
        full = [g for g in group if g[3] > i]
        if len(full) == len(group) or i == 0:
            pdf.poly([(x1, yy), (x2, yy), (x2, yy - 2 * (1 if up else -1)),
                      (x1, yy - 2 * (1 if up else -1))], fill=True)
        else:
            for g in full:                # partial 16th beams: short hooks
                pdf.poly([(g[0], yy), (g[0] + 6, yy),
                          (g[0] + 6, yy - 2 * (1 if up else -1)),
                          (g[0], yy - 2 * (1 if up else -1))], fill=True)


def draw_barline(pdf, meas, x0, top, width):
    xr = x0 + width
    right = meas.get('right') or {}
    style = right.get('style')
    if style == 'light-heavy':
        pdf.line(xr - 4, top, xr - 4, top - STAFF, w=0.9)
        pdf.line(xr - 1, top, xr - 1, top - STAFF, w=2.6)
    elif style == 'light-light':
        pdf.line(xr - 4, top, xr - 4, top - STAFF, w=0.9)
        pdf.line(xr - 1, top, xr - 1, top - STAFF, w=0.9)
    else:
        pdf.line(xr - 1, top, xr - 1, top - STAFF, w=0.9)
    if right.get('repeat') == 'backward':
        for dy in (1.5 * SP, 2.5 * SP):
            _dot(pdf, xr - 7.5, top - dy)
    left = meas.get('left') or {}
    if left.get('repeat') == 'forward':
        pdf.line(x0 + 1, top, x0 + 1, top - STAFF, w=2.6)
        pdf.line(x0 + 4.5, top, x0 + 4.5, top - STAFF, w=0.9)
        for dy in (1.5 * SP, 2.5 * SP):
            _dot(pdf, x0 + 8, top - dy)


def draw_ending(pdf, meas, x0, top, width):
    for num, etype, left in meas['ending']:
        yy = top + 3.2 * SP
        if etype == 'start':
            pdf.line(x0 + 2, yy, x0 + 2, yy - 1.6 * SP, w=1.0)
            pdf.line(x0 + 2, yy, x0 + width, yy, w=1.0)
            pdf.text(x0 + 6, yy - 1.4 * SP, str(num), size=8.5, font='HB')
        elif etype == 'stop':
            pdf.line(x0, yy, x0 + width - 1, yy, w=1.0)
            pdf.line(x0 + width - 1, yy, x0 + width - 1, yy - 1.6 * SP,
                     w=1.0)
        else:                              # discontinue: open on the right
            pdf.line(x0, yy, x0 + width - 1, yy, w=1.0)
