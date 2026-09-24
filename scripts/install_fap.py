#!/usr/bin/env python3
"""Stage the standalone Flipper app in an official firmware checkout."""

import argparse
import shutil
from pathlib import Path


def install(firmware: Path) -> None:
    firmware = firmware.resolve()
    if not (firmware / "fbt").is_file() or not (firmware / "applications_user").is_dir():
        raise SystemExit(f"Not a Flipper firmware checkout: {firmware}")

    source = Path(__file__).resolve().parents[1] / "flipper"
    destination = firmware / "applications_user" / "switch_controller"
    destination.mkdir(exist_ok=True)
    for file in source.iterdir():
        if file.is_file() and file.suffix in {".c", ".h"}:
            shutil.copy2(file, destination / file.name)
    shutil.copy2(source / "fap" / "application.fam", destination / "application.fam")
    print(f"Installed {destination}; run ./fbt fap_switch_controller")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("firmware", type=Path)
    install(parser.parse_args().firmware)
