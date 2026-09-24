#pragma once

#include <furi.h>
#include <stdbool.h>
#include <stdint.h>

// BLE serial transport is independent of the USB gamepad.
// Incoming messages are exactly CONTROLLER_PACKET_SIZE bytes long.
typedef struct BleLink BleLink;
BleLink* ble_link_start(FuriMessageQueue* packets);
void ble_link_stop(BleLink* link);
bool ble_link_connected(const BleLink* link);
void ble_link_ack(BleLink* link);
