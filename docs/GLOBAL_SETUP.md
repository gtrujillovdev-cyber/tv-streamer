# 🌐 TV Streamer - Guía de Configuración Global para Cualquier Hogar

Esta guía detalla cómo desplegar y usar **TV Streamer** en cualquier casa con cualquier combinación de ordenador (Mac / Linux / Windows / NAS) y Smart TV (Android TV, Google TV, Xiaomi TV, TCL, Sony, Chromecast, Fire TV).

---

## 🚀 Instalación en 1 Línea (Mac / Linux)

Abre la terminal en tu ordenador y ejecuta:

```bash
curl -fsSL https://raw.githubusercontent.com/gtrujillovdev-cyber/tv-streamer/main/install.sh | bash
```

El instalador automático se encarga de todo:
1. Comprueba e instala dependencias (`adb`, `ffmpeg`, `python3`).
2. Crea el icono nativo **TV Streamer.app** en tu Launchpad / Aplicaciones.
3. Configura los comandos de terminal `tv` (iniciar) y `tv-stop` (detener).
4. Abre la interfaz web en `http://localhost:8501`.

---

## 🏡 Modos de Reproducción Disponibles

TV Streamer incluye una arquitectura híbrida con dos modos según las preferencias del usuario:

### Modo 1: Google Cast (Zero-Config) — ¡El más fácil para cualquier hogar!
- **Requisitos en la TV:** **NINGUNO**. Funciona tal como sacas la tele de la caja.
- **Sin opciones de desarrollador, sin ADB, sin instalar apps en la TV.**
- La app detecta tu Smart TV en el Wi-Fi automáticamente (igual que cuando transmites desde YouTube o Netflix en el móvil).
- Soporta control multimedia táctil (Play, Pausa, saltos de 10s, Volumen y Stop).
- Compatible con cualquier Smart TV Android, Google TV, Xiaomi, Sony, TCL, Philips o dongle Chromecast.

### Modo 2: VLC Pro (ADB) — Máximo Rendimiento y Control Total
- Utiliza la API de depuración de Android (ADB) para forzar aceleración por hardware MediaCodec y decodificación de audio directa mediante AudioTrack.
- Permite encendido automático desde el Mac y despertar pantallas en reposo profundo.

---

## 📺 Preparación de la Smart TV

### Si usas el Modo Google Cast (Zero-Config):
¡Ya has terminado! Solo asegúrate de que tu Smart TV y tu ordenador estén conectados al mismo Wi-Fi de tu casa.

### Si usas el Modo VLC Pro:
1. En la TV, entra en Google Play Store e instala **VLC for Android**.
2. Entra en **Ajustes** -> **Preferencias del dispositivo** -> **Información**.
3. Pulsa 7 veces seguidas sobre **Compilación** hasta activar el modo desarrollador.
4. En **Opciones para desarrolladores**, activa **Depuración de red / inalámbrica**.
5. Anota la IP local que muestra tu TV (ej. `192.168.1.150`).

> 💡 **La primera vez que transmitas por VLC Pro:** Aparecerá un aviso en la pantalla de tu TV diciendo *"¿Permitir depuración por USB?"*. Marca la casilla **"Permitir siempre desde este equipo"** y pulsa **Aceptar**.

---

## 🏡 Modos de Conexión Disponibles

| Modo | Escenario | Rendimiento | Configuración |
|---|---|---|---|
| **🏠 Red LAN Local** | Mac y TV conectados al mismo Wi-Fi de casa | **Máximo (0ms jitter, 0% CPU en TV)** | Solo necesitas la IP local de la TV. Sin cuentas ni registros. |
| **🌐 Tailscale Mesh VPN** | Transmisión remota entre casas diferentes o vía 4G/5G | **Cifrado WireGuard punto a punto** | Instalar Tailscale en el Mac y en la TV. Conexión segura sin abrir puertos en el router. |

---

## 📱 Control Remoto Virtual desde el Móvil

Puedes usar tu teléfono (iPhone / Android) o tablet como mando a distancia del streaming:
1. Asegúrate de que el móvil esté conectado al mismo Wi-Fi de tu casa.
2. En el navegador del móvil, abre: `http://<IP_DE_TU_MAC>:8501`
*(La app te muestra la IP exacta de tu Mac en la esquina superior izquierda de la pantalla).*
3. Tendrás en tu mano el mando a distancia táctil:
   - ⏯️ Reproducir / Pausa
   - ⏪ -10s / ⏩ +10s
   - 🔊 Subir / Bajar volumen / Mute
   - 🏠 Volver al inicio de la TV
   - ⏹️ Detener reproducción

---

## 🐳 Despliegue en Servidor Casero / NAS (Docker)

Si dispones de un NAS (Synology, QNAP, Unraid, TrueNAS) o un mini PC / Raspberry Pi siempre encendido:

```bash
docker compose up -d
```

TV Streamer estará disponible las 24 horas del día para toda la familia en el puerto `8501`.
