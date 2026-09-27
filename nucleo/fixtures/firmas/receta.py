"""
La RECETA del proyecto fijo con el que se vigilan las firmas.

Que es
------
Un proyecto pequeno e inventado -- cuatro planos, un personaje, ningun dato de
nadie -- construido con el API publico del nucleo (`Estado.set_params`,
`actualizar_params`, `completar`), igual que lo construyen los pasos de verdad.
No llama a ningun modelo, no genera ninguna imagen y no sale a la red: los
pasos se "completan" con salidas escritas aqui, que es lo unico que el nucleo
necesita para firmar.

La copia CONGELADA de lo que produce esta receta vive al lado, en
`proyecto_firmas/`, y es lo que abre `nucleo/prueba_firmas.py`. La receta se
guarda para dos cosas:

  1. poder leer de donde sale cada dato del fixture sin descifrar estado.json;
  2. comprobar que el MISMO recorrido, hecho hoy con el codigo de hoy, sigue
     dando las mismas firmas que el congelado (si `completar` o
     `propagar_dependencias` cambiasen su forma de firmar, esto lo canta).

Por que tiene la forma que tiene
--------------------------------
Reproduce las formas que tienen los proyectos reales en los sitios donde una
firma se puede mover sin que nadie lo note:

  - `guion` con una CORRECCION A MANO de sus bloques despues de completarse:
    su `firma` guardada ya no cuadra con la calculada y aun asi el paso sigue
    `listo` (`CORRECCIONES`, `firma_propia`). Es la trampa n.º 1 de CLAUDE.md
    («no re-selles lo que la mudanza no movio»).
  - `assets` por UNIDAD, con los ids de siempre (`escena:S001`, `asset:...`),
    la cartela decidida por unidad y las firmas de los assets PROPAGADAS a las
    escenas (`assets` + `huella_assets`), como hace `p6_assets.propagar_dependencias`.
  - `assets` con DOS versiones: la v1 reescrita en el FORMATO VIEJO (manifiesto
    dentro de estado.json) y la v2 en el actual (`_versiones/v2.json`). CLAUDE.md
    dice que el viejo se sigue leyendo para siempre.
  - `callouts` y `render` heredando las unidades por el DAG.

Los params de `assets` llevan las claves reales (`calidad`, `motor_imagen`,
`estilo`, `catalogo`...) con los valores por defecto de hoy: si una fase
posterior empezara a ESCRIBIR una clave nueva por defecto, se veria al rehacer
esta receta.

Ninguna ruta del fixture es absoluta: el mismo estado firma igual en cualquier
carpeta y en cualquier maquina.

    python nucleo/prueba_firmas.py --congelar      # rehace proyecto_firmas/
"""
import copy
import os
import sys

RAIZ_ESTUDIO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if RAIZ_ESTUDIO not in sys.path:
    sys.path.insert(0, RAIZ_ESTUDIO)

from nucleo import Estado, Proyecto  # noqa: E402
from nucleo.proyecto import huella  # noqa: E402

NOMBRE = "Proyecto firmas"

BLOQUES = [
    {"id": "B01", "texto": "En un puerto pequeno, una grua se detiene."},
    {"id": "B02", "texto": "Ana revisa la lista de carga dos veces."},
    {"id": "B03", "texto": "Faltan cuatro mil cajas."},
    {"id": "B04", "texto": "Nadie en el muelle sabe donde estan."},
]

#: Lo que se corrige A MANO en el guion despues de generarlo.
BLOQUE_CORREGIDO = {"id": "B02", "texto": "Ana revisa la lista de carga tres veces."}

ESCENAS = ("S001", "S002", "S003", "S004")

#: Que assets usa cada escena (lo que p6 devuelve como "dependencias").
DEPENDENCIAS = {
    "escena:S001": ["asset:set_muelle"],
    "escena:S002": ["asset:ana", "asset:set_muelle"],
    "escena:S004": ["asset:set_muelle"],
}

PARAMS_ASSETS = {
    "calidad": "low",
    "estilo": {"prompt": "", "referencias": []},
    "min_s": 3.0,
    "max_s": 6.0,
    "min_s_rotulos": 3.0,
    "semilla": 7,
    "motor_imagen": "openai",
    "imagenes_previas": [],
    "referencias_reales": [],
    "cadenas": 0,
    "catalogo": {
        "sets": [{"nombre": "muelle", "descripcion": "un muelle de carga al amanecer",
                  "palabras": ["puerto", "muelle", "grua"]}],
        "reparto": [{"nombre": "ana", "descripcion": "una inspectora de aduanas"}],
    },
    "unidades": {
        "escena:S003": {"cartela": {"plantilla": "cifra", "texto": "4.000 cajas"}},
        "escena:S002": {"direccion": "Ana en primer termino, mirando la lista"},
    },
}


def _salidas_escena(sid):
    return {"imagen": f"escenas/{sid}.png", "prompt": f"prompt de {sid}",
            "origen": "generada"}


def construir(base):
    """Construye el proyecto en `base` y lo devuelve (Proyecto, Estado)."""
    proyecto = Proyecto.crear(base, NOMBRE)
    estado = Estado(proyecto)

    estado.set_params("ingesta", {
        "texto": " ".join(b["texto"] for b in BLOQUES),
        "titulo": "El puerto",
    })
    estado.completar("ingesta", {"archivo": "ingesta.json", "trozos": 4,
                                 "sin_tiempos": True})

    estado.set_params("brief", {"duracion_s": 60, "idioma_salida": "es",
                                "velocidad": "normal", "hueco_minimo": 1.0,
                                "instrucciones": "seco y sin adjetivos"})
    estado.completar("brief", {"palabras_min": 90, "palabras_max": 170})

    estado.set_params("guion", {"bloques": copy.deepcopy(BLOQUES),
                                "cta": {"cuantas": 0}})
    estado.completar("guion", {"archivo": "guion.json", "bloques": len(BLOQUES)})
    # LA CORRECCION A MANO: cambia `bloques`, que esta en CORRECCIONES.
    corregidos = [BLOQUE_CORREGIDO if b["id"] == BLOQUE_CORREGIDO["id"] else b
                  for b in BLOQUES]
    estado.actualizar_params("guion", {"bloques": copy.deepcopy(corregidos)})

    estado.set_params("voz", {"preset": "", "voz_id": "voz-ficticia-0001",
                              "modelo": "sonic-3.5", "idioma": "es",
                              "velocidad": "normal", "hueco_minimo": 1.0})
    estado.completar("voz", {"archivo": "narracion.wav", "duracion": 14.2})

    estado.set_params("revision_audio", {"comentarios": []})
    estado.completar("revision_audio", {"archivo": "narracion.wav",
                                        "bloques_modificados": []})

    # assets v1: escenas y assets del reparto, por unidad
    estado.set_params("assets", copy.deepcopy(PARAMS_ASSETS))
    unidades_v1 = {f"escena:{sid}": _salidas_escena(sid) for sid in ESCENAS}
    unidades_v1["asset:ana"] = {"imagen": "reparto/ana.png"}
    unidades_v1["asset:set_muelle"] = {"imagen": "sets/muelle.png"}
    estado.completar("assets", {"resumen": "4 planos y 2 assets"}, unidades_v1)

    # lo que hace p6_assets.propagar_dependencias antes de completar: mete en
    # cada escena la firma de los assets que usa (del_propio_paso=True)
    previos = estado.params("assets").get("unidades") or {}
    cambios = {}
    for escena, usados in sorted(DEPENDENCIAS.items()):
        firmas = {uid: estado.firma_unidad("assets", uid) for uid in sorted(usados)}
        ficha = dict(previos.get(escena) or {})
        ficha["assets"] = sorted(usados)
        ficha["huella_assets"] = huella(firmas)
        cambios[escena] = ficha
    estado.actualizar_params("assets", {"unidades": cambios}, del_propio_paso=True)

    # assets v2: la pasada que propaga sella en la MISMA version las escenas
    # cuya firma acaba de mover (S001, S002 y S004); S002 ademas trae imagen
    # nueva. S003 (la cartela) no usa ningun asset y se queda como estaba.
    v2 = {f"escena:{sid}": _salidas_escena(sid) for sid in ("S001", "S004")}
    v2["escena:S002"] = dict(_salidas_escena("S002"), imagen="escenas/S002_v2.png")
    estado.completar("assets", {"resumen": "propagadas y rehecho S002"}, v2)

    estado.set_params("callouts", {"diseno": {"plantilla": "banda",
                                              "color": "#f2c230"}})
    estado.completar("callouts", {"resumen": "capas"},
                     {f"escena:{sid}": {"capa": f"capas/{sid}.svg"}
                      for sid in ESCENAS})

    estado.set_params("render", {"fps": 30, "resolucion": [1920, 1080],
                                 "calidad_video": "alta"})
    estado.completar("render", {"mp4": "video.mp4", "duracion": 14.2},
                     {f"escena:{sid}": {"clip": f"clips/{sid}.mp4"}
                      for sid in ESCENAS})

    _pasar_v1_de_assets_al_formato_viejo(proyecto, estado)
    return proyecto, Estado(proyecto)


def _pasar_v1_de_assets_al_formato_viejo(proyecto, estado):
    """La v1 de assets con su manifiesto DENTRO de estado.json, como antes.

    Es exactamente lo que deshace `herramientas/migrar_manifiestos.py`, al reves:
    el manifiesto vuelve a la entrada y el fichero `_versiones/v1.json` se borra.
    Un proyecto que llegue de fuera sin migrar tiene esta forma.
    """
    from nucleo.proyecto import escribir_json, leer_json  # noqa: PLC0415

    manifiesto = estado.manifiesto_version("assets", 1)
    ruta_estado = proyecto.ruta("estado.json")
    doc = leer_json(ruta_estado)
    for entrada in doc["pasos"]["assets"]["versiones"]:
        if entrada.get("n") == 1:
            entrada.pop("n_unidades", None)
            entrada["unidades"] = manifiesto
    escribir_json(ruta_estado, doc)
    os.remove(proyecto.ruta("pasos", "assets", "_versiones", "v1.json"))
