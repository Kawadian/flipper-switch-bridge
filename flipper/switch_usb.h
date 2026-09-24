#pragma once

#include "controller_state.h"

// A self-contained USB HID device. Usable without Bluetooth.
bool switch_usb_start(void);
bool switch_usb_send(const ControllerState* state);
bool switch_usb_connected(void);
void switch_usb_stop(void);
