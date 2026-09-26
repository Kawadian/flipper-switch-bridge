#pragma once

#include "controller_state.h"

// Standalone wired Pro Controller USB implementation; does not depend on BLE.
bool pro_usb_start(void);
bool pro_usb_connected(void);
bool pro_usb_ready(void);
bool pro_usb_send(const ControllerState* state);
void pro_usb_stop(void);
