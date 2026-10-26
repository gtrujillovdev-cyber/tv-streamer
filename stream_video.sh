#!/usr/bin/env bash
# ==============================================================================
# stream_video.sh
# Transmite un video local mediante HTTP a través de Tailscale y lo lanza por SSH o ADB
# en un dispositivo remoto (Xiaomi TV, Raspberry Pi, Mac).
# ==============================================================================

set -e

DEFAULT_PORT=8080
DEFAULT_DEST_HOST="100.90.61.47" # Xiaomi TV
DEFAULT_DEST_USER=""

show_usage() {
    cat <<EOF
Uso:
  ./stream_video.sh <ruta_al_video> [host_o_user@host] [tipo: android|linux|mac]

Ejemplos:
  ./stream_video.sh ~/Movies/pelicula.mp4 100.90.61.47 android   # Xiaomi TV
  ./stream_video.sh ~/Movies/pelicula.mp4 raspberry@100.95.199.1 linux # Raspberry Pi
  ./stream_video.sh ~/Movies/pelicula.mp4 gtrujillo@100.108.212.124 mac

EOF
    exit 1
}

if [ -z "$1" ]; then
    show_usage
fi

VIDEO_PATH="$1"

if [ ! -f "$VIDEO_PATH" ]; then
    echo "❌ Error: El archivo '$VIDEO_PATH' no existe."
    exit 1
fi

DEST_TARGET="${2:-$DEFAULT_DEST_HOST}"
OS_TYPE="${3:-auto}"

if [[ "$DEST_TARGET" == *"@"* ]]; then
    REMOTE_USER="${DEST_TARGET%%@*}"
    REMOTE_HOST="${DEST_TARGET##*@}"
else
    REMOTE_USER="$DEFAULT_DEST_USER"
    REMOTE_HOST="$DEST_TARGET"
fi

# Detectar automáticamente si es la Xiaomi TV
if [ "$REMOTE_HOST" = "100.90.61.47" ] || [ "$REMOTE_HOST" = "tv" ]; then
    OS_TYPE="android"
fi

MY_TAILSCALE_IP=$(ifconfig | awk '/inet 100\./ {print $2; exit}')
if [ -z "$MY_TAILSCALE_IP" ]; then
    MY_TAILSCALE_IP="100.108.32.67"
fi

PORT=$DEFAULT_PORT
while lsof -i :$PORT >/dev/null 2>&1; do
    PORT=$((PORT + 1))
done

VIDEO_DIR="$(cd "$(dirname "$VIDEO_PATH")" && pwd)"
VIDEO_FILENAME="$(basename "$VIDEO_PATH")"

ENCODED_FILENAME=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$VIDEO_FILENAME")
STREAM_URL="http://${MY_TAILSCALE_IP}:${PORT}/${ENCODED_FILENAME}"

echo "=========================================================="
echo "🎬 Streaming Tailscale -> $REMOTE_HOST"
echo "=========================================================="
echo "📁 Archivo:     $VIDEO_FILENAME"
echo "🌐 IP Emisor:   $MY_TAILSCALE_IP"
echo "🔌 Puerto HTTP: $PORT"
echo "🎯 Destino:     $REMOTE_HOST ($OS_TYPE)"
echo "🔗 URL Stream:  $STREAM_URL"
echo "=========================================================="

cd "$VIDEO_DIR"
python3 -m http.server "$PORT" > /dev/null 2>&1 &
SERVER_PID=$!

cleanup() {
    echo ""
    echo "🛑 Deteniendo streaming..."
    kill "$SERVER_PID" 2>/dev/null || true
    if [ "$OS_TYPE" = "android" ]; then
        adb -s "$REMOTE_HOST:5555" shell am force-stop org.videolan.vlc 2>/dev/null || true
    fi
    echo "✅ Servidor detenido."
    exit 0
}
trap cleanup EXIT INT TERM

sleep 1

if [ "$OS_TYPE" = "android" ]; then
    echo "🚀 Conectando a Xiaomi TV por ADB y lanzando reproductor..."
    adb connect "$REMOTE_HOST:5555" >/dev/null 2>&1
    adb -s "$REMOTE_HOST:5555" shell am start -n org.videolan.vlc/.gui.video.VideoPlayerActivity -d "$STREAM_URL" >/dev/null 2>&1 || \
    adb -s "$REMOTE_HOST:5555" shell am start -a android.intent.action.VIEW -d "$STREAM_URL" -t "video/*" >/dev/null 2>&1
elif [ "$OS_TYPE" = "linux" ]; then
    echo "🚀 Conectando a $REMOTE_HOST por SSH..."
    ssh -o ConnectTimeout=6 "$REMOTE_USER@$REMOTE_HOST" "export DISPLAY=:0; (vlc '$STREAM_URL' --fullscreen --play-and-exit 2>/dev/null || mpv '$STREAM_URL' --fs 2>/dev/null)" &
else
    echo "🚀 Conectando a Mac por SSH..."
    ssh -o ConnectTimeout=6 "$REMOTE_USER@$REMOTE_HOST" "open -a VLC '$STREAM_URL' 2>/dev/null || open '$STREAM_URL'" &
fi

echo ""
echo "✨ ¡El video se está reproduciendo en la pantalla! Presiona [ENTER] o Ctrl+C para detener."
read -r _ || true
