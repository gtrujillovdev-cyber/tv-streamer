"""Lanzador de contenido universal: Apps de Streaming y Canales TDT / Movistar Plus+."""
import shlex
import threading
import time
import urllib.parse
from typing import Optional, Tuple
from . import discovery, lg, xiaomi
from .lg import encender_lg
from .xiaomi import encender_xiaomi

DIALES_MOVISTAR = {
    # Canales Generalistas
    "la 1": "1", "la1": "1", "tve": "1", "1": "1", "primera": "1", "tve 1": "1",
    "la 2": "2", "la2": "2", "2": "2", "segunda": "2", "tve 2": "2",
    "antena 3": "3", "antena3": "3", "a3": "3", "3": "3",
    "cuatro": "4", "4": "4",
    "telecinco": "5", "tele 5": "5", "telecinco hd": "5", "t5": "5", "5": "5",
    "la sexta": "6", "lasexta": "6", "sexta": "6", "6": "6",
    # Canales Movistar y Deportes
    "movistar plus": "7", "movistar+": "7", "#0": "7", "movistar": "7", "cero": "7", "7": "7",
    "vamos": "8", "#vamos": "8", "8": "8",
    "laliga": "52", "la liga": "52", "futbol": "52", "liga": "52", "movistar laliga": "52",
    "dazn laliga": "53", "dazn liga": "53",
    "champions": "56", "liga de campeones": "56", "movistar champions": "56",
    "teledeporte": "64", "tdp": "64",
    "real madrid tv": "67", "rmtv": "67",
    "gol": "68", "gol play": "68", "gol tv": "68",
    # Canales Temáticos TDT
    "fdf": "26", "factoria de ficcion": "26",
    "neox": "27",
    "atreseries": "28", "a3series": "28",
    "energy": "29",
    "dmax": "30", "discovery": "30",
    "mega": "31",
    "trece": "32", "13": "32",
    "paramount": "33", "paramount network": "33",
    "divinity": "34",
    "nova": "35",
    "be mad": "36", "bemad": "36",
    "ten": "38",
    "24 horas": "112", "canal 24 horas": "112", "noticias": "112",
    "clan": "115",
    "boing": "116",
}

NOMBRES_PLATAFORMAS = {
    "smarttube": "SmartTube", "youtube": "YouTube", "netflix": "Netflix",
    "prime": "Prime Video", "amazon": "Prime Video", "disney": "Disney+",
    "movistar": "Movistar Plus", "dazn": "DAZN", "spotify": "Spotify",
    "max": "Max", "hbo": "Max", "appletv": "Apple TV+", "twitch": "Twitch",
    "atresplayer": "Atresplayer", "rtve": "RTVE Play", "mitele": "Mitele"
}

APPS_LG = {
    "smarttube": "youtube.leanback.v4",
    "youtube": "youtube.leanback.v4",
    "netflix": "netflix",
    "prime": "amazon",
    "amazon": "amazon",
    "disney": "com.disney.disneyplus-prod",
    "movistar": "com.telefonica.app.nux",
    "dazn": "dazn",
    "spotify": "spotify-beehive",
    "max": "com.wbd.stream",
    "hbo": "com.wbd.stream",
    "appletv": "com.apple.appletv",
    "twitch": "tv.twitch.tv",
    "atresplayer": "es.atresmedia.atresplayer",
    "rtve": "com.rtve.play",
    "mitele": "es.mediaset.mitele",
}

APPS_XIAOMI = {
    "smarttube": "org.smarttube.stable/com.liskovsoft.smartyoutubetv2.tv.ui.main.SplashActivity",
    "youtube": "com.google.android.youtube.tv/com.google.android.apps.youtube.tv.activity.ShellActivity",
    "netflix": "com.netflix.ninja/.MainActivity",
    "prime": "com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity",
    "amazon": "com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity",
    "disney": "com.disney.disneyplus/com.bamtechmedia.dominguez.main.MainActivity",
    "movistar": "com.movistarplus.androidtv/.MainActivity",
    "dazn": "com.dazn/.MainActivity",
    "spotify": "com.spotify.tv.android/.SpotifyTVActivity",
    "max": "com.wbd.stream/.MainActivity",
    "hbo": "com.wbd.stream/.MainActivity",
    "appletv": "com.apple.atve.androidtv.appletv/.MainActivity",
    "twitch": "tv.twitch.android.app/.core.MainActivity",
    "atresplayer": "com.atresplayer.tv/.gui.activities.HomeActivity",
    "rtve": "es.rtve.rtveplay.tv/.MainActivity",
    "mitele": "es.mediaset.mitele/.ui.MainActivity",
}

PLATAFORMAS_TV = {"", "movistar", "tdt", "tv", "tele", "canal", "television"}
_DIALES_VALIDOS = set(DIALES_MOVISTAR.values())


def resolver_canal_o_plataforma(query: str, plataforma: str = "smarttube") -> Tuple[bool, Optional[str], str, str]:
    """Resuelve si la petición es canal de TV en Movistar+ sin secuestrar búsquedas en otras apps."""
    q_clean = (query or "").strip()
    q_lower = q_clean.lower()
    for pref in ("el canal ", "canal ", "dial ", "el dial ", "pon el canal ", "pon canal "):
        if q_lower.startswith(pref):
            q_lower = q_lower[len(pref):].strip()
            break

    plat_lower = (plataforma or "").strip().lower()
    es_tv_explicita = plat_lower in PLATAFORMAS_TV
    dial = DIALES_MOVISTAR.get(q_lower)
    if not dial and q_lower.isdigit() and q_lower in _DIALES_VALIDOS and es_tv_explicita:
        dial = q_lower

    if es_tv_explicita:
        return True, dial, "movistar", q_clean

    # Solo redirigir a Movistar si la app pedida es movistar/tv o la búsqueda empezó explícitamente con prefijo de canal
    if dial and (q_clean.lower() != q_lower):
        return True, dial, "movistar", q_clean

    return False, None, plat_lower or "smarttube", q_clean


def _cmd_lanzar_xiaomi(plataforma: str, q_clean: str) -> str:
    comp = APPS_XIAOMI.get(plataforma)
    if not comp:
        return f"monkey -p {shlex.quote(plataforma)} 1"

    comp_norm = comp if "/" in comp else f"{comp}/.MainActivity"
    if q_clean:
        q_enc = urllib.parse.quote_plus(q_clean)
        deep_links = {
            "smarttube": f"https://www.youtube.com/results?search_query={q_enc}",
            "youtube": f"https://www.youtube.com/results?search_query={q_enc}",
            "netflix": f"https://www.netflix.com/search?q={q_enc}",
            "spotify": f"spotify:search:{q_enc}",
            "prime": f"https://app.primevideo.com/search?phrase={q_enc}",
            "amazon": f"https://app.primevideo.com/search?phrase={q_enc}",
            "disney": f"https://www.disneyplus.com/search/{q_enc}",
        }
        uri = deep_links.get(plataforma)
        if uri:
            return f"am start -a android.intent.action.VIEW -d {shlex.quote(uri)} -n {shlex.quote(comp_norm)}"
    return f"am start -n {shlex.quote(comp_norm)}"


def _secuencia_movistar_xiaomi(dial: Optional[str]):
    """Secuencia asíncrona no bloqueante para perfil Hogar y sintonización de dial en Xiaomi."""
    xiaomi.ejecutar_adb_xiaomi("am start -n com.movistarplus.androidtv/.MainActivity")
    time.sleep(2.8)
    xiaomi.ejecutar_adb_xiaomi("input keyevent 23")
    if dial and dial.isdigit():
        time.sleep(1.8)
        xiaomi.ejecutar_adb_xiaomi("input keyevent 4")
        time.sleep(1.2)
        for d in dial:
            xiaomi.ejecutar_adb_xiaomi(f"input keyevent {7 + int(d)}")
            time.sleep(0.3)


def reproducir_streaming(query: str, plataforma: str = "smarttube", target: str = "xiaomi") -> str:
    """Lanza apps y canales tanto en Xiaomi TV como en LG 65\". Todos los canales se dirigen siempre a Movistar Plus+."""
    es_canal_tv, dial, plataforma, q_clean = resolver_canal_o_plataforma(query, plataforma)
    q_enc = urllib.parse.quote_plus(q_clean) if q_clean else ""
    nombre_plat = NOMBRES_PLATAFORMAS.get(plataforma, plataforma.capitalize())

    # 1. XIAOMI TV (Android TV)
    if target in ["xiaomi", "ambas"]:
        ip_xm = discovery.resolver_ip_xiaomi()
        xm_st = xiaomi.estado_y_info_xiaomi()
        if not discovery.puerto_abierto(ip_xm, 5555, timeout=0.25) or xm_st.get("state") != "on":
            encender_xiaomi()
        else:
            xiaomi.conectar_adb_xiaomi()

        if plataforma == "movistar":
            threading.Thread(target=_secuencia_movistar_xiaomi, args=(dial,), daemon=True).start()
        else:
            xiaomi.ejecutar_adb_xiaomi(_cmd_lanzar_xiaomi(plataforma, q_clean), timeout=4.0)

    # 2. LG 65" (webOS)
    if target in ["lg", "ambas"]:
        ip_lg = discovery.resolver_ip_lg()
        if not discovery.puerto_abierto(ip_lg, 3000, timeout=0.25):
            encender_lg()
            lg.esperar_lg(timeout=12.0)

        app_id = APPS_LG.get(plataforma, "youtube.leanback.v4")
        params = {}
        if q_clean and not dial:
            if "youtube" in app_id:
                params["contentTarget"] = f"https://www.youtube.com/results?search_query={q_enc}"
            elif "netflix" in app_id:
                params["contentTarget"] = f"nflx://www.netflix.com/search?q={q_enc}"
            elif "prime" in app_id or "amazon" in app_id:
                params["contentTarget"] = f"https://www.amazon.es/s?k={q_enc}"
            elif "disney" in app_id:
                params["contentTarget"] = f"https://www.disneyplus.com/search/{q_enc}"

        lg.run_lg("app", {"id": app_id, "params": params, "mensaje": f"Abriendo {nombre_plat}"})

        if plataforma == "movistar":
            def _secuencia_movistar_lg(digitos: Optional[str] = None):
                time.sleep(2.5)
                lg.run_lg("reset_ptr", {})
                lg.run_lg("tecla", {"tecla": "ENTER"})
                if digitos:
                    time.sleep(2.0)
                    lg.run_lg("reset_ptr", {})
                    lg.run_lg("tecla", {"tecla": "BACK"})
                    time.sleep(1.0)
                    for d in digitos:
                        if d.isdigit():
                            lg.run_lg("tecla", {"tecla": d})
                            time.sleep(0.3)

            threading.Thread(target=_secuencia_movistar_lg, args=(dial,), daemon=True).start()

    if dial or es_canal_tv:
        return f"Poniendo {q_clean or 'Movistar Plus'} en Movistar Plus"
    elif q_clean:
        return f"Buscando '{q_clean}' en {nombre_plat}"
    else:
        return f"Abriendo {nombre_plat}"
