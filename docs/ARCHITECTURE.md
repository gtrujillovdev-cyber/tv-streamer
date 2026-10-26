# 🏗️ TV Streamer - Documentación Técnica y Arquitectura

Este documento recopila las decisiones de diseño de software y red, los cuellos de botella detectados durante el desarrollo y las soluciones de bajo nivel implementadas.

---

## 1. El Desafío: Zero-Touch Streaming en Smart TVs

En televisores Smart TV (como Xiaomi TV / Android TV), la transmisión de video desde un ordenador suele requerir:
1. Copiar archivos por USB o SMB.
2. Escribir manualmente URLs kilométricas con el mando a distancia en VLC.
3. Usar soluciones pesadas tipo Plex/Jellyfin que requieren transcodificación y servidores permanentes.

**El objetivo de TV Streamer:** Permitir que desde el Mac (o desde el móvil sentado en el sofá), con un solo clic, el video empiece a reproducirse en la tele a pantalla completa mediante aceleración de hardware.

---

## 2. Decisiones de Arquitectura y Red

### 2.1 Enrutamiento Híbrido: Tailscale vs. Direct LAN

- **Problema con Tailscale en Android TV de bajo consumo:**  
  La Xiaomi TV utiliza un SoC MediaTek ARM Cortex-A53. Al transmitir un video 1080p a través de la interfaz VPN de Tailscale, el proceso en espacio de usuario (`com.tailscale.ipn` en Go) debe descifrar paquetes WireGuard continuamente. Esto consumía entre el 35% y el 50% de la CPU de la tele, provocando caídas de frames y desincronización de audio.
- **Solución implementada:**  
  Detección automática de subred local. Si tanto el Mac M4 como la TV están en la misma red Wi-Fi de casa (`192.168.1.x`), el servidor envía el stream a través de la IP local (`192.168.1.205`). Esto libera a la CPU de la TV de cualquier sobrecarga de cifrado, multiplicando el ancho de banda disponible por cinco. Si el usuario está fuera de casa, conmuta a Tailscale (`100.x.x.x`).

### 2.2 Servidor HTTP Multihilo con Soporte Range 206 (`socketserver.ThreadingMixIn`)

- **El cuello de botella de `http.server` mono-hilo:**  
  Al reproducir un archivo `.mp4`, los reproductores como VLC no descargan el archivo de forma lineal:
  1. Abren una conexión inicial para leer la cabecera.
  2. Abren una segunda conexión simultánea para leer el bloque `moov atom` (índice de metadatos y pistas) situado al final del archivo.
  3. Abren conexiones adicionales para trozos de audio y video.
  
  Con el servidor HTTP estándar de Python (mono-hilo), la primera petición bloqueaba el bucle `while remaining > 0`. La segunda conexión que intentaba leer el final del archivo quedaba encolada indefinidamente, provocando que la pantalla de la TV se quedara en negro absoluto.
- **Solución:**  
  Implementar un servidor HTTP multihilo usando `ThreadingMixIn, HTTPServer`:
  ```python
  class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
      daemon_threads = True
  ```
  Permite atender lecturas de rangos de bytes concurrentes en paralelo sin que una petición bloquee a las demás.

### 2.3 Ajustes de Sockets del Kernel de macOS Darwin

- **`TCP_NODELAY`:** Desactiva el algoritmo de Nagle, garantizando que los paquetes de video se transmitan inmediatamente por el Wi-Fi sin esperar a acumularse.
- **`SO_SNDBUF` a 4 MB:** Evita que el buffer de envío del kernel se sature y ahogue la tasa de transferencia hacia el reproductor.
- **Bloques de 1 MB:** Reduce los cambios de contexto en el espacio de usuario.

---

## 3. Resolución del Desacople de Audio/Video (Audio Desync)

### 3.1 Análisis de Paquetes con `ffprobe`

Al analizar videos deportivos grabados (como clasificaciones de MotoGP), detectamos:
- **Video:** H.264 Main Profile con **B-Frames** (fotogramas bidireccionales desordenados temporalmente).
- **Audio:** AAC a **44.1 kHz**, mientras que el hardware de sonido de la tele corre nativamente a **48 kHz**.

### 3.2 El Retardo Fijo de 1500 ms en VLC

Al consultar `adb logcat`, encontramos la advertencia continua:
```text
libvlc decoder: Timestamp conversion failed (delay 1500000, buffering 100000)
libvlc decoder: discarded audio buffer
```
`delay 1500000` correspondía a un desfase exacto de **1.5 segundos**. El pipeline de reordenación de B-Frames en el decodificador de hardware MediaTek introducía ese retraso, pero el motor de audio clásico de VLC (*OpenSL ES*) no compensaba este retardo, reproduciendo el sonido 1.5 segundos adelantado y descartando muestras de audio.

### 3.3 Solución:

1. **Cambio al motor `AudioTrack`:** En Android TV, `AudioTrack` está acoplado al subsistema `SurfaceFlinger`, permitiendo que el hardware sincronice automáticamente la pista de audio con los Presentation Time Stamps (PTS) de la pantalla.
2. **Buffer de Red a 4000 ms (`network-caching = 4000`):** Absorbe los picos de jitter de hasta 120 ms medidos en la red Wi-Fi sin vaciar el buffer del reproductor.

---

## 4. Automatización Remota vía ADB

Para conseguir una experiencia 100% *zero-touch* en Android TV:

```bash
# 1. Conectar al demonio ADB de la tele
adb connect 100.90.61.47:5555

# 2. Despertar la pantalla si está en reposo o con salvapantallas (Daydream)
adb shell input keyevent KEYCODE_WAKEUP

# 3. Forzar cierre de instancias colgadas
adb shell am force-stop org.videolan.vlc

# 4. Lanzar el Intent de reproducción directa con flags de aceleración
adb shell am start \
    -a android.intent.action.VIEW \
    -d "http://192.168.1.205:8080/video.mp4" \
    -t "video/mp4" \
    -f 0x10000000 \
    --ei "hardware_acceleration" 2 \
    --ei "network-caching" 4000 \
    --ei "clock-jitter" 2000 \
    --ei "clock-synchro" 0 \
    org.videolan.vlc
```
