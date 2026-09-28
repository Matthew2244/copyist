#!/usr/bin/env python3
"""chartdrums — tell Copyist what your drum library's notes are, once.

    chart.py "My Tune.chart" drums

Many drum libraries (Tony Royster Jr., Superior Drummer, Addictive
Drums, any Kontakt kit) keep their note map in the plugin, not on disk,
and not all of it is General MIDI. This walks every note a drum part's
demo plays and asks what it is on that kit:

    drums: note 39, played 20 times, first in bar 5. General MIDI calls
    it clap. What is it on your kit?

Say it the way a drummer does ("snare roll", "cross stick", "ride
bell", "china"). Enter keeps the General MIDI reading. The answers are
saved as a drum map named for the library, in
~/.config/copyist/drummaps/, and the part's band line learns
`drummap "NAME"` — every take from that kit reads right from then on.
"""
import os
import re
import sys
from collections import Counter

import chartc
import chartdemo
import instruments
from chartedit import ask, say
from chartkeys import link_band_line

DRUM_DIR = os.path.expanduser("~/.config/copyist/drummaps")


def load_saved(name):
    """A saved drum map: {note: the drummer's words}."""
    path = saved_path(name)
    out = {}
    if path and os.path.exists(path):
        for ln in open(path, encoding='utf-8'):
            m = re.match(r'\s*(\d{1,3})\s+(.+?)\s*$', ln)
            if m and not ln.lstrip().startswith('#'):
                out[int(m.group(1))] = m.group(2)
    return out


def saved_path(name):
    if os.path.isdir(DRUM_DIR):
        for fn in os.listdir(DRUM_DIR):
            if os.path.splitext(fn)[0].lower() == name.strip().lower():
                return os.path.join(DRUM_DIR, fn)
    return os.path.join(DRUM_DIR, name.strip() + ".txt")


def as_gm(words_map):
    """{note: words} -> {note: GM note} for the compiler; a word that
    names no kit piece keeps its note."""
    out = {}
    for n, w in words_map.items():
        g = instruments.gm_for_words(w)
        out[n] = g if g is not None else n
    return out


def artics(words_map):
    """{note: words} -> {note: 'ghost' | 'flam' | ...} for the strokes
    a drummer named along with the piece."""
    out = {}
    for n, w in words_map.items():
        a = instruments.drum_artic(w)
        if a:
            out[n] = a
    return out


def demo_notes(chart, chart_path, band):
    """Every note a drum part's demo plays: Counter and first bar."""
    here = os.path.dirname(os.path.abspath(chart_path))
    src = band.get('demo')
    if src and src.lower().endswith(('.mid', '.midi')):
        path, track = src, None
    else:
        path, track = chart['header'].get('demo'), src
    if not path:
        return None, None
    path = path if os.path.isabs(path) else os.path.join(here, path)
    dm = chartdemo.load_demo(path)
    notes = dm.track(track)
    first = {}
    for n in sorted(notes, key=lambda n: n.on):
        first.setdefault(n.pitch, dm.bar_of(n.on))
    return Counter(n.pitch for n in notes), first


def name_drums(chart_path):
    chart = chartc.parse_chart(chart_path)
    title = chart['header'].get('title', 'Untitled')
    drums = [b for b in chart['band']
             if chartc.canonical_instrument(b['instrument']) in
             ('drums', 'drum set') and b.get('demo')]
    if not drums:
        say("No drum part here plays from a demo, so there's nothing "
            "to name.")
        return 0
    for b in drums:
        counts, first = demo_notes(chart, chart_path, b)
        if not counts:
            say(f"{b['label']}: I couldn't find its demo.")
            continue
        name = b.get('drummap')
        builtin = instruments.DRUM_MAPS.get(
            instruments.DRUM_MAP_NAMES.get((name or '').strip().lower(),
                                           ''), {})
        if not name:
            name = ask(f"{b['label']}: which drum library was this take "
                       "played on? That names the map, so every take from "
                       "it reads right.", f"{title} drums").strip() \
                or f"{title} drums"
        known = load_saved(name)
        # a built-in map already knows its notes: ask only about the
        # rest (a kit's Flexi percussion), added on top of it
        todo = [n for n in sorted(counts)
                if n not in known and (n not in builtin or builtin[n] >=
                                       instruments.UNNAMED_DRUM)]
        if not todo:
            say(f'Every note in {b["label"]}\'s take is already in '
                f'"{name}".')
            continue
        say(f"{len(todo)} note(s) to name for {b['label']}. Say what each "
            "is on that kit, like snare roll, cross stick, ride bell, "
            "china or conga slap. Name the stroke too when there is one: "
            "snare ghost prints in parentheses. Enter keeps the General "
            "MIDI name.")
        added = {}
        for n in todo:
            gm = instruments.drum_name(n)
            ans = ask(f"{b['label']}: note {n}, played {counts[n]} "
                      f"time{'s' if counts[n] != 1 else ''}, first in bar "
                      f"{first[n]}. General MIDI calls it {gm}. What is it "
                      "on your kit?").strip()
            if not ans:
                continue
            if instruments.gm_for_words(ans) is None:
                say(f"I don't know '{ans}' as a kit piece yet, so note "
                    f"{n} stays {gm}. Try words like snare, kick, hi-hat, "
                    "ride, crash, china, tom, conga or shaker.")
                continue
            added[n] = ans
            say(f"Note {n} is {ans}.")
        if added:
            os.makedirs(DRUM_DIR, exist_ok=True)
            path = saved_path(name)
            with open(path, 'a', encoding='utf-8') as f:
                if not known:
                    f.write(f"# drum map for {name}, named by the writer\n")
                for n, w in sorted(added.items()):
                    f.write(f"{n} {w}\n")
            if not b.get('drummap'):
                link_band_line(chart_path, b['label'], name,
                               attr='drummap')
            say(f'Saved {len(added)} note(s) in the drum map "{name}". '
                "Build again and the page and the band follow them.")
        else:
            say("Nothing named; nothing changed.")
    return 0


if __name__ == '__main__':
    sys.exit(name_drums(sys.argv[1]))
