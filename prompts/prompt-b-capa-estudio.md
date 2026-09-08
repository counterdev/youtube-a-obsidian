---
title: "Prompt B — Capa de estudio"
tipo: plantilla
uso: "Generar preguntas de recuperación activa y casos a partir de una nota de video"
tags:
  - plantilla
  - prompt
  - estudio
---

# Prompt B — Capa de estudio

> [!info] Cómo se usa
> Se ejecuta **después** de [[Prompt A - Nota base de video]]. Pega la nota ya generada, no la transcripción cruda: es mucho más corta y el resultado sale completo en una sola respuesta.
> Si en la nota base quedaron marcados fragmentos dudosos, revísalos antes de generar el repaso: no conviene memorizar sobre datos inciertos.

---

Eres un diseñador de materiales de estudio. Te entregaré una nota de Obsidian generada a partir de la transcripción de un video.

Tu tarea es crear la capa de repaso de esa nota: preguntas de recuperación activa, casos de aplicación y una lista de comprobación.

Regla base: todo debe apoyarse exclusivamente en el contenido de la nota. No agregues información externa, no completes vacíos con conocimiento general y no formules preguntas cuya respuesta no esté en la nota.

Si la nota incluye una sección de "Problemas de transcripción", no construyas preguntas sobre esos fragmentos dudosos.

## 1. Formato de salida

Entrega el resultado como un archivo `.md` descargable, nombrado `<título de la nota base> — Repaso`.

Usa la raya (—) tanto en el nombre del archivo como en el `title` del frontmatter, para que ambos coincidan y el enlace `[[ ]]` hacia esta nota funcione sin ajustes.

Si no puedes crear archivos en este entorno, entrega todo dentro de un único bloque de código markdown, sin introducciones ni comentarios fuera del bloque.

Comienza con este frontmatter, incluidos los tres guiones de apertura y cierre:

```
---
title: "<título de la nota base> — Repaso"
tipo: repaso
nota-base: "[[<título exacto de la nota base>]]"
fecha-nota: <fecha actual en formato AAAA-MM-DD>
tags:
  - repaso
  - <las mismas etiquetas temáticas de la nota base>
estado: sin-repasar
---
```

## 2. Preguntas de recuperación activa

Genera **una pregunta por cada idea clave** de la nota base, más **3 preguntas de aplicación**. Ese es el total: no lo infles ni lo recortes.

Ordénalas avanzando desde lo básico hacia lo aplicado, con este reparto:

- **Preguntas sobre las ideas clave:** aproximadamente la mitad debe apuntar a recordar y explicar conceptos, y la otra mitad a comparar, relacionar y distinguir causas y consecuencias.
- **Las 3 preguntas finales:** siempre de aplicación del contenido a una situación concreta.

El conteo manda por sobre el reparto. Si el número de ideas clave no permite una mitad exacta, redondea a favor de las preguntas de comparación y relación.

Formato de cada pregunta:

`**P1.** <pregunta>`

`> [!success]- Respuesta`
`> Respuesta razonada, basada solo en la nota. No repitas una definición: explica por qué, cómo o en qué contexto aplica.`

El guion después de `[!success]` es obligatorio: es lo que deja el callout plegado y permite estudiar tapando la respuesta.

Numera de forma correlativa y consistente.

## 3. Casos de aplicación

Incluye entre 2 y 4 casos breves, solo si el contenido permite aplicar los conceptos. Si el video es puramente conceptual o informativo, omite esta sección.

Formato de cada caso:

`### Caso 1 — <título>`

**Situación:** descripción breve del escenario.

**Pregunta:** una pregunta que obligue a decidir, explicar o justificar.

`> [!success]- Resolución`
`> Explicación que use únicamente los criterios entregados por la nota base.`

Cuando el caso sea una elaboración tuya y no aparezca en el video, agrégale:

`> [!note] Caso elaborado`
`> Esta situación fue creada para practicar; no aparece en el video.`

Nunca atribuyas al expositor un caso que inventaste.

## 4. Lista de comprobación

Entre 5 y 10 afirmaciones en formato de casilla (`- [ ]`), adaptadas a los temas reales del video, del tipo:

- Puedo explicar…
- Puedo distinguir…
- Puedo relacionar…
- Puedo aplicar…
- Puedo justificar…

## 5. Reglas generales

- Escribe en español de Chile, con tono claro y directo.
- Las respuestas deben permitir estudiar sin volver a abrir la nota base.
- No formules preguntas ambiguas ni de respuesta sí/no.
- Evita que dos preguntas cubran exactamente el mismo punto.
- Si una sección no corresponde al contenido, omítela en vez de dejarla vacía.

Aquí comienza la nota base:

---

[PEGA AQUÍ LA NOTA GENERADA CON EL PROMPT A]
