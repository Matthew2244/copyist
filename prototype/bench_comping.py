"""The comping against the rules pros learn: low interval limits (how
low each interval can sit before it turns to mud), where the voicings
sit, how often a chord is struck, how much of it is syncopated.
Compiles swing tunes with a tenor solo over several takes.
    bench_comping.py
"""
import collections
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chartaudio  # noqa: E402
import chartc  # noqa: E402

# the lowest the LOWER note of each interval should sit (MIDI), the
# standard low-interval-limit table
LIL = {1: 52, 2: 51, 3: 48, 4: 46, 5: 46, 6: 47, 7: 34, 8: 41, 9: 41,
       10: 41, 11: 41}
TUNES = {
    'blues': 'F7, Bb7, F7, Cm7 F7, Bb7, Bdim7, F7, Am7 D7, Gm7, C7, '
             'F7 D7, Gm7 C7',
    'rhythm': 'Bb6 G7, Cm7 F7, Bb6 G7, Cm7 F7, Fm7 Bb7, Eb7 Ab7, Dm7 G7, '
              'Cm7 F7',
    'ballad': 'Ebmaj7, Cm7, Fm7, Bb7, Gm7, C7, Fm7, Bb7',
}


def main():
    tmp = tempfile.mkdtemp()
    for who in ('piano', 'guitar'):
        lil = viol = 0
        low = []
        hits = collections.Counter()
        sync = [0, 0]
        ex = []
        for name, ch in TUNES.items():
            bars = len(ch.split(','))
            feel = 'ballad' if name == 'ballad' else 'swing'
            tempo = 70 if name == 'ballad' else 170
            chart = ("title: C\nkey: F\nmeter: 4/4\ntempo: %d\nfeel: %s\n\n"
                     "band:\n  tenor = tenor sax\n  %s\n  bass\n  drums\n\n"
                     "section solos, %d bars, repeat 2x\n  chords: %s\n"
                     "  tenor: solo\n" % (tempo, feel, who, bars, ch))
            p = os.path.join(tmp, name + who + '.chart')
            open(p, 'w', encoding='utf-8').write(chart)
            for tk in range(3):
                chartc.TAKE = tk
                od = os.path.join(tmp, '%s%s%d' % (name, who, tk))
                with redirect_stdout(io.StringIO()):
                    chartc.compile_chart(p, od)
                lx = [f for f in os.listdir(od) if 'listening' in f][0]
                sc = chartaudio.parse_score(os.path.join(od, lx))
                ev = [e for pt in sc['parts'] if pt['name'] == who
                      for e in pt['events']]
                end = bars * 4 * 2 - 4
                by = collections.defaultdict(list)
                for q, _d, m, *_r in ev:
                    if q < end:
                        by[round(q, 3)].append(m)
                per_bar = collections.Counter(int(q // 4) for q in by)
                for b in range(int(end // 4)):
                    hits[per_bar.get(b, 0)] += 1
                for q, ms in by.items():
                    ms = sorted(set(ms))
                    if len(ms) < 2:
                        continue
                    sync[1] += 1
                    sync[0] += abs(q % 1) > 0.1
                    low.append(ms[0])
                    for a, b in zip(ms, ms[1:]):
                        iv = b - a
                        if iv in LIL:
                            lil += 1
                            if a < LIL[iv]:
                                viol += 1
                                if len(ex) < 4:
                                    ex.append((name, q, ms))
        low.sort()
        t = sum(hits.values()) or 1
        print(f"{who}: low-interval-limit breaks {viol} of {lil} "
              f"({100 * viol // max(lil, 1)}%) e.g. {ex}")
        print(f"   lowest note of a voicing p10/50/90: "
              f"{[low[int(len(low) * x)] for x in (.1, .5, .9)] if low else []}")
        print(f"   chords struck a bar: "
              f"{ {k: round(v / t, 2) for k, v in sorted(hits.items())} }")
        print(f"   syncopated (off the beat): "
              f"{round(sync[0] / max(sync[1], 1), 2)}")


if __name__ == '__main__':
    main()
