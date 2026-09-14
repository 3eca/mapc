import unittest
from io import BytesIO

from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError
from sqlmodel import Session, create_engine

from mapc.db import init_db
from mapc.models.camera import Camera
from mapc.routes.maps import (
    delete_placement,
    get_image,
    image_info,
    list_maps,
    list_placements,
    put_placement,
    save_map,
)
from mapc.schemas.map import PlacementInput


class MapTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        init_db(self.engine)
        output = BytesIO()
        Image.new("RGB", (40, 20), "white").save(output, format="PNG")
        self.image = output.getvalue()

    def tearDown(self):
        self.engine.dispose()

    def test_image_storage_and_placement(self):
        item = save_map(self.engine, "Test", self.image)
        self.assertEqual((item.width, item.height), (40, 20))
        self.assertNotIn("image", item.model_dump())
        with Session(self.engine) as db:
            self.assertNotIn("image", list_maps(db)[0])
            self.assertEqual(get_image(item.id, db).body, self.image)
            cam = Camera(
                ip="192.0.2.1",
                port=80,
                protocol="test",
                manufacturer="test",
                model="test",
                firmware="test",
                serial_number="test",
                mac_address="test",
            )
            db.add(cam)
            db.commit()
            db.refresh(cam)
            placement = put_placement(item.id, cam.id, PlacementInput(x=0.5, y=0.5), db)
            old_id = placement.id
            updated = put_placement(
                item.id, cam.id, PlacementInput(x=0.2, y=0.3, direction=90), db
            )
            self.assertEqual(updated.id, old_id)
            self.assertEqual(len(list_placements(item.id, db)), 1)
            self.assertEqual(updated.x, 0.2)
            delete_placement(item.id, cam.id, db)
            self.assertEqual(list_placements(item.id, db), [])

    def test_reject_invalid_image(self):
        for data in [b"", b"<svg></svg>", b"not an image", self.image[:30]]:
            with self.assertRaises(HTTPException):
                image_info(data)

    def test_validation_and_missing_parents(self):
        for values in [
            {"x": -1, "y": 0},
            {"x": 0, "y": 2},
            {"x": float("nan"), "y": 0},
            {"x": 0, "y": 0, "direction": 360},
            {"x": 0, "y": 0, "view_angle": 0},
        ]:
            with self.assertRaises(ValidationError):
                PlacementInput(**values)
        with Session(self.engine) as db:
            with self.assertRaises(HTTPException) as error:
                put_placement(999, 999, PlacementInput(x=0, y=0), db)
            self.assertEqual(error.exception.status_code, 404)
            item = save_map(self.engine, "Test", self.image)
            with self.assertRaises(HTTPException) as error:
                put_placement(item.id, 999, PlacementInput(x=0, y=0), db)
            self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
