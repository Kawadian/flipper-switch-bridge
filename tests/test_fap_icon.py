import struct
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "flipper" / "fap" / "icon.png"


def _png_chunks(data: bytes):
    signature = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(signature):
        raise AssertionError("not a png")
    offset = len(signature)
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        chunk = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        yield kind, chunk


class IconTests(unittest.TestCase):
    def test_icon_is_10x10_monochrome_and_not_blank(self):
        chunks = dict(_png_chunks(ICON.read_bytes()))
        width, height, depth, color, compression, filt, interlace = struct.unpack(
            ">IIBBBBB", chunks[b"IHDR"])
        self.assertEqual((width, height, depth, color, compression, filt, interlace),
                         (10, 10, 1, 0, 0, 0, 0))
        raw = zlib.decompress(chunks[b"IDAT"])
        self.assertEqual(len(raw), 30)

        def bits(index):
            self.assertEqual(raw[index * 3], 0)
            value = (raw[index * 3 + 1] << 8) | raw[index * 3 + 2]
            return [(value >> (15 - bit)) & 1 for bit in range(10)]

        # 1 is white and 0 is black. Top edge, then the left D-pad bar.
        self.assertEqual(bits(0), [1, 0, 0, 0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(bits(3), [0, 1, 0, 0, 0, 1, 1, 1, 1, 0])
        self.assertIn('fap_icon="icon.png"',
                      (ROOT / "flipper" / "fap" / "application.fam").read_text())

    def test_install_copies_the_icon_next_to_the_manifest(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            firmware = Path(directory)
            (firmware / "applications_user").mkdir()
            (firmware / "fbt").write_text("")
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "install_fap.py"), str(firmware)],
                check=True)
            destination = firmware / "applications_user" / "switch_controller"
            self.assertEqual((destination / "icon.png").read_bytes(), ICON.read_bytes())
            manifest = (destination / "application.fam").read_text()
            self.assertIn('fap_icon="icon.png"', manifest)
            self.assertTrue((destination / "app.c").is_file())


if __name__ == "__main__":
    unittest.main()
