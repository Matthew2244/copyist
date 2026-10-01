#!/usr/bin/env python3
"""The vocabulary real soloists share, measured: reads the Weimar Jazz
Database (Jazzomat Research Project, Hochschule für Musik Weimar; ODbL
1.0 — 456 transcribed solos with the chord on every beat and the
phrases marked) and writes data/lick_stats.json: the short figures
players reach for over each kind of chord, and across the common
changes (ii to V, V to I), each one written relative to the chord —
the degree it starts on, the steps it moves by, its rhythm on the
beat — never as one player's notes.

A figure is kept only when several different players used it, so what
ships is the shared language, not anyone's solo. Only the derived
counts ship (a Produced Work under the ODbL); the database stays where
it was downloaded (Matthew, 2026-10-01: "keep training the band").
    learn_licks.py [path to wjazzd.db]
"""
import collections
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from learn_solos import DEFAULT, chord  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data',
                   'lick_stats.json')
GRID = 6                    # sixths of a beat: eighths and triplets both
MIN_COUNT = 4               # heard at least this often
MIN_PLAYERS = 3             # from at least this many different solos


def on_grid(x):
    g = round(x * GRID) / GRID
    return g if abs(g - x) < 0.06 else None


def main(db):
    con = sqlite3.connect(db)
    solos = con.execute(
        "select melid, performer from solo_info where "
        "rhythmfeel='SWING' and signature='4/4'").fetchall()
    one = collections.defaultdict(lambda: collections.defaultdict(list))
    two = collections.defaultdict(lambda: collections.defaultdict(list))
    n_solos = 0
    for melid, who in solos:
        notes = con.execute(
            "select onset, pitch, duration, bar, beat, tatum, division, "
            "beatdur from melody where melid=? order by eventid",
            (melid,)).fetchall()
        beats = con.execute(
            "select onset, chord from beats where melid=? order by onset",
            (melid,)).fetchall()
        phrases = con.execute(
            "select start, end from sections where melid=? and "
            "type='PHRASE' order by start", (melid,)).fetchall()
        if len(notes) < 20 or not beats or not phrases:
            continue
        n_solos += 1
        cur, bi, ch_at = None, 0, []
        for n in notes:
            while bi < len(beats) and beats[bi][0] <= n[0] + 0.02:
                if beats[bi][1]:
                    cur = chord(beats[bi][1]) or cur
                bi += 1
            ch_at.append(cur)

        def pos(n):
            _o, _p, _d, bar, beat, tatum, div, _bd = n
            return bar * 4 + (beat - 1) + (tatum - 1) / max(div, 1)
        for a, b in phrases:
            for i in range(a, b + 1):
                if i >= len(notes) or ch_at[i] is None:
                    continue
                p0 = pos(notes[i])
                if abs(p0 - round(p0)) > 0.02:
                    continue              # a figure starts on a beat
                for k in range(4, 8):
                    j = i + k
                    if j > b + 1 or j > len(notes):
                        break
                    seg = notes[i:j]
                    chs = ch_at[i:j]
                    if any(c is None for c in chs):
                        break
                    ons = [on_grid(pos(n) - p0) for n in seg]
                    if None in ons or ons[-1] > 4.0:
                        break
                    durs = [min(round((n[2] / max(n[7] or 0.3, 0.05))
                                      * GRID) / GRID, 2.0) for n in seg]
                    r0, q0 = chs[0]
                    deg = (int(seg[0][1]) - r0) % 12
                    steps = tuple(int(seg[x + 1][1]) - int(seg[x][1])
                                  for x in range(len(seg) - 1))
                    if any(abs(s) > 9 for s in steps):
                        break
                    kinds = []
                    for c in chs:
                        if not kinds or c != kinds[-1][1]:
                            kinds.append((None, c))
                    if len(kinds) == 1 and ons[-1] <= 2.0:
                        key = (q0, deg, steps, tuple(ons))
                        one[q0][key].append((melid, durs))
                    elif len(kinds) == 2:
                        r1, q1 = kinds[1][1]
                        at = next(ons[x] for x in range(len(seg))
                                  if chs[x] != chs[0])
                        if abs(at - round(at)) > 0.02 or at < 1.0:
                            continue
                        move = (r1 - r0) % 12
                        prog = f'{q0}>{q1}+{move}'
                        key = (prog, deg, steps, tuple(ons), at)
                        two[prog][key].append((melid, durs))

    def keep(table, with_change):
        out = {}
        for q, figs in table.items():
            rows = []
            for key, uses in figs.items():
                players = {u[0] for u in uses}
                if len(uses) < MIN_COUNT or len(players) < MIN_PLAYERS:
                    continue
                durs = [sorted(u[1][x] for u in uses)[len(uses) // 2]
                        for x in range(len(key[2]) + 1)]
                row = {'deg': key[1], 'steps': list(key[2]),
                       'on': list(key[3]), 'len': durs, 'n': len(uses),
                       'players': len(players)}
                if with_change:
                    row['change'] = key[4]
                rows.append(row)
            rows.sort(key=lambda r: (-r['players'], -r['n']))
            if rows:
                out[q] = rows[:120]
        return out
    stats = {'source': 'Weimar Jazz Database 2.1 (ODbL 1.0)',
             'solos': n_solos,
             'one_chord': keep(one, False),
             'two_chords': keep(two, True)}
    with open(OUT, 'w') as f:
        json.dump(stats, f, indent=1)
    return stats


if __name__ == '__main__':
    s = main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    print(f"{s['solos']} solos")
    for k in ('one_chord', 'two_chords'):
        print(k, {q: len(v) for q, v in s[k].items()})
