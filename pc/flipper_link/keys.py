"""Keyboard controls for the focused play window.

Arrow keys are the D-pad. Terminal input usually cannot see those keys, or the
moment they are released, so the window collects press and release itself.
Stick Y uses 0 for up: Pro USB inverts that byte, and the legacy report treats
0 as up as well.
"""

from .protocol import Button, ControllerState, Hat

# Canonical token for each Tk keysym. Letters are stored lowercased.
_KEY_TOKENS = {
    "up": "up", "down": "down", "left": "left", "right": "right",
    "kp_up": "up", "kp_down": "down", "kp_left": "left", "kp_right": "right",
    "w": "ls_up", "s": "ls_down", "a": "ls_left", "d": "ls_right",
    "i": "rs_up", "k": "rs_down", "j": "rs_left", "l": "rs_right",
    "kp_8": "rs_up", "kp_2": "rs_down", "kp_4": "rs_left", "kp_6": "rs_right",
    "space": "a",
    "b": "b", "x": "x", "y": "y",
    "q": "l", "r": "r",
    "z": "zl", "1": "zl",
    "c": "zr", "3": "zr",
    "minus": "minus", "kp_subtract": "minus",
    "equal": "plus", "plus": "plus", "return": "plus", "kp_enter": "plus", "kp_add": "plus",
    "home": "home",
    "end": "capture",
    "v": "l3", "f": "r3",
}

_TOKEN_BUTTONS = {
    "a": Button.A, "b": Button.B, "x": Button.X, "y": Button.Y,
    "l": Button.L, "r": Button.R, "zl": Button.ZL, "zr": Button.ZR,
    "minus": Button.MINUS, "plus": Button.PLUS,
    "l3": Button.L_STICK, "r3": Button.R_STICK,
    "home": Button.HOME, "capture": Button.CAPTURE,
}

HELP_TEXT = """\
十字キー      矢印キー（同時押しで斜め）
左スティック  W A S D（Wが上）
右スティック  I J K L（Iが上、Kが下、Jが左、Lが右）
              テンキーの 8 2 4 6 も右スティック
A             Space（Aキーは左スティックです）
B / X / Y     B / X / Y
L / R         Q / R
ZL / ZR       Z / C
− / +         - / = または Enter
Home          Home
Capture       End
スティック押し V が左、F が右
Escape        押したままの入力を離す
"""

_HAT_NAMES = {
    Hat.CENTER: "中央", Hat.UP: "上", Hat.UP_RIGHT: "右上", Hat.RIGHT: "右",
    Hat.DOWN_RIGHT: "右下", Hat.DOWN: "下", Hat.DOWN_LEFT: "左下", Hat.LEFT: "左",
    Hat.UP_LEFT: "左上",
}

_BUTTON_LABELS = (
    (Button.A, "A"), (Button.B, "B"), (Button.X, "X"), (Button.Y, "Y"),
    (Button.L, "L"), (Button.R, "R"), (Button.ZL, "ZL"), (Button.ZR, "ZR"),
    (Button.MINUS, "−"), (Button.PLUS, "+"), (Button.L_STICK, "L3"), (Button.R_STICK, "R3"),
    (Button.HOME, "Home"), (Button.CAPTURE, "Cap"),
)


def canonical_key(keysym: str) -> str | None:
    return _KEY_TOKENS.get(keysym.lower())


def hat_directions(hat: Hat) -> set[str]:
    return set({
        Hat.UP: {"up"}, Hat.UP_RIGHT: {"up", "right"}, Hat.RIGHT: {"right"},
        Hat.DOWN_RIGHT: {"down", "right"}, Hat.DOWN: {"down"},
        Hat.DOWN_LEFT: {"down", "left"}, Hat.LEFT: {"left"}, Hat.UP_LEFT: {"up", "left"},
        Hat.CENTER: set(),
    }[Hat(hat)])


def _axis(negative: bool, positive: bool) -> int:
    if negative and not positive:
        return 0
    if positive and not negative:
        return 255
    return 128


def _hat(tokens: set[str]) -> Hat:
    up = "up" in tokens and "down" not in tokens
    down = "down" in tokens and "up" not in tokens
    left = "left" in tokens and "right" not in tokens
    right = "right" in tokens and "left" not in tokens
    if up and right:
        return Hat.UP_RIGHT
    if up and left:
        return Hat.UP_LEFT
    if down and right:
        return Hat.DOWN_RIGHT
    if down and left:
        return Hat.DOWN_LEFT
    if up:
        return Hat.UP
    if down:
        return Hat.DOWN
    if left:
        return Hat.LEFT
    if right:
        return Hat.RIGHT
    return Hat.CENTER


def state_from_keys(tokens: set[str]) -> ControllerState:
    buttons = Button(0)
    for token, button in _TOKEN_BUTTONS.items():
        if token in tokens:
            buttons |= button
    return ControllerState(
        buttons=buttons, hat=_hat(tokens),
        lx=_axis("ls_left" in tokens, "ls_right" in tokens),
        ly=_axis("ls_up" in tokens, "ls_down" in tokens),
        rx=_axis("rs_left" in tokens, "rs_right" in tokens),
        ry=_axis("rs_up" in tokens, "rs_down" in tokens))


def describe_state(state: ControllerState) -> str:
    names = [label for button, label in _BUTTON_LABELS if state.buttons & button]
    buttons = " ".join(names) if names else "なし"
    return (f"十字: {_HAT_NAMES[Hat(state.hat)]}    ボタン: {buttons}\n"
            f"左: {state.lx},{state.ly}    右: {state.rx},{state.ry}")


class KeyboardSession:
    """Pressed keysyms, ignoring auto-repeat, turned into one controller state."""

    def __init__(self) -> None:
        self.keysyms: set[str] = set()
        self.state = ControllerState()

    def press(self, keysym: str) -> bool:
        if canonical_key(keysym) is None:
            return False
        normalized = keysym.lower()
        if normalized in self.keysyms:
            return False
        self.keysyms.add(normalized)
        self._rebuild()
        return True

    def release(self, keysym: str) -> bool:
        normalized = keysym.lower()
        if normalized not in self.keysyms:
            return False
        self.keysyms.discard(normalized)
        self._rebuild()
        return True

    def clear(self) -> bool:
        if not self.keysyms:
            return False
        self.keysyms.clear()
        self.state = ControllerState()
        return True

    def _rebuild(self) -> None:
        tokens = {token for keysym in self.keysyms if (token := canonical_key(keysym))}
        self.state = state_from_keys(tokens)
