from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from database import DEFAULT_DB_PATH, get_connection
from descriptions import refresh_long_description

COLUMN_ALIASES = {
    "supplier_code": {"supplier_code", "codigo_proveedor", "proveedor_codigo", "parts_supplier_code"},
    "sap_code": {"sap", "sap_code", "codigo_sap", "codigo", "codigo_repuesto", "parts_sap_code"},
    "description": {"description", "descripcion", "descripcion_repuesto", "nombre", "parts_description"},
    "measure": {"measure", "medida", "dimensiones", "parts_measure"},
    "brand_name": {"brand", "marca", "marca_repuesto", "parts_brand_name"},
    "oem_code": {"oem", "oem_code", "codigo_oem", "codigo_original", "part_oem_code_oem_code", "part_oem_codes_oem_code"},
    "reference_type": {"reference_type", "part_cross_references_reference_type"},
    "reference_code": {"reference_code", "referencia", "referencia_cruzada", "equivalencia", "part_cross_references_reference_code"},
    "vehicle_brand": {"vehicle_brands_name", "vehicle_brand_name"},
    "vehicle_model": {"vehicle_model_name", "vehicle_models_name"},
    "engine_code": {"engine_type_code", "engine_types_code"},
    "engine_description": {"engine_type_description", "engine_types_description"},
    "displacement": {"applications_displacement", "part_applications_displacement"},
    "year_from": {"applications_year_from", "part_applications_year_from"},
    "year_to": {"applications_year_to", "part_applications_year_to"},
    "application_text": {"applications_application", "applications_application_text", "part_applications_application_text", "aplicacion"},
}


def normalize_column(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value).strip().lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def map_columns(columns: list[Any]) -> dict[str, str]:
    normalized = {normalize_column(column): str(column) for column in columns}
    result = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in sorted(aliases):
            if alias in normalized:
                result[target] = normalized[alias]
                break
    return result


def read_source(path: str | Path, sheet_name: str | int = 0) -> pd.DataFrame:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        options = dict(sep=None, engine="python", encoding="utf-8-sig", dtype=str, keep_default_na=False)
        first = pd.read_csv(source, nrows=0, **options)
        master = any(str(c).strip().upper() == "PARTS" for c in first.columns)
        dataframe = pd.read_csv(source, header=1 if master else 0, **options)
    elif suffix in {".xlsx", ".xls", ".xlsm"}:
        options = dict(sheet_name=sheet_name, dtype=str, keep_default_na=False)
        first = pd.read_excel(source, nrows=0, **options)
        master = any(str(c).strip().upper() == "PARTS" for c in first.columns)
        dataframe = pd.read_excel(source, header=1 if master else 0, **options)
    else:
        raise ValueError("Formato no soportado. Use CSV o Excel.")
    dataframe.attrs["first_data_row"] = 3 if master else 2
    dataframe.attrs["master_format"] = master
    return dataframe


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    result = str(value).strip()
    return "" if result.upper() in {"N/A", "N/D"} else result


def _key(value: str) -> str:
    return value.strip().upper()


def _split_codes(value: str) -> list[str]:
    return list(dict.fromkeys(c.strip() for c in re.split(r"[,;|]", value) if c.strip()))


def _application_warnings(data: dict[str, Any]) -> list[str]:
    fields = ("vehicle_brand", "vehicle_model", "engine_code", "engine_description", "displacement", "year_from", "year_to", "application_text")
    if not any(data.get(field) for field in fields):
        return []
    warnings = []
    if not data.get("vehicle_brand") or not data.get("vehicle_model"):
        warnings.append("Aplicación sin marca y modelo completos")
    if data.get("engine_description") and not data.get("engine_code"):
        warnings.append("Descripción de motor sin código")
    if data.get("engine_code") and re.search(r"\b(DEL|DESDE|HASTA|AL)\b|;", data["engine_code"], re.I):
        warnings.append("Motor contiene texto de aplicación")
    if data.get("displacement"):
        try:
            if float(data["displacement"].replace(",", ".")) <= 0:
                raise ValueError
        except ValueError:
            warnings.append("Cilindrada inválida")
    years = {}
    for field in ("year_from", "year_to"):
        if data.get(field):
            try:
                years[field] = int(data[field])
                if not 1886 <= years[field] <= 2200:
                    raise ValueError
            except ValueError:
                warnings.append(f"{field} inválido")
    if years.get("year_from", 0) > years.get("year_to", 2200):
        warnings.append("Rango de años invertido")
    return warnings


def stage_dataframe(dataframe: pd.DataFrame, file_name: str, sheet_name: str | None = None,
                    db_path: str | Path = DEFAULT_DB_PATH) -> int:
    mapping = map_columns(list(dataframe.columns))
    if "supplier_code" not in mapping and "sap_code" not in mapping:
        raise ValueError("Falta una columna de código de proveedor o código SAP")
    master = bool(dataframe.attrs.get("master_format"))
    if master and "supplier_code" not in mapping:
        raise ValueError("El maestro necesita parts.supplier_code")
    first_row = int(dataframe.attrs.get("first_data_row", 2))
    staged = []
    last_supplier = last_brand = last_model = ""
    for _, row in dataframe.iterrows():
        data = {target: _text(row[source]) for target, source in mapping.items()}
        has_application_data = any(data.get(field) for field in (
            "vehicle_brand", "vehicle_model", "engine_code", "engine_description", "displacement", "year_from", "year_to", "application_text"
        ))
        if master:
            supplied = data.get("supplier_code", "")
            if supplied and _key(supplied) != _key(last_supplier):
                last_brand = last_model = ""
            data["supplier_code"] = supplied or last_supplier
            last_supplier = data["supplier_code"]
            brand = data.get("vehicle_brand", "")
            if brand:
                brand = brand.rstrip(" :").strip()
                if _key(brand) != _key(last_brand):
                    last_model = ""
                last_brand = brand
            data["vehicle_brand"] = last_brand
            if data.get("vehicle_model"):
                last_model = data["vehicle_model"]
            data["vehicle_model"] = last_model
        errors = []
        if not data.get("supplier_code") and not data.get("sap_code"):
            errors.append("Falta código de proveedor o SAP")
        if master and not data.get("supplier_code"):
            errors.append("Falta código de proveedor")
        if data.get("reference_code") and not data.get("reference_type"):
            if master:
                errors.append("La referencia necesita reference_type")
            else:
                data["reference_type"] = "IMPORTADO"
        warnings = _application_warnings(data) if has_application_data else []
        data["has_application_data"] = has_application_data
        data["application_warnings"] = warnings
        staged.append((first_row + len(staged), row.to_dict(), data, errors, warnings))
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO import_batches (file_name, sheet_name, total_rows, valid_rows, error_rows) VALUES (?, ?, ?, ?, ?)",
            (file_name, sheet_name, len(staged), sum(not x[3] for x in staged), sum(bool(x[3]) for x in staged)),
        )
        batch_id = int(cursor.lastrowid)
        for number, raw, data, errors, warnings in staged:
            connection.execute(
                """INSERT INTO import_staging_rows
                   (batch_id, row_number, raw_data, normalized_data, status, errors)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (batch_id, number, json.dumps(raw, default=str, ensure_ascii=False),
                 json.dumps(data, ensure_ascii=False), "error" if errors else "valid",
                 "; ".join(errors + [f"Aviso: {w}" for w in warnings]) or None),
            )
    return batch_id


def _find_part(connection: sqlite3.Connection, data: dict[str, Any]) -> sqlite3.Row | None:
    supplier, sap = data.get("supplier_code"), data.get("sap_code")
    by_supplier = connection.execute(
        "SELECT * FROM parts WHERE upper(trim(supplier_code)) = ?", (_key(supplier),)
    ).fetchone() if supplier else None
    by_sap = connection.execute(
        "SELECT * FROM parts WHERE upper(trim(sap_code)) = ?", (_key(sap),)
    ).fetchone() if sap else None
    if by_supplier and by_sap and by_supplier["id"] != by_sap["id"]:
        raise ValueError(f"El proveedor {supplier} y SAP {sap} pertenecen a repuestos distintos")
    part = by_supplier or by_sap
    if part and supplier and part["supplier_code"] and _key(part["supplier_code"]) != _key(supplier):
        raise ValueError(f"El SAP {sap} ya pertenece al proveedor {part['supplier_code']}")
    return part


def _find_or_create(connection: sqlite3.Connection, table: str, field: str, value: str,
                    extra: tuple[str, Any] | None = None) -> int:
    if extra:
        extra_field, extra_value = extra
        row = connection.execute(
            f"SELECT id FROM {table} WHERE {extra_field} = ? AND upper(trim({field})) = ?",
            (extra_value, _key(value)),
        ).fetchone()
        if row:
            return int(row["id"])
        cursor = connection.execute(
            f"INSERT INTO {table} ({extra_field}, {field}) VALUES (?, ?)", (extra_value, value)
        )
    else:
        row = connection.execute(
            f"SELECT id FROM {table} WHERE upper(trim({field})) = ?", (_key(value),)
        ).fetchone()
        if row:
            return int(row["id"])
        cursor = connection.execute(f"INSERT INTO {table} ({field}) VALUES (?)", (value,))
    return int(cursor.lastrowid)


def save_application(connection: sqlite3.Connection, part_id: int, data: dict[str, Any],
                     application_id: int | None = None) -> bool:
    warnings = _application_warnings(data)
    if warnings:
        raise ValueError("; ".join(warnings))
    if not data.get("vehicle_brand") or not data.get("vehicle_model"):
        raise ValueError("Marca y modelo son obligatorios")
    brand_id = _find_or_create(connection, "vehicle_brands", "name", data["vehicle_brand"])
    model_id = _find_or_create(connection, "vehicle_models", "name", data["vehicle_model"], ("brand_id", brand_id))
    engine_id = None
    engine_changed = False
    if data.get("engine_code"):
        engine_id = _find_or_create(connection, "engine_types", "code", data["engine_code"])
        if data.get("engine_description"):
            previous = connection.execute("SELECT description FROM engine_types WHERE id = ?", (engine_id,)).fetchone()[0]
            if data["engine_description"] != (previous or ""):
                connection.execute("UPDATE engine_types SET description = ? WHERE id = ?",
                                   (data["engine_description"], engine_id))
                engine_changed = True
                related = connection.execute(
                    "SELECT DISTINCT part_id FROM part_applications WHERE engine_type_id = ?", (engine_id,)
                ).fetchall()
                for row in related:
                    refresh_long_description(connection, int(row["part_id"]))
    displacement = float(data["displacement"].replace(",", ".")) if data.get("displacement") else None
    year_from = int(data["year_from"]) if data.get("year_from") else None
    year_to = int(data["year_to"]) if data.get("year_to") else None
    application_text = data.get("application_text") or None
    exists = connection.execute(
        """SELECT 1 FROM part_applications WHERE part_id = ? AND brand_id = ? AND model_id = ?
           AND engine_type_id IS ? AND displacement IS ? AND year_from IS ? AND year_to IS ?
           AND upper(trim(coalesce(application_text, ''))) = ?
           AND (? IS NULL OR id <> ?)""",
        (part_id, brand_id, model_id, engine_id, displacement, year_from, year_to,
         _key(application_text or ""), application_id, application_id),
    ).fetchone()
    if exists:
        return engine_changed
    if application_id is None:
        connection.execute(
            """INSERT INTO part_applications
               (part_id, brand_id, model_id, engine_type_id, displacement, year_from, year_to, application_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (part_id, brand_id, model_id, engine_id, displacement, year_from, year_to, application_text),
        )
    else:
        connection.execute(
            """UPDATE part_applications SET brand_id = ?, model_id = ?, engine_type_id = ?,
               displacement = ?, year_from = ?, year_to = ?, application_text = ?
               WHERE id = ? AND part_id = ?""",
            (brand_id, model_id, engine_id, displacement, year_from, year_to,
             application_text, application_id, part_id),
        )
    return True


def confirm_batch(batch_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> tuple[int, int]:
    inserted_ids: set[int] = set()
    changed_ids: set[int] = set()
    with get_connection(db_path) as connection:
        batch = connection.execute("SELECT status FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
        if batch is None:
            raise ValueError("La carga no existe")
        if batch["status"] != "staged":
            raise ValueError("La carga ya fue procesada")
        rows = connection.execute(
            "SELECT normalized_data FROM import_staging_rows WHERE batch_id = ? AND status = 'valid' ORDER BY row_number",
            (batch_id,),
        ).fetchall()
        for row in rows:
            data = json.loads(row["normalized_data"])
            part = _find_part(connection, data)
            if part is None:
                cursor = connection.execute(
                    """INSERT INTO parts (supplier_code, sap_code, description, measure, brand_name)
                       VALUES (?, ?, ?, ?, ?)""",
                    tuple(data.get(f) or None for f in (
                        "supplier_code", "sap_code", "description", "measure", "brand_name"
                    )),
                )
                part_id = int(cursor.lastrowid)
                inserted_ids.add(part_id)
                changed_ids.add(part_id)
            else:
                part_id = int(part["id"])
                updates = {
                    field: data[field]
                    for field in ("supplier_code", "sap_code", "description", "measure", "brand_name")
                    if data.get(field) and data[field] != (part[field] or "")
                }
                if updates:
                    assignments = ", ".join(f"{field} = ?" for field in updates)
                    connection.execute(
                        f"UPDATE parts SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (*updates.values(), part_id),
                    )
                    changed_ids.add(part_id)
            for code in _split_codes(data.get("oem_code", "")):
                exists = connection.execute(
                    "SELECT 1 FROM part_oem_codes WHERE part_id = ? AND upper(trim(oem_code)) = ?",
                    (part_id, _key(code)),
                ).fetchone()
                if not exists:
                    connection.execute("INSERT INTO part_oem_codes (part_id, oem_code) VALUES (?, ?)", (part_id, code))
                    changed_ids.add(part_id)
            for code in _split_codes(data.get("reference_code", "")):
                reference_type = data["reference_type"]
                exists = connection.execute(
                    """SELECT 1 FROM part_cross_references WHERE part_id = ?
                       AND upper(trim(reference_type)) = ? AND upper(trim(reference_code)) = ?""",
                    (part_id, _key(reference_type), _key(code)),
                ).fetchone()
                if not exists:
                    connection.execute(
                        "INSERT INTO part_cross_references (part_id, reference_type, reference_code) VALUES (?, ?, ?)",
                        (part_id, reference_type, code),
                    )
                    changed_ids.add(part_id)
            if data.get("has_application_data") and not data.get("application_warnings") and data.get("vehicle_brand") and data.get("vehicle_model") and save_application(connection, part_id, data):
                changed_ids.add(part_id)
        for part_id in changed_ids:
            refresh_long_description(connection, part_id)
        connection.execute(
            "UPDATE import_batches SET status = 'confirmed', processed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (batch_id,),
        )
    return len(inserted_ids), len(changed_ids - inserted_ids)
