import unittest
from unittest.mock import AsyncMock, patch

from mapc.services.checker import Checker, onvif_error


class CheckerTests(unittest.IsolatedAsyncioTestCase):
    async def test_failures_remain_in_results(self):
        checker = Checker(
            cams={"192.0.2.1": [80], "192.0.2.2": [554]},
            usernames=["admin"],
            passwords=["secret"],
        )
        with patch.object(
            Checker,
            "_attempt",
            new=AsyncMock(
                return_value={
                    "error": "GetDeviceInformation: ONVIF is disabled in the device settings"
                }
            ),
        ):
            result = await checker.run()
        self.assertEqual(result["onvif"], [])
        self.assertEqual(len(result["errors"]), 2)
        self.assertIn("disabled", result["errors"][0]["error"])
        self.assertEqual(result["errors"][1]["open_ports"], [554])

    async def test_success_after_failed_credentials(self):
        checker = Checker(
            cams={"192.0.2.1": [81]}, usernames=["admin"], passwords=["a", "b"]
        )
        camera = {"ip": "192.0.2.1", "port": 81, "protocol": "onvif", "streams": []}
        with patch.object(
            Checker,
            "_attempt",
            new=AsyncMock(side_effect=[{"error": "Authentication failed"}, camera]),
        ) as attempt:
            result = await checker.run()
        self.assertEqual(result["onvif"], [camera])
        self.assertEqual(result["errors"], [])
        self.assertEqual(attempt.await_count, 2)

    async def test_missing_credentials(self):
        checker = Checker(cams={"192.0.2.1": [80]}, usernames=[], passwords=[])
        result = await checker.run()
        self.assertIn("not configured", result["errors"][0]["error"])

    def test_error_messages_do_not_expose_response_secrets(self):
        cases = [
            ("ONVIF integrate function is disabled", "disabled"),
            ("401 Unauthorized", "authentication"),
            ("403 Forbidden", "permissions"),
            ("Read timed out", "timeout"),
            ("404 Not Found", "not found"),
            ("Connection refused", "connect"),
            ("SOAP fault", "format"),
        ]
        for raw, expected in cases:
            message = onvif_error(
                Exception(raw + " rtsp://admin:secret@192.0.2.1/main")
            )
            self.assertIn(expected, message)
            self.assertNotIn("secret", message)
            self.assertNotIn("rtsp://", message)

    async def test_custom_port_is_checked_by_onvif(self):
        checker = Checker(
            cams={"192.0.2.1": [8081]}, usernames=["admin"], passwords=["test"]
        )
        camera = {"ip": "192.0.2.1", "port": 8081, "protocol": "onvif", "streams": []}
        with patch.object(
            Checker, "_attempt", new=AsyncMock(return_value=camera)
        ) as attempt:
            result = await checker.run()
        attempt.assert_awaited_once_with("192.0.2.1", 8081, "admin", "test")
        self.assertEqual(result["onvif"], [camera])
