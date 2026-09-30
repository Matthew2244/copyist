#!/usr/bin/env python3
"""How real trios feel time, measured: reads the Jazz Trio Database
v0.2 (Huw Cheston et al., University of Cambridge, MIT licence —
detected onsets and beats for piano, bass and drums across hundreds of
piano-trio recordings) and writes data/timing_stats.json: the swing
ratio each player uses against tempo (it narrows as the tempo climbs)
and where each player sits against the band's beat (the drummer's
ride, the bassist's walk, the pianist's comping).

Only the derived numbers ship.

    learn_timing.py [jazz-trio-database-v02 dir]
"""
import csv
import json
import math
import os
import statistics
import sys

DEFAULT = ("/Volumes/VST's/Copyist Training Data/jtd/"
           "jazz-trio-database-v02")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data',
                   'timing_stats.json')
PLAYERS = ('piano', 'bass', 'drums')


def floats(path):
    out = []
    with open(path) as f:
        for row in csv.reader(f):
            try:
                out.append(float(row[-1]))
            except (ValueError, IndexError):
                pass
    return sorted(out)


def main(src):
    tracks = []
    for d in sorted(os.listdir(src)):
        p = os.path.join(src, d)
        if not os.path.isfile(os.path.join(p, 'beats.csv')):
            continue
        beats, near = [], {k: [] for k in PLAYERS}
        with open(os.path.join(p, 'beats.csv')) as f:
            for row in csv.DictReader(f):
                try:
                    b = float(row['beats'])
                except (ValueError, KeyError):
                    continue
                beats.append(b)
                for k in PLAYERS:
                    try:
                        near[k].append(float(row[k]) - b)
                    except (ValueError, KeyError):
                        pass
        if len(beats) < 32:
            continue
        ibi = statistics.median(b - a for a, b in zip(beats, beats[1:]))
        bpm = 60.0 / ibi
        row = {'bpm': bpm}
        for k in PLAYERS:
            if len(near[k]) > 16:
                row[f'{k}_ms'] = 1000 * statistics.median(near[k])
            ons = floats(os.path.join(p, f'{k}_onsets.csv'))
            # the swung eighth: an onset between two beats, past the
            # middle, read as long:short
            rs, j = [], 0
            for a, b in zip(beats, beats[1:]):
                span = b - a
                while j < len(ons) and ons[j] <= a + 0.05 * span:
                    j += 1
                k2 = j
                while k2 < len(ons) and ons[k2] < b - 0.05 * span:
                    f_ = (ons[k2] - a) / span
                    if 0.5 <= f_ <= 0.82:
                        rs.append(f_ / (1 - f_))
                    k2 += 1
            if len(rs) > 20:
                row[f'{k}_ratio'] = statistics.median(rs)
        tracks.append(row)

    def fit(key):
        """log(ratio) = a + b * bpm, least squares."""
        pts = [(t['bpm'], math.log(t[key])) for t in tracks if key in t]
        n = len(pts)
        mx = sum(x for x, _ in pts) / n
        my = sum(y for _, y in pts) / n
        b = sum((x - mx) * (y - my) for x, y in pts) / \
            sum((x - mx) ** 2 for x, _ in pts)
        return {'a': round(my - b * mx, 5), 'b': round(b, 7), 'n': n}

    def band(lo, hi, key):
        xs = [t[key] for t in tracks if key in t and lo <= t['bpm'] < hi]
        return round(statistics.median(xs), 3) if len(xs) > 3 else None
    stats = {
        'source': 'Jazz Trio Database v0.2 (Cheston et al.), MIT, '
                  f'{len(tracks)} recordings',
        'ratio_fit': {k: fit(f'{k}_ratio') for k in PLAYERS},
        'ratio_by_tempo': {f'{lo}-{hi}': {k: band(lo, hi, f'{k}_ratio')
                                          for k in PLAYERS}
                           for lo, hi in ((0, 120), (120, 160), (160, 200),
                                          (200, 240), (240, 400))},
        'offset_ms_median': {k: round(statistics.median(
            t[f'{k}_ms'] for t in tracks if f'{k}_ms' in t), 2)
            for k in PLAYERS},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(stats, f, indent=1)
    return stats


if __name__ == '__main__':
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT),
                     indent=1))
