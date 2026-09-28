#!/usr/bin/env python3
"""textformats: song material out of any text file a writer is holding.

    python3 textformats.py "Autumn Leaves.txt"     what is in it, spoken
    python3 textformats.py --selftest               every check, one line each

The importer (chartimport.py) turns what this module returns into a
chart. This module only reads and understands; it never writes a chart.

Two jobs, kept apart so each can be tested on its own:

  read_text(path)    any text-bearing file -> plain text. Plain text in
                     any common encoding, Markdown, RTF and RTFD, Word
                     (.doc, .docx), OpenDocument (.odt), web pages and
                     Safari web archives, PDF, Pages, ChordPro, ABC and
                     CSV. On a Mac, Apple's textutil does the office
                     formats; everywhere else (Windows included) plain
                     Python does .docx, .odt, .rtf, .html and
                     .webarchive itself, so nobody is shut out for not
                     owning a Mac.

  parse_song(text)   plain text -> one song: title, key, meter, tempo,
                     sections of bars of chords, words, and a melody
                     when the source has one. It recognises an iReal
                     Pro link, ABC notation, ChordPro, a chord sheet
                     (chords written over the words) and plain lyrics.

Every chord that comes out is one chartc.split_chord accepts, so the
importer never has to second-guess a spelling. When a source uses a
chord the chart format does not know yet, it is simplified to the
nearest one it does, and a finding says exactly what changed.

Every message is one plain sentence a screen reader can speak: no
tracebacks, no box drawing. ImportTrouble carries that sentence.

Python 3 standard library only, like the rest of Copyist.
"""
import codecs
import csv
import html
import io
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction
from html.parser import HTMLParser
from urllib.parse import quote, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import chartc  # noqa: E402


class ImportTrouble(Exception):
    """Something the writer needs to hear about. str() is the one
    sentence to speak; it always says what to do next where there is
    something to do."""


# =================================================================
# reading: any file -> plain text
# =================================================================

TEXTUTIL = '/usr/bin/textutil'

HOW = {
    '.txt': 'a plain text file', '.text': 'a plain text file',
    '.md': 'a Markdown file', '.markdown': 'a Markdown file',
    '.rtf': 'a Rich Text file', '.rtfd': 'a Rich Text file with pictures',
    '.doc': 'an older Word document', '.docx': 'a Word document',
    '.odt': 'an OpenDocument text file',
    '.html': 'a web page', '.htm': 'a web page',
    '.webarchive': 'a Safari web archive',
    '.pdf': 'a PDF', '.pages': 'a Pages document',
    '.cho': 'a ChordPro file', '.chordpro': 'a ChordPro file',
    '.chopro': 'a ChordPro file', '.crd': 'a ChordPro file',
    '.pro': 'a ChordPro file',
    '.abc': 'an ABC tune file', '.csv': 'a spreadsheet saved as CSV',
}
# the formats textutil can read; each also has a plain-Python fallback
# below except .doc, whose binary layout the standard library cannot open
OFFICE = ('.rtf', '.rtfd', '.doc', '.docx', '.odt', '.html', '.htm',
          '.webarchive')

IREAL_LINK = re.compile(r'irealb(?:ook)?://[^\s"\'<>]+')


def read_text(path):
    """Any supported file -> (plain text, how), `how` a short phrase
    like 'a Word document'. Raises ImportTrouble with one sentence."""
    name = os.path.basename(path.rstrip(os.sep)) or path
    if not os.path.exists(path):
        raise ImportTrouble(f"I can't find {name}.")
    ext = os.path.splitext(path.rstrip(os.sep))[1].lower()
    how = HOW.get(ext, 'a text file')
    if os.path.isdir(path) and ext not in ('.rtfd', '.pages'):
        raise ImportTrouble(f"{name} is a folder; bring in one file at "
                            "a time.")
    if ext == '.pdf':
        text = _pdf_text(path)
    elif ext == '.pages':
        text = _pages_text(path)
    elif ext in OFFICE:
        # an iReal Pro link hides in a hyperlink's address, which every
        # text conversion throws away, so look for one in the raw file
        # first; a playlist page exported from iReal is exactly this
        links = _ireal_links_in(path, ext)
        if links:
            text = "\n".join(links)
        else:
            text = _textutil(path) if _have_textutil() else None
            if text is None:
                text = _office_fallback(path, ext, name)
    else:
        with open(path, 'rb') as f:
            text = _decode(f.read(), name)
        if ext in ('.md', '.markdown'):
            text = _strip_markdown(text)
        elif ext == '.csv':
            text = _csv_text(text)
    return normalize_text(text), how


def normalize_text(text):
    """One newline convention, no byte-order mark, no invisible
    spaces: every parser below can then trust what it sees."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\f', '\n').replace('\u2028', '\n')
    text = text.replace('\u2029', '\n').replace('\u00a0', ' ')
    text = text.replace('\u200b', '').replace('\ufeff', '')
    return "\n".join(ln.rstrip() for ln in text.split('\n'))


def _decode(raw, name='that file'):
    """Bytes -> str for a file that claims to be text. UTF-8 first,
    UTF-16 when it says so (or plainly is: every other byte zero, the
    way Windows Notepad saves 'Unicode'), then Windows and Latin-1,
    which between them decode anything."""
    if raw.startswith(codecs.BOM_UTF8):
        return raw[3:].decode('utf-8', 'replace')
    if raw.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        return raw.decode('utf-32', 'replace')
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode('utf-16', 'replace')
    if len(raw) >= 4 and raw.count(0) > len(raw) // 4:
        even, odd = raw[0::2].count(0), raw[1::2].count(0)
        if max(even, odd) > len(raw) // 4:
            enc = 'utf-16-le' if odd > even else 'utf-16-be'
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                pass
        raise ImportTrouble(f"{name} doesn't look like text; if it is a "
                            "document, save it as Word or plain text "
                            "and bring that in.")
    ctrl = sum(1 for b in raw[:4096] if b < 32 and b not in (9, 10, 12, 13))
    if 0 in raw or ctrl > len(raw[:4096]) // 20:
        raise ImportTrouble(f"{name} doesn't look like text; if it is a "
                            "document, save it as Word or plain text "
                            "and bring that in.")
    for enc in ('utf-8', 'cp1252'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1')


def _have_textutil():
    return sys.platform == 'darwin' and os.path.exists(TEXTUTIL)


def _textutil(path):
    """Apple's converter. None on any failure, so the plain-Python
    reader gets its turn rather than the writer getting an error."""
    try:
        r = subprocess.run([TEXTUTIL, '-convert', 'txt', '-stdout', path],
                           capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return r.stdout.decode('utf-8', 'replace')


def _office_fallback(path, ext, name):
    try:
        if ext == '.docx':
            return docx_text(path)
        if ext == '.odt':
            return odt_text(path)
        if ext == '.rtf':
            with open(path, 'rb') as f:
                return rtf_text(f.read().decode('latin-1'))
        if ext == '.rtfd':
            inner = os.path.join(path, 'TXT.rtf')
            if not os.path.exists(inner):
                raise ImportTrouble(f"{name} has no text inside it that "
                                    "I can find.")
            with open(inner, 'rb') as f:
                return rtf_text(f.read().decode('latin-1'))
        if ext in ('.html', '.htm'):
            with open(path, 'rb') as f:
                return html_text(_decode(f.read(), name))
        if ext == '.webarchive':
            return webarchive_text(path)
    except (zipfile.BadZipFile, KeyError, ET.ParseError,
            plistlib.InvalidFileException, ValueError) as e:
        if isinstance(e, ImportTrouble):
            raise
        raise ImportTrouble(f"{name} looks damaged, and I couldn't read "
                            "it; open it and save it again, or save it "
                            "as plain text.")
    # .doc: a binary Word 97 file, which only Word (or textutil) opens
    raise ImportTrouble(f"{name} is an older Word document, which this "
                        "computer can't read; open it in Word, save it "
                        "as a .docx or as plain text, and bring that in.")


def _ireal_links_in(path, ext):
    """Every iReal Pro link in the raw bytes of an office file or web
    page, decoded far enough to find them."""
    try:
        if ext in ('.docx', '.odt'):
            with zipfile.ZipFile(path) as z:
                raw = b"".join(z.read(n) for n in z.namelist()
                               if n.endswith(('.xml', '.rels')))
        elif ext == '.rtfd':
            inner = os.path.join(path, 'TXT.rtf')
            raw = open(inner, 'rb').read() if os.path.exists(inner) else b''
        elif ext == '.webarchive':
            with open(path, 'rb') as f:
                d = plistlib.load(f)
            raw = d.get('WebMainResource', {}).get('WebResourceData', b'')
        else:
            with open(path, 'rb') as f:
                raw = f.read()
    except Exception:
        return []
    text = html.unescape(raw.decode('utf-8', 'replace'))
    return IREAL_LINK.findall(text)


# ---- Word .docx, plain Python

W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def docx_text(path):
    """A .docx is a zip; the words are in word/document.xml. Text comes
    from runs only, so tab-stop definitions in the paragraph settings
    never turn into stray tabs."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    lines = []
    for p in root.iter(W_NS + 'p'):
        buf = []
        for r in p.iter(W_NS + 'r'):
            for el in r:
                tag = el.tag
                if tag == W_NS + 't':
                    buf.append(el.text or '')
                elif tag == W_NS + 'tab':
                    buf.append('\t')
                elif tag in (W_NS + 'br', W_NS + 'cr'):
                    buf.append('\n')
                elif tag == W_NS + 'noBreakHyphen':
                    buf.append('-')
        lines.append("".join(buf))
    return "\n".join(lines)


# ---- OpenDocument .odt, plain Python

T_NS = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'


def odt_text(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('content.xml'))
    lines = []

    def inline(el):
        parts = [el.text or '']
        for ch in el:
            tag = ch.tag
            if tag == T_NS + 's':
                parts.append(' ' * int(ch.get(T_NS + 'c', '1')))
            elif tag == T_NS + 'tab':
                parts.append('\t')
            elif tag == T_NS + 'line-break':
                parts.append('\n')
            elif tag.endswith(('}note', '}annotation')):
                pass        # footnotes and comments are not the song
            else:
                parts.append(inline(ch))
            parts.append(ch.tail or '')
        return "".join(parts)

    def walk(el):
        for ch in el:
            if ch.tag in (T_NS + 'p', T_NS + 'h'):
                lines.append(inline(ch))
            else:
                walk(ch)
    walk(root)
    return "\n".join(lines)


# ---- RTF, plain Python

RTF_SKIP = {
    'fonttbl', 'colortbl', 'stylesheet', 'info', 'pict', 'header',
    'footer', 'headerl', 'headerr', 'headerf', 'footerl', 'footerr',
    'footerf', 'object', 'themedata', 'colorschememapping',
    'latentstyles', 'datastore', 'xmlnstbl', 'listtable',
    'listoverridetable', 'rsidtbl', 'generator', 'fldinst',
    'expandedcolortbl', 'filetbl', 'revtbl', 'mmathPr', 'footnote',
    'annotation', 'bkmkstart', 'bkmkend', 'shppict', 'nonshppict',
}
RTF_WORDS = {
    'par': '\n', 'line': '\n', 'sect': '\n', 'page': '\n', 'row': '\n',
    'tab': '\t', 'cell': '\t', 'emdash': '\u2014', 'endash': '\u2013',
    'lquote': '\u2018', 'rquote': '\u2019', 'ldblquote': '\u201c',
    'rdblquote': '\u201d', 'bullet': '\u2022', 'emspace': ' ',
    'enspace': ' ', 'qmspace': ' ',
}
RTF_TOKEN = re.compile(
    r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)|([{}])"
    r"|(\r\n|\r|\n)|([^\\{}\r\n]+)", re.S)


def rtf_text(src):
    """Strip RTF to its words: skip the font and colour tables and every
    other destination, turn \\par and \\line into newlines and \\tab into
    a tab, decode \\'hh (Windows code page) and \\uNNNN (Unicode, with
    its fallback characters skipped)."""
    if not src.lstrip().startswith('{\\rtf'):
        return src
    out, stack = [], []
    skip, uc, pending = False, 1, 0
    for m in RTF_TOKEN.finditer(src):
        word, arg, hexc, sym, brace, nl, txt = m.groups()
        if brace == '{':
            stack.append((skip, uc))
            continue
        if brace == '}':
            skip, uc = stack.pop() if stack else (False, 1)
            pending = 0
            continue
        if nl:
            continue
        if pending and (hexc or txt):
            # the characters after \uNNNN are a fallback for old readers
            if hexc:
                pending -= 1
                continue
            drop = min(pending, len(txt))
            txt, pending = txt[drop:], pending - drop
            if not txt:
                continue
        if word:
            if word in RTF_SKIP:
                skip = True
            elif word == 'uc':
                uc = int(arg or 1)
            elif word == 'u' and arg is not None:
                if not skip:
                    n = int(arg)
                    out.append(chr(n + 65536 if n < 0 else n))
                pending = uc
            elif word in RTF_WORDS and not skip:
                out.append(RTF_WORDS[word])
            continue
        if sym is not None:
            if sym == '*':
                skip = True
            elif skip:
                pass
            elif sym in '\\{}':
                out.append(sym)
            elif sym == '~':
                out.append(' ')
            elif sym == '_':
                out.append('-')
            elif sym in '\r\n':
                out.append('\n')
            continue
        if skip:
            continue
        if hexc:
            out.append(bytes([int(hexc, 16)]).decode('cp1252', 'replace'))
        elif txt:
            out.append(txt)
    return "".join(out)


# ---- HTML and web archives, plain Python

class _HTMLText(HTMLParser):
    BLOCK = {'p', 'div', 'li', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5',
             'h6', 'tr', 'table', 'section', 'article', 'blockquote',
             'header', 'footer', 'hr', 'dl', 'dt', 'dd', 'figure',
             'main', 'nav', 'aside', 'form', 'fieldset', 'address'}
    SKIP = {'script', 'style', 'noscript', 'template', 'title', 'svg'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.pre, self.skip = [], 0, 0

    PARA = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote',
            'table', 'ul', 'ol', 'dl', 'hr'}

    def _nl(self, n=1):
        # a paragraph ends in a blank line (a stanza break, on a lyric
        # page); a list item or a div only starts a new line
        tail = "".join(self.parts[-3:])
        have = len(tail) - len(tail.rstrip('\n')) if self.parts else n
        if have < n:
            self.parts.append('\n' * (n - have))

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == 'br':
            self._nl()
        elif tag == 'pre':
            self.pre += 1
            self._nl()
        elif tag in ('td', 'th'):
            self.parts.append('\t')
        elif tag in self.BLOCK:
            self._nl(2 if tag in self.PARA else 1)

    def handle_startendtag(self, tag, attrs):
        if tag in ('br', 'hr'):
            self._nl()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == 'pre':
            self.pre = max(0, self.pre - 1)
            self._nl()
        elif tag in self.BLOCK:
            self._nl(2 if tag in self.PARA else 1)

    def handle_data(self, data):
        if self.skip:
            return
        if self.pre:
            # a chord sheet on the web is usually a <pre>: its spacing
            # is what puts each chord over its word, so keep it all
            self.parts.append(data)
            return
        data = re.sub(r'\s+', ' ', data)
        if not self.parts or self.parts[-1].endswith(('\n', '\t')):
            data = data.lstrip()
        self.parts.append(data)


def html_text(src):
    p = _HTMLText()
    p.feed(src)
    p.close()
    text = "".join(p.parts)
    return re.sub(r'\n{3,}', '\n\n', text).strip('\n')


def webarchive_text(path):
    """A Safari .webarchive is a property list holding the page's
    HTML; plistlib opens it on any computer."""
    with open(path, 'rb') as f:
        d = plistlib.load(f)
    main = d.get('WebMainResource') or {}
    data = main.get('WebResourceData') or b''
    enc = main.get('WebResourceTextEncodingName') or 'utf-8'
    try:
        src = data.decode(enc, 'replace')
    except LookupError:
        src = data.decode('utf-8', 'replace')
    return html_text(src)


# ---- PDF and Pages

def _pdftotext():
    # a GUI launch gets a bare PATH, so look where Homebrew puts it too
    for c in (shutil.which('pdftotext'), '/opt/homebrew/bin/pdftotext',
              '/usr/local/bin/pdftotext', '/usr/bin/pdftotext'):
        if c and os.path.exists(c):
            return c
    return None


def _pdf_text(path):
    name = os.path.basename(path)
    tool = _pdftotext()
    if not tool:
        raise ImportTrouble("Reading a PDF needs the free poppler tools, "
                            "which this computer doesn't have; save the "
                            "song as Word or plain text instead, or "
                            "install poppler.")
    try:
        # -layout keeps each chord over its word, which is the whole
        # meaning of a chord sheet
        r = subprocess.run([tool, '-layout', '-enc', 'UTF-8', path, '-'],
                           capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        r = None
    if r is None or r.returncode != 0:
        raise ImportTrouble(f"{name} wouldn't open as a PDF; it may be "
                            "damaged or locked.")
    text = r.stdout.decode('utf-8', 'replace')
    if not text.strip():
        raise ImportTrouble(f"{name} has pictures of pages but no text in "
                            "it; bring in the original document instead, "
                            "or run it through text recognition first.")
    return text


def _pages_text(path):
    """Pages files carry a PDF preview of the document; poppler reads
    that. Newer Pages files sometimes carry only a picture preview, and
    then the honest answer is to export from Pages."""
    name = os.path.basename(path.rstrip(os.sep))
    pdf = None
    if os.path.isdir(path):
        cand = os.path.join(path, 'QuickLook', 'Preview.pdf')
        if os.path.exists(cand):
            with open(cand, 'rb') as f:
                pdf = f.read()
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.endswith('QuickLook/Preview.pdf'):
                    pdf = z.read(n)
                    break
    if pdf is None:
        raise ImportTrouble(f"I can't read the words inside {name}; in "
                            "Pages, choose File, Export To, then Word or "
                            "Plain Text, and bring that in.")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'Preview.pdf')
        with open(p, 'wb') as f:
            f.write(pdf)
        return _pdf_text(p)


# ---- Markdown and CSV

def _strip_markdown(text):
    """Headings, bold and quote marks off, so '## Verse 1' reads as a
    section header and '**Chorus**' as a word."""
    out = []
    for ln in text.split('\n'):
        if re.match(r'^\s*(```|~~~)', ln):
            continue
        ln = re.sub(r'^\s{0,3}#{1,6}\s*', '', ln)
        ln = re.sub(r'^\s{0,3}>\s?', '', ln)
        ln = ln.replace('**', '').replace('__', '')
        ln = re.sub(r'\\([\[\]#*_|])', r'\1', ln)
        out.append(ln)
    return "\n".join(out)


def _csv_text(text):
    """A spreadsheet row of chords becomes a barred chord line, one
    cell a bar; a row of words stays words."""
    out = []
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return text
    for row in rows:
        cells = [c.strip() for c in row if c.strip()]
        if not cells:
            out.append('')
            continue
        head = header_line(cells[0] + ':') if len(cells) > 1 else None
        body = cells[1:] if head else cells
        if all(chordish(c) for c in body):
            if head:
                out.append(cells[0] + ':')
            out.append('| ' + ' | '.join(body) + ' |')
        else:
            out.append(' '.join(cells))
    return "\n".join(out)


# =================================================================
# chords: any spelling -> one chartc accepts
# =================================================================

UNICODE_CHORD = [('\u266d', 'b'), ('\u266f', '#'), ('\u0394 7', 'maj7'),
                 ('\u03947', 'maj7'), ('\u0394', 'maj7'),
                 ('\u25b37', 'maj7'), ('\u25b3', 'maj7'),
                 ('\u00f87', 'm7b5'), ('\u00f8', 'm7b5'),
                 ('\u00d87', 'm7b5'), ('\u00d8', 'm7b5'),
                 ('\u00b0', 'dim'), ('\u00ba', 'dim'),
                 ('\u2212', '-'), ('\u2013', '-')]

NC_RX = re.compile(r'^\(?(?:n\.?\s?c\.?|no\s*chord)\)?$', re.I)

ACC = r'(?:b|#|\u266d|\u266f)'
# loose shape of a chord symbol: used to tell a chord line from a line of
# words. 'o' and 'h' (iReal's dim and half-dim) only count before a
# digit, so the words Go, Do, Ah and Eh never read as chords
CHORD_RX = re.compile(
    r'^[A-G]' + ACC + r'?'
    r'(?:maj|Maj|MAJ|ma|M|min|mi|m|dim|aug|sus|add|alt|dom|6/9'
    r'|\u0394|\u25b3|\u00f8|\u00d8|\u00b0|\u00ba|\^|\+|-|\u2212'
    r'|b|#|\u266d|\u266f|\d|\(|\)|o(?=\d)|h(?=\d))*'
    r'(?:/[A-G]' + ACC + r'?)?$')


def chordish(tok):
    """Does this token look like a chord symbol (or N.C.)?"""
    t = tok.strip()
    if len(t) > 2 and t[0] == '(' and t[-1] == ')' and t.count('(') == 1:
        t = t[1:-1]
    return bool(CHORD_RX.match(t) or NC_RX.match(t))


def chord_ok(sym):
    try:
        chartc.split_chord(sym)
        return True
    except SystemExit:
        return False
    except Exception:
        return False


def _translate(q):
    """A source's quality spelling -> candidate chart spellings, most
    faithful first. Covers iReal Pro's codes (^ - h o +), the classical
    signs, and the working shorthand of lead sheets."""
    t = q.strip().replace(' ', '')
    if len(t) > 2 and t[0] == '(' and t[-1] == ')' and t.count('(') == 1:
        t = t[1:-1]
    if t in ('', 'M', 'maj', 'Maj', 'MAJ', 'major', 'ma', 'Ma'):
        return ['maj']
    if t == '^':
        return ['maj7']          # iReal's bare triangle is a major seventh
    t = re.sub(r'\^(?![\d(])', 'maj7', t)   # iReal -^ is minor-major 7
    t = t.replace('^', 'maj')
    t = re.sub(r'^(?:Maj|MAJ|Ma|ma|M)(?=\d|\(|$|#|b)', 'maj', t)
    t = re.sub(r'(?<=m)(?:Maj|MAJ|Ma|M)(?=\d|\(|$)', 'maj', t)
    t = re.sub(r'^(?:min|mi)(?=[\d(#b+\-]|maj|M|$)', 'm', t)
    if t.startswith('+'):
        t = 'aug' + t[1:]
    if t.startswith('-'):
        t = 'm' + t[1:]
    # interior - and + are flat and sharp: 7-9 is 7b9, m7-5 is m7b5
    t = re.sub(r'-(?=13|11|9|5|6)', 'b', t)
    t = re.sub(r'\+(?=13|11|9|5)', '#', t)
    t = re.sub(r'(\d)\+$', r'\1#5', t)      # 7+ is an augmented seventh
    if t == 'aug9':
        t = '9#5'
    t = re.sub(r'^h(\d*)', lambda m: 'm' + (m.group(1) or '7') + 'b5', t)
    if t in ('m7b5', 'm7b57'):
        t = 'm7b5'
    t = re.sub(r'^o(?=\d|$|maj)', 'dim', t)
    t = re.sub(r'^dom(?=\d|$)', '', t) or 'maj'
    if t in ('2', 'add2'):
        t = 'add9'
    elif t == 'madd2':
        t = 'madd9'
    elif t == '4':
        t = 'sus4'
    elif t == 'alt7':
        t = 'alt'
    t = re.sub(r'13sus4?$', '13sus', t)
    return [t, t.replace('(', '').replace(')', '').replace(',', '')]


def _simplify(t):
    """The nearest accepted qualities for one the chart doesn't know,
    in order: keep the chord's family and as many of its alterations
    as the list allows, then its plain seventh, then its triad."""
    alts = re.findall(r'[b#](?:13|11|9|5)', t)
    base = re.sub(r'[b#](?:13|11|9|5)', '', t)
    minorish = base.startswith('m') and not base.startswith('maj')
    majorish = base.startswith('maj')
    domish = bool(re.match(r'\d', base))
    ext_m = re.search(r'(?<![b#])(\d+)', base)
    ext = int(ext_m.group(1)) if ext_m else 0
    cands = []
    for k in range(len(alts) - 1, 0, -1):
        cands.append(base + "".join(alts[:k]))
    if 'b5' in alts and minorish:
        cands.append('m7b5')
    if 'b5' in alts and domish:
        cands.append('7b5')
    if '#5' in alts and domish:
        cands.append('7#5')
    if '#5' in alts and not base:
        cands.append('aug')
    for a in alts:
        cands.append(base + a)
    fam7 = 'maj7' if majorish else 'm7' if minorish else '7' if domish \
        else None
    if fam7:
        for a in alts:
            cands.append(fam7 + a)
    cands.append(base)
    if 'mmaj' in base or base.startswith('mM'):
        cands.append('mmaj7')
    elif base.startswith('dim'):
        cands += ['dim7'] if '7' in base else ['dim']
    elif 'sus' in base:
        cands += ['7sus4'] if ext >= 7 else ['sus4']
    elif base.startswith('aug'):
        cands += ['7#5'] if ext >= 7 else ['aug']
    elif majorish:
        cands += ['maj9', 'maj7'] if ext >= 9 else ['maj7'] if ext else \
            ['maj']
    elif minorish:
        ladder = {13: ['m11', 'm9', 'm7'], 11: ['m11', 'm7'],
                  9: ['m9', 'm7'], 7: ['m7'], 6: ['m6']}
        cands += ladder.get(ext, ['m7'] if ext > 7 else ['m'])
    elif base.startswith('add') or base.startswith('6'):
        cands += ['add9', '6']
    elif domish:
        ladder = {13: ['13', '9', '7'], 11: ['11', '9', '7'],
                  9: ['9', '7'], 7: ['7'], 6: ['6']}
        cands += ladder.get(ext, ['maj'] if ext < 6 else ['7'])
    cands.append('maj')
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def normalize_chord(raw):
    """Any chord spelling -> (chart spelling, simplified?) or
    (None, False) when it is not a chord at all. The chart spelling
    always passes chartc.split_chord; 'nc' is no chord."""
    s = raw.strip()
    if not s:
        return None, False
    if NC_RX.match(s):
        return 'nc', False
    for a, b in UNICODE_CHORD:
        s = s.replace(a, b)
    s = s.replace('6/9', '69')
    if len(s) > 2 and s[0] == '(' and s[-1] == ')':
        s = s[1:-1]
    m = re.fullmatch(r'([A-G])([b#]?)(.*?)(?:/([A-Ga-g][b#]?))?', s)
    if not m:
        return None, False
    root = m.group(1) + m.group(2)
    bass = m.group(4)
    if bass:
        bass = bass[0].upper() + bass[1:]
    tail = '/' + bass if bass else ''
    cands = _translate(m.group(3))
    for q in cands:
        sym = _canonical(root + ('' if q == 'maj' else q) + tail)
        if sym:
            return sym, False
    for q in _simplify(cands[-1]):
        sym = _canonical(root + ('' if q == 'maj' else q) + tail)
        if sym:
            return sym, True
    return root, True


def _canonical(sym):
    """The compiler's own spelling of an accepted chord (Csus comes back
    Csus4, C7alt comes back Calt), or None when it is not accepted."""
    try:
        parts = chartc.split_chord(sym)
    except SystemExit:
        return None
    except Exception:
        return None
    if parts is None:
        return 'nc'
    step, alter, qual, bass = parts
    out = step + {-1: 'b', 1: '#', 0: ''}[alter] + \
        ('' if qual == 'maj' else qual) + ('/' + bass if bass else '')
    return out if chord_ok(out) else sym


class _Ctx:
    """What one parse has noticed: the findings to speak, and every
    chord it had to simplify (said once, together, at the end)."""

    def __init__(self):
        self.findings, self.simplified, self._once = [], {}, set()
        self.assumed_bars = False
        self.not_chords = []

    def find(self, sentence, key=None):
        key = key or sentence
        if key not in self._once:
            self._once.add(key)
            self.findings.append(sentence)

    def chord(self, raw):
        sym, simp = normalize_chord(raw)
        if sym is None:
            if raw.strip() and raw.strip() not in self.not_chords:
                self.not_chords.append(raw.strip())
            return None
        if simp:
            self.simplified.setdefault(raw.strip(), sym)
        return sym

    def finish(self):
        if self.assumed_bars:
            self.find("Each chord was given one bar; say the real "
                      "lengths at the editing desk.")
        if self.simplified:
            pairs = [f"{a} became {b}" for a, b in self.simplified.items()]
            more = len(pairs) - 6
            said = ", ".join(pairs[:6])
            if more > 0:
                said += f", and {more} more"
            self.find("Some chords were simplified to ones the chart "
                      f"knows: {said}.")
        if self.not_chords:
            self.find("These weren't read as chords and were left out: "
                      + ", ".join(self.not_chords[:6]) + ".")
        return self.findings


# =================================================================
# classify
# =================================================================

SECTION_WORD = (r'(?:intro|verse|chorus|pre[- ]?chorus|post[- ]?chorus'
                r'|bridge|outro|refrain|interlude|instrumental|solo|tag'
                r'|coda|break|breakdown|ending|hook|vamp|turnaround'
                r'|head|out[- ]?chorus|middle (?:8|eight)|link|riff'
                r'|reprise|fade(?: out)?|[a-h] section|section [a-h])')
_NAME = r'(?P<name>' + SECTION_WORD + r'(?:[ \t]*\d+)?)'
_REP = (r'(?:[ \t]*\(?[x\u00d7][ \t]*(?P<rep1>\d+)\)?'
        r'|[ \t]*\(?(?P<rep2>\d+)[ \t]*[x\u00d7]\)?)?')
_LEAD = r'^\s*[#*_>]*\s*'
HDR_BRACKET = re.compile(_LEAD + r'[\[\(\{]\s*(?P<repeat>repeat\s+)?'
                         + _NAME + _REP + r'\s*:?\s*[\]\)\}]\s*[*_]*'
                         r'\s*:?\s*(?P<rest>.*)$', re.I)
HDR_COLON = re.compile(_LEAD + r'(?P<repeat>repeat\s+)?' + _NAME + _REP
                       + r'\s*[*_]*\s*:\s*(?P<rest>.*)$', re.I)
HDR_BARE = re.compile(_LEAD + r'\(?(?P<repeat>repeat\s+)?' + _NAME + _REP
                      + r'\s*\)?\s*[*_]*\s*(?P<rest>)$', re.I)
# 'A:' and 'B:' as section letters, the jazz-chart habit; colon only,
# and only with nothing or chords after it
HDR_LETTER = re.compile(r'^\s*\[?(?P<name>[A-H]\d?)\]?\s*:\s*(?P<rest>.*)$')


def header_line(line):
    """A section header -> (label, repeat count, rest of line, marked
    'repeat'); None when the line is not one."""
    for rx in (HDR_BRACKET, HDR_COLON, HDR_BARE):
        m = rx.match(line)
        if m:
            rep = m.group('rep1') or m.group('rep2')
            return (m.group('name'), int(rep) if rep else 1,
                    (m.group('rest') or '').strip(),
                    bool(m.group('repeat')))
    m = HDR_LETTER.match(line)
    if m and (not m.group('rest').strip()
              or is_chord_line(m.group('rest'))):
        return m.group('name'), 1, m.group('rest').strip(), False
    return None


NEUTRAL_RX = re.compile(r'^(?:[|:/.%\-()\[\]]+|\(?[x\u00d7]\d+\)?'
                        r'|\(?\d+[x\u00d7]\)?)$')


def is_chord_line(line):
    """Four in five tokens chords (barlines, slashes, x2 and N.C. are
    allowed company), and at least one real chord."""
    toks = line.replace('|', ' | ').split()
    if not toks:
        return False
    chords = sum(1 for t in toks if chordish(t))
    neutral = sum(1 for t in toks if not chordish(t) and NEUTRAL_RX.match(t))
    return chords >= 1 and chords + neutral >= 0.8 * len(toks)


TAB_LINE = re.compile(r'^\s*[eEBGDA]\s*[|:][-\d|hpbr/\\~x ]{4,}$')


def classify(text):
    """-> 'ireal', 'abc', 'chordpro', 'chordsheet', 'lyrics' or
    'empty'."""
    if not re.search(r'[A-Za-z0-9]', text):
        return 'empty'
    if re.search(r'irealb(?:ook)?://', text):
        return 'ireal'
    if re.search(r'^\s*K:', text, re.M):
        if re.search(r'^\s*X:\s*\d', text, re.M):
            return 'abc'
        if (re.search(r'^\s*[LM]:', text, re.M)
                and re.search(r"^[\s\"A-Ga-gz^_=,'/\d()\[\]|:>\-]*\|",
                              text, re.M)):
            return 'abc'
    if re.search(r'\{\s*(?:title|t|subtitle|st|start_of_chorus|soc'
                 r'|start_of_verse|sov|artist|key)\s*[:}]', text, re.I):
        return 'chordpro'
    brs = re.findall(r'\[([^\]\n]{1,16})\]', text)
    chordy = [b for b in brs if chordish(b)]
    heads = [b for b in brs if not chordish(b) and header_line('[' + b + ']')]
    other = len(brs) - len(chordy) - len(heads)
    if len(chordy) >= 3 and len(chordy) >= 0.8 * (len(chordy) + other):
        return 'chordpro'
    lines = [ln for ln in text.split('\n') if ln.strip()]
    clines = 0
    for ln in lines:
        h = header_line(ln)
        body = h[2] if h else ln
        if body and is_chord_line(body):
            clines += 1
    if clines >= 2 or (clines >= 1 and clines * 2 >= len(lines)):
        return 'chordsheet'
    return 'lyrics'


# =================================================================
# the song dict
# =================================================================

def _new_song(kind, title):
    return {'title': title, 'composer': '', 'key': '', 'meter': (4, 4),
            'tempo': None, 'style': '', 'sections': [], 'melody': None,
            'kind': kind, 'findings': []}


KEY_TEXT = re.compile(r'^\s*([A-Ga-g])\s*(b|#|\u266d|\u266f|flat|sharp)?'
                      r'\s*(m|min|minor|mi|-|maj|major|dorian|mixolydian'
                      r'|lydian|phrygian|aeolian|ionian|locrian)?\b', re.I)


def key_from_text(text):
    """'Bb', 'g minor', 'F#m', 'Eb-' -> 'Bb', 'Gm', 'F#m', 'Ebm';
    '' when it can't be read."""
    m = KEY_TEXT.match(text or '')
    if not m:
        return ''
    root = m.group(1).upper()
    acc = (m.group(2) or '').lower()
    acc = {'\u266d': 'b', 'flat': 'b', '\u266f': '#', 'sharp': '#'}.get(
        acc, acc)
    mode = (m.group(3) or '').lower()
    minor = mode in ('m', 'min', 'minor', 'mi', '-', 'aeolian', 'dorian',
                     'phrygian', 'locrian')
    name = root + acc + ('m' if minor else '')
    try:
        chartc.parse_key(name)
    except SystemExit:
        return ''
    return name


def meter_from_text(text):
    m = re.search(r'(\d+)\s*/\s*(\d+)', text or '')
    if m and int(m.group(1)) > 0 and int(m.group(2)) in (1, 2, 4, 8, 16):
        return int(m.group(1)), int(m.group(2))
    return None


def _beat_value(b):
    """A beat the chart can write: a whole number or an and (x.5)."""
    b = Fraction(b)
    if b.denominator == 1:
        return int(b)
    if b.denominator == 2:
        return float(b)
    return None


def _slots_to_bar(slots, beats, prev):
    """Chords laid across a bar's slots (None is a slash or a dot: the
    chord before it goes on). Positions are stated, so they become
    explicit beats when the chart can write them."""
    chords = [c for c in slots if c]
    if not chords:
        return [(None, prev or 'nc')]
    if all(slots):
        return [(None, c) for c in slots]
    n = len(slots)
    placed = []
    for i, c in enumerate(slots):
        if c:
            bv = _beat_value(1 + Fraction(i * beats, n))
            if bv is None:
                return [(None, c) for c in chords]
            placed.append((bv, c))
    if placed[0][0] != 1:
        placed.insert(0, (1, prev or 'nc'))
    if len(placed) == 1:
        return [(None, placed[0][1])]
    return placed


REPEAT_TAIL = re.compile(r'\s*\(?\s*(?:[x\u00d7]\s*(\d+)|(\d+)\s*[x\u00d7])'
                         r'\s*\)?\s*$')


def chordline_bars(line, beats, ctx, prev=None):
    """One chord line -> bars. Barlines define bars exactly; without
    them, slashes count beats; with neither, each chord gets a bar
    (and the context remembers that bars were assumed)."""
    s = line
    reps = 1
    m = REPEAT_TAIL.search(s)
    if m and s[:m.start()].strip():
        reps = int(m.group(1) or m.group(2))
        s = s[:m.start()]
    s = re.sub(r':?\|+:?', '|', s)
    bars = []
    if '|' in s:
        for g in s.split('|'):
            toks = g.split()
            if not toks:
                continue
            if toks == ['%'] and bars:
                bars.append(list(bars[-1]))
                continue
            slots = []
            for t in toks:
                if t in ('/', '.', '-', '%', '//'):
                    slots.append(None)
                    continue
                sym = ctx.chord(t)
                if sym:
                    slots.append(sym)
            if not any(slots):
                continue
            bar = _slots_to_bar(slots, beats, prev)
            prev = bar[-1][1]
            bars.append(bar)
    else:
        toks = s.split()
        if any(t == '/' for t in toks):
            items = []
            for t in toks:
                if t == '/' and items:
                    items[-1][1] += 1
                elif t != '/':
                    sym = ctx.chord(t)
                    if sym:
                        items.append([sym, 1])
            cur, pos = [], 0
            for sym, d in items:
                while d > 0:
                    cur.append((pos + 1, sym))
                    take = min(d, beats - pos)
                    pos += take
                    d -= take
                    if pos >= beats:
                        bars.append(cur)
                        cur, pos = [], 0
            if cur:
                bars.append(cur)
            bars = [[(None, b[0][1])] if len(b) == 1 else b for b in bars]
        else:
            for t in toks:
                sym = ctx.chord(t)
                if sym:
                    bars.append([(None, sym)])
                    ctx.assumed_bars = True
    return [list(b) for _ in range(reps) for b in bars]


# ---- stanzas -> named sections, shared by ChordPro, chord sheets, lyrics

class _Stanza:
    def __init__(self, label=None, repeat=False):
        self.label, self.repeat = label, repeat
        self.bars, self.words = [], []


def canon_label(raw):
    t = re.sub(r'\s+', ' ', raw.strip()).lower()
    t = re.sub(r'^pre[- ]?chorus', 'pre-chorus', t)
    t = re.sub(r'^post[- ]?chorus', 'post-chorus', t)
    t = re.sub(r'^out[- ]?chorus', 'out-chorus', t)
    m = re.fullmatch(r'section ([a-h])', t)
    if m:
        return m.group(1).upper()
    m = re.fullmatch(r'([a-h]) section', t)
    if m:
        return m.group(1).upper()
    if re.fullmatch(r'[a-h]\d?', t):
        return t.upper()
    return t.title()


def _label_base(label):
    return re.sub(r'\s*\d+$', '', label).strip() or label


def _words_key(s):
    return re.sub(r'\W+', ' ', ' '.join(s.words).lower()).strip()


def finish_sections(stanzas, ctx):
    """Name every stanza: headers win; an unnamed stanza whose words
    come back verbatim is a Chorus; the rest are Verse 1, Verse 2 ...;
    a header with nothing under it repeats the last section of that
    name."""
    st = [s for s in stanzas if s.bars or s.words or s.label]
    for s in st:
        if s.label and not s.bars and not s.words:
            s.repeat = True
    counts = Counter(_words_key(s) for s in st if not s.label and s.words)
    labeled = {}
    for s in st:
        if s.label and s.words and not s.repeat:
            labeled.setdefault(_words_key(s), canon_label(s.label))
    out, used, verse_n, last = [], Counter(), 0, {}

    def assign(label):
        nonlocal verse_n
        m = re.fullmatch(r'(.*?)\s*(\d+)', label)
        if _label_base(label) == 'Verse':
            if m:
                verse_n = max(verse_n, int(m.group(2)))
                name = label
            else:
                verse_n += 1
                name = f'Verse {verse_n}'
        else:
            used[label] += 1
            name = label if used[label] == 1 else f'{label} {used[label]}'
        while any(o['name'] == name for o in out):
            name += "'"
        return name

    for idx, s in enumerate(st):
        if s.repeat:
            base = _label_base(canon_label(s.label))
            src = last.get(base)
            if src is None:
                continue
            out.append({'name': assign(base),
                        'bars': [list(b) for b in src['bars']],
                        'words': src['words']})
            continue
        if s.label:
            label = canon_label(s.label)
        elif s.words:
            k = _words_key(s)
            label = labeled.get(k) or ('Chorus' if counts[k] > 1
                                       else 'Verse')
        else:
            label = ('Intro' if idx == 0 else
                     'Outro' if idx == len(st) - 1 else 'Interlude')
        sec = {'name': assign(label), 'bars': s.bars,
               'words': "\n".join(s.words) if s.words else None}
        out.append(sec)
        last[_label_base(label)] = sec
    return out


def _title_block(lines, song, ctx, kind):
    """A short first block (one line, maybe a 'by' line) above a blank
    line is a title, the way nearly every lyric sheet starts. Returns
    how many lines it used."""
    idx = [i for i, ln in enumerate(lines) if ln.strip()]
    if not idx:
        return 0
    first = idx[0]
    block = []
    for ln in lines[first:]:
        if not ln.strip():
            break
        block.append(ln.strip())
    rest = [ln for ln in lines[first + len(block):] if ln.strip()]
    if not rest or len(block) > 2:
        return 0
    t = block[0]
    if (len(t) > 60 or is_chord_line(t) or header_line(t)
            or META_RX.match(t) or t.endswith((',', ';'))):
        return 0
    comp = None
    if len(block) == 2:
        m = re.match(r'^(?:by|written by|words and music by|music by|'
                     r'artist:|composer:)\s*(.+)$', block[1], re.I)
        if not m:
            return 0
        comp = m.group(1).strip()
    song['title'] = t
    if comp:
        song['composer'] = comp
    return first + len(block)


META_RX = re.compile(r'^\s*(title|artist|composer|by|written by|words and '
                     r'music by|music by|key|capo|tempo|bpm|time signature'
                     r'|time|meter|style|feel)\s*[:=]\s*(.+?)\s*$', re.I)


def _meta_line(ln, song, ctx):
    m = META_RX.match(ln)
    if not m:
        return False
    k, v = m.group(1).lower(), m.group(2)
    if k == 'title':
        song['title'] = v
    elif k in ('artist', 'composer', 'by', 'written by',
               'words and music by', 'music by'):
        song['composer'] = song['composer'] or v
    elif k == 'key':
        song['key'] = key_from_text(v) or song['key']
    elif k == 'capo':
        n = re.search(r'\d+', v)
        if n and int(n.group()):
            ctx.find(f"The sheet says capo {n.group()}; the chords are "
                     "kept as written, so they sound "
                     f"{n.group()} half steps higher.")
    elif k in ('tempo', 'bpm'):
        n = re.search(r'\d+', v)
        if n:
            song['tempo'] = int(n.group())
    elif k in ('time', 'time signature', 'meter'):
        song['meter'] = meter_from_text(v) or song['meter']
    elif k in ('style', 'feel'):
        song['style'] = v
    return True


# =================================================================
# ChordPro
# =================================================================

CP_DIRECTIVE = re.compile(r'^\{\s*([A-Za-z_]+)(?:\s*[:\s]\s*(.*?))?\s*\}$')


def parse_chordpro(text, name_hint='Untitled'):
    song, ctx = _new_song('chordpro', name_hint), _Ctx()
    stanzas, cur, env = [], None, None
    in_tab = in_grid = False

    def start(label=None):
        nonlocal cur
        cur = _Stanza(label)
        stanzas.append(cur)

    def ensure():
        if cur is None:
            start()

    for raw in text.split('\n'):
        s = raw.strip()
        if s.startswith('#'):
            continue            # ChordPro comment
        d = CP_DIRECTIVE.match(s)
        if d:
            name, val = d.group(1).lower(), (d.group(2) or '').strip()
            if name == 'meta' and val:
                name, _, val = val.partition(' ')
                name, val = name.lower(), val.strip()
            if in_tab:
                if name in ('eot', 'end_of_tab'):
                    in_tab = False
                continue
            if name in ('title', 't'):
                song['title'] = val or song['title']
            elif name in ('composer', 'artist', 'subtitle', 'st',
                          'lyricist'):
                if name == 'composer' or not song['composer']:
                    song['composer'] = val
            elif name == 'key':
                song['key'] = key_from_text(val) or song['key']
            elif name == 'tempo':
                n = re.search(r'\d+', val)
                song['tempo'] = int(n.group()) if n else song['tempo']
            elif name == 'time':
                song['meter'] = meter_from_text(val) or song['meter']
            elif name in ('soc', 'start_of_chorus'):
                start(val or 'Chorus')
                env = 'chorus'
            elif name in ('sov', 'start_of_verse'):
                start(val or 'Verse')
                env = 'verse'
            elif name in ('sob', 'start_of_bridge'):
                start(val or 'Bridge')
                env = 'bridge'
            elif name in ('sot', 'start_of_tab'):
                in_tab = True
            elif name in ('sog', 'start_of_grid'):
                start(val or None)
                env, in_grid = 'grid', True
            elif name.startswith('start_of_'):
                start(val or name[9:].replace('_', ' '))
                env = name[9:]
            elif name in ('eoc', 'eov', 'eob', 'eog') or \
                    name.startswith('end_of_'):
                cur, env, in_grid = None, None, False
            elif name == 'chorus':
                stanzas.append(_Stanza(val or 'Chorus', repeat=True))
                cur = None
            elif name in ('c', 'comment', 'ci', 'comment_italic', 'cb',
                          'comment_box', 'highlight'):
                h = header_line(val)
                if h:
                    if h[3]:
                        stanzas.append(_Stanza(h[0], repeat=True))
                        cur = None
                    else:
                        start(h[0])
            continue
        if in_tab:
            continue
        if not s:
            if env is None and cur is not None and (cur.bars or cur.words):
                cur = None
            continue
        if TAB_LINE.match(s):
            continue
        beats = song['meter'][0]
        if in_grid:
            ensure()
            prev = cur.bars[-1][-1][1] if cur.bars else None
            cur.bars += chordline_bars(s, beats, ctx, prev)
            continue
        if '[' not in s:
            h = header_line(s)
            if h and (not h[2] or is_chord_line(h[2])):
                if h[3]:
                    stanzas.append(_Stanza(h[0], repeat=True))
                    cur = None
                    continue
                start(h[0])
                if h[2]:
                    cur.bars += chordline_bars(h[2], beats, ctx)
                continue
        ensure()
        for ch in re.findall(r'\[([^\]]*)\]', s):
            ch = ch.strip()
            if not ch or ch.startswith('*'):
                continue            # [*Riff] is an annotation, not a chord
            sym = ctx.chord(ch)
            if sym:
                cur.bars.append([(None, sym)])
                ctx.assumed_bars = True
        words = re.sub(r'\s+', ' ', re.sub(r'\[[^\]]*\]', '', s)).strip()
        if words and re.search(r'\w', words):
            cur.words.append(words)
    song['sections'] = finish_sections(stanzas, ctx)
    song['findings'] = ctx.finish()
    return song


# =================================================================
# chord sheets (chords over words) and plain lyrics
# =================================================================

def parse_chordsheet(text, name_hint='Untitled', kind='chordsheet'):
    song, ctx = _new_song(kind, name_hint), _Ctx()
    lines = text.split('\n')
    lines = [ln for ln in lines if not _meta_line(ln, song, ctx)] \
        if kind == 'chordsheet' else lines
    used = _title_block(lines, song, ctx, kind)
    if used:
        ctx.find(f"The first line, {song['title']}, was taken as the "
                 "title.")
    stanzas, cur = [], None
    seen = set()

    def start(label=None):
        nonlocal cur
        cur = _Stanza(label)
        stanzas.append(cur)

    def ensure():
        if cur is None:
            start()

    for ln in lines[used:]:
        s = ln.strip()
        if not s:
            if cur is None:
                continue
            if cur.bars or cur.words:
                if cur.label:
                    seen.add(_label_base(canon_label(cur.label)))
                cur = None
            elif cur.label and _label_base(canon_label(cur.label)) in seen:
                # 'Chorus' alone above a blank line, after a chorus was
                # already written out: an instruction to sing it again
                cur.repeat = True
                cur = None
            continue
        if kind == 'chordsheet' and TAB_LINE.match(s):
            continue
        h = header_line(s)
        if h and (not h[2] or kind == 'lyrics' or is_chord_line(h[2])
                  or h[0].lower() not in ('break', 'solo', 'tag', 'hook',
                                          'link', 'riff', 'head')):
            if cur is not None and cur.label and not (cur.bars or
                                                      cur.words):
                cur.repeat = True
            if cur is not None and cur.label and (cur.bars or cur.words):
                seen.add(_label_base(canon_label(cur.label)))
            if h[3]:
                stanzas.append(_Stanza(h[0], repeat=True))
                cur = None
                continue
            start(h[0])
            if h[1] > 1:
                ctx.find(f"{canon_label(h[0])} is marked to play "
                         f"{h[1]} times; it was written once.",
                         key='times-' + h[0].lower())
            if h[2]:
                if kind == 'chordsheet' and is_chord_line(h[2]):
                    cur.bars += chordline_bars(h[2], song['meter'][0], ctx)
                else:
                    cur.words.append(h[2])
            continue
        if re.fullmatch(r'\(?\s*(?:repeat|rpt\.?)\s*(?:x\s*\d+)?\s*\)?', s,
                        re.I):
            continue
        ensure()
        if kind == 'chordsheet' and is_chord_line(s):
            prev = cur.bars[-1][-1][1] if cur.bars else None
            cur.bars += chordline_bars(s, song['meter'][0], ctx, prev)
        else:
            w = REPEAT_TAIL.sub('', s) if REPEAT_TAIL.search(s) and \
                re.search(r'[a-z]', s) else s
            cur.words.append(w.strip())
    song['sections'] = finish_sections(stanzas, ctx)
    if kind == 'lyrics':
        for sec in song['sections']:
            sec['bars'] = []
    song['findings'] = ctx.finish()
    return song


def parse_lyrics(text, name_hint='Untitled'):
    return parse_chordsheet(text, name_hint, kind='lyrics')


# =================================================================
# repeats: shared by iReal and ABC
# =================================================================

def _propagate_endings(bars):
    """An ending starts on a marked bar and runs until a repeat sign, a
    double bar, a new section, or another ending."""
    cur = None
    for b in bars:
        if b.get('ending_start'):
            cur = b['ending_start']
        elif b.get('rstart') or b.get('mark'):
            cur = None
        b['ending'] = cur
        if b.get('rend') or b.get('hard'):
            cur = None


def _expand(bars, ctx):
    """Play the repeats in order and return the bars as heard. The
    chart's own repeat signs can be put back at the editing desk; the
    form reading straight through is the safe starting point."""
    _propagate_endings(bars)
    out, i, rs, pass_n = [], 0, 0, 1
    done, region_end, guard = set(), -1, 0
    n = len(bars)
    had_repeat = had_ending = False
    while i < n:
        guard += 1
        if guard > 50 * n + 100:
            break
        b = bars[i]
        if b['ending'] is None and pass_n > 1 and i > region_end:
            rs, pass_n = i, 1
        if b.get('rstart') and i != rs:
            rs, pass_n = i, 1
        if b['ending'] is not None and pass_n not in b['ending']:
            i += 1
            continue
        out.append(b)
        if b.get('rend') and i not in done:
            done.add(i)
            region_end = max(region_end, i)
            had_repeat = True
            had_ending = had_ending or b['ending'] is not None
            i, pass_n = rs, pass_n + 1
            continue
        i += 1
    if had_repeat:
        ctx.find("Repeats were written out in full, so the form reads "
                 "straight through.")
    if had_ending:
        ctx.find("First and second endings were written out one after "
                 "the other.")
    return out


def _group_sections(bars, default='A'):
    secs = []
    for b in bars:
        if b.get('mark') or not secs:
            secs.append({'name': b.get('mark') or default, 'bars': [],
                         'words': None})
        secs[-1]['bars'].append(list(b['chords']))
    return secs


# =================================================================
# iReal Pro
# =================================================================

IREAL_PREFIX = '1r34LbKcu7'
IREAL_MARKS = {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D', 'V': 'Verse',
               'i': 'Intro'}
IREAL_CHORD = re.compile(r'([A-GW])([b#]?)((?:sus|alt|add|[+\-\^\dhob#])*)'
                         r'(\*[^*|]{0,20}\*)?(/[A-G][b#]?)?')


def _obfusc50(s):
    """iReal's swap inside one 50-character chunk: positions 0-4 trade
    with 49-45, and 10-23 with 39-26. It undoes itself."""
    c = list(s)
    for i in range(5):
        c[i], c[49 - i] = s[49 - i], s[i]
    for i in range(10, 24):
        c[i], c[49 - i] = s[49 - i], s[i]
    return "".join(c)


def ireal_unscramble(s):
    """The music field without its 1r34LbKcu7 prefix -> iReal's own
    chart string. Whole 50-character chunks are swapped while more than
    51 characters remain, which is how the app and every published
    reader (pianosnake's ireal-reader, infojunkie's ireal-musicxml) do
    it; the tail is left as it is."""
    r = []
    while len(s) > 51:
        r.append(_obfusc50(s[:50]))
        s = s[50:]
    return "".join(r) + s


def ireal_scramble(s):
    """The inverse, for building test links: the swap is its own
    inverse and the chunking depends only on length."""
    return ireal_unscramble(s)


def _ireal_expand_tokens(music):
    return (music.replace('Kcl', '| x').replace('LZ', ' |')
            .replace('XyQ', '   '))


def ireal_links(text):
    """Every song in every iReal link in the text -> list of
    (scheme, song string)."""
    songs = []
    for link in IREAL_LINK.findall(html.unescape(text)):
        scheme, _, body = link.partition('://')
        body = unquote(body)
        for part in body.split('==='):
            if scheme == 'irealb' and IREAL_PREFIX not in part:
                continue        # the playlist's own name
            if scheme == 'irealbook' and part.count('=') < 5:
                continue
            songs.append((scheme, part))
    return songs


def _ireal_composer(c):
    c = c.strip()
    if c.lower() in ('composer unknown', 'unknown composer', 'unknown',
                     ''):
        return ''
    w = c.split()
    # iReal stores 'Kosma Joseph'; the page wants 'Joseph Kosma'
    if len(w) == 2 and not re.search(r'[&,/-]', c):
        return w[1] + ' ' + w[0]
    return c


def parse_ireal_song(scheme, part, ctx, name_hint='Untitled'):
    song = _new_song('ireal', name_hint)
    f = part.split('=')
    if scheme == 'irealb':
        mi = next(i for i, x in enumerate(f) if x.startswith(IREAL_PREFIX))
        music = ireal_unscramble(f[mi][len(IREAL_PREFIX):])
        mid = [x for x in f[2:mi] if x.strip()]
        after = f[mi + 1:]
    else:
        # irealbook://Title=Composer=Style=Key=n=music, never scrambled
        mi = 5 if len(f) > 5 else len(f) - 1
        music = f[mi]
        mid = [x for x in f[2:mi] if x.strip() and x != 'n']
        after = f[mi + 1:]
    song['title'] = f[0].strip() or name_hint
    song['composer'] = _ireal_composer(f[1]) if len(f) > 1 and mi > 1 \
        else ''
    keyf = [x for x in mid if re.fullmatch(r'[A-G][b#]?-?', x.strip())]
    if keyf:
        k = keyf[0].strip()
        song['key'] = key_from_text(k[:-1] + 'm' if k.endswith('-') else k)
    style = [x for x in mid if x not in keyf]
    song['style'] = style[0].strip() if style else ''
    for x in after:
        if x.strip().isdigit() and 40 <= int(x) <= 400:
            song['tempo'] = int(x)
            break
    bars, meter = _ireal_bars(_ireal_expand_tokens(music), ctx)
    song['meter'] = meter
    played = _expand(bars, ctx)
    song['sections'] = _group_sections(played, 'A')
    return song


def _ireal_bars(m, ctx):
    """iReal's chart string -> bar dicts with resolved chords."""
    bars = []
    comments, jumps, unknown = [], False, 0

    def new():
        return {'slots': [], 'mark': None, 'rstart': False, 'rend': False,
                'hard': False, 'ending_start': None, 'meter': None}
    cur = new()

    def close(ch):
        nonlocal cur
        if cur['slots']:
            if ch == '}':
                cur['rend'] = True
            if ch in ']Z':
                cur['hard'] = True
            bars.append(cur)
            cur = new()
        else:
            if ch == '}' and bars:
                bars[-1]['rend'] = True
            if ch in ']Z' and bars:
                bars[-1]['hard'] = True
        if ch == '{':
            cur['rstart'] = True

    i, n = 0, len(m)
    while i < n:
        c = m[i]
        if c in ' ,\t\n':
            i += 1
        elif c == '<':
            j = m.find('>', i)
            j = n if j < 0 else j
            comments.append(m[i + 1:j])
            i = j + 1
        elif c == '(':
            j = m.find(')', i)      # an alternate chord: leave it out
            i = n if j < 0 else j + 1
        elif c == '*' and i + 1 < n and m[i + 1] in IREAL_MARKS:
            cur['mark'] = IREAL_MARKS[m[i + 1]]
            i += 2
        elif c == 'T' and re.match(r'T\d\d', m[i:i + 3]):
            d = m[i + 1:i + 3]
            cur['meter'] = (12, 8) if d == '12' else (int(d[0]), int(d[1]))
            i += 3
        elif c == 'N' and i + 1 < n and m[i + 1].isdigit():
            cur['ending_start'] = {int(m[i + 1])} if m[i + 1] != '0' \
                else None
            i += 2
        elif c in '|[]{}Z':
            close(c)
            i += 1
        elif c in 'QS':
            jumps = True
            i += 1
        elif c in 'fYUsl':
            i += 1              # fermata, spacers, end, chord size
        elif c in 'xrnp':
            cur['slots'].append((c,))
            i += 1
        else:
            mm = IREAL_CHORD.match(m, i)
            if mm and mm.end() > i:
                root, acc, qual, custom, bass = mm.groups()
                if custom:
                    qual = qual + custom.strip('*')
                cur['slots'].append(('chord', root + acc, qual,
                                     (bass or '')[1:]))
                i = mm.end()
            else:
                unknown += 1
                i += 1
    close('|')

    # resolve slots into chords, bar by bar in written order
    meter = next((b['meter'] for b in bars if b['meter']), (4, 4))
    beats, prev, prev_bar, out = meter[0], None, None, []
    for b in bars:
        if b['meter']:
            if b['meter'] != meter:
                ctx.find(f"The meter changes to {b['meter'][0]}/"
                         f"{b['meter'][1]} partway through; the chart "
                         f"keeps {meter[0]}/{meter[1]} for now, so say "
                         "the change at the editing desk.",
                         key='meter-change')
            beats = b['meter'][0]
        slots = b['slots']
        kinds = [s[0] for s in slots]
        if kinds == ['r'] and len(out) >= 2:
            two = [out[-2], out[-1]]
            for k, src in enumerate(two):
                nb = dict(b)
                nb['chords'] = list(src['chords'])
                if k == 0:
                    nb['rend'] = nb['hard'] = False
                else:
                    nb['mark'] = None
                    nb['rstart'] = False
                    nb['ending_start'] = None
                out.append(nb)
            continue
        if 'x' in kinds:
            chords = list(prev_bar) if prev_bar else [(None, 'nc')]
        else:
            flat = []
            for s in slots:
                if s[0] == 'chord':
                    root, qual, bass = s[1], s[2], s[3]
                    if root == 'W':
                        if bass and prev:
                            flat.append(prev.split('/')[0] + '/' + bass)
                        else:
                            flat.append(None)
                        continue
                    sym = ctx.chord(root + qual + ('/' + bass if bass
                                                   else ''))
                    flat.append(sym)
                    if sym:
                        prev = sym
                elif s[0] == 'n':
                    flat.append('nc')
                elif s[0] == 'p':
                    flat.append(None)
                else:
                    flat.append(None)
            if not any(flat):
                chords = [(None, prev or 'nc')]
            else:
                chords = _slots_to_bar(flat, beats, prev_bar[-1][1]
                                       if prev_bar else prev)
        for _, sym in chords:
            if sym != 'nc':
                prev = sym
        nb = dict(b)
        nb['chords'] = chords
        out.append(nb)
        prev_bar = chords
    text = " ".join(comments).lower()
    if jumps or re.search(r'd\.?\s?[cs]\.?|coda|segno|fine', text):
        ctx.find("The chart has a D.C., D.S. or coda jump; the bars are "
                 "written in page order and the jump isn't taken.")
    if unknown:
        ctx.find(f"{unknown} symbol{'s' if unknown != 1 else ''} in the "
                 "chart weren't understood and were skipped.")
    return out, meter


def parse_ireal_all(text, name_hint='Untitled'):
    songs = []
    for scheme, part in ireal_links(text):
        ctx = _Ctx()
        try:
            s = parse_ireal_song(scheme, part, ctx, name_hint)
        except (StopIteration, ValueError, IndexError):
            continue
        s['findings'] = ctx.finish()
        songs.append(s)
    return songs


# =================================================================
# ABC notation
# =================================================================

ABC_NOTE = re.compile(r"(\^\^|\^|__|_|=)?([A-Ga-g])([',]*)(\d*/*\d*)")
ABC_REST = re.compile(r"([zx])(\d*/*\d*)")
ABC_MREST = re.compile(r"([ZX])(\d*)")
ABC_BAR = re.compile(r"(:*)(\[\||\|\]|\|\||\||::)(:*)")
ABC_ENDING = re.compile(r"\s*\[?(\d+(?:[,-]\d+)*)")
ABC_INLINE = re.compile(r"\[([A-Za-z]):([^\]]*)\]")
STEP_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
MAJOR_FIFTHS = {'C': 0, 'G': 1, 'D': 2, 'A': 3, 'E': 4, 'B': 5, 'F#': 6,
                'C#': 7, 'F': -1, 'Bb': -2, 'Eb': -3, 'Ab': -4, 'Db': -5,
                'Gb': -6, 'Cb': -7, 'G#': 8, 'D#': 9, 'A#': 10, 'E#': 11,
                'Fb': -8}
MODE_SHIFT = {'': 0, 'maj': 0, 'ion': 0, 'm': -3, 'min': -3, 'aeo': -3,
              'dor': -2, 'phr': -4, 'lyd': 1, 'mix': -1, 'loc': -5}
MODE_NAME = {'dor': 'dorian', 'phr': 'phrygian', 'lyd': 'lydian',
             'mix': 'mixolydian', 'loc': 'locrian'}
MAJOR_BY_FIFTHS = {v: k for k, v in MAJOR_FIFTHS.items() if -7 <= v <= 7}
MINOR_BY_FIFTHS = {-7: 'Abm', -6: 'Ebm', -5: 'Bbm', -4: 'Fm', -3: 'Cm',
                   -2: 'Gm', -1: 'Dm', 0: 'Am', 1: 'Em', 2: 'Bm', 3: 'F#m',
                   4: 'C#m', 5: 'G#m', 6: 'D#m', 7: 'A#m'}


def _abc_key(val, ctx=None):
    """K: text -> (key name for the chart, signature {step: alter}).
    A modal key keeps its signature: D dorian prints with no sharps or
    flats, so the chart's key is the major or minor that shares it."""
    v = val.strip()
    m = re.match(r'([A-G])([b#]?)\s*([A-Za-z]*)', v)
    if not m or v.lower().startswith(('none', 'hp')):
        return ('', {})
    root = m.group(1) + m.group(2)
    mode = m.group(3).lower()[:3]
    if mode.startswith('m') and mode not in ('maj', 'mix', 'min'):
        mode = 'm'
    shift = MODE_SHIFT.get(mode, 0)
    fifths = MAJOR_FIFTHS.get(root, 0) + shift
    if not -7 <= fifths <= 7:
        return ('', {})
    minorish = mode in ('m', 'min', 'aeo', 'dor', 'phr', 'loc')
    name = (MINOR_BY_FIFTHS if minorish else MAJOR_BY_FIFTHS)[fifths]
    if mode in MODE_NAME and ctx is not None:
        ctx.find(f"The tune is in {root} {MODE_NAME[mode]}; the chart's "
                 f"key is written as {name}, which has the same key "
                 "signature.", key='mode')
    sig = {}
    if fifths > 0:
        for s in 'FCGDAEB'[:fifths]:
            sig[s] = 1
    elif fifths < 0:
        for s in 'BEADGCF'[:-fifths]:
            sig[s] = -1
    return name, sig


def _abc_meter(val):
    v = val.strip()
    if v == 'C':
        return (4, 4)
    if v == 'C|':
        return (2, 2)
    m = re.match(r'\(?([\d+]+)\)?\s*/\s*(\d+)', v)
    if m:
        return (sum(int(x) for x in m.group(1).split('+') if x),
                int(m.group(2)))
    return None


def _abc_len(spec):
    m = re.fullmatch(r'(\d*)(/*)(\d*)', spec or '')
    if not m:
        return Fraction(1)
    num = int(m.group(1)) if m.group(1) else 1
    if m.group(2):
        den = int(m.group(3)) if m.group(3) else 2 ** len(m.group(2))
    else:
        den = 1
    return Fraction(num, den)


def _abc_tempo(val):
    m = re.search(r'(\d+)/(\d+)\s*=\s*(\d+)', val)
    if m:
        return round(int(m.group(3)) * Fraction(int(m.group(1)),
                                                int(m.group(2))) * 4)
    m = re.search(r'=\s*(\d+)', val) or re.fullmatch(r'\s*(\d+)\s*', val)
    return int(m.group(1)) if m else None


def _abc_tunes(text):
    """The tunes in a file: each starts at X: and ends at a blank line
    that isn't followed by more music (ABC's own rule, forgiving of a
    blank line inside a tune)."""
    lines = text.split('\n')
    starts = [i for i, ln in enumerate(lines)
              if re.match(r'\s*X:\s*\d', ln)]
    if not starts:
        starts = [0]
    tunes = []
    for n, s in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        body, seen_k = [], False
        for j in range(s, end):
            ln = lines[j]
            if re.match(r'\s*K:', ln):
                seen_k = True
            if not ln.strip() and seen_k:
                nxt = next((x for x in lines[j + 1:end] if x.strip()), '')
                if not (re.match(r'\s*[A-Za-z]:', nxt) or '|' in nxt):
                    break
            body.append(ln)
        if seen_k:
            tunes.append(body)
    return tunes


def parse_abc_all(text, name_hint='Untitled'):
    tunes = _abc_tunes(text.replace('\u201c', '"').replace('\u201d', '"')
                       .replace('\u2019', "'"))
    return [parse_abc_tune(t, name_hint) for t in tunes]


def parse_abc_tune(lines, name_hint='Untitled'):
    ctx = _Ctx()
    song = _new_song('abc', name_hint)
    meter, unit, sig = None, None, {}
    title = composer = None
    header_order = None
    voices_declared = []
    body_start = len(lines)
    for i, ln in enumerate(lines):
        m = re.match(r'\s*([A-Za-z]):(.*)$', ln)
        if not m:
            continue
        f, v = m.group(1), m.group(2).strip()
        if f == 'T' and title is None:
            title = v
        elif f == 'C':
            composer = v if composer is None else composer + ' and ' + v
        elif f == 'M':
            meter = _abc_meter(v)
        elif f == 'L':
            unit = _abc_len(v.strip())
        elif f == 'Q':
            song['tempo'] = _abc_tempo(v)
        elif f == 'R':
            song['style'] = v
        elif f == 'P':
            header_order = v
        elif f == 'V':
            voices_declared.append(v.split()[0] if v.split() else v)
        elif f == 'K':
            song['key'], sig = _abc_key(v, ctx)
            body_start = i + 1
            break
    song['title'] = title or name_hint
    song['composer'] = composer or ''
    song['meter'] = meter or (4, 4)
    if unit is None:
        m_num, m_den = song['meter']
        unit = Fraction(1, 16) if Fraction(m_num, m_den) < Fraction(3, 4) \
            else Fraction(1, 8)
    if header_order and len(header_order.replace('.', '').strip()) > 1:
        ctx.find(f"The tune's part order is {header_order.strip()}; the "
                 "parts are written in page order, once each.")

    st = {
        'unit': unit, 'meter': song['meter'], 'sig': sig, 'bar_acc': {},
        'bars': [], 'cur': None, 'tup_left': 0, 'tup_factor': Fraction(1),
        'broken': None, 'last': None, 'next': {}, 'voice_ok': True,
        'grace': False, 'overlay': False, 'first_key': song['key'],
        'first_meter': song['meter'],
    }
    chosen = voices_declared[0] if voices_declared else None
    cur_voice = chosen
    voices = set(voices_declared)
    lyrics, words = [], []

    def newbar():
        b = {'notes': [], 'chords': [], 'mark': None, 'rstart': False,
             'rend': False, 'hard': False, 'ending_start': None}
        b.update(st['next'])
        st['next'] = {}
        st['cur'] = b
    newbar()

    def close_bar(rend=False, hard=False, rstart=False):
        cur = st['cur']
        if cur['notes'] or cur['chords']:
            cur['rend'] |= rend
            cur['hard'] |= hard
            st['bars'].append(cur)
            newbar()
        else:
            if rend and st['bars']:
                st['bars'][-1]['rend'] = True
            if hard and st['bars']:
                st['bars'][-1]['hard'] = True
        if rstart:
            st['cur']['rstart'] = True
        st['bar_acc'] = {}

    def set_mark(name):
        if st['cur']['notes']:
            st['next']['mark'] = name
        else:
            st['cur']['mark'] = name

    def field(f, v):
        nonlocal cur_voice, chosen
        if f == 'K':
            k, s = _abc_key(v, ctx)
            st['sig'] = s
            if k and k != st['first_key']:
                ctx.find(f"The key changes to {k} partway through; the "
                         "chart keeps the first key for now.",
                         key='key-change')
        elif f == 'M':
            mt = _abc_meter(v)
            if mt and mt != st['first_meter']:
                ctx.find(f"The meter changes to {mt[0]}/{mt[1]} partway "
                         "through; the chart keeps the first meter for "
                         "now.", key='meter-change')
            if mt:
                st['meter'] = mt
        elif f == 'L':
            st['unit'] = _abc_len(v.strip())
        elif f == 'P' and st['voice_ok']:
            set_mark(v.strip() or None)
        elif f == 'T' and st['voice_ok'] and v.strip():
            set_mark(v.strip())
        elif f == 'V':
            vid = v.split()[0] if v.split() else v
            voices.add(vid)
            if chosen is None and not st['bars'] and \
                    not st['cur']['notes']:
                chosen = vid
            cur_voice = vid
            st['voice_ok'] = (cur_voice == chosen)

    def add_note(midi, q):
        if st['tup_left']:
            q *= st['tup_factor']
            st['tup_left'] -= 1
        if st['broken'] and st['last'] is not None:
            ch, k = st['broken']
            f = Fraction(1, 2 ** k)
            if ch == '>':
                st['last']['q'] *= (2 - f)
                q *= f
            else:
                st['last']['q'] *= f
                q *= (2 - f)
        st['broken'] = None
        note = {'q': q, 'midi': midi, 'tie': False}
        st['cur']['notes'].append(note)
        st['last'] = note

    def pitch(acc, letter, octs):
        base = 60 + STEP_PC[letter.upper()] + (12 if letter.islower()
                                                else 0)
        base += 12 * octs.count("'") - 12 * octs.count(',')
        key = (letter.upper(), base)
        if acc:
            alt = {'^': 1, '^^': 2, '_': -1, '__': -2, '=': 0}[acc]
            st['bar_acc'][key] = alt
        else:
            alt = st['bar_acc'].get(key, st['sig'].get(letter.upper(), 0))
        return base + alt

    def music(s):
        i, n = 0, len(s)
        while i < n:
            c = s[i]
            if c == '[' and s.startswith('[V:', i):
                mm = ABC_INLINE.match(s, i)
                if mm:
                    field('V', mm.group(2))
                    i = mm.end()
                    continue
            if not st['voice_ok']:
                i += 1
                continue
            if c in ' \t`$\\y':
                i += 1
            elif c == '%':
                break
            elif c == '"':
                j = s.find('"', i + 1)
                j = n if j < 0 else j
                txt = s[i + 1:j]
                i = j + 1
                if txt and txt[0] not in '^_<>@':
                    txt = re.sub(r'\([A-G].*$', '', txt).strip()
                    sym = ctx.chord(txt) if txt else None
                    if sym:
                        st['cur']['chords'].append(
                            (len(st['cur']['notes']), sym))
            elif c == '!':
                j = s.find('!', i + 1)
                i = n if j < 0 else j + 1
            elif c == '+' and re.match(r'\+[A-Za-z]', s[i:i + 2]):
                j = s.find('+', i + 1)
                i = n if j < 0 else j + 1
            elif c == '{':
                j = s.find('}', i)
                i = n if j < 0 else j + 1
                if not st['grace']:
                    st['grace'] = True
                    ctx.find("Grace notes were left out of the melody.")
            elif c == '[':
                mm = ABC_INLINE.match(s, i)
                if mm:
                    field(mm.group(1), mm.group(2))
                    i = mm.end()
                    continue
                mm = re.match(r'\[(\d+(?:[,-]\d+)*)', s[i:])
                if mm:
                    st['cur']['ending_start'] = _ending_set(mm.group(1))
                    i += mm.end()
                    continue
                if s.startswith('[|', i):
                    i = bar(s, i)
                    continue
                mm = re.match(r'\[([^\]]*)\]', s[i:])
                if not mm:
                    i += 1
                    continue
                inner = ABC_NOTE.findall(mm.group(1))
                j = i + mm.end()
                mult = re.match(r'\d*/*\d*', s[j:]).group()
                j += len(mult)
                if inner:
                    top = max(pitch(a, l, o) for a, l, o, _ in inner)
                    q = st['unit'] * _abc_len(inner[0][3]) * \
                        _abc_len(mult) * 4
                    add_note(top, q)
                i = j
            elif c in '|:' or (c == ']' and s.startswith('|]', i - 1)):
                i = bar(s, i)
            elif c == '(':
                mm = re.match(r'\((\d)(?::(\d*))?(?::(\d*))?', s[i:])
                if mm:
                    p = int(mm.group(1))
                    num = st['meter'][0]
                    compound = num % 3 == 0 and num > 3
                    qd = {2: 3, 3: 2, 4: 3, 6: 2, 8: 3}.get(
                        p, 3 if compound else 2)
                    q = int(mm.group(2)) if mm.group(2) else qd
                    r = int(mm.group(3)) if mm.group(3) else p
                    st['tup_factor'] = Fraction(q, p)
                    st['tup_left'] = r
                    i += mm.end()
                else:
                    i += 1          # a slur: phrasing, not rhythm
            elif c == ')':
                i += 1
            elif c == '-':
                if st['last'] is not None:
                    st['last']['tie'] = True
                i += 1
            elif c in '<>':
                k = 1
                while i + k < n and s[i + k] == c:
                    k += 1
                st['broken'] = (c, k)
                i += k
            elif c == '&':
                if not st['overlay']:
                    st['overlay'] = True
                    ctx.find("A second voice inside the melody's bars was "
                             "left out.")
                # an overlay's notes run to the next barline
                j = s.find('|', i)
                i = n if j < 0 else j
            elif c in 'zx':
                mm = ABC_REST.match(s, i)
                add_note(None, st['unit'] * _abc_len(mm.group(2)) * 4)
                i = mm.end()
            elif c in 'ZX':
                mm = ABC_MREST.match(s, i)
                k = int(mm.group(2)) if mm.group(2) else 1
                full = Fraction(st['meter'][0] * 4, st['meter'][1])
                for r in range(k):
                    if r:
                        close_bar()
                    add_note(None, full)
                i = mm.end()
            elif c in '^_=' or c in 'ABCDEFGabcdefg':
                mm = ABC_NOTE.match(s, i)
                if not mm:
                    i += 1
                    continue
                acc, letter, octs, ln = mm.groups()
                midi = pitch(acc, letter, octs)
                add_note(midi, st['unit'] * _abc_len(ln) * 4)
                i = mm.end()
            else:
                i += 1          # decorations .~HLMOPSTuv and the rest

    def bar(s, i):
        mm = ABC_BAR.match(s, i)
        if not mm:
            return i + 1
        tok = mm.group(0)
        rend = tok.startswith(':')
        rstart = tok.endswith(':')
        hard = any(x in tok for x in ('||', '|]', '[|'))
        close_bar(rend=rend, hard=hard, rstart=rstart)
        j = mm.end()
        em = ABC_ENDING.match(s, j)
        if em and (s[j:em.end()].strip().startswith('[') or
                   s[j:j + 1].isdigit()):
            st['cur']['ending_start'] = _ending_set(em.group(1))
            j = em.end()
        return j

    for ln in lines[body_start:]:
        raw = re.sub(r'(?<!\\)%.*$', '', ln)
        if not raw.strip():
            continue
        m = re.match(r'\s*([A-Za-z]):(.*)$', raw)
        if m and not re.match(r'\s*[A-Ga-g]:[|]', raw):
            f, v = m.group(1), m.group(2)
            if f == 'w':
                if st['voice_ok']:
                    lyrics.append(v)
            elif f == 'W':
                words.append(v.strip())
            else:
                field(f, v)
            continue
        music(raw)
    close_bar()

    written = st['bars']
    if not written:
        song['findings'] = ctx.finish() + ["The tune has no notes that I "
                                           "could read."]
        return song
    if len(voices) > 1:
        ctx.find(f"The tune has {len(voices)} voices; the first one was "
                 "taken as the melody.")
    full = Fraction(song['meter'][0] * 4, song['meter'][1])
    first_len = sum(nt['q'] for nt in written[0]['notes'])
    pickup = None
    if len(written) > 1 and 0 < first_len < full:
        pickup = first_len
        ctx.find(f"The tune starts with a pickup of {_quarters_words(first_len)}"
                 "; it was kept as a short first bar.")
    played = _expand(written, ctx)

    # melody: flat, with ties merged into one longer note
    notes, tie_open = [], False
    for b in played:
        for nt in b['notes']:
            if (tie_open and notes and nt['midi'] is not None
                    and notes[-1][1] == nt['midi']):
                notes[-1] = (notes[-1][0] + nt['q'], nt['midi'])
            else:
                notes.append((Fraction(nt['q']), nt['midi']))
            tie_open = nt['tie']
    lyr = " ".join(_abc_lyric(x) for x in lyrics).strip() or None
    song['melody'] = {'notes': notes, 'lyrics': lyr}
    if pickup is not None:
        song['melody']['pickup_quarters'] = pickup

    # chords: one list per played bar, the harmony carried across bars
    # that name none
    den = song['meter'][1]
    any_chord = any(b['chords'] for b in played)
    prev = 'nc'
    for b in played:
        placed = {}
        for idx, sym in b['chords']:
            pos = sum((nt['q'] for nt in b['notes'][:idx]), Fraction(0))
            beat = 1 + pos * Fraction(den, 4)
            bv = _beat_value(beat) or _beat_value(Fraction(round(beat * 2),
                                                           2))
            if bv is None or bv >= song['meter'][0] + 1:
                continue
            placed[bv] = sym
        items = sorted(placed.items())
        if not items or items[0][0] != 1:
            items.insert(0, (1, prev))
        if len(items) == 1:
            b['chords_out'] = [(None, items[0][1])]
        else:
            b['chords_out'] = [(bb, sym) for bb, sym in items]
        prev = items[-1][1]
    if not any_chord:
        ctx.find("The tune has no chord symbols, so every bar reads no "
                 "chord.")
    has_marks = any(b['mark'] for b in played)
    secs = []
    for b in played:
        if b['mark'] or not secs:
            secs.append({'name': b['mark'] or ('Intro' if has_marks
                                               else 'A'),
                         'bars': [], 'words': None})
        secs[-1]['bars'].append(list(b['chords_out']))
    if words:
        secs[0]['words'] = "\n".join(w for w in words if w)
    song['sections'] = secs
    song['findings'] = ctx.finish()
    return song


def _ending_set(text):
    out = set()
    for part in text.split(','):
        if '-' in part:
            a, b = part.split('-', 1)
            if a.isdigit() and b.isdigit():
                out.update(range(int(a), int(b) + 1))
        elif part.isdigit():
            out.add(int(part))
    return out or None


def _abc_lyric(s):
    s = s.replace('\\-', '\x00').replace('~', ' ').replace('_', '')
    s = s.replace('*', '').replace('|', ' ')
    s = re.sub(r'\s*-\s*', '-', s).replace('\x00', '-')
    return re.sub(r'\s+', ' ', s).strip()


def _quarters_words(q):
    q = Fraction(q)
    if q == 1:
        return "one beat"
    if q.denominator == 1:
        return f"{q} beats"
    return {Fraction(1, 2): "an eighth", Fraction(3, 2): "a beat and a "
            "half", Fraction(1, 4): "a sixteenth"}.get(
                q, f"{float(q):g} beats")


# =================================================================
# the front door
# =================================================================

def parse_all(text, name_hint='Untitled'):
    """Every song in the text: a playlist link or a many-tune ABC file
    gives several; anything else gives one."""
    text = normalize_text(text)
    kind = classify(text)
    if kind == 'ireal':
        songs = parse_ireal_all(text, name_hint)
        if not songs:
            s = _new_song('ireal', name_hint)
            s['findings'] = ["The iReal Pro link is damaged, and I couldn't "
                             "read a song from it."]
            songs = [s]
    elif kind == 'abc':
        songs = parse_abc_all(text, name_hint) or [_new_song('abc',
                                                             name_hint)]
    elif kind == 'chordpro':
        songs = [parse_chordpro(text, name_hint)]
    elif kind == 'chordsheet':
        songs = [parse_chordsheet(text, name_hint)]
    elif kind == 'lyrics':
        songs = [parse_lyrics(text, name_hint)]
    else:
        songs = [_new_song('empty', name_hint)]
    for s in songs:
        _verify(s)
    return songs


def parse_song(text, name_hint='Untitled'):
    """The first song in the text, as the dict the importer reads; see
    the module docstring and README of chartimport for its shape."""
    songs = parse_all(text, name_hint)
    first = songs[0]
    if len(songs) > 1:
        what = 'link' if first['kind'] == 'ireal' else 'file'
        others = len(songs) - 1
        first['findings'].append(
            f"The {what} holds {len(songs)} songs; this is the first, "
            f"{first['title']}, and the other {others} "
            f"{'was' if others == 1 else 'were'} skipped.")
    return first


def _verify(song):
    """The promise to the importer: every chord passes
    chartc.split_chord, every bar has one, every beat is writable."""
    beats = song['meter'][0]
    bad = 0
    for sec in song['sections']:
        fixed = []
        for bar in sec['bars']:
            nb = []
            for beat, sym in bar:
                if not chord_ok(sym):
                    sym2, _ = normalize_chord(sym)
                    if not sym2 or not chord_ok(sym2):
                        sym2 = 'nc'
                        bad += 1
                    sym = sym2
                if beat is not None and (_beat_value(beat) is None
                                         or not 1 <= beat < beats + 1):
                    beat = None
                nb.append((beat, sym))
            fixed.append(nb or [(None, 'nc')])
        sec['bars'] = fixed
    if bad:
        song['findings'].append(f"{bad} chord{'s' if bad != 1 else ''} "
                                "couldn't be read and became no chord.")


# =================================================================
# the spoken summary
# =================================================================

KIND_WORDS = {'ireal': 'An iReal Pro chart', 'abc': 'An ABC tune',
              'chordpro': 'A ChordPro song', 'chordsheet': 'A chord sheet',
              'lyrics': 'Lyrics', 'empty': 'Nothing'}


def describe(song, how=None):
    """One line per thing said, built whole and written once."""
    out = []
    head = KIND_WORDS.get(song['kind'], song['kind'])
    if how:
        head += f", from {how}"
    head += f": {song['title']}"
    if song['composer']:
        head += f", by {song['composer']}"
    out.append(head + '.')
    facts = []
    if song['key']:
        facts.append(f"key {song['key']}")
    facts.append(f"{song['meter'][0]}/{song['meter'][1]} time")
    if song['tempo']:
        facts.append(f"tempo {song['tempo']}")
    if song['style']:
        facts.append(f"style {song['style']}")
    out.append(", ".join(facts).capitalize() + '.')
    secs = song['sections']
    if secs:
        parts = []
        for s in secs:
            n = len(s['bars'])
            parts.append(f"{s['name']}, {n} bar{'s' if n != 1 else ''}"
                         if n else f"{s['name']}, words only")
        out.append(f"{len(secs)} section{'s' if len(secs) != 1 else ''}: "
                   + "; ".join(parts) + '.')
    chords = [sym for s in secs for bar in s['bars'] for _, sym in bar]
    if chords:
        out.append("First chords: " + ", ".join(chords[:8]) + '.')
    worded = [s['name'] for s in secs if s.get('words')]
    if worded:
        out.append("Words under " + ", ".join(worded) + '.')
    mel = song.get('melody')
    if mel:
        line = f"A melody of {len(mel['notes'])} notes"
        if mel.get('lyrics'):
            line += ", with lyrics under it"
        out.append(line + '.')
    for f in song['findings']:
        out.append(f)
    return "\n".join(out)


# =================================================================
# self test
# =================================================================

def _minimal_pdf(lines):
    """A one-page PDF with the given lines in Helvetica, built by hand
    so the test needs no library."""
    ops = ["BT /F1 12 Tf 72 720 Td 14 TL"]
    for ln in lines:
        esc = ln.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        ops.append(f"({esc}) Tj T*")
    ops.append("ET")
    stream = "\n".join(ops).encode('latin-1')
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{x}\n%%EOF\n").encode()
    return bytes(out)


def _make_docx(path, paras):
    body = "".join(
        '<w:p><w:pPr><w:tabs><w:tab w:val="left" w:pos="720"/></w:tabs>'
        '</w:pPr>' + "".join(
            '<w:r><w:tab/></w:r>' if piece == '\t' else
            '<w:r><w:br/></w:r>' if piece == '\n' else
            f'<w:r><w:t xml:space="preserve">{html.escape(piece)}</w:t></w:r>'
            for piece in re.split(r'(\t|\n)', p) if piece) + '</w:p>'
        for p in paras)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/'
           'wordprocessingml/2006/main"><w:body>' + body +
           '</w:body></w:document>')
    ct = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://'
          'schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.'
          'openxmlformats-package.relationships+xml"/><Default Extension='
          '"xml" ContentType="application/xml"/><Override PartName="/word/'
          'document.xml" ContentType="application/vnd.openxmlformats-'
          'officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns='
            '"http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.'
            'org/officeDocument/2006/relationships/officeDocument" Target='
            '"word/document.xml"/></Relationships>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', doc)


def _make_odt(path, paras):
    body = "".join(
        '<text:p>' + html.escape(p).replace('\t', '<text:tab/>')
        .replace('  ', ' <text:s text:c="1"/>') + '</text:p>'
        for p in paras)
    content = ('<?xml version="1.0" encoding="UTF-8"?><office:document-'
               'content xmlns:office="urn:oasis:names:tc:opendocument:'
               'xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:'
               'opendocument:xmlns:text:1.0" office:version="1.2">'
               '<office:body><office:text><text:h>Heading Line</text:h>'
               + body + '<text:p>with <text:span>a span</text:span>'
               '<text:line-break/>and a break</text:p>'
               '</office:text></office:body></office:document-content>')
    manifest = ('<?xml version="1.0" encoding="UTF-8"?><manifest:manifest '
                'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:'
                'manifest:1.0" manifest:version="1.2"><manifest:file-entry '
                'manifest:full-path="/" manifest:media-type="application/'
                'vnd.oasis.opendocument.text"/><manifest:file-entry '
                'manifest:full-path="content.xml" manifest:media-type='
                '"text/xml"/></manifest:manifest>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(zipfile.ZipInfo('mimetype'),
                   'application/vnd.oasis.opendocument.text')
        z.writestr('content.xml', content)
        z.writestr('META-INF/manifest.xml', manifest)


TEST_IREAL_MUSIC = (
    "*A{T44C^7XyQ|A-7XyQ|D-7XyQ|G7XyQ|N1E-7 A7XyQ|D-7 G7XyQ}  "
    "|N2D-7 G7XyQ|C^7XyQ]*B[Bh7XyQ|E7b9XyQKcl  LZA-7 D7XyQ|G7sus G7XyQ]"
    "*A[C^7 p p A7XyQ|D-7XyQ|nXyQ|C6XyQZ")


def _test_ireal_link(second=True):
    music = IREAL_PREFIX + ireal_scramble(TEST_IREAL_MUSIC)
    song1 = ("Test Tune=Writer Jane==Medium Swing=C==" + music +
             "==Jazz-Medium Swing=160=3")
    parts = [song1]
    if second:
        parts.append("Other Tune=Doe John==Bossa Nova=F-==" + IREAL_PREFIX
                     + ireal_scramble("{*AT44F-7XyQ|Bb7XyQ|Eb^7XyQ|x Z")
                     + "==Latin-Brazil: Bossa Acoustic=0=3")
        parts.append("My Playlist")
    return "irealb://" + quote("===".join(parts), safe='')


TEST_ABC = r"""X:1
T:Test Reel
C:Trad.
M:4/4
L:1/8
Q:1/4=120
K:G
|:"D7"d2|"G"G2 B>c d2 (3def|"C"e2 ^c2 c2 g2-|"G"g4 z2 "D7"FA|
[1"G"G6 d2:|[2"G"G8|]
w:la la la
"""

TEST_CHORDPRO = """{title: Test Song}
{artist: Some Writer}
{key: G}
{tempo: 96}
{time: 3/4}

[G]Hello [C]world, [D]here we go
[G]Second line

{start_of_chorus}
[C]Sing it [G]out
[D]Loud
{end_of_chorus}

[G]Verse two [C]line
[D]More words

{chorus}
"""

TEST_SHEET = """Test Sheet
by Someone

Key: D
[Intro]
| D  G | A / / D | Bm |  x2

[Verse 1]
D          G
Walking down the road
A              D
Singing all the way

[Chorus]
G      A     D
This is the chorus
"""

TEST_SHEET_PLAIN = """Verse:
C / / / G / / /
Here is a line
C / G /
And another one
"""

TEST_LYRICS = """My Song

The morning comes
and I am here

Hold on, hold on
to the light

The evening falls
and you are near

Hold on, hold on
to the light
"""

TEST_LYRICS_HEADED = """[Verse 1]
First verse words
more of them

Chorus:
Sing the chorus now

[Bridge]
Something new

Repeat Chorus
"""

CHORD_TABLE = [
    ('C^7', 'Cmaj7'), ('D-7', 'Dm7'), ('Bh7', 'Bm7b5'), ('Ch', 'Cm7b5'),
    ('Co7', 'Cdim7'), ('Co', 'Cdim'), ('C+', 'Caug'), ('Csus', 'Csus4'),
    ('C^', 'Cmaj7'), ('C69', 'C69'), ('C6/9', 'C69'), ('C7b9', 'C7b9'),
    ('C7#9', 'C7#9'), ('C7alt', 'Calt'), ('C-^7', 'Cmmaj7'),
    ('F#m7-5', 'F#m7b5'), ('Bb\u03947', 'Bbmaj7'), ('E\u00f8', 'Em7b5'),
    ('N.C.', 'nc'), ('C/E', 'C/E'), ('Am7/G', 'Am7/G'), ('CM7', 'Cmaj7'),
    ('Cmin7', 'Cm7'), ('C7(b9)', 'C7b9'), ('C(add9)', 'Cadd9'),
    ('C2', 'Cadd9'), ('C7+5', 'C7#5'), ('C+7', 'C7#5'), ('Eb-6', 'Ebm6'),
    ('B\u266d7', 'Bb7'), ('C\u00b07', 'Cdim7'), ('Cmaj7(#11)', 'Cmaj7#11'),
    # the compiler reads these as written since 2026-09-27; the last
    # three still simplify, because nothing in the chart language names
    # them yet
    ('C9sus4', 'C9sus4'), ('C7b9b13', 'C7b9b13'), ('Cm13', 'Cm13'),
    ('C5', 'C5'), ('C^9#11', 'Cmaj9#11'), ('C9#11', 'C9#11'),
    ('C13#9', 'C13#9'), ('Cmaj13', 'Cmaj13'), ('C-13', 'Cm13'),
    ('Ch9', 'Cm7b5'), ('C-b6', 'Cm'),
]


def selftest():
    """-> [(name, ok, detail)]."""
    results = []

    def check(name, fn):
        try:
            ok, detail = fn()
        except ImportTrouble as e:
            ok, detail = False, f"ImportTrouble: {e}"
        except SystemExit as e:
            ok, detail = False, f"exit: {e}"
        except Exception as e:     # a failing check reports, never dies
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((name, bool(ok), detail))

    tmp = tempfile.mkdtemp(prefix='textformats-test-')

    def p(n):
        return os.path.join(tmp, n)

    def wb(n, data):
        with open(p(n), 'wb') as f:
            f.write(data)
        return p(n)

    # ---------------------------------------------------- extraction
    def t_utf8():
        path = wb('a.txt', codecs.BOM_UTF8 + 'caf\u00e9 [C]\r\nline'
                  .encode('utf-8'))
        text, how = read_text(path)
        return text == 'caf\u00e9 [C]\nline' and how == 'a plain text file', \
            repr(text)
    check('plain text, UTF-8 with BOM and CRLF', t_utf8)

    def t_utf16():
        path = wb('b.txt', 'Verse 1\nhello \u2019there\u2019'
                  .encode('utf-16'))
        text, _ = read_text(path)
        return text == 'Verse 1\nhello \u2019there\u2019', repr(text)
    check('plain text, UTF-16 with BOM', t_utf16)

    def t_utf16_nobom():
        path = wb('c.song', 'Chorus\nla la'.encode('utf-16-le'))
        text, how = read_text(path)
        return text == 'Chorus\nla la' and how == 'a text file', repr(text)
    check('unknown extension, UTF-16 without BOM', t_utf16_nobom)

    def t_latin1():
        path = wb('d.txt', 'caf\u00e9 cr\u00e8me'.encode('cp1252'))
        text, _ = read_text(path)
        return text == 'caf\u00e9 cr\u00e8me', repr(text)
    check('plain text, Windows code page', t_latin1)

    def t_binary():
        path = wb('e.bin', bytes(range(256)) * 4)
        try:
            read_text(path)
        except ImportTrouble as e:
            return '\n' not in str(e) and str(e).endswith('.'), str(e)
        return False, 'no trouble raised'
    check('binary junk refused in one sentence', t_binary)

    def t_missing():
        try:
            read_text(p('nope.txt'))
        except ImportTrouble as e:
            return str(e) == "I can't find nope.txt.", str(e)
        return False, 'no trouble raised'
    check('missing file refused in one sentence', t_missing)

    def t_md():
        path = wb('f.md', b'# My Tune\n\n## Verse 1\nhello **world**\n')
        text, how = read_text(path)
        return ('My Tune' in text and '\nVerse 1\n' in text
                and 'hello world' in text and how == 'a Markdown file'), \
            repr(text)
    check('Markdown headings and bold stripped', t_md)

    paras = ['Verse 1', 'C\tG', 'Hello & goodbye', 'line one\nline two']

    def t_docx_fallback():
        _make_docx(p('g.docx'), paras)
        text = normalize_text(docx_text(p('g.docx')))
        want = 'Verse 1\nC\tG\nHello & goodbye\nline one\nline two'
        return text == want, repr(text)
    check('Word .docx, plain-Python reader', t_docx_fallback)

    def t_docx_read():
        text, how = read_text(p('g.docx'))
        return ('C\tG' in text and 'Hello & goodbye' in text
                and how == 'a Word document'), repr(text)
    check('Word .docx through read_text', t_docx_read)

    def t_odt_fallback():
        _make_odt(p('h.odt'), ['Verse 1', 'C\tG', 'two  spaces'])
        text = normalize_text(odt_text(p('h.odt')))
        want = ('Heading Line\nVerse 1\nC\tG\ntwo  spaces\nwith a span\n'
                'and a break')
        return text == want, repr(text)
    check('OpenDocument .odt, plain-Python reader', t_odt_fallback)

    def t_odt_read():
        text, how = read_text(p('h.odt'))
        return 'with a span' in text and 'C\tG' in text, repr(text)
    check('OpenDocument .odt through read_text', t_odt_read)

    rtf = (r"{\rtf1\ansi\ansicpg1252{\fonttbl{\f0\fswiss Helvetica;}}"
           r"{\colortbl;\red0\green0\blue0;}{\*\generator Test;}"
           r"\f0\fs24 Verse 1\par caf\'e9 \u8217? ok\tab X\line next\par}")

    def t_rtf_fallback():
        text = normalize_text(rtf_text(rtf))
        want = 'Verse 1\ncaf\u00e9 \u2019 ok\tX\nnext'
        return text.strip() == want, repr(text)
    check('RTF, plain-Python reader', t_rtf_fallback)

    def t_rtf_read():
        text, how = read_text(wb('i.rtf', rtf.encode('latin-1')))
        return ('caf\u00e9' in text and '\u2019' in text
                and how == 'a Rich Text file'), repr(text)
    check('RTF through read_text', t_rtf_read)

    page = ('<html><head><title>Ignore Me</title><style>p{color:red}'
            '</style></head><body><h1>Song</h1><p>A &amp; B</p>'
            '<pre>  C    G\nhello there</pre><ul><li>one</li>'
            '<li>two</li></ul><script>var x=1;</script></body></html>')

    def t_html_fallback():
        text = normalize_text(html_text(page))
        return ('Ignore' not in text and 'var x' not in text
                and text.startswith('Song\n\nA & B\n\n')
                and '  C    G\nhello there' in text
                and '\none\ntwo' in text), repr(text)
    check('HTML, plain-Python reader', t_html_fallback)

    def t_html_read():
        text, how = read_text(wb('j.html', page.encode('utf-8')))
        return 'A & B' in text and 'C    G' in text, repr(text)
    check('HTML through read_text', t_html_read)

    def t_html_ireal():
        link = _test_ireal_link(second=False)
        pg = (f'<html><body><a href="{html.escape(link)}">Test Tune</a>'
              '</body></html>')
        text, _ = read_text(wb('k.html', pg.encode('utf-8')))
        return text.startswith('irealb://') and classify(text) == 'ireal', \
            text[:60]
    check('HTML iReal playlist keeps its link', t_html_ireal)

    def t_webarchive():
        d = {'WebMainResource': {
            'WebResourceData': page.encode('utf-8'),
            'WebResourceMIMEType': 'text/html',
            'WebResourceTextEncodingName': 'UTF-8',
            'WebResourceURL': 'file:///song.html',
            'WebResourceFrameName': ''}}
        with open(p('l.webarchive'), 'wb') as f:
            plistlib.dump(d, f, fmt=plistlib.FMT_BINARY)
        a = normalize_text(webarchive_text(p('l.webarchive')))
        b, how = read_text(p('l.webarchive'))
        return ('A & B' in a and 'A & B' in b
                and how == 'a Safari web archive'), repr(a)
    check('Safari web archive, both readers', t_webarchive)

    def t_csv():
        path = wb('m.csv', b'Verse,C,G,Am,F\nsome words,here\n')
        text, _ = read_text(path)
        return text == 'Verse:\n| C | G | Am | F |\nsome words here', \
            repr(text)
    check('CSV rows of chords become barred lines', t_csv)

    pdf = _minimal_pdf(['Verse 1', 'Hello there'])
    has_pdf = _pdftotext() is not None

    def t_pdf():
        path = wb('n.pdf', pdf)
        if not has_pdf:
            try:
                read_text(path)
            except ImportTrouble as e:
                return 'poppler' in str(e), 'no pdftotext: ' + str(e)
            return False, 'no trouble raised without pdftotext'
        text, how = read_text(path)
        return 'Verse 1' in text and 'Hello there' in text, repr(text)
    check('PDF through pdftotext', t_pdf)

    def t_pages():
        with zipfile.ZipFile(p('o.pages'), 'w') as z:
            z.writestr('Index/Document.iwa', b'\x00\x01')
            z.writestr('QuickLook/Preview.pdf', pdf)
        if not has_pdf:
            return True, 'skipped: no pdftotext on this computer'
        text, how = read_text(p('o.pages'))
        return 'Hello there' in text and how == 'a Pages document', \
            repr(text)
    check('Pages with a PDF preview', t_pages)

    def t_pages_none():
        with zipfile.ZipFile(p('q.pages'), 'w') as z:
            z.writestr('Index/Document.iwa', b'\x00\x01')
            z.writestr('preview.jpg', b'\xff\xd8')
        try:
            read_text(p('q.pages'))
        except ImportTrouble as e:
            return 'Export To' in str(e), str(e)
        return False, 'no trouble raised'
    check('Pages without a preview says how to export', t_pages_none)

    # ---------------------------------------------------- classify
    kinds = [(_test_ireal_link(), 'ireal'), (TEST_ABC, 'abc'),
             (TEST_CHORDPRO, 'chordpro'),
             ("[C]Hello [G]world [Am]and [F]more\n", 'chordpro'),
             (TEST_SHEET, 'chordsheet'), (TEST_SHEET_PLAIN, 'chordsheet'),
             (TEST_LYRICS, 'lyrics'), ("Go go go\nDo it now\nAh\n",
                                       'lyrics'),
             ("  \n\n ", 'empty')]
    for text, want in kinds:
        check(f'classify as {want}: {text.strip()[:24]!r}',
              lambda t=text, w=want: (classify(normalize_text(t)) == w,
                                      classify(normalize_text(t))))

    # ---------------------------------------------------- chords
    def t_chords():
        bad = []
        for raw, want in CHORD_TABLE:
            got, _ = normalize_chord(raw)
            if got != want or not chord_ok(got):
                bad.append(f"{raw} gave {got}, wanted {want}")
        return not bad, "; ".join(bad) or f"{len(CHORD_TABLE)} spellings"
    check('chord spellings translate to accepted ones', t_chords)

    def t_not_chords():
        bad = [w for w in ('Go', 'Do', 'Ah', 'Eh', 'Bass', 'Add', 'Dim',
                           'Be') if chordish(w)]
        return not bad, ", ".join(bad) or 'none mistaken'
    check('common words are not chords', t_not_chords)

    # ---------------------------------------------------- iReal
    def t_scramble():
        s = TEST_IREAL_MUSIC
        sc = ireal_scramble(s)
        return sc != s and ireal_unscramble(sc) == s and len(s) > 101, \
            f"{len(s)} characters"
    check('iReal scramble round trip', t_scramble)

    def t_ireal():
        song = parse_song(_test_ireal_link())
        names = [(s['name'], len(s['bars'])) for s in song['sections']]
        flat = [bar for s in song['sections'] for bar in s['bars']]
        want_names = [('A', 6), ('A', 6), ('B', 5), ('A', 4)]
        ok = (names == want_names and song['title'] == 'Test Tune'
              and song['composer'] == 'Jane Writer' and song['key'] == 'C'
              and song['style'] == 'Medium Swing' and song['tempo'] == 160
              and song['meter'] == (4, 4)
              and flat[0] == [(None, 'Cmaj7')]
              and flat[4] == [(None, 'Em7'), (None, 'A7')]
              and flat[10] == [(None, 'Dm7'), (None, 'G7')]
              and flat[12] == [(None, 'Bm7b5')]
              and flat[14] == [(None, 'E7b9')]
              and flat[16] == [(None, 'G7sus4'), (None, 'G7')]
              and flat[17] == [(1, 'Cmaj7'), (4, 'A7')]
              and flat[19] == [(None, 'nc')]
              and flat[20] == [(None, 'C6')]
              and any('2 songs' in f for f in song['findings'])
              and any('endings' in f for f in song['findings']))
        return ok, f"{names} {flat[16:18]} {song['findings']}"
    check('iReal link parses bar by bar', t_ireal)

    def t_ireal_all():
        songs = parse_all(_test_ireal_link())
        s2 = songs[1] if len(songs) > 1 else None
        ok = (len(songs) == 2 and s2['title'] == 'Other Tune'
              and s2['key'] == 'Fm' and s2['composer'] == 'John Doe'
              and [b for s in s2['sections'] for b in s['bars']][-1]
              == [(None, 'Ebmaj7')])
        return ok, f"{len(songs)} songs"
    check('iReal playlist gives every song to parse_all', t_ireal_all)

    def t_ireal_book():
        link = "irealbook://" + quote(
            "Plain Tune=Smith Al=Swing=Bb=n=T44*A{Bb^7 |G-7 |C-7 |F7 }",
            safe='')
        song = parse_song(link)
        flat = [b for s in song['sections'] for b in s['bars']]
        return (len(flat) == 8 and flat[0] == [(None, 'Bbmaj7')]
                and song['key'] == 'Bb'), f"{flat}"
    check('iReal unscrambled irealbook link', t_ireal_book)

    # ---------------------------------------------------- ABC
    def t_abc():
        song = parse_song(TEST_ABC)
        mel = song['melody']
        bars = [b for s in song['sections'] for b in s['bars']]
        notes = mel['notes']
        trip = notes[5:8]
        ok = (song['title'] == 'Test Reel' and song['key'] == 'G'
              and song['composer'] == 'Trad.' and song['tempo'] == 120
              and mel['pickup_quarters'] == 1 and len(bars) == 10
              and bars[0] == [(None, 'D7')] and bars[1] == [(None, 'G')]
              and bars[3] == [(1, 'G'), (4, 'D7')]
              and notes[0] == (Fraction(1), 74)
              and notes[2] == (Fraction(3, 4), 71)
              and notes[3] == (Fraction(1, 4), 72)
              and trip == [(Fraction(1, 3), 74), (Fraction(1, 3), 76),
                           (Fraction(1, 3), 78)]
              and notes[9] == (Fraction(1), 73)
              and notes[10] == (Fraction(1), 73)
              and notes[11] == (Fraction(3), 79)
              and notes[12] == (Fraction(1), None)
              and notes[13] == (Fraction(1, 2), 66)
              and mel['lyrics'] == 'la la la'
              and sum(q for q, _ in notes) == 1 + 4 * 4 + 1 + 4 * 3 + 4)
        return ok, f"{bars[:4]} {notes[:14]} {song['findings']}"
    check('ABC tune: chords, ties, triplet, accidentals, pickup', t_abc)

    def t_abc_modal():
        song = parse_song("X:1\nT:Modal\nM:6/8\nL:1/8\nK:D dor\n"
                          '"Dm"DEF "C"GAB|"Dm"d3 d3|]\n')
        bars = [b for s in song['sections'] for b in s['bars']]
        return (song['key'] == 'Am' and song['meter'] == (6, 8)
                and bars[0] == [(1, 'Dm'), (4, 'C')]
                and any('dorian' in f for f in song['findings'])), \
            f"{song['key']} {bars} {song['findings']}"
    check('ABC modal key and 6/8 chord beats', t_abc_modal)

    # ---------------------------------------------------- ChordPro
    def t_chordpro():
        song = parse_song(TEST_CHORDPRO)
        names = [(s['name'], len(s['bars'])) for s in song['sections']]
        ok = (names == [('Verse 1', 4), ('Chorus', 3), ('Verse 2', 3),
                        ('Chorus 2', 3)]
              and song['title'] == 'Test Song'
              and song['composer'] == 'Some Writer'
              and song['key'] == 'G' and song['tempo'] == 96
              and song['meter'] == (3, 4)
              and song['sections'][0]['words'] ==
              'Hello world, here we go\nSecond line'
              and song['sections'][3]['words'] == 'Sing it out\nLoud'
              and sum('one bar' in f for f in song['findings']) == 1)
        return ok, f"{names} {song['findings']}"
    check('ChordPro song with a chorus', t_chordpro)

    # ---------------------------------------------------- chord sheets
    def t_sheet():
        song = parse_song(TEST_SHEET)
        names = [(s['name'], len(s['bars'])) for s in song['sections']]
        intro = song['sections'][0]['bars']
        ok = (names == [('Intro', 6), ('Verse 1', 4), ('Chorus', 3)]
              and song['title'] == 'Test Sheet'
              and song['composer'] == 'Someone' and song['key'] == 'D'
              and intro[0] == [(None, 'D'), (None, 'G')]
              and intro[1] == [(1, 'A'), (4, 'D')]
              and intro[3] == intro[0]
              and song['sections'][1]['words'] ==
              'Walking down the road\nSinging all the way')
        return ok, f"{names} {intro[:3]}"
    check('chord sheet with barlines, x2 and headers', t_sheet)

    def t_sheet_plain():
        song = parse_song(TEST_SHEET_PLAIN)
        bars = song['sections'][0]['bars']
        ok = (song['kind'] == 'chordsheet' and bars ==
              [[(None, 'C')], [(None, 'G')], [(1, 'C'), (3, 'G')]]
              and song['sections'][0]['name'] == 'Verse 1'
              and not any('one bar' in f for f in song['findings']))
        return ok, f"{bars}"
    check('chord sheet with slashes and no barlines', t_sheet_plain)

    # ---------------------------------------------------- lyrics
    def t_lyrics():
        song = parse_song(TEST_LYRICS)
        names = [s['name'] for s in song['sections']]
        ok = (names == ['Verse 1', 'Chorus', 'Verse 2', 'Chorus 2']
              and song['title'] == 'My Song'
              and all(s['bars'] == [] for s in song['sections'])
              and song['sections'][1]['words'] ==
              'Hold on, hold on\nto the light')
        return ok, f"{names} {song['title']}"
    check('lyrics with a repeated chorus', t_lyrics)

    def t_lyrics_headed():
        song = parse_song(TEST_LYRICS_HEADED)
        names = [s['name'] for s in song['sections']]
        ok = (names == ['Verse 1', 'Chorus', 'Bridge', 'Chorus 2']
              and song['sections'][3]['words'] == 'Sing the chorus now')
        return ok, f"{names}"
    check('lyrics with headers and Repeat Chorus', t_lyrics_headed)

    # ---------------------------------------------------- the promise
    def t_all_chords():
        texts = [_test_ireal_link(), TEST_ABC, TEST_CHORDPRO, TEST_SHEET,
                 TEST_SHEET_PLAIN, TEST_LYRICS,
                 "| C9sus4 Db7b9b13 | Cm13 G5 | F#m11b5 |\n| E7#9#5 |\n"]
        bad, n = [], 0
        for t in texts:
            for song in parse_all(t):
                for s in song['sections']:
                    for bar in s['bars']:
                        if not bar:
                            bad.append('empty bar')
                        for beat, sym in bar:
                            n += 1
                            if not chord_ok(sym):
                                bad.append(sym)
                            if beat is not None and _beat_value(beat) is None:
                                bad.append(f"beat {beat}")
        return not bad, ", ".join(bad) or f"{n} chords all accepted"
    check('every chord in every result passes chartc', t_all_chords)

    def t_spoken():
        lines = describe(parse_song(TEST_SHEET), 'a plain text file') \
            .split('\n')
        return all(ln and ln.endswith(('.', '?')) and '\u2500' not in ln
                   for ln in lines), lines[0]
    check('spoken summary is plain sentences', t_spoken)

    shutil.rmtree(tmp, ignore_errors=True)
    return results


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print("Say a file to read, like: python3 textformats.py "
              "song.docx, or --selftest to check this module.")
        return 0 if argv else 2
    if argv[0] == '--selftest':
        res = selftest()
        lines = [f"{'PASS' if ok else 'FAIL'} {name}"
                 + ('' if ok else f": {detail}") for name, ok, detail in res]
        failed = sum(1 for _, ok, _ in res if not ok)
        lines.append(f"{len(res) - failed} of {len(res)} checks passed.")
        print("\n".join(lines))
        return 1 if failed else 0
    path = argv[0]
    try:
        text, how = read_text(path)
        song = parse_song(text, os.path.splitext(
            os.path.basename(path.rstrip(os.sep)))[0])
    except ImportTrouble as e:
        print(str(e))
        return 1
    print(describe(song, how))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
