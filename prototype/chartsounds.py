#!/usr/bin/env python3
"""chartsounds — the sample shelf: what the band can play, where it
comes from, and installing it (Matthew, 2026-09-29: "it should come
bundled with all sounds / samples ready to go and the user could decide
if they wanna use them or not and where they should be installed").

The shelf is about 34 GB, too big to ride inside the app, so the app
carries this catalog instead: every library the band plays, what it
plays, its size and license, and where to fetch it. The writer picks
which to install and where; Copyist downloads, unpacks, converts what
its pure-Python reader needs (FLAC to WAV twins, 24-bit to 16-bit) and
builds its own extras (tenor, saxello, falls, choir, organ) from them.
Nothing is ever fetched without being asked. Every library here is
openly licensed for this use; the licence line travels with it.

    chart sounds                 what plays now, what's on the shelf
    chart sounds list            the catalog, each line saying installed or not
    chart sounds install band    everything the band plays (or names, or all)
    chart sounds remove NAME     take one off the shelf (asks first)
"""
import os
import re
import shutil
import sys
import tarfile
import time
import urllib.request
import wave
import zipfile

# key: (name, what it plays, size in MB installed, license, folder on
# the shelf, source url, top folder inside the archive or None, needs)
# 'band' marks what the band plays; the rest are optional colours.
CATALOG = [
    # every url checked 2026-09-29 (HEAD 200, no login); licences read
    # from each project's own licence file
    {'key': 'piano', 'name': 'Salamander Grand Piano V3',
     'plays': 'the piano', 'mb': 1260, 'license': 'CC-BY 3.0',
     'credit': 'Salamander Grand Piano V3 by Alexander Holm, CC-BY 3.0',
     'folder': 'Salamander',
     'url': 'https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/'
            'SalamanderGrandPianoV3+20161209_48khz24bit.tar.xz',
     'band': True},
    {'key': 'orchestra', 'name': 'VSCO 2 Community Edition (samples)',
     'plays': 'the recorded trombone falls, and the orchestra samples',
     'mb': 3100, 'license': 'CC0', 'folder': 'VSCO2-CE',
     'url': 'https://github.com/' + 'sgossner/VSCO-2-CE/archive/refs/heads/master.zip',
     'band': True},
    {'key': 'orchestra-maps', 'name': 'VSCO 2 CE, SFZ edition',
     'plays': 'brass, winds, strings, mallets, orchestral percussion',
     'mb': 3100, 'license': 'CC0', 'folder': 'VSCO2-CE-SFZ',
     'url': 'https://github.com/' + 'sgossner/VSCO-2-CE/archive/refs/heads/SFZ.zip',
     'band': True},
    {'key': 'vcsl', 'name': 'VCSL (Versilian Community Sample Library)',
     'plays': 'hand percussion, tenor sax, saxello, and more',
     'mb': 5900, 'license': 'CC0', 'folder': 'VCSL',
     'url': 'https://github.com/' + 'sgossner/VCSL/archive/refs/heads/master.zip',
     'band': True},
    {'key': 'kit', 'name': 'Virtuosity Drums', 'plays': 'the drum kit',
     'mb': 1400, 'license': 'CC0', 'folder': 'VirtuosityDrums',
     'url': 'https://github.com/' + 'sfzinstruments/virtuosity_drums/archive/refs/heads/'
                 'master.zip', 'band': True},
    {'key': 'brushes', 'name': 'Swirly Drums',
     'plays': 'the drum kit with brushes, stirs and all', 'mb': 1700,
     'license': 'CC0', 'folder': 'SwirlyDrums',
     'url': 'https://github.com/' + 'sfzinstruments/karoryfer.swirly-drums/archive/refs/'
                 'heads/main.zip', 'band': True},
    {'key': 'upright', 'name': 'Meatbass', 'plays': 'the upright bass',
     'mb': 282, 'license': 'CC0', 'folder': 'Meatbass',
     'url': 'https://github.com/' + 'sfzinstruments/karoryfer.meatbass/archive/refs/heads/'
                 'master.zip', 'band': True},
    {'key': 'electric-bass', 'name': 'Black and Blue Basses',
     'plays': 'the electric bass', 'mb': 1100, 'license': 'CC0',
     'folder': 'Bass-black-and-blue-basses',
     'url': 'https://github.com/' + 'sfzinstruments/karoryfer.black-and-blue-basses/archive/'
                 'refs/heads/main.zip', 'band': True},
    {'key': 'alto', 'name': 'Weresax', 'plays': 'the alto sax',
     'mb': 194, 'license': 'CC0', 'folder': 'Weresax',
     'url': 'https://github.com/' + 'sfzinstruments/karoryfer.weresax/archive/refs/heads/'
                 'master.zip', 'band': True},
    {'key': 'bari', 'name': 'Bear Sax', 'plays': 'the baritone sax',
     'mb': 138, 'license': 'CC0', 'folder': 'BearSax',
     'url': 'https://github.com/' + 'sfzinstruments/karoryfer.bear-sax/archive/refs/heads/'
                 'master.zip', 'band': True},
    {'key': 'epianos', 'name': "Greg Sullivan's E-Pianos",
     'plays': 'Wurlitzer, CP80 and Pianet electric pianos', 'mb': 20,
     'license': 'CC-BY 3.0',
     'credit': "E-Pianos by Greg Sullivan, mapped to SFZ by kinwie, "
               "CC-BY 3.0",
     'folder': 'EPianos',
     'url': 'https://github.com/' + 'sfzinstruments/GregSullivan.E-Pianos/archive/refs/'
                 'heads/master.zip', 'band': True},
    {'key': 'choir', 'name': 'VocalSet 1.1',
     'plays': 'the source of the choir (ah, oh, oo)', 'mb': 2080,
     'license': 'CC-BY 4.0',
     'credit': 'VocalSet by Julia Wilkins, Prem Seetharaman, Alison '
               'Wahl and Bryan Pardo, CC-BY 4.0',
     'folder': 'VocalSet',
     'url': 'https://zenodo.org/records/1442513/files/VocalSet11.zip',
     'band': True},
    {'key': 'floor', 'name': 'MuseScore General SoundFont',
     'plays': 'the floor under everything, and the jazz guitar',
     'mb': 216, 'license': 'MIT',
     'credit': 'MuseScore General SoundFont, MIT (licence file alongside)',
     'folder': 'MuseScore_General.sf2',
     'url': 'https://ftp.osuosl.org/pub/musescore/soundfont/'
            'MuseScore_General/MuseScore_General.sf2',
     'also': [('https://ftp.osuosl.org/pub/musescore/soundfont/'
               'MuseScore_General/MuseScore_General_License.md',
               'MuseScore_General_License.md')],
     'band': True, 'file': True},
]


def say(line):
    print(line, flush=True)


def progress(pct, what):
    """The app's progress bar reads these; the terminal hears them."""
    if os.environ.get('COPYIST_PROGRESS'):
        print(f"progress: {int(pct)}% — {what}", flush=True)


def find(words):
    """'band', 'all', or names/keys -> catalog entries."""
    w = (words or 'band').strip().lower()
    if w in ('band', 'everything the band plays'):
        return [e for e in CATALOG if e.get('band')]
    if w == 'all':
        return list(CATALOG)
    got = []
    for part in re.split(r'[,;]', w):
        p = part.strip()
        hit = next((e for e in CATALOG if p in (e['key'], e['name'].lower(),
                                                e['folder'].lower())), None)
        if hit is None:
            hit = next((e for e in CATALOG if p and
                        p in e['name'].lower()), None)
        if hit is None:
            raise SystemExit(f"chart: no library called '{p}' — 'chart "
                             "sounds list' names them all.")
        got.append(hit)
    return got


def installed(e, home):
    return os.path.exists(os.path.join(home, e['folder']))


def catalog_lines(home):
    lines = []
    for e in CATALOG:
        state = 'installed' if installed(e, home) else 'not installed'
        size = (f"{e['mb'] / 1000:.1f} GB" if e['mb'] >= 1000
                else f"{e['mb']} MB")
        lines.append(f"  {e['key']}: {e['name']} — {e['plays']}; "
                     f"{size}, {e['license']}; {state}")
    return lines


# ------------------------------------------------------------- fetching

def _download(url, dest, what, share):
    """Fetch url to dest, saying how far along it is every tenth."""
    req = urllib.request.Request(url, headers={'User-Agent': 'Copyist'})
    with urllib.request.urlopen(req, timeout=60) as r, \
            open(dest, 'wb') as f:
        total = int(r.headers.get('Content-Length') or 0)
        got, said = 0, -1
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if not total and got // (100 << 20) != said:
                # GitHub's archives send no size: say it by the 100 MB
                said = got // (100 << 20)
                if said:
                    say(f"  {what}: {got / 1e6:.0f} MB so far")
                    progress(share[0], f"downloading {what}, "
                             f"{got / 1e6:.0f} MB")
            if total:
                tenth = got * 10 // total
                if tenth != said:
                    said = tenth
                    progress(share[0] + (share[1] - share[0]) * got / total,
                             f"downloading {what}")
                    if tenth % 2 == 0:
                        say(f"  {what}: {tenth * 10}% "
                            f"({got / 1e6:.0f} of {total / 1e6:.0f} MB)")


def _clone_instead(e, home, why):
    """GitHub builds its zips on the fly and can give up on the
    biggest repositories (VCSL is 5.9 GB). With git on the machine, a
    shallow clone of the same branch gets the same files."""
    m = re.match(r'https://github\.com/([^/]+/[^/]+)/archive/refs/heads/'
                 r'([^/]+)\.zip$', e.get('url') or '')
    git = shutil.which('git')
    if not m or not git:
        return False
    say(f"  the download stopped ({why}); fetching {e['name']} with git "
        "instead")
    dest = os.path.join(home, e['folder'])
    shutil.rmtree(dest, ignore_errors=True)
    import subprocess
    r = subprocess.run([git, 'clone', '--depth', '1', '--branch',
                        m.group(2), f"https://github.com/{m.group(1)}.git",
                        dest], capture_output=True, text=True)
    if r.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        return False
    shutil.rmtree(os.path.join(dest, '.git'), ignore_errors=True)
    for note in settle(dest):
        say(f"  {note}")
    return True


def _extract(archive, home, e):
    """Unpack into the shelf, the archive's own top folder renamed to
    the catalog's folder."""
    dest = os.path.join(home, e['folder'])
    tmp = dest + '.unpacking'
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                if n.startswith(('/', '..')) or '/../' in n:
                    raise ValueError(f"unsafe path in archive: {n}")
            z.extractall(tmp)
    else:
        with tarfile.open(archive) as t:
            try:
                t.extractall(tmp, filter='data')   # nothing outside tmp
            except TypeError:
                for m in t.getmembers():
                    if m.name.startswith(('/', '..')) or '/../' in m.name:
                        raise ValueError(f"unsafe path in archive: {m.name}")
                t.extractall(tmp)
    inner = [os.path.join(tmp, n) for n in os.listdir(tmp)
             if not n.startswith(('.', '__MACOSX'))]
    src = inner[0] if len(inner) == 1 and os.path.isdir(inner[0]) else tmp
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.move(src, dest)
    shutil.rmtree(tmp, ignore_errors=True)
    # a Mac-made zip carries its desktop's junk
    for dp, dn, fns in os.walk(dest):
        for d_ in list(dn):
            if d_ == '__MACOSX':
                shutil.rmtree(os.path.join(dp, d_), ignore_errors=True)
                dn.remove(d_)
        for fn in fns:
            if fn == '.DS_Store' or fn.startswith('._'):
                os.remove(os.path.join(dp, fn))
    return dest


# ---------------------------------------------------------- conversions

def to_16bit(path):
    """A 24- or 32-bit PCM WAV rewritten as 16-bit in place: the top
    two bytes of every sample, no library needed. Pure Python decodes
    24-bit too slowly to play a band (2026-09-21). Floats and anything
    unreadable are left alone."""
    try:
        with wave.open(path, 'rb') as w:
            ch, sw, sr, n = (w.getnchannels(), w.getsampwidth(),
                             w.getframerate(), w.getnframes())
            if sw not in (3, 4):
                return False
            data = w.readframes(n)
    except Exception:
        return False
    out = bytearray(len(data) // sw * 2)
    out[0::2] = data[sw - 2::sw]
    out[1::2] = data[sw - 1::sw]
    tmp = path + '.16'
    with wave.open(tmp, 'wb') as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(out))
    os.replace(tmp, path)
    return True


def flac_twins(folder, ffmpeg):
    """A 16-bit WAV beside every FLAC (the reader prefers the twin)."""
    made = 0
    for dp, _dn, fns in os.walk(folder):
        for fn in fns:
            if not fn.lower().endswith('.flac'):
                continue
            src = os.path.join(dp, fn)
            twin = os.path.splitext(src)[0] + '.wav'
            if os.path.exists(twin):
                continue
            import subprocess
            r = subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', src,
                                '-sample_fmt', 's16', twin],
                               capture_output=True)
            if r.returncode == 0:
                made += 1
    return made


def settle(folder):
    """Everything a freshly unpacked library needs before it plays."""
    ffmpeg = shutil.which('ffmpeg')
    flacs = sum(1 for _dp, _dn, fns in os.walk(folder)
                for fn in fns if fn.lower().endswith('.flac'))
    notes = []
    if flacs and ffmpeg:
        notes.append(f"{flac_twins(folder, ffmpeg)} FLAC files given WAV "
                     "twins")
    elif flacs:
        notes.append(f"{flacs} FLAC files need ffmpeg to become playable "
                     "— install ffmpeg, then run the install again")
    wide = 0
    for dp, _dn, fns in os.walk(folder):
        for fn in fns:
            if fn.lower().endswith('.wav') and to_16bit(os.path.join(dp,
                                                                     fn)):
                wide += 1
    if wide:
        notes.append(f"{wide} WAV files brought to 16-bit")
    return notes


# -------------------------------------------------------------- install

def install(words, home, keep_going=True):
    """Install the chosen libraries onto the shelf at home."""
    want = [e for e in find(words) if not installed(e, home)]
    if not want:
        say("Everything asked for is already on the shelf.")
        return 0
    need = sum(e['mb'] for e in want) * 2.2 * 1e6   # archive + unpacked
    os.makedirs(home, exist_ok=True)
    free = shutil.disk_usage(home).free
    if free < need:
        raise SystemExit(
            f"chart: that needs about {need / 1e9:.0f} GB free while it "
            f"installs, and {home} has {free / 1e9:.0f} GB. Pick fewer "
            "libraries, or another place with 'chart set sounds_dir='.")
    missing = [e for e in want if not e.get('url')]
    if missing:
        say("No download source is on file yet for: "
            + ", ".join(e['name'] for e in missing) + ". Skipping those.")
        want = [e for e in want if e.get('url')]
    done = 0
    for i, e in enumerate(want):
        share = (100 * i / len(want), 100 * (i + 1) / len(want))
        say(f"Installing {e['name']} ({e['plays']}) into {home}.")
        arch = os.path.join(home, f".{e['key']}.download")
        try:
            try:
                _download(e['url'], arch, e['name'], share)
            except Exception as ex:
                if not _clone_instead(e, home, ex):
                    raise
                done += 1
                say(f"  {e['name']} is on the shelf ({e['license']}).")
                continue
            if e.get('file'):
                os.replace(arch, os.path.join(home, e['folder']))
                for url, name in e.get('also', ()):
                    _download(url, os.path.join(home, name), name,
                              share)
            else:
                say(f"  unpacking {e['name']}")
                dest = _extract(arch, home, e)
                for note in settle(dest):
                    say(f"  {note}")
            done += 1
            say(f"  {e['name']} is on the shelf ({e['license']}).")
        except Exception as ex:
            say(f"  {e['name']} did not install: {ex}. The rest go on.")
            if not keep_going:
                raise
        finally:
            if os.path.exists(arch):
                os.remove(arch)
    extras(home)
    write_credits(home)
    say(f"Done: {done} of {len(want)} installed. 'chart sounds' shows "
        "what the band plays now.")
    return done


def extras(home):
    """Copyist's own instruments, built from what's on the shelf: the
    tenor and saxello maps, the trombone falls, the choir, the organ."""
    try:
        import mkshelf
        made = mkshelf.main(home)
        if not os.path.exists(os.path.join(home, 'Copyist-Extras',
                                           'organ-gospel-slow.sfz')):
            made += mkshelf.build_organ(home) or []
        if made:
            say("  built Copyist's own: " + ", ".join(made))
    except Exception as ex:
        say(f"  Copyist's own extras were not built: {ex}")


def write_credits(home):
    """CREDITS.txt on the shelf: who made each installed library and
    under what licence — attribution the CC-BY and MIT licences ask
    for, kept where the samples are."""
    lines = ['The sample shelf Copyist plays: who made each library.', '']
    for e in CATALOG:
        if installed(e, home):
            lines.append(f"{e['name']} ({e['plays']}): "
                         + e.get('credit', e['license']))
    try:
        with open(os.path.join(home, 'CREDITS.txt'), 'w',
                  encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    except OSError:
        pass


def remove(words, home, yes=False):
    for e in find(words):
        p = os.path.join(home, e['folder'])
        if not os.path.exists(p):
            say(f"{e['name']} is not on the shelf.")
            continue
        if not yes:
            say(f"{e['name']} would go ({e['mb']} MB). Run again with "
                "--yes to remove it.")
            continue
        if os.path.isdir(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
        say(f"{e['name']} is off the shelf.")
