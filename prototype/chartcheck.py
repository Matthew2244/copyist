#!/usr/bin/env python3
"""Verify a .chart file's harmony and form against a source MusicXML score.

Reference implementation of the CHART-FORMAT.md bars grammar (§3.3), and the
machine check behind the worked example: the chart's governing-chord timeline
is compared against the score's harmony events at eighth-note resolution, and
every section's start bar is compared against the score's rehearsal marks.

Usage: chartcheck.py <file.chart> <score.musicxml>

Exit 0 only if every check passes. Errors are sentences, not stack traces.
"""
import re
import sys

KIND = {
    'dominant': '7', 'dominant-ninth': '9', 'dominant-11th': '11',
    'dominant-13th': '13', 'minor-seventh': 'm7', 'minor-ninth': 'm9',
    'major': 'maj', 'major-seventh': 'maj7', 'minor': 'm',
    'diminished': 'dim', 'diminished-seventh': 'dim7',
    'suspended-fourth': 'sus4', 'augmented': 'aug',
    'major-sixth': '6', 'minor-sixth': 'm6',
    'half-diminished': 'm7b5',
}


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


# ---------------- chart side ----------------

def parse_beat(tok):
    """All three equivalent off-beat spellings parse: 2+, 2.5, and-of-2."""
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


def norm_chord(sym):
    if sym == 'nc':
        return None
    if re.fullmatch(r'[A-G][b#]?', sym):
        return sym + 'maj'
    return sym


def parse_bars(text, where):
    """One chords line -> list of bars; each bar is a list of (beat, chord)."""
    bars = []
    for raw in text.split(','):
        raw = raw.strip()
        if not raw:
            fail(f"empty bar in {where}")
        m = re.fullmatch(r'(.*?)\s+x(\d+)', raw)
        reps = 1
        if m:
            raw, reps = m.group(1).strip(), int(m.group(2))
        bar = []
        for tok in raw.split():
            if '@' in tok:
                sym, beat = tok.split('@', 1)
                bar.append((parse_beat(beat), norm_chord(sym)))
            else:
                bar.append((None, norm_chord(tok)))
        n = len(bar)
        placed = [b for b, _ in bar if b is not None]
        beats_in_bar = 4.0  # 4/4 assumed for placement of unplaced chords
        out = []
        for i, (b, c) in enumerate(bar):
            if b is None:
                b = 1.0 + i * (beats_in_bar / n) if not placed else 1.0
            out.append((b, c))
        bars.extend([out] * reps)
    return bars


def parse_chart(path):
    defs, sections = {}, []
    cur = None
    for lineno, line in enumerate(open(path, encoding='utf-8'), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        m = re.match(r'chords ([\w ]+?):\s*(.+)$', s)
        if m and cur is None or (m and not line.startswith((' ', '\t'))):
            defs[m.group(1).strip()] = parse_bars(m.group(2), f"chords {m.group(1)}")
            continue
        m = re.match(r'section ([\w ]+?)(?:,\s*(\d+) bars)?(?:,.*)?$', s)
        if m:
            cur = {'name': m.group(1).strip(),
                   'bars': int(m.group(2)) if m.group(2) else None,
                   'content': None, 'line': lineno}
            sections.append(cur)
            continue
        if cur is not None:
            m = re.match(r'chords:\s*(.+)$', s)
            if m:
                cur['content'] = parse_bars(m.group(1), f"section {cur['name']}")
                continue
            m = re.match(r'use chords ([\w ]+?)(?:\s+x(\d+))?$', s)
            if m:
                name = m.group(1).strip()
                if name not in defs:
                    fail(f"section {cur['name']} uses chords '{name}', which is not defined")
                cur['content'] = defs[name] * (int(m.group(2)) if m.group(2) else 1)
                continue
        if s.startswith('ending'):
            fail("this checker does not support endings yet")
    for sec in sections:
        if sec['content'] is None:
            fail(f"section {sec['name']} has no chords")
        if sec['bars'] is not None and len(sec['content']) != sec['bars']:
            fail(f"section {sec['name']} declares {sec['bars']} bars but its chords cover {len(sec['content'])}")
    return sections


# ---------------- score side ----------------

def score_events(path):
    xml = open(path, encoding='utf-8').read()
    id2name = dict(re.findall(
        r'<score-part id="([^"]+)">.*?<part-name[^>]*>([^<]*)</part-name>', xml, re.S))
    hpid = max(id2name, key=lambda p: re.search(
        r'<part id="%s">(.*?)</part>' % p, xml, re.S).group(1).count('<harmony'))
    body = re.search(r'<part id="%s">(.*?)</part>' % hpid, xml, re.S).group(1)
    div, events, marks, nbars = 8, [], {}, 0
    for num, m in re.findall(r'<measure [^>]*?number="([^"]+)"[^>]*>(.*?)</measure>', body, re.S):
        bar = int(num)
        nbars = max(nbars, bar)
        dv = re.search(r'<divisions>(\d+)</divisions>', m)
        if dv:
            div = int(dv.group(1))
        pos = 0
        for tag in re.finditer(r'<(harmony|note|backup|forward)[^>]*>(.*?)</\1>', m, re.S):
            kind, t = tag.group(1), tag.group(2)
            if kind == 'harmony':
                r = re.search(r'<root-step>(\w)</root-step>', t).group(1)
                alter = re.search(r'<root-alter>(-?\d+)</root-alter>', t)
                a = int(alter.group(1)) if alter else 0
                r += 'b' if a == -1 else '#' if a == 1 else ''
                kv = re.search(r'<kind[^>]*>([^<]*)</kind>', t).group(1).strip()
                if kv not in KIND:
                    fail(f"score uses chord kind '{kv}' this checker does not map")
                off = re.search(r'<offset>(-?\d+)</offset>', t)
                p = pos + (int(off.group(1)) if off else 0)
                events.append((bar, p / div + 1, r + KIND[kv]))
            else:
                d = re.search(r'<duration>(\d+)</duration>', t)
                dur = int(d.group(1)) if d else 0
                if kind == 'note' and '<chord/>' not in t and not re.search(r'<grace', t.split('<duration')[0] if '<duration' in t else t):
                    pos += dur
                elif kind == 'backup':
                    pos -= dur
                elif kind == 'forward':
                    pos += dur
    # rehearsal marks from the first part that has them
    for pid in id2name:
        b = re.search(r'<part id="%s">(.*?)</part>' % pid, xml, re.S).group(1)
        for num, m in re.findall(r'<measure [^>]*?number="([^"]+)"[^>]*>(.*?)</measure>', b, re.S):
            for rh in re.findall(r'<rehearsal[^>]*>([^<]+)</rehearsal>', m):
                if re.fullmatch(r'[A-Z]', rh):
                    marks.setdefault(rh, int(num))
        if marks:
            break
    return events, marks, nbars


def timeline(pairs, nbars):
    """pairs: list of (bar, beat, chord) events -> governing chord at each
    eighth position of bars 1..nbars."""
    pairs = sorted(pairs, key=lambda e: (e[0], e[1]))
    out, i, cur = {}, 0, None
    for bar in range(1, nbars + 1):
        for eighth in range(8):
            beat = 1 + eighth * 0.5
            while i < len(pairs) and (pairs[i][0], pairs[i][1]) <= (bar, beat):
                cur = pairs[i][2]
                i += 1
            out[(bar, beat)] = cur
    return out


def main():
    chart_path, score_path = sys.argv[1], sys.argv[2]
    sections = parse_chart(chart_path)
    events, marks, nbars = score_events(score_path)

    # chart -> absolute events
    chart_events, start, starts = [], 1, {}
    for sec in sections:
        starts[sec['name']] = start
        for off, bar in enumerate(sec['content']):
            for beat, chord in bar:
                chart_events.append((start + off, beat, chord))
        start += len(sec['content'])
    total = start - 1
    if total != nbars:
        fail(f"chart covers {total} bars but the score has {nbars}")

    for mark, bar in sorted(marks.items(), key=lambda kv: kv[1]):
        if mark not in starts:
            fail(f"score has rehearsal mark {mark} at bar {bar}; the chart has no section named {mark}")
        if starts[mark] != bar:
            fail(f"section {mark} starts at bar {starts[mark]} in the chart but the score marks it at bar {bar}")

    tl_chart = timeline(chart_events, nbars)
    tl_score = timeline([(b, p, c) for b, p, c in events], nbars)
    diffs = [(k, tl_score[k], tl_chart[k]) for k in tl_score if tl_score[k] != tl_chart[k]]
    if diffs:
        for (bar, beat), want, got in sorted(diffs)[:10]:
            print(f"  bar {bar} beat {beat}: score says {want}, chart says {got}")
        fail(f"{len(diffs)} of {len(tl_score)} eighth-note positions disagree")

    print(f"OK: {total} bars, {len(marks)} rehearsal marks aligned, "
          f"{len(events)} harmony events, all {len(tl_score)} eighth-note "
          f"positions agree.")


if __name__ == '__main__':
    main()
