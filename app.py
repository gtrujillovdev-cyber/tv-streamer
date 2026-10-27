import streamlit as st
import os
import time
from pathlib import Path
from stream_manager import (
    load_config, save_config, get_tailscale_ip, get_local_lan_ip, get_tailscale_peers,
    scan_videos, get_thumbnail, StreamController, clean_title,
    get_history, add_to_history, clear_history, discover_android_tvs
)

st.set_page_config(
    page_title="TV Streamer Pro",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom High-End Styling
st.markdown("""
<style>
    .remote-card {
        background: linear-gradient(135deg, #1e1e2f 0%, #252538 100%);
        border: 1px solid #4f46e5;
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 24px;
        box-shadow: 0 8px 24px rgba(79, 70, 229, 0.15);
    }
    .remote-title {
        color: #818cf8;
        font-weight: 700;
        font-size: 16px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .video-card {
        background-color: #181820;
        border-radius: 12px;
        padding: 12px;
        border: 1px solid #2a2a38;
        margin-bottom: 16px;
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .video-card:hover {
        transform: translateY(-3px);
        border-color: #6366f1;
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.45);
    }
    .clean-title {
        font-weight: 600;
        font-size: 15px;
        color: #f8fafc;
        margin-top: 8px;
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .raw-filename {
        font-size: 11px;
        color: #64748b;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-bottom: 8px;
    }
    .badge-container {
        display: flex;
        gap: 6px;
        margin-bottom: 10px;
        flex-wrap: wrap;
    }
    .badge {
        font-size: 11px;
        padding: 2px 7px;
        border-radius: 6px;
        font-weight: 600;
        text-transform: uppercase;
    }
    .badge-ext {
        background-color: #312e81;
        color: #c7d2fe;
    }
    .badge-size {
        background-color: #1e293b;
        color: #94a3b8;
        border: 1px solid #334155;
    }
    .badge-folder {
        background-color: #1e1e24;
        color: #64748b;
        font-size: 10px;
    }
    .history-card {
        background: #1e1e28;
        border-left: 4px solid #6366f1;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.15s ease;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Config & Controllers
cfg = load_config()
st.session_state.config = cfg

if "stream_ctrl" not in st.session_state:
    st.session_state.stream_ctrl = StreamController.get_instance()

if "last_message" not in st.session_state:
    st.session_state.last_message = None

if "discovered_devices" not in st.session_state:
    st.session_state.discovered_devices = None

ctrl = st.session_state.stream_ctrl
ts_ip = get_tailscale_ip()
lan_ip = get_local_lan_ip()
ts_peers = get_tailscale_peers()

# ==========================================
# SIDEBAR: DISPOSITIVOS Y RED
# ==========================================
with st.sidebar:
    st.title("📺 TV Streamer")
    st.caption("Streaming ultra-rápido LAN + Tailscale")

    # Network Status Pills
    st.markdown(f"""
    <div style="background-color: #111e19; border: 1px solid #10b981; border-radius: 8px; padding: 8px 12px; margin-bottom: 12px;">
        <div style="color: #34d399; font-weight: 700; font-size: 13px;">● Red Lista</div>
        <div style="font-size: 12px; color: #a7f3d0; margin-top: 2px;">
            🏠 LAN Local: <code>{lan_ip}</code><br>
            🌐 Tailscale: <code>{ts_ip}</code>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Dispositivo Activo
    st.subheader("🎯 Dispositivo Destino")
    devices = cfg.get("devices", {})
    device_names = list(devices.keys())

    if not device_names:
        devices["TV (Xiaomi)"] = {
            "host": "100.90.61.47",
            "lan_ip": "192.168.1.208",
            "user": "",
            "os_type": "android",
            "player": "vlc",
            "display": ""
        }
        cfg["devices"] = devices
        save_config(cfg)
        device_names = list(devices.keys())

    selected_device_name = st.selectbox(
        "Seleccionar pantalla:",
        options=device_names,
        index=device_names.index(cfg.get("active_device")) if cfg.get("active_device") in device_names else 0
    )
    if selected_device_name != cfg.get("active_device"):
        cfg["active_device"] = selected_device_name
        save_config(cfg)

    active_dev_info = devices.get(selected_device_name, {})
    dev_host = active_dev_info.get("host", "")
    dev_lan = active_dev_info.get("lan_ip", "")

    # Comprobación de estado del host
    is_online = False
    for p_name, p_data in ts_peers.items():
        if p_data.get("ip") == dev_host or p_name.lower() in selected_device_name.lower():
            is_online = p_data.get("online", False)
            break

    status_color = "#22c55e" if is_online else "#eab308"
    status_text = "🟢 En línea (Tailscale)" if is_online else "🟡 En espera / LAN Local"

    st.markdown(f"""
    <div style="font-size: 12px; margin-bottom: 12px; line-height: 1.5;">
        <b>Estado:</b> <span style="color: {status_color}; font-weight: 600;">{status_text}</span><br>
        <b>Host / IP:</b> <code>{dev_host}</code> {f"(LAN: <code>{dev_lan}</code>)" if dev_lan else ""}<br>
        <b>Sistema:</b> <code>{active_dev_info.get('os_type', 'android')}</code> ({active_dev_info.get('player', 'vlc')})
    </div>
    """, unsafe_allow_html=True)

    # Auto-detección inteligente
    with st.expander("🔍 Auto-detectar Smart TVs"):
        if st.button("Buscar TVs en red y ADB", use_container_width=True):
            with st.spinner("Escaneando red local y Tailscale..."):
                found = discover_android_tvs()
                st.session_state.discovered_devices = found

        if st.session_state.discovered_devices:
            st.write(f"**Detectados ({len(st.session_state.discovered_devices)}):**")
            for d_name, d_val in st.session_state.discovered_devices.items():
                col_d1, col_d2 = st.columns([3, 1])
                col_d1.caption(f"📺 {d_name}")
                if col_d2.button("Añadir", key=f"add_disc_{d_name}"):
                    clean_name = d_name.split("(")[0].strip()
                    cfg["devices"][clean_name] = d_val
                    cfg["active_device"] = clean_name
                    save_config(cfg)
                    st.success(f"Añadido {clean_name}")
                    st.rerun()

    # Configurar / Añadir dispositivo manual
    with st.expander("⚙️ Configurar / Nuevo Dispositivo"):
        with st.form("device_form"):
            dev_name = st.text_input("Nombre (ej. Salón, Dormitorio)", value=selected_device_name)
            dev_host_in = st.text_input("IP Tailscale o Hostname", value=dev_host)
            dev_lan_in = st.text_input("IP LAN Local (Opcional, ej. 192.168.1.208)", value=dev_lan)
            dev_os_in = st.selectbox(
                "Sistema",
                ["android", "linux", "mac"],
                index=["android", "linux", "mac"].index(active_dev_info.get("os_type", "android"))
            )
            dev_player_in = st.selectbox(
                "Reproductor",
                ["vlc", "mpv"],
                index=0 if active_dev_info.get("player") == "vlc" else 1
            )

            if st.form_submit_button("Guardar Dispositivo"):
                cfg["devices"][dev_name] = {
                    "host": dev_host_in.strip(),
                    "lan_ip": dev_lan_in.strip(),
                    "user": active_dev_info.get("user", ""),
                    "os_type": dev_os_in,
                    "player": dev_player_in,
                    "display": active_dev_info.get("display", "")
                }
                cfg["active_device"] = dev_name
                save_config(cfg)
                st.success("Guardado correctamente")
                st.rerun()

    # Carpetas escaneadas
    with st.expander("📁 Carpetas de Video"):
        dirs = cfg.get("video_directories", [])
        for idx, folder in enumerate(dirs):
            col_f, col_del = st.columns([4, 1])
            col_f.caption(f"📂 `{Path(folder).name}` ({folder})")
            if col_del.button("🗑️", key=f"del_dir_{idx}"):
                cfg["video_directories"].pop(idx)
                save_config(cfg)
                st.rerun()

        new_dir = st.text_input("Añadir ruta absoluta:")
        if st.button("➕ Añadir Carpeta") and new_dir:
            expanded = str(Path(new_dir.strip()).expanduser().resolve())
            if expanded not in cfg["video_directories"]:
                cfg["video_directories"].append(expanded)
                save_config(cfg)
                st.rerun()

    if st.button("🔄 Refrescar Lista", use_container_width=True):
        st.rerun()

    st.divider()
    if st.button("🔌 Apagar TV Streamer", type="secondary", use_container_width=True):
        ctrl.stop_stream()
        st.warning("Servidor apagado. Puedes cerrar esta pestaña.")
        import signal, subprocess
        subprocess.run(["pkill", "-f", "video_server.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.kill(os.getpid(), signal.SIGTERM)

# ==========================================
# ÁREA PRINCIPAL
# ==========================================
st.title("🎬 TV Streamer")

# Notificaciones
if st.session_state.last_message:
    msg_type, msg_text = st.session_state.last_message
    if msg_type == "success":
        st.success(msg_text)
    elif msg_type == "error":
        st.error(msg_text)
    elif msg_type == "info":
        st.info(msg_text)
    st.session_state.last_message = None

# ==========================================
# 1. VIRTUAL REMOTE CONTROL (MANDO A DISTANCIA)
# ==========================================
if ctrl.current_video:
    st.markdown(f"""
    <div class="remote-card">
        <div class="remote-title">
            <span>🎮 Mando a Distancia Xiaomi TV</span>
            <span style="font-size: 12px; background: #22c55e; color: #022c22; padding: 2px 8px; border-radius: 12px; font-weight: 700;">TRANSMITIENDO EN VIVO</span>
        </div>
        <div style="font-size: 14px; color: #cbd5e1; margin-bottom: 12px;">
            <b>Video:</b> <code>{clean_title(Path(ctrl.current_video).name)}</code><br>
            <span style="font-size: 12px; color: #94a3b8;">Stream: <code>{ctrl.current_url}</code></span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Botones del Mando
    r_col1, r_col2, r_col3, r_col4, r_col5, r_col6, r_col7 = st.columns(7)
    with r_col1:
        if st.button("⏪ -10s", key="btn_rew", use_container_width=True, help="Retroceder 10 segundos"):
            ctrl.send_remote_key("rewind", active_dev_info)
    with r_col2:
        if st.button("⏯️ Play/Pausa", key="btn_pp", use_container_width=True, type="primary", help="Alternar Reproducir / Pausa"):
            ctrl.send_remote_key("play_pause", active_dev_info)
    with r_col3:
        if st.button("⏩ +10s", key="btn_ff", use_container_width=True, help="Avanzar 10 segundos"):
            ctrl.send_remote_key("fast_forward", active_dev_info)
    with r_col4:
        if st.button("🔉 Vol -", key="btn_voldown", use_container_width=True, help="Bajar volumen"):
            ctrl.send_remote_key("vol_down", active_dev_info)
    with r_col5:
        if st.button("🔊 Vol +", key="btn_volup", use_container_width=True, help="Subir volumen"):
            ctrl.send_remote_key("vol_up", active_dev_info)
    with r_col6:
        if st.button("🔇 Silencio", key="btn_mute", use_container_width=True, help="Silenciar / Activar sonido"):
            ctrl.send_remote_key("mute", active_dev_info)
    with r_col7:
        if st.button("⏹️ Detener", key="btn_stop", use_container_width=True, help="Detener transmisión y cerrar VLC"):
            ctrl.stop_stream(active_dev_info)
            st.session_state.last_message = ("info", "Transmisión finalizada.")
            st.rerun()

    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

# ==========================================
# 2. VISTOS RECIENTEMENTE (HISTORIAL)
# ==========================================
history_items = get_history()
if history_items:
    with st.expander("⏱️ Vistos Recientemente / Continuar viendo", expanded=(not ctrl.current_video)):
        col_h_header, col_h_clear = st.columns([5, 1])
        col_h_header.caption("Últimos videos reproducidos:")
        if col_h_clear.button("🗑️ Limpiar Historial"):
            clear_history()
            st.rerun()

        for h_idx, h_item in enumerate(history_items[:4]):
            h_cols = st.columns([5, 1, 1])
            with h_cols[0]:
                st.markdown(f"**{h_item.get('title', h_item['name'])}**")
                st.caption(f"📦 {h_item.get('size', 'N/A')} • `{h_item.get('path')}`")
            with h_cols[1]:
                if Path(h_item.get("path", "")).exists():
                    st.caption("✅ Disponible")
                else:
                    st.caption("⚠️ No encontrado")
            with h_cols[2]:
                if st.button("▶️ Reanudar", key=f"resume_{h_idx}", use_container_width=True):
                    with st.spinner("Reanudando streaming..."):
                        ok, res = ctrl.start_stream(h_item["path"], active_dev_info, port=cfg.get("http_port", 8080))
                        if ok:
                            st.session_state.last_message = ("success", f"Reproduciendo: {h_item.get('title')}")
                        else:
                            st.session_state.last_message = ("error", res)
                        st.rerun()

# ==========================================
# 3. REPRODUCCIÓN DIRECTA / ARRASTRAR Y SOLTAR
# ==========================================
with st.expander("⚡ Transmitir Archivo Directo (Ruta o Arrastrar)", expanded=False):
    direct_path_input = st.text_input(
        "Pega aquí la ruta absoluta de cualquier video (ej. /Volumes/USB/Pelicula.mkv):",
        placeholder="/ruta/completa/al/video.mp4"
    )
    if st.button("🚀 Transmitir Este Archivo Ahora", type="primary"):
        if direct_path_input and Path(direct_path_input.strip()).exists():
            clean_p = str(Path(direct_path_input.strip()).resolve())
            with st.spinner("Conectando con la TV..."):
                ok, res = ctrl.start_stream(clean_p, active_dev_info, port=cfg.get("http_port", 8080))
                if ok:
                    st.session_state.last_message = ("success", f"¡Transmitiendo directamente: {Path(clean_p).name}!")
                else:
                    st.session_state.last_message = ("error", res)
                st.rerun()
        else:
            st.error("Ruta no válida o el archivo no existe en el equipo.")

# ==========================================
# 4. BARRA DE BÚSQUEDA, FILTRO Y ORDENACIÓN
# ==========================================
c_search, c_fmt, c_size, c_sort = st.columns([3, 1, 1, 1.5])
with c_search:
    search_query = st.text_input("🔍 Buscar video...", placeholder="Filtrar por título o nombre...")
with c_fmt:
    format_filter = st.selectbox("Formato", ["Todos", "MP4", "MKV", "MOV", "AVI", "WEBM"])
with c_size:
    size_filter = st.selectbox("Tamaño", ["Todos", "< 500 MB", "≥ 500 MB (Películas)"])
with c_sort:
    sort_order = st.selectbox("Ordenar por", ["🕒 Más reciente", "🔤 Nombre (A-Z)", "📦 Mayor tamaño", "📦 Menor tamaño"])

# Escanear y filtrar catálogo
all_videos = scan_videos(cfg.get("video_directories", []))

filtered = all_videos
if search_query:
    q = search_query.lower()
    filtered = [v for v in filtered if q in v["name"].lower() or q in v["title"].lower()]

if format_filter != "Todos":
    filtered = [v for v in filtered if v["ext"] == format_filter]

if size_filter == "< 500 MB":
    filtered = [v for v in filtered if v["size_bytes"] < 500 * 1024 * 1024]
elif size_filter == "≥ 500 MB (Películas)":
    filtered = [v for v in filtered if v["size_bytes"] >= 500 * 1024 * 1024]

# Ordenar
if sort_order == "🕒 Más reciente":
    filtered.sort(key=lambda x: x["mtime"], reverse=True)
elif sort_order == "🔤 Nombre (A-Z)":
    filtered.sort(key=lambda x: x["title"].lower())
elif sort_order == "📦 Mayor tamaño":
    filtered.sort(key=lambda x: x["size_bytes"], reverse=True)
elif sort_order == "📦 Menor tamaño":
    filtered.sort(key=lambda x: x["size_bytes"])

st.caption(f"Mostrando **{len(filtered)}** de **{len(all_videos)}** videos encontrados.")

# ==========================================
# 5. CATÁLOGO EN CUADRÍCULA
# ==========================================
if not filtered:
    st.info("No se encontraron videos con los filtros actuales.")
else:
    cols_per_row = 2
    for i in range(0, len(filtered), cols_per_row):
        row_cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            idx = i + j
            if idx >= len(filtered):
                break
            video = filtered[idx]
            vpath = Path(video["path"])
            is_current = (ctrl.current_video == video["path"])

            with row_cols[j]:
                # Thumbnail
                thumb = get_thumbnail(vpath)
                if thumb and os.path.exists(thumb):
                    st.image(thumb, use_container_width=True)
                else:
                    st.markdown("""
                    <div style="background-color: #21212e; height: 160px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 40px; margin-bottom: 8px;">
                        🎥
                    </div>
                    """, unsafe_allow_html=True)

                # Badges
                st.markdown(f"""
                <div class="clean-title" title="{video['name']}">{video['title']}</div>
                <div class="raw-filename">{video['name']}</div>
                <div class="badge-container">
                    <span class="badge badge-ext">{video['ext']}</span>
                    <span class="badge badge-size">{video['size']}</span>
                    <span class="badge badge-folder">📂 {Path(video['folder']).name}</span>
                </div>
                """, unsafe_allow_html=True)

                # Acciones
                if is_current:
                    if st.button("⏹️ Detener Transmisión", key=f"stop_{idx}", type="secondary", use_container_width=True):
                        ctrl.stop_stream(active_dev_info)
                        st.session_state.last_message = ("info", f"Detenido: {video['title']}")
                        st.rerun()
                else:
                    if st.button(f"▶️ Reproducir en {selected_device_name}", key=f"play_{idx}", type="primary", use_container_width=True):
                        with st.spinner(f"Lanzando a {selected_device_name}..."):
                            ok, result = ctrl.start_stream(
                                video["path"],
                                active_dev_info,
                                port=cfg.get("http_port", 8080)
                            )
                            if ok:
                                st.session_state.last_message = ("success", f"¡Transmitiendo {video['title']} en tu TV!")
                            else:
                                st.session_state.last_message = ("error", result)
                            st.rerun()
