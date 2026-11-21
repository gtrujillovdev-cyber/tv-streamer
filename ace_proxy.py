#!/usr/bin/env python3
"""
ace_proxy.py — Proxy HTTP que convierte el stream Acestream (con redirects internos a 127.0.0.1)
en un stream HTTP estable accesible desde la LG TV u otros dispositivos en la red.

Uso: python3 ace_proxy.py <hash_acestream> [puerto]
"""
import sys
import threading
import http.server
import urllib.request
import socket
import time

ACE_HOST   = "127.0.0.1"
ACE_PORT   = 6878
PROXY_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8889
ACE_HASH   = sys.argv[1] if len(sys.argv) > 1 else ""
CHUNK_SIZE = 65536
MAX_RETRIES = 10
RETRY_DELAY = 1.5


def get_acestream_url(ace_hash: str) -> str:
    """Sigue todos los redirects del engine y devuelve la URL final del contenido."""
    start_url = f"http://{ACE_HOST}:{ACE_PORT}/ace/getstream?id={ace_hash}"
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    req = urllib.request.Request(start_url, headers={"User-Agent": "VLC/3.0"})
    # Solo hacemos HEAD-equivalent siguiendo redirects para obtener URL final
    resp = opener.open(req, timeout=15)
    return resp.url, resp


class StreamHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[proxy] {self.address_string()} {fmt % args}")

    def do_GET(self):
        if not ACE_HASH:
            self.send_error(400, "No hash configured")
            return

        # Reintentar si el engine todavía no está sirviendo
        resp = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                _, resp = get_acestream_url(ACE_HASH)
                break
            except Exception as e:
                print(f"[proxy] Intento {attempt}/{MAX_RETRIES} fallido: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        if resp is None:
            self.send_error(502, "No se pudo conectar al engine Acestream")
            return

        self.send_response(200)
        self.send_header("Content-Type", "video/mp2t")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        print(f"[proxy] Sirviendo stream a {self.client_address[0]}...")
        try:
            while True:
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            print(f"[proxy] Cliente {self.client_address[0]} desconectado.")
        except Exception as e:
            print(f"[proxy] Error durante stream: {e}")
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "video/mp2t")
        self.end_headers()


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


if __name__ == "__main__":
    if not ACE_HASH:
        print("Uso: python3 ace_proxy.py <hash> [puerto]")
        sys.exit(1)

    local_ip = get_local_ip()
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PROXY_PORT), StreamHandler)
    print(f"[proxy] Escuchando en 0.0.0.0:{PROXY_PORT}")
    print(f"[proxy] URL para la TV: http://{local_ip}:{PROXY_PORT}/stream")
    print(f"[proxy] Hash: {ACE_HASH}")
    server.serve_forever()
