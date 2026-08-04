#!/usr/bin/env python3
"""
Copyist — MIDI to MusicXML, prototype.

Implements the parts of DESIGN.md that matter most for a first end-to-end run:

  7.3   gate time becomes articulation, never rests   <- the headline fix
  8.2   stream separation by hand physics
  8.3   hand span from the user profile
  8.5   hand assignment and staff assignment kept separate
  9     key-aware pitch spelling (not yet ps13 — see caveat below)
  10.2  plugin-name alias table
  10.3  instrument-sound identifier
  15    findings, printed severity-first

Usage:
    python3 convert.py IN.mid [-o OUT.musicxml] [--key "C# minor"]
                              [--reach 17] [--comfortable 14]

Caveat: pitch spelling here is key-aware but is NOT ps13. It spells diatonic
notes from the key signature and chromatic notes by the key's accidental
direction. Good enough to read; replace with ps13 before this is real.
"""

import sys
import math
import argparse
from collections import defaultdict
from xml.sax.saxutils import escape

from analyze import (parse_midi, extract, estimate_key, classify_timing,
                     GRIDS, PC, name_interval)
from spelling import ps13, double_accidentals
import articulation
import smf
import harmony
import detail

# --------------------------------------------------------------- constants

# 10.2 — real exports name the track after the plugin, not the instrument.
PLUGIN_ALIASES = {
    "pianoteq": ("Piano", "keyboard.piano", "Pno"),
    "keyscape": ("Piano", "keyboard.piano", "Pno"),
    "ivory": ("Piano", "keyboard.piano", "Pno"),
    "addictive keys": ("Piano", "keyboard.piano", "Pno"),
    "kontakt": (None, None, None),          # too generic to guess
    "omnisphere": (None, None, None),
    "serum": (None, None, None),
    "addictive drums": ("Drum Set", "drum.group.set", "Drs"),
    "superior drummer": ("Drum Set", "drum.group.set", "Drs"),
    "ez drummer": ("Drum Set", "drum.group.set", "Drs"),
    "trilian": ("Electric Bass", "pluck.bass.electric", "El. Bs"),
}

# Circle of fifths -> (fifths value, tonic pitch class, mode)
KEYS = {}
for i, (maj, mi) in enumerate([
        ("Cb", "Ab"), ("Gb", "Eb"), ("Db", "Bb"), ("Ab", "F"), ("Eb", "C"),
        ("Bb", "G"), ("F", "D"), ("C", "A"), ("G", "E"), ("D", "B"),
        ("A", "F#"), ("E", "C#"), ("B", "G#"), ("F#", "D#"), ("C#", "A#")]):
    fifths = i - 7
    KEYS[f"{maj} major"] = fifths
    KEYS[f"{mi} minor"] = fifths

# Enharmonic aliases. estimate_key now emits conventional names, but a user
# typing --key "A# major" should not silently produce an empty score.
for _alias, _real in [("A# major", "Bb major"), ("D# major", "Eb major"),
                      ("G# major", "Ab major"), ("C# major", "Db major"),
                      ("Db minor", "C# minor"), ("Gb minor", "F# minor"),
                      ("Ab minor", "G# minor"), ("Cb major", "B major"),
                      ("E# minor", "F minor"), ("B# major", "C major")]:
    KEYS.setdefault(_alias, KEYS[_real])

STEP_OF_FIFTH = ["F", "C", "G", "D", "A", "E", "B"]

NOTE_TYPES = [(4.0, "whole"), (2.0, "half"), (1.0, "quarter"), (0.5, "eighth"),
              (0.25, "16th"), (0.125, "32nd"), (0.0625, "64th")]

DYNAMICS = [(0.00, "pp"), (0.20, "p"), (0.38, "mp"),
            (0.56, "mf"), (0.74, "f"), (0.90, "ff")]


# --------------------------------------------------------------- findings

class Findings:
    def __init__(self):
        self.items = []

    def add(self, severity, what, why="", suggestion="", location=""):
        self.items.append(dict(id=f"F{len(self.items) + 1}", severity=severity,
                               location=location, what=what, why=why,
                               suggestion=suggestion))

    def report(self):
        order = ["will-look-bad", "uncertain", "fixed-silently"]
        label = {"will-look-bad": "things that will look bad",
                 "uncertain": "things I wasn't sure about",
                 "fixed-silently": "things I fixed silently"}
        out = []
        for sev in order:
            group = [f for f in self.items if f["severity"] == sev]
            if not group:
                continue
            text = label[sev]
            if len(group) == 1:
                text = text.replace("things", "thing").replace("wasn't", "wasn't")
            out.append(f"\n{len(group)} {text}")
            for f in group:
                loc = f" ({f['location']})" if f["location"] else ""
                out.append(f"  {f['id']}{loc}: {f['what']}")
                if f["why"]:
                    out.append(f"        why: {f['why']}")
                if f["suggestion"]:
                    out.append(f"        fix: {f['suggestion']}")
        return "\n".join(out)


# --------------------------------------------------------------- spelling

BASE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def spell_fifth(f):
    """Position on the circle of fifths (F=0, C=1, G=2 ...) -> spelling."""
    step = STEP_OF_FIFTH[f % 7]
    alter = f // 7
    return step, alter, (BASE_PC[step] + alter) % 12


def spelling_table(fifths, find):
    """
    9 — key-aware spelling. The seven diatonic degrees come straight from the
    key signature. Chromatic notes take the spelling *closest to the key on the
    circle of fifths*, which is what keeps double accidentals off the page —
    naively raising the note below produces F double-sharp for a plain G.
    """
    table = {}
    for f in range(fifths, fifths + 7):
        step, alter, pc = spell_fifth(f)
        table[pc] = (step, alter)

    centre = fifths + 3                    # middle of the key's fifths span
    doubles = 0
    for pc in range(12):
        if pc in table:
            continue
        best = None
        for f in range(centre - 14, centre + 15):
            step, alter, p = spell_fifth(f)
            if p == pc and abs(alter) <= 1:
                cost = abs(f - centre)
                if best is None or cost < best[0]:
                    best = (cost, step, alter)
        if best is None:                   # genuinely needs a double accidental
            for f in range(centre - 21, centre + 22):
                step, alter, p = spell_fifth(f)
                if p == pc:
                    best = (abs(f - centre), step, alter)
                    doubles += 1
                    break
        table[pc] = (best[1], best[2])

    if doubles:
        find.add("uncertain",
                 f"{doubles} pitch classes needed double accidentals",
                 suggestion="Implement ps13 (DESIGN 9)")
    return table


def spell(pitch, table):
    step, alter = table[pitch % 12]
    # Octave must follow the *spelled* letter, not the MIDI number, or B# and
    # Cb land an octave out.
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[step]
    octave = (pitch - alter - base) // 12 - 1
    return step, alter, octave


# --------------------------------------------------------------- durations

def decompose(ticks, div):
    """
    Split a duration into tied note values, largest first.

    Must never lose time. A remainder smaller than the shortest notatable
    value used to be dropped on the floor, which produced measures that were a
    few ticks short — silently, and only on real material whose final chord
    does not land on the grid. Nine of twenty-five real files hit it.
    """
    out = []
    remaining = int(ticks)
    guard = 0
    while remaining > 0 and guard < 16:
        guard += 1
        beats = remaining / div
        for value, name in NOTE_TYPES:
            for dots, mult in ((2, 1.75), (1, 1.5), (0, 1.0)):
                if abs(beats - value * mult) < 1e-6:
                    out.append((int(round(value * mult * div)), name, dots))
                    return out
        placed = False
        for value, name in NOTE_TYPES:
            if value * div <= remaining + 1e-6:
                out.append((int(value * div), name, 0))
                remaining -= int(value * div)
                placed = True
                break
        if not placed:
            # Smaller than a 64th. Absorb it into the value already emitted so
            # the measure still adds up; if there is nothing to absorb into,
            # emit the shortest value we have rather than nothing.
            if out:
                ln, nm, dots = out[-1]
                out[-1] = (ln + remaining, nm, dots)
            else:
                out.append((remaining, "64th", 0))
            remaining = 0
            break
    return out


# --------------------------------------------------------------- hands

class Hands:
    """
    8.2 — separation by physics, not pitch. Greedy version of the DP: split an
    event when it exceeds the reach, then assign groups by proximity to where
    each hand already was.
    """

    def __init__(self, reach, comfortable, find):
        self.reach = reach
        self.comfortable = comfortable
        self.find = find
        self.rh = None
        self.lh = None
        self.certain = 0
        self.inferred = 0
        self.low_conf = 0

    def cost(self, lh, rh, dt):
        c = 0.0
        for group, prev in ((lh, self.lh), (rh, self.rh)):
            if not group:
                continue
            span = group[-1] - group[0]
            if span > self.reach:                     # physically impossible
                c += 1000 + (span - self.reach) * 50
            elif span > self.comfortable:             # a stretch, rising cost
                c += (span - self.comfortable) ** 2
            if prev is not None:
                move = abs(sum(group) / len(group) - prev)
                c += move * move * 0.05 / (dt + 0.25)  # can't teleport
        if lh and rh and lh[-1] > rh[0]:
            c += 200                                   # hands crossed
        if not lh and self.lh is not None:
            c += 8                                     # a hand going idle
        if not rh and self.rh is not None:
            c += 8
        return c

    def assign(self, event_pitches, bar, dt):
        pitches = sorted(set(event_pitches))
        n = len(pitches)

        if self.lh is None and self.rh is None:        # seed the hands
            lo = [p for p in pitches if p < 60]
            hi = [p for p in pitches if p >= 60]
            if not lo or not hi:
                mid = n // 2 if n > 1 else 0
                lo, hi = pitches[:mid], pitches[mid:]
            self.lh = sum(lo) / len(lo) if lo else None
            self.rh = sum(hi) / len(hi) if hi else None
            self.certain += n
            return set(lo), set(hi)

        # Enumerate every split point and take the cheapest (DESIGN 8.2).
        scored = []
        for k in range(n + 1):
            lh, rh = pitches[:k], pitches[k:]
            scored.append((self.cost(lh, rh, dt), k, lh, rh))
        scored.sort(key=lambda s: s[0])
        best, second = scored[0], (scored[1] if len(scored) > 1 else None)
        _, _, lh, rh = best

        span = pitches[-1] - pitches[0] if n > 1 else 0
        if span > self.reach:
            self.certain += n
        else:
            self.inferred += n
            if second and second[0] - best[0] < 2.0:
                self.low_conf += n
                self.find.add(
                    "uncertain",
                    f"{n} note(s) could be either hand",
                    why=f"two hand splits score within {second[0] - best[0]:.1f}",
                    suggestion="Listen and lock, or name the hand tracks "
                               "(DESIGN 8.4)",
                    location=f"bar {bar}")

        if rh:
            self.rh = sum(rh) / len(rh)
        if lh:
            self.lh = sum(lh) / len(lh)
        return set(lh), set(rh)


# --------------------------------------------------------------- conversion

LAST_FINDINGS = None      # set by convert(), read by engine.py
LAST_SUMMARY = None


def convert(path, out_path, key_name, reach, comfortable,
            level="full"):
    global LAST_FINDINGS, LAST_SUMMARY
    LAST_FINDINGS = LAST_SUMMARY = None
    mid = parse_midi(path)
    x = extract(mid)
    div = mid["division"]
    notes = x["notes"]
    find = Findings()

    if not notes:
        raise ValueError("That file contains no notes.")

    bpm = 60_000_000 / x["tempos"][0][1] if x["tempos"] else 120.0
    ts_num, ts_den = (x["timesigs"][0][1], x["timesigs"][0][2]) if x["timesigs"] else (4, 4)
    measure_ticks = int(ts_num * (4 / ts_den) * div)

    # ---- key
    if key_name is None:
        est = estimate_key(notes)
        key_name = est[0][0]
        if est[0][1] < 0.60:
            find.add("uncertain", f"Key is ambiguous: {est[0][0]} vs {est[1][0]}",
                     why=f"{est[0][1] * 100:.0f}% / {est[1][1] * 100:.0f}%",
                     suggestion=f'Pass --key "{est[1][0]}" if that is right')
    fifths = KEYS.get(key_name)
    if fifths is None:
        # Returning here used to leave the caller believing it had succeeded,
        # which is exactly the silent failure this project exists to avoid.
        # Six of twenty-five real files hit it before anyone noticed.
        raise ValueError(
            f"Unknown key {key_name!r}. Known: "
            + ", ".join(sorted(KEYS)[:6]) + ", …")
    mode = "minor" if key_name.endswith("minor") else "major"

    # ---- 9: ps13. Spelling is per note from its local context, not one table
    # for the whole piece, so a pitch can be E-flat in one bar and D-sharp in
    # the next. `table` stays as the fallback for anything ps13 cannot see.
    table = spelling_table(fifths, find)
    _sp = ps13(notes)
    for _n, _s in zip(notes, _sp):
        _n.spell = _s
    dbl = double_accidentals(_sp)
    if dbl:
        find.add("uncertain", f"{dbl} notes needed a double accidental",
                 why="ps13 could not find a single-accidental spelling in context")

    # ---- instrument (10.2)
    track_name = ""
    for ti, nm in x["names"].items():
        if any(n.track == ti for n in notes):
            track_name = nm
            break
    inst_name, inst_sound, abbrev = "Piano", "keyboard.piano", "Pno."
    matched = None
    for alias, (nm, snd, ab) in PLUGIN_ALIASES.items():
        if alias in track_name.lower():
            matched = alias
            if nm:
                inst_name, inst_sound, abbrev = nm, snd, ab + "."
            break
    if matched:
        find.add("fixed-silently",
                 f'Track named "{track_name}" resolved to {inst_name}',
                 why=f"matched plugin alias '{matched}'; no GM program in file")
    else:
        find.add("uncertain", f'Could not identify instrument from "{track_name}"',
                 why="no GM program event and no plugin alias matched",
                 suggestion=f"Defaulted to {inst_name}")

    # ---- 7.5: classify the timing, then snap to the detected grid.
    # REAPER's humanize moves every note INDEPENDENTLY, so a three-note chord
    # becomes three onsets up to 67 ms apart. Snapping re-forms the chords;
    # without it the score notates one chord as three shattered events.
    gname, tstats = classify_timing(notes, div, bpm, (ts_num, ts_den))
    gbeats = dict(GRIDS).get(gname, 0.5)
    gticks = max(int(round(gbeats * div)), 1)
    before = len({n.on for n in notes})
    for n in notes:
        snapped = int(round(n.on / gticks)) * gticks
        n.off += snapped - n.on               # keep the gate length intact
        n.on = snapped
    after = len({n.on for n in notes})
    if after < before:
        find.add("fixed-silently",
                 f"{before - after} shattered onsets re-formed into chords",
                 why=f"timing reads as {gname}-grid with "
                     f"{tstats.get('sd', 0):.1f} ms of independent jitter",
                 suggestion="DESIGN 7.5 — humanize moves notes one at a time, "
                            "so chords arrive as separate events")

    # ---- group notes into events, then chords per hand
    by_onset = defaultdict(list)
    for n in notes:
        by_onset[n.on].append(n)
    onsets = sorted(by_onset)

    hands = Hands(reach, comfortable, find)
    streams = {1: [], 2: []}                  # 1 = right hand, 2 = left hand
    widest_seen = 0

    prev_on = None
    for on in onsets:
        group = by_onset[on]
        pitches = [n.pitch for n in group]
        if len(pitches) > 1:
            widest_seen = max(widest_seen, max(pitches) - min(pitches))
        bar = on // measure_ticks + 1
        dt = (on - prev_on) / div if prev_on is not None else 1.0
        prev_on = on
        lh, rh = hands.assign(pitches, bar, dt)
        for staff, members in ((1, rh), (2, lh)):
            sel = [n for n in group if n.pitch in members]
            if sel:
                streams[staff].append(dict(on=on, notes=sel,
                                           gate=max(n.off for n in sel) - on))

    if widest_seen > reach:
        find.add("fixed-silently",
                 f"Widest simultaneity is {name_interval(widest_seen)}",
                 why=f"beyond the {name_interval(reach)} reach, so those events "
                     f"split into two hands with certainty")

    # ---- 8.5: hand is not staff. A chord the right hand played low down still
    # belongs on the bass staff — print it where it needs fewest ledger lines.
    def ledgers(pitches, staff):
        lo, hi = (64, 77) if staff == 1 else (43, 57)   # E4–F5 / G2–A3
        return sum(max(0, (lo - p + 1) // 2) + max(0, (p - hi + 1) // 2)
                   for p in pitches)

    moved = 0
    for src, dst in ((1, 2), (2, 1)):
        for ch in list(streams[src]):
            ps = [n.pitch for n in ch["notes"]]
            here, there = ledgers(ps, src), ledgers(ps, dst)
            if there + 1 < here:               # +1 biases toward staying put
                streams[src].remove(ch)
                streams[dst].append(ch)
                moved += 1
    # Moving a chord can land two chords on one onset in the same staff. They
    # have to merge, or the second silently overwrites the first.
    for staff, seq in streams.items():
        merged = {}
        for ch in seq:
            if ch["on"] in merged:
                prev = merged[ch["on"]]
                prev["notes"] += ch["notes"]
                prev["gate"] = max(prev["gate"], ch["gate"])
            else:
                merged[ch["on"]] = ch
        streams[staff] = [merged[k] for k in sorted(merged)]
    if moved:
        find.add("fixed-silently",
                 f"{moved} chords printed on the other staff",
                 why="fewer ledger lines there; hand assignment unchanged",
                 suggestion="DESIGN 8.5 — who played it and where it prints "
                            "are separate decisions")

    # ---- 7.3: notated duration = slot minus grid-quantized gap
    grid = div // 2                            # eighth note
    phantom_rests_killed = 0
    real_rests = 0

    for staff, seq in streams.items():
        for i, ch in enumerate(seq):
            nxt = seq[i + 1]["on"] if i + 1 < len(seq) else None
            if nxt:
                slot = nxt - ch["on"]
            else:
                # The final chord has no following onset to bound it. Its raw
                # gate time is not a grid value, and a non-grid duration is
                # what leaves a measure a few ticks short.
                slot = max(int(round(ch["gate"] / grid)) * grid, grid)
            gap = max(slot - ch["gate"], 0)
            gap_q = int(round(gap / grid)) * grid
            gap_q = min(gap_q, slot - grid) if slot > grid else 0
            ch["dur"] = slot - gap_q
            ch["rest_after"] = gap_q
            if gap_q:
                real_rests += 1
            elif gap > 0:
                phantom_rests_killed += 1


    # ---- O10: articulation. Gate time alone gives staccato and nothing else;
    # accent, marcato and tenuto come from velocity relative to neighbours.
    artic_counts = {}
    for seq in streams.values():
        for k, v in articulation.annotate(seq).items():
            artic_counts[k] = artic_counts.get(k, 0) + v
    if artic_counts:
        find.add("fixed-silently",
                 f"Articulation: {articulation.summarize(artic_counts)}",
                 why="gate time for staccato; velocity relative to neighbours "
                     "for accent, marcato and tenuto")

    if phantom_rests_killed:
        find.add("fixed-silently",
                 f"{phantom_rests_killed} phantom rests removed",
                 why="short releases quantized to a zero-length gap",
                 suggestion="This is DESIGN 7.3 — gate time is articulation, "
                            "not note value")

    # ---- dynamics, normalized to the piece (pipeline step 10)
    vels = sorted(n.vel for n in notes)
    vlo, vhi = vels[0], vels[-1]
    find.add("fixed-silently",
             f"Dynamics normalized to this piece's velocity range {vlo}–{vhi}",
             why="absolute MIDI velocity would mark the whole piece pp–mp")

    def dyn_for(v):
        t = (v - vlo) / (vhi - vlo) if vhi > vlo else 0.5
        name = "pp"
        for thresh, d in DYNAMICS:
            if t >= thresh:
                name = d
        return name

    measure_dyn = {}
    per_measure = defaultdict(list)
    for n in notes:
        per_measure[n.on // measure_ticks].append(n.vel)
    last = None
    for m in sorted(per_measure):
        d = dyn_for(sum(per_measure[m]) / len(per_measure[m]))
        if d != last:                          # hysteresis: only on change
            measure_dyn[m] = d
            last = d

    # ---- pedal (10) — CC64 spans
    pedal = []
    for ti, ev in enumerate(mid["tracks"]):
        down = None
        for e in ev:
            if e[1] == "chan" and e[2] == 0xB0 and e[4] == 64:
                if e[5] >= 64 and down is None:
                    down = e[0]
                elif e[5] < 64 and down is not None:
                    pedal.append((down, e[0]))
                    down = None
    if pedal:
        find.add("fixed-silently", f"{len(pedal)} pedal marks written",
                 why="CC64 spans, normally discarded entirely on MIDI import")

    total_ticks = max(n.off for n in notes)
    n_measures = total_ticks // measure_ticks + 1

    # ---- 12.1 harmony, then 11 reduction. Reduction runs LAST because you
    # cannot decide a bar becomes four slashes until you know what is in it.
    chords = harmony.detect(notes, measure_ticks, fifths,
                            per_bar=1, find=find)
    if level != "full":
        streams, _ = detail.reduce_streams(
            streams, level, measure_ticks, div, ts_num, ts_den,
            n_measures, find)
        pedal = []                      # a slash chart carries no pedalling

    xml = render(streams, measure_dyn, pedal, div, measure_ticks, n_measures,
                 fifths, mode, ts_num, ts_den, bpm, table,
                 inst_name, abbrev, inst_sound, chords, level)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)

    # 16 — render what the SCORE says back to MIDI, for the A/B audition.
    # Not the performance: quantized onsets, notated durations, the
    # articulations Copyist chose. If these two disagree audibly, Copyist is
    # wrong about something.
    notated_midi = out_path.rsplit(".", 1)[0] + ".notated.mid"
    try:
        smf.write(notated_midi, smf.notes_from_streams(streams),
                  div, bpm, (ts_num, ts_den), "Copyist — as notated")
    except Exception as e:
        notated_midi = None
        find.add("uncertain", "Could not render the notated version for audition",
                 why=str(e))

    LAST_FINDINGS = find
    LAST_SUMMARY = {
        "notatedMidi": notated_midi,
        "key": key_name, "fifths": fifths, "instrument": inst_name,
        "instrumentSound": inst_sound, "measures": int(n_measures),
        "notes": len(notes),
        "handsCertain": hands.certain, "handsInferred": hands.inferred,
        "handsLowConfidence": hands.low_conf,
        "phantomRestsRemoved": phantom_rests_killed,
        "genuineRests": real_rests,
        "articulation": artic_counts,
        "pedalMarks": len(pedal),
        "doubleAccidentals": dbl,
    }

    print(f"\nCOPYIST — {path}")
    print("=" * 60)
    print(f"  key            {key_name} ({fifths:+d})")
    print(f"  instrument     {inst_name}  [{inst_sound}]")
    print(f"  measures       {n_measures}")
    print(f"  hands          {hands.certain} certain, {hands.inferred} inferred, "
          f"{hands.low_conf} low confidence")
    print(f"  phantom rests  {phantom_rests_killed} removed, "
          f"{real_rests} genuine rests kept")
    print(f"  written to     {out_path}")
    print(find.report())
    print()


# --------------------------------------------------------------- rendering

def render(streams, measure_dyn, pedal, div, mticks, n_measures,
           fifths, mode, ts_num, ts_den, bpm, table,
           inst_name, abbrev, inst_sound, chords=(), level="full"):
    by_measure_chords = {}
    for c in chords:
        by_measure_chords.setdefault(c["measure"], []).append(c)
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 '
         'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
         '<score-partwise version="4.0">',
         '  <identification><encoding>'
         '<software>Copyist prototype</software>'
         '</encoding></identification>',
         '  <part-list>',
         '    <score-part id="P1">',
         f'      <part-name>{escape(inst_name)}</part-name>',
         f'      <part-abbreviation>{escape(abbrev)}</part-abbreviation>',
         '      <score-instrument id="P1-I1">',
         f'        <instrument-name>{escape(inst_name)}</instrument-name>',
         f'        <instrument-sound>{inst_sound}</instrument-sound>',
         '      </score-instrument>',
         '    </score-part>',
         '  </part-list>',
         '  <part id="P1">']

    # Flatten each staff into (start, dur, notes, artic) and index by measure.
    carry = {1: [], 2: []}                     # ties spilling into next measure

    for m in range(n_measures):
        m_start = m * mticks
        m_end = m_start + mticks
        L.append(f'    <measure number="{m + 1}">')

        if m == 0:
            L += ['      <attributes>',
                  f'        <divisions>{div}</divisions>',
                  f'        <key><fifths>{fifths}</fifths>'
                  f'<mode>{mode}</mode></key>',
                  f'        <time><beats>{ts_num}</beats>'
                  f'<beat-type>{ts_den}</beat-type></time>',
                  ] + (['        <staves>2</staves>',
                  '        <clef number="1"><sign>G</sign><line>2</line></clef>',
                  '        <clef number="2"><sign>F</sign><line>4</line></clef>']
                  if level == 'full' else
                  ['        <clef><sign>G</sign><line>2</line></clef>']) + [
                  '      </attributes>',
                  '      <direction placement="above">',
                  '        <direction-type><metronome>'
                  '<beat-unit>quarter</beat-unit>'
                  f'<per-minute>{bpm:.0f}</per-minute>'
                  '</metronome></direction-type>',
                  f'        <sound tempo="{bpm:.2f}"/>',
                  '      </direction>']

        for c in by_measure_chords.get(m, []):
            step, alter = root_step(c["root"], fifths)
            L += ['      <harmony>',
                  '        <root><root-step>' + step + '</root-step>'
                  + (f'<root-alter>{alter}</root-alter>' if alter else '')
                  + '</root>',
                  f'        <kind text="{escape(c["suffix"])}">{c["kind"]}</kind>',
                  '      </harmony>']

        if m in measure_dyn:
            L += ['      <direction placement="below">',
                  '        <direction-type><dynamics>'
                  f'<{measure_dyn[m]}/></dynamics></direction-type>',
                  '        <staff>1</staff>',
                  '      </direction>']

        for staff in ((1, 2) if level == 'full' else (1,)):
            voice = 1 if staff == 1 else 5
            if staff == 2:
                L.append(f'      <backup><duration>{mticks}</duration></backup>')

            for p in pedal if staff == 2 else []:
                if m_start <= p[0] < m_end:
                    L += ['      <direction placement="below">',
                          '        <direction-type>'
                          '<pedal type="start" line="yes"/></direction-type>',
                          '        <staff>2</staff>', '      </direction>']
                if m_start <= p[1] < m_end:
                    L += ['      <direction placement="below">',
                          '        <direction-type>'
                          '<pedal type="stop" line="yes"/></direction-type>',
                          '        <staff>2</staff>', '      </direction>']

            pos = m_start
            events = [c for c in streams[staff] if m_start <= c["on"] < m_end]

            for tied in carry[staff]:
                length = min(tied, mticks)
                L += emit_note(tied_notes(carry_notes[staff]), length, div, voice,
                               staff, table, artic=None,
                               tie_stop=True, tie_start=length < tied)
                pos += length
            carry[staff] = []

            for ch in events:
                if ch.get("slash"):
                    if ch["on"] > pos:
                        L += emit_rest(ch["on"] - pos, div, voice, staff)
                        pos = ch["on"]
                    fits = min(ch["dur"], m_end - pos)
                    L += emit_slash(fits, div, voice, staff, level)
                    pos += fits
                    continue
                if ch["on"] > pos:
                    L += emit_rest(ch["on"] - pos, div, voice, staff)
                    pos = ch["on"]
                length = ch["dur"]
                fits = min(length, m_end - pos)
                L += emit_note(ch["notes"], fits, div, voice, staff, table,
                               ch["artic"], tie_stop=False,
                               tie_start=fits < length)
                if fits < length:
                    carry[staff] = [length - fits]
                    carry_notes[staff] = ch["notes"]
                pos += fits

            if pos < m_end:
                L += emit_rest(m_end - pos, div, voice, staff)

        L.append('    </measure>')

    L += ['  </part>', '</score-partwise>', '']
    return "\n".join(L)


carry_notes = {1: [], 2: []}


def tied_notes(ns):
    return ns


def root_step(pc, fifths):
    """Spell a chord root the way the key would spell that pitch class."""
    from spelling import _KEY_TABLES, spell_fifth as _sf
    f = _KEY_TABLES[max(-7, min(7, fifths))][pc % 12]
    step, alter, _ = _sf(f)
    return step, alter


_TRANSPOSE_TABLE = {}   # set by multipart.convert

ACC_NAME = {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "sharp-sharp"}


def emit_note(ns, ticks, div, voice, staff, table, artic,
              tie_stop=False, tie_start=False):
    out = []
    parts = decompose(ticks, div)
    if not parts:
        return out
    for pi, (plen, ptype, dots) in enumerate(parts):
        for ni, n in enumerate(sorted(ns, key=lambda z: z.pitch)):
            step, alter, octave = n.spell or spell(n.pitch, table)
            out.append('      <note>')
            if ni:
                out.append('        <chord/>')
            out.append('        <pitch>'
                       f'<step>{step}</step>'
                       + (f'<alter>{alter}</alter>' if alter else '')
                       + f'<octave>{octave}</octave></pitch>')
            out.append(f'        <duration>{plen}</duration>')
            first, last = pi == 0, pi == len(parts) - 1
            if tie_stop and first:
                out.append('        <tie type="stop"/>')
            if (tie_start and last) or not last:
                out.append('        <tie type="start"/>')
            out.append(f'        <voice>{voice}</voice>')
            out.append(f'        <type>{ptype}</type>')
            out += ['        <dot/>'] * dots
            if alter:
                out.append(f'        <accidental>{ACC_NAME[alter]}</accidental>')
            out.append(f'        <staff>{staff}</staff>')
            notations = []
            if tie_stop and first:
                notations.append('<tied type="stop"/>')
            if (tie_start and last) or not last:
                notations.append('<tied type="start"/>')
            if artic and last and ni == 0:
                notations.append(f'<articulations><{artic}/></articulations>')
            if notations:
                out.append('        <notations>' + "".join(notations)
                           + '</notations>')
            out.append('      </note>')
    return out


def emit_slash(ticks, div, voice, staff, level):
    """
    11 — a slash: play the chord above, in your own time. Pitchless by
    design, sitting on the middle line, with no stem so it does not read as
    a specific rhythm.
    """
    out = []
    for plen, ptype, dots in decompose(ticks, div):
        out.append('      <note>')
        out.append('        <unpitched><display-step>B</display-step>'
                   '<display-octave>4</display-octave></unpitched>')
        out.append(f'        <duration>{plen}</duration>')
        out.append(f'        <voice>{voice}</voice>')
        out.append(f'        <type>{ptype}</type>')
        out += ['        <dot/>'] * dots
        out.append('        <stem>none</stem>')
        out.append('        <notehead>slash</notehead>')
        if staff != 1 or True:
            out.append(f'        <staff>{staff}</staff>')
        out.append('      </note>')
    return out


def emit_rest(ticks, div, voice, staff):
    out = []
    for plen, ptype, dots in decompose(ticks, div):
        out.append('      <note>')
        out.append('        <rest/>')
        out.append(f'        <duration>{plen}</duration>')
        out.append(f'        <voice>{voice}</voice>')
        out.append(f'        <type>{ptype}</type>')
        out += ['        <dot/>'] * dots
        out.append(f'        <staff>{staff}</staff>')
        out.append('      </note>')
    return out


# --------------------------------------------------------------- entry

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Copyist prototype: MIDI to MusicXML")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--key", help='e.g. "C# minor". Default: estimated')
    ap.add_argument("--reach", type=int, default=17,
                    help="maximum reach in semitones (default 17, an eleventh)")
    ap.add_argument("--comfortable", type=int, default=14,
                    help="comfortable reach in semitones (default 14)")
    ap.add_argument("--detail", default="full", choices=detail.LEVELS,
                    help="how much to tell them (DESIGN 11). default full")
    a = ap.parse_args()
    out = a.output or a.input.rsplit(".", 1)[0] + ".musicxml"
    convert(a.input, out, a.key, a.reach, a.comfortable, a.detail)
