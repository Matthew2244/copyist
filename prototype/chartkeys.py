#!/usr/bin/env python3
"""chartkeys — name the keyswitches a demo played, once.

    chart.py "My Tune.chart" keys

Compiles the chart quietly, finds every keyswitch that has no name yet
(the findings list them part by part), and asks about each one:

    violin: F#1 (MIDI 30) comes in before bar 5. What does it do?

The answer goes where that part's map lives: the chart's own
`keyswitches "NAME":` block when it has one, else a saved library map in
~/.config/copyist/keyswitches/ (so every chart using that patch knows
it). A part with no map yet gets one, named after the tune and the part,
and its band line learns to use it. Enter skips a key; nothing is
written for a skipped key.
"""
import io
import os
import re
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

import chartc
from chartedit import ask, say

UNNAMED = re.compile(r'^(?P<part>.+?): keyswitch (?P<name>\S+) \(MIDI '
                     r'(?P<midi>\d+)\) governs bars (?P<bars>.+?) but has '
                     r'no name yet')


def unnamed_keys(chart_path):
    """[(part label, midi, note name, bars text)] from a quiet compile."""
    tmp = tempfile.mkdtemp()
    text = ''
    try:
        with redirect_stdout(io.StringIO()):
            chartc.compile_chart(chart_path, tmp)
        for fn in os.listdir(tmp):
            if fn.endswith('findings.txt'):
                text = open(os.path.join(tmp, fn), encoding='utf-8').read()
    except SystemExit as e:
        raise SystemExit(f"The chart doesn't compile yet: {e.code}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = []
    for ln in text.splitlines():
        ln = re.sub(r'^finding:\s*', '', ln.strip())
        m = UNNAMED.match(ln)
        if m:
            out.append((m.group('part'), int(m.group('midi')),
                        m.group('name'), m.group('bars')))
    return out


def save_saved_map(name, midi, word):
    """Add or replace one key in a saved library map."""
    os.makedirs(chartc.KS_DIR, exist_ok=True)
    path = None
    for fn in os.listdir(chartc.KS_DIR):
        if os.path.splitext(fn)[0].lower() == name.lower():
            path = os.path.join(chartc.KS_DIR, fn)
    path = path or os.path.join(chartc.KS_DIR, name + ".txt")
    lines = open(path, encoding='utf-8').read().splitlines() \
        if os.path.exists(path) else []
    keep = []
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith('#'):
            try:
                k, _w = chartc.parse_ks_line(s, "saved map")
                if k == midi:
                    continue
            except SystemExit:
                pass
        keep.append(ln)
    keep.append(f"{midi} {word}")
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(keep) + "\n")
    return path


def add_to_chart_block(chart_path, name, midi, word):
    """Add a key line to the chart's own `keyswitches "NAME":` block."""
    lines = open(chart_path, encoding='utf-8').read().split('\n')
    head = next(i for i, ln in enumerate(lines)
                if re.match(r'keyswitches "%s":\s*$' % re.escape(name),
                            ln.strip(), re.I) and not ln[:1].isspace())
    j = head + 1
    while j < len(lines) and (lines[j][:1] in (' ', '\t')):
        j += 1
    lines.insert(j, f"  {midi} {word}")
    open(chart_path, 'w', encoding='utf-8').write('\n'.join(lines))


def link_band_line(chart_path, label, name, attr='keyswitches'):
    """Give a part's band line `, keyswitches "NAME"` (or drummap)."""
    lines = open(chart_path, encoding='utf-8').read().split('\n')
    in_band = False
    for i, ln in enumerate(lines):
        if ln.strip() == 'band:' and not ln[:1].isspace():
            in_band = True
            continue
        if in_band and ln.strip() and not ln[:1].isspace():
            in_band = False
        if in_band and ln[:1].isspace() and re.match(
                r'\s*%s(\s*=|\s*,|\s*$)' % re.escape(label), ln) \
                and f'{attr} "' not in ln:
            if attr == 'keyswitches' and ', drummap "' in ln:
                # the band line's order: keyswitches before drummap
                a, b_ = ln.split(', drummap "', 1)
                lines[i] = a + f', keyswitches "{name}", drummap "' + b_
            else:
                lines[i] = ln.rstrip() + f', {attr} "{name}"'
            break
    open(chart_path, 'w', encoding='utf-8').write('\n'.join(lines))


def name_keys(chart_path):
    try:
        todo = unnamed_keys(chart_path)
    except SystemExit as e:
        say(str(e.code))
        return 1
    if not todo:
        say("Every keyswitch in this chart's demos already has a name.")
        return 0
    chart = chartc.parse_chart(chart_path)
    title = chart['header'].get('title', 'Untitled')
    bands = {b['label']: b for b in chart['band']}
    say(f"{len(todo)} keyswitch(es) without a name. For each, say what it "
        "does, like staccato, pizzicato, marcato, harmon mute, or the "
        "library's own name for it. Enter skips one.")
    named = 0
    for part, midi, note, bars in todo:
        where_ = re.sub(r', ([^,]+)$', r' and \1', bars)
        word = ask(f"{part}: {note} (MIDI {midi}) is in effect in "
                   f"bar{'s' if (',' in bars or 'more' in bars) else ''} "
                   f"{where_}. What does it do?").strip()
        if not word:
            continue
        b = bands.get(part) or {}
        mapname = b.get('keyswitches')
        if mapname and mapname.lower() in chart.get('keyswitches', {}):
            add_to_chart_block(chart_path, mapname, midi, word)
            where = "the chart's own list"
        else:
            if not mapname:
                mapname = f"{title} {part}"
                link_band_line(chart_path, part, mapname)
                bands[part] = dict(b, keyswitches=mapname)
            save_saved_map(mapname, midi, word)
            where = f'the saved map "{mapname}"'
        named += 1
        say(f"{note} is {word}, in {where}.")
    say(f"Named {named} of {len(todo)}. Build again and the page marks "
        "them." if named else "Nothing named; nothing changed.")
    return 0


if __name__ == '__main__':
    sys.exit(name_keys(sys.argv[1]))
