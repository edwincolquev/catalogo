from __future__ import annotations

import sqlite3
import os
from contextlib import closing, contextmanager
from pathlib import Path

from migrations import migrate_management, migrate_spanish_names

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = Path(os.environ.get("CATALOGO_DB_PATH") or BASE_DIR / "data" / "catalogo.sqlite3")
SCHEMA_PATH = BASE_DIR / "schema.sql"


def _postgres_url(db_path: str | Path) -> str | None:
    if Path(db_path) != DEFAULT_DB_PATH:
        return None
    url = os.environ.get("DATABASE_URL")
    if not url:
        env_file = BASE_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8-sig").splitlines():
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if url and "[YOUR-PASSWORD]" in url:
        raise ValueError("Sustituya [YOUR-PASSWORD] en DATABASE_URL")
    return url or None


def using_postgres() -> bool:
    return bool(_postgres_url(DEFAULT_DB_PATH))


@contextmanager
def get_connection(db_path: str | Path = DEFAULT_DB_PATH, *, autocommit: bool = False):
    postgres_url = _postgres_url(db_path)
    if postgres_url:
        from postgres_database import PostgresConnection

        connection = PostgresConnection(postgres_url, autocommit=autocommit)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    if _postgres_url(db_path):
        with get_connection(db_path, autocommit=True) as connection:
            connection.execute("SELECT 1 FROM public.repuestos LIMIT 1")
        return
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptions_need_refresh = False
    # SQLite cannot remove NOT NULL from an existing column with ALTER TABLE.
    # Keep IDs intact so references from OEM, applications and staging remain valid.
    with closing(sqlite3.connect(path)) as connection:
        existing = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'parts'"
        ).fetchone()
        if existing:
            columns = {row[1]: row for row in connection.execute("PRAGMA table_info(parts)")}
            if columns["sap_code"][3] or columns["description"][3]:
                duplicate = connection.execute(
                    """SELECT upper(trim(supplier_code)), COUNT(*) FROM parts
                       WHERE supplier_code IS NOT NULL AND trim(supplier_code) <> ''
                       GROUP BY upper(trim(supplier_code)) HAVING COUNT(*) > 1 LIMIT 1"""
                ).fetchone()
                if duplicate:
                    raise ValueError(f"Hay códigos de proveedor duplicados: {duplicate[0]}")
                backup_path = path.with_name(path.stem + ".pre_supplier_migration" + path.suffix)
                if not backup_path.exists():
                    with closing(sqlite3.connect(backup_path)) as backup_connection:
                        connection.backup(backup_connection)
                connection.execute("PRAGMA foreign_keys = OFF")
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute("""CREATE TABLE parts_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sap_code TEXT, supplier_code TEXT, description TEXT,
                        measure TEXT, brand_name TEXT, long_description TEXT,
                        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )""")
                    connection.execute("""INSERT INTO parts_new
                        (id, sap_code, supplier_code, description, measure, brand_name,
                         long_description, is_active, created_at, updated_at)
                        SELECT id, sap_code, supplier_code, description, measure, brand_name,
                               long_description, is_active, created_at, updated_at FROM parts""")
                    connection.execute("DROP TABLE parts")
                    connection.execute("ALTER TABLE parts_new RENAME TO parts")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.execute("PRAGMA foreign_keys = ON")
                violation = connection.execute("PRAGMA foreign_key_check").fetchone()
                if violation:
                    raise ValueError(f"La migración dejó una referencia inválida: {violation}")
                descriptions_need_refresh = True
        applications = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'part_applications'"
        ).fetchone()
        if applications:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(part_applications)")}
            if "application_text" not in columns:
                backup_path = path.with_name(path.stem + ".pre_application_text_migration" + path.suffix)
                if not backup_path.exists():
                    with closing(sqlite3.connect(backup_path)) as backup_connection:
                        connection.backup(backup_connection)
                connection.execute("PRAGMA foreign_keys = OFF")
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute("""CREATE TABLE part_applications_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        part_id INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                        brand_id INTEGER NOT NULL REFERENCES vehicle_brands(id) ON DELETE RESTRICT,
                        model_id INTEGER NOT NULL REFERENCES vehicle_models(id) ON DELETE RESTRICT,
                        engine_type_id INTEGER REFERENCES engine_types(id) ON DELETE RESTRICT,
                        displacement REAL CHECK (displacement IS NULL OR displacement > 0),
                        year_from INTEGER CHECK (year_from IS NULL OR year_from BETWEEN 1886 AND 2200),
                        year_to INTEGER CHECK (year_to IS NULL OR year_to BETWEEN 1886 AND 2200),
                        application_text TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        CHECK (year_from IS NULL OR year_to IS NULL OR year_from <= year_to)
                    )""")
                    connection.execute("""INSERT INTO part_applications_new
                        (id, part_id, brand_id, model_id, engine_type_id, displacement,
                         year_from, year_to, created_at)
                        SELECT id, part_id, brand_id, model_id, engine_type_id, displacement,
                               year_from, year_to, created_at FROM part_applications""")
                    connection.execute("""DELETE FROM part_applications_new WHERE id NOT IN (
                        SELECT min(id) FROM part_applications_new
                        GROUP BY part_id, brand_id, model_id, coalesce(engine_type_id, 0),
                                 coalesce(displacement, 0), coalesce(year_from, 0), coalesce(year_to, 0)
                    )""")
                    connection.execute("DROP TABLE part_applications")
                    connection.execute("ALTER TABLE part_applications_new RENAME TO part_applications")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.execute("PRAGMA foreign_keys = ON")
                violation = connection.execute("PRAGMA foreign_key_check").fetchone()
                if violation:
                    raise ValueError(f"La migración de aplicaciones dejó una referencia inválida: {violation}")
                descriptions_need_refresh = True
        migrate_spanish_names(connection, path)
        migrate_management(connection, path)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(path) as connection:
        connection.executescript(schema)
        connection.executescript((BASE_DIR / "schema_gestion.sql").read_text(encoding="utf-8"))
        for unit in ("Pieza", "Juego", "Metro"):
            connection.execute("INSERT OR IGNORE INTO unidades_medida (nombre) VALUES (?)", (unit,))
        if descriptions_need_refresh:
            from descriptions import refresh_long_description

            part_ids = [int(row[0]) for row in connection.execute("SELECT id FROM repuestos").fetchall()]
            for part_id in part_ids:
                refresh_long_description(connection, part_id)


def fetch_all(query: str, parameters: tuple = (), db_path: str | Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    with get_connection(db_path, autocommit=True) as connection:
        return connection.execute(query, parameters).fetchall()


def execute(query: str, parameters: tuple = (), db_path: str | Path = DEFAULT_DB_PATH) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.execute(query, parameters)
        return cursor.lastrowid
