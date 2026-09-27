"""Focused window that forwards the keyboard to the Switch over BLE."""

import asyncio
import sys
import threading
from collections.abc import Awaitable, Callable

from .ble import ControllerLink
from .keys import HELP_TEXT, KeyboardSession, describe_state, hat_directions
from .protocol import Button, ControllerState

# X11 auto-repeat emits a release just before the next press. Wait that pair out.
# Windows reports the real release, so forward it on the next turn.
RELEASE_DELAY_MS = 40 if sys.platform.startswith("linux") else 0
RESEND_SECONDS = 0.1

Send = Callable[[ControllerState], Awaitable[None]]
GetState = Callable[[], ControllerState]


async def pump_states(get_state: GetState, stop: threading.Event, send: Send, *,
                      interval: float = RESEND_SECONDS, poll: float = 0.02) -> None:
    """Send on every change, and repeat a held state so the Flipper watchdog stays armed."""
    last = None
    last_sent_at = 0.0
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        state = get_state()
        now = loop.time()
        active = state != ControllerState()
        if state != last or (active and now - last_sent_at >= interval):
            await send(state)
            last = state
            last_sent_at = loop.time()
        await asyncio.sleep(poll)


class LinkBridge:
    """Own the BLE connection on a background thread. Key state is read from the GUI."""

    def __init__(self, address: str | None) -> None:
        self.address = address
        self.stop = threading.Event()
        self._lock = threading.Lock()
        self._state = ControllerState()
        self._status = "idle"
        self._message = "未接続"
        self.thread: threading.Thread | None = None

    def get_state(self) -> ControllerState:
        with self._lock:
            return self._state

    def update(self, state: ControllerState) -> None:
        with self._lock:
            self._state = state

    def snapshot(self) -> tuple[str, str]:
        with self._lock:
            return self._status, self._message

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self._thread_main, name="switch-link", daemon=True)
        self.thread.start()

    def shutdown(self) -> None:
        self.stop.set()
        thread = self.thread
        if thread is None:
            return
        with self._lock:
            connected = self._status == "connected"
        thread.join(timeout=2.0 if connected else 0.05)

    def _set_status(self, status: str, message: str) -> None:
        with self._lock:
            self._status = status
            self._message = message

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except Exception as error:
            if self.stop.is_set():
                self._set_status("stopped", "切断しました")
            else:
                self._set_status("error", f"接続失敗: {error}")

    async def _async_main(self) -> None:
        self._set_status("connecting", "SwitchLinkを検索しています…")
        try:
            async with ControllerLink.connect(self.address) as link:
                self._set_status("connected", "接続しました。このウィンドウのキーをSwitchへ送っています")
                await pump_states(self.get_state, self.stop, link.send)
        except Exception as error:
            if self.stop.is_set():
                self._set_status("stopped", "切断しました")
            else:
                self._set_status("error", f"接続失敗: {error}")
            return
        self._set_status("stopped", "切断しました")


class KeyboardApp:
    def __init__(self, root, address: str | None, *, connect: bool = True) -> None:
        import tkinter as tk
        from tkinter import font as tkfont

        self.tk = tk
        self.root = root
        self.session = KeyboardSession()
        self.bridge = LinkBridge(address)
        self._jobs: dict[str, str] = {}
        self._alive = True
        self._closing = False

        family = _font_family(tkfont)
        self.font = (family, 11)
        self.small = (family, 9)
        self.title_font = (family, 14, "bold")
        bg, fg, muted = "#1b1b1f", "#f4f4f5", "#a1a1aa"
        self._bg, self._fg, self._muted = bg, fg, muted
        self._off, self._on, self._stick = "#3f3f46", "#ff4d4f", "#38bdf8"

        root.title("Switch キーボード")
        root.configure(bg=bg)
        root.resizable(False, False)
        outer = tk.Frame(root, bg=bg, padx=16, pady=14)
        outer.pack(fill="both")

        tk.Label(outer, text="Switch キーボード", bg=bg, fg=fg, font=self.title_font,
                 anchor="w").pack(fill="x")
        tk.Label(outer, text="前面にある間だけ、押したキーと離したキーをSwitchへ送ります。",
                 bg=bg, fg=muted, font=self.small, anchor="w", wraplength=460,
                 justify="left").pack(fill="x", pady=(2, 8))

        self.link_var = tk.StringVar(value="未接続")
        self.link_label = tk.Label(outer, textvariable=self.link_var, bg=bg, fg=muted,
                                    font=self.font, anchor="w", wraplength=460, justify="left")
        self.link_label.pack(fill="x")
        self.focus_var = tk.StringVar(value="")
        tk.Label(outer, textvariable=self.focus_var, bg=bg, fg="#fbbf24",
                 font=self.small, anchor="w", wraplength=460, justify="left").pack(
                     fill="x", pady=(0, 8))

        self.canvas = tk.Canvas(outer, width=460, height=168, bg=bg, highlightthickness=0)
        self.canvas.pack()
        self.readout_var = tk.StringVar(value=describe_state(ControllerState()))
        tk.Label(outer, textvariable=self.readout_var, bg=bg, fg=fg, font=self.font,
                 anchor="w", wraplength=460, justify="left").pack(fill="x", pady=(8, 10))
        tk.Label(outer, text=HELP_TEXT, bg=bg, fg=muted, font=(family, 10),
                 justify="left", anchor="w").pack(fill="x")

        actions = tk.Frame(outer, bg=bg)
        actions.pack(fill="x", pady=(12, 0))
        retry = self._button(actions, "再接続", self._retry)
        retry.pack(side="left")
        self._button(actions, "終了", self._on_close).pack(side="right")

        root.bind("<KeyPress>", self._on_press)
        root.bind("<KeyRelease>", self._on_release)
        root.bind("<FocusOut>", lambda _event: root.after(20, self._sync_focus))
        root.bind("<FocusIn>", lambda _event: root.after(20, self._sync_focus))
        root.bind("<Button-1>", lambda _event: root.focus_force(), add="+")
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(50, root.focus_force)
        root.after(200, self._poll_link)
        self._draw(ControllerState())
        if connect:
            self.bridge.start()

    def _button(self, parent, text, command):
        button = self.tk.Button(
            parent, text=text, command=command, takefocus=False,
            bg="#27272a", fg=self._fg, activebackground="#3f3f46", activeforeground=self._fg,
            relief="flat", padx=12, pady=4)
        # A focused button would otherwise treat Space as a click. Handle keys first.
        button.bind("<KeyPress>", self._on_press)
        button.bind("<KeyRelease>", self._on_release)
        button.bind("<Button-1>", lambda _event: self.root.focus_force(), add="+")
        return button

    def _retry(self) -> None:
        self.root.focus_force()
        self.bridge.start()

    def _on_press(self, event):
        # 0x4 is Control and 0x8 is Alt. Leave those chords to the window manager.
        if not self._alive or (event.state & 0x000C):
            return "break"
        key = event.keysym.lower()
        self._cancel_job(key)
        if key == "escape":
            self.session.clear()
            self._publish()
            return "break"
        if self.session.press(event.keysym):
            self._publish()
        return "break"

    def _on_release(self, event):
        if not self._alive:
            return "break"
        key = event.keysym.lower()

        def fire(expected=key, original=event.keysym):
            self._jobs.pop(expected, None)
            if self.session.release(original):
                self._publish()

        self._jobs[key] = self.root.after(RELEASE_DELAY_MS, fire)
        return "break"

    def _sync_focus(self) -> None:
        if not self._alive:
            return
        focused = self._has_focus()
        self.focus_var.set(
            "" if focused else "背面です。ウィンドウをクリックするとキー入力を再開します。")
        if not focused:
            self._cancel_jobs()
            self.session.clear()
            self._publish()

    def _has_focus(self) -> bool:
        owner = self.root.focus_displayof()
        return owner is not None and owner.winfo_toplevel() == self.root

    def _publish(self) -> None:
        state = self.session.state
        self.bridge.update(state)
        self.readout_var.set(describe_state(state))
        self._draw(state)

    def _poll_link(self) -> None:
        if not self._alive:
            return
        status, message = self.bridge.snapshot()
        colors = {"connected": "#4ade80", "error": "#ff5a5a", "connecting": "#e4e4e7"}
        self.link_var.set(message)
        self.link_label.configure(fg=colors.get(status, self._muted))
        self.root.after(200, self._poll_link)

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._alive = False
        self._cancel_jobs()
        self.session.clear()
        self.bridge.update(ControllerState())
        self.link_var.set("切断中…")
        self.root.update_idletasks()
        self.bridge.shutdown()
        self.root.destroy()

    def _cancel_job(self, key: str) -> None:
        job = self._jobs.pop(key, None)
        if job is not None:
            self.root.after_cancel(job)

    def _cancel_jobs(self) -> None:
        for job in self._jobs.values():
            self.root.after_cancel(job)
        self._jobs.clear()

    def _draw(self, state: ControllerState) -> None:
        canvas = self.canvas
        canvas.delete("all")
        directions = hat_directions(state.hat)
        _cross(canvas, 78, 96, directions, self._off, self._on)
        _stick(canvas, 210, 96, state.lx, state.ly, "L", self._off, self._stick, self.small)
        _stick(canvas, 290, 96, state.rx, state.ry, "R", self._off, self._stick, self.small)
        buttons = (
            (400, 58, "Y", Button.Y), (364, 96, "X", Button.X),
            (436, 96, "A", Button.A), (400, 134, "B", Button.B),
        )
        for x, y, label, button in buttons:
            _pad(canvas, x, y, label, bool(state.buttons & button), self._off, self._on, self.small)


def _font_family(tkfont) -> str:
    families = set(tkfont.families())
    for name in ("Segoe UI", "Yu Gothic UI", "Meiryo", "Noto Sans CJK JP"):
        if name in families:
            return name
    return "TkDefaultFont"


def _cross(canvas, cx: int, cy: int, directions: set[str], off: str, on: str) -> None:
    t, g = 22, 4
    arms = {
        "up": (cx - t // 2, cy - g - t * 2, cx + t // 2, cy - g - t),
        "left": (cx - g - t * 2, cy - t // 2, cx - g - t, cy + t // 2),
        "right": (cx + g + t, cy - t // 2, cx + g + t * 2, cy + t // 2),
        "down": (cx - t // 2, cy + g + t, cx + t // 2, cy + g + t * 2),
    }
    for name, box in arms.items():
        canvas.create_rectangle(*box, fill=on if name in directions else off, width=0)
    canvas.create_rectangle(cx - t // 2, cy - t // 2, cx + t // 2, cy + t // 2,
                            fill=on if directions else off, width=0)


def _stick(canvas, cx: int, cy: int, x: int, y: int, label: str,
           off: str, color: str, font) -> None:
    radius = 28
    canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=off, width=2)
    moved = x != 128 or y != 128
    dx = (x - 128) / 128 * (radius - 8)
    dy = (y - 128) / 128 * (radius - 8)
    dot = 6
    canvas.create_oval(cx + dx - dot, cy + dy - dot, cx + dx + dot, cy + dy + dot,
                       fill=color if moved else off, width=0)
    canvas.create_text(cx, cy + radius + 12, text=label, fill="#a1a1aa", font=font)


def _pad(canvas, cx: int, cy: int, label: str, pressed: bool, off: str, on: str, font) -> None:
    radius = 16
    canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                       fill=on if pressed else off, width=0)
    canvas.create_text(cx, cy, text=label, fill="#ffffff", font=font)


def run_keyboard_gui(address: str | None = None) -> None:
    try:
        import tkinter as tk
    except ImportError as error:
        raise SystemExit(
            "tkinter is required for flipper-link play. "
            "On Linux install python3-tk; the Windows Python installer includes it."
        ) from error
    root = tk.Tk()
    app = KeyboardApp(root, address)
    root.mainloop()
    app.bridge.shutdown()
