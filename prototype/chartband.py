#!/usr/bin/env python3
"""chartband — the band that plays the page, on recorded instruments.

chartaudio parses the listening document and owns the fallback synth;
this module is the performance. It takes the parsed plan and a sample
library (.sf2 read by sf2.py) and renders every part the way a player
reads the ink: dynamics are velocity, brightness and level together;
hairpins swell through held notes; staccato clips, tenuto rings,
accents and marcato hit harder and brighter; scoops and plops bend
into the pitch, falls and doits bend out of it; ghosts duck dark
behind the beat; slurred lines connect without re-attack; fermatas
hold time itself (chartaudio's clock does that part). The drum part
plays the real kit — every staff position decodes to its GM voice, and
an open hi-hat chokes the moment the closed one steps on it, because
the library says they share an exclusive class.

Seating and the room: parts spread across the stage the way the score
lists them, and a small Schroeder room sits behind the band with
per-family sends — horns and voices wetter, bass and kick nearly dry.
The reverb runs at half rate on the send bus (a room tail has no
business above 11 kHz) which keeps pure Python honest about time.
"""
import math
import os
import wave
from array import array

import chartaudio
import sf2 as sf2mod
import sfz as sfzmod

# The band map: instrument sound-id fragments -> SFZ programs on the
# shelf, per articulation. 'sus' is the default; 'stac' serves both
# staccato and marcato when the library recorded real short takes.
# Every entry is a recorded player under an open license (CC0/CC-BY,
# receipts in the research notes, 2026-09-20). Anything unmapped falls
# to the GM SoundFont on the shelf, and that falls to the synth.
_V = 'VSCO2-CE-SFZ/'
_SFZ_VOICES = (
    (('drum.group',),
     {'sus': 'VirtuosityDrums/Programs/02-full-kit.sfz'}),
    (('pluck.bass.acoustic', 'strings.contrabass'),
     {'sus': 'Meatbass/Programs/pizz_six.sfz'}),
    (('pluck.bass',),
     {'sus': 'Bass-black-and-blue-basses/Programs/'
             '05-darkblack_pluck.sfz',
      'stac': 'Bass-black-and-blue-basses/Programs/'
              '09-darkblack_stac.sfz',
      'ghost': 'Bass-black-and-blue-basses/Programs/'
               '07-darkblack_ghost.sfz'}),
    (('keyboard.piano.electric',),
     {'sus': 'EPianos/Wurlitzer EP200/Wurlitzer EP200.sfz'}),
    (('keyboard.piano', 'keyboard.harpsichord', 'keyboard.celesta'),
     {'sus': 'Salamander/SalamanderGrandPianoV3.sfz'}),
    (('keyboard.organ',),
     {'sus': 'Organ-DrawbarOrganEmulation/'
             'DrawbarOrganEmulation-20190712.sfz'}),
    (('pluck.guitar',),
     {'sus': 'BlackAndGreenGuitars/Programs/04-green_twang.sfz',
      'stac': 'BlackAndGreenGuitars/Programs/05-green_staccato.sfz'}),
    (('saxophone.alto', 'saxophone.soprano'),
     {'sus': 'Weresax/Programs/Sax.sfz'}),
    (('saxophone.baritone',),
     {'sus': 'BearSax/Programs/2-solo-poly.sfz'}),
    (('brass.trumpet',),
     {'sus': _V + 'TrumpetSusVib.sfz', 'stac': _V + 'TrumpetStac.sfz'}),
    (('brass.trombone',),
     {'sus': _V + 'TromboneSus.sfz', 'stac': _V + 'TromboneStac.sfz'}),
    (('brass.french-horn',),
     {'sus': _V + 'FHornSus.sfz', 'stac': _V + 'FHornStac.sfz'}),
    (('brass.tuba',),
     {'sus': _V + 'TubaSus.sfz', 'stac': _V + 'TubaStac.sfz'}),
    (('flutes.flute.piccolo',),
     {'sus': _V + 'PiccoloSus.sfz', 'stac': _V + 'PiccoloStac.sfz'}),
    (('flutes.flute', 'flutes.recorder'),
     {'sus': _V + 'FluteSusVib.sfz', 'stac': _V + 'FluteStac.sfz'}),
    (('reed.clarinet',),
     {'sus': _V + 'ClarinetSus.sfz', 'stac': _V + 'ClarinetStac.sfz'}),
    (('reed.oboe', 'reed.english-horn',),
     {'sus': _V + 'OboeSusVib.sfz', 'stac': _V + 'OboeStac.sfz'}),
    (('reed.bassoon',),
     {'sus': _V + 'BassoonVib.sfz', 'stac': _V + 'BassoonStac.sfz'}),
    (('strings.violin',),
     {'sus': _V + 'SViolinVib.sfz', 'stac': _V + 'SViolinSpic.sfz'}),
    (('strings.viola',),
     {'sus': _V + 'ViolaEnsSusVib.sfz',
      'stac': _V + 'ViolaEnsSpic.sfz'}),
    (('strings.cello',),
     {'sus': _V + 'CelloEnsSusVib.sfz',
      'stac': _V + 'CelloEnsSpic.sfz'}),
    (('strings.group',),
     {'sus': _V + 'ViolinEnsSusVib.sfz',
      'stac': _V + 'ViolinEnsSpic.sfz'}),
    (('pitched-percussion.glockenspiel',),
     {'sus': _V + 'Glockenspiel.sfz'}),
    (('pitched-percussion.marimba',), {'sus': _V + 'Marimba.sfz'}),
    (('pitched-percussion.xylophone',), {'sus': _V + 'Xylophone.sfz'}),
    (('pitched-percussion.tubular-bells',),
     {'sus': _V + 'TubularBells.sfz'}),
    (('drum.timpani',), {'sus': _V + 'Timpani.sfz'}),
    (('pluck.harp',), {'sus': _V + 'Harp.sfz'}),
)


class Shelf:
    """Everything the band can pick up: the SFZ voices on disk, the GM
    SoundFont floor, and a cache so a library parses once per render."""

    def __init__(self, path):
        self.dir = None
        self.sf2 = None
        self._cache = {}
        if os.path.isdir(path):
            self.dir = path
            import glob as _g
            floors = sorted(_g.glob(os.path.join(path, '*.sf2')))
            if floors:
                self.sf2 = sf2mod.SoundFont(floors[0])
        else:
            self.sf2 = sf2mod.SoundFont(path)

    def _load(self, rel):
        if rel in self._cache:
            return self._cache[rel]
        inst = None
        p = os.path.join(self.dir, rel)
        if os.path.exists(p):
            try:
                inst = sfzmod.SfzInstrument(p)
            except Exception:
                inst = None
        self._cache[rel] = inst
        return inst

    def voice(self, sound_id, percussion):
        """The articulation set for this chair: {'sus': inst, ...} or
        None to use the GM floor."""
        if not self.dir:
            return None
        sid = (sound_id or '').lower()
        if percussion and 'drum.group' not in sid:
            sid = 'drum.group'
        for frags, variants in _SFZ_VOICES:
            if any(f in sid for f in frags):
                out = {}
                for k, rel in variants.items():
                    inst = self._load(rel)
                    if inst is not None and inst.regions:
                        out[k] = inst
                if out:
                    return out
        return None


def _hash01(*xs):
    """A deterministic 0..1 from note identity — humanization that
    rebuilds byte-identical."""
    h = 2166136261
    for x in xs:
        for b in str(x).encode():
            h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h / 0xFFFFFFFF

# GM program (1-based) -> family; family -> (room send, detache)
_FAMILIES = [
    (range(1, 9), 'piano'), (range(9, 17), 'mallet'),
    (range(17, 25), 'organ'), (range(25, 33), 'guitar'),
    (range(33, 41), 'bass'), (range(41, 53), 'strings'),
    (range(53, 57), 'voice'), (range(57, 65), 'brass'),
    (range(65, 73), 'reed'), (range(73, 81), 'flute'),
]
_SEND = {'piano': .12, 'mallet': .16, 'organ': .08, 'guitar': .10,
         'bass': .04, 'strings': .22, 'voice': .24, 'brass': .18,
         'reed': .16, 'flute': .16, 'synth': .12, 'drums': .10}
_BREATHERS = {'brass', 'reed', 'flute', 'voice', 'strings'}


def _family(program, percussion):
    if percussion:
        return 'drums'
    for rng, fam in _FAMILIES:
        if program in rng:
            return fam
    return 'synth'


def _dyn_curve(part):
    """A function q -> dynamics (the 0-1ish gain scale), built from the
    part's dynamic timeline and its hairpins. Between a wedge's ends
    the value walks from the level at its start to the next spoken
    dynamic at or after its stop — or 30% up/down when the writer left
    the arrival unsaid, which is what a player would do."""
    dyns = part.get('dyns') or []
    wedges = part.get('wedges') or []

    def level_at(q):
        v = None
        for at, val in dyns:
            if at <= q + 1e-9:
                v = val
        return (v if v is not None else 80.0) / 100.0

    def target_after(q, kind, start):
        for at, val in dyns:
            if at >= q - 1e-9:
                return val / 100.0
        return start * (1.3 if kind == 'cresc' else 0.7)

    def f(q):
        for q0, q1, kind in wedges:
            if q0 - 1e-9 <= q <= q1 + 1e-9 and q1 > q0:
                a = level_at(q0)
                b = target_after(q1, kind, a)
                return a + (b - a) * (q - q0) / (q1 - q0)
        return level_at(q)
    return f


def _shape(art, d, vel, fam):
    """The page's marks -> what the player does: length, weight,
    brightness, and pitch/amp curves. Returns (d, vel, brightness,
    bend, amps)."""
    bend = amps = None
    bright = 1.0
    if 'ghost' in art:
        vel *= 0.5
        bright *= 0.6
    if 'acc' in art:
        vel *= 1.25
        bright *= 1.12
    if 'marc' in art:
        vel *= 1.35
        d = max(d * 0.55, 0.06)
        bright *= 1.2
    if 'stac' in art:
        d = max(min(d * 0.45, 0.5), 0.06)
    elif 'ten' not in art and 'leg' not in art and fam in _BREATHERS:
        d = max(d * 0.93, 0.05)         # air between unslurred notes
    if 'trill' in art:
        # alternate with the upper neighbor, easing in like a player:
        # whole step unless the mark carries an accidental
        step = 1.0 if 'trill_half' in art else 2.0
        bend, t, up, period = [(0.0, 0.0)], 0.12, False, 0.075
        while t < d - 0.02:
            up = not up
            bend.append((t, step if up else 0.0))
            bend.append((min(t + period, d), step if up else 0.0))
            t += period
        bend.append((d, 0.0))
    if 'slide_to' in art and ('gliss' in art or 'port' in art):
        delta = float(art['slide_to'])
        if 'port' in art:               # the whole note leans over
            bend = [(0.0, 0.0), (d * 0.35, 0.0), (d, delta)]
        else:                           # gliss: the tail slides
            slide = min(0.35, d * 0.45)
            bend = [(0.0, 0.0), (d - slide, 0.0), (d, delta)]
    if 'scoop' in art:
        bend = [(0.0, -2.5), (min(0.15, d * 0.4), 0.0)]
    if 'plop' in art:
        bend = [(0.0, 6.0), (min(0.07, d * 0.3), 0.0)]
    if 'fall' in art:
        fl = min(0.45, d * 0.5)
        bend = [(0.0, 0.0), (d - fl, 0.0), (d, -7.0)]
        amps = [(0.0, 1.0), (d - fl, 1.0), (d, 0.15)]
    if 'doit' in art:
        ext = min(0.22, max(d * 0.4, 0.12))
        bend = [(0.0, 0.0), (d, 0.0), (d + ext, 6.0)]
        amps = [(0.0, 1.0), (d, 1.0), (d + ext, 0.1)]
        d += ext
    return d, min(max(vel, 1.0), 127.0), bright, bend, amps


_HATS = {42, 44, 46}                     # one hi-hat, three voices


def _choke_map(shelf, part, events):
    """Effective sounding length per drum event, in quarters: to the
    next onset of the same exclusive family (the closed hat steps on
    the open one), else the sample's own natural life. The hi-hat rule
    is GM law and applies whichever engine plays the kit; a SoundFont
    kit adds its own exclusive classes on top."""
    classes = {}
    if shelf.sf2 is not None:
        preset = shelf.sf2.preset(128, max(part['program'] - 1, 0))
        if preset is not None:
            for i, (_q, _d, midi, _g, _a) in enumerate(events):
                if midi not in classes:
                    classes[midi] = sf2mod.exclusive_class(
                        preset, int(midi), 100)
    by_class = {}
    for i, (q_on, _d, midi, _g, _a) in enumerate(events):
        c = 'hat' if midi in _HATS else classes.get(midi, 0)
        if c:
            by_class.setdefault(c, []).append((q_on, i))
    chokes = {}
    for c, lst in by_class.items():
        lst.sort()
        for (q, i), (q2, _j) in zip(lst, lst[1:]):
            chokes[i] = q2 - q
    return chokes


def _variant(voice, art):
    """Which recorded take plays this note: the library's own staccato
    for short marks, its ghost set for ghosts, sustain otherwise."""
    if voice is None:
        return None
    if ('stac' in art or 'marc' in art) and 'stac' in voice:
        return voice['stac']
    if 'ghost' in art and 'ghost' in voice:
        return voice['ghost']
    return voice.get('sus')


def render_plan(plan, wav_path, sf_path, tail=2.0, count_in=None):
    """The parsed plan -> a stereo WAV through the sample shelf.
    sf_path may be the shelf directory (SFZ voices per instrument,
    the GM SoundFont as the floor) or a single .sf2. Mirrors
    chartaudio.render's return: (seconds, n_parts, n_notes,
    lead_seconds)."""
    SR = chartaudio.SR
    shelf = Shelf(sf_path)
    holds = plan.get('holds', ())
    swings = plan['swings']
    tempos = plan['tempos']

    def sec_of(q):
        return chartaudio._sec_of(chartaudio._warp(q, swings),
                                  tempos, holds)

    lead = 0.0
    n0, d0 = plan['meter0']
    if count_in:
        qbpm = tempos[0][1] if tempos else 120.0
        pulse = (4.0 / d0) * 60.0 / qbpm
        lead = n0 * count_in * pulse

    # each chair's players, and the section spread: chairs sharing one
    # sound (four trumpets) sit a few cents and milliseconds apart, so
    # a section reads as people, not one sample times four
    n_parts = len(plan['parts'])
    voices, detunes = [], []
    sound_count = {}
    for part in plan['parts']:
        sid = part.get('sound', '')
        nth = sound_count.get(sid, 0)
        sound_count[sid] = nth + 1
        voices.append(shelf.voice(sid, part['percussion']))
        detunes.append(((nth % 4) - 1.5) * 0.04 if sid else 0.0)

    jobs = []    # (t, dur, idx, key, vel, bright, bend, amps, fam, art)
    notes = 0
    for idx, part in enumerate(plan['parts']):
        fam = _family(part['program'], part['percussion'])
        dyn = _dyn_curve(part)
        events = part['events']
        chokes = _choke_map(shelf, part, events) \
            if part['percussion'] else {}
        for i, (q_on, q_dur, midi, gain, art) in enumerate(events):
            a = sec_of(q_on) + lead
            b = sec_of(q_on + q_dur) + lead
            d = max(b - a, 0.03)
            g0 = dyn(q_on)
            g1 = dyn(q_on + q_dur)
            if abs(g0 - gain) > 0.005 and not part.get('wedges'):
                g0 = gain               # a note's own mark wins
            vel = g0 * 90.0
            # humanization, deterministic: nobody plays on the grid,
            # and nobody plays two notes at the same weight
            h = _hash01(idx, i, midi)
            a += (h - 0.5) * (0.006 if part['percussion'] else 0.016)
            a = max(a, 0.0)
            vel *= 0.96 + 0.08 * _hash01(idx, midi, i)
            if part['percussion']:
                nat = chokes.get(i)
                if nat is not None:
                    ns = sec_of(q_on + nat) - sec_of(q_on)
                    d = min(max(ns - 0.004, 0.02), 8.0)
                else:
                    d = 8.0
                dd, vel, bright, bend, amps = _shape(art, d, vel, fam)
            else:
                dd, vel, bright, bend, amps = _shape(art, d, vel, fam)
                if amps is None and abs(g1 - g0) > 0.02 and g0 > 0:
                    amps = [(0.0, 1.0), (dd, g1 / g0)]   # the hairpin
            jobs.append((a, dd, idx, midi, vel, bright, bend, amps,
                         fam, art))
            notes += 1

    end = max((a + d for a, d, *_ in jobs), default=0.0) + tail
    frames = int(end * SR)
    L = array('f', bytes(4 * frames))
    R = array('f', bytes(4 * frames))
    wetL = array('f', bytes(4 * frames))
    wetR = array('f', bytes(4 * frames))

    if count_in:
        for c in range(n0 * count_in):
            chartaudio._add_tick(L, R, c * pulse,
                                 1568.0 if c % n0 == 0 else 1047.0, 0.5)

    for a, d, idx, key, vel, bright, bend, amps, fam, art in jobs:
        part = plan['parts'][idx]
        v = int(round(min(max(vel, 1.0), 127.0)))
        res = None
        inst = _variant(voices[idx], art)
        if inst is not None:
            res = inst.render_note(int(key), v, d, SR, bend=bend,
                                   brightness=bright, amps=amps,
                                   detune=detunes[idx])
        if res is None and shelf.sf2 is not None:
            if part['percussion']:
                res = sf2mod.render_note(
                    shelf.sf2, 128, max(part['program'] - 1, 0),
                    int(key), v, d, SR, bend=bend, brightness=bright,
                    amps=amps, detune=detunes[idx])
            else:
                res = sf2mod.render_note(
                    shelf.sf2, 0, max(part['program'] - 1, 0),
                    int(key), v, d, SR, bend=bend, brightness=bright,
                    amps=amps, detune=detunes[idx])
        if res is None:
            continue
        nl, nr = res
        pan = (-0.6 + 1.2 * idx / max(n_parts - 1, 1)) \
            if n_parts > 1 else 0.0
        gl = math.cos((pan + 1) * math.pi / 4) * 1.1
        gr = math.sin((pan + 1) * math.pi / 4) * 1.1
        i0 = int(a * SR)
        send = _SEND[fam]
        room = min(len(nl), frames - i0)
        for i in range(room):
            sl = nl[i] * gl
            sr_ = nr[i] * gr
            j = i0 + i
            L[j] += sl
            R[j] += sr_
            wetL[j] += sl * send
            wetR[j] += sr_ * send

    _room(L, R, wetL, wetR, SR)

    peak = max(max(abs(x) for x in L), max(abs(x) for x in R)) or 1.0
    scale = 0.85 * 32767.0 / peak
    with wave.open(wav_path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        out = array('h', bytes(4 * frames))
        for i in range(frames):
            out[2 * i] = int(max(-32767.0, min(32767.0, L[i] * scale)))
            out[2 * i + 1] = int(max(-32767.0,
                                     min(32767.0, R[i] * scale)))
        w.writeframes(out.tobytes())
    return end, n_parts, notes, lead


def _room(L, R, wetL, wetR, sr):
    """A small hall behind the band: Freeverb-shaped combs and
    allpasses run at half rate on the send bus, mixed back in. Half
    rate is a choice, not a corner — a room tail is dark."""
    n = len(L)
    h = n // 2
    if h < 4:
        return
    for src, dst, tunings in ((wetL, L, (1116, 1188, 1277, 1356)),
                              (wetR, R, (1139, 1211, 1300, 1379))):
        half = array('f', bytes(4 * h))
        for i in range(h):
            half[i] = (src[2 * i] + src[2 * i + 1]) * 0.5
        acc = array('f', bytes(4 * h))
        for delay in tunings:
            d = delay // 2
            buf = array('f', bytes(4 * d))
            filt = 0.0
            pos = 0
            for i in range(h):
                y = buf[pos]
                filt = y * 0.75 + filt * 0.25       # damped tail
                buf[pos] = half[i] + filt * 0.82
                acc[i] += y
                pos += 1
                if pos == d:
                    pos = 0
        for delay in (556, 441):
            d = delay // 2
            buf = array('f', bytes(4 * d))
            pos = 0
            for i in range(h):
                b = buf[pos]
                x = acc[i]
                buf[pos] = x + b * 0.5
                acc[i] = b - x * 0.5
                pos += 1
                if pos == d:
                    pos = 0
        for i in range(h - 1):
            dst[2 * i] += acc[i] * 0.30
            dst[2 * i + 1] += (acc[i] + acc[i + 1]) * 0.15
