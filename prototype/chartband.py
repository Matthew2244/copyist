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
     {'sus': 'VirtuosityDrums/Programs/02-full-kit.sfz',
      # brushes: Karoryfer's Swirly Drums, stirs and all
      'brush': 'SwirlyDrums/Programs/Full_kit.sfz'}),
    # the upright plays plucked; "arco" on the page picks up the bow —
    # the orchestra's own contrabass takes, sustained, short and
    # tremolo. ONE bass: pizz_six is a section of six, each detuned
    # and spread, and a walking line through it sounded like six
    # players not quite agreeing (Matthew, 2026-09-28: "the bass
    # sounds so funny"). The orchestra's section keeps the six.
    (('pluck.bass.acoustic',),
     {'sus': 'Meatbass/Programs/pizz_basic.sfz',
      'arco': _V + 'ContrabassSusVB.sfz',
      'arco_stac': _V + 'ContrabassSpic.sfz',
      'arco_trem': _V + 'ContrabassTrem.sfz'}),
    (('strings.contrabass',),
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
    # no SFZ guitar: every recording in Black And Green Guitars is
    # limited flat into full scale (crest ~7 dB against the SoundFont's
    # 15-20), which is the distortion Matthew kept hearing — "clippy
    # white noise" (2026-09-28). Guitars play the GM SoundFont's own.
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
    # no sampled voices: Matthew heard the VocalSet choir and asked for
    # every voice back on a synth voice, not too loud (2026-09-30) —
    # voices play the GM SoundFont's Synth Voice (program 55)
    (('pitched-percussion.glockenspiel',),
     {'sus': _V + 'Glockenspiel.sfz'}),
    (('pitched-percussion.vibraphone',),
     {'sus': 'Copyist-Extras/vibraphone.sfz'}),
    (('pitched-percussion.marimba',), {'sus': _V + 'Marimba.sfz'}),
    (('pitched-percussion.xylophone',), {'sus': _V + 'Xylophone.sfz'}),
    (('pitched-percussion.tubular-bells',),
     {'sus': _V + 'TubularBells.sfz'}),
    (('drum.timpani',), {'sus': _V + 'Timpani.sfz'}),
    (('pluck.harp',), {'sus': _V + 'Harp.sfz'}),
)


# Level trims, dB, for libraries whose unison and extra-microphone
# layers once sounded all at once because CC gates were ignored, and
# for the upright, once a section of six. Each note is one clean layer
# now; the trim keeps the band's balance where it was set by ear
# (2026-09-28). The hi-hat is not trimmed back: it
# had an open hat ringing under every closed one.
_MAKEUP = {
    'Bass-black-and-blue-basses/': 10.0,
    'VirtuosityDrums/': 8.0,
    'Meatbass/Programs/pizz_basic': 7.0,    # one bass where six stood
    # Swirly's brushes sit 10 dB under Virtuosity's sticks on the same
    # hits (measured K-weighted, 2026-09-29); brushes play lighter, but
    # not that much lighter — this leaves them ~2 dB under
    'SwirlyDrums/': 8.0,
}


# Where each chair sits and how loud, the way an engineer sets up a
# jazz record (Matthew, 2026-09-29, on Trading Room: "tenor is loud,
# bass could come down a little, trumpet could come up a little").
# Seat levels are dB on top of the library trims above, set by
# measuring each chair alone at a fixed gain (balance_report), then by
# ear. Pan: -1 hard left, +1 hard right; the bass and the kick's centre
# stay in the middle, the kit's own stereo does the spreading.
_SEATS = (
    # (sound-id fragment, dB, pan). Every chair is first brought to one
    # heard loudness (calibrate), so these are the mix itself: the horns
    # the reference, the rhythm section under them. Set on Trading Room
    # by measured loudness per chair (2026-09-29): comping chords stack
    # three or four notes, so keys and guitar sit well down.
    ('saxophone.tenor', -0.5, -0.30), ('saxophone.alto', -1.0, -0.20),
    ('saxophone.soprano', -1.0, -0.15), ('saxophone.baritone', -1.0,
                                         -0.40),
    ('brass.trumpet', -1.5, 0.25), ('brass.flugelhorn', -1.5, 0.25),
    ('brass.cornet', -1.5, 0.25), ('brass.trombone', -5.0, 0.40),
    ('brass.', 0.0, 0.3),
    ('pluck.bass', -4.5, 0.0), ('strings.contrabass', -4.0, 0.0),
    ('keyboard.piano', -15.0, 0.30), ('keyboard.organ', -16.0, 0.25),
    ('keyboard', -15.0, 0.25), ('pluck.guitar', -13.0, -0.35),
    ('pitched-percussion.vibraphone', -8.0, 0.35),
    ('drum.group', -6.5, 0.0),
    ('drum.', -4.0, 0.45), ('metal.', -5.0, 0.45), ('wood.', -5.0, 0.45),
    ('rattle.', -6.0, 0.45),
    ('voice', -7.0, 0.0),          # a synth voice sits under the band
    ('wind.', -1.0, -0.20), ('strings.', -1.0, -0.25),
)


_LEVEL_TARGET = 500.0     # every chair's heard loudness, before its seat (library units)
SYNTH_VOICE = 55          # GM Synth Voice, 1-based
_LEVELS = None            # cache: (voice, key, vel) -> loudness


def _kweight_coeffs(sr):
    """ITU-R BS.1770's K-weighting as two biquads at this sample rate:
    the head's high shelf (+4 dB above ~1.7 kHz) and the RLB high-pass
    (~38 Hz) — the curve loudness meters (LUFS) hear through."""
    import math as m
    f0, g, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = m.tan(m.pi * f0 / sr)
    vh = 10 ** (g / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = ((vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0,
             (vh - vb * k / q + k * k) / a0, 2 * (k * k - 1) / a0,
             (1 - k / q + k * k) / a0)
    f0, q = 38.13547087602444, 0.5003270373238773
    k = m.tan(m.pi * f0 / sr)
    a0 = 1 + k / q + k * k
    hp = (1.0, -2.0, 1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)
    return shelf, hp


def _biquad_run(x, c):
    b0, b1, b2, a1, a2 = c
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, v in enumerate(x):
        o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, o
        y[i] = o
    return y


def _heard(res, sr, secs=1.0):
    """How loud a rendered note sounds, the way a loudness meter hears
    it: K-weighted (ITU-R BS.1770), then the RMS over the note's own
    length. A cruder 150 Hz high-pass once under-heard every low voice
    and boosted a choir's basses 9 dB over the rest (Midnight Train,
    2026-09-29)."""
    if not res:
        return 0.0
    L = res[0]
    n = min(len(L), int(sr * max(secs, 0.2)))
    if n < 10:
        return 0.0
    shelf, hp = _kweight_coeffs(sr)
    y = _biquad_run(_biquad_run(list(L[:n]), shelf), hp)
    return math.sqrt(sum(v * v for v in y) / n)


def _levels_cache():
    global _LEVELS
    if _LEVELS is None:
        import json
        path = os.path.expanduser('~/.cache/copyist/levels.json')
        try:
            _LEVELS = json.load(open(path))
        except Exception:
            _LEVELS = {}
    return _LEVELS


def _save_levels():
    import json
    path = os.path.expanduser('~/.cache/copyist/levels.json')
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(_LEVELS or {}, open(path, 'w'))
    except Exception:
        pass


def calibrate(shelf, voice, part, sr, note_secs=1.0):
    """The gain that brings this chair to the common heard loudness,
    measured where the part actually plays (its middle note) at the
    band's ordinary weight. The libraries differ by 45 dB raw (Trading
    Room, 2026-09-29); a trim per library only ever covered a few."""
    evs = part['events']
    if not evs:
        return 1.0
    if part['percussion']:
        keys = [38] if not part.get('sound', '').startswith(
            ('drum.conga', 'drum.bongo', 'metal.', 'wood.', 'rattle.')) \
            else [sorted(e[2] for e in evs)[len(evs) // 2]]
    else:
        # three notes across where the part plays, not one: a library's
        # samples are not even note to note (the choir's C3 sits 6 dB
        # under its neighbours, and one-note calibration boosted a whole
        # bass section 8 dB — Midnight Train, 2026-09-29)
        ks = sorted(e[2] for e in evs)
        keys = sorted({ks[len(ks) // 4], ks[len(ks) // 2],
                       ks[(3 * len(ks)) // 4]})
    inst = (voice or {}).get('sus') if voice else None
    tag = (getattr(inst, 'path', None) or
           f"sf2:{part['program']}:{part['percussion']}")
    secs = 1.0 if part['percussion'] else \
        min(max(round(note_secs * 2) / 2, 0.5), 4.0)
    cache = _levels_cache()
    levels = []
    for key in keys:
        key = int(key)
        ck = f"k|{tag}|{key}|{secs}"
        if ck not in cache:
            res = None
            if inst is not None:
                k2, cc = _kit_key(inst, key) if part['percussion'] \
                    else (key, None)
                res = inst.render_note(k2, 72, secs + 0.2, sr, cc=cc)
            if res is None and shelf.sf2 is not None:
                res = sf2mod.render_note(
                    shelf.sf2, 128 if part['percussion'] else 0,
                    max(part['program'] - 1, 0), key, 72, secs + 0.2, sr)
            cache[ck] = _heard(res, sr, secs)
            _save_levels()
        levels.append(cache[ck])
    # the power average: a quiet sample among loud ones counts as it sounds
    loud = math.sqrt(sum(x * x for x in levels) / len(levels))
    if loud <= 1e-9:
        return 1.0
    return min(max(_LEVEL_TARGET / loud, 1e-3), 1e3)


def seat_of(sound_id):
    """(dB, pan) for a chair, or None to keep the old spread."""
    sid = (sound_id or '').lower()
    for frag, db, pan in _SEATS:
        if frag in sid:
            return db, pan
    return None


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
        if inst is not None:
            for prefix, db in _MAKEUP.items():
                if rel.startswith(prefix):
                    inst.makeup = 10.0 ** (db / 20.0)
        self._cache[rel] = inst
        return inst

    def voice(self, sound_id, percussion, name=''):
        """The articulation set for this chair: {'sus': inst, ...} or
        None to use the GM floor. The part's name settles what the sound
        id cannot: notation programs label every bass part
        strings.contrabass, but a part called Acoustic Bass is one
        player; Contrabass, Double Bass or Basses is the section."""
        if not self.dir:
            return None
        sid = (sound_id or '').lower()
        nm = (name or '').lower()
        if 'strings.contrabass' in sid and nm and not any(
                w in nm for w in ('contrabass', 'double bass', 'basses',
                                  'cb.', 'd.b.')):
            sid = 'pluck.bass.acoustic'
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
_ONE_LINE = {'brass', 'reed', 'flute', 'voice', 'bass', 'guitar'}
_CHANGE = 0.035          # seconds two notes overlap in a real change
_TAIL = 0.35             # a note's own tail before a rest
_FADE = 0.03


def _cut_at(res, secs):
    """A rendered note ended after secs, fading over its last 30 ms."""
    nl, nr = res[0], res[1]
    n = max(int(secs * chartaudio.SR), 1)
    if len(nl) <= n:
        return nl, nr
    f = max(min(int(_FADE * chartaudio.SR), n), 1)
    ol = array('f', nl[:n])
    orr = ol if nr is nl else array('f', nr[:n])
    for k in range(f):
        g = (f - k) / f
        ol[n - f + k] *= g
        if orr is not ol:
            orr[n - f + k] *= g
    return ol, orr


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
_VIRTUOSITY = {41: 41, 43: 41, 45: 43, 47: 43, 48: 48, 50: 48, 37: 88}


def _kit_key(inst, key):
    """The key and controllers a GM drum note plays on this kit. A kit
    that puts every hi-hat on one key and chooses closed from open by
    the pedal controller (CC 4, as an e-drum does) gets the pedal set
    per note: down for 42, up for 46. Anything else plays as written."""
    key = int(key)
    if 'VirtuosityDrums' in str(getattr(inst, 'path', '')):
        # Virtuosity is not General MIDI past the snare: its 47 is the
        # low tom's CROSS-STICK and 45 a tom rimshot, so every "mid tom"
        # in a fill clicked like a rim (Matthew, 2026-09-30: "sounds
        # like drummer is hitting crossstick ... why?"). It has two toms;
        # floor, mid and high get the low tom, its off-centre stroke and
        # the high tom. GM's side stick is its key 88; 37 is a stick shot.
        key = _VIRTUOSITY.get(key, key)
    if key not in (42, 46) or not hasattr(inst, 'regions'):
        return key, None
    pedal = getattr(inst, '_hat_pedal', None)
    if pedal is None:
        pedal = any('locc4' in r or 'hicc4' in r for r in inst.regions
                    if r.get('key') == '42' or r.get('lokey') == '42')
        inst._hat_pedal = pedal
    if not pedal:
        return key, None
    return 42, {4: 127.0 if key == 42 else 0.0}


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
    if art.get('brush') and 'brush' in voice:
        return voice['brush']
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
                on_progress=None, window=None):
    """The parsed plan -> a stereo WAV through the sample shelf.
    sf_path may be the shelf directory (SFZ voices per instrument,
    the GM SoundFont as the floor) or a single .sf2. Mirrors
    chartaudio.render's return: (seconds, n_parts, n_notes,
    lead_seconds).

    window=(t0, t1), in the score's seconds, renders only what sounds
    between them, from a few seconds before t0 so held notes and the
    room are already ringing at the cut. The WAV then starts there, and
    the returned lead is where score time 0 would sit in it — t0 plus
    lead is still where the bars begin. A bar-range listen used to
    render the whole song and throw most of it away."""
    SR = chartaudio.SR
    shelf = Shelf(sf_path)
    holds = plan.get('holds', ())
    swings = plan['swings']
    tempos = plan['tempos']

    def sec_of(q):
        return chartaudio._sec_of(chartaudio._warp(q, swings),
                                  tempos, holds)

    # a soloist swings flatter than the drummer's ride (Friberg &
    # Sundstrom 2002; Corcoran & Frieler 2021: soloists near 1.3:1)
    def _flat(sw):
        out = []
        for q, r in sw:
            if isinstance(r, tuple) and r[0]:
                ratio = r[0] / (1 - r[0])
                rs = 1 + (ratio - 1) * 0.35
                out.append((q, (rs / (1 + rs), r[1])))
            else:
                out.append((q, r))
        return out
    swings_solo = _flat(swings)

    def sec_solo(q):
        return chartaudio._sec_of(chartaudio._warp(q, swings_solo),
                                  tempos, holds)

    def bpm_at(q):
        got = tempos[0][1] if tempos else 120.0
        for at, bpm in tempos:
            if at <= q + 1e-9:
                got = bpm
        return got

    feels = plan.get('feels', ())

    def feel_at(q):
        """The feel word standing at q ('tight' by default: nothing
        written, the band plays tight and confident)."""
        got = None
        for at, k in feels:
            if at <= q + 1e-9:
                got = k
            else:
                break
        return got

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
        voices.append(shelf.voice(sid, part['percussion'],
                                  part.get('name', '')))
        if sid.startswith('voice') or 53 <= part['program'] <= 55:
            part['program'] = SYNTH_VOICE     # every singer, one sound
        if 'pluck.guitar' in sid and not 25 <= part['program'] <= 32:
            # a guitar with no program of its own would fall to the
            # piano: jazz guitar, or nylon for an acoustic
            part['program'] = 25 if 'acoustic' in sid else 27
        detunes.append(((nth % 4) - 1.5) * 0.04 if sid else 0.0)

    # every chair to one heard loudness first; the seats set the mix
    def typical_secs(p):
        # the chair's own note length, measured where it plays
        ds = sorted(sec_of(q + d_) - sec_of(q)
                    for q, d_, *_ in p['events'])
        return ds[len(ds) // 2] if ds else 1.0
    cal = [calibrate(shelf, voices[i], p, SR, typical_secs(p)) if seat_of(
        p.get('sound', '')) is not None else 1.0
        for i, p in enumerate(plan['parts'])]

    jobs = []    # (t, dur, idx, key, vel, bright, bend, amps, fam, art)
    notes = 0
    for idx, part in enumerate(plan['parts']):
        fam = _family(part['program'], part['percussion'])
        dyn = _dyn_curve(part)
        events = part['events']
        chokes = _choke_map(shelf, part, events) \
            if part['percussion'] else {}
        steals = _steals(voices[idx], events, sec_of, lead) \
            if part['percussion'] else {}
        # one player, one note at a time: where the next note starts
        # (chord tones share an onset, so they are not "next")
        onsets = sorted({q for q, *_ in events})
        nxt_of = {q: (onsets[k + 1] if k + 1 < len(onsets) else None)
                  for k, q in enumerate(onsets)}
        for i, (q_on, q_dur, midi, gain, art) in enumerate(events):
            soloing = bool(art and art.get('lead')) and \
                not part['percussion'] and fam != 'bass'
            so = sec_solo if soloing else sec_of
            a = so(q_on) + lead
            b = so(q_on + q_dur) + lead
            if soloing and abs(q_on - round(q_on)) < 0.02:
                # a soloist sits behind on the downbeats, offbeats with
                # the ride: ~30 ms at 150, more slow, none past ~210
                # (Nelias et al. 2022, 456 Weimar solos)
                bpm = bpm_at(q_on)
                a += max(0.0, min(0.045, 0.030 * (150.0 / bpm) ** 0.8)) \
                    * max(0.0, min(1.0, (215.0 - bpm) / 65.0))
            d = max(b - a, 0.03)
            g0 = dyn(q_on)
            g1 = dyn(q_on + q_dur)
            if abs(g0 - gain) > 0.005 and not part.get('wedges'):
                g0 = gain               # a note's own mark wins
            vel = g0 * 90.0
            # humanization, deterministic: nobody plays on the grid,
            # and nobody plays two notes at the same weight
            h = _hash01(idx, i, midi)
            fk = feel_at(q_on)
            jit = {'loose': 2.6, 'tight': 0.5, 'back': 1.3}.get(fk, 1.0)
            a += (h - 0.5) * (0.006 if part['percussion'] else 0.016) * jit
            # where the band sits against the time, when the chart says
            if fk == 'back':
                # laid back the way players mean it: the soloist and
                # horns well behind (50-80 ms in the literature), the
                # comping less, the bass and drums nearly with the time
                a += 0.005 if part['percussion'] else \
                    0.014 if fam == 'bass' else \
                    0.030 if fam in ('piano', 'organ', 'guitar') else \
                    0.060
            elif fk == 'push':
                a -= 0.003 if part['percussion'] else \
                    0.005 if fam == 'bass' else 0.010
            a = max(a, 0.0)
            vel *= 0.96 + 0.08 * (2.2 if fk == 'loose' else 1.0) * \
                (_hash01(idx, midi, i) - 0.5) + 0.04
            if part['percussion']:
                nat = chokes.get(i)
                if nat is not None:
                    ns = sec_of(q_on + nat) - sec_of(q_on)
                    d = min(max(ns - 0.004, 0.02), 8.0)
                else:
                    d = 8.0
                if art and art.get('stac'):
                    d = min(d, 0.13)        # the hand grabs it: a choke
                dd, vel, bright, bend, amps = _shape(art, d, vel, fam)
            else:
                dd, vel, bright, bend, amps = _shape(art, d, vel, fam)
                if amps is None and abs(g1 - g0) > 0.02 and g0 > 0:
                    amps = [(0.0, 1.0), (dd, g1 / g0)]   # the hairpin
            # a single-line player's note ends where the next begins,
            # overlapping only as long as a real change takes; before a
            # rest its tail is the player's, a breath, and the room
            # carries the rest. A library's multi-second release rang
            # under the next note (Matthew, 2026-09-28: "that's not how
            # a real player plays")
            cut = steals.get(i)
            if fam in _ONE_LINE and not part['percussion']:
                nq = nxt_of.get(q_on)
                end_note = a + dd
                cut = end_note + _TAIL
                if nq is not None:
                    cut = min(cut, sec_of(nq) + lead + _CHANGE)
            jobs.append((a, dd, idx, midi, vel, bright, bend, amps,
                         fam, art, cut))
            notes += 1

    if window:
        t0, t1 = window
        shift = max(t0 + lead - _PRE_ROLL, 0.0)
        kept = []
        for j in jobs:
            a, dd = j[0], j[1]
            ring = _RING if plan['parts'][j[2]]['percussion'] else dd + 4.0
            if a < t1 + lead and a + max(dd, ring) > shift:
                kept.append((a - shift,) + tuple(j[1:10]) +
                            ((j[10] - shift) if j[10] is not None
                             else None,))
        jobs = kept
        lead -= shift
        if shift > 0:
            count_in = None         # the click belongs to the top
    end = max((a + d for a, d, *_ in jobs), default=0.0) + tail + 1.0
    frames = int(end * SR)
    def play(jlist, L, R, wetL, wetR, report=None):
        """Render these notes into these buffers: dry and the room's
        send."""
        drum_cache = {}
        drum_turn = {}
        span = [frames, 0]          # where this call wrote anything
        step = max(len(jlist) // 50, 1)
        for ji, (a, d, idx, key, vel, bright, bend, amps, fam, art, cut) \
                in enumerate(jlist):
            if report and ji % step == 0:
                report(ji / max(len(jlist), 1))
            part = plan['parts'][idx]
            v = int(round(min(max(vel, 1.0), 127.0)))
            pieces = []
            voice = voices[idx]
            if part['percussion'] and bend is None and amps is None:
                # four full-length takes per piece and loudness band; a
                # choked or shortened hit is its take released where the
                # hit ends. Keyed on each hit's own length as well, the
                # cache almost never hit and a kit rendered every hit
                # afresh on four microphones — most of an export's time
                ck = (idx, int(key), v // 8, bright)
                takes = drum_cache.setdefault(ck, [])
                if len(takes) >= 4:
                    n = drum_turn.get(ck, 0)
                    drum_turn[ck] = n + 1
                    res = takes[n % 4]
                    if res is not None:
                        pieces.append((a, _drum_end(res, d, a, cut, voice,
                                                    key)))
                    else:
                        continue
                else:
                    inst = _variant(voice, art)
                    res = None
                    if inst is not None:
                        k2, cc = _kit_key(inst, key)
                        res = inst.render_note(k2, v, _RING, SR,
                                               brightness=bright,
                                               detune=detunes[idx],
                                               cc=cc)
                    if res is None and shelf.sf2 is not None:
                        res = sf2mod.render_note(
                            shelf.sf2, 128, max(part['program'] - 1, 0),
                            int(key), v, _RING, SR, brightness=bright,
                            detune=detunes[idx])
                    res = _trim_quiet(res)
                    takes.append(res)
                    if res is None:
                        continue
                    pieces.append((a, _drum_end(res, d, a, cut, voice,
                                                key)))
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
                    k2, cc = _kit_key(inst, key) if part['percussion'] \
                        else (int(key), None)
                    res = inst.render_note(k2, v, d, SR, bend=bend,
                                           brightness=bright, amps=amps,
                                           detune=detunes[idx], cc=cc,
                                           limit=None if cut is None
                                           or part['percussion']
                                           else cut - a + 0.01)
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
            if cut is not None and not part['percussion']:
                pieces = [(at, _cut_at(res_, cut - at)) for at, res_ in pieces]
            seat = seat_of(part.get('sound', ''))
            if seat is not None:
                sdb, pan = seat
                sg = 10.0 ** (sdb / 20.0) * cal[idx]
            else:
                pan = (-0.6 + 1.2 * idx / max(n_parts - 1, 1)) \
                    if n_parts > 1 else 0.0
                sg = 1.0
            if art.get('lead') and fam in ('piano', 'guitar', 'mallet',
                                           'organ', 'bass'):
                # a rhythm player taking a solo: the engineer pushes
                # the fader up to where the horns sit
                sg *= 10.0 ** (8.0 / 20.0)
            gl = math.cos((pan + 1) * math.pi / 4) * 1.1 * sg
            gr = math.sin((pan + 1) * math.pi / 4) * 1.1 * sg
            send = _SEND[fam]
            for at, (nl, nr) in pieces:
                i0 = int(at * SR)
                room = min(len(nl), frames - i0)
                # a note already sounding when a window opens joins
                # partway through
                first = max(-i0, 0)
                if room > first:
                    span[0] = min(span[0], i0 + first)
                    span[1] = max(span[1], i0 + room)
                for i in range(first, room):
                    sl = nl[i] * gl
                    sr_ = nr[i] * gr
                    j = i0 + i
                    L[j] += sl
                    R[j] += sr_
                    wetL[j] += sl * send
                    wetR[j] += sr_ * send
        return span

    def fresh():
        return tuple(array('f', bytes(4 * frames)) for _ in range(4))

    def ticks(L, R):
        if count_in:
            for c in range(n0 * count_in):
                chartaudio._add_tick(L, R, c * pulse,
                                     1568.0 if c % n0 == 0 else 1047.0,
                                     0.5)

    groups = _groups(jobs, [p['percussion'] for p in plan['parts']])
    if len(groups) > 1 and _can_fork():
        pcm = _play_parallel(groups, play, fresh, ticks, frames, SR,
                             on_progress)
    else:
        pcm = None
    if pcm is None:
        L, R, wetL, wetR = fresh()
        ticks(L, R)
        play(jobs, L, R, wetL, wetR,
             (lambda f: on_progress(f, "the band is playing it in"))
             if on_progress else None)
        _room(L, R, wetL, wetR, SR)
        peak = max(max(abs(x) for x in L), max(abs(x) for x in R)) or 1.0
        scale = 0.85 * 32767.0 / peak
        if os.environ.get('COPYIST_FIXED_GAIN'):
            # measuring one chair against another: no leveling
            scale = float(os.environ['COPYIST_FIXED_GAIN'])
        out = array('h', bytes(4 * frames))
        for i in range(frames):
            out[2 * i] = int(max(-32767.0, min(32767.0, L[i] * scale)))
            out[2 * i + 1] = int(max(-32767.0,
                                     min(32767.0, R[i] * scale)))
        pcm = out.tobytes()
    if plan.get('fade') is not None:
        # "fade out" on the page: the band goes down to nothing by the
        # last note, the room tail with it
        pcm = chartaudio.apply_fade(pcm, SR, sec_of(plan['fade']) + lead,
                                    sec_of(plan['end_q']) + lead)
    with wave.open(wav_path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return end, n_parts, notes, lead


_ROOM_TAIL = 3.0     # seconds: the room is 100 dB down by then


def _room(L, R, wetL, wetR, sr, span=None):
    """A small hall behind the band: Freeverb-shaped combs and
    allpasses run at half rate on the send bus, mixed back in. Half
    rate is a choice, not a corner — a room tail is dark. span=(lo, hi)
    says where anything was sent: before lo the room is silent, and
    past hi plus its tail it has died away, so only that stretch is
    run."""
    n = len(L)
    lo = 0
    if span is not None:
        lo = max(span[0] - span[0] % 2, 0)
        n = min(n, span[1] + int(_ROOM_TAIL * sr))
        if span[1] <= span[0]:
            return
    h = (n - lo) // 2
    if h < 4:
        return
    for src, dst, tunings in ((wetL, L, (1116, 1188, 1277, 1356)),
                              (wetR, R, (1139, 1211, 1300, 1379))):
        half = array('f', bytes(4 * h))
        for i in range(h):
            half[i] = (src[lo + 2 * i] + src[lo + 2 * i + 1]) * 0.5
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
            dst[lo + 2 * i] += acc[i] * 0.30
            dst[lo + 2 * i + 1] += (acc[i] + acc[i + 1]) * 0.15


# ------------------------------------------------------------ in parallel

_K = 256.0               # float -> int32 headroom scale for the reduction


def _can_fork():
    """Parallel rendering forks the process (the parts' state comes
    along for free) and sums with audioop, both C-speed; either missing
    — Windows, or a Python without audioop — renders in one process."""
    import multiprocessing
    try:
        multiprocessing.get_context('fork')
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            import audioop   # noqa: F401
        return True
    except (ValueError, ImportError):
        return False


_RING = 8.0          # how long a drum hit may ring, choked or not
_RELEASE = 0.08      # the sampler's default release: a choke's fade


_PRE_ROLL = 4.0      # seconds rendered ahead of a window's first bar


def _polyphony(voice, key):
    """(voices a drum may ring at once, its release) from the kit's own
    note_polyphony and ampeg_release, or None where the kit sets none."""
    inst = (voice or {}).get('sus')
    if inst is None or not hasattr(inst, 'regions_for'):
        return None
    memo = inst.__dict__.setdefault('_poly_memo', {})
    if key not in memo:
        k2, cc = _kit_key(inst, key)
        n, rel = None, _RELEASE
        for r in inst.regions:
            lo = sfzmod._keynum(r.get('lokey', r.get('key', '0')))
            hi = sfzmod._keynum(r.get('hikey', r.get('key', '127')))
            if lo is None or hi is None or not lo <= k2 <= hi or \
                    not inst._cc_ok(r, cc):
                continue
            try:
                np_ = int(float(r.get('note_polyphony', 0)))
                rel = max(rel, float(r.get('ampeg_release', 0)))
            except ValueError:
                continue
            if np_ > 0:
                n = np_ if n is None else min(n, np_)
        memo[key] = (n, rel) if n else None
    return memo[key]


def _steals(voice, events, sec_of, lead):
    """Event index -> the second its voice is stolen: a kit that lets a
    drum ring n voices at once (note_polyphony) releases the oldest when
    the next hit comes. Without this every ride hit rang eight seconds
    over all the others — a wash no cymbal makes, and most of a render's
    time (2026-09-28)."""
    by_key = {}
    for i, (q_on, _d, midi, _g, _a) in enumerate(events):
        if midi is not None:
            by_key.setdefault(int(midi), []).append((q_on, i))
    out = {}
    for key, hits in by_key.items():
        poly = _polyphony(voice, key)
        if not poly:
            continue
        n = poly[0]
        hits.sort()
        for k, (_q, i) in enumerate(hits):
            if k + n < len(hits):
                out[i] = sec_of(hits[k + n][0]) + lead
    return out


def _drum_end(res, d, a, steal, voice, key):
    """A drum take ended by whichever comes first: its choke (the hat
    pedal closing, at the sampler's quick release) or its voice being
    stolen (at the kit's own release)."""
    if steal is not None and steal - a < d:
        poly = _polyphony(voice, key)
        return _release_at(res, max(steal - a, 0.0),
                           poly[1] if poly else _RELEASE)
    return _release_at(res, d)


def _release_at(res, d, release=_RELEASE):
    """A full-length take ended at d seconds the way the sampler ends
    a note: a straight-line release from where it is."""
    if d >= _RING - 1e-6:
        return res
    L, R = res
    sr = chartaudio.SR
    n_on = max(int(d * sr), 1)
    r_n = max(int(release * sr), 1)
    if n_on >= len(L):
        return res
    n = min(len(L), n_on + r_n)
    oL = L[:n]
    oR = R[:n]
    for i in range(n_on, n):
        g = 1.0 - (i - n_on) / r_n
        oL[i] *= g
        oR[i] *= g
    return oL, oR


def _trim_quiet(res, floor=1.0):
    """A drum take without the tail it has already rung out of. Every
    hit renders eight seconds so a cymbal can ring, and a kick is
    silent well before that. Samples here are in 16-bit units, so a
    floor of 1 is below the last bit the file can hold: nothing heard
    changes."""
    if res is None:
        return None
    L, R = res
    n = len(L)
    step = 512
    while n > step:
        lo = n - step
        if max(max(L[lo:n]), -min(L[lo:n]),
               max(R[lo:n]), -min(R[lo:n])) > floor:
            break
        n = lo
    if n >= len(L):
        return res
    return L[:n], R[:n]


_SLICE_MIN = 40      # notes: a stretch smaller than this isn't worth a fork


def _groups(jobs, percussion):
    """The notes split into as many groups as the computer has cores to
    spare, balanced by note count. A pitched part stays whole while
    there are enough parts to go round, so its round robins behave as in
    one process; a kit splits by piece — its
    cache and round robins are per piece already, and a kit's four
    microphones on every hit are most of a band's rendering."""
    import os as _os
    per = {}
    for j in jobs:
        unit = (j[2], j[3]) if percussion[j[2]] else (j[2], None)
        per.setdefault(unit, []).append(j)
    cores = max(1, min((_os.cpu_count() or 2) - 1, 16))

    def cost(js):
        # seconds of sound to render and mix: a drum hit rings on its
        # microphones, a single-line note stops at its cut, anything
        # else rings a little past its length
        t = 0.0
        for j in js:
            if percussion[j[2]]:
                t += 3.0
            elif j[10] is not None:
                t += max(j[10] - j[0], 0.05)
            else:
                t += j[1] + 1.0
        return t
    # a part heavier than its share of the cores, or too few players to
    # fill them (one instrument alone), splits into stretches of time —
    # the room and every note still sum exactly. Round robins restart at
    # each stretch: a different take, never a different note
    share = cost(jobs) / cores
    while True:
        unit, js = max(per.items(), key=lambda kv: cost(kv[1]))
        if len(js) < 2 * _SLICE_MIN or \
                (cost(js) <= share and len(per) >= cores):
            break
        js = sorted(js, key=lambda j: j[0])
        mid = len(js) // 2
        del per[unit]
        per[unit + ('a%d' % len(per),)] = js[:mid]
        per[unit + ('b%d' % len(per),)] = js[mid:]
    want = max(1, min(cores, len(per)))
    bins = [[] for _ in range(want)]
    sizes = [0] * want
    for idx, js in sorted(per.items(), key=lambda kv: -cost(kv[1])):
        k = sizes.index(min(sizes))
        bins[k] += js
        sizes[k] += cost(js)
    return [sorted(b, key=lambda j: j[0]) for b in bins if b]


def _play_parallel(groups, play, fresh, ticks, frames, sr, on_progress):
    """Each group rendered in its own forked process — its notes, its
    share of the room (the room is linear, so the rooms of the parts sum
    to the room of the whole) — and handed back as 32-bit PCM through
    shared memory; the sum, the level and the 16-bit file are audioop's.
    Returns the 16-bit stereo PCM, or None to fall back."""
    import multiprocessing
    import warnings
    from multiprocessing import shared_memory
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        import audioop
    ctx = multiprocessing.get_context('fork')
    size = frames * 2 * 4
    shms, procs = [], []

    def work(k, g, name):
        import os as _os
        import time as _t
        t0 = _t.time()
        shm = shared_memory.SharedMemory(name=name)
        L, R, wetL, wetR = fresh()
        span = play(g, L, R, wetL, wetR)
        t1 = _t.time()
        _room(L, R, wetL, wetR, sr, span)
        t2 = _t.time()
        lo, hi = span[0], min(frames, span[1] + int(_ROOM_TAIL * sr))
        if k == 0:
            ticks(L, R)             # dry, at the top: convert from 0
            lo = 0
        out = array('i', bytes(size))
        top = 2147483000.0
        for i in range(lo, max(hi, lo)):
            a = L[i] * _K
            b = R[i] * _K
            out[2 * i] = int(top if a > top else -top if a < -top else a)
            out[2 * i + 1] = int(top if b > top else -top if b < -top
                                 else b)
        shm.buf[:size] = out.tobytes()
        shm.close()
        if _os.environ.get('COPYIST_RENDER_TIMES'):
            import sys as _sys
            _sys.stderr.write(f"group {k}: {len(g)} notes, parts "
                              f"{sorted({j[2] for j in g})}, play "
                              f"{t1 - t0:.1f}s room {t2 - t1:.1f}s pcm "
                              f"{_t.time() - t2:.1f}s\n")

    try:
        for k, g in enumerate(groups):
            shm = shared_memory.SharedMemory(create=True, size=size)
            shms.append(shm)
            p = ctx.Process(target=work, args=(k, g, shm.name))
            p.start()
            procs.append(p)
        done = 0
        for p in procs:
            p.join()
            done += 1
            if on_progress:
                on_progress(done / len(procs), "the band is playing it in")
        if any(p.exitcode != 0 for p in procs):
            return None
        total = bytes(shms[0].buf[:size])
        for shm in shms[1:]:
            total = audioop.add(total, bytes(shm.buf[:size]), 4)
        peak = audioop.max(total, 4) or 1
        factor = 0.85 * 32767.0 / (peak / _K) / _K * 65536.0
        if os.environ.get('COPYIST_FIXED_GAIN'):
            factor = float(os.environ['COPYIST_FIXED_GAIN']) / _K \
                * 65536.0
        return audioop.lin2lin(audioop.mul(total, 4, factor), 4, 2)
    finally:
        for shm in shms:
            try:
                shm.close()
                shm.unlink()
            except FileNotFoundError:
                pass
