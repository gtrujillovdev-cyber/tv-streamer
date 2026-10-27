#!/usr/bin/env bash
# ==============================================================================
# TV Streamer - Generador de DMG para macOS
# Empaqueta la app nativa en un instalador .dmg con arrastrar a /Applications
# ==============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$PROJECT_DIR/dist"
STAGING_DIR="$PROJECT_DIR/build/dmg_staging"
APP_NAME="TV Streamer.app"
APP_SOURCE="$HOME/Applications/$APP_NAME"
[ ! -d "$APP_SOURCE" ] && APP_SOURCE="/Applications/$APP_NAME"

echo "=== Empaquetando TV Streamer en DMG para macOS ==="

if [ ! -d "$APP_SOURCE" ]; then
    echo "Compilando aplicación nativa primero..."
    mkdir -p "$HOME/Applications/$APP_NAME/Contents/MacOS" "$HOME/Applications/$APP_NAME/Contents/Resources"
    cat <<EOF > "$HOME/Applications/$APP_NAME/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>TV Streamer</string>
    <key>CFBundleDisplayName</key>
    <string>TV Streamer</string>
    <key>CFBundleIdentifier</key>
    <string>com.cyberdev.tvstreamer</string>
    <key>CFBundleVersion</key>
    <string>2.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>TV Streamer</string>
</dict>
</plist>
EOF
    cat <<EOF > "$HOME/Applications/$APP_NAME/Contents/MacOS/TV Streamer"
#!/usr/bin/env bash
cd "$PROJECT_DIR"
exec ./run.sh
EOF
    chmod +x "$HOME/Applications/$APP_NAME/Contents/MacOS/TV Streamer"
    APP_SOURCE="$HOME/Applications/$APP_NAME"
fi

# Preparar carpetas
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR" "$DIST_DIR"

echo "Copiando aplicación..."
cp -R "$APP_SOURCE" "$STAGING_DIR/"

echo "Creando acceso directo a /Applications..."
ln -s /Applications "$STAGING_DIR/Applications"

echo "Generando imagen de disco DMG comprimida..."
DMG_PATH="$DIST_DIR/TV-Streamer.dmg"
rm -f "$DMG_PATH"

hdiutil create -volname "TV Streamer" \
    -srcfolder "$STAGING_DIR" \
    -ov -format UDZO \
    "$DMG_PATH"

rm -rf "$PROJECT_DIR/build"

echo "=========================================================="
echo "🎉 ¡DMG generado con éxito!"
echo "Ubicación: $DMG_PATH"
echo "=========================================================="
