#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

// Shared wire format: version, sequence, buttons LE, hat, LX, LY, RX, RY, XOR.
#define CONTROLLER_PACKET_SIZE 10
#define CONTROLLER_PACKET_VERSION 1

enum {
    ControllerButtonY = 0x0001,
    ControllerButtonB = 0x0002,
    ControllerButtonA = 0x0004,
    ControllerButtonX = 0x0008,
    ControllerButtonL = 0x0010,
    ControllerButtonR = 0x0020,
    ControllerButtonZL = 0x0040,
    ControllerButtonZR = 0x0080,
    ControllerButtonMinus = 0x0100,
    ControllerButtonPlus = 0x0200,
    ControllerButtonLStick = 0x0400,
    ControllerButtonRStick = 0x0800,
    ControllerButtonHome = 0x1000,
    ControllerButtonCapture = 0x2000,
};

typedef struct {
    uint16_t buttons;
    uint8_t hat; // 0..7 clockwise from up; 8 = centered
    uint8_t lx, ly, rx, ry; // 128 = centered
} ControllerState;

static inline ControllerState controller_state_neutral(void) {
    return (ControllerState){.buttons = 0, .hat = 8, .lx = 128, .ly = 128, .rx = 128, .ry = 128};
}

static inline bool controller_packet_decode(
    const uint8_t* packet, size_t length, ControllerState* state, uint8_t* sequence) {
    if(!packet || !state || !sequence || length != CONTROLLER_PACKET_SIZE ||
       packet[0] != CONTROLLER_PACKET_VERSION || packet[4] > 8) return false;
    uint8_t check = 0;
    for(size_t i = 0; i < CONTROLLER_PACKET_SIZE - 1; ++i) check ^= packet[i];
    if(check != packet[CONTROLLER_PACKET_SIZE - 1]) return false;
    *sequence = packet[1];
    *state = (ControllerState){
        .buttons = (uint16_t)packet[2] | ((uint16_t)packet[3] << 8),
        .hat = packet[4], .lx = packet[5], .ly = packet[6], .rx = packet[7], .ry = packet[8]};
    return true;
}
