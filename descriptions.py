from __future__ import annotations

import sqlite3


def generate_long_description(connection: sqlite3.Connection, part_id: int) -> str:
    part = connection.execute(
        "SELECT description, measure FROM parts WHERE id = ?", (part_id,)
    ).fetchone()
    if part is None:
        raise ValueError(f"No existe el repuesto {part_id}")

    values = [part["description"].strip()]
    if part["measure"] and part["measure"].strip():
        values.append(part["measure"].strip())

    oems = connection.execute(
        "SELECT oem_code FROM part_oem_codes WHERE part_id = ? ORDER BY upper(oem_code)",
        (part_id,),
    ).fetchall()
    if oems:
        values.append("(OEM: " + ", ".join(row["oem_code"].strip() for row in oems) + ")")

    applications = connection.execute(
        """
        SELECT vb.name AS brand_name, vm.name AS model_name, et.description AS engine_description,
               pa.displacement, pa.year_from, pa.year_to
        FROM part_applications pa
        JOIN vehicle_brands vb ON vb.id = pa.brand_id
        JOIN vehicle_models vm ON vm.id = pa.model_id
        LEFT JOIN engine_types et ON et.id = pa.engine_type_id
        WHERE pa.part_id = ?
        ORDER BY upper(vb.name), upper(vm.name), pa.displacement, pa.year_from, pa.year_to
        """,
        (part_id,),
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    for application in applications:
        pieces = [application["model_name"].strip()]
        if application["engine_description"]:
            pieces.append(application["engine_description"].strip())
        if application["displacement"] is not None:
            pieces.append(f'{application["displacement"]:g}')
        if application["year_from"] and application["year_to"]:
            pieces.append(f'DEL {str(application["year_from"])[-2:]} AL {str(application["year_to"])[-2:]}')
        elif application["year_from"]:
            pieces.append(f'DESDE {application["year_from"]}')
        elif application["year_to"]:
            pieces.append(f'HASTA {application["year_to"]}')
        grouped.setdefault(application["brand_name"].strip(), []).append(" ".join(pieces))

    for brand_name in sorted(grouped, key=str.upper):
        values.append(f'{brand_name.upper()}: {"; ".join(grouped[brand_name])}')
    return "\n".join(values)


def refresh_long_description(connection: sqlite3.Connection, part_id: int) -> str:
    description = generate_long_description(connection, part_id)
    connection.execute(
        "UPDATE parts SET long_description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (description, part_id),
    )
    return description
