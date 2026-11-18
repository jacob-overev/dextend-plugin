// SPDX-License-Identifier: GPL-2.0-only
/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Independent AOA 1.0 gadget for Linux/NXP 3.14.
 * Exposes a bounded nonblocking byte stream at /dev/yamaha_aoa.
 * One in-flight bulk request per direction; no drops on a slow reader.
 * This source contains no vendor code, offsets, or binary patches.
 */
#ifdef YAMAHA_AOA_TEST
#include "test_kernel.h"
#else
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/miscdevice.h>
#include <linux/fs.h>
#include <linux/poll.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/uaccess.h>
#include <linux/workqueue.h>
#include <linux/delay.h>
#include <linux/completion.h>
#include <linux/usb/ch9.h>
#include <linux/usb/gadget.h>
#endif
#include "aoa_protocol.h"

#define BULK_SIZE 16384
#define CTRL_SIZE 256
static bool experimental;
module_param(experimental, bool, 0444);
MODULE_PARM_DESC(experimental, "Explicit opt-in; only after target ABI verification");
/* Controller selection is deliberately fixed; never claim the phone port. */
static const char target_udc[] = "ci_hdrc.1";
static DEFINE_SPINLOCK(state_lock);
static DEFINE_MUTEX(read_lock);
static DEFINE_MUTEX(write_lock);
static DECLARE_WAIT_QUEUE_HEAD(io_wait);
static atomic_t opened = ATOMIC_INIT(0);
static struct usb_gadget *gadget;
static struct usb_ep *ep_in, *ep_out;
static struct usb_request *rx, *tx, *control;
static unsigned rx_size, rx_offset, generation;
static bool online, bound, rx_busy, rx_held, tx_busy, tx_held, fault;
static bool accessory, stopping;
static bool control_pending;
static struct completion control_drained;
static bool in_halted, out_halted;
static enum aoa_action control_action;
static unsigned control_index;
static unsigned char host_strings[6][CTRL_SIZE];
static void switch_mode(struct work_struct *work);
static DECLARE_DELAYED_WORK(mode_work, switch_mode);

static struct usb_device_descriptor device_desc = {
    .bLength = USB_DT_DEVICE_SIZE,
    .bDescriptorType = USB_DT_DEVICE,
    .bcdUSB = cpu_to_le16(0x0200),
    .bMaxPacketSize0 = 64,
    /* Lab profile matching the owner's device before AOA negotiation. */
    .idVendor = cpu_to_le16(0x1314),
    .idProduct = cpu_to_le16(0x1521),
    .bcdDevice = cpu_to_le16(0x0100),
    .iManufacturer = 1,
    .iProduct = 2,
    .bNumConfigurations = 1,
};
static struct usb_qualifier_descriptor qualifier = {
    .bLength = sizeof(qualifier),
    .bDescriptorType = USB_DT_DEVICE_QUALIFIER,
    .bcdUSB = cpu_to_le16(0x0200),
    .bMaxPacketSize0 = 64,
    .bNumConfigurations = 1,
};
/* Endpoint descriptors in Linux contain two optional audio bytes, so build
 * configuration bytes explicitly rather than copying struct descriptors. */
static struct usb_endpoint_descriptor in_desc = {
    .bLength = USB_DT_ENDPOINT_SIZE,
    .bDescriptorType = USB_DT_ENDPOINT,
    .bEndpointAddress = USB_DIR_IN,
    .bmAttributes = USB_ENDPOINT_XFER_BULK,
};
static struct usb_endpoint_descriptor out_desc = {
    .bLength = USB_DT_ENDPOINT_SIZE,
    .bDescriptorType = USB_DT_ENDPOINT,
    .bEndpointAddress = USB_DIR_OUT,
    .bmAttributes = USB_ENDPOINT_XFER_BULK,
};
static int config_descriptor(u8 *buffer, bool other)
{
    bool high = gadget->speed == USB_SPEED_HIGH;
    unsigned packet;
    u8 desc[] = {
        9,
        USB_DT_CONFIG,
        32,
        0,
        1,
        1,
        0,
        USB_CONFIG_ATT_ONE,
        50,
        9,
        USB_DT_INTERFACE,
        0,
        0,
        2,
        0xff,
        0xff,
        0,
        0,
        7,
        USB_DT_ENDPOINT,
        0,
        USB_ENDPOINT_XFER_BULK,
        0,
        0,
        0,
        7,
        USB_DT_ENDPOINT,
        0,
        USB_ENDPOINT_XFER_BULK,
        0,
        0,
        0,
    };
    if (other)
        high = !high;
    packet = high ? 512 : 64;
    desc[1] = other ? USB_DT_OTHER_SPEED_CONFIG : USB_DT_CONFIG;
    desc[20] = in_desc.bEndpointAddress;
    desc[27] = out_desc.bEndpointAddress;
    desc[22] = desc[29] = packet & 255;
    desc[23] = desc[30] = packet >> 8;
    memcpy(buffer, desc, sizeof(desc));
    return sizeof(desc);
}
static int string_descriptor(u8 *buffer, unsigned index, unsigned language)
{
    const char *s;
    unsigned i, n;
    if (!index) {
        buffer[0] = 4;
        buffer[1] = USB_DT_STRING;
        buffer[2] = 9;
        buffer[3] = 4;
        return 4;
    }
    if (language != 0x0409)
        return -EOPNOTSUPP;
    if (index == 1)
        s = "Yamaha bridge project";
    else if (index == 2)
        s = "Experimental AOA transport";
    else
        return -EOPNOTSUPP;
    n = strlen(s);
    buffer[0] = 2 + 2 * n;
    buffer[1] = USB_DT_STRING;
    for (i = 0; i < n; ++i) {
        buffer[2 + 2 * i] = s[i];
        buffer[3 + 2 * i] = 0;
    }
    return buffer[0];
}
/* Called under state_lock; queue completion cannot run synchronously on success. */
static int queue_rx(void)
{
    int result;
    if (!online || fault || rx_busy || rx_held || rx_size)
        return 0;
    rx->length = BULK_SIZE;
    rx_busy = true;
    result = usb_ep_queue(ep_out, rx, GFP_ATOMIC);
    if (result) {
        rx_busy = false;
        fault = true;
    }
    return result;
}
static void bulk_complete(struct usb_ep *ep, struct usb_request *request)
{
    unsigned long flags;
    spin_lock_irqsave(&state_lock, flags);
    if (request == rx) {
        rx_busy = false;
        if (online && !request->status) {
            rx_size = request->actual;
            rx_offset = 0;
            if (!rx_size)
                queue_rx(); /* Empty USB packets are not EOF. */
        }
    } else
        tx_busy = false;
    if (online && request->status)
        fault = true;
    spin_unlock_irqrestore(&state_lock, flags);
    wake_up_interruptible(&io_wait);
}
static void disable_data(void)
{
    unsigned long flags;
    bool was_online;
    spin_lock_irqsave(&state_lock, flags);
    was_online = online;
    online = false;
    generation++;
    rx_size = rx_offset = 0;
    spin_unlock_irqrestore(&state_lock, flags);
    /* disable completes all queued requests; callbacks take state_lock. */
    if (was_online) {
        usb_ep_disable(ep_out);
        usb_ep_disable(ep_in);
    }
    wake_up_interruptible(&io_wait);
}
static int configure(unsigned value)
{
    unsigned long flags;
    int result;
    disable_data();
    if (!value)
        return 0;
    in_desc.wMaxPacketSize = out_desc.wMaxPacketSize =
        cpu_to_le16(gadget->speed == USB_SPEED_HIGH ? 512 : 64);
    ep_in->desc = &in_desc;
    ep_out->desc = &out_desc;
    result = usb_ep_enable(ep_in);
    if (result)
        return result;
    result = usb_ep_enable(ep_out);
    if (result) {
        usb_ep_disable(ep_in);
        return result;
    }
    spin_lock_irqsave(&state_lock, flags);
    online = true;
    fault = false;
    in_halted = out_halted = false;
    result = queue_rx();
    spin_unlock_irqrestore(&state_lock, flags);
    if (result)
        disable_data();
    wake_up_interruptible(&io_wait);
    return result;
}
static void control_complete(struct usb_ep *ep, struct usb_request *request)
{
    unsigned long flags;
    spin_lock_irqsave(&state_lock, flags);
    if (!request->status && !stopping && control_action == AOA_START && !accessory)
        schedule_delayed_work(&mode_work, msecs_to_jiffies(100));
    else if (!request->status && !stopping && control_action == AOA_STRING &&
             request->actual <= CTRL_SIZE) {
        if (request->actual) {
            memcpy(host_strings[control_index], request->buf, request->actual);
            host_strings[control_index][request->actual - 1] = 0;
        } else {
            host_strings[control_index][0] = 0;
        }
    }
    control_pending = false;
    complete(&control_drained);
    spin_unlock_irqrestore(&state_lock, flags);
}
static int setup(struct usb_gadget *g, const struct usb_ctrlrequest *c)
{
    unsigned value = le16_to_cpu(c->wValue), index = le16_to_cpu(c->wIndex);
    unsigned length = le16_to_cpu(c->wLength);
    unsigned long flags;
    int result = -EOPNOTSUPP;
    u8 *b;
    struct usb_ep *endpoint = NULL;
    /* Reserve the single EP0 request before touching its buffer or metadata.
     * ChipIdea can complete an old request while nuking a nonempty EP0 queue;
     * prevent requeue of that request before entering usb_ep_queue(). */
    spin_lock_irqsave(&state_lock, flags);
    if (stopping || !bound || control_pending) {
        result = (stopping || !bound) ? -ESHUTDOWN : -EBUSY;
        spin_unlock_irqrestore(&state_lock, flags);
        return result;
    }
    reinit_completion(&control_drained);
    control_pending = true;
    spin_unlock_irqrestore(&state_lock, flags);
    b = control->buf;
    control_action = AOA_STALL;
    if ((c->bRequestType & USB_TYPE_MASK) == USB_TYPE_VENDOR) {
        control_action = aoa_request(c->bRequestType, c->bRequest, value, index, length);
        if (control_action == AOA_PROTOCOL) {
            b[0] = 1;
            b[1] = 0;
            result = 2;
        } else if (control_action == AOA_STRING) {
            control_index = index;
            result = length;
        } else if (control_action == AOA_START)
            result = 0;
    } else if (c->bRequestType == USB_DIR_IN && c->bRequest == USB_REQ_GET_DESCRIPTOR) {
        switch (value >> 8) {
        case USB_DT_DEVICE:
            if (!(value & 255) && !index) {
                memcpy(b, &device_desc, sizeof(device_desc));
                result = sizeof(device_desc);
            }
            break;
        case USB_DT_CONFIG:
        case USB_DT_OTHER_SPEED_CONFIG:
            if (!(value & 255) && !index)
                result = config_descriptor(b, (value >> 8) == USB_DT_OTHER_SPEED_CONFIG);
            break;
        case USB_DT_DEVICE_QUALIFIER:
            if (!(value & 255) && !index) {
                memcpy(b, &qualifier, sizeof(qualifier));
                result = sizeof(qualifier);
            }
            break;
        case USB_DT_STRING:
            result = string_descriptor(b, value & 255, index);
            break;
        }
    } else if (c->bRequestType == 0 && c->bRequest == USB_REQ_SET_CONFIGURATION && !index &&
               !length && value <= 1)
        result = configure(value);
    else if (c->bRequestType == USB_DIR_IN && c->bRequest == USB_REQ_GET_CONFIGURATION && !value &&
             !index && length == 1) {
        b[0] = online ? 1 : 0;
        result = 1;
    } else if (c->bRequestType == USB_RECIP_INTERFACE && c->bRequest == USB_REQ_SET_INTERFACE &&
               online && !value && !index && !length)
        result = configure(1);
    else if (c->bRequestType == (USB_DIR_IN | USB_RECIP_INTERFACE) &&
             c->bRequest == USB_REQ_GET_INTERFACE && online && !value && !index && length == 1) {
        b[0] = 0;
        result = 1;
    } else if (c->bRequest == USB_REQ_GET_STATUS && !value && length == 2) {
        if (c->bRequestType == USB_DIR_IN && !index) {
            b[0] = b[1] = 0;
            result = 2;
        } else if (c->bRequestType == (USB_DIR_IN | USB_RECIP_INTERFACE) && !index && online) {
            b[0] = b[1] = 0;
            result = 2;
        } else if (c->bRequestType == (USB_DIR_IN | USB_RECIP_ENDPOINT) && online &&
                   (index == in_desc.bEndpointAddress || index == out_desc.bEndpointAddress)) {
            b[0] = index == in_desc.bEndpointAddress ? in_halted : out_halted;
            b[1] = 0;
            result = 2;
        }
    } else if (c->bRequestType == USB_RECIP_ENDPOINT && value == USB_ENDPOINT_HALT && !length &&
               online &&
               (c->bRequest == USB_REQ_CLEAR_FEATURE || c->bRequest == USB_REQ_SET_FEATURE)) {
        if (index == in_desc.bEndpointAddress)
            endpoint = ep_in;
        else if (index == out_desc.bEndpointAddress)
            endpoint = ep_out;
        if (endpoint) {
            bool halt = c->bRequest == USB_REQ_SET_FEATURE;
            result = halt ? usb_ep_set_halt(endpoint) : usb_ep_clear_halt(endpoint);
            if (!result) {
                if (endpoint == ep_in)
                    in_halted = halt;
                else
                    out_halted = halt;
            }
        }
    }
    if (result < 0)
        goto abort_control;
    /* Vendor string parsing already bounds length; enforce the buffer limit
     * for all current/future handlers before giving a request to DMA. */
    if ((unsigned)result > CTRL_SIZE) {
        result = -EOVERFLOW;
        goto abort_control;
    }
    control->length = min_t(unsigned, result, length);
    control->zero = (unsigned)result < length;
    spin_lock_irqsave(&state_lock, flags);
    result = stopping ? -ESHUTDOWN : usb_ep_queue(g->ep0, control, GFP_ATOMIC);
    if (result) {
        control_pending = false;
        complete(&control_drained);
    }
    spin_unlock_irqrestore(&state_lock, flags);
    return result;
abort_control:
    spin_lock_irqsave(&state_lock, flags);
    control_pending = false;
    complete(&control_drained);
    spin_unlock_irqrestore(&state_lock, flags);
    return result;
}
static void switch_mode(struct work_struct *work)
{
    if (stopping || !bound || accessory)
        return;
    usb_gadget_disconnect(gadget);
    disable_data();
    msleep(300);
    if (stopping)
        return;
    device_desc.idVendor = cpu_to_le16(0x18d1);
    device_desc.idProduct = cpu_to_le16(0x2d00);
    accessory = true;
    usb_gadget_connect(gadget);
}
static int device_open(struct inode *inode, struct file *file)
{
    if (atomic_cmpxchg(&opened, 0, 1))
        return -EBUSY;
    return 0;
}
static int device_release(struct inode *inode, struct file *file)
{
    atomic_set(&opened, 0);
    return 0;
}
/* This initial driver intentionally requires nonblocking clients; the bridge
 * already uses O_NONBLOCK and poll. Avoid sleeping USB calls in file I/O. */
static ssize_t device_read(struct file *file, char __user *buffer, size_t count, loff_t *pos)
{
    unsigned long flags;
    unsigned n, offset, epoch;
    int result;
    if (!count)
        return 0;
    if (mutex_lock_interruptible(&read_lock))
        return -ERESTARTSYS;
    spin_lock_irqsave(&state_lock, flags);
    if (!online || fault || !rx_size) {
        result = !online ? -ENODEV : fault ? -EIO : -EAGAIN;
        spin_unlock_irqrestore(&state_lock, flags);
        goto done;
    }
    n = min_t(size_t, count, rx_size - rx_offset);
    offset = rx_offset;
    epoch = generation;
    rx_held = true;
    spin_unlock_irqrestore(&state_lock, flags);
    result = copy_to_user(buffer, rx->buf + offset, n) ? -EFAULT : (int)n;
    spin_lock_irqsave(&state_lock, flags);
    rx_held = false;
    if (epoch != generation)
        result = -EIO;
    else if (result > 0) {
        rx_offset += n;
        if (rx_offset == rx_size)
            rx_size = rx_offset = 0;
    }
    queue_rx();
    spin_unlock_irqrestore(&state_lock, flags);
done:
    mutex_unlock(&read_lock);
    return result;
}
static ssize_t device_write(struct file *file, const char __user *buffer, size_t count, loff_t *pos)
{
    unsigned long flags;
    unsigned n = min_t(size_t, count, BULK_SIZE), epoch;
    int result;
    if (!count)
        return 0;
    if (mutex_lock_interruptible(&write_lock))
        return -ERESTARTSYS;
    spin_lock_irqsave(&state_lock, flags);
    if (!online || fault || tx_busy) {
        result = !online ? -ENODEV : fault ? -EIO : -EAGAIN;
        spin_unlock_irqrestore(&state_lock, flags);
        goto done;
    }
    epoch = generation;
    tx_held = true;
    spin_unlock_irqrestore(&state_lock, flags);
    result = copy_from_user(tx->buf, buffer, n) ? -EFAULT : 0;
    spin_lock_irqsave(&state_lock, flags);
    tx_held = false;
    if (epoch != generation || !online)
        result = -EIO;
    if (!result) {
        tx_busy = true;
        tx->length = n;
        tx->zero = 0;
        result = usb_ep_queue(ep_in, tx, GFP_ATOMIC);
        if (result) {
            tx_busy = false;
            fault = true;
        } else
            result = n;
    }
    spin_unlock_irqrestore(&state_lock, flags);
done:
    mutex_unlock(&write_lock);
    return result;
}
static unsigned device_poll(struct file *file, poll_table *wait)
{
    unsigned long flags;
    unsigned mask = 0;
    poll_wait(file, &io_wait, wait);
    spin_lock_irqsave(&state_lock, flags);
    if (!online)
        mask = POLLHUP | POLLERR;
    else if (fault)
        mask = POLLERR;
    else {
        if (rx_size)
            mask |= POLLIN | POLLRDNORM;
        if (!tx_busy && !tx_held)
            mask |= POLLOUT | POLLWRNORM;
    }
    spin_unlock_irqrestore(&state_lock, flags);
    return mask;
}
static const struct file_operations device_ops = {
    .owner = THIS_MODULE,
    .open = device_open,
    .release = device_release,
    .read = device_read,
    .write = device_write,
    .poll = device_poll,
    .llseek = no_llseek,
};
static struct miscdevice misc = {
    .minor = MISC_DYNAMIC_MINOR,
    .name = "yamaha_aoa",
    .fops = &device_ops,
    .mode = 0600,
};
static ssize_t state_show(struct device *dev, struct device_attribute *attr, char *buf)
{
    unsigned long flags;
    const char *state;
    spin_lock_irqsave(&state_lock, flags);
    state = !online ? "DISCONNECTED" : accessory ? "CONFIGURED" : "NEGOTIATING";
    spin_unlock_irqrestore(&state_lock, flags);
    return sprintf(buf, "%s\n", state);
}
static DEVICE_ATTR(state, 0444, state_show, NULL);
static struct usb_request *alloc_request(struct usb_ep *ep, unsigned size)
{
    struct usb_request *request = usb_ep_alloc_request(ep, GFP_KERNEL);
    if (!request)
        return NULL;
    request->buf = kmalloc(size, GFP_KERNEL);
    if (!request->buf) {
        usb_ep_free_request(ep, request);
        return NULL;
    }
    request->complete = bulk_complete;
    return request;
}
static void free_request(struct usb_ep *ep, struct usb_request *request)
{
    if (!request)
        return;
    kfree(request->buf);
    usb_ep_free_request(ep, request);
}
static void unbind(struct usb_gadget *g)
{
    unsigned long flags;
    bool pending;
    spin_lock_irqsave(&state_lock, flags);
    stopping = true;
    pending = control_pending;
    spin_unlock_irqrestore(&state_lock, flags);
    cancel_delayed_work_sync(&mode_work);
    if (pending) {
        usb_ep_dequeue(g->ep0, control);
        wait_for_completion(&control_drained);
    }
    disable_data();
    mutex_lock(&read_lock);
    mutex_lock(&write_lock);
    bound = false;
    /* Both control and bulk completions are drained before freeing buffers. */
    free_request(g->ep0, control);
    free_request(ep_out, rx);
    free_request(ep_in, tx);
    control = rx = tx = NULL;
    mutex_unlock(&write_lock);
    mutex_unlock(&read_lock);
}
static int bind(struct usb_gadget *g, struct usb_gadget_driver *driver)
{
    gadget = g;
    /* Fail closed even if a vendor UDC implementation misroutes attachment. */
    if (!g->dev.parent || strcmp(dev_name(g->dev.parent), target_udc))
        return -ENODEV;
    ep_in = usb_ep_autoconfig(g, &in_desc);
    ep_out = usb_ep_autoconfig(g, &out_desc);
    if (!ep_in || !ep_out)
        return -ENODEV;
    rx = alloc_request(ep_out, BULK_SIZE);
    tx = alloc_request(ep_in, BULK_SIZE);
    control = alloc_request(g->ep0, CTRL_SIZE);
    if (!rx || !tx || !control) {
        free_request(ep_out, rx);
        free_request(ep_in, tx);
        free_request(g->ep0, control);
        rx = tx = control = NULL;
        return -ENOMEM;
    }
    control->complete = control_complete;
    init_completion(&control_drained);
    device_desc.bMaxPacketSize0 = qualifier.bMaxPacketSize0 = g->ep0->maxpacket;
    bound = true;
    stopping = false;
    return 0;
}
static void disconnect(struct usb_gadget *g) { disable_data(); }
static struct usb_gadget_driver driver = {
    .function = "yamaha_aoa",
    .max_speed = USB_SPEED_HIGH,
    .bind = bind,
    .unbind = unbind,
    .setup = setup,
    .disconnect = disconnect,
    .driver = {.name = "yamaha_aoa", .owner = THIS_MODULE},
};
static int __init aoa_init(void)
{
    int result;
    if (!experimental)
        return -EPERM;
    /* NXP 3.14 exports this API; never fall back to the first available UDC. */
    result = udc_attach_driver(target_udc, &driver);
    if (result)
        return result;
    result = misc_register(&misc);
    if (result) {
        usb_gadget_unregister_driver(&driver);
        return result;
    }
    result = device_create_file(misc.this_device, &dev_attr_state);
    if (result) {
        misc_deregister(&misc);
        usb_gadget_unregister_driver(&driver);
    }
    return result;
}
static void __exit aoa_exit(void)
{
    device_remove_file(misc.this_device, &dev_attr_state);
    misc_deregister(&misc);
    stopping = true;
    cancel_delayed_work_sync(&mode_work);
    usb_gadget_unregister_driver(&driver);
}
module_init(aoa_init);
module_exit(aoa_exit);
MODULE_LICENSE("GPL v2");
MODULE_DESCRIPTION("Independent experimental AOA 1.0 USB byte transport");
