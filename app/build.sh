#!/bin/bash
# Build Copyist.app — the real Mac app over the same engine.
#
#   app/build.sh              build into app/build/Copyist.app
#   app/build.sh --install    build, then replace /Applications/Copyist.app
#
# The engine (prototype/*.py) and fonts are bundled into Resources so
# the app is self-contained; a checkout at ~/copyist still wins at
# runtime so development stays live. Ad-hoc signed, like every local
# build on this Mac, unless COPYIST_SIGN_ID names a Developer ID
# (tools/release_mac.sh sets it): then hardened runtime and a timestamp,
# ready for Apple's notary.
#
# Sparkle 2.10.0 is embedded for app updates: downloaded once into
# ~/Library/Caches/copyist-build, checked against its sha256. The app
# looks for updates itself and says so; Sparkle's window opens only
# from Copyist > Check for Updates.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(tr -d '[:space:]' < VERSION)
SIGN_ID="${COPYIST_SIGN_ID:-}"
SPARKLE_URL="https://github.com/sparkle-project/Sparkle/releases/download/2.10.0/Sparkle-2.10.0.tar.xz"
SPARKLE_SHA="c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c"
# the public half of the update-signing key; the private half is in the
# Studio's login Keychain (Sparkle's generate_keys), shared with Wavelength
SPARKLE_KEY="TJlHNK3idLU77+cj97Pwh4xeuvFhhIVm32CLFwN5Dz0="
FEED="${COPYIST_TEST_FEED:-https://github.com/Matthew2244/copyist/releases/latest/download/appcast.xml}"

CACHE="$HOME/Library/Caches/copyist-build/sparkle-2.10.0"
if [ ! -d "$CACHE/x/Sparkle.framework" ]; then
    echo "fetching Sparkle…"
    mkdir -p "$CACHE/x"
    curl -fsSL -o "$CACHE/Sparkle.tar.xz.part" "$SPARKLE_URL"
    got=$(shasum -a 256 "$CACHE/Sparkle.tar.xz.part" | cut -d' ' -f1)
    if [ "$got" != "$SPARKLE_SHA" ]; then
        rm -f "$CACHE/Sparkle.tar.xz.part"
        echo "Sparkle's download didn't match its checksum; run the build again." >&2
        exit 1
    fi
    tar -xf "$CACHE/Sparkle.tar.xz.part" -C "$CACHE/x"
    rm -f "$CACHE/Sparkle.tar.xz.part"
fi

APP="app/build/Copyist.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/prototype" \
         "$APP/Contents/Resources/fonts" "$APP/Contents/Frameworks"

echo "compiling…"
swiftc -O -swift-version 5 -parse-as-library \
    -F "$CACHE/x" -framework Sparkle \
    -Xlinker -rpath -Xlinker @executable_path/../Frameworks \
    app/CopyistApp.swift -o "$APP/Contents/MacOS/Copyist"

echo "embedding Sparkle…"
ditto "$CACHE/x/Sparkle.framework" "$APP/Contents/Frameworks/Sparkle.framework"
# the XPC services are for sandboxed apps; Copyist isn't one
rm -rf "$APP/Contents/Frameworks/Sparkle.framework/Versions/B/XPCServices"

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
    <key>CFBundleShortVersionString</key> <string>VERSION_HERE</string>
    <key>CFBundleVersion</key>         <string>VERSION_HERE</string>
    <key>LSMinimumSystemVersion</key>  <string>13.0</string>
    <key>NSPrincipalClass</key>        <string>NSApplication</string>
    <key>NSHighResolutionCapable</key> <true/>
    <key>SUFeedURL</key>               <string>FEED_HERE</string>
    <key>SUPublicEDKey</key>           <string>KEY_HERE</string>
    <key>SUEnableAutomaticChecks</key> <false/>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeName</key>      <string>Copyist chart</string>
            <key>CFBundleTypeRole</key>      <string>Editor</string>
            <key>LSHandlerRank</key>         <string>Owner</string>
            <key>LSItemContentTypes</key>
            <array><string>net.matthewwhitaker.copyist.chart</string></array>
        </dict>
    </array>
    <key>UTExportedTypeDeclarations</key>
    <array>
        <dict>
            <key>UTTypeIdentifier</key>      <string>net.matthewwhitaker.copyist.chart</string>
            <key>UTTypeDescription</key>     <string>Copyist chart</string>
            <key>UTTypeConformsTo</key>
            <array><string>public.plain-text</string></array>
            <key>UTTypeTagSpecification</key>
            <dict>
                <key>public.filename-extension</key>
                <array><string>chart</string></array>
            </dict>
        </dict>
    </array>
</dict>
</plist>
PLIST

sed -i '' -e "s|VERSION_HERE|$VERSION|g" -e "s|FEED_HERE|$FEED|" \
    -e "s|KEY_HERE|$SPARKLE_KEY|" "$APP/Contents/Info.plist"
if [ -n "${COPYIST_TEST_FEED:-}" ]; then   # a local test feed is plain http
    plutil -replace NSAppTransportSecurity -json \
        '{"NSAllowsLocalNetworking": true}' "$APP/Contents/Info.plist"
fi

if [ -n "$SIGN_ID" ]; then
    sign=(codesign --force --options runtime --timestamp --sign "$SIGN_ID")
else
    sign=(codesign --force --sign -)
fi
B="$APP/Contents/Frameworks/Sparkle.framework/Versions/B"
"${sign[@]}" "$B/Autoupdate"
"${sign[@]}" "$B/Updater.app"
"${sign[@]}" "$APP/Contents/Frameworks/Sparkle.framework"
"${sign[@]}" "$APP"
echo "built $APP"

if [ "${1:-}" = "--install" ]; then
    rm -rf /Applications/Copyist.app
    ditto "$APP" /Applications/Copyist.app
    echo "installed to /Applications/Copyist.app"
fi
