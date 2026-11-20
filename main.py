# -*- coding: utf-8 -*-
"""
Created on Fri Nov 20 12:43:36 2026

@author: Arh
"""

# -*- coding: utf-8 -*-
"""
Created on Fri Nov 20 09:21:54 2026

@author: Arh
"""


import flet as ft
import yt_dlp
import threading
import os
import flet_audio as fta
import flet_permission_handler as fph
import flet_notifications as ftn  # <-- AÑADIR ARRIBA (requiere: pip install flet-notifications)
import asyncio
import urllib.parse
import urllib.request
import ssl
import time

try:
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
except Exception:
    pass
ssl._create_default_https_context = ssl._create_unverified_context


try:
    import flet_video as ftv
except ImportError:
    ftv = None


from concurrent.futures import ThreadPoolExecutor

def main(page: ft.Page):
    page.title = "Descargador Paralelo"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    permisos = fph.PermissionHandler()

    ultima_caratula_cache = (None, None)
    titulo_stream_actual = None
    caratula_stream_actual = None
    tarea_notif_pendiente = None

    ultimo_clic_notif = 0.0

    async def manejar_accion_notificacion(e: ftn.NotificationActionEvent):
        nonlocal ultimo_clic_notif
        ahora = time.monotonic()
        if ahora - ultimo_clic_notif < 0.35:
            return
        ultimo_clic_notif = ahora

        if e.action_id == "prev":
            page.run_task(anterior_cancion, None)
        elif e.action_id == "play_pause":
            page.run_task(toggle_play_pause, None)
        elif e.action_id == "next":
            page.run_task(siguiente_cancion, None)


    notificaciones = ftn.Notifications(on_action=manejar_accion_notificacion)
    page.services.append(notificaciones) if hasattr(page, "services") else page.overlay.append(notificaciones)

    async def _enviar_notificacion_async(titulo, ruta_caratula, reproduciendo):
        nonlocal ultima_caratula_cache
        await asyncio.sleep(0.15)

        texto_boton = "   ❚❚   " if reproduciendo else "   ▶   "
        large_icon = None

        if ruta_caratula and os.path.isfile(ruta_caratula):
            if ultima_caratula_cache[0] == ruta_caratula:
                large_icon = ultima_caratula_cache[1]
            else:
                try:
                    loop = asyncio.get_running_loop()
                    data = await loop.run_in_executor(None, lambda: open(ruta_caratula, "rb").read())
                    large_icon = ftn.AndroidBytesBitmap(data=data)
                    ultima_caratula_cache = (ruta_caratula, large_icon)
                except Exception:
                    large_icon = None

        try:
            await asyncio.wait_for(
                notificaciones.show(
                    id=1001,
                    title=titulo,
                    body="Reproduciendo" if reproduciendo else "En pausa",
                    actions=[
                        ftn.NotificationAction(
                            id="prev",
                            title="   ◀◀   ",
                            cancel_notification=False,
                            foreground=False,
                            require_authentication=False,
                        ),
                        ftn.NotificationAction(
                            id="play_pause",
                            title=texto_boton,
                            cancel_notification=False,
                            foreground=False,
                            require_authentication=False,
                        ),
                        ftn.NotificationAction(
                            id="next",
                            title="   ▶▶   ",
                            cancel_notification=False,
                            foreground=False,
                            require_authentication=False,
                        ),
                    ],
                    options=ftn.NotificationOptions(
                        android=ftn.AndroidOptions(
                            ongoing=reproduciendo,
                            silent=True,
                            only_alert_once=True,
                            large_icon=large_icon,
                            category=ftn.AndroidCategory.TRANSPORT,
                            visibility=ftn.AndroidVisibility.PUBLIC,
                        )
                    ),
                ),
                timeout=1.5,
            )
        except Exception:
            pass


    async def actualizar_notificacion_bloqueo(titulo_custom=None, caratula_custom=None):
        nonlocal tarea_notif_pendiente, titulo_stream_actual, caratula_stream_actual
        if titulo_custom:
            titulo_stream_actual = titulo_custom
            caratula_stream_actual = caratula_custom

        if 0 <= indice_actual < len(canciones_locales):
            nombre_archivo = canciones_locales[indice_actual]
            titulo = os.path.splitext(nombre_archivo)[0]
            ruta_caratula = obtener_caratula(nombre_archivo)
        elif titulo_stream_actual:
            titulo = titulo_stream_actual
            ruta_caratula = caratula_stream_actual
        else:
            return

        if tarea_notif_pendiente and not tarea_notif_pendiente.done():
            tarea_notif_pendiente.cancel()

        tarea_notif_pendiente = page.run_task(
            _enviar_notificacion_async, titulo, ruta_caratula, esta_reproduciendo
        )

    
   


    
    
    
    
    page.services.append(permisos) if hasattr(page, "services") else page.overlay.append(permisos)

    raiz_storage = "/storage/emulated/0" if os.path.exists("/storage/emulated/0") else os.path.abspath(".")
    ruta_actual = os.path.join(raiz_storage, "Download") if os.path.exists("/storage/emulated/0") else os.path.join(raiz_storage, "descargas")
    os.makedirs(ruta_actual, exist_ok=True)

    lbl_ruta_actual = ft.Text(ruta_actual, size=12, color=ft.Colors.GREY_400, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)

    def establecer_carpeta(nueva_ruta):
        nonlocal ruta_actual
        if os.path.isdir(nueva_ruta):
            ruta_actual = nueva_ruta
            lbl_ruta_actual.value = ruta_actual
            escanear_canciones()
            status_text.value = f"Carpeta: {os.path.basename(ruta_actual)}"
        else:
            status_text.value = "No se pudo acceder a la carpeta."
        page.update()

    async def abrir_selector_carpeta(e=None):
        try:
            await permisos.request(fph.Permission.MANAGE_EXTERNAL_STORAGE)
            await permisos.request(fph.Permission.AUDIO)
            await permisos.request(fph.Permission.STORAGE)
        except Exception:
            pass
        ruta_elegida = await file_picker.get_directory_path(dialog_title="Selecciona carpeta de música")
        if ruta_elegida:
            establecer_carpeta(ruta_elegida)


    file_picker = ft.FilePicker()
    page.services.append(file_picker) if hasattr(page, "services") else page.overlay.append(file_picker)



    canciones_locales = []
    indice_actual = -1
    esta_reproduciendo = False
    arrastrando_slider = False

    lbl_cancion_actual = ft.Text("Ninguna canción", weight=ft.FontWeight.BOLD, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    lbl_tiempo = ft.Text("00:00 / 00:00", size=12)
    slider_progreso = ft.Slider(min=0, max=100, value=0, expand=True)
    btn_play_pause = ft.IconButton(icon=ft.Icons.PLAY_ARROW, icon_size=32)
    lista_canciones_ui = ft.ListView(expand=True, spacing=4)

    def formatear_tiempo(ms):
        if not ms or ms < 0:
            return "00:00"
        s = int(ms // 1000)
        return f"{s // 60:02d}:{s % 60:02d}"

    async def on_position_changed(e: fta.AudioPositionChangeEvent):
        pos_ms = e.position.in_milliseconds if hasattr(e.position, "in_milliseconds") else int(e.position or 0)
        if not arrastrando_slider and slider_progreso.max > 0:
            slider_progreso.value = min(pos_ms, slider_progreso.max)
            lbl_tiempo.value = f"{formatear_tiempo(pos_ms)} / {formatear_tiempo(slider_progreso.max)}"
            page.update()
    
    async def on_duration_changed(e: fta.AudioDurationChangeEvent):
        dur_ms = e.duration.in_milliseconds if hasattr(e.duration, "in_milliseconds") else int(e.duration or 0)
        if dur_ms > 0:
            slider_progreso.max = dur_ms
            lbl_tiempo.value = f"{formatear_tiempo(slider_progreso.value)} / {formatear_tiempo(dur_ms)}"
            page.update()        

    cambiando_pista = False
    ignorar_estados_hasta = 0.0

    async def on_state_changed(e: fta.AudioStateChangeEvent):
        nonlocal esta_reproduciendo
        ahora = time.monotonic()
        if e.state == fta.AudioState.COMPLETED:
            if cambiando_pista or ahora < ignorar_estados_hasta:
                return
            await siguiente_cancion(None)
        elif e.state == fta.AudioState.PLAYING:
            esta_reproduciendo = True
            btn_play_pause.icon = ft.Icons.PAUSE
            page.update()
            page.run_task(actualizar_notificacion_bloqueo)
        elif e.state in (fta.AudioState.PAUSED, fta.AudioState.STOPPED):
            if cambiando_pista or ahora < ignorar_estados_hasta:
                return
            esta_reproduciendo = False
            btn_play_pause.icon = ft.Icons.PLAY_ARROW
            page.update()
            page.run_task(actualizar_notificacion_bloqueo)


    
    audio_player = fta.Audio(
        autoplay=False,
        release_mode=fta.ReleaseMode.STOP,
        context=fta.AudioContext(
            focus=fta.AudioFocus.GAIN,
            respect_silence=False,
        ),
        on_position_change=on_position_changed,
        on_duration_change=on_duration_changed,
        on_state_change=on_state_changed,
    )

    page.services.append(audio_player) if hasattr(page, "services") else page.overlay.append(audio_player)

    videos_yt_actuales = []
    indice_video_yt = -1
    reproduccion_lock = asyncio.Lock()
    token_reproduccion = 0

    async def reproducir_indice(idx):
        nonlocal indice_actual, cambiando_pista, ignorar_estados_hasta, titulo_stream_actual, token_reproduccion, esta_reproduciendo
        if not canciones_locales or idx < 0 or idx >= len(canciones_locales):
            return

        token_reproduccion += 1
        mi_token = token_reproduccion
        anterior_idx = indice_actual
        indice_actual = idx
        titulo_stream_actual = None

        nombre = canciones_locales[indice_actual]
        lbl_cancion_actual.value = os.path.splitext(nombre)[0]
        slider_progreso.value = 0
        slider_progreso.max = 100

        for pos in (anterior_idx, indice_actual):
            if 0 <= pos < len(lista_canciones_ui.controls):
                tile = lista_canciones_ui.controls[pos]
                if isinstance(tile.title, ft.Text):
                    tile.title.weight = ft.FontWeight.BOLD if pos == indice_actual else None
        page.update()

        async with reproduccion_lock:
            if mi_token != token_reproduccion:
                return
            if contenedor_video_mini.visible:
                await cerrar_reproductor_video()

            cambiando_pista = True
            ignorar_estados_hasta = time.monotonic() + 1.0
            try:
                try:
                    await audio_player.pause()
                except Exception:
                    pass
                audio_player.src = os.path.join(ruta_actual, nombre)
                page.update()
                await asyncio.sleep(0.08)
                if mi_token != token_reproduccion:
                    return
                await audio_player.play()
                esta_reproduciendo = True
                btn_play_pause.icon = ft.Icons.PAUSE
                page.update()
                await actualizar_notificacion_bloqueo()
            finally:
                await asyncio.sleep(0.35)
                if mi_token == token_reproduccion:
                    cambiando_pista = False
                    ignorar_estados_hasta = time.monotonic() + 0.4



    async def toggle_play_pause(e):
        nonlocal esta_reproduciendo
        if video_player and contenedor_video_mini.visible:
            if esta_reproduciendo:
                await video_player.pause()
                esta_reproduciendo = False
            else:
                await video_player.play()
                esta_reproduciendo = True
            btn_play_pause.icon = ft.Icons.PAUSE if esta_reproduciendo else ft.Icons.PLAY_ARROW
            try:
                page.update()
            except Exception:
                pass
            await actualizar_notificacion_bloqueo()
            return

        if indice_actual < 0 or indice_actual >= len(canciones_locales):
            if canciones_locales:
                await reproducir_indice(0)
            return

        if esta_reproduciendo:
            await audio_player.pause()
        else:
            await audio_player.play()

    async def siguiente_cancion(e):
        nonlocal indice_video_yt
        if contenedor_video_mini.visible and videos_yt_actuales:
            siguiente_idx = (indice_video_yt + 1) % len(videos_yt_actuales)
            indice_video_yt = siguiente_idx
            v_url, titulo = videos_yt_actuales[indice_video_yt]
            await reproducir_video_youtube(v_url, titulo, idx_lista=indice_video_yt)
            return

        if canciones_locales:
            base = indice_actual if 0 <= indice_actual < len(canciones_locales) else -1
            await reproducir_indice((base + 1) % len(canciones_locales))

    async def anterior_cancion(e):
        nonlocal indice_video_yt
        if contenedor_video_mini.visible and videos_yt_actuales:
            anterior_idx = (indice_video_yt - 1) % len(videos_yt_actuales)
            indice_video_yt = anterior_idx
            v_url, titulo = videos_yt_actuales[indice_video_yt]
            await reproducir_video_youtube(v_url, titulo, idx_lista=indice_video_yt)
            return

        if canciones_locales:
            base = indice_actual if 0 <= indice_actual < len(canciones_locales) else 0
            await reproducir_indice((base - 1) % len(canciones_locales))



    def on_slider_start(e):
        nonlocal arrastrando_slider
        arrastrando_slider = True

 
    
    async def on_slider_end(e):
        nonlocal arrastrando_slider
        arrastrando_slider = False
        await audio_player.seek(ft.Duration(milliseconds=int(e.control.value)))
    

    btn_play_pause.on_click = lambda e: page.run_task(toggle_play_pause, e)
    slider_progreso.on_change_start = on_slider_start
    # slider_progreso.on_change_end = on_slider_end
    slider_progreso.on_change_end = lambda e: page.run_task(on_slider_end, e)

    caratulas_buscadas = set()
    descargando_caratulas = False



    def obtener_caratula(nombre_archivo):
        base = os.path.splitext(nombre_archivo)[0]
        carpeta_caratulas = os.path.join(ruta_actual, ".caratulas")

        for carpeta in (carpeta_caratulas, ruta_actual):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                ruta_img = os.path.join(carpeta, base + ext)
                if os.path.isfile(ruta_img):
                    return ruta_img
        return None

    def extraer_caratula_embebida(nombre_archivo):
        base = os.path.splitext(nombre_archivo)[0]
        carpeta_caratulas = os.path.join(ruta_actual, ".caratulas")
        try:
            import mutagen
            ruta_audio = os.path.join(ruta_actual, nombre_archivo)
            audio = mutagen.File(ruta_audio)
            datos_img = None
            if audio and getattr(audio, "tags", None):
                for tag in audio.tags.values():
                    if hasattr(tag, "data"):
                        datos_img = tag.data
                        break
                if not datos_img and "covr" in audio.tags:
                    datos_img = bytes(audio.tags["covr"])
            if datos_img:
                os.makedirs(carpeta_caratulas, exist_ok=True)
                ruta_guardada = os.path.join(carpeta_caratulas, base + ".jpg")
                with open(ruta_guardada, "wb") as f:
                    f.write(datos_img)
                return ruta_guardada
        except Exception:
            pass
        return None


    def descargar_caratulas_faltantes():
        nonlocal descargando_caratulas
        if descargando_caratulas:
            return
        descargando_caratulas = True

        def _iniciar_ui():
            btn_caratulas.disabled = True
            status_text.value = "Buscando carátulas..."
        ui_sync(_iniciar_ui)

        try:
            carpeta_actual_snap = ruta_actual
            carpeta_caratulas = os.path.join(carpeta_actual_snap, ".caratulas")
            copia_canciones = list(canciones_locales)
            hubo_cambios = False

            for archivo in copia_canciones:
                if ruta_actual != carpeta_actual_snap:
                    return
                if obtener_caratula(archivo) is None:
                    if extraer_caratula_embebida(archivo):
                        hubo_cambios = True

            if hubo_cambios and ruta_actual == carpeta_actual_snap:
                ui_sync(actualizar_lista_ui)
                hubo_cambios = False

            pendientes = [
                f for f in copia_canciones
                if (carpeta_actual_snap, f) not in caratulas_buscadas and obtener_caratula(f) is None
            ]
            if not pendientes:
                ui_sync(lambda: setattr(status_text, "value", "Carátulas al día"))
                return

            opts = {
                "extract_flat": "in_playlist",
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "nocheckcertificate": True,
                "socket_timeout": 10,
            }
            yt_img_base = "https://i.ytimg.com/vi/"
            encontradas = 0
            total_pendientes = len(pendientes)

            with yt_dlp.YoutubeDL(opts) as ydl:
                for idx_p, archivo in enumerate(pendientes):
                    if ruta_actual != carpeta_actual_snap:
                        return
                    caratulas_buscadas.add((carpeta_actual_snap, archivo))
                    base_nombre, _ = os.path.splitext(archivo)
                    ui_sync(lambda i=idx_p: setattr(status_text, "value", f"Carátula {i + 1}/{total_pendientes}..."))

                    try:
                        info = ydl.extract_info(f"ytsearch1:{base_nombre}", download=False)
                        entries = [e for e in (info.get("entries") or []) if e] if info else []
                        if not entries:
                            continue
                        primer_res = entries[0]
                        vid_id = primer_res.get("id")

                        thumb_url = primer_res.get("thumbnail") or (
                            f"{yt_img_base}{vid_id}/hqdefault.jpg" if vid_id else None
                        )
                        if not thumb_url:
                            continue

                        ruta_audio = os.path.join(carpeta_actual_snap, archivo)
                        incrustar_caratula_en_audio(ruta_audio, thumb_url, carpeta_caratulas, base_nombre)
                        if obtener_caratula(archivo):
                            encontradas += 1
                            hubo_cambios = True
                            if encontradas % 10 == 0 and ruta_actual == carpeta_actual_snap:
                                ui_sync(actualizar_lista_ui)
                                hubo_cambios = False
                    except Exception:
                        continue

            if hubo_cambios and ruta_actual == carpeta_actual_snap:
                ui_sync(actualizar_lista_ui)
            ui_sync(lambda: setattr(status_text, "value", f"Carátulas encontradas: {encontradas}"))
        finally:
            descargando_caratulas = False
            def _fin_ui():
                btn_caratulas.disabled = False
            ui_sync(_fin_ui)



    def iniciar_descarga_caratulas(e=None):
        claves_carpeta = [k for k in caratulas_buscadas if k[0] == ruta_actual]
        for k in claves_carpeta:
            caratulas_buscadas.discard(k)
        page.run_thread(descargar_caratulas_faltantes)


    def escanear_canciones(e=None):
        nonlocal canciones_locales, indice_actual
        exts = (".m4a", ".mp3", ".webm", ".opus", ".ogg", ".wav", ".flac", ".aac")
        try:
            archivos = [
                f for f in os.listdir(ruta_actual)
                if os.path.isfile(os.path.join(ruta_actual, f)) and f.lower().endswith(exts)
            ]
            archivos.sort(key=lambda x: os.path.getmtime(os.path.join(ruta_actual, x)), reverse=True)
            canciones_locales = archivos
        except Exception as err:
            canciones_locales = []
            lista_canciones_ui.controls.clear()
            lista_canciones_ui.controls.append(
                ft.Text(f"Sin permiso para leer carpeta. Pulsa 'Elegir carpeta' o activa Audio en Ajustes. ({err})", color=ft.Colors.RED_300, size=12)
            )
            page.update()
            return

        
        if indice_actual >= len(canciones_locales):
            indice_actual = -1
        actualizar_lista_ui()



    
    def actualizar_lista_ui():
        lista_canciones_ui.controls.clear()
        for i, archivo in enumerate(canciones_locales):
            es_actual = (i == indice_actual)
            ruta_caratula = obtener_caratula(archivo)

            if ruta_caratula:
                img = ft.Image(
                    src=ruta_caratula,
                    width=42,
                    height=42,
                    fit=ft.BoxFit.COVER,
                )
                miniatura = ft.Container(
                    width=42,
                    height=42,
                    border_radius=6,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    content=ft.Stack(
                        [
                            img,
                            ft.Container(
                                bgcolor=ft.Colors.BLACK_54,
                                alignment=ft.Alignment.CENTER,
                                content=ft.Icon(ft.Icons.GRAPHIC_EQ, size=20, color=ft.Colors.WHITE),
                            ),
                        ]
                    ) if es_actual else img,
                )
            else:
                miniatura = ft.Container(
                    width=42,
                    height=42,
                    border_radius=6,
                    bgcolor=ft.Colors.GREY_800,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(
                        ft.Icons.GRAPHIC_EQ if es_actual else ft.Icons.MUSIC_NOTE,
                        size=20,
                    ),
                )

            lista_canciones_ui.controls.append(
                ft.ListTile(
                    dense=True,
                    content_padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                    leading=miniatura,
                    title=ft.Text(
                        os.path.splitext(archivo)[0],
                        size=12,
                        weight=ft.FontWeight.BOLD if es_actual else None,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    on_click=lambda e, idx=i: page.run_task(reproducir_indice, idx),
                )
            )
        page.update()

    
           
    url_input = ft.TextField(
        label="Enlace de la lista de reproducción",
        hint_text="https://youtube.com...",
        expand=True
    )

    status_text = ft.Text("Listo para descargar", size=14)
    progress_bar = ft.ProgressBar(width=400, value=0, visible=False)
    log_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

    
    ui_lock = threading.Lock()
    descarga_en_curso = False

    async def _ejecutar_en_ui(fn):
        try:
            fn()
            page.update()
        except Exception:
            pass

    def ui_sync(fn):
        try:
            page.run_task(_ejecutar_en_ui, fn)
        except Exception:
            pass

    def log(mensaje):
        def _agregar():
            log_column.controls.append(ft.Text(mensaje, size=12, selectable=True))
            if len(log_column.controls) > 150:
                log_column.controls = log_column.controls[-150:]
        ui_sync(_agregar)

    def incrustar_caratula_en_audio(ruta_audio, thumb_url, carpeta_caratulas, base_nombre):
        os.makedirs(carpeta_caratulas, exist_ok=True)
        datos_img = None
        posible = ""

        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            ruta_test = os.path.join(carpeta_caratulas, base_nombre + ext)
            if os.path.isfile(ruta_test):
                posible = ruta_test
                with open(ruta_test, "rb") as f:
                    datos_img = f.read()
                break

        if thumb_url and (not datos_img or posible.endswith(".webp")):
            try:
                jpg_url = thumb_url.replace("vi_webp/", "vi/").replace(".webp", ".jpg")
                req = urllib.request.Request(jpg_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    datos_img = resp.read()
                ruta_jpg = os.path.join(carpeta_caratulas, base_nombre + ".jpg")
                with open(ruta_jpg, "wb") as f:
                    f.write(datos_img)
            except Exception:
                pass

        if not datos_img:
            return

        try:
            from mutagen.mp4 import MP4, MP4Cover
            from mutagen.id3 import ID3, APIC

            if ruta_audio.lower().endswith((".m4a", ".mp4")):
                audio = MP4(ruta_audio)
                fmt = MP4Cover.FORMAT_PNG if datos_img[:8] == b"\x89PNG\r\n\x1a\n" else MP4Cover.FORMAT_JPEG
                audio["covr"] = [MP4Cover(datos_img, imageformat=fmt)]
                audio.save()
            elif ruta_audio.lower().endswith(".mp3"):
                tags = ID3(ruta_audio)
                tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=datos_img))
                tags.save()
        except Exception:
            pass

    def descargar_playlist(url, max_hilos):
        nonlocal descarga_en_curso
        if descarga_en_curso:
            log("⚠ Ya hay una descarga en curso. Espera a que termine.")
            return

        descarga_en_curso = True
        try:
            os.makedirs(ruta_actual, exist_ok=True)

            def _prep_ui():
                btn_descargar.disabled = True
                log_column.controls = []
                status_text.value = "Extrayendo canciones de la lista..."
                progress_bar.visible = True
                progress_bar.value = None
            ui_sync(_prep_ui)

            ydl_extract_opts = {
                'extract_flat': 'in_playlist',
                'noplaylist': False,
                'quiet': True,
                'ignoreerrors': True,
                'no_warnings': True,
                'nocheckcertificate': True,
            }

            urls_videos = []
            try:
                with yt_dlp.YoutubeDL(ydl_extract_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info and 'entries' in info and info['entries']:
                        for entry in info['entries']:
                            if not entry:
                                continue
                            vid_id = entry.get('id')
                            v_url = entry.get('url')
                            if v_url and not v_url.startswith("http"):
                                v_url = f"https://www.youtube.com/watch?v={v_url}"
                            elif not v_url and vid_id:
                                v_url = f"https://www.youtube.com/watch?v={vid_id}"
                            if v_url:
                                urls_videos.append((v_url, entry.get('title') or vid_id or "Vídeo"))
                    elif info:
                        urls_videos = [(url, info.get('title') or "Vídeo")]
            except Exception as e:
                def _err_lista():
                    status_text.value = f"Error al leer lista: {str(e)[:65]}"
                    btn_descargar.disabled = False
                    progress_bar.visible = False
                ui_sync(_err_lista)
                return

            total = len(urls_videos)
            if total == 0:
                def _sin_videos():
                    status_text.value = "No se encontraron videos."
                    btn_descargar.disabled = False
                    progress_bar.visible = False
                ui_sync(_sin_videos)
                return

            completadas = 0
            exitosas = 0
            fallidas = 0

            def _inicio_desc():
                progress_bar.value = 0
                status_text.value = f"Descargando 0 de {total} ({max_hilos} hilos)..."
            ui_sync(_inicio_desc)

            def descargar_una(item):
                nonlocal completadas, exitosas, fallidas
                video_url, titulo_previo = item
                carpeta_caratulas = os.path.join(ruta_actual, ".caratulas")
                os.makedirs(carpeta_caratulas, exist_ok=True)

                ydl_opts = {
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'noplaylist': True,
                    'outtmpl': {
                        'default': f'{ruta_actual}/%(title)s.m4a',
                        'thumbnail': f'{carpeta_caratulas}/%(title)s.%(ext)s',
                    },
                    'writethumbnail': True,
                    'ignoreerrors': False,
                    'abort_on_error': False,
                    'quiet': True,
                    'no_warnings': True,
                    'nocheckcertificate': True,
                    'retries': 3,
                    'fragment_retries': 3,
                }

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info_video = ydl.extract_info(video_url, download=True)
                        if not info_video:
                            raise RuntimeError("Vídeo privado, eliminado o no disponible")
                        ruta_archivo = ydl.prepare_filename(info_video)
                        if not os.path.exists(ruta_archivo):
                            raise RuntimeError("No se generó el archivo descargado")
                        titulo_real = info_video.get('title') or titulo_previo
                        base_nombre, _ = os.path.splitext(os.path.basename(ruta_archivo))

                        try:
                            incrustar_caratula_en_audio(
                                ruta_archivo, info_video.get("thumbnail"), carpeta_caratulas, base_nombre
                            )
                        except Exception:
                            pass
                        with ui_lock:
                            exitosas += 1
                        log(f"✔ Descarga finalizada (.m4a): {titulo_real}")
                except BaseException as e:
                    with ui_lock:
                        fallidas += 1
                    msg_error = str(e).replace("ERROR: ", "").strip() or "Error desconocido"
                    log(f"✖ Falló ({titulo_previo}): {msg_error[:75]}")
                finally:
                    with ui_lock:
                        completadas += 1
                        c_snap, e_snap, f_snap = completadas, exitosas, fallidas
                    def _prog():
                        progress_bar.value = c_snap / total
                        status_text.value = f"Progreso: {c_snap}/{total} (✔ {e_snap} | ✖ {f_snap})"
                    ui_sync(_prog)

            with ThreadPoolExecutor(max_workers=max_hilos) as executor:
                futures = [executor.submit(descargar_una, item) for item in urls_videos]
                for f in futures:
                    try:
                        f.result()
                    except BaseException:
                        pass

            def _fin_total():
                escanear_canciones()
                status_text.value = f"¡Finalizado! ✔ {exitosas} descargadas | ✖ {fallidas} fallidas"
                btn_descargar.disabled = False
            ui_sync(_fin_total)
        finally:
            descarga_en_curso = False


    def iniciar_descarga_desde_busqueda(url_destino, hilos):
        url_input.value = url_destino
        tabs.selected_index = 2
        page.update()
        threading.Thread(target=descargar_playlist, args=(url_destino, hilos), daemon=True).start()

    def iniciar_click(e):
        url = url_input.value.strip()
        if not url:
            status_text.value = "Por favor, introduce un enlace válido."
            page.update()
            return
        max_hilos = os.cpu_count() or 4
        threading.Thread(target=descargar_playlist, args=(url, max_hilos), daemon=True).start()

    btn_descargar = ft.Button("Descargar Todo", icon=ft.Icons.DOWNLOAD, on_click=iniciar_click)

    # escanear_canciones()  # <-- AÑADIR ANTES DE page.add
    btn_caratulas = ft.Button("Carátulas", icon=ft.Icons.IMAGE_SEARCH, on_click=iniciar_descarga_caratulas)

    vista_biblioteca = ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        expand=True,
        content=ft.Column([
            ft.Row([
                ft.Button("Elegir carpeta", icon=ft.Icons.FOLDER_OPEN, on_click=lambda _: page.run_task(abrir_selector_carpeta)),
                btn_caratulas,
                ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Actualizar", on_click=escanear_canciones),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([ft.Icon(ft.Icons.FOLDER, size=14, color=ft.Colors.GREY_400), lbl_ruta_actual]),
            ft.Divider(height=1),
            lista_canciones_ui
        ], expand=True, spacing=8)
    )


    vista_descargador = ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        expand=True,
        content=ft.Column([
            ft.Row([url_input]),
            ft.Row([btn_descargar, status_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            progress_bar,
            ft.Divider(height=1),
            log_column
        ], expand=True, spacing=10)
    )

    busqueda_input = ft.TextField(
        label="Buscar en YouTube",
        hint_text="Artista, canción o vídeo...",
        expand=True,
        on_submit=lambda e: buscar_youtube_click(e),
    )
    status_busqueda = ft.Text("Escribe algo para buscar", size=12, color=ft.Colors.GREY_400)
    lista_resultados_yt = ft.ListView(expand=True, spacing=6)

    video_player = ftv.Video(
        playlist=[],
        aspect_ratio=16 / 9,
        autoplay=True,
        expand=True,
        fill_color=ft.Colors.BLACK,
    ) if ftv else None

    lbl_video_mini = ft.Text("", size=12, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)

    async def cerrar_reproductor_video(e=None):
        if video_player and contenedor_video_mini.visible:
            try:
                await video_player.pause()
                video_player.playlist = []
            except Exception:
                pass
        if contenedor_video_mini.visible:
            contenedor_video_mini.visible = False
            page.update()


    contenedor_video_mini = ft.Container(
        visible=False,
        bgcolor=ft.Colors.BLACK,
        border_radius=8,
        padding=6,
        border=ft.Border.all(1, ft.Colors.GREY_800),
        content=ft.Column([
            ft.Row([
                lbl_video_mini,
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_size=18,
                    tooltip="Cerrar vídeo",
                    on_click=lambda e: page.run_task(cerrar_reproductor_video, e),
                ),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(
                height=180,
                border_radius=6,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=video_player if video_player else ft.Text(
                    "Instala 'flet-video' para ver el vídeo aquí.",
                    size=12,
                    color=ft.Colors.GREY_400,
                ),
            ),
        ], spacing=4),
    )


    async def reproducir_video_youtube(video_url, titulo, idx_lista=None):
        nonlocal indice_actual, esta_reproduciendo, indice_video_yt
        indice_actual = -1
        if idx_lista is not None:
            indice_video_yt = idx_lista
        lbl_cancion_actual.value = f"Cargando vídeo: {titulo}..."
        lbl_video_mini.value = titulo
        slider_progreso.value = 0
        slider_progreso.max = 100
        if esta_reproduciendo:
            await audio_player.pause()
        page.update()

        def extraer_stream():
            fmt = (
                "best[ext=mp4][vcodec!=none][acodec!=none]/"
                "best[vcodec!=none][acodec!=none]/"
                "best"
            ) if video_player else "bestaudio[ext=m4a]/bestaudio/best"
            opts = {
                "format": fmt,
                "quiet": True,
                "no_warnings": True,
                "nocheckcertificate": True,
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                url_directa = info.get("url")
                headers = info.get("http_headers") or {}
                if not url_directa and info.get("formats"):
                    validos = [
                        f for f in info["formats"]
                        if f.get("url") and f.get("vcodec") != "none" and f.get("acodec") != "none"
                    ]
                    if not validos:
                        validos = [f for f in info["formats"] if f.get("url")]
                    if validos:
                        url_directa = validos[-1]["url"]
                        headers = validos[-1].get("http_headers") or headers
                return url_directa, info.get("title", titulo), headers

        try:
            loop = asyncio.get_running_loop()
            stream_url, titulo_real, headers = await loop.run_in_executor(None, extraer_stream)
            if not stream_url:
                status_busqueda.value = "No se pudo obtener el vídeo."
                page.update()
                return

            lbl_cancion_actual.value = titulo_real
            lbl_video_mini.value = titulo_real

            if video_player:
                if contenedor_video_mini.visible:
                    await video_player.pause()
                contenedor_video_mini.visible = True
                video_player.playlist = [ftv.VideoMedia(resource=stream_url, http_headers=headers)]
                esta_reproduciendo = True
                btn_play_pause.icon = ft.Icons.PAUSE
                page.update()
                await video_player.play()
            else:
                audio_player.src = stream_url
                page.update()
                await audio_player.play()

            await actualizar_notificacion_bloqueo(titulo_custom=titulo_real)

        except Exception as err:
            lbl_cancion_actual.value = "Error al reproducir vídeo"
            status_busqueda.value = f"Error: {str(err)[:65]}"
            page.update()

    async def on_lifecycle_change(e: ft.AppLifecycleStateChangeEvent):
        if e.state in (ft.AppLifecycleState.PAUSE, ft.AppLifecycleState.HIDE, ft.AppLifecycleState.INACTIVE):
            if video_player and contenedor_video_mini.visible and esta_reproduciendo:
                await asyncio.sleep(0.2)
                try:
                    await video_player.play()
                except Exception:
                    pass

    page.on_app_lifecycle_state_change = on_lifecycle_change

    def buscar_youtube_click(e=None):
        query = busqueda_input.value.strip()
        if not query:
            return
        status_busqueda.value = "Buscando vídeos y colecciones en YouTube..."
        lista_resultados_yt.controls = []
        page.update()

        def tarea_busqueda():
            nonlocal videos_yt_actuales, indice_video_yt
            yt_watch_base = "https://www.youtube.com/watch?v="
            yt_playlist_base = "https://youtube.com"
            yt_img_base = "https://i.ytimg.com/vi/"

            ydl_search_opts = {
                "extract_flat": "in_playlist",
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": True,
                "nocheckcertificate": True,
                "socket_timeout": 10,
            }

            entries_listas = []
            entries_videos = []

            try:
                query_encoded = urllib.parse.quote(query)
                url_listas = f"https://youtube.com{query_encoded}&sp=EgIQAw%3D%3D"
                with yt_dlp.YoutubeDL({**ydl_search_opts, "playlistend": 8}) as ydl_pl:
                    res_pl = ydl_pl.extract_info(url_listas, download=False)
                    entries_listas = [e for e in ((res_pl or {}).get("entries") or []) if e]
            except Exception:
                entries_listas = []

            try:
                with yt_dlp.YoutubeDL(ydl_search_opts) as ydl:
                    res = ydl.extract_info(f"ytsearch25:{query}", download=False)
                    entries_videos = [e for e in ((res or {}).get("entries") or []) if e]
            except Exception as err:
                def _err_busq():
                    status_busqueda.value = f"Error de búsqueda: {str(err)[:65]}"
                ui_sync(_err_busq)
                return

            nuevos_controles = []
            nueva_lista_videos = []
            ids_vistos = set()

            for item in entries_listas + entries_videos:
                titulo = item.get("title") or "Sin título"
                canal = item.get("uploader") or item.get("channel") or ""
                vid_id = item.get("id") or ""
                entry_url = item.get("url") or ""
                ie_key = (item.get("ie_key") or "").lower()

                if not vid_id or vid_id in ids_vistos:
                    continue
                ids_vistos.add(vid_id)

                es_playlist = (
                    item.get("_type") == "playlist"
                    or "playlist" in ie_key
                    or "list=" in entry_url
                    or vid_id.startswith(("PL", "OLAK", "RD", "UU"))
                )

                if es_playlist:
                    v_url = entry_url if entry_url.startswith("http") else f"{yt_playlist_base}{vid_id}"
                    thumbs = item.get("thumbnails") or []
                    thumb_url = (
                        thumbs[-1].get("url")
                        if thumbs and isinstance(thumbs[-1], dict)
                        else item.get("thumbnail")
                    )
                    subtitulo = f"📑 COLECCIÓN / PLAYLIST • {canal}" if canal else "📑 COLECCIÓN DE CANCIONES"

                    portada = ft.Container(
                        width=76,
                        height=44,
                        border_radius=6,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        bgcolor=ft.Colors.GREY_800,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Stack([
                            ft.Image(src=thumb_url, width=76, height=44, fit=ft.BoxFit.COVER),
                            ft.Container(
                                alignment=ft.Alignment.CENTER,
                                bgcolor=ft.Colors.BLACK_45,
                                content=ft.Icon(ft.Icons.PLAYLIST_PLAY, color=ft.Colors.AMBER, size=24),
                            ),
                        ]) if thumb_url else ft.Icon(ft.Icons.PLAYLIST_PLAY, color=ft.Colors.AMBER, size=24),
                    )

                    nuevos_controles.append(
                        ft.ListTile(
                            dense=True,
                            content_padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                            leading=portada,
                            title=ft.Text(titulo, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            subtitle=ft.Text(subtitulo, size=11, color=ft.Colors.AMBER_200),
                            on_click=lambda _, u=v_url: iniciar_descarga_desde_busqueda(u, os.cpu_count() or 4),
                            trailing=ft.IconButton(
                                icon=ft.Icons.DOWNLOAD,
                                tooltip="Descargar todas las canciones",
                                on_click=lambda _, u=v_url: iniciar_descarga_desde_busqueda(u, os.cpu_count() or 4),
                            ),
                        )
                    )
                else:
                    v_url = entry_url if entry_url.startswith("http") else f"{yt_watch_base}{vid_id}"
                    thumb_url = f"{yt_img_base}{vid_id}/hqdefault.jpg" if vid_id else item.get("thumbnail")
                    dur = item.get("duration")
                    dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}" if dur else ""

                    idx_vid = len(nueva_lista_videos)
                    nueva_lista_videos.append((v_url, titulo))

                    portada = ft.Container(
                        width=76,
                        height=44,
                        border_radius=6,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        bgcolor=ft.Colors.GREY_800,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Stack([
                            ft.Image(src=thumb_url, width=76, height=44, fit=ft.BoxFit.COVER),
                            ft.Container(
                                alignment=ft.Alignment.CENTER,
                                bgcolor=ft.Colors.BLACK_26,
                                content=ft.Icon(ft.Icons.PLAY_ARROW, color=ft.Colors.WHITE, size=20),
                            ),
                        ]) if thumb_url else ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, color=ft.Colors.RED_400),
                    )

                    nuevos_controles.append(
                        ft.ListTile(
                            dense=True,
                            content_padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                            leading=portada,
                            title=ft.Text(titulo, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            subtitle=ft.Text(f"{canal} • {dur_str}".strip(" •"), size=11, color=ft.Colors.GREY_400),
                            on_click=lambda _, u=v_url, t=titulo, iv=idx_vid: page.run_task(
                                reproducir_video_youtube, u, t, iv
                            ),
                            trailing=ft.IconButton(
                                icon=ft.Icons.DOWNLOAD,
                                tooltip="Descargar audio (.m4a)",
                                on_click=lambda _, u=v_url: iniciar_descarga_desde_busqueda(u, 1),
                            ),
                        )
                    )

            videos_yt_actuales = nueva_lista_videos
            indice_video_yt = -1

            def _pintar_resultados():
                lista_resultados_yt.controls = nuevos_controles
                status_busqueda.value = f"{len(nuevos_controles)} resultados encontrados"
            ui_sync(_pintar_resultados)

        page.run_thread(tarea_busqueda)










    vista_buscador = ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        expand=True,
        content=ft.Column([
            ft.Row([
                busqueda_input,
                ft.IconButton(icon=ft.Icons.SEARCH, on_click=buscar_youtube_click),
            ]),
            contenedor_video_mini,
            status_busqueda,
            ft.Divider(height=1),
            lista_resultados_yt,
        ], expand=True, spacing=8)
    )


    tabs = ft.Tabs(
        selected_index=0,
        length=3,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label="Mi Música", icon=ft.Icons.LIBRARY_MUSIC),
                        ft.Tab(label="Buscar", icon=ft.Icons.SEARCH),
                        ft.Tab(label="Descargar", icon=ft.Icons.CLOUD_DOWNLOAD),
                    ]
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        vista_biblioteca,
                        vista_buscador,
                        vista_descargador,
                    ],
                ),
            ],
        ),
    )



    barra_reproductor = ft.Container(
        padding=ft.Padding.only(left=14, right=14, top=8, bottom=10),
        bgcolor=ft.Colors.GREY_900,
        border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.GREY_800)),
        content=ft.Column([
            ft.Row([ft.Container(content=lbl_cancion_actual, expand=True), lbl_tiempo]),
            slider_progreso,
            ft.Row([
                ft.IconButton(icon=ft.Icons.SKIP_PREVIOUS_ROUNDED, icon_size=32, on_click=lambda e: page.run_task(anterior_cancion, e)),
                btn_play_pause,
                ft.IconButton(icon=ft.Icons.SKIP_NEXT_ROUNDED, icon_size=32, on_click=lambda e: page.run_task(siguiente_cancion, e)),
                # ft.IconButton(icon=ft.Icons.SKIP_PREVIOUS_ROUNDED, icon_size=32, on_click=anterior_cancion),
                # btn_play_pause,
                # ft.IconButton(icon=ft.Icons.SKIP_NEXT_ROUNDED, icon_size=32, on_click=siguiente_cancion),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=20)
        ], spacing=0)
    )

    async def inicializar_app():
        try:
            await permisos.request(fph.Permission.MANAGE_EXTERNAL_STORAGE)
            await permisos.request(fph.Permission.AUDIO)
            await permisos.request(fph.Permission.STORAGE)
            await permisos.request(fph.Permission.IGNORE_BATTERY_OPTIMIZATIONS)
            await notificaciones.request_permissions()
        except Exception:
            pass
        carpeta_music = os.path.join(raiz_storage, "Music")
        try:
            if os.path.isdir(carpeta_music) and os.listdir(carpeta_music):
                establecer_carpeta(carpeta_music)
                return
        except Exception:
            pass
        escanear_canciones()


    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Column([tabs, barra_reproductor], expand=True, spacing=0)
        )
    )

    page.run_task(inicializar_app)



raiz_assets = "/storage/emulated/0" if os.path.exists("/storage/emulated/0") else os.path.abspath(".")
ft.run(main)


