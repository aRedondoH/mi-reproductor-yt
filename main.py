# -*- coding: utf-8 -*-
"""
Created on Thu Nov 19 17:23:41 2026

@author: Arh
"""

# -*- coding: utf-8 -*-
"""
Created on Wed Nov 18 09:25:24 2026

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
    async def manejar_accion_notificacion(e: ftn.NotificationActionEvent):
        if e.action_id == "prev":
            await anterior_cancion(None)
        elif e.action_id == "play_pause":
            await toggle_play_pause(None)
        elif e.action_id == "next":
            await siguiente_cancion(None)

    notificaciones = ftn.Notifications(on_action=manejar_accion_notificacion)
    page.services.append(notificaciones) if hasattr(page, "services") else page.overlay.append(notificaciones)

    async def actualizar_notificacion_bloqueo(titulo_custom=None, caratula_custom=None):
        if titulo_custom:
            titulo = titulo_custom
            ruta_caratula = caratula_custom
        else:
            if indice_actual < 0 or indice_actual >= len(canciones_locales):
                return
            nombre_archivo = canciones_locales[indice_actual]
            titulo = os.path.splitext(nombre_archivo)[0]
            ruta_caratula = obtener_caratula(nombre_archivo)

        texto_boton = "⏸ Pausar" if esta_reproduciendo else "▶ Reproducir"
        # large_icon = ftn.AndroidFileBitmap(ruta_caratula) if ruta_caratula and os.path.isfile(ruta_caratula) else None
        large_icon = None
        if ruta_caratula and os.path.isfile(ruta_caratula):
            try:
                with open(ruta_caratula, "rb") as f:
                    large_icon = ftn.AndroidBytesBitmap(data=f.read())
            except Exception:
                large_icon = None

        await notificaciones.show(
            id=1001,
            title=titulo,
            body="Reproduciendo" if esta_reproduciendo else "En pausa",
            actions=[
                ftn.NotificationAction(
                    id="prev",
                    title="⏮ Anterior",
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
                    title="⏭ Siguiente",
                    cancel_notification=False,
                    foreground=False,
                    require_authentication=False,
                ),
            ],
            options=ftn.NotificationOptions(
                android=ftn.AndroidOptions(
                    ongoing=True,
                    silent=True,
                    only_alert_once=True,
                    large_icon=large_icon,
                    category=ftn.AndroidCategory.TRANSPORT,
                    visibility=ftn.AndroidVisibility.PUBLIC,
                )
            ),
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
        if not arrastrando_slider and slider_progreso.max > 0:
            slider_progreso.value = min(e.position, slider_progreso.max)
            lbl_tiempo.value = f"{formatear_tiempo(e.position)} / {formatear_tiempo(slider_progreso.max)}"
            page.update()

    # async def on_duration_changed(e: fta.AudioDurationChangeEvent):
    #     if e.duration > 0:
    #         slider_progreso.max = e.duration
    #         page.update()

    # async def on_state_changed(e: fta.AudioStateChangeEvent):
    #     nonlocal esta_reproduciendo
    #     if e.state == fta.AudioState.COMPLETED:
    #         await siguiente_cancion(None)
    #     elif e.state == fta.AudioState.PLAYING:
    #         esta_reproduciendo = True
    #         btn_play_pause.icon = ft.Icons.PAUSE
    #         page.update()
    #     elif e.state in (fta.AudioState.PAUSED, fta.AudioState.STOPPED):
    #         esta_reproduciendo = False
    #         btn_play_pause.icon = ft.Icons.PLAY_ARROW
    #         page.update()
    
    async def on_duration_changed(e: fta.AudioDurationChangeEvent):
        dur_ms = e.duration.in_milliseconds if hasattr(e.duration, "in_milliseconds") else int(e.duration or 0)
        if dur_ms > 0:
            slider_progreso.max = dur_ms
            lbl_tiempo.value = f"{formatear_tiempo(slider_progreso.value)} / {formatear_tiempo(dur_ms)}"
            page.update()

    async def on_state_changed(e: fta.AudioStateChangeEvent):
        nonlocal esta_reproduciendo
        if e.state == fta.AudioState.COMPLETED:
            await siguiente_cancion(None)
        elif e.state == fta.AudioState.PLAYING:
            esta_reproduciendo = True
            btn_play_pause.icon = ft.Icons.PAUSE
            page.update()
            await actualizar_notificacion_bloqueo()
        elif e.state in (fta.AudioState.PAUSED, fta.AudioState.STOPPED):
            esta_reproduciendo = False
            btn_play_pause.icon = ft.Icons.PLAY_ARROW
            page.update()
            await actualizar_notificacion_bloqueo()
    

    audio_player = fta.Audio(
        autoplay=False,
        release_mode=fta.ReleaseMode.STOP,
        context=fta.AudioContext(focus=fta.AudioFocus.GAIN),
        on_position_change=on_position_changed,
        on_duration_change=on_duration_changed,
        on_state_change=on_state_changed,
    )
    page.services.append(audio_player) if hasattr(page, "services") else page.overlay.append(audio_player)

#     async def reproducir_indice(idx):
#         nonlocal indice_actual
#         if not canciones_locales or idx < 0 or idx >= len(canciones_locales):
#             return
#         indice_actual = idx
#         nombre = canciones_locales[indice_actual]
#         lbl_cancion_actual.value = os.path.splitext(nombre)[0]
#         slider_progreso.value = 0
#         await audio_player.pause()
#         # audio_player.src = f"/{nombre}"
#         ruta_completa = os.path.join(ruta_actual, nombre)
# #        ruta_relativa = os.path.relpath(ruta_completa, raiz_storage).replace("\\", "/")
# #        audio_player.src = f"/{ruta_relativa}"
# #        ruta_completa = os.path.join(carpeta_input.value.strip(), nombre)
#         audio_player.src = ruta_completa
        
#         page.update()
#         await audio_player.play()
#         actualizar_lista_ui()

    async def reproducir_indice(idx):
        nonlocal indice_actual
        if not canciones_locales or idx < 0 or idx >= len(canciones_locales):
            return
        await cerrar_reproductor_video()
        anterior_idx = indice_actual
        indice_actual = idx
        nombre = canciones_locales[indice_actual]
        lbl_cancion_actual.value = os.path.splitext(nombre)[0]
        slider_progreso.value = 0
        slider_progreso.max = 100

        for pos in (anterior_idx, indice_actual):
            if 0 <= pos < len(lista_canciones_ui.controls):
                tile = lista_canciones_ui.controls[pos]
                if isinstance(tile.title, ft.Text):
                    tile.title.weight = ft.FontWeight.BOLD if pos == indice_actual else None

        await audio_player.pause()
        audio_player.src = os.path.join(ruta_actual, nombre)
        page.update()
        await audio_player.play()
        await actualizar_notificacion_bloqueo()



    async def toggle_play_pause(e):
        if indice_actual == -1:
            if canciones_locales:
                await reproducir_indice(0)
            return

        if esta_reproduciendo:
            await audio_player.pause()
        else:
            await audio_player.resume()


    

    async def siguiente_cancion(e):
        if canciones_locales:
            await reproducir_indice((indice_actual + 1) % len(canciones_locales))

    async def anterior_cancion(e):
        if canciones_locales:
            await reproducir_indice((indice_actual - 1) % len(canciones_locales))

    def on_slider_start(e):
        nonlocal arrastrando_slider
        arrastrando_slider = True

    # async def on_slider_end(e):
    #     nonlocal arrastrando_slider
    #     arrastrando_slider = False
    #     await audio_player.seek(int(e.control.value))
    
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

  




    # def actualizar_lista_ui():
    #     lista_canciones_ui.controls.clear()
    #     for i, archivo in enumerate(canciones_locales):
    #         es_actual = (i == indice_actual)
    #         lista_canciones_ui.controls.append(
    #             ft.ListTile(
    #                 leading=ft.Icon(ft.Icons.GRAPHIC_EQ if es_actual else ft.Icons.MUSIC_NOTE),
    #                 title=ft.Text(os.path.splitext(archivo)[0], max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
    #                 on_click=lambda e, idx=i: page.run_task(reproducir_indice, idx)
    #             )
    #         )
    #     page.update()

    # def actualizar_lista_ui():
    #     lista_canciones_ui.controls.clear()
    #     for i, archivo in enumerate(canciones_locales):
    #         es_actual = (i == indice_actual)
    #         lista_canciones_ui.controls.append(
    #             ft.ListTile(
    #                 dense=True,
    #                 content_padding=ft.Padding.symmetric(horizontal=4, vertical=0),
    #                 leading=ft.Icon(ft.Icons.GRAPHIC_EQ if es_actual else ft.Icons.MUSIC_NOTE, size=16),
    #                 title=ft.Text(
    #                     os.path.splitext(archivo)[0],
    #                     size=12,
    #                     max_lines=1,
    #                     overflow=ft.TextOverflow.ELLIPSIS,
    #                 ),
    #                 on_click=lambda e, idx=i: page.run_task(reproducir_indice, idx),
    #             )
    #         )
    #     page.update()

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
        btn_caratulas.disabled = True
        page.update()
        try:
            carpeta_actual_snap = ruta_actual
            carpeta_caratulas = os.path.join(carpeta_actual_snap, ".caratulas")
            hubo_cambios = False

            for archivo in list(canciones_locales):
                if ruta_actual != carpeta_actual_snap:
                    break
                if obtener_caratula(archivo) is None:
                    if extraer_caratula_embebida(archivo):
                        hubo_cambios = True

            if hubo_cambios and ruta_actual == carpeta_actual_snap:
                actualizar_lista_ui()
                hubo_cambios = False

            pendientes = [
                f for f in list(canciones_locales)
                if (carpeta_actual_snap, f) not in caratulas_buscadas and obtener_caratula(f) is None
            ]
            if not pendientes:
                return

            opts = {"extract_flat": "in_playlist", "quiet": True, "ignoreerrors": True}
            yt_img_base = "https://" + "i.ytimg.com/vi/"
            with yt_dlp.YoutubeDL(opts) as ydl:
                for idx_p, archivo in enumerate(pendientes):
                    if ruta_actual != carpeta_actual_snap:
                        break
                    caratulas_buscadas.add((carpeta_actual_snap, archivo))
                    base_nombre = os.path.splitext(archivo)[0]
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
                            hubo_cambios = True
                            if idx_p % 3 == 0:
                                actualizar_lista_ui()
                                hubo_cambios = False
                    except Exception:
                        continue

            if hubo_cambios and ruta_actual == carpeta_actual_snap:
                actualizar_lista_ui()
        finally:
            descargando_caratulas = False
            btn_caratulas.disabled = False
            page.update()

    def iniciar_descarga_caratulas(e=None):
        claves_carpeta = [k for k in caratulas_buscadas if k[0] == ruta_actual]
        for k in claves_carpeta:
            caratulas_buscadas.discard(k)
        threading.Thread(target=descargar_caratulas_faltantes, daemon=True).start()

    def escanear_canciones(e=None):
        nonlocal canciones_locales
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
                                bgcolor=ft.Colors.BLACK54,
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

    
    # Candado para evitar conflictos visuales entre hilos
    ui_lock = threading.Lock()

    def log(mensaje):
        with ui_lock:
            log_column.controls.append(ft.Text(mensaje, size=12))
            page.update()

    def incrustar_caratula_en_audio(ruta_audio, thumb_url, carpeta_caratulas, base_nombre):
        try:
            import urllib.request
            from mutagen.mp4 import MP4, MP4Cover
            from mutagen.id3 import ID3, APIC

            datos_img = None
            # 1. Buscar si yt-dlp ya descargó una miniatura local
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                posible = os.path.join(carpeta_caratulas, base_nombre + ext)
                if os.path.isfile(posible):
                    with open(posible, "rb") as f:
                        datos_img = f.read()
                    break

            # 2. Si es webp o no existe, descargar directamente en JPG desde YouTube
            if thumb_url and (not datos_img or posible.endswith(".webp")):
                jpg_url = thumb_url.replace("vi_webp/", "vi/").replace(".webp", ".jpg")
                req = urllib.request.urlopen(jpg_url, timeout=10)
                datos_img = req.read()
                ruta_jpg = os.path.join(carpeta_caratulas, base_nombre + ".jpg")
                with open(ruta_jpg, "wb") as f:
                    f.write(datos_img)

            if not datos_img:
                return

            # 3. Incrustar en M4A/MP4 o MP3
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
        os.makedirs(ruta_actual, exist_ok=True)

        status_text.value = "Extrayendo canciones de la lista..."
        progress_bar.visible = True
        progress_bar.value = None
        page.update()

        # 1. Extraer rápidamente todas las URLs de la playlist sin descargar
        ydl_extract_opts = {
            'extract_flat': True,
            'quiet': True,
            'ignoreerrors': True
        }

        urls_videos = []
        try:
            with yt_dlp.YoutubeDL(ydl_extract_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    urls_videos = [entry['url'] for entry in info['entries'] if entry and entry.get('url')]
                else:
                    # Por si el usuario pegó el enlace de un solo video en lugar de una lista
                    urls_videos = [url]
        except Exception as e:
            status_text.value = f"Error al leer lista: {str(e)}"
            btn_descargar.disabled = False
            progress_bar.visible = False
            page.update()
            return

        total = len(urls_videos)
        if total == 0:
            status_text.value = "No se encontraron videos."
            btn_descargar.disabled = False
            progress_bar.visible = False
            page.update()
            return

        completadas = 0
        progress_bar.value = 0
        status_text.value = f"Descargando 0 de {total} canciones ({max_hilos} hilos)..."
        page.update()

        # 2. Función que ejecutará cada hilo individualmente
        # def descargar_una(video_url):
        #     nonlocal completadas
        #     os.makedirs(ruta_actual, exist_ok=True)
        #     ydl_opts = {
        #         'format': 'bestaudio[ext=m4a]/bestaudio',
        #         'outtmpl': f'{ruta_actual}/%(title)s.%(ext)s',
        #         'ignoreerrors': True,
        #         'quiet': True,
        #         'no_warnings': True
        #     }

            
        #     try:
        #         with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        #             info_video = ydl.extract_info(video_url, download=True)
        #             titulo = info_video.get('title', 'Canción') if info_video else 'Canción'
        #             log(f"✔ {titulo}")
        #     except Exception as e:
        #         log(f"✖ Error en un enlace: {str(e)[:40]}")
        #     finally:
        #         with ui_lock:
        #             completadas += 1
        #             progress_bar.value = completadas / total
        #             status_text.value = f"Progreso: {completadas} de {total} completadas"
                    
        #             page.update()
        # def descargar_una(video_url):
        #     nonlocal completadas
        #     os.makedirs(ruta_actual, exist_ok=True)
        #     ydl_opts = {
        #         'format': 'bestaudio[ext=m4a]/bestaudio',
        #         'outtmpl': f'{ruta_actual}/%(title)s.%(ext)s',
        #         'ignoreerrors': False,
        #         'quiet': True,
        #         'no_warnings': True,
        #     }

        def descargar_una(video_url):
            nonlocal completadas
            carpeta_caratulas = os.path.join(ruta_actual, ".caratulas")
            os.makedirs(carpeta_caratulas, exist_ok=True)
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio',
                'outtmpl': {
                    'default': f'{ruta_actual}/%(title)s.%(ext)s',
                    'thumbnail': f'{carpeta_caratulas}/%(title)s.%(ext)s',
                },
                'writethumbnail': True,
                'ignoreerrors': False,
                'quiet': True,
                'no_warnings': True,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_video = ydl.extract_info(video_url, download=True)
                    if not info_video:
                        raise Exception("No se pudo obtener información del vídeo.")
                    ruta_archivo = ydl.prepare_filename(info_video)
                    if not os.path.exists(ruta_archivo):
                        raise Exception("El archivo no se guardó en el dispositivo.")
                    base_nombre = os.path.splitext(os.path.basename(ruta_archivo))[0]
                    incrustar_caratula_en_audio(ruta_archivo, info_video.get("thumbnail"), carpeta_caratulas, base_nombre)
                    titulo = info_video.get('title', 'Canción')
                    log(f"✔ {titulo}")
            except Exception as e:
                msg_error = str(e).replace("ERROR: ", "").strip()
                log(f"✖ Error ({video_url}): {msg_error[:80]}")
            finally:
                with ui_lock:
                    completadas += 1
                    progress_bar.value = completadas / total
                    status_text.value = f"Progreso: {completadas} de {total} completadas"
                    page.update()

        
                    

        # 3. Lanzar el pool de hilos en paralelo
        with ThreadPoolExecutor(max_workers=max_hilos) as executor:
            executor.map(descargar_una, urls_videos)

        escanear_canciones()
        status_text.value = f"¡Finalizado! Se procesaron {total} elementos."
        btn_descargar.disabled = False
        page.update()

    def iniciar_click(e):
        url = url_input.value.strip()
        if not url:
            status_text.value = "Por favor, introduce un enlace válido."
            page.update()
            return
        
        btn_descargar.disabled = True
        log_column.controls.clear()
        max_hilos = os.cpu_count() or 4
        page.update()
        
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
        if video_player:
            try:
                await video_player.pause()
                video_player.playlist = []
            except Exception:
                pass
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


    async def reproducir_video_youtube(video_url, titulo):
        nonlocal indice_actual
        indice_actual = -1
        lbl_cancion_actual.value = f"Cargando vídeo: {titulo}..."
        lbl_video_mini.value = titulo
        slider_progreso.value = 0
        slider_progreso.max = 100
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
                await video_player.pause()
                contenedor_video_mini.visible = True
                video_player.playlist = [ftv.VideoMedia(resource=stream_url, http_headers=headers)]
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

    def buscar_youtube_click(e=None):
        query = busqueda_input.value.strip()
        if not query:
            return
        status_busqueda.value = "Buscando en YouTube..."
        lista_resultados_yt.controls.clear()
        page.update()

        def tarea_busqueda():
            opts = {
                "extract_flat": "in_playlist",
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": False,
                "playlistend": 15,
                "extractor_args": {"youtube": {"player_client": ["web", "android"]}},
            }
            resultados = []
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(f"ytsearch15:{query}", download=False)
                    resultados = [r for r in (info.get("entries") or []) if r] if info else []
                    if not resultados:
                        dominio_yt = "www." + "youtube" + ".com"
                        ruta_busqueda = "/results" + "?search_query="
                        search_url = f"https://{dominio_yt}{ruta_busqueda}{urllib.parse.quote(query)}"

                        # search_url = "https://" + "://youtube.com" + urllib.parse.quote(query)
                        info = ydl.extract_info(search_url, download=False)
                        resultados = [r for r in (info.get("entries") or []) if r and r.get("id")] if info else []
            except Exception as err:
                status_busqueda.value = f"Error de búsqueda: {str(err)[:65]}"
                page.update()
                return

            yt_watch_base = "https://" + "www.youtube.com/watch?v="
            yt_img_base = "https://" + "i.ytimg.com/vi/"

            lista_resultados_yt.controls.clear()
            for item in resultados:
                titulo = item.get("title", "Sin título")
                canal = item.get("uploader") or item.get("channel") or ""
                duracion = item.get("duration")
                dur_str = f"{int(duracion // 60):02d}:{int(duracion % 60):02d}" if duracion else ""
                vid_id = item.get("id")
                raw_url = item.get("url") or ""
                v_url = raw_url if raw_url.startswith("http") else f"{yt_watch_base}{vid_id}"

                thumbs = item.get("thumbnails") or []
                thumb_url = (
                    item.get("thumbnail")
                    or (thumbs[-1].get("url") if thumbs else None)
                    or (f"{yt_img_base}{vid_id}/hqdefault.jpg" if vid_id else None)
                )

                if thumb_url:
                    portada = ft.Container(
                        width=76,
                        height=44,
                        border_radius=6,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        bgcolor=ft.Colors.GREY_900,
                        content=ft.Stack([
                            ft.Image(
                                src=thumb_url,
                                width=76,
                                height=44,
                                fit=ft.BoxFit.COVER,
                            ),
                            ft.Container(
                                alignment=ft.Alignment.CENTER,
                                bgcolor=ft.Colors.BLACK26,
                                content=ft.Icon(ft.Icons.PLAY_ARROW, color=ft.Colors.WHITE, size=20),
                            ),
                        ]),
                    )
                else:
                    portada = ft.Container(
                        width=76,
                        height=44,
                        border_radius=6,
                        bgcolor=ft.Colors.GREY_800,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, color=ft.Colors.RED_400),
                    )

                lista_resultados_yt.controls.append(
                    ft.ListTile(
                        dense=True,
                        content_padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                        leading=portada,
                        title=ft.Text(titulo, size=13, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        subtitle=ft.Text(f"{canal} • {dur_str}".strip(" •"), size=11, color=ft.Colors.GREY_400),
                        on_click=lambda _, u=v_url, t=titulo: page.run_task(reproducir_video_youtube, u, t),
                        trailing=ft.IconButton(
                            icon=ft.Icons.DOWNLOAD,
                            tooltip="Descargar audio",
                            on_click=lambda _, u=v_url: threading.Thread(
                                target=descargar_playlist, args=(u, 1), daemon=True
                            ).start(),
                        ),
                    )
                )
            status_busqueda.value = f"{len(resultados)} resultados encontrados"
            page.update()

        threading.Thread(target=tarea_busqueda, daemon=True).start()



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


