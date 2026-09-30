#!/usr/bin/env python3
"""What real bassists do, measured: walks the FiloBass transcriptions
(Riley & Dixon, QMUL, ISMIR 2023, CC BY 4.0 — 48 professional walking
lines, chord symbols aligned) and writes the statistics the listen's
walking bass plays from, data/walking_stats.json.

Only the derived numbers ship; the transcriptions stay where they were
downloaded (Matthew, 2026-09-29: "look anything up and train the app").

    learn_walking.py [FiloBass musicxml_no_repeats dir]
"""
import collections
import json
import os
import re
import sys

STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
DEFAULT = ("/Volumes/VST's/Copyist Training Data/filobass/"
           "FiloBass ISMIR Publication/musicxml_no_repeats")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data',
                   'walking_stats.json')


def kind_of(text):
    """FiloBass kind text -> the families the listen thinks in."""
    t = text or ''
    if t.startswith('m7b5') or 'ø' in t:
        return 'half'
    if t.startswith('dim') or t.startswith('o'):
        return 'dim'
    if t.startswith('maj') or t in ('6', '69', '', 'maj'):
        return 'maj'
    if t.startswith('m'):
        return 'min'
    return 'dom'


TONES = {'maj': (0, 4, 7, 11, 9), 'min': (0, 3, 7, 10, 9),
         'dom': (0, 4, 7, 10), 'half': (0, 3, 6, 10), 'dim': (0, 3, 6, 9)}
SCALE = {'maj': (0, 2, 4, 5, 7, 9, 11), 'min': (0, 2, 3, 5, 7, 9, 10),
         'dom': (0, 2, 4, 5, 7, 9, 10), 'half': (0, 1, 3, 5, 6, 8, 10),
         'dim': (0, 2, 3, 5, 6, 8, 9, 11)}


def parse(path):
    """-> [(onset in beats, midi sounding or None, chord (root, kind))]
    and the list of chord changes [(beat, (root, kind))]."""
    x = open(path, encoding='utf-8').read()
    div = int(re.search(r'<divisions>(\d+)</divisions>', x).group(1))
    beats = int(re.search(r'<beats>(\d+)</beats>', x).group(1))
    notes, changes = [], []
    t = 0.0
    tied = False
    for mi, meas in enumerate(re.findall(r'<measure[^>]*>(.*?)</measure>',
                                         x, re.S)):
        bar0 = mi * beats
        t = float(bar0)
        for el in re.finditer(r'<harmony>(.*?)</harmony>|<note>(.*?)</note>',
                              meas, re.S):
            if el.group(1):
                h = el.group(1)
                r = STEP[re.search(r'<root-step>(\w)', h).group(1)]
                a = re.search(r'<root-alter>(-?\d)', h)
                r = (r + (int(a.group(1)) if a else 0)) % 12
                k = re.search(r'<kind(?: text="([^"]*)")?', h).group(1)
                changes.append((t, (r, kind_of(k))))
                continue
            n = el.group(2)
            dm = re.search(r'<duration>(\d+)', n)
            if not dm:
                continue                    # a grace note takes no beat
            dur = int(dm.group(1)) / div
            if '<rest' in n:
                notes.append((t, dur, None))
            else:
                p = STEP[re.search(r'<step>(\w)', n).group(1)]
                a = re.search(r'<alter>(-?\d)', n)
                o = int(re.search(r'<octave>(\d)', n).group(1))
                midi = 12 * (o + 1) + p + (int(a.group(1)) if a else 0) - 12
                if not tied:
                    notes.append((t, dur, midi))
                tied = '<tie type="start"' in n
            t += dur
    return notes, changes, beats


def chord_at(changes, t):
    c = None
    for b, ch in changes:
        if b <= t + 1e-6:
            c = ch
        else:
            break
    return c


def main(src):
    first = collections.Counter()        # degree on a chord's arrival
    approach = collections.Counter()     # interval, last beat -> next root
    appr_note = collections.Counter()    # what the lead-in is, over the
    middle = collections.Counter()       # chord tone / scale / chromatic
    steps = collections.Counter()        # beat-to-beat interval
    register = collections.Counter()
    repeat = [0, 0]
    turn = [0, 0]                        # direction changes / chances
    offbeat = [0, 0]                     # bars with any eighth or triplet
    trip = [0, 0]
    tunes = 0
    for fn in sorted(os.listdir(src)):
        if not fn.endswith('.xml'):
            continue
        tunes += 1
        notes, changes, beats = parse(os.path.join(src, fn))
        pitched = [(t, m) for t, _d, m in notes if m is not None]
        for _t, m in pitched:
            register[m] += 1
        onbeat = {round(t): m for t, m in pitched if abs(t - round(t)) < 0.02}
        bars = collections.defaultdict(list)
        for t, _d, m in notes:
            if m is not None:
                bars[int(t // beats)].append(t % beats)
        for b, ons in bars.items():
            offbeat[1] += 1
            if any(abs(o - round(o)) > 0.02 for o in ons):
                offbeat[0] += 1
            trip[1] += 1
            if any(min(abs(o * 3 - round(o * 3)), 1) < 0.03
                   and abs(o * 2 - round(o * 2)) > 0.05 for o in ons):
                trip[0] += 1
        ch_beats = sorted({round(b) for b, _c in changes})
        prev, prevdir = None, 0
        for q in sorted(onbeat):
            m = onbeat[q]
            c = chord_at(changes, q)
            if c is None:
                continue
            root, kind = c
            deg = (m - root) % 12
            if q in ch_beats:
                first[f'{kind}:{deg}'] += 1
            else:
                if deg in TONES[kind]:
                    middle['tone'] += 1
                elif deg in SCALE[kind]:
                    middle['scale'] += 1
                else:
                    middle['chromatic'] += 1
            if q + 1 in ch_beats and q + 1 in onbeat:
                nc = chord_at(changes, q + 1)
                nxt = onbeat[q + 1]
                if nc and (nxt - nc[0]) % 12 == 0:
                    approach[max(-12, min(12, m - nxt))] += 1
                    appr_note[(m - nc[0]) % 12] += 1
            if prev is not None and q - 1 == prev[0]:
                iv = m - prev[1]
                steps[max(-12, min(12, iv))] += 1
                repeat[1] += 1
                repeat[0] += iv == 0
                d = (iv > 0) - (iv < 0)
                if d and prevdir:
                    turn[1] += 1
                    turn[0] += d != prevdir
                if d:
                    prevdir = d
            prev = (q, m)
    tot = sum(register.values())
    acc, pct = 0, {}
    for m in sorted(register):
        acc += register[m]
        for p in (1, 5, 25, 50, 75, 95, 99):
            if f'p{p}' not in pct and acc >= tot * p / 100:
                pct[f'p{p}'] = m
    norm = lambda c: {str(k): round(v / sum(c.values()), 4)
                      for k, v in c.most_common()}
    by_kind = collections.defaultdict(collections.Counter)
    for k, v in first.items():
        kind, deg = k.split(':')
        by_kind[kind][int(deg)] += v
    stats = {
        'source': 'FiloBass (Riley & Dixon, ISMIR 2023), CC BY 4.0, '
                  f'{tunes} transcriptions',
        'arrival_degree': {k: norm(c) for k, c in by_kind.items()},
        'approach_interval': norm(approach),
        'approach_degree_of_next_root': norm(appr_note),
        'middle': norm(middle),
        'step': norm(steps),
        'register_percentiles': pct,
        'repeat_rate': round(repeat[0] / max(repeat[1], 1), 4),
        'turn_rate': round(turn[0] / max(turn[1], 1), 4),
        'bars_with_offbeats': round(offbeat[0] / max(offbeat[1], 1), 4),
        'bars_with_triplets': round(trip[0] / max(trip[1], 1), 4),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(stats, f, indent=1)
    return stats


if __name__ == '__main__':
    s = main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    print(json.dumps(s, indent=1))
