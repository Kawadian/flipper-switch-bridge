#include "ble_link.h"
#include "controller_state.h"
#include "switch_usb.h"

#include <furi.h>
#include <gui/gui.h>
#include <gui/view_port.h>
#include <input/input.h>
#include <stdio.h>
#include <string.h>

#define INPUT_TIMEOUT_MS 500

typedef enum { ModeUsb, ModeBle, ModeBridge } AppMode;

typedef struct {
    AppMode mode;
    bool active;
    bool usb_ready;
    BleLink* ble;
    ControllerState state;
    uint8_t last_sequence;
    uint32_t last_packet_tick;
    uint32_t received;
    uint32_t last_usb_tick;
} App;

static void draw(Canvas* canvas, void* context) {
    App* app = context;
    canvas_clear(canvas);
    canvas_set_font(canvas, FontPrimary);
    canvas_draw_str(canvas, 2, 12, "Switch Controller");
    canvas_set_font(canvas, FontSecondary);
    if(!app->active) {
        const char* labels[] = {"USB gamepad", "BLE receiver", "BLE -> USB"};
        canvas_draw_str(canvas, 2, 29, labels[app->mode]);
        canvas_draw_str(canvas, 2, 46, "UP/DOWN mode   OK start");
    } else {
        canvas_draw_str(canvas, 2, 28, app->usb_ready ?
            (switch_usb_connected() ? "USB: connected" : "USB: waiting") : "USB: off");
        canvas_draw_str(canvas, 2, 40, app->ble ?
            (ble_link_connected(app->ble) ? "BLE: connected" : "BLE: waiting") : "BLE: off");
        char counter[32];
        snprintf(counter, sizeof(counter), "RX: %lu  SEQ: %u", (unsigned long)app->received,
                 app->last_sequence);
        canvas_draw_str(canvas, 2, 53, counter);
        canvas_draw_str(canvas, 2, 63, "OK=A   hold BACK=exit");
    }
}

static void input_callback(InputEvent* event, void* context) {
    furi_message_queue_put(context, event, 0);
}

static bool start_mode(App* app, FuriMessageQueue* packets) {
    if(app->mode != ModeBle) {
        app->usb_ready = switch_usb_start();
        if(!app->usb_ready) return false;
        switch_usb_send(&app->state);
    }
    if(app->mode != ModeUsb) {
        app->ble = ble_link_start(packets);
        if(!app->ble) {
            if(app->usb_ready) switch_usb_stop();
            app->usb_ready = false;
            return false;
        }
    }
    app->active = true;
    app->last_packet_tick = furi_get_tick();
    return true;
}

static void stop_mode(App* app) {
    if(app->ble) {
        ble_link_stop(app->ble);
        app->ble = NULL;
    }
    if(app->usb_ready) {
        switch_usb_stop();
        app->usb_ready = false;
    }
    app->active = false;
}

int32_t switch_controller_app(void* args) {
    UNUSED(args);
    App app = {.mode = ModeUsb, .state = controller_state_neutral()};
    FuriMessageQueue* events = furi_message_queue_alloc(16, sizeof(InputEvent));
    FuriMessageQueue* packets = furi_message_queue_alloc(16, CONTROLLER_PACKET_SIZE);
    Gui* gui = furi_record_open(RECORD_GUI);
    ViewPort* view = view_port_alloc();
    view_port_draw_callback_set(view, draw, &app);
    view_port_input_callback_set(view, input_callback, events);
    gui_add_view_port(gui, view, GuiLayerFullscreen);

    bool running = true;
    while(running) {
        InputEvent event;
        if(furi_message_queue_get(events, &event, 20) == FuriStatusOk) {
            if(!app.active) {
                if(event.type == InputTypePress && event.key == InputKeyUp)
                    app.mode = (app.mode + 2) % 3;
                if(event.type == InputTypePress && event.key == InputKeyDown)
                    app.mode = (app.mode + 1) % 3;
                if(event.type == InputTypePress && event.key == InputKeyOk)
                    start_mode(&app, packets);
                if(event.type == InputTypePress && event.key == InputKeyBack) running = false;
            } else if(event.key == InputKeyBack && event.type == InputTypeLong) {
                running = false;
            } else if(event.key == InputKeyOk && app.usb_ready &&
                      (event.type == InputTypePress || event.type == InputTypeRelease)) {
                if(event.type == InputTypePress) app.state.buttons |= ControllerButtonA;
                else app.state.buttons &= ~ControllerButtonA;
                switch_usb_send(&app.state);
            }
        }
        uint8_t packet[CONTROLLER_PACKET_SIZE];
        bool drained = false;
        while(app.ble && furi_message_queue_get(packets, packet, 0) == FuriStatusOk) {
            drained = true;
            ControllerState state;
            uint8_t sequence;
            if(controller_packet_decode(packet, sizeof(packet), &state, &sequence)) {
                app.state = state;
                app.last_sequence = sequence;
                app.last_packet_tick = furi_get_tick();
                app.received++;
                if(app.usb_ready) switch_usb_send(&app.state);
            }
        }
        if(drained) ble_link_ack(app.ble);
        if(app.ble && app.usb_ready &&
           (!ble_link_connected(app.ble) ||
            furi_get_tick() - app.last_packet_tick > furi_ms_to_ticks(INPUT_TIMEOUT_MS))) {
            ControllerState neutral = controller_state_neutral();
            if(app.state.buttons || app.state.hat != 8 || app.state.lx != 128 ||
               app.state.ly != 128 || app.state.rx != 128 || app.state.ry != 128) {
                app.state = neutral;
                switch_usb_send(&app.state);
            }
        }
        if(app.usb_ready &&
           furi_get_tick() - app.last_usb_tick >= furi_ms_to_ticks(50)) {
            switch_usb_send(&app.state);
            app.last_usb_tick = furi_get_tick();
        }
        view_port_update(view);
    }
    stop_mode(&app);
    gui_remove_view_port(gui, view);
    view_port_free(view);
    furi_record_close(RECORD_GUI);
    furi_message_queue_free(packets);
    furi_message_queue_free(events);
    return 0;
}
