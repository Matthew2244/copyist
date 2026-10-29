"""Sign, notarize and publish a Copyist release: python3 tools/release_mac.py v2.102.0

Run on the Studio, which holds the Developer ID certificate, the App
Store Connect key for the notary and Sparkle's signing key. Never in
GitHub Actions: those keys stay on this Mac.

The release must already exist on GitHub (gh release create), and the
Windows installer CI builds for it should be attached first (the
release workflow does that); without it this run publishes the Mac
update only and says so.

Steps, each checked before the next:
1. Build with the Developer ID and the hardened runtime (app/build.sh,
   COPYIST_SIGN_ID set), then verify the signature strictly.
2. Send it to Apple's notary and wait; staple the approval on.
3. Check Gatekeeper accepts it, zip it as Copyist-mac.zip.
4. Write appcast.xml (Sparkle, Mac) and appcast-windows.xml
   (WinSparkle), each signed with the EdDSA key, and attach all of it.
"""
import argparse
import base64
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "Matthew2244/copyist"
APP = os.path.join(ROOT, "app", "build", "Copyist.app")
DIST = os.path.join(ROOT, "app", "build", "release")


def run(cmd, **kw):
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, text=True, **kw)


def developer_id():
    out = subprocess.run(["security", "find-identity", "-v", "-p",
                          "codesigning"], capture_output=True,
                         text=True).stdout
    ids = re.findall(r'"(Developer ID Application: [^"]+)"', out)
    if not ids:
        sys.exit("No Developer ID Application certificate in the Keychain.")
    return ids[0]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("tag", help="the release, for example v2.102.0")
    p.add_argument("--key-id", default="44L73HXU2W")
    p.add_argument("--issuer", default="4eeb658c-79f1-4dc6-bb6f-54db15d61ce8")
    p.add_argument("--keychain-service", default="asc-api-key")
    p.add_argument("--no-upload", action="store_true",
                   help="do everything except attaching to the release")
    a = p.parse_args()
    version = a.tag.lstrip("v")
    have = open(os.path.join(ROOT, "VERSION")).read().strip()
    if have != version:
        sys.exit("VERSION says %s but the tag is %s." % (have, a.tag))

    ident = developer_id()
    print("Signing as:", ident)
    run([os.path.join(ROOT, "app", "build.sh")],
        env=dict(os.environ, COPYIST_SIGN_ID=ident))
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", APP])

    os.makedirs(DIST, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        p8 = os.path.join(tmp, "AuthKey_%s.p8" % a.key_id)
        b64 = subprocess.run(
            ["security", "find-generic-password", "-s", a.keychain_service,
             "-a", a.key_id, "-w"], capture_output=True, text=True,
            check=True).stdout.strip()
        with open(p8, "wb") as f:
            f.write(base64.b64decode(b64))
        os.chmod(p8, 0o600)
        upload = os.path.join(tmp, "notarize.zip")
        run(["ditto", "-c", "-k", "--keepParent", APP, upload])
        res = subprocess.run(
            ["xcrun", "notarytool", "submit", upload, "--key", p8,
             "--key-id", a.key_id, "--issuer", a.issuer, "--wait"],
            capture_output=True, text=True)
        print(res.stdout, res.stderr)
        if "status: Accepted" not in res.stdout:
            sub = re.search(r"id: ([0-9a-f-]{36})", res.stdout)
            if sub:
                subprocess.run(["xcrun", "notarytool", "log", sub.group(1),
                                "--key", p8, "--key-id", a.key_id,
                                "--issuer", a.issuer])
            sys.exit("Apple did not accept the app. The log above says why.")

    run(["xcrun", "stapler", "staple", APP])
    run(["spctl", "--assess", "--type", "execute", "--verbose=2", APP])
    mac_zip = os.path.join(DIST, "Copyist-mac.zip")
    if os.path.exists(mac_zip):
        os.remove(mac_zip)
    run(["ditto", "-c", "-k", "--keepParent", APP, mac_zip])

    notes = subprocess.run(["gh", "release", "view", a.tag, "-R", REPO,
                            "--json", "body", "--jq", ".body"],
                           capture_output=True, text=True).stdout
    notes_file = os.path.join(DIST, "release-notes.md")
    with open(notes_file, "w") as f:
        f.write(notes)
    base = "https://github.com/%s/releases/download/%s/" % (REPO, a.tag)
    cast = os.path.join(DIST, "appcast.xml")
    with open(cast, "w") as f:
        run([sys.executable, os.path.join(ROOT, "tools", "appcast.py"),
             mac_zip, version, base + "Copyist-mac.zip", notes_file],
            stdout=f)
    uploads = [mac_zip, cast]

    setup = os.path.join(DIST, "Copyist-Setup.exe")
    if os.path.exists(setup):
        os.remove(setup)
    got = subprocess.run(["gh", "release", "download", a.tag, "-R", REPO,
                          "-p", "Copyist-Setup.exe", "-D", DIST],
                         capture_output=True, text=True)
    if got.returncode == 0 and os.path.exists(setup):
        win_cast = os.path.join(DIST, "appcast-windows.xml")
        with open(win_cast, "w") as f:
            run([sys.executable, os.path.join(ROOT, "tools", "appcast.py"),
                 setup, version, base + "Copyist-Setup.exe", notes_file,
                 "--windows"], stdout=f)
        uploads.append(win_cast)
    else:
        print("No Windows installer on the release yet, so no Windows "
              "update list this time.")
    if not a.no_upload:
        run(["gh", "release", "upload", a.tag, "-R", REPO, *uploads,
             "--clobber"])
    print("Done: Copyist %s is signed, notarized and stapled%s." % (
        version, "" if a.no_upload else ", attached to " + a.tag
        + " with its signed update lists"))


if __name__ == "__main__":
    main()
