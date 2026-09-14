import unittest

from fastapi import HTTPException
from sqlalchemy import event
from sqlmodel import Session, create_engine, select

from mapc.db import init_db
from mapc.models.camera import Camera, CameraPlacement
from mapc.models.map import Map
from mapc.models.stream import Stream
from mapc.routes.cameras import add_cam, delete_camera
from mapc.schemas.camera import CameraCreate


class CameraDeleteTests(unittest.TestCase):
    def test_delete_dependencies_and_reuse_endpoint(self):
        engine = create_engine("sqlite://")
        event.listen(
            engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )
        init_db(engine)
        data = CameraCreate(
            ip="192.0.2.1",
            port=80,
            protocol="onvif",
            manufacturer="",
            model="",
            firmware="",
            serial_number="",
            mac_address="",
        )
        with Session(engine) as db:
            camera = add_cam(data, db)
            camera_id = camera.id
            site = Map(
                name="Site", image=b"image", mime_type="image/png", width=1, height=1
            )
            db.add(site)
            db.commit()
            db.add(
                Stream(
                    camera_id=camera_id,
                    profile="main",
                    token="main",
                    uri="rtsp://192.0.2.1/live",
                )
            )
            db.add(CameraPlacement(camera_id=camera_id, map_id=site.id, x=0.5, y=0.5))
            db.commit()
            self.assertEqual(delete_camera(camera_id, db).status_code, 204)
            for model in (Camera, Stream, CameraPlacement):
                self.assertEqual(db.exec(select(model)).all(), [])
            self.assertEqual(len(db.exec(select(Map)).all()), 1)
            with self.assertRaises(HTTPException) as error:
                delete_camera(camera_id, db)
            self.assertEqual(error.exception.status_code, 404)
            self.assertEqual(add_cam(data, db).ip, data.ip)
        engine.dispose()
