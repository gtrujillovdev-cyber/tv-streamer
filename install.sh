#!/usr/bin/env bash
# ==============================================================================
# TV Streamer - Universal Installer for macOS & Linux
# https://github.com/gtrujillovdev-cyber/tv-streamer
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BLUE}${BOLD}"
echo "=========================================================="
echo "          📺 TV STREAMER - INSTALADOR UNIVERSAL           "
echo "=========================================================="
echo -e "${NC}"

OS="$(uname -s)"
INSTALL_DIR="$HOME/.tv-streamer"

# 1. Comprobar o clonar repositorio
if [ -f "app.py" ] && [ -f "video_server.py" ]; then
    PROJECT_DIR="$(pwd)"
    echo -e "${GREEN}✓ Ejecutando desde el repositorio local: ${PROJECT_DIR}${NC}"
else
    echo -e "${YELLOW}➜ Clonando TV Streamer en ${INSTALL_DIR}...${NC}"
    if [ -d "$INSTALL_DIR" ]; then
        cd "$INSTALL_DIR" && git pull origin main
    else
        git clone https://github.com/gtrujillovdev-cyber/tv-streamer.git "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
    PROJECT_DIR="$INSTALL_DIR"
fi

cd "$PROJECT_DIR"

# 2. Comprobar dependencias del sistema
echo -e "\n${BOLD}1. Verificando dependencias del sistema...${NC}"

if [ "$OS" = "Darwin" ]; then
    # macOS
    if ! command -v brew >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️ Homebrew no está instalado. Se recomienda instalarlo desde https://brew.sh${NC}"
    fi

    # Comprobar Python3
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}✗ Python 3 no está instalado. Instálalo con: brew install python3${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Python 3 detectado: $(python3 --version)${NC}"

    # Comprobar adb
    if ! command -v adb >/dev/null 2>&1; then
        echo -e "${YELLOW}➜ Instalando Android Platform Tools (adb) vía brew...${NC}"
        brew install --cask android-platform-tools || brew install android-platform-tools || true
    fi
    if command -v adb >/dev/null 2>&1; then
        echo -e "${GREEN}✓ ADB detectado: $(adb version | head -n 1)${NC}"
    else
        echo -e "${YELLOW}⚠️ ADB no encontrado. Es necesario para controlar la TV automáticamente.${NC}"
    fi

    # Comprobar ffmpeg
    if ! command -v ffmpeg >/dev/null 2>&1; then
        echo -e "${YELLOW}➜ Instalando ffmpeg para miniaturas vía brew...${NC}"
        brew install ffmpeg || true
    fi
    if command -v ffmpeg >/dev/null 2>&1; then
        echo -e "${GREEN}✓ ffmpeg detectado${NC}"
    fi

elif [ "$OS" = "Linux" ]; then
    # Linux (Debian / Ubuntu / Raspberry Pi OS)
    echo -e "${GREEN}✓ Sistema Linux detectado.${NC}"
    if command -v apt-get >/dev/null 2>&1; then
        echo -e "${YELLOW}➜ Verificando adb, ffmpeg y python3-pip...${NC}"
        sudo apt-get update -y && sudo apt-get install -y adb ffmpeg python3-pip python3-venv || true
    fi
fi

# 3. Entorno virtual o dependencias de Python
echo -e "\n${BOLD}2. Instalando dependencias de Python...${NC}"
python3 -m pip install -r requirements.txt --quiet || pip3 install -r requirements.txt --quiet
echo -e "${GREEN}✓ Dependencias de Python listas (Streamlit, Pillow, requests).${NC}"

# 4. Configuración inicial
echo -e "\n${BOLD}3. Configuración inicial...${NC}"
if [ ! -f "config.json" ]; then
    if [ -f "config.example.json" ]; then
        cp config.example.json config.json
        echo -e "${GREEN}✓ Archivo de configuración config.json creado a partir de la plantilla.${NC}"
    fi
fi

# 5. Accesos directos y Lanzador
echo -e "\n${BOLD}4. Creando accesos directos y lanzadores...${NC}"

# Scripts ejecutables
chmod +x run.sh stop.sh stream_video.sh 2>/dev/null || true

# Configurar alias en shell
SHELL_RC="$HOME/.zshrc"
[ ! -f "$SHELL_RC" ] && SHELL_RC="$HOME/.bashrc"

if [ -f "$SHELL_RC" ]; then
    if ! grep -q "tv-streamer" "$SHELL_RC"; then
        echo "" >> "$SHELL_RC"
        echo "# TV Streamer Aliases" >> "$SHELL_RC"
        echo "alias tv=\"cd '$PROJECT_DIR' && ./run.sh\"" >> "$SHELL_RC"
        echo "alias tvstreamer=\"cd '$PROJECT_DIR' && ./run.sh\"" >> "$SHELL_RC"
        echo "alias tv-stop=\"cd '$PROJECT_DIR' && ./stop.sh\"" >> "$SHELL_RC"
        echo -e "${GREEN}✓ Aliases 'tv', 'tvstreamer' y 'tv-stop' añadidos a ${SHELL_RC}${NC}"
    else
        echo -e "${GREEN}✓ Aliases ya configurados en ${SHELL_RC}${NC}"
    fi
fi

# En macOS, crear TV Streamer.app en ~/Applications
if [ "$OS" = "Darwin" ]; then
    APP_DIR="$HOME/Applications/TV Streamer.app"
    mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

    cat <<EOF > "$APP_DIR/Contents/Info.plist"
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
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

    cat <<EOF > "$APP_DIR/Contents/MacOS/TV Streamer"
#!/usr/bin/env bash
cd "$PROJECT_DIR"
exec ./run.sh
EOF
    chmod +x "$APP_DIR/Contents/MacOS/TV Streamer"

    # Copiar icono si existe
    if [ -f "$HOME/Applications/TV Streamer.app/Contents/Resources/AppIcon.icns" ]; then
        cp "$HOME/Applications/TV Streamer.app/Contents/Resources/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns" 2>/dev/null || true
    fi

    # Registrar en Launchpad
    /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_DIR" 2>/dev/null || true
    echo -e "${GREEN}✓ Aplicación macOS creada en ${APP_DIR} y registrada en el Launchpad.${NC}"
fi

echo -e "\n${GREEN}${BOLD}=========================================================="
echo "          🎉 ¡INSTALACIÓN COMPLETADA CON ÉXITO!          "
echo "=========================================================="
echo -e "${NC}"
echo -e "Puedes iniciar TV Streamer de cualquiera de las siguientes formas:"
echo -e "  1. Ejecuta el comando ${BOLD}tv${NC} en cualquier terminal."
echo -e "  2. Abre ${BOLD}TV Streamer${NC} desde el Launchpad o Spotlight en tu Mac."
echo -e "  3. Abre tu navegador en ${BOLD}http://localhost:8501${NC}"
echo ""
echo -e "Para detenerlo: escribe ${BOLD}tv-stop${NC} en la terminal o pulsa 'Apagar' en la app."
echo ""
