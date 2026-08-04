#!/usr/bin/env python3
"""
Multi-part scores — DESIGN.md 10, extending the single-part converter.

Until this existed, Copyist merged every track of a file onto two piano
staves. A nineteen-track band arrangement came out as an unplayable piano
reduction, and the hand-separation model — which reasons about what one pair
of hands can physically reach — was being applied to a whole horn section.

What changes here:

  * (track, channel) pairs become separate parts. Verified against 25 real
    files: every one is format 1 with exactly one instrument per track.
  * GM program numbers finally resolve instruments (§10.2). The 25 files have
    empty track names and correct programs throughout, so name-only
    resolution identified nothing in material that was fully labelled.
  * Channel 10 routes to a percussion staff with real drum positions and
    noteheads, instead of treating a kick drum as a pitched C1.
  * Transposing instruments are written at written pitch with a <transpose>
    element (§10.3). Get this wrong and the part is unplayable, and it is
    invisible to a blind composer unless the tool says so.
  * Hand separation runs ONLY for two-staff instruments.

Usage:
    python3 multipart.py IN.mid [-o OUT.musicxml] [--key K] [--detail LEVEL]
"""

import argparse
import os
import sys
from collections import defaultdict
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analyze as A                                        # noqa: E402
import articulation                                        # noqa: E402
import convert as C                                        # noqa: E402
import detail                                              # noqa: E402
import harmony                                             # noqa: E402
import instruments as I                                    # noqa: E402
import organ                                               # noqa: E402
import pedals                                              # noqa: E402
import smf                                                 # noqa: E402
from spelling import ps13                                  # noqa: E402

# Chromatic semitones -> diatonic steps, for <transpose>.
DIATONIC = {0: 0, 1: 0, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4,
            8: 5, 9: 5, 10: 6, 11: 6, 12: 7, 14: 8, 21: 12, -12: -7}

CLEF_XML = {
    "treble": ('<clef><sign>G</sign><line>2</line></clef>',),
    "bass": ('<clef><sign>F</sign><line>4</line></clef>',),
    "treble8va": ('<clef><sign>G</sign><line>2</line>'
                  '<clef-octave-change>1</clef-octave-change></clef>',),
    "percussion": ('<clef><sign>percussion</sign><line>2</line></clef>',),
    "grand": ('<clef number="1"><sign>G</sign><line>2</line></clef>',
              '<clef number="2"><sign>F</sign><line>4</line></clef>'),
    # Organ: manuals then pedals. The pedal staff is always bass clef — feet
    # do not play above it.
    "organ": ('<clef number="1"><sign>G</sign><line>2</line></clef>',
              '<clef number="2"><sign>F</sign><line>4</line></clef>',
              '<clef number="3"><sign>F</sign><line>4</line></clef>'),
}


class Part:
    def __init__(self, pid, track, chan, notes, program, name, info):
        self.id = pid
        self.track, self.chan = track, chan
        self.notes = notes
        self.program = program
        self.track_name = name
        self.info = info
        self.streams = {1: [], 2: [], 3: []}
        self.divisions = None


def group_parts(mid, x, find):
    """One part per (track, channel). Drums always separate."""
    buckets = defaultdict(list)
    drums = []
    for n in x["notes"]:
        if n.chan == 9:
            # Every channel-10 track is the same player at the same kit.
            # Splitting them gives a score with four "Drum Kit" staves and no
            # drummer who could read it.
            drums.append(n)
        else:
            buckets[(n.track, n.chan)].append(n)
    if drums:
        buckets[(max((t for t, _ in buckets), default=0) + 99, 9)] = drums

    parts = []
    for i, ((trk, ch), notes) in enumerate(sorted(buckets.items()), start=1):
        progs = sorted(x["programs"].get(trk, []))
        program = progs[0] if progs else 0
        info = I.resolve(program, ch == 9, [n.pitch for n in notes],
                         x["names"].get(trk, ""), C.PLUGIN_ALIASES)
        parts.append(Part(f"P{i}", trk, ch, notes, program,
                          x["names"].get(trk, ""), info))

    unknown = [p for p in parts if p.info["source"] == "unidentified"]
    if unknown:
        find.add("uncertain",
                 f"{len(unknown)} track(s) could not be identified",
                 why="no track name, no plugin alias, no GM program",
                 suggestion="They default to a single treble staff")
    ndrum = sum(1 for p in parts if p.info["drums"])
    if ndrum:
        tracks = len({n.track for p in parts if p.info["drums"]
                      for n in p.notes})
        if tracks > 1:
            find.add("fixed-silently",
                     f"{tracks} percussion tracks merged into one kit",
                     why="channel 10 is one player, however many tracks it "
                         "was sequenced across")
    return parts


def report_parts(parts, find):
    """Called AFTER organ divisions are folded, or it counts one organ as three."""
    find.add("fixed-silently",
             f"{len(parts)} part(s) detected",
             why="; ".join(f"{p.info['name']}"
                           + (f" ({p.info['staves']} staves)"
                              if p.info["staves"] > 1 else "")
                           for p in parts[:8])
                 + (" …" if len(parts) > 8 else ""))


def process_part(part, div, grid, measure_ticks, reach, comfortable, find):
    """Everything that is per-instrument: snapping, staves, durations, spelling."""
    notes = part.notes
    for n in notes:
        snapped = int(round(n.on / grid)) * grid
        n.off += snapped - n.on
        n.on = snapped

    for n, sp in zip(notes, ps13(notes)):
        n.spell = sp

    by_onset = defaultdict(list)
    for n in notes:
        by_onset[n.on].append(n)

    if part.info["staves"] == 2:
        hands = C.Hands(reach, comfortable, find)
        prev = None
        for on in sorted(by_onset):
            group = by_onset[on]
            dt = (on - prev) / div if prev is not None else 1.0
            prev = on
            lh, rh = hands.assign([n.pitch for n in group],
                                  on // measure_ticks + 1, dt)
            for staff, members in ((1, rh), (2, lh)):
                sel = [n for n in group if n.pitch in members]
                if sel:
                    part.streams[staff].append(
                        dict(on=on, notes=sel,
                             gate=max(n.off for n in sel) - on))
    else:
        for on in sorted(by_onset):
            group = by_onset[on]
            part.streams[1].append(
                dict(on=on, notes=group, gate=max(n.off for n in group) - on))

    # 7.3 — gate time is articulation, never rests
    for seq in part.streams.values():
        for i, ch in enumerate(seq):
            nxt = seq[i + 1]["on"] if i + 1 < len(seq) else None
            slot = (nxt - ch["on"]) if nxt else max(
                int(round(ch["gate"] / grid)) * grid, grid)
            gap = max(slot - ch["gate"], 0)
            gap_q = int(round(gap / grid)) * grid
            gap_q = min(gap_q, slot - grid) if slot > grid else 0
            ch["dur"] = slot - gap_q
        articulation.annotate(seq)


def render(parts, chords, div, mticks, n_measures, fifths, mode,
           ts_num, ts_den, bpm, level):
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 '
         'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
         '<score-partwise version="4.0">',
         '  <identification><encoding>'
         '<software>Copyist prototype</software></encoding></identification>',
         '  <part-list>']

    for p in parts:
        inf = p.info
        L += [f'    <score-part id="{p.id}">',
              f'      <part-name>{escape(inf["name"])}</part-name>',
              f'      <part-abbreviation>{escape(inf["abbrev"])}</part-abbreviation>',
              f'      <score-instrument id="{p.id}-I1">',
              f'        <instrument-name>{escape(inf["name"])}</instrument-name>',
              f'        <instrument-sound>{inf["sound"]}</instrument-sound>',
              '      </score-instrument>',
              f'      <midi-instrument id="{p.id}-I1">',
              f'        <midi-channel>{p.chan + 1}</midi-channel>',
              f'        <midi-program>{p.program + 1}</midi-program>',
              '      </midi-instrument>',
              '    </score-part>']
    L.append('  </part-list>')

    chords_by_measure = defaultdict(list)
    for c in chords:
        chords_by_measure[c["measure"]].append(c)

    for pi, p in enumerate(parts):
        L.append(f'  <part id="{p.id}">')
        staves = p.info["staves"]
        carry = {i: None for i in range(1, staves + 1)}

        for m in range(int(n_measures)):
            m_start, m_end = m * mticks, (m + 1) * mticks
            L.append(f'    <measure number="{m + 1}">')

            if m == 0:
                tr = p.info["transpose"]
                L += ['      <attributes>',
                      f'        <divisions>{div}</divisions>',
                      f'        <key><fifths>{0 if p.info["drums"] else fifths}'
                      f'</fifths><mode>{mode}</mode></key>',
                      f'        <time><beats>{ts_num}</beats>'
                      f'<beat-type>{ts_den}</beat-type></time>']
                if staves >= 2:
                    L.append(f'        <staves>{staves}</staves>')
                for c in CLEF_XML[p.info["clef"]]:
                    L.append('        ' + c)
                if tr:
                    # MusicXML <transpose> goes WRITTEN -> SOUNDING, the
                    # opposite direction from our field.
                    ch_i = -tr
                    L += ['        <transpose>',
                          f'          <diatonic>{DIATONIC.get(ch_i, 0)}</diatonic>',
                          f'          <chromatic>{ch_i}</chromatic>',
                          '        </transpose>']
                L.append('      </attributes>')
                if pi == 0:
                    L += ['      <direction placement="above">',
                          '        <direction-type><metronome>'
                          '<beat-unit>quarter</beat-unit>'
                          f'<per-minute>{bpm:.0f}</per-minute>'
                          '</metronome></direction-type>',
                          f'        <sound tempo="{bpm:.2f}"/>',
                          '      </direction>']

            for staff_i, marks in getattr(p, "organ_marks", {}).items():
                for tick, text in marks:
                    if m_start <= tick < m_end:
                        L += ['      <direction placement="above">',
                              f'        <direction-type><words>{escape(text)}'
                              '</words></direction-type>',
                              f'        <staff>{staff_i}</staff>',
                              '      </direction>']

            for d in pedals.directions_for_measure(
                    getattr(p, 'pedals', {}), m_start, m_end,
                    2 if staves == 2 else 1):
                L.append(d)

            if pi == 0:
                for c in chords_by_measure.get(m, []):
                    step, alter = C.root_step(c["root"], fifths)
                    L += ['      <harmony>',
                          '        <root><root-step>' + step + '</root-step>'
                          + (f'<root-alter>{alter}</root-alter>' if alter else '')
                          + '</root>',
                          f'        <kind text="{escape(c["suffix"])}">'
                          f'{c["kind"]}</kind>',
                          '      </harmony>']

            for staff in range(1, staves + 1):
                # Convention: staff 1 owns voices 1-4, staff 2 owns
                # 5-8, staff 3 owns 9-12.
                voice = (staff - 1) * 4 + 1
                if staff > 1:
                    L.append(f'      <backup><duration>{mticks}</duration></backup>')
                pos = m_start
                seq = [c for c in p.streams[staff] if m_start <= c["on"] < m_end]

                if carry[staff]:
                    length, notes = carry[staff]
                    fits = min(length, mticks)
                    L += emit(notes, fits, div, voice, staff, None, p,
                              tie_stop=True, tie_start=fits < length)
                    carry[staff] = (length - fits, notes) if fits < length else None
                    pos += fits

                for ch in seq:
                    if ch["on"] > pos:
                        L += emit_rest(ch["on"] - pos, div, voice, staff, staves)
                        pos = ch["on"]
                    fits = min(ch["dur"], m_end - pos)
                    if fits <= 0:
                        continue
                    L += emit(ch["notes"], fits, div, voice, staff,
                              ch.get("artic"), p, tie_start=fits < ch["dur"])
                    if fits < ch["dur"]:
                        carry[staff] = (ch["dur"] - fits, ch["notes"])
                    pos += fits

                if pos < m_end:
                    L += emit_rest(m_end - pos, div, voice, staff, staves)

            L.append('    </measure>')
        L.append('  </part>')

    L += ['</score-partwise>', '']
    return "\n".join(L)


def emit(ns, ticks, div, voice, staff, artic, part,
         tie_stop=False, tie_start=False):
    out = []
    parts_ = C.decompose(ticks, div)
    drums = part.info["drums"]
    tr = part.info["transpose"]
    for pi, (plen, ptype, dots) in enumerate(parts_):
        first, last = pi == 0, pi == len(parts_) - 1
        for ni, n in enumerate(sorted(ns, key=lambda z: z.pitch)):
            out.append('      <note>')
            if ni:
                out.append('        <chord/>')
            if drums:
                step, octv, head = I.drum_position(n.pitch)
                out.append(f'        <unpitched><display-step>{step}'
                           f'</display-step><display-octave>{octv}'
                           f'</display-octave></unpitched>')
            else:
                written = n.pitch + tr
                if tr and n.spell:
                    st, al, oc = C.spell(written, C._TRANSPOSE_TABLE)
                else:
                    st, al, oc = (n.spell if n.spell
                                  else C.spell(written, C._TRANSPOSE_TABLE))
                out.append('        <pitch>'
                           f'<step>{st}</step>'
                           + (f'<alter>{al}</alter>' if al else '')
                           + f'<octave>{oc}</octave></pitch>')
            out.append(f'        <duration>{plen}</duration>')
            if tie_stop and first:
                out.append('        <tie type="stop"/>')
            if (tie_start and last) or not last:
                out.append('        <tie type="start"/>')
            out.append(f'        <voice>{voice}</voice>')
            out.append(f'        <type>{ptype}</type>')
            out += ['        <dot/>'] * dots
            if drums:
                _, _, head = I.drum_position(n.pitch)
                if head != "normal":
                    out.append(f'        <notehead>{head}</notehead>')
            elif not drums and n.spell and n.spell[1]:
                out.append(f'        <accidental>'
                           f'{C.ACC_NAME[n.spell[1]]}</accidental>')
            if part.info["staves"] >= 2:
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


def emit_rest(ticks, div, voice, staff, staves):
    out = []
    for plen, ptype, dots in C.decompose(ticks, div):
        out.append('      <note><rest/>')
        out.append(f'        <duration>{plen}</duration>')
        out.append(f'        <voice>{voice}</voice>')
        out.append(f'        <type>{ptype}</type>')
        out += ['        <dot/>'] * dots
        if staves >= 2:
            out.append(f'        <staff>{staff}</staff>')
        out.append('      </note>')
    return out


def convert(path, out_path, key_name=None, reach=17, comfortable=14,
            level="full"):
    mid = A.parse_midi(path)
    x = A.extract(mid)
    div = mid["division"]
    notes = x["notes"]
    if not notes:
        raise ValueError("That file contains no notes.")

    find = C.Findings()
    bpm = 60_000_000 / x["tempos"][0][1] if x["tempos"] else 120.0
    ts_num, ts_den = ((x["timesigs"][0][1], x["timesigs"][0][2])
                      if x["timesigs"] else (4, 4))
    measure_ticks = int(ts_num * (4 / ts_den) * div)

    if key_name is None:
        est = A.estimate_key([n for n in notes if n.chan != 9])
        key_name = est[0][0]
        if est[0][1] < 0.60:
            find.add("uncertain",
                     f"Key is ambiguous: {est[0][0]} vs {est[1][0]}",
                     why=f"{est[0][1] * 100:.0f}% / {est[1][1] * 100:.0f}%")
    fifths = C.KEYS.get(key_name)
    if fifths is None:
        raise ValueError(f"Unknown key {key_name!r}")
    mode = "minor" if key_name.endswith("minor") else "major"
    C._TRANSPOSE_TABLE = C.spelling_table(fifths, find)

    gname, _ = A.classify_timing(notes, div, bpm, (ts_num, ts_den))
    grid = max(int(round(dict(A.GRIDS).get(gname, 0.5) * div)), 1)

    parts = group_parts(mid, x, find)

    # 8 / 10 — an organ is ONE player at ONE instrument on three staves, not
    # three instruments in the part list.
    organ_parts = organ.looks_like_organ(parts)
    organ_divisions = {}
    if organ_parts:
        organ_divisions = organ.assign_divisions(organ_parts)
        keep = organ_divisions[organ.STAFF_UPPER]
        keep.info = dict(keep.info)
        keep.info.update(name="Organ", abbrev="Org.",
                         sound="keyboard.organ",
                         staves=len(organ_divisions), clef="organ")
        keep.divisions = organ_divisions
        parts = [keep] + [p for p in parts if p not in organ_parts]
        for i, p in enumerate(parts, start=1):
            p.id = f"P{i}"
    report_parts(parts, find)

    for p in parts:
        if getattr(p, "divisions", None):
            for staff, dpart in p.divisions.items():
                process_part(dpart, div, grid, measure_ticks,
                             reach, comfortable, find)
                p.streams[staff] = dpart.streams[1]
        else:
            process_part(p, div, grid, measure_ticks, reach, comfortable, find)
        # Pedalling belongs to keyboards. A trumpet part with sustain marks on
        # it is noise, and DESIGN 11.3 found that even a real piano part in an
        # ensemble chart carries none.
        if getattr(p, "divisions", None):
            p.organ_marks = organ.describe(p.divisions, mid["tracks"],
                                           level, find)
        p.pedals = (pedals.collect(mid["tracks"], p.chan,
                                   find if p.info["staves"] == 2 else None)
                    if p.info["staves"] == 2 else {})

    pitched = [n for n in notes if n.chan != 9]
    chords = harmony.detect(pitched, measure_ticks, fifths, find=find) \
        if pitched else []

    total = max(n.off for n in notes)
    n_measures = total // measure_ticks + 1

    if level != "full":
        for p in parts:
            p.streams, _ = detail.reduce_streams(
                p.streams, level, measure_ticks, div, ts_num, ts_den,
                n_measures, None)
            p.info["staves"] = 1

    xml = render(parts, chords, div, measure_ticks, n_measures, fifths, mode,
                 ts_num, ts_den, bpm, level)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)

    C.LAST_FINDINGS = find
    C.LAST_SUMMARY = {
        "key": key_name, "fifths": fifths, "measures": int(n_measures),
        "notes": len(notes), "parts": len(parts),
        "partNames": [p.info["name"] for p in parts],
        "transposing": sum(1 for p in parts if p.info["transpose"]),
        "drumParts": sum(1 for p in parts if p.info["drums"]),
    }
    return C.LAST_SUMMARY


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Copyist multi-part converter")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--key")
    ap.add_argument("--detail", default="full", choices=detail.LEVELS)
    ap.add_argument("--reach", type=int, default=17)
    ap.add_argument("--comfortable", type=int, default=14)
    a = ap.parse_args()
    out = a.output or a.input.rsplit(".", 1)[0] + ".musicxml"
    s = convert(a.input, out, a.key, a.reach, a.comfortable, a.detail)
    print(f"\n{os.path.basename(a.input)}")
    print(f"  key        {s['key']}")
    print(f"  parts      {s['parts']}  ({s['transposing']} transposing, "
          f"{s['drumParts']} percussion)")
    for n in s["partNames"]:
        print(f"               {n}")
    print(f"  measures   {s['measures']}")
    print(f"  written to {out}")
    print(C.LAST_FINDINGS.report())
