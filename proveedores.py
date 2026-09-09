"""
Catalogo de proveedores de IA.

La aplicacion habla dos dialectos: el propio de Anthropic y el de OpenAI, que
casi toda la industria adopto como estandar. Con esos dos basta para conectar
cualquier servicio: los presets de aqui abajo solo rellenan la URL y sugieren
modelos, pero el usuario puede escribir los suyos.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Proveedor:
    nombre: str
    dialecto: str            # "anthropic" o "openai"
    base_url: str = ""       # vacia en Anthropic: la pone su propio SDK
    modelos: tuple[str, ...] = ()
    max_tokens: int = 8192
    url_claves: str = ""
    # Dolares por millon de tokens (entrada, salida). Vacio = no se estima gasto.
    precios: dict[str, tuple[float, float]] = field(default_factory=dict)
    nota: str = ""

    @property
    def editable(self) -> bool:
        """Si el usuario puede cambiarle la URL base."""
        return self.dialecto == "openai"


# El orden es el del desplegable. Los nombres de modelo son sugerencias: cada
# proveedor publica los suyos y los renueva, por eso el campo es escribible.
CATALOGO: tuple[Proveedor, ...] = (
    Proveedor(
        nombre="Anthropic (Claude)",
        dialecto="anthropic",
        modelos=("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"),
        max_tokens=64000,
        url_claves="https://console.anthropic.com/settings/keys",
        precios={
            "claude-opus-5": (5.00, 25.00),
            "claude-sonnet-5": (2.00, 10.00),
            "claude-haiku-4-5": (1.00, 5.00),
        },
    ),
    Proveedor(
        nombre="OpenAI",
        dialecto="openai",
        base_url="https://api.openai.com/v1",
        modelos=("gpt-4o", "gpt-4o-mini"),
        max_tokens=16384,
        url_claves="https://platform.openai.com/api-keys",
    ),
    Proveedor(
        nombre="DeepSeek",
        dialecto="openai",
        base_url="https://api.deepseek.com",
        modelos=("deepseek-chat", "deepseek-reasoner"),
        max_tokens=8192,
        url_claves="https://platform.deepseek.com/api_keys",
    ),
    Proveedor(
        nombre="Google (Gemini)",
        dialecto="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        modelos=("gemini-2.0-flash", "gemini-1.5-pro"),
        max_tokens=8192,
        url_claves="https://aistudio.google.com/apikey",
    ),
    Proveedor(
        nombre="Groq",
        dialecto="openai",
        base_url="https://api.groq.com/openai/v1",
        modelos=("llama-3.3-70b-versatile",),
        max_tokens=8192,
        url_claves="https://console.groq.com/keys",
    ),
    Proveedor(
        nombre="Mistral",
        dialecto="openai",
        base_url="https://api.mistral.ai/v1",
        modelos=("mistral-large-latest", "mistral-small-latest"),
        max_tokens=8192,
        url_claves="https://console.mistral.ai/api-keys",
    ),
    Proveedor(
        nombre="xAI (Grok)",
        dialecto="openai",
        base_url="https://api.x.ai/v1",
        modelos=("grok-3", "grok-2-latest"),
        max_tokens=8192,
        url_claves="https://console.x.ai",
    ),
    Proveedor(
        nombre="OpenRouter (varios)",
        dialecto="openai",
        base_url="https://openrouter.ai/api/v1",
        modelos=("anthropic/claude-sonnet-4.5", "deepseek/deepseek-chat"),
        max_tokens=8192,
        url_claves="https://openrouter.ai/keys",
        nota="Un solo saldo para modelos de muchas empresas.",
    ),
    Proveedor(
        nombre="Ollama (en este PC)",
        dialecto="openai",
        base_url="http://localhost:11434/v1",
        modelos=("llama3.1", "qwen2.5"),
        max_tokens=8192,
        url_claves="https://ollama.com/download",
        nota="Gratis y sin conexión. La API key puede ser cualquier texto.",
    ),
    Proveedor(
        nombre="Otro (compatible con OpenAI)",
        dialecto="openai",
        base_url="",
        modelos=(),
        max_tokens=8192,
        nota="Pega la URL base que indique tu proveedor.",
    ),
)

POR_NOMBRE = {p.nombre: p for p in CATALOGO}
POR_DEFECTO = CATALOGO[0].nombre


def obtener(nombre: str) -> Proveedor:
    """Devuelve el proveedor guardado, o el primero si ya no existe ese nombre."""
    return POR_NOMBRE.get(nombre, CATALOGO[0])
