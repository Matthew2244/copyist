"""Write Sparkle's update list for one release.

    python3 tools/appcast.py FILE VERSION URL [NOTES.md] [--windows] > appcast.xml

With --windows, FILE is the Windows installer and the list is for
WinSparkle. FILE is signed with the EdDSA key in this Mac's login
Keychain (Sparkle's sign_update finds it there; the same key signs
Wavelength); every installed copy checks that signature against
SUPublicEDKey before installing anything.

NOTES.md is the release notes in the plain Markdown the release page
uses (paragraphs and "- " lists), turned into the HTML Sparkle shows.
"""
import html
import os
import re
import subprocess
import sys
from email.utils import formatdate

# The Keychain's "Always Allow" for the signing key is tied to one
# sign_update path: Wavelength's copy of the same Sparkle already has it,
# so it's used first and no Keychain prompt interrupts a release.
SIGN_UPDATE = next((p for p in (os.path.expanduser(
    "~/Library/Caches/%s/sparkle-2.10.0/x/bin/sign_update" % d)
    for d in ("media-download-build", "copyist-build"))
    if os.path.exists(p)), "sign_update")
MIN_MACOS = "13.0"


def notes_html(md):
    out = []
    for block in re.split(r"\n\s*\n", md.strip()):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if all(ln.startswith("- ") for ln in lines):
            out.append("<ul>%s</ul>" % "".join(
                "<li>%s</li>" % html.escape(ln[2:]) for ln in lines))
        elif lines[0].startswith("#"):
            out.append("<h3>%s</h3>" % html.escape(lines[0].lstrip("# ")))
            if lines[1:]:
                out.append("<p>%s</p>" % html.escape(" ".join(lines[1:])))
        else:
            out.append("<p>%s</p>" % html.escape(" ".join(lines)))
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", "\n".join(out))


def main():
    windows = "--windows" in sys.argv
    argv = [a for a in sys.argv if a != "--windows"]
    path, version, url = argv[1:4]
    notes = open(argv[4]).read() if len(argv) > 4 else ""
    sig = subprocess.run([SIGN_UPDATE, path], capture_output=True,
                         text=True, check=True).stdout.strip()
    if "sparkle:edSignature" not in sig:
        sys.exit("sign_update gave no signature: " + sig)
    minsys = "" if windows else (
        "<sparkle:minimumSystemVersion>%s</sparkle:minimumSystemVersion>"
        % MIN_MACOS)
    # WinSparkle runs the installer: quietly, and /relaunch=1 opens
    # Copyist again afterwards
    win = (' sparkle:os="windows" sparkle:installerArguments="/SILENT '
           '/SP- /SUPPRESSMSGBOXES /NORESTART /relaunch=1"'
           if windows else "")
    print("""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Copyist</title>
    <item>
      <title>Copyist {v}</title>
      <pubDate>{date}</pubDate>
      <sparkle:version>{v}</sparkle:version>
      <sparkle:shortVersionString>{v}</sparkle:shortVersionString>
      {minsys}
      <description><![CDATA[{notes}]]></description>
      <enclosure url="{url}" {sig} type="application/octet-stream"{win}/>
    </item>
  </channel>
</rss>""".format(v=version, date=formatdate(usegmt=True), minsys=minsys,
                 notes=notes_html(notes), url=html.escape(url, quote=True),
                 sig=sig, win=win))


if __name__ == "__main__":
    main()
