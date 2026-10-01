"""How the made-up rhythm section compares with the real players it
learned from, metric by metric: the drummer against the Groove MIDI
jazz drummers (data/drum_stats.json), the walking bass against
FiloBass (data/walking_stats.json). Compiles swing tunes with a tenor
solo over several takes and measures the listening document.
    bench_band.py
"""
import collections
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chartaudio  # noqa: E402
import chartc  # noqa: E402
import chartgroove as G  # noqa: E402

DR = json.load(open(os.path.join(HERE, 'data', 'drum_stats.json')))
WK = json.load(open(os.path.join(HERE, 'data', 'walking_stats.json')))
NAMES = ['1', '1t', '1&', '2', '2t', '2&', '3', '3t', '3&', '4', '4t', '4&']
TUNES = {
    'blues': 'F7, Bb7, F7, Cm7 F7, Bb7, Bdim7, F7, Am7 D7, Gm7, C7, '
             'F7 D7, Gm7 C7',
    'rhythm': 'Bb6 G7, Cm7 F7, Bb6 G7, Cm7 F7, Fm7 Bb7, Eb7 Ab7, Dm7 G7, '
              'Cm7 F7',
}


def slot(x):
    b = int(x // 1)
    f = x - b
    p = 0 if f < 0.17 else 1 if f < 0.42 else 2 if f < 0.84 else None
    if p is None:
        return None
    return 3 * b + p


def chord_of(sym):
    import re
    m = re.match(r'([A-G])([b#]?)(.*)', sym)
    return (m.group(1), {'b': -1, '#': 1, '': 0}[m.group(2)], m.group(3),
            None)


def share(c):
    t = sum(c.values()) or 1
    return {k: round(v / t, 3) for k, v in c.most_common(8)}


def main():
    tmp = tempfile.mkdtemp()
    ride_pat = collections.Counter()
    sn_bar = collections.Counter()
    sn_slot = collections.Counter()
    k_bar = collections.Counter()
    k_slot = collections.Counter()
    hf_slot = collections.Counter()
    b_arr = collections.Counter()
    b_app = collections.Counter()
    b_step = collections.Counter()
    b_reg = []
    turns = [0, 0]
    rep = [0, 0]
    offb = [0, 0]
    for name, ch in TUNES.items():
        bars = [b.strip() for b in ch.split(',')]
        chart = ("title: Bench\nkey: F\nmeter: 4/4\ntempo: 160\n"
                 "feel: swing\n\nband:\n  tenor = tenor sax\n  piano\n"
                 "  bass\n  drums\n\nsection solos, %d bars, repeat 3x\n"
                 "  chords: %s\n  tenor: solo\n" % (len(bars), ch))
        p = os.path.join(tmp, name + '.chart')
        open(p, 'w').write(chart)
        seq = []
        for b in bars:
            cs = b.split()
            seq.append([(0.0, chord_of(cs[0]))] + (
                [(2.0, chord_of(cs[1]))] if len(cs) > 1 else []))
        n_form = len(bars) * 4 * 3          # three choruses, in beats

        def chord_at(q):
            bi = int(q // 4) % len(seq)
            c = seq[bi][0][1]
            for o, cc in seq[bi]:
                if o <= (q % 4) + 1e-6:
                    c = cc
            return c
        for tk in range(4):
            chartc.TAKE = tk
            od = os.path.join(tmp, '%s%d' % (name, tk))
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(p, od)
            lx = [f for f in os.listdir(od) if 'listening' in f][0]
            sc = chartaudio.parse_score(os.path.join(od, lx))
            ev = {pt['name']: pt['events'] for pt in sc['parts']}
            dr = ev['drums']
            per = collections.defaultdict(lambda: collections.defaultdict(
                list))
            for q, _d, m, *_r in dr:
                if q >= n_form - 4:
                    continue
                s = slot(q % 4)
                if s is None:
                    continue
                per[int(q // 4)][m].append(s)
            for b, kit in per.items():
                rs = tuple(sorted(set(kit.get(51, []) + kit.get(53, []))))
                if rs:
                    ride_pat[' '.join(NAMES[x] for x in rs)] += 1
                sn = kit.get(38, [])
                sn_bar[len(sn)] += 1
                for x in sn:
                    sn_slot[NAMES[x]] += 1
                k = kit.get(36, [])
                k_bar[len(k)] += 1
                for x in k:
                    k_slot[NAMES[x]] += 1
                for x in kit.get(44, []):
                    hf_slot[NAMES[x]] += 1
            bs = sorted((q, m) for q, _d, m, *_r in ev['bass']
                        if q < n_form - 4)
            last_dir = 0
            for i, (q, m) in enumerate(bs):
                b_reg.append(m)
                c = chord_at(q)
                if abs(q % 2) < 1e-6 and (i == 0 or chord_at(q - 0.5) != c
                                          or q % 4 == 0):
                    if chord_at(q - 0.5) != c:
                        b_arr[(m - G._root_pc(c)) % 12] += 1
                        if i:
                            b_app[m - bs[i - 1][1]] += 1
                if i:
                    st = m - bs[i - 1][1]
                    b_step[st] += 1
                    rep[0] += st == 0
                    rep[1] += 1
                    if st:
                        dd = 1 if st > 0 else -1
                        if last_dir:
                            turns[0] += dd != last_dir
                            turns[1] += 1
                        last_dir = dd
            bars_q = collections.defaultdict(list)
            for q, m in bs:
                bars_q[int(q // 4)].append(q % 1)
            for b, fr in bars_q.items():
                offb[1] += 1
                offb[0] += any(0.1 < f_ < 0.9 for f_ in fr)
    top = ride_pat.most_common(4)
    tot = sum(ride_pat.values()) or 1
    print('DRUMS                       ours / Groove MIDI drummers')
    print('ride, top patterns  ', [(k, round(v / tot, 3)) for k, v in top])
    print('   real             ', [(p['spelled'], p['share'])
                                    for p in DR['ride_patterns'][:4]])
    print('snare hits a bar    ', share(sn_bar))
    print('   real             ', dict(list(DR['snare_per_bar'].items())[:8]))
    print('snare slots         ', share(sn_slot))
    print('   real             ', dict(list(DR['snare_slot'].items())[:8]))
    print('kick hits a bar     ', share(k_bar))
    print('   real             ', dict(list(DR['kick_per_bar'].items())[:8]))
    print('kick slots          ', share(k_slot))
    print('   real             ', dict(list(DR['kick_slot'].items())[:8]))
    print('hat foot slots      ', share(hf_slot))
    print('   real             ', dict(list(DR['hat_foot_slot'].items())[:8]))
    print()
    print('BASS                        ours / FiloBass')
    t = sum(b_arr.values()) or 1
    print('lands on a new chord', {k: round(v / t, 3) for k, v in
                                   b_arr.most_common(5)})
    print('   real (dom)       ', dict(list(WK['arrival_degree']['dom']
                                         .items())[:5]))
    t = sum(b_app.values()) or 1
    print('approach into it    ', {k: round(v / t, 3) for k, v in
                                   b_app.most_common(6)})
    print('   real             ', dict(list(WK['approach_interval']
                                         .items())[:6]))
    t = sum(b_step.values()) or 1
    print('steps               ', {k: round(v / t, 3) for k, v in
                                   b_step.most_common(8)})
    print('   real             ', dict(list(WK['step'].items())[:8]))
    r = sorted(b_reg)
    print('register p5/50/95   ', [r[int(len(r) * x)] for x in (.05, .5,
                                                                 .95)],
          [WK['register_percentiles'][k] for k in ('p5', 'p50', 'p95')])
    print('repeat / turn rate  ', round(rep[0] / max(rep[1], 1), 3),
          round(turns[0] / max(turns[1], 1), 3), '/', WK['repeat_rate'],
          WK['turn_rate'])
    print('bars with skips     ', round(offb[0] / max(offb[1], 1), 3), '/',
          WK['bars_with_offbeats'])


if __name__ == '__main__':
    main()
