#!/usr/bin/env python3
"""chartaudio — Copyist's own ears: the listen file without MuseScore.

Parses the listening document Copyist itself emitted (a subset of
MusicXML this module and the emitter agree on), schedules every note in
seconds, and synthesizes the band with a small wavetable synth — stdlib
only. ffmpeg encodes the MP3; without it the WAV stands and says so.

Why this exists: the listening path is the blind writer's primary proof
channel, and it depended on an external CLI that crashes after (and
sometimes instead of) writing, plays slashes it was told to mute, puts
a ~-13 dB noise floor under silence, and reads the MusicXML swing
element backwards. Playing our own resolved music removes every one of
those — and the page and the sound can no longer disagree, because
they are the same data.

The synth is deliberately plain: harmonic recipes per instrument
family, clean envelopes, a little stereo seating, no reverb, headroom
kept (peaks at -1.4 dBFS — the iMessage playback lesson). Robot horns,
but OUR robot horns.
"""
import math
import os
import re
import struct
import subprocess
import wave
from array import array

SR = 44100
TABLE = 4096
STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

# what a note carries besides pitch and time: the articulation flags the
# page prints, so the band can play them. Ties merge these across the
# tied span (a fall marked on the last tied note falls out of the whole).
_ART_MARKS = [('<staccato/>', 'stac'), ('<tenuto/>', 'ten'),
              ('<accent/>', 'acc'), ('<strong-accent', 'marc'),
              ('<falloff', 'fall'), ('<doit', 'doit'),
              ('<scoop', 'scoop'), ('<plop', 'plop'),
              ('<fermata', 'fermata'), ('<trill-mark', 'trill'),
              ('<glissando type="start"', 'gliss'),
              ('<slide type="start"', 'port')]

# the drum map read backwards: staff position and notehead -> GM number.
# Our own charts write instruments.DRUM_MAP positions; a lifted engraving
# passes its source's positions through verbatim, so exact match falls
# back to same-position-any-head, then to the nearest staff position
# (same head family preferred) — a normal head at E4 is somebody's kick.
def _drum_decode():
    import instruments
    prefer = {('F', 4, 'normal'): 36, ('C', 5, 'normal'): 38,
              ('C', 5, 'x'): 37, ('A', 4, 'normal'): 43,
              ('D', 5, 'normal'): 47, ('E', 5, 'normal'): 48,
              ('A', 5, 'x'): 49, ('F', 5, 'x'): 51}
    # a hand-percussion staff reads the same positions differently: its
    # G5 x is a shaker, its C5 is the low bongo — never a snare
    prefer_hand = {('G', 5, 'x'): 82, ('E', 5, 'normal'): 60,
                   ('C', 5, 'normal'): 61, ('D', 5, 'normal'): 65,
                   ('B', 4, 'normal'): 66, ('A', 4, 'normal'): 63,
                   ('A', 4, 'x'): 62, ('F', 4, 'normal'): 64,
                   ('E', 5, 'x'): 76, ('C', 5, 'x'): 77,
                   ('D', 5, 'x'): 75}
    out = []
    for pref in (prefer, prefer_hand):
        exact, by_pos = {}, {}
        for midi, (st, oc, head) in sorted(instruments.DRUM_MAP.items()):
            exact.setdefault((st, oc, head), pref.get((st, oc, head), midi))
            by_pos.setdefault((st, oc), []).append(
                (head, pref.get((st, oc, head), midi)))
        out.append((exact, by_pos))
    return out


_DRUM_TABLES = None


def drum_midi(step, octave, notehead, hand=False):
    """GM drum number for a staff position and notehead. `hand` reads
    the position as a hand-percussion staff instead of the kit's."""
    global _DRUM_TABLES
    if _DRUM_TABLES is None:
        _DRUM_TABLES = _drum_decode()
    exact, by_pos = _DRUM_TABLES[1 if hand else 0]
    key = (step, octave, notehead)
    if key in exact:
        return exact[key]
    cands = by_pos.get((step, octave))
    if cands:
        for head, midi in cands:
            if head == notehead:
                return midi
        return cands[0][1]
    want = 'CDEFGAB'.index(step) + 7 * octave
    best, best_key = 38, (99, 2)
    for (st, oc), cands in _DRUM_BYPOS.items():
        d = abs('CDEFGAB'.index(st) + 7 * oc - want)
        for head, midi in cands:
            key = (d, 0 if head == notehead else 1)
            if key < best_key:
                best, best_key = midi, key
    return best

# ---------------------------------------------------------------- parse


def _measures(body):
    return re.findall(r'<measure [^>]*?number="([^"]+)"[^>]*>(.*?)'
                      r'</measure>', body, re.S)


def _expand_repeats(ms):
    """Linearize repeats the way a player reads them. A plain backward
    with times=N plays its segment N times total. Volta brackets take
    one ending per pass: play the body plus ending K on pass K, jump
    back at each ending's backward repeat, walk on out of the last."""
    out = []
    i, seg_start, seg_out, pass_no = 0, -1, 0, 1
    while i < len(ms):
        num, m = ms[i]
        if '<repeat direction="forward"' in m and i != seg_start:
            seg_start, seg_out, pass_no = i, len(out), 1
        endm = re.search(r'<ending number="(\d+)" type="start"/>', m)
        if endm and int(endm.group(1)) != pass_no:
            k = int(endm.group(1))       # not this pass's bracket: skip it
            while i < len(ms):
                if re.search(r'<ending number="%d" '
                             r'type="(?:stop|discontinue)"' % k, ms[i][1]):
                    i += 1
                    break
                i += 1
            continue
        out.append((num, m))
        bk = re.search(r'<repeat direction="backward"'
                       r'(?:\s+times="(\d+)")?', m)
        if bk:
            if '<ending' in m:
                i = seg_start            # take the next ending this time
                pass_no += 1
                continue
            times = int(bk.group(1) or 2)
            seg = out[seg_out:]
            for _ in range(times - 1):
                out.extend(seg)
        i += 1
    return out


def parse_score(path, only=None):
    """Our emitted listening document -> a playable plan:
    parts: [{name, program, percussion, events: [(q_on, q_dur, midi,
    gain)]}] with q in quarter notes from the top; tempos: [(q, qbpm)];
    swings: [(q, ratio_or_None)]."""
    xml = open(path, encoding='utf-8').read()
    meta = {}
    for sp in re.findall(r'<score-part id="([^"]+)">(.*?)</score-part>',
                         xml, re.S):
        pid, body = sp
        name = re.search(r'<part-name>([^<]*)</part-name>', body)
        prog = re.search(r'<midi-program>(\d+)</midi-program>', body)
        chan = re.search(r'<midi-channel>(\d+)</midi-channel>', body)
        snd = re.search(r'<instrument-sound>([^<]*)</instrument-sound>',
                        body)
        meta[pid] = {'name': name.group(1) if name else pid,
                     'program': int(prog.group(1)) if prog else 1,
                     'percussion': bool(chan) and chan.group(1) == '10',
                     'sound': snd.group(1) if snd else ''}

    parts, tempos, swings, holds = [], {}, {}, {}
    for pid, body in re.findall(r'<part id="([^"]+)">(.*?)</part>',
                                xml, re.S):
        m = meta.get(pid, {'name': pid, 'program': 1, 'percussion': False})
        if only is not None and m['name'].lower().strip() not in only:
            continue
        div, tnum, tden = 24, 4, 4
        meter0 = None
        transpose = 0
        dyn_state = 80.0
        q0 = 0.0                        # quarters at the measure's start
        bars = {}                       # printed bar -> q of FIRST play
        events = []
        carry = {}                      # (voice, midi) -> event index, for ties
        dyns = []                       # (q, dynamics value) timeline
        wedges = []                     # (q_start, q_end, 'cresc'|'dim')
        wedge_open = None
        slur_depth = 0
        for num, meas in _expand_repeats(_measures(body)):
            if num.isdigit():
                bars.setdefault(int(num), q0)
            dv = re.search(r'<divisions>(\d+)</divisions>', meas)
            if dv:
                div = int(dv.group(1))
            ts = re.search(r'<beats>(\d+)</beats>\s*'
                           r'<beat-type>(\d+)</beat-type>', meas)
            if ts:
                tnum, tden = int(ts.group(1)), int(ts.group(2))
                if meter0 is None:
                    meter0 = (tnum, tden)
            tr = re.search(r'<transpose>.*?</transpose>', meas, re.S)
            if tr:
                ch = re.search(r'<chromatic>(-?\d+)</chromatic>', tr.group(0))
                oc = re.search(r'<octave-change>(-?\d+)</octave-change>',
                               tr.group(0))
                transpose = ((int(ch.group(1)) if ch else 0)
                             + 12 * (int(oc.group(1)) if oc else 0))
            pos = 0
            top = 0                     # a pickup is only as long as itself
            last_on = {}                # voice -> onset ticks, for <chord/>
            for el in re.finditer(
                    r'<note[ >].*?</note>|<backup>.*?</backup>'
                    r'|<forward>.*?</forward>|<direction[ >].*?</direction>',
                    meas, re.S):
                t = el.group(0)
                if t.startswith('<backup'):
                    pos -= int(re.search(r'<duration>(\d+)</duration>',
                                         t).group(1))
                    continue
                if t.startswith('<forward'):
                    pos += int(re.search(r'<duration>(\d+)</duration>',
                                         t).group(1))
                    continue
                if t.startswith('<direction'):
                    sd = re.search(r'<sound tempo="([\d.]+)"', t)
                    if sd:
                        tempos[q0 + pos / div] = float(sd.group(1))
                    sd = re.search(r'<sound dynamics="([\d.]+)"', t)
                    if sd:
                        dyn_state = float(sd.group(1))
                        dyns.append((q0 + pos / div, dyn_state))
                    wd = re.search(r'<wedge [^>]*type="(\w+)"', t)
                    if wd:
                        if wd.group(1) in ('crescendo', 'diminuendo'):
                            wedge_open = (q0 + pos / div,
                                          'cresc' if wd.group(1)[0] == 'c'
                                          else 'dim')
                        elif wd.group(1) == 'stop' and wedge_open:
                            wedges.append((wedge_open[0], q0 + pos / div,
                                           wedge_open[1]))
                            wedge_open = None
                    sw = re.search(r'<swing>(.*?)</swing>', t, re.S)
                    if sw:
                        if '<straight/>' in sw.group(1):
                            swings[q0 + pos / div] = None
                        else:
                            f = re.search(r'<first>(\d+)</first>',
                                          sw.group(1))
                            s = re.search(r'<second>(\d+)</second>',
                                          sw.group(1))
                            # a 16th swing-type swings each half-beat
                            # — the 8-Bit book's "Swing 16ths Groove"
                            unit = 0.5 if re.search(
                                r'<swing-type>16th</swing-type>',
                                sw.group(1)) else 1.0
                            if f and s:
                                fv, sv = int(f.group(1)), int(s.group(1))
                                swings[q0 + pos / div] = \
                                    (fv / (fv + sv), unit)
                    continue
                # a note
                if '<grace' in t.split('<duration')[0] \
                        if '<duration' in t else '<grace' in t:
                    continue
                d = re.search(r'<duration>(\d+)</duration>', t)
                if not d:
                    continue
                dur = int(d.group(1))
                voice = re.search(r'<voice>(\d+)</voice>', t)
                voice = voice.group(1) if voice else '1'
                chorded = '<chord/>' in t
                on = last_on.get(voice, pos) if chorded else pos
                if not chorded:
                    last_on[voice] = pos
                    pos += dur
                    top = max(top, pos)
                if '<rest' in t or '<cue/>' in t \
                        or '<notehead>slash</notehead>' in t:
                    # cues and slashes print; they never sound — but a
                    # fermata over a REST still holds time (the
                    # phrase-end hold on an empty bar)
                    if '<rest' in t and '<fermata' in t:
                        hq = q0 + (on + dur) / div - 1e-6
                        holds[hq] = max(holds.get(hq, 0.0),
                                        min(dur / div, 2.0) * 0.9)
                    continue
                nd = re.search(r'dynamics="([\d.]+)"', t)
                gain = (float(nd.group(1)) if nd else dyn_state) / 100.0
                if gain <= 0:
                    continue            # a slash is an instruction
                art = {}
                for pat, flag in _ART_MARKS:
                    if pat in t:
                        art[flag] = True
                if 'trill' in art and '<accidental-mark' in t:
                    art['trill_half'] = True   # marked neighbor: a step
                if '<notehead parentheses="yes"' in t:
                    art['ghost'] = True
                starts = len(re.findall(r'<slur [^>]*type="start"', t))
                stops = len(re.findall(r'<slur [^>]*type="stop"', t))
                if slur_depth + starts - stops > 0:
                    art['leg'] = True   # the line carries on past this note
                slur_depth = max(slur_depth + starts - stops, 0)
                if '<unpitched' in t or m['percussion']:
                    st = re.search(r'<display-step>(\w)</display-step>', t)
                    oc = re.search(r'<display-octave>(\d)</display-octave>',
                                   t)
                    nh = re.search(r'<notehead[^>]*>([a-z-]+)</notehead>',
                                   t)
                    hand = bool(re.search(
                        r'percussion|conga|bongo|timbale|shaker|cowbell'
                        r'|clave|guiro|maraca|tambourine|aux',
                        m['name'], re.I)) and not re.search(
                        r'drum|kit|batterie', m['name'], re.I)
                    midi = drum_midi(st.group(1), int(oc.group(1)),
                                     nh.group(1) if nh else 'normal',
                                     hand=hand) \
                        if st and oc else 38
                else:
                    st = re.search(r'<step>(\w)</step>', t).group(1)
                    al = re.search(r'<alter>(-?\d+)</alter>', t)
                    oc = int(re.search(r'<octave>(\d+)</octave>',
                                       t).group(1))
                    midi = (STEP[st] + (int(al.group(1)) if al else 0)
                            + (oc + 1) * 12 + transpose)
                q_on = q0 + on / div
                q_dur = dur / div
                if 'fermata' in art:
                    # time itself holds just before the note lets go
                    hq = q_on + q_dur - 1e-6
                    holds[hq] = max(holds.get(hq, 0.0),
                                    min(q_dur, 2.0) * 0.9)
                key = (voice, midi)
                if '<tie type="stop"/>' in t and key in carry:
                    i = carry[key]
                    events[i] = (events[i][0], events[i][1] + q_dur,
                                 events[i][2], events[i][3],
                                 {**events[i][4], **art})
                    if '<tie type="start"/>' not in t:
                        del carry[key]
                    continue
                events.append((q_on, q_dur, midi, gain, art))
                if '<tie type="start"/>' in t:
                    carry[key] = len(events) - 1
            barlen = div * 4 * tnum // tden
            q0 += (top if num == '0' else barlen) / div
        if wedge_open:                  # a hairpin nothing closed
            wedges.append((wedge_open[0], q0, wedge_open[1]))
        # a gliss or portamento rides toward the NEXT sounding pitch
        order = sorted(range(len(events)), key=lambda k: events[k][0])
        for oi, k in enumerate(order):
            ev = events[k]
            if ('gliss' in ev[4] or 'port' in ev[4]) \
                    and ev[2] is not None:
                for k2 in order[oi + 1:]:
                    nxt = events[k2]
                    if nxt[0] > ev[0] + 1e-9 and nxt[2] is not None:
                        ev[4]['slide_to'] = nxt[2] - ev[2]
                        break
        parts.append({'name': m['name'], 'program': m['program'],
                      'percussion': m['percussion'],
                      'sound': m.get('sound', ''), 'events': events,
                      'bars': bars, 'meter0': meter0 or (4, 4),
                      'length_q': q0, 'dyns': dyns, 'wedges': wedges})
    return {'parts': parts,
            'bars': parts[0]['bars'] if parts else {},
            'meter0': parts[0]['meter0'] if parts else (4, 4),
            'tempos': sorted(tempos.items()),
            'swings': sorted(swings.items()),
            'holds': sorted(holds.items())}


# ------------------------------------------------------------- schedule


def _warp(q, swings):
    """Swing as an honest time warp: inside a swung span, the second
    half of each swing unit starts at the ratio point instead of
    halfway. The unit is the beat for eighth swing, the half-beat
    for 16th swing."""
    ratio, unit = None, 1.0
    for at, r in swings:
        if at <= q + 1e-9:
            if r is None:
                ratio = None
            else:
                ratio, unit = r if isinstance(r, tuple) else (r, 1.0)
    if not ratio:
        return q
    base = math.floor(q / unit) * unit
    f = (q - base) / unit
    if f <= 0.5:
        f = f * (ratio / 0.5)
    else:
        f = ratio + (f - 0.5) * ((1 - ratio) / 0.5)
    return base + f * unit


def _sec_of(q, tempos, holds=()):
    tempos = tempos or [(0.0, 120.0)]
    if tempos[0][0] > 0:
        tempos = [(0.0, tempos[0][1])] + tempos
    s, prev_q, bpm = 0.0, 0.0, tempos[0][1]
    for at, t in tempos:
        if at >= q:
            break
        s += (at - prev_q) * 60.0 / bpm
        prev_q, bpm = at, t
    s += (q - prev_q) * 60.0 / bpm
    for hq, extra_q in holds:           # every fermata already passed
        if q > hq + 1e-9:
            hb = tempos[0][1]
            for at, t in tempos:
                if at > hq:
                    break
                hb = t
            s += extra_q * 60.0 / hb
    return s


def first_bar_seconds(path, printed_bar):
    """Seconds into the rendered audio where printed bar N first plays —
    repeats, voltas and fermatas included, because this is the player's
    own walk. None when the page has no such bar."""
    plan = parse_score(path)
    q = plan['bars'].get(printed_bar)
    if q is None:
        return None
    return _sec_of(q, plan['tempos'], plan.get('holds', ()))


def _seconds(plan):
    """Quarter positions -> seconds through the tempo map, swing warp
    first. Returns per part: [(sec_on, sec_dur, midi, gain, art)]."""
    holds = plan.get('holds', ())

    def sec_of(q):
        return _sec_of(q, plan['tempos'], holds)

    out = []
    for part in plan['parts']:
        ev = []
        for q_on, q_dur, midi, gain, art in part['events']:
            a = sec_of(_warp(q_on, plan['swings']))
            b = sec_of(_warp(q_on + q_dur, plan['swings']))
            ev.append((a, max(b - a, 0.03), midi, gain, art))
        out.append(ev)
    return out


# ---------------------------------------------------------------- synth

# harmonic recipes by GM program (1-based), nearest family wins;
# 'pluck' decays on its own, 'sustain' holds and releases
RECIPES = [
    (range(1, 9),    'pluck',   [1, .5, .33, .2, .14, .09, .06]),   # piano
    (range(9, 17),   'pluck',   [1, .08, .3, .05, .12]),            # mallets
    (range(17, 25),  'sustain', [1, .7, .5, .7, .4, .3]),           # organ
    (range(25, 33),  'pluck',   [1, .55, .35, .22, .12, .08]),      # guitar
    (range(33, 41),  'pluck',   [1, .45, .2, .08]),                 # bass
    (range(41, 53),  'sustain', [1, .7, .55, .4, .3, .22]),         # strings
    (range(53, 57),  'sustain', [1, .5, .25, .12]),                 # voice
    (range(57, 65),  'sustain', [1, .8, .7, .62, .5, .4, .3, .22]), # brass
    (range(65, 72),  'sustain', [1, .6, .75, .5, .3, .2, .12]),     # reeds
    (range(72, 81),  'sustain', [1, .35, .15, .06]),                # flutes
]


def _recipe(program):
    for rng, kind, harm in RECIPES:
        if program in rng:
            return kind, harm
    return 'sustain', [1, .6, .75, .5, .3, .2, .12]


def _wavetable(harmonics):
    tab = array('f', [0.0]) * TABLE
    for k, amp in enumerate(harmonics, 1):
        w = 2 * math.pi * k / TABLE
        for i in range(TABLE):
            tab[i] += amp * math.sin(w * i)
    peak = max(abs(x) for x in tab) or 1.0
    for i in range(TABLE):
        tab[i] /= peak
    return tab


def _add_note(L, R, t0, dur, freq, gain, tab, panl, panr):
    """A sustained voice: quick attack, hold, short release."""
    n = int(dur * SR)
    if n <= 0:
        return
    i0 = int(t0 * SR)
    step = freq * TABLE / SR
    atk = int(SR * 0.010)
    rel = int(SR * 0.045)
    total = min(n + rel, len(L) - i0)
    phase = 0.0
    for i in range(total):
        if i < atk:
            env = i / atk
        elif i > n:
            env = max(0.0, 1.0 - (i - n) / rel)
        else:
            env = 1.0
        s = tab[int(phase) & (TABLE - 1)] * env * gain
        j = i0 + i
        L[j] += s * panl
        R[j] += s * panr
        phase += step


def _add_pluck(L, R, t0, dur, freq, gain, tab, panl, panr):
    n = int(max(dur, 0.08) * SR)
    i0 = int(t0 * SR)
    if i0 + n > len(L):
        n = len(L) - i0
    step = freq * TABLE / SR
    atk = int(SR * 0.004)
    k = math.exp(math.log(0.002) / max(n - atk, 1))
    phase, env = 0.0, 1.0
    for i in range(n):
        if i < atk:
            e = (i / atk) if atk else 1.0
        else:
            env *= k
            e = env
        s = tab[int(phase) & (TABLE - 1)] * e * gain
        j = i0 + i
        L[j] += s * panl
        R[j] += s * panr
        phase += step


def _add_click(L, R, t0, gain, panl, panr, seed=1234):
    n = int(SR * 0.03)
    i0 = int(t0 * SR)
    if i0 + n > len(L):
        n = len(L) - i0
    x = seed
    for i in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        s = ((x / 0x3FFFFFFF) - 1.0) * gain * (1.0 - i / n) * 0.4
        L[i0 + i] += s * panl
        R[i0 + i] += s * panr


def render(listen_path, wav_path, only=None, tail=1.5, count_in=None,
           samples=None):
    """The listening document -> a stereo WAV. `only` filters part
    names (lowercased); `count_in` prepends that many bars of click,
    high tick on one, like a session. `samples` names a sample library
    (.sf2); with one, chartband plays real recorded instruments and
    this module's wavetable is only the no-library fallback. Returns
    (seconds, n_parts, n_notes, lead_seconds)."""
    plan = parse_score(listen_path,
                       only={o.lower().strip() for o in only}
                       if only else None)
    if not plan['parts']:
        raise SystemExit("chartaudio: no parts matched")
    if samples:
        import chartband
        return chartband.render_plan(plan, wav_path, samples,
                                     tail=tail, count_in=count_in)
    scheduled = _seconds(plan)
    lead = 0.0
    if count_in:
        n0, d0 = plan['meter0']
        qbpm = plan['tempos'][0][1] if plan['tempos'] else 120.0
        pulse = (4.0 / d0) * 60.0 / qbpm
        lead = n0 * count_in * pulse
        scheduled = [[(a + lead, d, mi, g, ar) for a, d, mi, g, ar in ev]
                     for ev in scheduled]
    end = max((a + d for ev in scheduled for a, d, _, _, _ in ev),
              default=0.0) + tail
    frames = int(end * SR)
    L = array('f', [0.0]) * frames
    R = array('f', [0.0]) * frames

    if count_in:
        for c in range(n0 * count_in):
            _add_tick(L, R, c * pulse,
                      1568.0 if c % n0 == 0 else 1047.0, 0.5)

    n_parts = len(plan['parts'])
    notes = 0
    for idx, (part, ev) in enumerate(zip(plan['parts'], scheduled)):
        pan = (-0.6 + 1.2 * idx / max(n_parts - 1, 1)) if n_parts > 1 else 0
        panl = math.cos((pan + 1) * math.pi / 4) * 1.2
        panr = math.sin((pan + 1) * math.pi / 4) * 1.2
        kind, harm = _recipe(part['program'])
        tab = _wavetable(harm)
        for a, d, midi, gain, art in ev:
            notes += 1
            if part['percussion'] or midi is None:
                _add_click(L, R, a, gain, panl, panr)
                continue
            # the fallback plays the page's marks too, plainly
            if 'stac' in art:
                d = max(d * 0.5, 0.05)
            if 'marc' in art:
                d, gain = max(d * 0.6, 0.05), gain * 1.25
            if 'acc' in art:
                gain = gain * 1.2
            if 'ghost' in art:
                gain = gain * 0.5
            freq = 440.0 * 2 ** ((midi - 69) / 12)
            g = gain ** 1.4 * 0.5
            if kind == 'pluck':
                _add_pluck(L, R, a, d, freq, g, tab, panl, panr)
            else:
                _add_note(L, R, a, d, freq, g, tab, panl, panr)

    peak = max(max(abs(x) for x in L), max(abs(x) for x in R)) or 1.0
    scale = 0.85 / peak                 # headroom on purpose
    with wave.open(wav_path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames_i = array('h', [0]) * (2 * frames)
        for i in range(frames):
            frames_i[2 * i] = int(max(-1, min(1, L[i] * scale)) * 32767)
            frames_i[2 * i + 1] = int(max(-1, min(1, R[i] * scale)) * 32767)
        w.writeframes(frames_i.tobytes())
    return end, n_parts, notes, lead


def _add_tick(L, R, t0, freq, gain):
    """One click of the count-in: a short sine with a hard decay."""
    n = min(int(SR * 0.05), len(L) - int(t0 * SR))
    i0 = int(t0 * SR)
    w = 2 * math.pi * freq / SR
    for i in range(n):
        s = math.sin(w * i) * (1 - i / n) ** 2 * gain
        L[i0 + i] += s
        R[i0 + i] += s


def to_mp3(wav_path, mp3_path):
    """WAV -> MP3 via ffmpeg. False (with the WAV intact) when absent."""
    from shutil import which
    if which('ffmpeg') is None:
        return False
    r = subprocess.run(['ffmpeg', '-y', '-hide_banner', '-i', wav_path,
                        '-codec:a', 'libmp3lame', '-qscale:a', '3',
                        mp3_path], capture_output=True)
    return r.returncode == 0 and os.path.exists(mp3_path)
