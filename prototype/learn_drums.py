#!/usr/bin/env python3
"""How real drummers keep swing time, measured: reads the jazz swing
grooves and fills of the Groove MIDI Dataset (Gillick et al., Google
Magenta, CC BY 4.0 — human drummers on an electronic kit; in Matthew's
MIDI library) and writes data/drum_stats.json: the ride patterns they
really play and how often, where the snare comps and how hard, the
kick, the hi-hat foot, and what a fill is made of.

Every onset is read on the swing grid — each beat's three triplet
partials; a swung 'and' is the third. Only the derived numbers ship.

    learn_drums.py [Groove directory]
"""
import collections
import csv
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze  # noqa: E402

DEFAULT = os.path.expanduser('~/Music/MIDI Collections/'
                             'Groove - Drum Performances')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data',
                   'drum_stats.json')
SWING = {'jazz', 'jazz/swing', 'jazz/mediumfast', 'jazz/fast'}
KIT = {36: 'kick', 38: 'snare', 40: 'snare', 37: 'xstick',
       42: 'hat', 22: 'hat', 46: 'hat_open', 26: 'hat_open',
       44: 'hat_foot', 51: 'ride', 59: 'ride', 53: 'bell',
       49: 'crash', 55: 'crash', 57: 'crash', 52: 'crash',
       48: 'tom_hi', 50: 'tom_hi', 45: 'tom_mid', 47: 'tom_mid',
       43: 'tom_floor', 58: 'tom_floor'}


def hits(path):
    """-> [(beat, kit piece, velocity)], beats from the file's start."""
    m = analyze.parse_midi(path)
    div = m['division']
    out = []
    for tr in m['tracks']:
        for ev in tr:
            if ev[1] == 'chan' and ev[2] & 0xF0 == 0x90 and ev[5] > 0:
                k = KIT.get(ev[4])
                if k:
                    out.append((ev[0] / div, k, ev[5]))
    return sorted(out)


def slot(beat_frac):
    """0, 1, 2: on the beat, the middle triplet, the swung 'and'; 3 is
    'rounds up into the next beat'."""
    f = beat_frac
    if f < 0.17:
        return 0
    if f < 0.45:
        return 1
    if f < 0.88:
        return 2
    return 3


def main(src):
    rows = [r for r in csv.DictReader(open(os.path.join(src, 'info.csv')))
            if r['style'] in SWING and r['time_signature'] == '4-4']
    ride_pat = collections.Counter()
    snare_n = collections.Counter()
    snare_slot = collections.Counter()
    snare_vel = []
    kick_n = collections.Counter()
    kick_slot = collections.Counter()
    kick_vel = []
    foot = collections.Counter()
    fill_mix = collections.Counter()
    fill_grid = collections.Counter()
    fill_beats = []
    skip_frac = []
    grooves = fills = 0
    for r in rows:
        path = os.path.join(src, r['midi_filename'])
        if not os.path.isfile(path):
            continue
        hs = hits(path)
        if not hs:
            continue
        if r['beat_type'] == 'fill':
            # a fill file is a bar or two of time, then the fill: take
            # the notes off the ride/hat as the fill itself
            fills += 1
            fn = [h for h in hs if h[1] in ('snare', 'tom_hi', 'tom_mid',
                                            'tom_floor', 'kick')]
            if fn:
                fill_beats.append(fn[-1][0] - fn[0][0])
            for b, k, v in fn:
                fill_mix[k] += 1
                f = b % 1
                fill_grid['triplet' if abs(f * 3 - round(f * 3)) < 0.08
                          and abs(f * 2 - round(f * 2)) > 0.1 else
                          '16th' if abs(f * 4 - round(f * 4)) < 0.06
                          and abs(f * 2 - round(f * 2)) > 0.1 else
                          '8th' if abs(f - 0.5) < 0.08 else 'beat'
                          if f < 0.06 or f > 0.94 else 'other'] += 1
            continue
        grooves += 1
        nbars = int(hs[-1][0] // 4)
        bars = collections.defaultdict(lambda: collections.defaultdict(list))
        for b, k, v in hs:
            bi = int(b // 4)
            beat = int(b % 4)
            s = slot(b % 1)
            if s == 3:
                beat, s = beat + 1, 0
                if beat == 4:
                    bi, beat = bi + 1, 0
            bars[bi][k].append((beat * 3 + s, v))
            if k in ('ride', 'bell') and 0.5 <= b % 1 <= 0.85:
                skip_frac.append(b % 1)
        for bi in range(1, nbars):              # skip the count-in bar
            bar = bars.get(bi)
            if not bar:
                continue
            rd = sorted({x for x, _v in bar['ride'] + bar['bell']})
            if len(rd) >= 3:
                ride_pat[tuple(rd)] += 1
            sn = bar['snare'] + bar['xstick']
            snare_n[min(len(sn), 8)] += 1
            for x, v in sn:
                snare_slot[x] += 1
                snare_vel.append(v)
            kk = bar['kick']
            kick_n[min(len(kk), 8)] += 1
            for x, v in kk:
                kick_slot[x] += 1
                kick_vel.append(v)
            for x, _v in bar['hat_foot']:
                foot[x] += 1

    def norm(c, top=None):
        t = sum(c.values()) or 1
        return {str(k): round(v / t, 4) for k, v in c.most_common(top)}
    names = ['1', '1t', '1&', '2', '2t', '2&', '3', '3t', '3&', '4', '4t',
             '4&']

    def spell(pat):
        return ' '.join(names[x] for x in pat)
    tot = sum(ride_pat.values())
    stats = {
        'source': 'Groove MIDI Dataset (Gillick et al., Magenta), CC BY 4.0'
                  f' — {grooves} jazz swing grooves, {fills} fills',
        'ride_patterns': [{'slots': list(p), 'spelled': spell(p),
                           'share': round(n / tot, 4)}
                          for p, n in ride_pat.most_common(16)],
        'ride_skip_fraction_median': round(statistics.median(skip_frac), 3)
        if skip_frac else None,
        'snare_per_bar': norm(snare_n),
        'snare_slot': {names[int(k)]: v for k, v in norm(snare_slot).items()
                       if int(k) < 12},
        'snare_velocity_quartiles': statistics.quantiles(snare_vel, n=4)
        if len(snare_vel) > 4 else None,
        'kick_per_bar': norm(kick_n),
        'kick_slot': {names[int(k)]: v for k, v in norm(kick_slot).items()
                      if int(k) < 12},
        'kick_velocity_quartiles': statistics.quantiles(kick_vel, n=4)
        if len(kick_vel) > 4 else None,
        'hat_foot_slot': {names[int(k)]: v for k, v in norm(foot).items()
                          if int(k) < 12},
        'fill_mix': norm(fill_mix),
        'fill_grid': norm(fill_grid),
        'fill_beats_median': round(statistics.median(fill_beats), 2)
        if fill_beats else None,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(stats, f, indent=1)
    return stats


if __name__ == '__main__':
    print(json.dumps(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT),
                     indent=1))
