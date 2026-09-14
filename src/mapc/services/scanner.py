import asyncio
import ipaddress

from pydantic import BaseModel, Field


class Scanner(BaseModel):
    network: ipaddress.IPv4Network
    ports: list[int]
    excluded_ips: set[ipaddress.IPv4Address] = Field(default_factory=set)
    timeout: float = 5.0
    concurrency: int = 10

    async def check_port(
        self, host: ipaddress.IPv4Address, port: int, semaphore: asyncio.Semaphore
    ):
        async with semaphore:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(str(host), port), timeout=self.timeout
                )
                writer.close()
                await writer.wait_closed()
                return str(host), port
            except (TimeoutError, ConnectionRefusedError, OSError):
                return None

    async def run(self) -> dict[str, list[int]]:
        semaphore = asyncio.Semaphore(self.concurrency)

        tasks = [
            self.check_port(host=host, port=port, semaphore=semaphore)
            for host in self.network.hosts()
            if host not in self.excluded_ips
            for port in self.ports
        ]

        results = await asyncio.gather(*tasks)

        cameras = {}

        for result in results:
            if result is None:
                continue

            host, port = result
            cameras.setdefault(host, []).append(port)

        return cameras


if __name__ == "__main__":
    ...
