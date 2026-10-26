#!/usr/bin/env bash
# ==============================================================================
# stop.sh - Detiene limpiamente todos los procesos de TV Streamer
# ==============================================================================

echo "🛑 Deteniendo TV Streamer..."

# 1. Detener streaming en la Xiaomi TV vía ADB si está abierta
adb -s 100.90.61.47:5555 shell am force-stop org.videolan.vlc >/dev/null 2>&1 || true

# 2. Matar servidores de video en segundo plano
pkill -f "video_server.py" >/dev/null 2>&1 || true

# 3. Matar el servidor web de Streamlit
pkill -f "streamlit run app.py" >/dev/null 2>&1 || true

# 4. Asegurar que los puertos queden liberados
for port in 8080 8081 8082 8501; do
    pid=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
        kill -9 $pid 2>/dev/null || true
    fi
done

echo "✅ Todos los procesos de TV Streamer han sido cerrados y los puertos liberados."
osascript -e 'display notification "TV Streamer se ha detenido completamente." with title "📺 TV Streamer"' 2>/dev/null || true
