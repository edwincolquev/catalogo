"""Adaptador mínimo para las consultas existentes del catálogo en PostgreSQL.

Mantiene los parámetros `?`, el acceso a filas por índice/nombre y `lastrowid`
que usa la aplicación SQLite, mientras ejecuta transacciones reales en Postgres.
"""

from __future__ import annotations

import re
from decimal import Decimal
from threading import BoundedSemaphore, Lock
from typing import Any

import psycopg2
from psycopg2.pool import ThreadedConnectionPool


_POOL_SIZE = 5
_pool_lock = Lock()
_pools: dict[str, tuple[ThreadedConnectionPool, BoundedSemaphore]] = {}


def _pool_for(dsn: str) -> tuple[ThreadedConnectionPool, BoundedSemaphore]:
    with _pool_lock:
        if dsn not in _pools:
            pool = ThreadedConnectionPool(
                1, _POOL_SIZE, dsn=dsn, sslmode="require", connect_timeout=10
            )
            _pools[dsn] = (pool, BoundedSemaphore(_POOL_SIZE))
        return _pools[dsn]


class Record(dict):
    def __init__(self, columns: list[str], values: tuple[Any, ...]):
        normalized = tuple(float(value) if isinstance(value, Decimal) else value for value in values)
        super().__init__(zip(columns, normalized))
        self._values = normalized

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class Result:
    def __init__(self, cursor, lastrowid: int | None = None):
        self.cursor = cursor
        self.lastrowid = lastrowid
        self.columns = [item.name for item in cursor.description] if cursor.description else []

    def fetchone(self) -> Record | None:
        row = self.cursor.fetchone() if self.columns else None
        return Record(self.columns, row) if row is not None else None

    def fetchall(self) -> list[Record]:
        return [Record(self.columns, row) for row in self.cursor.fetchall()] if self.columns else []

    def __iter__(self):
        while (row := self.fetchone()) is not None:
            yield row


def _sql(query: str) -> tuple[str, bool]:
    if query.strip().upper() == "BEGIN IMMEDIATE":
        return "select 1", False
    query = re.sub(r"\bIS\s+\?", "IS NOT DISTINCT FROM %s", query, flags=re.IGNORECASE)
    query = query.replace("?", "%s")
    inserted = bool(re.match(r"\s*INSERT\s+INTO\s+", query, flags=re.IGNORECASE))
    if inserted and not re.search(r"\bRETURNING\b", query, flags=re.IGNORECASE):
        query = query.rstrip().rstrip(";") + " RETURNING id"
    return query, inserted


def _parameter(value: Any) -> Any:
    if type(value).__module__.startswith("numpy"):
        return value.item()
    return value


class PostgresConnection:
    def __init__(self, dsn: str, autocommit: bool = False):
        self.pool, self._slot = _pool_for(dsn)
        if not self._slot.acquire(timeout=15):
            raise TimeoutError("No hay conexiones disponibles para PostgreSQL")
        raw = None
        try:
            raw = self.pool.getconn()
            if raw.closed:
                self.pool.putconn(raw, close=True)
                raw = None
                raw = self.pool.getconn()
            raw.autocommit = autocommit
            self.raw = raw
        except Exception:
            try:
                if raw is not None:
                    self.pool.putconn(raw, close=bool(raw.closed))
            finally:
                self._slot.release()
            raise

    def execute(self, query: str, parameters=()) -> Result:
        sql, inserted = _sql(query)
        cursor = self.raw.cursor()
        cursor.execute(sql, tuple(_parameter(value) for value in parameters))
        if inserted:
            row = cursor.fetchone()
            return Result(cursor, int(row[0]) if row else None)
        return Result(cursor)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        if self.raw is not None:
            try:
                self.pool.putconn(self.raw, close=bool(self.raw.closed))
            finally:
                self.raw = None
                self._slot.release()
