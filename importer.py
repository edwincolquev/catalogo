from __future__ import annotations

import json
import csv
import io
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from database import DEFAULT_DB_PATH, get_connection
from descriptions import refresh_long_description
from schema_names import IMPORT_KEY_RENAMES, normalize_import_data
from gestion import guardar_repuesto, validar_gestion


def plantilla_maestro_bytes() -> bytes:
    columns = [
        "repuestos.codigo_proveedor", "repuestos.codigo_sap", "repuestos.descripcion", "repuestos.medida",
        "unidades_medida.nombre", "marcas_repuestos.nombre", "categorias_repuestos.nombre",
        "repuestos.estado_gestion", "repuestos.minimo_compra", "repuestos.precio_compra",
        "repuestos.precio_venta", "repuestos.cantidad_compra", "codigos_oem.codigo_oem",
        "referencias_cruzadas.tipo_referencia", "referencias_cruzadas.codigo_referencia",
        "marcas_vehiculos.nombre", "modelos_vehiculos.nombre", "tipos_motor.codigo", "tipos_motor.descripcion",
        "aplicaciones_repuestos.cilindrada", "aplicaciones_repuestos.anio_desde",
        "aplicaciones_repuestos.anio_hasta", "aplicaciones_repuestos.texto_aplicacion",
    ]
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([column.split(".")[0].upper() for column in columns])
    writer.writerow(columns)
    return output.getvalue().encode("utf-8-sig")

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

SPANISH_COLUMN_ALIASES = {
    "codigo_proveedor": {"repuestos_codigo_proveedor"},
    "codigo_sap": {"repuestos_codigo_sap"},
    "descripcion": {"repuestos_descripcion"},
    "medida": {"repuestos_medida"},
    "nombre_marca": {"repuestos_nombre_marca"},
    "codigo_oem": {"codigos_oem_codigo_oem"},
    "tipo_referencia": {"referencias_cruzadas_tipo_referencia"},
    "codigo_referencia": {"referencias_cruzadas_codigo_referencia"},
    "marca_vehiculo": {"marcas_vehiculos_nombre", "marcas_vehiculo_nombre"},
    "modelo_vehiculo": {"modelos_vehiculos_nombre"},
    "codigo_motor": {"tipos_motor_codigo"},
    "descripcion_motor": {"tipos_motor_descripcion"},
    "cilindrada": {"aplicaciones_repuestos_cilindrada"},
    "anio_desde": {"aplicaciones_repuestos_anio_desde"},
    "anio_hasta": {"aplicaciones_repuestos_anio_hasta"},
    "texto_aplicacion": {"aplicaciones_repuestos_texto_aplicacion"},
}
COLUMN_ALIASES = {
    IMPORT_KEY_RENAMES.get(target, target): aliases
    | {IMPORT_KEY_RENAMES.get(target, target)}
    | SPANISH_COLUMN_ALIASES.get(IMPORT_KEY_RENAMES.get(target, target), set())
    for target, aliases in COLUMN_ALIASES.items()
}
COLUMN_ALIASES["nombre_marca"].add("marcas_repuestos_nombre")
for field, aliases in {
    "unidad": {"unidad_medida", "unidades_medida_nombre", "repuestos_unidad"},
    "categoria": {"categorias_repuestos_nombre", "repuestos_categoria"},
    "estado_gestion": {"estado_del_proceso", "estado_proceso"},
    "minimo_compra": {"minimo_de_compra"},
    "precio_compra": {"precio_de_compra", "precio_compra_usd"},
    "precio_venta": {"precio_de_venta", "precio_venta_usd"},
    "cantidad_compra": {"cantidad_de_compra"},
}.items():
    COLUMN_ALIASES[field] = aliases | {field, f"repuestos_{field}"}


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


def read_source(path: str | Path, nombre_hoja: str | int = 0) -> pd.DataFrame:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        options = dict(sep=None, engine="python", encoding="utf-8-sig", dtype=str, keep_default_na=False)
        first = pd.read_csv(source, nrows=0, **options)
        master = any(str(c).strip().upper() in {"PARTS", "REPUESTOS"} for c in first.columns)
        dataframe = pd.read_csv(source, header=1 if master else 0, **options)
    elif suffix in {".xlsx", ".xls", ".xlsm"}:
        options = dict(sheet_name=nombre_hoja, dtype=str, keep_default_na=False)
        first = pd.read_excel(source, nrows=0, **options)
        master = any(str(c).strip().upper() in {"PARTS", "REPUESTOS"} for c in first.columns)
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
    fields = ("marca_vehiculo", "modelo_vehiculo", "codigo_motor", "descripcion_motor", "cilindrada", "anio_desde", "anio_hasta", "texto_aplicacion")
    if not any(data.get(field) for field in fields):
        return []
    warnings = []
    if not data.get("marca_vehiculo") or not data.get("modelo_vehiculo"):
        warnings.append("Aplicación sin marca y modelo completos")
    if data.get("descripcion_motor") and not data.get("codigo_motor"):
        warnings.append("Descripción de motor sin código")
    if data.get("codigo_motor") and re.search(r"\b(DEL|DESDE|HASTA|AL)\b|;", data["codigo_motor"], re.I):
        warnings.append("Motor contiene texto de aplicación")
    if data.get("cilindrada"):
        try:
            if float(data["cilindrada"].replace(",", ".")) <= 0:
                raise ValueError
        except ValueError:
            warnings.append("Cilindrada inválida")
    years = {}
    for field in ("anio_desde", "anio_hasta"):
        if data.get(field):
            try:
                years[field] = int(data[field])
                if not 1886 <= years[field] <= 2200:
                    raise ValueError
            except ValueError:
                warnings.append(f"{field} inválido")
    if years.get("anio_desde", 0) > years.get("anio_hasta", 2200):
        warnings.append("Rango de años invertido")
    return warnings


def stage_dataframe(dataframe: pd.DataFrame, nombre_archivo: str, nombre_hoja: str | None = None,
                    db_path: str | Path = DEFAULT_DB_PATH) -> int:
    mapping = map_columns(list(dataframe.columns))
    if "codigo_proveedor" not in mapping and "codigo_sap" not in mapping:
        raise ValueError("Falta una columna de código de proveedor o código SAP")
    master = bool(dataframe.attrs.get("master_format"))
    if master and "codigo_proveedor" not in mapping:
        raise ValueError("El maestro necesita repuestos.codigo_proveedor")
    first_row = int(dataframe.attrs.get("first_data_row", 2))
    staged = []
    last_supplier = last_brand = last_model = ""
    for _, row in dataframe.iterrows():
        data = {target: _text(row[source]) for target, source in mapping.items()}
        has_application_data = any(data.get(field) for field in (
            "marca_vehiculo", "modelo_vehiculo", "codigo_motor", "descripcion_motor", "cilindrada", "anio_desde", "anio_hasta", "texto_aplicacion"
        ))
        if master:
            supplied = data.get("codigo_proveedor", "")
            if supplied and _key(supplied) != _key(last_supplier):
                last_brand = last_model = ""
            data["codigo_proveedor"] = supplied or last_supplier
            last_supplier = data["codigo_proveedor"]
            brand = data.get("marca_vehiculo", "")
            if brand:
                brand = brand.rstrip(" :").strip()
                if _key(brand) != _key(last_brand):
                    last_model = ""
                last_brand = brand
            data["marca_vehiculo"] = last_brand
            if data.get("modelo_vehiculo"):
                last_model = data["modelo_vehiculo"]
            data["modelo_vehiculo"] = last_model
        errores = validar_gestion(data)
        if not data.get("codigo_proveedor") and not data.get("codigo_sap"):
            errores.append("Falta código de proveedor o SAP")
        if master and not data.get("codigo_proveedor"):
            errores.append("Falta código de proveedor")
        if data.get("codigo_referencia") and not data.get("tipo_referencia"):
            if master:
                errores.append("La referencia necesita tipo_referencia")
            else:
                data["tipo_referencia"] = "IMPORTADO"
        warnings = _application_warnings(data) if has_application_data else []
        data["has_application_data"] = has_application_data
        data["application_warnings"] = warnings
        staged.append((first_row + len(staged), row.to_dict(), data, errores, warnings))
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO lotes_importacion (nombre_archivo, nombre_hoja, total_filas, filas_validas, filas_error) VALUES (?, ?, ?, ?, ?)",
            (nombre_archivo, nombre_hoja, len(staged), sum(not x[3] for x in staged), sum(bool(x[3]) for x in staged)),
        )
        lote_id = int(cursor.lastrowid)
        for number, raw, data, errores, warnings in staged:
            connection.execute(
                """INSERT INTO filas_importacion
                   (lote_id, numero_fila, datos_originales, datos_normalizados, estado, errores)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (lote_id, number, json.dumps(raw, default=str, ensure_ascii=False),
                 json.dumps(data, ensure_ascii=False), "error" if errores else "valid",
                 "; ".join(errores + [f"Aviso: {w}" for w in warnings]) or None),
            )
    return lote_id


def _find_part(connection: sqlite3.Connection, data: dict[str, Any]) -> sqlite3.Row | None:
    supplier, sap = data.get("codigo_proveedor"), data.get("codigo_sap")
    by_supplier = connection.execute(
        "SELECT * FROM vista_repuestos WHERE upper(trim(codigo_proveedor)) = ?", (_key(supplier),)
    ).fetchone() if supplier else None
    by_sap = connection.execute(
        "SELECT * FROM vista_repuestos WHERE upper(trim(codigo_sap)) = ?", (_key(sap),)
    ).fetchone() if sap else None
    if by_supplier and by_sap and by_supplier["id"] != by_sap["id"]:
        raise ValueError(f"El proveedor {supplier} y SAP {sap} pertenecen a repuestos distintos")
    part = by_supplier or by_sap
    if part and supplier and part["codigo_proveedor"] and _key(part["codigo_proveedor"]) != _key(supplier):
        raise ValueError(f"El SAP {sap} ya pertenece al proveedor {part['codigo_proveedor']}")
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


def save_application(connection: sqlite3.Connection, repuesto_id: int, data: dict[str, Any],
                     application_id: int | None = None) -> bool:
    warnings = _application_warnings(data)
    if warnings:
        raise ValueError("; ".join(warnings))
    if not data.get("marca_vehiculo") or not data.get("modelo_vehiculo"):
        raise ValueError("Marca y modelo son obligatorios")
    marca_id = _find_or_create(connection, "marcas_vehiculos", "nombre", data["marca_vehiculo"])
    modelo_id = _find_or_create(connection, "modelos_vehiculos", "nombre", data["modelo_vehiculo"], ("marca_id", marca_id))
    engine_id = None
    engine_changed = False
    if data.get("codigo_motor"):
        engine_id = _find_or_create(connection, "tipos_motor", "codigo", data["codigo_motor"])
        if data.get("descripcion_motor"):
            previous = connection.execute("SELECT descripcion FROM tipos_motor WHERE id = ?", (engine_id,)).fetchone()[0]
            if data["descripcion_motor"] != (previous or ""):
                connection.execute("UPDATE tipos_motor SET descripcion = ? WHERE id = ?",
                                   (data["descripcion_motor"], engine_id))
                engine_changed = True
                related = connection.execute(
                    "SELECT DISTINCT repuesto_id FROM aplicaciones_repuestos WHERE tipo_motor_id = ?", (engine_id,)
                ).fetchall()
                for row in related:
                    refresh_long_description(connection, int(row["repuesto_id"]))
    cilindrada = float(data["cilindrada"].replace(",", ".")) if data.get("cilindrada") else None
    anio_desde = int(data["anio_desde"]) if data.get("anio_desde") else None
    anio_hasta = int(data["anio_hasta"]) if data.get("anio_hasta") else None
    texto_aplicacion = data.get("texto_aplicacion") or None
    exists = connection.execute(
        """SELECT 1 FROM aplicaciones_repuestos WHERE repuesto_id = ? AND marca_id = ? AND modelo_id = ?
           AND tipo_motor_id IS ? AND cilindrada IS ? AND anio_desde IS ? AND anio_hasta IS ?
           AND upper(trim(coalesce(texto_aplicacion, ''))) = ?
           AND (? IS NULL OR id <> ?)""",
        (repuesto_id, marca_id, modelo_id, engine_id, cilindrada, anio_desde, anio_hasta,
         _key(texto_aplicacion or ""), application_id, application_id),
    ).fetchone()
    if exists:
        return engine_changed
    if application_id is None:
        connection.execute(
            """INSERT INTO aplicaciones_repuestos
               (repuesto_id, marca_id, modelo_id, tipo_motor_id, cilindrada, anio_desde, anio_hasta, texto_aplicacion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (repuesto_id, marca_id, modelo_id, engine_id, cilindrada, anio_desde, anio_hasta, texto_aplicacion),
        )
    else:
        connection.execute(
            """UPDATE aplicaciones_repuestos SET marca_id = ?, modelo_id = ?, tipo_motor_id = ?,
               cilindrada = ?, anio_desde = ?, anio_hasta = ?, texto_aplicacion = ?
               WHERE id = ? AND repuesto_id = ?""",
            (marca_id, modelo_id, engine_id, cilindrada, anio_desde, anio_hasta,
             texto_aplicacion, application_id, repuesto_id),
        )
    return True


def confirm_batch(lote_id: int, db_path: str | Path = DEFAULT_DB_PATH) -> tuple[int, int]:
    inserted_ids: set[int] = set()
    changed_ids: set[int] = set()
    with get_connection(db_path) as connection:
        batch = connection.execute("SELECT estado FROM lotes_importacion WHERE id = ?", (lote_id,)).fetchone()
        if batch is None:
            raise ValueError("La carga no existe")
        if batch["estado"] != "staged":
            raise ValueError("La carga ya fue procesada")
        rows = connection.execute(
            "SELECT datos_normalizados FROM filas_importacion WHERE lote_id = ? AND estado = 'valid' ORDER BY numero_fila",
            (lote_id,),
        ).fetchall()
        for row in rows:
            data = normalize_import_data(json.loads(row["datos_normalizados"]))
            part = _find_part(connection, data)
            try:
                repuesto_id, changed = guardar_repuesto(
                    connection, data, int(part["id"]) if part else None, parcial=True
                )
            except ValueError as error:
                raise ValueError(f"Repuesto {data.get('codigo_proveedor') or data.get('codigo_sap')}: {error}") from error
            if part is None:
                inserted_ids.add(repuesto_id)
            if changed:
                changed_ids.add(repuesto_id)
            for codigo in _split_codes(data.get("codigo_oem", "")):
                exists = connection.execute(
                    "SELECT 1 FROM codigos_oem WHERE repuesto_id = ? AND upper(trim(codigo_oem)) = ?",
                    (repuesto_id, _key(codigo)),
                ).fetchone()
                if not exists:
                    connection.execute("INSERT INTO codigos_oem (repuesto_id, codigo_oem) VALUES (?, ?)", (repuesto_id, codigo))
                    changed_ids.add(repuesto_id)
            for codigo in _split_codes(data.get("codigo_referencia", "")):
                tipo_referencia = data["tipo_referencia"]
                exists = connection.execute(
                    """SELECT 1 FROM referencias_cruzadas WHERE repuesto_id = ?
                       AND upper(trim(tipo_referencia)) = ? AND upper(trim(codigo_referencia)) = ?""",
                    (repuesto_id, _key(tipo_referencia), _key(codigo)),
                ).fetchone()
                if not exists:
                    connection.execute(
                        "INSERT INTO referencias_cruzadas (repuesto_id, tipo_referencia, codigo_referencia) VALUES (?, ?, ?)",
                        (repuesto_id, tipo_referencia, codigo),
                    )
                    changed_ids.add(repuesto_id)
            if data.get("has_application_data") and not data.get("application_warnings") and data.get("marca_vehiculo") and data.get("modelo_vehiculo") and save_application(connection, repuesto_id, data):
                changed_ids.add(repuesto_id)
        for repuesto_id in changed_ids:
            refresh_long_description(connection, repuesto_id)
        connection.execute(
            "UPDATE lotes_importacion SET estado = 'confirmed', fecha_procesamiento = CURRENT_TIMESTAMP WHERE id = ?",
            (lote_id,),
        )
    return len(inserted_ids), len(changed_ids - inserted_ids)
