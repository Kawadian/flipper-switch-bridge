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
from flipper_link.gui import RELEASE_DELAY_MS, KeyboardApp, LinkBridge, pump_states
from flipper_link.protocol import Button, ControllerState, Hat

try:
    import tkinter as tk
except ImportError:
    tk = None


class _Event:
    def __init__(self, keysym, state=0):
        self.keysym = keysym
        self.state = state


class PumpTests(unittest.IsolatedAsyncioTestCase):
    async def test_change_is_sent_once_and_a_hold_repeats(self):
        sent = []
        holder = {"state": ControllerState()}
        stop = threading.Event()

        async def send(state):
            sent.append(state)

        task = asyncio.create_task(
            pump_states(lambda: holder["state"], stop, send, interval=0.05, poll=0.005))
        await asyncio.sleep(0.03)
        self.assertEqual(sent, [ControllerState()])
        holder["state"] = ControllerState(buttons=Button.A)
        await asyncio.sleep(0.03)
        self.assertIn(ControllerState(buttons=Button.A), sent)
        await asyncio.sleep(0.12)
        self.assertGreaterEqual(sent.count(ControllerState(buttons=Button.A)), 2)
        holder["state"] = ControllerState()
        await asyncio.sleep(0.03)
        self.assertEqual(sent[-1], ControllerState())
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


if __name__ == "__main__":
    unittest.main()
