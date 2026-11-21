"""Servidor HTTP: mando web, hub Siri y API."""
from . import config
from . import discovery
from . import lg
from . import scenes
from . import timers
from . import xiaomi
import socketserver
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import socket
import urllib.parse
from .config import PUERTO
from .lg import encender_lg
from .streaming import reproducir_streaming
from .xiaomi import encender_xiaomi


_cache_status: bytes = b""
_cache_status_ts: float = 0.0
_status_lock = threading.Lock()
_status_pool = ThreadPoolExecutor(max_workers=6)


def _leer_web(nombre: str) -> bytes:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", nombre), "rb") as f:
        return f.read()


def _consultar_estado_lg() -> dict:
    lg_ip = discovery.resolver_ip_lg()
    lg_st = lg.estado_lg()
    lg_info = lg.obtener_info_lg() if lg_st == "on" else {"volume": 0, "backlight": 0, "soundOutput": "tv_speaker"}
    return {
        "lg_online": lg_st == "on",
        "lg_state": lg_st,
        "lg_ip": lg_ip,
        "lg_vol": lg_info.get("volume", 0),
        "lg_backlight": lg_info.get("backlight", 0),
        "lg_audio": lg_info.get("soundOutput", "tv_speaker"),
    }


def _consultar_estado_xiaomi() -> dict:
    xm_ip = discovery.resolver_ip_xiaomi()
    xm_info = xiaomi.estado_y_info_xiaomi()
    return {
        "xiaomi_online": xm_info.get("online", False),
        "xiaomi_state": xm_info.get("state", "standby"),
        "xiaomi_ip": xm_ip,
        "xiaomi_vol": xm_info.get("volume", 0),
        "xiaomi_backlight": xm_info.get("backlight", 0),
    }


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class MandoHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _enviar_encabezados(self, tipo: str = "text/html; charset=utf-8", codigo: int = 200, longitud: int = -1):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        if longitud >= 0:
            self.send_header("Content-Length", str(longitud))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()

    def _enviar_respuesta(self, contenido: bytes, tipo: str = "text/html; charset=utf-8", codigo: int = 200):
        self._enviar_encabezados(tipo=tipo, codigo=codigo, longitud=len(contenido))
        self.wfile.write(contenido)

    def do_GET(self):
        global _cache_status, _cache_status_ts
        url = urllib.parse.urlparse(self.path)

        try:
            if url.path in ["/", "/index.html"]:
                self._enviar_respuesta(_leer_web("index.html"), "text/html; charset=utf-8")

            elif url.path in ["/siri", "/siri.html"]:
                host = self.headers.get("Host") or "localhost"
                self._enviar_respuesta(_leer_web("siri.html").replace(b"__HOST__", host.encode()), "text/html; charset=utf-8")

            elif url.path == "/api/status":
                ahora = time.time()
                if ahora - _cache_status_ts < 2.0 and _cache_status:
                    self._enviar_respuesta(_cache_status, "application/json")
                    return

                adquirido = _status_lock.acquire(blocking=False)
                if not adquirido:
                    if _cache_status:
                        self._enviar_respuesta(_cache_status, "application/json")
                        return
                    _status_lock.acquire()

                try:
                    if time.time() - _cache_status_ts < 2.0 and _cache_status:
                        self._enviar_respuesta(_cache_status, "application/json")
                        return
                    fut_lg = _status_pool.submit(_consultar_estado_lg)
                    fut_xm = _status_pool.submit(_consultar_estado_xiaomi)
                    data = {}
                    try:
                        data.update(fut_lg.result(timeout=2.0))
                    except Exception:
                        data.update({
                            "lg_online": False, "lg_state": "standby",
                            "lg_ip": discovery.resolver_ip_lg(),
                            "lg_vol": 0, "lg_backlight": 0, "lg_audio": "tv_speaker",
                        })
                    try:
                        data.update(fut_xm.result(timeout=2.0))
                    except Exception:
                        data.update({
                            "xiaomi_online": False, "xiaomi_state": "standby",
                            "xiaomi_ip": discovery.resolver_ip_xiaomi(),
                            "xiaomi_vol": 0, "xiaomi_backlight": 0,
                        })
                    data["timer_lg"] = timers.obtener_tiempo_restante_timer("lg")
                    data["timer_xiaomi"] = timers.obtener_tiempo_restante_timer("xiaomi")
                    data["server_ip"] = _ip_local()
                    _cache_status = json.dumps(data).encode("utf-8")
                    _cache_status_ts = time.time()
                finally:
                    _status_lock.release()

                self._enviar_respuesta(_cache_status, "application/json")

            elif url.path == "/api/action":
                qs = urllib.parse.parse_qs(url.query)
                cmd = qs.get("cmd", [""])[0]
                target = qs.get("target", ["xiaomi"])[0]
                val = qs.get("val", ["0"])[0]

                if target == "xiaomi" and cmd in ("solo_audio", "audio_sharp", "audio_tv"):
                    payload = json.dumps({"ok": False, "mensaje": "Función exclusiva de LG"}).encode("utf-8")
                    self._enviar_respuesta(payload, "application/json")
                    return

                # Respuesta HTTP instantánea (<1ms para feedback táctil en iPhone)
                labels = {
                    "vol_up": "Volumen +", "vol_down": "Volumen -", "mute": "Mute",
                    "ch_up": "Canal +", "ch_down": "Canal -",
                    "up": "▲ Arriba", "down": "▼ Abajo", "left": "◄ Izquierda", "right": "► Derecha", "enter": "OK",
                    "play_pause": "Play / Pausa", "rewind": "⏪ -10s", "fast_forward": "⏩ +10s",
                    "back": "↩ Atrás", "home": "🏠 Inicio", "settings": "⚙️ Ajustes", "info": "ℹ️ Info", "source": "🔌 HDMI",
                    "dia": "☀️ Modo Día (100%)", "noche": "🌙 Modo Noche (6% + 90m)",
                    "cine": "🎬 Modo Cine", "juego": "🎮 Modo Juego", "descanso": "👁️ Modo Descanso", "solo_audio": "📻 Solo Audio",
                    "encender": "⚡ Encendiendo...", "apagar": "🔌 Apagando...",
                    "set_brillo": f"☀️ Brillo: {val}%", "set_volumen": f"🔊 Vol: {val}%",
                    "smarttube": "📺 SmartTube",
                    "audio_sharp": "📢 Barra Sharp (ARC)", "audio_tv": "📺 Altavoces TV"
                }
                mensaje = labels.get(cmd, f"{cmd.upper()}")

                payload = json.dumps({"ok": True, "mensaje": mensaje}).encode("utf-8")
                self._enviar_respuesta(payload, "application/json")

                # Ejecución en segundo plano sin bloquear jamás el navegador; invalida caché al terminar
                def _run_action():
                    global _cache_status_ts
                    try:
                        self.ejecutar_comando(cmd, target, val)
                    finally:
                        _cache_status_ts = 0.0

                threading.Thread(target=_run_action, daemon=True).start()

            elif url.path == "/api/voice":
                qs = urllib.parse.parse_qs(url.query)
                query = qs.get("q", [""])[0] or qs.get("query", [""])[0]
                platform = qs.get("platform", ["smarttube"])[0] or qs.get("plat", ["smarttube"])[0]
                target = qs.get("target", ["xiaomi"])[0]

                # Despacho en segundo plano
                def _do_stream():
                    reproducir_streaming(query, platform, target)
                threading.Thread(target=_do_stream, daemon=True).start()

                nombres = {
                    "smarttube": "SmartTube", "youtube": "YouTube", "netflix": "Netflix",
                    "prime": "Prime Video", "amazon": "Prime Video", "disney": "Disney+",
                    "movistar": "Movistar Plus", "dazn": "DAZN", "spotify": "Spotify",
                    "max": "Max", "hbo": "Max", "appletv": "Apple TV+", "twitch": "Twitch",
                    "atresplayer": "Atresplayer", "rtve": "RTVE Play", "mitele": "Mitele",
                }
                nombre_p = nombres.get(platform.lower(), platform.capitalize())
                msg = f"▶ Buscando '{query}' en {nombre_p}" if query else f"Abriendo {nombre_p}"

                self._enviar_respuesta(json.dumps({"ok": True, "mensaje": msg}).encode("utf-8"), "application/json")

            elif url.path == "/api/siri":
                qs = urllib.parse.parse_qs(url.query)
                action = qs.get("action", ["status"])[0]
                target = qs.get("target", ["ambas"])[0]
                q = qs.get("q", [""])[0] or qs.get("query", [""])[0]
                platform = qs.get("platform", ["smarttube"])[0] or qs.get("plat", ["smarttube"])[0]
                val = qs.get("val", ["20"])[0]

                respuesta_siri = self.procesar_comando_siri(action, target, q, platform, val)

                self._enviar_respuesta(respuesta_siri.encode("utf-8"), "text/plain; charset=utf-8")

            elif url.path == "/api/shortcut":
                qs = urllib.parse.parse_qs(url.query)
                sid = qs.get("id", [""])[0].strip()
                safe_sid = "".join(c for c in sid if c.isalnum() or c in ("-", "_"))
                ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shortcuts", f"{safe_sid}.shortcut")
                if not safe_sid or not os.path.exists(ruta):
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                nombres_sc = {
                    "master": "Mando TV",
                    # Salón - Control & Audio
                    "lg-on": "Enciende la tele del salón",
                    "lg-off": "Apaga la tele del salón",
                    "lg-volup-vol": "Sube el volumen de la tele del salón",
                    "lg-voldown-vol": "Baja el volumen de la tele del salón",
                    "lg-mute": "Silencia la tele del salón",
                    "lg-sharp": "Audio por barra en el salón",
                    "lg-noche": "Modo noche en la tele del salón",
                    "lg-dia": "Modo día en la tele del salón",
                    "lg-cine": "Modo cine en la tele del salón",
                    # Salón - Canales (Siempre en Movistar Plus+)
                    "lg-antena3": "Pon Antena 3 en la tele del salón",
                    "lg-la1": "Pon La 1 en la tele del salón",
                    "lg-la2": "Pon La 2 en la tele del salón",
                    "lg-cuatro": "Pon Cuatro en la tele del salón",
                    "lg-telecinco": "Pon Telecinco en la tele del salón",
                    "lg-lasexta": "Pon La Sexta en la tele del salón",
                    "lg-movistar": "Pon Movistar Plus en la tele del salón",
                    "lg-vamos": "Pon Vamos en la tele del salón",
                    "lg-laliga": "Pon LaLiga en la tele del salón",
                    "lg-champions": "Pon la Champions en la tele del salón",
                    "lg-teledeporte": "Pon Teledeporte en la tele del salón",
                    # Salón - Apps
                    "lg-nf": "Pon Netflix en la tele del salón",
                    "lg-yt": "Pon YouTube en la tele del salón",
                    "lg-spotify": "Pon Spotify en la tele del salón",
                    "lg-prime": "Pon Prime Video en la tele del salón",
                    "lg-disney": "Pon Disney en la tele del salón",
                    "lg-max": "Pon Max en la tele del salón",
                    "lg-dazn": "Pon DAZN en la tele del salón",
                    "lg-appletv": "Pon Apple TV en la tele del salón",
                    # Cuarto - Control & Audio
                    "xm-on": "Enciende la tele del cuarto",
                    "xm-off": "Apaga la tele del cuarto",
                    "xm-volup-vol": "Sube el volumen de la tele del cuarto",
                    "xm-voldown-vol": "Baja el volumen de la tele del cuarto",
                    "xm-noche": "Modo noche en la tele del cuarto",
                    "xm-dia": "Modo día en la tele del cuarto",
                    # Cuarto - Canales (Siempre en Movistar)
                    "xm-antena3": "Pon Antena 3 en la tele del cuarto",
                    "xm-la1": "Pon La 1 en la tele del cuarto",
                    "xm-la2": "Pon La 2 en la tele del cuarto",
                    "xm-cuatro": "Pon Cuatro en la tele del cuarto",
                    "xm-telecinco": "Pon Telecinco en la tele del cuarto",
                    "xm-lasexta": "Pon La Sexta en la tele del cuarto",
                    "xm-movistar": "Pon Movistar en la tele del cuarto",
                    # Cuarto - Apps
                    "xm-st": "Pon SmartTube en la tele del cuarto",
                    "xm-yt": "Pon YouTube en la tele del cuarto",
                    "xm-nf": "Pon Netflix en la tele del cuarto",
                    "xm-spotify": "Pon Spotify en la tele del cuarto",
                    "xm-prime": "Pon Prime Video en la tele del cuarto",
                    "xm-disney": "Pon Disney en la tele del cuarto",
                    "xm-max": "Pon Max en la tele del cuarto",
                    "xm-dazn": "Pon DAZN en la tele del cuarto",
                    # Ambas
                    "ambas-on": "Enciende las teles",
                    "ambas-off": "Apaga las teles",
                    "ambas-pausa": "Pausa la tele",
                    "ambas-status": "Estado de las teles",
                    # Búsquedas por voz
                    "pon-salon-yt": "Pon en YouTube en el salón",
                    "pon-salon-nf": "Pon en Netflix en el salón",
                    "pon-salon-prime": "Pon en Prime Video en el salón",
                    "pon-salon-disney": "Pon en Disney en el salón",
                    "pon-salon-max": "Pon en Max en el salón",
                    "pon-cuarto-yt": "Pon en YouTube en el cuarto",
                    "pon-cuarto-nf": "Pon en Netflix en el cuarto",
                    "pon-cuarto-prime": "Pon en Prime Video en el cuarto",
                    "pon-cuarto-disney": "Pon en Disney en el cuarto",
                }
                nombre_sc = nombres_sc.get(safe_sid, safe_sid)
                fname_ascii = (nombre_sc.replace("ó", "o").replace("í", "i").replace("á", "a").replace("é", "e").replace("ú", "u")) + ".shortcut"
                fname_utf8 = urllib.parse.quote(nombre_sc + ".shortcut")
                with open(ruta, "rb") as f:
                    data_sc = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{fname_ascii}"; filename*=UTF-8\'\'{fname_utf8}')
                self.send_header("Content-Length", str(len(data_sc)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data_sc)

            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        except (BrokenPipeError, ConnectionResetError):
            pass

    def procesar_comando_siri(self, action: str, target: str, q: str, platform: str, val: str) -> str:
        """Genera respuestas en lenguaje natural hablado para Siri y despacha la acción."""
        t_norm = target.strip().lower()
        if t_norm in ["lg", "salon", "salón", "tele_salon"]:
            target = "lg"
        elif t_norm in ["xiaomi", "cuarto", "habitacion", "habitación", "tele_cuarto"]:
            target = "xiaomi"
        else:
            target = "ambas"

        disp_nombre = "la tele del salón" if target == "lg" else ("la tele del cuarto" if target == "xiaomi" else "ambas teles")

        if action == "noche":
            def _n():
                if target == "lg": lg.lg_noche(90)
                elif target == "xiaomi": xiaomi.xiaomi_noche(90)
                else: scenes.modo_noche(90)
            threading.Thread(target=_n, daemon=True).start()
            if target == "lg":
                return "Modo Noche activado en la tele del salón. Retroiluminación al 6% y temporizador de 90 minutos."
            elif target == "xiaomi":
                return "Modo Noche activado en la tele del cuarto. Retroiluminación tenue y temporizador de 90 minutos."
            else:
                return "Modo Noche activado en ambas teles con retroiluminación al 6% y temporizador de 90 minutos."

        elif action == "dia":
            def _d():
                if target == "lg": lg.lg_dia()
                elif target == "xiaomi": xiaomi.xiaomi_dia()
                else: scenes.modo_dia()
            threading.Thread(target=_d, daemon=True).start()
            if target == "lg":
                return "Modo Día activado en la tele del salón con retroiluminación al 100%."
            elif target == "xiaomi":
                return "Modo Día activado en la tele del cuarto con retroiluminación al 100%."
            else:
                return "Modo Día activado en ambas teles al 100%."

        elif action == "cine":
            def _c():
                if target == "lg": lg.lg_cine()
                elif target == "xiaomi": xiaomi.xiaomi_cine()
                else: scenes.modo_cine()
            threading.Thread(target=_c, daemon=True).start()
            return f"Modo Cine activado en {disp_nombre}."

        elif action == "juego":
            def _j():
                if target == "lg": lg.lg_juego()
                elif target == "xiaomi": xiaomi.xiaomi_juego()
                else: scenes.modo_juego()
            threading.Thread(target=_j, daemon=True).start()
            return f"Modo Juego de ultra baja latencia activado en {disp_nombre}."

        elif action == "descanso":
            def _des():
                if target == "lg": lg.lg_descanso()
                elif target == "xiaomi": xiaomi.xiaomi_descanso()
                else: scenes.modo_descanso()
            threading.Thread(target=_des, daemon=True).start()
            return f"Modo Descanso Visual activado en {disp_nombre}."

        elif action == "encender":
            def _e():
                if target in ["lg", "ambas"]: encender_lg()
                if target in ["xiaomi", "ambas"]: encender_xiaomi()
            threading.Thread(target=_e, daemon=True).start()
            if target == "lg": return "Tele del salón encendida."
            elif target == "xiaomi": return "Tele del cuarto encendida."
            else: return "Ambas teles encendidas."

        elif action == "apagar":
            def _a():
                if target in ["lg", "ambas"]: lg.apagar_lg()
                if target in ["xiaomi", "ambas"]: xiaomi.apagar_xiaomi()
            threading.Thread(target=_a, daemon=True).start()
            if target == "lg": return "Tele del salón apagada."
            elif target == "xiaomi": return "Tele del cuarto apagada y en modo de bajo consumo."
            else: return "Ambas teles apagadas."

        elif action == "volumen":
            try: v = int(val)
            except ValueError: v = 20
            def _v():
                if target in ["lg", "ambas"]: lg.lg_volumen(v)
                if target in ["xiaomi", "ambas"]: xiaomi.xiaomi_volumen(v, escala_porcentaje=True)
            threading.Thread(target=_v, daemon=True).start()
            return f"Volumen de {disp_nombre} ajustado al {v}%."

        elif action in ["silenciar", "mute"]:
            def _m():
                if target in ["lg", "ambas"]: lg.lg_mute()
                if target in ["xiaomi", "ambas"]: xiaomi.xiaomi_mute()
            threading.Thread(target=_m, daemon=True).start()
            return f"Silenciando {disp_nombre}."

        elif action in ["play", "play_pause", "pausa"]:
            def _pp():
                if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "PLAY"})
                if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 85")
            threading.Thread(target=_pp, daemon=True).start()
            return "Reproducción alternada."

        elif action in ["retroceder", "rewind"]:
            def _rw():
                if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "REWIND"})
                if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 89")
            threading.Thread(target=_rw, daemon=True).start()
            return f"Retrocediendo 10 segundos en {disp_nombre}."

        elif action in ["adelantar", "fastforward"]:
            def _ff():
                if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "FASTFORWARD"})
                if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 90")
            threading.Thread(target=_ff, daemon=True).start()
            return f"Avanzando 10 segundos en {disp_nombre}."

        elif action == "vol_up":
            def _vu():
                if target in ["lg", "ambas"]: lg.run_lg("vol_up", {})
                if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 24")
            threading.Thread(target=_vu, daemon=True).start()
            return f"Subiendo volumen de {disp_nombre}."

        elif action == "vol_down":
            def _vd():
                if target in ["lg", "ambas"]: lg.run_lg("vol_down", {})
                if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 25")
            threading.Thread(target=_vd, daemon=True).start()
            return f"Bajando volumen de {disp_nombre}."

        elif action == "audio_tv":
            def _at():
                if target in ["lg", "ambas"]: lg.run_lg("audio_output", {"output": "tv_speaker"})
            threading.Thread(target=_at, daemon=True).start()
            return "Audio cambiado a los altavoces de la tele del salón."

        elif action == "audio_sharp":
            def _as():
                if target in ["lg", "ambas"]: lg.run_lg("audio_output", {"output": "external_arc"})
            threading.Thread(target=_as, daemon=True).start()
            return "Audio cambiado a la barra de sonido Sharp."

        elif action in ["ver", "buscar", "poner", "reproducir", "canal"]:
            from .streaming import resolver_canal_o_plataforma
            es_canal_tv, _, platform, _ = resolver_canal_o_plataforma(q, platform)

            nombres = {
                "smarttube": "SmartTube", "youtube": "YouTube", "netflix": "Netflix",
                "prime": "Prime Video", "amazon": "Prime Video", "disney": "Disney+",
                "movistar": "Movistar Plus", "dazn": "DAZN", "spotify": "Spotify",
                "max": "Max", "hbo": "Max", "appletv": "Apple TV+", "twitch": "Twitch",
                "atresplayer": "Atresplayer", "rtve": "RTVE Play", "mitele": "Mitele",
            }
            nombre_p = nombres.get(platform.lower(), platform.capitalize())
            def _v():
                reproducir_streaming(q, platform, target)
            threading.Thread(target=_v, daemon=True).start()
            lugar = f" en {disp_nombre}" if target != "ambas" else ""
            if es_canal_tv and q:
                return f"Poniendo {q} en Movistar Plus{lugar}."
            elif q:
                return f"Poniendo {q} en {nombre_p}{lugar}."
            else:
                return f"Abriendo {nombre_p}{lugar}."

        elif action == "status":
            lg_on = discovery.puerto_abierto(discovery.resolver_ip_lg(), 3000, timeout=0.15)
            xm_on = xiaomi.estado_y_info_xiaomi().get("state") == "on"
            lg_str = "encendida" if lg_on else "en espera"
            xm_str = "encendida" if xm_on else "en espera"
            return f"Estado actual: la tele del salón está {lg_str} y la tele del cuarto está {xm_str}."

        else:
            return "Comando de voz recibido."

    def ejecutar_comando(self, cmd: str, target: str, val: str = "0") -> str:
        # 1. ENCENDIDO (Power ON)
        if cmd == "encender":
            if target in ["lg", "ambas"]: encender_lg()
            if target in ["xiaomi", "ambas"]: encender_xiaomi()
            return "Encendido enviado"

        # 2. APAGADO (Power OFF)
        elif cmd == "apagar":
            if target in ["lg", "ambas"]: lg.apagar_lg()
            if target in ["xiaomi", "ambas"]: xiaomi.apagar_xiaomi()
            return "Apagado enviado"

        # 3. SLIDERS (Brillo & Volumen)
        elif cmd == "set_brillo":
            try: v = max(0, min(100, int(val)))
            except ValueError: v = 50
            if target in ["xiaomi", "ambas"]:
                # Evitar poner picture_backlight a 0 desde slider (dejaría el panel en negro)
                v_xm = max(5, v)
                br_xm = max(12, round(v_xm * 255 / 100))
                xiaomi.ejecutar_adb_xiaomi(
                    f"settings put global picture_backlight {v_xm}; "
                    f"settings put system screen_brightness {br_xm}"
                )
            if target in ["lg", "ambas"]:
                lg.run_lg("ajustes", {
                    "category": "picture", "settings": {"backlight": str(v)},
                    "mensaje": f"Retroiluminación: {v}%"
                })
            return f"☀️ Retroiluminación: {v}%"

        elif cmd == "set_volumen":
            try: v = max(0, min(100, int(val)))
            except ValueError: v = 15
            if target in ["lg", "ambas"]: lg.lg_volumen(v)
            if target in ["xiaomi", "ambas"]: xiaomi.xiaomi_volumen(v, escala_porcentaje=True)
            return f"🔊 Volumen: {v}%"

        # 4. MODOS DE IMAGEN & SUEÑO
        elif cmd == "noche":
            try: mins = max(10.0, min(360.0, float(val)))
            except (ValueError, TypeError): mins = 90.0
            if target == "lg": lg.lg_noche(mins); return f"🌙 LG: Modo Noche (6% + {int(mins)}m)"
            elif target == "xiaomi": xiaomi.xiaomi_noche(mins); return f"🌙 Xiaomi: Modo Noche (6% + {int(mins)}m)"
            else: scenes.modo_noche(mins); return f"🌙 Ambas: Modo Noche (6% + {int(mins)}m)"

        elif cmd == "cine":
            if target == "lg": lg.lg_cine(); return "🎬 LG: Filmmaker Mode D65"
            elif target == "xiaomi": xiaomi.xiaomi_cine(); return "🎬 Xiaomi: Modo Película"
            else: scenes.modo_cine(); return "🎬 Ambas: Modo Cine"

        elif cmd == "juego":
            if target == "lg": lg.lg_juego(); return "🎮 LG: Modo Juego (~9ms)"
            elif target == "xiaomi": xiaomi.xiaomi_juego(); return "🎮 Xiaomi: Modo Juego"
            else: scenes.modo_juego(); return "🎮 Ambas: Modo Juego"

        elif cmd == "descanso":
            if target == "lg": lg.lg_descanso(); return "👁️ LG: Modo Descanso Visual"
            elif target == "xiaomi": xiaomi.xiaomi_descanso(); return "👁️ Xiaomi: Modo Descanso Visual"
            else: scenes.modo_descanso(); return "👁️ Ambas: Modo Descanso Visual"

        elif cmd == "dia":
            if target == "lg": lg.lg_dia(); return "☀️ LG: Modo Día (100%)"
            elif target == "xiaomi": xiaomi.xiaomi_dia(); return "☀️ Xiaomi: Modo Día (100%)"
            else: scenes.modo_dia(); return "☀️ Ambas: Modo Día"

        elif cmd == "solo_audio":
            if target in ["lg", "ambas"]: lg.lg_solo_audio()
            return "📻 Solo Audio activado"

        elif cmd == "audio_sharp":
            if target in ["lg", "ambas"]: lg.run_lg("audio_output", {"output": "external_arc"})
            return "📢 Audio: Barra Sharp (HDMI ARC)"

        elif cmd == "audio_tv":
            if target in ["lg", "ambas"]: lg.run_lg("audio_output", {"output": "tv_speaker"})
            return "📺 Audio: Altavoces TV"

        elif cmd == "cancelar_timer":
            if target == "lg": lg.cancelar_temporizador_lg()
            elif target == "xiaomi": xiaomi.cancelar_temporizador_xiaomi()
            else: scenes.cancelar_todos_temporizadores()
            return "⏱️ Temporizador cancelado"

        # 5. CRUCETA DIRECCIONAL (D-Pad)
        elif cmd in ["up", "down", "left", "right", "enter"]:
            mapping_lg = {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT", "enter": "ENTER"}
            mapping_xm = {"up": "19", "down": "20", "left": "21", "right": "22", "enter": "23"}

            if target in ["lg", "ambas"]:
                lg.run_lg("tecla", {"tecla": mapping_lg[cmd]})
            if target in ["xiaomi", "ambas"]:
                xiaomi.ejecutar_adb_xiaomi(f"input keyevent {mapping_xm[cmd]}")
            return f"Tecla: {cmd.upper()}"

        # 6. ROCKER DE VOLUMEN & CANALES (CH)
        elif cmd == "vol_up":
            if target in ["lg", "ambas"]: lg.run_lg("vol_up", {})
            if target in ["xiaomi", "ambas"]: xiaomi.xiaomi_vol_up()
            return "Volumen +"
        elif cmd == "vol_down":
            if target in ["lg", "ambas"]: lg.run_lg("vol_down", {})
            if target in ["xiaomi", "ambas"]: xiaomi.xiaomi_vol_down()
            return "Volumen -"
        elif cmd == "ch_up":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "CHANNELUP"})
            if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 166")
            return "Canal +"
        elif cmd == "ch_down":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "CHANNELDOWN"})
            if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 167")
            return "Canal -"
        elif cmd == "mute":
            if target in ["lg", "ambas"]: lg.lg_mute()
            if target in ["xiaomi", "ambas"]: xiaomi.xiaomi_mute()
            return "Silenciar (Mute)"

        # 7. CONTROLES DE REPRODUCCIÓN (PLAYBACK)
        elif cmd == "play_pause":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "PLAY"})
            if target in ["xiaomi", "ambas"]: xiaomi.xiaomi_play_pause()
            return "Play / Pausa"
        elif cmd == "rewind":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "REWIND"})
            if target in ["xiaomi", "ambas"]: xiaomi.xiaomi_rewind()
            return "Rebobinar -10s"
        elif cmd == "fast_forward":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "FASTFORWARD"})
            if target in ["xiaomi", "ambas"]: xiaomi.xiaomi_fast_forward()
            return "Avanzar +10s"

        # 8. TECLAS DE SISTEMA (HOME, ATRÁS, AJUSTES, SOURCE, INFO)
        elif cmd == "back":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "BACK"})
            if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 4")
            return "Atrás"
        elif cmd == "home":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "HOME"})
            if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 3")
            return "Inicio (Home)"
        elif cmd == "settings":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "MENU"})
            if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 176 || input keyevent 82")
            return "Ajustes"
        elif cmd == "source":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "INPUT"})
            if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 178")
            return "Entrada HDMI / Source"
        elif cmd == "info":
            if target in ["lg", "ambas"]: lg.run_lg("tecla", {"tecla": "INFO"})
            if target in ["xiaomi", "ambas"]: xiaomi.ejecutar_adb_xiaomi("input keyevent 165")
            return "Info"

        # 9. APPS DIRECTAS
        elif cmd == "smarttube":
            reproducir_streaming("", "smarttube", target)
            return "Lanzando SmartTube"

        return f"Comando '{cmd}' ejecutado"


def _ip_local() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "localhost"


def _background_monitor():
    """
    Monitor en segundo plano:
    1. Mantiene viva la conexión ADB con la Xiaomi TV.
    2. Detecta transiciones de standby a ON en la LG TV (incluso si se enciende
       con el mando físico tradicional) y desvía la TDT a Movistar Plus / Home.
    """
    try:
        lg.precalentar()
        xiaomi.conectar_adb_xiaomi()
    except Exception:
        pass

    ultimo_estado_lg = lg.estado_lg()
    contador_ciclos = 0

    while True:
        time.sleep(3)
        contador_ciclos += 1

        # ADB keepalive para Xiaomi cada ~60s (cada 20 ciclos de 3s)
        if contador_ciclos % 20 == 0:
            try:
                xiaomi.conectar_adb_xiaomi()
            except Exception:
                pass

        # Centinela Anti-TDT para LG
        try:
            estado_actual = lg.estado_lg()
            if ultimo_estado_lg in ("standby", "booting") and estado_actual == "on":
                # La tele se acaba de encender (vía mando físico, Alexa o app)
                threading.Thread(
                    target=lg.redirigir_si_tdt,
                    args=("com.telefonica.app.nux", 15.0),
                    name="lg-anti-tdt-auto",
                    daemon=True,
                ).start()
            ultimo_estado_lg = estado_actual
        except Exception:
            pass


def iniciar_servidor():
    server = ThreadingHTTPServer(("0.0.0.0", PUERTO), MandoHandler)
    threading.Thread(target=_background_monitor, daemon=True, name="bg-monitor").start()
    print(f"\n{'='*70}")
    print(f" 🎛️  MANDO UNIVERSAL & HUB SIRI EN LÍNEA (iPhone 16 Calibrado)")
    print(f"{'='*70}")
    print(f"  • Mando Móvil:       http://{_ip_local()}:{PUERTO}")
    print(f"  • Hub Atajos Siri:   http://{_ip_local()}:{PUERTO}/siri")
    print(f"  • Webhook Siri API:  http://{_ip_local()}:{PUERTO}/api/siri")
    print(f"{'='*70}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Deteniendo servidor...")
        server.server_close()


if __name__ == "__main__":
    iniciar_servidor()
