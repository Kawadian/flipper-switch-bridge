import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))
from flipper_link.protocol import Button, ControllerState, Hat, decode, encode


class ProtocolTests(unittest.TestCase):
    def test_neutral_bytes(self):
        self.assertEqual(encode(ControllerState(), 0),
                         bytes((1, 0, 0, 0, 8, 128, 128, 128, 128, 9)))

    def test_roundtrip_and_checksum(self):
        state = ControllerState(Button.A | Button.ZR, Hat.LEFT, 0, 255, 22, 88)
        packet = encode(state, 255)
        self.assertEqual(decode(packet), (state, 255))
        corrupt = bytearray(packet)
        corrupt[2] ^= 1
        with self.assertRaises(ValueError):
            decode(corrupt)

    def test_reject_invalid_axis(self):
        with self.assertRaises(ValueError):
            ControllerState(lx=256)


if __name__ == "__main__":
    unittest.main()
