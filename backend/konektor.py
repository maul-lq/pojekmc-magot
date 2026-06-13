from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

import mysql.connector
from mysql.connector import MySQLConnection

from backend.config import Settings, settings


class Konektor:
    """Small MySQL connection helper with one connection per operation."""

    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    def connect(self) -> MySQLConnection:
        connection = mysql.connector.connect(
            host=self.config.mysql_host,
            port=self.config.mysql_port,
            user=self.config.mysql_user,
            password=self.config.mysql_password,
            database=self.config.mysql_database,
            autocommit=False,
            connection_timeout=5,
        )
        cursor = connection.cursor()
        try:
            cursor.execute("SET time_zone = '+00:00'")
        finally:
            cursor.close()
        return connection

    @contextmanager
    def transaction(self) -> Iterator[MySQLConnection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.transaction() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql, params)
                return cursor.lastrowid
            finally:
                cursor.close()

    def execute_many(self, statements: Sequence[str]) -> None:
        with self.transaction() as connection:
            cursor = connection.cursor()
            try:
                for statement in statements:
                    cursor.execute(statement)
            finally:
                cursor.close()

    def fetch_one(
        self, sql: str, params: Sequence[Any] = ()
    ) -> dict[str, Any] | None:
        connection = self.connect()
        try:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(sql, params)
                return cursor.fetchone()
            finally:
                cursor.close()
        finally:
            connection.close()

    def fetch_all(
        self, sql: str, params: Sequence[Any] = ()
    ) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(sql, params)
                return list(cursor.fetchall())
            finally:
                cursor.close()
        finally:
            connection.close()
