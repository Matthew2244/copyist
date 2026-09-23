#!/bin/bash
# Build Copyist.app — the real Mac app over the same engine.
#
#   app/build.sh              build into app/build/Copyist.app
#   app/build.sh --install    build, then replace /Applications/Copyist.app
#
# The engine (prototype/*.py) and fonts are bundled into Resources so
# the app is self-contained; a checkout at ~/copyist still wins at
# runtime so development stays live. Ad-hoc signed, like every local
# build on this Mac.
set -euo pipefail
cd "$(dirname "$0")/.."

APP="app/build/Copyist.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/prototype" \
         "$APP/Contents/Resources/fonts"

echo "compiling…"
swiftc -O -swift-version 5 -parse-as-library \
    app/CopyistApp.swift -o "$APP/Contents/MacOS/Copyist"

echo "bundling the engine…"
cp prototype/*.py "$APP/Contents/Resources/prototype/"
cp -R fonts/. "$APP/Contents/Resources/fonts/"

echo "drawing the icon…"
ICONSET="app/build/Copyist.iconset"
rm -rf "$ICONSET"
swift app/make-icon.swift "$ICONSET" >/dev/null
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Copyist.icns"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>Copyist</string>
    <key>CFBundleDisplayName</key>     <string>Copyist</string>
    <key>CFBundleIdentifier</key>      <string>net.matthewwhitaker.copyist</string>
    <key>CFBundleExecutable</key>      <string>Copyist</string>
    <key>CFBundleIconFile</key>        <string>Copyist</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleShortVersionString</key> <string>2.4.1</string>
    <key>CFBundleVersion</key>         <string>2.4.1</string>
    <key>LSMinimumSystemVersion</key>  <string>13.0</string>
    <key>NSPrincipalClass</key>        <string>NSApplication</string>
    <key>NSHighResolutionCapable</key> <true/>
</dict>
</plist>
PLIST

codesign --force --deep -s - "$APP"
echo "built $APP"

if [ "${1:-}" = "--install" ]; then
    rm -rf /Applications/Copyist.app
    ditto "$APP" /Applications/Copyist.app
    echo "installed to /Applications/Copyist.app"
fi
