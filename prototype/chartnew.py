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
import re
import sys

import chartc
import chartdemo
from chartedit import ask, say

NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
MAJOR_BY_FIFTHS = ["Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C",
                   "G", "D", "A", "E", "B", "F#", "C#"]
MINOR_BY_FIFTHS = ["Ab", "Eb", "Bb", "F", "C", "G", "D", "A",
                   "E", "B", "F#", "C#", "G#", "D#", "A#"]


def key_name(fifths, minor):
    """A demo's key signature event, said the way the header takes it."""
    if not -7 <= fifths <= 7:
        return "C"
    if minor:
        return f"{MINOR_BY_FIFTHS[fifths + 7]} minor"
    return MAJOR_BY_FIFTHS[fifths + 7]


def compound(meter):
    """6/8, 9/8, 12/8: the tempo a drummer is given is the dotted
    quarter — the same test the compiler uses when it prints one."""
    return meter[1] == 8 and meter[0] % 3 == 0


def track_instrument(name):
    """A track already named for its instrument ("trumpet", "bone",
    "kit") offers that as the answer, so Enter is enough."""
    if not name:
        return ""
    inst = chartc.canonical_instrument(name)
    if inst in chartc.HORNS:
        return inst
    # "Trumpet 1", "tenor sax 2": the name with its chair number off
    bare = chartc.canonical_instrument(re.sub(r"\s*\d+$", "", name))
    return bare if bare in chartc.HORNS else ""


def pname(p):
    return f"{NAMES[p % 12]}{p // 12 - 1}"


def sniff_octave(pitches, rng):
    """Propose an octave shift when the played register disagrees with
    the instrument's sounding range — the voicing-stack lesson."""
    lo, hi = rng
    for shift in (0, -1, 1):
        inside = sum(1 for p in pitches if lo <= p + 12 * shift <= hi)
        if inside >= len(pitches) * 0.9:
            return shift
    return 0


def spans(notes, barof):
    """Bar spans of activity, in the demo's own bar numbers. `barof`
    maps a tick to a bar, so mixed-meter demos count their bars right."""
    bars = sorted({barof(n.on) for n in notes})
    runs = []
    for b in bars:
        if runs and b - runs[-1][1] <= 1:
            runs[-1][1] = b
        else:
            runs.append([b, b])
    return ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in runs)


SAX_BY_DEFAULT = {"alto": "alto sax", "tenor": "tenor sax",
                  # on a band list "bell" is the cowbell; "bells", plural,
                  # stays the glockenspiel, like every band room says it
                  "bell": "cowbell"}


def band_from_words(text):
    """'trumpet, 2 tenors, piano, bass and drums' -> [(label, inst)],
    each instrument by the name the band table knows, repeated chairs
    numbered (tenor 1, tenor 2). Unknown words come back separately."""
    wanted, unknown = [], []
    band_from_words.saxed = False
    band_from_words.belled = False
    text = re.sub(r"\band\b", ",", text)
    for raw in text.split(","):
        w = raw.strip().lower()
        if not w:
            continue
        m = re.match(r"^(\d+|two|three|four|five)\s+(.+)$", w)
        n = 1
        if m:
            n = {"two": 2, "three": 3, "four": 4, "five": 5}.get(
                m.group(1)) or int(m.group(1))
            w = m.group(2)
        inst = chartc.canonical_instrument(w)
        if inst not in chartc.HORNS and w.endswith("s"):
            inst = chartc.canonical_instrument(w[:-1])   # "trumpets"
        # on a band list a bare alto or tenor is the sax; the singer is
        # "alto voice" (said once, below)
        # plurals only for the saxes ("2 tenors"); "bells" is its own
        # instrument, the glockenspiel
        bare = w[:-1] if w.endswith("s") and w[:-1] in ("alto", "tenor") \
            else w
        if inst not in chartc.HORNS and bare in SAX_BY_DEFAULT:
            inst = SAX_BY_DEFAULT[bare]
            if bare == "bell":
                band_from_words.belled = True
            else:
                band_from_words.saxed = True
        if inst not in chartc.HORNS:
            unknown.append(raw.strip())
            continue
        # the label is the writer's own word ("bass", "tenor"), the
        # instrument the table's name for it
        word = bare if bare in SAX_BY_DEFAULT else (
            w[:-1] if w.endswith("s") and chartc.canonical_instrument(
                w) not in chartc.HORNS else w)
        # a bare "bass" stays bare: the chart's feel picks upright or
        # electric when it compiles
        wanted += [(word, 'bass' if word == 'bass' else inst)] * n
    band, seen, count = [], {}, {}
    for word, _ in wanted:
        seen[word] = seen.get(word, 0) + 1
    for word, inst in wanted:
        count[word] = count.get(word, 0) + 1
        label = word if seen[word] == 1 else f"{word} {count[word]}"
        band.append((label, inst))
    return band, unknown


def ask_until(prompt, default, check, help_):
    """Ask, and ask again until the answer reads, saying what's wanted;
    with no more answers coming, the default."""
    while True:
        got = ask(prompt, default)
        try:
            check(got)
            return got
        except (SystemExit, ValueError):
            say(f"'{got}' doesn't read as that. {help_}.")
            if ask.eof:
                return default


def interview_no_demo(out_path, composer='', cfg=None):
    """No demo yet: the header, then the band by name. The roadmap
    conversation writes the sections from here; the lines can come
    later, played or spoken."""
    title = ask("Title", os.path.splitext(os.path.basename(out_path))[0])
    composer = ask("Composer", composer)
    # a wrong answer asks again; it never ends the conversation
    key = ask_until("Key, like Eb minor or F", "C", chartc.parse_key,
                    "A key is a note name and maybe minor: F, Bb, "
                    "Eb minor, F sharp")
    meter_txt = ask_until("Meter, like 4/4 or 3/4 or 6/8", "4/4",
                          chartc.parse_meter,
                          "A meter is two numbers, like 4/4, 3/4, 6/8 "
                          "or 5/4")
    meter = chartc.parse_meter(meter_txt)
    tempo = ask_until("Tempo" + (", dotted quarter to the beat"
                                 if compound(meter) else ""), "120",
                      lambda t: float(t) if 20 <= float(t) <= 400
                      else chartc.fail("tempo out of range"),
                      "A tempo is a number of beats a minute, like 120")
    band = []
    while not band:
        words = ask("Who's in the band? Like: trumpet, tenor, piano, "
                    "bass, drums. Nicknames work, and '2 trumpets'",
                    "piano, bass, drums")
        band, unknown = band_from_words(words)
        if band_from_words.saxed:
            say("Alto and tenor read as saxes; say 'alto voice' or "
                "'tenor voice' for a singer.")
        if band_from_words.belled:
            say("The bell is the cowbell; say 'bells' for the "
                "glockenspiel.")
        if unknown:
            say("I don't have " + ", ".join(unknown) + " in the band "
                "table yet, so they're left out.")
        if not band and ask.eof:
            sys.exit("chart: no band named, no chart written.")
    say("The band: " + ", ".join(label for label, _ in band) + ".")
    lines = [f"title: {title}"]
    if composer:
        lines.append(f"composer: {composer}")
    lines += [f"key: {key}", f"meter: {meter[0]}/{meter[1]}",
              f"tempo: {tempo}", "", "band:"]
    for label, inst in band:
        lines.append(f"  {label}" + (f" = {inst}" if label != inst
                                     else ""))
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")
    name = os.path.basename(out_path)
    say(f"Wrote {name}: {len(band)} part(s), no sections yet. Next, "
        f"describe the tune: run 'chart {name} edit' and say it the way "
        "you'd tell the band, like: blues in F, swing at 140, head twice, "
        "solos for everybody, head out.")


def interview(out_path, demo_path, composer='', cfg=None):
    cfg = cfg or {}
    if os.path.exists(out_path):
        sys.exit(f"chart: {out_path} already exists — I will not write "
                 "over a chart. Pick a new name.")
    while not demo_path:
        demo_path = ask("Which MIDI file is the demo? Enter for none: "
                        "you describe the tune and name the band").strip()
        if not demo_path or demo_path.lower() in ("none", "no", "n"):
            return interview_no_demo(out_path, composer, cfg)
        found = demo_path if os.path.exists(demo_path) else None
        if not found and cfg.get('midi'):
            cand = os.path.join(os.path.expanduser(cfg['midi']), demo_path)
            found = cand if os.path.exists(cand) else None
        if not found:
            # a wrong answer re-asks; it never ends the conversation
            say(f"No MIDI file called '{demo_path}' here. Give its full "
                "path, or press Enter for no demo.")
            if ask.eof:
                sys.exit("chart: no demo and no answer — nothing written.")
            demo_path = ""
    # a bare filename looks in the midi folder — the settings desk's
    # 'midi' is where his DAW exports land
    if demo_path and not os.path.exists(demo_path) and \
            cfg.get('midi'):
        cand = os.path.join(os.path.expanduser(cfg['midi']), demo_path)
        if os.path.exists(cand):
            demo_path = cand
    if not demo_path or not os.path.exists(demo_path):
        sys.exit("chart: the interview starts from a demo MIDI and that "
                 "one is not there. Export it, then come back.")

    dm = chartdemo.load_demo(demo_path)
    tracks = [(ti, dm.names.get(ti, f"track {ti}"), dm.tracks[ti])
              for ti in sorted(dm.tracks)]
    say(f"Read it: {len(tracks)} playing track(s) in "
        f"{os.path.basename(demo_path)}.")

    # tempo and count-in read from the file, offered as defaults
    import analyze
    mid = analyze.parse_midi(demo_path)
    ex = analyze.extract(mid)
    quarter_bpm = None
    if ex["tempos"]:
        quarter_bpm = 60_000_000 / ex["tempos"][0][1]
    key_default = "C"
    if ex["keysigs"]:
        _, sf, mi = ex["keysigs"][0]
        key_default = key_name(sf, mi)
    ts_default = "4/4"
    if ex["timesigs"]:
        _, tn, td = ex["timesigs"][0]
        ts_default = f"{tn}/{td}"

    title = ask("Title", os.path.splitext(os.path.basename(out_path))[0])
    composer = ask("Composer", composer)
    key = ask("Key, like Eb minor or F", key_default)
    meter_txt = ask("Meter, like 4/4 or 3/4 or 6/8", ts_default)
    meter = chartc.parse_meter(meter_txt)
    # a demo whose own map changes meter counts its bars by that map;
    # otherwise the answered meter rules, uniform
    meter_events = []
    if dm.mixed_meter():
        seen = None
        for b in range(1, dm.bar_of(max(n.off or n.on
                                        for ns in dm.tracks.values()
                                        for n in ns)) + 1):
            mo = dm.meter_of(b)
            if mo != seen:
                if seen is not None:
                    meter_events.append((b, mo))
                seen = mo
        say("The demo changes meter: " +
            "; ".join(f"bar {b} goes to {n}/{d}"
                      for b, (n, d) in meter_events) +
            ". I will write those into the chart.")
        rawbar = dm.bar_of
    else:
        bar_ticks = dm.division * 4 * meter[0] // meter[1]
        rawbar = lambda tick: int(tick // bar_ticks) + 1
    # an attack played a hair ahead of the barline belongs to the bar it
    # aims at — the same eighth-of-a-beat slack the extractor allows
    slack = dm.division // 8
    barof = lambda tick: rawbar(tick + slack)
    first_bar = min(barof(n.on)
                    for ns in dm.tracks.values() for n in ns)
    # the file's own evidence first; his standing countin setting
    # speaks only when the file says nothing
    countin_default = "1" if first_bar > 1 else \
        (cfg.get('countin') or "0")
    tempo_default = ""
    tempo_q = "Tempo"
    if quarter_bpm:
        if compound(meter):
            # the file stores quarter notes; the chart's tempo in 6/8
            # is the dotted-quarter figure, the one the page prints
            tempo_default = str(round(quarter_bpm * 2 / 3))
            tempo_q = "Tempo, dotted quarter to the beat"
        else:
            tempo_default = str(round(quarter_bpm))
    tempo = ask(tempo_q, tempo_default)
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
        inst = ask(info, track_instrument(name))
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
        # the resolver matches real track names; a display name invented
        # for an unnamed track must not land in the chart
        band.append((label, inst, dm.names.get(ti), shift))
        notes_by_label[label] = (notes, name)

    if not band:
        sys.exit("chart: no parts named, no chart written.")

    total = max(barof(n.on)
                for ns in dm.tracks.values() for n in ns) - int(countin or 0)

    lines = [f"# {title} — started by the chart interview. The activity",
             "# map below says who plays which bars (demo numbering);",
             "# carve your sections from it, then replace this one big",
             "# section. CHART-WRITING.md is the guide.",
             ""]
    for label, inst, tname, shift in band:
        notes, _ = notes_by_label[label]
        lines.append(f"# {label} plays demo bars "
                     f"{spans(notes, barof)}")
    lines += ["",
              f"title: {title}"]
    if composer:
        lines.append(f"composer: {composer}")
    lines += [f"key: {key}",
              f"meter: {meter[0]}/{meter[1]}",
              f"tempo: {tempo}" if tempo else "# tempo: none stated",
              f"demo: {os.path.relpath(demo_path, os.path.dirname(os.path.abspath(out_path)))}"]
    if int(countin or 0):
        lines.append(f"countin: {countin}")
    if dyn.lower().startswith("h") or "hand" in dyn.lower():
        lines.append("dynamics: by hand")
    lines += ["", "band:"]
    for label, inst, tname, shift in band:
        piece = f"  {label}" + (f" = {inst}" if label != inst else "")
        if tname:
            piece += f', demo "{tname}"'
        if shift:
            piece += f" octave {shift:+d}"
        lines.append(piece)
    lines += ["",
              f"section A, {total} bars"]
    for b, (n, d) in meter_events:
        printed = b - int(countin or 0)
        if 2 <= printed <= total:
            lines.append(f"  at bar {printed}: meter {n}/{d}")
        else:
            lines.append(f"# the demo goes to {n}/{d} at its bar {b}, "
                         "outside this section's bars")
    lines += [f"  chords: nc x{total}",
              "# give each part its lines, e.g.:"]
    for label, inst, tname, shift in band[:1]:
        notes, _ = notes_by_label[label]
        lines.append(f"#   {label}: from demo bars "
                     f"{spans(notes, barof).split(',')[0].strip()}")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")
    say(f"Wrote {os.path.basename(out_path)}: {len(band)} part(s), one "
        f"{total}-bar section "
        "to carve up. Next: edit it, then run the build.")
