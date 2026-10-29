"""Clasificación del repuesto y seguimiento comercial previo a SAP (USD)."""

from decimal import Decimal, InvalidOperation
import math
import sqlite3
import unicodedata

ESTADOS = {
    "propuesto": "Propuesto",
    "en_cotizacion": "En cotización",
    "pendiente_aprobacion": "Pendiente de aprobación",
    "aprobado": "Aprobado",
    "rechazado": "Rechazado",
    "pedido": "Pedido",
    "en_sap": "En SAP",
}
TRANSICIONES = {
    "propuesto": ("en_cotizacion", "rechazado"),
    "en_cotizacion": ("pendiente_aprobacion", "rechazado"),
    "pendiente_aprobacion": ("aprobado", "rechazado"),
    "aprobado": ("pedido", "rechazado"),
    "pedido": ("en_sap", "rechazado"),
    "rechazado": (),
    "en_sap": (),
}
NUMERICOS = ("minimo_compra", "precio_compra", "precio_venta", "cantidad_compra")
CAMPOS_GESTION = ("unidad", "nombre_marca", "categoria", "estado_gestion", *NUMERICOS)


def normalizar_estado(value):
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c)).replace(" ", "_")
    aliases = {"cotizacion": "en_cotizacion", "pendiente_de_aprobacion": "pendiente_aprobacion",
               "aprobacion": "pendiente_aprobacion", "sap": "en_sap", "sistema_sap": "en_sap"}
    result = aliases.get(text, text)
    if result not in ESTADOS:
        raise ValueError(f"Estado de gestión desconocido: {value}")
    return result


def numero_gestion(field, value):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value).strip().replace(",", "."))
        if not number.is_finite() or number < 0 or (field == "minimo_compra" and number == 0):
            raise InvalidOperation
        result = float(number)
        if not math.isfinite(result):
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, OverflowError):
        condition = "mayor que cero" if field == "minimo_compra" else "mayor o igual a cero"
        raise ValueError(f"{field}: debe ser un número {condition}") from None


def validar_gestion(data):
    errors = []
    for field in NUMERICOS:
        try:
            numero_gestion(field, data.get(field))
        except ValueError as error:
            errors.append(str(error))
    if data.get("estado_gestion"):
        try:
            normalizar_estado(data["estado_gestion"])
        except ValueError as error:
            errors.append(str(error))
    return errors


def _catalogo_id(connection, table, nombre, marca_id=None):
    nombre = str(nombre).strip()
    if not nombre:
        return None
    extra = " AND marca_id = ?" if table == "categorias_repuestos" else ""
    params = (nombre, marca_id) if extra else (nombre,)
    row = connection.execute(
        f"SELECT id FROM {table} WHERE upper(trim(nombre)) = upper(trim(?)){extra}", params
    ).fetchone()
    if row:
        return row[0]
    if extra:
        return connection.execute(f"INSERT INTO {table} (nombre, marca_id) VALUES (?, ?)", params).lastrowid
    return connection.execute(f"INSERT INTO {table} (nombre) VALUES (?)", params).lastrowid


def guardar_repuesto(connection: sqlite3.Connection, data: dict, repuesto_id=None, *, parcial=False):
    """Guarda datos informados; parcial=True conserva las celdas vacías del CSV.

    Debe llamarse dentro de la transacción de la operación (formulario o lote).
    Devuelve el identificador y si los datos del repuesto cambiaron.
    """
    data = {key: value for key, value in data.items()
            if not parcial or (value is not None and str(value).strip() != "")}
    errors = validar_gestion(data)
    if errors:
        raise ValueError("; ".join(errors))
    current = connection.execute("SELECT * FROM vista_repuestos WHERE id = ?", (repuesto_id,)).fetchone() if repuesto_id else None
    if repuesto_id and current is None:
        raise ValueError("El repuesto no existe")
    values = {}
    for field in ("codigo_proveedor", "codigo_sap", "descripcion", "medida"):
        if field in data:
            values[field] = str(data[field]).strip() if data[field] is not None else None
            values[field] = values[field] or None
    if "activo" in data:
        values["activo"] = bool(data["activo"])
    for field in NUMERICOS:
        if field in data:
            values[field] = numero_gestion(field, data[field])
    if "unidad" in data:
        values["unidad_id"] = _catalogo_id(connection, "unidades_medida", data["unidad"]) if data["unidad"] else None
    marca_id = current["marca_id"] if current else None
    if "nombre_marca" in data:
        marca_id = _catalogo_id(connection, "marcas_repuestos", data["nombre_marca"]) if data["nombre_marca"] else None
        values["marca_id"] = marca_id
        if current and marca_id != current["marca_id"]:
            values["categoria_id"] = None
    if "categoria" in data:
        if data["categoria"] and marca_id is None:
            raise ValueError("Seleccione una marca comercial antes de asignar una categoría")
        values["categoria_id"] = _catalogo_id(connection, "categorias_repuestos", data["categoria"], marca_id) if data["categoria"] else None

    codigo_sap = values.get("codigo_sap", current["codigo_sap"] if current else None)
    state = normalizar_estado(data["estado_gestion"]) if data.get("estado_gestion") else (
        current["estado_gestion"] if current else ("en_sap" if codigo_sap else "propuesto")
    )
    if state == "en_sap" and not codigo_sap:
        raise ValueError("Para pasar a En SAP debe informar el código SAP")
    if current:
        if state != current["estado_gestion"] and state not in TRANSICIONES[current["estado_gestion"]]:
            raise ValueError(f"No se puede pasar de {ESTADOS[current['estado_gestion']]} a {ESTADOS[state]}")
        if current["estado_gestion"] == "en_sap" and any(
            field in values and values[field] != current[field] for field in NUMERICOS
        ):
            raise ValueError("El seguimiento comercial está cerrado porque el repuesto está en SAP")
    elif state not in ("propuesto", "en_sap"):
        raise ValueError("Un repuesto nuevo inicia en Propuesto; los que ya tienen código SAP pueden iniciar en En SAP")
    values["estado_gestion"] = state
    if current:
        changes = {field: value for field, value in values.items() if value != current[field]}
        if changes:
            assignments = ", ".join(f"{field} = ?" for field in changes)
            connection.execute(f"UPDATE repuestos SET {assignments}, fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = ?",
                               (*changes.values(), repuesto_id))
        return repuesto_id, bool(changes)
    fields = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cursor = connection.execute(f"INSERT INTO repuestos ({fields}) VALUES ({marks})", tuple(values.values()))
    return int(cursor.lastrowid), True
