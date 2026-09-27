#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PRO_PROTOCOL_PACKET_SIZE 64

typedef struct {
    uint8_t reply[PRO_PROTOCOL_PACKET_SIZE];
    bool has_reply;
    bool changes_streaming;
    bool streaming;
    uint8_t report_id;
    uint8_t command;
    uint8_t pairing_step;
} ProProtocolResult;

// Process a single 64-byte USB OUT report. This has no Flipper or BLE dependencies.
void pro_protocol_receive(
    const uint8_t* packet,
    size_t size,
    const uint8_t input[PRO_PROTOCOL_PACKET_SIZE],
    uint8_t counter,
    const uint8_t device_info[12],
    ProProtocolResult* result);
