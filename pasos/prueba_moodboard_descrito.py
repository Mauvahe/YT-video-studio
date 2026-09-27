"""
Las laminas de un estilo DESCRITO (`moodboard.dibujar_desde_guia`), sin pagar.

EL FALLO QUE VIGILA
-------------------
El motor de imagen (`motores/imagen_openai/imagen.py`, `generar`) se llama
SIEMPRE con al menos una imagen de referencia: va contra `/v1/images/edits`, y
sin adjuntos la peticion sale con el formato equivocado. Por eso lo primero que
hace `generar` es lanzar `ValueError` si la lista viene vacia.

`dibujar_desde_guia` -- las seis laminas de un estilo creado desde una
descripcion y unas imagenes de apoyo (`_correr_light_referencias` en app.py) --
lo llamaba con `[]`. Asi que ese camino fallaba SIEMPRE, lamina a lamina, dentro
de sus hilos. Y las imagenes estaban ahi: la tarea `referencias` depende de
`guia`, y la guia no se escribe con menos de tres imagenes aportadas
(`estilo.generar_guia`).

Lo que se comprueba:

  1. el contrato del motor de verdad: sin referencias, `generar` lanza (antes de
     tocar la red);
  2. sin imagenes de apoyo, `dibujar_desde_guia` lo dice ANTES de gastar nada y
     sin llamar al motor;
  3. con imagenes de apoyo, cada llamada al motor lleva UNA lamina montada con
     ellas, que existe, y el prompt la presenta como referencia 1 -- lo mismo
     que hace el camino con video (`moodboard.generar`);
  4. las correcciones por eje siguen llegando y solo se dibuja lo pedido;
  5. app.py le pasa las imagenes aportadas;
  6. nada abre una conexion de red ni necesita una clave.

El motor se sustituye por un doble que aplica la MISMA comprobacion de entrada
que el de verdad: nunca se paga una imagen.

    python pasos/prueba_moodboard_descrito.py
"""
import os
import shutil
import socket
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# las claves y el historico, a una carpeta de usar y tirar ANTES de importar
# nada: los motores leen ESTUDIO_SECRETOS al cargarse
_TMP = tempfile.mkdtemp(prefix="moodboard_descrito_")
os.environ["ESTUDIO_SECRETOS"] = os.path.join(_TMP, "secretos")
os.environ.setdefault("ESTUDIO_ESTADISTICAS", os.path.join(_TMP, "estadisticas.json"))
for _clave in ("OPENAI_API_KEY", "CARTESIA_API_KEY"):
    os.environ.pop(_clave, None)

import medios                                                # noqa: E402
import moodboard                                             # noqa: E402

FALLOS = []
CUENTA = [0]
CONEXIONES = []


def ok(condicion, texto):
    CUENTA[0] += 1
    if condicion:
        print(f"  ok    {texto}")
    else:
        print(f"  FALLO {texto}")
        FALLOS.append(texto)


def seccion(titulo):
    print(f"\n{titulo}")


def _sin_red():
    """Cualquier conexion de red pasa a ser un fallo con nombre."""
    def prohibido(sock, direccion, *a, **k):
        CONEXIONES.append(repr(direccion))
        raise OSError(f"conexion de red prohibida en la prueba: {direccion!r}")
    socket.socket.connect = prohibido


def _png(ruta, color):
    from PIL import Image
    Image.new("RGB", (640, 427), color).save(ruta, "PNG")
    return ruta


class MotorFalso:
    """Hace de `imagen.generar` con la MISMA comprobacion de entrada."""

    def __init__(self):
        self.llamadas = []

    def __call__(self, prompt, referencias, *, quality="low", tamano="apaisado",
                 api_key=None, reintentos=6):
        # copiado del contrato de imagen.generar: sin esto el doble aceptaria
        # justo lo que el motor de verdad rechaza
        if not referencias:
            raise ValueError("generar() necesita al menos una imagen de referencia")
        faltan = [r for r in referencias if not os.path.exists(r)]
        if faltan:
            raise ValueError("estas imagenes de referencia no existen: "
                             + ", ".join(faltan))
        self.llamadas.append({"prompt": prompt, "referencias": list(referencias),
                              "quality": quality, "tamano": tamano})
        import io
        from PIL import Image
        buffer = io.BytesIO()
        Image.new("RGB", (64, 43), (200, 200, 200)).save(buffer, "PNG")
        return buffer.getvalue(), {"coste": 0.01, "segundos": 0.0,
                                   "quality": quality, "refs": len(referencias)}


ESTILO = {"guia": {"guia": "flat drawing, thick black outlines",
                   "paleta": ["#112233", "#f2c230"]}}


def prueba_contrato_del_motor_de_verdad(imagen):
    seccion("[1] el contrato del motor de imagen de verdad")
    try:
        imagen.generar("lo que sea", [])
        ok(False, "generar() sin referencias deberia lanzar")
    except ValueError as fallo:
        ok("al menos una imagen de referencia" in str(fallo),
           "generar() sin referencias lanza ValueError antes de salir a la red")


def prueba_sin_imagenes_de_apoyo(falso, carpeta):
    seccion("[2] sin imagenes de apoyo lo dice ANTES de gastar")
    destino = os.path.join(carpeta, "sin_apoyo")
    for referencias in (None, [], [os.path.join(carpeta, "no_existe.png")]):
        try:
            moodboard.dibujar_desde_guia(ESTILO, destino, calidad="low",
                                         referencias=referencias)
            ok(False, f"con referencias={referencias!r} deberia avisar")
        except RuntimeError as fallo:
            ok("imagen de apoyo" in str(fallo),
               f"referencias={referencias!r}: error claro, no un ValueError "
               f"desde dentro de un hilo")
    ok(not falso.llamadas, "y no se ha llamado al motor ni una vez")


def prueba_con_imagenes_de_apoyo(falso, carpeta):
    seccion("[3] con imagenes de apoyo, cada lamina lleva su referencia")
    aportadas = [_png(os.path.join(carpeta, f"apoyo_{i}.png"), color)
                 for i, color in enumerate(((200, 40, 40), (40, 200, 40),
                                            (40, 40, 200)))]
    destino = os.path.join(carpeta, "dibujadas")
    hecho = moodboard.dibujar_desde_guia(ESTILO, destino, calidad="low",
                                         idioma="es", referencias=aportadas)
    ejes = list(moodboard.EJES)
    ok(len(falso.llamadas) == len(ejes),
       f"una llamada por eje ({len(falso.llamadas)} de {len(ejes)})")
    ok(all(len(ll["referencias"]) == 1 for ll in falso.llamadas),
       "cada llamada lleva UNA referencia: la lamina con las imagenes de apoyo")
    lamina = falso.llamadas[0]["referencias"][0]
    ok(os.path.isfile(lamina) and all(ll["referencias"][0] == lamina
                                      for ll in falso.llamadas),
       "la lamina existe y es la misma en todas las llamadas")
    ok(all("Reference image 1 is a STYLE SHEET" in ll["prompt"]
           for ll in falso.llamadas),
       "el prompt presenta el adjunto como referencia 1, igual que con video")
    ok(all(ll["prompt"].startswith("Produce one single full-frame image for a "
                                   "style reference sheet.")
           for ll in falso.llamadas),
       "y conserva el encabezado neutro del camino sin video")
    ok(all("flat drawing, thick black outlines" in ll["prompt"]
           for ll in falso.llamadas),
       "la guia escrita sigue entrando entera en el prompt")
    ok(all(ll["quality"] == "low" and ll["tamano"] == "apaisado"
           for ll in falso.llamadas),
       "la calidad y el tamano que se piden no cambian")
    ok(sorted(hecho["ejes"]) == sorted(ejes) and hecho["origen"] == "descrito",
       "devuelve los mismos campos de siempre (ejes, origen 'descrito')")
    ok(all(os.path.isfile(r) and os.path.dirname(r) == destino
           and os.path.basename(r) == f"{e}.png"
           for r, e in zip(hecho["rutas"], hecho["ejes"])),
       "cada lamina se escribe como <destino>/<eje>.png, como antes")
    ok(abs(hecho["coste_usd"] - 0.01 * len(ejes)) < 1e-9,
       f"el coste es la suma de lo que dice el motor ({hecho['coste_usd']})")
    ok(sorted(os.listdir(destino)) == sorted(["_refs"] + [f"{e}.png" for e in ejes]),
       "en la carpeta solo quedan las laminas y la subcarpeta _refs: la lamina "
       "de apoyo no se cuela entre las referencias")
    ok(os.path.dirname(lamina) == os.path.join(destino, "_refs"),
       "la lamina de apoyo vive en <destino>/_refs")
    return aportadas


def prueba_un_eje_con_correccion(falso, carpeta, aportadas):
    seccion("[4] corregir UNA lamina sigue dibujando solo esa")
    falso.llamadas.clear()
    destino = os.path.join(carpeta, "dibujadas")
    hecho = moodboard.dibujar_desde_guia(
        ESTILO, destino, ejes=["cara"], calidad="low",
        peticiones={"cara": "ojos mas grandes"}, referencias=aportadas)
    ok(hecho["ejes"] == ["cara"] and len(falso.llamadas) == 1,
       "solo el eje pedido")
    ok("Correction, this takes priority: ojos mas grandes"
       in falso.llamadas[0]["prompt"],
       "con su correccion en el prompt")


def prueba_app_pasa_las_aportadas():
    seccion("[5] app.py le pasa las imagenes aportadas")
    with open(os.path.join(RAIZ, "app.py"), "r", encoding="utf-8") as fh:
        fuente = fh.read()
    inicio = fuente.find("def _correr_light_referencias(")
    cuerpo = fuente[inicio:fuente.find("\ndef ", inicio + 10)]
    ok("referencias=_aportadas_del_taller(ctx)" in cuerpo,
       "_correr_light_referencias manda las imagenes del taller")
    ok("ejes=pedidos, peticiones=peticiones" in cuerpo,
       "y sigue mandando los ejes y las correcciones")


def main():
    _sin_red()
    carpeta = os.path.join(_TMP, "trabajo")
    os.makedirs(carpeta, exist_ok=True)
    imagen = medios.motor("imagen_openai/imagen.py")
    original = imagen.generar
    falso = MotorFalso()
    try:
        prueba_contrato_del_motor_de_verdad(imagen)
        imagen.generar = falso
        prueba_sin_imagenes_de_apoyo(falso, carpeta)
        aportadas = prueba_con_imagenes_de_apoyo(falso, carpeta)
        prueba_un_eje_con_correccion(falso, carpeta, aportadas)
        prueba_app_pasa_las_aportadas()
        seccion("[6] sin red y sin claves")
        ok(not CONEXIONES, f"ninguna conexion de red intentada ({len(CONEXIONES)})")
        ok(not os.path.exists(os.path.join(os.environ["ESTUDIO_SECRETOS"],
                                           "claves.json")),
           "no hace falta ninguna clave")
    finally:
        imagen.generar = original
        shutil.rmtree(_TMP, ignore_errors=True)
    print()
    if FALLOS:
        print(f"MOODBOARD DESCRITO: {len(FALLOS)} de {CUENTA[0]} comprobaciones FALLAN")
        return 1
    print(f"MOODBOARD DESCRITO OK: {CUENTA[0]} comprobaciones pasan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
