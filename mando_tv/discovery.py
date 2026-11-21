"""Descubrimiento automático y resolución dinámica de IPs por dirección MAC."""
import json
import os
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
from . import config


def _cargar_ip_config(ruta: str, fallback: str) -> str:
    try:
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                ip = json.load(f).get("ip")
                if ip:
                    return ip
    except Exception:
        pass
    return fallback


_lock = threading.Lock()
_estado: Dict[str, Dict] = {
    "lg": {
        "ip": _cargar_ip_config(config.LG_CONFIG_PATH, config.IP_LG),
        "ts_ok": 0.0,
        "ts_scan": 0.0,
        "puerto": 3000,
    },
    "xiaomi": {
        "ip": _cargar_ip_config(config.XIAOMI_CONFIG_PATH, config.IP_XIAOMI),
        "ts_ok": 0.0,
        "ts_scan": 0.0,
        "puerto": 5555,
    },
}


def _normalizar_mac(mac_str: str) -> str:
    """Normaliza cualquier formato MAC (con o sin ceros a la izquierda) a xx:xx:xx:xx:xx:xx."""
    try:
        partes = mac_str.strip().lower().replace("-", ":").split(":")
        if len(partes) == 6:
            return ":".join(f"{int(p, 16):02x}" for p in partes)
    except Exception:
        pass
    return mac_str.strip().lower()


def puerto_abierto(ip: str, puerto: int, timeout: float = 0.2) -> bool:
    """Verifica de forma rápida si un puerto TCP está abierto."""
    if not ip:
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((ip, puerto)) == 0
    except Exception:
        return False


def obtener_ips_arp_por_mac(mac_objetivo: str) -> List[str]:
    """Obtiene todas las IPs asociadas a una MAC en la tabla ARP del sistema."""
    mac_norm = _normalizar_mac(mac_objetivo)
    ips: List[str] = []

    if os.path.exists("/proc/net/arp"):
        try:
            with open("/proc/net/arp", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4 and _normalizar_mac(parts[3]) == mac_norm:
                        ips.append(parts[0])
            if ips:
                return ips
        except Exception:
            pass

    try:
        salida = subprocess.check_output(["arp", "-an"], text=True, stderr=subprocess.DEVNULL, timeout=2.0)
        for linea in salida.splitlines():
            partes = linea.split()
            if len(partes) >= 4 and _normalizar_mac(partes[3]) == mac_norm:
                ips.append(partes[1].strip("()"))
    except Exception:
        pass

    return ips


def _ip_de_subred_base(ip_referencia: str) -> str:
    partes = (ip_referencia or "").split(".")
    if len(partes) == 4 and all(p.isdigit() for p in partes):
        return ".".join(partes[:3]) + "."
    return "192.168.1."


def escanear_subred(puerto: int, subred_base: str = "192.168.1.", timeout: float = 0.15) -> List[str]:
    """Escanea la subred completa /24 en paralelo buscando un puerto específico."""
    ips_a_probar = [f"{subred_base}{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=64) as pool:
        resultados = pool.map(lambda ip: ip if puerto_abierto(ip, puerto, timeout=timeout) else None, ips_a_probar)
        return [ip for ip in resultados if ip]


def _elegir_ip_por_mac(candidatas: List[str], mac_objetivo: str) -> Optional[str]:
    """Filtra las IPs con puerto abierto verificando que su MAC ARP coincida con la TV."""
    if not candidatas:
        return None
    ips_mac = set(obtener_ips_arp_por_mac(mac_objetivo))
    for ip in candidatas:
        if ip in ips_mac:
            return ip
    if len(candidatas) == 1 and not ips_mac:
        return candidatas[0]
    return None


def _guardar_ip_json(ruta: str, nueva_ip: str):
    try:
        parent = os.path.dirname(ruta)
        if parent:
            os.makedirs(parent, exist_ok=True)
        datos = {}
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
        datos["ip"] = nueva_ip
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2)
    except Exception:
        pass


def _spec_dispositivo(nombre: str):
    if nombre == "lg":
        return config.MAC_LG, config.LG_CONFIG_PATH, "LG TV", "IP_LG"
    return config.MAC_XIAOMI, config.XIAOMI_CONFIG_PATH, "Xiaomi TV", "IP_XIAOMI"


def _actualizar_ip(nombre: str, nueva_ip: str):
    _, ruta, etiqueta, attr = _spec_dispositivo(nombre)
    ant = _estado[nombre]["ip"]
    if ant != nueva_ip:
        print(f"📡 [DISCOVERY] {etiqueta} detectada en nueva IP: {nueva_ip} (anterior: {ant})")
        _estado[nombre]["ip"] = nueva_ip
        setattr(config, attr, nueva_ip)
        _guardar_ip_json(ruta, nueva_ip)


def _scan_bg(nombre: str):
    mac, _, _, _ = _spec_dispositivo(nombre)
    with _lock:
        puerto = _estado[nombre]["puerto"]
        base = _ip_de_subred_base(_estado[nombre]["ip"])
    elegida = _elegir_ip_por_mac(escanear_subred(puerto, subred_base=base), mac)
    if elegida:
        with _lock:
            _actualizar_ip(nombre, elegida)
            _estado[nombre]["ts_ok"] = time.time()


def _resolver_ip(nombre: str, forzar: bool = False) -> str:
    mac, _, _, _ = _spec_dispositivo(nombre)
    ahora = time.time()
    with _lock:
        st = _estado[nombre]
        ip_actual = st["ip"]
        puerto = st["puerto"]
        if not forzar and (ahora - st["ts_ok"] < 20.0):
            return ip_actual

    if not forzar and puerto_abierto(ip_actual, puerto, timeout=0.15):
        with _lock:
            _estado[nombre]["ts_ok"] = time.time()
        return ip_actual

    for ip in obtener_ips_arp_por_mac(mac):
        if puerto_abierto(ip, puerto, timeout=0.15):
            with _lock:
                _actualizar_ip(nombre, ip)
                _estado[nombre]["ts_ok"] = time.time()
            return ip

    if forzar:
        elegida = _elegir_ip_por_mac(
            escanear_subred(puerto, subred_base=_ip_de_subred_base(ip_actual)), mac
        )
        if elegida:
            with _lock:
                _actualizar_ip(nombre, elegida)
                _estado[nombre]["ts_ok"] = time.time()
            return elegida
    else:
        lanzar = False
        with _lock:
            if ahora - _estado[nombre]["ts_scan"] > 60.0:
                _estado[nombre]["ts_scan"] = ahora
                lanzar = True
        if lanzar:
            threading.Thread(target=_scan_bg, args=(nombre,), daemon=True).start()

    return ip_actual


def resolver_ip_lg(forzar: bool = False) -> str:
    """Resuelve la IP viva de la televisión LG 65\" sin bloquear otros hilos."""
    return _resolver_ip("lg", forzar=forzar)


def resolver_ip_xiaomi(forzar: bool = False) -> str:
    """Resuelve la IP viva de la televisión Xiaomi sin bloquear otros hilos."""
    return _resolver_ip("xiaomi", forzar=forzar)
