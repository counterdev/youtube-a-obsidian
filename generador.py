"""
Generacion de las notas con la API de Claude.

Aplica el Prompt A sobre la transcripcion (nota base) y el Prompt B sobre esa
nota (capa de estudio). Este modulo solo se usa cuando hay una API key
configurada: sin ella la aplicacion funciona igual, pero solo transcribe.
"""

from __future__ import annotations

import re
from datetime import date

# Modelos ofrecidos. Ambos admiten pensamiento adaptativo y niveles de esfuerzo.
MODELOS = {
    "Claude Opus 5 — mejor calidad": "claude-opus-5",
    "Claude Sonnet 5 — más económico": "claude-sonnet-5",
}
MODELO_POR_DEFECTO = "claude-opus-5"

# Dolares por millon de tokens, para estimar lo que costo cada video.
PRECIOS = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
}

MAX_TOKENS = 64000
MAX_CONTINUACIONES = 3

# Se anexa a cada prompt para adaptarlo a esta aplicacion: aqui el modelo no
# entrega archivos descargables, escribe el markdown y la app lo guarda.
AJUSTE_ENTORNO = """

---

## Ajustes de esta aplicación

Responde ÚNICAMENTE con el contenido del archivo markdown, empezando por los tres
guiones del frontmatter. Sin bloque de código envolvente, sin introducción, sin
comentarios finales y sin preguntas: lo que escribas se guarda tal cual en la bóveda.
"""

AJUSTE_A = """
Los datos del video vienen en el frontmatter de la transcripción. Úsalos en vez de
dejar campos vacíos: `url`, `fecha-video` y `source` (desde `canal`), y la duración
para la ficha rápida. El título sale de `titulo`.

La transcripción trae marcas de tiempo reales en formato [MM:SS]. Consérvalas en las
ideas clave y en la estructura del video, y nunca inventes una que no esté en el texto.

La regla de continuación por respuesta larga no aplica: dispones de espacio suficiente,
así que entrega la nota completa y no escribas el marcador CONTINÚA DESDE.

Si la transcripción viene en otro idioma —el campo `idioma_subs` del frontmatter lo
indica—, la nota se escribe igualmente en español de Chile: traduce el contenido al
redactarla. Traducir no es interpretar, así que la regla de fidelidad sigue mandando:
no completes lo que el video no dice ni resuelvas ambigüedades a tu favor. Conserva en
su idioma original los nombres propios, los títulos de obras y los términos técnicos
sin equivalente asentado, con la traducción entre paréntesis la primera vez si ayuda.
Si una frase resulta ambigua al traducirla, regístrala en «Problemas de transcripción».
"""

AJUSTE_B = """
Cuenta las ideas clave que realmente trae la nota base y genera una pregunta por cada
una, más las 3 de aplicación. El conteo manda.
"""


class ErrorGeneracion(Exception):
    """Falla al generar las notas, con un mensaje pensado para el usuario."""


def extraer_prompt(texto: str) -> str:
    """
    Saca el prompt puro de la plantilla de Obsidian.

    Las plantillas traen frontmatter y un callout con instrucciones de uso al
    principio, y el marcador «[PEGA AQUÍ…]» al final. Nada de eso debe llegar al
    modelo: el contenido va aparte, como mensaje del usuario.
    """
    inicio = re.search(r"^Eres .+$", texto, re.MULTILINE)
    if inicio:
        texto = texto[inicio.start():]

    fin = re.search(r"^Aquí comienza .+$", texto, re.MULTILINE)
    if fin:
        texto = texto[:fin.start()]

    return texto.strip()


def crear_cliente(api_key: str, workspace_id: str = ""):
    try:
        import anthropic
    except ImportError as exc:
        raise ErrorGeneracion(
            "Falta la librería de Claude.\nInstálala con: pip install anthropic"
        ) from exc

    if not api_key or not api_key.strip():
        raise ErrorGeneracion("No hay API key configurada.")

    # Las claves de organizacion no estan asociadas a un espacio de trabajo, y la
    # API exige que cada peticion diga a cual cargar el uso.
    cabeceras = {}
    if workspace_id and workspace_id.strip():
        cabeceras["anthropic-workspace-id"] = workspace_id.strip()

    return anthropic.Anthropic(api_key=api_key.strip(),
                               default_headers=cabeceras or None)


def _pedir(cliente, modelo, sistema, mensajes, avisar=None):
    """
    Una llamada con streaming, continuando sola si la respuesta topa el límite.

    Devuelve (texto, tokens_entrada, tokens_salida).
    """
    import anthropic

    partes: list[str] = []
    entrada = salida = 0
    historial = list(mensajes)

    for intento in range(MAX_CONTINUACIONES + 1):
        try:
            with cliente.messages.stream(
                model=modelo,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=[{
                    "type": "text",
                    "text": sistema,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=historial,
            ) as flujo:
                respuesta = flujo.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise ErrorGeneracion(
                "La API key no es válida. Revísala en Opciones."
            ) from exc
        except anthropic.PermissionDeniedError as exc:
            raise ErrorGeneracion(
                "La API key no tiene permiso para usar este modelo."
            ) from exc
        except anthropic.NotFoundError as exc:
            raise ErrorGeneracion(f"El modelo {modelo} no está disponible.") from exc
        except anthropic.RateLimitError as exc:
            raise ErrorGeneracion(
                "Alcanzaste el límite de uso de la API. Espera un momento "
                "y vuelve a intentar."
            ) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ErrorGeneracion(
                    "La API de Claude tuvo un problema temporal. Intenta de nuevo."
                ) from exc
            if "workspace" in str(exc).lower():
                raise ErrorGeneracion(
                    "Tu API key es de organización y no está asignada a un espacio "
                    "de trabajo, así que la API no sabe a cuál cargar el uso.\n\n"
                    "Dos salidas:\n"
                    "· Pega el ID del espacio de trabajo en el campo «Workspace ID» "
                    "(está en la URL de console.anthropic.com al abrirlo, y empieza "
                    "con wrkspc_).\n"
                    "· O crea una API key nueva dentro de un espacio de trabajo, y "
                    "deja ese campo vacío."
                ) from exc
            raise ErrorGeneracion(f"Error de la API: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ErrorGeneracion(
                "No hay conexión con la API de Claude. Revisa tu internet."
            ) from exc

        entrada += respuesta.usage.input_tokens
        salida += respuesta.usage.output_tokens

        texto = "".join(b.text for b in respuesta.content if b.type == "text")
        partes.append(texto)

        if respuesta.stop_reason != "max_tokens":
            break

        if intento == MAX_CONTINUACIONES:
            raise ErrorGeneracion(
                "La nota resultó demasiado extensa para completarse. "
                "Prueba con un video más corto."
            )

        if avisar:
            avisar("La nota es larga: pidiendo la continuación…")

        historial = historial + [
            {"role": "assistant", "content": texto},
            {"role": "user", "content":
                "Continúa exactamente desde donde te quedaste. No repitas nada "
                "de lo ya escrito ni añadas comentarios: solo el resto del archivo."},
        ]

    return _desenvolver("".join(partes)), entrada, salida


def _desenvolver(texto: str) -> str:
    """Quita el bloque de código si el modelo envolvió el markdown de todos modos."""
    texto = texto.strip()
    cerca = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", texto, re.DOTALL)
    if cerca:
        return cerca.group(1).strip()
    return texto


def costo(modelo: str, entrada: int, salida: int) -> float:
    precio_in, precio_out = PRECIOS.get(modelo, (0.0, 0.0))
    return entrada / 1_000_000 * precio_in + salida / 1_000_000 * precio_out


def nota_base(cliente, modelo, prompt_a, transcripcion_md, avisar=None):
    """Aplica el Prompt A sobre la transcripción y devuelve el markdown de la nota."""
    sistema = (
        extraer_prompt(prompt_a)
        + AJUSTE_ENTORNO
        + AJUSTE_A
        + f"\n\nLa fecha de hoy es {date.today().isoformat()}."
    )
    mensajes = [{
        "role": "user",
        "content": "Aquí comienza la transcripción:\n\n---\n\n" + transcripcion_md,
    }]
    return _pedir(cliente, modelo, sistema, mensajes, avisar)


def capa_estudio(cliente, modelo, prompt_b, nota_md, avisar=None):
    """Aplica el Prompt B sobre la nota base y devuelve el markdown del repaso."""
    sistema = (
        extraer_prompt(prompt_b)
        + AJUSTE_ENTORNO
        + AJUSTE_B
        + f"\n\nLa fecha de hoy es {date.today().isoformat()}."
    )
    mensajes = [{
        "role": "user",
        "content": "Aquí comienza la nota base:\n\n---\n\n" + nota_md,
    }]
    return _pedir(cliente, modelo, sistema, mensajes, avisar)


def titulo_de(markdown: str, respaldo: str) -> str:
    """Lee el `title:` del frontmatter para nombrar el archivo."""
    m = re.search(r'^title:\s*"?(.+?)"?\s*$', markdown, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return respaldo
