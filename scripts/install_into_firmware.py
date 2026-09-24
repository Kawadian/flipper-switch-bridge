#!/usr/bin/env python3
"""Install or update the built-in app in an official firmware checkout."""

import argparse
import shutil
from pathlib import Path


def install(firmware: Path) -> None:
    firmware = firmware.resolve()
    manifest = firmware / "applications/main/application.fam"
    if not manifest.is_file():
        raise SystemExit(f"Not a Flipper firmware checkout: {firmware}")
    source = Path(__file__).resolve().parents[1] / "flipper"
    destination = manifest.parent / "switch_controller"
    destination.mkdir(exist_ok=True)
    for file in source.iterdir():
        if file.is_file() and file.suffix in {".c", ".h", ".fam"}:
            shutil.copy2(file, destination / file.name)
    contents = manifest.read_text()
    if '"switch_controller"' not in contents:
        anchor = 'appid="main_apps"'
        start = contents.find(anchor)
        provides = contents.find("provides=[", start)
        if start < 0 or provides < 0:
            raise SystemExit("Cannot locate the main_apps provides list")
        insert = contents.find("\n", provides) + 1
        contents = contents[:insert] + '        "switch_controller",\n' + contents[insert:]
        manifest.write_text(contents)
    print(f"Installed {destination}; run ./fbt firmware_all")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("firmware", type=Path)
    install(parser.parse_args().firmware)
