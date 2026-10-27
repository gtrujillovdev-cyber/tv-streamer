import os
import sys
import subprocess
import json
import time
import socket
import hashlib
import re
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "tv-streamer"
THUMBS_DIR = CACHE_DIR / "thumbs"
HISTORY_FILE = CACHE_DIR / "history.json"
CONFIG_FILE = Path(__file__).parent / "config.json"
VIDEO_SERVER_SCRIPT = Path(__file__).parent / "video_server.py"

DEFAULT_CONFIG = {
    "video_directories": [
        str(Path.home() / "Movies"),
        str(Path.home() / "Downloads"),
        str(Path.home() / "Desktop")
    ],
    "devices": {
        "TV (Xiaomi)": {
            "host": "100.90.61.47",
            "lan_ip": "192.168.1.208",
            "user": "",
            "os_type": "android",
            "player": "vlc",
            "display": ""
        }
    },
    "active_device": "TV (Xiaomi)",
    "http_port": 8080
}

def load_config():
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if "devices" not in cfg or not cfg["devices"]:
                cfg["devices"] = DEFAULT_CONFIG["devices"]
            return cfg
    except Exception:
        return DEFAULT_CONFIG

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

def get_tailscale_ip():
    try:
        res = subprocess.check_output(
            "ifconfig | awk '/inet 100\\./ {print $2; exit}'",
            shell=True,
            text=True
        ).strip()
        if res:
            return res
    except Exception:
        pass
    return "100.108.32.67"

def get_local_lan_ip(target_host: str = None) -> str:
    """Detecta la IP local de este Mac en la red LAN hacia el host destino o el router."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        dest = target_host if (target_host and not target_host.startswith("100.")) else "192.168.1.1"
        s.connect((dest, 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"

def get_tailscale_peers():
    peers = {}
    try:
        out = subprocess.check_output(["tailscale", "status", "--json"], timeout=3)
        data = json.loads(out)
        for _, peer in data.get("Peer", {}).items():
            name = peer.get("HostName", "")
            ips = peer.get("TailscaleIPs", [])
            ipv4 = ips[0] if ips else ""
            os_name = peer.get("OS", "linux").lower()
            online = peer.get("Online", False)
            peers[name] = {
                "name": name,
                "ip": ipv4,
                "os": os_name,
                "online": online,
            }
    except Exception:
        pass
    return peers

def clean_title(filename: str) -> str:
    """Limpia nombres de archivos eliminando hashes, tags técnicos y formatos."""
    name = Path(filename).stem
    # Eliminar hashes o identificadores como #abc1234
    name = re.sub(r'#[a-zA-Z0-9_-]+', '', name)
    # Eliminar tags comunes como [1080p], (720p), [x264], [AAC], etc.
    name = re.sub(r'\[.*?\]|\(.*?\)', '', name)
    # Reemplazar puntos o guiones bajos por espacios
    name = re.sub(r'[_.]+', ' ', name)
    # Limpiar espacios repetidos
    name = re.sub(r'\s+', ' ', name).strip()
    return name if name else Path(filename).stem

def get_history() -> list:
    """Recupera el historial de videos reproducidos recientemente."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [item for item in data if Path(item.get("path", "")).exists()]
    except Exception:
        return []

def add_to_history(video_path: str, size_str: str = ""):
    """Añade un video al historial de reproducción."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        history = get_history()
        vpath = str(Path(video_path).resolve())
        history = [h for h in history if str(Path(h.get("path", "")).resolve()) != vpath]
        history.insert(0, {
            "name": Path(video_path).name,
            "title": clean_title(Path(video_path).name),
            "path": vpath,
            "size": size_str,
            "played_at": int(time.time())
        })
        history = history[:12]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

def clear_history():
    """Limpia el historial de reproducción."""
    try:
        if HISTORY_FILE.exists():
            HISTORY_FILE.unlink()
    except Exception:
        pass

def discover_android_tvs():
    """Descubre Smart TVs y dispositivos Android TV en la red local y Tailscale."""
    found = {}

    # 1. Chequear dispositivos ya conectados por ADB
    try:
        out = subprocess.check_output(["adb", "devices", "-l"], text=True, timeout=3)
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                model = "Android TV"
                for p in parts[2:]:
                    if p.startswith("model:"):
                        model = p.split(":")[1].replace("_", " ")
                host = serial.split(":")[0] if ":" in serial else serial
                found[f"ADB: {model} ({host})"] = {
                    "host": host,
                    "os_type": "android",
                    "player": "vlc",
                    "type": "adb_connected"
                }
    except Exception:
        pass

    # 2. Tailscale peers
    ts_peers = get_tailscale_peers()
    for name, data in ts_peers.items():
        if data.get("os") in ("android", "linux"):
            found[f"Tailscale: {name}"] = {
                "host": data.get("ip"),
                "os_type": data.get("os", "android"),
                "player": "vlc",
                "type": "tailscale"
            }

    # 3. Escaneo rápido de mDNS de ADB si está disponible
    try:
        mdns_out = subprocess.check_output(["adb", "mdns", "services"], text=True, timeout=2)
        for line in mdns_out.splitlines():
            if "_adb-tls-connect._tcp" in line or "_adb._tcp" in line:
                parts = line.split()
                if len(parts) >= 3:
                    ip_port = parts[2]
                    ip = ip_port.split(":")[0]
                    found[f"Auto-mDNS: Android TV ({ip})"] = {
                        "host": ip,
                        "os_type": "android",
                        "player": "vlc",
                        "type": "mdns"
                    }
    except Exception:
        pass

    return found

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

def get_available_port(start_port=8080):
    port = start_port
    while is_port_in_use(port):
        port += 1
    return port

def get_thumbnail(video_path: Path) -> str:
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        file_stat = video_path.stat()
        cache_key = hashlib.md5(f"{video_path}_{file_stat.st_mtime}".encode()).hexdigest()
        thumb_path = THUMBS_DIR / f"{cache_key}.jpg"

        if thumb_path.exists():
            return str(thumb_path)

        cmd = [
            "ffmpeg", "-y",
            "-ss", "00:00:05",
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", "scale=360:-1",
            "-q:v", "3",
            str(thumb_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        if thumb_path.exists() and thumb_path.stat().st_size > 0:
            return str(thumb_path)
    except Exception:
        pass
    return ""

def scan_videos(directories, extensions=(".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v")):
    videos = []
    for d_str in directories:
        d = Path(os.path.expanduser(d_str))
        if not d.is_dir():
            continue
        try:
            for root, _, files in os.walk(d):
                if "/." in root or "\\." in root:
                    continue
                for f in files:
                    if any(f.lower().endswith(ext) for ext in extensions):
                        full_path = Path(root) / f
                        try:
                            st = full_path.stat()
                            size_mb = round(st.st_size / (1024 * 1024), 1)
                            size_str = f"{size_mb} MB" if size_mb < 1000 else f"{round(size_mb/1024, 2)} GB"
                            ext = full_path.suffix.lstrip(".").upper()
                            videos.append({
                                "name": f,
                                "title": clean_title(f),
                                "path": str(full_path),
                                "folder": str(Path(root)),
                                "size": size_str,
                                "size_bytes": st.st_size,
                                "mtime": st.st_mtime,
                                "ext": ext
                            })
                        except Exception:
                            continue
        except Exception:
            continue
    videos.sort(key=lambda x: x["mtime"], reverse=True)
    return videos

class StreamController:
    _instance = None

    def __init__(self):
        self.server_proc = None
        self.current_video = None
        self.current_url = None
        self.current_port = None
        self.current_device = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = StreamController()
        return cls._instance

    def send_remote_key(self, key: str, device_info: dict = None):
        """Envía comandos de control remoto multimedia a la TV vía ADB."""
        dev = device_info or self.current_device
        if not dev:
            return False, "No hay dispositivo seleccionado"

        host = dev.get("host", "").strip()
        if not host:
            return False, "No se ha configurado la dirección IP del dispositivo"

        adb_target = f"{host}:5555" if ":5555" not in host else host

        KEY_MAP = {
            "play_pause": "KEYCODE_MEDIA_PLAY_PAUSE",
            "play": "KEYCODE_MEDIA_PLAY",
            "pause": "KEYCODE_MEDIA_PAUSE",
            "rewind": "KEYCODE_MEDIA_REWIND",
            "fast_forward": "KEYCODE_MEDIA_FAST_FORWARD",
            "vol_up": "KEYCODE_VOLUME_UP",
            "vol_down": "KEYCODE_VOLUME_DOWN",
            "mute": "KEYCODE_VOLUME_MUTE",
            "home": "KEYCODE_HOME",
            "back": "KEYCODE_BACK",
            "left": "KEYCODE_DPAD_LEFT",
            "right": "KEYCODE_DPAD_RIGHT",
            "up": "KEYCODE_DPAD_UP",
            "down": "KEYCODE_DPAD_DOWN",
            "select": "KEYCODE_DPAD_CENTER",
        }

        target_key = KEY_MAP.get(key, key)
        try:
            res = subprocess.run(
                ["adb", "-s", adb_target, "shell", "input", "keyevent", target_key],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3
            )
            return res.returncode == 0, f"Enviado {key}"
        except Exception as e:
            return False, f"Error enviando comando: {e}"

    def stop_stream(self, device_info=None):
        if self.server_proc:
            try:
                self.server_proc.terminate()
                self.server_proc.wait(timeout=2)
            except Exception:
                try:
                    self.server_proc.kill()
                except Exception:
                    pass
            self.server_proc = None

        # Matar cualquier proceso huérfano de video_server
        try:
            subprocess.run(["pkill", "-f", "video_server.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        dev = device_info or self.current_device
        if dev and dev.get("host"):
            host = dev["host"]
            os_type = dev.get("os_type", "android")
            if os_type == "android":
                adb_target = f"{host}:5555" if ":5555" not in host else host
                try:
                    subprocess.run(["adb", "-s", adb_target, "shell", "am", "force-stop", "org.videolan.vlc"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                except Exception:
                    pass

        self.current_video = None
        self.current_url = None
        self.current_device = None

    def start_stream(self, video_path: str, device_info: dict, port: int = 8080):
        self.stop_stream(device_info)

        vpath = Path(video_path)
        if not vpath.exists():
            return False, f"El archivo '{video_path}' no existe."

        host = device_info.get("host", "100.90.61.47").strip()
        lan_ip = device_info.get("lan_ip", "").strip()

        # Selección inteligente de IP de streaming:
        # Priorizar LAN directa si está disponible para 0 carga de CPU en la TV y máxima velocidad
        stream_ip = None
        candidate_lan = lan_ip or (host if not host.startswith("100.") else "192.168.1.208")

        if candidate_lan:
            try:
                lan_check = subprocess.run(["ping", "-c", "1", "-W", "1", candidate_lan],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if lan_check.returncode == 0:
                    stream_ip = get_local_lan_ip(candidate_lan)
            except Exception:
                pass

        if not stream_ip or stream_ip.startswith("127."):
            stream_ip = get_tailscale_ip()

        available_port = get_available_port(port)
        self.current_port = available_port

        # Iniciar servidor HTTP dedicado
        try:
            self.server_proc = subprocess.Popen(
                [sys.executable, str(VIDEO_SERVER_SCRIPT), str(available_port), str(vpath)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            return False, f"Error iniciando video_server: {e}"

        time.sleep(0.8)

        stream_url = f"http://{stream_ip}:{available_port}/video.mp4"
        self.current_url = stream_url
        self.current_video = str(vpath)
        self.current_device = device_info

        adb_target = f"{host}:5555" if ":5555" not in host else host

        try:
            # 1. Conectar ADB
            subprocess.run(["adb", "connect", adb_target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)

            # 2. Despertar la TV y limpiar instancias previas
            subprocess.run(["adb", "-s", adb_target, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            subprocess.run(["adb", "-s", adb_target, "shell", "am", "force-stop", "org.videolan.vlc"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            time.sleep(0.5)

            # 3. Lanzar VLC con aceleración por hardware, buffer de 4 segundos y tolerancia a jitter
            cmd = [
                "adb", "-s", adb_target, "shell",
                "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", stream_url,
                "-t", "video/mp4",
                "-f", "0x10000000",
                "--ei", "hardware_acceleration", "2",
                "--ei", "network-caching", "4000",
                "--es", "network-caching", "4000",
                "--ei", "clock-jitter", "2000",
                "--ei", "clock-synchro", "0",
                "org.videolan.vlc"
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=8)

            # 4. Enviar Play automático
            time.sleep(1.5)
            subprocess.run(["adb", "-s", adb_target, "shell", "input", "keyevent", "KEYCODE_MEDIA_PLAY"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)

            # 5. Registrar en historial
            try:
                st = vpath.stat()
                size_mb = round(st.st_size / (1024 * 1024), 1)
                size_str = f"{size_mb} MB" if size_mb < 1000 else f"{round(size_mb/1024, 2)} GB"
                add_to_history(str(vpath), size_str)
            except Exception:
                add_to_history(str(vpath))

            return True, stream_url
        except Exception as e:
            return False, f"Error comunicando con la TV: {e}"
