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

DUR_HEADS = {'whole': 'whole', 'half': 'half'}
FLAGS = {'eighth': 1, '16th': 2, '32nd': 3, '64th': 4}
TYPE_ORDER = ['whole', 'half', 'quarter', 'eighth', '16th', '32nd', '64th']


def step_pos(step, octave, clef):
    """Vertical position in half-spaces above the bottom line."""
    return CLEF_C4.get(clef, -2) + (octave - 4) * 7 + STEPS[step]


# ------------------------------------------------------------ the font

# SMuFL names -> codepoints. One em is four staff spaces, glyphs are
# registered to their staff lines — the font was designed for exactly
# this use.
SMUFL = {
    'gClef': 0xE050, 'cClef': 0xE05C, 'fClef': 0xE062, 'percClef': 0xE069,
    'flat': 0xE260, 'natural': 0xE261, 'sharp': 0xE262,
    'wholeHead': 0xE0A2, 'halfHead': 0xE0A3, 'blackHead': 0xE0A4,
    'restW': 0xE4E3, 'restH': 0xE4E4, 'restQ': 0xE4E5,
    'rest8': 0xE4E6, 'rest16': 0xE4E7, 'rest32': 0xE4E8,
    'flag8U': 0xE240, 'flag8D': 0xE241,
    'flag16U': 0xE242, 'flag16D': 0xE243,
    'flag32U': 0xE244, 'flag32D': 0xE245,
    'brace': 0xE000, 'dot': 0xE1E7,
    'marcato': 0xE4AC, 'accent': 0xE4A0, 'stacc': 0xE4A2,
    'tenuto': 0xE4A4,
    'dynP': 0xE520, 'dynF': 0xE522, 'dynMP': 0xE52C, 'dynMF': 0xE52D,
    'dynPP': 0xE52B, 'dynFF': 0xE52F, 'dynSFZ': 0xE539, 'dynFP': 0xE534,
}
for _d in range(10):
    SMUFL[f'ts{_d}'] = 0xE080 + _d

import struct


class MusicFont:
    """A SMuFL OpenType font, whole-file embedded: cmap for glyph ids,
    hmtx for widths, the em taken from head."""

    def __init__(self, path):
        self.data = open(path, 'rb').read()
        n = struct.unpack('>H', self.data[4:6])[0]
        self.tables = {}
        for i in range(n):
            off = 12 + 16 * i
            tag = self.data[off:off + 4].decode('latin-1')
            toff, tlen = struct.unpack('>II', self.data[off + 8:off + 16])
            self.tables[tag] = (toff, tlen)
        h = self.tables['head'][0]
        self.upem = struct.unpack('>H', self.data[h + 18:h + 20])[0]
        self.cmap = self._cmap()
        self.adv = self._hmtx()
        self.gids = {name: self.cmap.get(cp)
                     for name, cp in SMUFL.items()}

    def _cmap(self):
        data = self.data
        off, _ = self.tables['cmap']
        n = struct.unpack('>H', data[off + 2:off + 4])[0]
        best = None
        for i in range(n):
            pid, eid, sub = struct.unpack(
                '>HHI', data[off + 4 + 8 * i:off + 12 + 8 * i])
            fmt = struct.unpack('>H', data[off + sub:off + sub + 2])[0]
            if fmt in (4, 12):
                best = (fmt, off + sub)
                if fmt == 12:
                    break
        cmap = {}
        fmt, s = best
        if fmt == 12:
            ngroups = struct.unpack('>I', data[s + 12:s + 16])[0]
            for g in range(ngroups):
                a, b, gid = struct.unpack(
                    '>III', data[s + 16 + 12 * g:s + 28 + 12 * g])
                for cp in range(a, b + 1):
                    cmap[cp] = gid + (cp - a)
        else:
            segx2 = struct.unpack('>H', data[s + 6:s + 8])[0]
            segs = segx2 // 2
            ends = struct.unpack(f'>{segs}H', data[s + 14:s + 14 + segx2])
            starts = struct.unpack(
                f'>{segs}H', data[s + 16 + segx2:s + 16 + 2 * segx2])
            deltas = struct.unpack(
                f'>{segs}h', data[s + 16 + 2 * segx2:s + 16 + 3 * segx2])
            rpos = s + 16 + 3 * segx2
            rngs = struct.unpack(f'>{segs}H', data[rpos:rpos + segx2])
            for i in range(segs):
                for cp in range(starts[i], min(ends[i], 0xFFFF) + 1):
                    if rngs[i] == 0:
                        gid = (cp + deltas[i]) & 0xFFFF
                    else:
                        ga = rpos + 2 * i + rngs[i] + 2 * (cp - starts[i])
                        gid = struct.unpack('>H', data[ga:ga + 2])[0]
                        if gid:
                            gid = (gid + deltas[i]) & 0xFFFF
                    if gid:
                        cmap[cp] = gid
        return cmap

    def _hmtx(self):
        hh = self.tables['hhea'][0]
        nm = struct.unpack('>H', self.data[hh + 34:hh + 36])[0]
        off = self.tables['hmtx'][0]
        return [struct.unpack('>H', self.data[off + 4 * i:off + 4 * i + 2])[0]
                for i in range(nm)]

    def width(self, name, size):
        gid = self.gids.get(name)
        if gid is None:
            return 0
        adv = self.adv[gid] if gid < len(self.adv) else self.adv[-1]
        return adv * size / self.upem


_FONT_CACHE = {}


def load_font(fname):
    """An OTF by file name, from the repo's fonts/ first, else the
    MuseScore bundle; None means the fallback carries on."""
    if fname in _FONT_CACHE:
        return _FONT_CACHE[fname]
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, '..', 'fonts', fname),
              '/Applications/MuseScore 4.app/Contents/Resources/fonts/'
              + fname):
        if os.path.exists(p):
            try:
                _FONT_CACHE[fname] = MusicFont(p)
            except Exception:
                _FONT_CACHE[fname] = None
            return _FONT_CACHE[fname]
    _FONT_CACHE[fname] = None
    return None


def music_font():
    return load_font('Leland.otf')


# every look dresses the words in its own hand: Edwin is Leland's
# own text companion (the default and the engraved look), MuseJazz
# Text is the classic jazz chart hand, Petaluma Script the looser
# handwritten one. 'plain' keeps the built-in Helvetica.
FACE_FAMILIES = {
    'edwin': ('Edwin-Roman.otf', 'Edwin-Bold.otf', 'Edwin-Italic.otf'),
    'jazz': ('MuseJazzText.otf',) * 3,
    'handwritten': ('PetalumaScript.otf',) * 3,
}


def text_faces(look):
    words = (look or '').lower()
    if 'plain' in words:
        return {}
    fam = 'edwin'
    if 'jazz' in words:
        fam = 'jazz'
    if 'handwritten' in words:
        fam = 'handwritten'
    reg, bold, ital = FACE_FAMILIES[fam]
    faces = {}
    for tag, fn in (('H', reg), ('HB', bold), ('HO', ital),
                    ('TB', bold), ('TBI', ital)):
        f = load_font(fn)
        if f:
            faces[tag] = f
    return faces


# ------------------------------------------------------------ pdf bones


class Pdf:
    """A hand-rolled multi-page PDF: standard fonts, path graphics."""

    FONTS = {'H': 'Helvetica', 'HB': 'Helvetica-Bold',
             'HO': 'Helvetica-Oblique', 'TI': 'Times-Italic',
             'TB': 'Times-Bold', 'TBI': 'Times-BoldItalic'}

    def __init__(self, scale=1.0, music=None, faces=None):
        self.pages = []
        self.buf = []
        self.scale = scale
        self.music = music
        self.faces = faces or {}
        self.face_res = {}          # font object -> /FE<n> resource
        for f in self.faces.values():
            if id(f) not in self.face_res:
                self.face_res[id(f)] = f"FE{len(self.face_res)}"

    def tw(self, s, size, font='H'):
        """The real width of s in the embedded face, or the built-in
        estimate."""
        face = self.faces.get(font)
        if face:
            return sum(face.adv[min(face.cmap.get(ord(c), 0),
                                    len(face.adv) - 1)]
                       for c in s) * size / face.upem
        return 0.52 * size * len(s)

    def glyph(self, x, y, name, size):
        """One SMuFL glyph at its registration point. True if drawn."""
        gid = self.music.gids.get(name) if self.music else None
        if gid is None:
            return False
        self._w(f"BT /FM {size:.2f} Tf {x:.2f} {y:.2f} Td "
                f"<{gid:04X}> Tj ET")
        return True

    def gw(self, name, size):
        return self.music.width(name, size) if self.music else 0

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
        face = self.faces.get(font)
        if center or right:
            est = self.tw(s, size, font)
            x -= est / 2 if center else est
        if face:
            gids = "".join(f"{face.cmap.get(ord(c), 0):04X}" for c in s)
            self._w(f"BT /{self.face_res[id(face)]} {size:.1f} Tf "
                    f"{x:.2f} {y:.2f} Td <{gids}> Tj ET")
            return x
        s = s.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')
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
        def embed_otf(font, psname):
            fdata = zlib.compress(font.data)
            ff = add(f"<< /Length {len(fdata)} /Filter /FlateDecode "
                     "/Subtype /OpenType >>\nstream\n"
                     + fdata.decode('latin-1') + "\nendstream")
            fd = add(f"<< /Type /FontDescriptor /FontName /{psname} "
                     "/Flags 4 /FontBBox [-1000 -1200 3000 1500] "
                     "/ItalicAngle 0 /Ascent 1000 /Descent -300 "
                     "/CapHeight 800 /StemV 50 "
                     f"/FontFile3 {ff} 0 R >>")
            # glyph advances, 1000/em — text is unreadable without
            ws = " ".join(str(round(a * 1000 / font.upem))
                          for a in font.adv)
            cid = add(f"<< /Type /Font /Subtype /CIDFontType0 "
                      f"/BaseFont /{psname} /CIDSystemInfo "
                      "<< /Registry (Adobe) /Ordering (Identity) "
                      "/Supplement 0 >> "
                      f"/FontDescriptor {fd} 0 R "
                      f"/DW {round(font.adv[-1] * 1000 / font.upem)} "
                      f"/W [0 [{ws}]] >>")
            return add(f"<< /Type /Font /Subtype /Type0 "
                       f"/BaseFont /{psname} /Encoding /Identity-H "
                       f"/DescendantFonts [{cid} 0 R] >>")

        face_refs = ""
        seen = {}
        for f in self.faces.values():
            if id(f) in seen:
                continue
            seen[id(f)] = embed_otf(f, f"Face{len(seen)}")
            face_refs += f" /{self.face_res[id(f)]} {seen[id(f)]} 0 R"
        music_ref = ""
        if self.music:
            music_ref = (" /FM "
                         + str(embed_otf(self.music, 'Leland'))
                         + " 0 R")
        res = ("<< /Font << "
               + " ".join(f"/F{t} {i} 0 R" for t, i in font_ids.items())
               + music_ref + face_refs + " >> >>")
        page_ids = []
        kids_id = len(objs) + 2 * len(self.pages) + 1
        for content in self.pages:
            if self.scale != 1.0:
                content = (f"q {self.scale:.4f} 0 0 {self.scale:.4f} "
                           "0 0 cm\n" + content + "Q\n")
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
    """An oval head — Leland's when the font is here, our bezier when
    not; a parallelogram for slashes either way."""
    rx, ry = 1.28 * SP * scale, 0.92 * SP * scale
    if kind != 'slash' and pdf.music:
        name = {'black': 'blackHead', 'half': 'halfHead',
                'whole': 'wholeHead'}.get(kind, 'blackHead')
        size = 4 * SP * scale
        hw = pdf.gw(name, size)
        if pdf.glyph(x - hw / 2, y, name, size):
            if parens:
                for sx, side in ((x - hw / 2 - 2.4, 1),
                                 (x + hw / 2 + 2.4, -1)):
                    pdf.bez([(sx + side * 1.2, y + 1.7 * SP),
                             ((sx - side * 0.8, y + 0.8 * SP),
                              (sx - side * 0.8, y - 0.8 * SP),
                              (sx + side * 1.2, y - 1.7 * SP))], w=0.9)
            return
    if kind in ('open', 'half', 'whole'):
        kind = 'open'
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
    if pdf.music:
        name = {1: 'flag8', 2: 'flag16', 3: 'flag32'}.get(min(n, 3))
        if name and pdf.glyph(x, y, name + ('U' if up else 'D'), 4 * SP):
            return
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
    if pdf.music:
        name, yy = {'G': ('gClef', top - 3 * SP),
                    'F': ('fClef', top - SP),
                    'C': ('cClef', mid),
                    'percussion': ('percClef', mid)}.get(
            clef, ('gClef', top - 3 * SP))
        if name and pdf.glyph(x - SP, yy, name, 4 * SP):
            return
    if clef == 'C':                     # plain alto clef: bars + wings
        pdf.line(x - SP, top, x - SP, top - STAFF, w=2.4)
        pdf.line(x + 0.1 * SP, top, x + 0.1 * SP, top - STAFF, w=0.9)
        for d in (1, -1):
            pdf.bez([(x + 0.3 * SP, mid),
                     ((x + 1.7 * SP, mid + d * 0.4 * SP),
                      (x + 1.7 * SP, mid + d * 1.8 * SP),
                      (x + 0.5 * SP, mid + d * 1.8 * SP))], w=1.3)
        return
    if clef == 'G':
        g = top - 3 * SP            # the G line
        s = SP
        # the spiral, wound onto the G line
        pdf.bez([(x + 1.55 * s, g + 1.55 * s),
                 ((x + 0.6 * s, g + 2.6 * s), (x - 1.5 * s, g + 1.9 * s),
                  (x - 1.5 * s, g + 0.4 * s)),
                 ((x - 1.5 * s, g - 1.1 * s), (x - 0.4 * s, g - 1.85 * s),
                  (x + 0.5 * s, g - 1.55 * s)),
                 ((x + 1.5 * s, g - 1.2 * s), (x + 1.6 * s, g + 0.3 * s),
                  (x + 0.65 * s, g + 0.7 * s)),
                 ((x - 0.1 * s, g + 1.0 * s), (x - 0.5 * s, g + 0.4 * s),
                  (x - 0.35 * s, g - 0.1 * s))], w=2.1)
        # the tall loop above, lean and closing back across the stem
        pdf.bez([(x + 1.55 * s, g + 1.55 * s),
                 ((x + 0.1 * s, g + 3.2 * s), (x - 0.6 * s, g + 4.4 * s),
                  (x - 0.45 * s, g + 5.6 * s)),
                 ((x - 0.35 * s, g + 6.6 * s), (x + 0.5 * s, g + 6.7 * s),
                  (x + 0.55 * s, g + 5.5 * s)),
                 ((x + 0.6 * s, g + 4.0 * s), (x + 0.0 * s, g + 2.4 * s),
                  (x - 0.45 * s, g + 1.2 * s))], w=1.9)
        # the stem falls straight through to the tail
        pdf.line(x + 0.02 * s, g + 5.6 * s, x + 0.32 * s, g - 2.5 * s,
                 w=1.5)
        pdf.bez([(x + 0.32 * s, g - 2.5 * s),
                 ((x + 0.3 * s, g - 3.3 * s), (x - 0.9 * s, g - 3.4 * s),
                  (x - 1.0 * s, g - 2.6 * s))], w=1.4)
        _dot(pdf, x - 0.72 * s, g - 2.65 * s)
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
    if pdf.music:
        name = {1: 'sharp', -1: 'flat', 0: 'natural'}[alter]
        size = 4 * SP * scale
        if pdf.glyph(x - pdf.gw(name, size) * 0.6, y, name, size):
            return
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
    if pdf.music:
        name, yy = {'whole': ('restW', top - SP),
                    'measure': ('restW', top - SP),
                    'half': ('restH', top - 2 * SP),
                    'quarter': ('restQ', mid), 'eighth': ('rest8', mid),
                    '16th': ('rest16', mid), '32nd': ('rest32', mid),
                    '64th': ('rest32', mid)}.get(rtype, ('restQ', mid))
        if pdf.glyph(x - pdf.gw(name, 4 * SP) / 2, yy, name, 4 * SP):
            return
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
        pdf.bez([(x - 0.45 * SP, mid + 1.9 * SP),
                 ((x + 0.55 * SP, mid + 1.0 * SP),
                  (x + 0.6 * SP, mid + 0.9 * SP),
                  (x - 0.35 * SP, mid - 0.05 * SP))], w=2.6)
        pdf.bez([(x - 0.35 * SP, mid - 0.05 * SP),
                 ((x + 0.75 * SP, mid - 0.7 * SP),
                  (x + 0.8 * SP, mid - 0.75 * SP),
                  (x + 0.5 * SP, mid - 1.0 * SP))], w=2.2)
        pdf.bez([(x + 0.5 * SP, mid - 1.0 * SP),
                 ((x - 0.6 * SP, mid - 1.15 * SP),
                  (x - 0.5 * SP, mid - 1.9 * SP),
                  (x + 0.35 * SP, mid - 2.05 * SP))], w=1.5)
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


REFUSE = ('<grace',)


def parse_part(xml, pid):
    """One part of our own document -> measures ready to draw, or a
    sentence naming why this part still needs MuseScore."""
    body = re.search(r'<part id="%s">(.*?)</part>' % pid, xml, re.S)
    body = body.group(1)
    for tag in REFUSE:
        if tag in body:
            what = {'<grace': 'grace notes'}[tag]
            return None, f"{what} (still MuseScore's for now)"
    measures = []
    state = {'clefs': {1: 'G'}, 'staves': 1, 'fifths': 0,
             'time': (4, 4), 'div': 24}
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
        sv = re.search(r'<staves>(\d+)</staves>', m)
        if sv:
            state['staves'] = int(sv.group(1))
        for cnum, sign in re.findall(
                r'<clef(?: number="(\d+)")?><sign>(\w+)</sign>', m):
            state['clefs'][int(cnum or 1)] = (
                'percussion' if sign == 'percussion' else sign)
            meas['show']['clef'] = dict(state['clefs'])
        pos = 0
        hi_pos = 0
        for el in re.finditer(r'<note[ >].*?</note>|<forward>.*?</forward>'
                              r'|<backup>.*?</backup>'
                              r'|<direction[ >].*?</direction>'
                              r'|<harmony[^>]*>.*?</harmony>'
                              r'|<barline[^>]*>.*?</barline>', m, re.S):
            t = el.group(0)
            if t.startswith('<forward'):
                pos += int(re.search(r'<duration>(\d+)</duration>',
                                     t).group(1))
                continue
            if t.startswith('<backup'):
                pos -= int(re.search(r'<duration>(\d+)</duration>',
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
            sv = re.search(r'<staff>(\d+)</staff>', t)
            n_staff = int(sv.group(1)) if sv else 1
            vv = re.search(r'<voice>(\d+)</voice>', t)
            n_voice = int(vv.group(1)) if vv else 1
            if n.chord:
                for p2, ns2, st2, vo2 in reversed(meas['events']):
                    if st2 == n_staff and vo2 == n_voice and \
                            not ns2[-1].rest:
                        ns2.append(n)
                        break
                continue
            meas['events'].append((pos, [n], n_staff, n_voice))
            pos += n.dur
            hi_pos = max(hi_pos, pos)
        meas['state'] = {'clefs': dict(state['clefs']),
                         'staves': state['staves'],
                         'fifths': state['fifths'],
                         'time': state['time'], 'div': state['div']}
        meas['len'] = hi_pos
        measures.append(meas)
    return measures, None


def acc_text(m):
    if not m:
        return ''
    return {'-1': 'b', '1': '#', '0': ''}.get(m.group(1), '')


# ------------------------------------------------------------ layout


KEY_SHARPS = [8, 5, 9, 6, 3, 7, 4]      # F C G D A E B, treble positions
KEY_FLATS = [4, 7, 3, 6, 2, 5, 1]


INK_GAP = 0.65 * SP     # air an engraver leaves between one onset's
                        # ink and the next, beyond the rhythm's share


def ink_needs(meas):
    """pos -> (left, right): how far each onset's ink actually reaches
    either side of its center — accidental columns, offset seconds,
    dots, flags, scoops. Optical spacing keeps neighbours at least
    this far apart, whatever the rhythm says."""
    needs = {}
    for pos, notes, staff, voice in meas['events']:
        n0 = notes[0]
        s = 0.68 if n0.cue else 1.0
        if n0.rest:
            l, r = 1.5 * SP, 1.5 * SP
        else:
            l = r = 1.35 * SP * s
            naccs = sum(1 for n in notes if n.alter)
            if naccs:
                l = max(l, (2.1 + 1.7 * (naccs - 1) + 1.7) * SP)
            # seconds flip a head across the stem; count them the way
            # draw_stream will (intervals only, so any clef serves)
            ps = sorted(step_pos(n.step, n.octave, 'G') for n in notes)
            if any(b - a == 1 for a, b in zip(ps, ps[1:])):
                r += 2.15 * SP * s
            if FLAGS.get(n0.ntype, 0):
                r = max(r, 2.5 * SP * s)
        if n0.dots:
            r = max(r, (1.9 + 0.7 * n0.dots) * SP)
        if n0.artic in ('scoop', 'plop'):
            l += 3.6 * SP
        elif n0.artic in ('falloff', 'doit'):
            r = max(r, 3.8 * SP)
        pl, pr = needs.get(pos, (0.0, 0.0))
        needs[pos] = (max(pl, l), max(pr, r))
    return needs


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
    per = {}
    for pos, notes, staff, voice in meas['events']:
        n = notes[0]
        per[(staff, voice)] = per.get((staff, voice), 0) + (
            2.4 * SP + 1.15 * SP * (max(n.dur, 2) ** 0.5)
            + (1.6 * SP if any(x.alter and not x.rest
                               for x in notes) else 0))
    # the optical floor: every onset's ink plus the gap, end to end
    opt = sum(l + r + INK_GAP for l, r in ink_needs(meas).values())
    # chord symbols need their letters' room too — two changes in an
    # empty bar must not print on top of each other
    cw = sum(6.2 * len(s) + 8 for _, s in meas['chords'])
    return max(w + max(per.values(), default=0), w + opt + 2 * SP,
               w + cw, 12 * SP)


def engrave(xml_path, pdf_path, look=None):
    """One of our documents -> a PDF, or (False, why). A single part
    gets the part treatment; several parts get the conductor score.
    `look` picks the text hand (jazz, handwritten, engraved, plain)."""
    xml = open(xml_path, encoding='utf-8').read()
    pids = re.findall(r'<score-part id="([^"]+)">', xml)
    names = dict(re.findall(r'<score-part id="([^"]+)">.*?<part-name[^>]*>'
                            r'([^<]*)</part-name>', xml, re.S))
    if len(pids) != 1:
        return engrave_score(xml, pids, names, pdf_path, look=look)
    measures, why = parse_part(xml, pids[0])
    if measures is None:
        return False, why
    title = re.search(r'<work-title>([^<]*)</work-title>', xml)
    composer = re.search(r'<creator type="composer">([^<]*)</creator>', xml)

    pdf = Pdf(music=music_font(), faces=text_faces(look))
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
    carry = {}
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
    staves = measures[0]['state']['staves'] if measures else 1
    ph = part_height(staves)

    for si, system in enumerate(systems):
        if y - (ph + SYS_GAP) < MARGIN - SYS_GAP:
            pdf.new_page()
            y = PAGE_H - MARGIN - 2 * SP
            first_page = False
        tops = staff_tops(y, staves)
        for stop in tops:
            for i in range(5):
                pdf.line(MARGIN, stop - i * SP, PAGE_W - MARGIN,
                         stop - i * SP, w=0.7)
        if staves > 1:
            draw_brace(pdf, MARGIN - 2, tops[0], tops[-1] - STAFF)
            pdf.line(MARGIN, tops[0], MARGIN, tops[-1] - STAFF, w=1.2)
        if si == 0:
            pdf.text(MARGIN - (14 if staves > 1 else 4),
                     (tops[0] + tops[-1] - STAFF) / 2 - 3, pname, size=9,
                     font='H', right=True)
        x = MARGIN
        state = system[0][0]['state']
        xk = x
        for st, stop in enumerate(tops, 1):
            draw_clef(pdf, x + 1.2 * SP, stop, state['clefs'].get(st, 'G'))
            xk = max(xk, draw_key(pdf, x + 6.5 * SP, stop,
                                  state['fifths'],
                                  state['clefs'].get(st, 'G'),
                                  system[0][0]))
        x = xk
        stretch = (PAGE_W - MARGIN - x) / sum(w for _, w in system)
        if si == len(systems) - 1:
            stretch = min(stretch, 1.15)   # the last system never gapes
        for mi, (meas, w) in enumerate(system):
            x = draw_measure(pdf, meas, x, tops, w * stretch,
                             first_in_system=(mi == 0), carry=carry)
        drain_ties(pdf, carry, PAGE_W - MARGIN - 0.5 * SP)
        y = tops[-1] - STAFF - SYS_GAP
    pdf.save(pdf_path)
    return True, None


# ------------------------------------------------------------ the score

SCORE_GAP = 9 * SP          # between one part's staff and the next
SYS_HEAD = 7 * SP           # the top part's header band


def engrave_score(xml, pids, names, pdf_path, look=None):
    """Every part, stacked and synchronized — the conductor's page,
    drawn at score size: the whole layout happens on a virtual page and
    one PDF transform shrinks it, the way real scores drop the staff
    size rather than the music."""
    parts = []
    for pid in pids:
        measures, why = parse_part(xml, pid)
        if measures is None:
            return False, f"{names.get(pid, pid)} needs {why}"
        staves = measures[0]['state']['staves'] if measures else 1
        parts.append((names.get(pid, pid), measures, staves))
    counts = {len(m) for _, m, _ in parts}
    if len(counts) != 1:
        return False, "parts of different lengths (report that)"
    nmeas = counts.pop()
    title = re.search(r'<work-title>([^<]*)</work-title>', xml)
    composer = re.search(r'<creator type="composer">([^<]*)</creator>', xml)

    widths = [max(measure_width(m[j]) for _, m, _ in parts)
              for j in range(nmeas)]

    sys_h = (sum(part_height(s) for _, _, s in parts)
             + (len(parts) - 1) * SCORE_GAP)
    per_sys = sys_h + SYS_HEAD + 4 * SP
    want = 2 if len(parts) > 3 else 3
    scale = max(0.38, min(0.75,
                (PAGE_H - 2 * MARGIN - TITLE_H) / (want * per_sys)))
    pdf = Pdf(scale=scale, music=music_font(), faces=text_faces(look))
    W, H, M = PAGE_W / scale, PAGE_H / scale, MARGIN / scale

    pdf.text(W / 2, H - M - 14 / scale,
             title.group(1) if title else '', size=19 / scale, font='HB',
             center=True)
    if composer:
        pdf.text(W - M, H - M - 32 / scale, composer.group(1),
                 size=9.5 / scale, font='H', right=True)
    y = H - M - TITLE_H / scale - SYS_HEAD

    lead_guess = 12 * SP
    carries = [dict() for _ in parts]
    avail = W - 2 * M - lead_guess
    systems, cur, cur_w = [], [], 0.0
    for j in range(nmeas):
        if cur and cur_w + widths[j] > avail:
            systems.append(cur)
            cur, cur_w = [], 0.0
        cur.append(j)
        cur_w += widths[j]
    if cur:
        systems.append(cur)

    for si, cols in enumerate(systems):
        if y - sys_h < M:
            pdf.new_page()
            y = H - M - SYS_HEAD
        part_tops = []
        py = y
        for pname, measures, staves in parts:
            part_tops.append(staff_tops(py, staves))
            py -= part_height(staves) + SCORE_GAP
        for (pname, measures, staves), tops in zip(parts, part_tops):
            for stop in tops:
                for i in range(5):
                    pdf.line(M, stop - i * SP, W - M, stop - i * SP,
                             w=0.7)
            if staves > 1:
                draw_brace(pdf, M - 2, tops[0], tops[-1] - STAFF)
            pdf.text(M - (14 if staves > 1 else 4),
                     (tops[0] + tops[-1] - STAFF) / 2 - 3, pname,
                     size=8.5, font='H', right=True)
        pdf.line(M, part_tops[0][0], M, part_tops[-1][-1] - STAFF, w=1.4)
        x0 = M
        lead = 0
        for (pname, measures, staves), tops in zip(parts, part_tops):
            state = measures[cols[0]]['state']
            for st, stop in enumerate(tops, 1):
                draw_clef(pdf, x0 + 1.2 * SP, stop,
                          state['clefs'].get(st, 'G'))
                xk = draw_key(pdf, x0 + 6.5 * SP, stop, state['fifths'],
                              state['clefs'].get(st, 'G'),
                              measures[cols[0]])
                lead = max(lead, xk - x0)
        x = x0 + lead
        stretch = (W - M - x) / sum(widths[j] for j in cols)
        if si == len(systems) - 1:
            stretch = min(stretch, 1.15)
        for mi, j in enumerate(cols):
            w = widths[j] * stretch
            for pi, ((pname, measures, staves), tops) in enumerate(
                    zip(parts, part_tops)):
                draw_measure(pdf, measures[j], x, tops, w,
                             first_in_system=(mi == 0),
                             carry=carries[pi])
            x += w
        for c in carries:
            drain_ties(pdf, c, W - M - 0.5 * SP)
        y = part_tops[-1][-1] - STAFF - SYS_HEAD - 2 * SP
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


GRAND_GAP = 6.5 * SP


def part_height(staves):
    return staves * STAFF + (staves - 1) * GRAND_GAP


def staff_tops(y, staves):
    return [y - i * (STAFF + GRAND_GAP) for i in range(staves)]


def draw_brace(pdf, x, top, bottom_y):
    """The grand staff's curly brace, two mirrored strokes."""
    mid = (top + bottom_y) / 2
    for a, b in ((top, mid), (bottom_y, mid)):
        d = 1 if a > b else -1
        pdf.bez([(x, a),
                 ((x - 2.4 * SP, a - d * (a - b) * 0.32),
                  (x + 0.4 * SP, b + d * (a - b) * 0.45),
                  (x - 1.9 * SP, b))], w=1.8)


def draw_measure(pdf, meas, x0, tops, width, first_in_system=False,
                 carry=None):
    state = meas['state']
    div = state['div']
    top = tops[0]
    bottom_y = tops[-1] - STAFF
    x = x0 + 1.2 * SP

    show_clefs = meas['show'].get('clef')
    if show_clefs and not first_in_system:
        for st, stop in enumerate(tops, 1):
            draw_clef(pdf, x, stop, show_clefs.get(st, 'G'))
        x += 6 * SP
    if 'time' in meas['show']:
        n, d = meas['show']['time']
        for stop in tops:
            if pdf.music:
                for val, yy in ((n, stop - SP), (d, stop - 3 * SP)):
                    digits = str(val)
                    tw = sum(pdf.gw(f'ts{c}', 4 * SP) for c in digits)
                    dx = x - tw / 2
                    for c in digits:
                        pdf.glyph(dx, yy, f'ts{c}', 4 * SP)
                        dx += pdf.gw(f'ts{c}', 4 * SP)
            else:
                pdf.text(x, stop - 1.9 * SP, str(n), size=2.6 * SP,
                         font='TB', center=True)
                pdf.text(x, stop - 3.9 * SP, str(d), size=2.6 * SP,
                         font='TB', center=True)
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
        meas['_repx'] = max(x0, x - 1.2 * SP)
        x += 2.4 * SP
    if meas['multi']:
        for stop in tops:
            smid = stop - STAFF / 2
            pdf.line(x + SP, smid, x0 + width - 2 * SP, smid, w=4.5)
            for xx in (x + SP, x0 + width - 2 * SP):
                pdf.line(xx, smid - 1.2 * SP, xx, smid + 1.2 * SP, w=1.2)
        pdf.text((x + x0 + width) / 2, top + 1.2 * SP,
                 str(meas['multi']), size=12, font='HB', center=True)
        draw_barline(pdf, meas, x0, tops, width)
        draw_measure_number(pdf, meas, x0, top)
        return x0 + width

    span = max(x0 + width - x - 2.2 * SP, 4 * SP)
    total = max(meas['len'], 1)

    # optical spacing: onsets take their rhythm's share of the bar,
    # but never sit closer than their ink allows
    needs = ink_needs(meas)
    pts = sorted(needs)
    x_lo = x + 1.2 * SP
    x_hi = x_lo + span - 2.4 * SP
    marks = [(0, x_lo)]
    if pts:
        xs, prev = [], None
        for p in pts:
            ideal = x_lo + (p / total) * (span - 2.4 * SP)
            xi = max(ideal, x + needs[p][0] + 0.3 * SP)
            if prev is not None:
                xi = max(xi, xs[-1] + needs[prev][1]
                         + needs[p][0] + INK_GAP)
            xs.append(xi)
            prev = p
        limit = x + span - 1.2 * SP
        over = xs[-1] + needs[pts[-1]][1] - limit
        if over > 0 and xs[-1] > xs[0]:      # squeeze, best effort
            t = max((limit - needs[pts[-1]][1] - xs[0])
                    / (xs[-1] - xs[0]), 0.5)
            xs = [xs[0] + (xi - xs[0]) * t for xi in xs]
        marks = [(0, min(x_lo, xs[0]))] if pts[0] > 0 else []
        marks += list(zip(pts, xs))
        end = max(x_hi, xs[-1] + 0.5 * SP)
    else:
        end = x_hi
    if marks[-1][0] < total:
        marks.append((total, end))

    def xat(pos, extra=0.0):
        for (p0, v0), (p1, v1) in zip(marks, marks[1:]):
            if pos <= p1:
                if pos <= p0:
                    return v0 + extra
                return v0 + (pos - p0) / (p1 - p0) * (v1 - v0) + extra
        return marks[-1][1] + extra

    last_cx = None
    for pos, sym in meas['chords']:
        cxs = xat(pos)
        if last_cx is not None:      # two changes never print on top
            cxs = max(cxs, last_cx + 7)
        last_cx = draw_chord_symbol(pdf, cxs, top + 1.5 * SP, sym)
    DYN_GLYPH = {'p': 'dynP', 'f': 'dynF', 'mf': 'dynMF',
                 'mp': 'dynMP', 'pp': 'dynPP', 'ff': 'dynFF',
                 'sfz': 'dynSFZ', 'fp': 'dynFP'}
    for pos, mark in meas['dyn']:
        g = DYN_GLYPH.get(mark)
        if not (g and pdf.glyph(xat(pos), bottom_y - 2.6 * SP, g,
                                4 * SP)):
            pdf.text(xat(pos), bottom_y - 2.6 * SP, mark, size=11,
                     font='TBI')

    beat_len = div * 4 // state['time'][1]
    streams = {}
    for pos, notes, staff, voice in meas['events']:
        streams.setdefault((staff, voice), []).append((pos, notes))
    voices_of = {}
    for staff, voice in streams:
        voices_of.setdefault(staff, set()).add(voice)
    if carry is None:
        carry = {}
    for (staff, voice), evs in streams.items():
        stop = tops[min(staff, len(tops)) - 1]
        two = len(voices_of[staff]) > 1
        forced = (voice == min(voices_of[staff])) if two else None
        clef = state['clefs'].get(staff, 'G')
        draw_stream(pdf, evs, stop, clef, beat_len, xat, x0, width,
                    forced, bottom_y,
                    carry.setdefault((staff, voice), []))

    draw_barline(pdf, meas, x0, tops, width)
    draw_ending(pdf, meas, x0, top, width)
    draw_measure_number(pdf, meas, x0, top)
    return x0 + width


def draw_stream(pdf, events, top, clef, beat_len, xat, x0, width,
                forced, bottom_y, opens=None):
    """One voice on one staff: heads, stems, beams, ties, words.
    `opens` carries unclosed ties and slurs between measures, so an
    arc across a barline is one true curve, not a hint."""
    mid = top - STAFF / 2
    pend_beam = []
    slur_open = opens if opens is not None else []
    drawn = []
    # notes that will beam together share one stem direction, decided
    # by the whole group — a lone dissenter would get its stem drawn
    # from the wrong side of the beam, a pole through the staff
    beat_ps = {}
    for pos, notes in events:
        n0 = notes[0]
        if n0.rest or not FLAGS.get(n0.ntype, 0):
            continue
        beat_ps.setdefault(pos // beat_len, []).extend(
            step_pos(n.step, n.octave, clef) for n in notes)
    beat_dir = {b: (sum(ps) / len(ps)) < 4 for b, ps in beat_ps.items()}
    for ei, (pos, notes) in enumerate(events):
        n0 = notes[0]
        cx = xat(pos)
        if n0.rest:
            flush_beam(pdf, pend_beam)
            pend_beam = []
            if n0.measure_rest and forced is False:
                continue           # the second voice's filler rest
            draw_rest(pdf, cx, top,
                      'measure' if n0.measure_rest else n0.ntype)
            dot_x = cx + 1.6 * SP
            for _ in range(n0.dots):
                _dot(pdf, dot_x, mid + 0.5 * SP)
                dot_x += 3.4
            continue
        scale = 0.68 if n0.cue else 1.0
        ps = [step_pos(n.step, n.octave, clef) for n in notes]
        ys = [top - STAFF + p * SP / 2 for p in ps]
        if forced is not None:
            up = forced
        elif FLAGS.get(n0.ntype, 0) and pos // beat_len in beat_dir:
            up = beat_dir[pos // beat_len]
        else:
            up = (sum(ps) / len(ps)) < 4
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
            if n.alter and not n.slash:    # a slash has no pitch to alter
                draw_accidental(pdf, ax, yy, n.alter, scale=scale)
                ax -= 1.7 * SP
        head = ('slash' if n0.slash else DUR_HEADS.get(n0.ntype, 'black'))
        order = sorted(range(len(ps)), key=lambda i: ps[i])
        side = {}
        prev_p, flip = None, False
        for i in order:
            flip = (not flip) if (prev_p is not None
                                  and ps[i] - prev_p == 1) else False
            side[i] = flip
            prev_p = ps[i]
        for i, (n, yy) in enumerate(zip(notes, ys)):
            dx = 2.15 * SP * scale * (1 if up else -1) if side[i] else 0
            notehead(pdf, cx + dx, yy, head, scale=scale, parens=n.parens)
        dot_x = cx + 1.9 * SP
        for _ in range(n0.dots):
            for yy in ys:
                _dot(pdf, dot_x, yy + (0 if (round(yy - top) % round(SP))
                                       else 0.5 * SP))
            dot_x += 3.4
        stem_x = cx + (1.15 * SP if up else -1.15 * SP) * scale
        if n0.ntype != 'whole':
            lo, hi = min(ys), max(ys)
            tip = (hi + 3.4 * SP * scale) if up else (lo - 3.4 * SP * scale)
            pdf.line(stem_x, (lo if up else hi), stem_x, tip,
                     w=1.1 * scale)
        else:
            tip = max(ys) if up else min(ys)
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
        if n0.artic:
            if n0.artic in ('strong-accent', 'accent'):
                ay = max(top + 0.6 * SP, max(ys) + 1.8 * SP)
            else:
                ay = (min(ys) - 2.2 * SP) if up else (max(ys) + 1.6 * SP)
            acx = cx
            if n0.artic in ('scoop', 'plop') and any(n.alter for n in notes):
                acx -= 1.9 * SP        # start left of the accidental
            draw_artic(pdf, acx, ay, n0.artic)
        if n0.tie_stop or n0.slur_stop:
            if slur_open:
                sx, sy, sup = slur_open.pop()
                ey = (max(ys) if sup else min(ys))
                arc = 2.2 * SP * (1 if sup else -1)
                if sx is None:      # broken at the system turn: the
                    sx = max(x0 + 0.8 * SP, cx - 5 * SP)
                    sy = ey         # incoming half, flat to the note
                    arc = 1.8 * SP * (1 if sup else -1)
                draw_arc(pdf, sx, sy + 0.27 * arc, cx,
                         ey + 0.27 * arc, arc)
        if n0.tie_start or n0.slur_start:
            sup = not up
            slur_open.append((cx + SP,
                              (max(ys) if sup else min(ys)), sup))
        if n0.lyric:
            syl, txt, ext = n0.lyric
            shown = txt + ("" if syl in ('single', 'end') else " -")
            lx = pdf.text(cx, bottom_y - 4.6 * SP, shown, size=8.5,
                          font='H', center=True)
            if ext:
                pdf.line(lx + max(0.55 * 8.5 * len(shown),
                                  pdf.tw(shown, 8.5, 'H')) + 2,
                         bottom_y - 4.6 * SP,
                         xat(pos + n0.dur * 0.9),
                         bottom_y - 4.6 * SP, w=0.8)
        if n0.tmod and (not drawn or drawn[-1] != pos // beat_len):
            pdf.text(xat(pos + beat_len / 2 - n0.dur / 2),
                     (tip + (1.6 * SP if up else -2.6 * SP)),
                     str(n0.tmod), size=8, font='HO', center=True)
            drawn.append(pos // beat_len)
    flush_beam(pdf, pend_beam)


def drain_ties(pdf, carry, edge):
    """A system ends: every open tie draws its outgoing half to the
    right edge and becomes a resume marker for the next system's
    incoming half."""
    for key, opens in carry.items():
        fresh = []
        for sx, sy, sup in opens:
            if sx is None:
                continue            # never landed; let it go quietly
            arc = 1.8 * SP * (1 if sup else -1)
            draw_arc(pdf, sx, sy + 0.3 * arc, edge, sy + 0.3 * arc, arc)
            fresh.append((None, None, sup))
        carry[key] = fresh


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
    if pdf.music:
        name = {'staccato': 'stacc', 'accent': 'accent',
                'strong-accent': 'marcato', 'tenuto': 'tenuto'}.get(artic)
        if name and pdf.glyph(x - pdf.gw(name, 4 * SP) / 2, y, name,
                              4 * SP):
            return
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
    """F7, Bbm7b5, C/E — root and bass accidentals drawn as real
    flats and sharps beside their letters."""
    m = re.match(r'([A-G])([b#]?)([^/]*)(?:/([A-G])([b#]?))?$', sym)
    if not m:
        pdf.text(x, y, sym, size=10.5, font='HB')
        return x + 0.58 * 10.5 * len(sym)
    size = 10.5

    def piece(px, letter, acc, rest=''):
        pdf.text(px, y, letter, size=size, font='HB')
        px += max(0.68 * size, pdf.tw(letter, size, 'HB') + 1.5)
        if acc:
            draw_accidental(pdf, px + 1.5, y + 3.2,
                            -1 if acc == 'b' else 1, scale=0.52)
            px += 4.6
        if rest:
            pdf.text(px, y, rest, size=size * 0.86, font='HB')
            px += max(0.56 * size * 0.86 * len(rest),
                      pdf.tw(rest, size * 0.86, 'HB') + 1)
        return px
    px = piece(x, m.group(1), m.group(2), m.group(3) or '')
    if m.group(4):
        pdf.text(px, y, "/", size=size, font='HB')
        px = piece(px + 0.5 * size, m.group(4), m.group(5))
    return px


def draw_arc(pdf, sx, sy, ex, ey, arc):
    """A tapered tie or slur: two curves closed and filled."""
    mx = (sx + ex) / 2
    pdf.bez([(sx, sy),
             ((mx, sy + arc), (mx, ey + arc), (ex, ey)),
             ((mx, ey + arc * 0.72), (mx, sy + arc * 0.72), (sx, sy))],
            fill=True, w=0.7)


def flush_beam(pdf, group):
    if len(group) < 2:
        if group:
            x, tip, up, n = group[0]
            draw_flag(pdf, x, tip, up, n)
        return
    up = group[0][2]
    x1, x2 = group[0][0], group[-1][0]
    # the beam leans the way the line goes, gently
    rise = group[-1][1] - group[0][1]
    rise = max(-SP, min(SP, rise))
    slope = rise / max(x2 - x1, 1)

    def beam_y(x):
        return ref + slope * (x - x1)
    ref = (max if up else min)(g[1] - slope * (g[0] - x1) for g in group)
    levels = max(g[3] for g in group)
    d = 1 if up else -1
    for g in group:                       # stems reach the slanted beam
        pdf.line(g[0], g[1] - d * 2.5 * SP, g[0], beam_y(g[0]), w=1.1)
    for i in range(levels):
        off = -i * 2.6 * d
        full = [g for g in group if g[3] > i]
        if len(full) == len(group) or i == 0:
            pdf.poly([(x1, beam_y(x1) + off), (x2, beam_y(x2) + off),
                      (x2, beam_y(x2) + off - 2 * d),
                      (x1, beam_y(x1) + off - 2 * d)], fill=True)
        else:
            for g in full:                # partial 16th beams: short hooks
                gx = g[0]
                pdf.poly([(gx, beam_y(gx) + off),
                          (gx + 6, beam_y(gx + 6) + off),
                          (gx + 6, beam_y(gx + 6) + off - 2 * d),
                          (gx, beam_y(gx) + off - 2 * d)], fill=True)


def draw_barline(pdf, meas, x0, tops, width):
    xr = x0 + width
    top, bottom_y = tops[0], tops[-1] - STAFF
    right = meas.get('right') or {}
    style = right.get('style')
    if style == 'light-heavy':
        pdf.line(xr - 4, top, xr - 4, bottom_y, w=0.9)
        pdf.line(xr - 1, top, xr - 1, bottom_y, w=2.6)
    elif style == 'light-light':
        pdf.line(xr - 4, top, xr - 4, bottom_y, w=0.9)
        pdf.line(xr - 1, top, xr - 1, bottom_y, w=0.9)
    else:
        pdf.line(xr - 1, top, xr - 1, bottom_y, w=0.9)
    if right.get('repeat') == 'backward':
        for stop in tops:
            for dy in (1.5 * SP, 2.5 * SP):
                _dot(pdf, xr - 7.5, stop - dy)
    left = meas.get('left') or {}
    if left.get('repeat') == 'forward':
        rx = meas.get('_repx', x0)     # past any clef/key/time block
        pdf.line(rx + 1, top, rx + 1, bottom_y, w=2.6)
        pdf.line(rx + 4.5, top, rx + 4.5, bottom_y, w=0.9)
        for stop in tops:
            for dy in (1.5 * SP, 2.5 * SP):
                _dot(pdf, rx + 8, stop - dy)


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
