"""Every listen at one loudness: -16 LUFS integrated (ITU-R BS.1770,
gated), never over -1 dB true peak.

Matthew's call, 2026-10-27. The listens used to be scaled so the
loudest sample sat at 0.85 of full scale, which made each one as loud
as its single loudest moment: a big band shout and a ballad came out
anywhere from -19.8 to -26.6 LUFS, so every new listen meant reaching
for the volume. Now the whole song is raised (or lowered) to -16, and
a look-ahead peak limiter catches what then goes over the ceiling.

The work is split so the slow part can run on every core: k_energies
is the only per-sample loop (the K-weighting filters), and it runs
over any stretch of the song on its own, handing back the power of
each 0.7 ms block, as true_peaks does the peaks. Everything after
that, the gating, the gain and the limiter, runs on those blocks,
cheap enough for the parent. gain_ramp turns the block gains back into one gain per sample
for whoever writes the file.

Stdlib only, like the rest of the engine."""

import math
from collections import deque

TARGET = -16.0          # LUFS, integrated
CEILING = -1.0          # dBTP
_LOOK = 0.003           # seconds the limiter looks ahead
_RELEASE = 0.15         # seconds it takes to let go
_MARGIN = 0.4           # dB aimed under the ceiling


def kweight_coeffs(sr):
    """ITU-R BS.1770's K-weighting as two biquads at this sample rate:
    the head's high shelf (+4 dB above ~1.7 kHz) and the RLB high-pass
    (~38 Hz) — the curve loudness meters (LUFS) hear through."""
    f0, g, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / sr)
    vh = 10 ** (g / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = ((vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0,
             (vh - vb * k / q + k * k) / a0, 2 * (k * k - 1) / a0,
             (1 - k / q + k * k) / a0)
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / sr)
    a0 = 1 + k / q + k * k
    hp = (1.0, -2.0, 1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0)
    return shelf, hp


def hop_of(sr):
    """Samples in one 100 ms loudness block."""
    return sr // 10


def blk_of(sr):
    """Samples in one limiter block: about 0.7 ms, and a whole number of
    them to each 100 ms (30 at 44.1 kHz, 32 at 48)."""
    hop = hop_of(sr)
    return max(d for d in range(1, 33) if hop % d == 0)


def k_energies(chans, sr, skip=0):
    """The K-weighted power of each limiter block, summed over the
    channels: a list of sums of squares, one per blk_of(sr) samples,
    starting at sample `skip` (the samples before it only warm the
    filters up). The last block may be short. Fine blocks rather than
    100 ms ones because the limiter's cut lands on the hits, where the
    energy is: spreading it over 100 ms predicted -16.0 for a file that
    measured -16.5."""
    hop = blk_of(sr)
    shelf, hp = kweight_coeffs(sr)
    sb0, sb1, sb2, sa1, sa2 = shelf
    hb0, hb1, hb2, ha1, ha2 = hp
    out = None
    for x in chans:
        n = len(x)
        sums = [0.0] * (-(-(n - skip) // hop))
        x1 = x2 = y1 = y2 = z1 = z2 = 0.0
        acc, cnt, bi = 0.0, 0, 0
        for i in range(n):
            v = x[i]
            y = sb0 * v + sb1 * x1 + sb2 * x2 - sa1 * y1 - sa2 * y2
            x2, x1 = x1, v
            z = hb0 * y + hb1 * y1 + hb2 * y2 - ha1 * z1 - ha2 * z2
            y2, y1 = y1, y
            z2, z1 = z1, z
            if i >= skip:
                acc += z * z
                cnt += 1
                if cnt == hop:
                    sums[bi] = acc
                    bi += 1
                    acc, cnt = 0.0, 0
        if cnt:
            sums[bi] = acc
        out = sums if out is None else [a + b for a, b in zip(out, sums)]
    return out or []


def integrated(fine, sr, gain=1.0, g=None):
    """Integrated loudness, in LUFS, of the signal those block energies
    came from, scaled by `gain` and by the limiter's block gains `g`
    when given: 400 ms windows every 100 ms, the absolute gate at -70
    LUFS and the relative one 10 LU under. None when nothing is above
    the gate."""
    hop = hop_of(sr)
    per = hop // blk_of(sr)
    if g is not None:
        fine = [e * v * v for e, v in zip(fine, g)]
    energies = [sum(fine[k:k + per]) for k in range(0, len(fine), per)]
    g2 = gain * gain
    zs = []
    for k in range(len(energies) - 3):
        z = (energies[k] + energies[k + 1] + energies[k + 2]
             + energies[k + 3]) * g2 / (4 * hop)
        if z > 0 and -0.691 + 10 * math.log10(z) > -70.0:
            zs.append(z)
    if not zs:
        return None
    rel = -0.691 + 10 * math.log10(sum(zs) / len(zs)) - 10.0
    kept = [z for z in zs if -0.691 + 10 * math.log10(z) > rel]
    return -0.691 + 10 * math.log10(sum(kept) / len(kept))


def block_peaks(chans, blk):
    """The largest magnitude in each block, over the channels, and
    where each channel's own peak in the block sits, so the true-peak
    check can look around them."""
    n = min(len(x) for x in chans)
    peaks, where = [], []
    for a in range(0, n, blk):
        best, at = 0.0, []
        for x in chans:
            s = x[a:a + blk]
            hi, lo = max(s), min(s)
            i = a + (s.index(hi) if hi >= -lo else s.index(lo))
            at.append(i)
            best = max(best, hi, -lo)
        peaks.append(best)
        where.append(at)
    return peaks, where


def true_peaks(chans, blk, skip=0, upto=None):
    """The largest magnitude in each block of samples skip..upto-1,
    over the channels, counting the point halfway between every two
    samples as well as the samples: where the waveform a DAC draws
    usually goes over when a meter's true peak does. An 8-tap
    half-sample interpolator run as C-speed passes over the whole
    stretch, not a loop per sample, so it can see every pair rather
    than only those beside each block's loudest sample (a test of hard
    hits found +0.4 dB overs that way). Samples outside the stretch, if
    the arrays have them, feed the interpolator at its edges."""
    import operator
    from itertools import repeat
    n = min(len(x) for x in chans)
    upto = n if upto is None else upto
    taps = []
    for k in range(-3, 5):
        d = k - 0.5
        w = 0.5 + 0.5 * math.cos(math.pi * d / 4.5)
        taps.append(w * math.sin(math.pi * d) / (math.pi * d))
    lo, hi = max(0, skip - 4), min(n, upto + 4)
    out = None
    for x in chans:
        seg = list(x[lo:hi])
        m = len(seg) - 7
        mid = [0.0] * max(m, 0)
        for k, t in enumerate(taps):
            mid = list(map(operator.add, mid,
                           map(operator.mul, seg[k:k + m], repeat(t))))
        # mid[i] sits between seg[i + 3] and seg[i + 4]
        pk = []
        for a in range(skip, upto, blk):
            b = min(upto, a + blk)
            s1 = seg[a - lo:b - lo]
            s2 = mid[max(0, a - lo - 3):max(0, b - lo - 3)]
            v = max(max(s1), -min(s1))
            if s2:
                v = max(v, max(s2), -min(s2))
            pk.append(v)
        out = pk if out is None else list(map(max, out, pk))
    return out or []


# a 16-tap Hann-windowed sinc, sampled at quarter steps: what the signal
# does between two samples, the way a DAC (or a meter's 4x
# oversampling) hears it
def _taps(frac):
    t = []
    for k in range(-7, 9):
        d = k - frac
        w = 0.5 + 0.5 * math.cos(math.pi * d / 8.5)
        t.append(w * (math.sin(math.pi * d) / (math.pi * d) if d else 1.0))
    return t


_FRACS = [(f, _taps(f)) for f in (0.25, 0.5, 0.75)]


def _true_peak_near(x, i):
    """The largest magnitude within a sample either side of x[i],
    between the samples as well as on them."""
    n = len(x)
    best = abs(x[i])
    for base in (i - 1, i):
        if base - 7 < 0 or base + 8 >= n:
            continue
        for _f, taps in _FRACS:
            v = 0.0
            for k, t in enumerate(taps):
                v += t * x[base - 7 + k]
            if abs(v) > best:
                best = abs(v)
    return best


def _envelope(need, sr, blk):
    """Block gains that never exceed `need` (what each block may have),
    reached smoothly: a running minimum over the look-ahead either side,
    averaged over half that so the gain ramps down instead of stepping,
    then let back up over the release time."""
    n = len(need)
    A = max(2, int(round(_LOOK * sr / blk)))
    A += A % 2
    # sliding minimum of need over [j-A, j+A]
    m = [1.0] * n
    dq = deque()
    for j in range(n + A):
        if j < n:
            while dq and need[dq[-1]] >= need[j]:
                dq.pop()
            dq.append(j)
        c = j - A
        if c >= 0:
            while dq[0] < c - A:
                dq.popleft()
            m[c] = need[dq[0]]
    # box average over [j-A/2, j+A/2]: each term's window covers j, so
    # the mean is still no more than need[j]
    h = A // 2
    pre = [0.0]
    for v in m:
        pre.append(pre[-1] + v)
    s = [(pre[min(n, j + h + 1)] - pre[max(0, j - h)])
         / (min(n, j + h + 1) - max(0, j - h)) for j in range(n)]
    rc = 1 - math.exp(-blk / (sr * _RELEASE))
    g, prev = [1.0] * n, 1.0
    for j in range(n):
        v = s[j]
        if v < prev:
            prev = v
        else:
            prev += (v - prev) * rc
        g[j] = prev
    return g


def plan(chans, sr, energies, target=TARGET, ceiling=CEILING, tps=None):
    """How to bring this song to the target: (gain, block_gains,
    report). gain takes the raw mix to full scale (1.0); block_gains,
    one per blk_of(sr) samples, is the limiter on top of it. tps is
    true_peaks for the song when the caller has already worked it out
    (the renderer does, a stretch per core). report says what happened:
    the loudness the old 0.85-peak scaling gave, the loudness now, the
    true peak now, and the most the limiter took off."""
    blk = blk_of(sr)
    peaks, where = block_peaks(chans, blk)
    # the limiter works from each block's peak between the samples too
    tps = true_peaks(chans, blk) if tps is None else tps
    peaks = [max(p, t) for p, t in zip(peaks, tps)]
    top = max(peaks, default=0.0)
    if top <= 0.0:
        return 1.0, [1.0] * len(peaks), {}
    old = integrated(energies, sr, 0.85 / top)
    raw = integrated(energies, sr, 1.0)
    if raw is None:
        return 0.85 / top, [1.0] * len(peaks), {}
    G = 10 ** ((target - raw) / 20)
    raw = integrated(energies, sr, G)      # the absolute gate, at level
    if raw is not None:
        G *= 10 ** ((target - raw) / 20)
    # aim a little under the ceiling: the check between samples is an
    # estimate, and the MP3 encoder adds its own overs on top
    ceil = 10 ** ((ceiling - _MARGIN) / 20)

    def limited(G, extra):
        need = [min(1.0, ceil * e / (G * p)) if p > 0 else 1.0
                for p, e in zip(peaks, extra)]
        return _envelope(need, sr, blk)

    def loudness(G, g):
        # K-weighting is linear and the gain barely moves inside a
        # 0.7 ms block, so the limited song's energy is each block's
        # energy times its gain squared
        return integrated(energies, sr, G, g)

    extra = [1.0] * len(peaks)        # true-peak tightening per block
    tried = []
    g = limited(G, extra)
    for _ in range(8):
        now = loudness(G, g)
        if now is None or abs(now - target) < 0.05:
            break
        tried.append((math.log10(G), now))
        if len(tried) >= 2 and tried[-1][1] != tried[-2][1]:
            (x0, y0), (x1, y1) = tried[-2], tried[-1]
            G = 10 ** (x1 + (target - y1) * (x1 - x0) / (y1 - y0))
        else:
            G *= 10 ** ((target - now) / 20)
        g = limited(G, extra)

    # between the samples: where a block now comes close to the
    # ceiling, look around its peak, and hold that block lower if the
    # waveform would go over between samples
    for _ in range(3):
        over = False
        for j, (p, gj) in enumerate(zip(peaks, g)):
            if p * G * gj < ceil * 0.8:
                continue
            tp = max(_true_peak_near(x, i)
                     for x, i in zip(chans, where[j])) * G * gj
            if tp > ceil * 0.9999:
                extra[j] *= ceil / tp * 0.999
                over = True
        if not over:
            break
        g = limited(G, extra)
    tp_now = 0.0
    for j, (p, gj) in enumerate(zip(peaks, g)):
        if p * G * gj >= ceil * 0.8:
            tp_now = max(tp_now, max(_true_peak_near(x, i) for x, i
                                     in zip(chans, where[j])) * G * gj)
        else:
            tp_now = max(tp_now, p * G * gj)
    report = {
        'before_lufs': old,
        'lufs': loudness(G, g),
        'true_peak_db': 20 * math.log10(tp_now) if tp_now > 0 else None,
        'limited_db': -20 * math.log10(min(g)) if g and min(g) > 0 else 0.0,
    }
    return G, g, report


def gain_ramp(g, a, b, scale, sr):
    """One gain per sample for samples a..b-1, the block gains joined by
    straight lines and multiplied by `scale`. Each block's line runs
    between the lower of it and each neighbour, so no sample is given
    more than its own block allows."""
    BLK = blk_of(sr)
    n = len(g)
    out = []
    j = a // BLK
    while j * BLK < b:
        here = g[j] if j < n else 1.0
        g0 = min(here, g[j - 1]) if 0 < j <= n else here
        g1 = min(here, g[j + 1]) if j + 1 < n else here
        lo, hi = max(a, j * BLK), min(b, (j + 1) * BLK)
        if g0 == g1:
            out += [g0 * scale] * (hi - lo)
        else:
            step = (g1 - g0) / BLK
            base = j * BLK
            out += [(g0 + step * (k - base)) * scale for k in range(lo, hi)]
        j += 1
    return out
