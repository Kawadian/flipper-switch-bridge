#!/usr/bin/env python3
"""Package an FBT updater directory for qFlipper and microSD installation."""

import argparse
import tarfile
from pathlib import Path


def package(dist: Path, output: Path) -> None:
    manifests = list(dist.glob("f7-*/f7-update-*/update.fuf"))
    if len(manifests) != 1:
        raise SystemExit(f"Expected one f7 update package under {dist}, found {len(manifests)}")

    update_dir = manifests[0].parent
    if not (update_dir / "firmware.dfu").is_file():
        raise SystemExit(f"Missing firmware.dfu in {update_dir}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        archive.add(update_dir, arcname=update_dir.name)
    print(f"Created {output} from {update_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="FBT dist directory")
    parser.add_argument("--output", type=Path, required=True, help="Output .tgz file")
    args = parser.parse_args()
    package(args.dist, args.output)
