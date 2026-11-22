# CLAUDE.md — Tv-streamer

## Propósito
Streamer de video y canales en directo (Acestream) desde el Mac al televisor LG WebOS.
UI: Streamlit en :8501. API interna Acestream: :8891.

## Arquitectura principal

```
Tv-streamer (Streamlit :8501)
    └── stream_manager.py   ← núcleo: lógica TV, Acestream, mando_tv wrappers
    └── app.py              ← UI Streamlit
    └── acestream_api.py    ← REST :8891 para mando-tv remoto
    └── ace_proxy.py        ← proxy HTTP que sigue redirects 127.0.0.1 del engine
    └── mando_tv/           ← subpaquete del proyecto mando-tv (copia sincronizada)
    └── canales_acestream.json ← canales favoritos (MotoGP, Eurosport, beIN, etc.)
    └── config.json         ← dispositivos TV, directorio de videos, puerto HTTP
```

## Pipeline Acestream → LG TV (OBLIGATORIO seguir este flujo)

```
Docker acestream (6878)
  └── ace_proxy.py (:8889)   ← sigue redirects 127.0.0.1 internamente
        └── ffmpeg HLS → /tmp/hls_tvstreamer/stream.m3u8
              └── python3 -m http.server (:8890) sirve HLS_DIR
                    └── player.html → <video> + requestFullscreen()
                          └── ssap://system.launcher/open → LG browser → pantalla completa
```

La función principal es `StreamController.start_acestream(hash, device_info)`.
Para WebOS siempre usar `acestream_hls_start` + `lgtv_webos_open_fullscreen`.
**Nunca usar ssap://media.viewer/open ni com.webos.app.mediadiscovery directamente** — no funcionan en WebOS 6 UP75.

## Canales favoritos (canales_acestream.json)
- Favoritos con `slug`: buscan señales en acestreamid.com al click
- Favoritos con `hash`: lanzamiento directo
- Gestión: `load/save/add/remove/resolve_ace_channel` en stream_manager.py
- La búsqueda usa `_ssl_ctx()` (sin verificación) por bug de certificados en macOS

## Dispositivos configurados (config.json)
- **LG 65UP75 (WebOS)**: 192.168.1.193 — `os_type: webos` — cliente activo
- **TV (Google Cast)**: 192.168.1.217 — `os_type: cast`
- **TV (Xiaomi VLC Pro)**: Tailscale 100.90.61.47 — `os_type: android`

## LG TV — datos clave
- Modelo: 65UP75006LF | WebOS 6
- IP: 192.168.1.193 (DHCP — puede cambiar; `mando_tv/discovery.py` resuelve por MAC)
- MAC: 74:e6:b8:26:02:0e
- Clave WebOS: `~/.lgtv_key` (también en `~/.config/lg_tv/config.json` via `LG_CONFIG`)

## mando_tv (subpaquete)
- Código fuente autoritativo: `~/Documents/projects/Tools/mando-tv/`
- Cuando se modifique `mando_tv/` en Tv-streamer, sincronizar al repo mando-tv y hacer commit allí también
- `_init_mando_tv()` propaga IP/MAC/LG_CONFIG desde config.json a las vars de entorno
- Acción `browser` en lg.py: `run_lg("browser", {"url": url})` → ssap://system.launcher/open

## LaunchAgents en el M4 (arrancan al login)
- `com.gtrujillo.mandotv` → `~/Documents/projects/Tools/mando-tv` (:8899)
- `com.gtrujillo.acestream-api` → `acestream_api.py` (:8891)
- Logs: `/tmp/mando_tv.log`, `/tmp/mando_tv_err.log`, `/tmp/acestream_api.log`

## Despliegue en mac-pro-2014 (mbp1 — 100.108.212.124 / 192.168.1.158)
- Servidor mando-tv: `~/mando-tv/` (watchdog cron cada minuto)
- `ACESTREAM_API_HOST=192.168.1.159` apunta al M4 para el pipeline HLS
- Desplegar cambios: `rsync -az ~/Documents/projects/Tools/mando-tv/mando_tv/ 100.108.212.124:~/mando-tv/mando_tv/`
- Reiniciar: `ssh 100.108.212.124 "pkill -9 -f '[m]ando_tv'; sleep 1; ~/mando-tv/watchdog.sh"`

## Reglas de desarrollo
1. **Acestream search**: siempre usar `_ssl_ctx()` para bypass SSL en macOS.
2. **Pipeline LG**: solo HLS + player.html funciona en WebOS 6. No usar media.viewer.
3. **IP LG dinámica**: confiar en `mando_tv/discovery.py` que resuelve por MAC.
4. **Al modificar mando_tv/**: sincronizar a `Tools/mando-tv/` y commitear allí también.
5. **Al añadir canales**: editar `canales_acestream.json` con `{name, slug, icon}` para búsqueda lazy, o `{name, hash, icon}` para hash fijo.
6. **acestream_api.py** (:8891) siempre debe estar corriendo en el M4 para que el mando iPhone funcione.
