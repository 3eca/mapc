import unittest
from copy import deepcopy
from types import SimpleNamespace

from fastapi import HTTPException
from sqlmodel import Session, create_engine, select

from mapc.db import init_db
from mapc.models.camera import Camera
from mapc.routes.scans import get_scan, save_scanned_camera


class ScanImportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        init_db(self.engine)
        self.job = {
            "status": "completed",
            "result": {
                "network": {
                    "onvif": [
                        {
                            "ip": "192.0.2.1",
                            "port": 80,
                            "protocol": "onvif",
                            "mac_address": None,
                            "streams": [
                                {
                                    "profile": "Main",
                                    "token": "1",
                                    "uri": "rtsp://192.0.2.1/main",
                                }
                            ],
                        }
                    ],
                    "errors": [
                        {
                            "ip": "192.0.2.2",
                            "port": 443,
                            "protocol": "onvif",
                            "error": "ONVIF disabled",
                        }
                    ],
                }
            },
        }

        def get(scan_id):
            if scan_id != "scan":
                raise KeyError(scan_id)
            return deepcopy(self.job)

        self.request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(scan_manager=SimpleNamespace(get=get))
            )
        )

    def tearDown(self):
        self.engine.dispose()

    def test_import_preserves_streams_and_prevents_repeat(self):
        with Session(self.engine) as db:
            saved = save_scanned_camera("scan", 0, self.request, db)
            self.assertFalse(saved["already_exists"])
            self.assertNotIn("uri", str(saved))
            camera = db.get(Camera, saved["id"])
            self.assertEqual(camera.mac_address, "")
            self.assertEqual(camera.streams[0].uri, "rtsp://192.0.2.1/main")
            repeated = save_scanned_camera("scan", 0, self.request, db)
            self.assertTrue(repeated["already_exists"])
            self.assertEqual(repeated["id"], saved["id"])
            self.assertEqual(len(db.exec(select(Camera)).all()), 1)
            with self.assertRaises(HTTPException) as caught:
                save_scanned_camera("scan", 1, self.request, db)
            self.assertEqual(caught.exception.status_code, 409)
            self.assertEqual(
                self.job["result"]["network"]["onvif"][0]["mac_address"], None
            )

    def test_missing_or_unfinished_scan_and_invalid_index(self):
        with Session(self.engine) as db:
            for scan_id, index in [("missing", 0), ("scan", -1), ("scan", 2)]:
                with self.assertRaises(HTTPException) as caught:
                    save_scanned_camera(scan_id, index, self.request, db)
                self.assertEqual(caught.exception.status_code, 404)
            self.job["status"] = "running"
            with self.assertRaises(HTTPException) as caught:
                save_scanned_camera("scan", 0, self.request, db)
            self.assertEqual(caught.exception.status_code, 409)

    def test_results_check_current_database_without_mutating_scan(self):
        with Session(self.engine) as db:
            before = get_scan("scan", self.request, db)
            self.assertFalse(before["result"]["network"]["onvif"][0]["already_exists"])
            saved = save_scanned_camera("scan", 0, self.request, db)
            after = get_scan("scan", self.request, db)
            camera = after["result"]["network"]["onvif"][0]
            self.assertTrue(camera["already_exists"])
            self.assertEqual(camera["camera_id"], saved["id"])
            self.assertEqual(camera["streams"][0]["uri"], "rtsp://192.0.2.1/main")
            self.assertFalse(after["result"]["network"]["errors"][0]["already_exists"])
            original = self.job["result"]["network"]["onvif"][0]
            self.assertNotIn("already_exists", original)
            self.assertIn("uri", original["streams"][0])
            db.delete(db.get(Camera, saved["id"]).streams[0])
            db.delete(db.get(Camera, saved["id"]))
            db.commit()
            self.assertFalse(
                get_scan("scan", self.request, db)["result"]["network"]["onvif"][0][
                    "already_exists"
                ]
            )
