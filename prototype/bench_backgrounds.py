"""Made-up horn backgrounds against the arranging rules: spacing (no
gap wider than an octave between the upper voices), low interval
limits, two horns on one note (a wasted voice), the 3rd and 7th present
(the chord is clear), and a smooth top line. Compiles a soloist with a
horn section on backgrounds over several takes.
    bench_backgrounds.py
"""
import collections
import io
import os
import re
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chartaudio  # noqa: E402
import chartc  # noqa: E402
import chartgroove as G  # noqa: E402
from bench_comping import LIL  # noqa: E402

BANDS = {
    'small': ['trumpet', 'alto = alto sax', 'bone = trombone'],
    'big': ['trumpet', 'alto = alto sax', 'tenor 2 = tenor sax',
            'bone = trombone', 'bari = baritone sax'],
}
CH = 'Fmaj7, D7, Gm7, C7, Am7 D7, Gm7 C7, Fmaj7, C7'


def chord_of(sym):
    m = re.match(r'([A-G])([b#]?)(.*)', sym)
    return (m.group(1), {'b': -1, '#': 1, '': 0}[m.group(2)], m.group(3),
            None)


def main():
    tmp = tempfile.mkdtemp()
    seq = []
    for b in CH.split(','):
        cs = b.split()
        seq.append([(0.0, chord_of(cs[0]))] + (
            [(2.0, chord_of(cs[1]))] if len(cs) > 1 else []))

    def chord_at(q):
        bi = int(q // 4) % len(seq)
        c = seq[bi][0][1]
        for o, cc in seq[bi]:
            if o <= (q % 4) + 1e-6:
                c = cc
        return c
    for name, horns in BANDS.items():
        n_ch = gaps = lil = lil_n = dup = guide_ok = leaps = tops = 0
        ex = []
        for tk in range(6):
            chart = ("title: BG\nkey: F\nmeter: 4/4\ntempo: 150\n"
                     "feel: swing\n\nband:\n  tenor = tenor sax\n  "
                     + "\n  ".join(horns) + "\n  piano\n  bass\n  drums\n\n"
                     "section solos, 8 bars, repeat 4x\n  chords: %s\n"
                     "  tenor: solo\n  horns: backgrounds\n\n"
                     "group horns: %s\n" % (CH, ", ".join(
                         h.split(' = ')[0] for h in horns)))
            # the group line belongs before the sections
            head, body = chart.split("section solos", 1)
            body, grp = body.split("\ngroup horns:", 1)
            chart = head + "group horns:" + grp + "\nsection solos" + body
            p = os.path.join(tmp, name + '.chart')
            open(p, 'w', encoding='utf-8').write(chart)
            chartc.TAKE = tk
            od = os.path.join(tmp, '%s%d' % (name, tk))
            with redirect_stdout(io.StringIO()):
                chartc.compile_chart(p, od)
            lx = [f for f in os.listdir(od) if 'listening' in f][0]
            sc = chartaudio.parse_score(os.path.join(od, lx))
            names = [h.split(' = ')[0] for h in horns]
            ons = collections.defaultdict(dict)
            for pt in sc['parts']:
                if pt['name'] in names:
                    for q, d_, m, *_r in pt['events']:
                        if q < 4 * 8 * 4 - 4:
                            ons[round(q, 3)][pt['name']] = m
            last_top = None
            for q in sorted(ons):
                v = ons[q]
                if len(v) < len(names):
                    continue
                n_ch += 1
                ms = sorted(v.values())
                if len(set(ms)) < len(ms):
                    dup += 1
                for a, b in zip(ms[1:], ms[2:]):      # above the bottom
                    gaps += b - a > 12
                for a, b in zip(ms, ms[1:]):
                    iv = b - a
                    if iv in LIL:
                        lil_n += 1
                        if a < LIL[iv]:
                            lil += 1
                            if len(ex) < 3:
                                ex.append((q, ms))
                c = chord_at(q)
                r = G._root_pc(c)
                rel = {(m - r) % 12 for m in ms}
                guide_ok += bool(rel & {3, 4}) and bool(rel & {10, 11, 9})
                top = ms[-1]
                if last_top is not None:
                    tops += 1
                    leaps += abs(top - last_top) > 5
                last_top = top
        print(f"{name} section ({len(BANDS[name])} horns): {n_ch} chords")
        print(f"   gaps over an octave above the bottom: {gaps}")
        print(f"   low interval limit breaks: {lil} of {lil_n} e.g. {ex}")
        print(f"   two horns on one note: {dup}")
        print(f"   3rd and 7th (or 6th) both there: "
              f"{round(guide_ok / max(n_ch, 1), 2)}")
        print(f"   top line leaps over a 4th: "
              f"{round(leaps / max(tops, 1), 2)}")


if __name__ == '__main__':
    main()
