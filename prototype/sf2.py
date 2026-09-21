#!/usr/bin/env python3
"""sf2 — a SoundFont 2 reader and voice renderer, pure stdlib.

Copyist's listen path plays recorded instruments — real players — and
this module is the whole engine: it parses an .sf2 library (RIFF
chunks, preset and instrument zones, generators, 16-bit samples) and
renders single notes as float sample blocks. No fluidsynth, no
MuseScore, no compiled extension; the same file runs on a bare Windows
box. chartaudio drives it and remains the only caller.

What is implemented, deliberately: key/velocity zone selection with
preset-over-instrument generator combination per the spec (preset
generators are relative, instrument generators absolute), the volume
envelope (DAHDSR in timecents and centibels), sample loops (modes 1
and 3), root-key/tuning/scale-tuning pitch math, a resonant state-
variable lowpass for initialFilterFc plus dynamics-driven brightness,
stereo sample pairs via per-zone pan, exclusiveClass choking (hi-hats),
and a per-voice pitch-bend curve — that last one is how scoops, plops,
falls and doits happen. Modulators are not implemented; the default
velocity-to-attenuation and velocity-to-filter curves live here
instead, which is what nearly every GM library assumes anyway.
"""
import math
import struct
from array import array

# ------------------------------------------------------------- the file


def _chunks(buf, pos, end):
    """Yield (fourcc, start, size) for each chunk in buf[pos:end]."""
    while pos + 8 <= end:
        cc = buf[pos:pos + 4].decode('latin-1')
        size = struct.unpack_from('<I', buf, pos + 4)[0]
        yield cc, pos + 8, size
        pos += 8 + size + (size & 1)


GEN_KEY_RANGE = 43
GEN_VEL_RANGE = 44
GEN_INSTRUMENT = 41
GEN_SAMPLE_ID = 53

# generators that are indices or ranges never add preset-over-instrument
_NON_ADDITIVE = {GEN_KEY_RANGE, GEN_VEL_RANGE, GEN_INSTRUMENT,
                 GEN_SAMPLE_ID, 54, 57, 58}


class SoundFont:
    """One parsed .sf2. Presets keyed (bank, program); samples stay in
    the file's own 16-bit array and are only converted per rendered
    voice, so a 400 MB library costs its file size once, not 4x."""

    def __init__(self, path):
        self.path = path
        buf = open(path, 'rb').read()
        if buf[:4] != b'RIFF' or buf[8:12] != b'sfbk':
            raise ValueError('%s is not a SoundFont' % path)
        self.name = ''
        smpl = None
        lists = {}
        for cc, start, size in _chunks(buf, 12, len(buf)):
            if cc == 'LIST':
                lists[buf[start:start + 4].decode('latin-1')] = \
                    (start + 4, size - 4)
        info_start, info_size = lists['INFO']
        for cc, start, size in _chunks(buf, info_start,
                                       info_start + info_size):
            if cc == 'INAM':
                self.name = buf[start:start + size].split(b'\0')[0] \
                    .decode('latin-1')
        sd_start, sd_size = lists['sdta']
        for cc, start, size in _chunks(buf, sd_start, sd_start + sd_size):
            if cc == 'smpl':
                smpl = array('h')
                smpl.frombytes(buf[start:start + size - (size & 1)])
        if smpl is None:
            raise ValueError('%s has no sample data' % path)
        import sys
        if sys.byteorder == 'big':
            smpl.byteswap()
        self.smpl = smpl

        pd_start, pd_size = lists['pdta']
        raw = {}
        for cc, start, size in _chunks(buf, pd_start, pd_start + pd_size):
            raw[cc] = buf[start:start + size]

        def records(cc, fmt, size):
            data = raw[cc]
            return [struct.unpack_from(fmt, data, i)
                    for i in range(0, len(data) - size + 1, size)]

        phdr = records('phdr', '<20sHHHIII', 38)
        pbag = records('pbag', '<HH', 4)
        pgen = records('pgen', '<Hh', 4)
        inst = records('inst', '<20sH', 22)
        ibag = records('ibag', '<HH', 4)
        igen = records('igen', '<Hh', 4)
        self.shdr = records('shdr', '<20sIIIIIBbHH', 46)

        def zones(bags, gens, lo, hi):
            out = []
            for b in range(lo, hi):
                g0 = bags[b][0]
                g1 = bags[b + 1][0] if b + 1 < len(bags) else len(gens)
                out.append({op: amt for op, amt in gens[g0:g1]})
            return out

        insts = []
        for i in range(len(inst) - 1):
            insts.append(zones(ibag, igen, inst[i][1], inst[i + 1][1]))

        self.presets = {}
        for i in range(len(phdr) - 1):
            name, program, bank, bag0 = phdr[i][:4]
            bag1 = phdr[i + 1][3]
            pzones = zones(pbag, pgen, bag0, bag1)
            pglobal = {}
            expanded = []
            for z in pzones:
                if GEN_INSTRUMENT not in z:
                    pglobal = z          # a global preset zone
                    continue
                izones = insts[z[GEN_INSTRUMENT]]
                iglobal = {}
                for iz in izones:
                    if GEN_SAMPLE_ID not in iz:
                        iglobal = iz
                        continue
                    gen = dict(iglobal)
                    gen.update(iz)       # local instrument zone wins
                    for src in (pglobal, z):
                        for op, amt in src.items():
                            if op == GEN_INSTRUMENT:
                                continue
                            if op in _NON_ADDITIVE:
                                gen.setdefault(op, amt)
                            else:
                                gen[op] = gen.get(op, _DEFAULT.get(op, 0)) \
                                    + amt
                    expanded.append(gen)
            self.presets[(bank, program)] = {
                'name': name.split(b'\0')[0].decode('latin-1').strip(),
                'zones': expanded}

    def preset(self, bank, program):
        """The preset, GM-style fallbacks included: a missing bank
        falls to bank 0; a missing percussion program falls to the
        standard kit."""
        for key in ((bank, program), (0, program),
                    ((128, 0) if bank == 128 else (0, 0))):
            if key in self.presets:
                return self.presets[key]
        return None


# defaults per the SF2 spec, for the generators the math below reads
_DEFAULT = {
    33: -12000, 34: -12000, 35: -12000, 36: -12000,  # vol env timecents
    37: 0, 38: -12000,                               # sustain cB, release
    8: 13500, 9: 0,                                  # filter Fc, Q
    17: 0, 48: 0, 51: 0, 52: 0, 56: 100, 58: -1,
    54: 0,
}


def _g(gen, op):
    return gen.get(op, _DEFAULT.get(op, 0))


def _tc2sec(tc):
    """Timecents to seconds; the spec's -32768 means instant."""
    if tc <= -12000:
        return 0.0
    return 2.0 ** (tc / 1200.0)


# ---------------------------------------------------------------- voices


def zones_for(preset, key, vel):
    out = []
    for gen in preset['zones']:
        if GEN_KEY_RANGE in gen:
            lo, hi = gen[GEN_KEY_RANGE] & 0xFF, (gen[GEN_KEY_RANGE] >> 8) & 0xFF
            if not lo <= key <= hi:
                continue
        if GEN_VEL_RANGE in gen:
            lo, hi = gen[GEN_VEL_RANGE] & 0xFF, (gen[GEN_VEL_RANGE] >> 8) & 0xFF
            if not lo <= vel <= hi:
                continue
        out.append(gen)
    return out


def render_zone(sf, gen, key, vel, dur, sr, bend=None, brightness=1.0,
                amps=None, detune=0.0):
    """One zone of one note -> (mono float array, pan -500..500).

    dur is the sounding length in seconds; the release tail plays past
    it. bend is None or a list of (time_sec, semitones) breakpoints —
    linearly interpolated, applied on top of the zone's own pitch.
    amps is the same shape for amplitude (1.0 = as struck): hairpin
    swells and the dying end of a fall both live there. brightness
    scales the filter cutoff; dynamics own it."""
    sh = sf.shdr[gen[GEN_SAMPLE_ID]]
    (sname, start, end, loop_s, loop_e, srate,
     orig_key, correction, slink, stype) = sh
    start += _g(gen, 0) + 32768 * _g(gen, 4)
    end += _g(gen, 1) + 32768 * _g(gen, 12)
    loop_s += _g(gen, 2) + 32768 * _g(gen, 45)
    loop_e += _g(gen, 3) + 32768 * _g(gen, 50)
    root = _g(gen, 58)
    if root < 0:
        root = orig_key if orig_key <= 127 else 60
    if 46 in gen and 0 <= gen[46] <= 127:
        key = gen[46]
    if 47 in gen and 0 <= gen[47] <= 127:
        vel = gen[47]

    semis = ((key - root) * _g(gen, 56) / 100.0 + _g(gen, 51)
             + _g(gen, 52) / 100.0 + correction / 100.0 + detune)
    base_step = (srate / sr) * (2.0 ** (semis / 12.0))

    mode = _g(gen, 54) & 3
    looping = mode in (1, 3) and loop_e > loop_s

    # envelope, in samples at the output rate
    delay = int(_tc2sec(_g(gen, 33)) * sr)
    attack = int(_tc2sec(_g(gen, 34)) * sr)
    hold = int(_tc2sec(_g(gen, 35)) * sr)
    decay = int(_tc2sec(_g(gen, 36)) * sr)
    sus_cb = min(max(_g(gen, 37), 0), 1440)
    sustain = 10.0 ** (-sus_cb / 200.0)
    release = int(_tc2sec(_g(gen, 38)) * sr) or 1

    # velocity: quieter is also darker — the curve every GM font assumes
    v = max(1, min(vel, 127)) / 127.0
    amp = (v * v) * 10.0 ** (-min(max(_g(gen, 48), 0), 1440) / 200.0)

    fc_cents = _g(gen, 8)
    fc = 8.176 * 2.0 ** (fc_cents / 1200.0) * brightness * (0.6 + 0.7 * v)
    fc = min(max(fc, 80.0), 18000.0)
    q_db = min(max(_g(gen, 9), 0), 960) / 10.0
    # the Chamberlin SVF is only stable below about sr/6 — above that
    # the ear can't hear a lowpass anyway, so bypass instead of blow up
    use_filter = fc < sr / 6.5
    f1 = 2.0 * math.sin(math.pi * min(fc, sr / 6.5) / sr)
    damp = min(2.0 * 10.0 ** (-q_db / 20.0), 1.9)

    n_on = max(int(dur * sr), 1)
    n = n_on + release
    smpl = sf.smpl
    out = array('f', bytes(4 * n))
    pos = float(start)
    end_f = float(end - 1)
    loop_len = float(loop_e - loop_s)
    low = band = 0.0
    env = sustain
    rel_base = None
    if bend:
        bend = list(bend)
    if amps:
        amps = list(amps)

    i = 0
    amul = 1.0
    while i < n:
        # pitch and swell for this block: constant unless a curve moves
        if bend or amps:
            t = i / sr
            step = base_step * (2.0 ** (_bend_at(bend, t) / 12.0)
                                if bend else 1.0)
            amul = _bend_at(amps, t) if amps else 1.0
            block = min(n - i, int(sr * 0.005) or 1)
        else:
            step = base_step
            block = n - i
        for _ in range(block):
            ip = int(pos)
            if looping and (mode == 1 or i < n_on) and ip >= loop_e - 1:
                pos -= loop_len
                ip = int(pos)
            if pos >= end_f:
                i = n
                break
            frac = pos - ip
            s = smpl[ip] * (1.0 - frac) + smpl[ip + 1] * frac
            # envelope
            if i >= n_on:
                # release fades from wherever the note actually was —
                # restarting at full is an audible pop
                if rel_base is None:
                    rel_base = env
                env = rel_base * max(0.0, 1.0 - (i - n_on) / release)
                if env <= 0.0:
                    i = n
                    break
            elif i < delay:
                env = 0.0
            elif i < delay + attack:
                env = (i - delay) / attack
            elif i < delay + attack + hold:
                env = 1.0
            elif i < delay + attack + hold + decay:
                f = (i - delay - attack - hold) / decay
                env = 1.0 + (sustain - 1.0) * f
            else:
                env = sustain
            if use_filter:
                low += f1 * band
                high = s - low - damp * band
                band += f1 * high
                s = low
            out[i] = s * env * amp * amul
            pos += step
            i += 1
    return out, _g(gen, 17)


def _bend_at(bend, t):
    if t <= bend[0][0]:
        return bend[0][1]
    for (t0, s0), (t1, s1) in zip(bend, bend[1:]):
        if t <= t1:
            return s0 + (s1 - s0) * (t - t0) / max(t1 - t0, 1e-9)
    return bend[-1][1]


def render_note(sf, bank, program, key, vel, dur, sr,
                bend=None, brightness=1.0, amps=None, detune=0.0):
    """A whole note: every matching zone rendered and panned into a
    stereo pair of float arrays, sample-frame length matched."""
    preset = sf.preset(bank, program)
    if preset is None:
        return None
    parts = []
    for gen in zones_for(preset, key, vel):
        mono, pan = render_zone(sf, gen, key, vel, dur, sr, bend=bend,
                                brightness=brightness, amps=amps,
                                detune=detune)
        parts.append((mono, pan))
    if not parts:
        return None
    n = max(len(m) for m, _ in parts)
    L = array('f', bytes(4 * n))
    R = array('f', bytes(4 * n))
    for mono, pan in parts:
        p = min(max(pan / 500.0, -1.0), 1.0)      # -1 left .. +1 right
        gl = math.cos((p + 1.0) * math.pi / 4.0)
        gr = math.sin((p + 1.0) * math.pi / 4.0)
        for i, s in enumerate(mono):
            L[i] += s * gl
            R[i] += s * gr
    return L, R


def exclusive_class(preset, key, vel):
    """The zone's exclusiveClass, for hi-hat style choking; 0 = none."""
    for gen in zones_for(preset, key, vel):
        ec = gen.get(57, 0)
        if ec:
            return ec
    return 0
