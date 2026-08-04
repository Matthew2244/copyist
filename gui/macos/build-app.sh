#!/bin/bash
# Build Copyist.app.
#
# `swift build` produces a bare executable, which is fine for development and
# useless as a deliverable: macOS will not treat it as a real application, it
# cannot be launched from Spotlight or the Dock, and other apps cannot even see
# it by name. This wraps it in a proper bundle.
#
#   ./build-app.sh [--release]

set -euo pipefail
cd "$(dirname "$0")"

CONFIG=debug
[[ "${1:-}" == "--release" ]] && CONFIG=release

swift build -c "$CONFIG"

APP="Copyist.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp ".build/$CONFIG/Copyist" "$APP/Contents/MacOS/Copyist"
cp ".build/$CONFIG/axaudit" "$APP/Contents/MacOS/axaudit" 2>/dev/null || true

# The engine ships inside the bundle so a built app does not depend on the
# source tree sitting next to it.
mkdir -p "$APP/Contents/Resources/prototype"
cp ../../prototype/*.py "$APP/Contents/Resources/prototype/"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>              <string>Copyist</string>
    <key>CFBundleDisplayName</key>       <string>Copyist</string>
    <key>CFBundleExecutable</key>        <string>Copyist</string>
    <key>CFBundleIdentifier</key>        <string>me.matthewwhitaker.copyist</string>
    <key>CFBundlePackageType</key>       <string>APPL</string>
    <key>CFBundleShortVersionString</key><string>0.1.0</string>
    <key>CFBundleVersion</key>           <string>1</string>
    <key>LSMinimumSystemVersion</key>    <string>13.0</string>
    <key>NSHighResolutionCapable</key>   <true/>
    <key>NSSupportsAutomaticTermination</key><false/>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeName</key><string>MIDI File</string>
            <key>CFBundleTypeRole</key><string>Viewer</string>
            <key>LSItemContentTypes</key>
            <array><string>public.midi-audio</string></array>
        </dict>
    </array>
</dict>
</plist>
PLIST

# Ad-hoc signature. Enough for local use; a real release needs a Developer ID
# and notarization, which is a decision for whenever this ships.
codesign --force --deep --sign - "$APP" 2>/dev/null \
  && echo "signed (ad-hoc)" || echo "codesign unavailable; running unsigned"

echo "built $PWD/$APP"
