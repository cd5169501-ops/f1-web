#!/usr/bin/env python3
"""Descarga las posiciones de pilotos y constructores de 2026.

Consulta la API publica de Jolpica F1 (compatible con Ergast) y guarda un JSON
ordenado en data/posiciones.json, con la fecha de actualizacion.

Si la consulta falla, el archivo anterior queda intacto y el script termina con
codigo 1 para que GitHub Actions marque el error.

Solo usa la biblioteca estandar: no hace falta instalar nada.

Uso:
    python scripts/posiciones.py
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Rutas relativas a la raiz del proyecto (este archivo vive en scripts/).
RAIZ = Path(__file__).resolve().parent.parent
RUTA_SALIDA = RAIZ / "data" / "posiciones.json"

TEMPORADA = 2026
BASE = f"https://api.jolpi.ca/ergast/f1/{TEMPORADA}"
URL_PILOTOS = f"{BASE}/driverStandings.json"
URL_CONSTRUCTORES = f"{BASE}/constructorStandings.json"

INTENTOS = 3
ESPERA_SEGUNDOS = 3


def preparar_salida():
    """Fuerza UTF-8 en la consola para que los acentos se vean bien."""
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            try:
                flujo.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def descargar(url):
    """Baja un JSON con reintentos cortos para errores transitorios."""
    ultimo_error = None

    for intento in range(1, INTENTOS + 1):
        try:
            pedido = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "f1-calendario-posiciones/1.0",
                },
            )
            with urllib.request.urlopen(pedido, timeout=25) as respuesta:
                return json.load(respuesta)
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            ultimo_error = error
            if intento < INTENTOS:
                print(f"Intento {intento} fallo ({error}). Reintentando en {ESPERA_SEGUNDOS}s…")
                time.sleep(ESPERA_SEGUNDOS)

    raise RuntimeError(f"no se pudo consultar {url}: {ultimo_error}")


def obtener_lista(datos, clave):
    """Devuelve la primera StandingsList y valida que tenga datos."""
    try:
        listas = datos["MRData"]["StandingsTable"]["StandingsLists"]
        if not listas:
            raise ValueError("la lista de posiciones vino vacia")
        return listas[0]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"respuesta con formato inesperado: {error}") from error


def a_entero(valor, defecto=0):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return defecto


def a_numero(valor, defecto=0):
    """Puntos: pueden ser enteros o medios puntos (12.5)."""
    try:
        numero = float(str(valor).strip())
    except (TypeError, ValueError):
        return defecto
    return int(numero) if numero.is_integer() else numero


def normalizar_pilotos(standing):
    pilotos = []

    for fila in standing.get("DriverStandings", []):
        piloto = fila.get("Driver") or {}
        equipos = fila.get("Constructors") or []
        equipo = equipos[0] if equipos else {}

        pilotos.append({
            "posicion": a_entero(fila.get("position")),
            "puntos": a_numero(fila.get("points")),
            "victorias": a_entero(fila.get("wins")),
            "codigo": piloto.get("code") or "",
            "nombre": piloto.get("givenName") or "",
            "apellido": piloto.get("familyName") or "",
            "nacionalidad": piloto.get("nationality") or "",
            "equipo": equipo.get("name") or "",
            "equipoId": equipo.get("constructorId") or "",
        })

    return pilotos


def normalizar_constructores(standing):
    constructores = []

    for fila in standing.get("ConstructorStandings", []):
        equipo = fila.get("Constructor") or {}

        constructores.append({
            "posicion": a_entero(fila.get("position")),
            "puntos": a_numero(fila.get("points")),
            "victorias": a_entero(fila.get("wins")),
            "nombre": equipo.get("name") or "",
            "id": equipo.get("constructorId") or "",
            "nacionalidad": equipo.get("nationality") or "",
        })

    return constructores


def leer_anterior():
    """Lee el JSON previo. Si no existe o esta roto, devuelve None."""
    if not RUTA_SALIDA.exists():
        return None

    try:
        with open(RUTA_SALIDA, encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, ValueError) as error:
        print(f"Aviso: no se pudo leer {RUTA_SALIDA.name} ({error}). Se reescribe.")
        return None


def sin_cambios(anterior, nuevo):
    """Compara solo los datos de la tabla, no la fecha de actualizacion."""
    if not isinstance(anterior, dict):
        return False

    for clave in ("temporada", "ronda", "pilotos", "constructores"):
        if anterior.get(clave) != nuevo.get(clave):
            return False

    return True


def guardar(datos):
    """Escribe el JSON de forma atomica para no dejar un archivo a medias."""
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    temporal = RUTA_SALIDA.with_suffix(".json.tmp")

    with open(temporal, "w", encoding="utf-8", newline="\n") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")

    temporal.replace(RUTA_SALIDA)


def main():
    preparar_salida()

    try:
        print(f"Consultando pilotos: {URL_PILOTOS}")
        datos_pilotos = descargar(URL_PILOTOS)

        print(f"Consultando constructores: {URL_CONSTRUCTORES}")
        datos_constructores = descargar(URL_CONSTRUCTORES)

        standing_pilotos = obtener_lista(datos_pilotos, "DriverStandings")
        standing_constructores = obtener_lista(datos_constructores, "ConstructorStandings")

        pilotos = normalizar_pilotos(standing_pilotos)
        constructores = normalizar_constructores(standing_constructores)

        if not pilotos or not constructores:
            raise RuntimeError("la API respondio sin pilotos o sin constructores")

    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        print(f"Se conserva el archivo anterior: {RUTA_SALIDA.name}", file=sys.stderr)
        return 1

    ahora = datetime.now(timezone.utc).replace(microsecond=0)
    nuevo = {
        "temporada": TEMPORADA,
        "ronda": a_entero(standing_pilotos.get("round")),
        "actualizadoUTC": ahora.isoformat().replace("+00:00", "Z"),
        "fuente": {
            "pilotos": URL_PILOTOS,
            "constructores": URL_CONSTRUCTORES,
        },
        "pilotos": pilotos,
        "constructores": constructores,
    }

    anterior = leer_anterior()

    if sin_cambios(anterior, nuevo):
        print(f"Sin cambios desde {anterior.get('actualizadoUTC')}. No se reescribe el archivo.")
        return 0

    try:
        guardar(nuevo)
    except OSError as error:
        print(f"Error: no se pudo escribir {RUTA_SALIDA}: {error}", file=sys.stderr)
        return 1

    print(
        f"Guardado {RUTA_SALIDA.name}: {len(pilotos)} pilotos, "
        f"{len(constructores)} constructores, ronda {nuevo['ronda']}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
