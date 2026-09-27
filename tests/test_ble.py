import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))
from flipper_link.ble import find_flipper


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_bridge_identity_is_distinct_from_default_flipper(self):
        default = SimpleNamespace(address="00:00:00:00:00:01", name="Flipper Domuzir")
        bridge = SimpleNamespace(address="00:00:00:00:00:03", name="SwitchLink Domuzir")
        with patch("flipper_link.ble.BleakScanner.discover",
                   new=AsyncMock(return_value=[default, bridge])):
            self.assertIs(await find_flipper(), bridge)
            self.assertIs(await find_flipper(bridge.address), bridge)
            with self.assertRaises(RuntimeError):
                await find_flipper(default.address)


if __name__ == "__main__":
    unittest.main()
