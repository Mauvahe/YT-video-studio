# AS Video Studio — Fase 0: red de seguridad

> **Tipo de documento:** informe de implementación de referencia.
> **Fase:** 0 — Red de seguridad (plan de `docs/AS_VIDEO_STUDIO_AUDIT.md`, sección N).
> **Commit:** `59d75a0` en la rama `claude/stoic-tesla-m12790` (sin pull request).
> **Commit anterior (base):** `6bba07d` (auditoría).
> **Alcance:** detectar cualquier regresión en las firmas antes de introducir
> proveedores intercambiables, y corregir el camino roto del moodboard sin
> referencias. **No** incluye ninguna parte de las fases 1–8.

---

## Índice

- [0. Resumen](#0-resumen)
- [A. Archivos modificados y creados](#a-archivos-modificados-y-creados)
- [B. Qué cambió](#b-qué-cambió)
- [C. Baseline de firmas](#c-baseline-de-firmas)
- [D. Moodboard sin referencias](#d-moodboard-sin-referencias)
- [E. Pruebas](#e-pruebas)
- [F. Servicios externos](#f-servicios-externos)
- [G. Compatibilidad](#g-compatibilidad)
- [H. Problemas encontrados fuera de alcance](#h-problemas-encontrados-fuera-de-alcance)
- [I. Cómo usar la red de seguridad en las fases siguientes](#i-cómo-usar-la-red-de-seguridad-en-las-fases-siguientes)

---

## 0. Resumen

| Objetivo | Resultado |
|---|---|
| Prueba de regresión de firmas | `nucleo/prueba_firmas.py` — 28 comprobaciones, **88 firmas** contra la base, en verde |
| Baseline explícita y legible | `nucleo/fixtures/firmas/base.json` |
| Fixture estable y sin datos privados | `nucleo/fixtures/firmas/proyecto_firmas/` + `receta.py` |
| Detección real de regresiones | 3 mutaciones introducidas en copias del repo → las 3 detectadas con la firma exacta |
| Moodboard sin referencias | Corregido en `pasos/moodboard.py` + `app.py`; prueba nueva con 23 comprobaciones en verde |
| Suites existentes | Mismos resultados antes y después |
| Llamadas a servicios de pago | **Ninguna** (ver salvedad en F) |

---

## A. Archivos modificados y creados

### A.1 Modificados (3)

| Archivo | Cambio |
|---|---|
| `pasos/moodboard.py` | `dibujar_desde_guia` recibe y adjunta imágenes de apoyo; docstring de `prompt_de_eje` corregido |
| `app.py` | Una llamada en `_correr_light_referencias` pasa `referencias=_aportadas_del_taller(ctx)` |
| `pruebas.ps1` | Las dos suites nuevas añadidas a la lista |

### A.2 Creados

| Archivo | Qué es |
|---|---|
| `nucleo/prueba_firmas.py` | La prueba de regresión de firmas |
| `nucleo/fixtures/firmas/receta.py` | Cómo se construye el proyecto de prueba con el API público del núcleo |
| `nucleo/fixtures/firmas/proyecto_firmas/` | El proyecto congelado: 14 ficheros JSON (`estado.json`, `proyecto.json`, `pasos/*/activa.json`, manifiestos `pasos/*/_versiones/v*.json`) |
| `nucleo/fixtures/firmas/base.json` | La línea base de firmas |
| `pasos/prueba_moodboard_descrito.py` | La prueba del camino del moodboard descrito |

Ficheros del proyecto congelado:

```
nucleo/fixtures/firmas/proyecto_firmas/
  proyecto.json
  estado.json
  pasos/ingesta/activa.json
  pasos/brief/activa.json
  pasos/guion/activa.json
  pasos/voz/activa.json
  pasos/revision_audio/activa.json
  pasos/assets/activa.json
  pasos/assets/_versiones/v2.json        (la v1 va en formato viejo, dentro de estado.json)
  pasos/callouts/activa.json
  pasos/callouts/_versiones/v1.json
  pasos/render/activa.json
  pasos/render/_versiones/v1.json
```

---

## B. Qué cambió

### B.1 Prueba de firmas (`nucleo/prueba_firmas.py`)

1. Copia el proyecto fijo a una carpeta temporal y lo abre desde ahí (nunca
   ensucia el fixture del repositorio).
2. Verifica que **abrirlo no reescribe ningún fichero** (comparación byte a byte).
3. Calcula todas las firmas y las compara **una a una** con la base.
4. Si algo cambia, imprime la ruta exacta (por ejemplo `assets.firma_calculada`)
   con el valor de la base y el de ahora.
5. Reconstruye el proyecto desde la receta con el código de hoy y exige las
   mismas firmas (detecta cambios en `completar`, `set_params` o la propagación).
6. Instala un guardián en `socket` que hace fallar cualquier conexión de red.
7. Borra las variables de claves del entorno y apunta `ESTUDIO_SECRETOS` a una
   carpeta vacía: no lee ninguna clave.

Solo usa `nucleo/`, que no importa ningún motor.

Modos:

```bash
python nucleo/prueba_firmas.py                 # comparar con la base
python nucleo/prueba_firmas.py --escribir-base  # rehacer la base A PROPÓSITO
python nucleo/prueba_firmas.py --congelar       # rehacer el fixture desde la receta
```

> **Rehacer la base no es arreglar la prueba.** Una firma movida en este fixture
> es una firma movida en todos los proyectos guardados. Solo se rehace cuando el
> cambio es deliberado, y se dice en el commit.

### B.2 Fixture (`nucleo/fixtures/firmas/`)

Proyecto inventado (4 planos, un personaje, ningún dato real, ninguna ruta
absoluta). Reproduce los casos delicados de los proyectos reales:

| Caso | Cómo aparece en el fixture |
|---|---|
| Guion corregido a mano (`CORRECCIONES`, `firma_propia`) | Bloque `B02` cambiado después de completar: firma guardada ≠ calculada y el paso sigue `listo` |
| Unidades de `assets` | `escena:S001`–`S004`, `asset:ana`, `asset:set_muelle` |
| Decisión por unidad | Cartela en `escena:S003`, dirección en `escena:S002` |
| Dependencias propagadas | `assets` + `huella_assets` en las escenas, como `p6_assets.propagar_dependencias` |
| Formato viejo de manifiesto | `assets` v1 con el manifiesto dentro de `estado.json` |
| Formato actual de manifiesto | `assets` v2 en `_versiones/v2.json` |
| Herencia por el DAG | `callouts` y `render` heredan las 4 escenas |
| Params reales de `assets` | `calidad`, `motor_imagen`, `estilo`, `catalogo`… con los valores por defecto de hoy |

### B.3 Moodboard (`pasos/moodboard.py`, `app.py`)

- `dibujar_desde_guia` acepta un parámetro nuevo y opcional: `referencias`.
- Sin ninguna imagen de apoyo existente, falla **antes de gastar nada** con un
  `RuntimeError` claro.
- Con imágenes, las monta en **una sola lámina** con `_montar` (igual que el
  camino con vídeo) en `<destino>/_refs/aportadas.png` y la adjunta a cada
  llamada al motor.
- El prompt usa `con_lamina=True` y conserva el encabezado neutro.
- `app.py` (`_correr_light_referencias`) le pasa las imágenes aportadas del taller.
- Se corrigió la frase del docstring de `prompt_de_eje` que decía que
  `con_lamina=False` era el caso del estilo descrito.

### B.4 `pruebas.ps1`

Se añadieron `nucleo\prueba_firmas.py` y `pasos\prueba_moodboard_descrito.py` a
la lista de suites.

---

## C. Baseline de firmas

### C.1 Datos

| Campo | Valor |
|---|---|
| Fixture | `nucleo/fixtures/firmas/proyecto_firmas` |
| Receta | `nucleo/fixtures/firmas/receta.py` |
| Ubicación de la base | `nucleo/fixtures/firmas/base.json` |
| Firmas verificadas | **88** |
| Comprobaciones | 28 |
| Resultado | Coincidencia total; los 8 pasos en `listo`; ninguna unidad obsoleta |
| Repetibilidad | 3 ejecuciones idénticas, una de ellas desde otro directorio (`/tmp`) |

### C.2 Qué contienen las 88 firmas

| Grupo | Detalle |
|---|---|
| Grafo | ids, `depende_de` y `unidades` de los 8 pasos, en orden |
| `huella()` | Huella de un valor fijo (claves desordenadas, tildes, anidado, `None`): `30481339284fd43d` |
| Por paso | Estado, firma guardada, firma calculada, firma global, firma propia guardada |
| Por unidad | Firma calculada y firma guardada de cada unidad |
| Manifiestos | Firma de cada versión y firma de cada unidad en su manifiesto |

### C.3 Firmas por paso en la base

| Paso | Estado | Firma calculada | Unidades |
|---|---|---|---|
| `ingesta` | listo | `d78efba3af666537` | 0 |
| `brief` | listo | `73b2af41b41383f9` | 0 |
| `guion` | listo | `fe980a79b8eea5d6` | 0 |
| `voz` | listo | `9f552ef973ee508d` | 0 |
| `revision_audio` | listo | `e0ea54d7b49eefcd` | 0 |
| `assets` | listo | `adae972e07aae651` | 4 |
| `callouts` | listo | `d04e3d2e82fd1a34` | 4 |
| `render` | listo | `b59a14b42d191213` | 4 |

Formatos de manifiesto: `assets` v1 **viejo**, v2 actual; el resto, v1 actual.

### C.4 Detección comprobada (mutaciones en copias del repositorio)

Las mutaciones se hicieron en copias bajo `/tmp`; el repositorio real no se tocó.

| Mutación | Qué detecta la prueba |
|---|---|
| `huella()` recortada a 15 caracteres | Cambian todas las firmas; todos los pasos pasan a obsoletos |
| `_params_globales` ignora `calidad` | `assets`, `callouts` y `render` pasan a obsoletos |
| Dependencia extra (`voz`) en `callouts` | Cambia el grafo; `callouts` y `render` pasan a obsoletos |

En los tres casos la prueba sale con código 1 y nombra la firma exacta con sus
dos valores.

---

## D. Moodboard sin referencias

### D.1 El problema

- `moodboard.dibujar_desde_guia` llamaba a `imagen.generar(prompt, [])`.
- El motor lanza `ValueError` si no recibe al menos una referencia
  (`motores/imagen_openai/imagen.py:602`), porque llama a `/v1/images/edits`.
- Resultado: las láminas de un estilo descrito fallaban **siempre**, eje a eje,
  dentro de sus hilos.
- Reproducido con el código original:
  `ValueError: generar() necesita al menos una imagen de referencia`.

### D.2 Qué lo provocaba

| Pieza | Papel |
|---|---|
| `pasos/moodboard.py` → `dibujar_desde_guia` | Pasaba `[]` como referencias y `con_lamina=False` |
| `app.py` → `_correr_light_referencias` | No le pasaba ninguna imagen |
| `motores/imagen_openai/imagen.py` → `generar` | Exige al menos una referencia (contrato correcto) |

**Las imágenes sí existían:** la tarea `referencias` depende de `guia`
(`pasos/presets_light.py`), y `estilo.generar_guia` no escribe la guía con menos
de 3 imágenes aportadas (`estilo/aportadas`, leídas por `_aportadas_del_taller`).
Simplemente no se pasaban.

### D.3 La corrección

- El camino descrito adjunta las imágenes aportadas igual que `moodboard.generar`:
  una lámina montada con `_montar`, presentada como referencia 1 (`con_lamina=True`).
- Se mantienen: encabezado neutro, guía escrita, correcciones por eje, calidad,
  tamaño (`apaisado`) y ficheros `<eje>.png`.
- La lámina de apoyo va a `<destino>/_refs`, fuera de las láminas entregadas
  (nadie recorre esa carpeta: las referencias van en listas explícitas).

### D.4 Por qué no altera contratos existentes

- El motor de OpenAI no se toca.
- El parámetro nuevo es opcional y va al final de la firma de la función.
- El valor devuelto no cambia (`rutas`, `ejes`, `coste_usd`, `origen: "descrito"`).
- Ese camino no pasa por firmas del grafo ni por la caché de `assets`.
- Antes fallaba siempre: ningún proyecto dependía de su comportamiento.
- La prueba existente de `prueba_enrutar_estilo` (que exige `ejes` y `peticiones`
  en la firma y el literal `ejes=pedidos, peticiones=peticiones` en `app.py`)
  sigue pasando.

### D.5 Cambio de comportamiento a tener en cuenta

El prompt de estas láminas dice ahora «copia el estilo de dibujo de la
referencia 1», la misma frase que el camino con vídeo. En un canal de estilo
**fotográfico**, la palabra «dibujo» podría empujar hacia la ilustración.

### D.6 Qué comprueba `pasos/prueba_moodboard_descrito.py` (23 comprobaciones)

| Sección | Comprobación |
|---|---|
| [1] | El motor de verdad lanza sin referencias, antes de salir a la red |
| [2] | Con `None`, `[]` o rutas inexistentes: error claro y el motor no se llama |
| [3] | Una llamada por eje; una sola referencia por llamada; la lámina existe y es la misma; prompt con «Reference image 1»; encabezado neutro; guía completa; calidad y tamaño iguales; campos devueltos iguales; ficheros `<eje>.png`; coste sumado; solo láminas y `_refs` en la carpeta |
| [4] | Corregir un eje dibuja solo ese, con su corrección en el prompt |
| [5] | `app.py` pasa las imágenes aportadas y sigue pasando ejes y correcciones |
| [6] | Ninguna conexión de red; ninguna clave necesaria |

El motor se sustituye por un doble que aplica **la misma comprobación de entrada**
que el real: nunca se paga una imagen.

---

## E. Pruebas

### E.1 Entorno

No hay PowerShell en el contenedor: `pruebas.ps1` se replicó con un script bash
(fuera del repositorio).

| Elemento | Configuración |
|---|---|
| Python | 3.12.3 con las versiones fijadas de `requirements.txt`, en un venv temporal |
| Red | `HTTPS_PROXY`/`HTTP_PROXY` a un puerto muerto (`127.0.0.1:9`); `NO_PROXY` solo local |
| CLI de Claude | `claude` falso en el `PATH` que falla al instante y registra cada invocación |
| Fuentes | `ESTUDIO_FUENTES` a una carpeta con enlaces a DejaVu/Liberation (como `instalar.sh`) |
| Navegador | Chromium de Playwright con `--no-sandbox` (el contenedor corre como root) |
| ffmpeg | Binario completo de `imageio-ffmpeg` (el de Playwright no trae libx264) |
| Clave OpenAI | `sk-falsa-solo-para-pruebas` (`prueba_piezas` exige que exista alguna) |
| Datos | Todas las variables `ESTUDIO_*` a una carpeta temporal |

### E.2 Suites nuevas

| Comando | Resultado |
|---|---|
| `python nucleo/prueba_firmas.py` | `FIRMAS OK: 28 comprobaciones pasan (88 firmas contra la base)` |
| `python pasos/prueba_moodboard_descrito.py` | `MOODBOARD DESCRITO OK: 23 comprobaciones pasan` |

### E.3 Suites existentes, antes y después

| Suite | Antes | Después |
|---|---|---|
| `prueba_api.py` | OK (807) | OK (807) |
| `prueba_coste_capturas.py` | OK (165) | OK (165) |
| `nucleo/prueba_nucleo.py` | OK | OK |
| `nucleo/prueba_adversarial.py` | OK | OK |
| `nucleo/prueba_manifiestos.py` | OK | OK |
| `pasos/prueba_ajustes.py` | OK | OK |
| `pasos/prueba_asistente.py` | OK | OK |
| `pasos/prueba_salud_cli.py` | OK | OK |
| `pasos/prueba_enrutar_estilo.py` | OK | OK |
| `pasos/prueba_p1.py` | OK | OK |
| `pasos/prueba_p2.py` | OK | OK |
| `pasos/prueba_p3.py` | OK | OK |
| `pasos/prueba_cta.py` | OK | OK |
| `pasos/prueba_marcas_tts.py` | OK | OK |
| `pasos/prueba_pasos_voz.py` | OK (158) | OK (158) |
| `pasos/prueba_repaso.py` | OK (100) | OK (100) |
| `pasos/prueba_conservar.py` | OK (46) | OK (46) |
| `pasos/prueba_encuadres.py` | OK (179) | OK (179) |
| `pasos/prueba_presets.py` | OK (84) | OK (84) |
| `pasos/prueba_presets_light.py` | OK (262) | OK (262) |
| `pasos/prueba_piezas.py` | 1 fallo de 1044 | el mismo fallo |
| `pasos/prueba_pasos_visuales.py` | corta a 900 s con fallos | corta a 900 s con el fallo de duración |

**Fallos por entorno (idénticos antes y después):**

- `prueba_piezas`: la comprobación «lo que no se ha podido retirar se dice por su
  nombre» simula un bloqueo de ficheros de Windows; la propia prueba dice que en
  Linux se puede borrar un fichero abierto.
- `prueba_pasos_visuales`: no hay ffprobe en el contenedor, la duración del vídeo
  sale 0,0 s. En la pasada «antes» apareció además un fallo de determinismo del
  render en paralelo que no se repitió «después». La suite no usa nada de lo
  cambiado (0 referencias a `moodboard` o `dibujar_desde_guia`).

**No ejecutadas:** `pasos/prueba_login.py` y `pasos/prueba_pasos_guion.py`,
porque existen para llamar al CLI de Claude real.

### E.4 Herramientas de análisis (antes y después: salida idéntica)

| Herramienta | Resultado |
|---|---|
| `indefinidos_py.py` | OK: ningún nombre sin declarar |
| `indefinidos_js.py` | OK: ningún identificador sin declarar |
| `huerfanas_js.py` | 2 sospechosas de siempre: `async`, `fallar` |
| `sin_llamar_js.py` | 415 funciones, 0 sin llamar |
| `alcanzables_js.py` | 463 piezas, 463 vivas |
| `atributos_py.py` | OK: ningún atributo de módulo inexistente |
| `css_sin_usar.py` | 63 sin usar (ya conocido) |

---

## F. Servicios externos

**Ninguna llamada a servicios de pago:** ni OpenAI, ni Cartesia, ni Jamendo, ni
FreeSound. Las dos suites nuevas registran **0** intentos de conexión.

**Salvedad:** en la primera tanda de suites existentes, antes de poner el `claude`
falso, `prueba_pasos_guion` lanzó el CLI de Claude real
(`claude -p --model opus`). La red ya estaba cortada por el proxy muerto y el
proceso se mató a los pocos minutos sin respuesta, pero no se puede garantizar
al 100 % que no llegara a intentar salir. Desde entonces esa suite quedó excluida
y cualquier llamada al CLI fue al falso, que solo registró
`claude auth status --json`.

Aparte de las pruebas, se instalaron paquetes de PyPI para preparar el entorno.

---

## G. Compatibilidad

| Elemento | Estado | Verificado por |
|---|---|---|
| Grafo | Intacto | `prueba_firmas` [2] |
| IDs | Intactos | `prueba_firmas` [2] |
| Dependencias | Intactas | `prueba_firmas` [2] |
| `huella()` | Intacta | `prueba_firmas` [2] |
| `_params_globales` | Intacto | `prueba_firmas` [3] |
| Formato de manifiestos | Intacto | `prueba_firmas` [4] |
| Formato de estado | Intacto | `prueba_firmas` [1] y [3] |
| Valores por defecto existentes | Sin cambios | diff |
| Orden guion → voz → revision_audio → assets | Intacto | `prueba_firmas` [2] |
| Contrato del CLI de Claude | Intacto | diff (no se tocó `pasos/cli_claude.py`) |

Además: no se tocó `nucleo/`, el motor de OpenAI ni `p6_assets`, y no se añadió
ningún param global.

---

## H. Problemas encontrados fuera de alcance

| # | Problema | Dónde |
|---|---|---|
| 1 | **FUERA DE ALCANCE — FASE 0:** `prueba_pasos_guion` y `prueba_login` llaman al CLI de Claude real y `pruebas.ps1` las corre siempre; no hay forma de ejecutar la tanda sin salir a la red | `pruebas.ps1`, `pasos/prueba_pasos_guion.py`, `pasos/prueba_login.py` |
| 2 | **FUERA DE ALCANCE — FASE 0:** la comprobación «lo que no se ha podido retirar se dice por su nombre» no está protegida para Linux, a diferencia de la anterior | `pasos/prueba_piezas.py` |
| 3 | **FUERA DE ALCANCE — FASE 0:** `prueba_pasos_visuales` depende de ffprobe y tarda más de 15 minutos en este entorno | `pasos/prueba_pasos_visuales.py` |
| 4 | **FUERA DE ALCANCE — FASE 0:** `requirements.txt` fija versiones que no existen para Python 3.11 (p. ej. `numpy==2.5.2`); solo instalan en 3.12 y no está documentado | `requirements.txt` |
| 5 | **FUERA DE ALCANCE — FASE 0:** `tipografia.py` usa `C:\Windows\Fonts` por defecto si no se define `ESTUDIO_FUENTES` | `pasos/tipografia.py` |
| 6 | **FUERA DE ALCANCE — FASE 0:** siguen las funciones sin uso de la auditoría: `_correr_extraer_estilo` (llama a `estilo.extraer`, que no existe) y `_correr_tono` | `app.py:2456`, `app.py:2477` |
| 7 | **FUERA DE ALCANCE — FASE 0:** la prueba de firmas cubre el núcleo, pero no detectaría código que escriba un valor por defecto nuevo al crear un proyecto (`crear_proyecto`). Le toca a la fase 1 | `app.py` → `crear_proyecto` |

---

## I. Cómo usar la red de seguridad en las fases siguientes

1. **Antes de cada cambio** que toque `nucleo/`, params de pasos, caché o
   proveedores: ejecutar `python nucleo/prueba_firmas.py`.
2. **Si falla:** leer las líneas `CAMBIA …` (ruta exacta, valor base y valor
   actual). Una firma movida aquí es una firma movida en todos los proyectos
   guardados.
3. **Solo si el cambio es deliberado** y se ha decidido pagar sus consecuencias:
   `--escribir-base` y explicarlo en el commit.
4. **Si cambia la receta** (nuevos casos a cubrir): `--congelar`, después
   `--escribir-base`, y revisar el diff de `base.json`.
5. **Fase 1 (fachada de imagen):** añadir la cobertura del punto H.7 (que crear
   un proyecto no escriba params nuevos por defecto) y mantener verdes
   `prueba_firmas` y `prueba_moodboard_descrito`.
