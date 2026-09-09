"""
Descarga y limpieza de transcripciones de YouTube.

Este modulo no sabe nada de interfaces ni de IA: recibe una URL y devuelve
una transcripcion limpia con marcas de tiempo reales.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

TAG_RE = re.compile(r"<[^>]+>")
CUE_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)
# Etiquetas de sonido que YouTube inserta y que son ruido para una nota de estudio.
SONIDO_RE = re.compile(
    r"^\[(music|applause|laughter|musica|música|aplausos|risas|aplauso)\]$",
    re.IGNORECASE,
)

IDIOMAS_POR_DEFECTO = "es.*,es,en.*,en"
VENTANA_POR_DEFECTO = 45

# Alturas de video ofrecidas, mas la opcion de guardar solo el audio.
CALIDAD_AUDIO = "audio"
CALIDADES = ("1080", "720", "480", CALIDAD_AUDIO)
CALIDAD_POR_DEFECTO = "1080"


class ErrorTranscripcion(Exception):
    """Falla esperable al obtener una transcripcion, con mensaje para el usuario."""


class ErrorDescarga(Exception):
    """Falla esperable al descargar el video, con mensaje para el usuario."""


@dataclass
class Transcripcion:
    titulo: str
    canal: str
    url: str
    duracion: str
    fecha: str
    idioma: str
    origen: str
    bloques: list[tuple[int, str]] = field(default_factory=list)

    @property
    def cuerpo(self) -> str:
        return "\n\n".join(f"{marca(t)} {txt}" for t, txt in self.bloques)

    @property
    def palabras(self) -> int:
        return len(self.cuerpo.split())

    def a_markdown(self) -> str:
        comilla = chr(34)
        return (
            "---\n"
            f'titulo: "{self.titulo.replace(comilla, chr(39))}"\n'
            f'canal: "{self.canal.replace(comilla, chr(39))}"\n'
            f"url: {self.url}\n"
            f"duracion: {self.duracion}\n"
            f"fecha_video: {self.fecha}\n"
            f"idioma_subs: {self.idioma}\n"
            f"origen_subs: {self.origen}\n"
            "tipo: transcripcion-cruda\n"
            "---\n\n"
            f"# Transcripcion — {self.titulo}\n\n"
            f"{self.cuerpo}\n"
        )


def segundos(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def marca(total) -> str:
    """Formatea segundos como [MM:SS] o [HH:MM:SS] segun la duracion."""
    total = int(total)
    h, resto = divmod(total, 3600)
    m, s = divmod(resto, 60)
    if h:
        return f"[{h:02d}:{m:02d}:{s:02d}]"
    return f"[{m:02d}:{s:02d}]"


def duracion_legible(segs) -> str:
    if not segs:
        return "desconocida"
    return marca(segs).strip("[]")


def parsear_vtt(texto: str) -> list[tuple[float, list[str]]]:
    """Devuelve una lista de (inicio_en_segundos, [lineas de texto])."""
    cues = []
    for bloque in re.split(r"\n\s*\n", texto):
        lineas = [l for l in bloque.strip().split("\n") if l.strip()]
        if not lineas:
            continue

        idx = next((i for i, l in enumerate(lineas) if CUE_RE.match(l.strip())), None)
        if idx is None:
            continue

        m = CUE_RE.match(lineas[idx].strip())
        inicio = segundos(*m.groups()[:4])
        fin = segundos(*m.groups()[4:])

        # Los bloques de duracion ~0 solo repiten la linea anterior: se descartan.
        if fin - inicio < 0.05:
            continue

        contenido = []
        for l in lineas[idx + 1:]:
            l = TAG_RE.sub("", l).strip()
            l = re.sub(r"\s+", " ", l)
            if l and not SONIDO_RE.match(l):
                contenido.append(l)

        if contenido:
            cues.append((inicio, contenido))
    return cues


def desduplicar(cues, memoria: int = 8) -> list[tuple[float, str]]:
    """
    Los subtitulos automaticos repiten en cada bloque la ultima linea del anterior
    por el efecto de scroll. Se emite solo lo que no aparezca entre las ultimas
    lineas ya escritas.
    """
    salida = []
    recientes: list[str] = []
    for inicio, lineas in cues:
        nuevas = []
        for l in lineas:
            clave = l.lower().strip()
            if clave in recientes:
                continue
            nuevas.append(l)
            recientes.append(clave)
            if len(recientes) > memoria:
                recientes.pop(0)
        if nuevas:
            salida.append((inicio, " ".join(nuevas)))
    return salida


def agrupar(fragmentos, ventana: int) -> list[tuple[int, str]]:
    """Junta los fragmentos en bloques de `ventana` segundos con su marca de tiempo."""
    if not fragmentos:
        return []
    bloques = []
    inicio_bloque = fragmentos[0][0]
    acumulado: list[str] = []
    for t, texto in fragmentos:
        if t - inicio_bloque >= ventana and acumulado:
            bloques.append((int(inicio_bloque), " ".join(acumulado)))
            inicio_bloque = t
            acumulado = []
        acumulado.append(texto)
    if acumulado:
        bloques.append((int(inicio_bloque), " ".join(acumulado)))
    return bloques


def limpiar_nombre(nombre: str) -> str:
    """Quita los caracteres que Windows no admite en nombres de archivo."""
    nombre = re.sub(r'[<>:"/\\|?*]', "", nombre)
    nombre = re.sub(r"\s+", " ", nombre).strip().rstrip(".")
    return nombre[:120] or "video"


def _preferencias(langs: str) -> list[str]:
    """Convierte «es.*,en» en una lista de prefijos por orden de preferencia."""
    return [p.strip().replace(".*", "").lower()
            for p in langs.split(",") if p.strip()]


def _descargar(url, langs, carpeta, automaticos):
    """Una pasada de yt-dlp. Devuelve (info, lista de .vtt encontrados)."""
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise ErrorTranscripcion(
            "Falta el motor de descarga (yt-dlp).\n"
            "Instálalo con: pip install yt-dlp"
        ) from exc

    opciones = {
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "writesubtitles": not automaticos,
        "writeautomaticsub": automaticos,
        "subtitleslangs": [x.strip() for x in langs.split(",") if x.strip()],
        "subtitlesformat": "vtt",
        "outtmpl": str(carpeta / "v"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }

    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as fallo:
        # YouTube corta la pasada a medias cuando limita alguna descarga. Si
        # algun subtitulo alcanzo a bajar, sirve igual: se rescatan los
        # metadatos con una consulta que ya no toca los subtitulos.
        vtts = list(carpeta.glob("*.vtt"))
        if not vtts:
            raise
        sin_subs = {**opciones, "writesubtitles": False, "writeautomaticsub": False}
        try:
            with yt_dlp.YoutubeDL(sin_subs) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            info = None
        if not info:
            # Sin metadatos no hay nota que escribir, y lo que hay que explicar
            # es el fallo de origen, no el del rescate.
            raise fallo from None
        return info, vtts

    return info, list(carpeta.glob("*.vtt"))


def obtener(url: str, langs: str = IDIOMAS_POR_DEFECTO,
            ventana: int = VENTANA_POR_DEFECTO, avisar=None) -> Transcripcion:
    """
    Descarga los subtitulos del video y devuelve la transcripcion ya limpia.

    Prefiere los subtitulos escritos por el autor; solo si no existen recurre a
    los automaticos de YouTube, que traen mas errores de dictado.
    """
    def aviso(texto):
        if avisar:
            avisar(texto)

    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp)

        aviso("Buscando subtítulos del autor…")
        try:
            info, vtts = _descargar(url, langs, carpeta, automaticos=False)
        except ErrorTranscripcion:
            raise
        except Exception as exc:
            raise ErrorTranscripcion(_explicar(exc)) from exc

        origen = "manuales (del autor)"
        preferencias = _preferencias(langs)

        if not vtts:
            # En los automaticos, cualquier idioma distinto del original es una
            # traduccion automatica de YouTube hecha sobre una transcripcion
            # tambien automatica. Se degrada dos veces. Conviene traer el idioma
            # original y dejar que el modelo traduzca, que lo hace mejor y con
            # todo el contexto delante.
            original = (info.get("language") or "").split("-")[0].strip().lower()
            if original:
                aviso(f"No hay subtítulos del autor. Usando los automáticos "
                      f"en el idioma original del video ({original})…")
                # Solo el idioma original: anadir es/en obligaria a YouTube a
                # generar traducciones automaticas, y esas las limita con un
                # HTTP 429 que tumbaba la descarga completa.
                langs_auto = f"{original}-orig,{original}"
                preferencias = _preferencias(langs_auto)
            else:
                aviso("No hay subtítulos del autor. Usando los automáticos…")
                langs_auto = langs

            try:
                info, vtts = _descargar(url, langs_auto, carpeta, automaticos=True)
            except Exception as exc:
                raise ErrorTranscripcion(_explicar(exc)) from exc

            if not vtts and langs_auto != langs:
                # YouTube a veces declara un idioma de audio que no coincide con
                # el de sus propios subtitulos automaticos. Ahi no queda mas que
                # aceptar los idiomas pedidos, aunque sean traducciones.
                aviso("El idioma original no estaba disponible. "
                      "Probando con los idiomas pedidos…")
                preferencias = _preferencias(langs)
                try:
                    info, vtts = _descargar(url, langs, carpeta, automaticos=True)
                except Exception as exc:
                    raise ErrorTranscripcion(_explicar(exc)) from exc

            origen = "automáticos de YouTube"

        if not vtts:
            raise ErrorTranscripcion(
                "El video no tiene subtítulos en los idiomas pedidos.\n\n"
                f"Idiomas buscados: {langs}\n"
                "Prueba con otros idiomas en Opciones, o revisa si el video "
                "realmente tiene subtítulos disponibles."
            )

        # Si bajo varios idiomas, se respeta el orden de preferencia.
        def prioridad(p: Path) -> int:
            codigo = p.stem.split(".")[-1].lower()
            for i, pref in enumerate(preferencias):
                if codigo.startswith(pref):
                    return i
            return 999

        vtt = sorted(vtts, key=prioridad)[0]
        cues = parsear_vtt(vtt.read_text(encoding="utf-8"))
        bloques = agrupar(desduplicar(cues), ventana)

        if not bloques:
            raise ErrorTranscripcion(
                "El archivo de subtítulos vino vacío tras la limpieza."
            )

        fecha = info.get("upload_date") or ""
        if len(fecha) == 8:
            fecha = f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:]}"

        return Transcripcion(
            titulo=info.get("title") or "Video sin título",
            canal=info.get("uploader") or "",
            url=info.get("webpage_url") or url,
            duracion=duracion_legible(info.get("duration")),
            fecha=fecha or "desconocida",
            idioma=vtt.stem.split(".")[-1],
            origen=origen,
            bloques=bloques,
        )


def ruta_ffmpeg() -> str | None:
    """
    Ubica ffmpeg: el que viaja dentro del .exe, o el que haya en el sistema.

    Por encima de 360p YouTube sirve el video y el audio en pistas separadas,
    asi que sin ffmpeg no hay forma de unirlas en un archivo unico.
    """
    empaquetado = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    if (empaquetado / "ffmpeg.exe").is_file() or (empaquetado / "ffmpeg").is_file():
        return str(empaquetado)

    delsistema = shutil.which("ffmpeg")
    if delsistema:
        return str(Path(delsistema).parent)
    return None


def _formato(calidad: str, con_ffmpeg: bool) -> str:
    """Arma el selector de formato de yt-dlp para la calidad pedida."""
    if calidad == CALIDAD_AUDIO:
        return "bestaudio[ext=m4a]/bestaudio"

    if con_ffmpeg:
        # Pista de video y pista de audio por separado, que luego se unen.
        return (f"bestvideo[height<={calidad}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={calidad}]+bestaudio/"
                f"best[height<={calidad}]/best")

    # Sin ffmpeg solo sirven los formatos que ya traen audio y video juntos.
    return f"best[height<={calidad}][ext=mp4]/best[height<={calidad}]/best"


def _ya_descargado(carpeta: Path, nombre: str) -> Path | None:
    """
    Busca un archivo ya bajado con ese nombre.

    Se compara el nombre entero en vez de usar glob porque los titulos de
    YouTube traen corchetes, y glob los interpreta como comodines.
    """
    if not carpeta.is_dir():
        return None
    for hijo in carpeta.iterdir():
        if (hijo.is_file() and hijo.stem == nombre
                and hijo.suffix.lower() not in (".part", ".ytdl")):
            return hijo
    return None


def descargar_video(url: str, carpeta: Path, nombre: str,
                    calidad: str = CALIDAD_POR_DEFECTO, avisar=None) -> Path:
    """
    Baja el video a `carpeta` con el nombre indicado y devuelve su ruta.

    Recibe el nombre desde fuera para que el archivo quede junto a la nota y
    con el mismo titulo, que es lo que permite incrustarlo en Obsidian.
    """
    def aviso(texto):
        if avisar:
            avisar(texto)

    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise ErrorDescarga(
            "Falta el motor de descarga (yt-dlp).\n"
            "Instálalo con: pip install yt-dlp"
        ) from exc

    carpeta.mkdir(parents=True, exist_ok=True)

    # Bajar de nuevo un archivo de cientos de MB por repetir una URL no tiene
    # sentido: si ya esta, se informa y se sigue.
    existente = _ya_descargado(carpeta, nombre)
    if existente:
        aviso(f"El video ya estaba descargado: {existente.name}")
        return existente

    ffmpeg = ruta_ffmpeg()
    solo_audio = calidad == CALIDAD_AUDIO

    if not ffmpeg and not solo_audio:
        aviso("No se encontró ffmpeg: se bajará la mejor calidad que YouTube "
              "entregue con audio y video ya unidos, normalmente 360p.")

    # yt-dlp llama al hook muchas veces por segundo; se avisa cada 25%.
    umbral = [25.0]

    def progreso(estado):
        if estado.get("status") == "finished":
            umbral[0] = 25.0
            return
        if estado.get("status") != "downloading":
            return
        total = estado.get("total_bytes") or estado.get("total_bytes_estimate")
        if not total:
            return
        porcentaje = estado.get("downloaded_bytes", 0) / total * 100
        if porcentaje >= umbral[0]:
            aviso(f"Descargando… {int(umbral[0])}% de {total / 1048576:.1f} MB")
            umbral[0] += 25

    opciones = {
        "format": _formato(calidad, bool(ffmpeg)),
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "outtmpl": str(carpeta / f"{nombre}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [progreso],
    }
    if ffmpeg:
        opciones["ffmpeg_location"] = ffmpeg
        if not solo_audio:
            opciones["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as exc:
        raise ErrorDescarga(_explicar(exc)) from exc

    descargado = _ya_descargado(carpeta, nombre)
    if not descargado:
        raise ErrorDescarga(
            "La descarga terminó pero no quedó ningún archivo en la bóveda.\n"
            "Revisa que haya espacio en disco y permisos de escritura."
        )
    return descargado


def _explicar(exc: Exception) -> str:
    """Traduce los errores mas comunes de yt-dlp a algo accionable."""
    texto = str(exc)
    bajo = texto.lower()

    if "no space left" in bajo or "not enough space" in bajo or "errno 28" in bajo:
        return ("No queda espacio en el disco donde está la bóveda. "
                "Libera espacio o elige una calidad más baja.")
    if "requested format" in bajo or "no video formats" in bajo:
        return ("YouTube no ofrece este video en la calidad pedida. "
                "Prueba con una calidad más baja en Opciones.")
    if "ffmpeg" in bajo or "ffprobe" in bajo:
        return ("Falló la unión de las pistas de video y audio. "
                "Prueba con «solo audio» o con una calidad más baja.")
    if "private" in bajo or "sign in" in bajo:
        return ("El video es privado o exige iniciar sesión, así que no se "
                "pueden leer sus subtítulos.")
    if "unavailable" in bajo or "not available" in bajo:
        return "El video no está disponible (retirado, restringido por región o URL incorrecta)."
    if "is not a valid url" in bajo or "unsupported url" in bajo:
        return "Esa URL no es válida. Pega el enlace completo del video."
    if "429" in bajo or "too many requests" in bajo:
        return ("YouTube limitó las descargas por exceso de solicitudes. "
                "Espera unos minutos y vuelve a intentar.")
    if "certificate" in bajo or "ssl" in bajo:
        return "Falló la conexión segura con YouTube. Revisa tu conexión o antivirus."

    return (
        "No se pudo completar la operación con YouTube.\n\n"
        f"{texto[:500]}\n\n"
        "Si el problema persiste, suele deberse a que YouTube cambió algo y el "
        "motor de descarga quedó desactualizado. Descarga la versión más nueva "
        "de la aplicación."
    )
