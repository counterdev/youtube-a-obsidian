# NotaVideo — de YouTube a Obsidian

Pega la URL de un video de YouTube y obtén, en tu bóveda de Obsidian, la
transcripción limpia con marcas de tiempo, una nota de estudio estructurada y una
capa de repaso con preguntas de recuperación activa.

App de escritorio para Windows, en un `.exe` único sin instalación.

---

## Qué hace

Por cada video genera hasta tres archivos:

| Archivo | Carpeta | Contenido |
|---|---|---|
| `<título> — transcripcion.md` | `Videos/Transcripciones/` | Transcripción limpia, en bloques de 45 s con marca de tiempo real |
| `<título>.md` | `Videos/` | Nota base: idea central, ideas clave, conceptos enlazados, datos, limitaciones del contenido |
| `<título> — Repaso.md` | `Videos/Repasos/` | Preguntas de recuperación activa con respuesta plegada, casos de aplicación y lista de comprobación |

Las notas usan enlaces internos `[[ ]]`, callouts de Obsidian y frontmatter con
etiquetas, así que se integran al grafo desde el primer momento.

## Dos modos

**Solo transcripción** — gratis, sin cuentas ni claves. Baja los subtítulos, los
limpia y los deja en la bóveda. Sirve tal cual para pegar en cualquier chat.

**Notas completas** — genera además la nota base y el repaso llamando a la API de
Claude. Necesita una API key de Anthropic, que consigues en
[console.anthropic.com](https://console.anthropic.com/settings/keys), **creada dentro
de un espacio de trabajo**: una clave de organización exige además el ID del
workspace, que se pega en el campo correspondiente.

Es de pago por uso. Medido sobre una charla TED de 16 minutos con 2.455 palabras de
transcripción: **US$ 0,43 con Opus 5**, contando las dos llamadas. Da del orden de
US$ 0,03 por minuto de video; Sonnet 5 cuesta alrededor de la mitad. La app informa
el gasto real de cada tanda al terminar.

Tu clave se guarda solo en tu equipo, en `%APPDATA%\NotaVideo\config.json`, y no
se envía a ningún sitio salvo a la API de Anthropic.

## Instalación

**Opción rápida:** descarga `NotaVideo.exe` desde
[Releases](https://github.com/counterdev/youtube-a-obsidian/releases) y ábrelo.
No requiere Python ni instalación.

**Desde el código:**

```
git clone https://github.com/counterdev/youtube-a-obsidian
cd youtube-a-obsidian
iniciar.bat
```

`iniciar.bat` crea el entorno virtual, instala las dependencias y abre la app.
Para generar el ejecutable, `construir-exe.bat`.

## Uso

1. Pega una o varias URLs, una por línea.
2. Elige la carpeta de tu bóveda de Obsidian.
3. Elige el modo y presiona **Procesar**.

## Los prompts se pueden editar

La estructura de las notas la definen dos plantillas incluidas en `prompts/`:

- **Prompt A** convierte la transcripción en la nota base.
- **Prompt B** convierte esa nota en la capa de estudio.

El botón **Copiar plantillas a la bóveda** las deja en `Plantillas/` dentro de tu
bóveda. Si están ahí, la app usa tu versión en vez de la incluida, así que puedes
adaptarlas desde Obsidian —cambiar secciones, el idioma, el número de preguntas—
sin tocar el programa.

El diseño en dos etapas es deliberado: la capa de estudio se genera a partir de la
nota base, no de la transcripción. La nota es mucho más corta y ya viene depurada,
así que el repaso sale completo y no arrastra los errores del dictado.

## Detalles que importan

**Subtítulos del autor antes que automáticos.** La app pide primero los subtítulos
escritos por el autor y solo recurre a los automáticos si no existen. La mayoría de
las herramientas piden ambos a la vez y no distinguen cuál obtuvieron; aquí queda
registrado en el frontmatter, porque cambia cuánto puedes confiar en el texto.

**Limpieza del efecto scroll.** Los subtítulos automáticos de YouTube repiten en
cada bloque parte del anterior y traen una etiqueta por palabra. Sin limpiar, eso
multiplica el texto y degrada el resultado. Medido sobre un archivo real: 14.807 →
1.254 caracteres, un 92 % menos, sin perder contenido.

**Marcas de tiempo reales.** Los timestamps salen del archivo de subtítulos, nunca
los inventa el modelo. Si un video no los trae, las notas simplemente no los
incluyen.

**Videos en otro idioma.** Las notas salen siempre en español, aunque el video esté
en inglés: la transcripción cruda conserva el idioma original y la traducción ocurre
al redactar la nota. Cuando no hay subtítulos del autor, la app pide los automáticos
**en el idioma original del video**, no en español. Puede parecer al revés, pero las
pistas en español que YouTube ofrece para un video en inglés son una traducción
automática hecha sobre una transcripción también automática: se degrada dos veces.
Traducir a partir del original, con el contexto completo delante, da un resultado
bastante mejor.

## Limitaciones

- Solo videos que tengan subtítulos, propios o automáticos. No transcribe audio.
- Windows. El código es multiplataforma, pero el `.exe` y los `.bat` no.
- YouTube cambia su sitio a menudo y el motor de descarga queda desactualizado. Si
  algo deja de funcionar, descarga la versión más reciente del `.exe`; desde el
  código, basta con `pip install -U yt-dlp`.
- La desduplicación descarta una línea repetida dentro de las 8 anteriores. En
  contenido hablado es lo correcto; en un video con estribillos puede comerse una
  repetición legítima.

## Licencia

MIT.
