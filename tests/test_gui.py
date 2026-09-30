import asyncio
import os
import sys
import threading
import time
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc"))
from flipper_link.gui import (
    RELEASE_DELAY_MS, KeyboardApp, LinkBridge, StateQueue, keymap_bit_is_set, pump_states,
    releases_controls)
from flipper_link.protocol import Button, ControllerState, Hat

try:
    import tkinter as tk
except ImportError:
    tk = None


class _Event:
    def __init__(self, keysym, state=0, keycode=0):
        self.keysym = keysym
        self.state = state
        self.keycode = keycode


class ReleaseTests(unittest.TestCase):
    def test_releasing_a_direction_or_button_is_detected(self):
        pressed = ControllerState(buttons=Button.A, hat=Hat.UP, lx=0, ly=0)
        self.assertTrue(releases_controls(pressed, ControllerState()))
        self.assertTrue(releases_controls(pressed, ControllerState(buttons=Button.A, hat=Hat.UP)))
        self.assertFalse(releases_controls(
            ControllerState(hat=Hat.UP), ControllerState(hat=Hat.UP_RIGHT)))
        self.assertFalse(releases_controls(ControllerState(lx=0), ControllerState(lx=255)))
        self.assertTrue(releases_controls(ControllerState(lx=0), ControllerState(lx=64)))
        self.assertFalse(releases_controls(pressed, pressed))

    def test_keymap_bits_follow_x11_layout(self):
        keymap = bytearray(32)
        keymap[5] = 1 << 3  # keycode 43
        self.assertTrue(keymap_bit_is_set(bytes(keymap), 43))
        self.assertFalse(keymap_bit_is_set(bytes(keymap), 42))
        self.assertFalse(keymap_bit_is_set(bytes(keymap), 256))


class PumpTests(unittest.IsolatedAsyncioTestCase):
    async def test_change_is_sent_once_and_a_hold_repeats(self):
        sent = []
        states = StateQueue()
        stop = threading.Event()

        async def send(state):
            sent.append(state)

        task = asyncio.create_task(
            pump_states(states, stop, send, interval=0.05, min_hold=0, poll=0.005))
        await asyncio.sleep(0.03)
        self.assertEqual(sent, [ControllerState()])
        states.publish(ControllerState(buttons=Button.A))
        await asyncio.sleep(0.03)
        self.assertIn(ControllerState(buttons=Button.A), sent)
        await asyncio.sleep(0.12)
        self.assertGreaterEqual(sent.count(ControllerState(buttons=Button.A)), 2)
        states.publish(ControllerState())
        await asyncio.sleep(0.03)
        self.assertEqual(sent[-1], ControllerState())
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    async def test_a_press_queued_during_a_write_is_still_sent(self):
        sent = []
        states = StateQueue()
        stop = threading.Event()
        started = asyncio.Event()
        release_send = asyncio.Event()

        async def send(state):
            sent.append(state)
            if len(sent) == 1:
                started.set()
                await release_send.wait()

        task = asyncio.create_task(
            pump_states(states, stop, send, interval=1, min_hold=0.05, poll=0.005))
        await asyncio.wait_for(started.wait(), timeout=1)
        states.publish(ControllerState(buttons=Button.B))
        states.publish(ControllerState())
        release_send.set()
        deadline = time.time() + 1
        pressed = ControllerState(buttons=Button.B)
        while time.time() < deadline and not (
                pressed in sent and sent[-1] == ControllerState() and len(sent) >= 3):
            await asyncio.sleep(0.01)
        self.assertEqual(sent[0], ControllerState())
        self.assertLess(sent.index(pressed), len(sent) - 1)
        self.assertEqual(sent[-1], ControllerState())
        stop.set()
        await asyncio.wait_for(task, timeout=1)

    async def test_short_press_stays_down_long_enough_to_sample(self):
        sent = []
        states = StateQueue()
        stop = threading.Event()
        pressed_at = None

        async def send(state):
            nonlocal pressed_at
            sent.append((time.monotonic(), state))
            if state.buttons & Button.A and pressed_at is None:
                pressed_at = time.monotonic()

        task = asyncio.create_task(
            pump_states(states, stop, send, interval=1, min_hold=0.08, poll=0.005))
        await asyncio.sleep(0.02)
        states.publish(ControllerState(buttons=Button.A))
        states.publish(ControllerState())
        deadline = time.time() + 1

        def released_after_press():
            return pressed_at is not None and any(
                stamp > pressed_at and state == ControllerState() for stamp, state in sent)

        while time.time() < deadline and not released_after_press():
            await asyncio.sleep(0.005)
        self.assertIsNotNone(pressed_at)
        released_at = next(stamp for stamp, state in sent if stamp > pressed_at
                           and state == ControllerState())
        self.assertGreaterEqual(released_at - pressed_at, 0.07)
        stop.set()
        await asyncio.wait_for(task, timeout=1)


class BridgeTests(unittest.TestCase):
    def test_forwards_latest_state_and_releases_on_shutdown(self):
        sent = []
        entered = threading.Event()

        class FakeLink:
            async def send(self, state):
                sent.append(state)

        @asynccontextmanager
        async def fake_connect(address=None):
            self.assertIsNone(address)
            entered.set()
            link = FakeLink()
            try:
                yield link
            finally:
                await link.send(ControllerState())

        bridge = LinkBridge(None)
        bridge.update(ControllerState(hat=Hat.LEFT))
        with patch("flipper_link.gui.ControllerLink.connect", fake_connect):
            bridge.start()
            self.assertTrue(entered.wait(1))
            deadline = time.time() + 1
            while time.time() < deadline and Hat.LEFT not in [item.hat for item in sent]:
                time.sleep(0.02)
            self.assertIn(Hat.LEFT, [item.hat for item in sent])
            bridge.shutdown()
            bridge.thread.join(1)
        self.assertEqual(sent[-1], ControllerState())
        self.assertEqual(bridge.snapshot()[0], "stopped")

    def test_connection_failure_is_reported(self):
        def fake_connect(address=None):
            raise RuntimeError("no SwitchLink")

        bridge = LinkBridge("addr")
        with patch("flipper_link.gui.ControllerLink.connect", fake_connect):
            bridge.start()
            bridge.thread.join(1)
        status, message = bridge.snapshot()
        self.assertEqual(status, "error")
        self.assertIn("no SwitchLink", message)


@unittest.skipUnless(tk is not None and os.environ.get("DISPLAY"), "tkinter display required")
class WindowTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.app = KeyboardApp(self.root, None, connect=False)
        self.root.update()

    def tearDown(self):
        if self.app._alive:
            self.app._on_close()

    def test_arrow_and_release_update_the_readout(self):
        self.app._on_press(_Event("Up"))
        self.root.update()
        self.assertEqual(self.app.session.state.hat, Hat.UP)
        self.assertIn("上", self.app.readout_var.get())
        self.app._on_press(_Event("space"))
        self.assertTrue(self.app.session.state.buttons & Button.A)
        self.app._on_release(_Event("Up"))
        self.assertEqual(self.app.session.state.hat, Hat.UP)
        self.root.update()
        time.sleep(RELEASE_DELAY_MS / 1000 + 0.05)
        self.root.update()
        self.assertEqual(self.app.session.state.hat, Hat.CENTER)
        self.assertTrue(self.app.session.state.buttons & Button.A)

    def test_key_repeat_does_not_drop_the_dpad(self):
        self.app._on_press(_Event("Left"))
        self.app._on_release(_Event("Left"))
        self.app._on_press(_Event("Left"))
        time.sleep(RELEASE_DELAY_MS / 1000 + 0.05)
        self.root.update()
        self.assertEqual(self.app.session.state.hat, Hat.LEFT)

    def test_losing_focus_clears_held_keys(self):
        self.app._on_press(_Event("Right"))
        self.app._on_press(_Event("b"))
        self.app._has_focus = lambda: False
        self.app._sync_focus()
        self.assertEqual(self.app.session.state, ControllerState())
        self.assertIn("背面", self.app.focus_var.get())
        self.assertEqual(self.app.bridge.get_state(), ControllerState())

    def test_real_key_event_reaches_the_binding(self):
        self.root.focus_force()
        self.root.update()
        self.root.event_generate("<KeyPress>", keysym="Down")
        self.root.update()
        self.assertEqual(self.app.session.state.hat, Hat.DOWN)
        self.root.event_generate("<KeyRelease>", keysym="Down")
        time.sleep(RELEASE_DELAY_MS / 1000 + 0.05)
        self.root.update()
        self.assertEqual(self.app.session.state.hat, Hat.CENTER)

    def test_ctrl_chord_is_not_forwarded(self):
        self.app._on_press(_Event("b", state=0x4))
        self.app._on_press(_Event("Up", state=0x8))
        self.assertEqual(self.app.session.state, ControllerState())

    def test_escape_releases_everything(self):
        self.app._on_press(_Event("d"))
        self.app._on_press(_Event("y"))
        self.app._on_press(_Event("Escape"))
        self.assertEqual(self.app.session.state, ControllerState())

    def test_autorepeat_release_keeps_the_button_while_the_key_is_down(self):
        checks = {"count": 0}

        def still_down(keycode):
            self.assertEqual(keycode, 65)
            checks["count"] += 1
            return checks["count"] == 1

        self.app._on_press(_Event("space", keycode=65))
        with patch("flipper_link.gui.key_is_physically_down", still_down):
            self.app._on_release(_Event("space", keycode=65))
            time.sleep(RELEASE_DELAY_MS / 1000 + 0.05)
            self.root.update()
            self.assertTrue(self.app.session.state.buttons & Button.A)
            time.sleep(RELEASE_DELAY_MS / 1000 + 0.05)
            self.root.update()
        self.assertGreaterEqual(checks["count"], 2)
        self.assertFalse(self.app.session.state.buttons & Button.A)


if __name__ == "__main__":
    unittest.main()
