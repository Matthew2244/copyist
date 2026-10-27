#!/usr/bin/env python3
"""
Lead sheets from a played chord track, shaped by the demo's markers.

Two jobs, both read from the MIDI the writer already has:

  1. CHORDS. A track of block chords (his left hand on the root, right
     hand voicing) becomes chord symbols placed where they land: on the
     beat, on the and, a push on the and of four.  Only onsets count;
     a voicing struck again unchanged prints nothing new, the way an
     engraver suppresses a repeated symbol.

  2. MARKERS. DAW markers become the chart's form.  A marker's first
     word is the section's name (rehearsal letter, number or word); the
     words after it say what that section does, in plain bandstand
     language ("A intro, hits", "B swing, repeat 2x", "solo open").  A
     marker that starts with an instruction instead of a name ("fermata",
     "d.s. al coda", "text Ritard") is an event at its bar inside the
     section already running.  Words Copyist does not act on yet print
     as text on the page and are named in the findings, never dropped.

The chart this writes is ordinary chart text — explicit chords, explicit
directives — so everything it decided can be read back and changed.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PC_NAME = {0: "C", 1: "Db", 2: "D", 3: "Eb", 4: "E", 5: "F", 6: "Gb",
           7: "G", 8: "Ab", 9: "A", 10: "Bb", 11: "B"}
PC_SHARP = {0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F", 6: "F#",
            7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B"}

# (symbol suffix, intervals that must sound, intervals that may).  Most
# specific first: a ninth chord is named only when the ninth is there.
# Every suffix is one the chart format already accepts (CHART-FORMAT 3.3).
TEMPLATES = [
    ("13sus", {0, 5, 10, 9}, {2, 7}),
    ("9sus4", {0, 5, 10, 2}, {7}),
    ("13", {0, 4, 10, 9}, {2, 7}),
    ("7#9", {0, 4, 10, 3}, {7}),
    ("7b9", {0, 4, 10, 1}, {7}),
    ("9", {0, 4, 10, 2}, {7}),
    ("maj9", {0, 4, 11, 2}, {7}),
    ("m9", {0, 3, 10, 2}, {7}),
    ("m11", {0, 3, 10, 5}, {7, 2}),
    ("7sus4", {0, 5, 10}, {7, 2}),
    ("m7b5", {0, 3, 6, 10}, set()),
    ("dim7", {0, 3, 6, 9}, set()),
    ("7", {0, 4, 10}, {7}),
    ("maj7", {0, 4, 11}, {7}),
    ("m7", {0, 3, 10}, {7}),
    ("mmaj7", {0, 3, 11}, {7}),
    ("69", {0, 4, 9, 2}, {7}),
    ("6", {0, 4, 9}, {7}),
    ("m6", {0, 3, 9}, {7}),
    ("add9", {0, 4, 2}, {7}),
    ("madd9", {0, 3, 2}, {7}),
    ("dim", {0, 3, 6}, set()),
    ("aug", {0, 4, 8}, set()),
    ("sus4", {0, 5, 7}, set()),
    ("sus2", {0, 2, 7}, set()),
    ("", {0, 4}, {7}),
    ("m", {0, 3}, {7}),
    ("5", {0, 7}, set()),
]

# Near misses a pianist plays every night: the flat nine with the
# seventh left out still reads as a seven-flat-nine on a lead sheet.
NEAR = [("7b9", {0, 4, 1}, {7}), ("7#9", {0, 4, 3}, {7, 10})]


def name_chord(pitches, flats=True):
    """Sounding MIDI pitches -> chord symbol, or None.  The lowest note
    is the root when any template fits on it (his left hand is the
    bass); otherwise the best fit over it, written as a slash chord."""
    if not pitches:
        return None
    pcs = {p % 12 for p in pitches}
    bass = min(pitches) % 12
    names = PC_NAME if flats else PC_SHARP
    if len(pcs) == 1:
        return None
    best = None
    for templates, near in ((TEMPLATES, False), (NEAR, True)):
        for root in sorted(pcs, key=lambda r: (r != bass, r)):
            rel = {(p - root) % 12 for p in pcs}
            for qual, req, opt in templates:
                if req <= rel and rel <= req | opt:
                    # bass as root first, then the richer reading
                    cand = ((root == bass), len(req), qual, root)
                    if best is None or cand[:2] > best[:2]:
                        best = cand
                    break
        if best is not None:
            break
    if best is None:
        return None
    _, _, qual, root = best
    sym = names[root] + qual
    if bass != root:
        sym += "/" + names[bass]
    return sym


def beat_text(pos_eighths, meter):
    """0-based eighth position in the bar -> '1', '2+', '3' ...; None
    for the downbeat (the format's default)."""
    num, den = meter
    per_beat = 8 // den if den <= 8 else 1
    if den == 8:
        return None if pos_eighths == 0 else str(pos_eighths + 1)
    beat, rem = divmod(pos_eighths, per_beat)
    if beat == 0 and rem == 0:
        return None
    return f"{beat + 1}" + ("+" if rem else "")


def chord_events(notes, division, meter, barof, first=1, last=None):
    """Onset clusters on one track -> {bar: [(eighth, symbol, pitches)]}.

    Notes starting within a sixteenth of each other are one chord (a
    hand is never perfectly together); the cluster lands on the nearest
    eighth.  Bars are the demo's own numbering."""
    num, den = meter
    eighth = division // 2 if den == 4 else division * 4 // den // 2
    bar_ticks = division * 4 * num // den
    ons = sorted(notes, key=lambda n: n.on)
    clusters = []
    for n in ons:
        if clusters and n.on - clusters[-1][0] <= division // 4:
            clusters[-1][1].append(n)
        else:
            clusters.append([n.on, [n]])
    out = {}
    for start, ns in clusters:
        q = int(round(start / eighth)) * eighth
        b = barof(q)
        if b < first or (last is not None and b > last):
            continue
        pos = (q - (b - 1) * bar_ticks) // eighth
        pos = max(0, min(pos, num * (8 // den if den <= 8 else 1) - 1))
        sym = name_chord([n.pitch for n in ns])
        rings = max((n.off or n.on) for n in ns)
        out.setdefault(b, []).append((pos, sym, [n.pitch for n in ns],
                                      rings >= b * bar_ticks + eighth))
    return out


def chord_bars(events, first, last, meter):
    """Per-bar chord text in the bars grammar ('Abm7 Bmaj7@2+ Dbadd9@4+')
    plus the hit positions, for the bars first..last.  A chord that is
    the one already sounding prints nothing; an empty bar restates the
    chord it holds, which the printer suppresses."""
    bars, hits, misses = [], [], []
    held = "nc"
    for b in range(first, last + 1):
        evs = sorted(events.get(b, []))
        carried = held
        parts, beats = [], []
        for pos, sym, _, _r in evs:
            beats.append(beat_text(pos, meter) or "1")
            if sym is None:
                misses.append(b)
                continue
            if sym == held and parts:
                continue
            if sym == held and not parts and pos != 0:
                continue
            bt = beat_text(pos, meter)
            parts.append(sym + (f"@{bt}" if bt else ""))
            held = sym
        if not parts:
            parts = [carried]
        elif "@" in parts[0]:
            # nothing struck on the one: the bar opens on the chord
            # carried over the barline, said explicitly
            parts.insert(0, carried)
        bars.append(" ".join(parts))
        nxt = sorted(events.get(b + 1, []))
        if evs and beats and evs[-1][0] % 2 == 1 and evs[-1][3] \
                and b < last and not (nxt and nxt[0][0] == 0):
            beats[-1] += " push"
        hits.append(beats)
    return bars, hits, misses


def chordiness(notes, division):
    """Share of onsets that come in clusters of three or more: block
    chords read near 1, a melody near 0."""
    if not notes:
        return 0.0
    ons = sorted(n.on for n in notes)
    groups, cur = [], [ons[0]]
    for t in ons[1:]:
        if t - cur[-1] <= division // 4:
            cur.append(t)
        else:
            groups.append(cur)
            cur = [t]
    groups.append(cur)
    big = sum(len(g) for g in groups if len(g) >= 3)
    return big / len(ons)


# ------------------------------------------------------------ markers

def read_markers(path):
    """[(tick, text)] from marker (FF 06) and cue point (FF 07) events,
    in time order.  REAPER, Logic, Cubase and MuseScore all write 06."""
    import analyze
    mid = analyze.parse_midi(path)
    out = []
    for tr in mid["tracks"]:
        for e in tr:
            if e[1] == "meta" and e[2] in (0x06, 0x07):
                txt = e[3].decode("utf-8", "replace").strip()
                if txt:
                    out.append((e[0], txt))
    out.sort()
    return out, mid["division"]


# section-label words: printed beside the rehearsal mark
LABEL_WORDS = ("intro", "verse", "pre-chorus", "pre chorus", "prechorus",
               "chorus", "hook", "bridge", "interlude", "outro", "coda",
               "tag", "vamp", "shout", "head", "solos", "solo section",
               "breakdown", "turnaround", "ending", "refrain", "head out",
               "out head", "out chorus", "send off", "send-off")

FEEL_RX = (r"swing|shuffle|bossa(?: nova)?|samba|latin|afro[- ]cuban|"
           r"funk|swung funk|gospel|ballad|rock|reggae|one drop|motown|"
           r"hip hop|second line|waltz|jazz waltz|straight(?: eighths)?|"
           r"half[- ]time(?: \w+)?|double[- ]time(?: \w+)?|even eighths")


def parse_marker(text):
    """One marker's words -> dict(name, label, header, lines, events,
    unknown).  `header` are section-header options, `lines` directive
    or chords lines for the section, `events` (bar-relative=1) timed
    events, `unknown` words printed as text and reported."""
    raw = text.strip()
    low = re.sub(r"\s+", " ", raw.lower())
    res = dict(name=None, label=None, header=[], feel=None, mode=None,
               lines=[], events=[], unknown=[], chords=None)
    # "A: intro, hits" / "A - intro" / "A intro hits"
    m = re.match(r"^(?:section\s+|letter\s+|rehearsal\s+)?"
                 r"([a-z]|[a-z]\d|\d{1,3})(?:\b|$)[\s:.\-,]*(.*)$", low)
    rest = low
    if m and not re.match(r"^(d\.?[sc]\.?|ds|dc|fine|segno|to coda)",
                          low):
        res["name"] = m.group(1).upper()
        rest = m.group(2)
    else:
        # a word name: "Intro", "Verse 2", "Chorus: hits"
        m = re.match(r"^((?:" + "|".join(re.escape(w) for w in
                                          LABEL_WORDS) + r")(?: \d+)?)"
                     r"\b[\s:.\-,]*(.*)$", low)
        if m:
            res["name"] = raw[:len(m.group(1))].strip().title() \
                .replace(" ", "")
            res["label"] = raw[:len(m.group(1))].strip()
            rest = m.group(2)
    # what the writer wrote, piece by piece; a quoted phrase stays whole
    pieces = [p.strip() for p in re.split(
        r'(?:[,;:]+|\s+-\s+)(?=(?:[^"]*"[^"]*")*[^"]*$)', rest)
        if p.strip()]
    # 'A intro hits swing' with no commas: try word groups
    flat = []
    for p in pieces:
        flat.extend(_split_words(p))
    for p in flat:
        _apply(p, res)
    return res


_KNOWN_STARTS = None


def _split_words(p):
    """'intro hits swing' -> ['intro', 'hits', 'swing'] when every word
    is something known on its own; otherwise the phrase stays whole so a
    longer instruction ('repeat 2 times', 'vamp till cue') still reads."""
    if '"' in p:
        return [p]
    whole = dict(name=None, label=None, header=[], feel=None, mode=None,
                 lines=[], events=[], unknown=[], chords=None)
    _apply(p, whole)
    if not whole["unknown"]:
        return [p]
    words = p.split()
    out, i = [], 0
    while i < len(words):
        for j in range(len(words), i, -1):
            chunk = " ".join(words[i:j])
            probe = dict(whole, header=[], lines=[], events=[],
                         unknown=[], label=None, feel=None, mode=None)
            _apply(chunk, probe)
            if not probe["unknown"]:
                out.append(chunk)
                i = j
                break
        else:
            return [p]
    return out


def _apply(p, res):
    p = p.strip()
    bare = p.rstrip(".").strip()
    if bare in LABEL_WORDS or bare in ("repeat", "twice", "segno",
                                       "fine", "coda", "hold"):
        p = bare
    if not p:
        return
    if p in LABEL_WORDS or re.fullmatch(
            r"(?:" + "|".join(re.escape(w) for w in LABEL_WORDS) +
            r")(?: \d+)?", p):
        res["label"] = p
        return
    m = re.fullmatch(r'label "?([^"]+)"?', p)
    if m:
        res["label"] = m.group(1)
        return
    # how the part prints
    if re.fullmatch(r"(play )?(the )?(hits|kicks|stabs|pushes|rhythm|"
                    r"as played|rhythm as played|rhythmic slashes|"
                    r"play what i played|my rhythm)", p):
        res["mode"] = "hits"
        return
    if re.fullmatch(r"(slashes|time|comp|comping|groove|just chords|"
                    r"chords only|chords|changes|free|play time)", p):
        res["mode"] = "slashes"
        return
    if re.fullmatch(r"(notes|as written|play my notes|written out|"
                    r"exact|play this exact|voicings)", p):
        res["mode"] = "notes"
        return
    if re.fullmatch(r"(tacet|rest|lay out|layout|out|drop out)", p):
        res["mode"] = "tacet"
        return
    if re.fullmatch(r"(solo|solos|solo open|open solo|solos open|"
                    r"blow|blowing)", p):
        res["mode"] = "solo open" if "open" in p else "solo"
        if res["label"] is None:
            res["label"] = "solos" if "open" in p else "solo"
        return
    if re.fullmatch(r"(no chords|nc|n\.c\.|break|stop time|stop)", p):
        res["chords"] = "nc"
        if p in ("break", "stop time", "stop"):
            res["events"].append("break")
        return
    # header: repeats, vamps, cues
    m = re.fullmatch(r"(?:repeat|play|vamp)?\s*(?:x\s*(\d+)|(\d+)\s*(?:x|"
                     r"times))|repeat (\d+)x?|repeat|twice", p)
    if m:
        n = next((g for g in m.groups() if g), None)
        n = int(n) if n else 2
        res["header"].append(f"repeat {n}x")
        return
    if re.fullmatch(r"(open|vamp|vamp till cue|till cue|until cue|"
                    r"vamp until cue|on cue|repeat till cue)", p):
        res["header"].append("vamp till cue" if "cue" in p or p == "vamp"
                             else "open")
        return
    if re.fullmatch(FEEL_RX, p) or re.fullmatch(
            r"(feel|groove) (.+)", p):
        mm = re.fullmatch(r"(?:feel|groove) (.+)", p)
        res["feel"] = (mm.group(1) if mm else p)
        return
    m = re.fullmatch(r"(?:tempo|bpm)\s*(\d{2,3})|(\d{2,3})\s*bpm", p)
    if m:
        res["events"].append(f"tempo {m.group(1) or m.group(2)}")
        return
    m = re.fullmatch(r"(?:key(?: of)?|modulate to|key change to)\s+"
                     r"([a-g](?:b|#| flat| sharp)?(?: minor| major|m)?)",
                     p)
    if m:
        k = m.group(1).replace(" flat", "b").replace(" sharp", "#")
        res["events"].append("key " + k[0].upper() + k[1:])
        return
    m = re.fullmatch(r"(?:meter|time)\s*(\d+/\d+)|(\d+/\d+)", p)
    if m:
        res["events"].append(f"meter {m.group(1) or m.group(2)}")
        return
    road = {"segno": "segno", "sign": "segno", "coda": "coda",
            "to coda": "to coda", "fine": "fine", "d.s.": "d.s.",
            "ds": "d.s.", "d.s. al coda": "d.s. al coda",
            "ds al coda": "d.s. al coda", "d.s. al fine": "d.s. al fine",
            "ds al fine": "d.s. al fine", "d.c.": "d.c.", "dc": "d.c.",
            "d.c. al coda": "d.c. al coda", "dc al coda": "d.c. al coda",
            "d.c. al fine": "d.c. al fine", "dc al fine": "d.c. al fine",
            "fermata": "fermata", "hold": "fermata",
            "dal segno": "d.s.", "da capo": "d.c."}
    if p in road:
        res["events"].append(road[p])
        return
    m = re.fullmatch(r"(cresc|crescendo|dim|diminuendo|decresc)", p)
    if m:
        res["events"].append("cresc" if p.startswith("cresc") else "dim")
        return
    m = re.fullmatch(r"(rit\.?|ritard\.?|rall\.?|rallentando|a tempo|"
                     r"accel\.?|colla voce|tempo i|molto rit\.?)", p)
    if m:
        word = {"rit": "rit.", "rall": "rall.", "accel": "accel.",
                "ritard": "ritard.", "molto rit": "molto rit.",
                "tempo i": "Tempo I", "a tempo": "a tempo",
                "colla voce": "Colla Voce"}.get(p.rstrip("."), p)
        res["events"].append(f'text "{word}"')
        return
    m = re.fullmatch(r'(?:text|say|print|words?)\s*"?([^"]+)"?', p)
    if m:
        res["events"].append(f'text "{m.group(1)}"')
        return
    m = re.fullmatch(r"(fill|drum fill|fill in|fill into it|"
                     r"fill into the next section)", p)
    if m:
        res["events"].append("fill")
        return
    m = re.fullmatch(r"(pp|p|mp|mf|f|ff)", p)
    if m:
        res["events"].append(f"dyn {p}")
        return
    res["unknown"].append(p)


def is_section_marker(text):
    return parse_marker(text)["name"] is not None


# ------------------------------------------------------------ the chart

def lead_sheet(demo_path, out_path, title=None, composer="", key=None,
               tempo=None, part="piano", chord_track=None, feel=None,
               countin=0):
    """Write a lead-sheet chart from one demo: chords from its chord
    track, form from its markers.  Returns (chart text, findings)."""
    import chartdemo
    import analyze
    dm = chartdemo.load_demo(demo_path)
    find = []
    mid = analyze.parse_midi(demo_path)
    ex = analyze.extract(mid)
    meter = (4, 4)
    if ex["timesigs"]:
        _, tn, td = ex["timesigs"][0]
        meter = (tn, td)
    if tempo is None and ex["tempos"]:
        tempo = round(60_000_000 / ex["tempos"][0][1])
    div = dm.division
    bar_ticks = div * 4 * meter[0] // meter[1]
    slack = div // 8
    barof = lambda t: int((t + slack) // bar_ticks) + 1
    # the chord track: named, or the one that plays most like chords
    names = {ti: dm.names.get(ti, f"track {ti}") for ti in dm.tracks}
    if chord_track is not None:
        ti = next((t for t, n in names.items()
                   if n.lower() == str(chord_track).lower()), None)
        if ti is None:
            raise SystemExit("chart: the demo has no track called "
                             f"'{chord_track}' — it has: "
                             + ", ".join(names.values()))
    else:
        ti = max(dm.tracks, key=lambda t: (chordiness(dm.tracks[t], div),
                                           len(dm.tracks[t])))
    notes = dm.tracks[ti]
    share = chordiness(notes, div)
    if share < 0.5:
        find.append(f'"{names[ti]}" plays more lines than chords '
                    f"({share * 100:.0f} percent of its notes are in "
                    "chords); the symbols are my best reading of it")
    if key is None:
        guess = analyze.estimate_key(notes)[0][0]
        key = guess.replace(" major", "").replace(" minor", " minor")
    import chartc
    fifths = chartc.parse_key(key)[0] if hasattr(chartc, "parse_key") \
        else -1
    try:
        flats = fifths <= 0
    except TypeError:
        flats = True
    first = 1 + int(countin or 0)
    last = barof(max(n.off or n.on for n in notes))
    # a note releasing exactly on a barline does not open that bar
    if all(barof(n.on) < last for n in notes):
        last -= 1
    events = chord_events(notes, div, meter, barof, first, last)
    if not flats:
        for b, evs in events.items():
            events[b] = [(p, name_chord(ps, flats=False), ps, r)
                         for p, _s, ps, r in evs]
    marks, mdiv = read_markers(demo_path)
    # the form: section markers start sections; the rest are events
    secs = []
    for tick, text in marks:
        b = barof(tick * div // mdiv if mdiv != div else tick)
        pm = parse_marker(text)
        if pm["name"] and (not secs or b > secs[-1]["bar"]) \
                and first <= b <= last:
            secs.append(dict(bar=b, text=text, pm=pm, events=[]))
        elif pm["name"] and secs and b == secs[-1]["bar"]:
            find.append(f'two section markers at bar {b - first + 1} '
                        f'("{secs[-1]["text"]}" and "{text}"); kept the '
                        "first")
        elif secs:
            secs[-1]["events"].append((b, pm, text))
        elif first <= b:
            # an instruction before any section marker opens section A
            secs.append(dict(bar=first, text="A", pm=parse_marker("A"),
                             events=[(b, pm, text)]))
    if not secs or secs[0]["bar"] > first:
        secs.insert(0, dict(bar=first, text="(start)",
                            pm=parse_marker("Intro" if secs else "A"),
                            events=[]))
        if marks:
            find.append("the first marker is after the first bar; the "
                        "bars before it are their own section")
    # names must be unique: a second 'A' is A2, the way a book writes it
    seen = {}
    for s in secs:
        nm = s["pm"]["name"]
        if nm in seen:
            seen[nm] += 1
            s["pm"]["name"] = f"{nm}{seen[nm]}"
        else:
            seen[nm] = 1
    lines = [f"# Lead sheet from {os.path.basename(demo_path)}: chords "
             f'read from the "{names[ti]}" track, form from its',
             "# markers. Every chord and every word below is plain chart "
             "text;",
             "# change any of it and build again.", ""]
    lines.append(f"title: {title or os.path.splitext(os.path.basename(out_path))[0]}")
    if composer:
        lines.append(f"composer: {composer}")
    lines += [f"key: {key}", f"meter: {meter[0]}/{meter[1]}"]
    if tempo:
        lines.append(f"tempo: {tempo}")
    tune_feel = feel or secs[0]["pm"]["feel"]
    if tune_feel:
        lines.append(f"feel: {tune_feel}")
    lines.append("demo: " + os.path.relpath(
        demo_path, os.path.dirname(os.path.abspath(out_path))
    ).replace(os.sep, "/"))
    if countin:
        lines.append(f"countin: {countin}")
    lines += ["", "band:", f'  {part}, demo "{names[ti]}", one staff', ""]
    allmiss = []
    for i, s in enumerate(secs):
        lo = s["bar"]
        hi = secs[i + 1]["bar"] - 1 if i + 1 < len(secs) else last
        n = hi - lo + 1
        pm = s["pm"]
        bars, hits, misses = chord_bars(events, lo, hi, meter)
        allmiss += [b - first + 1 for b in misses]
        if pm["chords"] == "nc":
            bars = ["nc"] * n
        head = f"section {pm['name']}, {n} bars"
        if pm["label"] and pm["label"].replace(" ", "").lower() != \
                pm["name"].lower():
            head += f', label "{pm["label"]}"'
        for h in pm["header"]:
            head += f", {h}"
        lines.append(head)
        if pm["feel"] and pm["feel"] != tune_feel:
            lines.append(f"  feel: {pm['feel']}")
        lines.append("  chords: " + compress(bars))
        mode = pm["mode"] or "slashes"
        if mode == "hits":
            pieces = []
            for k, beats in enumerate(hits):
                if beats:
                    pieces.append(f"hits bar {k + 1} on "
                                  + ", ".join(beats))
            lines.append(f"  {part}: " + (", ".join(pieces)
                                          if pieces else "groove"))
        elif mode == "notes":
            lines.append(f"  {part}: from demo bars {lo}-{hi}")
        elif mode == "tacet":
            lines.append(f"  {part}: tacet")
        elif mode.startswith("solo"):
            lines.append(f"  {part}: {mode}")
        else:
            lines.append(f"  {part}: groove")
        for ev in pm["events"]:
            lines.append("  " + _event_line(ev, 1, n))
        for b, epm, etext in s["events"]:
            rel = b - lo + 1
            for ev in epm["events"]:
                lines.append("  " + _event_line(ev, rel, n))
            if epm["mode"] or epm["header"] or epm["label"]:
                find.append(f'marker "{etext}" at bar {b - first + 1} '
                            "is inside a section, so its section words "
                            "only print as text; give it a name first "
                            '(like "C, hits") to start a section')
                lines.append(f'  at bar {rel}: text "{etext}"')
            for w in epm["unknown"]:
                lines.append(f'  at bar {rel}: text "{w}"')
                find.append(f'marker "{etext}" at bar {b - first + 1}: '
                            f'I don\'t act on "{w}" yet, so it prints as '
                            "words")
        for w in pm["unknown"]:
            lines.append(f'  at bar 1: text "{w}"')
            find.append(f'marker "{s["text"]}": I don\'t act on "{w}" '
                        "yet, so it prints as words over the section")
        lines.append("")
    if allmiss:
        find.append("no chord name for the hits at bar(s) "
                    + ", ".join(str(b) for b in sorted(set(allmiss)))
                    + "; they carry the chord before")
    # sections that are the same as an earlier one, said once
    sig = {}
    for i, s in enumerate(secs):
        lo = s["bar"]
        hi = secs[i + 1]["bar"] - 1 if i + 1 < len(secs) else last
        key_ = tuple(chord_bars(events, lo, hi, meter)[0])
        if key_ in sig:
            find.append(f"section {s['pm']['name']} has the same changes "
                        f"as {sig[key_]}")
        else:
            sig[key_] = s["pm"]["name"]
    return "\n".join(lines).rstrip() + "\n", find


def _event_line(ev, rel, n):
    if ev == "cresc" or ev == "dim":
        return f"at bar {rel}: text \"{ev}.\""
    if ev.startswith("dyn "):
        return f'at bar {rel}: text "{ev[4:]}"'
    if ev == "fill":
        return f"fill into bar {min(rel + 1, n)}" if rel < n else \
            "fill into the next section"
    return f"at bar {rel}: {ev}"


def compress(bars):
    out = []
    for b in bars:
        if out and out[-1][0] == b:
            out[-1][1] += 1
        else:
            out.append([b, 1])
    return ", ".join(b + (f" x{k}" if k > 1 else "") for b, k in out)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Make a lead sheet chart from a MIDI chord track "
                    "and its markers.")
    ap.add_argument("demo", help="the MIDI file")
    ap.add_argument("chart", help="the chart file to write")
    ap.add_argument("--title", help="the title (default: the file name)")
    ap.add_argument("--key", help="the key (default: guessed from the "
                    "notes, and said)")
    ap.add_argument("--track", help="which track plays the chords "
                    "(default: the one that plays most like chords)")
    ap.add_argument("--part", default="piano",
                    help="the instrument the lead sheet prints for")
    ap.add_argument("--print", action="store_true",
                    help="print the chart instead of writing it")
    a = ap.parse_args(argv)
    text, find = lead_sheet(a.demo, a.chart, title=a.title, key=a.key,
                            chord_track=a.track, part=a.part)
    if a.print:
        print(text)
    else:
        if os.path.exists(a.chart):
            sys.exit(f"chart: {a.chart} already exists — I will not "
                     "write over a chart.")
        with open(a.chart, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {a.chart}.")
    for f_ in find:
        print("  " + f_)


if __name__ == "__main__":
    main()
