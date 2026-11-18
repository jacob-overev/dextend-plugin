/* SPDX-License-Identifier: GPL-2.0-only
 * Deterministic userspace USB/OS substitute. No hardware or timing emulation.
 */
/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <sys/types.h>
#include <poll.h>
#include <linux/usb/ch9.h>
typedef uint8_t u8;
/* glibc and musl differ in whether they expose this kernel-only typedef. */
typedef int64_t test_loff_t;
#define loff_t test_loff_t
#define __user
#define __init
#define __exit
#define __packed __attribute__((packed))
#define THIS_MODULE NULL
#define GFP_KERNEL 0
#define GFP_ATOMIC 0
#define ERESTARTSYS 512
#define MISC_DYNAMIC_MINOR 255
#define min_t(t, a, b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define cpu_to_le16(v) (v)
#define le16_to_cpu(v) (v)
#define module_param(...)
#define MODULE_PARM_DESC(...)
#define MODULE_LICENSE(...)
#define MODULE_DESCRIPTION(...)
#define module_init(...)
#define module_exit(...)
#define DEFINE_SPINLOCK(n) int n
#define DEFINE_MUTEX(n) int n
#define DECLARE_WAIT_QUEUE_HEAD(n) int n
#define spin_lock_irqsave(l, f)                                                                    \
    do {                                                                                           \
        (void)(l);                                                                                 \
        (f) = 0;                                                                                   \
    } while (0)
#define spin_unlock_irqrestore(l, f)                                                               \
    do {                                                                                           \
        (void)(l);                                                                                 \
        (void)(f);                                                                                 \
    } while (0)
#define mutex_lock(l) ((void)(l))
#define mutex_lock_interruptible(l) ((void)(l), 0)
#define mutex_unlock(l) ((void)(l))
#define wake_up_interruptible(l) ((void)(l))
#define no_llseek NULL
typedef int atomic_t;
#define ATOMIC_INIT(n) (n)
static int atomic_cmpxchg(int *p, int old, int value)
{
    int x = *p;
    if (x == old)
        *p = value;
    return x;
}
static void atomic_set(int *p, int value) { *p = value; }
struct inode {
    int unused;
};
struct file {
    int unused;
};
typedef int poll_table;
static void poll_wait(struct file *f, void *q, poll_table *p)
{
    (void)f;
    (void)q;
    (void)p;
}
struct file_operations {
    void *owner;
    int (*open)(struct inode *, struct file *);
    int (*release)(struct inode *, struct file *);
    ssize_t (*read)(struct file *, char *, size_t, loff_t *);
    ssize_t (*write)(struct file *, const char *, size_t, loff_t *);
    unsigned (*poll)(struct file *, poll_table *);
    void *llseek;
};
struct device_attribute {
    int unused;
};
#define DEVICE_ATTR(name, mode, show, store) int dev_attr_##name
static int device_create_file(void *dev, void *attr)
{
    (void)dev;
    (void)attr;
    return 0;
}
static void device_remove_file(void *dev, void *attr)
{
    (void)dev;
    (void)attr;
}
struct miscdevice {
    int minor;
    const char *name;
    const struct file_operations *fops;
    int mode;
    void *this_device;
};
static int misc_register(struct miscdevice *m)
{
    (void)m;
    return 0;
}
static void misc_deregister(struct miscdevice *m) { (void)m; }
static void *kmalloc(size_t n, int flags)
{
    (void)flags;
    return malloc(n);
}
#define kfree free
static bool copy_failure;
static void (*copy_hook)(void);
static unsigned copy_to_user(void *dst, const void *src, size_t n)
{
    if (copy_failure)
        return n;
    memcpy(dst, src, n);
    if (copy_hook) {
        void (*hook)(void) = copy_hook;
        copy_hook = NULL;
        hook();
    }
    return 0;
}
#define copy_from_user copy_to_user
struct work_struct {
    int unused;
};
struct delayed_work {
    void (*fn)(struct work_struct *);
    bool scheduled;
};
#define DECLARE_DELAYED_WORK(n, f) struct delayed_work n = {.fn = f}
static void schedule_delayed_work(struct delayed_work *w, unsigned delay)
{
    (void)delay;
    w->scheduled = true;
}
static void cancel_delayed_work_sync(struct delayed_work *w) { w->scheduled = false; }
#define msecs_to_jiffies(n) (n)
static void msleep(unsigned ms) { (void)ms; }
struct completion {
    bool done;
};
static void init_completion(struct completion *c) { c->done = false; }
static void reinit_completion(struct completion *c) { c->done = false; }
static void complete(struct completion *c) { c->done = true; }
static void wait_for_completion(struct completion *c) { assert(c->done); }
struct device {
    const char *name;
    struct device *parent;
};
static const char *dev_name(struct device *d) { return d->name; }
struct usb_ep;
struct usb_request {
    void *buf;
    unsigned length, actual, zero;
    int status;
    void (*complete)(struct usb_ep *, struct usb_request *);
};
struct usb_ep {
    struct usb_endpoint_descriptor *desc;
    unsigned maxpacket;
    struct usb_request *queued;
    bool enabled;
};
struct usb_gadget {
    struct usb_ep *ep0;
    struct device dev;
    enum usb_device_speed speed;
    bool connected;
};
struct device_driver {
    const char *name;
    void *owner;
};
struct usb_gadget_driver {
    const char *function;
    enum usb_device_speed max_speed;
    int (*bind)(struct usb_gadget *, struct usb_gadget_driver *);
    void (*unbind)(struct usb_gadget *);
    int (*setup)(struct usb_gadget *, const struct usb_ctrlrequest *);
    void (*disconnect)(struct usb_gadget *);
    struct device_driver driver;
};
static struct usb_ep fake_in, fake_out, fake_ep0 = {.maxpacket = 64, .enabled = true};
static struct device fake_parent = {.name = "ci_hdrc.1"};
static struct usb_gadget fake_gadget = {
    .ep0 = &fake_ep0, .dev = {.parent = &fake_parent}, .speed = USB_SPEED_HIGH};
static struct usb_gadget_driver *registered_driver;
static bool queue_failure, enable_failure;
static void finish_request(struct usb_ep *ep, int status, const void *data, unsigned count)
{
    struct usb_request *r = ep->queued;
    assert(r);
    assert(count <= r->length);
    ep->queued = NULL;
    if (data)
        memcpy(r->buf, data, count);
    r->actual = count;
    r->status = status;
    r->complete(ep, r);
}
static struct usb_request *usb_ep_alloc_request(struct usb_ep *e, int flags)
{
    (void)e;
    (void)flags;
    return calloc(1, sizeof(struct usb_request));
}
static void usb_ep_free_request(struct usb_ep *e, struct usb_request *r)
{
    assert(e->queued != r);
    free(r);
}
static int usb_ep_queue(struct usb_ep *e, struct usb_request *r, int flags)
{
    (void)flags;
    if (queue_failure)
        return -EIO;
    if (!e->enabled)
        return -ESHUTDOWN;
    assert(!e->queued);
    e->queued = r;
    return 0;
}
static int usb_ep_enable(struct usb_ep *e)
{
    if (enable_failure && e == &fake_out)
        return -EIO;
    e->enabled = true;
    return 0;
}
static int usb_ep_dequeue(struct usb_ep *e, struct usb_request *r)
{
    if (e->queued != r)
        return -EINVAL;
    finish_request(e, -ECONNRESET, NULL, 0);
    return 0;
}
static void usb_ep_disable(struct usb_ep *e)
{
    e->enabled = false;
    if (e->queued)
        finish_request(e, -ESHUTDOWN, NULL, 0);
}
static int usb_ep_set_halt(struct usb_ep *e) { return e->queued ? -EAGAIN : 0; }
static int usb_ep_clear_halt(struct usb_ep *e)
{
    (void)e;
    return 0;
}
static struct usb_ep *usb_ep_autoconfig(struct usb_gadget *g, struct usb_endpoint_descriptor *d)
{
    (void)g;
    if (d->bEndpointAddress & USB_DIR_IN) {
        d->bEndpointAddress = 0x81;
        return &fake_in;
    }
    d->bEndpointAddress = 2;
    return &fake_out;
}
static int udc_attach_driver(const char *name, struct usb_gadget_driver *d)
{
    int r;
    assert(!strcmp(name, "ci_hdrc.1"));
    r = d->bind(&fake_gadget, d);
    if (!r)
        registered_driver = d;
    return r;
}
static int usb_gadget_disconnect(struct usb_gadget *g)
{
    g->connected = false;
    registered_driver->disconnect(g);
    return 0;
}
static int usb_gadget_connect(struct usb_gadget *g)
{
    g->connected = true;
    return 0;
}
static void usb_gadget_unregister_driver(struct usb_gadget_driver *d)
{
    d->unbind(&fake_gadget);
    registered_driver = NULL;
}
