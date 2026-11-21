"""Temporizadores de apagado."""
import os
import time
from .config import TIMER_FILE_LG, TIMER_FILE_XIAOMI_META


def _leer_restante(ruta: str) -> int:
    if not os.path.exists(ruta):
        return 0
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            parts = f.read().strip().split(":")
        if len(parts) >= 2:
            dur, ini = parts[-2], parts[-1]
            restante = int(dur) - (int(time.time()) - int(ini))
            return max(0, restante)
    except Exception:
        pass
    return 0


def obtener_tiempo_restante_timer(dispositivo: str) -> int:
    """Devuelve los segundos restantes del temporizador o 0 si no hay."""
    if dispositivo == "lg":
        return _leer_restante(TIMER_FILE_LG)
    if dispositivo == "xiaomi":
        return _leer_restante(TIMER_FILE_XIAOMI_META)
    return 0
