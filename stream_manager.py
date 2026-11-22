import os
import sys
import subprocess
import json
import time
import socket
import hashlib
import re
from pathlib import Path

try:
    import pychromecast
    HAS_PYCHROMECAST = True
except ImportError:
    HAS_PYCHROMECAST = False

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

def wake_tv(device_info: dict) -> tuple:
    """Envía la orden de encendido / despertar pantalla a la TV vía ADB."""
    if not device_info:
        return False, "No se ha seleccionado dispositivo"
    host = device_info.get("host", "").strip()
    if not host:
        return False, "No hay IP configurada para la TV"

    adb_target = f"{host}:5555" if ":5555" not in host else host
    try:
        subprocess.run(["adb", "connect", adb_target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        res = subprocess.run(
            ["adb", "-s", adb_target, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4
        )
        return (res.returncode == 0, "¡Señal enviada! Tu TV debería encenderse o salir del reposo.")
    except Exception as e:
        return False, f"Error enviando señal a la TV: {e}"

def test_tv_connection(device_info: dict) -> dict:
    """Comprobación de salud integral con la TV (Ping, Modo Cast, ADB y VLC)."""
    result = {
        "ping_ok": False,
        "ping_ms": None,
        "mode": "adb",
        "adb_ok": False,
        "vlc_ok": False,
        "cast_ok": False,
        "message": "",
        "details": []
    }
    if not device_info:
        result["message"] = "No hay ningún dispositivo seleccionado."
        return result

    host = device_info.get("host", "").strip()
    lan_ip = device_info.get("lan_ip", "").strip()
    target_ip = lan_ip or host
    is_cast = (device_info.get("mode") == "cast" or device_info.get("os_type") == "cast")
    result["mode"] = "cast" if is_cast else "adb"

    # 1. Comprobar Ping / Conectividad de red
    if target_ip:
        try:
            ping_out = subprocess.check_output(
                ["ping", "-c", "1", "-W", "1", target_ip],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2
            )
            result["ping_ok"] = True
            # Extraer tiempo en ms
            match = re.search(r'time=([\d.]+)\s*ms', ping_out)
            if match:
                result["ping_ms"] = float(match.group(1))
            result["details"].append(f"✅ Red Wi-Fi: Conectado a {target_ip} ({result['ping_ms'] or '<5'} ms de latencia)")
        except Exception:
            result["details"].append(f"⚠️ Red Wi-Fi: No responde al ping en {target_ip}. Comprueba que la TV esté encendida.")

    # 2. Comprobar modo Cast
    if is_cast and HAS_PYCHROMECAST:
        try:
            cast_name = device_info.get("cast_name", "")
            chromecasts, browser = pychromecast.get_chromecasts(tries=1, timeout=2.5)
            for cc in chromecasts:
                if (cast_name and cc.name == cast_name) or (target_ip and hasattr(cc, "cast_info") and cc.cast_info.host == target_ip):
                    result["cast_ok"] = True
                    result["details"].append(f"✅ Google Cast: TV detectada y lista para recibir vídeo sin cables.")
                    break
            browser.stop_discovery()
            if not result["cast_ok"]:
                result["details"].append("⚠️ Google Cast: No se localizó el receptor Cast en la red Wi-Fi.")
        except Exception as e:
            result["details"].append(f"⚠️ Google Cast: {e}")

    # 3. Comprobar modo ADB / VLC
    if not is_cast:
        adb_target = f"{host}:5555" if ":5555" not in host else host
        try:
            subprocess.run(["adb", "connect", adb_target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            state_out = subprocess.check_output(["adb", "-s", adb_target, "get-state"], text=True, timeout=2).strip()
            if state_out == "device":
                result["adb_ok"] = True
                result["details"].append("✅ Conexión de control: Autorizada y enlazada.")

                # Verificar VLC
                pm_out = subprocess.check_output(
                    ["adb", "-s", adb_target, "shell", "pm", "list", "packages", "org.videolan.vlc"],
                    text=True,
                    timeout=3
                )
                if "org.videolan.vlc" in pm_out:
                    result["vlc_ok"] = True
                    result["details"].append("✅ Reproductor VLC: Instalado y con aceleración lista.")
                else:
                    result["details"].append("ℹ️ VLC: No encontrado en la TV. Instala 'VLC for Android' desde la Play Store.")
            elif state_out == "unauthorized":
                result["details"].append("⚠️ Autorización pendiente: Mira la pantalla de tu TV y pulsa 'Permitir siempre'.")
            else:
                result["details"].append(f"⚠️ Estado ADB: {state_out}")
        except Exception:
            result["details"].append("⚠️ Control remoto: No se pudo conectar por ADB. Asegúrate de encender la TV.")

    # Mensaje global
    if (is_cast and result["cast_ok"]) or (not is_cast and result["adb_ok"] and result["vlc_ok"]):
        result["message"] = "🎉 ¡Todo listo! Tu tele está perfectamente conectada y lista para transmitir sin HDMI."
    elif result["ping_ok"]:
        result["message"] = "🟡 La tele está conectada al Wi-Fi pero falta un detalle de enlace."
    else:
        result["message"] = "🔴 No se detecta la televisión. Asegúrate de que esté encendida en el mismo Wi-Fi."

    return result

def discover_android_tvs():
    """Descubre Smart TVs y dispositivos en la red local (Google Cast, ADB y Tailscale)."""
    found = {}

    # 1. Google Cast / Chromecast (Zero-Config, sin opciones de desarrollador)
    if HAS_PYCHROMECAST:
        try:
            chromecasts, browser = pychromecast.get_chromecasts(tries=1, timeout=2.5)
            for cc in chromecasts:
                cast_name = cc.name or "Smart TV"
                host = cc.cast_info.host if hasattr(cc, "cast_info") else ""
                model = cc.model_name or "Google Cast"
                found[f"Cast: {cast_name} ({model})"] = {
                    "host": host,
                    "cast_name": cast_name,
                    "mode": "cast",
                    "os_type": "cast",
                    "player": "native",
                    "type": "chromecast"
                }
            browser.stop_discovery()
        except Exception:
            pass

    # 2. Chequear dispositivos ya conectados por ADB
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
        self.current_cast = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = StreamController()
        return cls._instance

    def send_remote_key(self, key: str, device_info: dict = None):
        """Envía comandos de control remoto multimedia (Chromecast o ADB)."""
        dev = device_info or self.current_device
        if not dev:
            return False, "No hay dispositivo seleccionado"

        # Modo Google Cast
        if self.current_cast:
            try:
                mc = self.current_cast.media_controller
                if key in ("play_pause", "pause", "play"):
                    if key == "pause" or (key == "play_pause" and mc.status.player_state == "PLAYING"):
                        mc.pause()
                    else:
                        mc.play()
                elif key == "rewind":
                    cur = mc.status.current_time or 0
                    mc.seek(max(0, cur - 10))
                elif key == "fast_forward":
                    cur = mc.status.current_time or 0
                    mc.seek(cur + 10)
                elif key == "vol_up":
                    self.current_cast.volume_up()
                elif key == "vol_down":
                    self.current_cast.volume_down()
                elif key == "mute":
                    self.current_cast.set_volume_muted(not self.current_cast.status.is_volume_muted)
                elif key in ("home", "stop"):
                    mc.stop()
                    self.current_cast.quit_app()
                return True, f"Comando Cast: {key}"
            except Exception as e:
                return False, f"Error en control Cast: {e}"

        # Modo ADB
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
        if self.current_cast:
            try:
                self.current_cast.media_controller.stop()
                self.current_cast.quit_app()
            except Exception:
                pass
            self.current_cast = None

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

        is_cast = (device_info.get("mode") == "cast" or device_info.get("os_type") == "cast")
        host = device_info.get("host", "100.90.61.47").strip()
        lan_ip = device_info.get("lan_ip", "").strip()

        # Selección inteligente de IP de streaming
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

        # MODO 1: GOOGLE CAST (Cero configuración, nativo)
        if is_cast and HAS_PYCHROMECAST:
            try:
                cast_name = device_info.get("cast_name", "")
                chromecasts, browser = pychromecast.get_chromecasts(tries=1, timeout=3)
                target_cc = None
                for cc in chromecasts:
                    if (cast_name and cc.name == cast_name) or (host and hasattr(cc, "cast_info") and cc.cast_info.host == host):
                        target_cc = cc
                        break
                browser.stop_discovery()

                if not target_cc and chromecasts:
                    target_cc = chromecasts[0]

                if not target_cc:
                    return False, f"No se encontró el dispositivo Cast '{cast_name or host}' en la red."

                target_cc.wait()
                mc = target_cc.media_controller
                mc.play_media(stream_url, "video/mp4")
                mc.block_until_active(timeout=5)
                mc.play()
                self.current_cast = target_cc

                # Historial
                try:
                    st = vpath.stat()
                    size_mb = round(st.st_size / (1024 * 1024), 1)
                    size_str = f"{size_mb} MB" if size_mb < 1000 else f"{round(size_mb/1024, 2)} GB"
                    add_to_history(str(vpath), size_str)
                except Exception:
                    add_to_history(str(vpath))

                return True, stream_url
            except Exception as e:
                return False, f"Error transmitiendo por Google Cast: {e}"

        # MODO 2: ADB + VLC (Modo Pro)
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

    def start_acestream(self, ace_hash: str, device_info: dict) -> tuple:
        """Reproduce un canal Acestream en el dispositivo configurado."""
        if not acestream_engine_running():
            ok, msg = acestream_engine_start()
            if not ok:
                return False, msg
            time.sleep(4)

        os_type = device_info.get("os_type", "android")
        host = device_info.get("host", "").strip()
        mac_ip = get_local_lan_ip()

        if os_type == "webos":
            # Pipeline HLS: proxy → ffmpeg → .m3u8 → player.html → LG browser
            ok, result = acestream_hls_start(ace_hash, mac_ip)
            if not ok:
                return False, f"Pipeline HLS falló: {result}"
            return lgtv_webos_open_fullscreen(host, result)

        # Para otros modos, URL directa del engine
        ok, stream_url = acestream_get_stream_url(ace_hash)
        if not ok:
            stream_url = f"http://{mac_ip}:{ACESTREAM_ENGINE_PORT}/ace/getstream?id={ace_hash}"

        if os_type == "cast" and HAS_PYCHROMECAST:
            try:
                cast_name = device_info.get("cast_name", "")
                chromecasts, browser = pychromecast.get_chromecasts(tries=1, timeout=3)
                target_cc = next((c for c in chromecasts if not cast_name or c.name == cast_name), None)
                browser.stop_discovery()
                if not target_cc:
                    return False, "Dispositivo Cast no encontrado"
                target_cc.wait()
                target_cc.media_controller.play_media(stream_url, "video/mp2t")
                target_cc.media_controller.block_until_active(timeout=5)
                return True, stream_url
            except Exception as e:
                return False, f"Error Cast: {e}"

        # ADB / Android fallback
        adb_target = f"{host}:5555" if ":5555" not in host else host
        try:
            subprocess.run(["adb", "connect", adb_target], capture_output=True, timeout=4)
            subprocess.run(
                ["adb", "-s", adb_target, "shell", "am", "start",
                 "-a", "android.intent.action.VIEW",
                 "-d", stream_url, "-t", "video/mp2t",
                 "-f", "0x10000000", "org.videolan.vlc"],
                capture_output=True, timeout=8
            )
            return True, stream_url
        except Exception as e:
            return False, f"Error ADB: {e}"


# =====================================================
# ACESTREAM ENGINE + LG TV WEBOS (via mando_tv)
# =====================================================
import asyncio
import urllib.request
import urllib.parse

ACESTREAM_ENGINE_IMAGE = "jopsis/acestream:latest"
ACESTREAM_ENGINE_NAME  = "acestream"
ACESTREAM_ENGINE_PORT  = 6878
LGTV_KEY_FILE          = Path.home() / ".lgtv_key"
HLS_DIR                = Path("/tmp/hls_tvstreamer")
HLS_PORT               = 8890

# --- Inicializar mando_tv con la IP/MAC de la TV webos de config.json ---
def _init_mando_tv():
    cfg = load_config()
    for dev in cfg.get("devices", {}).values():
        if dev.get("os_type") == "webos":
            ip  = dev.get("host", "").strip()
            mac = dev.get("mac", "74:e6:b8:26:02:0e").strip()
            if ip:
                os.environ["LG_TV_IP"]  = ip
            if mac:
                os.environ["LG_TV_MAC"] = mac
            break
    # Apuntar mando_tv al mismo fichero de clave que usamos nosotros (~/.lgtv_key)
    if str(LGTV_KEY_FILE) not in os.environ.get("LG_CONFIG", ""):
        os.environ["LG_CONFIG"] = str(LGTV_KEY_FILE)

_init_mando_tv()

try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    from mando_tv import lg as _lg
    from mando_tv.wol import enviar_wol as _enviar_wol
    from mando_tv.streaming import (
        reproducir_streaming, APPS_LG, NOMBRES_PLATAFORMAS, DIALES_MOVISTAR
    )
    from mando_tv.scenes import (
        modo_noche, modo_dia, modo_cine, modo_juego, modo_descanso,
        apagar_ambas_tvs, encender_ambas
    )
    from mando_tv.timers import obtener_tiempo_restante_timer
    HAS_MANDO_TV = True
except Exception as _e:
    HAS_MANDO_TV = False
    APPS_LG = {}
    NOMBRES_PLATAFORMAS = {}
    DIALES_MOVISTAR = {}
    print(f"[tv-streamer] mando_tv no disponible: {_e}")


def acestream_engine_running() -> bool:
    """Devuelve True si el contenedor Docker de Acestream está activo."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", ACESTREAM_ENGINE_NAME],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() == "true"
    except Exception:
        return False


def acestream_engine_start() -> tuple:
    """Inicia el engine Acestream en Docker. Devuelve (ok, mensaje)."""
    if acestream_engine_running():
        return True, "Engine ya en marcha"
    # Intentar arrancar contenedor existente parado
    try:
        subprocess.run(["docker", "start", ACESTREAM_ENGINE_NAME],
                       capture_output=True, timeout=10)
        time.sleep(3)
        if acestream_engine_running():
            return True, "Engine Acestream iniciado"
    except Exception:
        pass
    # Crear contenedor nuevo
    try:
        subprocess.run(
            ["docker", "run", "-d",
             "--name", ACESTREAM_ENGINE_NAME,
             "-p", f"{ACESTREAM_ENGINE_PORT}:{ACESTREAM_ENGINE_PORT}",
             "--platform", "linux/amd64",
             ACESTREAM_ENGINE_IMAGE],
            capture_output=True, timeout=90, check=True
        )
        time.sleep(5)
        return True, "Engine Acestream arrancado"
    except Exception as e:
        return False, f"Error iniciando Acestream: {e}"


def acestream_get_stream_url(ace_hash: str) -> tuple:
    """
    Obtiene la URL HTTP del stream para el hash. Devuelve (ok, url_o_error).
    La URL apunta a la IP LAN del Mac para que la TV pueda acceder.
    """
    mac_ip = get_local_lan_ip()
    api_url = f"http://127.0.0.1:{ACESTREAM_ENGINE_PORT}/ace/getstream?id={ace_hash}&format=json"
    try:
        with urllib.request.urlopen(api_url, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("error"):
            return False, f"Engine error: {data['error']}"
        url = (data["response"]["playback_url"]
               .replace("localhost", mac_ip)
               .replace("127.0.0.1", mac_ip))
        return True, url
    except Exception as e:
        # Fallback: URL directa (el navegador de la TV puede seguir los redirects)
        return True, f"http://{mac_ip}:{ACESTREAM_ENGINE_PORT}/ace/getstream?id={ace_hash}"


def _ssl_ctx():
    """Contexto SSL sin verificación de certificado (necesario en macOS sin certifi)."""
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def acestream_search_channels(query: str) -> list:
    """
    Busca canales en acestreamid.com.
    Devuelve lista de dicts con {name, hash}.
    """
    import html as _html
    slug = query.lower().strip().replace(" ", "-")
    urls_to_try = [
        f"https://acestreamid.com/channel/{slug}",
        f"https://acestreamid.com/channel/{query.lower().strip().replace(' ', '')}",
    ]
    results = []
    seen: set = set()

    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8, context=_ssl_ctx()) as r:
                body = r.read().decode("utf-8", errors="ignore")

            # Extraer bloques: texto de canal + hash acestream://
            blocks = re.findall(
                r'href=["\']acestream://([a-f0-9]{40})["\']',
                body, re.IGNORECASE
            )
            # Obtener nombres de canal del contexto HTML cercano
            name_blocks = re.findall(
                r'([\w\s\-/&#;]{2,60})\s*</[^>]+>\s*.*?acestream://([a-f0-9]{40})',
                body, re.DOTALL | re.IGNORECASE
            )
            name_map = {h: _html.unescape(re.sub(r'\s+', ' ', n).strip())
                        for n, h in name_blocks if h}

            for ace_hash in blocks:
                if ace_hash not in seen:
                    seen.add(ace_hash)
                    name = name_map.get(ace_hash, f"{query.capitalize()} #{len(results)+1}")
                    results.append({"name": name[:60], "hash": ace_hash})

            # Fallback: extraer todos los hashes de 40 chars si no hubo bloques
            if not results:
                all_hashes = list(dict.fromkeys(re.findall(r'[a-f0-9]{40}', body)))
                title_m = re.search(r'<h[12][^>]*>\s*([^<]{2,60})\s*</h', body)
                base_name = title_m.group(1).strip() if title_m else query.capitalize()
                for i, h in enumerate(all_hashes):
                    if h not in seen:
                        seen.add(h)
                        results.append({"name": f"{base_name}" if i == 0 else f"{base_name} #{i+1}", "hash": h})
        except Exception:
            continue

    return results


# --- Canales favoritos Acestream ---

ACE_CHANNELS_FILE = Path(__file__).parent / "canales_acestream.json"

_ACE_CHANNELS_DEFAULT = [
    {"name": "MotoGP",        "slug": "motogp",        "icon": "🏍️"},
    {"name": "Eurosport 1",   "slug": "eurosport",     "icon": "🏃"},
    {"name": "Eurosport 2",   "slug": "eurosport-2",   "icon": "⛷️"},
    {"name": "beIN Sports",   "slug": "bein-sports",   "icon": "⚽"},
]


def load_ace_channels() -> list:
    """Carga la lista de canales favoritos desde disco."""
    try:
        with open(ACE_CHANNELS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return list(_ACE_CHANNELS_DEFAULT)


def save_ace_channels(channels: list):
    """Guarda la lista de canales favoritos."""
    with open(ACE_CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


def add_ace_channel(name: str, icon: str = "📺", slug: str = "", hash_: str = "") -> list:
    """Añade un canal favorito. Acepta slug (acestreamid.com) o hash directo."""
    channels = load_ace_channels()
    entry: dict = {"name": name, "icon": icon}
    if hash_:
        entry["hash"] = hash_
    elif slug:
        entry["slug"] = slug
    channels.append(entry)
    save_ace_channels(channels)
    return channels


def remove_ace_channel(index: int) -> list:
    """Elimina el canal en la posición dada."""
    channels = load_ace_channels()
    if 0 <= index < len(channels):
        channels.pop(index)
        save_ace_channels(channels)
    return channels


def resolve_ace_channel(channel: dict) -> list:
    """
    Dado un canal favorito (slug o hash directo), devuelve lista de {name, hash}.
    Si tiene hash directo lo devuelve de inmediato.
    Si tiene slug, busca en acestreamid.com.
    """
    if channel.get("hash"):
        return [{"name": channel["name"], "hash": channel["hash"]}]
    slug = channel.get("slug", "")
    if not slug:
        return []
    return acestream_search_channels(slug)


_ace_proxy_proc = None  # Proceso del proxy Acestream activo
ACESTREAM_PROXY_PORT = 8889
ACESTREAM_PROXY_SCRIPT = Path(__file__).parent / "ace_proxy.py"


def acestream_proxy_running(port: int = ACESTREAM_PROXY_PORT) -> bool:
    """Devuelve True si el puerto del proxy está en uso."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def acestream_proxy_start(ace_hash: str, mac_ip: str, port: int = ACESTREAM_PROXY_PORT) -> tuple:
    """
    Arranca el proxy HTTP en background. Devuelve (ok, proxy_url).
    El proxy sirve el stream de Acestream sin redirects a 127.0.0.1,
    con Content-Type correcto para que el reproductor nativo de la TV lo abra.
    """
    global _ace_proxy_proc

    # Matar proxy anterior si había
    if _ace_proxy_proc and _ace_proxy_proc.poll() is None:
        _ace_proxy_proc.terminate()
        time.sleep(0.5)

    # Matar cualquier proceso huérfano del proxy
    subprocess.run(["pkill", "-f", "ace_proxy.py"], capture_output=True)
    time.sleep(0.3)

    try:
        _ace_proxy_proc = subprocess.Popen(
            [sys.executable, str(ACESTREAM_PROXY_SCRIPT), ace_hash, str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        return False, f"No se pudo iniciar el proxy: {e}"

    # Esperar a que el proxy esté escuchando (máx 5s)
    for _ in range(10):
        time.sleep(0.5)
        if acestream_proxy_running(port):
            return True, f"http://{mac_ip}:{port}/stream"

    return False, "Proxy no respondió a tiempo"


def acestream_proxy_stop():
    """Para el proxy Acestream si está en marcha."""
    global _ace_proxy_proc
    if _ace_proxy_proc and _ace_proxy_proc.poll() is None:
        _ace_proxy_proc.terminate()
        _ace_proxy_proc = None
    subprocess.run(["pkill", "-f", "ace_proxy.py"], capture_output=True)


def lgtv_load_key() -> str:
    """Carga la client key guardada para la LG TV."""
    try:
        with open(LGTV_KEY_FILE) as f:
            return json.load(f).get("client_key", "")
    except Exception:
        return ""


# --- Pipeline HLS (ffmpeg → .m3u8 → HTTP server → player.html) ---

_hls_ffmpeg_proc = None
_hls_http_proc   = None


def acestream_hls_stop():
    """Para el pipeline HLS (ffmpeg + servidor HTTP)."""
    global _hls_ffmpeg_proc, _hls_http_proc
    for p in (_hls_ffmpeg_proc, _hls_http_proc):
        if p and p.poll() is None:
            p.terminate()
    _hls_ffmpeg_proc = _hls_http_proc = None
    subprocess.run(["pkill", "-f", "hls_tvstreamer"], capture_output=True)


def acestream_hls_start(ace_hash: str, mac_ip: str) -> tuple:
    """
    Arranca el pipeline completo acestream → HLS → HTML player.
    Pasos:
      1. Proxy HTTP (ace_proxy.py) sigue los redirects de Acestream.
      2. ffmpeg convierte MPEG-TS → HLS (.m3u8 + .ts) en /tmp/hls_tvstreamer/.
      3. Servidor HTTP minimalista sirve el directorio en HLS_PORT.
      4. Genera player.html con <video src='stream.m3u8'> + JS fullscreen.
    Devuelve (ok, player_url | error).
    """
    global _hls_ffmpeg_proc, _hls_http_proc

    # 1. Proxy
    if not acestream_proxy_running():
        ok, _ = acestream_proxy_start(ace_hash, mac_ip)
        if not ok:
            return False, "No se pudo iniciar el proxy Acestream"

    # 2. Crear directorio HLS
    HLS_DIR.mkdir(parents=True, exist_ok=True)

    # Matar ffmpeg anterior
    if _hls_ffmpeg_proc and _hls_ffmpeg_proc.poll() is None:
        _hls_ffmpeg_proc.terminate()
        time.sleep(0.5)
    subprocess.run(["pkill", "-f", "hls_tvstreamer"], capture_output=True)
    time.sleep(0.3)

    # 3. ffmpeg: proxy → HLS
    _hls_ffmpeg_proc = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-user_agent", "Mozilla/5.0",
            "-i", f"http://127.0.0.1:{ACESTREAM_PROXY_PORT}/stream",
            "-c:v", "copy", "-c:a", "copy",
            "-f", "hls",
            "-hls_time", "2",
            "-hls_list_size", "5",
            "-hls_flags", "delete_segments",
            "-hls_segment_filename", str(HLS_DIR / "seg%03d.ts"),
            str(HLS_DIR / "stream.m3u8"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 4. player.html
    player_html = HLS_DIR / "player.html"
    player_html.write_text(
        "<!DOCTYPE html><html><head><style>"
        "* { margin:0; padding:0; box-sizing:border-box; }"
        "body { background:#000; overflow:hidden; width:100vw; height:100vh; }"
        "video { width:100vw; height:100vh; object-fit:contain; }"
        "</style></head><body>"
        '<video id="v" src="stream.m3u8" autoplay playsinline muted></video>'
        "<script>"
        "var v = document.getElementById('v');"
        "v.muted = false; v.volume = 1.0; v.play().catch(function(){});"
        "(document.documentElement.requestFullscreen||document.documentElement.webkitRequestFullscreen||function(){}).call(document.documentElement);"
        "v.addEventListener('loadeddata', function(){"
        "  (v.requestFullscreen||v.webkitRequestFullscreen||function(){}).call(v); v.play();"
        "});"
        "</script></body></html>"
    )

    # 5. Matar servidor HTTP anterior y arrancar nuevo
    if _hls_http_proc and _hls_http_proc.poll() is None:
        _hls_http_proc.terminate()
        time.sleep(0.3)

    _hls_http_proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(HLS_PORT), "--directory", str(HLS_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Esperar a que el .m3u8 aparezca (máx 15s)
    m3u8 = HLS_DIR / "stream.m3u8"
    for _ in range(30):
        time.sleep(0.5)
        if m3u8.exists() and m3u8.stat().st_size > 0:
            return True, f"http://{mac_ip}:{HLS_PORT}/player.html"

    return False, "ffmpeg no generó el stream HLS a tiempo"


# --- Wrappers públicos WebOS (usan mando_tv internamente) ---

def lgtv_webos_open_fullscreen(tv_ip: str, url: str, client_key: str = None) -> tuple:
    """Abre una URL en la LG TV a pantalla completa (vía mando_tv / SSAP WebSocket)."""
    if not HAS_MANDO_TV:
        return False, "mando_tv no disponible"
    ok = _lg.run_lg("browser", {"url": url})
    return (True, f"[browser] {url}") if ok else (False, "LG TV no respondió al comando browser")


def lgtv_webos_open_url(tv_ip: str, url: str, client_key: str = None) -> tuple:
    """Alias de lgtv_webos_open_fullscreen."""
    return lgtv_webos_open_fullscreen(tv_ip, url, client_key)


# --- Wrappers públicos para el panel de control LG en app.py ---

def lg_encender() -> bool:
    """Enciende la LG TV por Wake-on-LAN."""
    if not HAS_MANDO_TV:
        return False
    return _lg.encender_lg()


def lg_apagar() -> bool:
    """Apaga la LG TV por SSAP."""
    if not HAS_MANDO_TV:
        return False
    return _lg.run_lg("apagar")


def lg_app(app_key: str) -> bool:
    """Abre una app en la LG TV por clave corta (ej. 'netflix', 'youtube')."""
    if not HAS_MANDO_TV:
        return False
    from mando_tv.streaming import APPS_LG
    app_id = APPS_LG.get(app_key.lower(), app_key)
    return _lg.run_lg("app", {"id": app_id})


def lg_escena(nombre: str, minutos: float = 90.0) -> bool:
    """Aplica una escena a la LG TV: noche, dia, cine, juego, descanso."""
    if not HAS_MANDO_TV:
        return False
    nombre = nombre.lower()
    from mando_tv.lg import lg_noche, lg_dia, lg_cine, lg_juego, lg_descanso
    if nombre == "noche":
        lg_noche(minutos)
    elif nombre == "dia":
        lg_dia()
    elif nombre == "cine":
        lg_cine()
    elif nombre == "juego":
        lg_juego()
    elif nombre == "descanso":
        lg_descanso()
    else:
        return False
    return True


def lg_timer_info() -> str:
    """Devuelve texto con el tiempo restante del temporizador de apagado LG."""
    if not HAS_MANDO_TV:
        return ""
    secs = obtener_tiempo_restante_timer("lg")
    if not secs:
        return ""
    mins = secs // 60
    return f"{mins} min {secs % 60} s"
