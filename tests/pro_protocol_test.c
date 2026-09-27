#include "../flipper/pro_protocol.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    const uint8_t device_info[12] = {
        0x04, 0x91, 0x03, 0x02, 0x7C, 0xBB, 0x8A, 0x12, 0x34, 0x56, 0x01, 0x02};
    const uint8_t input[64] = {0x30, 0, 0x80};
    uint8_t out[64] = {0};
    ProProtocolResult result;

    out[0] = 0x80;
    out[1] = 0x01;
    pro_protocol_receive(out, sizeof(out), input, 0, device_info, &result);
    assert(result.has_reply && result.reply[0] == 0x81 && result.reply[3] == 0x03);
    assert(result.reply[4] == 0x56 && result.reply[9] == 0x7C);

    out[1] = 0x04;
    pro_protocol_receive(out, sizeof(out), input, 0, device_info, &result);
    assert(!result.has_reply && result.changes_streaming && result.streaming);

    out[0] = 0x01;
    out[10] = 0x01;
    for(uint8_t step = 1; step <= 3; step++) {
        out[11] = step;
        pro_protocol_receive(out, sizeof(out), input, 4, device_info, &result);
        assert(result.has_reply && result.reply[0] == 0x21);
        assert(result.reply[13] == 0x81 && result.reply[14] == 0x01);
        assert(result.reply[15] == step);
        if(step == 1) {
            assert(result.reply[16] == 0x56 && result.reply[21] == 0x7C);
        } else if(step == 2) {
            for(int i = 16; i < 32; i++) assert(result.reply[i] == 0xAA);
        }
    }
    out[10] = 0x03;
    out[11] = 0x30;
    pro_protocol_receive(out, sizeof(out), input, 0, device_info, &result);
    assert(result.has_reply && result.changes_streaming && result.streaming);

    out[10] = 0x10;
    out[11] = 0x3D;
    out[12] = 0x60;
    out[13] = out[14] = 0;
    out[15] = 9;
    pro_protocol_receive(out, sizeof(out), input, 0, device_info, &result);
    assert(result.reply[13] == 0x90 && result.reply[14] == 0x10);
    assert(result.reply[15] == 0x3D && result.reply[16] == 0x60);
    puts("Pro USB handshake, pairing and calibration replies: OK");
}
