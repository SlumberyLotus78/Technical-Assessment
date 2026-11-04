"""Preparación compartida de bases PostgreSQL desechables para las suites SQL."""

import os
import re
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


class PostgresTestCase(unittest.TestCase):
    """Cada caso utiliza su propia base; el proyecto y su .env quedan fuera."""

    def setUp(self):
        if not TEST_DATABASE_URL:
            self.skipTest("Requiere TEST_DATABASE_URL y una base de prueba dedicada.")
        params = conninfo_to_dict(TEST_DATABASE_URL)
        if not params.get("dbname", "").startswith("grain_test_"):
            raise ValueError("La base de TEST_DATABASE_URL debe comenzar por grain_test_.")
        self.admin = psycopg.connect(TEST_DATABASE_URL, autocommit=True, connect_timeout=10)
        self.addCleanup(self.admin.close)
        self.database_name = "grain_test_" + uuid4().hex
        self.admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
            sql.Identifier(self.database_name)))
        self.addCleanup(self.drop_test_database)
        self.database_url = make_conninfo(TEST_DATABASE_URL, dbname=self.database_name)
        self.connection = psycopg.connect(self.database_url, connect_timeout=10)
        self.addCleanup(self.connection.close)

    def drop_test_database(self):
        """Elimina exclusivamente la base UUID creada por esta instancia de prueba."""
        if re.fullmatch(r"grain_test_[0-9a-f]{32}", self.database_name) is None:
            raise ValueError("Nombre de limpieza de prueba incompatible.")
        self.admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
            sql.Identifier(self.database_name)))
