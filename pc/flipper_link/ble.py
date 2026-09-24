"""BLE client for the Flipper serial GATT RX characteristic."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from bleak import BleakClient, BleakScanner

from .protocol import ControllerState, encode

SERIAL_SERVICE_UUID = "8fe5b3d5-2e7f-4a98-2a48-7acc60fe0000"
SERIAL_RX_UUID = "19ed82ae-ed21-4c9d-4145-228e62fe0000"


async def find_flipper(address: str | None = None, timeout: float = 8.0):
    devices = await BleakScanner.discover(timeout=timeout)
    if address:
        matches = [device for device in devices if device.address.lower() == address.lower()]
    else:
        matches = [device for device in devices if device.name and
                   device.name.lower().startswith("flipper")]
    if len(matches) != 1:
        raise RuntimeError(
            f"Found {len(matches)} matching Flippers. "
            "Launch BLE receiver/bridge on the device and pass --address if needed.")
    return matches[0]


class ControllerLink:
    def __init__(self, client: BleakClient):
        self._client = client
        self._sequence = 0

    async def send(self, state: ControllerState) -> None:
        if not self._client.is_connected:
            raise ConnectionError("Flipper disconnected")
        await self._client.write_gatt_char(
            SERIAL_RX_UUID, encode(state, self._sequence), response=True)
        self._sequence = (self._sequence + 1) & 0xFF

    async def hold(self, state: ControllerState, seconds: float) -> None:
        """Keep a state alive during a bounded hold; release on all exits."""
        if seconds < 0:
            raise ValueError("seconds must not be negative")
        try:
            end = asyncio.get_running_loop().time() + seconds
            while True:
                await self.send(state)
                remaining = end - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(0.1, remaining))
        finally:
            if self._client.is_connected:
                await self.send(ControllerState())

    @classmethod
    @asynccontextmanager
    async def connect(cls, address: str | None = None) -> AsyncIterator["ControllerLink"]:
        device = await find_flipper(address)
        async with BleakClient(device, pair=True, timeout=30.0) as client:
            if client.services.get_characteristic(SERIAL_RX_UUID) is None:
                raise RuntimeError("Serial RX characteristic missing: is the BLE app running?")
            link = cls(client)
            try:
                yield link
            finally:
                if client.is_connected:
                    await link.send(ControllerState())
