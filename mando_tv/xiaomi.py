"""Control de la Xiaomi TV (Android TV vía ADB)."""
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional
from .config import Color, MAC_XIAOMI, ROOT_DIR, TIMER_FILE_XIAOMI_META
from .wol import enviar_wol
from . import discovery


_wol_ts: float = 0.0
BOOT_SEGUNDOS = 60

_adb_conectado: bool = False
_adb_saneado: bool = False
_adb_lock = threading.Lock()

_info_cache: Dict[str, Any] = {"state": "standby", "online": False, "volume": 0, "backlight": 0}
_info_cache_ts: float = 0.0
INFO_CACHE_TTL = 5.0


def invalidar_cache_xiaomi():
    global _info_cache_ts
    _info_cache_ts = 0.0


def conectar_adb_xiaomi() -> bool:
    global _adb_conectado, _adb_saneado
    ip = discovery.resolver_ip_xiaomi()
    if not discovery.puerto_abierto(ip, 5555, timeout=0.25):
        _adb_conectado = False
        _adb_saneado = False
        return False
    try:
        res = subprocess.run(
            ["adb", "connect", f"{ip}:5555"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0
        )
        _adb_conectado = (res.returncode == 0)
    except Exception:
        _adb_conectado = False
        _adb_saneado = False
    return _adb_conectado


def esperar_xiaomi(timeout: float = 8.0) -> bool:
    """Espera brevemente a que el puerto ADB 5555 de la Xiaomi responda tras WoL."""
    fin = time.time() + timeout
    while time.time() < fin:
        ip = discovery.resolver_ip_xiaomi()
        if discovery.puerto_abierto(ip, 5555, timeout=0.3):
            return True
        time.sleep(0.4)
    return False


def _ejecutar_adb_raw(ip: str, comando_shell: str, timeout: float):
    return subprocess.run(
        ["adb", "-s", f"{ip}:5555", "shell", comando_shell],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout
    )


def ejecutar_adb_xiaomi(comando_shell: str, timeout: float = 2.5, invalidar_cache: bool = True):
    global _adb_conectado, _adb_saneado
    with _adb_lock:
        ip = discovery.resolver_ip_xiaomi()
        if not _adb_conectado and not conectar_adb_xiaomi():
            return None
        try:
            res = _ejecutar_adb_raw(ip, comando_shell, timeout)
            err = (res.stderr or "").lower()
            if res.returncode != 0 and ("device not found" in err or "offline" in err or "closed" in err):
                _adb_conectado = False
                if conectar_adb_xiaomi():
                    ip = discovery.resolver_ip_xiaomi()
                    res = _ejecutar_adb_raw(ip, comando_shell, timeout)
            if invalidar_cache:
                invalidar_cache_xiaomi()
            return res
        except Exception:
            _adb_conectado = False
            _adb_saneado = False
            return None


def sanear_ajustes_xiaomi_si_necesario():
    """Repara ajustes heredados que dejan el panel negro o desincronizan el mando físico."""
    global _adb_saneado
    if _adb_saneado:
        return
    res = ejecutar_adb_xiaomi(
        'echo "S:$(settings get global stay_on_while_plugged_in 2>/dev/null)"; '
        'echo "P:$(settings get global picture_backlight 2>/dev/null)"; '
        'echo "B:$(settings get system screen_brightness 2>/dev/null)"',
        timeout=2.0,
        invalidar_cache=False,
    )
    if not res or res.returncode != 0:
        return
    fixes = []
    for line in (res.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("S:") and line[2:].strip() not in ("", "0", "null"):
            fixes.append("settings put global stay_on_while_plugged_in 0")
        elif line.startswith("P:") and line[2:].strip() == "0":
            fixes.append("settings put global picture_backlight 50")
        elif line.startswith("B:") and line[2:].strip() == "0":
            fixes.append("settings put system screen_brightness 128")
    if fixes:
        ejecutar_adb_xiaomi("; ".join(fixes), timeout=2.5, invalidar_cache=False)
    _adb_saneado = True


def encender_xiaomi() -> bool:
    """Despierta la Xiaomi TV con KEYCODE_WAKEUP y garantiza brillo/energía limpios para el mando físico."""
    global _wol_ts, _adb_saneado
    _wol_ts = time.time()
    ip = discovery.resolver_ip_xiaomi()
    print(f"{Color.CYAN}[*] Despertando Xiaomi TV ({ip})...{Color.END}")
    enviar_wol(MAC_XIAOMI)

    if not discovery.puerto_abierto(ip, 5555, timeout=0.3):
        esperar_xiaomi(timeout=6.0)

    if not conectar_adb_xiaomi():
        print(f"{Color.YELLOW}[!] Xiaomi TV ({ip}): ADB aún no disponible tras WoL.{Color.END}")
        return False

    # Restaurar políticas limpias y brillo si quedó bloqueado en 0; usar KEYCODE_WAKEUP (no HOME forzado)
    cmd = (
        "settings put global stay_on_while_plugged_in 0; "
        "P=$(settings get global picture_backlight 2>/dev/null); "
        "[ \"$P\" = \"0\" ] || [ \"$P\" = \"null\" ] && settings put global picture_backlight 50; "
        "B=$(settings get system screen_brightness 2>/dev/null); "
        "[ \"$B\" = \"0\" ] || [ \"$B\" = \"null\" ] && settings put system screen_brightness 128; "
        "V=$(settings get system volume_music_speaker 2>/dev/null); "
        "[ \"$V\" = \"0\" ] && cmd media_session volume --stream 3 --set 5 >/dev/null 2>&1; "
        "input keyevent 224"
    )
    ejecutar_adb_xiaomi(cmd, timeout=3.0)
    _adb_saneado = True
    print(f"{Color.GREEN}[✓] Xiaomi TV: Pantalla encendida y mando físico sincronizado.{Color.END}")
    return True


def _comando_sleep_seguro() -> str:
    """Comando ADB idempotente para pausar y suspender la Xiaomi sin dejar brillo/backlight a 0."""
    return (
        "cmd media_session dispatch pause >/dev/null 2>&1; "
        "settings put global stay_on_while_plugged_in 0; "
        "P=$(settings get global picture_backlight 2>/dev/null); "
        "[ \"$P\" = \"0\" ] || [ \"$P\" = \"null\" ] && settings put global picture_backlight 50; "
        "B=$(settings get system screen_brightness 2>/dev/null); "
        "[ \"$B\" = \"0\" ] || [ \"$B\" = \"null\" ] && settings put system screen_brightness 128; "
        "input keyevent 223"
    )


def programar_temporizador_xiaomi(minutos: float = 90.0):
    """Lanza un proceso en segundo plano en el Mac para suspender la Xiaomi de forma fiable."""
    cancelar_temporizador_xiaomi(silencioso=True)
    segundos = max(1, int(minutos * 60))
    cmd = (
        f"nohup bash -c 'sleep {segundos} && {sys.executable} -c \""
        f"import sys; sys.path.insert(0, \\\"{ROOT_DIR}\\\"); "
        f"from mando_tv.xiaomi import apagar_xiaomi_si_despierta; apagar_xiaomi_si_despierta()\"' "
        f"</dev/null >/dev/null 2>&1 & echo $!"
    )
    try:
        pid = subprocess.check_output(cmd, shell=True, text=True).strip()
        with open(TIMER_FILE_XIAOMI_META, "w", encoding="utf-8") as f:
            f.write(f"{pid}:{segundos}:{int(time.time())}")
    except Exception as e:
        print(f"{Color.RED}[!] Error programando timer Xiaomi: {e}{Color.END}")


def cancelar_temporizador_xiaomi(silencioso: bool = False):
    if os.path.exists(TIMER_FILE_XIAOMI_META):
        try:
            with open(TIMER_FILE_XIAOMI_META, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
            pid = contenido.split(":")[0] if ":" in contenido else ""
            if pid.isdigit():
                subprocess.run(f"pkill -P {pid} 2>/dev/null; kill -9 {pid} 2>/dev/null", shell=True)
            os.remove(TIMER_FILE_XIAOMI_META)
            if not silencioso:
                print(f"{Color.GREEN}[✓] Xiaomi TV: Temporizador de apagado cancelado.{Color.END}")
        except Exception:
            pass
    elif not silencioso:
        print(f"{Color.CYAN}[*] Xiaomi TV: No había temporizadores activos.{Color.END}")


def apagar_xiaomi_si_despierta():
    """Ejecutado al vencer el temporizador: suspende la Xiaomi solo si está despierta."""
    if os.path.exists(TIMER_FILE_XIAOMI_META):
        try:
            os.remove(TIMER_FILE_XIAOMI_META)
        except Exception:
            pass
    ip = discovery.resolver_ip_xiaomi()
    if not discovery.puerto_abierto(ip, 5555, timeout=0.5):
        return
    cmd = f'dumpsys power | grep -q "mWakefulness=Awake" && ({_comando_sleep_seguro()})'
    ejecutar_adb_xiaomi(cmd, timeout=4.0)


def apagar_xiaomi(forzar_apagado_total: bool = False):
    """Suspende la Xiaomi TV con KEYCODE_SLEEP sin dejar backlight=0 ni mute bloqueados."""
    global _wol_ts
    _wol_ts = 0.0
    print(f"{Color.CYAN}[*] Suspendiendo Xiaomi TV (KEYCODE_SLEEP compatible con mando físico)...{Color.END}")
    cancelar_temporizador_xiaomi(silencioso=True)
    # 1. Pausar reproducción sin alternar (dispatch pause en vez de toggle 85).
    # 2. Dejar stay_on_while_plugged_in=0 para que el mando físico mantenga sincronía real Awake/Asleep.
    # 3. Garantizar backlight/brightness > 0 antes de dormir para que al despertar con el mando físico
    #    la pantalla vuelva iluminada y nunca se quede en negro.
    # 4. Evitar keyevent 164 (Mute toggle) y poner a dormir con KEYCODE_SLEEP (223, idempotente).
    ejecutar_adb_xiaomi(_comando_sleep_seguro(), timeout=3.0)
    print(f"{Color.GREEN}[✓] Xiaomi TV: Suspendida limpiamente (lista para despertar con el mando físico).{Color.END}")


def xiaomi_noche(minutos: float = 90.0):
    print(f"\n{Color.BOLD}🌙 [XIAOMI TV] ACTIVANDO MODO NOCHE...{Color.END}")
    print(f"  • Retroiluminación: {Color.CYAN}6%{Color.END}")
    print(f"  • Temporizador de apagado: {Color.CYAN}{minutos} minutos ({minutos/60:.1f}h){Color.END}")

    ejecutar_adb_xiaomi("settings put global picture_backlight 6 && settings put system screen_brightness 15")
    programar_temporizador_xiaomi(minutos)
    print(f"{Color.GREEN}[✓] Xiaomi TV: Retroiluminación al 6% y temporizador de {minutos}m activado.{Color.END}\n")


def xiaomi_dia():
    print(f"\n{Color.BOLD}☀️ [XIAOMI TV] ACTIVANDO MODO DÍA...{Color.END}")
    ejecutar_adb_xiaomi("settings put global picture_backlight 100 && settings put system screen_brightness 255")
    print(f"{Color.GREEN}[✓] Xiaomi TV: Retroiluminación al 100% y brillo máximo activado.{Color.END}\n")


def xiaomi_cine():
    print(f"\n{Color.BOLD}🎬 [XIAOMI TV] ACTIVANDO MODO CINE (MODO PELÍCULA)...{Color.END}")
    ejecutar_adb_xiaomi("settings put global picture_mode 1 && settings put system tv_picture_video_game_mode 0 && settings put global tv_picture_video_allm 0")
    print(f"{Color.GREEN}[✓] Xiaomi TV: Modo Película D65 activo.{Color.END}\n")


def xiaomi_juego():
    print(f"\n{Color.BOLD}🎮 [XIAOMI TV] ACTIVANDO MODO JUEGO (LATENCIA MÍNIMA Y ALLM)...{Color.END}")
    ejecutar_adb_xiaomi("settings put global picture_mode 5 && settings put system tv_picture_video_game_mode 1 && settings put global tv_picture_video_allm 1")
    print(f"{Color.GREEN}[✓] Xiaomi TV: Modo Juego activo (Bypass de procesado y ALLM activado).{Color.END}\n")


def xiaomi_descanso():
    print(f"\n{Color.BOLD}👁️ [XIAOMI TV] ACTIVANDO MODO DESCANSO VISUAL...{Color.END}")
    ejecutar_adb_xiaomi("settings put global picture_backlight 25 && settings put system screen_brightness 40")
    print(f"{Color.GREEN}[✓] Xiaomi TV: Modo Descanso Visual activado (brillo atenuado para no forzar la vista).{Color.END}\n")


def xiaomi_vol_up():
    ejecutar_adb_xiaomi("cmd media_session volume --show --stream 3 --adj raise")


def xiaomi_vol_down():
    ejecutar_adb_xiaomi("cmd media_session volume --show --stream 3 --adj lower")


def xiaomi_play_pause():
    ejecutar_adb_xiaomi("cmd media_session dispatch play-pause")


def xiaomi_rewind():
    ejecutar_adb_xiaomi("cmd media_session dispatch rewind")


def xiaomi_fast_forward():
    ejecutar_adb_xiaomi("cmd media_session dispatch fast-forward")


def xiaomi_volumen(nivel: int, escala_porcentaje: bool = False):
    if escala_porcentaje:
        pct = max(0, min(100, int(nivel)))
        nivel_android = max(0, min(15, round(pct * 15 / 100)))
    else:
        nivel_android = max(0, min(15, int(nivel)))
    ejecutar_adb_xiaomi(f"cmd media_session volume --show --stream 3 --set {nivel_android}")
    print(f"{Color.GREEN}[✓] Xiaomi TV: Volumen ajustado a {nivel_android}/15.{Color.END}")


def xiaomi_mute():
    ejecutar_adb_xiaomi("input keyevent 164")
    print(f"{Color.GREEN}[✓] Xiaomi TV: Mute conmutado.{Color.END}")


def estado_y_info_xiaomi() -> Dict[str, Any]:
    """Devuelve estado real (on/booting/standby), volumen y retroiluminación con caché TTL."""
    global _info_cache, _info_cache_ts
    ahora = time.time()
    if ahora - _info_cache_ts < INFO_CACHE_TTL:
        return dict(_info_cache)

    ip = discovery.resolver_ip_xiaomi()
    if not discovery.puerto_abierto(ip, 5555, timeout=0.2):
        st = "booting" if (ahora - _wol_ts < BOOT_SEGUNDOS) else "standby"
        _info_cache = {"state": st, "online": False, "volume": 0, "backlight": 0}
        _info_cache_ts = ahora
        return dict(_info_cache)

    sanear_ajustes_xiaomi_si_necesario()

    vol = 0
    backlight = 0
    awake = True
    try:
        res = ejecutar_adb_xiaomi(
            'dumpsys power | grep -m1 -E "mWakefulness=|Display Power: state="; '
            'echo "P:$(settings get global picture_backlight 2>/dev/null)"; '
            'echo "B:$(settings get system screen_brightness 2>/dev/null)"; '
            'echo "V:$(settings get system volume_music_speaker 2>/dev/null)"',
            timeout=1.5,
            invalidar_cache=False,
        )
        raw_pic_backlight: Optional[int] = None
        if res and res.stdout:
            for line in res.stdout.splitlines():
                line = line.strip()
                if "mWakefulness=" in line or "Display Power:" in line:
                    low = line.lower()
                    if any(w in low for w in ("asleep", "dozing", "dreaming", "state=off")):
                        awake = False
                elif line.startswith("P:"):
                    raw = line[2:].strip()
                    if raw.isdigit():
                        raw_pic_backlight = max(0, min(100, int(raw)))
                elif line.startswith("B:"):
                    raw = line[2:].strip()
                    if raw.isdigit():
                        backlight = min(100, max(0, round((int(raw) / 255.0) * 100)))
                elif line.startswith("V:"):
                    raw = line[2:].strip()
                    if raw.isdigit():
                        vol = min(100, max(0, round((int(raw) / 15.0) * 100)))
        if raw_pic_backlight is not None:
            backlight = raw_pic_backlight
    except Exception:
        pass

    is_on = awake and backlight > 0
    state = "on" if is_on else ("booting" if (ahora - _wol_ts < BOOT_SEGUNDOS) else "standby")
    _info_cache = {
        "state": state,
        "online": is_on,
        "volume": vol if is_on else 0,
        "backlight": backlight if is_on else 0,
    }
    _info_cache_ts = time.time()
    return dict(_info_cache)


def obtener_info_xiaomi() -> dict:
    """Lee retroiluminación y volumen actuales de la Xiaomi vía ADB (compatibilidad)."""
    info = estado_y_info_xiaomi()
    return {"volume": info["volume"], "backlight": info["backlight"]}
