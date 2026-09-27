#include "ble_link.h"
#include "controller_state.h"

#include <bt/bt_service/bt.h>
#include <furi_ble/event_dispatcher.h>
#include <furi_ble/gatt.h>
#include <furi_ble/profile_interface.h>
#include <profiles/serial_profile.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef ACI_GATT_ATTRIBUTE_MODIFIED_VSEVT_CODE
#define ACI_GATT_ATTRIBUTE_MODIFIED_VSEVT_CODE 0x0C01
#endif

// Same UUIDs as the official serial RX service, without its authenticated-write
// requirement. Windows on this adapter never finishes that pairing ceremony.
static const Service_UUID_t service_uuid = {
    .Service_UUID_128 = {0x00, 0x00, 0xfe, 0x60, 0xcc, 0x7a, 0x48, 0x2a, 0x98, 0x4a, 0x7f, 0x2e,
                         0xd5, 0xb3, 0xe5, 0x8f}};

static const BleGattCharacteristicParams rx_params = {
    .name = "RX",
    .data_prop_type = FlipperGattCharacteristicDataFixed,
    .data.fixed.length = CONTROLLER_PACKET_SIZE,
    .uuid.Char_UUID_128 = {0x00, 0x00, 0xfe, 0x62, 0x8e, 0x22, 0x45, 0x41, 0x9d, 0x4c, 0x21,
                            0xed, 0xae, 0x82, 0xed, 0x19},
    .uuid_type = UUID_TYPE_128,
    .char_properties = CHAR_PROP_WRITE | CHAR_PROP_WRITE_WITHOUT_RESP,
    .security_permissions = 0,
    .gatt_evt_mask = GATT_NOTIFY_ATTRIBUTE_WRITE,
    .is_variable = CHAR_VALUE_LEN_VARIABLE,
};

typedef struct __attribute__((packed)) {
    uint8_t type;
    uint8_t data[];
} HciUartPacket;

typedef struct __attribute__((packed)) {
    uint8_t evt;
    uint8_t plen;
    uint8_t data[];
} HciEventPacket;

typedef struct __attribute__((packed)) {
    uint16_t ecode;
    uint8_t data[];
} EvtBleCore;

typedef struct __attribute__((packed)) {
    uint16_t connection_handle;
    uint16_t attr_handle;
    uint16_t offset;
    uint16_t attr_data_length;
    uint8_t attr_data[];
} GattAttributeModified;

typedef struct {
    FuriHalBleProfileBase base;
    uint16_t svc_handle;
    BleGattCharacteristicInstance rx;
    GapSvcEventHandler* events;
    FuriMessageQueue* packets;
} ControllerProfile;

struct BleLink {
    Bt* bt;
    FuriHalBleProfileBase* profile;
    volatile bool connected;
};

static FuriHalBleProfileBase* profile_start(FuriHalBleProfileParams params);
static void profile_stop(FuriHalBleProfileBase* profile);
static void profile_config(GapConfig* config, FuriHalBleProfileParams params);
static BleEventAckStatus on_ble_event(void* event, void* context);

// Distinct profile so Windows does not reuse the standard Flipper serial GATT cache.
// The BT system service only attaches its RPC parser to ble_profile_serial.
static const FuriHalBleProfileTemplate controller_profile = {
    .start = profile_start, .stop = profile_stop, .get_gap_config = profile_config};

static FuriHalBleProfileBase* profile_start(FuriHalBleProfileParams params) {
    UNUSED(params);
    ControllerProfile* profile = malloc(sizeof(ControllerProfile));
    if(!profile) return NULL;
    memset(profile, 0, sizeof(*profile));
    profile->base.config = &controller_profile;
    if(!ble_gatt_service_add(
           UUID_TYPE_128, &service_uuid, PRIMARY_SERVICE, 4, &profile->svc_handle)) {
        free(profile);
        return NULL;
    }
    ble_gatt_characteristic_init(profile->svc_handle, &rx_params, &profile->rx);
    profile->events = ble_event_dispatcher_register_svc_handler(on_ble_event, profile);
    return &profile->base;
}

static void profile_stop(FuriHalBleProfileBase* base) {
    if(!base) return;
    ControllerProfile* profile = (ControllerProfile*)base;
    profile->packets = NULL;
    if(profile->events) ble_event_dispatcher_unregister_svc_handler(profile->events);
    ble_gatt_characteristic_delete(profile->svc_handle, &profile->rx);
    ble_gatt_service_delete(profile->svc_handle);
    free(profile);
}

static void profile_config(GapConfig* config, FuriHalBleProfileParams params) {
    ble_profile_serial->get_gap_config(config, params);
    // The default profile has a different GATT database. Give this app its
    // own BLE identity so Windows does not reuse cached characteristic handles.
    // The official HID profile uses the adjacent address (+1).
    config->mac_address[2] += 2;
    // Authenticated pairing returns Failed on this Windows adapter after the
    // code is confirmed. Writes use an open characteristic, so do not bond.
    config->pairing_method = GapPairingNone;
    config->bonding_mode = false;
    // Byte 0 is AD_TYPE_COMPLETE_LOCAL_NAME. gap.c skips it for the GATT device
    // name and sends the whole buffer as the advertising local name. Replacing
    // that byte removes the name from scans and shifts the visible text.
    char original_name[sizeof(config->adv_name)];
    memcpy(original_name, config->adv_name, sizeof(original_name));
    const char* visible = original_name + 1;
    char* name = config->adv_name + 1;
    size_t name_size = sizeof(config->adv_name) - 1;
    // Visible room is 16 characters: "SwitchLink" plus 6 from the custom suffix.
    if(strncmp(visible, "Flipper", 7) == 0)
        snprintf(name, name_size, "SwitchLink%.6s", visible + 7);
    else
        snprintf(name, name_size, "SwitchLink");
}

static BleEventAckStatus on_ble_event(void* event, void* context) {
    ControllerProfile* profile = context;
    const HciUartPacket* uart = event;
    const HciEventPacket* hci = (const HciEventPacket*)uart->data;
    if(hci->evt != HCI_VENDOR_SPECIFIC_DEBUG_EVT_CODE) return BleEventNotAck;
    const EvtBleCore* core = (const EvtBleCore*)hci->data;
    if(core->ecode != ACI_GATT_ATTRIBUTE_MODIFIED_VSEVT_CODE) return BleEventNotAck;
    const GattAttributeModified* modified = (const GattAttributeModified*)core->data;
    if(modified->attr_handle != profile->rx.handle + 1) return BleEventNotAck;
    if(profile->packets && modified->attr_data_length == CONTROLLER_PACKET_SIZE) {
        uint8_t copy[CONTROLLER_PACKET_SIZE];
        for(size_t i = 0; i < sizeof(copy); ++i) copy[i] = modified->attr_data[i];
        furi_message_queue_put(profile->packets, copy, 0);
    }
    return BleEventAckFlowEnable;
}

static void status_changed(BtStatus status, void* context) {
    BleLink* link = context;
    link->connected = status == BtStatusConnected;
}

BleLink* ble_link_start(FuriMessageQueue* packets) {
    if(!packets) return NULL;
    BleLink* link = malloc(sizeof(BleLink));
    if(!link) return NULL;
    link->connected = false;
    link->bt = furi_record_open(RECORD_BT);
    link->profile = bt_profile_start(link->bt, &controller_profile, NULL);
    if(!link->profile) {
        furi_record_close(RECORD_BT);
        free(link);
        return NULL;
    }
    ((ControllerProfile*)link->profile)->packets = packets;
    bt_set_status_changed_callback(link->bt, status_changed, link);
    return link;
}

bool ble_link_connected(const BleLink* link) { return link && link->connected; }

void ble_link_ack(BleLink* link) { UNUSED(link); }

void ble_link_stop(BleLink* link) {
    if(!link) return;
    bt_set_status_changed_callback(link->bt, NULL, NULL);
    ((ControllerProfile*)link->profile)->packets = NULL;
    bt_disconnect(link->bt);
    bt_profile_restore_default(link->bt);
    furi_record_close(RECORD_BT);
    free(link);
}
