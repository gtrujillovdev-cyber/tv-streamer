#!/usr/bin/env bash
# ==============================================================================
# Lanzador de TV Streamer
# Inicia la interfaz web en 0.0.0.0:8501 para que puedas usarla desde tu Mac,
# tu iPhone/iPad o cualquier otro dispositivo conectado a tu red Tailscale.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Detectar el binario de Python adecuado
if command -v python3 >/dev/null 2>&1 && python3 -c "import streamlit" >/dev/null 2>&1; then
    PY_CMD="python3"
elif /usr/local/bin/python3 -c "import streamlit" >/dev/null 2>&1; then
    PY_CMD="/usr/local/bin/python3"
elif command -v streamlit >/dev/null 2>&1; then
    PY_CMD=""
else
    PY_CMD="python3"
fi

TS_IP=$(ifconfig | awk '/inet 100\./ {print $2; exit}')
if [ -z "$TS_IP" ]; then
    TS_IP="100.108.32.67"
fi

echo "=========================================================="
echo "📺  Iniciando TV Streamer Web UI..."
echo "=========================================================="
echo "💻  En este Mac:           http://localhost:8501"
echo "📱  Desde tu Móvil / Red:  http://${TS_IP}:8501"
echo "=========================================================="
echo ""

if [ -n "$PY_CMD" ]; then
    exec "$PY_CMD" -m streamlit run app.py \
        --server.address 0.0.0.0 \
        --server.port 8501 \
        --server.headless true \
        --theme.base "dark" \
        --theme.primaryColor "#6366f1"
else
    exec streamlit run app.py \
        --server.address 0.0.0.0 \
        --server.port 8501 \
        --server.headless true \
        --theme.base "dark" \
        --theme.primaryColor "#6366f1"
fi
