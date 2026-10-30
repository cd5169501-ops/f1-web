#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Valida los datos de la web antes de publicar cambios.

Uso:
    python scripts/validar_datos.py

Revisa que el JSON de la temporada tenga todas las sesiones, que las horas
sean ISO 8601 en UTC, que no haya campos vacíos ni duplicados y que las
novedades tengan fecha y texto. Sale con código 1 si encuentra errores.
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_TEMPORADA = RAIZ / "data" / "temporada-2026.json"
ARCHIVO_NOVEDADES = RAIZ / "data" / "novedades.json"

# Tipos de sesión permitidos y su duración estimada en minutos.
DURACIONES = {
    "FP1": 60,
    "FP2": 60,
    "FP3": 60,
    "SprintQualy": 30,
    "Sprint": 45,
    "Qualy": 60,
    "Carrera": 120,
}

# Una hora ISO 8601 en UTC, por ejemplo 2026-03-06T01:30:00Z
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

errores = []
advertencias = []


def error(mensaje):
    errores.append(mensaje)


def advertencia(mensaje):
    advertencias.append(mensaje)


def texto_requerido(valor, campo, contexto):
    """Devuelve True si el campo tiene un texto no vacío."""
    if not isinstance(valor, str) or not valor.strip():
        error(f"{contexto}: falta el campo '{campo}' o está vacío")
        return False
    return True


def validar_temporada():
    if not ARCHIVO_TEMPORADA.exists():
        error(f"No existe {ARCHIVO_TEMPORADA}")
        return

    try:
        datos = json.loads(ARCHIVO_TEMPORADA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        error(f"temporada-2026.json no es JSON válido: {exc}")
        return

    for campo in ("temporada", "zonaHoraria", "actualizadoUTC", "carreras"):
        if campo not in datos:
            error(f"temporada-2026.json: falta el campo '{campo}'")

    if datos.get("zonaHoraria") != "America/Argentina/Buenos_Aires":
        error("temporada-2026.json: la zonaHoraria debe ser America/Argentina/Buenos_Aires")

    actualizado = datos.get("actualizadoUTC", "")
    if not ISO_UTC.match(str(actualizado)):
        error(f"temporada-2026.json: 'actualizadoUTC' inválido: {actualizado!r}")

    carreras = datos.get("carreras")
    if not isinstance(carreras, list) or not carreras:
        error("temporada-2026.json: 'carreras' debe ser una lista con al menos un GP")
        return

    rondas_vistas = set()
    total_sesiones = 0
    tipos_por_ronda = {}

    for indice, carrera in enumerate(carreras, start=1):
        contexto = f"carrera #{indice}"
        if not isinstance(carrera, dict):
            error(f"{contexto}: no es un objeto")
            continue

        ronda = carrera.get("ronda")
        if not isinstance(ronda, int) or ronda < 1:
            error(f"{contexto}: 'ronda' debe ser un entero positivo")
        else:
            contexto = f"ronda {ronda}"
            if ronda in rondas_vistas:
                error(f"{contexto}: ronda duplicada")
            rondas_vistas.add(ronda)

        for campo in ("nombre", "pais", "bandera", "circuito", "ciudad", "fuente"):
            texto_requerido(carrera.get(campo), campo, contexto)

        fuente = carrera.get("fuente", "")
        if isinstance(fuente, str) and fuente and not fuente.startswith("https://"):
            error(f"{contexto}: 'fuente' debe ser una URL https")

        if not isinstance(carrera.get("verificado"), bool):
            error(f"{contexto}: 'verificado' debe ser true o false")

        sesiones = carrera.get("sesiones")
        if not isinstance(sesiones, list) or not sesiones:
            error(f"{contexto}: 'sesiones' debe ser una lista con al menos una sesión")
            continue

        tipos = set()
        fechas = []
        for numero, sesion in enumerate(sesiones, start=1):
            ctx = f"{contexto}, sesión #{numero}"
            if not isinstance(sesion, dict):
                error(f"{ctx}: no es un objeto")
                continue

            tipo = sesion.get("tipo")
            if tipo not in DURACIONES:
                error(f"{ctx}: tipo de sesión inválido: {tipo!r}")
            elif tipo in tipos:
                error(f"{ctx}: sesión duplicada de tipo {tipo}")
            else:
                tipos.add(tipo)

            inicio = sesion.get("inicioUTC")
            if not isinstance(inicio, str) or not ISO_UTC.match(inicio):
                error(f"{ctx}: 'inicioUTC' inválido (se espera ISO 8601 UTC): {inicio!r}")
            else:
                try:
                    fecha = datetime.strptime(inicio, "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    error(f"{ctx}: la fecha/hora no existe: {inicio}")
                    continue
                if fecha.year != datos.get("temporada"):
                    error(f"{ctx}: el año de {inicio} no coincide con la temporada")
                fechas.append(fecha)

            duracion = sesion.get("duracionMin")
            if not isinstance(duracion, int) or not 1 <= duracion <= 240:
                error(f"{ctx}: 'duracionMin' debe ser un entero entre 1 y 240")
            elif tipo in DURACIONES and duracion != DURACIONES[tipo]:
                advertencia(
                    f"{ctx}: duración {duracion} min distinta de la estimada "
                    f"({DURACIONES[tipo]} min) para {tipo}"
                )

            total_sesiones += 1

        tipos_por_ronda[ronda] = tipos

        if len(fechas) != len(sesiones):
            continue

        # Las sesiones deben estar en orden cronológico y no pisarse.
        for anterior, siguiente in zip(fechas, fechas[1:]):
            if siguiente <= anterior:
                error(f"{contexto}: las sesiones no están en orden cronológico")
                break

        # Un fin de semana de F1 no dura más de 5 días.
        if fechas[-1] - fechas[0] > timedelta(days=5):
            error(f"{contexto}: las sesiones abarcan más de 5 días")

        # La carrera debe ser la última sesión y durar 120 minutos.
        if "Carrera" not in tipos:
            error(f"{contexto}: falta la carrera")
        else:
            ultima = sesiones[-1]
            if ultima.get("tipo") != "Carrera":
                error(f"{contexto}: la carrera debe ser la última sesión")

        # Todo GP tiene clasificación (tradicional o sprint).
        if "Qualy" not in tipos:
            error(f"{contexto}: falta la clasificación")

        # Si hay sprint, debe estar el fin de semana completo de sprint.
        if "Sprint" in tipos and not {"SprintQualy", "Sprint"} <= tipos:
            error(f"{contexto}: el fin de semana con sprint está incompleto")

        # Los fines de semana normales deben tener las tres prácticas.
        if "Sprint" not in tipos and not {"FP1", "FP2", "FP3"} <= tipos:
            error(f"{contexto}: faltan prácticas libres")

    # El calendario 2026 tiene 23 rondas (Arabia Saudita fue cancelada).
    if len(carreras) != 23:
        advertencia(f"Se encontraron {len(carreras)} carreras; el calendario 2026 tiene 23")

    if rondas_vistas and rondas_vistas != set(range(1, max(rondas_vistas) + 1)):
        error("Las rondas no son consecutivas desde 1")

    print(f"Temporada: {len(carreras)} carreras, {total_sesiones} sesiones")
    print(f"Fines de semana con sprint: {sum(1 for t in tipos_por_ronda.values() if 'Sprint' in t)}")


def validar_novedades():
    if not ARCHIVO_NOVEDADES.exists():
        error(f"No existe {ARCHIVO_NOVEDADES}")
        return

    try:
        datos = json.loads(ARCHIVO_NOVEDADES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        error(f"novedades.json no es JSON válido: {exc}")
        return

    novedades = datos.get("novedades")
    if not isinstance(novedades, list) or not novedades:
        error("novedades.json: 'novedades' debe ser una lista con al menos una novedad")
        return

    fechas = []
    for indice, novedad in enumerate(novedades, start=1):
        contexto = f"novedad #{indice}"
        if not isinstance(novedad, dict):
            error(f"{contexto}: no es un objeto")
            continue

        fecha = novedad.get("fecha")
        if not isinstance(fecha, str) or not FECHA.match(fecha):
            error(f"{contexto}: 'fecha' inválida (se espera AAAA-MM-DD): {fecha!r}")
        else:
            try:
                fechas.append(datetime.strptime(fecha, "%Y-%m-%d"))
            except ValueError:
                error(f"{contexto}: la fecha no existe: {fecha}")

        if "titulo" in novedad:
            texto_requerido(novedad.get("titulo"), "titulo", contexto)
        if not texto_requerido(novedad.get("texto"), "texto", contexto):
            continue
        if len(novedad["texto"]) > 280:
            advertencia(f"{contexto}: el texto supera los 280 caracteres")

    if fechas != sorted(fechas, reverse=True):
        advertencia("Las novedades no están ordenadas de la más nueva a la más vieja")

    print(f"Novedades: {len(novedades)}")


def main():
    validar_temporada()
    validar_novedades()

    for mensaje in advertencias:
        print(f"ADVERTENCIA: {mensaje}")

    if errores:
        print()
        for mensaje in errores:
            print(f"ERROR: {mensaje}")
        print(f"\nValidación fallida: {len(errores)} error(es).")
        return 1

    print("\nValidación OK: los datos tienen formato correcto y no hay horas vacías.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
