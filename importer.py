from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from database import DEFAULT_DB_PATH, get_connection

COLUMN_ALIASES = {
    "sap_code": {"sap", "sap_code", "codigo_sap", "codigo", "codigo_repuesto"},
    "supplier_code": {"supplier_code", "codigo_proveedor", "proveedor_codigo"},
    "description": {"description", "descripcion", "descripcion_repuesto", "nombre"},
    "measure": {"measure", "medida", "dimensiones"},
    "brand_name": {"brand", "marca", "marca_repuesto"},
    "oem_code": {"oem", "oem_code", "codigo_oem", "codigo_original"},
    "reference_code": {"reference_code", "referencia", "referencia_cruzada", "equivalencia"},
}


def normalize_column(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def map_columns(columns: list[Any]) -> dict[str, str]:
    normalized = {normalize_column(column): str(column) for column in columns}
    mapping = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[target] = normalized[alias]
                break
    return mapping


def read_source(path: str | Path, sheet_name: str | int = 0) -> pd.DataFrame:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        # Detecta automaticamente comas, punto y coma o tabulaciones.
        return pd.read_csv(source, sep=None, engine="python", encoding="utf-8-sig")
    if source.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(source, sheet_name=sheet_name)
    raise ValueError("Formato no soportado. Use CSV o Excel.")


def stage_dataframe(
    dataframe: pd.DataFrame,
    file_name: str,
    sheet_name: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    mapping = map_columns(list(dataframe.columns))
    missing_columns = [field for field in ("sap_code", "description") if field not in mapping]
    if missing_columns:
        expected = "Codigo SAP y Descripcion"
        detected = ", ".join(str(column) for column in dataframe.columns) or "ninguna"
        raise ValueError(f"Faltan columnas obligatorias ({expected}). Columnas detectadas: {detected}")
    errors = []
    normalized_rows = []
    for _, row in dataframe.iterrows():
        normalized = {}
        for target, source in mapping.items():
            value = row[source]
            if pd.notna(value):
                normalized[target] = str(value).strip()
        row_errors = []
        if not normalized.get("sap_code"):
            row_errors.append("Falta codigo SAP")
        if not normalized.get("description"):
            row_errors.append("Falta descripcion")
        normalized_rows.append((normalized, row_errors))
        errors.append(row_errors)

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO import_batches (file_name, sheet_name, total_rows, valid_rows, error_rows) VALUES (?, ?, ?, ?, ?)",
            (file_name, sheet_name, len(normalized_rows), sum(not item for item in errors), sum(bool(item) for item in errors)),
        )
        batch_id = cursor.lastrowid
        for row_number, (normalized, row_errors) in enumerate(normalized_rows, start=2):
            raw = dataframe.iloc[row_number - 2].to_dict()
            connection.execute(
                """
                INSERT INTO import_staging_rows
                    (batch_id, row_number, raw_data, normalized_data, status, errors)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (batch_id, row_number, json.dumps(raw, default=str, ensure_ascii=False),
                 json.dumps(normalized, ensure_ascii=False), "error" if row_errors else "valid",
                 "; ".join(row_errors) or None),
            )
    return int(batch_id)


def confirm_batch(batch_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> tuple[int, int]:
    inserted = 0
    skipped = 0
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
            try:
                cursor = connection.execute(
                    "INSERT INTO parts (sap_code, supplier_code, description, measure, brand_name) VALUES (?, ?, ?, ?, ?)",
                    (data["sap_code"], data.get("supplier_code"), data["description"], data.get("measure"), data.get("brand_name")),
                )
                part_id = cursor.lastrowid
                if data.get("oem_code"):
                    for code in re.split(r"[,;|]", data["oem_code"]):
                        if code.strip():
                            connection.execute("INSERT OR IGNORE INTO part_oem_codes (part_id, oem_code) VALUES (?, ?)", (part_id, code.strip()))
                if data.get("reference_code"):
                    for code in re.split(r"[,;|]", data["reference_code"]):
                        if code.strip():
                            connection.execute("INSERT OR IGNORE INTO part_cross_references (part_id, reference_type, reference_code) VALUES (?, ?, ?)", (part_id, "IMPORTADO", code.strip()))
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
        connection.execute(
            "UPDATE import_batches SET status = 'confirmed', processed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (batch_id,),
        )
    return inserted, skipped
