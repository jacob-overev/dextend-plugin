/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

#define YAMAHA_AOA_TEST
#include "yamaha_aoa.c"
static int request(unsigned type, unsigned code, unsigned value, unsigned index, unsigned length)
{
    struct usb_ctrlrequest c = {.bRequestType = type,
                                .bRequest = code,
                                .wValue = value,
                                .wIndex = index,
                                .wLength = length};
    assert(!fake_ep0.queued);
    return setup(&fake_gadget, &c);
}
static void ack(void) { finish_request(&fake_ep0, 0, NULL, 0); }
static void reset_during_copy(void)
{
    disconnect(&fake_gadget);
    assert(!configure(1));
}
int main(void)
{
    char buffer[64];
    unsigned type, code, i;
    assert(aoa_init() == -EPERM);
    experimental = true;
    fake_parent.name = "ci_hdrc.0";
    assert(aoa_init() == -ENODEV);
    fake_parent.name = "ci_hdrc.1";
    assert(!aoa_init());
    state_show(NULL, NULL, buffer);
    assert(!strcmp(buffer, "DISCONNECTED\n"));
    assert(!device_open(NULL, NULL));
    assert(device_open(NULL, NULL) == -EBUSY);
    assert(device_read(NULL, buffer, 1, NULL) == -ENODEV);
    assert(device_poll(NULL, NULL) & POLLHUP);
    /* Vendor request type and code must match exactly; no class/interface alias. */
    for (type = 0; type < 256; type++)
        for (code = 0; code < 256; code++) {
            enum aoa_action a = aoa_request(type, code, 0, 0, 2);
            assert(a == ((type == 0xc0 && code == 51)   ? AOA_PROTOCOL
                         : (type == 0x40 && code == 52) ? AOA_STRING
                                                        : AOA_STALL));
        }
    assert(aoa_request(0x40, 52, 0, 6, 1) == AOA_STALL);
    assert(aoa_request(0x40, 52, 0, 0, 257) == AOA_STALL);
    assert(aoa_request(0x40, 52, 0, 4, 0) == AOA_STRING);
    assert(aoa_request(0x40, 53, 1, 0, 0) == AOA_STALL);
    assert(request(0xc0, 51, 0, 0, 2) == 0);
    {
        struct usb_ctrlrequest overlapping = {
            .bRequestType = 0x40, .bRequest = 52, .wValue = 0, .wIndex = 5, .wLength = 4};
        unsigned char before[2];
        memcpy(before, control->buf, sizeof(before));
        assert(setup(&fake_gadget, &overlapping) == -EBUSY);
        assert(control_pending && control_action == AOA_PROTOCOL && control->length == 2);
        assert(!memcmp(control->buf, before, sizeof(before)));
    }
    assert(control->length == 2 && ((u8 *)control->buf)[0] == 1 && ((u8 *)control->buf)[1] == 0);
    ack();
    assert(request(0x40, 52, 0, 0, 257) == -EOPNOTSUPP);
    assert(!control_pending);
    for (i = 0; i < 6; i++) {
        assert(!request(0x40, 52, 0, i, 4));
        finish_request(&fake_ep0, 0, "abc\0", 4);
        assert(!strcmp((char *)host_strings[i], "abc"));
    }
    assert(!request(0x80, 6, USB_DT_CONFIG << 8, 0, 255));
    assert(control->length == 32);
    assert(((u8 *)control->buf)[20] == 0x81 && ((u8 *)control->buf)[27] == 2);
    assert(((u8 *)control->buf)[22] == 0 && ((u8 *)control->buf)[23] == 2);
    ack();
    assert(!request(0x80, 6, USB_DT_OTHER_SPEED_CONFIG << 8, 0, 255));
    assert(((u8 *)control->buf)[1] == USB_DT_OTHER_SPEED_CONFIG && ((u8 *)control->buf)[22] == 64);
    ack();
    assert(request(0x80, 6, (USB_DT_CONFIG << 8) | 1, 0, 9) == -EOPNOTSUPP);
    assert(!request(0x80, 6, USB_DT_DEVICE << 8, 0, 8));
    assert(control->length == 8);
    ack();
    assert(!request(0x80, 6, (USB_DT_STRING << 8) | 1, 0x409, 255));
    assert(control->length > 2);
    ack();
    assert(request(0x80, 6, (USB_DT_STRING << 8) | 3, 0x409, 255) == -EOPNOTSUPP);
    /* Yamaha sends an empty URI before START. ACK it and clear the old URI. */
    assert(!request(0x40, 52, 0, 4, 0));
    assert(control->length == 0);
    ack();
    assert(host_strings[4][0] == 0 && !mode_work.scheduled);
    assert(!request(0x40, 53, 0, 0, 0));
    assert(!mode_work.scheduled);
    finish_request(&fake_ep0, -ECONNRESET, NULL, 0);
    assert(!mode_work.scheduled);
    assert(!request(0x40, 53, 0, 0, 0));
    ack();
    assert(mode_work.scheduled);
    mode_work.scheduled = false;
    switch_mode(NULL);
    assert(accessory && device_desc.idVendor == 0x18d1 && device_desc.idProduct == 0x2d00);
    assert(!request(0x40, 53, 0, 0, 0));
    ack();
    assert(!mode_work.scheduled);
    assert(!request(0, 9, 1, 0, 0));
    ack();
    assert(online && fake_out.queued);
    state_show(NULL, NULL, buffer);
    assert(!strcmp(buffer, "CONFIGURED\n"));
    assert(device_read(NULL, buffer, sizeof(buffer), NULL) == -EAGAIN);
    finish_request(&fake_out, 0, NULL, 0);
    assert(fake_out.queued);
    finish_request(&fake_out, 0, "abcdef", 6);
    assert(!fake_out.queued);
    assert(device_poll(NULL, NULL) & POLLIN);
    copy_failure = true;
    assert(device_read(NULL, buffer, 3, NULL) == -EFAULT);
    copy_failure = false;
    assert(rx_offset == 0);
    assert(device_read(NULL, buffer, 2, NULL) == 2 && !memcmp(buffer, "ab", 2));
    assert(!fake_out.queued);
    assert(device_read(NULL, buffer, 64, NULL) == 4 && !memcmp(buffer, "cdef", 4));
    assert(fake_out.queued);
    assert(device_write(NULL, "xyz", 3, NULL) == 3);
    assert(!(device_poll(NULL, NULL) & POLLOUT));
    assert(device_write(NULL, "x", 1, NULL) == -EAGAIN);
    assert(tx->length == 3 && !memcmp(tx->buf, "xyz", 3));
    finish_request(&fake_in, 0, NULL, 3);
    assert(device_poll(NULL, NULL) & POLLOUT);
    /* Reset with requests in flight must wake users and discard old input. */
    assert(device_write(NULL, "q", 1, NULL) == 1);
    disconnect(&fake_gadget);
    assert(!online && !fake_in.queued && !fake_out.queued);
    assert(!configure(1));
    finish_request(&fake_out, 0, "old", 3);
    disconnect(&fake_gadget);
    assert(!rx_size);
    assert(!configure(1));
    finish_request(&fake_out, 0, "old", 3);
    copy_hook = reset_during_copy;
    assert(device_read(NULL, buffer, 3, NULL) == -EIO);
    assert(fake_out.queued && !rx_size);
    copy_hook = reset_during_copy;
    assert(device_write(NULL, "old", 3, NULL) == -EIO);
    assert(!fake_in.queued);
    {
        char *large = malloc(BULK_SIZE + 1);
        memset(large, 'x', BULK_SIZE + 1);
        assert(device_write(NULL, large, BULK_SIZE + 1, NULL) == BULK_SIZE);
        finish_request(&fake_in, 0, NULL, BULK_SIZE);
        free(large);
    }
    queue_failure = true;
    assert(device_write(NULL, "q", 1, NULL) == -EIO);
    queue_failure = false;
    assert(device_poll(NULL, NULL) & POLLERR);
    assert(!configure(1));
    assert(!fault);
    enable_failure = true;
    assert(configure(1) == -EIO);
    assert(!online && !fake_in.enabled);
    enable_failure = false;
    assert(!configure(1));
    finish_request(&fake_out, -EIO, NULL, 0);
    assert(fault);
    assert(!configure(0));
    assert(!online);
    assert(!request(0xc0, 51, 0, 0, 2)); /* Unload with an EP0 transfer outstanding. */
    device_release(NULL, NULL);
    aoa_exit();
    assert(!registered_driver && !control && !rx && !tx);
    puts("PASS: 65536 request combinations, AOA handshake, descriptors, controller guard, bounded "
         "I/O, backpressure, reset, cancellation and error recovery");
}
