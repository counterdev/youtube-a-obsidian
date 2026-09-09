"""
NotaVideo — de un video de YouTube a notas de Obsidian.

Pega una o varias URLs, elige la boveda y la aplicacion deja la transcripcion
limpia y, si hay API key configurada, la nota base y la capa de estudio.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
import webbrowser
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

import generador
import nucleo
import proveedores

APP = "NotaVideo"
VERSION = "1.2.1"
REPO = "https://github.com/counterdev/youtube-a-obsidian"

CARPETA_NOTAS = "Videos"
CARPETA_REPASOS = "Videos/Repasos"
CARPETA_TRANSCRIPCIONES = "Videos/Transcripciones"
CARPETA_PLANTILLAS = "Plantillas"

NOMBRE_PROMPT_A = "Prompt A - Nota base de video.md"
NOMBRE_PROMPT_B = "Prompt B - Capa de estudio.md"


def ruta_config() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP / "config.json"


def ruta_recurso(relativa: str) -> Path:
    """Ubica un archivo incluido en el paquete, tanto en .exe como en desarrollo."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / relativa


# Antes del soporte multi-proveedor el modelo se guardaba por su nombre visible.
MODELOS_ANTIGUOS = {
    "Claude Opus 5 — mejor calidad": "claude-opus-5",
    "Claude Sonnet 5 — más económico": "claude-sonnet-5",
}


def cargar_config() -> dict:
    try:
        cfg = json.loads(ruta_config().read_text(encoding="utf-8"))
    except Exception:
        return {}
    return migrar_config(cfg)


def migrar_config(cfg: dict) -> dict:
    """Adapta la configuracion de versiones anteriores, que solo hablaban con Claude."""
    if not isinstance(cfg, dict):
        return {}
    if not cfg or "claves" in cfg:
        return cfg

    anthropic = proveedores.CATALOGO[0].nombre
    cfg.setdefault("proveedor", anthropic)
    cfg["claves"] = {anthropic: cfg.get("api_key", "")}
    cfg["modelos"] = {anthropic: MODELOS_ANTIGUOS.get(cfg.get("modelo", ""),
                                      cfg.get("modelo") or "claude-sonnet-5")}
    cfg["urls"] = {}
    cfg["modelo"] = cfg["modelos"][anthropic]
    return cfg


def guardar_config(datos: dict) -> None:
    try:
        destino = ruta_config()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(datos, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    except Exception:
        pass  # Que no se pueda guardar la config no debe romper la aplicacion.


def leer_prompt(boveda: Path, nombre: str, respaldo: str) -> str:
    """
    Usa la plantilla de la boveda si el usuario la tiene, y si no la incluida.

    Asi cualquiera puede editar los prompts desde Obsidian sin tocar el programa.
    """
    propia = boveda / CARPETA_PLANTILLAS / nombre
    if propia.is_file():
        return propia.read_text(encoding="utf-8")
    return ruta_recurso(respaldo).read_text(encoding="utf-8")


class Aplicacion(ttk.Frame):
    def __init__(self, raiz: tk.Tk):
        super().__init__(raiz, padding=16)
        self.raiz = raiz
        self.grid(sticky="nsew")
        raiz.columnconfigure(0, weight=1)
        raiz.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.cfg = cargar_config()
        self.mensajes: queue.Queue = queue.Queue()
        self.trabajando = False

        self._construir()
        self._revisar_cola()
        raiz.protocol("WM_DELETE_WINDOW", self.close_app)

    def save_settings(self) -> None:
        self._recordar_proveedor()
        self.cfg.update({
            "proveedor": self.var_proveedor.get(),
            "boveda": self.var_boveda.get().strip(),
            "modo": self.var_modo.get(),
            "workspace_id": self.var_workspace.get().strip(),
        })
        self.cfg.pop("api_key", None)
        guardar_config(self.cfg)

    def close_app(self) -> None:
        if self.trabajando and not messagebox.askyesno(
                APP, "Hay un procesamiento en curso. ¿Quieres cerrar y detenerlo?"):
            return
        self.save_settings()
        self.raiz.destroy()

    # ------------------------------------------------------------------ interfaz

    def _construir(self) -> None:
        fila = 0

        ttk.Label(self, text="Videos de YouTube",
                  font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w")
        fila += 1
        ttk.Label(self, text="Una URL por línea. Se procesan en orden.",
                  foreground="#666").grid(row=fila, column=0, sticky="w", pady=(0, 4))
        fila += 1

        marco_url = ttk.Frame(self)
        marco_url.grid(row=fila, column=0, sticky="ew")
        marco_url.columnconfigure(0, weight=1)
        self.txt_urls = tk.Text(marco_url, height=4, wrap="none", font=("Consolas", 9))
        self.txt_urls.grid(row=0, column=0, sticky="ew")
        barra = ttk.Scrollbar(marco_url, orient="vertical",
                              command=self.txt_urls.yview)
        barra.grid(row=0, column=1, sticky="ns")
        self.txt_urls.configure(yscrollcommand=barra.set)
        fila += 1

        # --- boveda
        ttk.Label(self, text="Bóveda de Obsidian",
                  font=("Segoe UI", 10, "bold")).grid(row=fila, column=0,
                                                      sticky="w", pady=(14, 4))
        fila += 1
        marco_b = ttk.Frame(self)
        marco_b.grid(row=fila, column=0, sticky="ew")
        marco_b.columnconfigure(0, weight=1)
        self.var_boveda = tk.StringVar(value=self.cfg.get("boveda", ""))
        ttk.Entry(marco_b, textvariable=self.var_boveda).grid(row=0, column=0,
                                                              sticky="ew")
        ttk.Button(marco_b, text="Examinar…", command=self._elegir_boveda,
                   width=12).grid(row=0, column=1, padx=(6, 0))
        fila += 1

        # --- modo
        ttk.Label(self, text="Qué generar",
                  font=("Segoe UI", 10, "bold")).grid(row=fila, column=0,
                                                      sticky="w", pady=(14, 4))
        fila += 1
        self.var_modo = tk.StringVar(value=self.cfg.get("modo", "completo"))
        marco_m = ttk.Frame(self)
        marco_m.grid(row=fila, column=0, sticky="ew")
        ttk.Radiobutton(marco_m, text="Notas completas (necesita API key)",
                        variable=self.var_modo, value="completo",
                        command=self._alternar_modo).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(marco_m, text="Solo transcripción (gratis)",
                        variable=self.var_modo, value="transcripcion",
                        command=self._alternar_modo).grid(row=1, column=0, sticky="w")
        fila += 1

        # --- ajustes de IA
        self.marco_ia = ttk.LabelFrame(self, text=" Proveedor de IA ", padding=10)
        self.marco_ia.grid(row=fila, column=0, sticky="ew", pady=(12, 0))
        self.marco_ia.columnconfigure(1, weight=1)

        ttk.Label(self.marco_ia, text="Proveedor:").grid(row=0, column=0, sticky="w")
        self.var_proveedor = tk.StringVar(
            value=self.cfg.get("proveedor", proveedores.POR_DEFECTO))
        self.combo_prov = ttk.Combobox(
            self.marco_ia, textvariable=self.var_proveedor, state="readonly",
            values=[p.nombre for p in proveedores.CATALOGO])
        self.combo_prov.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(6, 0))
        self.combo_prov.bind("<<ComboboxSelected>>", self._cambiar_proveedor)

        ttk.Label(self.marco_ia, text="URL base:").grid(row=1, column=0, sticky="w",
                                                        pady=(8, 0))
        self.var_url = tk.StringVar(value=self.cfg.get("base_url", ""))
        self.entrada_url = ttk.Entry(self.marco_ia, textvariable=self.var_url)
        self.entrada_url.grid(row=1, column=1, columnspan=2, sticky="ew",
                              padx=(6, 0), pady=(8, 0))

        ttk.Label(self.marco_ia, text="API key:").grid(row=2, column=0, sticky="w",
                                                       pady=(8, 0))
        self.var_key = tk.StringVar()
        self.entrada_key = ttk.Entry(self.marco_ia, textvariable=self.var_key,
                                     show="•")
        self.entrada_key.grid(row=2, column=1, sticky="ew", padx=(6, 6), pady=(8, 0))
        self.var_ver = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.marco_ia, text="Ver", variable=self.var_ver,
                        command=self._alternar_key).grid(row=2, column=2, pady=(8, 0))

        ttk.Label(self.marco_ia, text="Modelo:").grid(row=3, column=0, sticky="w",
                                                      pady=(8, 0))
        self.var_modelo = tk.StringVar(value=self.cfg.get("modelo", ""))
        # Escribible a proposito: cada proveedor renombra sus modelos a su ritmo
        # y una lista cerrada quedaria obsoleta.
        self.combo_modelo = ttk.Combobox(self.marco_ia, textvariable=self.var_modelo)
        self.combo_modelo.grid(row=3, column=1, columnspan=2, sticky="ew",
                               padx=(6, 0), pady=(8, 0))

        # Solo hace falta para claves de organizacion de Anthropic.
        self.fila_workspace = ttk.Frame(self.marco_ia)
        self.fila_workspace.grid(row=4, column=0, columnspan=3, sticky="ew",
                                 pady=(8, 0))
        self.fila_workspace.columnconfigure(1, weight=1)
        ttk.Label(self.fila_workspace, text="Workspace:").grid(row=0, column=0,
                                                               sticky="w")
        self.var_workspace = tk.StringVar(value=self.cfg.get("workspace_id", ""))
        ttk.Entry(self.fila_workspace, textvariable=self.var_workspace).grid(
            row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(self.fila_workspace,
                  text="Opcional: solo si tu clave es de organización (wrkspc_…)",
                  foreground="#666").grid(row=1, column=1, sticky="w", padx=(6, 0))

        self.nota_prov = ttk.Label(self.marco_ia, text="", foreground="#666",
                                   wraplength=430, justify="left")
        self.nota_prov.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.enlace = ttk.Label(self.marco_ia, text="", foreground="#0a58ca",
                                cursor="hand2")
        self.enlace.grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.enlace.bind("<Button-1>", self._abrir_claves)
        fila += 1

        # --- acciones
        marco_a = ttk.Frame(self)
        marco_a.grid(row=fila, column=0, sticky="ew", pady=(14, 0))
        marco_a.columnconfigure(0, weight=1)
        self.boton = ttk.Button(marco_a, text="Procesar", command=self._procesar)
        self.boton.grid(row=0, column=1)
        ttk.Button(marco_a, text="Copiar plantillas a la bóveda",
                   command=self._copiar_plantillas).grid(row=0, column=0, sticky="w")
        fila += 1

        self.progreso = ttk.Progressbar(self, mode="determinate")
        self.progreso.grid(row=fila, column=0, sticky="ew", pady=(10, 0))
        fila += 1

        # --- registro
        marco_l = ttk.Frame(self)
        marco_l.grid(row=fila, column=0, sticky="nsew", pady=(10, 0))
        marco_l.columnconfigure(0, weight=1)
        marco_l.rowconfigure(0, weight=1)
        self.rowconfigure(fila, weight=1)
        self.log = tk.Text(marco_l, height=10, wrap="word", state="disabled",
                           font=("Consolas", 9), background="#1e1e1e",
                           foreground="#d4d4d4", relief="flat", padx=8, pady=6)
        self.log.grid(row=0, column=0, sticky="nsew")
        barra_l = ttk.Scrollbar(marco_l, orient="vertical", command=self.log.yview)
        barra_l.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=barra_l.set)
        self.log.tag_configure("error", foreground="#f48771")
        self.log.tag_configure("ok", foreground="#89d185")
        self.log.tag_configure("aviso", foreground="#dcdcaa")

        self._aplicar_proveedor(limpiar=True)
        self._alternar_modo()
        self._escribir(f"{APP} {VERSION}. Pega una URL y presiona Procesar.")

    def _alternar_key(self) -> None:
        self.entrada_key.configure(show="" if self.var_ver.get() else "•")

    def _alternar_modo(self) -> None:
        estado = "normal" if self.var_modo.get() == "completo" else "disabled"
        for marco in (self.marco_ia, self.fila_workspace):
            for hijo in marco.winfo_children():
                try:
                    hijo.configure(state=estado)
                except tk.TclError:
                    pass
        if estado == "normal":
            self.combo_prov.configure(state="readonly")
            self._aplicar_proveedor()

    def _cambiar_proveedor(self, _evento=None) -> None:
        """Guarda lo escrito para el proveedor anterior y carga el nuevo."""
        self._recordar_proveedor()
        self._aplicar_proveedor(limpiar=True)

    def _recordar_proveedor(self) -> None:
        """Cada proveedor conserva su clave y su URL, para poder alternar."""
        anterior = getattr(self, "_prov_actual", None)
        if not anterior:
            return
        self.cfg.setdefault("claves", {})[anterior] = self.var_key.get().strip()
        self.cfg.setdefault("urls", {})[anterior] = self.var_url.get().strip()
        self.cfg.setdefault("modelos", {})[anterior] = self.var_modelo.get().strip()

    def _aplicar_proveedor(self, limpiar: bool = False) -> None:
        """Deja la interfaz acorde al proveedor elegido."""
        prov = proveedores.obtener(self.var_proveedor.get())
        self._prov_actual = prov.nombre
        self.var_proveedor.set(prov.nombre)

        if limpiar:
            self.var_key.set(self.cfg.get("claves", {}).get(prov.nombre, ""))
            if not self.var_key.get() and prov.dialecto == "anthropic":
                self.var_key.set(os.environ.get("ANTHROPIC_API_KEY", ""))
            self.var_url.set(self.cfg.get("urls", {}).get(prov.nombre)
                             or prov.base_url)
            self.var_modelo.set(self.cfg.get("modelos", {}).get(prov.nombre)
                                or (prov.modelos[0] if prov.modelos else ""))

        self.combo_modelo.configure(values=list(prov.modelos))

        # Anthropic resuelve su propia URL; el resto la necesita explicita.
        self.entrada_url.configure(state="normal" if prov.editable else "disabled")
        if not prov.editable:
            self.var_url.set("")

        if prov.dialecto == "anthropic":
            self.fila_workspace.grid()
        else:
            self.fila_workspace.grid_remove()

        self.nota_prov.configure(text=prov.nota)
        self.enlace.configure(
            text=f"Conseguir una API key de {prov.nombre}" if prov.url_claves else "")

    def _abrir_claves(self, _evento=None) -> None:
        prov = proveedores.obtener(self.var_proveedor.get())
        if prov.url_claves:
            webbrowser.open(prov.url_claves)

    def _elegir_boveda(self) -> None:
        elegida = filedialog.askdirectory(title="Elige la carpeta de tu bóveda")
        if elegida:
            self.var_boveda.set(elegida)

    def _copiar_plantillas(self) -> None:
        boveda = Path(self.var_boveda.get().strip())
        if not self.var_boveda.get().strip() or not boveda.is_dir():
            messagebox.showwarning(APP, "Primero elige una bóveda válida.")
            return
        destino = boveda / CARPETA_PLANTILLAS
        destino.mkdir(parents=True, exist_ok=True)
        for nombre, recurso in ((NOMBRE_PROMPT_A, "prompts/prompt-a-nota-base.md"),
                                (NOMBRE_PROMPT_B, "prompts/prompt-b-capa-estudio.md")):
            if (destino / nombre).exists():
                self._escribir(f"Se conserva la plantilla existente: {nombre}", "aviso")
                continue
            (destino / nombre).write_text(
                ruta_recurso(recurso).read_text(encoding="utf-8"), encoding="utf-8")
        self._escribir(f"Plantillas copiadas a {destino}", "ok")
        self._escribir("Edítalas desde Obsidian: la app usará tu versión.", "aviso")

    # -------------------------------------------------------------------- log

    def _escribir(self, texto: str, etiqueta: str = "") -> None:
        self.log.configure(state="normal")
        self.log.insert("end", texto + "\n", etiqueta)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _revisar_cola(self) -> None:
        try:
            while True:
                tipo, dato = self.mensajes.get_nowait()
                if tipo == "log":
                    self._escribir(*dato)
                elif tipo == "progreso":
                    self.progreso["value"] = dato
                elif tipo == "fin":
                    self.trabajando = False
                    self.boton.configure(state="normal", text="Procesar")
        except queue.Empty:
            pass
        self.raiz.after(120, self._revisar_cola)

    def _avisar(self, texto: str, etiqueta: str = "") -> None:
        self.mensajes.put(("log", (texto, etiqueta)))

    # ---------------------------------------------------------------- proceso

    def _procesar(self) -> None:
        if self.trabajando:
            return

        urls = [l.strip() for l in self.txt_urls.get("1.0", "end").splitlines()
                if l.strip()]
        if not urls:
            messagebox.showwarning(APP, "Pega al menos una URL de YouTube.")
            return

        boveda = Path(self.var_boveda.get().strip())
        if not self.var_boveda.get().strip() or not boveda.is_dir():
            messagebox.showwarning(APP, "Elige la carpeta de tu bóveda de Obsidian.")
            return

        completo = self.var_modo.get() == "completo"
        prov = proveedores.obtener(self.var_proveedor.get())
        if prov.editable:
            prov = replace(prov, base_url=self.var_url.get().strip())
        modelo = self.var_modelo.get().strip()
        clave = self.var_key.get().strip()
        if prov.nombre == "Ollama (en este PC)" and not clave:
            clave = "ollama"
        if completo and not clave:
            messagebox.showwarning(
                APP,
                f"El modo de notas completas necesita una API key de {prov.nombre}.\n\n"
                "Ponla en el campo API key, o cambia a «Solo transcripción».")
            return

        if completo and not modelo:
            messagebox.showwarning(APP, "Escribe el modelo que quieres usar.")
            return
        if completo and prov.editable:
            endpoint = urlparse(prov.base_url)
            if endpoint.scheme not in ("http", "https") or not endpoint.hostname:
                messagebox.showwarning(APP, "Escribe una URL base válida (http:// o https://).")
                return

        self._recordar_proveedor()
        self.cfg.update({
            "proveedor": prov.nombre,
            "boveda": str(boveda),
            "modo": self.var_modo.get(),
            "modelo": self.var_modelo.get(),
            "workspace_id": self.var_workspace.get().strip(),
        })
        self.cfg.pop("api_key", None)
        guardar_config(self.cfg)

        self.trabajando = True
        self.boton.configure(state="disabled", text="Procesando…")
        self.progreso["value"] = 0
        self.progreso["maximum"] = len(urls) * (3 if completo else 1)

        hilo = threading.Thread(
            target=self._trabajar,
            args=(urls, boveda, completo, clave, prov, modelo,
                  self.var_workspace.get().strip()),
            daemon=True)
        hilo.start()

    def _trabajar(self, urls, boveda: Path, completo: bool, clave: str,
                  prov, modelo: str, workspace: str = "") -> None:
        pasos = 0
        failures = 0
        gastado = 0.0
        tokens = 0

        cliente = None
        if completo:
            try:
                cliente = generador.crear_cliente(prov, clave, workspace)
            except Exception as exc:
                self._avisar(str(exc), "error")
                self.mensajes.put(("fin", None))
                return

        for indice, url in enumerate(urls, start=1):
            self._avisar(f"\n[{indice}/{len(urls)}] {url}")
            try:
                # 1. Transcripcion
                trans = nucleo.obtener(url, avisar=lambda t: self._avisar("  " + t))
                carpeta = boveda / CARPETA_TRANSCRIPCIONES
                carpeta.mkdir(parents=True, exist_ok=True)
                nombre = nucleo.limpiar_nombre(trans.titulo)
                (carpeta / f"{nombre} — transcripcion.md").write_text(
                    trans.a_markdown(), encoding="utf-8")

                self._avisar(f"  {trans.titulo}")
                self._avisar(f"  Subtítulos {trans.origen} ({trans.idioma}) · "
                             f"{trans.palabras:,} palabras".replace(",", "."), "ok")
                pasos += 1
                self.mensajes.put(("progreso", pasos))

                if not completo:
                    continue

                if trans.origen.startswith("automáticos"):
                    self._avisar("  Son subtítulos automáticos: revisa después la "
                                 "sección de fragmentos dudosos.", "aviso")

                # 2. Nota base
                self._avisar("  Generando la nota base…")
                prompt_a = leer_prompt(boveda, NOMBRE_PROMPT_A,
                                       "prompts/prompt-a-nota-base.md")
                md_nota, ent, sal = generador.nota_base(
                    cliente, prov, modelo, prompt_a, trans.a_markdown(),
                    avisar=lambda t: self._avisar("  " + t, "aviso"))
                gastado += generador.costo(prov, modelo, ent, sal)
                tokens += ent + sal

                titulo_nota = generador.titulo_de(md_nota, trans.titulo)
                destino_notas = boveda / CARPETA_NOTAS
                destino_notas.mkdir(parents=True, exist_ok=True)
                archivo_nota = destino_notas / f"{nucleo.limpiar_nombre(titulo_nota)}.md"
                archivo_nota.write_text(md_nota, encoding="utf-8")
                self._avisar(f"  Nota base: {archivo_nota.name}", "ok")
                pasos += 1
                self.mensajes.put(("progreso", pasos))

                # 3. Capa de estudio
                self._avisar("  Generando la capa de estudio…")
                prompt_b = leer_prompt(boveda, NOMBRE_PROMPT_B,
                                       "prompts/prompt-b-capa-estudio.md")
                md_repaso, ent, sal = generador.capa_estudio(
                    cliente, prov, modelo, prompt_b, md_nota,
                    avisar=lambda t: self._avisar("  " + t, "aviso"))
                gastado += generador.costo(prov, modelo, ent, sal)
                tokens += ent + sal

                destino_repasos = boveda / CARPETA_REPASOS
                destino_repasos.mkdir(parents=True, exist_ok=True)
                archivo_repaso = (destino_repasos /
                                  f"{nucleo.limpiar_nombre(titulo_nota)} — Repaso.md")
                archivo_repaso.write_text(md_repaso, encoding="utf-8")
                self._avisar(f"  Repaso: {archivo_repaso.name}", "ok")
                pasos += 1
                self.mensajes.put(("progreso", pasos))

            except (nucleo.ErrorTranscripcion, generador.ErrorGeneracion) as exc:
                failures += 1
                self._avisar(f"  {exc}", "error")
            except Exception:
                failures += 1
                self._avisar("  Error inesperado:", "error")
                self._avisar("  " + traceback.format_exc(limit=3), "error")
            finally:
                pasos = indice * (3 if completo else 1)
                self.mensajes.put(("progreso", pasos))

        self._avisar(f"\nTerminados: {len(urls) - failures}. Con errores: {failures}.",
                     "aviso" if failures else "ok")
        if cliente is not None:
            try:
                cliente.close()
            except Exception:
                pass
        if gastado:
            self._avisar(f"Costo aproximado de esta tanda: US$ {gastado:.3f}")
        elif tokens:
            # Sin tabla de precios del proveedor, los tokens son el unico dato
            # honesto que podemos dar.
            self._avisar(f"Tokens usados en esta tanda: {tokens:,}".replace(",", "."))
        self.mensajes.put(("fin", None))


def modo_consola(argv: list[str]) -> int:
    """
    Uso sin ventana, para automatizar:

        NotaVideo.exe --url <URL> --boveda <carpeta> [--log <archivo>]

    Genera solo la transcripción. El resultado se escribe en el archivo de log,
    porque la aplicación se compila sin consola y no puede imprimir en pantalla.
    """
    import argparse

    ap = argparse.ArgumentParser(prog=APP, add_help=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--boveda", required=True)
    ap.add_argument("--langs", default=nucleo.IDIOMAS_POR_DEFECTO)
    ap.add_argument("--log", default=None)
    args = ap.parse_args(argv)

    lineas: list[str] = []

    def registrar(texto: str) -> None:
        lineas.append(texto)
        if sys.stdout:
            print(texto)

    codigo = 0
    try:
        boveda = Path(args.boveda)
        if not boveda.is_dir():
            raise nucleo.ErrorTranscripcion(f"No existe la bóveda: {boveda}")

        trans = nucleo.obtener(args.url, langs=args.langs, avisar=registrar)
        carpeta = boveda / CARPETA_TRANSCRIPCIONES
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"{nucleo.limpiar_nombre(trans.titulo)} — transcripcion.md"
        destino.write_text(trans.a_markdown(), encoding="utf-8")

        registrar(f"OK {trans.titulo}")
        registrar(f"OK subtítulos {trans.origen} ({trans.idioma})")
        registrar(f"OK {trans.palabras} palabras en {len(trans.bloques)} bloques")
        registrar(f"OK {destino}")
    except Exception as exc:
        registrar(f"ERROR {exc}")
        codigo = 1

    if args.log:
        Path(args.log).write_text("\n".join(lineas), encoding="utf-8")
    return codigo


def main() -> None:
    if len(sys.argv) > 1:
        sys.exit(modo_consola(sys.argv[1:]))

    raiz = tk.Tk()
    raiz.title(f"{APP} — de YouTube a Obsidian")
    raiz.geometry("760x720")
    raiz.minsize(640, 600)

    try:
        raiz.iconbitmap(str(ruta_recurso("icono.ico")))
    except Exception:
        pass  # Sin icono la aplicacion funciona igual.

    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass

    Aplicacion(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
