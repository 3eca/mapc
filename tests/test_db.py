import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect, text

from mapc.db import build_engine, init_db
from mapc.settings import AppSettings


class DatabaseInitializationTests(unittest.TestCase):
    def settings(self, path):
        return AppSettings(_env_file=None, admin_password="unused", database_url=path)

    def test_missing_directory_and_database_are_created_and_data_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "mapc.db"
            engine = build_engine(self.settings(f"sqlite:///{path}"))
            try:
                init_db(engine)
                self.assertTrue(path.is_file())
                self.assertIn("cameras", inspect(engine).get_table_names())
                with engine.begin() as connection:
                    connection.execute(text("CREATE TABLE retained (value INTEGER)"))
                    connection.execute(text("INSERT INTO retained VALUES (42)"))
                init_db(engine)
                with engine.connect() as connection:
                    self.assertEqual(connection.scalar(text("SELECT value FROM retained")), 42)
            finally:
                engine.dispose()

    def test_directory_at_database_path_reports_mount_problem(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "Mount its parent directory"),
        ):
            build_engine(self.settings(f"sqlite:///{directory}"))
