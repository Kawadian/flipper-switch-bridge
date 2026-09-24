"""Versioned 10-byte controller state protocol shared with Flipper firmware."""

from dataclasses import dataclass
from enum import IntEnum, IntFlag


class Button(IntFlag):
    Y = 0x0001
    B = 0x0002
    A = 0x0004
    X = 0x0008
    L = 0x0010
    R = 0x0020
    ZL = 0x0040
    ZR = 0x0080
    MINUS = 0x0100
    PLUS = 0x0200
    L_STICK = 0x0400
    R_STICK = 0x0800
    HOME = 0x1000
    CAPTURE = 0x2000


class Hat(IntEnum):
    UP = 0
    UP_RIGHT = 1
    RIGHT = 2
    DOWN_RIGHT = 3
    DOWN = 4
    DOWN_LEFT = 5
    LEFT = 6
    UP_LEFT = 7
    CENTER = 8


@dataclass(frozen=True)
class ControllerState:
    buttons: Button = Button(0)
    hat: Hat = Hat.CENTER
    lx: int = 128
    ly: int = 128
    rx: int = 128
    ry: int = 128

    def __post_init__(self) -> None:
        if not 0 <= int(self.buttons) <= 0x3FFF:
            raise ValueError("buttons must fit the 14 supported button bits")
        for axis in ("lx", "ly", "rx", "ry"):
            if not 0 <= getattr(self, axis) <= 255:
                raise ValueError(f"{axis} must be in [0, 255]")
        if int(self.hat) not in range(9):
            raise ValueError("hat must be in [0, 8]")


def encode(state: ControllerState, sequence: int) -> bytes:
    if not 0 <= sequence <= 255:
        raise ValueError("sequence must be in [0, 255]")
    buttons = int(state.buttons)
    body = bytes((1, sequence, buttons & 255, buttons >> 8,
                  int(state.hat), state.lx, state.ly, state.rx, state.ry))
    checksum = 0
    for value in body:
        checksum ^= value
    return body + bytes((checksum,))


def decode(packet: bytes) -> tuple[ControllerState, int]:
    if len(packet) != 10 or packet[0] != 1 or packet[4] > 8:
        raise ValueError("invalid packet header")
    checksum = 0
    for value in packet[:9]:
        checksum ^= value
    if checksum != packet[9]:
        raise ValueError("invalid packet checksum")
    state = ControllerState(
        buttons=Button(packet[2] | packet[3] << 8), hat=Hat(packet[4]),
        lx=packet[5], ly=packet[6], rx=packet[7], ry=packet[8])
    return state, packet[1]
