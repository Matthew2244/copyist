#!/usr/bin/env python3
"""sfz — an SFZ instrument reader and voice renderer, pure stdlib.

The other half of Copyist's ears. sf2.py plays General MIDI SoundFonts
— the guaranteed floor, every instrument covered. This module plays
SFZ instruments: a plain-text map plus recorded WAV samples, which is
the format every serious openly licensed library ships in (the
Salamander grand, the Karoryfer basses and saxes, Virtuosity and
Swirly drums, VSCO2 CE brass and winds). Same calling shape as sf2:
find the regions a note wants, render each to floats, let chartband
mix. Pitch bends and amplitude curves ride on top exactly as in sf2,
so scoops, falls and hairpin swells cost a library nothing.

Implemented opcodes, deliberately the set those libraries use:
regions/groups/global/master with inheritance and #include; lokey/
hikey/key/pitch_keycenter, lovel/hivel; seq_length/seq_position and
lorand/hirand round robins (a seeded counter per region set, so a
rebuild renders byte-identical audio); tune/transpose/pitch_keytrack;
volume/amplitude/pan/amp_veltrack; ampeg_ DAHDSR; loop_mode/
loop_start/loop_end (and smpl-chunk loops in the WAV itself);
trigger=attack/release (release regions are skipped — our notes end
on the page's say-so); group/off_by choking is reported to the
caller. WAVs may be 16 or 24 bit, mono or stereo; a missing sample
skips its region with one warning, never a crash.
"""
import math
import os
import re
import struct
from array import array

_NUM = re.compile(r'^-?\d+(\.\d+)?$')

_KEYNAME = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}


# where a sampler's controllers sit before anything moves them: volume
# 100, pan and balance centred, expression full (sfizz and the MIDI
# reset-all-controllers convention)
_CC_BOOT = {7: 100.0, 8: 64.0, 10: 64.0, 11: 127.0}


def _keynum(v):
    """An SFZ key: a MIDI number or a name like c4, f#3, eb2 (SFZ
    middle C = c4 = 60)."""
    v = v.strip().lower()
    if _NUM.match(v):
        return int(float(v))
    m = re.match(r'^([a-g])([#b]?)(-?\d+)$', v)
    if not m:
        return None
    n = _KEYNAME[m.group(1)] + (1 if m.group(2) == '#' else
                                -1 if m.group(2) == 'b' else 0)
    return n + (int(m.group(3)) + 1) * 12


def _tokens(text):
    """opcode=value pairs; a value runs to the next opcode= or header.
    Sample paths may hold spaces, so 'the next opcode' is the split."""
    text = re.sub(r'//[^\n]*', '', text)
    out = []
    for m in re.finditer(r'<(\w+)>|(\w+)=', text):
        if m.group(1):
            out.append(('<>', m.group(1), m.start(), m.end()))
        else:
            out.append(('=', m.group(2), m.start(), m.end()))
    items = []
    for i, (kind, name, s, e) in enumerate(out):
        if kind == '<>':
            items.append(('header', name, None))
        else:
            end = out[i + 1][2] if i + 1 < len(out) else len(text)
            items.append(('op', name.lower(), text[e:end].strip()))
    return items


class Region(dict):
    __slots__ = ()


class SfzInstrument:
    """One parsed .sfz and its sample folder."""

    def __init__(self, path):
        self.path = path
        self.dir = os.path.dirname(os.path.abspath(path))
        self.regions = []
        self._wavs = {}
        self._seq = {}
        self._rand = 0.5
        self._warned = set()
        text = self._read(path, depth=0)
        # sfz v2 #define: collect after includes, substitute longest
        # names first so $KICK never eats $KICK_SUB
        defs = dict(re.findall(r'#define\s+(\$\w+)\s+(\S+)', text))
        if defs:
            text = re.sub(r'#define[^\n]*', '', text)
            for name in sorted(defs, key=len, reverse=True):
                text = text.replace(name, defs[name])
        scope = {'global': {}, 'master': {}, 'group': {}}
        cur = None
        default_path = ''
        in_control = False
        self.cc = {}                    # control-header CC defaults
        self.makeup = 1.0               # the caller's level trim
        for kind, name, val in _tokens(text):
            if kind == 'header':
                in_control = name == 'control'
                if name == 'global':
                    scope = {'global': {}, 'master': {}, 'group': {}}
                    cur = scope['global']
                elif name == 'master':
                    scope['master'] = {}
                    scope['group'] = {}
                    cur = scope['master']
                elif name == 'group':
                    scope['group'] = {}
                    cur = scope['group']
                elif name == 'region':
                    r = Region()
                    r.update(scope['global'])
                    r.update(scope['master'])
                    r.update(scope['group'])
                    self.regions.append(r)
                    cur = r
                else:
                    cur = {}
            elif kind == 'op':
                if in_control and name == 'default_path':
                    default_path = val.replace('\\', os.sep)
                elif in_control and name.startswith('set_cc'):
                    try:
                        self.cc[int(name[6:])] = float(val)
                    except ValueError:
                        pass
                elif cur is not None:
                    cur[name] = val
        self.default_path = default_path
        # drop release-trigger and empty regions once, up front
        self.regions = [r for r in self.regions
                        if 'sample' in r
                        and r.get('trigger', 'attack') in ('attack',
                                                           'first',
                                                           'legato')]

    def _read(self, path, depth):
        """#include paths resolve against the ROOT .sfz's folder, per
        the format — Virtuosity's nested maps say so from two levels
        down. A path that misses there is retried beside the including
        file, for the libraries that assumed otherwise."""
        if depth > 8:
            return ''
        try:
            text = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            return ''
        here = os.path.dirname(os.path.abspath(path))

        def inc(m):
            rel = m.group(1).replace('\\', os.sep)
            p = os.path.join(self.dir, rel)
            if not os.path.exists(p):
                p = os.path.join(here, rel)
            return self._read(p, depth + 1)
        return re.sub(r'#include\s+"([^"]+)"', inc, text)

    # ------------------------------------------------------------ sound

    def _wav(self, rel):
        """The sample, preferring a .wav sibling over the named file —
        FLAC libraries get .wav twins at install time, and the twin is
        what a pure-Python reader can play."""
        rel = rel.replace('\\', os.sep)
        key = rel.lower()
        if key in self._wavs:
            return self._wavs[key]
        p = os.path.join(self.dir, self.default_path, rel)
        stem, ext = os.path.splitext(p)
        data = None
        tries = [stem + '.wav', stem + '.WAV', stem + '.Wav']
        if ext.lower() == '.wav':
            tries.insert(0, p)
        else:
            tries.append(p)
        for cand in tries:
            if os.path.exists(cand):
                data = _read_wav(cand)
                if data is not None:
                    break
        if data is None and rel not in self._warned:
            self._warned.add(rel)
        self._wavs[key] = data
        return data

    def _mod(self, r, base_name, default):
        """An opcode plus its CC modulations at the control header's
        default CC values — how Karoryfer sets real envelopes (their
        base sustain is 0; set_cc103=127 is what makes notes sustain)
        and how Virtuosity exposes its tuning knobs. curvecc 1 reads
        bipolar, centered CCs mean no change."""
        try:
            v = float(r.get(base_name, default))
        except (TypeError, ValueError):
            v = default
        for k, raw in r.items():
            n = None
            if k.startswith(base_name + '_oncc'):
                tail = k[len(base_name) + 5:]
            elif k.startswith(base_name + '_cc'):
                tail = k[len(base_name) + 3:]
            elif k.startswith(base_name + 'cc') and \
                    k[len(base_name) + 2:].isdigit():
                # SFZ 1's spelling, ampeg_attackcc55: Swirly Drums sets
                # its brush stirs' length this way; unread, every stir
                # lasted no time at all
                tail = k[len(base_name) + 2:]
            else:
                continue
            try:
                n = int(tail)
                amt = float(raw)
            except (TypeError, ValueError):
                continue
            cc = self.cc.get(n, 0.0)
            curve = r.get(base_name + '_curvecc%d' % n)
            if curve == '1':
                v += amt * (cc - 63.5) / 63.5
            else:
                v += amt * cc / 127.0
        return v

    def _cc_ok(self, r, cc):
        """A region's CC gates (loccN/hiccN) against the controllers as
        they stand. A drum kit switches its microphones, snare wires and
        hi-hat pedal this way: ignored, every mic and every pedal
        position sounded at once — an open hat under every closed one,
        and a render four times the work (2026-09-28)."""
        for k, raw in r.items():
            if k.startswith('locc') or k.startswith('hicc'):
                try:
                    n = int(k[4:])
                    lim = float(raw)
                except ValueError:
                    continue
                v = cc.get(n) if cc and n in cc else \
                    self.cc.get(n, _CC_BOOT.get(n, 0.0))
                if k[0] == 'l' and v < lim or k[0] == 'h' and v > lim:
                    return False
        return True

    def regions_for(self, key, vel, cc=None):
        """The regions this note plays: key, velocity and CC windows,
        then one winner per round-robin set (seq counters and the shared
        random draw both advance deterministically). cc overrides the
        control header's defaults for this note."""
        cands = []
        for r in self.regions:
            lo = _keynum(r.get('lokey', r.get('key', '0')))
            hi = _keynum(r.get('hikey', r.get('key', '127')))
            if lo is None or hi is None or not lo <= key <= hi:
                continue
            if not int(r.get('lovel', 1)) <= vel <= int(r.get('hivel',
                                                              127)):
                continue
            cands.append(r)
        if not cands:
            return []
        # CC gates choose among what the key holds; a library whose
        # controllers are set by a program we never load would gate
        # everything out, and silence is never the right reading
        gated = [r for r in cands if self._cc_ok(r, cc)]
        if gated:
            cands = gated
        # round robins: one counter per seq set, advanced once per
        # NOTE — every region in the set reads the same draw, so file
        # order cannot starve a position. lorand/hirand sets share one
        # advancing deterministic draw per call.
        self._rand = (self._rand * 16807.0) % 1.0 or 0.42
        rnd = self._rand
        out, seqs = [], {}
        for r in cands:
            sl = int(r.get('seq_length', 1))
            if sl > 1:
                bucket = (r.get('lokey', r.get('key', '')),
                          str(r.get('lovel', '')), sl)
                seqs.setdefault(bucket, []).append(r)
            else:
                out.append(r)
        for bucket, rs in seqs.items():
            n = self._seq.get(bucket, 0)
            self._seq[bucket] = n + 1
            want = (n % bucket[2]) + 1
            out.extend(r for r in rs
                       if int(r.get('seq_position', 1)) == want)
        return [r for r in out
                if not ('lorand' in r or 'hirand' in r)
                or float(r.get('lorand') or 0) <= rnd
                < float(r.get('hirand') or 1)]

    def render_region(self, r, key, vel, dur, sr, bend=None,
                      brightness=1.0, amps=None, detune=0.0, into=None,
                      limit=None):
        """One region -> (L floats, R floats) or None. brightness is
        accepted for engine symmetry; recorded dynamics come from
        velocity layers here, so it only trims level a touch."""
        wav = self._wav(r['sample'])
        if wav is None:
            return None
        smpL, smpR, wsr, loop = wav
        root = _keynum(r.get('pitch_keycenter',
                             r.get('key', str(key))))
        if root is None:
            root = 60
        keytrack = float(r.get('pitch_keytrack', 100)) / 100.0
        semis = ((key - root) * keytrack
                 + float(r.get('transpose', 0))
                 + self._mod(r, 'tune', 0.0) / 100.0 + detune)
        base_step = (wsr / sr) * (2.0 ** (semis / 12.0))

        lm = r.get('loop_mode')
        if lm is None:
            lm = 'loop_continuous' if (loop and 'loop_start' not in r) \
                else 'no_loop'
        loop_s = int(float(r.get('loop_start', loop[0] if loop else 0)))
        loop_e = int(float(r.get('loop_end', loop[1] if loop else 0)))
        looping = lm in ('loop_continuous', 'loop_sustain') \
            and loop_e > loop_s

        v = max(1, min(vel, 127)) / 127.0
        veltrack = float(r.get('amp_veltrack', 100)) / 100.0
        vgain = 1.0 - veltrack + veltrack * v * v
        gain = vgain * 10.0 ** (float(r.get('volume', 0)) / 20.0) \
            * float(r.get('amplitude', 100)) / 100.0 \
            * min(brightness, 1.0) * self.makeup
        pan = min(max(self._mod(r, 'pan', 0.0), -100.0),
                  100.0) / 100.0                 # -1..1

        atk = max(self._mod(r, 'ampeg_attack', 0.001), 0.0)
        hold = max(self._mod(r, 'ampeg_hold', 0.0), 0.0)
        dec = max(self._mod(r, 'ampeg_decay', 0.0), 0.0)
        sus = min(max(self._mod(r, 'ampeg_sustain', 100.0), 0.0),
                  100.0) / 100.0
        rel = max(self._mod(r, 'ampeg_release', 0.08), 0.01)

        n_on = max(int(dur * sr), 1)
        n = n_on + int(rel * sr) + 1
        if limit is not None:
            # the caller stops the note here: nothing past it is heard
            n = max(min(n, int(limit * sr) + 1), 1)
        # constant-power pan on top of the file's own stereo
        if pan:
            pgl = math.cos((pan + 1.0) * math.pi / 4.0) * 1.41421
            pgr = math.sin((pan + 1.0) * math.pi / 4.0) * 1.41421
        else:
            pgl = pgr = 1.0
        if into is not None:
            # mixed straight into the note: no second pass per region
            outL, outR = into
            if len(outL) < n:
                outL.extend(array('f', bytes(4 * (n - len(outL)))))
                outR.extend(array('f', bytes(4 * (n - len(outR)))))
            aL, aR = pgl, pgr
        else:
            outL = array('f', bytes(4 * n))
            outR = array('f', bytes(4 * n))
            aL = aR = 1.0
        a_n = max(int(atk * sr), 1)
        h_end = a_n + int(hold * sr)
        d_n = max(int(dec * sr), 1)
        r_n = max(int(rel * sr), 1)
        end_f = len(smpL) - 2
        if bend:
            bend = list(bend)
        if amps:
            amps = list(amps)

        pos = float(r.get('offset', 0))
        i = 0
        amul = gain
        env = sus
        rel_base = None
        stereo = smpR is not None
        loop_len = float(loop_e - loop_s) if looping else 0.0
        fade_src = max(0.008 * sr * base_step, 1.0)
        while i < n:
            if bend or amps:
                t = i / sr
                step = base_step * (2.0 ** (_interp(bend, t) / 12.0)
                                    if bend else 1.0)
                amul = gain * (_interp(amps, t) if amps else 1.0)
                block = min(n - i, int(sr * 0.005) or 1)
            else:
                step = base_step
                block = n - i
            for _ in range(block):
                ip = int(pos)
                if looping and (lm == 'loop_continuous' or i < n_on) \
                        and ip >= loop_e - 1:
                    pos -= loop_len
                    ip = int(pos)
                if pos >= end_f:
                    i = n
                    break
                frac = pos - ip
                # a note that outlasts its recording fades over the
                # last few milliseconds — stopping dead mid-wave is a
                # click, and a band of them is static (2026-09-28)
                left = end_f - pos
                if left < fade_src and not (
                        looping and (lm == 'loop_continuous' or i < n_on)):
                    edge = left / fade_src
                else:
                    edge = 1.0
                if i >= n_on:
                    # the note is over: release, from wherever the
                    # envelope actually was — whatever stage it was in.
                    # Letting attack, hold or decay run on past the
                    # note's end kept short notes ringing at full and
                    # then dropped them in one sample: a click per note,
                    # static across a band (2026-09-28)
                    if rel_base is None:
                        rel_base = env
                    env = rel_base * max(0.0, 1.0 - (i - n_on) / r_n)
                    if env <= 0.0:
                        i = n
                        break
                elif i < a_n:
                    env = i / a_n
                elif i < h_end:
                    env = 1.0
                elif i < h_end + d_n:
                    env = 1.0 + (sus - 1.0) * (i - h_end) / d_n
                else:
                    env = sus
                g = env * amul * edge
                vl = (smpL[ip] * (1.0 - frac) + smpL[ip + 1] * frac) * g
                outL[i] += vl * aL
                if stereo:
                    outR[i] += (smpR[ip] * (1.0 - frac)
                                + smpR[ip + 1] * frac) * g * aR
                else:
                    outR[i] += vl * aR
                pos += step
                i += 1
        if into is not None:
            return True
        return outL, outR, pgl, pgr

    def render_note(self, key, vel, dur, sr, bend=None, brightness=1.0,
                    amps=None, detune=0.0, cc=None, limit=None):
        """A note through every winning region -> (L, R) float arrays,
        or None when nothing matched (the caller may fall back)."""
        L = array('f')
        R = array('f')
        got = False
        for r in self.regions_for(key, vel, cc):
            if self.render_region(r, key, vel, dur, sr, bend=bend,
                                  brightness=brightness, amps=amps,
                                  detune=detune, into=(L, R),
                                  limit=limit):
                got = True
        if not got:
            return None
        return L, R


def _interp(bp, t):
    if not bp:
        return 0.0
    if t <= bp[0][0]:
        return bp[0][1]
    for (t0, v0), (t1, v1) in zip(bp, bp[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(t1 - t0, 1e-9)
    return bp[-1][1]


def _read_wav(path):
    """A WAV -> (L floats, R floats or None, sample rate, loop or
    None). Handles 16 and 24 bit PCM (and float32); reads the smpl
    chunk's first loop when present, because piano libraries keep
    their loops in the file."""
    buf = open(path, 'rb').read()
    if buf[:4] != b'RIFF' or buf[8:12] != b'WAVE':
        return None
    pos = 12
    fmt = None
    data = None
    loop = None
    while pos + 8 <= len(buf):
        cc = buf[pos:pos + 4]
        size = struct.unpack_from('<I', buf, pos + 4)[0]
        body = buf[pos + 8:pos + 8 + size]
        if cc == b'fmt ':
            fmt = struct.unpack_from('<HHIIHH', body, 0)
        elif cc == b'data':
            data = body
        elif cc == b'smpl' and len(body) >= 60:
            nloops = struct.unpack_from('<I', body, 28)[0]
            if nloops:
                s, e = struct.unpack_from('<II', body, 44)[0:2]
                if e > s:
                    loop = (s, e)
        pos += 8 + size + (size & 1)
    if not fmt or data is None:
        return None
    tag, nch, rate, _, _, bits = fmt
    if tag == 0xFFFE and bits in (16, 24, 32):
        tag = 1
    n = len(data) // (nch * bits // 8)
    if bits == 16 and tag == 1:
        raw = array('h')
        raw.frombytes(data[:n * nch * 2])
        import sys
        if sys.byteorder == 'big':
            raw.byteswap()
        scale = 1.0 / 32768.0
        chans = [array('f', bytes(4 * n)) for _ in range(min(nch, 2))]
        for c in range(len(chans)):
            ch = chans[c]
            for i in range(n):
                ch[i] = raw[i * nch + c] * scale
    elif bits == 24 and tag == 1:
        scale = 1.0 / 8388608.0
        chans = [array('f', bytes(4 * n)) for _ in range(min(nch, 2))]
        stride = nch * 3
        for c in range(len(chans)):
            ch = chans[c]
            off = c * 3
            for i in range(n):
                j = i * stride + off
                v = data[j] | (data[j + 1] << 8) | (data[j + 2] << 16)
                if v >= 8388608:
                    v -= 16777216
                ch[i] = v * scale
    elif bits == 32 and tag == 3:
        raw = array('f')
        raw.frombytes(data[:n * nch * 4])
        import sys
        if sys.byteorder == 'big':
            raw.byteswap()
        chans = [array('f', bytes(4 * n)) for _ in range(min(nch, 2))]
        for c in range(len(chans)):
            ch = chans[c]
            for i in range(n):
                ch[i] = raw[i * nch + c]
    else:
        return None
    L = chans[0]
    R = chans[1] if len(chans) > 1 else None
    # scale to the sf2 module's 16-bit-ish range so chartband's gain
    # staging treats both engines alike
    for ch in (L, R) if R is not None else (L,):
        for i in range(len(ch)):
            ch[i] *= 30000.0
    return L, R, rate, loop
