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

## 📺 Preparación de la Smart TV (Solo la primera vez, 2 minutos)

TV Streamer se comunica directamente con el reproductor **VLC** de tu televisión a través de la red local o Tailscale:

### Paso 1: Instalar VLC en la TV
1. Entra en Google Play Store / Amazon Appstore en tu TV.
2. Busca e instala **VLC for Android**.
3. Abre VLC, pulsa en *Ajustes* ⚙️ -> *Audio* -> **Salida de Audio** -> Selecciona **AudioTrack**.
*(Esto garantiza sincronización milimétrica entre imagen y sonido).*

### Paso 2: Activar la Depuración de Red (ADB)
1. En la TV, entra en **Ajustes** -> **Preferencias del dispositivo** -> **Información**.
2. Pulsa 7 veces seguidas sobre **Compilación** hasta que aparezca el mensaje *"¡Ya eres desarrollador!"*.
3. Vuelve atrás y entra en el nuevo menú **Opciones para desarrolladores**.
4. Activa **Depuración por USB** y **Depuración de red / inalámbrica**.
5. Anota la IP local que muestra tu TV (ej. `192.168.1.150`).

> 💡 **La primera vez que transmitas:** Aparecerá un aviso en la pantalla de tu TV diciendo *"¿Permitir depuración por USB?"*. Marca la casilla **"Permitir siempre desde este equipo"** y pulsa **Aceptar**.

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
