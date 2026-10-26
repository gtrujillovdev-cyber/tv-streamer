import os
import sys
import subprocess
import json
import time
import socket
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "tv-streamer"
THUMBS_DIR = CACHE_DIR / "thumbs"
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
                            videos.append({
                                "name": f,
                                "path": str(full_path),
                                "folder": str(Path(root)),
                                "size": size_str,
                                "size_bytes": st.st_size,
                                "mtime": st.st_mtime,
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

        # Seleccionar la mejor IP: LAN local si estamos en casa (más rápida y sin consumo de CPU) o Tailscale
        try:
            lan_check = subprocess.run(["ping", "-c", "1", "-W", "1", "192.168.1.208"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            stream_ip = "192.168.1.205" if lan_check.returncode == 0 else get_tailscale_ip()
        except Exception:
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

        host = device_info.get("host", "100.90.61.47").strip()
        adb_target = f"{host}:5555" if ":5555" not in host else host

        try:
            # 1. Conectar ADB
            subprocess.run(["adb", "connect", adb_target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)

            # 2. Despertar la Xiaomi TV y limpiar instancias previas
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

            return True, stream_url
        except Exception as e:
            return False, f"Error comunicando con Xiaomi TV: {e}"
