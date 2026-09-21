#!/usr/bin/env python3
"""chart — one command from a .chart file to everything a writer needs.

    chart.py <file.chart>                the whole pass: check, build,
                                         pages, the listen file, read-alouds
    chart.py <file.chart> check          compile and report, render nothing
    chart.py <file.chart> read           the form, spoken
    chart.py <file.chart> read --part X  one player's part, spoken
    chart.py <file.chart> parts          list the band

Built for ears first: one line per thing done, every failure in a
sentence that names the fix, and success measured by the files that
exist — never by an exit code (MuseScore's CLI crashes after writing,
and sometimes instead of it).
"""
import argparse
import glob
import os
import re
import subprocess
import sys

import chartaudio
import chartc
import chartengrave
import chartdemo
import chartread


def verify_measures(files):
    """Every measure must sum to exactly one bar — the classic silent
    failure of note emission. Returns a list of one-sentence problems."""
    bad = []
    for f in files:
        if not f.endswith('.musicxml'):
            continue
        xml = open(f, encoding='utf-8').read()
        for pid, body in re.findall(r'<part id="([^"]+)">(.*?)</part>',
                                    xml, re.S):
            div = 24
            tnum, tden = 4, 4
            for num, m in re.findall(
                    r'<measure [^>]*?number="([^"]+)"[^>]*>(.*?)</measure>',
                    body, re.S):
                dv = re.search(r'<divisions>(\d+)</divisions>', m)
                if dv:
                    div = int(dv.group(1))
                ts = re.search(r'<beats>(\d+)</beats>\s*'
                               r'<beat-type>(\d+)</beat-type>', m)
                if ts:
                    tnum, tden = int(ts.group(1)), int(ts.group(2))
                if num == '0':
                    continue               # a pickup is partial on purpose
                expect = div * 4 * tnum // tden
                total = 0
                for note in re.findall(r'<note[ >](.*?)</note>', m, re.S):
                    if '<chord/>' in note or '<grace' in note:
                        continue
                    d = re.search(r'<duration>(\d+)</duration>', note)
                    if d:
                        total += int(d.group(1))
                for bk in re.findall(
                        r'<backup>\s*<duration>(\d+)</duration>', m):
                    total -= int(bk)
                for fw in re.findall(
                        r'<forward>\s*<duration>(\d+)</duration>', m):
                    total += int(fw)
                if total not in (0, expect):
                    bad.append(f"{os.path.basename(f)}, part {pid}, "
                               f"bar {num}: {total} of {expect} ticks")
    return bad


def parse_readaloud(path):
    """A read-aloud file -> ({bar_number: line}, [every other line])."""
    bars, other = {}, []
    if not os.path.exists(path):
        return None
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'Bar (\d+): (.*)$', line)
        if m:
            bars[int(m.group(1))] = m.group(2)
        else:
            other.append(line)
    return bars, other


def diff_readalouds(prev_dir, cur_dir, title, labels):
    """Compare the previous build's read-alouds with the current ones.
    Returns (sentences, had_previous). Spoken style: the writer's own
    bar numbers, was/now, and an explicit all-clear."""
    out = []
    had_prev = False
    for label in labels:
        name = f"{title} — {label} part, read aloud.txt"
        old = parse_readaloud(os.path.join(prev_dir, name))
        new = parse_readaloud(os.path.join(cur_dir, name))
        if old is None or new is None:
            continue
        had_prev = True
        ob, oo = old
        nb, no = new
        for bar in sorted(set(ob) | set(nb)):
            if bar not in nb:
                out.append(f"{label}, bar {bar} — the written material "
                           f"is gone. Was: {ob[bar]}")
            elif bar not in ob:
                out.append(f"{label}, bar {bar} — new material: {nb[bar]}")
            elif ob[bar] != nb[bar]:
                out.append(f"{label}, bar {bar} — was: {ob[bar]} "
                           f"Now: {nb[bar]}")
        if oo != no:
            import difflib
            for d in difflib.unified_diff(oo, no, lineterm='', n=0):
                if d.startswith('-') and not d.startswith('---'):
                    out.append(f"{label} — wording removed: {d[1:]}")
                elif d.startswith('+') and not d.startswith('+++'):
                    out.append(f"{label} — wording added: {d[1:]}")
    return out, had_prev


def subset_listen(listen_src, keep_labels, dst):
    """Cut the listening score down to the named parts — the isolated
    listen that settles 'which line is that' questions by ear."""
    xml = open(listen_src, encoding='utf-8').read()
    keep = {k.strip().lower() for k in keep_labels}
    ids = []
    for sp in re.findall(r'<score-part id="(P\d+)">.*?'
                         r'<part-name>([^<]*)</part-name>', xml, re.S):
        if sp[1].strip().lower() in keep:
            ids.append(sp[0])
    if not ids:
        return None
    def drop_scorepart(m):
        return m.group(0) if m.group(1) in ids else ''
    xml = re.sub(r'<score-part id="(P\d+)">.*?</score-part>\n?',
                 drop_scorepart, xml, flags=re.S)
    xml = re.sub(r'<part id="(P\d+)">.*?</part>\n?',
                 lambda m: m.group(0) if m.group(1) in ids else '',
                 xml, flags=re.S)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(xml)
    return dst

MSCORE_CANDIDATES = [
    "/Applications/MuseScore 4.app/Contents/MacOS/mscore",
    "/Applications/MuseScore 4.5.app/Contents/MacOS/mscore",
    r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
    "mscore",
    "MuseScore4",
]


def say(line):
    """One write per thing said — a screen reader restarts on every write."""
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


CONFIG = os.path.expanduser("~/.config/copyist/config.json")
SETTINGS = (
    ('composer', '', "the name every new chart offers to put on the "
                     "page — set it once, stop typing it"),
    ('look', '', "how pages dress when a chart has no look: line — "
                 "jazz, handwritten, engraved or plain"),
    ('notify', 'no', "a phone ping when a build lands — for the long "
                     "ones you walk away from"),
    ('open', 'no', "pop the score PDF open the moment a build lands"),
)


def load_cfg():
    cfg = {k: d for k, d, _ in SETTINGS}
    try:
        import json
        cfg.update({k: v for k, v in
                    json.load(open(CONFIG, encoding='utf-8')).items()
                    if k in cfg})
    except Exception:
        pass
    return cfg


def run_settings(argv):
    cfg = load_cfg()
    if not argv or argv[0] == 'settings':
        say("Copyist settings — every one says what it is set to now:")
        for k, _, desc in SETTINGS:
            say(f"  {k} (now: {cfg[k] or 'not set'}) — {desc}")
        say("Change one with: chart set key=value")
        return
    # chart set key=value
    pair = " ".join(argv[1:])
    if '=' not in pair:
        sys.exit("chart: set wants key=value, like: chart set look=jazz")
    k, v = pair.split('=', 1)
    k, v = k.strip().lower(), v.strip()
    if k not in {s[0] for s in SETTINGS}:
        sys.exit(f"chart: no setting called '{k}' — settings lists "
                 "the four that exist.")
    if k in ('notify', 'open'):
        if v.lower() not in ('yes', 'no', 'on', 'off'):
            sys.exit(f"chart: {k} is yes or no.")
        v = 'yes' if v.lower() in ('yes', 'on') else 'no'
    if k == 'look' and v and not any(w in v.lower() for w in (
            'jazz', 'handwritten', 'engraved', 'plain')):
        sys.exit("chart: the looks are jazz, handwritten, engraved "
                 "and plain (or empty to let each chart decide).")
    cfg[k] = v
    import json
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=1)
    lines = {
        'composer': f"composer is now {v or 'not set'} — every new "
                    "chart offers it on the page.",
        'look': (f"look is now {v} — every chart without its own look: "
                 "line dresses this way." if v else
                 "look is now unset — each chart decides for itself."),
        'notify': ("notify is on — your phone hears every build land."
                   if v == 'yes' else
                   "notify is off — builds finish quietly."),
        'open': ("open is on — the score pops up when a build lands."
                 if v == 'yes' else
                 "open is off — the pages wait in the build folder."),
    }
    say(lines[k])


def notify_build(title, line, failed=False):
    """A phone ping when a build lands; never the reason one fails."""
    from shutil import which
    po = which('pushover') or os.path.expanduser('~/bin/pushover')
    if not os.path.exists(po):
        return
    try:
        subprocess.run([po, 'send', '--title', f"Copyist: {title}",
                        '--priority', '0' if failed else '-1', line],
                       capture_output=True, timeout=15)
    except Exception:
        pass


def open_pages(title_dir):
    """Pop the score (or the first PDF) open, each platform its way."""
    import glob as _g
    pdfs = sorted(_g.glob(os.path.join(title_dir, "* — score.pdf"))) or \
        sorted(_g.glob(os.path.join(title_dir, "*.pdf")))
    if not pdfs:
        return
    try:
        if sys.platform == 'darwin':
            subprocess.run(['open', pdfs[0]], timeout=15)
        elif sys.platform == 'win32':
            os.startfile(pdfs[0])
        else:
            subprocess.run(['xdg-open', pdfs[0]], timeout=15)
    except Exception:
        pass


def find_mscore():
    for c in MSCORE_CANDIDATES:
        if os.path.sep in c:
            if os.path.exists(c):
                return c
        else:
            from shutil import which
            if which(c):
                return c
    return None


def render_listen(listen_src, mp3, say, only=None, count_in=None,
                  lead=None):
    """Copyist synthesizes the listening document itself, then encodes.
    True with the MP3 in place (or, without ffmpeg, the WAV and a
    sentence)."""
    wav = mp3[:-4] + ".wav"
    try:
        _, _, _, lead_s = chartaudio.render(listen_src, wav, only=only,
                                            count_in=count_in)
        if lead is not None:
            lead[0] = lead_s
    except SystemExit:
        raise
    except Exception as e:
        say(f"Copyist hit a wall rendering its own audio: {e}")
        return False
    if chartaudio.to_mp3(wav, mp3):
        os.remove(wav)
    else:
        how = ("brew install ffmpeg" if sys.platform == "darwin"
               else "winget install ffmpeg" if sys.platform == "win32"
               else "your package manager's ffmpeg")
        say(f"No ffmpeg here, so the listen stays a WAV — {how} "
            "gets MP3s.")
    return True


FACES = ('titleFontFace', 'subTitleFontFace', 'composerFontFace',
         'lyricistFontFace', 'partNameFontFace', 'instrumentNameFontFace',
         'tempoFontFace', 'rehearsalMarkFontFace', 'measureNumberFontFace',
         'staffTextFontFace', 'systemTextFontFace', 'lyricsOddFontFace',
         'lyricsEvenFontFace', 'chordSymbolAFontFace', 'dynamicsFontFace',
         'expressionFontFace', 'metronomeFontFace')

LOOKS = {
    'jazz': ('MuseJazz', 'MuseJazz Text', 'MuseJazz Text'),
    'handwritten': ('MuseJazz', 'MuseJazz Text', 'MuseJazz Text'),
    'engraved': ('Leland', 'Leland Text', 'Edwin'),
}


def parse_look(text):
    """The look: header — how the pages dress. A preset (jazz,
    handwritten, engraved) plus adjustments: landscape, staff <size>,
    measure numbers. Validated here so `check` refuses nonsense."""
    opts = {'preset': None, 'landscape': False, 'staff': None,
            'numbers': False}
    for piece in (p.strip() for p in text.split(',')):
        if piece in LOOKS:
            opts['preset'] = piece
        elif piece == 'landscape':
            opts['landscape'] = True
        elif piece == 'measure numbers':
            opts['numbers'] = True
        else:
            m = re.match(r'staff ([\d.]+)$', piece)
            if m and 1.0 <= float(m.group(1)) <= 3.0:
                opts['staff'] = float(m.group(1))
            elif m:
                sys.exit("chart: look: staff size is in millimetres of "
                         "spatium, 1.0 to 3.0 — 1.75 is the usual, "
                         "bigger is easier to read")
            else:
                sys.exit(f"chart: look: cannot read '{piece}' — the "
                         "looks are jazz, handwritten and engraved, "
                         "plus landscape, staff <size>, and "
                         "measure numbers")
    return opts


def write_style(look_text, outdir):
    """look: -> a MuseScore style file applied at render (-S). One more
    thing the future engraver absorbs; until then the pages can at
    least dress the way the chart says."""
    o = parse_look(look_text)
    lines = []
    if o['preset']:
        sym, mtext, face = LOOKS[o['preset']]
        lines += [f'<musicalSymbolFont>{sym}</musicalSymbolFont>',
                  f'<musicalTextFont>{mtext}</musicalTextFont>']
        lines += [f'<{f}>{face}</{f}>' for f in FACES]
    if o['staff']:
        lines.append(f'<Spatium>{o["staff"]:g}</Spatium>')
    if o['landscape']:
        lines += ['<pageWidth>11</pageWidth>',
                  '<pageHeight>8.5</pageHeight>',
                  '<pagePrintableWidth>10.2</pagePrintableWidth>']
    if o['numbers']:
        lines += ['<showMeasureNumber>1</showMeasureNumber>',
                  '<showMeasureNumberOne>0</showMeasureNumberOne>',
                  '<measureNumberInterval>1</measureNumberInterval>',
                  '<measureNumberSystem>0</measureNumberSystem>']
    if not lines:
        return None
    path = os.path.join(outdir, 'look.mss')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<museScore version="4.40">\n  <Style>\n    '
                + '\n    '.join(lines) + '\n  </Style>\n</museScore>\n')
    return path


def render(mscore, src, dst, style=None):
    """Render src to dst, judging by the output file. One retry — the
    MuseScore CLI is crashy in ways that do not repeat."""
    for _ in range(2):
        if os.path.exists(dst):
            os.remove(dst)
        cmd = [mscore, src, "-o", dst]
        if style:
            cmd += ["-S", style]
        subprocess.run(cmd, capture_output=True, timeout=300)
        if os.path.exists(dst):
            return True
    return False


def list_instruments(want):
    """chart.py instruments [filter] — what can sit in the band?"""
    names = sorted(chartc.HORNS)
    if want:
        names = [n for n in names if want in n]
        aliased = sorted(a for a in chartc.INSTRUMENT_ALIASES
                         if want in a
                         or want in chartc.INSTRUMENT_ALIASES[a])
        if not names and not aliased:
            say(f'Nothing here matches "{want}" — but any word still '
                'prints verbatim through text, so nobody is blocked. '
                'Ask for the instrument to be added; it takes a minute.')
            return
        if names:
            say(f'{len(names)} instrument(s) matching "{want}": '
                + ", ".join(names) + ".")
        if aliased:
            say("Nicknames that work: " + ", ".join(
                f"{a} (that is {chartc.INSTRUMENT_ALIASES[a]})"
                for a in aliased) + ".")
    else:
        say(f"{len(chartc.HORNS)} instruments, piccolo to spoons, every "
            "voice included. Narrow it down: chart.py instruments bell "
            "— or try sax, voice, drum, cymbal, cello.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'instruments':
        list_instruments(" ".join(sys.argv[2:]).strip().lower())
        return

    if len(sys.argv) == 1:
        say("Copyist chart — a song from played demo to proofread "
            "parts, by ear.")
        say("Start with a chart file: 'chart my-tune.chart' builds "
            "everything; add 'check' to just prove it, 'read' to hear "
            "a part, 'parts' for the band, 'new --demo take.mid' to "
            "start one from your playing.")
        say("The writer's guide is CHART-WRITING.md, next to the code "
            "and in your Copyist Charts folder.")
        return
    try:
        sys.stdout.reconfigure(errors='replace')   # a Windows console
    except Exception:                              # never kills a build
        pass
    if len(sys.argv) > 1 and sys.argv[1] in ('settings', 'set'):
        run_settings(sys.argv[1:])
        return
    ap = argparse.ArgumentParser(
        description="Compile a chart and make everything a writer "
                    "needs. 'chart settings' shows the defaults desk.")
    ap.add_argument('chart', help="the .chart file")
    ap.add_argument('command', nargs='?', default='build',
                    choices=['build', 'check', 'read', 'parts', 'diff',
                             'listen', 'new',
                             'b', 'c', 'r', 'p', 'd', 'l', 'n'],
                    help="build (default): everything; check: compile "
                         "only; read: speak the chart; parts: list the "
                         "band; diff: what changed since the last build; "
                         "listen: just the MP3; new: interview a starter "
                         "chart into existence. Each has a one-letter "
                         "shortcut: b c r p d l n")
    ap.add_argument('--part', help='with read: one part, e.g. "trumpet 1"')
    ap.add_argument('--section', help="with read: just this section")
    ap.add_argument('--outdir', help="where the built files go "
                                     "(default: build, beside the chart)")
    ap.add_argument('--no-pages', action='store_true',
                    help="skip the PDFs")
    ap.add_argument('--no-listen', action='store_true',
                    help="skip the listening MP3")
    ap.add_argument('--solo',
                    help='also bounce an isolated listen of just these '
                         'parts, e.g. --solo "bari,trombone"')
    ap.add_argument('--count-in', type=int, nargs='?', const=1,
                    dest='count_in', metavar='BARS',
                    help="start the listen MP3 with this many bars of "
                         "click (default 1) — play along like a session")
    ap.add_argument('--from-bar', type=int, dest='from_bar',
                    help="also cut a listen MP3 starting at this bar "
                         "(your DAW's numbering) — no waiting through "
                         "the whole tune to proof the ending")
    ap.add_argument('--demo', help="with new: the demo MIDI to scaffold "
                                   "the chart around")
    args = ap.parse_args()
    args.command = {'b': 'build', 'c': 'check', 'r': 'read',
                    'p': 'parts', 'd': 'diff', 'l': 'listen',
                    'n': 'new'}.get(args.command, args.command)
    cfg = load_cfg()

    if args.command == 'new':
        import chartnew
        chartnew.interview(args.chart, args.demo,
                           composer=cfg['composer'])
        return

    path = args.chart
    if not os.path.exists(path):
        sys.exit(f"chart: no file at '{path}'.")
    base_dir = os.path.dirname(os.path.abspath(path))
    title_dir = args.outdir or os.path.join(base_dir, "build")

    if args.command == 'parts':
        chart = chartc.parse_chart(path)
        bits = []
        for b in chart['band']:
            inst = chartc.canonical_instrument(b['instrument'])
            name = (b['label'] if b['label'].lower() == inst
                    else f"{b['label']} ({inst})")
            if b.get('demo'):
                name += ", on the demo"
            bits.append(name)
        say(f"The band — {len(bits)} chairs: " + "; ".join(bits) + ".")
        return

    if args.command == 'read':
        argv = [path] + (['--part', args.part] if args.part else []) \
            + (['--section', args.section] if args.section else [])
        sys.argv = ['chartread'] + argv
        chartread.main()
        return

    chart = chartc.parse_chart(path)
    title = chart['header'].get('title', 'chart')
    labels = [b['label'] for b in chart['band']]
    prev_dir = os.path.join(title_dir, "previous read-alouds")

    if args.command == 'diff':
        sentences, had = diff_readalouds(prev_dir, base_dir, title, labels)
        if not had:
            say("Nothing to compare yet — the diff needs two builds.")
        elif not sentences:
            say("Nothing changed since the last build.")
        else:
            say(f"{len(sentences)} change(s) since the last build:")
            for s in sentences:
                say(s)
        return

    do_reads = args.command != 'listen'

    # remember which chart text produced the previous build, so a source
    # diff is always possible
    built_from = os.path.join(title_dir, "built from.chart")
    os.makedirs(title_dir, exist_ok=True)
    import shutil
    # the snapshot is a nicety for the diff — a cloud file that is not
    # local yet (or any copy hiccup) must never kill the build itself
    try:
        if os.path.exists(built_from):
            os.makedirs(prev_dir, exist_ok=True)
            shutil.copy2(built_from,
                         os.path.join(prev_dir,
                                      "previous built from.chart"))
    except OSError as e:
        say(f"Could not snapshot the previous source ({e}) — "
            "the build carries on; only the diff loses its memory.")

    # ---- check / build: compile first, loudly, then prove the arithmetic
    written = chartc.compile_chart(path, title_dir)
    try:
        shutil.copy2(path, built_from)
    except OSError as e:
        say(f"Could not snapshot the chart source ({e}) — "
            "the build carries on.")
    bad = verify_measures(written)
    if bad:
        for b in bad[:10]:
            say("broken measure: " + b)
        sys.exit(f"chart: {len(bad)} measure(s) do not add up — that is a "
                 "converter bug, not your chart. Report the lines above.")
    if chart['header'].get('look'):
        parse_look(chart['header']['look'])   # refuse nonsense in check
    if args.command == 'check':
        say("The chart compiles and every measure adds up. Nothing "
            "rendered — that was a check.")
        stale = [f for f in glob.glob(
                     os.path.join(base_dir, f"{title} — *read aloud.txt"))
                 if os.path.getmtime(f) < os.path.getmtime(path)]
        if stale:
            say("Heads up: the saved read-alouds are older than this "
                "chart — 'read' speaks the current version, and a "
                "build refreshes the files.")
        return

    # ---- read-alouds, next to the chart where the writer lives.
    # snapshot the outgoing read-alouds so the new build has something
    # to answer "what changed?" against
    os.makedirs(prev_dir, exist_ok=True)
    if do_reads:
        for label in labels:
            cur = os.path.join(base_dir,
                               f"{title} — {label} part, read aloud.txt")
            if os.path.exists(cur):
                shutil.copy2(cur, prev_dir)

    for label in (labels + [None] if do_reads else []):
        argv = [path] + (['--part', label] if label else [])
        name = (f"{title} — {label} part, read aloud.txt" if label
                else f"{title} — form, read aloud.txt")
        out = os.path.join(base_dir, name)
        old_stdout, sys.stdout = sys.stdout, open(out, 'w', encoding='utf-8')
        try:
            sys.argv = ['chartread'] + argv
            chartread.main()
        finally:
            sys.stdout.close()
            sys.stdout = old_stdout
    if do_reads:
        say(f"Read-alouds written for all {len(labels)} parts and the "
            "form.")

    # ---- the blast radius: what did this build change?
    sentences, had = ((diff_readalouds(prev_dir, base_dir, title, labels))
                      if do_reads else ([], False))
    if had:
        if not sentences:
            say("Nothing changed since the last build.")
        elif len(sentences) <= 12:
            say(f"{len(sentences)} change(s) since the last build:")
            for s in sentences:
                say(s)
        else:
            say(f"{len(sentences)} changes since the last build — run "
                "the diff command for the full list.")

    # ---- pages and the listen file. The listen is Copyist's own —
    # only the PDF pages still ask MuseScore (for now).
    mscore = find_mscore()
    if mscore is None and not (args.no_pages or args.command == 'listen'):
        say("No MuseScore here, so no PDF pages — it is free at "
            "musescore.org. The listen file is Copyist's own and comes "
            "out regardless.")

    look = chart['header'].get('look') or cfg['look'] or None
    look_style = write_style(look, title_dir) if look else None
    if not args.no_pages and args.command != 'listen':
        say("Drawing the pages.")
    pages = 0
    borrowed = []
    failed = []
    listen_src = None
    for src in written:
        if not src.endswith('.musicxml'):
            continue
        if '— for listening' in src:
            listen_src = src
            continue
        if args.no_pages or args.command == 'listen':
            continue
        dst = src[:-len('.musicxml')] + '.pdf'
        why = None
        try:
            ok, why = chartengrave.engrave(src, dst, look=look)
        except Exception as e:
            ok, why = False, f"engraver error: {e} (report that)"
        if ok:
            pages += 1
            continue
        if mscore and render(mscore, src, dst, style=look_style):
            pages += 1
            borrowed.append((os.path.basename(src)
                             .replace('.musicxml', ''), why))
        else:
            failed.append(os.path.basename(src) + f" ({why})"
                          if why else os.path.basename(src))
    if not args.no_pages and args.command != 'listen':
        if borrowed:
            say(f"{pages} pages — Copyist drew "
                f"{pages - len(borrowed)} itself; MuseScore covered "
                + ", ".join(f"{n} — {w}" for n, w in borrowed) + ".")
        else:
            say(f"{pages} pages, every one Copyist's own ink — no "
                "MuseScore anywhere in this build.")
        if failed:
            say("No page for " + ", ".join(failed) + ".")

    if not args.no_listen and listen_src:
        mp3 = os.path.join(title_dir,
                           f"{title} — chart as written (robot horns).mp3")
        lead = [0.0]
        if render_listen(listen_src, mp3, say,
                         count_in=args.count_in, lead=lead):
            say("The listen file is ready — Copyist's own robot horns "
                "playing exactly what the pages say"
                + (f", after {args.count_in} bar(s) of count-in"
                   if args.count_in else "")
                + ". Anywhere it sounds wrong, the page is wrong.")
        elif mscore and render(mscore, listen_src, mp3):
            say("Copyist's own render failed (report that), so MuseScore "
                "played this one — the old robot horns.")
        else:
            say("No listen MP3 this time — Copyist's render failed and "
                "MuseScore is not here to cover it. Report this.")

        # a trimmed listen: proof the ending without the commute
        if args.from_bar and os.path.exists(mp3):
            from shutil import which
            if which('ffmpeg') is None:
                say("No ffmpeg here, so no trimmed listen — brew install "
                    "ffmpeg gets it.")
            else:
                countin = int(chart['header'].get('countin', 0))
                printed = max(1, args.from_bar - countin)
                # the player's own walk: repeats and voltas included,
                # and by construction it matches the rendered audio
                seconds = chartaudio.first_bar_seconds(listen_src,
                                                       printed)
                if seconds is not None:
                    seconds += lead[0]
                if seconds is None:
                    say(f"The pages have no bar {printed}, so no trim — "
                        "the full MP3 stands.")
                    return
                cut = os.path.join(
                    title_dir, f"{title} — listen from bar "
                               f"{args.from_bar}.mp3")
                subprocess.run(['ffmpeg', '-y', '-hide_banner',
                                '-ss', f'{seconds:.2f}', '-i', mp3, cut],
                               capture_output=True)
                if os.path.exists(cut):
                    say(f"Trimmed listen ready, starting at bar "
                        f"{args.from_bar}.")
                else:
                    say("ffmpeg refused the trim; the full MP3 stands.")

    if args.solo and listen_src:
        wanted = [w.strip() for w in args.solo.split(',') if w.strip()]
        nice = " + ".join(wanted)
        mp3 = os.path.join(title_dir, f"{title} — listen, {nice}.mp3")
        try:
            if render_listen(listen_src, mp3, say, only=wanted):
                say(f"Isolated listen ready: {nice}, alone.")
        except SystemExit:
            say(f'No parts matched --solo "{args.solo}" — '
                "try the parts command for the exact names.")

    say("Done. Proof it by ear before a single player sees it.")
    tname = os.path.splitext(os.path.basename(path))[0]
    if cfg['notify'] == 'yes':
        notify_build(tname, f"{pages} page(s) built, listen ready."
                     if pages else "Built — listen ready.")
    if cfg['open'] == 'yes' and pages:
        open_pages(title_dir)
    marker = os.path.expanduser("~/.config/copyist/welcomed")
    if args.command == 'build' and not os.path.exists(marker):
        try:
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            open(marker, "w").write("hello\n")
            say("And since that was your first full build: 'read' "
                "speaks any part any time, the findings file next to "
                "the pages keeps everything I noticed, and every "
                "rebuild tells you exactly what changed. Welcome to "
                "the copy desk.")
        except OSError:
            pass


if __name__ == '__main__':
    try:
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as e:
        # the house rule: every error is one sentence. The whole story
        # goes to a file for whoever chases it.
        import traceback
        spot = os.path.expanduser('~/.config/copyist/last-error.txt')
        where = ""
        try:
            os.makedirs(os.path.dirname(spot), exist_ok=True)
            with open(spot, 'w', encoding='utf-8') as f:
                f.write(traceback.format_exc())
            where = f" The full story is in {spot}."
        except OSError:
            pass
        sys.exit(f"chart: something broke inside — "
                 f"{type(e).__name__}: {e}.{where} That is a bug in "
                 "Copyist, not in your chart.")
