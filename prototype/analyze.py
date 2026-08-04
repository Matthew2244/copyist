#!/usr/bin/env python3
"""
Copyist — analyze pass prototype.

Reads a Standard MIDI File and reports what it finds, in the shape described in
DESIGN.md section 13. No dependencies: the SMF parser is self-contained so this
runs on any stock Python 3.

Usage:  python3 analyze.py FILE.mid
"""

import sys
import math
import random
from collections import defaultdict

# ---------------------------------------------------------------- SMF parsing

class Reader:
    def __init__(self, data):
        self.d = data
        self.i = 0

    def u8(self):
        v = self.d[self.i]
        self.i += 1
        return v

    def u16(self):
        v = int.from_bytes(self.d[self.i:self.i + 2], "big")
        self.i += 2
        return v

    def u32(self):
        v = int.from_bytes(self.d[self.i:self.i + 4], "big")
        self.i += 4
        return v

    def raw(self, n):
        v = self.d[self.i:self.i + n]
        self.i += n
        return v

    def vlq(self):
        """Variable-length quantity."""
        v = 0
        while True:
            b = self.u8()
            v = (v << 7) | (b & 0x7F)
            if not b & 0x80:
                return v


def parse_midi(path):
    data = open(path, "rb").read()
    r = Reader(data)

    if r.raw(4) != b"MThd":
        raise ValueError("not a Standard MIDI File (no MThd)")
    hdr_len = r.u32()
    fmt = r.u16()
    ntrks = r.u16()
    division = r.u16()
    r.raw(hdr_len - 6)  # tolerate oversized headers

    if division & 0x8000:
        raise ValueError("SMPTE time division not supported by this prototype")

    tracks = []
    for _ in range(ntrks):
        chunk_id = r.raw(4)
        length = r.u32()
        if chunk_id != b"MTrk":
            r.raw(length)
            continue
        tracks.append(parse_track(Reader(r.raw(length))))

    return {"format": fmt, "division": division, "tracks": tracks}


def parse_track(r):
    events = []
    t = 0
    status = None
    while r.i < len(r.d):
        t += r.vlq()
        b = r.d[r.i]
        if b & 0x80:
            status = r.u8()
        # else: running status, reuse previous

        if status == 0xFF:                       # meta
            typ = r.u8()
            length = r.vlq()
            payload = r.raw(length)
            events.append((t, "meta", typ, payload))
        elif status in (0xF0, 0xF7):             # sysex
            length = r.vlq()
            r.raw(length)
        else:
            kind = status & 0xF0
            chan = status & 0x0F
            if kind in (0xC0, 0xD0):
                events.append((t, "chan", kind, chan, r.u8(), 0))
            else:
                d1 = r.u8()
                d2 = r.u8()
                events.append((t, "chan", kind, chan, d1, d2))
    return events


# ---------------------------------------------------------------- extraction

class Note:
    __slots__ = ("pitch", "on", "off", "vel", "chan", "track")

    def __init__(self, pitch, on, vel, chan, track):
        self.pitch, self.on, self.vel = pitch, on, vel
        self.chan, self.track = chan, track
        self.off = None

    @property
    def dur(self):
        return (self.off or self.on) - self.on


def extract(mid):
    notes, tempos, timesigs, keysigs, markers = [], [], [], [], []
    names = {}
    programs = defaultdict(set)
    cc64 = 0

    for ti, ev in enumerate(mid["tracks"]):
        pending = defaultdict(list)
        for e in ev:
            t = e[0]
            if e[1] == "meta":
                typ, payload = e[2], e[3]
                if typ == 0x03 and ti not in names:
                    names[ti] = payload.decode("latin-1", "replace").strip()
                elif typ == 0x06:
                    markers.append((t, payload.decode("latin-1", "replace").strip()))
                elif typ == 0x51 and len(payload) == 3:
                    tempos.append((t, int.from_bytes(payload, "big")))
                elif typ == 0x58 and len(payload) >= 2:
                    timesigs.append((t, payload[0], 2 ** payload[1]))
                elif typ == 0x59 and len(payload) >= 2:
                    keysigs.append((t, int.from_bytes(payload[:1], "big", signed=True),
                                    payload[1]))
            else:
                kind, chan, d1, d2 = e[2], e[3], e[4], e[5]
                if kind == 0x90 and d2 > 0:
                    pending[(chan, d1)].append(Note(d1, t, d2, chan, ti))
                elif kind == 0x80 or (kind == 0x90 and d2 == 0):
                    q = pending.get((chan, d1))
                    if q:
                        n = q.pop(0)
                        n.off = t
                        notes.append(n)
                elif kind == 0xC0:
                    programs[ti].add(d1)
                elif kind == 0xB0 and d1 == 64 and d2 >= 64:
                    cc64 += 1
        for q in pending.values():               # unterminated notes
            for n in q:
                n.off = n.on
                notes.append(n)

    notes.sort(key=lambda n: (n.on, n.pitch))
    return dict(notes=notes, tempos=tempos, timesigs=timesigs, keysigs=keysigs,
                markers=markers, names=names, programs=programs, cc64=cc64)


# ---------------------------------------------------------------- analysis

GRIDS = [("whole", 4.0), ("half", 2.0), ("quarter", 1.0), ("8th", 0.5),
         ("8th triplet", 1 / 3), ("16th", 0.25), ("16th triplet", 1 / 6),
         ("32nd", 0.125)]


def residuals(beats, grid):
    out = []
    for b in beats:
        nearest = round(b / grid) * grid
        out.append(b - nearest)
    return out


def classify_timing(notes, division, bpm):
    """Return (grid_name, stats dict) for the finest grid that explains onsets."""
    beats = [n.on / division for n in notes]
    if len(beats) < 8:
        return None, {}

    best = None
    for name, g in GRIDS:
        res = residuals(beats, g)
        ms = [abs(r) * 60000.0 / bpm for r in res]
        ms.sort()
        p95 = ms[int(len(ms) * 0.95)]
        # A grid "explains" the data if 95% of onsets sit well inside it.
        if p95 < (g * 60000.0 / bpm) * 0.25:
            best = (name, g, res)
            break

    if best is None:
        name, g = "finer than 32nd", 0.125
        res = residuals(beats, g)
        best = (name, g, res)

    name, g, res = best
    ms = [r * 60000.0 / bpm for r in res]
    n = len(ms)
    mean = sum(ms) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in ms) / n)
    peak = max(abs(x) for x in ms)
    exact = sum(1 for x in ms if abs(x) < 0.5) / n

    # Lag-1 autocorrelation: ~0 means independent noise, positive means drift.
    #
    # Order matters, and the obvious ordering is wrong. Sorting notes by their
    # ACTUAL time sorts them partly by the very jitter being measured — inside
    # a chord that produces a monotone run of residuals and a spuriously high
    # correlation. Order by INTENDED grid position instead, with pitch breaking
    # ties, so the sequence order cannot depend on the jitter.
    seq = [r for _, _, r in
           sorted(((round(b / g), p.pitch, dev)
                   for b, p, dev in zip(beats, notes, ms)),
                  key=lambda t: (t[0], t[1]))]
    if sd > 1e-9 and n > 2:
        num = sum((seq[i] - mean) * (seq[i - 1] - mean) for i in range(1, n))
        r1 = num / ((n - 1) * sd * sd)
    else:
        r1 = 0.0

    # Shape: 1.0 is uniform, ~0.64 is gaussian. Both are synthetic-looking;
    # this only tells us which generator, not whether it is synthetic.
    shape = sd / (peak / math.sqrt(3)) if peak > 0 else 0.0

    # The real discriminator: does deviation depend on METRICAL POSITION?
    # A human is systematically early on downbeats and late on weak beats.
    # A randomizer treats every slot in the bar identically.
    #
    # The raw statistic is NOT comparable across files — its distribution
    # depends on note count and how onsets fall across slots. So calibrate it
    # against the null hypothesis by simulation: take this file's own grid
    # positions, jitter them with this file's own sd, and see what structure
    # pure noise produces. The answer is a percentile, not a magic number.
    structure = _structure(beats, ms, g, sd)
    pct = _null_percentile(beats, g, sd, structure, bpm)

    return name, dict(mean=mean, sd=sd, peak=peak, exact=exact, r1=r1,
                      shape=shape, structure=structure, pct=pct, n=n)


def _structure(beats, ms, g, sd, per_bar=4.0):
    slots = defaultdict(list)
    for b, dev in zip(beats, ms):
        slots[round((b % per_bar) / g)].append(dev)
    usable = [v for v in slots.values() if len(v) >= 3]
    if len(usable) < 3 or sd <= 1e-9:
        return 0.0
    means = [sum(v) / len(v) for v in usable]
    gm = sum(means) / len(means)
    between = sum((m - gm) ** 2 for m in means) / (len(means) - 1)
    avg = sum(len(v) for v in usable) / len(usable)
    return between / (sd * sd / avg)


def _null_percentile(beats, g, sd, observed, bpm, trials=300):
    """What fraction of pure-noise runs score BELOW the observed value?"""
    if sd <= 1e-9:
        return 0.0
    rng = random.Random(20260803)
    grid_beats = [round(b / g) * g for b in beats]
    below = 0
    for _ in range(trials):
        jitter = [rng.gauss(0, sd) for _ in grid_beats]
        fake_beats = [gb + j * bpm / 60000.0 for gb, j in zip(grid_beats, jitter)]
        if _structure(fake_beats, jitter, g, sd) < observed:
            below += 1
    return below / trials * 100.0


def classify_lengths(notes, division, bpm):
    """Are note durations on the grid, or randomized?"""
    durs = [n.dur / division for n in notes if n.dur > 0]
    if not durs:
        return {}
    res = residuals(durs, 0.25)                  # against a 16th
    ms = [abs(r) * 60000.0 / bpm for r in res]
    exact = sum(1 for x in ms if x < 0.5) / len(ms)
    ms.sort()
    return dict(exact=exact, median=ms[len(ms) // 2], p95=ms[int(len(ms) * 0.95)],
                n=len(durs))


KRUMHANSL_MAJ = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KRUMHANSL_MIN = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
PC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def estimate_key(notes):
    w = [0.0] * 12
    for n in notes:
        w[n.pitch % 12] += max(n.dur, 1)
    total = sum(w) or 1
    w = [x / total for x in w]

    def corr(profile, rot):
        p = profile[-rot:] + profile[:-rot] if rot else profile[:]
        mp, mw = sum(p) / 12, sum(w) / 12
        num = sum((p[i] - mp) * (w[i] - mw) for i in range(12))
        den = math.sqrt(sum((p[i] - mp) ** 2 for i in range(12)) *
                        sum((w[i] - mw) ** 2 for i in range(12)))
        return num / den if den else 0

    scores = []
    for r in range(12):
        scores.append((corr(KRUMHANSL_MAJ, r), f"{PC[r]} major"))
        scores.append((corr(KRUMHANSL_MIN, r), f"{PC[r]} minor"))
    scores.sort(reverse=True)
    top = scores[:2]
    span = sum(max(s, 0) for s, _ in top) or 1
    return [(name, max(s, 0) / span) for s, name in top]


def texture(notes):
    """Max simultaneity and widest simultaneous interval."""
    events = []
    for n in notes:
        events.append((n.on, 1, n.pitch))
        events.append((max(n.off, n.on + 1), -1, n.pitch))
    events.sort(key=lambda e: (e[0], e[1]))
    live, maxsim, widest = set(), 0, 0
    for _, delta, pitch in events:
        if delta > 0:
            live.add(pitch)
            maxsim = max(maxsim, len(live))
            if len(live) > 1:
                widest = max(widest, max(live) - min(live))
        else:
            live.discard(pitch)
    return maxsim, widest


INTERVALS = {0: "unison", 1: "minor 2nd", 2: "major 2nd", 3: "minor 3rd",
             4: "major 3rd", 5: "perfect 4th", 6: "tritone", 7: "perfect 5th",
             8: "minor 6th", 9: "major 6th", 10: "minor 7th", 11: "major 7th",
             12: "octave", 13: "minor 9th", 14: "major 9th", 15: "minor 10th",
             16: "major 10th", 17: "11th", 18: "augmented 11th", 19: "12th"}


def name_interval(semitones):
    return INTERVALS.get(semitones, f"{semitones} semitones")


# ---------------------------------------------------------------- report

def bar_beat(tick, division, ts_num, ts_den):
    beats = tick / division
    per_bar = ts_num * (4.0 / ts_den)
    return int(beats // per_bar) + 1, beats % per_bar + 1


def main(path):
    mid = parse_midi(path)
    x = extract(mid)
    div = mid["division"]
    notes = x["notes"]

    if not notes:
        print("No notes found.")
        return

    bpm = 60_000_000 / x["tempos"][0][1] if x["tempos"] else 120.0
    ts_num, ts_den = (x["timesigs"][0][1], x["timesigs"][0][2]) if x["timesigs"] else (4, 4)

    print(f"\nCOPYIST ANALYZE — {path}\n" + "=" * 60)

    print("\nFILE")
    print(f"  Format {mid['format']}, {len(mid['tracks'])} tracks, "
          f"{div} ticks per quarter note")
    print(f"  {len(notes)} notes")

    print("\nTEMPO")
    if not x["tempos"]:
        print("  No tempo event. Assuming 120 BPM.")
    elif len(x["tempos"]) == 1:
        print(f"  {bpm:.2f} BPM, constant")
    else:
        vals = sorted({round(60_000_000 / t[1], 2) for t in x["tempos"]})
        print(f"  {len(x['tempos'])} tempo events, {min(vals)}–{max(vals)} BPM")
        print("  Variable tempo — free-tempo path may be required (DESIGN 7.6)")

    print("\nMETER")
    if not x["timesigs"]:
        print("  No time signature event. Assuming 4/4.")
    else:
        for t, num, den in x["timesigs"]:
            print(f"  {num}/{den} from tick {t}")

    print("\nKEY SIGNATURE")
    if x["keysigs"]:
        for t, sf, mi in x["keysigs"]:
            acc = f"{abs(sf)} {'sharps' if sf > 0 else 'flats'}" if sf else "no accidentals"
            print(f"  {acc}, {'minor' if mi else 'major'} (from the file)")
    else:
        print("  Absent — will be inferred")
    for name, conf in estimate_key(notes):
        print(f"  Estimated: {name} ({conf * 100:.0f}%)")

    print("\nTRACKS")
    for ti in range(len(mid["tracks"])):
        tn = [n for n in notes if n.track == ti]
        if not tn and ti not in x["names"]:
            continue
        nm = x["names"].get(ti, "(unnamed)")
        progs = ", ".join(str(p) for p in sorted(x["programs"].get(ti, []))) or "none"
        chans = sorted({n.chan for n in tn})
        drums = " [channel 10 — drums]" if 9 in chans else ""
        print(f"  {ti}: {nm} — {len(tn)} notes, GM program {progs}{drums}")
        if tn:
            lo, hi = min(n.pitch for n in tn), max(n.pitch for n in tn)
            sim, wide = texture(tn)
            print(f"      range {PC[lo % 12]}{lo // 12 - 1}–{PC[hi % 12]}{hi // 12 - 1}, "
                  f"up to {sim} notes at once, widest {name_interval(wide)}")

    print("\nMARKERS")
    if x["markers"]:
        for t, text in x["markers"]:
            b, be = bar_beat(t, div, ts_num, ts_den)
            print(f"  bar {b} beat {be:.2f}: {text}")
    else:
        print("  None. In REAPER, project markers survive MIDI export — "
              "regions and take markers do not.")

    print("\nTIMING")
    grid, st = classify_timing(notes, div, bpm)
    if not st:
        print("  Too few notes to classify.")
    else:
        print(f"  Effective grid: {grid}")
        print(f"  Onset deviation: mean {st['mean']:+.1f} ms, "
              f"sd {st['sd']:.1f} ms, peak {st['peak']:.1f} ms")
        print(f"  Exactly on grid: {st['exact'] * 100:.1f}% of notes")
        print(f"  Lag-1 autocorrelation: {st['r1']:+.3f}  (0 = independent)")
        print(f"  Metrical structure:    {st['structure']:.2f}, at the "
              f"{st['pct']:.0f}th percentile of pure noise")
        shape = ("uniform" if st["shape"] > 0.85 else
                 "gaussian" if st["shape"] > 0.5 else "peaked")
        print(f"  Deviation shape:       {shape} ({st['shape']:.2f})")

        if st["exact"] > 0.95 or st["peak"] < 1.0:
            verdict = "HARD QUANTIZED — grid is exact, quantization is free"
        elif abs(st["r1"]) < 0.20 and st["pct"] < 95:
            verdict = (f"QUANTIZED THEN HUMANIZED — {shape} noise, independent, "
                       "identical at every\n    metrical position. Grid is exact; "
                       "undo the offsets and skip the cost\n    model (DESIGN 7.5)")
        elif st["r1"] > 0.25 or st["pct"] >= 95:
            verdict = ("LIVE PLAYING — deviation depends on where you are in the "
                       "bar, so there is\n    real timing intent. Run the full "
                       "beat-scoring quantizer (DESIGN 7.2)")
        else:
            verdict = "AMBIGUOUS — inconclusive between humanize and live playing"
        print(f"  Verdict: {verdict}")

    print("\nNOTE LENGTHS")
    ln = classify_lengths(notes, div, bpm)
    if ln:
        print(f"  Exactly on a 16th: {ln['exact'] * 100:.1f}%")
        print(f"  Deviation: median {ln['median']:.1f} ms, p95 {ln['p95']:.1f} ms")
        if ln["exact"] > 0.9:
            print("  Lengths are quantized. No phantom-rest risk.")
        elif ln["p95"] > 25:
            print("  Lengths are NOT quantized. This is the phantom-rest source:")
            print("  gate time becomes articulation, never rests (DESIGN 7.3).")
        else:
            print("  Lengths are close to the grid but not exact.")

    print("\nVELOCITY")
    v = sorted(n.vel for n in notes)
    distinct = len(set(v))
    print(f"  Range {v[0]}–{v[-1]}, median {v[len(v) // 2]}, {distinct} distinct values")
    if distinct <= 2:
        print("  Flat velocity — no dynamics can be derived.")
    else:
        print("  Usable for dynamics and accents (DESIGN pipeline step 10).")

    print("\nPEDAL")
    print(f"  {x['cc64']} sustain depressions"
          + ("" if x["cc64"] else " — no pedal data"))

    print("\nHAND SPAN EVIDENCE")
    sim, wide = texture(notes)
    print(f"  Up to {sim} notes sounding at once")
    print(f"  Widest simultaneous interval: {name_interval(wide)}")
    print("  (Compare against the profile reach — DESIGN 8.3)")
    print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
