import asyncio
import logging
from copy import deepcopy
from typing import Any
from uuid import uuid4

from mapc.services.checker import Checker
from mapc.services.scanner import Scanner
from mapc.settings import AppSettings, ScanConfig

logger = logging.getLogger(__name__)


class ScanError(Exception): ...


class ScanManager:
    def __init__(self, settings: AppSettings, config: ScanConfig):
        self.settings = settings
        self.config = config
        self.task: asyncio.Task[None] | None = None
        self.job: dict[str, Any] | None = None
        self.results: dict[str, Any] = {}

    @property
    def result(self) -> dict[str, Any]:
        return deepcopy(self.results)

    def get(self, scan_id: str) -> dict[str, Any]:
        if self.job is None or self.job["id"] != scan_id:
            raise KeyError(scan_id)

        return deepcopy(self.job)

    def start(self) -> dict[str, Any]:
        if self.task is not None and not self.task.done():
            raise ScanError("A scan is already running")

        self.job = {
            "id": str(uuid4()),
            "status": "running",
            "result": None,
            "error": None,
        }

        self.task = asyncio.create_task(self.run())
        return self.get(self.job["id"])

    async def discover(self) -> None:
        self.results.clear()

        for network in self.config.networks:
            scanner = Scanner(
                network=network,
                ports=self.config.ports,
                excluded_ips=self.settings.excluded_ips,
                timeout=self.config.scanner_timeout,
                concurrency=self.config.concurrency,
            )
            hosts = await scanner.run()

            checker = Checker(
                cams=hosts,
                usernames=self.settings.usernames,
                passwords=self.settings.passwords,
                timeout=self.config.camera_timeout,
                concurrency=self.config.camera_concurrency,
            )
            cameras = await checker.run()

            self.results[str(network)] = cameras

    async def run(self) -> None:
        assert self.job is not None

        try:
            await self.discover()
        except asyncio.CancelledError:
            self.job["status"] = "cancelled"
            raise
        # Keep unexpected background failures visible as a terminal scan status.
        except Exception as error:  # noqa: BLE001
            logger.error("Scan failed: %s", type(error).__name__)
            self.job["status"] = "failed"
            self.job["error"] = "Scan failed"
        else:
            self.job["result"] = self.results
            self.job["status"] = "completed"

    async def close(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

            if self.task.cancelled() and self.job is not None:
                self.job["status"] = "cancelled"


if __name__ == "__main__":
    ...
