#!/usr/bin/env python3
"""chartnew — interview a starter chart into existence.

    chart.py "My Tune.chart" new --demo horns.mid

One question at a time, every question stating its default (a screen
reader user must never have to answer something to discover what it was
set to). The demo is scanned first, so the interview already knows each
track's name, note count and range — and it proposes the octave
correction by evidence: a track sitting above its instrument's sounding
range is a recording convention, not a voicing.

The scaffold it writes is annotated with each part's activity map — who
plays which bars — because that is the first thing a writer wants to
know when carving sections.
"""
import os
import sys

import chartc
import chartdemo

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def pname(p):
    return f"{NAMES[p % 12]}{p // 12 - 1}"


def ask(question, default=""):
    """One prompt, stating its default; Enter keeps it."""
    suffix = f" (now: {default})" if default != "" else ""
    sys.stdout.write(f"{question}{suffix}: ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        return default
    line = line.strip()
    return line if line else default


def sniff_octave(pitches, rng):
    """Propose an octave shift when the played register disagrees with
    the instrument's sounding range — the voicing-stack lesson."""
    lo, hi = rng
    for shift in (0, -1, 1):
        inside = sum(1 for p in pitches if lo <= p + 12 * shift <= hi)
        if inside >= len(pitches) * 0.9:
            return shift
    return 0


def spans(notes, division):
    """Bar spans of activity, in the demo's own bar numbers."""
    bars = sorted({int(n.on // (division * 4)) + 1 for n in notes})
    runs = []
    for b in bars:
        if runs and b - runs[-1][1] <= 1:
            runs[-1][1] = b
        else:
            runs.append([b, b])
    return ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in runs)


def interview(out_path, demo_path):
    if os.path.exists(out_path):
        sys.exit(f"chart: {out_path} already exists — I will not write "
                 "over a chart. Pick a new name.")
    if not demo_path:
        demo_path = ask("Which MIDI file is the demo")
    if not demo_path or not os.path.exists(demo_path):
        sys.exit("chart: the interview starts from a demo MIDI and that "
                 "one is not there. Export it, then come back.")

    dm = chartdemo.load_demo(demo_path)
    say = print
    tracks = [(ti, dm.names.get(ti, f"track {ti}"), dm.tracks[ti])
              for ti in sorted(dm.tracks)]
    say(f"Read it: {len(tracks)} playing track(s) in "
        f"{os.path.basename(demo_path)}.")

    # tempo and count-in read from the file, offered as defaults
    import analyze
    mid = analyze.parse_midi(demo_path)
    ex = analyze.extract(mid)
    tempo_default = ""
    if ex["tempos"]:
        tempo_default = str(round(60_000_000 / ex["tempos"][0][1]))
    first_bar = min(int(n.on // (dm.division * 4)) + 1
                    for ns in dm.tracks.values() for n in ns)
    countin_default = "1" if first_bar > 1 else "0"

    title = ask("Title", os.path.splitext(os.path.basename(out_path))[0])
    composer = ask("Composer", "")
    key = ask("Key, like Eb minor or F", "C")
    tempo = ask("Tempo", tempo_default)
    countin = ask("Count-in bars in the demo", countin_default)
    dyn = ask("Dynamics: pedal reads your CC 11, by hand means you "
              "dictate", "pedal")

    band, notes_by_label = [], {}
    say(f"Now the band — {len(chartc.HORNS)} instruments from piccolo "
        "to bass voice to congas, and nicknames work (kit, vibes, "
        "upright bass, bone). Name each track's instrument, or leave "
        "one blank to skip that track.")
    for ti, name, notes in tracks:
        pitches = [n.pitch for n in notes]
        info = (f'Track "{name}": {len(notes)} notes, '
                f'{pname(min(pitches))} to {pname(max(pitches))}. '
                'Instrument')
        inst = ask(info, "")
        if not inst:
            continue
        inst = chartc.canonical_instrument(inst)
        if inst not in chartc.HORNS:
            say(f"  {inst} is not in the instrument table yet — skipping "
                "this track; ask for it to be added, it takes a minute.")
            continue
        shift = sniff_octave(pitches, chartc.HORNS[inst]['fold'])
        if shift:
            keep = ask(f'  That track sits an octave '
                       f'{"high" if shift < 0 else "low"} for a '
                       f'{inst} — write octave {shift:+d}? yes or no',
                       "yes")
            if keep.lower().startswith('n'):
                shift = 0
        label = ask("  Part label", inst)
        band.append((label, inst, name, shift))
        notes_by_label[label] = (notes, name)

    if not band:
        sys.exit("chart: no parts named, no chart written.")

    total = max(int(n.on // (dm.division * 4)) + 1
                for ns in dm.tracks.values() for n in ns) - int(countin or 0)

    lines = [f"# {title} — started by the chart interview. The activity",
             "# map below says who plays which bars (demo numbering);",
             "# carve your sections from it, then replace this one big",
             "# section. CHART-WRITING.md is the guide.",
             ""]
    for label, inst, tname, shift in band:
        notes, _ = notes_by_label[label]
        lines.append(f"# {label} plays demo bars {spans(notes, dm.division)}")
    lines += ["",
              f"title: {title}"]
    if composer:
        lines.append(f"composer: {composer}")
    lines += [f"key: {key}",
              "meter: 4/4",
              f"tempo: {tempo}" if tempo else "# tempo: none stated",
              f"demo: {os.path.relpath(demo_path, os.path.dirname(os.path.abspath(out_path)))}"]
    if int(countin or 0):
        lines.append(f"countin: {countin}")
    if dyn.lower().startswith("h") or "hand" in dyn.lower():
        lines.append("dynamics: by hand")
    lines += ["", "band:"]
    for label, inst, tname, shift in band:
        piece = f"  {label}" + (f" = {inst}" if label != inst else "")
        piece += f', demo "{tname}"'
        if shift:
            piece += f" octave {shift:+d}"
        lines.append(piece)
    lines += ["",
              f"section A, {total} bars",
              f"  chords: nc x{total}",
              "# give each part its lines, e.g.:"]
    for label, inst, tname, shift in band[:1]:
        notes, _ = notes_by_label[label]
        lines.append(f"#   {label}: from demo bars "
                     f"{spans(notes, dm.division).split(',')[0].strip()}")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")
    say(f"Wrote {out_path}: {len(band)} part(s), one {total}-bar section "
        "to carve up. Next: edit it, then run the build.")
