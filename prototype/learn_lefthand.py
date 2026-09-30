#!/usr/bin/env python3
"""How a soloing pianist's left hand comps, measured: reads the piano
MIDI of the Jazz Trio Database v0.2 (Cheston et al., MIT — piano
solos in trio, transcribed) against its beat grid and writes
data/lefthand_stats.json: how many left-hand chords a bar, where in
the bar they fall, how many notes each, and where the hand sits.

The left hand is taken as the notes under middle C, struck together
(within 40 ms). Only the derived numbers ship.

    learn_lefthand.py [jazz-trio-database-v02 dir]
"""
import bisect
import collections
import csv
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze  # noqa: E402

DEFAULT = ("/Volumes/VST's/Copyist Training Data/jtd/"
           "jazz-trio-database-v02")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data',
                   'lefthand_stats.json')


def onsets(path):
    """-> [(seconds, pitch)] note-ons, through the file's tempo map."""
    m = analyze.parse_midi(path)
    div = m['division']
    tempo = [(0, 500000)]
    # analyze.parse_midi stores absolute ticks
    for tr in m['tracks']:
        for ev in tr:
            if ev[1] == 'meta' and ev[2] == 81:
                tempo.append((ev[0], int.from_bytes(ev[3], 'big')))
    tempo.sort()

    def sec(tick):
        s, last_t, us = 0.0, 0, 500000
        for tt, u in tempo:
            if tt > tick:
                break
            s += (tt - last_t) / div * us / 1e6
            last_t, us = tt, u
        return s + (tick - last_t) / div * us / 1e6
    out = []
    for tr in m['tracks']:
        for ev in tr:
            if ev[1] == 'chan' and ev[2] & 0xF0 == 0x90 and ev[5] > 0:
                out.append((sec(ev[0]), ev[4]))
    return sorted(out)


def main(src):
    per_bar = []
    where = collections.Counter()
    size = collections.Counter()
    low, top = [], []
    span = collections.Counter()
    n_tracks = 0
    for d in sorted(os.listdir(src)):
        p = os.path.join(src, d)
        mid = os.path.join(p, 'piano_midi.mid')
        if not os.path.isfile(mid):
            continue
        beats, metre = [], []
        with open(os.path.join(p, 'beats.csv')) as f:
            for row in csv.DictReader(f):
                try:
                    beats.append(float(row['beats']))
                    metre.append(int(float(row['metre_auto'])))
                except (ValueError, KeyError):
                    pass
        if len(beats) < 32 or set(metre) - {1, 2, 3, 4}:
            continue
        try:
            ons = onsets(mid)
        except (ValueError, IndexError):
            continue
        lh = [(t, p_) for t, p_ in ons if 33 <= p_ < 60]
        # chords: notes within 40 ms
        events = []
        for t, p_ in lh:
            if events and t - events[-1][0] < 0.04:
                events[-1][1].append(p_)
            else:
                events.append([t, [p_]])
        if len(events) < 16:
            continue
        n_tracks += 1
        bars = collections.Counter()
        for t, ps in events:
            i = bisect.bisect_right(beats, t) - 1
            if i < 0 or i + 1 >= len(beats):
                continue
            frac = (t - beats[i]) / (beats[i + 1] - beats[i])
            b = metre[i]
            # the bar this beat belongs to: count back to its beat 1
            bar_id = i - (b - 1)
            bars[bar_id] += 1
            half = 'and' if 0.45 <= frac < 0.9 else 'on'
            if frac >= 0.9:
                b = b % 4 + 1
                half = 'on'
            where[f'{b}{"&" if half == "and" else ""}'] += 1
            size[min(len(ps), 5)] += 1
            low.append(min(ps))
            top.append(max(ps))
            span[min(24, max(ps) - min(ps))] += 1
        nb = max(bars) - min(bars) + 1 if bars else 1
        per_bar.append(sum(bars.values()) / max(nb, 1))

    def norm(c):
        t = sum(c.values()) or 1
        return {str(k): round(v / t, 4) for k, v in c.most_common()}
    stats = {
        'source': 'Jazz Trio Database v0.2 piano MIDI (Cheston et al.), '
                  f'MIT, {n_tracks} recordings',
        'chords_per_bar_median': round(statistics.median(per_bar), 3),
        'chords_per_bar_quartiles': [round(x, 3) for x in
                                     statistics.quantiles(per_bar, n=4)],
        'position': norm(where),
        'notes': norm(size),
        'lowest_note_median': statistics.median(low),
        'top_note_median': statistics.median(top),
        'span': norm(span),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(stats, f, indent=1)
    return stats


if __name__ == '__main__':
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT),
                     indent=1))
