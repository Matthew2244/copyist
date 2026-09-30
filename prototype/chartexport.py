#!/usr/bin/env python3
"""chartexport — a chart out to the formats musicians pass around
(Matthew, 2026-09-29: "Speaking of iReal Pro, you should add support
for that and whatever"):

    <title> — iReal Pro.html   a page with the chart as an iReal Pro link:
                               tap it on the phone and iReal opens it
    <title> — iReal Pro.txt    the link itself, to paste or send
    <title> — band.mid         the listen as MIDI, one track per player,
                               made-up parts and swing included, for a DAW
    <title> — chords.txt       a plain chord sheet with barlines

The iReal link is proven the only way that counts: Copyist's own
importer reads it back to the same form and chords (test_corpus).
"""
import html
import os
import re
import struct
from urllib.parse import quote

import chartc
import smf
import textformats

# ------------------------------------------------------------ iReal Pro

_IREAL_Q = {
    'maj': '', 'maj7': '^7', 'maj9': '^9', 'maj13': '^13',
    'maj7#11': '^7#11', 'maj9#11': '^9#11', '6': '6', '69': '69',
    'add9': 'add9', 'm': '-', 'm7': '-7', 'm9': '-9', 'm11': '-11',
    'm6': '-6', 'm69': '-69', 'm13': '-13', 'mmaj7': '-^7',
    'mmaj9': '-^9', 'm7b5': 'h7', 'm9b5': 'h9', 'dim': 'o', 'dim7': 'o7',
    'aug': '+', 'alt': '7alt', '7sus4': '7sus', 'sus4': 'sus',
    'sus2': 'sus2', '9sus4': '9sus', '13sus': '13sus', 'madd9': '-add9',
    'mb6': '-b6', 'm#5': '-#5', 'm7b9': '-7b9', 'maj7#5': '^7#5',
}

_IREAL_STYLES = [
    (r'ballad', 'Ballad'), (r'bossa', 'Bossa Nova'), (r'samba', 'Samba'),
    (r'latin|afro|mambo|salsa|songo', 'Latin'), (r'funk', 'Funk'),
    (r'waltz', 'Waltz'), (r'shuffle', 'Shuffle'),
    (r'up ?tempo|fast|bebop', 'Up Tempo Swing'),
    (r'medium ?up', 'Medium Up Swing'), (r'slow', 'Slow Swing'),
    (r'rock|pop|straight|even', 'Even 8ths'), (r'reggae', 'Reggae'),
    (r'gospel', 'Gospel'), (r'second ?line', 'Second Line'),
    (r'swing', 'Medium Swing'),
]


def _acc(alter):
    return {-1: 'b', 1: '#', -2: 'bb', 2: '##'}.get(alter, '')


def ireal_chord(ch):
    """('F', 0, 'm7', None) -> 'F-7'; slash chords keep their bass."""
    if ch is None:
        return 'n'
    step, alter, qual, bass = ch
    q = _IREAL_Q.get(qual, qual)
    s = step + _acc(alter) + q
    if bass:
        if isinstance(bass, tuple):
            s += '/' + bass[0] + _acc(bass[1])
        else:
            s += '/' + str(bass)
    return s


def _ireal_style(feel):
    f = (feel or '').lower()
    for rx, name in _IREAL_STYLES:
        if re.search(rx, f):
            return name
    return 'Medium Swing'


def _ireal_key(key_text):
    k = (key_text or 'C').strip()
    m = re.match(r'([A-G][b#]?)\s*(m|min|minor)?\b', k, re.I)
    if not m:
        return 'C'
    root = m.group(1)[0].upper() + m.group(1)[1:]
    return root + ('-' if m.group(2) else '')


def _ireal_composer(name):
    w = (name or '').split()
    if len(w) == 2:
        return w[1] + ' ' + w[0]     # iReal files composers Last First
    return name or 'Composer Unknown'


def _bar_cells(bar, beats):
    """One bar's chords as iReal cells: a chord where it changes, a
    slash where the one before carries on."""
    got = [(b, c) for b, c in bar if c is not None]
    if not got:
        return 'x'                   # the bar before, again
    if len(got) == 1 and got[0][0] <= 1.0:
        return ireal_chord(got[0][1])
    cells = ['p'] * beats
    for b, c in got:
        i = min(max(int(round(b - 1)), 0), beats - 1)
        cells[i] = ireal_chord(c)
    if cells[0] == 'p':
        cells[0] = 'x'
    return ' '.join(cells)


def ireal_music(chart):
    """The chart's sections -> iReal's chart string (unscrambled)."""
    meters = chart.get('meters') or [(1, chartc.parse_meter(
        chart['header'].get('meter', '4/4')))]
    out = []
    start = 1
    cur_meter = None
    for sec in chart['sections']:
        n = sec['bars']
        mark = ''
        nm = sec['name'].strip().lower()
        if nm[:1] in 'abcd' and (len(nm) == 1 or nm[1:].isdigit()):
            mark = '*' + nm[0].upper()
        elif nm.startswith('intro'):
            mark = '*i'
        elif nm.startswith('verse'):
            mark = '*V'
        rep = sec.get('repeat') or 0
        ends = sec.get('endings') or []
        body_n = sec.get('body', n) if ends else n
        cells = []
        for off in range(n):
            meter = chartc.meter_at(meters, start + off)
            t = ''
            if meter != cur_meter:
                t = 'T' + ('12' if meter == (12, 8) else
                           f"{meter[0]}{meter[1]}")
                cur_meter = meter
            beats = meter[0] if meter[1] == 4 else max(meter[0] // 3, 1)
            cells.append(t + _bar_cells(sec['content'][off], beats))
        if ends:
            body = '|'.join(cells[:body_n])
            elen = ends[0]['bars']
            blocks = []
            for k in range(len(ends)):
                seg = cells[body_n + k * elen: body_n + (k + 1) * elen]
                close = '}' if k < len(ends) - 1 else ']'
                blocks.append(f"N{k + 1}" + '|'.join(seg) + close)
            out.append('{' + mark + body + '|' + ''.join(blocks))
        elif rep >= 2:
            out.append('{' + mark + '|'.join(cells) + '}')
        else:
            out.append('[' + mark + '|'.join(cells) + ']')
        start += n
    music = ''.join(out)
    # the final double bar: a closing bracket becomes it; a closing
    # repeat keeps its repeat and the end follows
    return music[:-1] + 'Z' if music.endswith(']') else music + 'Z'


def ireal_link(chart):
    """The chart as an irealb:// link iReal Pro opens: one song, in a
    playlist named for it."""
    hdr = chart['header']
    title = hdr.get('title', 'Untitled')
    tempo = str(int(float(hdr.get('tempo', 0) or 0))) \
        if hdr.get('tempo') else '0'
    song = "=".join([
        title, _ireal_composer(hdr.get('composer', '')), '',
        _ireal_style(hdr.get('feel', '')), _ireal_key(hdr.get('key', 'C')),
        '',
        textformats.IREAL_PREFIX + textformats.ireal_scramble(
            ireal_music(chart)),
        '', 'Jazz-' + _ireal_style(hdr.get('feel', '')), tempo, '0'])
    return "irealb://" + quote(song + "===" + title, safe='')


def write_ireal(chart, folder, title):
    link = ireal_link(chart)
    txt = os.path.join(folder, f"{title} — iReal Pro.txt")
    page = os.path.join(folder, f"{title} — iReal Pro.html")
    with open(txt, 'w', encoding='utf-8') as f:
        f.write(link + "\n")
    t = html.escape(title)
    with open(page, 'w', encoding='utf-8') as f:
        f.write(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t} for iReal Pro</title>
<style>
body {{ font: 18px/1.5 -apple-system, system-ui, sans-serif;
       margin: 2em auto; max-width: 34em; padding: 0 1em; }}
a.open {{ display: inline-block; padding: .8em 1.2em; border-radius: .5em;
         background: #2a5bd7; color: #fff; text-decoration: none; }}
</style></head><body>
<h1>{t}</h1>
<p>From Copyist. Open this page on a phone or tablet with iReal Pro
installed, then tap the link: iReal Pro opens the chart.</p>
<p><a class="open" href="{html.escape(link)}">Open {t} in iReal Pro</a></p>
</body></html>
""")
    return [page, txt]


# ----------------------------------------------------------------- MIDI

def write_midi(listen_path, folder, title):
    """The listening document as a type-1 MIDI file: a conductor track
    with the tempo map, then one track per player — its name, its
    General MIDI program, drums on channel 10 — every note where the
    band plays it, swing included, so a DAW gets the band as heard."""
    import chartaudio
    plan = chartaudio.parse_score(listen_path)
    ppq = 480

    def tick(q):
        return int(round(chartaudio._warp(q, plan['swings']) * ppq))
    tempos = plan['tempos'] or [(0.0, 120.0)]
    n0, d0 = plan['meter0']
    cond = [(0, b"\xFF\x03" + smf.vlq(len(title.encode('utf-8')))
             + title.encode('utf-8')),
            (0, b"\xFF\x58\x04" + bytes([n0, max(d0.bit_length() - 1, 0),
                                         0x18, 0x08]))]
    tmap = dict(tempos)

    def bpm_at(q):
        b = tempos[0][1]
        for tq, tb in tempos:
            if tq <= q + 1e-9:
                b = tb
        return b
    # a fermata holds time just before its note lets go: in MIDI that
    # is the half beat before the hold slowed down by exactly the
    # held time, then back in tempo
    for hq, extra in plan.get('holds', ()):
        w = 0.5
        base = bpm_at(hq)
        tmap[round(hq - w, 6)] = base * w / (w + extra)
        tmap.setdefault(round(hq, 6), base)      # and back in tempo
    for q, bpm in sorted(tmap.items()):
        cond.append((tick(q), b"\xFF\x51\x03"
                     + struct.pack(">I", int(60_000_000 / bpm))[1:]))
    tracks = [smf._track(cond)]
    chan = 0
    for part in plan['parts']:
        if not part['events']:
            continue
        if part['percussion']:
            ch = 9
        else:
            ch = chan
            chan += 1
            if chan == 9:
                chan += 1
            if chan > 15:
                chan = 15
        name = part['name'].encode('utf-8')
        ev = [(0, b"\xFF\x03" + smf.vlq(len(name)) + name)]
        if not part['percussion']:
            ev.append((0, bytes([0xC0 | ch, max(part['program'] - 1, 0)])))
        for q_on, q_dur, midi, gain, _art in part['events']:
            a, b = tick(q_on), tick(q_on + q_dur)
            v = max(1, min(int(gain * 110), 127))
            m = max(0, min(int(midi), 127))
            ev.append((a, bytes([0x90 | ch, m, v])))
            ev.append((max(b, a + 1), bytes([0x80 | ch, m, 0])))
        tracks.append(smf._track(ev))
    path = os.path.join(folder, f"{title} — band.mid")
    with open(path, 'wb') as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), ppq))
        for t in tracks:
            f.write(t)
    return [path]


# ---------------------------------------------------------- chord sheet

def _plain(ch):
    if ch is None:
        return 'N.C.'
    step, alter, qual, bass = ch
    qual = {'maj': '', 'alt': '7alt'}.get(qual, qual)   # as it's written
    s = step + _acc(alter) + qual
    if bass:
        s += '/' + (bass[0] + _acc(bass[1]) if isinstance(bass, tuple)
                    else str(bass))
    return s


def write_chords(chart, folder, title):
    """A chord sheet anyone can read, by eye or by ear: each section by
    name, four bars a line, barlines between, a chord that holds shown
    once with its bar left as a slash."""
    hdr = chart['header']
    lines = [title]
    if hdr.get('composer'):
        lines.append(hdr['composer'])
    k = (hdr.get('key', 'C') or 'C').strip()
    k = re.sub(r'^([A-G][b#]?)\s*(?:m|min)$', r'\1 minor', k)
    k = k.replace('b', ' flat', 1) if re.match(r'^[A-G]b', k) else k
    k = k.replace('#', ' sharp', 1)
    facts = [f"key of {k}",
             hdr.get('meter', '4/4')]
    if hdr.get('tempo'):
        facts.append(f"{hdr['tempo']} a beat")
    if hdr.get('feel'):
        facts.append(hdr['feel'])
    lines += [", ".join(facts), ""]
    for sec in chart['sections']:
        head = sec['label'] or sec['name']
        rep = sec.get('repeat') or 0
        lines.append(f"{head} ({sec['bars']} bars"
                     + (f", played {rep} times" if rep >= 2 else "") + ")")
        bars = []
        for bar in sec['content']:
            got = [c for _b, c in bar if c is not None]
            bars.append(" ".join(_plain(c) for c in got) if got else '/')
        for i in range(0, len(bars), 4):
            lines.append("| " + " | ".join(bars[i:i + 4]) + " |")
        lines.append("")
    path = os.path.join(folder, f"{title} — chords.txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    return [path]
