"""How the made-up soloists compare with the Weimar Jazz Database players,
metric by metric: phrase and breath lengths, density, what lands on the
beat, the rhythm grid, intervals, how phrases start and end. Run it
before and after training the soloists.
    bench_solos.py
"""
import os, sys, json, collections, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chartgroove as G
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from learn_solos import TONES, COLOR
W = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'solo_stats.json')))
def C(s):
    import re
    m = re.match(r'([A-G])([b#]?)(.*)', s)
    return (m.group(1), {'b': -1, '#': 1, '': 0}[m.group(2)], m.group(3), None)
PROGS = {
 'blues': ['F7','Bb7','F7','Cm7 F7','Bb7','Bdim7','F7','Am7 D7','Gm7','C7','F7 D7','Gm7 C7'],
 'rhythm': ['Bb6 G7','Cm7 F7','Bb6 G7','Cm7 F7','Fm7 Bb7','Eb7 Ab7','Dm7 G7','Cm7 F7'],
 'iivi': ['Dm7','G7','Cmaj7','Cmaj7','Em7b5','A7','Dm7','Dm7'],
 'modal': ['Dm7','Dm7','Dm7','Dm7','Dm7','Dm7','Dm7','Dm7'],
}
def chord_fn_of(bars):
    seq = []
    for b in bars:
        cs = b.split()
        if len(cs) == 1: seq.append([(0, C(cs[0]))])
        else: seq.append([(0, C(cs[0])), (2, C(cs[1]))])
    def f(t):
        bi = int(t // 4) % len(seq); off = t % 4
        c = seq[bi][0][1]
        for o, cc in seq[bi]:
            if o <= off + 1e-6: c = cc
        return c
    return f
def qual(c):
    q = G._lick_q(c)
    return {'half': 'half'}.get(q, q)
def cat(m, c):
    rel = (m - G._root_pc(c)) % 12
    q = qual(c)
    if rel in TONES[q]: return 'tone'
    if rel in COLOR[q]: return 'color'
    return 'other'
G.BPM = 160.0
stats = collections.defaultdict(collections.Counter)
plen, pnotes, gaps, dens = [], [], [], []
turns = [0, 0]; n_int = 0
for pname, bars in PROGS.items():
    cf = chord_fn_of(bars)
    nb = 32 if len(bars) == 8 else 36
    for persona in G.PERSONAS:
        for sd in range(5):
            sol = G.plan_solo(cf, nb, 4, 53, 74, 'swing', f'bench {pname} {persona} {sd}', persona=persona)
            sol = sorted(sol)
            # phrases: a gap of a beat or more
            ph = [[sol[0]]]
            for a, b in zip(sol, sol[1:]):
                if b[0] - (a[0] + a[1]) >= 0.9: ph.append([b])
                else: ph[-1].append(b)
            for i, p in enumerate(ph):
                L = p[-1][0] + p[-1][1] - p[0][0]
                plen.append(L); pnotes.append(len(p))
                if L > 0: dens.append(len(p) / max(L, 0.5))
                st = p[0][0] % 1
                stats['start'][('on' if abs(st) < .02 else 'and' if abs(st - .5) < .02 else 'other')] += 1
                en = p[-1][0] % 1
                stats['end'][('on' if abs(en) < .02 else 'and' if abs(en - .5) < .02 else 'other')] += 1
                if i + 1 < len(ph): gaps.append(ph[i + 1][0][0] - (p[-1][0] + p[-1][1]))
                prev_dir = 0
                for a, b in zip(p, p[1:]):
                    iv = b[2] - a[2]
                    stats['iv'][max(-9, min(9, iv))] += 1
                    if iv:
                        d_ = 1 if iv > 0 else -1
                        if prev_dir: turns[0] += d_ != prev_dir; turns[1] += 1
                        prev_dir = d_
            for at, ln, m, *_ in sol:
                fr = at % 1
                g = 'beat' if abs(fr) < .02 else 'eighth' if abs(fr - .5) < .02 else 'triplet' if min(abs(fr - 1/3), abs(fr - 2/3)) < .03 else '16th'
                stats['grid'][g] += 1
                c = cf(at)
                stats['on' if g == 'beat' else 'off'][cat(m, c)] += 1
def pct(xs, p):
    xs = sorted(xs); return xs[int(p / 100 * (len(xs) - 1))]
def share(cn):
    t = sum(cn.values()); return {k: round(v / t, 3) for k, v in cn.most_common()}
print('metric                 ours                     Weimar')
print('phrase beats p25/50/75', [round(pct(plen, p), 1) for p in (25, 50, 75)], [W['phrase_beats_pct'][k] for k in ('p25', 'p50', 'p75')])
print('phrase notes p25/50/75', [pct(pnotes, p) for p in (25, 50, 75)], [W['phrase_notes_pct'][k] for k in ('p25', 'p50', 'p75')])
print('gap beats p25/50/75   ', [round(pct(gaps, p), 1) for p in (25, 50, 75)], [W['gap_beats_pct'][k] for k in ('p25', 'p50', 'p75')])
print('notes/beat in phrase  ', round(sum(dens) / len(dens), 2), W['notes_per_beat'])
print('on beat               ', share(stats['on']), W['on_beat'])
print('off beat              ', share(stats['off']), W['off_beat'])
print('grid                  ', share(stats['grid']), W['grid'])
print('turn rate             ', round(turns[0] / max(turns[1], 1), 3), W['turn_rate'])
iv = share(stats['iv'])
print('intervals 0/±1/±2/±3/±4/±5/±7+', [round(sum(iv.get(k, 0) for k in ks), 3) for ks in ((0,), (1, -1), (2, -2), (3, -3), (4, -4), (5, -5), (6, -6, 7, -7, 8, -8, 9, -9))])
wi = W['interval']; print('   Weimar                       ', [round(sum(wi.get(str(k), 0) for k in ks), 3) for ks in ((0,), (1, -1), (2, -2), (3, -3), (4, -4), (5, -5), (6, -6, 7, -7, 8, -8, 9, -9))])
print('phrase start          ', share(stats['start']))
ws = collections.Counter()
for k, v in W['phrase_start'].items(): ws[k.split(':')[1]] += v
print('   Weimar             ', {k: round(v, 3) for k, v in ws.items()})
print('phrase end            ', share(stats['end']), W['end_position'])
