#pragma once

#include "controller_state.h"

// Standalone wired Pro Controller USB implementation; does not depend on BLE.
bool pro_usb_start(void);
bool pro_usb_connected(void);
bool pro_usb_ready(void);
uint8_t pro_usb_last_report_id(void);
uint8_t pro_usb_last_command(void);
uint8_t pro_usb_last_pairing_step(void);
bool pro_usb_send(const ControllerState* state);
void pro_usb_stop(void);
