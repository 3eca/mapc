"""Read a fresh ONVIF snapshot in an isolated, time-limited process."""

import asyncio
import base64
import json
import logging
import os
import signal
import subprocess
import sys
from io import BytesIO
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from onvif.operator import CacheMode
from onvif.services import Device
from onvif.services.media import Media
from PIL import Image
from requests.auth import HTTPDigestAuth

from mapc.services.checker import CAMERA_ERRORS, onvif_error


class SnapshotError(Exception):
    pass


def camera_url(uri: str, host: str) -> str:
    parsed = urlsplit(uri)
    if (
        parsed.scheme not in ("http", "https")
        or parsed.hostname != host
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SnapshotError(
            "The camera returned a snapshot or service URL on a different device"
        )
    return uri


def configure(service, username, password):
    transport = service.operator.client.transport
    transport.session.auth = HTTPDigestAuth(username, password)
    transport.session.trust_env = False
    transport.operation_timeout = 4
    return service


def download_image(uri, host, username, password):
    camera_url(uri, host)
    with requests.Session() as session:
        session.trust_env = False
        with session.get(
            uri,
            auth=HTTPDigestAuth(username, password),
            timeout=(4, 6),
            allow_redirects=False,
            stream=True,
        ) as response:
            response.raise_for_status()
            if response.is_redirect:
                raise SnapshotError(
                    "The camera redirected the snapshot request to another URL"
                )
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > 16 * 1024 * 1024:
                    raise SnapshotError("The snapshot is too large for preview")
    try:
        with Image.open(BytesIO(data), formats=["JPEG", "PNG"]) as image:
            mime = "image/jpeg" if image.format == "JPEG" else "image/png"
            image.verify()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise SnapshotError("The camera returned an invalid image") from None
    return bytes(data), mime


def rtsp_frame(uri, host, username, password):
    parsed = urlsplit(uri)
    if parsed.scheme != "rtsp" or parsed.hostname != host:
        raise SnapshotError("The camera returned an RTSP URL on a different device")
    # Use the credentials that successfully retrieved the ONVIF profiles.
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}"
    if parsed.port is not None:
        netloc += f":{parsed.port}"
    source = urlunsplit(parsed._replace(netloc=netloc))
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-rtsp_transport",
                "tcp",
                "-timeout",
                "5000000",
                "-i",
                source,
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-threads",
                "1",
                "-f",
                "image2pipe",
                "-c:v",
                "mjpeg",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except FileNotFoundError:
        raise SnapshotError("RTSP preview requires FFmpeg on the backend") from None
    except subprocess.TimeoutExpired:
        raise SnapshotError("RTSP frame capture timed out") from None
    if result.returncode or not result.stdout:
        raise SnapshotError("Could not decode a frame from the camera RTSP stream")
    try:
        with Image.open(BytesIO(result.stdout), formats=["JPEG"]) as image:
            image.verify()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise SnapshotError("RTSP capture returned an invalid image") from None
    return result.stdout, "image/jpeg"


def fetch_snapshot(host, port, usernames, passwords):
    if not usernames or not passwords:
        raise SnapshotError("Camera credentials are not configured")
    last_error = "Could not retrieve the snapshot"
    snapshot_error = None
    for password in passwords:
        for username in usernames:
            try:
                options = {
                    "host": host,
                    "port": port,
                    "username": username,
                    "password": password,
                    "timeout": 4,
                    "cache": CacheMode.NONE,
                    "use_https": port == 443,
                }
                device = configure(Device(**options), username, password)
                capabilities = device.GetCapabilities(Category="Media")
                uri = camera_url(capabilities.Media.XAddr, host)
                media = configure(Media(xaddr=uri, **options), username, password)
                profiles = media.GetProfiles()
                if not profiles:
                    raise SnapshotError("The camera returned no video profiles")
                # Prefer the first available profile, but try others if snapshot is unsupported.
                for profile in profiles:
                    try:
                        snapshot = media.GetSnapshotUri(ProfileToken=profile.token)
                        return download_image(snapshot.Uri, host, username, password)
                    except SnapshotError as error:
                        snapshot_error = str(error)
                    except CAMERA_ERRORS as error:
                        detail = str(error).lower()
                        if (
                            "actionnotsupported" in detail
                            or "optional action not implemented" in detail
                        ):
                            snapshot_error = "The camera does not support ONVIF snapshots (GetSnapshotUri)"
                        else:
                            snapshot_error = "ONVIF snapshot: " + onvif_error(error)
                onvif_failure = snapshot_error
                for profile in profiles:
                    try:
                        stream = media.GetStreamUri(
                            ProfileToken=profile.token,
                            StreamSetup={
                                "Stream": "RTP-Unicast",
                                "Transport": {"Protocol": "RTSP"},
                            },
                        )
                        return rtsp_frame(stream.Uri, host, username, password)
                    except SnapshotError as error:
                        snapshot_error = f"{onvif_failure}; RTSP fallback: {error}"
                    except CAMERA_ERRORS as error:
                        snapshot_error = (
                            f"{onvif_failure}; RTSP fallback: " + onvif_error(error)
                        )
            except SnapshotError as error:
                last_error = str(error)
            except CAMERA_ERRORS as error:
                last_error = "ONVIF snapshot: " + onvif_error(error)
    raise SnapshotError(snapshot_error or last_error)


async def snapshot_process(host, port, usernames, passwords):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "mapc.services.snapshot",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        payload = json.dumps(
            {
                "host": host,
                "port": port,
                "usernames": list(usernames),
                "passwords": list(passwords),
            }
        ).encode()
        output, _ = await asyncio.wait_for(process.communicate(payload), timeout=30)
        if process.returncode:
            raise SnapshotError("Could not execute the snapshot request")
        result = json.loads(output)
        if "error" in result:
            raise SnapshotError(result["error"])
        return base64.b64decode(result["data"]), result["mime"]
    except TimeoutError:
        raise SnapshotError(
            "The camera did not provide a snapshot within 30 seconds"
        ) from None
    finally:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()


class SnapshotService:
    def __init__(self, settings):
        self.settings = settings
        self.semaphore = asyncio.Semaphore(4)
        self.pending = {}

    async def get(self, camera_id, host, port):
        # Multiple viewers share an in-flight request, never a stale cached image.
        if camera_id not in self.pending:

            async def run():
                async with self.semaphore:
                    return await snapshot_process(
                        host, port, self.settings.usernames, self.settings.passwords
                    )

            task = asyncio.create_task(run())
            self.pending[camera_id] = task

            def finished(task):
                self.pending.pop(camera_id, None)
                if not task.cancelled():
                    task.exception()

            task.add_done_callback(finished)
        return await asyncio.shield(self.pending[camera_id])

    async def close(self):
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        data, mime = fetch_snapshot(**json.load(sys.stdin))
        print(json.dumps({"data": base64.b64encode(data).decode(), "mime": mime}))
    except SnapshotError as error:
        print(json.dumps({"error": str(error)}))
    # Always emit the worker JSON response without exposing SDK credentials.
    except Exception:  # noqa: BLE001
        print(json.dumps({"error": "Could not retrieve the camera snapshot"}))
