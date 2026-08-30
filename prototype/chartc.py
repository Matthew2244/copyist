#!/usr/bin/env python3
"""chartc — compile a .chart file (CHART-FORMAT.md) into MusicXML.

First increment, built against the Matt's Blues worked example. Implements:
header, band block, chord progressions and the full bars grammar, pickup,
sections with labels/repeats, `as engraved` lifts (each part's own bars from
the source engraving, exact), `groove` slash generation with chord symbols,
tacet, solo/backgrounds/text annotations, and score + per-part emission.

Deliberately not built yet (each one errors in a sentence rather than
guessing): `from midi` figures, inline `notes:` figures, volta endings,
`hits`, `mute`, `double`, `cue`, `build:`, `on pass`, meters other than 4/4.

Usage: chartc.py <file.chart> [-o outdir]
"""
import os
import re
import sys
import argparse

BEATS = 4          # 4/4 only in this increment
XMLHEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 '
           'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n')

CHORD_KINDS = {
    '7': ('dominant', '7'), '9': ('dominant-ninth', '9'),
    '11': ('dominant-11th', '11'), '13': ('dominant-13th', '13'),
    'maj': ('major', ''), 'maj7': ('major-seventh', 'maj7'),
    'm': ('minor', 'm'), 'm7': ('minor-seventh', 'm7'),
    'm9': ('minor-ninth', 'm9'), 'm6': ('minor-sixth', 'm6'),
    '6': ('major-sixth', '6'), 'dim': ('diminished', 'dim'),
    'dim7': ('diminished-seventh', 'dim7'),
    'm7b5': ('half-diminished', 'm7b5'),
    'sus4': ('suspended-fourth', 'sus4'),
    '7sus4': ('suspended-fourth', '7sus4'),
    'aug': ('augmented', 'aug'),
}

STEP = set('ABCDEFG')


def fail(msg):
    sys.exit("chartc: " + msg)


# ------------------------------------------------------------- parsing

def parse_beat(tok):
    m = re.fullmatch(r'(\d+)\+', tok)
    if m:
        return int(m.group(1)) + 0.5
    m = re.fullmatch(r'and-of-(\d+)', tok)
    if m:
        return int(m.group(1)) + 0.5
    m = re.fullmatch(r'(\d+)(\.5)?', tok)
    if m:
        return int(m.group(1)) + (0.5 if m.group(2) else 0.0)
    fail(f"cannot read beat '{tok}'")


def split_chord(sym):
    """'Bb7' -> ('B', -1, '7'); 'nc' -> None; bass slash split off."""
    if sym == 'nc':
        return None
    bass = None
    if '/' in sym:
        sym, bass = sym.split('/', 1)
    m = re.fullmatch(r'([A-G])([b#]?)(.*)', sym)
    if not m or m.group(1) not in STEP:
        fail(f"cannot read chord '{sym}'")
    step, acc, qual = m.groups()
    qual = qual or 'maj'
    if qual not in CHORD_KINDS:
        fail(f"chord quality '{qual}' (in '{sym}') is not in the supported list")
    alter = {'b': -1, '#': 1, '': 0}[acc]
    return (step, alter, qual, bass)


def parse_bars(text, where):
    bars = []
    for raw in text.split(','):
        raw = raw.strip()
        if not raw:
            fail(f"empty bar in {where}")
        reps = 1
        m = re.fullmatch(r'(.*?)\s+x(\d+)', raw)
        if m:
            raw, reps = m.group(1).strip(), int(m.group(2))
        toks = raw.split()
        bar = []
        for tok in toks:
            if '@' in tok:
                sym, beat = tok.split('@', 1)
                bar.append([parse_beat(beat), sym])
            else:
                bar.append([None, tok])
        n = len(bar)
        for i, item in enumerate(bar):
            if item[0] is None:
                item[0] = 1.0 + i * (BEATS / n) if n > 1 else 1.0
        for _ in range(reps):
            bars.append([(b, split_chord(s)) for b, s in bar])
    return bars


def parse_chart(path):
    chart = {'header': {}, 'band': [], 'chords': {}, 'sections': [],
             'pickup': None}
    cur = None          # current section
    mode = None         # 'band' or None
    for lineno, line in enumerate(open(path, encoding='utf-8'), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        loc = f"line {lineno}"
        indented = line[0] in ' \t'

        if not indented:
            mode, cur = None, None
            if s == 'band:':
                mode = 'band'
                continue
            if s == 'output:':
                mode = 'output'
                continue
            m = re.match(r'chords ([\w ]+?):\s*(.+)$', s)
            if m:
                chart['chords'][m.group(1).strip()] = parse_bars(
                    m.group(2), f"chords {m.group(1)}")
                continue
            m = re.match(r'figure ', s)
            if m:
                fail(f"{loc}: named figures are not built yet — "
                     "use 'as engraved' or wait for the next increment")
            m = re.match(r'pickup (\d+) beats((?:,\s*as engraved)?)'
                         r'(?::\s*(.*))?$', s)
            if m:
                texts = re.findall(r'text "([^"]*)"', m.group(3) or '')
                chart['pickup'] = {'beats': int(m.group(1)),
                                   'engraved': bool(m.group(2)),
                                   'texts': texts}
                continue
            m = re.match(r'section ([\w ]+?)'
                         r'(?:,\s*(\d+) bars)?'
                         r'(?:,\s*label "([^"]*)")?'
                         r'(?:,\s*repeat (\d+)x)?'
                         r'(,\s*open)?\s*$', s)
            if m:
                if m.group(2) is None:
                    fail(f"{loc}: section {m.group(1)} must declare its length")
                cur = {'name': m.group(1).strip(), 'bars': int(m.group(2)),
                       'label': m.group(3), 'repeat': int(m.group(4) or 0),
                       'open': bool(m.group(5)), 'content': None,
                       'feel': None, 'directives': [], 'events': []}
                chart['sections'].append(cur)
                continue
            m = re.match(r'(\w+):\s*(.+)$', s)
            if m and m.group(1) in ('title', 'composer', 'arranger', 'key',
                                    'meter', 'tempo', 'feel', 'source'):
                chart['header'][m.group(1)] = m.group(2).strip().strip('"')
                continue
            fail(f"{loc}: cannot read '{s}'")

        # indented lines
        if mode == 'band':
            m = re.match(r'([\w ]+?)(?:\s*=\s*([\w ]+?))?'
                         r'(?:,\s*detail (\w[\w-]*))?'
                         r'(?:,\s*tuning ([\w ]+))?\s*$', s)
            if not m:
                fail(f"{loc}: cannot read band line '{s}'")
            chart['band'].append({'label': m.group(1).strip(),
                                  'instrument': (m.group(2) or m.group(1)).strip(),
                                  'detail': m.group(3),
                                  'tuning': m.group(4)})
            continue
        if mode == 'output':
            continue        # defaults only in this increment
        if cur is None:
            fail(f"{loc}: indented line outside any section: '{s}'")

        m = re.match(r'feel:\s*(.+)$', s)
        if m:
            cur['feel'] = m.group(1).strip()
            continue
        m = re.match(r'chords:\s*(.+)$', s)
        if m:
            cur['content'] = parse_bars(m.group(1), f"section {cur['name']}")
            continue
        m = re.match(r'use chords ([\w ]+?)(?:\s+x(\d+))?$', s)
        if m:
            name = m.group(1).strip()
            if name not in parse_chart.defs_ref:
                pass
            cur['use'] = (name, int(m.group(2) or 1))
            continue
        m = re.match(r'at bar (\d+):\s*text "([^"]*)"$', s)
        if m:
            cur['events'].append((int(m.group(1)), 'text', m.group(2)))
            continue
        m = re.match(r'([\w ]+?):\s*(.+)$', s)
        if m:
            cur['directives'].append((m.group(1).strip(), m.group(2).strip(),
                                      loc))
            continue
        fail(f"{loc}: cannot read '{s}' in section {cur['name']}")

    # resolve `use chords`
    for sec in chart['sections']:
        if 'use' in sec:
            name, times = sec.pop('use')
            if name not in chart['chords']:
                fail(f"section {sec['name']} uses chords '{name}', not defined")
            sec['content'] = chart['chords'][name] * times
        if sec['content'] is None:
            fail(f"section {sec['name']} has no chords")
        if len(sec['content']) != sec['bars']:
            fail(f"section {sec['name']} declares {sec['bars']} bars but its "
                 f"chords cover {len(sec['content'])}")
    return chart


parse_chart.defs_ref = {}


# --------------------------------------------------------- source score

def load_source(path):
    xml = open(path, encoding='utf-8').read()
    order = re.findall(r'<score-part id="([^"]+)">', xml)
    names = dict(re.findall(
        r'<score-part id="([^"]+)">.*?<part-name[^>]*>([^<]*)</part-name>',
        xml, re.S))
    parts = {}
    for pid in order:
        body = re.search(r'<part id="%s">(.*?)</part>' % pid, xml, re.S).group(1)
        ms = {}
        for num, content in re.findall(
                r'<measure [^>]*?number="([^"]+)"[^>]*>(.*?)</measure>',
                body, re.S):
            ms[num] = content
        dv = re.search(r'<divisions>(\d+)</divisions>', body)
        staves = re.search(r'<staves>(\d+)</staves>', body)
        clef = re.search(r'<clef[^>]*>\s*<sign>(\w+)</sign>', body)
        fifths = re.search(r'<fifths>(-?\d+)</fifths>', body)
        parts[names[pid].strip()] = {
            'measures': ms, 'div': int(dv.group(1)) if dv else 8,
            'staves': int(staves.group(1)) if staves else 1,
            'clef': clef.group(1) if clef else 'G',
            'fifths': int(fifths.group(1)) if fifths else 0}
    return parts


def match_part(label, source_names):
    """Band label -> unique source part name, by token prefix matching."""
    drop = {'in', 'bb', 'eb', 'f', 'c'}
    lt = [t for t in label.lower().split()]
    hits = []
    for name in source_names:
        nt = [t for t in name.lower().split() if t not in drop]
        if all(any(a.startswith(b) or b.startswith(a) for a in nt) for b in lt):
            hits.append(name)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        fail(f"band part '{label}' matches no part in the source score")
    fail(f"band part '{label}' is ambiguous in the source score: {hits}")


# ------------------------------------------------------------ emission

def strip_lifted(content, percussion=False):
    """Remove what the compiler owns from a lifted measure: rehearsal marks,
    words, metronome marks, harmony, print/layout. Keep notes, dynamics,
    wedges, attributes, barlines."""
    content = re.sub(r'<harmony[^>]*>.*?</harmony>\s*', '', content, flags=re.S)
    if percussion:
        # a key signature on a percussion staff renders every slash with a
        # courtesy natural in MuseScore — strip it, drums have no key
        content = re.sub(r'<key[^>]*>.*?</key>\s*', '', content, flags=re.S)
    content = re.sub(r'<print[^>]*/>\s*|<print[^>]*>.*?</print>\s*', '',
                     content, flags=re.S)

    def keep(m):
        block = m.group(0)
        if re.search(r'<rehearsal|<words|<metronome', block):
            return ''
        return block
    return re.sub(r'<direction[^>]*>.*?</direction>\s*', keep, content,
                  flags=re.S)


def direction(text, placement='above'):
    return (f'      <direction placement="{placement}">'
            f'<direction-type><words>{text}</words></direction-type>'
            f'</direction>\n')


def rehearsal(mark):
    return ('      <direction placement="above"><direction-type>'
            f'<rehearsal>{mark}</rehearsal></direction-type></direction>\n')


def harmony_xml(chord, beat, div):
    step, alter, qual, bass = chord
    kind, ktext = CHORD_KINDS[qual]
    off = (beat - 1.0) * div
    if abs(off - round(off)) > 1e-6:
        fail(f"chord offset at beat {beat} is not integral at divisions {div}")
    out = ['      <harmony>',
           f'        <root><root-step>{step}</root-step>' +
           (f'<root-alter>{alter}</root-alter>' if alter else '') + '</root>',
           f'        <kind text="{ktext}">{kind}</kind>']
    if bass:
        bs = re.fullmatch(r'([A-G])([b#]?)', bass)
        ba = {'b': -1, '#': 1, '': 0}[bs.group(2)]
        out.append(f'        <bass><bass-step>{bs.group(1)}</bass-step>' +
                   (f'<bass-alter>{ba}</bass-alter>' if ba else '') + '</bass>')
    if round(off):
        out.append(f'        <offset>{int(round(off))}</offset>')
    out.append('      </harmony>')
    return "\n".join(out) + "\n"


SLASH_PITCH = {'G': ('B', 4), 'F': ('D', 3), 'C': ('C', 4),
               'percussion': ('B', 4)}

FLATS = 'BEADGCF'
SHARPS = 'FCGDAEB'


def key_alter(step, fifths):
    """The key signature's alteration for a step — so a slash note spelled
    on the middle line never earns an accidental (MuseScore renders the
    'unpitched' trick as a pitched natural, measured on the Bb chart)."""
    if fifths < 0:
        return -1 if step in FLATS[:-fifths] else 0
    if fifths > 0:
        return 1 if step in SHARPS[:fifths] else 0
    return 0


def slash_bar(div, clef, staves, fifths):
    step, octv = SLASH_PITCH.get(clef, ('B', 4))
    alter = key_alter(step, fifths)
    if clef == 'percussion':
        pitch = ('        <unpitched><display-step>%s</display-step>'
                 '<display-octave>%d</display-octave></unpitched>'
                 % (step, octv))
    else:
        pitch = ('        <pitch><step>%s</step>%s<octave>%d</octave></pitch>'
                 % (step,
                    f'<alter>{alter}</alter>' if alter else '', octv))
    out = []
    for _ in range(BEATS):
        out += ['      <note>',
                pitch,
                f'        <duration>{div}</duration>',
                '        <voice>1</voice>',
                '        <type>quarter</type>',
                '        <stem>none</stem>',
                '        <notehead>slash</notehead>']
        if staves > 1:
            out.append('        <staff>1</staff>')
        out.append('      </note>')
    if staves > 1:
        out += [f'      <backup><duration>{div * BEATS}</duration></backup>',
                '      <note>',
                '        <rest measure="yes"/>',
                f'        <duration>{div * BEATS}</duration>',
                '        <voice>2</voice>',
                '        <staff>2</staff>',
                '      </note>']
    return "\n".join(out) + "\n"


def rest_bar(div, staves):
    out = []
    for staff in range(1, staves + 1):
        if staff == 2:
            out.append(f'      <backup><duration>{div * BEATS}</duration>'
                       '</backup>')
        out += ['      <note>',
                '        <rest measure="yes"/>',
                f'        <duration>{div * BEATS}</duration>',
                f'        <voice>{staff}</voice>']
        if staves > 1:
            out.append(f'        <staff>{staff}</staff>')
        out.append('      </note>')
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ compile

def resolve_groups(band):
    labels = [b['label'] for b in band]
    inst = {b['label']: b['instrument'].lower() for b in band}
    g = {'all': labels[:],
         'saxes': [l for l in labels if 'sax' in inst[l]],
         'trumpets': [l for l in labels if 'trumpet' in inst[l]],
         'trombones': [l for l in labels if 'trombone' in inst[l]],
         'rhythm': [l for l in labels if inst[l] in
                    ('guitar', 'piano', 'bass', 'acoustic bass',
                     'electric bass', 'drums', 'drum set', 'organ')]}
    g['horns'] = [l for l in labels
                  if l in g['saxes'] or l in g['trumpets'] or
                  l in g['trombones']]
    g['band'] = labels[:]
    return g


def compile_chart(chart_path, outdir):
    chart = parse_chart(chart_path)
    hdr = chart['header']
    if hdr.get('meter', '4/4') != '4/4':
        fail("only 4/4 charts compile in this increment")
    src_path = hdr.get('source')
    if src_path and not os.path.isabs(src_path):
        src_path = os.path.join(os.path.dirname(os.path.abspath(chart_path)),
                                src_path)
    source = load_source(src_path) if src_path and os.path.exists(src_path) \
        else None
    if hdr.get('source') and source is None:
        fail(f"source score '{hdr['source']}' not found next to the chart")

    band = chart['band']
    groups = resolve_groups(band)
    labels = [b['label'] for b in band]
    src_of = {}
    if source:
        for b in band:
            src_of[b['label']] = match_part(b['label'], source.keys())

    chord_parts = {l for l in labels
                   if l in groups['rhythm'] and
                   'drum' not in next(b for b in band
                                      if b['label'] == l)['instrument'].lower()}

    # ---- resolve every part x section into a content plan
    plans = []           # per section: {'start': bar, ...}
    start = 1
    for sec in chart['sections']:
        plan = {'sec': sec, 'start': start,
                'content': {l: ('default', None) for l in labels},
                'texts': {l: [] for l in labels}}
        for target, instr, loc in sec['directives']:
            tgts = groups.get(target) or ([target] if target in labels else None)
            if tgts is None:
                fail(f"{loc}: '{target}' is not a band part or group")
            anns, engraved, groove_words = [], None, None
            for piece in [p.strip() for p in instr.split(',')]:
                m = re.match(r'as engraved bars (\d+)-(\d+)'
                             r'(?:\s+at bar (\d+))?$', piece)
                if m:
                    engraved = (int(m.group(1)), int(m.group(2)),
                                int(m.group(3) or 1))
                    continue
                m = re.match(r'groove(?:\s+"([^"]*)")?$', piece)
                if m:
                    groove_words = m.group(1) or ''
                    continue
                m = re.match(r'text "([^"]*)"(?:\s+at bar (\d+))?$', piece)
                if m:
                    anns.append((int(m.group(2) or 1), m.group(1)))
                    continue
                if piece == 'tacet':
                    engraved = 'tacet'
                    continue
                if piece in ('solo', 'solo open'):
                    anns.append((1, 'solos (open)' if 'open' in piece
                                 or sec['open'] else 'Solo'))
                    continue
                if piece == 'backgrounds':
                    anns.append((1, 'backgrounds'))
                    continue
                if piece == 'on cue':
                    if anns and anns[-1][1] == 'backgrounds':
                        anns[-1] = (anns[-1][0], 'backgrounds on cue')
                    else:
                        anns.append((1, 'on cue'))
                    continue
                fail(f"{loc}: instruction '{piece}' is not built yet")
            for l in tgts:
                if engraved == 'tacet':
                    plan['content'][l] = ('tacet', None)
                elif engraved:
                    if not source:
                        fail(f"{loc}: 'as engraved' needs a source: line")
                    plan['content'][l] = ('engraved', engraved)
                elif groove_words is not None:
                    plan['content'][l] = ('groove', groove_words)
                plan['texts'][l].extend(anns)
        for bar, kind, text in sec['events']:
            for l in labels:
                plan['texts'][l].append((bar, text))
        plans.append(plan)
        start += sec['bars']
    total = start - 1

    # ---- emit one part's measures
    def part_measures(label, with_directions, with_harmony):
        b = next(x for x in band if x['label'] == label)
        default_groove = label in groups['rhythm']
        sp = source[src_of[label]] if source else None
        div = sp['div'] if sp else 8
        staves = sp['staves'] if sp else 1
        clef = sp['clef'] if sp else 'G'
        fifths = sp['fifths'] if sp else 0
        governing = [None]      # printed-chord state, carried across bars
        out = []

        pk = chart['pickup']
        if pk:
            content = ''
            if pk['engraved'] and sp and '0' in sp['measures']:
                content = strip_lifted(sp['measures']['0'], clef == 'percussion')
            if with_directions:
                if hdr.get('feel'):
                    content = direction(hdr['feel'].capitalize()) + content
                for t in pk['texts']:
                    content = direction(t, 'below') + content
            out.append(f'    <measure implicit="yes" number="0">\n{content}'
                       '    </measure>\n')

        for plan in plans:
            sec = plan['sec']
            kind, arg = plan['content'][label]
            if kind == 'default':
                kind = 'groove' if default_groove else 'tacet'
                arg = '' if kind == 'groove' else None
            for off in range(sec['bars']):
                absbar = plan['start'] + off
                pieces = []
                if with_directions and off == 0:
                    mark = sec['name']
                    if re.fullmatch(r'[A-Z]|\d+', mark):
                        pieces.append(rehearsal(mark))
                    if sec['label']:
                        pieces.append(direction(sec['label']))
                    if sec['feel']:
                        pieces.append(direction(sec['feel']))
                    if kind == 'groove' and arg:
                        pieces.append(direction(arg))
                if with_directions:
                    for tbar, text in sorted(plan['texts'][label]):
                        if tbar == off + 1:
                            pieces.append(direction(text, 'above'))
                if with_harmony and clef != 'percussion' and (
                        label in chord_parts or any(
                            t[1].startswith('solos') for t in
                            plan['texts'][label])):
                    for beat, chord in sec['content'][off]:
                        if chord is None:
                            continue
                        if chord != governing[0] or off == 0:
                            pieces.append(harmony_xml(chord, beat, div))
                        governing[0] = chord
                if kind == 'engraved':
                    lo, hi, at = arg
                    idx = absbar - (plan['start'] + at - 1)
                    srcbar = lo + idx
                    if 0 <= idx <= hi - lo:
                        if str(srcbar) not in sp['measures']:
                            fail(f"{label}: source has no bar {srcbar}")
                        pieces.append(strip_lifted(sp['measures'][str(srcbar)],
                                                   clef == 'percussion'))
                    else:
                        pieces.append(rest_bar(div, staves))
                elif kind == 'groove':
                    pieces.append(slash_bar(div, clef, staves, fifths))
                else:
                    pieces.append(rest_bar(div, staves))

                barline = ''
                open_bl = ''
                if sec['repeat'] and off == 0:
                    open_bl = ('      <barline location="left">'
                               '<bar-style>heavy-light</bar-style>'
                               '<repeat direction="forward"/></barline>\n')
                if sec['repeat'] and off == sec['bars'] - 1:
                    barline = ('      <barline location="right">'
                               '<bar-style>light-heavy</bar-style>'
                               f'<repeat direction="backward" '
                               f'times="{sec["repeat"]}"/></barline>\n')
                out.append(f'    <measure number="{absbar}">\n' + open_bl +
                           "".join(pieces) + barline + '    </measure>\n')
        return "".join(out)

    # ---- whole documents
    def document(part_labels, directions_on, harmony_on):
        L = [XMLHEAD, '<score-partwise version="3.1">\n',
             '  <work><work-title>%s</work-title></work>\n' %
             hdr.get('title', 'Untitled'),
             '  <identification>']
        if hdr.get('composer'):
            L.append('<creator type="composer">%s</creator>' % hdr['composer'])
        if hdr.get('arranger'):
            L.append('<creator type="arranger">%s</creator>' % hdr['arranger'])
        L.append('<encoding><software>Copyist chartc</software></encoding>'
                 '</identification>\n')
        L.append('  <part-list>\n')
        for i, l in enumerate(part_labels, 1):
            name = src_of.get(l, l)
            L.append(f'    <score-part id="P{i}">'
                     f'<part-name>{name}</part-name></score-part>\n')
        L.append('  </part-list>\n')
        for i, l in enumerate(part_labels, 1):
            L.append(f'  <part id="P{i}">\n')
            L.append(part_measures(l, directions_on(l), harmony_on(l)))
            L.append('  </part>\n')
        L.append('</score-partwise>\n')
        return "".join(L)

    os.makedirs(outdir, exist_ok=True)
    title = hdr.get('title', 'chart')
    score_path = os.path.join(outdir, f'{title} — score.musicxml')
    with open(score_path, 'w', encoding='utf-8') as f:
        f.write(document(labels,
                         directions_on=lambda l: l == labels[0],
                         harmony_on=lambda l: l in chord_parts))
    written = [score_path]
    for l in labels:
        p = os.path.join(outdir, f'{title} — {src_of.get(l, l)}.musicxml')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(document([l], directions_on=lambda _: True,
                             harmony_on=lambda _: True))
        written.append(p)
    print(f"chartc: wrote {len(written)} files, {total} bars, "
          f"{len(chart['sections'])} sections.")
    return written


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('chart')
    ap.add_argument('-o', '--outdir', default='chart-build')
    a = ap.parse_args()
    compile_chart(a.chart, a.outdir)
