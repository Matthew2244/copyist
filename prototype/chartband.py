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
    # the upright plays plucked; "arco" on the page picks up the bow —
    # the orchestra's own contrabass takes, sustained, short and
    # tremolo
    (('pluck.bass.acoustic', 'strings.contrabass'),
     {'sus': 'Meatbass/Programs/pizz_six.sfz',
      'arco': _V + 'ContrabassSusVB.sfz',
      'arco_stac': _V + 'ContrabassSpic.sfz',
      'arco_trem': _V + 'ContrabassTrem.sfz'}),
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
     {'sus': 'Copyist-Extras/organ-gospel-slow.sfz'}),
    (('pluck.guitar',),
     {'sus': 'BlackAndGreenGuitars/Programs/04-green_twang.sfz',
      'stac': 'BlackAndGreenGuitars/Programs/05-green_staccato.sfz'}),
    (('saxophone.alto',),
     {'sus': 'Weresax/Programs/Sax.sfz'}),
    (('saxophone.soprano',),
     {'sus': 'Copyist-Extras/saxello.sfz',
      'stac': 'Copyist-Extras/saxello-stac.sfz'}),
    (('saxophone.tenor',),
     {'sus': 'Copyist-Extras/tenor-sax.sfz',
      'stac': 'Copyist-Extras/tenor-sax-stac.sfz'}),
    (('saxophone.baritone',),
     {'sus': 'BearSax/Programs/2-solo-poly.sfz'}),
    (('brass.trumpet',),
     {'sus': _V + 'TrumpetSusVib.sfz', 'stac': _V + 'TrumpetStac.sfz'}),
    (('brass.trombone',),
     {'sus': _V + 'TromboneSus.sfz', 'stac': _V + 'TromboneStac.sfz',
      'fall': 'Copyist-Extras/trombone-falls.sfz'}),
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
    # the strings' own plucked and bowed-tremolo takes: "pizz." on the
    # page (or a pizzicato keyswitch in the demo) plays these
    (('strings.violin',),
     {'sus': _V + 'SViolinVib.sfz', 'stac': _V + 'SViolinSpic.sfz',
      'pizz': _V + 'SViolinPizz.sfz', 'trem': _V + 'SViolinTrem.sfz'}),
    (('strings.viola',),
     {'sus': _V + 'ViolaEnsSusVib.sfz',
      'stac': _V + 'ViolaEnsSpic.sfz',
      'pizz': _V + 'ViolaEnsPizz.sfz', 'trem': _V + 'ViolaEnsTrem.sfz'}),
    (('strings.cello',),
     {'sus': _V + 'CelloEnsSusVib.sfz',
      'stac': _V + 'CelloEnsSpic.sfz',
      'pizz': _V + 'CelloEnsPizz.sfz', 'trem': _V + 'CelloEnsTrem.sfz'}),
    (('strings.group',),
     {'sus': _V + 'ViolinEnsSusVib.sfz',
      'stac': _V + 'ViolinEnsSpic.sfz',
      'pizz': _V + 'ViolinEnsPizz.sfz', 'trem': _V + 'ViolinEnsTrem.sfz'}),
    (('voice.',),
     {'sus': 'Copyist-Extras/choir-ah.sfz'}),
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
        if percussion and any(h in sid for h in HAND_SOUNDS):
            # the percussion table plays its own recordings
            if not os.path.exists(os.path.join(self.dir, HAND_SFZ)):
                write_hand_sfz(self.dir)
            inst = self._load(HAND_SFZ)
            if inst is not None and inst.regions:
                return {'sus': inst}
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


# ------------------------------------------------ the percussion table
#
# Hand percussion plays VCSL's own recordings (CC0), not the drum kit's:
# a conga part used to sound through a kit with no congas in it. The
# sampler file is written from what is on the shelf, one GM percussion
# key per sound, velocity layers and round robins as recorded. Keys the
# library never recorded (timbales) fall to the GM SoundFont, as ever.
_VM = 'Membranophones/Struck Membranophones/'
_VI = 'Idiophones/Struck Idiophones/'
HAND_KEYS = (
    (60, _VM + 'Bongos', r'BongoH_Hit1_'),
    (61, _VM + 'Bongos', r'BongoL_Hit1_'),
    (62, _VM + 'Conga', r'Conga_HitFM_'),
    (63, _VM + 'Conga', r'Conga_HitN_'),
    (64, _VM + 'Conga', r'Tumba_HitN_'),
    (54, _VI + 'Tambourine 1', r'Tamb1_Hit_'),
    (56, _VI + 'Cowbells', r'Cowbell1_Hit_'),
    (67, _VI + 'Agogo Bells', r'Agogo_High_'),
    (68, _VI + 'Agogo Bells', r'Agogo_Low_'),
    (69, _VI + 'Cabasa', r'Cabasa1_Rub_'),
    (70, _VI + 'Shaker, Small', r'Mid_ShakerHighFaster_Down'),
    (73, _VI + 'Guiro', r'Guiro_Hit_'),
    (74, _VI + 'Guiro', r'Guiro_Med_'),
    (75, _VI + 'Claves', r'Claves1_Hit_'),
    (76, _VI + 'Woodblock', r'wood_click_f'),
    (77, _VI + 'Woodblock', r'wood_click3_'),
    (80, _VI + 'Triangles', r'Triangle3_HitM_'),
    (81, _VI + 'Triangles', r'Triangle3_Hit_'),
    (82, _VI + 'Shaker, Small', r'Mid_ShakerDouble_'),
)
HAND_SFZ = 'Copyist-Extras/hand-percussion.sfz'
# level trims in dB, measured on the recordings (2026-09-28): the
# shakers and guiro were recorded 20-25 dB under the drums
HAND_TRIM = {54: 3, 64: 6, 67: 6, 68: 7, 69: 7, 70: 16, 73: 20, 74: 20,
             77: 4, 80: 8, 81: 9, 82: 16}
HAND_SOUNDS = ('drum.conga', 'drum.bongo', 'drum.timbale', 'metal.cowbell',
               'wood.', 'rattle.', 'drum.tambourine', 'metal.triangle',
               'metal.bells.agogo')


def write_hand_sfz(shelf_dir):
    """The percussion table's sampler file, from the recordings on disk.
    Returns its path, or None when VCSL is not on the shelf."""
    import re as _re
    vcsl = os.path.join(shelf_dir, 'VCSL')
    if not os.path.isdir(vcsl):
        return None
    lines = ['// written by chartband.write_hand_sfz from VCSL (CC0)',
             '<control> default_path=../VCSL/', '']
    for key, folder, pat in HAND_KEYS:
        d = os.path.join(vcsl, folder)
        if not os.path.isdir(d):
            continue
        files = sorted(f for f in os.listdir(d)
                       if f.lower().endswith('.wav') and _re.match(pat, f))
        if not files:
            continue
        layers = {}
        for f in files:
            m = _re.search(r'_v(\d+)', f)
            layers.setdefault(int(m.group(1)) if m else 1, []).append(f)
        vs = sorted(layers)
        for i, v in enumerate(vs):
            lo = 1 + (127 * i) // len(vs)
            hi = (127 * (i + 1)) // len(vs)
            takes = layers[v]
            for j, f in enumerate(takes, 1):
                lines.append(
                    f'<region> sample={folder}/{f} key={key} '
                    f'pitch_keytrack=0 lovel={lo} hivel={hi} '
                    f'seq_length={len(takes)} seq_position={j}'
                    f' volume={HAND_TRIM.get(key, 0)}')
    out = os.path.join(shelf_dir, HAND_SFZ)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return out


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
         'bass': .04, 'strings': .22, 'voice': .16, 'brass': .18,
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
        # alternate with the note the page names (chartaudio reads the
        # key, the accidental over the mark, or the target in
        # parentheses), easing in like a player
        step = float(art.get('trill_step', 2))
        bend, t, up, period = [(0.0, 0.0)], 0.12, False, 0.075
        while t < d - 0.02:
            up = not up
            bend.append((t, step if up else 0.0))
            bend.append((min(t + period, d), step if up else 0.0))
            t += period
        bend.append((d, 0.0))
    if art.get('trem'):
        # a measured-fast reiteration: the bow (or tongue) re-strikes,
        # so the level pulses rather than the pitch moving
        amps, t, on = [(0.0, 1.0)], 0.0, True
        period = 0.055
        while t < d - 0.01:
            t += period
            on = not on
            amps.append((min(t, d), 1.0 if on else 0.35))
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


# ---------------------------------------------------------------- mutes
#
# No muted brass is recorded anywhere open, so a mute is played the way
# an engineer would fake one convincingly: the open horn through the
# shape the mute cuts. RBJ cookbook biquads, in plain Python like the
# rest of the band. (freq Hz, Q, gain dB) per stage; 'hp'/'lp' are
# 12 dB/oct, 'pk' a peak; then an overall level.
_MUTES = {
    'harmon':   ([('hp', 900, 0.8, 0), ('pk', 1800, 2.0, 9),
                  ('lp', 5500, 0.7, 0)], -7),
    'cup':      ([('hp', 220, 0.7, 0), ('lp', 1500, 0.8, 0)], -5),
    'straight': ([('hp', 550, 0.8, 0), ('pk', 2500, 1.5, 6)], -4),
    'plunger':  ([('lp', 900, 0.9, 0)], -3),
    'bucket':   ([('lp', 2000, 0.7, 0)], -4),
    'strings':  ([('lp', 2600, 0.7, 0), ('pk', 900, 1.0, -3)], -2),
}


def _biquad(kind, f, q, gain_db, sr):
    a_ = 10 ** (gain_db / 40)
    w = 2 * math.pi * f / sr
    cw, sw = math.cos(w), math.sin(w)
    al = sw / (2 * q)
    if kind == 'lp':
        b = ((1 - cw) / 2, 1 - cw, (1 - cw) / 2)
        a = (1 + al, -2 * cw, 1 - al)
    elif kind == 'hp':
        b = ((1 + cw) / 2, -(1 + cw), (1 + cw) / 2)
        a = (1 + al, -2 * cw, 1 - al)
    else:
        b = (1 + al * a_, -2 * cw, 1 - al * a_)
        a = (1 + al / a_, -2 * cw, 1 - al / a_)
    return [x / a[0] for x in b], [a[1] / a[0], a[2] / a[0]]


def _run(samples, b, a):
    out = array('f', bytes(4 * len(samples)))
    x1 = x2 = y1 = y2 = 0.0
    b0, b1, b2 = b
    a1, a2 = a
    for i, x in enumerate(samples):
        y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x, y1, y
        out[i] = y
    return out


def mute_kind(word):
    """The mute a page's words put on: 'harmon mute - stem out' ->
    'harmon'; 'con sord.' on a string part -> the string mute."""
    w = (word or '').lower()
    for k in ('harmon', 'cup', 'straight', 'plunger', 'bucket'):
        if k in w:
            return k
    if 'wah' in w:
        return 'harmon'
    if 'con sord' in w or 'mute' in w:
        return 'straight'
    return None


def apply_mute(res, kind, sr, strings=False):
    """(L, R) of one note -> the same note through the mute."""
    if not res or not kind:
        return res
    stages, level = _MUTES['strings' if strings else kind]
    g = 10 ** (level / 20)
    out = []
    for ch in res:
        if ch is None:
            out.append(None)
            continue
        y = ch
        for kind_, f, q, gdb in stages:
            b, a = _biquad(kind_, f, q, gdb, sr)
            y = _run(y, b, a)
        for i in range(len(y)):
            y[i] *= g
        out.append(y)
    return tuple(out)


def _variant(voice, art):
    """Which recorded take plays this note: the library's own staccato
    for short marks, its ghost set for ghosts, sustain otherwise."""
    if voice is None:
        return None
    if 'pizz' in art and 'pizz' in voice:
        return voice['pizz']
    if art.get('arco') and 'arco' in voice:
        if art.get('trem') and 'arco_trem' in voice:
            return voice['arco_trem']
        if ('stac' in art or 'marc' in art) and 'arco_stac' in voice:
            return voice['arco_stac']
        return voice['arco']
    if art.get('trem') and 'trem' in voice:
        return voice['trem']
    if ('stac' in art or 'marc' in art) and 'stac' in voice:
        return voice['stac']
    if 'ghost' in art and 'ghost' in voice:
        return voice['ghost']
    return voice.get('sus')


def render_plan(plan, wav_path, sf_path, tail=2.0, count_in=None,
                on_progress=None):
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

    # a groove repeats its hits by the hundred: keep a four-take
    # round-robin cache per drum voice so the kit renders each take
    # once and then plays it like a player would — same variety, a
    # fraction of the time
    drum_cache = {}
    drum_turn = {}
    step = max(len(jobs) // 50, 1)
    for ji, (a, d, idx, key, vel, bright, bend, amps, fam, art) \
            in enumerate(jobs):
        if on_progress and ji % step == 0:
            on_progress(ji / max(len(jobs), 1),
                        "the band is playing it in")
        part = plan['parts'][idx]
        v = int(round(min(max(vel, 1.0), 127.0)))
        pieces = []
        voice = voices[idx]
        if part['percussion'] and bend is None and amps is None:
            ck = (idx, int(key), v // 8, round(d, 1))
            takes = drum_cache.setdefault(ck, [])
            if len(takes) >= 4:
                n = drum_turn.get(ck, 0)
                drum_turn[ck] = n + 1
                res = takes[n % 4]
                if res is not None:
                    pieces.append((a, res))
                else:
                    continue
            else:
                inst = _variant(voice, art)
                res = inst.render_note(int(key), v, d, SR,
                                       brightness=bright,
                                       detune=detunes[idx]) \
                    if inst is not None else None
                if res is None and shelf.sf2 is not None:
                    res = sf2mod.render_note(
                        shelf.sf2, 128, max(part['program'] - 1, 0),
                        int(key), v, d, SR, brightness=bright,
                        detune=detunes[idx])
                takes.append(res)
                if res is None:
                    continue
                pieces.append((a, res))
        if not pieces and 'fall' in art and voice and 'fall' in voice \
                and key is not None:
            # a RECORDED fall beats a synthetic bend every time. A
            # short note IS the gesture; a long one sings first and
            # falls out of the end.
            if d > 1.1 and 'sus' in voice:
                body = voice['sus'].render_note(
                    int(key), v, d - 0.45, SR,
                    amps=[(0.0, 1.0), (d - 0.45, 0.8)],
                    detune=detunes[idx])
                if body:
                    pieces.append((a, body))
                drop = voice['fall'].render_note(
                    int(key), v, 1.2, SR, detune=detunes[idx])
                if drop:
                    pieces.append((a + d - 0.5, drop))
            else:
                drop = voice['fall'].render_note(
                    int(key), v, max(d, 0.9), SR,
                    detune=detunes[idx])
                if drop:
                    pieces.append((a, drop))
        if not pieces:
            res = None
            inst = _variant(voice, art)
            if art.get('trem') and voice and 'trem' in voice:
                amps = None     # the recorded bow already trembles
            if inst is not None:
                res = inst.render_note(int(key), v, d, SR, bend=bend,
                                       brightness=bright, amps=amps,
                                       detune=detunes[idx])
            if res is None and shelf.sf2 is not None:
                res = sf2mod.render_note(
                    shelf.sf2, 128 if part['percussion'] else 0,
                    max(part['program'] - 1, 0),
                    int(key), v, d, SR, bend=bend, brightness=bright,
                    amps=amps, detune=detunes[idx])
            if res is None:
                continue
            if art.get('mute') and not part['percussion']:
                res = apply_mute(res, art['mute'], SR,
                                 strings='strings.' in (part.get('sound')
                                                        or ''))
            pieces.append((a, res))
        pan = (-0.6 + 1.2 * idx / max(n_parts - 1, 1)) \
            if n_parts > 1 else 0.0
        gl = math.cos((pan + 1) * math.pi / 4) * 1.1
        gr = math.sin((pan + 1) * math.pi / 4) * 1.1
        send = _SEND[fam]
        for at, (nl, nr) in pieces:
            i0 = int(at * SR)
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
