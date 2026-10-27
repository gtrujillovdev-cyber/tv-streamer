# 📺 TV Streamer (Mac to Android TV / Linux)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![macOS Apple Silicon](https://img.shields.io/badge/Platform-macOS%20M--Series-black.svg)](https://apple.com)
[![Android TV](https://img.shields.io/badge/Target-Android%20TV%20%7C%20Linux%20%7C%20macOS-green.svg)](https://android.com/tv)
[![Tailscale](https://img.shields.io/badge/Network-Tailscale%20%2B%20Direct%20LAN-orange.svg)](https://tailscale.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**TV Streamer** es una solución de streaming multimedia *zero-touch* que te permite transmitir cualquier video desde tu Mac (Apple Silicon) a tu Smart TV (Xiaomi, Android TV o Raspberry Pi) a pantalla completa y con un solo clic, sin escribir URLs en el mando a distancia.

Incluye una **Web UI moderna (Streamlit)** accesible desde el ordenador y el móvil, un **servidor HTTP 206 multihilo de alto rendimiento**, **automatización remota vía ADB/SSH**, y una aplicación nativa empaquetada para el **macOS Launchpad**.

---

## 🚀 Flujo de Arquitectura

```mermaid
flowchart LR
    subgraph Emisor["🖥️ Mac M4 (Emisor)"]
        UI["Streamlit UI (Port 8501)"]
        SRV["HTTP Server (Port 8080)<br/>• HTTP/1.1 Range (206)<br/>• TCP_NODELAY & 4MB Buffer<br/>• 1MB Chunks"]
        CLI["stream_video.sh / Launchpad"]
    end

    subgraph Red["🌐 Detección Inteligente de Red"]
        LAN["Direct LAN (192.168.1.x)<br/>• 0% CPU overhead<br/>• 100+ Mbps"]
        TS["Tailscale VPN (100.x.x.x)<br/>• Modo remoto cifrado"]
    end

    subgraph Receptor["📺 Xiaomi TV / Android TV"]
        ADB["ADB Daemon (Port 5555)<br/>Wakeup + Intent Dispatcher"]
        VLC["VLC / MediaCodec<br/>• Hardware Decoding<br/>• AudioTrack Sync<br/>• 4s Network Caching"]
    end

    UI -->|Controla| SRV
    CLI -->|Inicia| SRV
    UI -->|Comandos ADB| ADB
    CLI -->|Comandos ADB| ADB
    ADB -->|Despierta y Lanza| VLC
    VLC -->|Peticiones HTTP 206| Red
    Red --> SRV
```

---

## 🌟 Características Principales

- ⚡ **Zero-Touch Playback:** Envía órdenes automáticas por **ADB (Android)** o **SSH (Linux/Mac)** para despertar la pantalla, esquivar el salvapantallas y abrir el reproductor a pantalla completa sin usar el mando a distancia.
- 🎮 **Mando a Distancia Virtual en la Web:** Controla la reproducción desde tu móvil o portátil en tiempo real: Play/Pausa, saltos de $\pm 10$ segundos, control de volumen, silencio, botón inicio y detención inmediata.
- ⏱️ **Historial y Continuar Viendo:** Acceso directo a los últimos vídeos transmitidos para reanudarlos con un solo clic.
- 🏷️ **Títulos Limpios y Badges Informativos:** Formateo inteligente de nombres de archivo eliminando hashes y tags técnicos, con distintivos visuales de formato (`MP4`, `MKV`), tamaño y carpeta.
- 🔍 **Búsqueda, Filtros y Ordenación:** Filtrado instantáneo por texto, extensión de archivo y tamaño (cortos vs películas/series $\ge 500\text{ MB}$), con ordenación por fecha o nombre.
- 🚀 **Reproducción Directa (Drag & Drop):** Pega cualquier ruta o archivo externo para transmitirlo de inmediato sin necesidad de moverlo a las carpetas indexadas.
- 🎯 **Enrutamiento Inteligente LAN vs. Tailscale:** 
  - Si estás en casa en la misma red Wi-Fi, transmite por IP local directa, reduciendo a cero el consumo de CPU de la tele (sin descifrado WireGuard).
  - Si estás fuera de casa, conmuta automáticamente a la red cifrada de **Tailscale** (`100.x.x.x`).
- 🚀 **Servidor HTTP 206 Multihilo (Range Requests):**
  - Implementado con `socketserver.ThreadingMixIn` para permitir múltiples conexiones concurrentes (necesario para leer el índice `moov atom` de archivos MP4).
  - Bloques de streaming de **1 MB** y buffer de socket TCP de **4 MB** con `TCP_NODELAY`.
- 🔊 **Corrección de Desacople Audio/Video:**
  - Resuelve el desfase de 1.5s típico de videos **H.264 con B-Frames** y audio AAC 44.1 kHz en chips MediaTek mediante el motor **AudioTrack** y control de `clock-jitter`.
  - Buffer de red de **4 segundos (`network-caching = 4000`)** para absorber fluctuaciones de Wi-Fi.
- 🍏 **Integración Nativa con macOS & Multiplataforma:**
  - Instalador universal en una línea (`install.sh`), paquete `.app` para Launchpad y Docker para NAS.

---

## 📦 Estructura del Proyecto

```text
tv-streamer/
├── app.py               # Interfaz gráfica moderna en Streamlit
├── stream_manager.py    # Orquestador: ADB, SSH, IP dinámica y ciclo de vida
├── video_server.py      # Servidor HTTP 1.1 multihilo con soporte Range 206
├── stream_video.sh      # Script CLI para streaming rápido desde terminal
├── run.sh               # Lanzador del servicio web
├── stop.sh              # Script de apagado limpio y liberación de puertos
├── config.example.json  # Plantilla de configuración de dispositivos
└── requirements.txt     # Dependencias de Python
```

---

## 🛠️ Instalación Rápida

### Opción 1: Instalador Automático en 1 Línea (Recomendado)

En tu Mac o Linux, simplemente ejecuta:

```bash
curl -fsSL https://raw.githubusercontent.com/gtrujillovdev-cyber/tv-streamer/main/install.sh | bash
```

Esto instalará automáticamente las dependencias, configurará los accesos directos `tv` y creará la aplicación nativa en tu Launchpad.

Para una guía detallada sobre cómo configurar cualquier televisión y usar la app desde el móvil, consulta la [Guía de Configuración Global](docs/GLOBAL_SETUP.md).

### Opción 2: Instalación Manual

1. **Requisitos Previos:**
   - **Python 3.10+**.
   - **ADB (`android-platform-tools`)** y **ffmpeg**:
     ```bash
     brew install android-platform-tools ffmpeg
     ```
   - **Android TV / Smart TV:** Activar Opciones para desarrolladores $\rightarrow$ Depuración por red (ADB). Instalar VLC for Android.

2. **Clonar e Iniciar:**
   ```bash
   git clone https://github.com/gtrujillovdev-cyber/tv-streamer.git
   cd tv-streamer
   pip install -r requirements.txt
   ./run.sh
   ```
cp config.example.json config.json
```

---

## 🎬 Guía de Uso

### Método 1: Desde macOS Launchpad
Haz clic en el icono **TV Streamer** en tu Launchpad o abre Spotlight (`Cmd + Espacio`) y escribe `TV Streamer`. El servidor se iniciará y abrirá la interfaz en tu navegador por defecto.

### Método 2: Interfaz Web (Móvil / Desktop)
```bash
./run.sh
```
- **En tu Mac:** [http://localhost:8501](http://localhost:8501)
- **Desde tu móvil en el sofá:** `http://<IP_TAILSCALE>:8501`

### Método 3: Terminal CLI
```bash
# Transmitir a Xiaomi TV
./stream_video.sh ~/Movies/pelicula.mp4 100.90.61.47 android

# Transmitir a Raspberry Pi por SSH
./stream_video.sh ~/Movies/pelicula.mp4 pi@100.95.199.1 linux
```

### 🛑 Detener el Servicio
```bash
./stop.sh
# O usando los alias de terminal:
tv-stop
```

---

## 🔧 Ajustes Clave para Xiaomi / Android TV

Si experimentas tirones o desfase de audio en archivos H.264/MKV de alto bitrate:

1. **Salida de Audio:** En VLC en la tele, ve a **Ajustes $\rightarrow$ Audio $\rightarrow$ Salida de audio** y selecciona **`AudioTrack`** en lugar de OpenSL ES.
2. **Aceleración por Hardware:** Ve a **Ajustes $\rightarrow$ Vídeo $\rightarrow$ Aceleración hardware** y asegúrate de que esté en **Completa**.
3. **Caché de red:** En **Ajustes $\rightarrow$ Avanzado $\rightarrow$ Caché de red**, pon **2000 ms** o **3000 ms**.

---

## 📄 Licencia

Distribuido bajo la Licencia MIT. Consulta `LICENSE` para más detalles.
