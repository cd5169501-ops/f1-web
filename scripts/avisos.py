#!/usr/bin/env python3
"""Avisos por ntfy de las sesiones de F1 (Etapa 2).

Lee el calendario de data/temporada-2026.json, busca las sesiones que empiezan
dentro de los proximos X minutos y manda una notificacion a ntfy. Lo que ya se
aviso queda anotado en data/avisos_enviados.json para no repetirlo.

Variables de entorno:
    NTFY_TOPIC             Tema de ntfy donde publicar (obligatorio para enviar)
    NTFY_URL               Servidor ntfy (por defecto https://ntfy.sh)
    MINUTOS_ANTICIPACION   Minutos de anticipacion (por defecto 60)
    ACTIVAR_NTFY           "0", "false" o "no" para desactivar el envio
    URL_WEB                Opcional: link que se abre al tocar la notificacion

Ejemplos:
    python scripts/avisos.py --dry-run
    python scripts/avisos.py --minutos 30
    python scripts/avisos.py --dry-run --ahora 2026-10-31T20:30:00Z
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Rutas relativas a la raiz del proyecto (este archivo vive en scripts/).
RAIZ = Path(__file__).resolve().parent.parent
RUTA_TEMPORADA = RAIZ / "data" / "temporada-2026.json"
RUTA_REGISTRO = RAIZ / "data" / "avisos_enviados.json"

# Argentina no cambia de hora: siempre UTC-3. Evitamos depender de zoneinfo,
# que en Windows necesita el paquete tzdata aparte.
DESFASE_AR = timedelta(hours=-3)

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# Como se muestra cada tipo de sesion en el aviso.
NOMBRES = {
    "FP1": "Entrenamientos libres 1",
    "FP2": "Entrenamientos libres 2",
    "FP3": "Entrenamientos libres 3",
    "SprintQualy": "Clasificación sprint",
    "Sprint": "Carrera sprint",
    "Qualy": "Clasificación",
    "Carrera": "Carrera",
}

# Prioridad de ntfy: 5 = maxima, 3 = normal.
PRIORIDADES = {
    "Carrera": 5,
    "Qualy": 4,
    "Sprint": 4,
    "SprintQualy": 3,
    "FP1": 3,
    "FP2": 3,
    "FP3": 3,
}

ETIQUETAS = {
    "Carrera": ["checkered_flag"],
    "Qualy": ["stopwatch"],
    "Sprint": ["checkered_flag"],
    "SprintQualy": ["stopwatch"],
}


def preparar_salida():
    """Fuerza UTF-8 en la consola para que los acentos se vean bien."""
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            try:
                flujo.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def leer_json(ruta):
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)


def parsear_fecha(texto):
    """Convierte un ISO 8601 (con Z o con offset) a datetime en UTC."""
    fecha = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def a_iso_utc(fecha):
    return fecha.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def formatear_hora_ar(fecha_utc):
    """Devuelve algo como 'domingo 1 de noviembre a las 18:00'."""
    local = fecha_utc + DESFASE_AR
    return (
        f"{DIAS[local.weekday()]} {local.day} de {MESES[local.month - 1]} "
        f"a las {local.strftime('%H:%M')}"
    )


def clave_sesion(temporada, ronda, sesion):
    """Identificador estable: no cambia aunque se reordene el JSON."""
    return f"{temporada}-r{ronda:02d}-{sesion['tipo']}-{sesion['inicioUTC']}"


def leer_registro():
    """Lee el registro de avisos. Si no existe o esta roto, arranca vacio."""
    if not RUTA_REGISTRO.exists():
        return {"actualizadoUTC": None, "avisos": {}}

    try:
        datos = leer_json(RUTA_REGISTRO)
    except (OSError, ValueError) as error:
        print(f"Aviso: no se pudo leer {RUTA_REGISTRO.name} ({error}). Se empieza de cero.")
        return {"actualizadoUTC": None, "avisos": {}}

    if not isinstance(datos, dict):
        return {"actualizadoUTC": None, "avisos": {}}

    if not isinstance(datos.get("avisos"), dict):
        datos["avisos"] = {}

    return datos


def guardar_registro(registro, ahora):
    """Escribe el registro de forma ordenada (clave por clave)."""
    registro["actualizadoUTC"] = a_iso_utc(ahora)
    registro["avisos"] = dict(sorted(registro["avisos"].items()))

    temporal = RUTA_REGISTRO.with_suffix(".json.tmp")
    with open(temporal, "w", encoding="utf-8", newline="\n") as archivo:
        json.dump(registro, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")
    temporal.replace(RUTA_REGISTRO)


def minutos_hasta(inicio, ahora):
    return (inicio - ahora).total_seconds() / 60


def texto_tiempo(restantes):
    minutos = int(round(restantes))
    if minutos <= 0:
        return "ahora"
    if minutos == 1:
        return "en 1 min"
    return f"en {minutos} min"


def construir_aviso(temporada, carrera, sesion, restantes, url_web):
    """Arma el titulo y el mensaje que se mandan a ntfy."""
    tipo = sesion["tipo"]
    nombre = NOMBRES.get(tipo, tipo)

    titulo = f"F1 · {nombre} {texto_tiempo(restantes)}"

    partes = [f"{carrera['nombre']} — {carrera['circuito']}"]
    partes.append(f"Empieza {formatear_hora_ar(parsear_fecha(sesion['inicioUTC']))} (hora argentina)")
    if url_web:
        partes.append(url_web)

    return {
        "titulo": titulo,
        "mensaje": "\n".join(partes),
        "prioridad": PRIORIDADES.get(tipo, 3),
        "etiquetas": ETIQUETAS.get(tipo, ["stopwatch"]),
    }


def enviar_ntfy(servidor, tema, aviso, url_web):
    """Publica el aviso en ntfy usando el endpoint JSON (acepta UTF-8)."""
    cuerpo = {
        "topic": tema,
        "title": aviso["titulo"],
        "message": aviso["mensaje"],
        "priority": aviso["prioridad"],
        "tags": aviso["etiquetas"],
    }
    if url_web:
        cuerpo["click"] = url_web

    pedido = urllib.request.Request(
        servidor.rstrip("/"),
        data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "f1-calendario-avisos/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(pedido, timeout=20) as respuesta:
            detalle = respuesta.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        cuerpo_error = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ntfy respondio {error.code}: {cuerpo_error[:200]}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"no se pudo conectar con ntfy: {error.reason}") from error

    try:
        return json.loads(detalle).get("id")
    except ValueError:
        return None


def buscar_pendientes(temporada, ahora, minutos, avisos):
    """Sesiones que empiezan dentro de la ventana y todavia no se avisaron."""
    pendientes = []
    ya_avisadas = 0

    for carrera in temporada.get("carreras", []):
        for sesion in carrera.get("sesiones", []):
            try:
                inicio = parsear_fecha(sesion["inicioUTC"])
            except (KeyError, ValueError):
                print(f"Aviso: sesion con hora invalida en la ronda {carrera.get('ronda')}. Se omite.")
                continue

            restantes = minutos_hasta(inicio, ahora)
            if restantes <= 0 or restantes > minutos:
                continue

            clave = clave_sesion(temporada.get("temporada", "2026"), carrera["ronda"], sesion)
            if "ntfy" in avisos.get(clave, {}):
                ya_avisadas += 1
                continue

            pendientes.append((carrera, sesion, clave, restantes))

    pendientes.sort(key=lambda item: item[1]["inicioUTC"])
    return pendientes, ya_avisadas


def leer_argumentos():
    parser = argparse.ArgumentParser(
        description="Manda avisos por ntfy de las sesiones de F1 que estan por empezar."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="muestra los avisos sin enviarlos ni tocar el registro",
    )
    parser.add_argument(
        "--minutos",
        type=int,
        default=None,
        help="minutos de anticipacion (por defecto MINUTOS_ANTICIPACION o 60)",
    )
    parser.add_argument(
        "--ahora",
        default=None,
        help="fecha ISO para simular el momento actual (util para probar)",
    )
    return parser.parse_args()


def main():
    preparar_salida()
    argumentos = leer_argumentos()

    # Momento actual: real o simulado con --ahora.
    if argumentos.ahora:
        try:
            ahora = parsear_fecha(argumentos.ahora)
        except ValueError:
            print(f"Error: --ahora no es una fecha ISO valida: {argumentos.ahora}")
            return 1
    else:
        ahora = datetime.now(timezone.utc).replace(microsecond=0)

    # Ventana de anticipacion: argumento > variable de entorno > 60.
    minutos = argumentos.minutos
    if minutos is None:
        try:
            minutos = int(os.environ.get("MINUTOS_ANTICIPACION", "60"))
        except ValueError:
            print("Error: MINUTOS_ANTICIPACION tiene que ser un numero entero.")
            return 1
    if not 1 <= minutos <= 1440:
        print("Error: los minutos de anticipacion tienen que estar entre 1 y 1440.")
        return 1

    tema = (os.environ.get("NTFY_TOPIC") or "").strip()
    servidor = (os.environ.get("NTFY_URL") or "https://ntfy.sh").strip()
    url_web = (os.environ.get("URL_WEB") or "").strip()
    activar = (os.environ.get("ACTIVAR_NTFY") or "1").strip().lower() not in ("0", "false", "no")

    try:
        temporada = leer_json(RUTA_TEMPORADA)
    except (OSError, ValueError) as error:
        print(f"Error: no se pudo leer {RUTA_TEMPORADA}: {error}")
        return 1

    registro = leer_registro()
    avisos = registro["avisos"]

    pendientes, ya_avisadas = buscar_pendientes(temporada, ahora, minutos, avisos)

    print(f"Momento: {a_iso_utc(ahora)} UTC · ventana: {minutos} min")
    if ya_avisadas:
        print(f"Ya avisadas en esta ventana: {ya_avisadas}")

    if not pendientes:
        print("No hay sesiones por avisar.")
        return 0

    if not argumentos.dry_run:
        if not activar:
            print("NTFY desactivado con ACTIVAR_NTFY: no se envia nada.")
            return 0
        if not tema:
            print("Error: falta la variable de entorno NTFY_TOPIC (el tema de ntfy).")
            return 1

    enviados = 0
    errores = 0

    for carrera, sesion, clave, restantes in pendientes:
        aviso = construir_aviso(temporada, carrera, sesion, restantes, url_web)

        if argumentos.dry_run:
            print("")
            print(f"[DRY-RUN] {aviso['titulo']}")
            for linea in aviso["mensaje"].splitlines():
                print(f"          {linea}")
            print(f"          prioridad: {aviso['prioridad']} · clave: {clave}")
            continue

        try:
            identificador = enviar_ntfy(servidor, tema, aviso, url_web)
            avisos.setdefault(clave, {})["ntfy"] = a_iso_utc(ahora)
            enviados += 1
            detalle = f" (id {identificador})" if identificador else ""
            print(f"Enviado: {aviso['titulo']}{detalle}")
        except RuntimeError as error:
            errores += 1
            print(f"Error al enviar '{aviso['titulo']}': {error}")

    if argumentos.dry_run:
        print("")
        print(f"Dry-run: {len(pendientes)} aviso(s) mostrados, nada enviado.")
        return 0

    if enviados:
        guardar_registro(registro, ahora)

    print(f"Resumen: {enviados} enviado(s), {errores} error(es).")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
