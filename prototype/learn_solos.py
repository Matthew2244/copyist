#!/usr/bin/env python3
"""How real soloists phrase, measured: reads the Weimar Jazz Database
(Jazzomat Research Project, Hochschule für Musik Weimar; ODbL 1.0 —
456 transcribed solos with the chord on every beat and the phrases
marked) and writes data/solo_stats.json, the numbers the listen's
soloists play from: how long a phrase runs and how long they breathe,
where a phrase starts, how often a note on the beat is a chord tone,
the intervals they move by, how busy the line is at each tempo, how a
phrase ends.

Only swing-feel 4/4 solos are counted. Only the derived statistics
ship (a Produced Work under the ODbL); the database stays where it was
downloaded.

    learn_solos.py [path to wjazzd.db]
"""
import collections
import json
import os
import re
import sqlite3
import sys

DEFAULT = "/Volumes/VST's/Copyist Training Data/wjazzd.db"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data',
                   'solo_stats.json')
STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def chord(sym):
    """'C-7' -> (0, 'min'); None for NC and the unreadable."""
    m = re.match(r'([A-G])([b#]?)(.*)', sym or '')
    if not m:
        return None
    r = (STEP[m.group(1)] + {'b': -1, '#': 1, '': 0}[m.group(2)]) % 12
    q = m.group(3).split('/')[0]
    if q.startswith(('m7b5', '-7b5')) or 'ø' in q:
        k = 'half'
    elif q.startswith(('o', 'dim')):
        k = 'dim'
    elif q.startswith(('-', 'm')) and not q.startswith('maj'):
        k = 'min'
    elif q.startswith(('j', 'maj', '6')) or q == '':
        k = 'maj'
    elif q.startswith('+'):
        k = 'aug'
    else:
        k = 'dom'
    return r, k


TONES = {'maj': {0, 4, 7, 11, 9}, 'min': {0, 3, 7, 10}, 'dom': {0, 4, 7, 10},
         'half': {0, 3, 6, 10}, 'dim': {0, 3, 6, 9}, 'aug': {0, 4, 8, 10}}
COLOR = {'maj': {2, 6}, 'min': {2, 5, 9}, 'dom': {2, 9, 1, 3, 8, 6},
         'half': {5, 8, 2}, 'dim': {2, 5, 8, 11}, 'aug': {2, 6}}


def tempo_class(bpm):
    return 'slow' if bpm < 110 else 'medium' if bpm < 180 else 'fast'


def main(db):
    con = sqlite3.connect(db)
    solos = con.execute(
        "select melid, avgtempo, instrument from solo_info where "
        "rhythmfeel='SWING' and signature='4/4'").fetchall()
    plen = collections.Counter()           # phrase length, beats
    pnotes = collections.Counter()         # phrase length, notes
    gap = collections.Counter()            # breath between, beats x2
    start = collections.Counter()          # where a phrase starts
    on_cat = collections.Counter()         # note on the beat: tone/...
    off_cat = collections.Counter()        # note off the beat
    ivs = collections.Counter()
    turns = [0, 0]
    grid = collections.Counter()           # eighth / triplet / 16th
    dens = collections.defaultdict(list)   # notes per beat inside phrases
    end_cat = collections.Counter()
    end_len = collections.Counter()
    end_pos = collections.Counter()
    approach = [0, 0]                      # half step into a beat tone
    span = collections.defaultdict(list)
    n_solos = 0
    for melid, bpm, inst in solos:
        notes = con.execute(
            "select onset, pitch, duration, bar, beat, tatum, division, "
            "beatdur from melody where melid=? order by eventid",
            (melid,)).fetchall()
        if len(notes) < 20:
            continue
        beats = con.execute(
            "select onset, chord from beats where melid=? order by onset",
            (melid,)).fetchall()
        phrases = con.execute(
            "select start, end from sections where melid=? and "
            "type='PHRASE' order by start", (melid,)).fetchall()
        if not beats or not phrases:
            continue
        n_solos += 1
        tc = tempo_class(bpm or 150)
        ps = sorted(int(n[1]) for n in notes)
        span[inst].append((ps[len(ps) // 20], ps[len(ps) // 2],
                           ps[-len(ps) // 20 - 1]))
        # the chord sounding at each note: carry the last symbol forward
        cur, bi, ch_at = None, 0, []
        for n in notes:
            while bi < len(beats) and beats[bi][0] <= n[0] + 0.02:
                if beats[bi][1]:
                    cur = chord(beats[bi][1]) or cur
                bi += 1
            ch_at.append(cur)

        def pos(n):
            _o, _p, _d, _bar, _beat, tatum, div, _bd = n
            return (tatum - 1) / max(div, 1)

        for k, (a, b) in enumerate(phrases):
            ph = notes[a:b + 1]
            if len(ph) < 2:
                continue
            bd = ph[0][7] or 0.3
            length = (ph[-1][0] + ph[-1][2] - ph[0][0]) / bd
            plen[min(32, int(round(length)))] += 1
            pnotes[min(64, len(ph))] += 1
            dens[tc].append(len(ph) / max(length, 0.5))
            p0 = pos(ph[0])
            start[f"{ph[0][4]}:{'on' if p0 < 0.05 else 'and' if abs(p0 - 0.5) < 0.1 or abs(p0 - 2 / 3) < 0.1 else 'other'}"] += 1
            if k + 1 < len(phrases) and phrases[k + 1][0] < len(notes):
                nxt = notes[phrases[k + 1][0]]
                g = (nxt[0] - (ph[-1][0] + ph[-1][2])) / bd
                gap[min(32, max(0, int(round(g * 2))))] += 1
            last = ph[-1]
            c = ch_at[b] if b < len(ch_at) else None
            if c:
                d = (int(last[1]) - c[0]) % 12
                end_cat['tone' if d in TONES[c[1]] else 'color'
                        if d in COLOR[c[1]] else 'other'] += 1
            end_len[min(8, int(round(last[2] / bd * 2)))] += 1
            pe = pos(last)
            end_pos['on' if pe < 0.05 else 'and' if abs(pe - 0.5) < 0.1
                    or abs(pe - 2 / 3) < 0.1 else 'other'] += 1
            prevd = 0
            for j, n in enumerate(ph):
                c = ch_at[a + j]
                p = pos(n)
                if c:
                    d = (int(n[1]) - c[0]) % 12
                    cat = 'tone' if d in TONES[c[1]] else 'color' \
                        if d in COLOR[c[1]] else 'other'
                    (on_cat if p < 0.05 else off_cat)[cat] += 1
                    if p < 0.05 and cat == 'tone' and j:
                        approach[1] += 1
                        approach[0] += abs(int(n[1]) -
                                           int(ph[j - 1][1])) == 1
                div = n[6]
                grid['triplet' if div in (3, 6) and p not in (0.0,)
                     else '16th' if div in (4, 8) and abs(p * 2 -
                                                         round(p * 2)) > .1
                     else 'eighth' if p else 'beat'] += 1
                if j:
                    iv = int(n[1]) - int(ph[j - 1][1])
                    ivs[max(-12, min(12, iv))] += 1
                    dd = (iv > 0) - (iv < 0)
                    if dd and prevd:
                        turns[1] += 1
                        turns[0] += dd != prevd
                    if dd:
                        prevd = dd

    def norm(c):
        t = sum(c.values()) or 1
        return {str(k): round(v / t, 4) for k, v in c.most_common()}

    def median(xs):
        xs = sorted(xs)
        return round(xs[len(xs) // 2], 3) if xs else None

    def pct(c, ps):
        t = sum(c.values())
        out, acc = {}, 0
        for k in sorted(c):
            acc += c[k]
            for p in ps:
                if f'p{p}' not in out and acc >= t * p / 100:
                    out[f'p{p}'] = k
        return out
    stats = {
        'source': 'Weimar Jazz Database 2.1 (Jazzomat, HfM Weimar), '
                  f'ODbL 1.0, {n_solos} swing 4/4 solos',
        'phrase_beats': norm(plen),
        'phrase_beats_pct': pct(plen, (10, 25, 50, 75, 90)),
        'phrase_notes_pct': pct(pnotes, (10, 25, 50, 75, 90)),
        'gap_half_beats': norm(gap),
        'gap_beats_pct': {k: v / 2 for k, v in
                          pct(gap, (10, 25, 50, 75, 90)).items()},
        'phrase_start': norm(start),
        'on_beat': norm(on_cat),
        'off_beat': norm(off_cat),
        'interval': norm(ivs),
        'turn_rate': round(turns[0] / max(turns[1], 1), 4),
        'grid': norm(grid),
        'notes_per_beat': {k: median(v) for k, v in dens.items()},
        'end_degree': norm(end_cat),
        'end_len_half_beats': norm(end_len),
        'end_position': norm(end_pos),
        'half_step_into_beat_tone': round(approach[0] /
                                          max(approach[1], 1), 4),
        'range_by_instrument': {
            i: {'p5': median([x[0] for x in v]),
                'p50': median([x[1] for x in v]),
                'p95': median([x[2] for x in v])}
            for i, v in span.items() if len(v) >= 5},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(stats, f, indent=1)
    return stats


if __name__ == '__main__':
    s = main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    print(json.dumps({k: v for k, v in s.items()
                      if k not in ('phrase_beats', 'gap_half_beats',
                                   'interval', 'phrase_start')}, indent=1))
    print('phrase_start', list(s['phrase_start'].items())[:10])
    print('interval', list(s['interval'].items())[:14])
