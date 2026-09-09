"""Pruebas de regresión sin claves reales ni llamadas pagadas."""

import queue
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import generador
import notavideo_app as app_module
import nucleo
import proveedores


def make_var(value):
    state = [value]
    return SimpleNamespace(get=lambda: state[0], set=lambda value: state.__setitem__(0, value))


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name)
        self.app = object.__new__(app_module.Aplicacion)
        self.app.cfg = {}
        self.app.trabajando = False
        self.app.mensajes = queue.Queue()
        self.app.txt_urls = Mock()
        self.app.txt_urls.get.return_value = "https://www.youtube.com/watch?v=example"
        for name, value in {
            "var_boveda": str(self.vault), "var_modo": "completo",
            "var_proveedor": "OpenAI", "var_url": "https://example.com/v1",
            "var_modelo": "test-model", "var_key": "test-key", "var_workspace": "",
            "var_video": False, "var_calidad": "1080p (recomendada)",
        }.items():
            setattr(self.app, name, make_var(value))
        self.app._prov_actual = "OpenAI"
        self.app.boton = Mock()
        self.app.progreso = {}
        self.transcript = nucleo.Transcripcion(
            "Video de prueba", "Canal", "https://youtube.com/watch?v=example",
            "01:00", "2026-09-09", "es", "manuales (del autor)",
            [(0, "Contenido de prueba."), (45, "Segunda idea.")])

    def start_processing(self):
        with patch.object(app_module, "guardar_config") as save, \
                patch.object(app_module.threading, "Thread") as thread, \
                patch.object(app_module.messagebox, "showwarning") as warning:
            self.app._procesar()
            return save, thread, warning

    def test_process_passes_selected_model_and_custom_url(self):
        save, thread, warning = self.start_processing()
        warning.assert_not_called()
        args = thread.call_args.kwargs["args"]
        self.assertEqual(args[4].base_url, "https://example.com/v1")
        self.assertEqual(args[5], "test-model")
        self.assertEqual(save.call_args.args[0]["claves"]["OpenAI"], "test-key")
        self.assertEqual(save.call_args.args[0]["proveedor"], "OpenAI")
        thread.return_value.start.assert_called_once()

    def test_process_passes_video_options_to_worker(self):
        self.app.var_video.set(True)
        self.app.var_calidad.set("720p")
        _, thread, warning = self.start_processing()
        warning.assert_not_called()
        args = thread.call_args.kwargs["args"]
        self.assertEqual((args[7], args[8]), (True, "720"))
        # Un paso extra por URL: transcripcion, nota, repaso y video.
        self.assertEqual(self.app.progreso["maximum"], 4)

    def test_transcription_does_not_require_ai_settings(self):
        self.app.var_modo.set("transcripcion")
        self.app.var_key.set("")
        self.app.var_modelo.set("")
        self.app.var_url.set("")
        _, thread, warning = self.start_processing()
        warning.assert_not_called()
        thread.return_value.start.assert_called_once()

    def test_empty_vault_is_rejected(self):
        self.app.var_boveda.set("")
        _, thread, warning = self.start_processing()
        warning.assert_called_once()
        thread.assert_not_called()

    def test_invalid_ai_settings_are_rejected(self):
        for field in ("var_key", "var_modelo", "var_url"):
            with self.subTest(field=field):
                var = getattr(self.app, field)
                original = var.get()
                var.set("")
                _, thread, warning = self.start_processing()
                warning.assert_called_once()
                thread.assert_not_called()
                var.set(original)

    def test_ollama_without_key(self):
        self.app.var_proveedor.set("Ollama (en este PC)")
        self.app.var_url.set("http://localhost:11434/v1")
        self.app.var_key.set("")
        _, thread, warning = self.start_processing()
        warning.assert_not_called()
        self.assertEqual(thread.call_args.kwargs["args"][3], "ollama")

    def test_complete_pipeline_writes_three_notes(self):
        with patch.object(nucleo, "obtener", return_value=self.transcript), \
                patch.object(generador, "crear_cliente"), \
                patch.object(generador, "nota_base", return_value=("# Nota de prueba\nContenido", 10, 20)), \
                patch.object(generador, "capa_estudio", return_value=("# Repaso\nPregunta", 5, 10)):
            self.app._trabajar(["url"], self.vault, True, "test-key",
                              proveedores.obtener("OpenAI"), "test-model")
        files = list(self.vault.rglob("*.md"))
        self.assertEqual(len(files), 3)
        self.assertTrue(all(path.read_text(encoding="utf-8").strip() for path in files))
        self.assertIn(("fin", None), list(self.app.mensajes.queue))

    def test_batch_continues_after_download_error(self):
        with patch.object(nucleo, "obtener", side_effect=[
                nucleo.ErrorTranscripcion("Fallo de prueba"), self.transcript]):
            self.app._trabajar(["bad", "good"], self.vault, False, "",
                              proveedores.obtener("OpenAI"), "")
        self.assertEqual(len(list(self.vault.rglob("*.md"))), 1)
        events = list(self.app.mensajes.queue)
        self.assertIn(("progreso", 2), events)
        self.assertTrue(any("Con errores: 1" in str(event) for event in events))
        self.assertEqual(events[-1], ("fin", None))

    def test_client_initialization_failure_releases_ui(self):
        with patch.object(generador, "crear_cliente", side_effect=ValueError("Error de prueba")):
            self.app._trabajar(["url"], self.vault, True, "test-key",
                              proveedores.obtener("OpenAI"), "test-model")
        self.assertEqual(list(self.app.mensajes.queue)[-1], ("fin", None))

    def test_configuration_round_trip(self):
        config_path = self.vault / "config.json"
        with patch.object(app_module, "ruta_config", return_value=config_path):
            self.app.save_settings()
            saved = app_module.cargar_config()
        self.assertEqual(saved["modelos"]["OpenAI"], "test-model")
        self.assertEqual(saved["urls"]["OpenAI"], "https://example.com/v1")
        self.assertNotIn("api_key", saved)


class CoreTests(unittest.TestCase):
    def test_openai_sdk_retries_token_parameter(self):
        try:
            import httpx2 as httpx
        except ImportError:
            import httpx
        import openai

        requests = []

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            if "max_tokens" in body:
                return httpx.Response(400, json={"error": {
                    "message": "Use max_completion_tokens", "type": "invalid_request_error"}})
            return httpx.Response(200, json={
                "id": "test", "object": "chat.completion", "created": 0,
                "model": "test-model", "choices": [{"index": 0,
                    "message": {"role": "assistant", "content": "# Nota\nContenido"},
                    "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

        with openai.OpenAI(api_key="test-key", http_client=httpx.Client(
                transport=httpx.MockTransport(respond))) as client:
            result = generador._llamar_openai(client, proveedores.obtener("OpenAI"),
                                              "test-model", "Sistema", [])
        self.assertEqual(result, ("# Nota\nContenido", 10, 5, False))
        self.assertEqual(len(requests), 2)
        self.assertIn("max_completion_tokens", requests[-1])

    def test_anthropic_stream_with_text_and_usage(self):
        try:
            import httpx2 as httpx
        except ImportError:
            import httpx
        import anthropic

        events = [
            ("message_start", {"type": "message_start", "message": {
                "id": "test", "type": "message", "role": "assistant", "content": [],
                "model": "test-model", "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 0}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0,
                "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0,
                "delta": {"type": "text_delta", "text": "# Nota\nContenido"}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {
                "stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 5}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        payload = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=payload))
        with anthropic.Anthropic(api_key="test-key", http_client=httpx.Client(
                transport=transport)) as client:
            result = generador._llamar_anthropic(client, proveedores.CATALOGO[0],
                                                 "test-model", "Sistema", [])
        self.assertEqual(result, ("# Nota\nContenido", 10, 5, False))

    def test_legacy_model_is_preserved(self):
        config = app_module.migrar_config({"api_key": "test-key", "modelo": "custom-model"})
        self.assertEqual(config["modelos"][proveedores.POR_DEFECTO], "custom-model")
        self.assertEqual(app_module.migrar_config([]), {})

    def test_empty_generation_is_an_error(self):
        with patch.object(generador, "_llamar_openai", return_value=("", 1, 2, False)):
            with self.assertRaises(generador.ErrorGeneracion):
                generador._pedir(Mock(), proveedores.obtener("OpenAI"), "model", "prompt", [])

    def test_continuation_preserves_history_and_usage(self):
        with patch.object(generador, "_llamar_openai", side_effect=[
                ("# Nota\n", 1, 2, True), ("Contenido", 3, 4, False)]) as call:
            text, incoming, outgoing = generador._pedir(
                Mock(), proveedores.obtener("OpenAI"), "model", "prompt",
                [{"role": "user", "content": "transcripción"}])
        self.assertEqual(text, "# Nota\nContenido")
        self.assertEqual((incoming, outgoing), (4, 6))
        self.assertEqual(call.call_args.args[-1][-2]["content"], "# Nota\n")

    def test_subtitles_remove_scroll_and_preserve_timestamps(self):
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHola\n\n00:00:03.000 --> 00:00:05.000\nHola\nMundo\n\n00:00:50.000 --> 00:00:52.000\nOtra idea\n"
        blocks = nucleo.agrupar(nucleo.desduplicar(nucleo.parsear_vtt(vtt)), 45)
        self.assertEqual(blocks, [(1, "Hola Mundo"), (50, "Otra idea")])


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_format_prefers_separate_tracks_when_ffmpeg_is_available(self):
        selector = nucleo._formato("1080", con_ffmpeg=True)
        self.assertIn("bestvideo[height<=1080]", selector)
        self.assertIn("+bestaudio", selector)

    def test_format_falls_back_to_combined_streams_without_ffmpeg(self):
        selector = nucleo._formato("1080", con_ffmpeg=False)
        # Sin ffmpeg no se pueden unir pistas, asi que no debe pedirlas sueltas.
        self.assertNotIn("bestvideo", selector)
        self.assertIn("best[height<=1080]", selector)

    def test_audio_only_ignores_video_streams(self):
        self.assertEqual(nucleo._formato(nucleo.CALIDAD_AUDIO, con_ffmpeg=True),
                         "bestaudio[ext=m4a]/bestaudio")

    def test_partial_downloads_are_not_mistaken_for_finished_files(self):
        (self.folder / "Video.mp4.part").write_text("a", encoding="utf-8")
        self.assertIsNone(nucleo._ya_descargado(self.folder, "Video.mp4"))
        (self.folder / "Video.mp4").write_text("a", encoding="utf-8")
        self.assertEqual(nucleo._ya_descargado(self.folder, "Video").name,
                         "Video.mp4")

    def test_titles_with_brackets_are_found_literally(self):
        # Los corchetes son comodines para glob: el nombre se compara entero.
        (self.folder / "Charla [2026].mp4").write_text("a", encoding="utf-8")
        encontrado = nucleo._ya_descargado(self.folder, "Charla [2026]")
        self.assertEqual(encontrado.name, "Charla [2026].mp4")

    def test_existing_video_is_not_downloaded_again(self):
        (self.folder / "Charla.mp4").write_text("a", encoding="utf-8")
        with patch.dict("sys.modules", {"yt_dlp": Mock()}) as modules:
            resultado = nucleo.descargar_video(
                "https://youtu.be/x", self.folder, "Charla")
            modules["yt_dlp"].YoutubeDL.assert_not_called()
        self.assertEqual(resultado.name, "Charla.mp4")

    def test_download_sends_ffmpeg_location_and_merge_format(self):
        capturado = {}

        class FalsoYoutubeDL:
            def __init__(self, opciones):
                capturado.update(opciones)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def extract_info(self_inner, url, download):
                destino = Path(capturado["outtmpl"].replace("%(ext)s", "mp4"))
                destino.write_text("video", encoding="utf-8")
                return {}

        falso = Mock()
        falso.YoutubeDL = FalsoYoutubeDL
        with patch.dict("sys.modules", {"yt_dlp": falso}),                 patch.object(nucleo, "ruta_ffmpeg", return_value="C:/ffmpeg"):
            resultado = nucleo.descargar_video(
                "https://youtu.be/x", self.folder, "Charla", "720")

        self.assertEqual(capturado["ffmpeg_location"], "C:/ffmpeg")
        self.assertEqual(capturado["merge_output_format"], "mp4")
        self.assertTrue(capturado["noplaylist"])
        self.assertEqual(resultado.name, "Charla.mp4")

    def test_audio_only_does_not_request_a_merge(self):
        capturado = {}

        class FalsoYoutubeDL:
            def __init__(self, opciones):
                capturado.update(opciones)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def extract_info(self_inner, url, download):
                Path(capturado["outtmpl"].replace("%(ext)s", "m4a")).write_text(
                    "audio", encoding="utf-8")
                return {}

        falso = Mock()
        falso.YoutubeDL = FalsoYoutubeDL
        with patch.dict("sys.modules", {"yt_dlp": falso}),                 patch.object(nucleo, "ruta_ffmpeg", return_value="C:/ffmpeg"):
            resultado = nucleo.descargar_video(
                "https://youtu.be/x", self.folder, "Charla", nucleo.CALIDAD_AUDIO)

        self.assertNotIn("merge_output_format", capturado)
        self.assertEqual(resultado.name, "Charla.m4a")

    def test_download_that_leaves_no_file_is_reported(self):
        falso = Mock()
        falso.YoutubeDL.return_value.__enter__ = lambda self_inner: self_inner
        falso.YoutubeDL.return_value.__exit__ = lambda *_: False
        with patch.dict("sys.modules", {"yt_dlp": falso}):
            with self.assertRaises(nucleo.ErrorDescarga):
                nucleo.descargar_video("https://youtu.be/x", self.folder, "Charla")

    def test_disk_full_is_explained_before_the_generic_message(self):
        mensaje = nucleo._explicar(OSError("No space left on device"))
        self.assertIn("espacio en el disco", mensaje)

    def test_unavailable_quality_is_explained(self):
        mensaje = nucleo._explicar(Exception("Requested format is not available"))
        self.assertIn("calidad", mensaje)


if __name__ == "__main__":
    unittest.main()
