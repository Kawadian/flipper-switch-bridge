// Pro Controller USB replies adapted from Karakuri firmware (MIT).
// Copyright (c) 2026 Eggletric. See upstream for the MIT license.
#include "pro_protocol.h"
#include "pro_data.h"

#include <string.h>

static void spi_read(uint8_t* destination, uint32_t address, uint8_t size) {
    for(uint8_t i = 0; i < size; i++) {
        uint32_t at = address + i;
        if(at >= 0x6000 && at - 0x6000 < 0xEFF)
            destination[i] = at - 0x6000 < sizeof(pro_factory_data) ?
                                 pro_factory_data[at - 0x6000] : 0;
        else if(at >= 0x8000 && at - 0x8000 < 0x3F)
            destination[i] = at - 0x8000 < sizeof(pro_user_data) ?
                                 pro_user_data[at - 0x8000] : 0;
        else
            destination[i] = 0xFF;
    }
}

void pro_protocol_receive(
    const uint8_t* packet,
    size_t size,
    const uint8_t input[PRO_PROTOCOL_PACKET_SIZE],
    uint8_t counter,
    const uint8_t device_info[12],
    ProProtocolResult* result) {
    memset(result, 0, sizeof(*result));
    if(!packet || size < 2) return;
    result->report_id = packet[0];
    if(packet[0] == 0x80) {
        result->command = packet[1];
        switch(packet[1]) {
        case 0x01:
            result->reply[0] = 0x81;
            result->reply[1] = 0x01;
            result->reply[3] = 0x03;
            for(size_t i = 0; i < 6; i++) result->reply[4 + i] = device_info[9 - i];
            result->has_reply = true;
            break;
        case 0x02:
        case 0x03:
            result->reply[0] = 0x81;
            result->reply[1] = packet[1];
            result->has_reply = true;
            break;
        case 0x04: // Enter USB input mode; the host does not expect an ACK.
        case 0x05:
            result->changes_streaming = true;
            result->streaming = packet[1] == 0x04;
            break;
        default:
            break;
        }
        return;
    }
    if(packet[0] != 0x01 || size < 12) return;

    uint8_t command = packet[10];
    result->command = command;
    result->reply[0] = 0x21;
    result->reply[1] = counter;
    memcpy(&result->reply[2], &input[2], 11);
    result->reply[13] = 0x80;
    result->reply[14] = command;
    result->has_reply = true;

    switch(command) {
    case 0x01: { // Bluetooth manual pairing also occurs on the wired connection.
        result->reply[13] = 0x81;
        uint8_t step = packet[11];
        result->pairing_step = step;
        result->reply[15] = step;
        if(step == 0x01) {
            // Reply with this controller's MAC in little-endian order.
            for(size_t i = 0; i < 6; i++) result->reply[16 + i] = device_info[9 - i];
        } else if(step == 0x02) {
            // Stable, obfuscated 16-byte pairing key. No radio pairing is performed.
            memset(&result->reply[16], 0xAA, 16);
        }
        break;
    }
    case 0x02:
        result->reply[13] = 0x82;
        memcpy(&result->reply[15], device_info, 12);
        break;
    case 0x03:
        result->reply[15] = packet[11];
        if(packet[11] == 0x30) {
            result->changes_streaming = true;
            result->streaming = true;
        }
        break;
    case 0x04:
        result->reply[13] = 0x83;
        break;
    case 0x10:
        if(size >= 16) {
            uint32_t address = (uint32_t)packet[11] | ((uint32_t)packet[12] << 8) |
                               ((uint32_t)packet[13] << 16) | ((uint32_t)packet[14] << 24);
            uint8_t length = packet[15];
            result->reply[13] = 0x90;
            memcpy(&result->reply[15], &packet[11], 5);
            if(length > 29) length = 29;
            spi_read(&result->reply[20], address, length);
        }
        break;
    case 0x21:
        result->reply[13] = 0xA0;
        result->reply[15] = 0x01;
        result->reply[17] = 0xFF;
        result->reply[19] = 0x08;
        result->reply[21] = 0x1B;
        result->reply[22] = 0x01;
        break;
    case 0x31:
        result->reply[13] = 0xB0;
        result->reply[15] = packet[11];
        break;
    default:
        break;
    }
}
