import unittest
from ipaddress import IPv4Address
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from mapc.services.scan_manager import ScanManager
from mapc.services.scanner import Scanner
from mapc.settings import AppSettings, ScanConfig


class ExcludedAddressesTests(unittest.IsolatedAsyncioTestCase):
    async def test_excluded_hosts_never_have_ports_checked(self):
        scanner = Scanner(
            network="192.0.2.0/29",
            ports=[80, 554],
            excluded_ips=["192.0.2.2", "192.0.2.4"],
        )

        async def found(host, port, semaphore):
            return str(host), port

        with patch.object(
            Scanner, "check_port", new=AsyncMock(side_effect=found)
        ) as check:
            result = await scanner.run()
        self.assertEqual(
            set(result), {"192.0.2.1", "192.0.2.3", "192.0.2.5", "192.0.2.6"}
        )
        self.assertEqual(check.await_count, 8)

    async def test_env_setting_reaches_scanner_and_onvif(self):
        with TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text('MAPC_EXCLUDED_IPS=["192.0.2.1","192.0.2.2"]\n')
            settings = AppSettings(_env_file=env, admin_password="test")
        self.assertIn(IPv4Address("192.0.2.1"), settings.excluded_ips)
        manager = ScanManager(settings, ScanConfig(networks=["192.0.2.0/30"]))
        with patch.object(Scanner, "check_port", new=AsyncMock()) as check:
            await manager.discover()
        check.assert_not_awaited()
        self.assertEqual(manager.results["192.0.2.0/30"], {"onvif": [], "errors": []})

    def test_invalid_address_rejected(self):
        with self.assertRaises(ValidationError):
            AppSettings(_env_file=None, admin_password="test", excluded_ips=["invalid"])

    async def test_ports_from_env_reach_scanner(self):
        with TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("MAPC_SCAN_PORTS=[81,8080]\n")
            config = ScanConfig(_env_file=env, networks=["192.0.2.0/30"])
        self.assertEqual(config.ports, {81, 8080})
        settings = AppSettings(_env_file=None, admin_password="test", excluded_ips=[])
        manager = ScanManager(settings, config)
        with patch.object(
            Scanner, "check_port", new=AsyncMock(return_value=None)
        ) as check:
            await manager.discover()
        self.assertCountEqual(
            [call.kwargs["port"] for call in check.await_args_list],
            [81, 8080, 81, 8080],
        )

    def test_invalid_scan_ports_from_env(self):
        with TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            for ports in ["[0]", "[65536]", '["bad"]']:
                env.write_text("MAPC_SCAN_PORTS=" + ports + "\n")
                with self.assertRaises(ValidationError):
                    ScanConfig(_env_file=env, networks=["192.0.2.0/30"])

    async def test_networks_from_env_reach_scanner(self):
        with TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text(
                'MAPC_SCAN_NETWORKS=["192.0.2.0/30","198.51.100.0/30"]\nMAPC_SCAN_PORTS=[80]\n'
            )
            config = ScanConfig(_env_file=env)
        settings = AppSettings(_env_file=None, admin_password="test", excluded_ips=[])
        manager = ScanManager(settings, config)
        with patch.object(
            Scanner, "check_port", new=AsyncMock(return_value=None)
        ) as check:
            await manager.discover()
        self.assertEqual(
            {str(call.kwargs["host"]) for call in check.await_args_list},
            {"192.0.2.1", "192.0.2.2", "198.51.100.1", "198.51.100.2"},
        )

    def test_invalid_networks_from_env(self):
        with TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            for networks in ['["invalid"]', '["192.0.2.0/33"]', '["2001:db8::/64"]']:
                env.write_text("MAPC_SCAN_NETWORKS=" + networks + "\n")
                with self.assertRaises(ValidationError):
                    ScanConfig(_env_file=env)
