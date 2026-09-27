"""
RED DE SEGURIDAD DE LAS FIRMAS: un proyecto fijo, sus firmas, y una linea base.

Por que existe
--------------
Todo el Estudio se apoya en una promesa: abrir un proyecto guardado no ofrece
regenerar nada que nadie haya cambiado. Esa promesa la sostienen las FIRMAS
(`nucleo/estado.py`), y lo que las mueve no da ningun error: `huella()`
cambiada, una dependencia nueva en `PASOS`, `_params_globales` filtrando otra
clave, un formato de manifiesto que se lee distinto... El sintoma es el mismo en
todos los casos: el video entero en naranja y la pantalla ofreciendo pagar otra
vez ~126 imagenes.

Esta prueba abre un proyecto CONGELADO (`nucleo/fixtures/firmas/proyecto_firmas/`),
calcula todas sus firmas con el codigo de hoy y las compara una a una con las
guardadas en `nucleo/fixtures/firmas/base.json`. Si alguna cambia, dice CUAL,
con el valor de la base y el de ahora.

Que se comprueba
----------------
  1. el grafo: ids, dependencias y si va por unidades, en su orden;
  2. `huella()` sobre un valor fijo (con tildes, anidado, desordenado);
  3. abrir el proyecto NO reescribe ningun fichero;
  4. por paso: estado, firma guardada, firma calculada, firma global, firma
     propia guardada, y la firma de cada unidad (guardada y calculada);
  5. los manifiestos de cada version, incluido uno en el FORMATO VIEJO;
  6. que la RECETA (`nucleo/fixtures/firmas/receta.py`), recorrida hoy con el
     API publico del nucleo, sigue produciendo esas mismas firmas;
  7. que nada de esto abre una conexion de red ni necesita una clave.

Es local, determinista y gratis: solo usa `nucleo/`, que no importa ningun
motor, y un guardian en `socket` hace fallar cualquier conexion.

    python nucleo/prueba_firmas.py                 # comparar con la base
    python nucleo/prueba_firmas.py --escribir-base  # rehacer la base A PROPOSITO
    python nucleo/prueba_firmas.py --congelar       # rehacer el fixture desde la receta

REHACER LA BASE NO ES ARREGLAR LA PRUEBA. Si esto falla, lo primero es entender
por que se ha movido la firma: una firma movida en este fixture es una firma
movida en TODOS los proyectos guardados. Solo cuando el cambio es deliberado y
se ha decidido pagar sus consecuencias se rehace la base, y se dice en el commit.
"""
import argparse
import json
import os
import shutil
import socket
import sys
import tempfile

RAIZ_ESTUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ_ESTUDIO)

from nucleo import Estado, PASOS, Proyecto  # noqa: E402
from nucleo.proyecto import huella  # noqa: E402

CARPETA_FIXTURE = os.path.join(RAIZ_ESTUDIO, "nucleo", "fixtures", "firmas")
PROYECTO_FIJO = os.path.join(CARPETA_FIXTURE, "proyecto_firmas")
FICHERO_BASE = os.path.join(CARPETA_FIXTURE, "base.json")

#: Un valor fijo para vigilar `huella()` por si sola: claves desordenadas,
#: tildes, numeros, anidado y None. Si esto cambia, cambian TODAS las firmas.
VALOR_HUELLA = {"z": [3, 1, 2], "a": {"ñ": "canción", "n": None},
                "f": 1.5, "b": True}

FALLOS = []
CUENTA = [0]


def ok(condicion, texto):
    CUENTA[0] += 1
    if condicion:
        print(f"  ok    {texto}")
    else:
        print(f"  FALLO {texto}")
        FALLOS.append(texto)


def seccion(titulo):
    print(f"\n{titulo}")


# ------------------------------------------------------------ sin red

class _SinRed:
    """Hace fallar cualquier conexion de red mientras esta puesto.

    Nada de lo que se prueba aqui deberia abrir un socket: el nucleo no sabe de
    OpenAI, de Cartesia ni de nadie. Si algun dia lo hiciera, esto lo convierte
    en un fallo con nombre y no en una llamada que sale sin que se note.
    """

    def __init__(self):
        self.intentos = []
        self._original = None

    def __enter__(self):
        self._original = socket.socket.connect
        intentos = self.intentos

        def prohibido(sock, direccion, *a, **k):
            intentos.append(repr(direccion))
            raise OSError(f"prueba_firmas: conexion de red prohibida a {direccion!r}")

        socket.socket.connect = prohibido
        return self

    def __exit__(self, *_):
        socket.socket.connect = self._original


# ------------------------------------------------------------ la foto

def foto(estado):
    """Todo lo que se vigila, en un dict ordenado y comparable con la base."""
    grafo = [{"id": p["id"], "depende_de": list(p["depende_de"]),
              "unidades": bool(p["unidades"])} for p in PASOS]
    pasos = {}
    versiones = {}
    for paso in PASOS:
        pid = paso["id"]
        datos = estado._doc["pasos"][pid]           # lo GUARDADO, tal cual
        guardadas = datos.get("unidades") or {}
        pasos[pid] = {
            "estado": estado.estado_de(pid),
            "firma_guardada": datos.get("firma"),
            "firma_calculada": estado.firma(pid),
            "firma_global": estado.firma_global(pid),
            "firma_propia_guardada": datos.get("firma_propia"),
            "unidades_declaradas": estado.unidades_declaradas(pid),
            "firma_unidad_calculada": {
                u: estado.firma_unidad(pid, u)
                for u in estado.unidades_declaradas(pid)},
            "firma_unidad_guardada": {
                u: (r or {}).get("firma") for u, r in sorted(guardadas.items())},
            "unidades_obsoletas": estado.unidades_obsoletas(pid),
        }
        por_version = {}
        for entrada in estado.versiones(pid):
            manifiesto = estado.manifiesto_version(pid, entrada)
            por_version[f"v{entrada['n']}"] = {
                "firma": entrada.get("firma"),
                "formato": "viejo" if "unidades" in entrada else "actual",
                "manifiesto": {u: (r or {}).get("firma")
                               for u, r in sorted(manifiesto.items())},
            }
        versiones[pid] = por_version
    return {"grafo": grafo, "huella": huella(VALOR_HUELLA),
            "pasos": pasos, "versiones": versiones}


def contar_firmas(datos):
    """Cuantas firmas concretas lleva una foto (para decirlo, no para comparar)."""
    total = 1                                               # la de huella()
    for ficha in datos["pasos"].values():
        total += sum(1 for k in ("firma_guardada", "firma_calculada",
                                 "firma_global", "firma_propia_guardada")
                     if ficha.get(k))
        total += len(ficha["firma_unidad_calculada"])
        total += len(ficha["firma_unidad_guardada"])
    for por_version in datos["versiones"].values():
        for ficha in por_version.values():
            total += 1 + len(ficha["manifiesto"])
    return total


def diferencias(base, actual, ruta=""):
    """[(ruta, valor en la base, valor ahora)] de todo lo que no coincide."""
    if isinstance(base, dict) and isinstance(actual, dict):
        salida = []
        for clave in sorted(set(base) | set(actual)):
            sub = f"{ruta}.{clave}" if ruta else str(clave)
            if clave not in actual:
                salida.append((sub, base[clave], "<falta>"))
            elif clave not in base:
                salida.append((sub, "<no estaba>", actual[clave]))
            else:
                salida.extend(diferencias(base[clave], actual[clave], sub))
        return salida
    if base != actual:
        return [(ruta, base, actual)]
    return []


# ------------------------------------------------------------ ficheros

def _bytes_de(carpeta):
    """{ruta relativa: contenido} de todos los ficheros de una carpeta."""
    salida = {}
    for raiz, _, ficheros in os.walk(carpeta):
        for nombre in ficheros:
            ruta = os.path.join(raiz, nombre)
            with open(ruta, "rb") as fh:
                salida[os.path.relpath(ruta, carpeta)] = fh.read()
    return salida


def _abrir_copia(base_tmp):
    """Copia el proyecto fijo a una carpeta temporal y lo abre desde ahi.

    Se abre la COPIA: aunque abrir no escribe nada (y eso se comprueba), una
    prueba nunca puede dejar sucio el fixture del que dependen las demas.
    """
    destino = os.path.join(base_tmp, "proyecto_firmas")
    shutil.copytree(PROYECTO_FIJO, destino)
    return destino, Estado(Proyecto(destino))


def _cargar_receta():
    sys.path.insert(0, CARPETA_FIXTURE)
    try:
        import receta                                       # noqa: PLC0415
    finally:
        sys.path.remove(CARPETA_FIXTURE)
    return receta


# ------------------------------------------------------------ modos

def congelar():
    """Rehace `proyecto_firmas/` desde la receta. Solo a proposito."""
    receta = _cargar_receta()
    tmp = tempfile.mkdtemp(prefix="firmas_congelar_")
    try:
        proyecto, _ = receta.construir(tmp)
        shutil.rmtree(PROYECTO_FIJO, ignore_errors=True)
        shutil.copytree(proyecto.raiz, PROYECTO_FIJO)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"fixture congelado en {PROYECTO_FIJO}")
    print("AHORA hay que rehacer la base con --escribir-base y mirar el diff.")


def escribir_base():
    """Escribe base.json con las firmas del fixture tal y como las da HOY el codigo."""
    tmp = tempfile.mkdtemp(prefix="firmas_base_")
    try:
        _, estado = _abrir_copia(tmp)
        datos = foto(estado)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    documento = {
        "que_es": ("Linea base de las firmas del proyecto fijo. La compara "
                   "nucleo/prueba_firmas.py. Si cambia, cambian las firmas de "
                   "TODOS los proyectos guardados: no se rehace sin decidirlo."),
        "proyecto": "nucleo/fixtures/firmas/proyecto_firmas",
        "receta": "nucleo/fixtures/firmas/receta.py",
        "valor_huella": VALOR_HUELLA,
        "firmas_verificadas": contar_firmas(datos),
        **datos,
    }
    with open(FICHERO_BASE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(documento, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"base escrita en {FICHERO_BASE}: "
          f"{documento['firmas_verificadas']} firmas")


def comparar():
    with open(FICHERO_BASE, "r", encoding="utf-8") as fh:
        documento = json.load(fh)
    base = {k: documento[k] for k in ("grafo", "huella", "pasos", "versiones")}

    for clave in ("OPENAI_API_KEY", "CARTESIA_API_KEY", "JAMENDO_CLIENT_ID",
                  "FREESOUND_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(clave, None)
    tmp = tempfile.mkdtemp(prefix="firmas_prueba_")
    os.environ["ESTUDIO_SECRETOS"] = os.path.join(tmp, "secretos_vacios")

    try:
        with _SinRed() as red:
            seccion("[1] el proyecto fijo se abre sin tocar nada")
            ok(os.path.isfile(os.path.join(PROYECTO_FIJO, "estado.json")),
               f"existe el fixture {os.path.relpath(PROYECTO_FIJO, RAIZ_ESTUDIO)}")
            destino, estado = _abrir_copia(tmp)
            antes = _bytes_de(destino)
            actual = foto(estado)
            ok(_bytes_de(destino) == antes,
               "abrirlo y calcular todas sus firmas no reescribe ningun fichero")
            ok(_bytes_de(PROYECTO_FIJO) == antes,
               "y la copia abierta es byte a byte el fixture del repositorio")

            seccion("[2] el grafo y huella()")
            ok(actual["grafo"] == base["grafo"],
               "ids, dependencias y unidades del grafo: "
               + " -> ".join(p["id"] for p in actual["grafo"]))
            ok(actual["huella"] == base["huella"],
               f"huella() de un valor fijo = {actual['huella']}")

            seccion(f"[3] firmas del proyecto contra la base "
                    f"({documento.get('firmas_verificadas')} firmas)")
            for pid in [p["id"] for p in PASOS]:
                cambios = diferencias(base["pasos"].get(pid),
                                      actual["pasos"].get(pid), pid)
                ficha = actual["pasos"][pid]
                ok(not cambios,
                   f"{pid:<15} {ficha['estado']:<8} firma {ficha['firma_calculada']}"
                   f"  ({len(ficha['firma_unidad_calculada'])} unidades)")
                for ruta, era, es in cambios:
                    print(f"          CAMBIA {ruta}\n"
                          f"                 base  = {era!r}\n"
                          f"                 ahora = {es!r}")

            seccion("[4] manifiestos de cada version")
            for pid, por_version in actual["versiones"].items():
                if not por_version:
                    continue
                cambios = diferencias(base["versiones"].get(pid), por_version,
                                      f"versiones.{pid}")
                formatos = ", ".join(f"{v}:{f['formato']}"
                                     for v, f in por_version.items())
                ok(not cambios, f"{pid:<15} {formatos}")
                for ruta, era, es in cambios:
                    print(f"          CAMBIA {ruta}\n"
                          f"                 base  = {era!r}\n"
                          f"                 ahora = {es!r}")
            ok(actual["versiones"]["assets"]["v1"]["formato"] == "viejo",
               "assets v1 sigue en el FORMATO VIEJO y se lee (manifiesto en estado.json)")

            seccion("[5] lo que un proyecto guardado tiene que seguir diciendo")
            ok(all(f["estado"] == "listo" for f in actual["pasos"].values()),
               "los 8 pasos abren 'listo': nada ofrece regenerar")
            ok(not any(f["unidades_obsoletas"] for f in actual["pasos"].values()),
               "ninguna unidad obsoleta")
            guion = actual["pasos"]["guion"]
            ok(guion["firma_guardada"] != guion["firma_calculada"]
               and guion["estado"] == "listo",
               "guion corregido a mano: su firma guardada NO cuadra con la "
               "calculada y aun asi esta listo (no hay que re-sellarla)")

            seccion("[6] la receta, recorrida hoy, da las mismas firmas")
            receta = _cargar_receta()
            _, rehecho = receta.construir(os.path.join(tmp, "rehecho"))
            cambios = diferencias(base, foto(rehecho), "receta")
            ok(not cambios,
               "construir el fixture con el API del nucleo de hoy reproduce la base")
            for ruta, era, es in cambios:
                print(f"          CAMBIA {ruta}\n"
                      f"                 base  = {era!r}\n"
                      f"                 ahora = {es!r}")

        seccion("[7] sin red y sin claves")
        ok(not red.intentos,
           f"ninguna conexion de red intentada ({len(red.intentos)})")
        ok(not os.path.exists(os.environ["ESTUDIO_SECRETOS"]),
           "no se ha leido ni creado ningun almacen de claves")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FALLOS:
        print(f"FIRMAS: {len(FALLOS)} de {CUENTA[0]} comprobaciones FALLAN")
        print("Una firma movida aqui es una firma movida en TODOS los proyectos "
              "guardados. Mira la cabecera antes de rehacer la base.")
        return 1
    print(f"FIRMAS OK: {CUENTA[0]} comprobaciones pasan "
          f"({documento.get('firmas_verificadas')} firmas contra la base)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--escribir-base", action="store_true",
                        help="rehace base.json con las firmas de hoy")
    parser.add_argument("--congelar", action="store_true",
                        help="rehace el proyecto fijo desde la receta")
    args = parser.parse_args(argv)
    if args.congelar:
        congelar()
        return 0
    if args.escribir_base:
        escribir_base()
        return 0
    return comparar()


if __name__ == "__main__":
    sys.exit(main())
