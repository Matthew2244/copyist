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

def _mark_rx(pat):
    """'<staccato/>' -> the tag with any attributes an engraving hangs
    on it (<staccato default-x="0"/>); '<slide type="start"' -> that
    attribute anywhere inside the tag."""
    name = re.match(r'<([a-z-]+)', pat).group(1)
    attr = re.search(r'\s(\w[\w-]*="[^"]*")', pat)
    if attr:
        return re.compile('<' + name + r'\s[^>]*' + re.escape(attr.group(1)))
    return re.compile('<' + name + r'[\s/>]')


_ART_RX = [(_mark_rx(p), f) for p, f in _ART_MARKS]

# the rest of the books' small marks, as the player reads them
_MORE_MARKS = [('staccatissimo', ('stac',)), ('spiccato', ('stac',)),
               ('detached-legato', ('ten', 'stac')),
               ('breath-mark', ()), ('caesura', ())]

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


def _height(step, octave):
    return octave * 7 + 'CDEFGAB'.index(step)


def hand_midi(sound, step, octave, notehead):
    """A hand-percussion staff read by its own instrument: every note
    on a cowbell part is the cowbell, a triangle's x head is the muted
    stroke. One shared table gave a triangle part the cowbell (both
    print a triangle head on B5). None when the sound is not a hand
    instrument this knows."""
    s = (sound or '').lower()
    h = _height(step, octave)
    x = notehead in ('x', 'cross')
    if 'conga' in s:
        return 64 if h <= _height('F', 4) else (62 if x else 63)
    if 'bongo' in s and 'bell' not in s:
        return 60 if h >= _height('E', 5) else 61
    if 'timbale' in s:
        return 65 if h >= _height('D', 5) else 66
    if 'cowbell' in s:
        return 56
    if 'triangle' in s:
        return 80 if x else 81
    if 'agogo' in s:
        return 67 if h >= _height('A', 5) else 68
    if 'claves' in s:
        return 75
    if 'guiro' in s:
        return 73 if x else 74
    if 'wood-block' in s or 'woodblock' in s:
        return 76 if h >= _height('E', 5) else 77
    if 'maraca' in s:
        return 70
    if 'cabasa' in s:
        return 69
    if 'rattle.' in s:
        return 82
    if 'tambourine' in s:
        return 54
    return None


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
    # nearest staff position (the Sept 22 table split left this loop
    # reading a name that no longer existed; every engraved drum note
    # off the map crashed the band back to MuseScore)
    for (st, oc), cands in by_pos.items():
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



# the road-map signs, read from the playback attributes a score carries
# (<sound dalsegno=...>) or, as most engravings only print them, from
# the words and signs themselves
_RM_WORDS = [
    ('ds', re.compile(r'\bD\.?\s?S\.?(?=\s|$|\b)|dal\s+segno', re.I)),
    ('dc', re.compile(r'\bD\.?\s?C\.?(?=\s|$|\b)|da\s+capo', re.I)),
    ('tocoda', re.compile(r'\bto\s+coda\b', re.I)),
    ('fine', re.compile(r'^\s*fine\s*$', re.I)),
]


def roadmap_marks(m):
    """One measure -> the set of road-map marks it carries."""
    got = set()
    if re.search(r'<segno[\s/>]|<sound [^>]*segno=', m):
        got.add('segno')
    if re.search(r'<coda[\s/>]|<sound [^>]*coda=', m):
        got.add('coda')
    if re.search(r'<sound [^>]*dalsegno=', m):
        got.add('ds')
    if re.search(r'<sound [^>]*dacapo="yes"', m):
        got.add('dc')
    if re.search(r'<sound [^>]*tocoda=', m):
        got.add('tocoda')
    if re.search(r'<sound [^>]*fine=', m):
        got.add('fine')
    for w in re.findall(r'<words[^>]*>([^<]*)</words>', m):
        for kind, rx in _RM_WORDS:
            if rx.search(w):
                got.add(kind)
        if re.search(r'al\s+fine', w, re.I):
            got.add('alfine')
        if re.search(r'al\s+coda', w, re.I):
            got.add('alcoda')
    # "To Coda" also names a coda; the coda sign itself is the landing
    if 'tocoda' in got:
        got.discard('coda')
    return got


def _final_pass(ms):
    """A stretch played after a D.S. or D.C.: repeats are not taken
    again, and where there are endings the last one is played — how a
    band reads it unless the chart says otherwise."""
    out, i = [], 0
    last = {}
    for _n, m in ms:
        for k in re.findall(r'<ending number="(\d+)" type="start"', m):
            last[0] = max(last.get(0, 0), int(k))
    while i < len(ms):
        num, m = ms[i]
        em = re.search(r'<ending number="(\d+)" type="start"', m)
        if em and last and int(em.group(1)) < last[0]:
            k = int(em.group(1))
            while i < len(ms) and not re.search(
                    r'<ending number="%d" type="(?:stop|discontinue)"' % k,
                    ms[i][1]):
                i += 1
            i += 1
            continue
        out.append((num, m))
        i += 1
    return out


def expand_roadmap(ms, marks=None):
    """The whole walk a player takes: repeats and endings first, then a
    D.S. back to the sign (or a D.C. to the top), through once more
    without repeats, and out — at "To Coda" over to the coda, or at
    Fine to a stop. A chart with no road map is just its repeats."""
    marks = marks or [roadmap_marks(m) for _n, m in ms]
    jump = next((i for i, mk in enumerate(marks)
                 if 'ds' in mk or 'dc' in mk), None)
    if jump is None:
        return _expand_repeats(ms)
    is_ds = 'ds' in marks[jump]
    start = 0
    if is_ds:
        start = next((i for i, mk in enumerate(marks[:jump + 1])
                      if 'segno' in mk), 0)
    first = _expand_repeats(ms[:jump + 1])
    tocoda = next((i for i in range(start, jump + 1)
                   if 'tocoda' in marks[i]), None)
    fine = next((i for i in range(start, jump + 1)
                 if 'fine' in marks[i]), None)
    coda = next((i for i in range(jump + 1, len(ms))
                 if 'coda' in marks[i] or 'tocoda' not in marks[i]
                 and re.search(r'<coda[\s/>]', ms[i][1])), None)
    if tocoda is not None and 'alfine' not in marks[jump]:
        second = _final_pass(ms[start:tocoda + 1])
        rest = _expand_repeats(ms[coda:]) if coda is not None else \
            _expand_repeats(ms[jump + 1:])
        return first + second + rest
    if fine is not None:
        return first + _final_pass(ms[start:fine + 1])
    # a D.S. with nowhere marked to leave: once more to the jump, then on
    second = _final_pass(ms[start:jump + 1])
    return first + second + _expand_repeats(ms[jump + 1:])

# a dynamic mark's level when the document gives no playback value
_LEVEL = {'pppp': 12, 'ppp': 23, 'pp': 40, 'p': 54, 'mp': 71, 'mf': 89,
          'f': 106, 'ff': 123, 'fff': 127, 'ffff': 127, 'fffff': 127,
          'ffffff': 127, 'fp': 54, 'sfp': 54, 'sfpp': 40, 'pf': 106,
          'n': 5}
_HIT_MARKS = {'sf', 'sfz', 'sffz', 'fz', 'rf', 'rfz', 'sfp', 'sfpp',
              'fp', 'sfzp'}

_NAT = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
_ACC_MARK = {'sharp': 1, 'flat': -1, 'natural': 0, 'double-sharp': 2,
             'sharp-sharp': 2, 'flat-flat': -2}


def trill_step(t, fifths):
    """How far above its note a trill goes, in semitones, read the way
    a player reads the page: a target named in parentheses is exact; an
    accidental over the mark alters the next letter up; a bare mark
    takes the next letter up in the key — E in C trills a half step,
    D a whole step."""
    st = re.search(r'<step>(\w)</step>', t)
    if not st:
        return 2
    step = st.group(1)
    al = re.search(r'<alter>(-?\d+)</alter>', t)
    oc = int(re.search(r'<octave>(\d+)</octave>', t).group(1))
    main = _NAT[step] + (int(al.group(1)) if al else 0) + (oc + 1) * 12
    to = re.search(r'<other-ornament[^>]*>\(([A-G])(bb|b|#|x)?(\d)\)', t)
    if to:
        acc = {'bb': -2, 'b': -1, '#': 1, 'x': 2}.get(to.group(2), 0)
        aux = _NAT[to.group(1)] + acc + (int(to.group(3)) + 1) * 12
        return aux - main
    letters = 'CDEFGAB'
    up = letters[(letters.index(step) + 1) % 7]
    oct_up = oc + (1 if up == 'C' else 0)
    am = re.search(r'<accidental-mark[^>]*>([\w-]+)</accidental-mark>', t)
    if am and am.group(1) in _ACC_MARK:
        alt = _ACC_MARK[am.group(1)]
    else:
        sharps, flats = 'FCGDAEB', 'BEADGCF'
        alt = (1 if fifths > 0 and up in sharps[:fifths] else
               -1 if fifths < 0 and up in flats[:-fifths] else 0)
    return _NAT[up] + alt + (oct_up + 1) * 12 - main


def _note_midi(t, m, transpose):
    """One <note>'s sounding key: a percussion head decoded through the
    kit or hand-percussion table (chosen by the part's name), anything
    else from its written pitch plus the part's transposition."""
    if '<unpitched' in t or m['percussion']:
        st = re.search(r'<display-step>(\w)</display-step>', t)
        oc = re.search(r'<display-octave>(\d)</display-octave>', t)
        nh = re.search(r'<notehead[^>]*>([a-z-]+)</notehead>', t)
        # the part's instrument sound says it even when the writer's
        # label does not: a cowbell labelled "bell" is still a cowbell
        hand_rx = (r'percussion|conga|bongo|timbale|shaker|cowbell'
                   r'|clave|guiro|maraca|tambourine|aux')
        hand = bool(re.search(hand_rx, m['name'], re.I)
                    or re.search(hand_rx, m.get('sound', ''), re.I)) \
            and not re.search(r'drum|kit|batterie', m['name'], re.I) \
            and not m.get('sound', '').startswith('drum.group')
        if st and oc:
            own = hand_midi(m.get('sound', ''), st.group(1),
                            int(oc.group(1)), nh.group(1) if nh else
                            'normal')
            if own is not None:
                return own
        return drum_midi(st.group(1), int(oc.group(1)),
                         nh.group(1) if nh else 'normal',
                         hand=hand) if st and oc else 38
    st = re.search(r'<step>(\w)</step>', t).group(1)
    al = re.search(r'<alter>(-?\d+)</alter>', t)
    oc = int(re.search(r'<octave>(\d+)</octave>', t).group(1))
    return (STEP[st] + (int(al.group(1)) if al else 0)
            + (oc + 1) * 12 + transpose)


def parse_score(path, only=None):
    """Our emitted listening document -> a playable plan:
    parts: [{name, program, percussion, events: [(q_on, q_dur, midi,
    gain)]}] with q in quarter notes from the top; tempos: [(q, qbpm)];
    swings: [(q, ratio_or_None)]."""
    # an engraving's pretty-printing (`<chord />`, as every Sibelius
    # export writes it) must read exactly like our own compact form
    xml = re.sub(r'\s+/>', '/>', open(path, encoding='utf-8').read())
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
    # the road map is the band's, not one part's: a D.S. printed only on
    # the first part (our listening document carries words there alone)
    # sends everyone back to the sign
    road = None
    for _pid, body in re.findall(r'<part id="([^"]+)">(.*?)</part>',
                                 xml, re.S):
        mk = [roadmap_marks(m) for _n, m in _measures(body)]
        road = mk if road is None else [
            a | b for a, b in zip(road, mk)] + road[len(mk):]
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
        pend_grace = {}                 # voice -> grace <note> texts
        pend_hit = False                # a sforzando waits for its note
        pizz = False                    # "pizz." until "arco"
        mute = None                     # "harmon mute" until "open"
        arco = False                    # "arco" until "pizz." — for the
        # upright bass, plucked unless the page says to bow
        pedals = []                     # (q, 'start'|'stop'|'change')
        pend_trem = {}                  # voice -> event index of a
                                        # two-note tremolo's first note
        fifths = 0
        for num, meas in expand_roadmap(_measures(body), road):
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
            kf = re.search(r'<fifths>(-?\d+)</fifths>', meas)
            if kf:
                fifths = int(kf.group(1))
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
            last_voice = '1'
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
                    mk = re.search(r'<dynamics[^>]*>\s*<([a-z-]+)', t)
                    if sd:
                        dyn_state = float(sd.group(1))
                        dyns.append((q0 + pos / div, dyn_state))
                    elif mk:
                        # an engraving's mark with no playback value (the
                        # Sibelius books never carry one): read the mark
                        # the way a player does. A sforzando is one hit,
                        # not a new level; fp and sfp hit, then drop.
                        word = mk.group(1)
                        if word in _HIT_MARKS:
                            pend_hit = True
                        if word in _LEVEL:
                            dyn_state = float(_LEVEL[word])
                            dyns.append((q0 + pos / div, dyn_state))
                    pd = re.search(r'<pedal [^>]*type="(\w+)"', t)
                    if pd:
                        pedals.append((q0 + pos / div, pd.group(1)))
                    for w in re.findall(r'<words[^>]*>([^<]*)</words>', t):
                        if re.match(r'\s*pizz', w, re.I):
                            pizz, arco = True, False
                        elif re.match(r'\s*arco', w, re.I):
                            pizz, arco = False, True
                        elif re.match(r'\s*ord', w, re.I):
                            pizz = False
                        if re.match(r'\s*(open|senza sord)', w, re.I):
                            mute = None
                        elif re.search(r'mute|con sord', w, re.I):
                            import chartband as _cb
                            mute = _cb.mute_kind(w)
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
                    # a grace takes no written time: it is played
                    # just ahead of the note it leans on (below)
                    gv = re.search(r'<voice>(\d+)</voice>', t)
                    if '<chord/>' not in t:
                        pend_grace.setdefault(
                            gv.group(1) if gv else '1', []).append(t)
                    continue
                d = re.search(r'<duration>(\d+)</duration>', t)
                if not d:
                    continue
                dur = int(d.group(1))
                voice = re.search(r'<voice>(\d+)</voice>', t)
                chorded = bool(re.search(r'<chord\s*/>', t))
                if voice:
                    voice = voice.group(1)
                elif chorded:
                    voice = last_voice      # a chord member's voice is
                                            # the note it stacks on
                else:
                    voice = '1'
                if not chorded:
                    last_voice = voice
                on = last_on.get(voice, pos) if chorded else pos
                if not chorded:
                    last_on[voice] = pos
                    pos += dur
                    top = max(top, pos)
                graces = ([] if chorded else
                          pend_grace.pop(voice, []))
                if '<rest' in t or '<cue/>' in t \
                        or re.search(r'<notehead[^>]*>slash<', t):
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
                for rx, flag in _ART_RX:
                    if rx.search(t):
                        art[flag] = True
                for tag, flags in _MORE_MARKS:
                    if re.search('<' + tag + r'[\s/>]', t):
                        for fl in flags:
                            art[fl] = True
                if pend_hit:
                    art['acc'] = True
                    pend_hit = False
                if pizz:
                    art['pizz'] = True
                if arco:
                    art['arco'] = True
                if mute:
                    art['mute'] = mute
                if 'trill' in art:
                    art['trill_step'] = trill_step(t, fifths)
                ts1 = re.search(r'<tremolo type="single">(\d)', t)
                if ts1:
                    art['trem'] = int(ts1.group(1))
                if '<notehead parentheses="yes"' in t:
                    art['ghost'] = True
                starts = len(re.findall(r'<slur [^>]*type="start"', t))
                stops = len(re.findall(r'<slur [^>]*type="stop"', t))
                if slur_depth + starts - stops > 0:
                    art['leg'] = True   # the line carries on past this note
                slur_depth = max(slur_depth + starts - stops, 0)
                midi = _note_midi(t, m, transpose)
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
                # graces: a quick crushed run landing on the beat, each
                # a tenth of a quarter, a little under the main note
                gq = 0.1
                for gi, gt in enumerate(graces):
                    g_on = q_on - (len(graces) - gi) * gq
                    if g_on >= 0:
                        events.append((g_on, gq * 0.9,
                                       _note_midi(gt, m, transpose),
                                       gain * 0.85, {}))
                if '<tremolo type="stop"' in t and voice in pend_trem:
                    # the second note of a fingered tremolo: the first
                    # note alternates with it for both notes' time
                    i = pend_trem.pop(voice)
                    q1, d1, m1, g1, a1 = events[i]
                    events[i] = (q1, d1 + q_dur, m1, g1,
                                 {**a1, 'trill': True,
                                  'trill_step': midi - m1})
                    continue
                if '<tremolo type="start"' in t:
                    pend_trem[voice] = len(events)
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
        if pedals:
            # the sustain pedal holds what is struck while it is down;
            # a fresh Ped. with no release (how many engravings write it)
            # is a change: up and straight back down
            downs, open_q = [], None
            for q, kind in sorted(pedals):
                if open_q is not None:
                    downs.append((open_q, q))
                    open_q = None
                if kind in ('start', 'change'):
                    open_q = q
            if open_q is not None:
                downs.append((open_q, q0))
            for i, ev in enumerate(events):
                for d0, d1 in downs:
                    if d0 - 1e-6 <= ev[0] < d1:
                        if d1 - ev[0] > ev[1]:
                            events[i] = (ev[0], d1 - ev[0], ev[2], ev[3],
                                         {**ev[4], 'ped': True})
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
           samples=None, on_progress=None):
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
                                     tail=tail, count_in=count_in,
                                     on_progress=on_progress)
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
        if on_progress:
            on_progress(idx / max(n_parts, 1),
                        f"playing in {part['name']}")
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
