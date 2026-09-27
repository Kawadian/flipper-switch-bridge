"""BLE client for the Flipper serial GATT RX characteristic."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from bleak import BleakClient, BleakScanner

from .protocol import ControllerState, encode

SERIAL_SERVICE_UUID = "8fe5b3d5-2e7f-4a98-2a48-7acc60fe0000"
SERIAL_RX_UUID = "19ed82ae-ed21-4c9d-4145-228e62fe0000"
DEVICE_PREFIX = "switchlink"


async def find_flipper(address: str | None = None, timeout: float = 8.0):
    devices = await BleakScanner.discover(timeout=timeout)
    matches = [device for device in devices if device.name and
               device.name.lower().startswith(DEVICE_PREFIX) and
               (address is None or device.address.lower() == address.lower())]
    if len(matches) != 1:
        raise RuntimeError(
            f"Found {len(matches)} SwitchLink devices. "
            "Start BLE receiver or BLE -> USB Pro, then run scan; "
            "the regular Flipper Bluetooth entry is a different profile.")
    return matches[0]


def _address_int(address: str) -> int:
    return int(address.replace(":", "").replace("-", ""), 16)


async def ensure_paired(address: str) -> None:
    """Pair with numeric comparison. Serial RX requires an authenticated link."""
    from winrt.windows.devices.bluetooth import BluetoothLEDevice
    from winrt.windows.devices.enumeration import (
        DevicePairingKinds,
        DevicePairingResultStatus,
    )

    radio = await BluetoothLEDevice.from_bluetooth_address_async(_address_int(address))
    if radio is None:
        raise RuntimeError(f"Windows could not open {address}")
    pairing = radio.device_information.pairing
    if pairing.is_paired:
        return

    def on_requested(_sender, args) -> None:
        if args.pairing_kind != DevicePairingKinds.CONFIRM_PIN_MATCH:
            print(f"Unexpected pairing request: {args.pairing_kind}", flush=True)
            return
        print(f"Flipper is showing {args.pin}. Press OK on Flipper.", flush=True)
        args.accept()

    token = pairing.custom.add_pairing_requested(on_requested)
    try:
        result = await pairing.custom.pair_async(DevicePairingKinds.CONFIRM_PIN_MATCH)
    finally:
        pairing.custom.remove_pairing_requested(token)
    if result.status not in (
        DevicePairingResultStatus.PAIRED,
        DevicePairingResultStatus.ALREADY_PAIRED,
    ):
        raise RuntimeError(
            f"Pairing failed: {result.status.name}. "
            "Press OK on Flipper when it shows Verify code.")


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
        await ensure_paired(device.address)
        async with BleakClient(device, pair=False, timeout=30.0) as client:
            if client.services.get_characteristic(SERIAL_RX_UUID) is None:
                raise RuntimeError("Serial RX characteristic missing: is the BLE app running?")
            link = cls(client)
            try:
                yield link
            finally:
                if client.is_connected:
                    await link.send(ControllerState())
