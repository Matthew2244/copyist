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
BEATS = 4               # the 4/4 default; meter arrives per call
BAR = DIV * BEATS       # the 4/4 bar, kept for callers with no meter

# subdivisions a horn chart may use; quintuplets and septuplets stay out
ALLOW = {k: v for k, v in tuplets.CANDIDATES.items() if k in (1, 2, 3, 4, 6, 8)}

ACC_NAME = {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp",
            2: "sharp-sharp"}


class Findings:
    def __init__(self):
        self.lines = []

    def add(self, *args, **kw):
        text = ": ".join(str(a) for a in args if a)
        # convert.py callers pass structured detail; keep what a reader
        # needs (the where and the why), drop the machine fields
        extra = [str(kw[k]) for k in ('location', 'why') if kw.get(k)]
        if extra:
            text += " (" + "; ".join(extra) + ")"
        self.lines.append(text)


class Demo:
    """One demo MIDI file, parsed once, tracks addressable by name."""

    def __init__(self, path):
        self.path = path
        mid = analyze.parse_midi(path)
        self.division = mid["division"]
        ex = analyze.extract(mid)
        self.names = ex["names"]
        self.timesigs = ex["timesigs"]      # [(tick, num, den)], often 4/4@0
        by_track = {}
        for n in ex["notes"]:
            by_track.setdefault(n.track, []).append(n)
        self.tracks = by_track
        self.cc = {}                    # track -> [(tick, CC11 value)]
        for ti, trk in enumerate(mid["tracks"]):
            for ev in trk:
                if ev[1] == "chan" and ev[2] == 0xB0 and ev[4] == 11:
                    self.cc.setdefault(ti, []).append((ev[0], ev[5]))

    def _segments(self):
        """The file's meter map as (start_tick, num, den), deduped, with a
        4/4 floor at tick zero when the file starts silent about it."""
        segs = [(0, 4, 4)]
        for t, n, d in sorted(self.timesigs):
            if t == segs[-1][0]:
                segs[-1] = (t, n, d)
            else:
                segs.append((t, n, d))
        return segs

    def bar_tick(self, bar):
        """Tick where the file's own bar N (1-based) starts, from its time
        signatures. A signature landing mid-bar governs from the next
        computed bar — DAW exports land them on barlines anyway."""
        segs = self._segments()
        starts = [0]
        si = 0
        while len(starts) < bar:
            t0 = starts[-1]
            while si + 1 < len(segs) and segs[si + 1][0] <= t0:
                si += 1
            _, n, d = segs[si]
            starts.append(t0 + self.division * 4 * n // d)
        return starts[bar - 1]

    def bar_of(self, tick):
        """The file's own 1-based bar number holding a tick."""
        bar = 1
        while self.bar_tick(bar + 1) <= tick:
            bar += 1
        return bar

    def mixed_meter(self):
        """True when the file's own map holds more than one meter."""
        return len({(n, d) for _, n, d in self._segments()}) > 1

    def meter_of(self, bar):
        """The (num, den) governing the file's own bar N."""
        t0 = self.bar_tick(bar)
        n, d = 4, 4
        for t, nn, dd in self._segments():
            if t <= t0:
                n, d = nn, dd
        return (n, d)

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


def _mono_tl(events, n_units):
    """One voice's cleanup: truncate at the voice's next onset, close
    slivers of daylight, cap at the figure's end."""
    onsets = sorted(events)
    close = DIV // 4
    timeline = []                          # (start, end, [pitches])
    for i, q_on in enumerate(onsets):
        end = max(e for _, e, _ in events[q_on])
        nxt = onsets[i + 1] if i + 1 < len(onsets) else None
        if nxt is not None:
            if end > nxt:
                end = nxt                  # one voice, one line
            elif 0 < nxt - end <= close:
                end = nxt                  # close a sliver of daylight
        end = max(end, q_on + 1)
        end = min(end, n_units)
        pitches = sorted({p for p, _, _ in events[q_on]})
        timeline.append((q_on, end, pitches))
    return timeline


def _pedals(evts, n_units):
    """Pull pedal tones out of one staff's events: a note that keeps
    ringing under (or over) later movement becomes its own voice instead
    of being cut at the next onset. Mutates evts; returns the pedal
    timeline. The pedal layer never overlaps itself — of a run of
    let-ring notes, the first keeps ringing and the rest stay in the
    line, which is a chart's honest reading of a wash of sustain."""
    onsets = sorted(evts)
    pedals = []                            # [start, end, [pitches]]
    for q_on in onsets:
        for item in list(evts.get(q_on, ())):
            p, off, _raw = item
            off = min(off, n_units)
            crossed = [o for o in onsets
                       if q_on < o <= off - DIV // 2]
            if not crossed:
                continue
            others = [pp for o in crossed for (pp, _, _) in evts[o]]
            if not others or not (all(pp > p for pp in others)
                                  or all(pp < p for pp in others)):
                continue
            clash = [pe for pe in pedals
                     if not (off <= pe[0] or q_on >= pe[1])]
            if clash:
                pe = clash[-1]
                if len(clash) == 1 and pe[0] == q_on and pe[1] == off:
                    pe[2].append(p)        # a held chord rings as one
                else:
                    continue
            else:
                pedals.append([q_on, off, [p]])
            evts[q_on].remove(item)
            if not evts[q_on]:
                del evts[q_on]
    return [(s, e, sorted(ps)) for s, e, ps in pedals]


def resolve_range(demo, track_name, bar_lo, bar_hi, at_bar, *,
                  octave_shift=0, sounding_range=None, quant=None,
                  derive_dyns=True, short=False, spoken_shift=0,
                  poly=False, grand=False, reach=17, comfortable=14,
                  meter=(4, 4), window=None, part_label="",
                  findings=None):
    """
    Resolve demo bars [bar_lo, bar_hi] (the file's own 1-based numbering)
    into a quantized timeline of sounding pitches starting at absolute
    chart bar `at_bar`. Shared by the page (render_range) and the prose
    (say_range), so the two cannot disagree.

    `spoken_shift` is the count-in: everything SPOKEN (findings, the
    read-aloud) adds it, so the writer hears their own DAW bar numbers.
    The printed page keeps printed numbers — players count from one.
    """
    find = findings if findings is not None else Findings()
    src = demo.track(track_name)
    beat = demo.division
    m_num, m_den = meter
    tick_bar = beat * 4 * m_num // m_den
    bar_ticks = DIV * 4 * m_num // m_den
    pulse_div = DIV * 4 // m_den
    if window is not None:
        # the caller located the bars against a meter map (the demo's own
        # time signatures, or the chart's) — single-meter arithmetic below
        # would miss every bar after a change
        lo_t, hi_t = window
    else:
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
    gmod = {'quarters': beat, 'eighths': beat / 2, 'triplets': beat / 6,
            'triplet8': beat / 3, 'triplet16': beat / 6,
            'sixteenths': beat / 4}.get(quant, beat / 4)
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
    if quant == 'quarters':
        allow = {k: v for k, v in tuplets.CANDIDATES.items() if k in (1,)}
    elif quant == 'eighths':
        allow = {k: v for k, v in tuplets.CANDIDATES.items() if k in (1, 2)}
    elif quant == 'triplets':
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 2, 3, 6)}
    elif quant == 'triplet8':
        # the writer said eighth-note triplets: no binary escape hatch
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 3)}
    elif quant == 'triplet16':
        # sixteenth-note triplets: the whole swung-sextuplet family
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 3, 6)}
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

    n_units = (bar_hi - bar_lo + 1) * bar_ticks
    scale = DIV / beat                     # demo ticks -> chart ticks
    default_sub = {'quarters': 1, 'eighths': 2, 'triplet8': 3,
                   'triplet16': 6}.get(quant, 4)

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

        # The ending snaps to the grid of the beat it falls in, so a
        # duration inside a tuplet beat is always whole subdivisions —
        # EXCEPT that a sustained note's release is a cutoff the section
        # counts together: two-thirds of a beat or longer, ending in a
        # binary beat, releases on the eighth grid.
        x = off * scale
        ob = int(x // DIV)
        osub = grids.get(ob)               # None: no onsets in that beat
        if x - q_on >= 16 and (osub is None or osub in (1, 2, 4, 8)):
            # a sustained release in a beat nobody attacks in is a
            # cutoff, and cutoffs land on the eighth grid
            q_off = int(round(x / (DIV // 2))) * (DIV // 2)
        else:
            ostep = DIV / (osub or default_sub)
            q_off = int(round(ob * DIV + round((x - ob * DIV) / ostep)
                              * ostep))
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
                find.add(f"{part_label}: bar "
                         f"{at_bar + spoken_shift + q_on // bar_ticks} "
                         f"note moved {'up' if folded > p else 'down'} "
                         f"{abs(folded - p) // 12} octave(s) into range")
                p = folded
        events.setdefault(q_on, []).append((p, q_off, on))

    # A horn is one voice: when several played notes land on one slot,
    # the latest-played keeps it and earlier ones step back one free
    # subdivision — a note that exists in the playing should survive
    # quantization whenever there is room for it. A polyphonic
    # instrument (piano, guitar, vibes) keeps its chords instead.
    for q_on in sorted(events) if not poly else ():
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
                find.add(f"{part_label}: bar "
                         f"{at_bar + spoken_shift + q_on // bar_ticks}: "
                         "two played notes landed on one slot — moved "
                         "the earlier one back a step")
            else:
                find.add(f"{part_label}: bar "
                         f"{at_bar + spoken_shift + q_on // bar_ticks}: "
                         "two played notes landed on one slot with no "
                         "room — dropped the earlier one; proofread "
                         "this bar")

    # ---- monophonic cleanup and legato gap-closing
    timeline = _mono_tl(events, n_units)

    # The same phrase gets the same cutoff. A repeated sustained note at
    # the same bar position and pitch whose gates differed slightly in
    # the demo unifies to one canonical release — preferring a duration
    # that ends on the eighth grid, else the first pass.
    echo = {}
    for idx, (s, e, ps) in enumerate(timeline):
        if e - s >= DIV:
            echo.setdefault((s % bar_ticks, tuple(ps)), []).append(idx)
    for sig, idxs in echo.items():
        if len(idxs) < 2:
            continue
        durs = [timeline[i][1] - timeline[i][0] for i in idxs]
        if max(durs) == min(durs) or max(durs) - min(durs) > DIV:
            continue
        clean = [d for d in durs if d % (DIV // 2) == 0]
        target = clean[0] if clean else durs[0]
        for i in idxs:
            s, e, ps = timeline[i]
            nxt = timeline[i + 1][0] if i + 1 < len(timeline) else n_units
            timeline[i] = (s, min(s + target, nxt, n_units), ps)
        bars = sorted({at_bar + spoken_shift
                       + timeline[i][0] // bar_ticks for i in idxs})
        find.add(f"{part_label}: repeated phrase, one cutoff — bars "
                 + ", ".join(str(b) for b in bars))

    # `short` is the writer's word: the phrase's last note prints short,
    # whatever the demo's gate held
    if short and timeline:
        s, e, ps = timeline[-1]
        timeline[-1] = (s, min(e, s + DIV // 2), ps)

    # ---- polyphony: hands to staves, pedal tones to voices. The flat
    # timeline above stays as the range report's and the fallback's one
    # answer; when anything genuinely polyphonic is found, the page and
    # the prose read the voices instead.
    staves_out = None
    if poly:
        staff_events = {1: {k: list(v) for k, v in events.items()}}
        if grand:
            hands = convert.Hands(reach, comfortable, find)
            staff_events = {1: {}, 2: {}}
            prev_on = None
            holding = []                   # (end, pitch) still sounding —
            for q_on in sorted(events):    # a held note IS the hand's
                lst = events[q_on]         # position, so it anchors the
                holding = [(e, p) for e, p in holding if e > q_on]  # split
                bar_no = at_bar + spoken_shift + q_on // bar_ticks
                dt = ((q_on - prev_on) / DIV if prev_on is not None
                      else 1.0)
                prev_on = q_on
                lh, rh = hands.assign(
                    sorted({p for p, _, _ in lst}
                           | {p for _, p in holding}), bar_no, dt)
                for staff, members in ((1, rh), (2, lh)):
                    sel = [t for t in lst if t[0] in members]
                    if sel:
                        staff_events[staff][q_on] = sel
                        holding += [(e, p) for p, e, _ in sel]
        split = False
        staves_out = []
        for staff in sorted(staff_events):
            evts = staff_events[staff]
            ped = _pedals(evts, n_units)
            if ped:
                split = True
            voices = [_mono_tl(evts, n_units)]
            if ped:
                voices.append(ped)
            staves_out.append({'staff': staff, 'voices': voices})
        if not (split or grand):
            staves_out = None              # nothing polyphonic: flat path
        else:
            if short and staves_out[0]['voices'][0]:
                tl = staves_out[0]['voices'][0]
                s, e, ps = tl[-1]
                tl[-1] = (s, min(e, s + DIV // 2), ps)
            pbars = sorted({at_bar + spoken_shift + s // bar_ticks
                            for st in staves_out
                            for v in st['voices'][1:]
                            for s, _, _ in v})
            if pbars:
                find.add(f"{part_label}: held notes keep ringing under "
                         "the line and print as their own voice — bars "
                         + ", ".join(str(b) for b in pbars))

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
    active = {s // bar_ticks for s, _, _ in timeline}
    dyns, prev = [], None
    for bo in sorted(active):
        vs = sorted(by_bar.get(bo, []))
        if not vs:
            continue
        k = klass(vs[len(vs) // 2])
        if k != prev:
            dyns.append((bo * bar_ticks, k))
            prev = k
    if dyns:
        find.add(f"{part_label}: bars {bar_lo}-{bar_hi} dynamics read from "
                 "the expression pedal: "
                 + ", ".join(f"{k} at bar {at_bar + t // bar_ticks}"
                             for t, k in dyns))

    return {'timeline': timeline, 'grids': grids_chart,
            'n_units': n_units, 'at': at_bar,
            'bars': (bar_lo, bar_hi), 'dyns': dyns,
            'spoken_shift': spoken_shift, 'staves': staves_out,
            'bar_ticks': bar_ticks, 'pulse_div': pulse_div}


def bend_indices(res, bends):
    """Resolve scoop/plop placements ((kind, 'first'|'last'|(bar, beat)))
    to {timeline index: kind} — shared by the page and the prose."""
    tl = res['timeline']
    out = {}
    for kind, sp in bends or ():
        if sp == 'first':
            out[0] = kind
        elif sp == 'last':
            out[len(tl) - 1] = kind
        else:
            bar, beat = sp
            target = ((bar - res['bars'][0])
                      * res.get('bar_ticks', BAR)
                      + (beat - 1) * res.get('pulse_div', DIV))
            best = min(range(len(tl)), key=lambda i: abs(tl[i][0] - target))
            out[best] = kind
    return out


def render_range(res, fifths_written, transpose_to_written, fall,
                 findings=None, short=False, every=None, doit=False,
                 scoops=None):
    """Resolved timeline -> {abs_bar: MusicXML measure content}."""
    find = findings if findings is not None else Findings()
    at_bar = res['at']
    n_units = res['n_units']
    timeline = res['timeline']
    grids_chart = res['grids']
    table = spelling_table(fifths_written, find)
    last_artic = ('falloff' if fall else 'doit' if doit else
                  'staccato' if short else None)
    bends = bend_indices(res, scoops)

    bar_ticks = res.get('bar_ticks', BAR)
    SOUND_DYN = {'p': 54, 'mp': 71, 'mf': 89, 'f': 106, 'ff': 123}

    if res.get('staves'):
        # genuinely polyphonic: hands and held layers, each its own voice
        out = _render_voices(res, table, transpose_to_written, every,
                             last_artic)
        for t, k in res.get('dyns', []):
            bar = at_bar + t // bar_ticks
            if bar in out:
                out[bar] = (
                    '      <direction placement="below"><direction-type>'
                    f'<dynamics><{k}/></dynamics></direction-type>'
                    f'<sound dynamics="{SOUND_DYN[k]}"/></direction>\n'
                    + out[bar])
        return out

    out = {b: [] for b in
           range(at_bar, at_bar + (n_units // bar_ticks))}
    pos = 0
    for ti, (start, end, pitches) in enumerate(timeline):
        if start > pos:
            _emit(out, at_bar, pos, start, None, table, grids_chart,
                  None, transpose_to_written, bar=bar_ticks)
        is_last = ti == len(timeline) - 1
        _emit(out, at_bar, start, end, pitches, table, grids_chart,
              (last_artic if is_last else None) or every,
              transpose_to_written, bend=bends.get(ti), bar=bar_ticks)
        pos = end
    if pos < n_units:
        _emit(out, at_bar, pos, n_units, None, table, grids_chart,
              None, transpose_to_written, bar=bar_ticks)

    for t, k in res.get('dyns', []):
        bar = at_bar + t // bar_ticks
        if bar in out:
            out[bar].insert(
                0,
                '      <direction placement="below"><direction-type>'
                f'<dynamics><{k}/></dynamics></direction-type>'
                f'<sound dynamics="{SOUND_DYN[k]}"/></direction>\n')

    return {b: "".join(lines) for b, lines in out.items()}


def _render_voices(res, table, transpose, every, last_artic):
    """The polyphonic page: staff by staff, voice by voice, stitched per
    measure with backups. The first voice of a staff owns every figure
    bar (rests around its line); a held layer appears only in bars it
    actually rings, filled barline to barline so the arithmetic holds."""
    at_bar = res['at']
    n_units = res['n_units']
    bar_ticks = res['bar_ticks']
    grids = res['grids']
    staves = res['staves']
    nbars = n_units // bar_ticks
    two_staves = len(staves) > 1
    chunks = []                            # ({bar: [str]}, covered_bars)
    for st in staves:
        staff_no = st['staff'] if two_staves else 0
        base = 1 if st['staff'] == 1 else 5
        for vi, tl in enumerate(st['voices'] or [[]]):
            voice_no = base + vi
            outd = {b: [] for b in range(at_bar, at_bar + nbars)}
            if vi == 0:
                pos = 0
                for ti, (s, e, ps) in enumerate(tl):
                    if s > pos:
                        _emit(outd, at_bar, pos, s, None, table, grids,
                              None, transpose, bar=bar_ticks,
                              voice=voice_no, staff=staff_no)
                    is_last = ti == len(tl) - 1
                    _emit(outd, at_bar, s, e, ps, table, grids,
                          ((last_artic if is_last and st['staff'] == 1
                            else None) or every),
                          transpose, bar=bar_ticks,
                          voice=voice_no, staff=staff_no)
                    pos = e
                if pos < n_units:
                    _emit(outd, at_bar, pos, n_units, None, table, grids,
                          None, transpose, bar=bar_ticks,
                          voice=voice_no, staff=staff_no)
                covered = set(outd)
            else:
                covered = set()
                for s, e, _ in tl:
                    covered.update(range(at_bar + s // bar_ticks,
                                         at_bar + (e - 1) // bar_ticks + 1))
                regions = []
                for b in sorted(covered):
                    if regions and b == regions[-1][1]:
                        regions[-1][1] = b + 1
                    else:
                        regions.append([b, b + 1])
                idx = 0
                for rb, re_ in regions:
                    pos = (rb - at_bar) * bar_ticks
                    r1 = (re_ - at_bar) * bar_ticks
                    while idx < len(tl) and tl[idx][0] < r1:
                        s, e, ps = tl[idx]
                        if s > pos:
                            _emit(outd, at_bar, pos, s, None, table,
                                  grids, None, transpose, bar=bar_ticks,
                                  voice=voice_no, staff=staff_no)
                        _emit(outd, at_bar, s, e, ps, table, grids, None,
                              transpose, bar=bar_ticks,
                              voice=voice_no, staff=staff_no)
                        pos = e
                        idx += 1
                    if pos < r1:
                        _emit(outd, at_bar, pos, r1, None, table, grids,
                              None, transpose, bar=bar_ticks,
                              voice=voice_no, staff=staff_no)
            chunks.append((outd, covered))
    backup = f'      <backup><duration>{bar_ticks}</duration></backup>\n'
    out = {}
    for b in range(at_bar, at_bar + nbars):
        parts = ["".join(c[0][b]) for c in chunks
                 if b in c[1] and c[0].get(b)]
        out[b] = backup.join(p for p in parts if p)
    return out


def _is_tuplet(grids, b):
    sub = grids.get(b, 4)
    _, _, actual, normal, _ = tuplets.CANDIDATES[sub]
    return actual != normal


def _pieces(start, end, grids, bar=BAR):
    """Cut a span at barlines always, and at beat boundaries around any
    tuplet beat, so every piece lives in exactly one naming regime."""
    cuts = []
    pos = start
    while pos < end:
        b = pos // DIV
        next_beat = (b + 1) * DIV
        stop = min(end, (pos // bar + 1) * bar)
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


def _emit(out, at_bar, start, end, pitches, table, grids, artic, transpose,
          bend=None, bar=BAR, voice=1, staff=0):
    staff_xml = f'        <staff>{staff}</staff>\n' if staff else ''
    pieces = _pieces(start, end, grids, bar)
    for pi, (a, b) in enumerate(pieces):
        bar_no = at_bar + a // bar
        if bar_no not in out:
            continue
        first, last = pi == 0, pi == len(pieces) - 1
        sub = grids.get(a // DIV, 4)
        if pitches is None and a % bar == 0 and b - a == bar:
            out[bar_no].append(
                '      <note>\n        <rest measure="yes"/>\n'
                f'        <duration>{bar}</duration>\n'
                f'        <voice>{voice}</voice>\n'
                + staff_xml + '      </note>\n')
            continue
        parts = _name(b - a, sub)
        for qi, (plen, ptype, dots, mod) in enumerate(parts):
            plast = last and qi == len(parts) - 1
            pfirst = first and qi == 0
            if pitches is None:
                out[bar_no].append('      <note>\n        <rest/>\n'
                                f'        <duration>{plen}</duration>\n'
                                f'        <voice>{voice}</voice>\n'
                                f'        <type>{ptype}</type>\n'
                                + '        <dot/>\n' * dots
                                + (_mod_xml(mod) if mod else '')
                                + staff_xml
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
                lines.append(f'        <voice>{voice}</voice>')
                lines.append(f'        <type>{ptype}</type>')
                lines += ['        <dot/>'] * dots
                if alter:
                    lines.append(
                        f'        <accidental>{ACC_NAME[alter]}</accidental>')
                if mod:
                    lines.append(_mod_xml(mod).rstrip())
                if staff:
                    lines.append(f'        <staff>{staff}</staff>')
                notations = []
                if not pfirst:
                    notations.append('<tied type="stop"/>')
                if not plast:
                    notations.append('<tied type="start"/>')
                arts = []
                if bend and pfirst and ni == len(pitches) - 1:
                    arts.append(f'<{bend}/>')
                if artic and plast and ni == len(pitches) - 1:
                    arts.append(f'<{artic}/>')
                if arts:
                    notations.append('<articulations>' + ''.join(arts)
                                     + '</articulations>')
                if notations:
                    lines.append('        <notations>' + ''.join(notations)
                                 + '</notations>')
                lines.append('      </note>')
                out[bar_no].append("\n".join(lines) + "\n")


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


def _say_beat(pos, bar=BAR, pulse=DIV):
    beat = pos % bar / pulse + 1
    if beat == int(beat):
        return f"beat {int(beat)}"
    if (pos % pulse) % (pulse // 2 or 1) == 0:
        return f"the and of {int(beat)}"
    return f"inside beat {int(beat)}"


def _say_dur(ticks):
    if ticks in DUR_WORD:
        return DUR_WORD[ticks]
    pieces = decompose(ticks, DIV)
    if 1 <= len(pieces) <= 3:
        words = []
        for _, name, dots in pieces:
            words.append(("double-dotted " if dots == 2 else
                          "dotted " if dots == 1 else "") + name)
        return " tied to ".join(words)
    return f"about {ticks / DIV:.1f} beats"


def _say_tl(tl, table, at_bar, bar_ticks, pulse, bends,
            fall=False, doit=False, short=False):
    """One voice's timeline -> {abs_bar: [clauses]} — the run-grouping
    prose, shared by the flat path and each voice of a polyphonic part."""
    out = {}
    i = 0
    while i < len(tl):
        start, end, pitches = tl[i]
        dur = end - start
        j = i
        while (j + 1 < len(tl)
               and tl[j + 1][0] == tl[j][1]                 # gapless
               and tl[j + 1][1] - tl[j + 1][0] == dur       # same length
               and tl[j + 1][0] // bar_ticks
               == start // bar_ticks                        # same bar
               and len(tl[j + 1][2]) == 1 and len(pitches) == 1
               and j not in bends and (j + 1) not in bends):
            j += 1
        bar = at_bar + start // bar_ticks
        clauses = out.setdefault(bar, [])
        where = _say_beat(start, bar_ticks, pulse)
        if j > i:
            names = ", ".join(_say_pitch(t[2][0], table) for t in tl[i:j + 1])
            clauses.append(f"from {where}, {_say_dur(dur)}s: {names}")
        else:
            what = " and ".join(_say_pitch(p, table) for p in pitches)
            if len(pitches) > 1:
                what = "chord " + what
            held = ""
            if end // bar_ticks > start // bar_ticks and end % bar_ticks:
                held = f", held into bar {at_bar + end // bar_ticks}"
            clauses.append(f"{where}: {_say_dur(end - start)} {what}{held}")
        if i == j and i in bends:
            clauses[-1] += (", scooped" if bends[i] == 'scoop'
                            else ", plopped into")
        if j == len(tl) - 1:
            if fall:
                clauses[-1] += ", with a big fall off the end"
            elif doit:
                clauses[-1] += ", with a doit up off the end"
            elif short:
                clauses[-1] += ", short"
        i = j + 1
    return out


def say_range(res, concert_fifths, fall=False, findings=None, short=False,
              doit=False, scoops=None):
    """Resolved timeline -> {abs_bar: prose}, spoken at concert pitch."""
    find = findings if findings is not None else Findings()
    table = spelling_table(concert_fifths, find)
    at_bar = res['at'] + res.get('spoken_shift', 0)
    bar_ticks = res.get('bar_ticks', BAR)
    pulse = res.get('pulse_div', DIV)
    bends = bend_indices(res, scoops)

    if res.get('staves'):
        # polyphonic prose: each voice speaks, labelled, in page order
        two = len(res['staves']) > 1
        ordered = []
        for st in res['staves']:
            for vi, tl in enumerate(st['voices'] or [[]]):
                if not tl:
                    continue
                hand = ('right hand' if st['staff'] == 1 else
                        'left hand') if two else ''
                label = (hand + (', held underneath' if vi else '')
                         if two else ('held underneath' if vi else ''))
                first = st['staff'] == 1 and vi == 0
                ordered.append((label, _say_tl(
                    tl, table, at_bar, bar_ticks, pulse,
                    bends if first else {},
                    fall and first, doit and first, short and first)))
        out = {}
        for label, by_bar in ordered:
            for bar, clauses in by_bar.items():
                body = "; ".join(clauses)
                seg = (label[0].upper() + label[1:] + ": " + body
                       if label else body)
                out.setdefault(bar, []).append(seg)
        DYN_WORD = {'p': 'piano', 'mp': 'mezzo piano',
                    'mf': 'mezzo forte', 'f': 'forte', 'ff': 'fortissimo'}
        for t, k in res.get('dyns', []):
            bar = at_bar + t // bar_ticks
            if bar in out:
                out[bar].insert(0, DYN_WORD[k])
        return {b: ". ".join(segs) + "." for b, segs in out.items()}

    out = _say_tl(res['timeline'], table, at_bar, bar_ticks, pulse,
                  bends, fall, doit, short)
    DYN_WORD = {'p': 'piano', 'mp': 'mezzo piano', 'mf': 'mezzo forte',
                'f': 'forte', 'ff': 'fortissimo'}
    for t, k in res.get('dyns', []):
        bar = at_bar + t // bar_ticks
        if bar in out:
            out[bar].insert(0, DYN_WORD[k])
    return {b: "; ".join(cl) + "." for b, cl in out.items()}
