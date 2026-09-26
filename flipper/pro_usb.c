#include "pro_usb.h"
#include "pro_data.h"

#include <furi.h>
#include <furi_hal_usb.h>
#include <usb.h>
#include <usb_hid.h>
#include <string.h>

// USB wired Pro Controller protocol, based on GP2040-CE's MIT licensed driver.
// The firmware initializes EP0 at 8 bytes. Set its USB stack state to 64
// before attaching this interface, and restore 8 when detaching it.
#define PRO_IN 0x81
#define PRO_OUT 0x01
#define PRO_PACKET 64
#define PRO_EP0_SIZE 64
#define FLIPPER_EP0_SIZE 8
#define PRO_REPLY_SLOTS 8

typedef struct {
    struct usb_interface_descriptor interface;
    struct usb_hid_descriptor hid;
    struct usb_endpoint_descriptor in;
    struct usb_endpoint_descriptor out;
} ProHid;
typedef struct {
    struct usb_config_descriptor config;
    ProHid joystick;
} ProConfiguration;

static struct usb_device_descriptor device_descriptor = {
    .bLength = sizeof(struct usb_device_descriptor), .bDescriptorType = USB_DTYPE_DEVICE,
    .bcdUSB = VERSION_BCD(2, 0, 0), .bDeviceClass = 0,
    .bMaxPacketSize0 = PRO_EP0_SIZE, .idVendor = 0x057E, .idProduct = 0x2009,
    .bcdDevice = VERSION_BCD(2, 1, 0), .iManufacturer = 1,
    .iProduct = 2, .bNumConfigurations = 1,
};
static const ProConfiguration configuration = {
    .config = {
        .bLength = sizeof(struct usb_config_descriptor), .bDescriptorType = USB_DTYPE_CONFIGURATION,
        .wTotalLength = sizeof(ProConfiguration), .bNumInterfaces = 1,
        .bConfigurationValue = 1, .bmAttributes = USB_CFG_ATTR_RESERVED | 0x20,
        .bMaxPower = USB_CFG_POWER_MA(500),
    },
    .joystick = {
        .interface = {
            .bLength = sizeof(struct usb_interface_descriptor), .bDescriptorType = USB_DTYPE_INTERFACE,
            .bInterfaceNumber = 0, .bNumEndpoints = 2, .bInterfaceClass = USB_CLASS_HID,
        },
        .hid = {
            .bLength = sizeof(struct usb_hid_descriptor), .bDescriptorType = USB_DTYPE_HID,
            .bcdHID = VERSION_BCD(1, 1, 1), .bNumDescriptors = 1,
            .bDescriptorType0 = USB_DTYPE_HID_REPORT,
            .wDescriptorLength0 = sizeof(pro_report_descriptor),
        },
        .in = {
            .bLength = sizeof(struct usb_endpoint_descriptor), .bDescriptorType = USB_DTYPE_ENDPOINT,
            .bEndpointAddress = PRO_IN, .bmAttributes = USB_EPTYPE_INTERRUPT,
            .wMaxPacketSize = PRO_PACKET, .bInterval = 8,
        },
        .out = {
            .bLength = sizeof(struct usb_endpoint_descriptor), .bDescriptorType = USB_DTYPE_ENDPOINT,
            .bEndpointAddress = PRO_OUT, .bmAttributes = USB_EPTYPE_INTERRUPT,
            .wMaxPacketSize = PRO_PACKET, .bInterval = 8,
        },
    },
};
static const struct usb_string_descriptor manufacturer = USB_STRING_DESC("Nintendo Co., Ltd.");
static const struct usb_string_descriptor product = USB_STRING_DESC("Pro Controller");
static usbd_device* usb_device;
static FuriSemaphore* write_ready;
static volatile bool connected;
static volatile bool ready;
// USB callbacks produce complete replies; the app thread consumes them in order.
// The byte indices are atomic on the Flipper MCU. A slot is published last.
static uint8_t replies[PRO_REPLY_SLOTS][PRO_PACKET];
static volatile uint8_t reply_read;
static volatile uint8_t reply_write;
static uint8_t input[PRO_PACKET];
static uint8_t device_info[12] = {
    0x04, 0x91, 0x03, 0x02, 0x7C, 0xBB, 0x8A, 0x12, 0x34, 0x56, 0x01, 0x02};
static uint8_t counter;

static bool queue_reply(const uint8_t* report) {
    uint8_t next = (reply_write + 1) % PRO_REPLY_SLOTS;
    if(next == reply_read) return false;
    memcpy(replies[reply_write], report, PRO_PACKET);
    reply_write = next;
    return true;
}

static void identify(void) {
    uint8_t report[PRO_PACKET] = {0};
    report[0] = 0x81;
    report[1] = 0x01;
    report[3] = 0x03;
    // The USB identification response uses the MAC in reverse order.
    for(size_t i = 0; i < 6; i++) report[4 + i] = device_info[9 - i];
    queue_reply(report);
}

static void pack_stick(uint8_t* bytes, uint8_t x, uint8_t y) {
    uint16_t sx = ((uint32_t)x * 4095) / 255;
    uint16_t sy = ((uint32_t)(255 - y) * 4095) / 255;
    bytes[0] = sx & 0xFF;
    bytes[1] = ((sx >> 8) & 0x0F) | ((sy & 0x0F) << 4);
    bytes[2] = sy >> 4;
}

static void set_input(const ControllerState* state) {
    uint16_t b = state->buttons;
    memset(input, 0, sizeof(input));
    input[0] = 0x30;
    input[2] = 0x80; // Battery full, USB attached.
    input[3] = ((b & ControllerButtonY) ? 0x01 : 0) |
               ((b & ControllerButtonX) ? 0x02 : 0) |
               ((b & ControllerButtonB) ? 0x04 : 0) |
               ((b & ControllerButtonA) ? 0x08 : 0) |
               ((b & ControllerButtonR) ? 0x40 : 0) |
               ((b & ControllerButtonZR) ? 0x80 : 0);
    input[4] = ((b & ControllerButtonMinus) ? 0x01 : 0) |
               ((b & ControllerButtonPlus) ? 0x02 : 0) |
               ((b & ControllerButtonRStick) ? 0x04 : 0) |
               ((b & ControllerButtonLStick) ? 0x08 : 0) |
               ((b & ControllerButtonHome) ? 0x10 : 0) |
               ((b & ControllerButtonCapture) ? 0x20 : 0) | 0x80;
    uint8_t hat = state->hat;
    input[5] = ((hat >= 3 && hat <= 5) ? 0x01 : 0) |
               ((hat == 7 || hat == 0 || hat == 1) ? 0x02 : 0) |
               ((hat >= 1 && hat <= 3) ? 0x04 : 0) |
               ((hat >= 5 && hat <= 7) ? 0x08 : 0) |
               ((b & ControllerButtonL) ? 0x40 : 0) |
               ((b & ControllerButtonZL) ? 0x80 : 0);
    pack_stick(&input[6], state->lx, state->ly);
    pack_stick(&input[9], state->rx, state->ry);
    input[12] = 0x09;
}

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

static void receive(const uint8_t* packet, size_t size) {
    if(size < 2) return;
    if(packet[0] == 0x80) {
        if(packet[1] == 0x01) identify();
        else {
            uint8_t report[PRO_PACKET] = {0};
            report[0] = packet[1] == 0x04 ? 0x30 : 0x81;
            report[1] = packet[1];
            queue_reply(report);
            if(packet[1] == 0x04) ready = true;
        }
    } else if(packet[0] == 0x01 && size >= 12) {
        uint8_t command = packet[10];
        uint8_t report[PRO_PACKET] = {0};
        report[0] = 0x21;
        report[1] = counter;
        memcpy(&report[2], &input[2], 11);
        report[13] = 0x80;
        report[14] = command;
        if(command == 0x02) {
            report[13] = 0x82;
            memcpy(&report[15], device_info, sizeof(device_info));
        } else if(command == 0x03 || command == 0x30) {
            report[15] = packet[11];
        } else if(command == 0x10 && size >= 16) {
            uint32_t address = (uint32_t)packet[11] | ((uint32_t)packet[12] << 8) |
                               ((uint32_t)packet[13] << 16) | ((uint32_t)packet[14] << 24);
            uint8_t length = packet[15];
            report[13] = 0x90;
            memcpy(&report[15], &packet[11], 5);
            if(length > PRO_PACKET - 20) length = PRO_PACKET - 20;
            spi_read(&report[20], address, length);
        } else if(command == 0x31) {
            report[13] = 0xB0;
            report[15] = packet[11];
        }
        queue_reply(report);
    }
}

static void endpoint_callback(usbd_device* device, uint8_t event, uint8_t ep) {
    if(event == usbd_evt_eptx && write_ready) furi_semaphore_release(write_ready);
    if(event == usbd_evt_eprx) {
        uint8_t packet[PRO_PACKET] = {0};
        int count = usbd_ep_read(device, ep, packet, sizeof(packet));
        if(count > 0) receive(packet, (size_t)count);
    }
}

static usbd_respond configure(usbd_device* device, uint8_t value) {
    if(value == 0) {
        connected = ready = false;
        reply_read = reply_write = 0;
        usbd_ep_deconfig(device, PRO_IN);
        usbd_ep_deconfig(device, PRO_OUT);
        usbd_reg_endpoint(device, PRO_IN, NULL);
        usbd_reg_endpoint(device, PRO_OUT, NULL);
        return usbd_ack;
    }
    if(value != 1) return usbd_fail;
    if(!usbd_ep_config(device, PRO_IN, USB_EPTYPE_INTERRUPT, PRO_PACKET)) return usbd_fail;
    if(!usbd_ep_config(device, PRO_OUT, USB_EPTYPE_INTERRUPT, PRO_PACKET)) {
        usbd_ep_deconfig(device, PRO_IN);
        return usbd_fail;
    }
    usbd_reg_endpoint(device, PRO_IN, endpoint_callback);
    usbd_reg_endpoint(device, PRO_OUT, endpoint_callback);
    connected = true;
    ready = false;
    reply_read = reply_write = 0;
    identify();
    return usbd_ack;
}

static usbd_respond control(usbd_device* device, usbd_ctlreq* req, usbd_rqc_callback* cb) {
    UNUSED(cb);
    if(req->wIndex != 0) return usbd_fail;
    if(((USB_REQ_RECIPIENT | USB_REQ_TYPE) & req->bmRequestType) ==
       (USB_REQ_INTERFACE | USB_REQ_STANDARD) && req->bRequest == USB_STD_GET_DESCRIPTOR) {
        if((req->wValue >> 8) == USB_DTYPE_HID) {
            device->status.data_ptr = (uint8_t*)&configuration.joystick.hid;
            device->status.data_count = sizeof(configuration.joystick.hid);
            return usbd_ack;
        }
        if((req->wValue >> 8) == USB_DTYPE_HID_REPORT) {
            device->status.data_ptr = (uint8_t*)pro_report_descriptor;
            device->status.data_count = sizeof(pro_report_descriptor);
            return usbd_ack;
        }
    }
    if(((USB_REQ_RECIPIENT | USB_REQ_TYPE) & req->bmRequestType) ==
       (USB_REQ_INTERFACE | USB_REQ_CLASS)) {
        if(req->bRequest == USB_HID_SETIDLE || req->bRequest == USB_HID_SETPROTOCOL)
            return usbd_ack;
        if(req->bRequest == USB_HID_GETREPORT) {
            // Do not return report 0x30 for a request for another report ID.
            if((req->wValue & 0xFF) != 0x30 || (req->wValue >> 8) != 1)
                return usbd_fail;
            device->status.data_ptr = input;
            device->status.data_count = sizeof(input);
            return usbd_ack;
        }
        // Some hosts send output reports over EP0 instead of the interrupt OUT endpoint.
        if(req->bRequest == USB_HID_SETREPORT && req->wLength) {
            receive(req->data, req->wLength);
            return usbd_ack;
        }
    }
    return usbd_fail;
}

static void init(usbd_device* device, FuriHalUsbInterface* interface, void* context) {
    UNUSED(interface);
    UNUSED(context);
    usb_device = device;
    connected = ready = false;
    reply_read = reply_write = 0;
    device->status.ep0size = PRO_EP0_SIZE;
    usbd_reg_config(device, configure);
    usbd_reg_control(device, control);
    usbd_connect(device, true);
}
static void deinit(usbd_device* device) {
    connected = ready = false;
    reply_read = reply_write = 0;
    usbd_reg_config(device, NULL);
    usbd_reg_control(device, NULL);
    device->status.ep0size = FLIPPER_EP0_SIZE;
    usb_device = NULL;
}
static void wakeup(usbd_device* device) { UNUSED(device); connected = true; }
static void suspend(usbd_device* device) {
    UNUSED(device);
    connected = ready = false;
    if(write_ready) furi_semaphore_release(write_ready);
}
static FuriHalUsbInterface pro_interface = {
    .init = init, .deinit = deinit, .wakeup = wakeup, .suspend = suspend,
    .dev_descr = &device_descriptor, .str_manuf_descr = (void*)&manufacturer,
    .str_prod_descr = (void*)&product, .cfg_descr = (void*)&configuration,
};

bool pro_usb_start(void) {
    if(write_ready) return false;
    write_ready = furi_semaphore_alloc(1, 1);
    set_input(&(ControllerState){.hat = 8, .lx = 128, .ly = 128, .rx = 128, .ry = 128});
    if(!furi_hal_usb_set_config(&pro_interface, NULL)) {
        furi_semaphore_free(write_ready);
        write_ready = NULL;
        return false;
    }
    return true;
}
bool pro_usb_connected(void) { return connected; }
bool pro_usb_ready(void) { return connected && ready; }
bool pro_usb_send(const ControllerState* state) {
    if(!state || !connected || !usb_device || !write_ready) return false;
    if(furi_semaphore_acquire(write_ready, 0) != FuriStatusOk) return false;
    if(!connected || !usb_device) {
        furi_semaphore_release(write_ready);
        return false;
    }
    if(reply_read != reply_write) {
        uint8_t report[PRO_PACKET];
        memcpy(report, replies[reply_read], sizeof(report));
        if(usbd_ep_write(usb_device, PRO_IN, report, sizeof(report)) == PRO_PACKET) {
            reply_read = (reply_read + 1) % PRO_REPLY_SLOTS;
        } else {
            furi_semaphore_release(write_ready);
            return false;
        }
    } else if(ready) {
        set_input(state);
        input[1] = counter++;
        if(usbd_ep_write(usb_device, PRO_IN, input, sizeof(input)) != PRO_PACKET) {
            furi_semaphore_release(write_ready);
            return false;
        }
    } else {
        furi_semaphore_release(write_ready);
        return false;
    }
    return true;
}
void pro_usb_stop(void) {
    if(!write_ready) return;
    connected = ready = false;
    if(usb_device) usbd_connect(usb_device, false);
    furi_hal_usb_set_config(NULL, NULL);
    furi_semaphore_free(write_ready);
    write_ready = NULL;
    reply_read = reply_write = 0;
}
