"""Carga el respaldo SQLite del catálogo en el proyecto Supabase configurado.

Uso:
    python supabase/import_sqlite.py --check
    python supabase/import_sqlite.py --apply

Lee SUPABASE_ACCESS_TOKEN de C:/Catalogo/.env. Nunca imprime el token ni los datos.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "catalogo.pre_supabase_20261028.sqlite3"
PROJECT_REF = "wvsysymabduywfgekyfh"
QUERY_URL = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
TABLES = (
    "unidades_medida",
    "marcas_repuestos",
    "categorias_repuestos",
    "marcas_vehiculos",
    "modelos_vehiculos",
    "tipos_motor",
    "repuestos",
    "codigos_oem",
    "referencias_cruzadas",
    "aplicaciones_repuestos",
    "lotes_importacion",
    "filas_importacion",
    "historial_estados",
)


def access_token() -> str:
    env_file = ROOT / ".env"
    if not env_file.is_file():
        raise RuntimeError("Falta C:/Catalogo/.env")
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("SUPABASE_ACCESS_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("Falta SUPABASE_ACCESS_TOKEN en .env")


def query(token: str, sql: str, *, read_only: bool) -> list[dict]:
    request = urllib.request.Request(
        QUERY_URL,
        data=json.dumps({"query": sql, "read_only": read_only}).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Supabase HTTP {error.code}: {detail}") from None


def remote_counts(token: str) -> dict[str, int]:
    parts = [f"select '{table}' as tabla, count(*) as total from public.{table}" for table in TABLES]
    rows = query(token, " union all ".join(parts), read_only=True)
    return {row["tabla"]: int(row["total"]) for row in rows}


def literal(value: object, column: str) -> str:
    if value is None:
        return "null"
    if column == "activo":
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Número no finito en {column}")
        return repr(value)
    if not isinstance(value, str):
        raise TypeError(f"Tipo inesperado en {column}: {type(value).__name__}")
    if "\x00" in value:
        raise ValueError(f"NUL en {column}")
    if column.startswith("fecha_") and value and not value.endswith(("Z", "+00", "+00:00")):
        # SQLite CURRENT_TIMESTAMP almacena UTC sin zona horaria.
        value += "+00"
    return "'" + value.replace("'", "''") + "'"


def build_import_sql(connection: sqlite3.Connection) -> tuple[str, dict[str, int]]:
    statements = ["begin;", "set local standard_conforming_strings = on;"]
    counts = {}
    for table in TABLES:
        if table == "historial_estados":
            # Si las reglas ya están instaladas, los INSERT de repuestos
            # generaron historial nuevo. Conservamos el historial original.
            statements.append("truncate table public.historial_estados restart identity;")
        columns = [row[1] for row in connection.execute(f'pragma table_info("{table}")')]
        rows = connection.execute(f'select * from "{table}" order by id').fetchall()
        counts[table] = len(rows)
        if rows:
            values = []
            for row in rows:
                values.append("(" + ", ".join(literal(row[column], column) for column in columns) + ")")
            statements.append(
                f"insert into public.{table} (" + ", ".join(columns) + ") values\n"
                + ",\n".join(values) + ";"
            )
        statements.append(
            f"select setval(pg_get_serial_sequence('public.{table}', 'id'), "
            f"coalesce(max(id), 1), max(id) is not null) from public.{table};"
        )
    statements.append("commit;")
    return "\n".join(statements), counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    with sqlite3.connect(SOURCE) as connection:
        connection.row_factory = sqlite3.Row
        integrity = connection.execute("pragma integrity_check").fetchone()[0]
        foreign_keys = connection.execute("pragma foreign_key_check").fetchall()
        if integrity != "ok" or foreign_keys:
            raise RuntimeError("El respaldo SQLite no pasó las comprobaciones de integridad")
        sql, local = build_import_sql(connection)

    token = access_token()
    remote = remote_counts(token)
    if set(remote) != set(TABLES):
        raise RuntimeError("Faltan tablas remotas del catálogo")
    print("origen_sqlite", local)
    print("destino_supabase_antes", remote)
    print("tamano_sql_bytes", len(sql.encode("utf-8")))
    if args.verify:
        verify_rows(token)
        return
    if not args.apply:
        return
    if any(remote.values()):
        raise RuntimeError("El destino contiene filas; se detuvo la carga para evitar duplicados")
    query(token, sql, read_only=False)
    after = remote_counts(token)
    print("destino_supabase_despues", after)
    if after != local:
        raise RuntimeError("Los recuentos remotos no coinciden con SQLite")
    verify_rows(token)


def normalized(value: object, column: str) -> object:
    if value is None:
        return None
    if column == "activo":
        return bool(value)
    if column.startswith("fecha_"):
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    if column in {"minimo_compra", "precio_compra", "precio_venta", "cantidad_compra"}:
        return Decimal(str(value))
    return value


def verify_rows(token: str) -> None:
    with sqlite3.connect(SOURCE) as connection:
        connection.row_factory = sqlite3.Row
        for table in TABLES:
            local_rows = connection.execute(f'select * from "{table}" order by id').fetchall()
            remote_rows = query(token, f"select * from public.{table} order by id", read_only=True)
            if len(local_rows) != len(remote_rows):
                raise RuntimeError(f"Difieren los recuentos de {table}")
            for local_row, remote_row in zip(local_rows, remote_rows):
                for column in local_row.keys():
                    if normalized(local_row[column], column) != normalized(remote_row[column], column):
                        raise RuntimeError(f"Diferencia en {table}, id={local_row['id']}, columna={column}")
            print("verificado", table, len(local_rows))


if __name__ == "__main__":
    main()
