"""Edición de la hoja y guardado transaccional de varios repuestos."""

from copy import deepcopy
import math

from database import DEFAULT_DB_PATH, get_connection
from descriptions import refresh_long_description
from gestion import ESTADOS, guardar_repuesto, normalizar_estado

CAMPOS_EDITABLES = (
    "codigo_proveedor", "codigo_sap", "descripcion", "medida", "nombre_marca", "unidad", "categoria",
    "estado_gestion", "minimo_compra", "precio_compra", "precio_venta", "cantidad_compra", "activo",
)
CAMPOS_REPETIBLES = tuple(field for field in CAMPOS_EDITABLES if field not in ("codigo_proveedor", "codigo_sap"))


def valor_celda(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def valor_comparable(field, value):
    value = valor_celda(value)
    if field == "estado_gestion" and value:
        return normalizar_estado(value)
    if isinstance(value, str):
        return value.strip() or None
    return value


def filas_para_editor(rows, selected=()):
    return [dict(seleccionar=row["id"] in selected, id=row["id"], **{
        field: ESTADOS[row[field]] if field == "estado_gestion" else (
            bool(row[field]) if field == "activo" else row[field]
        ) for field in CAMPOS_EDITABLES
    }, fecha_actualizacion=row["fecha_actualizacion"]) for row in rows]


def cambios_hoja(originales, editadas):
    by_id = {row["id"]: row for row in originales}
    changes = {}
    for row in editadas:
        part_id = row["id"]
        if part_id not in by_id:
            raise ValueError("La hoja contiene un identificador que no pertenece a esta vista")
        fields = {field: valor_celda(row[field]) for field in CAMPOS_EDITABLES
                  if valor_comparable(field, row[field]) != valor_comparable(field, by_id[part_id][field])}
        if fields:
            changes[part_id] = fields
    return changes


def aplicar_edicion(anterior, propuesta, repetir=False):
    """Repite solo ediciones nuevas originadas en filas seleccionadas.

    La selección se resuelve por id, independientemente del orden visual.
    Si un pegado contiene valores distintos en una columna no se propagan.
    """
    result = deepcopy(propuesta)
    previous = {row["id"]: row for row in anterior}
    selected = {row["id"] for row in result if row["seleccionar"]}
    changed = {row["id"]: {
        field for field in CAMPOS_EDITABLES
        if valor_celda(row[field]) != valor_celda(previous[row["id"]][field])
    } for row in result}
    warnings = []
    if repetir and selected:
        for field in CAMPOS_REPETIBLES:
            values = []
            for row in result:
                if row["id"] in selected and field in changed[row["id"]]:
                    value = valor_celda(row[field])
                    if value not in values:
                        values.append(value)
            if len(values) > 1:
                warnings.append(f"{field}: se pegaron valores distintos; se conservaron las ediciones individuales.")
            elif values:
                for row in result:
                    if row["id"] in selected:
                        row[field] = values[0]
                        if valor_celda(row[field]) != valor_celda(previous[row["id"]][field]):
                            changed[row["id"]].add(field)
    for row in result:
        if "nombre_marca" in changed[row["id"]] and "categoria" not in changed[row["id"]]:
            row["categoria"] = None
    return result, warnings


def _validar_listas(connection, current, changes):
    for field, table in (("unidad", "unidades_medida"), ("nombre_marca", "marcas_repuestos")):
        value = changes.get(field)
        if value and not connection.execute(
            f"SELECT 1 FROM {table} WHERE upper(trim(nombre)) = upper(trim(?))", (value,)
        ).fetchone():
            raise ValueError(f"{field}: el valor no existe en Clasificación")
    if changes.get("categoria"):
        brand = changes.get("nombre_marca", current["nombre_marca"])
        exists = connection.execute("""SELECT 1 FROM categorias_repuestos c
            JOIN marcas_repuestos m ON m.id = c.marca_id
            WHERE upper(trim(c.nombre)) = upper(trim(?)) AND upper(trim(m.nombre)) = upper(trim(?))""",
                                    (changes["categoria"], brand)).fetchone()
        if not exists:
            raise ValueError("La categoría seleccionada no pertenece a la marca del repuesto")


def guardar_cambios_hoja(originales, cambios, db_path=DEFAULT_DB_PATH):
    """Comprueba la versión leída y guarda todas las filas o ninguna."""
    originals = {row["id"]: dict(row) for row in originales}
    count = 0
    with get_connection(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        for part_id, fields in cambios.items():
            if part_id not in originals:
                raise ValueError("El repuesto no pertenece a las filas mostradas")
            if not set(fields) <= set(CAMPOS_EDITABLES):
                raise ValueError("La hoja contiene campos no editables")
            original = originals[part_id]
            label = original["codigo_proveedor"] or f"ID {part_id}"
            try:
                current = connection.execute("SELECT * FROM vista_repuestos WHERE id = ?", (part_id,)).fetchone()
                if current is None:
                    raise ValueError("el repuesto fue eliminado; recargue la hoja")
                if any(valor_comparable(field, current[field]) != valor_comparable(field, original[field])
                       for field in CAMPOS_EDITABLES):
                    raise ValueError("los datos cambiaron desde que abrió la hoja; descarte los cambios y vuelva a editar")
                fields = {field: valor_celda(value) for field, value in fields.items()}
                if "codigo_proveedor" in fields and not str(fields["codigo_proveedor"] or "").strip():
                    raise ValueError("el código de proveedor no puede quedar vacío")
                if "estado_gestion" in fields and not fields["estado_gestion"]:
                    raise ValueError("el estado de gestión no puede quedar vacío")
                _validar_listas(connection, current, fields)
                _, changed = guardar_repuesto(connection, fields, part_id)
                if changed:
                    count += 1
                    if set(fields) & {"descripcion", "medida"}:
                        refresh_long_description(connection, part_id)
            except Exception as error:
                raise ValueError(f"Repuesto {label}: {error}") from error
    return count
