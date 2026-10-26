import streamlit as st
import os
from pathlib import Path
from stream_manager import (
    load_config, save_config, get_tailscale_ip, get_tailscale_peers,
    scan_videos, get_thumbnail, StreamController
)

st.set_page_config(
    page_title="TV Streamer",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .media-card {
        background-color: #1e1e24;
        border-radius: 12px;
        padding: 12px;
        border: 1px solid #33333f;
        margin-bottom: 15px;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .media-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 16px rgba(0,0,0,0.4);
        border-color: #6366f1;
    }
    .video-title {
        font-weight: 600;
        font-size: 15px;
        margin-top: 8px;
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        color: #f1f5f9;
    }
    .video-meta {
        font-size: 12px;
        color: #94a3b8;
        margin-bottom: 8px;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
    }
    .status-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Config & State
cfg = load_config()
st.session_state.config = cfg

if "stream_ctrl" not in st.session_state:
    st.session_state.stream_ctrl = StreamController.get_instance()

if "last_message" not in st.session_state:
    st.session_state.last_message = None

cfg = st.session_state.config
ctrl = st.session_state.stream_ctrl
ts_ip = get_tailscale_ip()
ts_peers = get_tailscale_peers()

# ==========================================
# SIDEBAR: DISPOSITIVOS Y CONFIGURACIÓN
# ==========================================
with st.sidebar:
    st.title("📺 TV Streamer")
    st.caption("Streaming vía Tailscale + SSH")

    # Status pill
    st.markdown(f"""
    <div style="background-color: #132f22; border: 1px solid #22c55e; border-radius: 8px; padding: 8px 12px; margin-bottom: 15px;">
        <span style="color: #4ade80; font-weight: bold;">● Tailscale Activo</span><br>
        <span style="font-size: 13px; color: #d1fae5;">Este Mac: <code>{ts_ip}</code></span>
    </div>
    """, unsafe_allow_html=True)

    # Active stream indicator
    if ctrl.current_video:
        st.warning(f"🔴 **Transmitiendo ahora:**\n\n`{Path(ctrl.current_video).name}`")
        if ctrl.current_url:
            st.code(ctrl.current_url, language=None)
            st.caption("💡 Puedes abrir este enlace en VLC de cualquier TV o móvil.")
        if st.button("⏹️ Detener Reproducción", type="primary", use_container_width=True):
            ctrl.stop_stream()
            st.session_state.last_message = ("info", "Reproducción detenida.")
            st.rerun()
        st.divider()

    # Dispositivos detectados en Tailscale
    st.subheader("🎯 Dispositivo Destino")
    
    # Combinar dispositivos de config con peers reales
    devices = cfg.get("devices", {})
    device_names = list(devices.keys())
    
    selected_device_name = st.selectbox(
        "Seleccionar destino:",
        options=device_names,
        index=device_names.index(cfg.get("active_device")) if cfg.get("active_device") in device_names else 0
    )
    if selected_device_name != cfg.get("active_device"):
        cfg["active_device"] = selected_device_name
        save_config(cfg)

    active_dev_info = devices.get(selected_device_name, {})
    dev_host = active_dev_info.get("host", "")
    
    # Comprobar si el host está online en Tailscale
    is_online = False
    for p_name, p_data in ts_peers.items():
        if p_data.get("ip") == dev_host or p_name.lower() in selected_device_name.lower():
            is_online = p_data.get("online", False)
            break

    status_color = "#22c55e" if is_online else "#ef4444"
    status_text = "🟢 En línea" if is_online else "🔴 Fuera de línea / Standby"
    
    st.markdown(f"""
    <div style="font-size: 13px; margin-bottom: 10px;">
        <b>Estado:</b> <span style="color: {status_color}; font-weight: bold;">{status_text}</span><br>
        <b>IP / Host:</b> <code>{dev_host}</code><br>
        <b>Sistema:</b> <code>{active_dev_info.get('os_type', 'linux')}</code>
    </div>
    """, unsafe_allow_html=True)

    if not is_online and active_dev_info.get("os_type") == "android":
        st.info("ℹ️ Tu TV Android parece estar en reposo o apagada. Enciéndela o abre la app Tailscale en ella.")

    # Administrar dispositivos
    with st.expander("⚙️ Editar / Configurar Dispositivo"):
        with st.form("device_form"):
            dev_name = st.text_input("Nombre de la TV / Dispositivo", value=selected_device_name)
            dev_host_in = st.text_input("IP de Tailscale o Hostname", value=dev_host)
            dev_user_in = st.text_input("Usuario SSH (ej. pi, gtrujillo)", value=active_dev_info.get("user", "pi"))
            dev_os_in = st.selectbox(
                "Tipo de Sistema",
                ["linux", "android", "mac"],
                index=["linux", "android", "mac"].index(active_dev_info.get("os_type", "linux"))
            )
            dev_player_in = st.selectbox(
                "Reproductor",
                ["vlc", "mpv"],
                index=0 if active_dev_info.get("player") == "vlc" else 1
            )
            dev_display_in = st.text_input("Pantalla DISPLAY (Linux)", value=active_dev_info.get("display", ":0"))

            if st.form_submit_button("Guardar Cambios"):
                cfg["devices"][dev_name] = {
                    "host": dev_host_in.strip(),
                    "user": dev_user_in.strip(),
                    "os_type": dev_os_in,
                    "player": dev_player_in,
                    "display": dev_display_in.strip()
                }
                cfg["active_device"] = dev_name
                save_config(cfg)
                st.success(f"Dispositivo '{dev_name}' actualizado.")
                st.rerun()

    # Carpetas a escanear
    with st.expander("📁 Carpetas de Videos"):
        for idx, folder in enumerate(cfg.get("video_directories", [])):
            col_f, col_del = st.columns([4, 1])
            col_f.code(folder, language=None)
            if col_del.button("🗑️", key=f"del_dir_{idx}"):
                cfg["video_directories"].pop(idx)
                save_config(cfg)
                st.rerun()

        new_dir = st.text_input("Añadir carpeta (ej. ~/Movies)")
        if st.button("➕ Añadir") and new_dir:
            expanded = str(Path(new_dir.strip()).expanduser())
            if expanded not in cfg["video_directories"]:
                cfg["video_directories"].append(expanded)
                save_config(cfg)
                st.rerun()

    if st.button("🔄 Refrescar", use_container_width=True):
        st.rerun()

    st.divider()
    if st.button("🔌 Apagar TV Streamer", help="Detiene el streaming y apaga el servidor", use_container_width=True):
        ctrl.stop_stream()
        st.warning("Servidor apagado. Puedes cerrar esta pestaña.")
        import os, signal, subprocess
        subprocess.run(["pkill", "-f", "video_server.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.kill(os.getpid(), signal.SIGTERM)

# ==========================================
# ÁREA PRINCIPAL: CATÁLOGO DE VIDEOS
# ==========================================
st.title("🎬 Catálogo de Videos")

if st.session_state.last_message:
    msg_type, msg_text = st.session_state.last_message
    if msg_type == "success":
        st.success(msg_text)
    elif msg_type == "error":
        st.error(msg_text)
    elif msg_type == "info":
        st.info(msg_text)
    st.session_state.last_message = None

# Mensaje activo si hay streaming en curso
if ctrl.current_video:
    st.success(f"🟢 **En reproducción en tu Xiaomi TV:** `{Path(ctrl.current_video).name}`")

# Búsqueda y filtros
col_search, col_filter = st.columns([3, 1])
with col_search:
    search_query = st.text_input("🔍 Buscar película o video...", placeholder="Filtrar por nombre...")
with col_filter:
    format_filter = st.selectbox("Formato", ["Todos", "mp4", "mkv", "mov", "avi"])

all_videos = scan_videos(cfg.get("video_directories", []))

filtered_videos = all_videos
if search_query:
    filtered_videos = [v for v in filtered_videos if search_query.lower() in v["name"].lower()]
if format_filter != "Todos":
    filtered_videos = [v for v in filtered_videos if v["name"].lower().endswith(f".{format_filter}")]

st.caption(f"Mostrando **{len(filtered_videos)}** videos encontrados.")

if not filtered_videos:
    st.info("No se encontraron videos en las carpetas seleccionadas.")
else:
    cols_per_row = 2
    for i in range(0, len(filtered_videos), cols_per_row):
        cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            idx = i + j
            if idx >= len(filtered_videos):
                break
            video = filtered_videos[idx]
            vpath = Path(video["path"])

            with cols[j]:
                thumb = get_thumbnail(vpath)
                if thumb and os.path.exists(thumb):
                    st.image(thumb, use_container_width=True)
                else:
                    st.markdown("""
                    <div style="background-color: #272730; height: 160px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 40px;">
                        🎥
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown(f"<div class='video-title' title='{video['name']}'>{video['name']}</div>", unsafe_allow_html=True)
                st.markdown(f"<div class='video-meta'>📦 {video['size']} • 📂 {Path(video['folder']).name}</div>", unsafe_allow_html=True)

                is_current = (ctrl.current_video == video["path"])

                if is_current:
                    if st.button("⏹️ Detener Transmisión", key=f"stop_{idx}", type="secondary", use_container_width=True):
                        ctrl.stop_stream(active_dev_info)
                        st.session_state.last_message = ("info", f"Detenido: {video['name']}")
                        st.rerun()
                else:
                    if st.button(f"▶️ Reproducir en {selected_device_name}", key=f"play_{idx}", type="primary", use_container_width=True):
                        with st.spinner(f"Iniciando streaming hacia {selected_device_name}..."):
                            ok, result = ctrl.start_stream(
                                video["path"],
                                active_dev_info,
                                port=cfg.get("http_port", 8080)
                            )
                            if ok:
                                st.session_state.last_message = ("success", f"¡Streaming activo! Reproduciendo en {selected_device_name}")
                            else:
                                st.session_state.last_message = ("error", result)
                            st.rerun()
