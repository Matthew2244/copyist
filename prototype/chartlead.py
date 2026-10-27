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
     marker that is only an instruction ("fermata", "d.s. al coda",
     "a tempo") is an event at its bar inside the section already
     running; on a section's first bar its words join that section.
     Words Copyist does not act on yet print as text on the page and are
     named in the findings, never dropped.

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
    ("7#9b13", {0, 4, 10, 3, 8}, {7}),
    ("13", {0, 4, 10, 9}, {2, 7}),
    ("7#9", {0, 4, 10, 3}, {7}),
    ("7b9", {0, 4, 10, 1}, {7}),
    ("7b13", {0, 4, 10, 8}, {2}),
    ("7#11", {0, 4, 10, 6}, {7, 2}),
    ("9", {0, 4, 10, 2}, {7}),
    ("maj7#11", {0, 4, 11, 6}, {7, 2}),
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

# Near misses a pianist plays every night, read on the bass only: a
# flat nine with the seventh left out still reads seven-flat-nine; a
# ninth chord with no third (C G Bb D) is C9, not Bb69/C.
NEAR = [("7b9", {0, 4, 1}, {7}), ("7#9", {0, 4, 3}, {7, 10}),
        ("9", {0, 10, 2}, {7}), ("maj9", {0, 11, 2}, {7}),
        ("maj7", {0, 11, 7}, set()), ("7", {0, 10, 7}, set())]


def spelling(fifths):
    """Root names for a key: a sharp key sharps only the notes its
    signature sharps (Bb stays Bb in D major); everything else, and every
    flat key, reads from the flat side the way a horn section reads."""
    if fifths is None or fifths <= 0:
        return dict(PC_NAME)
    sharped = "FCGDAEB"[:fifths]
    names = dict(PC_NAME)
    for letter in sharped:
        pc = ({"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9,
               "B": 11}[letter] + 1) % 12
        names[pc] = PC_SHARP[pc] if letter != "E" and letter != "B" \
            else names[pc]
    return names


def name_chord(pitches, flats=True, names=None):
    """Sounding MIDI pitches -> chord symbol, or None.  The lowest note
    is the root when any shape fits on it (his left hand is the bass);
    otherwise the best fit over it, written as a slash chord."""
    if not pitches:
        return None
    pcs = {p % 12 for p in pitches}
    bass = min(pitches) % 12
    names = names or (PC_NAME if flats else PC_SHARP)
    if len(pcs) == 1:
        return None

    def fit(root, templates):
        rel = {(p - root) % 12 for p in pcs}
        for qual, req, opt in templates:
            if req <= rel and rel <= req | opt:
                return qual
        return None
    found = None
    # a plain major triad's quality is "", so test for None, not truth
    q = fit(bass, TEMPLATES)
    if q is None:
        q = fit(bass, NEAR)
    if q is not None:
        found = (q, bass)
    else:
        best = None
        for root in sorted(pcs - {bass}):
            q = fit(root, TEMPLATES)
            if q is None:
                continue
            req = next(r for qq, r, _ in TEMPLATES if qq == q)
            # the richer reading first; on a tie a seventh chord beats a
            # sixth (E G A C over E is Am7/E, not C6/E)
            cand = (len(req), q not in ("6", "m6", "69"), q, root)
            if best is None or cand[:2] > best[:2]:
                best = cand
        if best:
            found = (best[2], best[3])
    if found is None:
        return None
    qual, root = found
    sym = names[root] + qual
    if bass != root:
        sym += "/" + names[bass]
    return sym


# ------------------------------------------------------------ the grid

def grid_ticks(division, meter):
    """One step of the placement grid: half a beat in /4 and /2 (the
    and), the eighth itself in /8 (6/8 counts eighths)."""
    num, den = meter
    beat = division * 4 // den
    return beat // 2 if den <= 4 else beat


def beat_text(pos, meter):
    """0-based grid step in the bar -> '2', '2+', or None for the one."""
    num, den = meter
    if pos == 0:
        return None
    if den > 4:
        return str(pos + 1)
    beat, rem = divmod(pos, 2)
    return f"{beat + 1}" + ("+" if rem else "")


def chord_events(notes, division, meter, barof, first=1, last=None,
                 names=None):
    """Onset clusters on one track -> {bar: [(step, symbol, pitches,
    end_tick)]}.

    Notes starting within a sixteenth of each other are one chord (a
    hand is never perfectly together); the cluster lands on the nearest
    grid step.  Bars are the demo's own numbering."""
    num, den = meter
    grid = grid_ticks(division, meter)
    bar_ticks = division * 4 * num // den
    steps = bar_ticks // grid
    ons = sorted(notes, key=lambda n: n.on)
    clusters = []
    for n in ons:
        if clusters and n.on - clusters[-1][0] <= division // 4:
            clusters[-1][1].append(n)
        else:
            clusters.append([n.on, [n]])
    out = {}
    for start, ns in clusters:
        q = int(round(start / grid)) * grid
        b = barof(q)
        if b < first or (last is not None and b > last):
            continue
        pos = (q - (b - 1) * bar_ticks) // grid
        pos = max(0, min(pos, steps - 1))
        sym = name_chord([n.pitch for n in ns], names=names)
        rings = max((n.off or n.on) for n in ns)
        out.setdefault(b, []).append((pos, sym, [n.pitch for n in ns],
                                      rings))
    return out


def chord_bars(events, first, last, meter, bar_ticks, grid, song_last=None):
    """Per-bar chord text in the bars grammar ('Abm7 Bmaj7@2+ Dbadd9@4+')
    plus each bar's hits, for the bars first..last.  A chord that is the
    one already sounding prints nothing; an empty bar restates the chord
    it holds, which the printer suppresses.

    Hits: a bar's last chord still ringing at the barline, with nothing
    struck on the next bar's one, is a push ('4+ push'); a bar struck
    nowhere that the chord rings through reads 'held' (and 'held push'
    when it rings on past that bar too)."""
    bars, hits, misses = [], [], []
    held = "nc"
    ring_end = 0              # when the last struck chord lets go
    # a push may tie over a section line; only the tune's end stops it
    song_last = song_last or last
    # a chord struck before this section may still be ringing into it
    before = [e for bb, evs in events.items() if bb < first for e in evs]
    if before:
        last_b = max(bb for bb in events if bb < first)
        ring_end = max(events[last_b], key=lambda e: e[0])[3]
    for b in range(first, last + 1):
        evs = sorted(events.get(b, []), key=lambda e: e[0])
        carried = held
        parts, beats = [], []
        for pos, sym, _, end in evs:
            beats.append(beat_text(pos, meter) or "1")
            ring_end = end
            if sym is None:
                misses.append(b)
                continue
            if sym == held and (parts or pos != 0):
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
        bar_end = b * bar_ticks
        nxt = sorted(events.get(b + 1, []), key=lambda e: e[0])
        opens_next = bool(nxt) and nxt[0][0] == 0
        rings_over = ring_end >= bar_end + grid // 2
        if not evs:
            bar_start = (b - 1) * bar_ticks
            if ring_end > bar_start + grid // 2:
                beats = ["held"]
                if rings_over and b < song_last and not opens_next:
                    beats[0] += " push"
        elif rings_over and b < song_last and not opens_next:
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
    in time order (markers at one tick keep the file's order).  REAPER,
    Logic, Cubase and MuseScore all write 06."""
    import analyze
    mid = analyze.parse_midi(path)
    out = []
    for tr in mid["tracks"]:
        for e in tr:
            if e[1] == "meta" and e[2] in (0x06, 0x07):
                txt = e[3].decode("utf-8", "replace").strip()
                if txt:
                    out.append((e[0], txt))
    out.sort(key=lambda x: x[0])
    return out, mid["division"]


# section-label words: printed beside the rehearsal mark; longest first
# so "head out" is read before "head"
LABEL_WORDS = tuple(sorted((
    "intro", "verse", "pre-chorus", "pre chorus", "prechorus", "chorus",
    "hook", "bridge", "interlude", "outro", "coda", "tag", "vamp",
    "vamp out", "shout", "shout chorus", "head", "head in", "head out",
    "out head", "out chorus", "solo", "solos", "solo section",
    "breakdown", "turnaround", "ending", "refrain", "send off",
    "send-off", "drum solo", "piano solo", "outro vamp", "groove"),
    key=len, reverse=True))
_LABEL_RX = "|".join(re.escape(w) for w in LABEL_WORDS)

FEEL_RX = (r"swing|shuffle|bossa(?: nova)?|samba|latin|afro[- ]cuban|"
           r"funk|swung funk|gospel|ballad|rock|reggae|one drop|motown|"
           r"hip hop|second line|waltz|jazz waltz|straight(?: eighths)?|"
           r"half[- ]time(?: \w+)?|double[- ]time(?: \w+)?|even eighths")

# a bare name: a rehearsal letter, a letter and a number, a number
_NAME_RX = r"([a-z]\d{0,2}|\d{1,3})"


def _blank():
    return dict(name=None, label=None, header=[], feel=None, mode=None,
                events=[], unknown=[], chords=None)


def _clean(text):
    """Words that go on the page: a double quote would end the chart's
    own quoted text, so it becomes a single one."""
    return text.replace('"', "'").replace("“", "'") \
        .replace("”", "'").strip()


def parse_marker(text):
    """One marker's words -> dict(name, label, header, feel, mode,
    events, unknown, chords).  `header` are section-header options,
    `events` timed events, `unknown` words printed as text and
    reported.  Matching reads the lowercase words; what prints keeps
    the writer's own capitals."""
    raw = re.sub(r"\s+", " ", text.strip())
    low = raw.lower()
    res = _blank()
    first_word = low.split(" ", 1)[0].strip(":,.-")
    labelish = re.match(r"(?:" + _LABEL_RX + r")\b", low)
    # a marker that is only an instruction ("a tempo", "x4", "fermata")
    # is not a section — unless it is a bare name ("f", "a") or starts
    # with a section word ("Solo")
    if not labelish and (not re.fullmatch(_NAME_RX, low)
                         or re.fullmatch(r"x\d+", low)):
        probe = _blank()
        for p, praw in _pieces(low, raw):
            _apply(p, praw, probe)
        if not probe["unknown"]:
            return probe
    m = re.match(r"^(?:section\s+|letter\s+|rehearsal\s+)?" + _NAME_RX +
                 r"(?=$|[\s:.,\-(])[\s:.,\-]*(.*)$", low)
    if m and not labelish:
        res["name"] = m.group(1).upper()
        start = len(low) - len(m.group(2))
    else:
        m = re.match(r"^((?:" + _LABEL_RX + r")(?: \d+)?)"
                     r"(?=$|[\s:.,\-(])[\s:.,\-]*(.*)$", low)
        if not m:
            res["unknown"].append(_clean(raw))
            return res
        word = raw[:len(m.group(1))]
        res["name"] = re.sub(r"[^\w .-]", "", word.title()).strip()
        res["label"] = word
        start = len(low) - len(m.group(2))
        if m.group(1).split(" ")[0] in ("solo", "solos") or \
                m.group(1).endswith("solo"):
            res["mode"] = "solo"
        if m.group(1) == "coda":
            res["events"].append("coda")
    rest_low, rest_raw = low[start:], raw[start:]
    # "A (intro)" — parentheses are only grouping
    rest_low = rest_low.replace("(", " ").replace(")", " ")
    rest_raw = rest_raw.replace("(", " ").replace(")", " ")
    for p, praw in _pieces(rest_low, rest_raw):
        _apply(p, praw, res)
    return res


def _pieces(low, raw):
    """Split on commas, semicolons, colons and ' - ' outside quotes; a
    run of words with no separators is split where every word is known
    on its own ('intro hits swing'), and kept whole otherwise."""
    spans = []
    pos = 0
    for m in re.finditer(r'(?:[,;:]+|\s+-\s+)(?=(?:[^"]*"[^"]*")*[^"]*$)',
                         low):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(low)))
    out = []
    for a, b in spans:
        pl, pr = low[a:b].strip(), raw[a:b].strip()
        if not pl:
            continue
        out.extend(_split_words(pl, pr))
    return out


def _split_words(pl, pr):
    if '"' in pl:
        return [(pl, pr)]
    probe = _blank()
    _apply(pl, pr, probe)
    if not probe["unknown"]:
        return [(pl, pr)]
    wl, wr = pl.split(), pr.split()
    out, i = [], 0
    while i < len(wl):
        for j in range(len(wl), i, -1):
            probe = _blank()
            _apply(" ".join(wl[i:j]), " ".join(wr[i:j]), probe)
            if not probe["unknown"]:
                out.append((" ".join(wl[i:j]), " ".join(wr[i:j])))
                i = j
                break
        else:
            return [(pl, pr)]
    return out


_ROAD = {"segno": "segno", "sign": "segno", "the sign": "segno",
         "coda": "coda", "to coda": "to coda", "to the coda": "to coda",
         "fine": "fine", "d.s.": "d.s.", "ds": "d.s.", "d.s": "d.s.",
         "d.s. al coda": "d.s. al coda", "ds al coda": "d.s. al coda",
         "d.s. al fine": "d.s. al fine", "ds al fine": "d.s. al fine",
         "d.c.": "d.c.", "dc": "d.c.", "d.c": "d.c.",
         "d.c. al coda": "d.c. al coda", "dc al coda": "d.c. al coda",
         "d.c. al fine": "d.c. al fine", "dc al fine": "d.c. al fine",
         "fermata": "fermata", "hold": "fermata",
         "dal segno": "d.s.", "dal segno al coda": "d.s. al coda",
         "da capo": "d.c.", "da capo al fine": "d.c. al fine"}

_TEMPO_WORDS = {"rit": "rit.", "rit.": "rit.", "ritard": "ritard.",
                "ritard.": "ritard.", "rall": "rall.", "rall.": "rall.",
                "rallentando": "rallentando", "accel": "accel.",
                "accel.": "accel.", "a tempo": "a tempo",
                "colla voce": "Colla Voce", "tempo i": "Tempo I",
                "molto rit": "molto rit.", "molto rit.": "molto rit."}


def _apply(p, praw, res):
    """One piece of a marker (lowercase p, the writer's own praw)."""
    p = p.strip()
    praw = praw.strip()
    bare = p.rstrip(".").strip()
    if not p:
        return
    if re.fullmatch(r"(?:" + _LABEL_RX + r")(?: \d+)?", bare):
        res["label"] = praw.rstrip(".")
        if bare.startswith("solo"):
            res["mode"] = res["mode"] or "solo"
        return
    if re.fullmatch(r'"[^"]+"', p):
        # quoted words are words to print, as they are
        res["events"].append(f'text "{_clean(praw.strip(chr(34)))}"')
        return
    m = re.fullmatch(r'label "?([^"]+)"?', p)
    if m:
        res["label"] = _clean(praw[len("label"):].strip().strip('"'))
        return
    # how the part prints
    if re.fullmatch(r"(play )?(the )?(hits|kicks|stabs|pushes|rhythm|"
                    r"as played|rhythm as played|rhythmic slashes|"
                    r"play what i played|my rhythm)", bare):
        res["mode"] = "hits"
        return
    if re.fullmatch(r"(slashes|time|comp|comping|just chords|"
                    r"chords only|chords|changes|play time)", bare):
        res["mode"] = "slashes"
        return
    if re.fullmatch(r"(notes|as written|play my notes|written out|"
                    r"exact|play this exact|voicings)", bare):
        res["mode"] = "notes"
        return
    if re.fullmatch(r"(tacet|rest|lay out|layout|out|drop out)", bare):
        res["mode"] = "tacet"
        return
    if re.fullmatch(r"(solo open|open solo|solos open|blow|blowing)",
                    bare):
        res["mode"] = "solo open"
        return
    if re.fullmatch(r"(no chords|nc|n\.c|n\.c\.|tacet chords)", bare):
        res["chords"] = "nc"
        return
    if re.fullmatch(r"(break|stop)", bare):
        res["events"].append("break")
        return
    if bare == "stop time":
        # the changes go on; the band hits the one and lays out
        res["events"].append("break")
        return
    # header: repeats, vamps, cues
    m = re.fullmatch(r"(?:repeat|play|vamp)?\s*(?:x\s*(\d+)|(\d+)\s*(?:x|"
                     r"times))|repeat (\d+)x?|repeat|twice", bare)
    if m:
        n = next((g for g in m.groups() if g), None)
        res["header"].append(f"repeat {int(n) if n else 2}x")
        return
    if re.fullmatch(r"(open|vamp till cue|till cue|until cue|"
                    r"vamp until cue|on cue|repeat till cue)", bare):
        res["header"].append("open" if bare == "open" else
                             "vamp till cue")
        return
    if re.fullmatch(FEEL_RX, bare) or re.fullmatch(r"(feel|groove) (.+)",
                                                  bare):
        mm = re.fullmatch(r"(?:feel|groove) (.+)", praw.lower())
        res["feel"] = _clean(praw[len(praw) - len(mm.group(1)):]
                             if mm else praw)
        return
    m = re.fullmatch(r"(?:tempo|bpm)\s*(\d{2,3})|(\d{2,3})\s*bpm", bare)
    if m:
        res["events"].append(f"tempo {m.group(1) or m.group(2)}")
        return
    m = re.fullmatch(r"(?:key(?: of)?|modulate to|key change(?: to)?|"
                     r"new key)\s+([a-g](?:b|#| flat| sharp)?"
                     r"(?: minor| major|m)?)", bare)
    if m:
        k = m.group(1).replace(" flat", "b").replace(" sharp", "#")
        k = re.sub(r"m$", " minor", k)
        res["events"].append("key " + k[0].upper() + k[1:])
        return
    m = re.fullmatch(r"(?:meter|time)\s*(\d+/\d+)|(\d+/\d+)", bare)
    if m:
        res["events"].append(f"meter {m.group(1) or m.group(2)}")
        return
    if p in _ROAD or bare in _ROAD:
        res["events"].append(_ROAD.get(p) or _ROAD[bare])
        return
    if re.fullmatch(r"(cresc\.?|crescendo|dim\.?|diminuendo|decresc\.?)",
                    p):
        res["events"].append("cresc" if p.startswith("cresc")
                             else "dim")
        return
    if p in _TEMPO_WORDS or bare in _TEMPO_WORDS:
        res["events"].append(f'text "{_TEMPO_WORDS.get(p) or _TEMPO_WORDS[bare]}"')
        return
    m = re.fullmatch(r'(?:text|say|print|words?)\s*"?([^"]+)"?', p)
    if m:
        said = praw[m.start(1):m.end(1)] if len(praw) == len(p) \
            else m.group(1)
        res["events"].append(f'text "{_clean(said)}"')
        return
    if re.fullmatch(r"(fill|drum fill|fill in|fill into it|"
                    r"fill into the next section)", bare):
        res["events"].append("fill")
        return
    if re.fullmatch(r"(pp|mp|mf|ff|dynamic (?:pp|p|mp|mf|f|ff))", bare):
        res["events"].append(f"dyn {bare.split()[-1]}")
        return
    res["unknown"].append(_clean(praw))


def is_section_marker(text):
    return parse_marker(text)["name"] is not None


# ------------------------------------------------------------ the chart

def _fifths_of(key):
    import chartc
    try:
        return chartc.parse_key(key)[0]
    except SystemExit:
        return None
    except Exception:
        return None


def form_from_markers(demo_path, div, barof, first, last):
    """The demo's markers as a form: [dict(bar, text, pm, events)] with
    demo bar numbers, plus findings. Section markers start sections;
    an instruction on a section's first bar joins it; any other is an
    event inside the section running; a marker in the count-in belongs
    to the first bar; one past the end is left out and said."""
    marks, mdiv = read_markers(demo_path)
    find = []

    def page(b):
        return b - first + 1
    # the form: section markers start sections; the rest are events
    secs = []
    for tick, text in marks:
        b = barof(tick * div // mdiv if mdiv != div else tick)
        pm = parse_marker(text)
        if b > last:
            find.append(f'marker "{text}" is after the last bar, so it '
                        "was left out")
            continue
        if b < first:
            # a marker in the count-in belongs to the first bar
            b = first
        if pm["name"]:
            if secs and b == secs[-1]["bar"]:
                if secs[-1].get("made"):
                    # a real name replaces the A made up for an earlier
                    # instruction at this bar; its words join
                    _merge(pm, secs[-1]["pm"])
                    secs[-1].update(text=text, pm=pm, made=False)
                else:
                    find.append(f"two section markers at bar {page(b)} "
                                f'("{secs[-1]["text"]}" and "{text}"); '
                                "kept the first")
                continue
            secs.append(dict(bar=b, text=text, pm=pm, events=[]))
        elif secs and b == secs[-1]["bar"] and not secs[-1]["events"]:
            # an instruction on a section's first bar is that section's
            _merge(secs[-1]["pm"], pm)
        elif secs:
            secs[-1]["events"].append((b, pm, text))
        else:
            # an instruction before any section marker opens section A
            pa = parse_marker("A")
            _merge(pa, pm) if b == first else None
            secs.append(dict(bar=first, text="A", pm=pa, made=True,
                             events=[] if b == first else
                             [(b, pm, text)]))
    if not secs or secs[0]["bar"] > first:
        secs.insert(0, dict(bar=first, text="(start)",
                            pm=parse_marker("Intro" if secs else "A"),
                            events=[]))
        if marks:
            find.append("the first marker is after the first bar; the "
                        "bars before it are their own section")
    # names must be unique: a second 'A' is A2, the way a book writes it
    used = set()
    for s in secs:
        nm = s["pm"]["name"]
        if nm in used:
            k = 2
            while f"{nm}{k}" in used:
                k += 1
            s["pm"]["name"] = f"{nm}{k}"
        used.add(s["pm"]["name"])
    return secs, find


def section_extras(s, lo, n, first):
    """A section's timed lines from its markers, and the findings: the
    events, and words that print because nothing acts on them yet."""
    lines, find = [], []
    pm = s["pm"]
    for ev in pm["events"]:
        lines.append("  " + _event_line(ev, 1, n))
    for b, epm, etext in s["events"]:
        rel = b - lo + 1
        for ev in epm["events"]:
            lines.append("  " + _event_line(ev, rel, n))
        loose = [w for w, v in (("its feel", epm["feel"]),
                                ("how the part plays", epm["mode"]),
                                ("a repeat", epm["header"]),
                                ("a label", epm["label"]),
                                ("no chords", epm["chords"])) if v]
        if loose:
            find.append(f'marker "{etext}" at bar {b - first + 1} is '
                        f"inside a section, so {', '.join(loose)} only "
                        "prints as words; give it a name first (like "
                        '"C, hits") to start a section there')
            lines.append(f'  at bar {rel}: text "{_clean(etext)}"')
        for w in epm["unknown"]:
            lines.append(f'  at bar {rel}: text "{w}"')
            find.append(f'marker "{etext}" at bar {b - first + 1}: I '
                        f'don\'t act on "{w}" yet, so it prints as words')
    for w in pm["unknown"]:
        lines.append(f'  at bar 1: text "{w}"')
        find.append(f'marker "{s["text"]}": I don\'t act on "{w}" yet, '
                    "so it prints as words over the section")
    return lines, find


def section_head(pm, n):
    """'section B, 8 bars, label "chorus", repeat 2x' from a marker."""
    head = f"section {pm['name']}, {n} bar{'s' if n != 1 else ''}"
    if pm["label"] and pm["label"].replace(" ", "").lower() != \
            pm["name"].replace(" ", "").lower():
        head += f', label "{_clean(pm["label"])}"'
    for h in pm["header"]:
        head += f", {h}"
    return head


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
    if dm.mixed_meter():
        raise SystemExit("chart: this demo changes meter, and a lead sheet "
                         "reads one meter for now. Bring it in as a demo "
                         "chart instead (answer no to the lead sheet).")
    meter = (4, 4)
    if ex["timesigs"]:
        _, tn, td = ex["timesigs"][0]
        meter = (tn, td)
    compound = meter[1] == 8 and meter[0] % 3 == 0 and meter[0] > 3
    if tempo is None and ex["tempos"]:
        q = 60_000_000 / ex["tempos"][0][1]
        # a 6/8 chart's tempo is the dotted quarter, the one it prints
        tempo = round(q * 2 / 3) if compound else round(q)
    div = dm.division
    bar_ticks = div * 4 * meter[0] // meter[1]
    grid = grid_ticks(div, meter)
    slack = div // 8
    barof = lambda t: int((t + slack) // bar_ticks) + 1
    names = {ti: dm.names.get(ti) for ti in dm.tracks}
    if chord_track is not None:
        ti = next((t for t, n in names.items()
                   if (n or f"track {t}").lower() ==
                   str(chord_track).lower()), None)
        if ti is None:
            raise SystemExit("chart: the demo has no track called "
                             f"'{chord_track}' — it has: "
                             + ", ".join(n or f"track {t}"
                                         for t, n in names.items()))
    else:
        ti = max(dm.tracks, key=lambda t: (chordiness(dm.tracks[t], div),
                                           len(dm.tracks[t])))
    tname = (names.get(ti) or "").strip()
    said_track = tname or "the only"
    notes = dm.tracks[ti]
    share = chordiness(notes, div)
    if share < 0.5:
        find.append(f'"{said_track}" plays more lines than chords '
                    f"({share * 100:.0f} percent of its notes are in "
                    "chords); the symbols are my best reading of it")
    if key is None:
        key = analyze.estimate_key(notes)[0][0].replace(" major", "")
    fifths = _fifths_of(key)
    spell = spelling(fifths)
    first = 1 + int(countin or 0)
    last = barof(max(n.off or n.on for n in notes))
    # a note releasing exactly on a barline does not open that bar
    if all(barof(n.on) < last for n in notes):
        last -= 1
    events = chord_events(notes, div, meter, barof, first, last,
                          names=spell)
    secs, mfind = form_from_markers(demo_path, div, barof, first, last)
    find += mfind

    def page(b):
        return b - first + 1
    lines = [f"# Lead sheet from {os.path.basename(demo_path)}: chords "
             f'read from the "{said_track}" track, form from its',
             "# markers. Every chord and every word below is plain chart "
             "text;",
             "# change any of it and build again.", ""]
    lines.append("title: " + (title or os.path.splitext(
        os.path.basename(out_path))[0]))
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
    # an unnamed track is found as the demo's only track, never by a
    # made-up name the demo reader cannot match
    band = f"  {part}" + (f', demo "{tname}"' if tname else "") + \
        ", one staff"
    lines += ["", "band:", band, ""]
    allmiss = []
    spans = []
    for i, s in enumerate(secs):
        lo = s["bar"]
        hi = secs[i + 1]["bar"] - 1 if i + 1 < len(secs) else last
        spans.append((lo, hi))
    for i, s in enumerate(secs):
        lo, hi = spans[i]
        n = hi - lo + 1
        pm = s["pm"]
        bars, hits, misses = chord_bars(events, lo, hi, meter, bar_ticks,
                                        grid, song_last=last)
        allmiss += [page(b) for b in misses]
        if pm["chords"] == "nc":
            bars = ["nc"] * n
        lines.append(section_head(pm, n))
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
        more, said = section_extras(s, lo, n, first)
        lines += more
        find += said
        lines.append("")
    if allmiss:
        find.append("no chord name for the hits at bar(s) "
                    + ", ".join(str(b) for b in sorted(set(allmiss)))
                    + "; they carry the chord before")
    # sections that are the same as an earlier one, said once
    sig = {}
    for i, s in enumerate(secs):
        lo, hi = spans[i]
        key_ = tuple(chord_bars(events, lo, hi, meter, bar_ticks,
                                grid)[0])
        if key_ in sig:
            find.append(f"section {s['pm']['name']} has the same changes "
                        f"as {sig[key_]}")
        else:
            sig[key_] = s["pm"]["name"]
    return "\n".join(lines).rstrip() + "\n", find


def _merge(into, other):
    """Another marker's words join a section's own."""
    for k in ("label", "feel", "mode", "chords"):
        if other.get(k) and not into.get(k):
            into[k] = other[k]
    into["header"] = into["header"] + [h for h in other["header"]
                                       if h not in into["header"]]
    into["events"] = into["events"] + other["events"]
    into["unknown"] = into["unknown"] + other["unknown"]


def _event_line(ev, rel, n):
    if ev in ("cresc", "dim"):
        return f'at bar {rel}: text "{ev}."'
    if ev.startswith("dyn "):
        return f'at bar {rel}: text "{ev[4:]}"'
    if ev == "fill":
        return f"fill into bar {rel + 1}" if rel < n else \
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
    ap.add_argument("--composer", default="", help="the composer")
    ap.add_argument("--key", help="the key (default: guessed from the "
                    "notes)")
    ap.add_argument("--track", help="which track plays the chords "
                    "(default: the one that plays most like chords)")
    ap.add_argument("--part", default="piano",
                    help="the instrument the lead sheet prints for")
    ap.add_argument("--countin", type=int, default=0,
                    help="count-in bars at the start of the demo")
    ap.add_argument("--print", action="store_true",
                    help="print the chart instead of writing it")
    a = ap.parse_args(argv)
    text, find = lead_sheet(a.demo, a.chart, title=a.title,
                            composer=a.composer, key=a.key,
                            chord_track=a.track, part=a.part,
                            countin=a.countin)
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
