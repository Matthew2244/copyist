#!/usr/bin/env python3
"""chartimport — bring anything a writer has into Copyist.

    chart import "Blue Rondo.mxl"
    chart import lyrics.docx --into "My Tune.chart"

One door for every file a writer is likely to be holding:

  a score      MusicXML (.musicxml, .xml) and compressed .mxl, the
               export every notation program makes. It becomes a
               chart: the band from the score's parts, sections carved
               at its rehearsal marks, its chord symbols as the
               changes, its key, meter and tempo — and every part's
               bars lifted exactly (`as engraved`), so nothing is
               retyped and nothing is guessed.
  MuseScore    .mscz / .mscx, converted through MuseScore when this
               machine has it.
  a demo       MIDI goes to the interview that already knows demos
               (`chart new --demo`).
  text         every text format (plain, Markdown, RTF, Word, OpenDoc,
               HTML, PDF, Pages): ChordPro and chord sheets become the
               form and its changes with the words kept in place, ABC
               becomes a melody with its chords, an iReal Pro link
               becomes the whole form bar by bar, and plain words
               become lyrics waiting for their tune.

What it cannot read (Sibelius, Finale, Dorico and Guitar Pro files,
audio) it says so in one sentence that names the way in — never a
traceback, never a silent nothing.

The chart it writes goes in its own folder inside Copyist Charts (the
folder-per-tune layout), with a copy of the source score beside it, and
it refuses to write over a chart that is already there.
"""
import os
import re
import shutil
import sys
import zipfile
from fractions import Fraction

import chartc

HERE = os.path.dirname(os.path.abspath(__file__))

SCORE_EXT = ('.musicxml', '.xml', '.mxl')
MIDI_EXT = ('.mid', '.midi', '.kar', '.smf')
MUSESCORE_EXT = ('.mscz', '.mscx')
AUDIO_EXT = ('.wav', '.aif', '.aiff', '.mp3', '.m4a', '.flac', '.ogg',
             '.caf', '.aac', '.opus', '.wma')
# formats whose own program has to export them first — each named with
# the menu path that does it
ASK_PROGRAM = {
    '.sib': "a Sibelius file: in Sibelius, File, Export, MusicXML, "
            "then bring that in",
    '.mus': "a Finale file: in Finale, File, Export, MusicXML, then "
            "bring that in",
    '.musx': "a Finale file: in Finale, File, Export, MusicXML, then "
             "bring that in",
    '.dorico': "a Dorico project: in Dorico, File, Export, MusicXML, "
               "then bring that in",
    '.gp': "a Guitar Pro file: in Guitar Pro, File, Export, MusicXML, "
           "then bring that in",
    '.gp3': "a Guitar Pro file: in Guitar Pro, File, Export, MusicXML, "
            "then bring that in",
    '.gp4': "a Guitar Pro file: in Guitar Pro, File, Export, MusicXML, "
            "then bring that in",
    '.gp5': "a Guitar Pro file: in Guitar Pro, File, Export, MusicXML, "
            "then bring that in",
    '.gpx': "a Guitar Pro file: in Guitar Pro, File, Export, MusicXML, "
            "then bring that in",
    '.rpp': "a REAPER project: export the MIDI items (File, Export "
            "project MIDI), then bring the .mid in",
    '.als': "an Ableton set: export the MIDI clips, then bring the "
            ".mid in",
    '.logicx': "a Logic project: File, Export, Selection as MIDI File, "
               "then bring the .mid in",
    '.band': "a GarageBand project: Share, Export Song to Disk won't "
             "carry notes — open it in Logic and export MIDI",
}


class ImportTrouble(Exception):
    """Its str is the one sentence the writer hears."""


def charts_folder():
    icloud = os.path.expanduser("~/Library/Mobile Documents/"
                                "com~apple~CloudDocs/Copyist Charts")
    if os.path.isdir(icloud):
        return icloud
    docs = os.path.expanduser("~/Documents/Copyist Charts")
    os.makedirs(docs, exist_ok=True)
    return docs


def safe_name(title):
    name = re.sub(r'[\\/:*?"<>|]+', ' ', title).strip() or 'Untitled'
    return re.sub(r'\s+', ' ', name)


def new_home(title, out_dir):
    """The new tune's own folder and chart path — never over an old one."""
    base = safe_name(title)
    folder = os.path.join(out_dir, base)
    chart = os.path.join(folder, base + '.chart')
    if os.path.exists(chart):
        raise ImportTrouble(
            f'There is already a chart called "{base}" in '
            f'{os.path.basename(out_dir)}. Rename or move it first; '
            'I will not write over a chart.')
    os.makedirs(folder, exist_ok=True)
    return folder, chart


# ------------------------------------------------------------ scores

KEY_MAJOR = {-7: 'Cb', -6: 'Gb', -5: 'Db', -4: 'Ab', -3: 'Eb', -2: 'Bb',
             -1: 'F', 0: 'C', 1: 'G', 2: 'D', 3: 'A', 4: 'E', 5: 'B',
             6: 'F#', 7: 'C#'}
KEY_MINOR = {-7: 'Abm', -6: 'Ebm', -5: 'Bbm', -4: 'Fm', -3: 'Cm',
             -2: 'Gm', -1: 'Dm', 0: 'Am', 1: 'Em', 2: 'Bm', 3: 'F#m',
             4: 'C#m', 5: 'G#m', 6: 'D#m', 7: 'A#m'}


def key_name(fifths, mode):
    table = KEY_MINOR if (mode or '').startswith('min') else KEY_MAJOR
    return table.get(fifths, 'C')


# MusicXML chord kinds -> the chart's qualities; degrees refine them
KIND = {
    'major': '', 'minor': 'm', 'augmented': 'aug', 'diminished': 'dim',
    'dominant': '7', 'major-seventh': 'maj7', 'minor-seventh': 'm7',
    'diminished-seventh': 'dim7', 'augmented-seventh': '7#5',
    'half-diminished': 'm7b5', 'major-minor': 'mmaj7',
    'major-sixth': '6', 'minor-sixth': 'm6', 'dominant-ninth': '9',
    'major-ninth': 'maj9', 'minor-ninth': 'm9', 'dominant-11th': '11',
    'minor-11th': 'm11', 'dominant-13th': '13', 'major-13th': 'maj13',
    'minor-13th': 'm13', 'suspended-second': 'sus2',
    'suspended-fourth': 'sus4', 'power': '5', 'other': '',
}
ALTER_WORD = {-1: 'b', 1: '#'}


def chord_ok(sym):
    try:
        chartc.split_chord(sym)
        return True
    except SystemExit:
        return False


def harmony_symbol(t, simplified):
    """One <harmony> -> a chord the compiler accepts. The engraver's own
    text (kind text="m7b5") is tried first, the kind plus its degrees
    second, the plain triad or seventh last — and a simplification is
    counted so the findings can say how many."""
    r = re.search(r'<root-step>(\w)</root-step>', t)
    if not r:
        return 'nc'
    a = re.search(r'<root-alter>(-?\d+)</root-alter>', t)
    root = r.group(1) + ALTER_WORD.get(int(a.group(1)) if a else 0, '')
    bs = re.search(r'<bass-step>(\w)</bass-step>', t)
    ba = re.search(r'<bass-alter>(-?\d+)</bass-alter>', t)
    bass = ('/' + bs.group(1) + ALTER_WORD.get(int(ba.group(1)) if ba
                                              else 0, '')) if bs else ''
    km = re.search(r'<kind([^>]*)>([^<]*)</kind>', t)
    kind = km.group(2).strip() if km else 'major'
    if kind == 'none':
        return 'nc'
    text = re.search(r'text="([^"]*)"', km.group(1)) if km else None
    q = KIND.get(kind, '')
    alts = ''
    for dv, da, dt in re.findall(
            r'<degree-value>(\d+)</degree-value>\s*'
            r'<degree-alter>(-?\d+)</degree-alter>\s*'
            r'<degree-type[^>]*>(\w+)</degree-type>', t):
        if dt in ('add', 'alter') and int(da):
            alts += ALTER_WORD.get(int(da), '') + dv
        elif dt == 'add' and dv == '9' and q in ('', '6', 'm', 'm6'):
            q = {'': 'add9', '6': '69', 'm': 'madd9', 'm6': 'm69'}[q]
        elif dt == 'add' and dv == '4' and q == '7':
            q = '7sus4'
    text_q = ''
    if text and text.group(1).strip():
        text_q = (text.group(1).strip().replace('Δ', 'maj')
                  .replace('ø', 'm7b5').replace('°', 'dim')
                  .replace('−', 'm'))
    # the engraver's text first, but WITH the degrees it stores apart:
    # a text of "13" and a flat nine as a degree is Ab13b9, not Ab13
    # (checked against a reference Bolivia: every alteration was being
    # dropped that way)
    tries = []
    if alts:
        tries += [text_q + alts] if text_q else []
        tries.append(q + alts)
    tries += [text_q] if text_q else []
    tries.append(q)
    for i, qual in enumerate(tries):
        for with_bass in (True, False):
            sym = root + qual + (bass if with_bass else '')
            if chord_ok(sym):
                lost = (alts and not qual.endswith(alts)) or (
                    i == len(tries) - 1 and len(tries) > 1
                    and tries[0] != qual)
                if lost or not with_bass and bass:
                    simplified.append(root + tries[0] + bass)
                return sym
    simplified.append(root + (tries[0] if tries else '') + bass)
    return root + ('m' if q.startswith('m') and not q.startswith('maj')
                   else '')


def resolve_instrument(name, sound, transpose, staves, perc, clef):
    """A score's part name -> one of Copyist's instruments, or a stand-in
    at the same pitch with a finding. Never a guess that would move a
    note: an unknown transposing instrument is refused, not respelled."""
    n = name.lower()
    n = re.sub(r'\bin\s+[a-g][b#♭♯]?\b', ' ', n)
    n = re.sub(r'\b(saxophone)\b', 'sax', n)
    n = re.sub(r'\b(\d+|i{1,3}|iv|v|vi{0,3}|solo|1st|2nd|3rd|4th)\b',
               ' ', n)
    n = re.sub(r'[^a-z\- ]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    n = re.sub(r's$', '', n) if n.endswith(('violins', 'violas',
                                            'cellos', 'flutes',
                                            'trumpets', 'trombones',
                                            'horns', 'clarinets',
                                            'oboes')) else n
    cands = [n, n.replace('acoustic ', ''), n.replace('electric ', ''),
             ' '.join(n.split()[-2:]), n.split()[-1] if n else '']
    for c in cands:
        c = chartc.canonical_instrument(c)
        if c in chartc.HORNS:
            return c, None
    if sound:
        tail = sound.split('.')[-1].replace('-', ' ')
        c = chartc.canonical_instrument(tail)
        if c in chartc.HORNS:
            return c, None
    # a bare "Alto" or "Tenor" in a band score is a saxophone, and the
    # part's own transposition says which instrument it is
    by_transpose = {-2: ('trumpet', 'clarinet', 'soprano sax'),
                    -9: ('alto sax',), -14: ('tenor sax',),
                    -21: ('baritone sax',), -7: ('french horn',),
                    -3: ('eb clarinet',), -5: ('alto flute',)}
    for c in by_transpose.get(transpose, ()):
        if not n or any(w in c for w in n.split()) or \
                len(by_transpose[transpose]) == 1:
            return c, (None if n and any(w in c for w in n.split())
                       else f'"{name}" read as {c} from its transposition')
    if perc:
        return ('drums' if re.search(r'drum|kit', n) else 'percussion',
                f'"{name}" read as {"drums" if "drum" in n else "percussion"}')
    if transpose:
        return None, (f'"{name}" is a transposing instrument Copyist does '
                      'not know yet, so it was left out rather than '
                      'printed at the wrong pitch')
    if staves > 1:
        return 'piano', f'"{name}" printed as piano, the same pitch'
    stand = {'F': 'cello', 'C': 'viola'}.get(clef, 'flute')
    return stand, (f'"{name}" is not in Copyist\'s instrument list, so '
                   f'it prints as {stand}, the same pitch; change its '
                   'band line to taste')


def read_mxl(path):
    """A compressed MusicXML: its container names the real score."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ImportTrouble(f"{os.path.basename(path)} is marked "
                            "compressed MusicXML but is not a zip file.")
    root = None
    if 'META-INF/container.xml' in z.namelist():
        c = z.read('META-INF/container.xml').decode('utf-8', 'replace')
        m = re.search(r'full-path="([^"]+)"', c)
        root = m.group(1) if m else None
    if not root:
        xs = [n for n in z.namelist() if n.endswith(('.xml', '.musicxml'))
              and not n.startswith('META-INF')]
        root = xs[0] if xs else None
    if not root:
        raise ImportTrouble(f"{os.path.basename(path)} holds no score.")
    return z.read(root).decode('utf-8', 'replace')


def score_to_chart(xml, score_file, title_hint):
    """MusicXML text -> (chart text, title, findings)."""
    xml = re.sub(r'\s+/>', '/>', xml)
    if '<score-timewise' in xml:
        raise ImportTrouble("This score is written time-wise, the rare "
                            "MusicXML shape; export it part-wise from "
                            "its program.")
    find = []

    import html

    def one(rx, text=xml):
        m = re.search(rx, text, re.S)
        return html.unescape(m.group(1)).strip() if m else ''
    title = (one(r'<work-title>([^<]*)</work-title>')
             or one(r'<movement-title>([^<]*)</movement-title>')
             or title_hint)
    # one line, no quote marks: a title spanning lines broke the header
    title = re.sub(r'\s+', ' ', title.replace('"', '')).strip() or \
        title_hint
    def credit(kind):
        # a credit spanning lines, or a template's "[Arranger]" left in
        lines_ = [re.sub(r'\s+', ' ', ln).strip() for ln in
                  one(r'<creator type="%s">([^<]*)</creator>' % kind)
                  .splitlines()]
        return [ln for ln in lines_ if ln and not re.fullmatch(
            r'\[[^\]]*\]|(arranged|composed|words|music)( by)?:?\s*'
            r'\[?[^\]]*\]?', ln, re.I) or not ln.startswith(('[',))]
    comp = credit('composer')
    arranger = " ".join(credit('arranger'))
    for ln in list(comp):
        if re.match(r'(arr\.?|arranged by|arr:)\s*', ln, re.I):
            comp.remove(ln)
            arranger = arranger or re.sub(r'^(arr\.?|arranged by|arr:)'
                                          r'\s*', '', ln, flags=re.I)
    composer = " ".join(comp)
    arranger = re.sub(r'^(arr\.?|arranged by|arr:)\s*', '', arranger,
                      flags=re.I)
    if re.search(r'\[[^\]]*\]', arranger):
        arranger = ''
    if re.search(r'\[[^\]]*\]', composer):
        composer = ''
    lyricist = " ".join(credit('lyricist'))

    order = re.findall(r'<score-part id="([^"]+)"', xml)
    if not order:
        raise ImportTrouble("This file has no parts in it — it may be "
                            "a MusicXML fragment rather than a score.")
    bodies, meta = {}, {}
    for pid in order:
        sp = re.search(r'<score-part id="%s">(.*?)</score-part>'
                       % re.escape(pid), xml, re.S).group(1)
        b = re.search(r'<part id="%s">(.*?)</part>' % re.escape(pid),
                      xml, re.S)
        if not b:
            continue
        bodies[pid] = b.group(1)
        pname = chartc.source_part_name(xml, pid)
        meta[pid] = {
            'name': pname,
            'sound': one(r'<instrument-sound>([^<]*)</instrument-sound>',
                         sp),
            'perc': bool(re.search(r'<midi-unpitched>|<midi-channel>10<',
                                   sp)),
        }
    # the form (measure numbers, meters, keys) is read from a part at
    # concert pitch: an alto's written D major is a chart in F
    def transposition(b_):
        tr_ = re.search(r'<chromatic>(-?\d+)</chromatic>', b_)
        return int(tr_.group(1)) if tr_ else 0
    concert = [p_ for p_ in order if p_ in bodies
               and transposition(bodies[p_]) == 0
               and '<sign>percussion' not in bodies[p_]]
    form_pid = concert[0] if concert else order[0]
    first = bodies[form_pid]
    shift = transposition(first)
    measures = re.findall(r'<measure ([^>]*)>(.*?)</measure>', first,
                          re.S)
    nums, pickup_q = [], None
    div, meter, fifths, mode = 1, (4, 4), 0, 'major'
    meter0 = (4, 4)
    events = []                     # (index, kind, value)
    tempo = None
    for i, (attrs, m) in enumerate(measures):
        num = re.search(r'number="([^"]+)"', attrs).group(1)
        nums.append(num)
        dv = re.search(r'<divisions>(\d+)</divisions>', m)
        if dv:
            div = int(dv.group(1))
        ts = re.search(r'<beats>(\d+)</beats>\s*<beat-type>(\d+)'
                       r'</beat-type>', m)
        if ts:
            new = (int(ts.group(1)), int(ts.group(2)))
            if i and new != meter:
                events.append((i, 'meter', f"{new[0]}/{new[1]}"))
            meter = new if i == 0 or new != meter else meter
            if i == 0:
                meter0 = new
        kf = re.search(r'<fifths>(-?\d+)</fifths>', m)
        if kf:
            md = re.search(r'<mode>(\w+)</mode>', m)
            nk = (int(kf.group(1)), md.group(1) if md else 'major')
            if i == 0:
                fifths, mode = nk
            elif nk != (fifths, mode):
                events.append((i, 'key', key_name(*nk)))
                fifths, mode = nk
        if tempo is None:
            tm = re.search(r'<sound[^>]*tempo="([\d.]+)"', m) or \
                re.search(r'<per-minute>([\d.]+)</per-minute>', m)
            if tm:
                tempo = round(float(tm.group(1)))
        if i == 0:
            # a pickup only if the bar is really short — some programs
            # number a full opening bar 0. Measured across every part:
            # the furthest any part reaches is the bar's true length.
            reach = 0
            for b_ in bodies.values():
                m0 = re.search(r'<measure [^>]*>(.*?)</measure>', b_, re.S)
                reach = max(reach, bar_reach(m0.group(1)) if m0 else 0)
            full = div * 4 * meter0[0] // meter0[1]
            if 0 < reach < full:
                pickup_q = Fraction(reach, div)
    body_nums = nums[1:] if pickup_q is not None else nums
    if not body_nums:
        raise ImportTrouble("This score has no measures to lift.")
    if not all(re.fullmatch(r'\d+', n) for n in body_nums):
        odd = [n for n in body_nums if not re.fullmatch(r'\d+', n)][:3]
        raise ImportTrouble(
            "This score numbers some bars with letters (" + ", ".join(odd)
            + "), which Copyist lifts by number; renumber the bars in "
            "its program and export again.")

    # rehearsal marks, from whichever part carries them first
    marks = {}
    for pid in order:
        for i, (attrs, m) in enumerate(re.findall(
                r'<measure ([^>]*)>(.*?)</measure>', bodies[pid], re.S)):
            for rh in re.findall(r'<rehearsal[^>]*>([^<]+)</rehearsal>', m):
                marks.setdefault(i, html.unescape(rh).strip())
        if marks:
            break
    if not marks:
        # no rehearsal marks: a section's name written as words at the
        # top of a bar ("Intro", "verse after chorus", "vamp 1") is a
        # rehearsal mark by another name
        SECTION_WORD = re.compile(
            r'^(intro|verse|pre-?chorus|chorus|bridge|vamp|solos?|head|'
            r'outro|coda|interlude|shout|send-?off|tag|ending|break|'
            r'a section|b section|letter [a-z])\b', re.I)
        # from whichever part carries them: the alto's page, not the
        # concert trombone the key was read from
        for pid in order:
            for i, (attrs, m) in enumerate(re.findall(
                    r'<measure ([^>]*)>(.*?)</measure>', bodies[pid],
                    re.S)):
                head = re.split(r'<note[ >]', m, maxsplit=1)[0]
                for w in re.findall(r'<words[^>]*>([^<]+)</words>', head):
                    w = html.unescape(w).strip()
                    if SECTION_WORD.match(w) and len(w) <= 24:
                        marks.setdefault(i, w)
            if marks:
                break
    # the chords: the part that carries the most symbols
    hp = max(order, key=lambda p: bodies[p].count('<harmony'))
    simplified = []
    bar_chords = {}
    if bodies[hp].count('<harmony'):
        hdiv = 1
        hmeter = meter0
        for i, (attrs, m) in enumerate(re.findall(
                r'<measure ([^>]*)>(.*?)</measure>', bodies[hp], re.S)):
            dv = re.search(r'<divisions>(\d+)</divisions>', m)
            if dv:
                hdiv = int(dv.group(1))
            ts = re.search(r'<beats>(\d+)</beats>\s*<beat-type>(\d+)',
                           m)
            if ts:
                hmeter = (int(ts.group(1)), int(ts.group(2)))
            pos, got = 0, []
            for el in re.finditer(r'<(harmony|note|backup|forward)'
                                  r'[ >].*?</\1>', m, re.S):
                t = el.group(0)
                if t.startswith('<harmony'):
                    off = re.search(r'<offset>(-?\d+)</offset>', t)
                    p = pos + (int(off.group(1)) if off else 0)
                    unit = hdiv * 4 / hmeter[1]
                    beat = round((p / unit) * 2) / 2 + 1
                    if all(b != beat for b, _ in got):
                        # two chord layers (a second staff, a second
                        # voice) name the same beat twice: first wins
                        got.append((beat, harmony_symbol(t, simplified)))
                    continue
                d = re.search(r'<duration>(\d+)</duration>', t)
                d = int(d.group(1)) if d else 0
                if t.startswith('<backup'):
                    pos -= d
                elif t.startswith('<forward') or (
                        '<chord/>' not in t and '<grace' not in t):
                    pos += d
            if got:
                bar_chords[i] = sorted(got)

    # parts -> the band
    band, used = [], set()
    for pid in order:
        mt = meta[pid]
        b0 = bodies[pid]
        if not re.search(r'<pitch>|<unpitched', b0):
            # a staff of nothing but rests (Sibelius leaves unnamed
            # empty ones) is no one's chair
            find.append(f'"{mt["name"]}" has no notes in it, so it was '
                        'left out of the band')
            continue
        tr = re.search(r'<chromatic>(-?\d+)</chromatic>', b0)
        stv = re.search(r'<staves>(\d+)</staves>', b0)
        cl = re.search(r'<sign>(\w+)</sign>', b0)
        inst, note = resolve_instrument(
            mt['name'], mt['sound'], int(tr.group(1)) if tr else 0,
            int(stv.group(1)) if stv else 1,
            mt['perc'] or (cl and cl.group(1) == 'percussion'),
            cl.group(1) if cl else 'G')
        if note:
            find.append(note)
        if not inst:
            continue
        label = re.sub(r'[^\w ]', ' ', mt['name']).lower()
        label = re.sub(r'^[\d_ ]+', '', label)     # a label starts
        label = re.sub(r'\s+', ' ', label).strip()  # with a word
        label = label or inst
        base, k = label, 2
        while label in used:
            label, k = f"{base} {k}", k + 1
        used.add(label)
        # the compiler lifts by matching this label to the score's own
        # part name; make sure it will find exactly this part
        src_names = [chartc.source_part_name(xml, q) for q in order]
        mine = src_names[order.index(pid)]
        ok = False
        for cand in (label, re.sub(r'\s+', ' ', re.sub(
                r'[^\w ]', ' ', mine.lower())).strip()):
            try:
                if cand and chartc.match_part(cand, src_names) == mine:
                    label, ok = cand, True
                    break
            except SystemExit:
                pass
        if not ok:
            find.append(f'"{mt["name"] or pid}" could not be told apart '
                        'from another part by name, so it was left out; '
                        'rename one in the score and import again')
            continue
        band.append((label, inst))
    if not band:
        raise ImportTrouble("None of this score's parts is an "
                            "instrument Copyist can print yet.")

    # sections: at each rehearsal mark, else one section
    # the same section word written again and again ("vamp 2" over every
    # two bars, a reminder) is one section continuing, not new ones
    last_word = None
    for i in sorted(marks):
        if marks[i].lower() == (last_word or '').lower():
            del marks[i]
        else:
            last_word = marks[i]
    start = 1 if pickup_q is not None else 0
    cuts = sorted(i for i in marks if i >= start) or [start]
    if cuts[0] != start:
        cuts.insert(0, start)
    names, sections = set(), []
    for si, c0 in enumerate(cuts):
        c1 = cuts[si + 1] if si + 1 < len(cuts) else len(measures)
        raw = marks.get(c0) or ('A' if si == 0 else chr(65 + si % 26))
        name = raw if len(raw) <= 24 else chr(65 + si % 26)
        name = re.sub(r'[^\w ]', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip() or 'A'
        base, k = name, 2
        while name.lower() in names:
            # a second "chorus" is "chorus 2"; a second "vamp 2" is
            # "vamp 2 again" — never a number that reads as the first
            name = (f"{base} again" + (f" {k - 1}" if k > 2 else "")
                    if base[-1].isdigit() else f"{base} {k}")
            k += 1
        names.add(name.lower())
        # an excerpt's numbering can jump (14, then 196): one lift
        # covers one unbroken run, so the section splits at the jump
        run0 = c0
        for j in range(c0 + 1, c1):
            if int(nums[j]) != int(nums[j - 1]) + 1:
                sections.append((name if run0 == c0 else
                                 f"{name} from {nums[run0]}", run0, j))
                run0 = j
        sections.append((name if run0 == c0 else
                         f"{name} from {nums[run0]}", run0, c1))

    def chord_bar(i, prev):
        if i not in bar_chords:
            return (prev or 'nc'), prev
        toks = []
        for beat, sym in bar_chords[i]:
            if toks and sym == prev:
                continue                # the same chord named again
            if beat <= 1.0 and not toks:
                toks.append(sym)
            else:
                b = int(beat) if beat == int(beat) else f"{int(beat)}+"
                toks.append(f"{sym}@{b}")
            prev = sym
        if not toks[0].split('@')[0] or '@' in toks[0]:
            toks.insert(0, prev if prev else 'nc')
        return " ".join(toks), prev

    lines = [f"# Imported by Copyist from {os.path.basename(score_file)}.",
             "# Every part's bars are lifted exactly from that score; the",
             "# form, chords and band below are yours to reshape.", "",
             f"title: {title}"]
    if composer:
        lines.append(f"composer: {composer}")
    if arranger:
        lines.append(f"arranger: {arranger}")
    if lyricist:
        lines.append(f"# words: {lyricist}")
    kf0, km0 = first_key(first)
    if shift:
        # written fifths -> concert: each semitone of transposition is
        # seven fifths around the circle
        kf0 = ((kf0 + shift * 7 + 6) % 12) - 6
    lines.append(f"key: {key_name(kf0, km0)}")
    lines.append(f"meter: {meter0[0]}/{meter0[1]}")
    if tempo:
        lines.append(f"tempo: {tempo}")
    lines.append(f'source: "{os.path.basename(score_file)}"')
    lines += ["", "band:"]
    for label, inst in band:
        lines.append(f"  {label}" if label == inst else
                     f"  {label} = {inst}")
    lines.append("")
    if pickup_q is not None:
        beats = pickup_q * meter0[1] / 4
        bw = int(beats) if beats == int(beats) else float(beats)
        lines += [f"pickup {bw} beats, as engraved", ""]
    prev = None
    for name, c0, c1 in sections:
        n = c1 - c0
        chords = []
        for i in range(c0, c1):
            cb, prev = chord_bar(i, prev)
            chords.append(cb)
        lo, hi = nums[c0], nums[c1 - 1]
        lines.append(f"section {name}, {n} bars")
        lines.append("  chords: " + ", ".join(chords))
        for i, kind, val in events:
            if c0 <= i < c1:
                lines.append(f"  at bar {i - c0 + 1}: {kind} {val}")
        lines.append(f"  all: as engraved bars {lo}-{hi}")
        lines.append("")
    if simplified:
        uniq = list(dict.fromkeys(simplified))
        find.append(f"{len(uniq)} chord spelling(s) simplified to one "
                    "Copyist reads: " + ", ".join(uniq[:6])
                    + (" and more" if len(uniq) > 6 else ""))
    if not bar_chords:
        find.append("the score has no chord symbols, so every bar reads "
                    "N.C.; the parts are exact either way")
    # a bar the score itself leaves short or long (a rounding slip in
    # the program that wrote it) is named here, so the check that finds
    # it later is not mistaken for Copyist's own fault
    flaws = []
    for pid in order:
        dvv, mtr = 1, meter0
        for i, (attrs, m) in enumerate(re.findall(
                r'<measure ([^>]*)>(.*?)</measure>', bodies[pid], re.S)):
            dv = re.search(r'<divisions>(\d+)</divisions>', m)
            if dv:
                dvv = int(dv.group(1))
            ts = re.search(r'<beats>(\d+)</beats>\s*<beat-type>(\d+)', m)
            if ts:
                mtr = (int(ts.group(1)), int(ts.group(2)))
            if i == 0 and pickup_q is not None:
                continue
            reach = bar_reach(m)
            want = dvv * 4 * mtr[0] // mtr[1]
            if reach and reach != want:
                bar_no = re.search(r'number="([^"]+)"', attrs)
                flaws.append(f"{meta[pid]['name'] or pid} bar "
                             f"{bar_no.group(1) if bar_no else i + 1}")
    if flaws:
        find.append("the score itself has bars that do not add up ("
                    + ", ".join(flaws[:4])
                    + (" and more" if len(flaws) > 4 else "")
                    + "), a slip in the program that wrote it; the check "
                    "will name them too, and fixing them there fixes them "
                    "here")
    find.insert(0, f"{len(band)} part(s), {len(sections)} section(s), "
                f"{len(body_nums)} bars"
                + (", a pickup" if pickup_q is not None else ""))
    return "\n".join(lines) + "\n", title, find


def bar_reach(m):
    """How far a bar's notes reach, in its own divisions: walking in
    order, backups included, the furthest point wins."""
    pos = reach = 0
    for el in re.finditer(r'<(note|backup|forward)[ >](.*?)</\1>', m, re.S):
        d = re.search(r'<duration>(\d+)</duration>', el.group(2))
        d = int(d.group(1)) if d else 0
        if el.group(1) == 'backup':
            pos -= d
        elif el.group(1) == 'forward' or not (
                '<chord/>' in el.group(2) or '<grace' in el.group(2)):
            pos += d
        reach = max(reach, pos)
    return reach


def first_key(body):
    kf = re.search(r'<fifths>(-?\d+)</fifths>', body)
    md = re.search(r'<mode>(\w+)</mode>', body)
    return (int(kf.group(1)) if kf else 0, md.group(1) if md else 'major')


def bodies_transposed(body):
    # the first part's key changes are concert only when it does not
    # transpose; a Bb part's written key is not the chart's key
    return bool(re.search(r'<chromatic>-?[1-9]', body))


def import_score(path, out_dir, say):
    ext = os.path.splitext(path)[1].lower()
    xml = read_mxl(path) if ext == '.mxl' else \
        open(path, encoding='utf-8', errors='replace').read()
    if '<score-partwise' not in xml and '<score-timewise' not in xml:
        raise ImportTrouble(f"{os.path.basename(path)} is XML but not a "
                            "MusicXML score.")
    hint = os.path.splitext(os.path.basename(path))[0]
    text, title, find = score_to_chart(xml, path, hint)
    try:
        folder, chart = new_home(title, out_dir)
    except ImportTrouble:
        # another version of this tune is already in: this file's own
        # name tells the two apart (Yardbird Suite, Yardbird Suite8)
        name = hint if safe_name(hint) != safe_name(title) else None
        k = 2
        while True:
            cand = name or f"{safe_name(title)} {k}"
            try:
                folder, chart = new_home(cand, out_dir)
                break
            except ImportTrouble:
                name, k = None, k + 1
                if k > 50:
                    raise
        find.append(f'a chart called "{safe_name(title)}" was already '
                    f'there, so this one is named "{safe_name(cand)}"')
    src_name = safe_name(title) + " (source).musicxml"
    with open(os.path.join(folder, src_name), 'w', encoding='utf-8') as f:
        f.write(xml)
    text = text.replace(f'source: "{os.path.basename(path)}"',
                        f'source: "{src_name}"')
    with open(chart, 'w', encoding='utf-8') as f:
        f.write(text)
    return chart, find


# ------------------------------------------------------------- text

DUR_LETTERS = [(96, 'w'), (72, 'h.'), (48, 'h'), (36, 'q.'), (24, 'q'),
               (18, 'e.'), (12, 'e'), (9, 's.'), (6, 's')]


def ticks_to_notes(ticks):
    """Ticks (24 a quarter) -> 'q+e' style, or None if not writable."""
    out, left = [], ticks
    for t, w in DUR_LETTERS:
        while left >= t:
            out.append(w)
            left -= t
    return "+".join(out) if not left and out else None


def melody_notes(notes):
    """[(Fraction quarters, midi or None)] -> the notes: grammar, with
    triplet groups where three notes fill a beat in thirds."""
    names = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb',
             'B']
    out, i, pos = [], 0, Fraction(0)

    def name(m):
        return f"{names[m % 12]}{m // 12 - 1}"
    while i < len(notes):
        q, m = notes[i]
        tk = q * 24
        if tk.denominator != 1 or int(tk) % 6:
            grp = notes[i:i + 3]
            if (len(grp) == 3 and pos.denominator == 1
                    and all(g[0] == grp[0][0] for g in grp)
                    and grp[0][0] in (Fraction(1, 3), Fraction(1, 6))):
                letter = 'e' if grp[0][0] == Fraction(1, 3) else 's'
                items = [(f"{name(g[1])} {letter}" if g[1] is not None
                          else f"rest {letter}") for g in grp]
                out.append("triplet( " + ", ".join(items) + " )")
                pos += sum(g[0] for g in grp)
                i += 3
                continue
            return None
        d = ticks_to_notes(int(tk))
        if d is None:
            return None
        out.append(f"{name(m)} {d}" if m is not None else f"rest {d}")
        pos += q
        i += 1
    return ", ".join(out)


def song_to_chart(song, source_name):
    """A song from textformats -> (chart text, title, findings, words
    only?)."""
    find = list(song.get('findings') or [])
    title = song.get('title') or 'Untitled'
    meter = song.get('meter') or (4, 4)
    lines = [f"# Imported by Copyist from {source_name}.",
             "# The form, chords and band below are a starting point;",
             "# say the real bar lengths and the band at the editing desk.",
             "", f"title: {title}"]
    if song.get('composer'):
        lines.append(f"composer: {song['composer']}")
    if song.get('key'):
        lines.append(f"key: {song['key']}")
    lines.append(f"meter: {meter[0]}/{meter[1]}")
    if song.get('tempo'):
        lines.append(f"tempo: {song['tempo']}")
    if song.get('style'):
        lines.append(f"feel: {song['style']}")
    has_words = any(s.get('words') for s in song['sections'])
    mel = song.get('melody')
    has_bars = any(s.get('bars') for s in song['sections'])
    lines += ["", "band:"]
    if mel:
        lines.append("  melody = voice" if mel.get('lyrics')
                     else "  melody = flute")
    elif has_words:
        lines.append("  voice")
    lines += ["  piano", "  bass = double bass", "  drums", ""]
    if mel and has_bars:
        figtxt = melody_notes(mel['notes'])
        nbars = sum(len(s['bars']) for s in song['sections'])
        pick = mel.get('pickup_quarters')
        if figtxt and not pick:
            lines += [f"figure melody, {nbars} bars:", "  notes: " + figtxt]
            if mel.get('lyrics'):
                lines.append("  lyrics: " + re.sub(r'\s+', ' ',
                                                   mel['lyrics']).strip())
            lines.append("")
        else:
            find.append("the melody has a rhythm the notes: line cannot "
                        "hold yet (or a pickup), so it was left out; the "
                        "form and chords came in")
            mel = None
    if not has_bars:
        # words with no tune yet: they wait in the chart for their form
        for s in song['sections']:
            lines.append(f"# {s['name']}:")
            for w in (s.get('words') or '').splitlines():
                lines.append(f"#   {w}")
            lines.append("")
        find.append("words only, so the chart has no form yet; open it "
                    "and tell me the tune, and the words are waiting "
                    "beside each section")
        return "\n".join(lines) + "\n", title, find, True
    first = True
    for s in song['sections']:
        if not s.get('bars'):
            continue
        name = re.sub(r'[,"]', ' ', s['name']).strip() or 'A'
        bars = []
        for bar in s['bars']:
            toks = []
            for beat, sym in bar:
                if beat and beat != 1:
                    b = int(beat) if beat == int(beat) else \
                        f"{int(beat)}+"
                    toks.append(f"{sym}@{b}")
                else:
                    toks.append(sym)
            bars.append(" ".join(toks) or 'nc')
        lines.append(f"section {name}, {len(bars)} bars")
        lines.append("  chords: " + ", ".join(bars))
        if mel and first:
            lines.append("  melody: figure melody")
        first = False
        for w in (s.get('words') or '').splitlines():
            if w.strip():
                lines.append(f"  # {w.strip()}")
        lines.append("")
    return "\n".join(lines) + "\n", title, find, False


def import_text(path, out_dir, say, into=None):
    try:
        import textformats
    except ImportError:
        raise ImportTrouble("Text import is not installed in this copy "
                            "of Copyist yet.")
    try:
        text, how = textformats.read_text(path)
        song = textformats.parse_song(
            text, os.path.splitext(os.path.basename(path))[0])
    except textformats.ImportTrouble as e:
        raise ImportTrouble(str(e))
    if song.get('kind') == 'empty':
        raise ImportTrouble(f"{os.path.basename(path)} has no words or "
                            "music in it that I can find.")
    if into:
        return add_words(into, song, path)
    text_out, title, find, _words = song_to_chart(
        song, os.path.basename(path))
    folder, chart = new_home(title, out_dir)
    with open(chart, 'w', encoding='utf-8') as f:
        f.write(text_out)
    find.insert(0, f"read {how}: {describe_kind(song['kind'])}")
    return chart, find


def describe_kind(kind):
    return {'ireal': 'an iReal Pro chart', 'abc': 'ABC notation',
            'chordpro': 'a ChordPro song', 'chordsheet':
            'a chord sheet', 'lyrics': 'lyrics'}.get(kind, kind)


def add_words(chart, song, path):
    """Words into an existing chart: each stanza under the section of
    the same name when there is one, the rest at the end — as comments,
    so nothing printed changes until the writer places them."""
    text = open(chart, encoding='utf-8').read()
    placed, left = 0, []
    for s in song['sections']:
        w = (s.get('words') or '').strip()
        if not w:
            continue
        block = "".join(f"  # {ln.strip()}\n" for ln in w.splitlines()
                        if ln.strip())
        m = re.search(r'^section %s,[^\n]*\n' % re.escape(s['name']),
                      text, re.M | re.I)
        if m:
            text = text[:m.end()] + block + text[m.end():]
            placed += 1
        else:
            left.append(f"# {s['name']}:\n" + block.replace("  #", "#"))
    if left:
        text = text.rstrip() + "\n\n# words from " + \
            os.path.basename(path) + "\n" + "".join(left)
    with open(chart, 'w', encoding='utf-8') as f:
        f.write(text)
    return chart, [f"words from {os.path.basename(path)}: {placed} "
                   "stanza(s) under their sections, "
                   f"{len(left)} at the end of the chart, as comments"]


# ------------------------------------------------------------ doors

def import_file(path, out_dir=None, say=print, into=None):
    """Any file -> (chart path or None, sentences). MIDI returns
    ('interview', path): the caller runs the demo interview."""
    if not os.path.exists(path):
        raise ImportTrouble(f"I can't find {path}.")
    out_dir = out_dir or charts_folder()
    ext = os.path.splitext(path)[1].lower()
    if os.path.isdir(path) and not ext == '.rtfd':
        raise ImportTrouble("That is a folder; bring in one file at a "
                            "time.")
    if ext in ASK_PROGRAM:
        raise ImportTrouble(f"That is {ASK_PROGRAM[ext]}.")
    if ext in AUDIO_EXT:
        raise ImportTrouble(
            "That is audio. Copyist cannot hear notes out of a recording "
            "yet; play the part into your DAW and bring in the MIDI, or "
            "export stems as MIDI if your DAW can.")
    if ext in MIDI_EXT:
        return 'interview', []
    if ext in MUSESCORE_EXT:
        return import_musescore(path, out_dir, say)
    if ext in SCORE_EXT:
        if ext == '.xml':
            head = open(path, encoding='utf-8', errors='replace').read(4000)
            if '<score-' not in head:
                return import_text(path, out_dir, say, into)
        return import_score(path, out_dir, say)
    if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.heic', '.gif'):
        raise ImportTrouble("That is a picture. Copyist cannot read "
                            "notes from an image yet; a MusicXML export "
                            "of the score is the way in.")
    return import_text(path, out_dir, say, into)


def import_musescore(path, out_dir, say):
    import subprocess
    import tempfile
    sys.path.insert(0, HERE)
    try:
        from chart import find_mscore
        ms = find_mscore()
    except Exception:
        ms = None
    if not ms:
        raise ImportTrouble("That is a MuseScore file. In MuseScore, "
                            "File, Export, MusicXML, then bring that in.")
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0]
                       + '.musicxml')
    subprocess.run([ms, '-o', out, path], capture_output=True, timeout=180)
    if not os.path.exists(out):          # judge by the file, never the
        raise ImportTrouble(             # exit code: it crashes after
            "MuseScore could not export that file; open it in "  # writing
            "MuseScore and export MusicXML by hand.")
    try:
        return import_score(out, out_dir, say)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(
        prog="chart import",
        description="Bring a score, a demo or any text into Copyist.")
    ap.add_argument('file', help="the file to bring in")
    ap.add_argument('--into', help="add words to this existing chart")
    ap.add_argument('--to', help="where the new tune's folder goes "
                                 "(default: Copyist Charts)")
    a = ap.parse_args(argv)
    try:
        chart, find = import_file(a.file, a.to, into=a.into)
    except ImportTrouble as e:
        print(str(e))
        return 1
    if chart == 'interview':
        print("That is a MIDI demo; the interview takes it from here.")
        return 3
    print(f"Imported. The chart is {chart}.")
    for s in find:
        print(s[0].upper() + s[1:] + ".")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
