#!/usr/bin/env python3
"""chartdemo — the `from demo` door: chart figures from played MIDI.

Slices a bar range out of a demo MIDI track and turns it into notation:

- The player's systematic lay-back is measured per phrase (median offset to
  the grid) and removed before anything snaps — the feel belongs to the
  player, the page gets the intended rhythm.
- The grid is chosen PER BEAT by tuplets.choose (the Arabesque lesson:
  straight sixteenths in one bar, triplets in the next).
- Short played gates are extended to the next onset when the gap is under a
  quarter of a beat, so live articulation does not become rest-peppered
  notation.
- Out-of-range notes fold by octaves into the part's sounding range, and a
  finding names the bar.

The chart is not a transcription: pitch bends, CC data and micro-timing are
deliberately discarded. What survives is the line.
"""
import os

import analyze
import convert
import tuplets
from convert import spelling_table, decompose

DIV = 24                # chart divisions per quarter (16th=6, trip-16th=4)
BEATS = 4               # 4/4 only, matching chartc's increment
BAR = DIV * BEATS

# subdivisions a horn chart may use; quintuplets and septuplets stay out
ALLOW = {k: v for k, v in tuplets.CANDIDATES.items() if k in (1, 2, 3, 4, 6, 8)}

ACC_NAME = {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp",
            2: "sharp-sharp"}


class Findings:
    def __init__(self):
        self.lines = []

    def add(self, *args, **kw):
        text = ": ".join(str(a) for a in args if a)
        self.lines.append(text)


class Demo:
    """One demo MIDI file, parsed once, tracks addressable by name."""

    def __init__(self, path):
        self.path = path
        mid = analyze.parse_midi(path)
        self.division = mid["division"]
        ex = analyze.extract(mid)
        self.names = ex["names"]
        by_track = {}
        for n in ex["notes"]:
            by_track.setdefault(n.track, []).append(n)
        self.tracks = by_track
        self.cc = {}                    # track -> [(tick, CC11 value)]
        for ti, trk in enumerate(mid["tracks"]):
            for ev in trk:
                if ev[1] == "chan" and ev[2] == 0xB0 and ev[4] == 11:
                    self.cc.setdefault(ti, []).append((ev[0], ev[5]))

    def idx(self, name):
        note_tracks = sorted(self.tracks)
        if name is None:
            if len(note_tracks) == 1:
                return note_tracks[0]
            raise SystemExit(
                f"chartc: demo '{os.path.basename(self.path)}' has "
                f"{len(note_tracks)} note tracks — name one")
        want = name.strip().lower()
        hits = [ti for ti in note_tracks
                if self.names.get(ti, "").strip().lower() == want]
        if len(hits) == 1:
            return hits[0]
        have = [self.names.get(ti, f"(track {ti})") for ti in note_tracks]
        raise SystemExit(
            f"chartc: demo track '{name}' "
            f"{'is ambiguous' if hits else 'not found'} in "
            f"{os.path.basename(self.path)} — tracks: {have}")

    def track(self, name):
        return self.tracks[self.idx(name)]

    def cc11(self, name):
        return self.cc.get(self.idx(name), [])


_DEMOS = {}


def load_demo(path):
    if path not in _DEMOS:
        if not os.path.exists(path):
            raise SystemExit(f"chartc: demo file '{path}' not found")
        _DEMOS[path] = Demo(path)
    return _DEMOS[path]


def resolve_range(demo, track_name, bar_lo, bar_hi, at_bar, *,
                  octave_shift=0, sounding_range=None, quant=None,
                  derive_dyns=True, part_label="", findings=None):
    """
    Resolve demo bars [bar_lo, bar_hi] (the file's own 1-based numbering)
    into a quantized timeline of sounding pitches starting at absolute
    chart bar `at_bar`. Shared by the page (render_range) and the prose
    (say_range), so the two cannot disagree.
    """
    find = findings if findings is not None else Findings()
    src = demo.track(track_name)
    beat = demo.division
    tick_bar = beat * BEATS
    lo_t = (bar_lo - 1) * tick_bar
    hi_t = bar_hi * tick_bar
    # A hair of pre-roll for an attack played a touch early — no more: a
    # generous slack swallows the previous figure's last note and makes a
    # phantom collision at beat 1 (the trombone climb taught this).
    slack = beat // 8
    picked = [(n.on, n.off or n.on, n.pitch) for n in src
              if lo_t - slack <= n.on < hi_t]
    if not picked:
        raise SystemExit(
            f"chartc: {part_label}: demo bars {bar_lo}-{bar_hi} of "
            f"'{track_name or os.path.basename(demo.path)}' hold no notes")

    # ---- take the lay-back out. The offset is measured against the grid
    # the writer named — measuring triplet positions against the sixteenth
    # grid manufactures a phantom lag that pushes the notes exactly
    # between the tuplet grids (the bari climb taught this).
    gmod = {'eighths': beat / 2, 'triplets': beat / 6,
            'triplet8': beat / 3, 'sixteenths': beat / 4}.get(quant, beat / 4)
    half = gmod / 2
    offs = sorted((on % gmod) if (on % gmod) < half
                  else (on % gmod) - gmod for on, _, _ in picked)
    lag = offs[len(offs) // 2]
    if abs(lag) > beat * 0.04:
        ms = abs(lag) * 60000 / (87 * beat)
        find.add(f"{part_label}: bars {bar_lo}-{bar_hi} played "
                 f"{'behind' if lag > 0 else 'ahead of'} the beat by about "
                 f"{ms:.0f} ms — that is the feel; the page keeps the "
                 "intended rhythm")
    else:
        lag = 0
    moved = [(on - lag - lo_t, off - lag - lo_t, p) for on, off, p in picked]

    # ---- per-beat grid, then snap. A `quant` hint from the writer beats
    # any statistics: "eighths" means these bars are eighth notes, full stop.
    allow = ALLOW
    if quant == 'eighths':
        allow = {k: v for k, v in tuplets.CANDIDATES.items() if k in (1, 2)}
    elif quant == 'triplets':
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 2, 3, 6)}
    elif quant == 'triplet8':
        # the writer said eighth-note triplets: no binary escape hatch
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 3)}
    elif quant == 'sixteenths':
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 2, 4)}
    grids = tuplets.choose(sorted(max(0, on) for on, _, _ in moved),
                           beat, allow)
    tupl = tuplets.summarize({b: s for b, s in grids.items()
                              if tuplets.CANDIDATES[s][2] !=
                              tuplets.CANDIDATES[s][3]})
    if tupl:
        find.add(f"{part_label}: bars {bar_lo}-{bar_hi} use tuplet beats "
                 f"({tupl})")

    n_units = (bar_hi - bar_lo + 1) * BAR
    scale = DIV / beat                     # demo ticks -> chart ticks
    default_sub = {'eighths': 2, 'triplet8': 3}.get(quant, 4)

    events = {}                            # chart-tick onset -> [(pitch, off)]
    for on, off, p in moved:
        on = max(0, on)
        b = int(on // beat)
        sub = grids.get(b, default_sub)
        step = beat / sub
        q_on = int(round((b * beat + round((on % beat) / step) * step)
                         * scale))
        if q_on >= n_units:
            continue

        # the ending snaps to the grid of the beat it falls in, so a
        # duration inside a tuplet beat is always whole subdivisions
        x = off * scale
        ob = int(x // DIV)
        ostep = DIV / grids.get(ob, default_sub)
        q_off = int(round(ob * DIV + round((x - ob * DIV) / ostep) * ostep))
        onstep = int(DIV / sub)
        q_off = max(q_on + onstep, min(q_off, n_units))
        if quant == 'eighths' and (off - on) < beat:
            # the writer said eighths: only a genuinely held gate may be
            # longer than one
            q_off = min(q_off, q_on + DIV // 2)
        p = p + 12 * octave_shift
        if sounding_range:
            lo_r, hi_r = sounding_range
            folded = p
            while folded < lo_r:
                folded += 12
            while folded > hi_r:
                folded -= 12
            if folded != p:
                find.add(f"{part_label}: bar {at_bar + q_on // BAR} note "
                         f"moved {'up' if folded > p else 'down'} "
                         f"{abs(folded - p) // 12} octave(s) into range")
                p = folded
        events.setdefault(q_on, []).append((p, q_off, on))

    # A horn is one voice: when several played notes land on one slot,
    # the latest-played keeps it and earlier ones step back one free
    # subdivision — a note that exists in the playing should survive
    # quantization whenever there is room for it.
    for q_on in sorted(events):
        lst = events[q_on]
        if len(lst) <= 1:
            continue
        lst.sort(key=lambda t: t[2])
        events[q_on] = [lst[-1]]
        for mv in reversed(lst[:-1]):
            step = DIV // grids.get(q_on // DIV, default_sub)
            tgt = q_on - step
            if tgt >= 0 and tgt not in events:
                events[tgt] = [(mv[0], min(mv[1], q_on), mv[2])]
                find.add(f"{part_label}: bar {at_bar + q_on // BAR}: two "
                         "played notes landed on one slot — moved the "
                         "earlier one back a step")
            else:
                find.add(f"{part_label}: bar {at_bar + q_on // BAR}: two "
                         "played notes landed on one slot with no room — "
                         "dropped the earlier one; proofread this bar")

    # ---- monophonic cleanup and legato gap-closing
    onsets = sorted(events)
    close = DIV // 4
    timeline = []                          # (start, end, [pitches])
    for i, q_on in enumerate(onsets):
        end = max(e for _, e, _ in events[q_on])
        nxt = onsets[i + 1] if i + 1 < len(onsets) else None
        if nxt is not None:
            if end > nxt:
                end = nxt                  # a horn is one voice
            elif 0 < nxt - end <= close:
                end = nxt                  # close a sliver of daylight
        end = max(end, q_on + 1)
        end = min(end, n_units)
        pitches = sorted({p for p, _, _ in events[q_on]})
        timeline.append((q_on, end, pitches))

    grids_chart = {b: grids.get(b, default_sub)
                   for b in range((n_units // DIV) + 1)}

    # ---- dynamics from the expression pedal (CC 11): one mark per level
    # change, judged by each bar's median, printed only on bars that play
    def klass(v):
        for cap, k in ((40, 'p'), (64, 'mp'), (90, 'mf'), (112, 'f')):
            if v < cap:
                return k
        return 'ff'
    by_bar = {}
    for t, v in (demo.cc11(track_name) if derive_dyns else ()):
        if lo_t <= t < hi_t:
            by_bar.setdefault(int((t - lo_t) // tick_bar), []).append(v)
    active = {s // BAR for s, _, _ in timeline}
    dyns, prev = [], None
    for bo in sorted(active):
        vs = sorted(by_bar.get(bo, []))
        if not vs:
            continue
        k = klass(vs[len(vs) // 2])
        if k != prev:
            dyns.append((bo * BAR, k))
            prev = k
    if dyns:
        find.add(f"{part_label}: bars {bar_lo}-{bar_hi} dynamics read from "
                 "the expression pedal: "
                 + ", ".join(f"{k} at bar {at_bar + t // BAR}"
                             for t, k in dyns))

    return {'timeline': timeline, 'grids': grids_chart,
            'n_units': n_units, 'at': at_bar,
            'bars': (bar_lo, bar_hi), 'dyns': dyns}


def render_range(res, fifths_written, transpose_to_written, fall,
                 findings=None, short=False, marcato=False):
    """Resolved timeline -> {abs_bar: MusicXML measure content}."""
    find = findings if findings is not None else Findings()
    at_bar = res['at']
    n_units = res['n_units']
    timeline = res['timeline']
    grids_chart = res['grids']
    table = spelling_table(fifths_written, find)
    last_artic = 'falloff' if fall else ('staccato' if short else None)
    every = 'strong-accent' if marcato else None    # the big-band daht

    out = {b: [] for b in
           range(at_bar, at_bar + (n_units // BAR))}
    pos = 0
    for ti, (start, end, pitches) in enumerate(timeline):
        if start > pos:
            _emit(out, at_bar, pos, start, None, table, grids_chart,
                  None, transpose_to_written)
        is_last = ti == len(timeline) - 1
        _emit(out, at_bar, start, end, pitches, table, grids_chart,
              (last_artic if is_last else None) or every,
              transpose_to_written)
        pos = end
    if pos < n_units:
        _emit(out, at_bar, pos, n_units, None, table, grids_chart,
              None, transpose_to_written)

    SOUND_DYN = {'p': 54, 'mp': 71, 'mf': 89, 'f': 106, 'ff': 123}
    for t, k in res.get('dyns', []):
        bar = at_bar + t // BAR
        if bar in out:
            out[bar].insert(
                0,
                '      <direction placement="below"><direction-type>'
                f'<dynamics><{k}/></dynamics></direction-type>'
                f'<sound dynamics="{SOUND_DYN[k]}"/></direction>\n')

    return {b: "".join(lines) for b, lines in out.items()}


def _is_tuplet(grids, b):
    sub = grids.get(b, 4)
    _, _, actual, normal, _ = tuplets.CANDIDATES[sub]
    return actual != normal


def _pieces(start, end, grids):
    """Cut a span at barlines always, and at beat boundaries around any
    tuplet beat, so every piece lives in exactly one naming regime."""
    cuts = []
    pos = start
    while pos < end:
        b = pos // DIV
        next_beat = (b + 1) * DIV
        stop = min(end, (pos // BAR + 1) * BAR)
        if _is_tuplet(grids, b):
            stop = min(stop, next_beat)
        else:
            nb = b + 1
            while nb * DIV < stop:
                if _is_tuplet(grids, nb):
                    stop = nb * DIV
                    break
                nb += 1
        cuts.append((pos, stop))
        pos = stop
    return cuts


def _name(ticks, sub):
    """(len, type, dots, time-modification) pieces for one duration.

    Inside a tuplet beat every piece must speak tuplet language — a binary
    64th sliver in a sextuplet beat is exactly what MuseScore refuses. A
    duration that is not one nameable value splits greedily into nameable
    tuplet chunks (five sextuplet-sixteenths = quarter + sixteenth, both
    carrying the 6:4 modification)."""
    mod = tuplets.modification(sub)
    if mod:
        nd = tuplets.notated(ticks, DIV, sub)
        if nd:
            return [(ticks, nd[0], nd[1], mod)]
        step = DIV // sub
        if ticks % step == 0:
            out, rem = [], ticks // step
            for mult in (8, 6, 4, 3, 2, 1):
                while rem >= mult:
                    nd = tuplets.notated(mult * step, DIV, sub)
                    if nd is None:
                        break
                    out.append((mult * step, nd[0], nd[1], mod))
                    rem -= mult
                if rem == 0:
                    return out
    return [(t, ty, d, None) for t, ty, d in decompose(ticks, DIV)]


def _emit(out, at_bar, start, end, pitches, table, grids, artic, transpose):
    pieces = _pieces(start, end, grids)
    for pi, (a, b) in enumerate(pieces):
        bar = at_bar + a // BAR
        if bar not in out:
            continue
        first, last = pi == 0, pi == len(pieces) - 1
        sub = grids.get(a // DIV, 4)
        if pitches is None and a % BAR == 0 and b - a == BAR:
            out[bar].append(
                '      <note>\n        <rest measure="yes"/>\n'
                f'        <duration>{BAR}</duration>\n'
                '        <voice>1</voice>\n      </note>\n')
            continue
        parts = _name(b - a, sub)
        for qi, (plen, ptype, dots, mod) in enumerate(parts):
            plast = last and qi == len(parts) - 1
            pfirst = first and qi == 0
            if pitches is None:
                out[bar].append('      <note>\n        <rest/>\n'
                                f'        <duration>{plen}</duration>\n'
                                '        <voice>1</voice>\n'
                                f'        <type>{ptype}</type>\n'
                                + '        <dot/>\n' * dots
                                + (_mod_xml(mod) if mod else '')
                                + '      </note>\n')
                continue
            for ni, p in enumerate(pitches):
                w = p + transpose
                step, alter, octave = convert.spell(w, table)
                lines = ['      <note>']
                if ni:
                    lines.append('        <chord/>')
                lines.append('        <pitch>'
                             f'<step>{step}</step>'
                             + (f'<alter>{alter}</alter>' if alter else '')
                             + f'<octave>{octave}</octave></pitch>')
                lines.append(f'        <duration>{plen}</duration>')
                if not pfirst:
                    lines.append('        <tie type="stop"/>')
                if not plast:
                    lines.append('        <tie type="start"/>')
                lines.append('        <voice>1</voice>')
                lines.append(f'        <type>{ptype}</type>')
                lines += ['        <dot/>'] * dots
                if alter:
                    lines.append(
                        f'        <accidental>{ACC_NAME[alter]}</accidental>')
                if mod:
                    lines.append(_mod_xml(mod).rstrip())
                notations = []
                if not pfirst:
                    notations.append('<tied type="stop"/>')
                if not plast:
                    notations.append('<tied type="start"/>')
                if artic and plast and ni == len(pitches) - 1:
                    notations.append(f'<articulations><{artic}/>'
                                     '</articulations>')
                if notations:
                    lines.append('        <notations>' + ''.join(notations)
                                 + '</notations>')
                lines.append('      </note>')
                out[bar].append("\n".join(lines) + "\n")


def _mod_xml(mod):
    return ('        <time-modification>'
            f'<actual-notes>{mod["actual"]}</actual-notes>'
            f'<normal-notes>{mod["normal"]}</normal-notes>'
            '</time-modification>\n')


# ------------------------------------------------------------- prose

ACC_WORD = {-2: ' double flat', -1: ' flat', 0: '', 1: ' sharp',
            2: ' double sharp'}

DUR_WORD = {96: 'whole note', 84: 'double-dotted half', 72: 'dotted half',
            48: 'half note', 36: 'dotted quarter', 24: 'quarter',
            18: 'dotted eighth', 12: 'eighth', 9: 'dotted sixteenth',
            6: 'sixteenth', 3: 'thirty-second',
            16: 'triplet quarter', 8: 'triplet eighth',
            4: 'triplet sixteenth', 2: 'sextuplet thirty-second'}


def _say_pitch(p, table):
    step, alter, octave = convert.spell(p, table)
    return f"{step}{ACC_WORD[alter]} {octave}"


def _say_beat(pos):
    beat = pos % BAR / DIV + 1
    if beat == int(beat):
        return f"beat {int(beat)}"
    if (pos % DIV) % (DIV // 2) == 0:
        return f"the and of {int(beat)}"
    return f"inside beat {int(beat)}"


def _say_dur(ticks):
    if ticks in DUR_WORD:
        return DUR_WORD[ticks]
    return f"about {ticks / DIV:.1f} beats"


def say_range(res, concert_fifths, fall=False, findings=None, short=False):
    """Resolved timeline -> {abs_bar: prose}, spoken at concert pitch."""
    find = findings if findings is not None else Findings()
    table = spelling_table(concert_fifths, find)
    at_bar = res['at']
    out = {}
    # group consecutive same-duration single notes into runs
    tl = res['timeline']
    i = 0
    while i < len(tl):
        start, end, pitches = tl[i]
        dur = end - start
        j = i
        while (j + 1 < len(tl)
               and tl[j + 1][0] == tl[j][1]                 # gapless
               and tl[j + 1][1] - tl[j + 1][0] == dur       # same length
               and tl[j + 1][0] // BAR == start // BAR      # same bar
               and len(tl[j + 1][2]) == 1 and len(pitches) == 1):
            j += 1
        bar = at_bar + start // BAR
        clauses = out.setdefault(bar, [])
        where = _say_beat(start)
        if j > i:
            names = ", ".join(_say_pitch(t[2][0], table) for t in tl[i:j + 1])
            clauses.append(f"from {where}, {_say_dur(dur)}s: {names}")
        else:
            what = " and ".join(_say_pitch(p, table) for p in pitches)
            if len(pitches) > 1:
                what = "chord " + what
            held = ""
            if end // BAR > start // BAR and end % BAR:
                held = f", held into bar {at_bar + end // BAR}"
            clauses.append(f"{where}: {_say_dur(end - start)} {what}{held}")
        if j == len(tl) - 1:
            if fall:
                clauses[-1] += ", with a big fall off the end"
            elif short:
                clauses[-1] += ", short"
        i = j + 1
    DYN_WORD = {'p': 'piano', 'mp': 'mezzo piano', 'mf': 'mezzo forte',
                'f': 'forte', 'ff': 'fortissimo'}
    for t, k in res.get('dyns', []):
        bar = at_bar + t // BAR
        if bar in out:
            out[bar].insert(0, DYN_WORD[k])
    return {b: "; ".join(cl) + "." for b, cl in out.items()}
