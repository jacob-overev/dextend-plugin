/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Replay the two USB control requests observed in the stock ARMadb-driver.
 * No configuration or flash writes. Run only against the connected iPhone.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/usbdevice_fs.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    unsigned char support[4] = {0};
    if (argc < 2 || argc > 3 || (argc == 3 && strcmp(argv[2], "--switch"))) {
        fprintf(stderr, "Usage: %s /dev/bus/usb/BBB/DDD [--switch]\n", argv[0]);
        return 2;
    }
    int fd = open(argv[1], O_RDWR);
    if (fd < 0) {
        perror("open USB");
        return 1;
    }
    struct usbdevfs_ctrltransfer c = {.bRequestType = 0xc0,
                                      .bRequest = 0x53,
                                      .wValue = 0,
                                      .wIndex = 0,
                                      .wLength = sizeof(support),
                                      .timeout = 2000,
                                      .data = support};
    int n = ioctl(fd, USBDEVFS_CONTROL, &c);
    printf("GET_SUPPORT c0.53: result=%d errno=%d bytes=%02x %02x %02x %02x\n", n,
           n < 0 ? errno : 0, support[0], support[1], support[2], support[3]);
    if (n < 1 || support[0] != 1) {
        close(fd);
        return 1;
    }
    if (argc == 3) {
        int control =
            open("/sys/bus/platform/devices/ci_hdrc.0/inputs/a_suspend_req_inf", O_WRONLY);
        if (control < 0) {
            perror("arm OTG suspend");
            close(fd);
            return 1;
        }
        if (write(control, "1\n", 2) != 2) {
            perror("arm OTG suspend");
            close(control);
            close(fd);
            return 1;
        }
        close(control);
        puts("OTG suspend request armed on phone-side controller");
        c.bRequestType = 0x40;
        c.bRequest = 0x51;
        c.wValue = 1;
        c.wLength = 0;
        c.data = NULL;
        n = ioctl(fd, USBDEVFS_CONTROL, &c);
        printf("ROLE_SWITCH 40.51 value=1: result=%d errno=%d\n", n, n < 0 ? errno : 0);
    }
    close(fd);
    return n < 0;
}
