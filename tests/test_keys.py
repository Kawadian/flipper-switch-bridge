import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))
from flipper_link.keys import (KeyboardSession, canonical_key, describe_state, hat_directions,
                               state_from_keys)
from flipper_link.protocol import Button, ControllerState, Hat, encode


class KeyMapTests(unittest.TestCase):
    def test_arrows_are_the_dpad_including_diagonals(self):
        self.assertEqual(state_from_keys({"up"}).hat, Hat.UP)
        self.assertEqual(state_from_keys({"up", "right"}).hat, Hat.UP_RIGHT)
        self.assertEqual(state_from_keys({"down", "left"}).hat, Hat.DOWN_LEFT)
        self.assertEqual(state_from_keys({"up", "down"}).hat, Hat.CENTER)
        self.assertEqual(state_from_keys({"left", "right"}).hat, Hat.CENTER)
        self.assertEqual(hat_directions(Hat.UP_RIGHT), {"up", "right"})

    def test_sticks_use_zero_for_up_and_cancel_opposites(self):
        state = state_from_keys({"ls_up", "ls_left", "rs_down", "rs_right"})
        self.assertEqual((state.lx, state.ly, state.rx, state.ry), (0, 0, 255, 255))
        neutral = state_from_keys({"ls_up", "ls_down", "rs_left", "rs_right"})
        self.assertEqual((neutral.lx, neutral.ly, neutral.rx, neutral.ry), (128, 128, 128, 128))

    def test_named_buttons_and_packet(self):
        state = state_from_keys({"a", "y", "zl", "home"})
        self.assertEqual(state.buttons, Button.A | Button.Y | Button.ZL | Button.HOME)
        encode(state, 3)
        self.assertIn("A", describe_state(state))
        self.assertIn("上", describe_state(state_from_keys({"up"})))

    def test_session_tracks_physical_keys_and_ignores_repeat(self):
        session = KeyboardSession()
        self.assertTrue(session.press("Up"))
        self.assertFalse(session.press("Up"))
        self.assertEqual(session.state.hat, Hat.UP)
        self.assertTrue(session.press("Right"))
        self.assertEqual(session.state.hat, Hat.UP_RIGHT)
        self.assertTrue(session.release("Up"))
        self.assertEqual(session.state.hat, Hat.RIGHT)
        self.assertTrue(session.press("i"))
        self.assertTrue(session.press("KP_8"))
        self.assertEqual(session.state.ry, 0)
        self.assertTrue(session.release("i"))
        self.assertEqual(session.state.ry, 0)
        self.assertTrue(session.release("KP_8"))
        self.assertEqual(session.state.ry, 128)
        self.assertIsNone(canonical_key("Shift_L"))
        self.assertFalse(session.press("Shift_L"))
        self.assertTrue(session.clear())
        self.assertEqual(session.state, ControllerState())
        self.assertFalse(session.clear())

    def test_documented_keysyms(self):
        expected = {
            "Up": {"hat": Hat.UP},
            "KP_Left": {"hat": Hat.LEFT},
            "w": {"ly": 0}, "s": {"ly": 255}, "a": {"lx": 0}, "d": {"lx": 255},
            "i": {"ry": 0}, "k": {"ry": 255}, "j": {"rx": 0}, "l": {"rx": 255},
            "KP_8": {"ry": 0}, "KP_2": {"ry": 255}, "KP_4": {"rx": 0}, "KP_6": {"rx": 255},
            "space": {"buttons": Button.A},
            "b": {"buttons": Button.B}, "x": {"buttons": Button.X}, "y": {"buttons": Button.Y},
            "q": {"buttons": Button.L}, "r": {"buttons": Button.R},
            "z": {"buttons": Button.ZL}, "1": {"buttons": Button.ZL},
            "c": {"buttons": Button.ZR}, "3": {"buttons": Button.ZR},
            "minus": {"buttons": Button.MINUS},
            "equal": {"buttons": Button.PLUS}, "Return": {"buttons": Button.PLUS},
            "Home": {"buttons": Button.HOME}, "End": {"buttons": Button.CAPTURE},
            "v": {"buttons": Button.L_STICK}, "f": {"buttons": Button.R_STICK},
        }
        for keysym, fields in expected.items():
            session = KeyboardSession()
            self.assertTrue(session.press(keysym), keysym)
            for name, value in fields.items():
                self.assertEqual(getattr(session.state, name), value, keysym)


if __name__ == "__main__":
    unittest.main()
