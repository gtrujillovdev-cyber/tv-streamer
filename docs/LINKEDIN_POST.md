# 📱 Publicación para LinkedIn: TV Streamer

A continuación tienes la propuesta de publicación diseñada para maximizar el engagement profesional en LinkedIn, destacando el reto técnico, la arquitectura de red y la resolución de problemas de bajo nivel.

---

### Versión en Español (Recomendada para tu perfil)

```markdown
¿Alguna vez has intentado escribir una URL de streaming con el mando a distancia de una Smart TV? Es la peor experiencia de usuario posible. 🤦‍♂️

Este fin de semana decidí resolver este problema de raíz: quería transmitir cualquier video local desde mi MacBook (Apple Silicon M4) directamente a mi Xiaomi TV (Android TV) a pantalla completa con un solo clic desde el sofá, aprovechando al 100% la aceleración por hardware de la tele y sin tocar el mando.

Lo que empezó como un simple script de streaming terminó siendo una masterclass de ingeniería de sistemas, redes y multimedia de bajo nivel. 🛠️

Aquí algunos de los desafíos técnicos más interesantes que resolví:

1️⃣ Automatización Zero-Touch vía ADB & Intent Dispatching:
En lugar de depender de servidores DLNA lentos, utilicé Android Debug Bridge (ADB sobre red). El sistema despierta la TV automáticamente, supera el salvapantallas de Android TV y despacha un Intent directo a VLC con flags de pantalla completa y decodificación por hardware nativa.

2️⃣ Cuello de botella HTTP 206 (Range Requests) & Concurrencia:
Al reproducir archivos MP4 grandes, los reproductores no descargan linealmente: abren conexiones paralelas para leer los primeros fotogramas y el índice "moov atom" al final del archivo. El servidor estándar de Python (mono-hilo) se bloqueaba al servir la primera conexión y dejaba la tele en pantalla negra. La solución: un servidor multihilo con `ThreadingMixIn`, soporte nativo de HTTP/1.1 persistente, `TCP_NODELAY` y buffers de socket de 4 MB en el kernel de macOS.

3️⃣ Enrutamiento inteligente: LAN directa vs. Tailscale VPN:
Detectamos que en SoCs modestos de TV (MediaTek A53), descifrar paquetes WireGuard de Tailscale en espacio de usuario consumía hasta el 50% de la CPU. Implementé conmutación inteligente: si ambos dispositivos están en la misma Wi-Fi, transmite a velocidad de red local pura (100+ Mbps y <5% CPU). Si estás fuera de casa, conmuta automáticamente a la red cifrada de Tailscale.

4️⃣ Diagnóstico y corrección del desacople Audio/Video (B-Frames & Audio HAL):
En transmisiones deportivas (como MotoGP en 1080p), la imagen y el sonido se desfasaban 1.5 segundos exactos (`delay 1500000` en logcat). Analizando los paquetes con `ffprobe`, descubrimos que la pipeline de reordenación de B-Frames del decodificador hardware acumulaba retardo mientras el motor de audio clásico (OpenSL ES) no lo esperaba. Forzando la salida a `AudioTrack` acoplada a `SurfaceFlinger` y un buffer de red de 4s, el sonido y la imagen quedaron sincronizados al milisegundo.

Para redondear la experiencia:
🍏 Empaquetado como aplicación nativa de macOS (.app) con icono en el Launchpad.
📱 Dashboard interactivo en Streamlit accesible desde el móvil.
💻 Atajos de terminal (`tv`, `tvstreamer`, `tv-stop`).

El proyecto es 100% open-source y ya está publicado en GitHub:
👉 https://github.com/gtrujillovdev-cyber/tv-streamer

¿Cómo resolvéis vosotros la transmisión multimedia local entre diferentes sistemas operativos? ¡Os leo en comentarios! 👇

#Python #SoftwareEngineering #Networking #macOS #AndroidTV #Tailscale #Streaming #OpenSource #DevOps
```
