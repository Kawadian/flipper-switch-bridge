#include "ble_link.h"
#include "controller_state.h"

#include <bt/bt_service/bt.h>
#include <furi_ble/profile_interface.h>
#include <profiles/serial_profile.h>
#include <services/serial_service.h>
#include <stdlib.h>

typedef struct {
    FuriHalBleProfileBase base;
    BleServiceSerial* service;
} ControllerProfile;

struct BleLink {
    Bt* bt;
    FuriHalBleProfileBase* profile;
    FuriMessageQueue* packets;
    volatile bool connected;
};

static FuriHalBleProfileBase* profile_start(FuriHalBleProfileParams params);
static void profile_stop(FuriHalBleProfileBase* profile);
static void profile_config(GapConfig* config, FuriHalBleProfileParams params);

// Reuse the official GATT serial service but register a distinct profile.
// The BT system service only attaches its RPC parser to ble_profile_serial.
static const FuriHalBleProfileTemplate controller_profile = {
    .start = profile_start, .stop = profile_stop, .get_gap_config = profile_config};

static FuriHalBleProfileBase* profile_start(FuriHalBleProfileParams params) {
    UNUSED(params);
    ControllerProfile* profile = malloc(sizeof(ControllerProfile));
    if(!profile) return NULL;
    profile->base.config = &controller_profile;
    profile->service = ble_svc_serial_start();
    if(!profile->service) {
        free(profile);
        return NULL;
    }
    return &profile->base;
}

static void profile_stop(FuriHalBleProfileBase* base) {
    if(!base) return;
    ControllerProfile* profile = (ControllerProfile*)base;
    ble_svc_serial_stop(profile->service);
    free(profile);
}

static void profile_config(GapConfig* config, FuriHalBleProfileParams params) {
    ble_profile_serial->get_gap_config(config, params);
}

static uint16_t receive(SerialServiceEvent event, void* context) {
    BleLink* link = context;
    if(event.event == SerialServiceEventTypeDataReceived &&
       event.data.size == CONTROLLER_PACKET_SIZE && link->packets) {
        uint8_t copy[CONTROLLER_PACKET_SIZE];
        for(size_t i = 0; i < sizeof(copy); ++i) copy[i] = event.data.buffer[i];
        // The callback runs on the BLE thread; the USB send runs on the app thread.
        furi_message_queue_put(link->packets, copy, 0);
    }
    // One packet is consumed immediately or discarded; we do not retain BLE buffers.
    return CONTROLLER_PACKET_SIZE * 8;
}

static void status_changed(BtStatus status, void* context) {
    BleLink* link = context;
    link->connected = status == BtStatusConnected;
}

BleLink* ble_link_start(FuriMessageQueue* packets) {
    if(!packets) return NULL;
    BleLink* link = malloc(sizeof(BleLink));
    if(!link) return NULL;
    link->packets = packets;
    link->connected = false;
    link->bt = furi_record_open(RECORD_BT);
    link->profile = bt_profile_start(link->bt, &controller_profile, NULL);
    if(!link->profile) {
        furi_record_close(RECORD_BT);
        free(link);
        return NULL;
    }
    ble_svc_serial_set_callbacks(
        ((ControllerProfile*)link->profile)->service,
        CONTROLLER_PACKET_SIZE * 8, receive, link);
    bt_set_status_changed_callback(link->bt, status_changed, link);
    return link;
}

bool ble_link_connected(const BleLink* link) { return link && link->connected; }

void ble_link_ack(BleLink* link) {
    if(link) ble_svc_serial_notify_buffer_is_empty(((ControllerProfile*)link->profile)->service);
}

void ble_link_stop(BleLink* link) {
    if(!link) return;
    bt_set_status_changed_callback(link->bt, NULL, NULL);
    // Stop receiving before releasing app memory and leave the normal BT profile active.
    ble_svc_serial_set_callbacks(((ControllerProfile*)link->profile)->service, 0, NULL, NULL);
    bt_disconnect(link->bt);
    bt_profile_restore_default(link->bt);
    furi_record_close(RECORD_BT);
    free(link);
}
