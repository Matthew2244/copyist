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

import chartc
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
            for num, m in re.findall(
                    r'<measure [^>]*?number="([^"]+)"[^>]*>(.*?)</measure>',
                    body, re.S):
                dv = re.search(r'<divisions>(\d+)</divisions>', m)
                if dv:
                    div = int(dv.group(1))
                if num == '0':
                    continue               # a pickup is partial on purpose
                expect = div * 4
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
    "mscore",
]


def say(line):
    """One write per thing said — a screen reader restarts on every write."""
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


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


def render(mscore, src, dst):
    """Render src to dst, judging by the output file. One retry — the
    MuseScore CLI is crashy in ways that do not repeat."""
    for _ in range(2):
        if os.path.exists(dst):
            os.remove(dst)
        subprocess.run([mscore, src, "-o", dst],
                       capture_output=True, timeout=300)
        if os.path.exists(dst):
            return True
    return False


def main():
    ap = argparse.ArgumentParser(
        description="Compile a chart and make everything a writer needs.")
    ap.add_argument('chart', help="the .chart file")
    ap.add_argument('command', nargs='?', default='build',
                    choices=['build', 'check', 'read', 'parts'],
                    help="build (default): everything; check: compile "
                         "only; read: speak the chart; parts: list the band")
    ap.add_argument('--part', help='with read: one part, e.g. "trumpet 1"')
    ap.add_argument('--outdir', help="where the built files go "
                                     "(default: build, beside the chart)")
    ap.add_argument('--no-pages', action='store_true',
                    help="skip the PDFs")
    ap.add_argument('--no-listen', action='store_true',
                    help="skip the listening MP3")
    ap.add_argument('--solo',
                    help='also bounce an isolated listen of just these '
                         'parts, e.g. --solo "bari,trombone"')
    args = ap.parse_args()

    path = args.chart
    if not os.path.exists(path):
        sys.exit(f"chart: no file at '{path}'.")
    base_dir = os.path.dirname(os.path.abspath(path))
    title_dir = args.outdir or os.path.join(base_dir, "build")

    if args.command == 'parts':
        chart = chartc.parse_chart(path)
        names = [b['label'] for b in chart['band']]
        say(f"{len(names)} parts: " + ", ".join(names) + ".")
        return

    if args.command == 'read':
        argv = [path] + (['--part', args.part] if args.part else [])
        sys.argv = ['chartread'] + argv
        chartread.main()
        return

    # ---- check / build: compile first, loudly, then prove the arithmetic
    written = chartc.compile_chart(path, title_dir)
    bad = verify_measures(written)
    if bad:
        for b in bad[:10]:
            say("broken measure: " + b)
        sys.exit(f"chart: {len(bad)} measure(s) do not add up — that is a "
                 "converter bug, not your chart. Report the lines above.")
    if args.command == 'check':
        say("The chart compiles and every measure adds up. Nothing "
            "rendered — that was a check.")
        return

    # ---- read-alouds, next to the chart where the writer lives
    chart = chartc.parse_chart(path)
    title = chart['header'].get('title', 'chart')
    labels = [b['label'] for b in chart['band']]
    for label in labels + [None]:
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
    say(f"Read-alouds written for all {len(labels)} parts and the form.")

    # ---- pages and the listen file
    mscore = find_mscore()
    if mscore is None:
        say("No MuseScore here, so no pages or listen file — it is free "
            "at musescore.org, and everything else is done.")
        return

    pages = 0
    failed = []
    listen_src = None
    for src in written:
        if not src.endswith('.musicxml'):
            continue
        if '— for listening' in src:
            listen_src = src
            continue
        if args.no_pages:
            continue
        dst = src[:-len('.musicxml')] + '.pdf'
        if render(mscore, src, dst):
            pages += 1
        else:
            failed.append(os.path.basename(src))
    if not args.no_pages:
        say(f"{pages} pages rendered." if not failed else
            f"{pages} pages rendered; MuseScore refused "
            + ", ".join(failed) + " — run check and read that part back.")

    if not args.no_listen and listen_src:
        mp3 = os.path.join(title_dir,
                           f"{title} — chart as written (robot horns).mp3")
        if render(mscore, listen_src, mp3):
            say("The listen file is ready — robot horns playing exactly "
                "what the pages say. Anywhere it sounds wrong, the page "
                "is wrong.")
        else:
            say("MuseScore refused the listen file, twice. The pages "
                "stand; the MP3 does not.")

    if args.solo and listen_src:
        wanted = [w for w in args.solo.split(',') if w.strip()]
        sub = os.path.join(title_dir, "solo-listen.musicxml")
        if subset_listen(listen_src, wanted, sub) is None:
            say(f'No parts matched --solo "{args.solo}" — '
                "try the parts command for the exact names.")
        else:
            nice = " + ".join(w.strip() for w in wanted)
            mp3 = os.path.join(title_dir, f"{title} — listen, {nice}.mp3")
            if render(mscore, sub, mp3):
                say(f"Isolated listen ready: {nice}, alone.")
            else:
                say("MuseScore refused the isolated listen, twice.")
            os.remove(sub)

    say("Done. Proof it by ear before a single player sees it.")


if __name__ == '__main__':
    main()
