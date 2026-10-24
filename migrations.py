"""Migración de nombres de SQLite sin reconstruir ni renumerar los datos."""

from contextlib import closing
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from schema_names import COLUMN_RENAMES, TABLE_RENAMES

INDEX_RENAMES = {
    "parts_sap_code_unique": "repuestos_codigo_sap_unico",
    "parts_supplier_code_unique": "repuestos_codigo_proveedor_unico",
    "parts_description_index": "repuestos_descripcion_indice",
    "part_applications_vehicle_lookup": "aplicaciones_repuestos_busqueda_vehiculo",
    "part_applications_unique": "aplicaciones_repuestos_unicas",
}


def _pending_renames(connection: sqlite3.Connection) -> bool:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for old, new in TABLE_RENAMES.items():
        if old in tables and new in tables:
            raise ValueError(f"Existen las tablas {old} y {new}; revise la base antes de traducirla.")
    if any(old in tables for old in TABLE_RENAMES):
        return True
    for table in TABLE_RENAMES.values():
        if table in tables:
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            if columns & COLUMN_RENAMES.keys():
                return True
    return False


def migrate_spanish_names(connection: sqlite3.Connection, path: Path) -> Path | None:
    """Crea respaldo y traduce tablas, campos e índices en una transacción.

    SQLite actualiza las claves foráneas, índices y disparadores dependientes
    mediante ALTER TABLE. Reabrir una base traducida no repite la migración.
    """
    if not _pending_renames(connection):
        return None
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA legacy_alter_table = OFF")
    connection.execute("BEGIN IMMEDIATE")
    try:
        if not _pending_renames(connection):
            connection.commit()
            return None
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("La base tiene errores de integridad; no se cambió ningún nombre.")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("La base tiene referencias inválidas; no se cambió ningún nombre.")

        backup_path = path.with_name(path.stem + ".pre_traduccion_es" + path.suffix)
        if backup_path.exists():
            backup_path = path.with_name(path.stem + f".pre_traduccion_es.{uuid4().hex[:8]}" + path.suffix)
        # Un lector separado respalda la versión confirmada mientras el bloqueo
        # IMMEDIATE impide que otro escritor cambie los datos durante la copia.
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(backup_path)) as backup:
                source.backup(backup)

        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for old, new in TABLE_RENAMES.items():
            if old in tables:
                connection.execute(f'ALTER TABLE "{old}" RENAME TO "{new}"')
                tables.remove(old)
                tables.add(new)
        for table in TABLE_RENAMES.values():
            if table not in tables:
                continue
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            for old, new in COLUMN_RENAMES.items():
                if old in columns:
                    if new in columns:
                        raise ValueError(f"La tabla {table} contiene los campos {old} y {new}.")
                    connection.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{old}" TO "{new}"')
        for old, new in INDEX_RENAMES.items():
            index = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?", (old,)).fetchone()
            if index:
                connection.execute(re.sub(r"\b" + re.escape(old) + r"\b", new, index[0], count=1))
                connection.execute(f'DROP INDEX "{old}"')
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("La traducción dejó una referencia inválida; se deshicieron los cambios.")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("La traducción no superó la verificación de integridad.")
        connection.commit()
        return backup_path
    except Exception:
        connection.rollback()
        raise


def _execute_statements(connection, sql):
    statement = ""
    for line in sql.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ""
    if statement.strip():
        raise ValueError("Esquema SQL incompleto")


def migrate_management(connection: sqlite3.Connection, path: Path) -> Path | None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(repuestos)")}
    if not columns or "estado_gestion" in columns:
        return None
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("BEGIN IMMEDIATE")
    try:
        backup_path = path.with_name(path.stem + ".pre_gestion_comercial" + path.suffix)
        if backup_path.exists():
            backup_path = path.with_name(path.stem + f".pre_gestion_comercial.{uuid4().hex[:8]}" + path.suffix)
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(backup_path)) as backup:
                source.backup(backup)
        additions = {
            "unidad_id": "INTEGER REFERENCES unidades_medida(id) ON DELETE RESTRICT",
            "marca_id": "INTEGER REFERENCES marcas_repuestos(id) ON DELETE RESTRICT",
            "categoria_id": "INTEGER REFERENCES categorias_repuestos(id) ON DELETE RESTRICT",
            "estado_gestion": """TEXT NOT NULL DEFAULT 'propuesto'
                CHECK (estado_gestion IN ('propuesto', 'en_cotizacion', 'pendiente_aprobacion', 'aprobado', 'rechazado', 'pedido', 'en_sap'))
                CHECK (estado_gestion <> 'en_sap' OR trim(coalesce(codigo_sap, '')) <> '')""",
            "minimo_compra": "REAL CHECK (minimo_compra IS NULL OR minimo_compra > 0)",
            "precio_compra": "REAL CHECK (precio_compra IS NULL OR precio_compra >= 0)",
            "precio_venta": "REAL CHECK (precio_venta IS NULL OR precio_venta >= 0)",
            "cantidad_compra": "REAL CHECK (cantidad_compra IS NULL OR cantidad_compra >= 0)",
        }
        for name, definition in additions.items():
            connection.execute(f"ALTER TABLE repuestos ADD COLUMN {name} {definition}")
        sql = Path(__file__).with_name("schema_gestion.sql").read_text(encoding="utf-8")
        tables_sql, view_sql = sql.split("CREATE VIEW IF NOT EXISTS", 1)
        _execute_statements(connection, tables_sql)
        for nombre, in connection.execute("SELECT DISTINCT nombre_marca FROM repuestos WHERE trim(coalesce(nombre_marca, '')) <> ''").fetchall():
            connection.execute("INSERT OR IGNORE INTO marcas_repuestos (nombre) VALUES (?)", (nombre.strip(),))
        connection.execute("""UPDATE repuestos SET marca_id = (
            SELECT id FROM marcas_repuestos WHERE upper(trim(nombre)) = upper(trim(repuestos.nombre_marca))
        ), estado_gestion = CASE WHEN trim(coalesce(codigo_sap, '')) <> '' THEN 'en_sap' ELSE 'propuesto' END""")
        connection.execute("ALTER TABLE repuestos DROP COLUMN nombre_marca")
        _execute_statements(connection, "CREATE VIEW IF NOT EXISTS" + view_sql)
        connection.execute("""INSERT INTO historial_estados (repuesto_id, estado_nuevo)
            SELECT id, estado_gestion FROM repuestos""")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("La migración comercial dejó referencias inválidas")
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("La migración comercial no superó la verificación de integridad")
        connection.commit()
        return backup_path
    except Exception:
        connection.rollback()
        raise
