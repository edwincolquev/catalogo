from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any


def _period(anio_desde: Any, anio_hasta: Any) -> str:
    first = str(anio_desde).strip()[-2:].zfill(2) if anio_desde not in (None, "") else ""
    last = str(anio_hasta).strip()[-2:].zfill(2) if anio_hasta not in (None, "") else ""
    if first and last:
        return f"DEL {first} AL {last}"
    if first:
        return f"DESDE {first}"
    if last:
        return f"HASTA {last}"
    return ""


def _displacement(value: Any) -> str:
    if value is None or value == "":
        return ""
    return (f"{value:g}" if isinstance(value, (float, int)) else str(value).strip()).replace(".", ",").upper()


def format_application_rows(rows: Iterable[Mapping[str, Any]]) -> str:
    """Reproduce la compactación de ObtenerDescripcion, respetando el orden recibido."""
    seen: set[tuple[str, ...]] = set()
    previous_brand = previous_model = previous_displacement = ""
    details: list[str] = []
    for row in rows:
        brand = str(row["nombre_marca"] or "").strip().rstrip(" :").upper()
        model = str(row["nombre_modelo"] or "").strip().upper()
        cilindrada = _displacement(row["cilindrada"])
        engine = str(row["codigo_motor"] or "").strip().upper()
        anio_desde = row["anio_desde"]
        anio_hasta = row["anio_hasta"]
        application = str(row["texto_aplicacion"] or "").strip().upper()
        key = (brand, model, cilindrada, engine,
               str(anio_desde) if anio_desde is not None else "",
               str(anio_hasta) if anio_hasta is not None else "", application)
        if key in seen:
            continue
        seen.add(key)

        pieces = []
        if brand and brand != previous_brand:
            pieces.append(f"{brand}:")
        if model and (model != previous_model or brand != previous_brand):
            pieces.append(model)
        if cilindrada and (
            cilindrada != previous_displacement or model != previous_model or brand != previous_brand
        ):
            pieces.append(cilindrada)
        if engine:
            pieces.append(engine)
        period = _period(anio_desde, anio_hasta)
        if period:
            pieces.append(period)
        if application:
            pieces.append(application)
        if pieces:
            details.append(" ".join(pieces))
        previous_brand, previous_model, previous_displacement = brand, model, cilindrada
    return "; ".join(details)


def generate_application_summary(connection: sqlite3.Connection, repuesto_id: int) -> str:
    """Texto de aplicaciones siguiendo la columna Resumen!N del VBA."""
    applications = connection.execute(
        """SELECT vb.nombre AS nombre_marca, vm.nombre AS nombre_modelo, et.codigo AS codigo_motor,
                  pa.cilindrada, pa.anio_desde, pa.anio_hasta, pa.texto_aplicacion
           FROM aplicaciones_repuestos pa
           JOIN marcas_vehiculos vb ON vb.id = pa.marca_id
           JOIN modelos_vehiculos vm ON vm.id = pa.modelo_id
           LEFT JOIN tipos_motor et ON et.id = pa.tipo_motor_id
           WHERE pa.repuesto_id = ? ORDER BY pa.id""",
        (repuesto_id,),
    ).fetchall()
    return format_application_rows(applications)


def generate_long_description(connection: sqlite3.Connection, repuesto_id: int) -> str:
    part = connection.execute(
        "SELECT descripcion, medida FROM repuestos WHERE id = ?", (repuesto_id,)
    ).fetchone()
    if part is None:
        raise ValueError(f"No existe el repuesto {repuesto_id}")
    values = [part["descripcion"].strip()] if part["descripcion"] and part["descripcion"].strip() else []
    if part["medida"] and part["medida"].strip():
        values.append(part["medida"].strip())
    oems = connection.execute(
        "SELECT codigo_oem FROM codigos_oem WHERE repuesto_id = ? ORDER BY upper(codigo_oem)",
        (repuesto_id,),
    ).fetchall()
    if oems:
        values.append("(OEM: " + ", ".join(row["codigo_oem"].strip() for row in oems) + ")")
    return "\n".join(values)


def refresh_long_description(connection: sqlite3.Connection, repuesto_id: int) -> str:
    descripcion = generate_long_description(connection, repuesto_id)
    connection.execute(
        "UPDATE repuestos SET descripcion_larga = ?, fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = ?",
        (descripcion, repuesto_id),
    )
    return descripcion
