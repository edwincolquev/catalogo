from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from typing import Any


def _period(year_from: Any, year_to: Any) -> str:
    first = str(year_from).strip()[-2:].zfill(2) if year_from not in (None, "") else ""
    last = str(year_to).strip()[-2:].zfill(2) if year_to not in (None, "") else ""
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
        brand = str(row["brand_name"] or "").strip().rstrip(" :").upper()
        model = str(row["model_name"] or "").strip().upper()
        displacement = _displacement(row["displacement"])
        engine = str(row["engine_code"] or "").strip().upper()
        year_from = row["year_from"]
        year_to = row["year_to"]
        application = str(row["application_text"] or "").strip().upper()
        key = (brand, model, displacement, engine,
               str(year_from) if year_from is not None else "",
               str(year_to) if year_to is not None else "", application)
        if key in seen:
            continue
        seen.add(key)

        pieces = []
        if brand and brand != previous_brand:
            pieces.append(f"{brand}:")
        if model and (model != previous_model or brand != previous_brand):
            pieces.append(model)
        if displacement and (
            displacement != previous_displacement or model != previous_model or brand != previous_brand
        ):
            pieces.append(displacement)
        if engine:
            pieces.append(engine)
        period = _period(year_from, year_to)
        if period:
            pieces.append(period)
        if application:
            pieces.append(application)
        if pieces:
            details.append(" ".join(pieces))
        previous_brand, previous_model, previous_displacement = brand, model, displacement
    return "; ".join(details)


def generate_application_summary(connection: sqlite3.Connection, part_id: int) -> str:
    """Texto de aplicaciones siguiendo la columna Resumen!N del VBA."""
    applications = connection.execute(
        """SELECT vb.name AS brand_name, vm.name AS model_name, et.code AS engine_code,
                  pa.displacement, pa.year_from, pa.year_to, pa.application_text
           FROM part_applications pa
           JOIN vehicle_brands vb ON vb.id = pa.brand_id
           JOIN vehicle_models vm ON vm.id = pa.model_id
           LEFT JOIN engine_types et ON et.id = pa.engine_type_id
           WHERE pa.part_id = ? ORDER BY pa.id""",
        (part_id,),
    ).fetchall()
    return format_application_rows(applications)


def generate_long_description(connection: sqlite3.Connection, part_id: int) -> str:
    part = connection.execute(
        "SELECT description, measure FROM parts WHERE id = ?", (part_id,)
    ).fetchone()
    if part is None:
        raise ValueError(f"No existe el repuesto {part_id}")
    values = [part["description"].strip()] if part["description"] and part["description"].strip() else []
    if part["measure"] and part["measure"].strip():
        values.append(part["measure"].strip())
    oems = connection.execute(
        "SELECT oem_code FROM part_oem_codes WHERE part_id = ? ORDER BY upper(oem_code)",
        (part_id,),
    ).fetchall()
    if oems:
        values.append("(OEM: " + ", ".join(row["oem_code"].strip() for row in oems) + ")")
    applications = generate_application_summary(connection, part_id)
    if applications:
        values.append(applications)
    return "\n".join(values)


def refresh_long_description(connection: sqlite3.Connection, part_id: int) -> str:
    description = generate_long_description(connection, part_id)
    connection.execute(
        "UPDATE parts SET long_description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (description, part_id),
    )
    return description
