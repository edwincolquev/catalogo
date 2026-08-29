from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "catalogo.sqlite3"
SCHEMA_PATH = BASE_DIR / "schema.sql"


@contextmanager
def get_connection(db_path: str | Path = DEFAULT_DB_PATH):
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
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(db_path) as connection:
        connection.executescript(schema)


def fetch_all(query: str, parameters: tuple = (), db_path: str | Path = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    with get_connection(db_path) as connection:
        return connection.execute(query, parameters).fetchall()


def execute(query: str, parameters: tuple = (), db_path: str | Path = DEFAULT_DB_PATH) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.execute(query, parameters)
        return cursor.lastrowid
