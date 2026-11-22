#!/usr/bin/env python3
"""
acestream_api.py — Mini servidor REST para el pipeline Acestream en el M4.
Escucha en :8891. Los clientes remotos (mando-tv en mbp1) llaman aquí.

Rutas:
  GET /play?hash=<40hex>        → lanza pipeline HLS → LG TV
  GET /play?slug=<slug>         → busca señales y lanza la primera
  GET /search?q=<query>         → devuelve señales JSON
  GET /status                   → estado del engine
"""
import sys
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import socketserver
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from stream_manager import (
    acestream_engine_running, acestream_engine_start,
    acestream_search_channels, acestream_hls_start,
    lgtv_webos_open_fullscreen, load_config, get_local_lan_ip,
)

PORT = 8891


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silenciar logs de acceso

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs  = urllib.parse.parse_qs(url.query)

        if url.path == "/status":
            self._json({"engine": acestream_engine_running()})

        elif url.path == "/search":
            q = qs.get("q", [""])[0].strip()
            self._json(acestream_search_channels(q) if q else [])

        elif url.path == "/play":
            ace_hash = qs.get("hash", [""])[0].strip()
            slug     = qs.get("slug", [""])[0].strip()

            if not ace_hash and not slug:
                self._json({"ok": False, "mensaje": "Falta hash o slug"}, 400)
                return

            # Respuesta inmediata; el pipeline corre en background (~15s)
            self._json({"ok": True, "mensaje": "Iniciando pipeline Acestream..."})

            def _run():
                h = ace_hash
                if not h and slug:
                    sigs = acestream_search_channels(slug)
                    if not sigs:
                        return
                    h = sigs[0]["hash"]
                if not acestream_engine_running():
                    acestream_engine_start()
                mac_ip = get_local_lan_ip()
                ok, player_url = acestream_hls_start(h, mac_ip)
                if ok:
                    cfg = load_config()
                    dev = cfg["devices"].get(cfg.get("active_device", ""), {})
                    host = dev.get("host", "192.168.1.193")
                    lgtv_webos_open_fullscreen(host, player_url)

            threading.Thread(target=_run, daemon=True).start()

        else:
            self._json({"error": "not found"}, 404)


class Server(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    srv = Server(("0.0.0.0", PORT), Handler)
    print(f"[acestream_api] Escuchando en :{PORT}")
    srv.serve_forever()
