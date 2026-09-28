#!/usr/bin/env python3
"""chartdemo — the `from demo` door: chart figures from played MIDI.

Slices a bar range out of a demo MIDI track and turns it into notation:

- The player's systematic lay-back is measured per phrase (median offset to
  the grid) and removed before anything snaps — the feel belongs to the
  player, the page gets the intended rhythm.
- The grid is chosen PER BEAT by tuplets.choose (the Arabesque lesson:
  straight sixteenths in one bar, triplets in the next).
- Short played gates are extended to the next onset when the gap is under a
  quarter of a beat, so live articulation does not become rest-peppered
  notation.
- Out-of-range notes fold by octaves into the part's sounding range, and a
  finding names the bar.

The chart is not a transcription: pitch bends, CC data and micro-timing are
deliberately discarded. What survives is the line.
"""
import os
import re

import analyze
import convert
import instruments
import tuplets
from convert import spelling_table, decompose

DIV = 24                # chart divisions per quarter (16th=6, trip-16th=4)
BEATS = 4               # the 4/4 default; meter arrives per call
BAR = DIV * BEATS       # the 4/4 bar, kept for callers with no meter

# subdivisions a horn chart may use; quintuplets and septuplets stay out
ALLOW = {k: v for k, v in tuplets.CANDIDATES.items() if k in (1, 2, 3, 4, 6, 8)}

ACC_NAME = {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp",
            2: "sharp-sharp"}


class Findings:
    def __init__(self):
        self.lines = []

    def add(self, *args, **kw):
        text = ": ".join(str(a) for a in args if a)
        # convert.py callers pass structured detail; keep what a reader
        # needs (the where and the why), drop the machine fields
        extra = [str(kw[k]) for k in ('location', 'why') if kw.get(k)]
        if extra:
            text += " (" + "; ".join(extra) + ")"
        self.lines.append(text)


class Demo:
    """One demo MIDI file, parsed once, tracks addressable by name."""

    def __init__(self, path):
        self.path = path
        mid = analyze.parse_midi(path)
        self.division = mid["division"]
        ex = analyze.extract(mid)
        self.names = ex["names"]
        self.timesigs = ex["timesigs"]      # [(tick, num, den)], often 4/4@0
        by_track = {}
        for n in ex["notes"]:
            by_track.setdefault(n.track, []).append(n)
        # MuseScore exports a grand staff as two tracks with one name
        # ("Piano", "Piano"); by-name resolution could only ever reach
        # the first, and a piano line wants both hands anyway — the
        # Hands physics re-splits them. Merge same-named tracks.
        seen = {}
        for ti in sorted(by_track):
            nm = (self.names.get(ti) or '').strip().lower()
            if nm and nm in seen:
                by_track[seen[nm]].extend(by_track.pop(ti))
                by_track[seen[nm]].sort(key=lambda n: n.on)
            elif nm:
                seen[nm] = ti
        self.tracks = by_track
        self.cc = {}                    # track -> [(tick, CC11 value)]
        for ti, trk in enumerate(mid["tracks"]):
            for ev in trk:
                if ev[1] == "chan" and ev[2] == 0xB0 and ev[4] == 11:
                    self.cc.setdefault(ti, []).append((ev[0], ev[5]))

    def _segments(self):
        """The file's meter map as (start_tick, num, den), deduped, with a
        4/4 floor at tick zero when the file starts silent about it."""
        segs = [(0, 4, 4)]
        for t, n, d in sorted(self.timesigs):
            if t == segs[-1][0]:
                segs[-1] = (t, n, d)
            else:
                segs.append((t, n, d))
        return segs

    def bar_tick(self, bar):
        """Tick where the file's own bar N (1-based) starts, from its time
        signatures. A signature landing mid-bar governs from the next
        computed bar — DAW exports land them on barlines anyway."""
        segs = self._segments()
        starts = [0]
        si = 0
        while len(starts) < bar:
            t0 = starts[-1]
            while si + 1 < len(segs) and segs[si + 1][0] <= t0:
                si += 1
            _, n, d = segs[si]
            starts.append(t0 + self.division * 4 * n // d)
        return starts[bar - 1]

    def bar_of(self, tick):
        """The file's own 1-based bar number holding a tick."""
        bar = 1
        while self.bar_tick(bar + 1) <= tick:
            bar += 1
        return bar

    def mixed_meter(self):
        """True when the file's own map holds more than one meter."""
        return len({(n, d) for _, n, d in self._segments()}) > 1

    def meter_of(self, bar):
        """The (num, den) governing the file's own bar N."""
        t0 = self.bar_tick(bar)
        n, d = 4, 4
        for t, nn, dd in self._segments():
            if t <= t0:
                n, d = nn, dd
        return (n, d)

    def idx(self, name):
        note_tracks = sorted(self.tracks)
        if name is None:
            if len(note_tracks) == 1:
                return note_tracks[0]
            raise SystemExit(
                f"chartc: demo '{os.path.basename(self.path)}' has "
                f"{len(note_tracks)} note tracks — name one")
        want = name.strip().lower()
        hits = [ti for ti in note_tracks
                if self.names.get(ti, "").strip().lower() == want]
        if len(hits) == 1:
            return hits[0]
        have = [self.names.get(ti, f"(track {ti})") for ti in note_tracks]
        raise SystemExit(
            f"chartc: demo track '{name}' "
            f"{'is ambiguous' if hits else 'not found'} in "
            f"{os.path.basename(self.path)} — tracks: {have}")

    def track(self, name):
        return self.tracks[self.idx(name)]

    def cc11(self, name):
        return self.cc.get(self.idx(name), [])


_DEMOS = {}


def load_demo(path):
    # keyed on the file's size and time as well as its name: a writer
    # re-exporting the take while the editing desk is open must get the
    # new one, not the take the desk read an hour ago
    if not os.path.exists(path):
        raise SystemExit(f"chartc: demo file '{path}' not found")
    st = os.stat(path)
    key = (path, st.st_mtime_ns, st.st_size)
    if key not in _DEMOS:
        _DEMOS[key] = Demo(path)
    return _DEMOS[key]


def find_trills(notes, beat):
    """Played ornaments in raw notes [(on, off, pitch, vel)], sorted by
    onset, each collapsed to one written note:

      trill    a fast strict back-and-forth a half step to a major third
               apart (a fourth or wider is a fingered tremolo instead,
               the way the orchestral books write it)
      ftrem    that back-and-forth a fourth to an octave apart
      trem     one pitch re-struck fast — a bowed tremolo, a mallet
               roll, a piano's repeated note

    Faster than sixteenths, four alternations (six re-strikes) are an
    ornament; at sixteenth speed an alternation takes eight and a
    re-strike never counts, so measured sixteenths stay notes. Other
    pitches (the other hand, a held chord) are looked past. Returns
    (kept notes, [(on, off, main, aux, vel, count, kind)]); main is the
    lower pitch, aux the upper (equal for a tremolo)."""
    six = beat / 4
    gap = beat * 0.3
    used, found = set(), []
    for i, (on0, _off0, a, _v) in enumerate(notes):
        if i in used:
            continue
        best = None
        for same in (False, True):
            chain, other, last = [i], (a if same else None), on0
            k = i + 1
            while k < len(notes):
                on, _off, p, _v2 = notes[k]
                if on - last > gap:
                    break
                if k in used or on <= last:
                    k += 1
                    continue
                if other is None and 1 <= abs(p - a) <= 12:
                    other = p
                expect = other if len(chain) % 2 else a
                if p == expect and other is not None:
                    chain.append(k)
                    last = on
                k += 1
            if len(chain) < 4:
                continue
            ons = [notes[c][0] for c in chain]
            mean = (ons[-1] - ons[0]) / (len(ons) - 1)
            if same:
                ok = mean < six * 0.8 and len(chain) >= 6
            else:
                ok = (mean < six * 0.9) or (mean <= six * 1.1
                                            and len(chain) >= 8)
            if ok and (best is None or len(chain) > len(best[0])):
                best = (chain, other, same)
        if best is None:
            continue
        chain, other, same = best
        used.update(chain)
        span = abs(other - a)
        kind = 'trem' if same else ('trill' if span <= 4 else 'ftrem')
        found.append((notes[chain[0]][0],
                      max(notes[c][1] for c in chain),
                      min(a, other), max(a, other),
                      max(notes[c][3] for c in chain), len(chain), kind))
    kept = [n for i, n in enumerate(notes) if i not in used]
    kept += [(on, off, main, vel) for on, off, main, _aux, vel, _n, _k
             in found]
    return sorted(kept), found


# ------------------------------------------------------------ keyswitches

# what a keyswitch's name means on the page. The name is the writer's
# (or the library's) word; anything not listed prints as the words
# themselves at the change, so nothing a library calls it is lost.
KS_MARK = {  # per-note articulation tags
    'staccato': 'staccato', 'stacc': 'staccato', 'short': 'staccato',
    'shorts': 'staccato', 'spiccato': 'spiccato',
    'staccatissimo': 'staccatissimo', 'marcato': 'strong-accent',
    'marcatos': 'strong-accent', 'accent': 'accent', 'accented': 'accent',
    'sfz': 'accent', 'sforzando': 'accent', 'tenuto': 'tenuto',
    'portato': 'detached-legato', 'loure': 'detached-legato',
    'detache': 'tenuto', 'detached': 'tenuto',
}
KS_TEXT = {  # techniques printed in words at the change
    'pizz': 'pizz.', 'pizzicato': 'pizz.', 'arco': 'arco',
    'con sord': 'con sord.', 'con sordino': 'con sord.',
    'sordino': 'con sord.', 'sord': 'con sord.',
    'mute': 'mute', 'muted': 'mute', 'senza sord': 'senza sord.',
    'open': 'open', 'harmon': 'harmon mute', 'harmon mute': 'harmon mute',
    'cup': 'cup mute', 'cup mute': 'cup mute', 'straight': 'straight mute',
    'straight mute': 'straight mute', 'plunger': 'plunger',
    'flutter': 'flz.', 'flutter tongue': 'flz.', 'flz': 'flz.',
    'sul pont': 'sul pont.', 'sul ponticello': 'sul pont.',
    'sul tasto': 'sul tasto', 'col legno': 'col legno',
    'harmonics': 'harm.', 'harmonic': 'harm.', 'growl': 'growl',
    'shake': 'shake', 'ord': 'ord.', 'ordinario': 'ord.', 'normale': 'ord.',
    'fortepiano': 'fp', 'crescendo': 'cresc.', 'glissando': 'gliss.',
    'gliss': 'gliss.', 'dead note': 'dead notes', 'dead notes': 'dead notes',
    'slap': 'slap', 'pop': 'pop', 'x note': 'dead notes',
    'flageolet': 'harm.', 'gliss key': 'gliss.', 'palm mute': 'P.M.',
}
KS_PLAIN = {'long', 'longs', 'sustain', 'sus', 'sustained', 'normal',
            'legato', 'slur', 'slurred', 'default'}
# a patch's playing modes that no copyist prints: how the sampler picks
# its takes, not what the player reads (Logic's own sets, surveyed)
KS_INTERNAL = re.compile(
    r'\b(expressive (long|medium)|standard|passionate|all auto|auto|'
    r'index|middle|down only|up only|down up|pickup|by velocity|'
    r'open slide|round robin|rr|select string|force string|chord mode|'
    r'playing position|position|repetition|shift|open strings|'
    r'strum|stroke|mode off|octave runs)\b', re.I)


def ks_meaning(word):
    """A keyswitch name -> (mark tag, printed words, legato?, ornament).
    Library names come dressed ('Violins - Spiccato', 'SHORTS marcato
    2'): the known words inside are found; the rest is the writer's."""
    w = re.sub(r'[^a-z ]', ' ', word.lower())
    w = re.sub(r'\s+', ' ', w).strip()
    if KS_INTERNAL.search(w) and not re.search(
            r'stac|spic|marc|pizz|trem|trill|fall|doit|legato|mute|'
            r'harm|slap|pop', w):
        return None, None, False, None
    mark = next((KS_MARK[k] for k in sorted(KS_MARK, key=len, reverse=True)
                 if re.search(r'\b%s\b' % k, w)), None)
    text = next((KS_TEXT[k] for k in sorted(KS_TEXT, key=len, reverse=True)
                 if re.search(r'\b%s\b' % k, w)), None)
    legato = bool(re.search(r'\b(legato|slur|slurred)\b', w))
    orn = ('trem' if re.search(r'\btrem', w) else
           'trill_half' if re.search(r'\btrill (semi|half)', w) else
           'trill_whole' if re.search(r'\btrill whole', w) else
           'trill' if re.search(r'\btrill', w) and 'shake' not in w
           else 'falloff' if re.search(r'\bfall', w) else
           'doit' if re.search(r'\bdoit', w) else
           'scoop' if re.search(r'\bscoop|\bslide in|\bslide up', w)
           else None)
    if orn in ('falloff', 'doit', 'scoop'):
        mark = None                   # "Fall Short" is a fall, not a dot
    if not (mark or text or legato or orn) and not any(
            re.search(r'\b%s\b' % k, w) for k in KS_PLAIN):
        text = word.strip().lower()   # the library's own word, printed
    return mark, text, legato, orn


def midi_name(p):
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#',
             'B']
    return f"{names[p % 12]}{p // 12 - 1}"


def ks_word_for(word, vel):
    '''A map line may split by how hard the key was pressed, as Kontakt
    guitars do: "low velo: mute | high velo: x-note" (the split is at
    100, the libraries' default). The press's own velocity picks.'''
    if not word or 'velo' not in word.lower():
        return word
    m = re.match(r'\s*low velo[^:]*:\s*(.*?)\s*\|\s*high velo[^:]*:\s*(.*)$',
                 word, re.I)
    if not m:
        return word
    return m.group(1) if vel <= 100 else m.group(2)


def find_keyswitches(notes, sounding_range, beat, mapped=frozenset()):
    """Keyswitches in played notes [(on, off, pitch, vel)]: keys well
    outside the instrument's playable range (an octave past its ends,
    or below A0 / above C8 when the range is unknown) that never sound
    in the part. Returns (musical notes, switches [(on, off, pitch)])."""
    lo, hi = sounding_range if sounding_range else (33, 96)
    floor, ceil = (lo - 12, hi + 12) if sounding_range else (21, 108)
    ks, kept = [], []
    for n in notes:
        # a key the part's map names counts once it is past the
        # playable range at all (many libraries sit their switches just
        # below the lowest note); an unnamed key must be an octave out,
        # so a low note really played is never taken for a switch
        out = n[2] < floor or n[2] > ceil or (
            n[2] in mapped and sounding_range and (n[2] < lo or n[2] > hi))
        (ks if out else kept).append(n)
    ks = [(on, off, p, v) for on, off, p, v in ks]
    return kept, sorted(ks)


def assign_keyswitches(notes, switches, beat):
    """Which switch governs each musical note, by its raw onset. A
    switch latches until the next one; a switch HELD across notes for
    more than a beat governs only while held, then the latched one
    returns. A switch pressed a hair after the note it meant (a 32nd)
    still counts for it."""
    slack = beat / 8
    latched_order = [s for s in switches if s[1] - s[0] <= beat * 0.9]
    held = [s for s in switches if s[1] - s[0] > beat * 0.9]
    out = {}
    for on, _off, _p, _v in notes:
        cur = None
        for s_on, s_off, sp, sv in held:
            if s_on - slack <= on < s_off:
                cur = (sp, sv)
        if cur is None:
            for s_on, _s_off, sp, sv in latched_order:
                if s_on - slack <= on:
                    cur = (sp, sv)
                else:
                    break
        if cur is not None:
            out[on] = cur
    return out


# the word that ends a technique when the playing returns to normal
KS_RELEASE = {'pizz.': 'arco', 'con sord.': 'senza sord.', 'mute': 'open',
              'harmon mute': 'open', 'cup mute': 'open',
              'straight mute': 'open', 'plunger': 'open',
              'sul pont.': 'ord.', 'sul tasto': 'ord.', 'col legno': 'ord.',
              'harm.': 'ord.', 'flz.': 'ord.'}


def ks_plan(res, timeline, fifths_concert):
    """res['ks'] -> what the page does with it: {start: mark tag},
    {start: words printed there}, legato slur runs over timeline
    indices, and trill/tremolo entries merged into res. Words print
    only where the technique changes, the way a part is marked."""
    ks = res.get('ks') or {}
    marks, texts, legato_idx = {}, {}, []
    state = None
    for ti, (st, _e, ps) in enumerate(timeline):
        word = next((ks[(st, p)] for p in ps if (st, p) in ks), None)
        if word is None:
            continue
        mark, text, legato, orn = ks_meaning(word)
        if mark:
            marks[st] = mark
        if text != state:
            if text:
                texts[st] = text
            elif state in KS_RELEASE:
                texts[st] = KS_RELEASE[state]
            state = text
        if legato:
            legato_idx.append(ti)
        if orn == 'trem':
            res.setdefault('trems', {})[(st, ps[0])] = 3
        elif orn in ('trill', 'trill_half', 'trill_whole'):
            spec = {'trill': ('key',), 'trill_half': ('second', 1),
                    'trill_whole': ('second', 2)}[orn]
            aux, form = trill_target(ps[-1], spec, fifths_concert)
            res.setdefault('trills', {})[(st, ps[-1])] = (aux, form)
        elif orn in ('falloff', 'doit', 'scoop'):
            marks[st] = orn
    runs, run = [], []
    for ti in legato_idx:
        if run and ti == run[-1] + 1 and timeline[run[-1]][1] == \
                timeline[ti][0]:
            run.append(ti)
        else:
            if len(run) > 1:
                runs.append((run[0], run[-1]))
            run = [ti]
    if len(run) > 1:
        runs.append((run[0], run[-1]))
    return marks, texts, runs


def words_direction(text):
    return ('      <direction placement="above"><direction-type>'
            f'<words font-style="italic">{text}</words>'
            '</direction-type></direction>\n')


INTERVAL_WORD = {1: 'a half step', 2: 'a whole step',
                 3: 'a minor third', 4: 'a major third',
                 5: 'a fourth', 6: 'a tritone', 7: 'a fifth'}


def _mono_tl(events, n_units):
    """One voice's cleanup: truncate at the voice's next onset, close
    slivers of daylight, cap at the figure's end."""
    onsets = sorted(events)
    close = DIV // 4
    timeline = []                          # (start, end, [pitches])
    for i, q_on in enumerate(onsets):
        end = max(e for _, e, *_ in events[q_on])
        nxt = onsets[i + 1] if i + 1 < len(onsets) else None
        if nxt is not None:
            if end > nxt:
                end = nxt                  # one voice, one line
            elif 0 < nxt - end <= close:
                end = nxt                  # close a sliver of daylight
        end = max(end, q_on + 1)
        end = min(end, n_units)
        pitches = sorted({p for p, *_ in events[q_on]})
        timeline.append((q_on, end, pitches))
    return timeline


def _slur_runs(tl, raw):
    """Maximal legato runs in one voice — each note held into the next
    (gate past 90% of its slot, DESIGN.md 7.3) — as (first, last) index
    pairs. A repeated single pitch breaks the run: legato onto the same
    note reads as a tie, which is not what was played. Runs follow the
    PLAYING: where the writer breathed, the slur breaks."""
    def legato(a, b):
        if a[1] != b[0]:                   # a rest breaks any phrase
            return False
        ra, rb = raw.get(a[0]), raw.get(b[0])
        if not ra or not rb:
            return False
        slot = rb[0] - ra[0]
        return slot > 0 and (ra[1] - ra[0]) / slot > 0.90
    runs, i = [], 0
    while i < len(tl):
        j = i
        while (j + 1 < len(tl) and legato(tl[j], tl[j + 1])
               and not (len(tl[j][2]) == 1
                        and tl[j][2] == tl[j + 1][2])):
            j += 1
        if j > i:
            runs.append((i, j))
        i = j + 1
    return runs


def _beat_end(s, cap, bar_ticks):
    """Where a drum hit at `s` may ring to on the page: the end of its
    beat. An offbeat hit never crosses into the next beat (the and of 2
    is an eighth and a rest, not a quarter over beat 3) - how drum
    books keep the beat visible."""
    b0 = s - s % bar_ticks
    return min(b0 + ((s - b0) // cap + 1) * cap, b0 + bar_ticks)


def _ghosts(tl, raw):
    """Indices of notes played well under their neighbours — ghost
    notes, printed in parentheses. Same relative-velocity judgment as
    the accent pass, mirrored."""
    import articulation
    vels = [raw.get(s, (0, 0, 64))[2] for s, _, _ in tl]
    out = set()
    for i in range(len(tl)):
        mean, sd = articulation.local_stats(vels, i)
        if sd and sd > 1e-6 and (vels[i] - mean) / sd <= articulation.GHOST_Z:
            out.add(i)
    return out


def _simplify(tl, raw, n_units):
    """DESIGN.md 11 'simplified': the phrase survives, the ornament
    noise goes. A note shorter than a sixteenth is absorbed, onsets
    land on the eighth grid, ends re-truncate at the next onset.
    Returns (timeline, raw, ornaments_dropped)."""
    E = DIV // 2
    dropped, kept = 0, []
    for s, e, ps in tl:
        if e - s < DIV // 4:
            dropped += 1
            continue
        vel = raw.get(s, (s, e, 84))[2]
        kept.append([s, e, ps, vel])
    out = []
    for s, e, ps, vel in kept:
        ns = int(round(s / E)) * E
        ne = max(int(round(e / E)) * E, ns + E)
        if out and out[-1][0] == ns:
            out[-1][2] = sorted(set(out[-1][2] + ps))
            out[-1][1] = max(out[-1][1], ne)
            continue
        out.append([ns, min(ne, n_units), ps, vel])
    for i in range(len(out) - 1):
        out[i][1] = min(out[i][1], out[i + 1][0])
    tl2 = [(s, e, ps) for s, e, ps, _ in out if e > s]
    raw2 = {s: (s, e, v) for (s, e, ps, v), t in zip(out, tl2)}
    return tl2, raw2, dropped


def _pedals(evts, n_units):
    """Pull pedal tones out of one staff's events: a note that keeps
    ringing under (or over) later movement becomes its own voice instead
    of being cut at the next onset. Mutates evts; returns the pedal
    timeline. The pedal layer never overlaps itself — of a run of
    let-ring notes, the first keeps ringing and the rest stay in the
    line, which is a chart's honest reading of a wash of sustain."""
    onsets = sorted(evts)
    pedals = []                            # [start, end, [pitches]]
    for q_on in onsets:
        for item in list(evts.get(q_on, ())):
            p, off = item[0], item[1]
            off = min(off, n_units)
            crossed = [o for o in onsets
                       if q_on < o <= off - DIV // 2]
            if not crossed:
                continue
            others = [pp for o in crossed for (pp, *_) in evts[o]]
            if not others or not (all(pp > p for pp in others)
                                  or all(pp < p for pp in others)):
                continue
            clash = [pe for pe in pedals
                     if not (off <= pe[0] or q_on >= pe[1])]
            if clash:
                pe = clash[-1]
                if len(clash) == 1 and pe[0] == q_on and pe[1] == off:
                    pe[2].append(p)        # a held chord rings as one
                else:
                    continue
            else:
                pedals.append([q_on, off, [p]])
            evts[q_on].remove(item)
            if not evts[q_on]:
                del evts[q_on]
    return [(s, e, sorted(ps)) for s, e, ps in pedals]


DIGRAPHS = {'ch', 'sh', 'th', 'ph', 'wh', 'gh', 'ck', 'qu'}


def syllabify(word):
    """Split an unhyphenated word for singing — a heuristic, so the
    writer's own hyphens always win and every auto-split is reported.
    The syllable COUNT is what alignment lives on; the split point only
    has to be singable."""
    letters = [(i, c.lower()) for i, c in enumerate(word) if c.isalpha()]
    if not letters:
        return [word]
    lows = ''.join(c for _, c in letters)
    groups = [m.span() for m in re.finditer(r'[aeiouy]+', lows)]
    if len(groups) > 1 and lows.endswith('e') \
            and groups[-1] == (len(lows) - 1, len(lows)) \
            and not lows.endswith('le'):
        groups = groups[:-1]           # a final silent e does not sing
    if len(groups) <= 1:
        return [word]
    cuts = []
    for (_, a_e), (b_s, _) in zip(groups, groups[1:]):
        if a_e >= b_s:                 # adjacent vowels: split between
            cut = b_s
        else:
            cut = b_s - 1              # one consonant starts the syllable
            if cut - 1 >= a_e and lows[cut - 1:cut + 1] in DIGRAPHS:
                cut -= 1
            cut = max(cut, a_e)
        cuts.append(letters[cut][0])
    out, prev = [], 0
    for c in cuts:
        out.append(word[prev:c])
        prev = c
    out.append(word[prev:])
    return [s for s in out if s]


def parse_lyrics(text):
    """CHART-FORMAT.md 3.4: write the words the way you'd say them.
    Hyphens split syllables (and always win); an unhyphenated word is
    split by syllabify() and reported; underscores hold a melisma;
    slashes group words into phrases that anchor to the melody's own.
    Returns (phrases, autos): phrases as lists of aligned tokens, autos
    as the words split automatically."""
    phrases, autos = [], []
    for group in text.split('/'):
        toks = []
        for word in group.split():
            tail = 0
            while word.endswith('_'):
                word = word[:-1]
                tail += 1
            if word:
                if '-' in word:
                    real = [s for s in word.split('-') if s]
                else:
                    real = syllabify(word)
                    if len(real) > 1:
                        autos.append('-'.join(real))
                for i, s in enumerate(real):
                    syllabic = ('single' if len(real) == 1 else
                                'begin' if i == 0 else
                                'end' if i == len(real) - 1 else 'middle')
                    toks.append([syllabic, s, False])
            for _ in range(tail):
                toks.append(None)
        if toks:
            phrases.append(toks)
    return phrases, autos


def attach_lyrics(res, text, part_label, loc, find=None):
    """Align the writer's words to the resolved notes — by phrase when
    the words carry slashes, one syllable per note either way, or refuse
    NAMING THE PHRASE AND THE BAR. Words silently misaligned to notes
    are the one failure a singer cannot proofread past."""
    if not text:
        return
    if res.get('staves'):
        raise SystemExit(
            f"chartc: {loc}: lyrics need one singing line — this figure "
            "came out polyphonic")
    phrases, autos = parse_lyrics(text)
    if autos and find is not None:
        find.add(f"{part_label}: I split these words myself — "
                 + ", ".join(autos) + " — hyphenate any I got wrong")
    tl = res['timeline']
    bt = res.get('bar_ticks', BAR)
    base = res['at'] + res.get('spoken_shift', 0)

    # the melody's own phrases: runs broken wherever a rest prints
    mel, run = [], [0]
    for i in range(1, len(tl)):
        if tl[i][0] > tl[i - 1][1]:
            mel.append(run)
            run = []
        run.append(i)
    mel.append(run)

    def bar_of(i):
        return base + tl[i][0] // bt

    if len(phrases) > 1:
        if len(phrases) != len(mel):
            shape = "; ".join(
                f"bar {bar_of(r[0])}: {len(r)} note(s)" for r in mel)
            raise SystemExit(
                f"chartc: {loc}: '{part_label}' sings "
                f"{len(mel)} phrase(s) but the words give "
                f"{len(phrases)} — the melody's phrases are: {shape}")
        def rejoin(ph):
            out, word = [], []
            for t in ph:
                if t is None:
                    if word:
                        out.append("-".join(word))
                        word = []
                    out.append("_")
                    continue
                word.append(t[1])
                if t[0] in ('single', 'end'):
                    out.append("-".join(word))
                    word = []
            if word:
                out.append("-".join(word))
            return " ".join(out)
        bad = []
        for r, ph in zip(mel, phrases):
            if len(ph) != len(r):
                bad.append(f"the phrase at bar {bar_of(r[0])} has "
                           f"{len(r)} note(s) but '{rejoin(ph)}' gives "
                           f"{len(ph)} syllable(s)")
        if bad:
            raise SystemExit(
                f"chartc: {loc}: '{part_label}': " + "; ".join(bad[:3])
                + " — an underscore holds a syllable one more note")
        toks = [t for ph in phrases for t in ph]
    else:
        toks = phrases[0] if phrases else []
        if len(toks) != len(tl):
            shape = ", ".join(str(len(r)) for r in mel)
            raise SystemExit(
                f"chartc: {loc}: '{part_label}' sings {len(tl)} note(s) "
                f"here but the lyrics carry {len(toks)} syllable(s) — "
                f"the melody phrases hold {shape}; slashes in the words "
                "anchor them phrase by phrase")
    for i, t in enumerate(toks):
        if t is None and i and toks[i - 1] is not None:
            toks[i - 1][2] = True        # the syllable keeps sounding
    res['lyrics'] = toks
    res['lyrics_text'] = text


def trill_target(midi, spec, fifths):
    """A written trill spec on a concert note -> the concert target.
    ('key',): the next letter up with the key's accidental on it — E in
    C trills to F (a half step), D to E (a whole step)."""
    kind = spec[0]
    if kind == 'ftrem':
        return (spec[1], 'trem')
    if kind == 'to':
        return (spec[1], spec[2])          # the writer's own letter
    if kind == 'second' or (kind == 'up' and spec[1] <= 2):
        return (midi + spec[1], 'second')
    if kind == 'up':
        return (midi + spec[1], 'auto')
    step, _alter, octave = convert.spell(midi,
                                         spelling_table(fifths, Findings()))
    letters = 'CDEFGAB'
    nat = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
    i = letters.index(step)
    up = letters[(i + 1) % 7]
    oct_up = octave + (1 if up == 'C' else 0)
    sharps, flats = 'FCGDAEB', 'BEADGCF'
    kalt = (1 if fifths > 0 and up in sharps[:fifths] else
            -1 if fifths < 0 and up in flats[:-fifths] else 0)
    return (nat[up] + kalt + (oct_up + 1) * 12, 'second')


def inline_res(ref, meter, spoken_shift, fifths=0):
    """A hand-written figure (CHART-FORMAT.md 3.4 notes:), shaped exactly
    like a resolved demo range so the page, the prose and the player need
    nothing new. Notes are concert pitch, like everything spoken."""
    m_num, m_den = meter
    bar_ticks = DIV * 4 * m_num // m_den
    pulse_div = DIV * 4 // m_den
    bars = ref['hi']
    n_units = bars * bar_ticks
    if ref['ticks'] != n_units:
        raise SystemExit(
            f"chartc: {ref['loc']}: the figure's notes fill "
            f"{ref['ticks'] / DIV:g} beats but {bars} bar(s) of "
            f"{m_num}/{m_den} hold {n_units / DIV:g}")
    timeline, pos, trills, trems = [], 0, {}, {}
    for item in ref['inline']:
        ticks, midi = item[0], item[1]
        if midi is not None:
            timeline.append((pos, pos + ticks, [midi]))
            if len(item) > 2 and item[2][0] == 'trem':
                trems[(pos, midi)] = 3
            elif len(item) > 2:
                trills[(pos, midi)] = trill_target(midi, item[2], fifths)
        pos += ticks
    if ref.get('short') and timeline:
        s, e, ps = timeline[-1]
        timeline[-1] = (s, min(e, s + DIV // 2), ps)
    grids = {b: 4 for b in range(n_units // DIV + 1)}
    grids.update(ref.get('grids') or {})
    raw = {s: (s, e, 90) for s, e, _ in timeline}
    return ({'timeline': timeline, 'grids': grids, 'n_units': n_units,
             'at': ref['at'], 'bars': (1, bars), 'dyns': [],
             'slurs': [], 'ghosts': set(), 'staves': None,
             'spoken_shift': spoken_shift, 'trills': trills,
             'trems': trems,
             'bar_ticks': bar_ticks, 'pulse_div': pulse_div}, raw)


def resolve_range(demo, track_name, bar_lo, bar_hi, at_bar, *,
                  octave_shift=0, sounding_range=None, quant=None,
                  derive_dyns=True, short=False, spoken_shift=0,
                  poly=False, grand=False, reach=17, comfortable=14,
                  legato=False, ghost=False, detail=None, meter=(4, 4),
                  window=None, part_label="", findings=None, drums=False,
                  trills=True, ks_map=None, drum_map=None):
    """
    Resolve demo bars [bar_lo, bar_hi] (the file's own 1-based numbering)
    into a quantized timeline of sounding pitches starting at absolute
    chart bar `at_bar`. Shared by the page (render_range) and the prose
    (say_range), so the two cannot disagree.

    `spoken_shift` is the count-in: everything SPOKEN (findings, the
    read-aloud) adds it, so the writer hears their own DAW bar numbers.
    The printed page keeps printed numbers — players count from one.
    """
    find = findings if findings is not None else Findings()
    src = demo.track(track_name)
    beat = demo.division
    m_num, m_den = meter
    tick_bar = beat * 4 * m_num // m_den
    bar_ticks = DIV * 4 * m_num // m_den
    pulse_div = DIV * 4 // m_den
    if window is not None:
        # the caller located the bars against a meter map (the demo's own
        # time signatures, or the chart's) — single-meter arithmetic below
        # would miss every bar after a change
        lo_t, hi_t = window
    else:
        lo_t = (bar_lo - 1) * tick_bar
        hi_t = bar_hi * tick_bar
    # A hair of pre-roll for an attack played a touch early — no more: a
    # generous slack swallows the previous figure's last note and makes a
    # phantom collision at beat 1 (the trombone climb taught this).
    slack = beat // 8
    picked = [(n.on, n.off or n.on, n.pitch, n.vel) for n in src
              if lo_t - slack <= n.on < hi_t]
    named_art = {}
    if drums and drum_map:
        # another maker's kit layout, read as the GM piece it plays;
        # a stroke the drummer NAMED (ghost, flam, rimshot, choke,
        # drag) stays that stroke, whatever the velocity says
        dart = getattr(drum_map, 'artic', None) or {}
        named_art = {(on, drum_map.get(p, p)): dart[p] for on, _f, p, _v
                     in picked if dart.get(p)}
        picked = [(on, off, drum_map.get(p, p), v)
                  for on, off, p, v in picked]
    elif drums:
        odd = sorted({p for _o, _f, p, _v in picked}
                     & instruments.NOT_GM_DRUMS)
        if odd:
            find.add(f"{part_label}: drum note(s) "
                     + ", ".join(str(p) for p in odd)
                     + " aren't General MIDI drums: played on EZdrummer "
                     "or Superior Drummer, add drummap \"Toontrack\"; on "
                     "Addictive Drums 2, drummap \"Addictive Drums 2\"; "
                     "on any other kit, Name the drum notes (chart TUNE "
                     "drums) names them once")
    if not picked:
        raise SystemExit(
            f"chartc: {part_label}: demo bars {bar_lo}-{bar_hi} of "
            f"'{track_name or os.path.basename(demo.path)}' hold no notes")

    # ---- take the lay-back out. The offset is measured against the grid
    # the writer named — measuring triplet positions against the sixteenth
    # grid manufactures a phantom lag that pushes the notes exactly
    # between the tuplet grids (the bari climb taught this).
    gmod = {'quarters': beat, 'eighths': beat / 2, 'triplets': beat / 6,
            'triplet8': beat / 3, 'triplet16': beat / 6, 'grid8': beat / 2,
            'sixteenths': beat / 4}.get(quant, beat / 4)
    half = gmod / 2
    offs = sorted((on % gmod) if (on % gmod) < half
                  else (on % gmod) - gmod for on, _, _, _ in picked)
    lag = offs[len(offs) // 2]
    if abs(lag) > beat * 0.04:
        ms = abs(lag) * 60000 / (87 * beat)
        find.add(f"{part_label}: bars {bar_lo}-{bar_hi} played "
                 f"{'behind' if lag > 0 else 'ahead of'} the beat by about "
                 f"{ms:.0f} ms — that is the feel; the page keeps the "
                 "intended rhythm")
    else:
        lag = 0
    moved = [(on - lag - lo_t, off - lag - lo_t, p, v)
             for on, off, p, v in picked]
    named_art = {(max(0, on - lag - lo_t), g): a
                 for (on, g), a in named_art.items()}

    # ---- keyswitches: keys pressed to change the patch's articulation
    # are not music. They leave the notes here (a C0 must never print
    # as a note folded up four octaves) and say what they meant.
    ks_by_on, ks_unmapped = {}, {}
    if not drums:
        shifted_rng = None
        if sounding_range:
            shifted_rng = (sounding_range[0] - 12 * octave_shift,
                           sounding_range[1] - 12 * octave_shift)
        moved, switches = find_keyswitches(moved, shifted_rng, beat,
                                           set(ks_map or ()))
        if switches:
            gov = assign_keyswitches(moved, switches, beat)
            for on, (sp, sv) in gov.items():
                word = ks_word_for((ks_map or {}).get(sp), sv)
                if word is None:
                    ks_unmapped.setdefault(sp, []).append(on)
                ks_by_on[on] = word
            used = sorted({sp for _o, _f, sp, _v in switches})
            named = [f"{midi_name(sp)} (MIDI {sp}) is "
                     f"{(ks_map or {})[sp]}" for sp in used
                     if sp in (ks_map or {})]
            find.add(f"{part_label}: {len(switches)} keyswitch press(es) "
                     f"on {len(used)} key(s) taken out of the notes"
                     + ("; " + "; ".join(named) if named else ""))
            for sp, ons in sorted(ks_unmapped.items()):
                bars_ = sorted({bar_lo + spoken_shift
                                + int(max(o, 0) // tick_bar) for o in ons})
                find.add(f"{part_label}: keyswitch {midi_name(sp)} (MIDI "
                         f"{sp}) governs bars "
                         + ", ".join(str(b) for b in bars_[:8])
                         + (" and more" if len(bars_) > 8 else "")
                         + " but has no name yet; name it in a "
                         "keyswitches block and the page marks it")

    # ---- a played trill is one note with a trill on it, not a pile of
    # thirty-seconds: collapse it before the grid is chosen, and keep
    # the exact upper note the fingers went to
    trill_on = {}
    if trills and not drums and detail != 'rhythmic-slashes':
        moved, found = find_trills(sorted(moved), beat)
        for on, _off, main, aux, _v, count, kind in found:
            trill_on[on] = (main, aux, kind)
            fb = bar_lo + int(max(on, 0) // tick_bar) + spoken_shift
            gap_w = INTERVAL_WORD.get(aux - main,
                                      f"{aux - main} semitones")
            find.add(f"{part_label}: bar {fb}: " + (
                f"a played tremolo, one note struck {count} times — "
                "written as one note with tremolo strokes"
                if kind == 'trem' else
                f"a played trill, {count} notes {gap_w} apart — "
                "written as one note with a trill"
                if kind == 'trill' else
                f"a played tremolo between two notes {gap_w} apart — "
                "written as a fingered tremolo"))

    # ---- per-beat grid, then snap. A `quant` hint from the writer beats
    # any statistics: "eighths" means these bars are eighth notes, full stop.
    allow = ALLOW
    if quant == 'quarters':
        allow = {k: v for k, v in tuplets.CANDIDATES.items() if k in (1,)}
    elif quant in ('eighths', 'grid8'):
        # grid8 is `straight`: onsets land on the eighth grid, but the
        # durations stay as played — a shuffle notated straight, not a
        # line OF eighth notes
        allow = {k: v for k, v in tuplets.CANDIDATES.items() if k in (1, 2)}
    elif quant == 'triplets':
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 2, 3, 6)}
    elif quant == 'triplet8':
        # the writer said eighth-note triplets: no binary escape hatch
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 3)}
    elif quant == 'triplet16':
        # sixteenth-note triplets: the whole swung-sextuplet family
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 3, 6)}
    elif quant == 'sixteenths':
        allow = {k: v for k, v in tuplets.CANDIDATES.items()
                 if k in (1, 2, 4)}
    grids = tuplets.choose(sorted(max(0, on) for on, _, _, _ in moved),
                           beat, allow)
    tupl = tuplets.summarize({b: s for b, s in grids.items()
                              if tuplets.CANDIDATES[s][2] !=
                              tuplets.CANDIDATES[s][3]})
    if tupl:
        find.add(f"{part_label}: bars {bar_lo}-{bar_hi} use tuplet beats "
                 f"({tupl})")

    n_units = (bar_hi - bar_lo + 1) * bar_ticks
    scale = DIV / beat                     # demo ticks -> chart ticks
    default_sub = {'quarters': 1, 'eighths': 2, 'grid8': 2, 'triplet8': 3,
                   'triplet16': 6}.get(quant, 4)

    ks_notes = {}        # (chart onset, sounding pitch) -> keyswitch word
    trill_map = {}       # (chart onset, sounding pitch) -> trill target
    trem_map = {}        # (chart onset, sounding pitch) -> strokes
    events = {}          # chart-tick onset -> [(pitch, q_off, raw_on,
                         #                        raw_off, velocity)]
    for on, off, p, v in moved:
        ks_word = ks_by_on.get(on)
        trill_here = trill_on.get(on)
        if trill_here and trill_here[0] != p:
            trill_here = None              # a chord tone sharing the onset
        on = max(0, on)
        b = int(on // beat)
        sub = grids.get(b, default_sub)
        step = beat / sub
        q_on = int(round((b * beat + round((on % beat) / step) * step)
                         * scale))
        if q_on >= n_units:
            continue

        # The ending snaps to the grid of the beat it falls in, so a
        # duration inside a tuplet beat is always whole subdivisions —
        # EXCEPT that a sustained note's release is a cutoff the section
        # counts together: two-thirds of a beat or longer, ending in a
        # binary beat, releases on the eighth grid.
        x = off * scale
        ob = int(x // DIV)
        osub = grids.get(ob)               # None: no onsets in that beat
        if x - q_on >= 16 and (osub is None or osub in (1, 2, 4, 8)):
            # a sustained release in a beat nobody attacks in is a
            # cutoff, and cutoffs land on the eighth grid
            q_off = int(round(x / (DIV // 2))) * (DIV // 2)
        else:
            ostep = DIV / (osub or default_sub)
            q_off = int(round(ob * DIV + round((x - ob * DIV) / ostep)
                              * ostep))
        onstep = int(DIV / sub)
        q_off = max(q_on + onstep, min(q_off, n_units))
        if quant == 'eighths' and (off - on) < beat:
            # the writer said eighths: only a genuinely held gate may be
            # longer than one
            q_off = min(q_off, q_on + DIV // 2)
        p = p + 12 * octave_shift
        if sounding_range and not drums:    # a kit piece is not a pitch
            lo_r, hi_r = sounding_range
            folded = p
            while folded < lo_r:
                folded += 12
            while folded > hi_r:
                folded -= 12
            if folded != p:
                find.add(f"{part_label}: bar "
                         f"{at_bar + spoken_shift + q_on // bar_ticks} "
                         f"note moved {'up' if folded > p else 'down'} "
                         f"{abs(folded - p) // 12} octave(s) into range")
                p = folded
        events.setdefault(q_on, []).append((p, q_off, on, off, v))
        if ks_word:
            ks_notes[(q_on, p)] = ks_word
        if trill_here and trill_here[2] == 'trem':
            trem_map[(q_on, p)] = 3
        elif trill_here:
            # the target moves with the note: octave shift and folding
            aux = trill_here[1] + (p - trill_here[0])
            trill_map[(q_on, p)] = (aux, 'trem' if trill_here[2] ==
                                    'ftrem' else 'second' if aux - p <= 2
                                    else 'auto')

    # A horn is one voice: when several played notes land on one slot,
    # the latest-played keeps it and earlier ones step back one free
    # subdivision — a note that exists in the playing should survive
    # quantization whenever there is room for it. A polyphonic
    # instrument (piano, guitar, vibes) keeps its chords instead.
    for q_on in sorted(events) if not (poly or drums) else ():
        lst = events[q_on]
        if len(lst) <= 1:
            continue
        lst.sort(key=lambda t: t[2])
        events[q_on] = [lst[-1]]
        for mv in reversed(lst[:-1]):
            step = DIV // grids.get(q_on // DIV, default_sub)
            tgt = q_on - step
            if tgt >= 0 and tgt not in events:
                events[tgt] = [(mv[0], min(mv[1], q_on)) + tuple(mv[2:])]
                find.add(f"{part_label}: bar "
                         f"{at_bar + spoken_shift + q_on // bar_ticks}: "
                         "two played notes landed on one slot — moved "
                         "the earlier one back a step")
            else:
                find.add(f"{part_label}: bar "
                         f"{at_bar + spoken_shift + q_on // bar_ticks}: "
                         "two played notes landed on one slot with no "
                         "room — dropped the earlier one; proofread "
                         "this bar")

    # what the fingers actually did, keyed by quantized onset — the slur
    # and ghost passes read this after the page's rhythm is settled
    raw = {q: (min(t[2] for t in lst), max(t[3] for t in lst),
               max(t[4] for t in lst))
           for q, lst in events.items()}
    # onset -> {pitch: the stroke the drummer named for it}
    named_strokes = {}
    for q, lst in events.items() if named_art else ():
        got = {t[0]: named_art[(t[2], t[0])] for t in lst
               if (t[2], t[0]) in named_art}
        if got:
            named_strokes[q] = got

    # ---- monophonic cleanup and legato gap-closing
    timeline = _mono_tl(events, n_units)

    if drums:
        # Kit notation reads spacing, not gate: each attack extends to
        # the next, capped at one beat, so an eighth-note hat pattern
        # prints as eighths and a lone crash as a beat and rests.
        cap = 3 * pulse_div if (m_den == 8 and m_num % 3 == 0) else DIV
        for i, (s_, e_, ps_) in enumerate(timeline):
            nxt = timeline[i + 1][0] if i + 1 < len(timeline) else n_units
            timeline[i] = (s_, max(s_ + 1, min(nxt, _beat_end(s_, cap,
                                                              bar_ticks),
                                               n_units)), ps_)
        drum_cap = cap

    if detail == 'simplified':
        timeline, raw, dropped = _simplify(timeline, raw, n_units)
        find.add(f"{part_label}: bars {bar_lo}-{bar_hi} simplified — "
                 + (f"{dropped} ornament(s) absorbed, " if dropped else "")
                 + "the rhythm smoothed to the eighth")

    # The same phrase gets the same cutoff. A repeated sustained note at
    # the same bar position and pitch whose gates differed slightly in
    # the demo unifies to one canonical release — preferring a duration
    # that ends on the eighth grid, else the first pass.
    echo = {}
    for idx, (s, e, ps) in enumerate(timeline):
        if e - s >= DIV:
            echo.setdefault((s % bar_ticks, tuple(ps)), []).append(idx)
    for sig, idxs in echo.items():
        if len(idxs) < 2:
            continue
        durs = [timeline[i][1] - timeline[i][0] for i in idxs]
        if max(durs) == min(durs) or max(durs) - min(durs) > DIV:
            continue
        clean = [d for d in durs if d % (DIV // 2) == 0]
        target = clean[0] if clean else durs[0]
        for i in idxs:
            s, e, ps = timeline[i]
            nxt = timeline[i + 1][0] if i + 1 < len(timeline) else n_units
            timeline[i] = (s, min(s + target, nxt, n_units), ps)
        bars = sorted({at_bar + spoken_shift
                       + timeline[i][0] // bar_ticks for i in idxs})
        find.add(f"{part_label}: repeated phrase, one cutoff — bars "
                 + ", ".join(str(b) for b in bars))

    # `short` is the writer's word: the phrase's last note prints short,
    # whatever the demo's gate held
    if short and timeline:
        s, e, ps = timeline[-1]
        timeline[-1] = (s, min(e, s + DIV // 2), ps)

    # ---- polyphony: hands to staves, pedal tones to voices. The flat
    # timeline above stays as the range report's and the fallback's one
    # answer; when anything genuinely polyphonic is found, the page and
    # the prose read the voices instead.
    staves_out = None
    if drums:
        pass                               # a kit is one staff of hits
    elif poly and detail in ('simplified', 'rhythmic-slashes'):
        find.add(f"{part_label}: detail {detail} prints one line — "
                 "hands and held voices fold into it")
    elif poly:
        staff_events = {1: {k: list(v) for k, v in events.items()}}
        if grand:
            hands = convert.Hands(reach, comfortable, find)
            staff_events = {1: {}, 2: {}}
            prev_on = None
            holding = []                   # (end, pitch) still sounding —
            for q_on in sorted(events):    # a held note IS the hand's
                lst = events[q_on]         # position, so it anchors the
                holding = [(e, p) for e, p in holding if e > q_on]  # split
                bar_no = at_bar + spoken_shift + q_on // bar_ticks
                dt = ((q_on - prev_on) / DIV if prev_on is not None
                      else 1.0)
                prev_on = q_on
                lh, rh = hands.assign(
                    sorted({p for p, *_ in lst}
                           | {p for _, p in holding}), bar_no, dt)
                for staff, members in ((1, rh), (2, lh)):
                    sel = [t for t in lst if t[0] in members]
                    if sel:
                        staff_events[staff][q_on] = sel
                        holding += [(e, p) for p, e, *_ in sel]
        split = False
        staves_out = []
        for staff in sorted(staff_events):
            evts = staff_events[staff]
            ped = _pedals(evts, n_units)
            if ped:
                split = True
            voices = [_mono_tl(evts, n_units)]
            if ped:
                voices.append(ped)
            staves_out.append({'staff': staff, 'voices': voices})
        if not (split or grand):
            staves_out = None              # nothing polyphonic: flat path
        else:
            if short and staves_out[0]['voices'][0]:
                tl = staves_out[0]['voices'][0]
                s, e, ps = tl[-1]
                tl[-1] = (s, min(e, s + DIV // 2), ps)
            pbars = sorted({at_bar + spoken_shift + s // bar_ticks
                            for st in staves_out
                            for v in st['voices'][1:]
                            for s, _, _ in v})
            if pbars:
                find.add(f"{part_label}: held notes keep ringing under "
                         "the line and print as their own voice — bars "
                         + ", ".join(str(b) for b in pbars))

    # ---- phrasing, only on the writer's word: `legato` reads the
    # played gates into slurs, `ghosts` reads the velocities into
    # parenthesized noteheads. Never unasked — a finished chart's pages
    # are the writer's, and phrase-end softness is not a ghost note.
    slurs = (_slur_runs(timeline, raw)
             if legato and not drums else [])
    ghosts = _ghosts(timeline, raw) if ghost else set()
    if staves_out:
        for st in staves_out:
            st['slurs'] = [_slur_runs(v, raw)
                           if legato and vi == 0 else []
                           for vi, v in enumerate(st['voices'])]
            st['ghosts'] = [_ghosts(v, raw) if ghost and vi == 0
                            else set()
                            for vi, v in enumerate(st['voices'])]
        n_sl = sum(len(r) for st in staves_out for r in st['slurs'])
        gh = sorted({at_bar + spoken_shift + v[i][0] // bar_ticks
                     for st in staves_out
                     for gs, v in zip(st['ghosts'], st['voices'])
                     for i in gs})
    else:
        n_sl = len(slurs)
        gh = sorted({at_bar + spoken_shift + timeline[i][0] // bar_ticks
                     for i in ghosts})
    if legato and len(timeline) >= 2:
        find.add(f"{part_label}: bars {bar_lo}-{bar_hi}: "
                 + (f"{n_sl} slurred phrase(s) from the played legato"
                    if n_sl else
                    "legato asked, but the playing is detached — "
                    "no slurs written; hold the notes into each other "
                    "and re-export"))
    if ghost:
        find.add(f"{part_label}: "
                 + ("ghost notes in parentheses — bars "
                    + ", ".join(str(b) for b in gh) if gh else
                    "ghosts asked, but no note sits far enough under "
                    "its neighbours — none written"))

    grids_chart = {b: grids.get(b, default_sub)
                   for b in range((n_units // DIV) + 1)}
    if detail == 'simplified':
        grids_chart = {b: 2 for b in range((n_units // DIV) + 1)}

    # ---- dynamics from the expression pedal (CC 11): one mark per level
    # change, judged by each bar's median, printed only on bars that play
    def klass(v):
        for cap, k in ((40, 'p'), (64, 'mp'), (90, 'mf'), (112, 'f')):
            if v < cap:
                return k
        return 'ff'
    by_bar = {}
    for t, v in (demo.cc11(track_name) if derive_dyns else ()):
        if lo_t <= t < hi_t:
            by_bar.setdefault(int((t - lo_t) // tick_bar), []).append(v)
    active = {s // bar_ticks for s, _, _ in timeline}
    dyns, prev = [], None
    for bo in sorted(active):
        vs = sorted(by_bar.get(bo, []))
        if not vs:
            continue
        k = klass(vs[len(vs) // 2])
        if k != prev:
            dyns.append((bo * bar_ticks, k))
            prev = k
    if dyns:
        find.add(f"{part_label}: bars {bar_lo}-{bar_hi} dynamics read from "
                 "the expression pedal: "
                 + ", ".join(f"{k} at bar {at_bar + t // bar_ticks}"
                             for t, k in dyns))

    return {'timeline': timeline, 'grids': grids_chart,
            'n_units': n_units, 'at': at_bar,
            'bars': (bar_lo, bar_hi), 'dyns': dyns,
            'slurs': slurs, 'ghosts': ghosts, 'detail': detail,
            'named_strokes': named_strokes,
            'spoken_shift': spoken_shift, 'staves': staves_out,
            'bar_ticks': bar_ticks, 'pulse_div': pulse_div,
            'drums': drums, 'drum_cap': drum_cap if drums else None,
            'trills': trill_map, 'trems': trem_map, 'ks': ks_notes}


def bend_indices(res, bends):
    """Resolve scoop/plop placements ((kind, 'first'|'last'|(bar, beat)))
    to {timeline index: kind} — shared by the page and the prose."""
    tl = res['timeline']
    out = {}
    for kind, sp in bends or ():
        if sp == 'first':
            out[0] = kind
        elif sp == 'last':
            out[len(tl) - 1] = kind
        else:
            bar, beat = sp
            target = ((bar - res['bars'][0])
                      * res.get('bar_ticks', BAR)
                      + (beat - 1) * res.get('pulse_div', DIV))
            best = min(range(len(tl)), key=lambda i: abs(tl[i][0] - target))
            out[best] = kind
    return out


class KeyedTable:
    '''A spelling table that follows the key bar by bar: whoever emits a
    bar sets .at first, and every lookup spells in that bar's key. A
    figure crossing a modulation spells each side in its own key.'''
    def __init__(self, fifths_at, find, minor_at=None, chords_at=None):
        self.fifths_at, self.find, self.at = fifths_at, find, None
        # minor_at(bar) -> is that bar's key minor; chords_at(bar) ->
        # {pitch class: (step, alter)} for the chord tones sounding in
        # that bar, already in this table's (written) frame. A chord
        # spells what the signature does not: C# under A7 in any key.
        self.minor_at, self.chords_at = minor_at, chords_at
        self._cache = {}

    def _t(self):
        f = self.fifths_at(self.at) if self.at is not None else \
            self.fifths_at(None)
        minor = bool(self.minor_at and self.minor_at(self.at))
        chords = (self.chords_at(self.at)
                  if self.chords_at and self.at is not None else None)
        ck = (f, minor, tuple(sorted(chords.items())) if chords else ())
        if ck not in self._cache:
            self._cache[ck] = spelling_table(f, self.find, minor=minor,
                                             chords=chords)
        return self._cache[ck]

    def __getitem__(self, k):
        return self._t()[k]

    def get(self, k, d=None):
        return self._t().get(k, d)


def render_range(res, fifths_written, transpose_to_written, fall,
                 findings=None, short=False, every=None, doit=False,
                 scoops=None, cue=False, fifths_at=None, minor_at=None,
                 chords_at=None):
    """Resolved timeline -> {abs_bar: MusicXML measure content}."""
    find = findings if findings is not None else Findings()
    at_bar = res['at']
    n_units = res['n_units']
    timeline = res['timeline']
    grids_chart = res['grids']
    table = (KeyedTable(lambda b: fifths_at(b) if b is not None
                        else fifths_written, find, minor_at, chords_at)
             if fifths_at else spelling_table(fifths_written, find))
    trills = res.setdefault('trills', {})

    def trill_of(start, pitches):
        for p in pitches:
            if (start, p) in trills:
                aux, form = trills[(start, p)]
                return {'main': p, 'aux': aux, 'form': form,
                        'fifths': fifths_written}
        return None
    res['_trill_of'] = trill_of
    trems = res.setdefault('trems', {})

    def trem_of(start, pitches):
        for p in pitches:
            if (start, p) in trems:
                return trems[(start, p)]
        return None
    res['_trem_of'] = trem_of
    last_artic = ('falloff' if fall else 'doit' if doit else
                  'staccato' if short else None)
    bends = bend_indices(res, scoops)

    bar_ticks = res.get('bar_ticks', BAR)
    slash = res.get('detail') == 'rhythmic-slashes'
    drums = bool(res.get('drums')) and not slash
    if drums:
        transpose_to_written = 0
    SOUND_DYN = {'p': 54, 'mp': 71, 'mf': 89, 'f': 106, 'ff': 123}

    if res.get('staves'):
        # genuinely polyphonic: hands and held layers, each its own voice
        out = _render_voices(res, table, transpose_to_written, every,
                             last_artic)
        for t, k in res.get('dyns', []):
            bar = at_bar + t // bar_ticks
            if bar in out:
                out[bar] = (
                    '      <direction placement="below"><direction-type>'
                    f'<dynamics><{k}/></dynamics></direction-type>'
                    f'<sound dynamics="{SOUND_DYN[k]}"/></direction>\n'
                    + out[bar])
        return out

    if drums:
        # Two voices when both families play, the way drum books are
        # engraved: cymbals (x-family heads) stems up as voice one,
        # kick, snare and toms stems down as voice two — decided BAR BY
        # BAR, so a stretch with no cymbals reads as one plain voice
        # instead of resting a phantom line above it. Durations re-read
        # spacing within each family, capped at a beat and chopped at
        # the barline (a drum hit is its attack; what follows is
        # silence either way).
        cyms, drms = [], []
        for s_, e_, ps_ in timeline:
            c = [p for p in ps_
                 if instruments.drum_position(p)[2] != 'normal']
            d = [p for p in ps_
                 if instruments.drum_position(p)[2] == 'normal']
            if c:
                cyms.append((s_, c))
            if d:
                drms.append((s_, d))
        if cyms and drms and res.get('kit', True):
            cap = res.get('drum_cap') or DIV
            ghost_on = ({res['timeline'][i][0] for i in res.get('ghosts')
                         or ()})
            named_s = res.get('named_strokes') or {}
            nbars = n_units // bar_ticks
            per_bar = {bi: ([], []) for bi in range(nbars)}
            for fam, hits in ((0, cyms), (1, drms)):
                for ti, (s_, ps_) in enumerate(hits):
                    nxt = (hits[ti + 1][0] if ti + 1 < len(hits)
                           else n_units)
                    wall = (s_ // bar_ticks + 1) * bar_ticks
                    e_ = max(s_ + 1, min(nxt, _beat_end(s_, cap,
                                                        bar_ticks),
                                         wall, n_units))
                    per_bar[s_ // bar_ticks][fam].append((s_, e_, ps_))
            backup = (f'      <backup><duration>{bar_ticks}</duration>'
                      '</backup>\n')
            merged = {}
            for bi in range(nbars):
                b = at_bar + bi
                lo, hi = bi * bar_ticks, (bi + 1) * bar_ticks
                lanes = [evs for evs in per_bar[bi] if evs]
                if not lanes:
                    outd = {b: []}
                    _emit(outd, at_bar, lo, hi, None, table, grids_chart,
                          None, 0, bar=bar_ticks)
                    merged[b] = "".join(outd[b])
                    continue
                parts = []
                last_ev = (drms[-1][0] if drms else -1)
                for vno, evs in enumerate(lanes, 1):
                    outd = {b: []}
                    pos = lo
                    for s_, e_, ps_ in evs:
                        if s_ > pos:
                            _emit(outd, at_bar, pos, s_, None, table,
                                  grids_chart, None, 0, bar=bar_ticks,
                                  voice=vno)
                        drum_fam = ps_ and instruments.drum_position(
                            ps_[0])[2] == 'normal'
                        _emit(outd, at_bar, s_, e_, ps_, table,
                              grids_chart,
                              (last_artic if (drum_fam and s_ == last_ev)
                               else None) or every,
                              0, bar=bar_ticks, voice=vno,
                              ghost=drum_fam and s_ in ghost_on,
                              drums=True, strokes=named_s.get(s_))
                        pos = e_
                    if pos < hi:
                        _emit(outd, at_bar, pos, hi, None, table,
                              grids_chart, None, 0, bar=bar_ticks,
                              voice=vno)
                    parts.append("".join(outd[b]))
                merged[b] = backup.join(pp for pp in parts if pp)
            for t, k in res.get('dyns', []):
                bar = at_bar + t // bar_ticks
                if bar in merged:
                    merged[bar] = (
                        '      <direction placement="below">'
                        '<direction-type>'
                        f'<dynamics><{k}/></dynamics></direction-type>'
                        f'<sound dynamics="{SOUND_DYN[k]}"/></direction>\n'
                        + merged[bar])
            return merged

    out = {b: [] for b in
           range(at_bar, at_bar + (n_units // bar_ticks))}
    concert_f = ((fifths_written - 7 * transpose_to_written + 6) % 12) - 6
    ks_marks, ks_texts, ks_runs = ks_plan(res, timeline, concert_f)
    if ks_runs and not res.get('slurs'):
        res['slurs'] = ks_runs      # legato the patch played, slurred
    slur_a = {i for i, _ in res.get('slurs', ())}
    slur_b = {j for _, j in res.get('slurs', ())}
    ghosts = res.get('ghosts') or set()
    lyr = res.get('lyrics')
    pos = 0
    for ti, (start, end, pitches) in enumerate(timeline):
        if start > pos:
            _emit(out, at_bar, pos, start, None, table, grids_chart,
                  None, transpose_to_written, bar=bar_ticks)
        is_last = ti == len(timeline) - 1
        if start in ks_texts:
            out[at_bar + start // bar_ticks].append(
                words_direction(ks_texts[start]))
        _emit(out, at_bar, start, end, pitches, table, grids_chart,
              (last_artic if is_last else None) or ks_marks.get(start)
              or every,
              transpose_to_written, bend=bends.get(ti), bar=bar_ticks,
              slur=(ti in slur_a, ti in slur_b),
              ghost=ti in ghosts,
              strokes=((res.get('named_strokes') or {}).get(start)
                       if drums else None),
              lyric=lyr[ti] if lyr else None, cue=cue, slash=slash,
              drums=drums, trill=trill_of(start, pitches),
              trem=trem_of(start, pitches))
        pos = end
    if pos < n_units:
        _emit(out, at_bar, pos, n_units, None, table, grids_chart,
              None, transpose_to_written, bar=bar_ticks)

    for t, k in res.get('dyns', []):
        bar = at_bar + t // bar_ticks
        if bar in out:
            out[bar].insert(
                0,
                '      <direction placement="below"><direction-type>'
                f'<dynamics><{k}/></dynamics></direction-type>'
                f'<sound dynamics="{SOUND_DYN[k]}"/></direction>\n')

    return {b: "".join(lines) for b, lines in out.items()}


def _render_voices(res, table, transpose, every, last_artic):
    """The polyphonic page: staff by staff, voice by voice, stitched per
    measure with backups. The first voice of a staff owns every figure
    bar (rests around its line); a held layer appears only in bars it
    actually rings, filled barline to barline so the arithmetic holds."""
    at_bar = res['at']
    n_units = res['n_units']
    bar_ticks = res['bar_ticks']
    grids = res['grids']
    staves = res['staves']
    nbars = n_units // bar_ticks
    two_staves = len(staves) > 1
    chunks = []                            # ({bar: [str]}, covered_bars)
    for st in staves:
        staff_no = st['staff'] if two_staves else 0
        base = 1 if st['staff'] == 1 else 5
        for vi, tl in enumerate(st['voices'] or [[]]):
            voice_no = base + vi
            runs = (st.get('slurs') or [[]] * (vi + 1))[vi] \
                if vi < len(st.get('slurs', ())) else []
            slur_a = {i for i, _ in runs}
            slur_b = {j for _, j in runs}
            gset = (st.get('ghosts') or [set()] * (vi + 1))[vi] \
                if vi < len(st.get('ghosts', ())) else set()
            outd = {b: [] for b in range(at_bar, at_bar + nbars)}
            if vi == 0:
                pos = 0
                for ti, (s, e, ps) in enumerate(tl):
                    if s > pos:
                        _emit(outd, at_bar, pos, s, None, table, grids,
                              None, transpose, bar=bar_ticks,
                              voice=voice_no, staff=staff_no)
                    is_last = ti == len(tl) - 1
                    _emit(outd, at_bar, s, e, ps, table, grids,
                          ((last_artic if is_last and st['staff'] == 1
                            else None) or every),
                          transpose, bar=bar_ticks,
                          voice=voice_no, staff=staff_no,
                          slur=(ti in slur_a, ti in slur_b),
                          ghost=ti in gset,
                          trill=res['_trill_of'](s, ps),
                          trem=res['_trem_of'](s, ps))
                    pos = e
                if pos < n_units:
                    _emit(outd, at_bar, pos, n_units, None, table, grids,
                          None, transpose, bar=bar_ticks,
                          voice=voice_no, staff=staff_no)
                covered = set(outd)
            else:
                covered = set()
                for s, e, _ in tl:
                    covered.update(range(at_bar + s // bar_ticks,
                                         at_bar + (e - 1) // bar_ticks + 1))
                regions = []
                for b in sorted(covered):
                    if regions and b == regions[-1][1]:
                        regions[-1][1] = b + 1
                    else:
                        regions.append([b, b + 1])
                idx = 0
                for rb, re_ in regions:
                    pos = (rb - at_bar) * bar_ticks
                    r1 = (re_ - at_bar) * bar_ticks
                    while idx < len(tl) and tl[idx][0] < r1:
                        s, e, ps = tl[idx]
                        if s > pos:
                            _emit(outd, at_bar, pos, s, None, table,
                                  grids, None, transpose, bar=bar_ticks,
                                  voice=voice_no, staff=staff_no)
                        _emit(outd, at_bar, s, e, ps, table, grids, None,
                              transpose, bar=bar_ticks,
                              voice=voice_no, staff=staff_no,
                              trill=res['_trill_of'](s, ps),
                              trem=res['_trem_of'](s, ps))
                        pos = e
                        idx += 1
                    if pos < r1:
                        _emit(outd, at_bar, pos, r1, None, table, grids,
                              None, transpose, bar=bar_ticks,
                              voice=voice_no, staff=staff_no)
            chunks.append((outd, covered))
    backup = f'      <backup><duration>{bar_ticks}</duration></backup>\n'
    out = {}
    for b in range(at_bar, at_bar + nbars):
        parts = ["".join(c[0][b]) for c in chunks
                 if b in c[1] and c[0].get(b)]
        out[b] = backup.join(p for p in parts if p)
    return out


def _is_tuplet(grids, b):
    sub = grids.get(b, 4)
    _, _, actual, normal, _ = tuplets.CANDIDATES[sub]
    return actual != normal


def _pieces(start, end, grids, bar=BAR):
    """Cut a span at barlines always, and at beat boundaries around any
    tuplet beat, so every piece lives in exactly one naming regime."""
    cuts = []
    pos = start
    while pos < end:
        b = pos // DIV
        next_beat = (b + 1) * DIV
        stop = min(end, (pos // bar + 1) * bar)
        if _is_tuplet(grids, b):
            stop = min(stop, next_beat)
        else:
            nb = b + 1
            while nb * DIV < stop:
                if _is_tuplet(grids, nb):
                    stop = nb * DIV
                    break
                nb += 1
        cuts.append((pos, stop))
        pos = stop
    return cuts


def _name(ticks, sub):
    """(len, type, dots, time-modification) pieces for one duration.

    Inside a tuplet beat every piece must speak tuplet language — a binary
    64th sliver in a sextuplet beat is exactly what MuseScore refuses. A
    duration that is not one nameable value splits greedily into nameable
    tuplet chunks (five sextuplet-sixteenths = quarter + sixteenth, both
    carrying the 6:4 modification)."""
    mod = tuplets.modification(sub)
    if mod:
        nd = tuplets.notated(ticks, DIV, sub)
        if nd:
            return [(ticks, nd[0], nd[1], mod)]
        step = DIV // sub
        if ticks % step == 0:
            out, rem = [], ticks // step
            for mult in (8, 6, 4, 3, 2, 1):
                while rem >= mult:
                    nd = tuplets.notated(mult * step, DIV, sub)
                    if nd is None:
                        break
                    out.append((mult * step, nd[0], nd[1], mod))
                    rem -= mult
                if rem == 0:
                    return out
    return [(t, ty, d, None) for t, ty, d in decompose(ticks, DIV)]


def _emit(out, at_bar, start, end, pitches, table, grids, artic, transpose,
          bend=None, bar=BAR, voice=1, staff=0, slur=(False, False),
          ghost=False, lyric=None, cue=False, slash=False, drums=False,
          trill=None, trem=None, strokes=None):
    staff_xml = f'        <staff>{staff}</staff>\n' if staff else ''
    strokes = strokes or {}
    pieces = _pieces(start, end, grids, bar)
    if trill and trill.get('form') == 'trem' and pitches \
            and len(pitches) == 1 and not (slash or drums or cue):
        if _emit_ftrem(out, at_bar, pieces, grids, bar, pitches[0],
                       trill, table, transpose, voice, staff_xml, artic,
                       lyric):
            return
        trill = dict(trill, form='auto')   # tied or odd: tr to (note)
    for pi, (a, b) in enumerate(pieces):
        bar_no = at_bar + a // bar
        if bar_no not in out:
            continue
        if isinstance(table, KeyedTable):
            table.at = bar_no
        first, last = pi == 0, pi == len(pieces) - 1
        sub = grids.get(a // DIV, 4)
        if pitches is None and a % bar == 0 and b - a == bar:
            out[bar_no].append(
                '      <note>\n        <rest measure="yes"/>\n'
                f'        <duration>{bar}</duration>\n'
                f'        <voice>{voice}</voice>\n'
                + staff_xml + '      </note>\n')
            continue
        parts = _name(b - a, sub)
        for qi, (plen, ptype, dots, mod) in enumerate(parts):
            plast = last and qi == len(parts) - 1
            pfirst = first and qi == 0
            if pitches is None:
                out[bar_no].append('      <note>\n        <rest/>\n'
                                f'        <duration>{plen}</duration>\n'
                                f'        <voice>{voice}</voice>\n'
                                f'        <type>{ptype}</type>\n'
                                + '        <dot/>\n' * dots
                                + (_mod_xml(mod) if mod else '')
                                + staff_xml
                                + '      </note>\n')
                continue
            if drums and not pfirst:
                # a drum hit is its attack — what follows is silence on
                # the page, never a tied note
                out[bar_no].append('      <note>\n        <rest/>\n'
                                f'        <duration>{plen}</duration>\n'
                                f'        <voice>{voice}</voice>\n'
                                f'        <type>{ptype}</type>\n'
                                + '        <dot/>\n' * dots
                                + staff_xml
                                + '      </note>\n')
                continue
            for ni, p in enumerate(pitches):
                if slash and ni:
                    continue           # a slash speaks for the voicing
                if drums:
                    pfirst = plast = True
                    dstep, doct, dhead = instruments.drum_position(p)
                    alter = 0
                    if strokes.get(p) == 'rimshot' and dhead == 'normal':
                        dhead = 'slashed'     # Weinberg: slash through
                    if ni == 0:
                        # flams and drags: small notes leaning on the
                        # stroke, before the first note of the chord
                        for gp in pitches:
                            n_g = {'flam': 1, 'drag': 2}.get(
                                strokes.get(gp), 0)
                            gs, go, gh = instruments.drum_position(gp)
                            for _k in range(n_g):
                                out[bar_no].append(
                                    '      <note>\n'
                                    + ('        <grace slash="yes"/>\n'
                                       if n_g == 1 else
                                       '        <grace/>\n')
                                    + '        <unpitched><display-step>'
                                    f'{gs}</display-step><display-octave>'
                                    f'{go}</display-octave></unpitched>\n'
                                    f'        <voice>{voice}</voice>\n'
                                    '        <type>'
                                    + ('eighth' if n_g == 1 else '16th')
                                    + '</type>\n'
                                    + (f'        <notehead>{gh}</notehead>\n'
                                       if gh != 'normal' else '')
                                    + staff_xml + '      </note>\n')
                else:
                    w = p + transpose
                    step, alter, octave = convert.spell(w, table)
                if slash:
                    step, alter, octave = 'B', 0, 4
                lines = ['      <note>']
                if cue:
                    # printed small, never sounded — and our own player
                    # honors that, which MuseScore never did
                    lines.append('        <cue/>')
                if ni:
                    lines.append('        <chord/>')
                if drums:
                    lines.append('        <unpitched>'
                                 f'<display-step>{dstep}</display-step>'
                                 f'<display-octave>{doct}</display-octave>'
                                 '</unpitched>')
                else:
                    lines.append('        <pitch>'
                                 f'<step>{step}</step>'
                                 + (f'<alter>{alter}</alter>' if alter
                                    else '')
                                 + f'<octave>{octave}</octave></pitch>')
                lines.append(f'        <duration>{plen}</duration>')
                if not pfirst and not cue:
                    lines.append('        <tie type="stop"/>')
                if not plast and not cue:
                    lines.append('        <tie type="start"/>')
                lines.append(f'        <voice>{voice}</voice>')
                lines.append(f'        <type>{ptype}</type>')
                lines += ['        <dot/>'] * dots
                if alter and not slash:
                    lines.append(
                        f'        <accidental>{ACC_NAME[alter]}</accidental>')
                if slash:
                    lines.append('        <notehead>slash</notehead>')
                if mod:
                    lines.append(_mod_xml(mod).rstrip())
                if ghost is True or (ghost and p in ghost) \
                        or strokes.get(p) == 'ghost':
                    # a ghost note prints in parentheses
                    lines.append('        <notehead parentheses="yes">'
                                 f'{dhead if drums else "normal"}'
                                 '</notehead>')
                elif drums and dhead != 'normal':
                    lines.append(f'        <notehead>{dhead}</notehead>')
                if staff:
                    lines.append(f'        <staff>{staff}</staff>')
                notations = []
                if not pfirst:
                    notations.append('<tied type="stop"/>')
                if not plast:
                    notations.append('<tied type="start"/>')
                if slur[0] and pfirst and ni == 0:
                    notations.append('<slur number="1" type="start"/>')
                if slur[1] and plast and ni == 0:
                    notations.append('<slur number="1" type="stop"/>')
                arts = []
                if bend and pfirst and ni == len(pitches) - 1:
                    arts.append(f'<{bend}/>')
                if artic and plast and ni == len(pitches) - 1:
                    arts.append(f'<{artic}/>')
                if drums and strokes.get(p) == 'choke':
                    arts.append('<breath-mark/>')   # the choke comma
                if arts:
                    notations.append('<articulations>' + ''.join(arts)
                                     + '</articulations>')
                if trem and not slash and not drums and ni == 0:
                    notations.append('<ornaments><tremolo type="single">'
                                     f'{trem}</tremolo></ornaments>')
                if trill and not slash and not drums \
                        and p == trill['main']:
                    orn = []
                    if pfirst:
                        orn += trill_marks(step, alter, octave,
                                           trill['aux'] + transpose,
                                           trill['fifths'], table,
                                           trill.get('form', 'auto'),
                                           transpose)
                        orn.append('<wavy-line type="start"/>')
                    if plast:
                        orn.append('<wavy-line type="stop"/>')
                    if orn:
                        notations.append('<ornaments>' + ''.join(orn)
                                         + '</ornaments>')
                if notations:
                    lines.append('        <notations>' + ''.join(notations)
                                 + '</notations>')
                if lyric and pfirst and ni == 0:
                    syl, txt, ext = lyric
                    lines.append('        <lyric>'
                                 f'<syllabic>{syl}</syllabic>'
                                 f'<text>{txt}</text>'
                                 + ('<extend/>' if ext else '')
                                 + '</lyric>')
                lines.append('      </note>')
                out[bar_no].append("\n".join(lines) + "\n")


def _emit_ftrem(out, at_bar, pieces, grids, bar, main, trill, table,
                transpose, voice, staff_xml, artic, lyric):
    """A fingered tremolo: the note's time shared by two notes, each
    printed at the full value (a half-note tremolo shows two half
    notes), 2:1 in the time, three floating beams between them — how
    the orchestral books print a wide shake. Only a note that is one
    plain piece of a quarter or longer can wear it; anything else says
    no and becomes a trill to its note."""
    if len(pieces) != 1:
        return False
    a, b = pieces[0]
    parts = _name(b - a, grids.get(a // DIV, 4))
    if len(parts) != 1:
        return False
    plen, ptype, dots, mod = parts[0]
    if mod or dots or plen % 2 or ptype not in ('whole', 'half',
                                                'quarter'):
        return False
    bar_no = at_bar + a // bar
    if bar_no not in out:
        return True
    for k, midi in enumerate((main, trill['aux'])):
        step, alter, octave = convert.spell(midi + transpose, table)
        lines = ['      <note>',
                 '        <pitch>' f'<step>{step}</step>'
                 + (f'<alter>{alter}</alter>' if alter else '')
                 + f'<octave>{octave}</octave></pitch>',
                 f'        <duration>{plen // 2}</duration>',
                 f'        <voice>{voice}</voice>',
                 f'        <type>{ptype}</type>']
        if alter:
            lines.append(f'        <accidental>{ACC_NAME[alter]}'
                         '</accidental>')
        lines.append('        <time-modification><actual-notes>2'
                     '</actual-notes><normal-notes>1</normal-notes>'
                     '</time-modification>')
        if staff_xml:
            lines.append(staff_xml.rstrip())
        nots = ['<ornaments><tremolo type="'
                + ('start' if k == 0 else 'stop') + '">3</tremolo>'
                '</ornaments>']
        if artic and k == 1:
            nots.append(f'<articulations><{artic}/></articulations>')
        lines.append('        <notations>' + ''.join(nots)
                     + '</notations>')
        if lyric and k == 0:
            syl, txt, ext = lyric
            lines.append('        <lyric>'
                         f'<syllabic>{syl}</syllabic><text>{txt}</text>'
                         + ('<extend/>' if ext else '') + '</lyric>')
        lines.append('      </note>')
        out[bar_no].append("\n".join(lines) + "\n")
    return True


def key_alter(letter, fifths):
    sharps, flats = 'FCGDAEB', 'BEADGCF'
    return (1 if fifths > 0 and letter in sharps[:fifths] else
            -1 if fifths < 0 and letter in flats[:-fifths] else 0)


ACC_TEXT = {-2: 'bb', -1: 'b', 0: '', 1: '#', 2: 'x'}


def spell_trill(step, alter, octave, aux_written, fifths, table,
                form='auto', transpose=0):
    """Where a trill's target sits on the page: (letter, alter, octave,
    second). A half or whole step, and an augmented second, stay on the
    next letter up; `tr to D#5` keeps the writer's letter through the
    horn's transposition; anything else takes the key's spelling."""
    nat = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
    letters = 'CDEFGAB'
    up = letters[(letters.index(step) + 1) % 7]
    oct_up = octave + (1 if up == 'C' else 0)
    diff = aux_written - (nat[up] + (oct_up + 1) * 12)
    if len(form) == 1:
        shift = {0: 0, 2: 1, -10: 1, 3: 2, 5: 3, 7: 4, 9: 5, -3: 5,
                 -5: 4, -7: 3, -9: 2, 14: 1, 21: 5, 12: 0, -12: 0,
                 -24: 0, 24: 0}.get(transpose)
        if shift is not None:
            lw = letters[(letters.index(form) + shift) % 7]
            oc = (aux_written // 12) - 1
            for o in (oc - 1, oc, oc + 1):
                al = aux_written - (nat[lw] + (o + 1) * 12)
                if -2 <= al <= 2:
                    return (lw, al, o, lw == up and o == oct_up)
        form = 'auto'
    if form == 'second' and -2 <= diff <= 2:
        return (up, diff, oct_up, True)
    st, al, oc = convert.spell(aux_written, table)
    return (st, al, oc, st == up and oc == oct_up)


def trill_marks(step, alter, octave, aux_written, fifths, table,
                form='auto', transpose=0):
    """The ornament children for a trill: the mark, an accidental over
    it when a second's target leaves the key, or — for anything wider —
    the target named in parentheses, the small note an engraver draws
    after the head and the exact pitch our player alternates with."""
    lw, al, oc, second = spell_trill(step, alter, octave, aux_written,
                                     fifths, table, form, transpose)
    out = ['<trill-mark/>']
    if second:
        if al != key_alter(lw, fifths):
            out.append(f'<accidental-mark>{ACC_NAME[al]}'
                       '</accidental-mark>')
        return out
    out.append(f'<other-ornament>({lw}{ACC_TEXT[al]}{oc})'
               '</other-ornament>')
    return out


INTERVAL_NAME = {(1, 0): 'a unison', (1, 1): 'a half step',
                 (1, 2): 'a whole step', (1, 3): 'an augmented second',
                 (2, 2): 'a diminished third', (2, 3): 'a minor third',
                 (2, 4): 'a major third', (3, 4): 'a diminished fourth',
                 (3, 5): 'a fourth', (3, 6): 'an augmented fourth',
                 (4, 6): 'a diminished fifth', (4, 7): 'a fifth',
                 (4, 8): 'an augmented fifth', (5, 8): 'a minor sixth',
                 (5, 9): 'a major sixth', (6, 10): 'a minor seventh',
                 (6, 11): 'a major seventh', (0, 12): 'an octave'}


def name_interval(step, octave, lw, oc, semis):
    letters = 'CDEFGAB'
    steps = (letters.index(lw) + 7 * oc) - (letters.index(step)
                                            + 7 * octave)
    return INTERVAL_NAME.get((steps % 7 if steps < 7 else 0, semis),
                             f"{semis} semitones")


def _mod_xml(mod):
    return ('        <time-modification>'
            f'<actual-notes>{mod["actual"]}</actual-notes>'
            f'<normal-notes>{mod["normal"]}</normal-notes>'
            '</time-modification>\n')


# ------------------------------------------------------------- prose

ACC_WORD = {-2: ' double flat', -1: ' flat', 0: '', 1: ' sharp',
            2: ' double sharp'}

DUR_WORD = {96: 'whole note', 84: 'double-dotted half', 72: 'dotted half',
            48: 'half note', 36: 'dotted quarter', 24: 'quarter',
            18: 'dotted eighth', 12: 'eighth', 9: 'dotted sixteenth',
            6: 'sixteenth', 3: 'thirty-second',
            16: 'triplet quarter', 8: 'triplet eighth',
            4: 'triplet sixteenth', 2: 'sextuplet thirty-second'}


def _say_pitch(p, table):
    if p == 'slash':
        return "slash"
    if table is None:
        return instruments.drum_name(p)
    step, alter, octave = convert.spell(p, table)
    return f"{step}{ACC_WORD[alter]} {octave}"


def _say_beat(pos, bar=BAR, pulse=DIV):
    beat = pos % bar / pulse + 1
    if beat == int(beat):
        return f"beat {int(beat)}"
    if (pos % pulse) % (pulse // 2 or 1) == 0:
        return f"the and of {int(beat)}"
    return f"inside beat {int(beat)}"


def _say_dur(ticks):
    if ticks in DUR_WORD:
        return DUR_WORD[ticks]
    pieces = decompose(ticks, DIV)
    if 1 <= len(pieces) <= 3:
        words = []
        for _, name, dots in pieces:
            words.append(("double-dotted " if dots == 2 else
                          "dotted " if dots == 1 else "") + name)
        return " tied to ".join(words)
    return f"about {ticks / DIV:.1f} beats"


def _say_tl(tl, table, at_bar, bar_ticks, pulse, bends,
            fall=False, doit=False, short=False, slurs=(), ghosts=(),
            lyrics=None, orn=None):
    """One voice's timeline -> {abs_bar: [clauses]} — the run-grouping
    prose, shared by the flat path and each voice of a polyphonic part."""
    out = {}
    slur_a = {a for a, _ in slurs}
    slur_end = {a: b for a, b in slurs}
    ghosts = set(ghosts)
    orn = orn or {}
    i = 0
    while i < len(tl):
        start, end, pitches = tl[i]
        dur = end - start
        j = i
        while (j + 1 < len(tl)
               and tl[j + 1][0] == tl[j][1]                 # gapless
               and tl[j + 1][1] - tl[j + 1][0] == dur       # same length
               and tl[j + 1][0] // bar_ticks
               == start // bar_ticks                        # same bar
               and len(tl[j + 1][2]) == 1 and len(pitches) == 1
               and j not in bends and (j + 1) not in bends
               and (j + 1) not in slur_a
               and tl[j][0] not in orn and tl[j + 1][0] not in orn
               and ((j + 1) in ghosts) == (i in ghosts)):
            j += 1
        bar = at_bar + start // bar_ticks
        if isinstance(table, KeyedTable):
            # speak in the key of the printed bar (spoken bars carry
            # the count-in; the key map counts printed bars)
            table.at = bar - getattr(table, 'shift', 0)
        clauses = out.setdefault(bar, [])
        where = _say_beat(start, bar_ticks, pulse)
        def word(k):
            if not lyrics or k >= len(lyrics):
                return ""
            t = lyrics[k]
            return " (held)" if t is None else f" '{t[1]}'"
        if j > i:
            names = ", ".join(_say_pitch(t[2][0], table) + word(i + o)
                              for o, t in enumerate(tl[i:j + 1]))
            clauses.append(f"from {where}, {_say_dur(dur)}s: {names}")
        else:
            what = (" and ".join(dict.fromkeys(
                        _say_pitch(p, table) for p in pitches))
                    + word(i))
            if len(pitches) > 1:
                what = (("together, " if table is None else "chord ")
                        + what)
            held = ""
            if end // bar_ticks > start // bar_ticks and end % bar_ticks:
                held = f", held into bar {at_bar + end // bar_ticks}"
            clauses.append(f"{where}: {_say_dur(end - start)} {what}{held}")
        if i == j and start in orn:
            clauses[-1] += ", " + orn[start]
        if i in ghosts:
            clauses[-1] += ", ghosted"
        if i in slur_a:
            k = slur_end[i]
            eb = at_bar + tl[k][0] // bar_ticks
            place = _say_beat(tl[k][0], bar_ticks, pulse)
            clauses[-1] += (f", slurred to {place}" if eb == bar
                            else f", slurred to bar {eb}")
        if i == j and i in bends:
            clauses[-1] += (", scooped" if bends[i] == 'scoop'
                            else ", plopped into")
        if j == len(tl) - 1:
            if fall:
                clauses[-1] += ", with a big fall off the end"
            elif doit:
                clauses[-1] += ", with a doit up off the end"
            elif short:
                clauses[-1] += ", short"
        i = j + 1
    return out


def say_ornaments(res, table, fifths=0):
    """{onset: words} for every trill and tremolo — spelled exactly as
    the page spells it, the interval named from the letters the way a
    player names it (G up to D-sharp is an augmented fifth)."""
    words = {}
    if table is None:
        return words
    for (s_, p), val in (res.get('trills') or {}).items():
        aux, form = val if isinstance(val, tuple) else (val, 'auto')
        step, alter, octave = convert.spell(p, table)
        lw, al, oc, _second = spell_trill(
            step, alter, octave, aux, fifths, table,
            'auto' if form == 'trem' else form)
        gap = name_interval(step, octave, lw, oc, aux - p)
        target = lw + ACC_WORD[al]
        if form == 'trem':
            words[s_] = f"fingered tremolo with {target}, {gap} up"
        else:
            words[s_] = f"trill {gap} up, to {target}"
    for (s_, p), n in (res.get('trems') or {}).items():
        words[s_] = "tremolo"
    # keyswitched articulation, spoken once where it changes, the way a
    # player pencils it in
    SAY_MARK = {'staccato': 'staccato', 'spiccato': 'spiccato',
                'staccatissimo': 'staccatissimo', 'strong-accent':
                'marcato', 'accent': 'accented', 'tenuto': 'tenuto',
                'detached-legato': 'portato', 'falloff': 'falls',
                'doit': 'doits'}
    prev = None
    for (s_, p), word in sorted((res.get('ks') or {}).items()):
        mark, text, legato, orn = ks_meaning(word)
        desc = text or SAY_MARK.get(mark) or ('legato' if legato else
                                              'ordinary')
        if orn == 'trem' and not text:
            desc = 'tremolo'
        if desc != prev:
            here = f"{desc} from here"
            words[s_] = (words[s_] + ", " + here) if s_ in words else here
            prev = desc
    return words


def say_range(res, concert_fifths, fall=False, findings=None, short=False,
              doit=False, scoops=None, fifths_at=None, minor_at=None,
              chords_at=None):
    """Resolved timeline -> {abs_bar: prose}, spoken at concert pitch."""
    find = findings if findings is not None else Findings()
    table = (None if res.get('drums') else
             KeyedTable(lambda b: fifths_at(b) if b is not None
                        else concert_fifths, find, minor_at, chords_at)
             if fifths_at
             else spelling_table(concert_fifths, find))
    if isinstance(table, KeyedTable):
        table.shift = res.get('spoken_shift', 0)
    orn = say_ornaments(res, table, concert_fifths)
    for q, got in (res.get('named_strokes') or {}).items():
        # the strokes the drummer named, said the way a drummer says them
        said = []
        for p_, art in sorted(got.items()):
            piece = instruments.drum_name(p_)
            said.append(f"{piece} ghosted" if art == 'ghost' else
                        f"{piece} choked" if art == 'choke' else
                        f"{art} on the {piece}")
        orn[q] = ", ".join(([orn[q]] if q in orn else []) + said)
    at_bar = res['at'] + res.get('spoken_shift', 0)
    bar_ticks = res.get('bar_ticks', BAR)
    pulse = res.get('pulse_div', DIV)
    bends = bend_indices(res, scoops)

    if res.get('detail') == 'rhythmic-slashes':
        res = dict(res, timeline=[(s, e, ['slash'])
                                  for s, e, _ in res['timeline']],
                   staves=None, lyrics=None)

    if res.get('staves'):
        # polyphonic prose: each voice speaks, labelled, in page order
        two = len(res['staves']) > 1
        ordered = []
        for st in res['staves']:
            for vi, tl in enumerate(st['voices'] or [[]]):
                if not tl:
                    continue
                hand = ('right hand' if st['staff'] == 1 else
                        'left hand') if two else ''
                label = (hand + (', held underneath' if vi else '')
                         if two else ('held underneath' if vi else ''))
                first = st['staff'] == 1 and vi == 0
                runs = st.get('slurs', [[]])[vi] \
                    if vi < len(st.get('slurs', ())) else []
                gset = st.get('ghosts', [set()])[vi] \
                    if vi < len(st.get('ghosts', ())) else set()
                ordered.append((label, _say_tl(
                    tl, table, at_bar, bar_ticks, pulse,
                    bends if first else {},
                    fall and first, doit and first, short and first,
                    slurs=runs, ghosts=gset, orn=orn)))
        out = {}
        for label, by_bar in ordered:
            for bar, clauses in by_bar.items():
                body = "; ".join(clauses)
                seg = (label[0].upper() + label[1:] + ": " + body
                       if label else body)
                out.setdefault(bar, []).append(seg)
        DYN_WORD = {'p': 'piano', 'mp': 'mezzo piano',
                    'mf': 'mezzo forte', 'f': 'forte', 'ff': 'fortissimo'}
        for t, k in res.get('dyns', []):
            bar = at_bar + t // bar_ticks
            if bar in out:
                out[bar].insert(0, DYN_WORD[k])
        return {b: ". ".join(segs) + "." for b, segs in out.items()}

    out = _say_tl(res['timeline'], table, at_bar, bar_ticks, pulse,
                  bends, fall, doit, short,
                  slurs=res.get('slurs', ()),
                  ghosts=res.get('ghosts', ()),
                  lyrics=res.get('lyrics'), orn=orn)
    DYN_WORD = {'p': 'piano', 'mp': 'mezzo piano', 'mf': 'mezzo forte',
                'f': 'forte', 'ff': 'fortissimo'}
    for t, k in res.get('dyns', []):
        bar = at_bar + t // bar_ticks
        if bar in out:
            out[bar].insert(0, DYN_WORD[k])
    return {b: "; ".join(cl) + "." for b, cl in out.items()}
