import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from fastapi import HTTPException
from sqlalchemy import inspect
from sqlmodel import Session, create_engine, select

from mapc.db import init_db
from mapc.models.camera import Camera
from mapc.routes.cameras import add_cam
from mapc.schemas.camera import CameraCreate


class CameraUniqueTests(unittest.TestCase):
    def test_parallel_add_and_existing_schema_upgrade(self):
        with TemporaryDirectory() as directory:
            engine = create_engine("sqlite:///" + str(Path(directory) / "test.db"))
            init_db(engine)
            with engine.begin() as connection:
                connection.exec_driver_sql("DROP INDEX uq_camera_endpoint")
            init_db(engine)
            init_db(engine)
            self.assertTrue(
                any(
                    i["name"] == "uq_camera_endpoint" and i["unique"]
                    for i in inspect(engine).get_indexes("cameras")
                )
            )
            barrier = Barrier(2)

            class RacingSession(Session):
                first = True

                def exec(self, *args, **kwargs):
                    result = super().exec(*args, **kwargs)
                    if self.first:
                        self.first = False
                        barrier.wait(timeout=5)
                    return result

            camera = CameraCreate(
                ip="192.0.2.1",
                port=8081,
                protocol="onvif",
                manufacturer="",
                model="",
                firmware="",
                serial_number="",
                mac_address="",
            )

            def add():
                with RacingSession(engine) as session:
                    try:
                        add_cam(camera, session)
                        return 201
                    except HTTPException as error:
                        return error.status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: add(), range(2)))
            self.assertCountEqual(results, [201, 409])
            with Session(engine) as session:
                self.assertEqual(len(session.exec(select(Camera)).all()), 1)
            engine.dispose()
