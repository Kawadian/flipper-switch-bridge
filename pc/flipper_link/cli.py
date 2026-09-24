"""Examples: flipper-link scan | flipper-link tap A | flipper-link hold A 1.5."""

import argparse
import asyncio

from bleak import BleakScanner

from .ble import ControllerLink
from .protocol import Button, ControllerState, Hat


def main() -> None:
    parser = argparse.ArgumentParser(description="Send gamepad states to Flipper over BLE")
    parser.add_argument("--address", help="BLE address / platform identifier of your Flipper")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("scan")
    for command in ("tap", "hold"):
        subparser = commands.add_parser(command)
        subparser.add_argument("control", help="A, B, X, Y, HOME, UP, LEFT, ...")
        if command == "hold":
            subparser.add_argument("seconds", type=float)
    args = parser.parse_args()
    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    if args.command == "scan":
        for device in await BleakScanner.discover(timeout=8):
            if device.name and device.name.lower().startswith("flipper"):
                print(device.address, device.name)
        return
    name = args.control.upper()
    try:
        state = ControllerState(buttons=Button[name])
    except KeyError:
        try:
            state = ControllerState(hat=Hat[name])
        except KeyError as error:
            raise SystemExit(f"Unknown control: {name}") from error
    seconds = 0.1 if args.command == "tap" else args.seconds
    async with ControllerLink.connect(args.address) as link:
        await link.hold(state, seconds)


if __name__ == "__main__":
    main()
