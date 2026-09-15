import asyncio
import logging
from multiprocessing import get_context
from multiprocessing.queues import Queue
from queue import Empty
from typing import Any

import onvif.operator as onvif_operator
from onvif import ONVIFClient
from onvif.utils import ONVIFOperationException
from pydantic import BaseModel, Field
from requests.auth import HTTPDigestAuth
from requests.exceptions import RequestException
from zeep import Transport

logger = logging.getLogger(__name__)
CAMERA_ERRORS = (
    ONVIFOperationException,
    RequestException,
    OSError,
    ValueError,
    TypeError,
    AttributeError,
)


def onvif_error(error: Exception) -> str:
    # Never expose raw SOAP responses: they may contain credentials or stream URIs.
    detail = str(error).lower()
    if "onvif integrate function is disabled" in detail:
        return "ONVIF is disabled in the device settings"
    if (
        "401" in detail
        or "notauthorized" in detail
        or "authentication failed" in detail
    ):
        return "ONVIF authentication failed: check the ONVIF username and password"
    if "403" in detail or "forbidden" in detail:
        return "Insufficient ONVIF user permissions"
    if "timeout" in detail or "timed out" in detail:
        return "ONVIF response timeout"
    if "404" in detail:
        return "ONVIF service not found (HTTP 404)"
    if "connection" in detail:
        return "Could not connect to the ONVIF service"
    return "Invalid ONVIF response or unsupported data format"


class Checker(BaseModel):
    cams: dict[str, list[int]]
    usernames: list[str] = [
        "admin",
    ]
    passwords: list[str]
    timeout: float = 10
    concurrency: int = Field(default=4, ge=1, le=32)
    verified_cams: dict[str, list[dict[str, Any]]] = {"onvif": [], "errors": []}

    @property
    def get_verified_cams(self):
        return self.verified_cams

    def worker_onvif(
        self, queue: Queue, host: str, port: int, username: str, password: str
    ):
        stage = "Connecting"
        try:
            # This override is isolated to this disposable child process.
            class AuthTransport(Transport):
                def __init__(transport_self, *args, **kwargs):
                    kwargs["session"].auth = HTTPDigestAuth(username, password)
                    kwargs["operation_timeout"] = min(self.timeout, 3)
                    super().__init__(*args, **kwargs)

            onvif_operator.Transport = AuthTransport
            client = ONVIFClient(
                host=host,
                port=port,
                username=username,
                password=password,
                timeout=min(self.timeout, 3),
                use_https=port == 443,
            )

            stage = "GetDeviceInformation"
            device = client.devicemgmt()
            info = device.GetDeviceInformation()

            stage = "GetProfiles"
            media = client.media()
            profiles = media.GetProfiles()

            streams = []

            stage = "GetStreamUri"
            for profile in profiles:
                stream = media.GetStreamUri(
                    ProfileToken=profile.token,
                    StreamSetup={
                        "Stream": "RTP-Unicast",
                        "Transport": {"Protocol": "RTSP"},
                    },
                )

                streams.append(
                    {
                        "profile": profile.Name,
                        "token": profile.token,
                        "uri": stream.Uri,
                    }
                )

            mac_address = None
            try:
                interfaces = device.GetNetworkInterfaces()
                for interface in interfaces:
                    mac_address = getattr(
                        getattr(interface, "Info", None), "HwAddress", None
                    )
                    if mac_address:
                        break
            except CAMERA_ERRORS as error:
                logger.debug(
                    "Optional network interface lookup failed: %s", type(error).__name__
                )

            queue.put(
                {
                    "ip": host,
                    "protocol": "onvif",
                    "port": port,
                    "manufacturer": info.Manufacturer,
                    "model": info.Model,
                    "firmware": info.FirmwareVersion,
                    "serial_number": info.SerialNumber,
                    "mac_address": mac_address,
                    "streams": streams,
                }
            )

        # The process boundary must return a result even for unexpected SDK failures.
        except Exception as er:  # noqa: BLE001
            logger.warning("ONVIF worker failed at %s: %s", stage, type(er).__name__)
            queue.put({"error": f"{stage}: {onvif_error(er)}"})

    async def _attempt(self, host: str, port: int, username: str, password: str):
        context = get_context("spawn")
        queue = context.Queue()
        process = context.Process(
            target=self.worker_onvif,
            args=(queue, host, port, username, password),
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        started = False
        try:
            process.start()
            started = True
            while loop.time() < deadline:
                try:
                    return queue.get_nowait()
                except Empty:
                    if not process.is_alive():
                        try:
                            return queue.get_nowait()
                        except Empty:
                            return {
                                "error": "The ONVIF check process exited without a response"
                            }
                    await asyncio.sleep(0.05)
            return {"error": "The ONVIF check exceeded its total timeout"}
        except (OSError, ValueError, RuntimeError):
            return {"error": "Could not run the ONVIF check"}
        finally:
            if started:
                if process.is_alive():
                    process.terminate()
                cleanup_deadline = loop.time() + 1
                while process.is_alive() and loop.time() < cleanup_deadline:
                    await asyncio.sleep(0.02)
                if process.is_alive():
                    process.kill()
                while process.is_alive():
                    await asyncio.sleep(0.02)
                process.join(timeout=0)
            queue.close()
            process.close()

    async def detect_onvif(
        self, host: str, ports: list[int], usernames: list[str], passwords: list[str]
    ) -> dict[str, Any]:
        candidates = sorted(set(ports))
        failure = {
            "ip": host,
            "port": candidates[0] if candidates else (ports[0] if ports else None),
            "protocol": "onvif",
            "open_ports": ports,
            "streams": [],
        }
        if not candidates:
            return {
                **failure,
                "error": "No open ports available for the ONVIF check",
            }
        if not usernames or not passwords:
            return {**failure, "error": "ONVIF username or password is not configured"}
        errors = []
        for port in candidates:
            for password in passwords:
                for username in usernames:
                    result = await self._attempt(host, port, username, password)
                    if not result.get("error"):
                        return {**result, "username": username, "password": password}
                    message = f"Port {port}: {result['error']}"
                    if message not in errors:
                        errors.append(message)
        return {**failure, "error": "; ".join(errors)}

    async def run(self) -> dict[str, list[dict[str, Any]]]:
        self.verified_cams = {"onvif": [], "errors": []}
        semaphore = asyncio.Semaphore(self.concurrency)

        async def check(host, ports):
            async with semaphore:
                return await self.detect_onvif(
                    host, ports, self.usernames, self.passwords
                )

        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(check(host, ports))
                for host, ports in self.cams.items()
            ]

        for task in tasks:
            result = task.result()
            if result:
                category = "errors" if result.get("error") else "onvif"
                self.verified_cams[category].append(result)
        return self.verified_cams


if __name__ == "__main__":
    ...
