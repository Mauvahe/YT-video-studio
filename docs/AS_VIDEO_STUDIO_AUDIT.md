# AS Video Studio — Auditoría técnica para proveedores intercambiables

> **Tipo de documento:** auditoría de referencia (solo lectura).
> **Fecha:** 27-09-2026.
> **Alcance:** análisis del repositorio antes de transformarlo en una plataforma
> local de generación automatizada de vídeos para YouTube con una arquitectura
> de proveedores de IA intercambiables (interés inicial: Agnes Video 2.5 Flash).
> **Estado:** durante la auditoría no se modificó ningún fichero, no se hizo
> ningún commit y no se abrió ningún pull request. Todo lo que sigue sale de leer
> el código; las referencias van como `fichero:línea`.

---

## Índice

- [0. Resumen ejecutivo](#0-resumen-ejecutivo)
- [A. Arquitectura actual](#a-arquitectura-actual)
- [B. Flujo completo de datos](#b-flujo-completo-de-datos)
- [C. Árbol de componentes relevantes](#c-árbol-de-componentes-relevantes)
- [D. Tabla de proveedores actuales](#d-tabla-de-proveedores-actuales)
- [E. Puntos exactos de integración](#e-puntos-exactos-de-integración)
- [F. Dependencias](#f-dependencias)
- [G. Variables de entorno y configuración](#g-variables-de-entorno-y-configuración)
- [H. Sistema de caché y regeneración](#h-sistema-de-caché-y-regeneración)
- [I. Riesgos técnicos](#i-riesgos-técnicos)
- [J. Qué debemos conservar](#j-qué-debemos-conservar)
- [K. Qué deberíamos modificar posteriormente](#k-qué-deberíamos-modificar-posteriormente)
- [L. Qué NO debemos modificar](#l-qué-no-debemos-modificar)
- [M. Arquitectura propuesta para proveedores intercambiables](#m-arquitectura-propuesta-para-proveedores-intercambiables)
- [N. Plan de implementación en fases pequeñas](#n-plan-de-implementación-en-fases-pequeñas)
- [O. Orden recomendado de las modificaciones](#o-orden-recomendado-de-las-modificaciones)
- [Anexo 1. Incidencias detectadas durante la auditoría](#anexo-1-incidencias-detectadas-durante-la-auditoría)
- [Anexo 2. Cómo se generan guiones, prompts, imágenes, vídeo, voz, subtítulos, música y efectos](#anexo-2-cómo-se-genera-cada-cosa)
- [Anexo 3. Qué es local y qué depende de servicios externos](#anexo-3-qué-es-local-y-qué-depende-de-servicios-externos)

---

## 0. Resumen ejecutivo

1. **Hoy no se genera vídeo con IA.** Cada plano es una **imagen fija**
   (gpt-image-2) sobre la que se mueve una cámara (zoom/recorrido dentro de un
   hyperframe ampliado ×2), con capas SVG (subtítulos, cartelas, mapas,
   cabeceras) y transiciones WebGL. Edge headless lo captura fotograma a
   fotograma por CDP y ffmpeg lo codifica. «Generación de vídeo» sería una
   **capacidad nueva**, no un cambio de proveedor.
2. **La voz marca los tiempos de todo.** El corte en planos se calcula con las
   **marcas de tiempo por palabra** de la voz (`motores/guion/segmentar.py`).
   El orden propuesto (VIDEO antes que VOZ) rompe la base del sistema.
   **Recomendación: mantener la voz antes del storyboard.**
3. **El grafo de 8 pasos es un contrato que no se toca.** Un param «por
   defecto» escrito sin cuidado, o una dependencia nueva, deja obsoletos todos
   los proyectos guardados, y regenerarlos cuesta dinero (~126 imágenes y
   ~4,4 $ por un vídeo de 4 minutos). Los proveedores tienen que entrar **sin
   mover ninguna firma existente**.
4. **Ya existe la semilla de un selector:**
   `p6_assets.PARAMS_POR_DEFECTO["motor_imagen"]` con los valores
   `openai | adoptar` (`pasos/p6_assets.py:132`).
5. **Riesgo concreto de caché:** la clave de caché de cada imagen **no incluye
   el proveedor ni el modelo** (`pasos/p6_assets.py:2948`). Con otro proveedor,
   la caché devolvería imágenes de OpenAI como si fueran suyas.

---

## A. Arquitectura actual

### A.1 Capas

```
web/ (index.html + app.js ~11.000 líneas, sin framework, sin npm)
   │  HTTP / SSE
app.py (FastAPI, ~9.600 líneas, 147 endpoints)  ← orquestador: rutas, recetas, trabajos
   │
   ├── nucleo/     grafo de build: Proyecto, Estado (firmas, versiones), Trabajos, Coste, Bitácora
   ├── pasos/      qué hacer: los 8 pasos + módulos de decisión (prompts, agentes, presets)
   └── motores/    cómo hacerlo: imagen OpenAI, voz Cartesia, segmentar, mapas, movimiento
```

### A.2 Fronteras (documentadas y respetadas en el código)

| Frontera | Qué significa |
|---|---|
| `nucleo/` no sabe de vídeo | Es un DAG genérico con firmas, versiones y obsolescencia derivada. |
| `pasos/` no sabe de HTTP | Cada paso expone `ejecutar(proyecto, params, avisar[, unidades])`. |
| `motores/` no importa código de la aplicación | Se cargan **por ruta** con `medios.motor()` (`pasos/medios.py:128`) o `comun.cargar_motor()` (`pasos/comun.py:38`). Se **recargan en caliente** por mtime y se **congelan** mientras un paso corre. Las claves se leen «por contrato» de `secretos/claves.json`. |
| Aislamiento por proceso | No hay usuarios en el código: un `app.py` por cuenta, con sus variables de entorno, y un login en Node delante (`despliegue/login/`). |

### A.3 El grafo (`nucleo/estado.py:79`)

```
ingesta → brief → guion → voz → revision_audio → assets → callouts → render
```

| id | Depende de | Por unidad |
|---|---|---|
| `ingesta` | — | no |
| `brief` | ingesta | no |
| `guion` | ingesta, brief | no |
| `voz` | guion | no |
| `revision_audio` | voz | no |
| `assets` | guion, voz | **sí** |
| `callouts` | assets | **sí** |
| `render` | callouts | **sí** |

Los ids **no se renombran ni se quitan** (ver `CLAUDE.md`): su firma encadena la
de los pasos de abajo.

---

## B. Flujo completo de datos

### B.1 Paso a paso

| Paso (id fijo) | Qué hace | Entrada → salida | Motor |
|---|---|---|---|
| `ingesta` | Normaliza el texto que escribe el usuario (sin red) | texto → `ingesta.json` (trozos con tiempos a 0) | local |
| `brief` | Traduce la duración a un presupuesto de palabras (determinista, sin modelo) | params → horquilla de palabras (±30 %) | local |
| `guion` | Redacta los bloques del guion | material + brief → `bloques` | **Claude CLI** |
| `voz` | Una sola toma TTS con marcas por palabra | bloques → `narracion.wav` + `palabras[{w,s,e}]` | **Cartesia** |
| `revision_audio` | Aplica comentarios, reescribe los bloques y vuelve a sintetizar la toma entera | comentarios → nueva toma | Claude + Cartesia |
| `assets` (por unidad) | Storyboard completo y generación de imágenes (ver B.2) | plan + imágenes `escenas/S###.png` + hojas de reparto | Claude + **OpenAI** |
| `callouts` (por unidad) | Capa SVG de subtítulos y cartelas, JSON de movimiento, hyperframe ×2 | → `capas/*.svg`, `movimiento/*.json`, `hyper/*.png`, `previo/*.png` | local (Edge rasteriza) |
| `render` (por unidad) | Captura por CDP, un clip por escena, concatenación y mezcla | → `mp4` | Edge + ffmpeg |

### B.2 El «storyboard» ya existe: tareas de la receta dentro de `assets`

Definidas en `pasos/recetas.py:79` (`TAREAS`) y cableadas en `app.py:5470`
(`_que_hace`):

| Orden | Tarea | Qué hace | Motor |
|---|---|---|---|
| 1 | `escenarios` | Catálogo visual: reparto, sitios, tono | Claude (`catalogo_visual`) |
| 2 | `guia_estilo` | Guía de estilo escrita a partir de las referencias | Claude (`estilo`) |
| 3 | `corte` | Segmentación por programación dinámica sobre las marcas de voz | local (`motores/guion/segmentar.py`) |
| 4 | `plan_cartelas` | Qué planos son cartela y qué dicen | Claude (`cartelas`) |
| 5 | `direccion` / `redactor` | Qué se ve en cada plano / el prompt entero del plano | Claude |
| 6 | `piezas` | Hojas de reparto, mapas, gráficos, cabeceras | OpenAI + local |
| 7 | `assets` | Imágenes de los planos | OpenAI |

Después: `callouts`, `banda_sonora`, `efectos` y `render`.

**Reglas de orden que cuestan dinero si se rompen** (docstring de `recetas.py`):
las cartelas van **antes** que los planos (un plano que será cartela no se
genera) y los rótulos **después** (el agente mira las imágenes).

### B.3 Orquestación

- `app.py:304` `_correr_paso`: ejecuta el módulo dentro de
  `_motores_congelados()`, desmonta el resultado, llama a
  `p6_assets.propagar_dependencias` (solo en `assets`), sella con
  `estado.completar` y retira unidades huérfanas.
- `app.py:5440` `_un_paso`: modo `todo` (replantea y rehace) o `pendientes`
  (solo lo sucio, sin replantear).
- `nucleo/trabajos.py`: hilos, progreso por SSE (`/api/trabajos/{tid}/eventos`)
  y cancelación.

---

## C. Árbol de componentes relevantes

```
nucleo/
  estado.py        PASOS (l.79), firmas (l.222-326), completar (l.995), revertir (l.1079)
  proyecto.py      huella() = sha256[:16] de JSON ordenado (l.228); carpetas pasos/<id>/v<N>
  coste.py         Medidor + instrumentar(): envuelve funciones POR NOMBRE (l.794)
  trabajos.py      hilos, progreso SSE, cancelación
  bitacora.py      registro de eventos por proyecto y global

pasos/
  recetas.py       TAREAS, orden, fase del CLI de cada tarea
  cli_claude.py    ÚNICO punto de llamada a Claude: ejecutar() l.637, escribiendo(), POR_FASE l.274
  p1_ingesta.py … p8_render.py     los 8 pasos
  p3_guion.py, p5_revision_audio.py, catalogo_visual.py, direccion.py, redactor.py,
  cartelas.py, conservar.py, corrector.py, repaso.py, estilo.py, tono.py,
  voz_descrita.py, enrutar_estilo.py, asistente.py        → todos llaman a cli_claude
  p6_assets.py     _producir_imagen l.2935 (adoptado → caché → API), _generar_escenas l.3161,
                   _referencias_estilo l.3721
  moodboard.py     láminas de estilo, también con imagen.generar
  p4_voz.py        _toma_real l.822 (SSE), _toma_por_contexto l.753 (websocket), listar_voces
  sonido.py        Jamendo l.264, FreeSound l.756, mezcla con ducking y loudnorm
  p7_callouts.py   capas SVG, movimiento, hyperframes (escala_hyper = 2)
  subtitulos.py    trozos de narración con tiempos (sin emparejar: es la narración)
  p8_render.py     _codificar l.436 (libx264), _concatenar l.551 (concat + filter_complex)
  medios.py        motor() l.128, rasterizar, ffmpeg(), sembrar_trabajo, huella
  comun.py         cargar_motor() l.38, extraer_json, utilidades de texto
  claves.py        almacén secretos/claves.json (esquema cerrado, l.101 y l.133)
  comprobar_claves.py   prueba cada clave contra su servicio sin gastar
  ajustes.py       calidad_imagen, onboarding_visto, TOKENS_ENTRADA_POR_IMAGEN
  presets_canal.py estilos: guion, estilo, rótulos, voz, canal
  mcp_estudio.py   herramientas MCP del asistente

motores/
  imagen_openai/imagen.py      generar() l.594, límite por minuto, varias cuentas
  voz_cartesia/voz.py          SSE / bytes, espaciar, marcas de palabra
  voz_cartesia/sincronizar.py  tiempos del plan a partir del audio
  guion/segmentar.py           corte por programación dinámica
  guion/medir_ritmo.py         cadencia real de una toma
  capa_vectorial/              cabecera.py, mapa.py (+ paises_110m.geojson)
  render_video/movimiento.py   recorrido de cámara sobre el hyperframe
  reglas/                      reglas de dibujo aprendidas (reglas.json, reglas.py)
  revision/regenerar.py        regeneración con feedback (importa imagen directamente)
```

---

## D. Tabla de proveedores actuales

| Proveedor | Para qué | Cómo | Dónde | Coste |
|---|---|---|---|---|
| **Claude** | Guion, catálogo, estilo, tono, dirección, redactor, cartelas, revisión, repaso, corrector, asistente | **CLI `claude -p` por subprocess**, con la suscripción. Borra a propósito `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX` (`cli_claude.py:117`) | `pasos/cli_claude.py` | Tokens medidos, no dólares (`tarifas.json`: `suma_al_total: false`) |
| **OpenAI gpt-image-2** | Planos, hojas de reparto, moodboard, regeneración | REST `https://api.openai.com/v1/images/edits` multipart, **siempre con referencias** | `motores/imagen_openai/imagen.py` | Tarifa por tokens (`tarifas.json`) |
| **Cartesia sonic-3.x** | Locución con marcas por palabra | SSE (`/tts/sse`), `/tts/bytes` y websocket | `motores/voz_cartesia/voz.py`, `pasos/p4_voz.py` | Por carácter |
| **Jamendo** | Música de fondo | REST v3.0, se descarga al banco | `pasos/sonido.py` | Gratis |
| **FreeSound** | Efectos | REST v2, se descarga al banco | `pasos/sonido.py` | Gratis |
| ffmpeg / ffprobe | Codificar, mezclar, medir | Local | `medios.ffmpeg()`, `medios.ffprobe()` | — |
| Edge / Chromium | Rasterizar SVG y capturar fotogramas por CDP | Local | `medios.rasterizar`, `p8_render` | — |

### D.1 Detalle de Claude

- Modelos aceptados: `haiku`, `sonnet`, `opus` o un id `claude-*` completo.
- Esfuerzos: `low`, `medium`, `high`, `xhigh`, `max`. El esfuerzo va **siempre
  explícito**; el tiempo máximo escala con él.
- Por defecto `opus` / `xhigh` (`cli_claude.py:83-84`), con ajustes por fase en
  `POR_FASE` (`cli_claude.py:274`) y en `recetas.json`.
- Varias cuentas (`CLAUDE_CONFIG_DIR`) en orden, con salto a la siguiente si una
  falla; `TiempoAgotado` y `LimiteAgotado` no se reintentan.
- `escribiendo()`: el agente escribe su JSON a un fichero en una carpeta
  temporal (para respuestas largas), con `Bash` siempre vetado.
- La salud de cada cuenta se anota en `pasos/salud_cli.py` desde `_una_pasada`.

### D.2 Detalle de OpenAI (imagen)

- Modelo `gpt-image-2`; tamaños `apaisado 1536x1024`, `cuadrado 1024x1024`,
  `vertical 1024x1536`; calidades `low | medium | high`.
- Orden de referencias fijo porque el prompt las cita por posición: estilo /
  lámina, estructura, personajes, continuidad (plano anterior).
- Freno compartido por cuenta, cubo de fichas calibrado con las cabeceras
  `x-ratelimit-*`, distinción entre 429 de ritmo y «sin saldo», 401 aparta la
  cuenta, reintento único de 400 de imagen inválida.
- Coste real: en calidad baja el 87 % del gasto son las **referencias** (tokens
  de entrada, mediana 5.114 por imagen).

| Calidad | Imagen | Referencias | Total | Real | Aparente |
|---|---|---|---|---|---|
| low | 0,006 $ | 0,041 $ | **0,047 $** | — | — |
| medium | 0,041 $ | 0,041 $ | **0,082 $** | **1,7×** | 6,8× |
| high | 0,165 $ | 0,041 $ | **0,206 $** | **4,4×** | 27,5× |

### D.3 Detalle de Cartesia (voz)

- Modelos `sonic-3.5` (defecto), `sonic-3`, `sonic-turbo`, `sonic-2`.
- `sonic-3`/`3.5` usan `generation_config`; `sonic-2`/`turbo` usan
  `__experimental_controls` (lo que no toca se ignora **sin error**).
- Emociones y niveles validados antes de gastar (la API devuelve 400).
- Salida obligatoria: wav + marcas `{w, s, e}` por palabra.

### D.4 Qué no hay activo

No hay transcripción, ni whisper, ni yt-dlp activos. Quedan menciones en
docstrings y funciones muertas: `_correr_extraer_estilo` (`app.py:2456`) llama a
`estilo.extraer`, que ya no existe; `_correr_tono` (`app.py:2477`) tampoco se
usa.

---

## E. Puntos exactos de integración

### E.1 Por capacidad

| Capacidad | Punto único de llamada | Contrato de salida |
|---|---|---|
| LLM | `cli_claude.ejecutar()` / `cli_claude.escribiendo()` | `(texto, sobre)`; `sobre` lleva `usage` y `_ajuste` (modelo, esfuerzo, segundos, cuenta) |
| Imagen | `imagen.generar(prompt, referencias, quality, tamano)` | `(png_bytes, meta{coste, usage, segundos, modelo, tamano, refs, quality})` |
| Voz | `p4_voz._toma_real(texto, cfg, progreso)` y `p4_voz._toma_por_contexto(trozos, cfg, progreso)` | wav + `palabras[{w,s,e}]` **obligatorias** |
| Música y efectos | `sonido.buscar_musica`, `sonido.buscar_efectos`, `sonido.traer` | ficha y fichero en `banco/audio/` |
| Montaje | `p8_render._codificar` y `p8_render._concatenar` | clips mp4 por escena y mp4 final |

### E.2 Llamadas directas al motor de imagen

| Fichero | Llamadas |
|---|---|
| `pasos/p6_assets.py` | 5 sitios (`_producir_imagen`, `_referencias_*`, `_generar_escenas`, …) |
| `pasos/moodboard.py` | 2 (`generar`, `dibujar_desde_guia`) |
| `app.py` | 2 (`_cuentas_de_imagen`, …) |
| `motores/revision/regenerar.py` | import directo de `imagen` |

### E.3 Llamadas al CLI de Claude

`pasos/p3_guion.py:870`, `pasos/p5_revision_audio.py:330`,
`pasos/catalogo_visual.py:911`, `pasos/direccion.py:626`,
`pasos/redactor.py:436`, `pasos/cartelas.py:2675`, `pasos/conservar.py:572`,
`pasos/estilo.py:241` y `:607`, `pasos/tono.py:154`, `pasos/enrutar_estilo.py:626`,
`pasos/corrector.py:250`, `pasos/repaso.py:954`, `pasos/voz_descrita.py:214`,
`pasos/p4_voz.py:1537`, `pasos/asistente.py:313`.

### E.4 Funciones que el medidor de coste envuelve por nombre

`nucleo/coste.py:794-866`: `ejecutar` de cada paso, `_llamar_claude` (guion,
revision_audio, estilo, tono, catalogo_visual, conservar), `_producir_imagen`,
`generar` (todas las copias de `imagen.py`), `_toma_real`,
`_toma_por_contexto` y `previsualizar`. Se re-engancha tras cada recarga de
motor con `medios.AL_CARGAR`.

---

## F. Dependencias

### F.1 Python (fijadas en `requirements.txt`)

| Paquete | Versión |
|---|---|
| fastapi | 0.141.1 |
| starlette | 1.6.0 |
| uvicorn | 0.52.1 |
| python-multipart | 0.0.32 |
| pillow | 12.3.0 |
| numpy | 2.5.2 |
| requests | 2.34.2 |
| websocket-client | 1.9.0 (camino de voz por websocket y CDP del render) |

### F.2 Sistema

- **ffmpeg y ffprobe** (voz, música, montaje).
- **Microsoft Edge** o Chrome/Chromium (rasterizado y captura).
- **Fuentes** instaladas en `/usr/local/share/fonts/estudio` (medir y dibujar
  deben usar el mismo fichero).
- **Node** + `@anthropic-ai/claude-code` (lo instala `instalar.sh`).

### F.3 Despliegue

systemd, nginx y el servicio de login en Node (`despliegue/`).

### F.4 Pruebas

`pruebas.ps1` con 23–24 suites, pensado para Windows/PowerShell, más las
herramientas de análisis de `herramientas/`.

---

## G. Variables de entorno y configuración

### G.1 Secretos

| Dónde | Qué |
|---|---|
| `secretos/claves.json` (espejado en `secretos/.env`) | Almacén de claves; fuera del control de versiones |
| `OPENAI_API_KEY`, `OPENAI_API_KEY_2..9` | OpenAI |
| `CARTESIA_API_KEY` | Cartesia |
| `JAMENDO_CLIENT_ID` | Jamendo |
| `FREESOUND_API_KEY` | FreeSound (token «Client secret/Api key») |
| Carpetas `CLAUDE_CONFIG_DIR` | Cuentas del CLI de Claude (login, no clave) |

### G.2 Rutas y comportamiento

| Grupo | Variables |
|---|---|
| Datos | `ESTUDIO_PROYECTOS`, `ESTUDIO_PRESETS`, `ESTUDIO_BANCO`, `ESTUDIO_BANCO_PRESETS`, `ESTUDIO_SECRETOS` |
| Configuración | `ESTUDIO_AJUSTES`, `ESTUDIO_RECETAS`, `ESTUDIO_TARIFAS` |
| Medidas y gasto | `ESTUDIO_ESTADISTICAS`, `ESTUDIO_COSTE_GLOBAL`, `ESTUDIO_BITACORA_GLOBAL` |
| Motores y fuentes | `ESTUDIO_MOTORES`, `ESTUDIO_FUENTES` |
| Ejecutables | `ESTUDIO_EDGE`, `ESTUDIO_FFMPEG`, `ESTUDIO_FFPROBE`, `ESTUDIO_LOTES` |
| Comportamiento | `ESTUDIO_SIMULAR=1`, `ESTUDIO_API`, `ESTUDIO_ASISTENTE_MODELO`, `ESTUDIO_ASISTENTE_ESFUERZO` |

### G.3 Ficheros de configuración

| Fichero | Contenido |
|---|---|
| `tarifas.json` | Precios por proveedor (openai, tts, claude_cli) |
| `ajustes.json` | `calidad_imagen`, `onboarding_visto` |
| `recetas.json` | Modelo y esfuerzo por fase del CLI |
| `presets.json` | Estilos de canal |

### G.4 Modo simulado

`ESTUDIO_SIMULAR` solo lo respetan la voz, la revisión y el asistente. **La
imagen no tiene modo simulado**: las pruebas la bloquean sustituyendo `generar`
(`prueba_piezas._prohibir_pagar`).

---

## H. Sistema de caché y regeneración

1. **Firma del paso** (`nucleo/estado.py`). Tres partes:
   - **global**: params sin `unidades` + firmas globales de las dependencias;
   - **por unidad**: datos de esa unidad + la misma unidad aguas arriba + sellos
     de salida;
   - **completa**: global + unidades + firmas completas y sellos de las
     dependencias.

   Un paso está obsoleto si la firma calculada no coincide con la guardada.
   `_params_globales` hashea los **params crudos guardados**: cualquier clave
   nueva mueve la firma. `CORRECCIONES = {"guion": ("bloques",)}` descuenta las
   correcciones a mano de la firma propia del guion (`firma_propia`).
2. **Versiones.** Cada paso escribe en `pasos/<id>/trabajo/`, `completar` lo
   mueve a `v<N>/`, y el manifiesto va en `pasos/<id>/_versiones/v<N>.json`,
   escrito **antes** que `datos`. `sembrar_trabajo` copia la versión activa antes
   de rehacer una parte. `revertir` restaura params, manifiesto y firma.
3. **Caché de imagen por contenido** (`pasos/p6_assets.py:2948`):
   `huella({prompt, calidad, tamano≠apaisado, refs=[huella_fichero]})` →
   `banco/imagenes/<firma>.png`. Orden de búsqueda: arte adoptado → caché → API.
   `rehacer` se salta las dos.
4. **Cascada de marcado.** Cuando cambia un asset, las escenas que lo usan
   quedan obsoletas (`propagar_dependencias`), pero **no se regeneran solas**.
5. **Decisiones por unidad.** Las cartelas y la dirección van en
   `unidades["escena:S013"]` para no mover la firma global. **Es el patrón que
   hay que imitar.**
6. **Render por escena.** Un clip por plano concatenado sin recodificar:
   rehacer un plano cuesta un clip. Música y efectos se mezclan al muxear
   (remuxear, no recodificar).
7. **Banco de audio determinista.** Buscar y elegir es un paso humano; renderizar
   no sale a la red.

---

## I. Riesgos técnicos

| # | Riesgo | Detalle | Mitigación |
|---|---|---|---|
| 1 | **Firmas** | Añadir `proveedor_imagen` a los params de `assets` con un valor por defecto deja obsoletas las ~126 imágenes de cada proyecto. | Si la clave no está, significa el comportamiento de siempre, y **nunca se escribe el valor por defecto**. |
| 2 | **Caché sin proveedor** | La huella no incluye proveedor ni modelo. | Incluirlos en la huella **solo cuando no sean los de hoy** (mismo truco que `tamano: None if apaisado`). |
| 3 | **Calidades acopladas a OpenAI** | `low/medium/high` están en `ajustes.CALIDADES`, en la firma, en `tarifas.json` y en la pantalla. | Calidades declaradas por proveedor. |
| 4 | **Contrato de imagen implícito** | Referencias obligatorias y su posición citada en el prompt (lámina, reparto, continuidad). Un proveedor sin edición multi-referencia rompe la continuidad visual. Además, `moodboard.dibujar_desde_guia` llama a `imagen.generar(prompt, [])` (`pasos/moodboard.py:721`) y `generar` lanza `ValueError` sin referencias (`imagen.py:602`): ese camino («estilo descrito») falla siempre. | Separar las capacidades «texto→imagen» e «imagen+refs→imagen». |
| 5 | **Voz sin marcas de palabra** | Sin ellas no hay corte, subtítulos ni cartelas sincronizadas. | Alineamiento forzado local para proveedores TTS sin marcas. |
| 6 | **Medidor por nombre** | `coste.instrumentar` busca ficheros `imagen.py` cuya ruta contenga `imagen_openai` (`nucleo/coste.py:890`). Un motor nuevo no se mediría y el gasto desaparecería **sin error**. `reportar_openai` y `reportar_tts` son específicos. | Anotar el coste en la fachada de cada capacidad. |
| 7 | **Esquema de claves cerrado** | `claves._normalizar` solo conserva `openai`, `cartesia`, `jamendo`, `freesound` y `claude_cli` (`pasos/claves.py:133`): una clave nueva se **borraría al guardar**. `comprobar_claves`, la guía de inicio y Configuración están cableados a esos nombres (~44 menciones de OpenAI y ~43 de Cartesia en `web/app.js`). | Esquema abierto por proveedor, conservando los nombres actuales. |
| 8 | **Estado de módulo en los motores** | Freno, cubo y cuentas de `imagen.py` viven en el módulo; la recarga en caliente y la doble importación (`medios` y `pasos.medios`) ya obligaron a crear `_medios_compartido`. | El registro de proveedores debe respetar ese mecanismo. |
| 9 | **Vídeo por IA no encaja en el modelo actual** | Llamadas asíncronas largas, coste alto por segundo, duración que debe cuadrar con la narración (planos de 3–6 s marcados por la voz). El render captura hyperframe + SVG + transiciones y no sabe usar un clip de entrada. | Capacidad nueva, opcional por plano (ver M). |
| 10 | **Agnes Video 2.5 Flash desconocido** | No hay información fiable sobre su API (formato, trabajos asíncronos, duraciones, image-to-video, precio). | No asumir nada; verificar su documentación antes de la fase de vídeo y empezar con un adaptador simulado. |
| 11 | **Claude CLI frente a API** | Hoy es una decisión de contrato (solo suscripción). | Si se quiere la API, es otro proveedor LLM, no un cambio en `cli_claude`. |

---

## J. Qué debemos conservar

- El grafo y sus ids.
- `nucleo/` entero.
- La firma por unidad.
- La caché por contenido.
- `cli_claude` como punto único de Claude.
- La voz como reloj maestro.
- El render por escena con concatenación sin recodificar.
- El banco de audio determinista.
- Las reglas de `CLAUDE.md`: no escribir defectos, una tanda de imágenes cada
  vez, el guardián de planos repetidos (`p6_assets._planos_repetidos`).
- El patrón «motores por contrato» y el medidor de coste.

---

## K. Qué deberíamos modificar posteriormente

| Fichero / área | Cambio |
|---|---|
| `motores/imagen_openai/imagen.py` | Pasa a ser un adaptador; el contrato `generar()` no cambia. |
| Nueva carpeta `motores/proveedores/` (o `pasos/proveedores.py`) | Registro y fachadas por capacidad. |
| `pasos/p6_assets.py` | `_producir_imagen`: resolver el proveedor y ampliar la huella de la caché. `_referencias_*`: usan `imagen.normalizar`. `PARAMS_POR_DEFECTO`: sin tocar el valor que ya existe. |
| `pasos/moodboard.py`, `motores/revision/regenerar.py`, `app.py` (`_cuentas_de_imagen`, `_correr_moodboard`) | Pasar por la fachada de imagen. |
| `pasos/p4_voz.py`, `motores/voz_cartesia/voz.py` | Fachada TTS con el contrato de marcas. |
| `nucleo/coste.py` | `instrumentar` y `modulos_de_imagen` por registro; `reportar_generico(proveedor, …)`. |
| `tarifas.json` | Una sección por proveedor. |
| `pasos/ajustes.py` | Calidades por proveedor. |
| `pasos/claves.py`, `pasos/comprobar_claves.py`, `pasos/mcp_estudio.py` | Esquema abierto por proveedor. |
| `pasos/recetas.py` | Tarea opcional `clips` si se añade vídeo por IA. |
| `pasos/p7_callouts.py`, `pasos/p8_render.py` | Aceptar un clip generado como fondo de un plano. |
| `web/app.js` | Selector de proveedor, claves, costes y estado de los clips. |
| Pruebas | `pasos/prueba_piezas.py`, `prueba_api.py`, `pasos/prueba_pasos_visuales.py`, `prueba_coste_capturas.py`. |

---

## L. Qué NO debemos modificar

- Los ids y las dependencias de `nucleo/estado.PASOS`: ni renombrar, ni quitar,
  ni meter pasos por delante de uno existente.
- `huella()` (`nucleo/proyecto.py:228`).
- El orden de escritura de `completar()` (manifiesto antes que `datos`).
- `_params_globales`.
- El formato de `estado.json` y de los manifiestos.
- Los valores por defecto guardados en proyectos existentes.
- El contrato «sin pago por uso» de `cli_claude`, salvo decisión explícita.
- El orden guion → voz → corte.

---

## M. Arquitectura propuesta para proveedores intercambiables

La idea es añadir capacidades por detrás de fachadas, **sin tocar el grafo**.

### M.1 Capacidades y adaptadores

| Capacidad (interfaz) | Firma conceptual | Adaptadores |
|---|---|---|
| **LLM** | texto/JSON | `claude_cli` (hoy) · `claude_api` · … |
| **ImagenRef** | prompt + refs → png | `openai_gpt_image` (hoy) · … |
| **ImagenTexto** | prompt → png | `openai` (arregla el moodboard) · … |
| **TTS** | texto → wav + marcas | `cartesia` (hoy) · … (+ alineador local si no hay marcas) |
| **VideoIA** | imagen/prompt → clip | `agnes_video_2_5_flash` · … (asíncrono: lanzar / consultar / bajar) |
| **Música / SFX** | buscar / traer | `jamendo` · `freesound` |

### M.2 Qué declara cada adaptador

Cada adaptador es un motor más (carga por ruta, claves por contrato) y declara:

- `id` y `modelo`;
- sus capacidades (`refs_max`, `tamanos`, `calidades`, `marcas_palabra`,
  `duraciones_clip`);
- `probar_clave()`;
- `tarifa()`;
- y devuelve `meta` con `proveedor`, `modelo`, `usage` y `coste`.

### M.3 Fachada

- Resuelve el proveedor así: primero el param de la **unidad**, después el del
  paso y, si no hay ninguno, el de siempre.
- **Anota el coste** en un único punto por capacidad; se deja de envolver por
  nombre.

### M.4 Firmas

Solo cuentan el proveedor y el modelo cuando alguien los elige. Los proyectos
existentes quedan idénticos byte a byte.

### M.5 Vídeo por IA

- Propiedad **opcional por plano** (`unidades["escena:S013"]["clip"]`),
  producida dentro de `assets` después de la imagen (la imagen es su fotograma
  inicial).
- `callouts` y `render` usarían el clip como fondo en lugar del hyperframe,
  recortado o ajustado a la duración que marca la voz.
- Así solo se ensucian los planos que lo piden, y **no hace falta un paso nuevo
  en el grafo**.

### M.6 El pipeline objetivo mapeado sobre los ids actuales

| Etapa objetivo | Id o tarea actual |
|---|---|
| Investigación | `ingesta` (hoy solo texto; el documentalista se quitó a propósito) |
| Guion | `brief` + `guion` |
| Voz | `voz` + `revision_audio` (**se queda aquí**, antes del storyboard) |
| Storyboard | tareas de `assets`: catálogo, corte, cartelas, dirección/redactor |
| Generación de assets | `assets` (piezas y planos) |
| Generación de vídeo | `assets`, subtarea `clips` |
| Montaje FFmpeg | `callouts` + `render` |
| Vídeo final | salida `mp4` de `render` |

---

## N. Plan de implementación en fases pequeñas

Cada fase es verificable por separado con `pruebas.ps1`. Regla de todas:
**«cero firmas movidas en un proyecto existente»**.

| Fase | Contenido | Criterio de hecho |
|---|---|---|
| **0. Red de seguridad** | Prueba que abre un proyecto fijado, calcula todas las firmas y las compara con las de antes. Arreglar el camino roto del moodboard sin referencias. | La prueba falla si cualquier firma cambia. |
| **1. Fachada de imagen** | `proveedores.imagen()` devuelve el motor OpenAI actual; todas las llamadas pasan por ahí y el medidor se engancha a la fachada. | Sin cambio de comportamiento; coste medido igual. |
| **2. Huella de caché con proveedor** | Inclusión condicional y retrocompatible, con su prueba. | Caché antigua sigue acertando; proveedor nuevo no la comparte. |
| **3. Esquema de claves abierto** | `claves.py` y `comprobar_claves.py`, conservando los nombres actuales. | Claves nuevas sobreviven a un guardado. |
| **4. Tarifas y calidades por proveedor** | `tarifas.json`, `ajustes.py`, `coste.py`. | Coste correcto por proveedor en pantalla. |
| **5. Fachada TTS** | Contrato `wav + palabras`, prueba de contrato común para cualquier adaptador. | Cartesia pasa la prueba de contrato. |
| **6. Selector en la interfaz** | Proveedor por paso o plano, sin escribir valores por defecto. | Abrir pantallas no mueve firmas. |
| **7. Capacidad VideoIA** | Interfaz asíncrona, adaptador simulado, render que acepta clips. | MP4 con un plano de clip simulado. |
| **8. Adaptador Agnes Video 2.5 Flash** | Tras verificar su API real. | Un plano real generado y medido. |
| **9. (Opcional)** | Otros proveedores de LLM, imagen o TTS. | — |

---

## O. Orden recomendado de las modificaciones

**0 → 1 → 2 → 4 → 3 → 5 → 6 → 7 → 8**

1. Primero lo que protege el dinero: red de firmas, fachada y caché.
2. Después el coste medido correctamente.
3. Luego las claves y la voz.
4. La interfaz va detrás de tener backend.
5. El vídeo por IA va al final porque es la única pieza nueva de verdad, y
   Agnes después de un adaptador simulado que fije el contrato.

---

## Anexo 1. Incidencias detectadas durante la auditoría

| Incidencia | Dónde | Efecto |
|---|---|---|
| `dibujar_desde_guia` llama a `imagen.generar(prompt, [])` y `generar` rechaza listas vacías | `pasos/moodboard.py:721`, `motores/imagen_openai/imagen.py:602` | El camino «estilo descrito» (láminas desde una guía escrita) falla siempre con `ValueError`. |
| `_correr_extraer_estilo` llama a `estilo.extraer`, que no existe | `app.py:2456` | Código muerto heredado de v1. |
| `_correr_tono` definido y sin uso | `app.py:2477` | Código muerto heredado de v1. |
| La imagen no respeta `ESTUDIO_SIMULAR` | `motores/imagen_openai/imagen.py` | Las pruebas dependen de sustituir `generar` para no pagar. |
| Clave de caché de imagen sin proveedor/modelo | `pasos/p6_assets.py:2948` | Riesgo al introducir otro proveedor (ver I.2). |

---

## Anexo 2. Cómo se genera cada cosa

| Qué | Cómo | Dónde |
|---|---|---|
| **Guiones** | Claude CLI redacta los bloques con material, brief, guion anterior e instrucción; entrada por stdin | `pasos/p3_guion.py` |
| **Prompts de imagen** | Código que ensambla estilo + sitio + beat + frase (`_prompt_visual`, `_prompt_completo`), o `direccion` (una línea por plano) / `redactor` (prompt entero) con Claude; reglas de `motores/reglas/` | `pasos/p6_assets.py`, `pasos/direccion.py`, `pasos/redactor.py` |
| **Imágenes** | gpt-image-2 `/images/edits` con referencias (lámina de estilo, hojas de reparto, continuidad) | `motores/imagen_openai/imagen.py` |
| **Vídeo** | Sin IA: hyperframe ×2 + movimiento de cámara + capas SVG + transiciones WebGL, capturado por Edge/CDP y codificado con libx264 | `pasos/p7_callouts.py`, `motores/render_video/movimiento.py`, `pasos/transiciones.py`, `pasos/p8_render.py` |
| **Voz** | Cartesia, una sola toma con marcas por palabra; silencios insertados después (`espaciar`) | `pasos/p4_voz.py`, `motores/voz_cartesia/voz.py` |
| **Subtítulos** | La narración troceada con los tiempos de las marcas; banda fija en el cuadro de salida | `pasos/subtitulos.py`, `pasos/p7_callouts.py` |
| **Cartelas** | Planos de texto sobre negro con 10 plantillas cerradas; qué plano y qué texto lo decide Claude | `pasos/cartelas.py` |
| **Música** | Jamendo, elegida por una persona, descargada al banco; cama al largo del vídeo, loudnorm y ducking | `pasos/sonido.py` |
| **Efectos** | FreeSound, surtidos al banco por papel; pista montada en numpy | `pasos/sonido.py` |
| **Montaje final** | ffmpeg concat de clips sin recodificar + `filter_complex` (voz, música con `sidechaincompress`, efectos, master con loudnorm medido), AAC 192k, `+faststart` | `pasos/p8_render.py:551` |

---

## Anexo 3. Qué es local y qué depende de servicios externos

| Local | Externo |
|---|---|
| Ingesta, brief, segmentación, cartelas, subtítulos, mapas, cabeceras, movimiento, transiciones, rasterizado, captura, codificación y mezcla | Claude (CLI con suscripción), OpenAI (imágenes), Cartesia (voz), Jamendo (música, solo al surtir), FreeSound (efectos, solo al surtir) |

Renderizar no sale a la red: música y efectos se toman del banco local.
