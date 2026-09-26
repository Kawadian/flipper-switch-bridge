#include "switch_usb.h"

#include <furi.h>
#include <furi_hal_usb.h>
#include <usb.h>
#include <usb_hid.h>
#include <string.h>

#define SWITCH_EP_IN  0x81
#define SWITCH_EP_OUT 0x02
// The Pokken Pad reference uses 64-byte interrupt endpoints on Switch.
#define SWITCH_EP_SIZE 64

typedef struct {
    struct usb_interface_descriptor interface;
    struct usb_hid_descriptor hid;
    struct usb_endpoint_descriptor in;
    struct usb_endpoint_descriptor out;
} HidInterface;

typedef struct {
    struct usb_config_descriptor config;
    HidInterface joystick;
} SwitchConfiguration;

// 16 buttons, 4-bit hat, 4 axes and a vendor byte. Output report is 8 bytes.
// These field lengths match the Pokken Pad-compatible Switch-Fightstick report.
static const uint8_t switch_report_descriptor[] = {
    0x05, 0x01, 0x09, 0x05, 0xA1, 0x01,
    0x15, 0x00, 0x25, 0x01, 0x35, 0x00, 0x45, 0x01,
    0x75, 0x01, 0x95, 0x10, 0x05, 0x09, 0x19, 0x01, 0x29, 0x10, 0x81, 0x02,
    0x05, 0x01, 0x25, 0x07, 0x46, 0x3B, 0x01,
    0x75, 0x04, 0x95, 0x01, 0x65, 0x14, 0x09, 0x39, 0x81, 0x42,
    0x65, 0x00, 0x95, 0x01, 0x81, 0x01,
    0x26, 0xFF, 0x00, 0x46, 0xFF, 0x00,
    0x09, 0x30, 0x09, 0x31, 0x09, 0x32, 0x09, 0x35,
    0x75, 0x08, 0x95, 0x04, 0x81, 0x02,
    0x06, 0x00, 0xFF, 0x09, 0x20, 0x95, 0x01, 0x81, 0x02,
    0x0A, 0x21, 0x26, 0x95, 0x08, 0x91, 0x02, 0xC0,
};

static struct usb_device_descriptor switch_device_descriptor = {
    .bLength = sizeof(struct usb_device_descriptor), .bDescriptorType = USB_DTYPE_DEVICE,
    .bcdUSB = VERSION_BCD(2, 0, 0), .bDeviceClass = 0,
    .bMaxPacketSize0 = 8, .idVendor = 0x0F0D, .idProduct = 0x0092,
    .bcdDevice = VERSION_BCD(1, 0, 0), .iManufacturer = 1,
    .iProduct = 2, .bNumConfigurations = 1,
};

static const SwitchConfiguration switch_configuration = {
    .config = {
        .bLength = sizeof(struct usb_config_descriptor), .bDescriptorType = USB_DTYPE_CONFIGURATION,
        .wTotalLength = sizeof(SwitchConfiguration), .bNumInterfaces = 1,
        .bConfigurationValue = 1, .bmAttributes = USB_CFG_ATTR_RESERVED,
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
            .wDescriptorLength0 = sizeof(switch_report_descriptor),
        },
        .in = {
            .bLength = sizeof(struct usb_endpoint_descriptor), .bDescriptorType = USB_DTYPE_ENDPOINT,
            .bEndpointAddress = SWITCH_EP_IN, .bmAttributes = USB_EPTYPE_INTERRUPT,
            .wMaxPacketSize = SWITCH_EP_SIZE, .bInterval = 5,
        },
        .out = {
            .bLength = sizeof(struct usb_endpoint_descriptor), .bDescriptorType = USB_DTYPE_ENDPOINT,
            .bEndpointAddress = SWITCH_EP_OUT, .bmAttributes = USB_EPTYPE_INTERRUPT,
            .wMaxPacketSize = SWITCH_EP_SIZE, .bInterval = 5,
        },
    },
};

static const struct usb_string_descriptor manufacturer = USB_STRING_DESC("HORI CO.,LTD.");
static const struct usb_string_descriptor product = USB_STRING_DESC("POKKEN CONTROLLER");
static usbd_device* usb_device;
static FuriSemaphore* write_ready;
static volatile bool connected;
static uint8_t last_report[8] = {0, 0, 8, 128, 128, 128, 128, 0};

static void endpoint_callback(usbd_device* device, uint8_t event, uint8_t ep) {
    if(event == usbd_evt_eptx && write_ready) furi_semaphore_release(write_ready);
    if(event == usbd_evt_eprx) {
        uint8_t ignored[SWITCH_EP_SIZE];
        usbd_ep_read(device, ep, ignored, sizeof(ignored));
    }
}

static usbd_respond configure(usbd_device* device, uint8_t value) {
    if(value == 0) {
        connected = false;
        usbd_ep_deconfig(device, SWITCH_EP_IN);
        usbd_ep_deconfig(device, SWITCH_EP_OUT);
        usbd_reg_endpoint(device, SWITCH_EP_IN, NULL);
        usbd_reg_endpoint(device, SWITCH_EP_OUT, NULL);
        return usbd_ack;
    }
    if(value != 1) return usbd_fail;
    usbd_ep_config(device, SWITCH_EP_IN, USB_EPTYPE_INTERRUPT, SWITCH_EP_SIZE);
    usbd_ep_config(device, SWITCH_EP_OUT, USB_EPTYPE_INTERRUPT, SWITCH_EP_SIZE);
    usbd_reg_endpoint(device, SWITCH_EP_IN, endpoint_callback);
    usbd_reg_endpoint(device, SWITCH_EP_OUT, endpoint_callback);
    connected = true;
    return usbd_ack;
}

static usbd_respond control(usbd_device* device, usbd_ctlreq* request, usbd_rqc_callback* cb) {
    UNUSED(cb);
    if(request->wIndex != 0) return usbd_fail;
    if(((USB_REQ_RECIPIENT | USB_REQ_TYPE) & request->bmRequestType) ==
       (USB_REQ_INTERFACE | USB_REQ_STANDARD) && request->bRequest == USB_STD_GET_DESCRIPTOR) {
        if((request->wValue >> 8) == USB_DTYPE_HID) {
            device->status.data_ptr = (uint8_t*)&switch_configuration.joystick.hid;
            device->status.data_count = sizeof(switch_configuration.joystick.hid);
            return usbd_ack;
        }
        if((request->wValue >> 8) == USB_DTYPE_HID_REPORT) {
            device->status.data_ptr = (uint8_t*)switch_report_descriptor;
            device->status.data_count = sizeof(switch_report_descriptor);
            return usbd_ack;
        }
    }
    if(((USB_REQ_RECIPIENT | USB_REQ_TYPE) & request->bmRequestType) ==
       (USB_REQ_INTERFACE | USB_REQ_CLASS)) {
        if(request->bRequest == USB_HID_SETIDLE || request->bRequest == USB_HID_SETPROTOCOL)
            return usbd_ack;
        if(request->bRequest == USB_HID_GETREPORT) {
            device->status.data_ptr = last_report;
            device->status.data_count = sizeof(last_report);
            return usbd_ack;
        }
    }
    return usbd_fail;
}

static void init(usbd_device* device, FuriHalUsbInterface* interface, void* context) {
    UNUSED(interface);
    UNUSED(context);
    usb_device = device;
    connected = false;
    usbd_reg_config(device, configure);
    usbd_reg_control(device, control);
    usbd_connect(device, true);
}

static void deinit(usbd_device* device) {
    connected = false;
    usbd_reg_config(device, NULL);
    usbd_reg_control(device, NULL);
    usb_device = NULL;
}

static void wakeup(usbd_device* device) { UNUSED(device); connected = true; }
static void suspend(usbd_device* device) {
    UNUSED(device);
    connected = false;
    if(write_ready) furi_semaphore_release(write_ready);
}

static FuriHalUsbInterface switch_interface = {
    .init = init, .deinit = deinit, .wakeup = wakeup, .suspend = suspend,
    .dev_descr = &switch_device_descriptor, .str_manuf_descr = (void*)&manufacturer,
    .str_prod_descr = (void*)&product, .cfg_descr = (void*)&switch_configuration,
};

bool switch_usb_start(void) {
    if(write_ready) return false;
    write_ready = furi_semaphore_alloc(1, 1);
    if(!furi_hal_usb_set_config(&switch_interface, NULL)) {
        furi_semaphore_free(write_ready);
        write_ready = NULL;
        return false;
    }
    return true;
}

bool switch_usb_connected(void) { return connected; }

bool switch_usb_send(const ControllerState* state) {
    if(!state || !connected || !usb_device || !write_ready) return false;
    if(furi_semaphore_acquire(write_ready, 20) != FuriStatusOk) return false;
    if(!connected || !usb_device) {
        furi_semaphore_release(write_ready);
        return false;
    }
    uint8_t report[8] = {
        (uint8_t)state->buttons, (uint8_t)(state->buttons >> 8), state->hat,
        state->lx, state->ly, state->rx, state->ry, 0};
    memcpy(last_report, report, sizeof(report));
    usbd_ep_write(usb_device, SWITCH_EP_IN, report, sizeof(report));
    return true;
}

void switch_usb_stop(void) {
    if(!write_ready) return;
    ControllerState neutral = controller_state_neutral();
    switch_usb_send(&neutral);
    furi_hal_usb_set_config(NULL, NULL);
    furi_semaphore_free(write_ready);
    write_ready = NULL;
    connected = false;
}
