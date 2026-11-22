"""Pipeline Acestream → HLS → LG WebOS (autónomo, sin dependencias de stream_manager)."""
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

ACESTREAM_ENGINE_PORT = 6878
ACESTREAM_PROXY_PORT  = 8889
HLS_PORT              = 8890
HLS_DIR               = Path("/tmp/hls_tvstreamer")

_ace_proxy_proc  = None
_hls_ffmpeg_proc = None
_hls_http_proc   = None


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _mac_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def engine_running() -> bool:
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", "acestream"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() == "true"
    except Exception:
        return False


def engine_start() -> bool:
    if engine_running():
        return True
    try:
        subprocess.run(["docker", "start", "acestream"], capture_output=True, timeout=10)
        time.sleep(3)
        if engine_running():
            return True
    except Exception:
        pass
    try:
        subprocess.run(
            ["docker", "run", "-d", "--name", "acestream",
             "-p", f"{ACESTREAM_ENGINE_PORT}:{ACESTREAM_ENGINE_PORT}",
             "--platform", "linux/amd64", "jopsis/acestream:latest"],
            capture_output=True, timeout=90, check=True
        )
        time.sleep(5)
        return True
    except Exception:
        return False


def proxy_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", ACESTREAM_PROXY_PORT)) == 0


def proxy_start(ace_hash: str) -> bool:
    global _ace_proxy_proc
    # Buscar ace_proxy.py relativo a este paquete (en el proyecto Tv-streamer)
    proxy_script = Path(__file__).parent.parent / "ace_proxy.py"
    if not proxy_script.exists():
        return False
    if _ace_proxy_proc and _ace_proxy_proc.poll() is None:
        _ace_proxy_proc.terminate()
        time.sleep(0.3)
    subprocess.run(["pkill", "-f", "ace_proxy.py"], capture_output=True)
    time.sleep(0.3)
    _ace_proxy_proc = subprocess.Popen(
        [sys.executable, str(proxy_script), ace_hash, str(ACESTREAM_PROXY_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    for _ in range(10):
        time.sleep(0.5)
        if proxy_running():
            return True
    return False


def hls_start(ace_hash: str) -> str | None:
    """
    Arranca el pipeline HLS completo. Devuelve la URL del player.html o None si falla.
    """
    global _hls_ffmpeg_proc, _hls_http_proc

    mac_ip = _mac_ip()

    if not engine_running() and not engine_start():
        return None

    if not proxy_running() and not proxy_start(ace_hash):
        return None

    HLS_DIR.mkdir(parents=True, exist_ok=True)

    if _hls_ffmpeg_proc and _hls_ffmpeg_proc.poll() is None:
        _hls_ffmpeg_proc.terminate()
        time.sleep(0.3)
    subprocess.run(["pkill", "-f", "hls_tvstreamer"], capture_output=True)
    time.sleep(0.2)

    _hls_ffmpeg_proc = subprocess.Popen(
        ["ffmpeg", "-y",
         "-user_agent", "Mozilla/5.0",
         "-i", f"http://127.0.0.1:{ACESTREAM_PROXY_PORT}/stream",
         "-c:v", "copy", "-c:a", "copy",
         "-f", "hls", "-hls_time", "2", "-hls_list_size", "5",
         "-hls_flags", "delete_segments",
         "-hls_segment_filename", str(HLS_DIR / "seg%03d.ts"),
         str(HLS_DIR / "stream.m3u8")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    player_html = HLS_DIR / "player.html"
    player_html.write_text(
        "<!DOCTYPE html><html><head><style>"
        "* { margin:0; padding:0; box-sizing:border-box; }"
        "body { background:#000; overflow:hidden; width:100vw; height:100vh; }"
        "video { width:100vw; height:100vh; object-fit:contain; }"
        "</style></head><body>"
        '<video id="v" src="stream.m3u8" autoplay playsinline muted></video>'
        "<script>"
        "var v=document.getElementById('v');"
        "v.muted=false;v.volume=1.0;v.play().catch(function(){});"
        "(document.documentElement.requestFullscreen||document.documentElement.webkitRequestFullscreen||function(){}).call(document.documentElement);"
        "v.addEventListener('loadeddata',function(){"
        "(v.requestFullscreen||v.webkitRequestFullscreen||function(){}).call(v);v.play();"
        "});"
        "</script></body></html>"
    )

    if _hls_http_proc and _hls_http_proc.poll() is None:
        _hls_http_proc.terminate()
        time.sleep(0.2)
    _hls_http_proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(HLS_PORT), "--directory", str(HLS_DIR)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    m3u8 = HLS_DIR / "stream.m3u8"
    for _ in range(30):
        time.sleep(0.5)
        if m3u8.exists() and m3u8.stat().st_size > 0:
            return f"http://{mac_ip}:{HLS_PORT}/player.html"

    return None


def hls_stop():
    global _hls_ffmpeg_proc, _hls_http_proc, _ace_proxy_proc
    for p in (_hls_ffmpeg_proc, _hls_http_proc, _ace_proxy_proc):
        if p and p.poll() is None:
            p.terminate()
    _hls_ffmpeg_proc = _hls_http_proc = _ace_proxy_proc = None
    subprocess.run(["pkill", "-f", "hls_tvstreamer"], capture_output=True)
    subprocess.run(["pkill", "-f", "ace_proxy.py"], capture_output=True)


def search_channels(query: str) -> list:
    """Busca canales en acestreamid.com. Devuelve [{name, hash}]."""
    import html as _html
    slug = query.lower().strip().replace(" ", "-")
    results = []
    seen: set = set()
    for url in [f"https://acestreamid.com/channel/{slug}",
                f"https://acestreamid.com/channel/{query.lower().strip().replace(' ', '')}"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8, context=_ssl_ctx()) as r:
                body = r.read().decode("utf-8", errors="ignore")
            blocks = re.findall(r'href=["\']acestream://([a-f0-9]{40})["\']', body, re.IGNORECASE)
            name_blocks = re.findall(
                r'([\w\s\-/&#;]{2,60})\s*</[^>]+>\s*.*?acestream://([a-f0-9]{40})',
                body, re.DOTALL | re.IGNORECASE
            )
            name_map = {h: _html.unescape(re.sub(r'\s+', ' ', n).strip()) for n, h in name_blocks if h}
            for h in blocks:
                if h not in seen:
                    seen.add(h)
                    results.append({"name": name_map.get(h, f"{query.capitalize()} #{len(results)+1}"), "hash": h})
            if not results:
                for h in list(dict.fromkeys(re.findall(r'[a-f0-9]{40}', body))):
                    if h not in seen:
                        seen.add(h)
                        results.append({"name": f"{query.capitalize()}" if not results else f"{query.capitalize()} #{len(results)+1}", "hash": h})
        except Exception:
            continue
    return results
