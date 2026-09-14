import asyncio
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from PIL import Image

from mapc.routes.cameras import camera_snapshot
from mapc.services.snapshot import (
    SnapshotError,
    SnapshotService,
    camera_url,
    download_image,
    fetch_snapshot,
    rtsp_frame,
)


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    def test_snapshot_address_stays_on_camera(self):
        self.assertEqual(
            camera_url("http://192.0.2.1/snapshot", "192.0.2.1"),
            "http://192.0.2.1/snapshot",
        )
        for uri in [
            "http://192.0.2.2/snapshot",
            "file:///etc/passwd",
            "http://user:pass@192.0.2.1/snapshot",
        ]:
            with self.assertRaises(SnapshotError):
                camera_url(uri, "192.0.2.1")

    def test_image_download_checks_actual_content(self):
        output = BytesIO()
        Image.new("RGB", (10, 10)).save(output, "JPEG")
        data = output.getvalue()
        with patch("mapc.services.snapshot.requests.Session") as factory:
            response = factory.return_value.__enter__.return_value.get.return_value.__enter__.return_value
            response.is_redirect = False
            response.iter_content.return_value = [data]
            self.assertEqual(
                download_image("http://192.0.2.1/image", "192.0.2.1", "user", "secret"),
                (data, "image/jpeg"),
            )
            response.iter_content.return_value = [b"<html>login</html>"]
            with self.assertRaises(SnapshotError):
                download_image("http://192.0.2.1/image", "192.0.2.1", "user", "secret")

    def test_credentials_retry_and_snapshot_profile(self):
        failed = MagicMock()
        failed.GetCapabilities.side_effect = ValueError("401 secret")
        device = MagicMock()
        device.GetCapabilities.return_value.Media.XAddr = "http://192.0.2.1/onvif/Media"
        media = MagicMock()
        media.GetProfiles.return_value = [SimpleNamespace(token="main")]
        media.GetSnapshotUri.return_value.Uri = "http://192.0.2.1/image"
        with (
            patch("mapc.services.snapshot.Device", side_effect=[failed, device]),
            patch("mapc.services.snapshot.Media", return_value=media),
            patch(
                "mapc.services.snapshot.download_image",
                return_value=(b"image", "image/jpeg"),
            ) as download,
        ):
            self.assertEqual(
                fetch_snapshot("192.0.2.1", 80, ["admin", "mapc"], ["secret"]),
                (b"image", "image/jpeg"),
            )
            media.GetSnapshotUri.assert_called_once_with(ProfileToken="main")
            download.assert_called_once_with(
                "http://192.0.2.1/image", "192.0.2.1", "mapc", "secret"
            )

    def test_unsupported_snapshot_is_not_overwritten_by_other_credentials(self):
        device = MagicMock()
        device.GetCapabilities.return_value.Media.XAddr = "http://192.0.2.1/media"
        failed = MagicMock()
        failed.GetCapabilities.side_effect = ValueError("401")
        media = MagicMock()
        media.GetProfiles.return_value = [
            SimpleNamespace(token="main"),
            SimpleNamespace(token="sub"),
        ]
        media.GetSnapshotUri.side_effect = ValueError(
            "ActionNotSupported: Optional Action Not Implemented"
        )
        media.GetStreamUri.side_effect = ValueError("ActionNotSupported")
        with (
            patch("mapc.services.snapshot.Device", side_effect=[device, failed]),
            patch("mapc.services.snapshot.Media", return_value=media),
            self.assertRaisesRegex(SnapshotError, "does not support ONVIF snapshots"),
        ):
            fetch_snapshot("192.0.2.1", 80, ["valid", "invalid"], ["secret"])
        self.assertEqual(media.GetSnapshotUri.call_count, 2)

    def test_rtsp_fallback_after_unsupported_snapshot(self):
        device, media = MagicMock(), MagicMock()
        device.GetCapabilities.return_value.Media.XAddr = "http://192.0.2.1/media"
        media.GetProfiles.return_value = [SimpleNamespace(token="main")]
        media.GetSnapshotUri.side_effect = ValueError("ActionNotSupported")
        media.GetStreamUri.return_value.Uri = "rtsp://192.0.2.1/live"
        with (
            patch("mapc.services.snapshot.Device", return_value=device),
            patch("mapc.services.snapshot.Media", return_value=media),
            patch(
                "mapc.services.snapshot.rtsp_frame",
                return_value=(b"jpeg", "image/jpeg"),
            ) as capture,
        ):
            self.assertEqual(
                fetch_snapshot("192.0.2.1", 80, ["user"], ["secret"]),
                (b"jpeg", "image/jpeg"),
            )
        capture.assert_called_once_with(
            "rtsp://192.0.2.1/live", "192.0.2.1", "user", "secret"
        )

    def test_rtsp_validates_host_and_frame_and_encodes_credentials(self):
        output = BytesIO()
        Image.new("RGB", (10, 10)).save(output, "JPEG")
        with patch("mapc.services.snapshot.subprocess.run") as run:
            with self.assertRaises(SnapshotError):
                rtsp_frame("rtsp://192.0.2.2/live", "192.0.2.1", "u", "p")
            run.assert_not_called()
            run.return_value = SimpleNamespace(returncode=0, stdout=output.getvalue())
            self.assertEqual(
                rtsp_frame("rtsp://192.0.2.1:554/live", "192.0.2.1", "a@", "p:/")[1],
                "image/jpeg",
            )
            self.assertIn(
                "rtsp://a%40:p%3A%2F@192.0.2.1:554/live", run.call_args.args[0]
            )
            run.return_value = SimpleNamespace(returncode=0, stdout=b"not an image")
            with self.assertRaisesRegex(SnapshotError, "invalid image"):
                rtsp_frame("rtsp://192.0.2.1/live", "192.0.2.1", "u", "p")

    async def test_parallel_requests_share_fetch_but_next_hover_is_fresh(self):
        service = SnapshotService(SimpleNamespace(usernames=["u"], passwords=["p"]))
        started, release = asyncio.Event(), asyncio.Event()

        async def worker(*args):
            started.set()
            await release.wait()
            return b"image", "image/jpeg"

        with patch(
            "mapc.services.snapshot.snapshot_process", new=AsyncMock(side_effect=worker)
        ) as fetch:
            a = asyncio.create_task(service.get(1, "192.0.2.1", 80))
            await started.wait()
            b = asyncio.create_task(service.get(1, "192.0.2.1", 80))
            await asyncio.sleep(0)
            release.set()
            self.assertEqual(await a, await b)
            self.assertEqual(fetch.await_count, 1)
            await service.get(1, "192.0.2.1", 80)
            self.assertEqual(fetch.await_count, 2)
        await service.close()

    async def test_route_image_errors_and_missing_camera(self):
        snapshots = SimpleNamespace(
            get=AsyncMock(return_value=(b"image", "image/jpeg"))
        )
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(snapshots=snapshots))
        )
        db = MagicMock()
        db.get.return_value = SimpleNamespace(
            id=1, ip="192.0.2.1", port=80, protocol="onvif"
        )
        response = await camera_snapshot(1, request, db)
        self.assertEqual(response.body, b"image")
        self.assertEqual(response.headers["cache-control"], "no-store")
        snapshots.get.side_effect = SnapshotError("Camera unavailable")
        with self.assertRaises(HTTPException) as error:
            await camera_snapshot(1, request, db)
        self.assertEqual(error.exception.status_code, 502)
        db.get.return_value = None
        with self.assertRaises(HTTPException) as error:
            await camera_snapshot(1, request, db)
        self.assertEqual(error.exception.status_code, 404)

    async def test_subprocess_accepts_settings_sets(self):
        import json

        from mapc.services.snapshot import snapshot_process

        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(
                return_value=(b'{"data":"aW1hZ2U=","mime":"image/jpeg"}', b"")
            ),
        )
        with patch(
            "mapc.services.snapshot.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ):
            self.assertEqual(
                await snapshot_process("192.0.2.1", 80, {"mapc"}, {"test"}),
                (b"image", "image/jpeg"),
            )
        payload = json.loads(process.communicate.await_args.args[0])
        self.assertEqual(payload["usernames"], ["mapc"])
        self.assertEqual(payload["passwords"], ["test"])
