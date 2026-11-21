"""Diagnóstico de estado."""
import os
import time
from . import discovery, timers, xiaomi
from .config import Color, TIMER_FILE_LG, TIMER_FILE_XIAOMI_META
from .lg import run_lg


def estado_sistema():
    print(f"\n{Color.BOLD}======================================================================{Color.END}")
    print(f"{Color.BOLD} 📊 ESTADO DEL SISTEMA MULTI-TV & CONTROL HOGAR{Color.END}")
    print(f"{Color.BOLD}======================================================================{Color.END}")

    ip_lg = discovery.resolver_ip_lg()
    lg_online = discovery.puerto_abierto(ip_lg, 3000, timeout=0.5)

    print(f"{Color.BOLD}📺 LG 65\" ({ip_lg}):{Color.END}")
    if lg_online:
        app_activa = run_lg("status") or "Encendida"
        print(f"  • Estado: {Color.GREEN}🟢 ENCENDIDA / ONLINE{Color.END}")
        print(f"  • App en primer plano: {Color.CYAN}{app_activa}{Color.END}")
    else:
        print(f"  • Estado: {Color.YELLOW}⚪ EN REPOSO / APAGADA{Color.END}")

    if os.path.exists(TIMER_FILE_LG):
        try:
            with open(TIMER_FILE_LG, "r", encoding="utf-8") as f:
                parts = f.read().strip().split(":")
            if len(parts) >= 3:
                _, duracion, inicio = parts
                restante = max(0, int(duracion) - int(time.time() - int(inicio)))
                print(f"  • Temporizador: {Color.MAGENTA}⏱️ ACTIVO (~{restante // 60}m restantes para apagar){Color.END}")
            else:
                print(f"  • Temporizador: {Color.MAGENTA}⏱️ ACTIVO (PID en ejecución){Color.END}")
        except Exception:
            print(f"  • Temporizador: {Color.MAGENTA}⏱️ ACTIVO{Color.END}")
    else:
        print("  • Temporizador: Inactivo")

    ip_xm = discovery.resolver_ip_xiaomi()
    xm_adb_open = discovery.puerto_abierto(ip_xm, 5555, timeout=0.5)

    print(f"\n{Color.BOLD}📺 Xiaomi TV ({ip_xm}):{Color.END}")
    if xm_adb_open:
        info = xiaomi.estado_y_info_xiaomi()
        if info.get("state") == "on":
            estado_xm = f"{Color.GREEN}🟢 ENCENDIDA (Awake | Brillo {info.get('backlight', 0)}%){Color.END}"
        else:
            estado_xm = f"{Color.YELLOW}⚪ EN REPOSO (Asleep / Pantalla off){Color.END}"
        print(f"  • Estado: {estado_xm}")

        restante_xm = timers.obtener_tiempo_restante_timer("xiaomi")
        if os.path.exists(TIMER_FILE_XIAOMI_META) and restante_xm > 0:
            print(f"  • Temporizador: {Color.MAGENTA}⏱️ ACTIVO (~{restante_xm // 60}m restantes para apagar){Color.END}")
        else:
            print("  • Temporizador: Inactivo")
    else:
        print(f"  • Estado: {Color.YELLOW}⚪ DESCONECTADA / APAGADA{Color.END}")

    print(f"{Color.BOLD}======================================================================{Color.END}\n")
