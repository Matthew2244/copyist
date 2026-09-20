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

# ---------------------------------------------------------------- parse


def _measures(body):
    return re.findall(r'<measure [^>]*?number="([^"]+)"[^>]*>(.*?)'
                      r'</measure>', body, re.S)


def _expand_repeats(ms):
    """Linearize our own repeat barlines: forward opens a segment, a
    backward with times=N plays the segment N times total."""
    out, seg_start = [], 0
    for num, m in ms:
        if '<repeat direction="forward"' in m:
            seg_start = len(out)
        out.append((num, m))
        bk = re.search(r'<repeat direction="backward"\s*'
                       r'times="(\d+)"', m)
        if bk:
            times = int(bk.group(1))
            seg = out[seg_start:]
            for _ in range(times - 1):
                out.extend(seg)
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
        meta[pid] = {'name': name.group(1) if name else pid,
                     'program': int(prog.group(1)) if prog else 1,
                     'percussion': bool(chan) and chan.group(1) == '10'}

    parts, tempos, swings = [], {}, {}
    for pid, body in re.findall(r'<part id="([^"]+)">(.*?)</part>',
                                xml, re.S):
        m = meta.get(pid, {'name': pid, 'program': 1, 'percussion': False})
        if only is not None and m['name'].lower().strip() not in only:
            continue
        div, tnum, tden = 24, 4, 4
        transpose = 0
        dyn_state = 80.0
        q0 = 0.0                        # quarters at the measure's start
        events = []
        carry = {}                      # (voice, midi) -> event index, for ties
        for num, meas in _expand_repeats(_measures(body)):
            dv = re.search(r'<divisions>(\d+)</divisions>', meas)
            if dv:
                div = int(dv.group(1))
            ts = re.search(r'<beats>(\d+)</beats>\s*'
                           r'<beat-type>(\d+)</beat-type>', meas)
            if ts:
                tnum, tden = int(ts.group(1)), int(ts.group(2))
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
                    sw = re.search(r'<swing>(.*?)</swing>', t, re.S)
                    if sw:
                        if '<straight/>' in sw.group(1):
                            swings[q0 + pos / div] = None
                        else:
                            f = re.search(r'<first>(\d+)</first>',
                                          sw.group(1))
                            s = re.search(r'<second>(\d+)</second>',
                                          sw.group(1))
                            if f and s:
                                fv, sv = int(f.group(1)), int(s.group(1))
                                swings[q0 + pos / div] = fv / (fv + sv)
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
                if '<rest' in t:
                    continue
                nd = re.search(r'dynamics="([\d.]+)"', t)
                gain = (float(nd.group(1)) if nd else dyn_state) / 100.0
                if gain <= 0:
                    continue            # a slash is an instruction
                if '<unpitched' in t or m['percussion']:
                    midi = None
                else:
                    st = re.search(r'<step>(\w)</step>', t).group(1)
                    al = re.search(r'<alter>(-?\d+)</alter>', t)
                    oc = int(re.search(r'<octave>(\d+)</octave>',
                                       t).group(1))
                    midi = (STEP[st] + (int(al.group(1)) if al else 0)
                            + (oc + 1) * 12 + transpose)
                q_on = q0 + on / div
                q_dur = dur / div
                key = (voice, midi)
                if '<tie type="stop"/>' in t and key in carry:
                    i = carry[key]
                    events[i] = (events[i][0], events[i][1] + q_dur,
                                 events[i][2], events[i][3])
                    if '<tie type="start"/>' not in t:
                        del carry[key]
                    continue
                events.append((q_on, q_dur, midi, gain))
                if '<tie type="start"/>' in t:
                    carry[key] = len(events) - 1
            barlen = div * 4 * tnum // tden
            q0 += (top if num == '0' else barlen) / div
        parts.append({'name': m['name'], 'program': m['program'],
                      'percussion': m['percussion'], 'events': events,
                      'length_q': q0})
    return {'parts': parts,
            'tempos': sorted(tempos.items()),
            'swings': sorted(swings.items())}


# ------------------------------------------------------------- schedule


def _warp(q, swings):
    """Swing as an honest time warp: inside a swung span, the second
    half of each beat starts at the ratio point instead of halfway."""
    ratio = None
    for at, r in swings:
        if at <= q + 1e-9:
            ratio = r
    if not ratio:
        return q
    f = q - math.floor(q)
    if f <= 0.5:
        f = f * (ratio / 0.5)
    else:
        f = ratio + (f - 0.5) * ((1 - ratio) / 0.5)
    return math.floor(q) + f


def _seconds(plan):
    """Quarter positions -> seconds through the tempo map, swing warp
    first. Returns per part: [(sec_on, sec_dur, midi, gain)]."""
    tempos = plan['tempos'] or [(0.0, 120.0)]
    if tempos[0][0] > 0:
        tempos = [(0.0, tempos[0][1])] + tempos

    def sec_of(q):
        s, prev_q, bpm = 0.0, 0.0, tempos[0][1]
        for at, t in tempos:
            if at >= q:
                break
            s += (at - prev_q) * 60.0 / bpm
            prev_q, bpm = at, t
        return s + (q - prev_q) * 60.0 / bpm

    out = []
    for part in plan['parts']:
        ev = []
        for q_on, q_dur, midi, gain in part['events']:
            a = sec_of(_warp(q_on, plan['swings']))
            b = sec_of(_warp(q_on + q_dur, plan['swings']))
            ev.append((a, max(b - a, 0.03), midi, gain))
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


def render(listen_path, wav_path, only=None, tail=1.5):
    """The listening document -> a stereo WAV. `only` filters part
    names (lowercased). Returns (seconds, n_parts, n_notes)."""
    plan = parse_score(listen_path,
                       only={o.lower().strip() for o in only}
                       if only else None)
    if not plan['parts']:
        raise SystemExit("chartaudio: no parts matched")
    scheduled = _seconds(plan)
    end = max((a + d for ev in scheduled for a, d, _, _ in ev),
              default=0.0) + tail
    frames = int(end * SR)
    L = array('f', [0.0]) * frames
    R = array('f', [0.0]) * frames

    n_parts = len(plan['parts'])
    notes = 0
    for idx, (part, ev) in enumerate(zip(plan['parts'], scheduled)):
        pan = (-0.6 + 1.2 * idx / max(n_parts - 1, 1)) if n_parts > 1 else 0
        panl = math.cos((pan + 1) * math.pi / 4) * 1.2
        panr = math.sin((pan + 1) * math.pi / 4) * 1.2
        kind, harm = _recipe(part['program'])
        tab = _wavetable(harm)
        for a, d, midi, gain in ev:
            notes += 1
            if midi is None:
                _add_click(L, R, a, gain, panl, panr)
                continue
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
    return end, n_parts, notes


def to_mp3(wav_path, mp3_path):
    """WAV -> MP3 via ffmpeg. False (with the WAV intact) when absent."""
    from shutil import which
    if which('ffmpeg') is None:
        return False
    r = subprocess.run(['ffmpeg', '-y', '-hide_banner', '-i', wav_path,
                        '-codec:a', 'libmp3lame', '-qscale:a', '3',
                        mp3_path], capture_output=True)
    return r.returncode == 0 and os.path.exists(mp3_path)
