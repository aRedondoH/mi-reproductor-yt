# -*- coding: utf-8 -*-
"""
Created on Wed Nov 18 09:25:24 2026

@author: Arh
"""


import nest_asyncio
nest_asyncio.apply()
import flet as ft
import yt_dlp
import threading
import os
import flet_audio as fta
from concurrent.futures import ThreadPoolExecutor

def main(page: ft.Page):
    page.title = "Descargador Paralelo"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.padding = 20
    page.scroll = ft.ScrollMode.ADAPTIVE

    
    raiz_storage = "/storage/emulated/0" if os.path.exists("/storage/emulated/0") else os.path.abspath(".")
    ruta_inicial = os.path.join(raiz_storage, "Download") if os.path.exists("/storage/emulated/0") else os.path.join(raiz_storage, "descargas")
    os.makedirs(ruta_inicial, exist_ok=True)

    def cambiar_carpeta(e):
        nueva_ruta = carpeta_input.value.strip()
        if os.path.isdir(nueva_ruta):
            escanear_canciones()
            status_text.value = f"Carpeta activa: {nueva_ruta}"
        else:
            status_text.value = "La carpeta no existe."
        page.update()

    carpeta_input = ft.TextField(
        label="Carpeta de música y descargas",
        value=ruta_inicial,
        expand=True,
        on_submit=cambiar_carpeta
    )
    btn_aplicar_carpeta = ft.IconButton(
        icon=ft.Icons.FOLDER_OPEN,
        tooltip="Cargar carpeta",
        on_click=cambiar_carpeta
    )

    def seleccionar_rapido(e):
        if carpetas_dropdown.value:
            carpeta_input.value = carpetas_dropdown.value
            cambiar_carpeta(None)

    # Detecta automáticamente las carpetas habituales que existan en tu dispositivo
    # rutas_posibles = [
    #     ("Descargas", os.path.join(raiz_storage, "Download")),
    #     ("Música", os.path.join(raiz_storage, "Music")),
    #     ("Documentos", os.path.join(raiz_storage, "Documents")),
    #     ("Carpeta App", os.path.join(raiz_storage, "descargas")),
    # ]
    base_carpetas = "/storage/emulated/0" if os.path.exists("/storage/emulated/0") else os.path.expanduser("~")
    rutas_posibles = [
        ("Descargas", os.path.join(base_carpetas, "Download" if os.path.exists("/storage/emulated/0") else "Downloads")),
        ("Música", os.path.join(base_carpetas, "Music")),
        ("Carpeta App", os.path.join(raiz_storage, "descargas")),
    ]

    opciones_carpetas = [
        ft.dropdown.Option(key=ruta, text=nombre)
        for nombre, ruta in rutas_posibles
        if os.path.exists(ruta)
    ]

    carpetas_dropdown = ft.Dropdown(
        label="Acceso rápido",
        width=150,
        options=opciones_carpetas,
        on_select=seleccionar_rapido
    )


    canciones_locales = []
    indice_actual = -1
    esta_reproduciendo = False
    arrastrando_slider = False

    lbl_cancion_actual = ft.Text("Ninguna canción", weight=ft.FontWeight.BOLD, size=14, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    lbl_tiempo = ft.Text("00:00 / 00:00", size=12)
    slider_progreso = ft.Slider(min=0, max=100, value=0, expand=True)
    btn_play_pause = ft.IconButton(icon=ft.Icons.PLAY_ARROW, icon_size=32)
    lista_canciones_ui = ft.ListView(height=200, spacing=5)

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

    async def on_duration_changed(e: fta.AudioDurationChangeEvent):
        if e.duration > 0:
            slider_progreso.max = e.duration
            page.update()

    async def on_state_changed(e: fta.AudioStateChangeEvent):
        nonlocal esta_reproduciendo
        if e.state == fta.AudioState.COMPLETED:
            await siguiente_cancion(None)
        elif e.state == fta.AudioState.PLAYING:
            esta_reproduciendo = True
            btn_play_pause.icon = ft.Icons.PAUSE
            page.update()
        elif e.state in (fta.AudioState.PAUSED, fta.AudioState.STOPPED):
            esta_reproduciendo = False
            btn_play_pause.icon = ft.Icons.PLAY_ARROW
            page.update()

    audio_player = fta.Audio(
        autoplay=False,
        release_mode=fta.ReleaseMode.STOP,
        context=fta.AudioContext(focus=fta.AudioFocus.GAIN),
        on_position_change=on_position_changed,
        on_duration_change=on_duration_changed,
        on_state_change=on_state_changed,
    )
    page.services.append(audio_player) if hasattr(page, "services") else page.overlay.append(audio_player)

    async def reproducir_indice(idx):
        nonlocal indice_actual
        if not canciones_locales or idx < 0 or idx >= len(canciones_locales):
            return
        indice_actual = idx
        nombre = canciones_locales[indice_actual]
        lbl_cancion_actual.value = os.path.splitext(nombre)
        slider_progreso.value = 0
        await audio_player.pause()
        # audio_player.src = f"/{nombre}"
        ruta_completa = os.path.join(carpeta_input.value.strip(), nombre)
#        ruta_relativa = os.path.relpath(ruta_completa, raiz_storage).replace("\\", "/")
#        audio_player.src = f"/{ruta_relativa}"
#        ruta_completa = os.path.join(carpeta_input.value.strip(), nombre)
        audio_player.src = ruta_completa
        
        page.update()
        await audio_player.play()
        actualizar_lista_ui()

    async def toggle_play_pause(e):
        if not canciones_locales:
            return
        if indice_actual == -1:
            await reproducir_indice(0)
        elif esta_reproduciendo:
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

    async def on_slider_end(e):
        nonlocal arrastrando_slider
        arrastrando_slider = False
        await audio_player.seek(int(e.control.value))

    btn_play_pause.on_click = toggle_play_pause
    slider_progreso.on_change_start = on_slider_start
    slider_progreso.on_change_end = on_slider_end

    def escanear_canciones(e=None):
        nonlocal canciones_locales
        carpeta_actual = carpeta_input.value.strip()
        if not os.path.isdir(carpeta_actual):
            return
        exts = (".m4a", ".mp3", ".webm", ".opus", ".ogg", ".wav")
        archivos = [f for f in os.listdir(carpeta_actual) if f.lower().endswith(exts)]
        archivos.sort(key=lambda x: os.path.getmtime(os.path.join(carpeta_actual, x)), reverse=True)
        canciones_locales = archivos
        actualizar_lista_ui()


    def actualizar_lista_ui():
        lista_canciones_ui.controls.clear()
        for i, archivo in enumerate(canciones_locales):
            es_actual = (i == indice_actual)
            lista_canciones_ui.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.GRAPHIC_EQ if es_actual else ft.Icons.MUSIC_NOTE),
                    title=ft.Text(os.path.splitext(archivo), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    on_click=lambda e, idx=i: page.run_task(reproducir_indice, idx)
                )
            )
           
    url_input = ft.TextField(
        label="Enlace de la lista de reproducción",
        hint_text="https://youtube.com...",
        expand=True
    )

    status_text = ft.Text("Listo para descargar", size=14)
    progress_bar = ft.ProgressBar(width=400, value=0, visible=False)
    log_column = ft.Column(scroll=ft.ScrollMode.AUTO, height=120)
    
    # Candado para evitar conflictos visuales entre hilos
    ui_lock = threading.Lock()

    def log(mensaje):
        with ui_lock:
            log_column.controls.append(ft.Text(mensaje, size=12))
            page.update()

    def descargar_playlist(url, max_hilos):
        ruta_destino = "/storage/emulated/0/Download" if os.path.exists("/storage/emulated/0/Download") else "./descargas"
        os.makedirs(ruta_destino, exist_ok=True)

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
        def descargar_una(video_url):
            nonlocal completadas
            carpeta_actual = carpeta_input.value.strip()
            os.makedirs(carpeta_actual, exist_ok=True)
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio',
                'outtmpl': f'{carpeta_actual}/%(title)s.%(ext)s',
                'ignoreerrors': True,
                'quiet': True,
                'no_warnings': True
            }
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_video = ydl.extract_info(video_url, download=True)
                    titulo = info_video.get('title', 'Canción') if info_video else 'Canción'
                    log(f"✔ {titulo}")
            except Exception as e:
                log(f"✖ Error en un enlace: {str(e)[:40]}")
            finally:
                with ui_lock:
                    completadas += 1
                    progress_bar.value = completadas / total
                    status_text.value = f"Progreso: {completadas} de {total} completadas"
                    escanear_canciones()
                    page.update()
                    

        # 3. Lanzar el pool de hilos en paralelo
        with ThreadPoolExecutor(max_workers=max_hilos) as executor:
            executor.map(descargar_una, urls_videos)

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

    escanear_canciones()  # <-- AÑADIR ANTES DE page.add
    page.add(
        ft.Text("Descargador Paralelo", size=24, weight=ft.FontWeight.BOLD),
        ft.Row([url_input]),
        btn_descargar,
        status_text,
        progress_bar,
        ft.Divider(),
        log_column,  # <-- Aquí faltaba esta coma
        ft.Divider(),
        ft.Row([
            ft.Text("Música Local", size=18, weight=ft.FontWeight.BOLD, expand=True),
            ft.IconButton(icon=ft.Icons.REFRESH, on_click=escanear_canciones)
        ]),
        # ft.Row([carpetas_dropdown, carpeta_input, btn_aplicar_carpeta]),
        ft.Row([carpetas_dropdown, btn_aplicar_carpeta]),
        ft.Row([carpeta_input]),


        lista_canciones_ui,
        ft.Container(
            padding=10,
            border_radius=10,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=ft.Column([
                ft.Row([ft.Container(content=lbl_cancion_actual, expand=True), lbl_tiempo]),
                slider_progreso,
                ft.Row([
                    ft.IconButton(icon=ft.Icons.SKIP_PREVIOUS, on_click=anterior_cancion),
                    btn_play_pause,
                    ft.IconButton(icon=ft.Icons.SKIP_NEXT, on_click=siguiente_cancion),
                ], alignment=ft.MainAxisAlignment.CENTER)
            ], spacing=2)
        )
    )


raiz_assets = "/storage/emulated/0" if os.path.exists("/storage/emulated/0") else os.path.abspath(".")
ft.run(main)


