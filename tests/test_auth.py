import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from argon2 import PasswordHasher
from fastapi import HTTPException
from pydantic import SecretStr
from starlette.requests import Request
from starlette.responses import Response

from mapc.auth import COOKIE, AuthStore, Login, guard, login, logout


class AuthTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = SimpleNamespace(
            admin_user="admin",
            admin_password=SecretStr(PasswordHasher().hash("test-password-only")),
            session_ttl=60,
            cookie_secure=False,
        )

    def setUp(self):
        self.store = AuthStore(self.settings)

    def request(self, path="/", method="GET", token=None, origin=None):
        headers = [(b"host", b"test")]
        if token:
            headers.append((b"cookie", f"{COOKIE}={token}".encode()))
        if origin:
            headers.append((b"origin", origin.encode()))
        return Request(
            {
                "type": "http",
                "method": method,
                "scheme": "http",
                "path": path,
                "root_path": "",
                "query_string": b"",
                "headers": headers,
                "server": ("test", 80),
                "app": SimpleNamespace(state=SimpleNamespace(auth=self.store)),
            }
        )

    async def next(self, request):
        return Response("protected")

    async def test_guard(self):
        for path in ["/camera/", "/scans/", "/openapi.json", "/auth/me", "/new-route"]:
            self.assertEqual(
                (await guard(self.request(path), self.next)).status_code, 401
            )
        self.assertEqual((await guard(self.request("/"), self.next)).status_code, 303)
        self.assertEqual(
            (await guard(self.request("/login"), self.next)).status_code, 200
        )
        token = self.store.issue()
        self.assertEqual(
            (await guard(self.request("/camera/", token=token), self.next)).status_code,
            200,
        )

    async def test_frontend_bundle_is_public_but_data_stays_protected(self):
        for path in ["/ui/index.html", "/ui/assets/app.js", "/ui/assets/app.css"]:
            self.assertEqual(
                (await guard(self.request(path), self.next)).status_code, 200
            )
        for path in ["/maps/", "/camera/1/snapshot", "/scans/1", "/ui-private"]:
            self.assertEqual(
                (await guard(self.request(path), self.next)).status_code, 401
            )
        self.assertEqual(
            (
                await guard(
                    self.request("/ui/assets/app.js", "POST", origin="http://test"),
                    self.next,
                )
            ).status_code,
            401,
        )

    async def test_csrf(self):
        token = self.store.issue()
        for origin in [None, "http://evil.test"]:
            response = await guard(
                self.request("/scans/", "POST", token, origin), self.next
            )
            self.assertEqual(response.status_code, 403)
        response = await guard(
            self.request("/scans/", "POST", token, "http://test"), self.next
        )
        self.assertEqual(response.status_code, 200)

    async def test_password_and_logout(self):
        # Run inline only in tests; production dispatches Argon2 to a worker thread.
        async def inline(fn, *args):
            return fn(*args)

        with patch("mapc.auth.run_in_threadpool", inline):
            with self.assertRaises(HTTPException) as error:
                await login(Login(username="admin", password="wrong"), self.request())
            self.assertEqual(error.exception.status_code, 401)
            response = await login(
                Login(username="admin", password="test-password-only"), self.request()
            )
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        token = cookie.split(";")[0].split("=", 1)[1]
        self.assertTrue(self.store.valid(token))
        await logout(self.request(token=token))
        self.assertFalse(self.store.valid(token))

    async def test_expiry_and_rate_limit(self):
        token = self.store.issue()
        self.store.sessions[token] = time.monotonic() - 1
        self.assertFalse(self.store.valid(token))
        self.store.attempts.extend([time.monotonic()] * 10)
        with self.assertRaises(HTTPException) as error:
            await login(Login(username="admin", password="wrong"), self.request())
        self.assertEqual(error.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
