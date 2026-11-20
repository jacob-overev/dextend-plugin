/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Minimal no-argument call verified in factory ARMadb at 0x37e30.
 * Explicit Hello and reply serial checks; no guessed pairing payloads. */
#define _POSIX_C_SOURCE 200809L
#include <sys/socket.h>
#include <sys/un.h>
#include <poll.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
static const unsigned char hello[] = {
    108, 1,   0,   1,   0,   0,   0,   0,   1,   0,   0,   0,   109, 0,   0,   0,   1,   1,   111,
    0,   21,  0,   0,   0,   47,  111, 114, 103, 47,  102, 114, 101, 101, 100, 101, 115, 107, 116,
    111, 112, 47,  68,  66,  117, 115, 0,   0,   0,   2,   1,   115, 0,   20,  0,   0,   0,   111,
    114, 103, 46,  102, 114, 101, 101, 100, 101, 115, 107, 116, 111, 112, 46,  68,  66,  117, 115,
    0,   0,   0,   0,   3,   1,   115, 0,   5,   0,   0,   0,   72,  101, 108, 108, 111, 0,   0,
    0,   6,   1,   115, 0,   20,  0,   0,   0,   111, 114, 103, 46,  102, 114, 101, 101, 100, 101,
    115, 107, 116, 111, 112, 46,  68,  66,  117, 115, 0,   0,   0,   0};
static const unsigned char autoconnect[] = {
    108, 1,   0,   1,   0,   0,   0,   0,   2,   0,   0,   0,   115, 0,   0,   0,   1,
    1,   111, 0,   23,  0,   0,   0,   47,  82,  105, 100, 100, 108, 101, 66,  108, 117,
    101, 116, 111, 111, 116, 104, 83,  101, 114, 118, 105, 99,  101, 0,   2,   1,   115,
    0,   27,  0,   0,   0,   111, 114, 103, 46,  114, 105, 100, 100, 108, 101, 46,  66,
    108, 117, 101, 116, 111, 111, 116, 104, 67,  111, 110, 116, 114, 111, 108, 0,   0,
    0,   0,   0,   3,   1,   115, 0,   11,  0,   0,   0,   65,  117, 116, 111, 67,  111,
    110, 110, 101, 99,  116, 0,   0,   0,   0,   0,   6,   1,   115, 0,   10,  0,   0,
    0,   111, 114, 103, 46,  114, 105, 100, 100, 108, 101, 0,   0,   0,   0,   0,   0};

static unsigned le(const unsigned char *p)
{
    return p[0] | (unsigned)p[1] << 8 | (unsigned)p[2] << 16 | (unsigned)p[3] << 24;
}
static int all(int fd, void *p, size_t n, int writing)
{
    unsigned char *b = p;
    while (n) {
        struct pollfd poller = {fd, writing ? POLLOUT : POLLIN, 0};
        if (poll(&poller, 1, 5000) <= 0)
            return -1;
        ssize_t r = writing ? send(fd, b, n, MSG_NOSIGNAL) : read(fd, b, n);
        if (r < 0 && errno == EINTR)
            continue;
        if (r <= 0)
            return -1;
        b += r;
        n -= (size_t)r;
    }
    return 0;
}
static int reply(int fd, unsigned serial)
{
    for (unsigned count = 0; count < 16; count++) {
        unsigned char h[16], data[8192];
        if (all(fd, h, 16, 0))
            return -1;
        if (h[0] != 'l' || h[3] != 1)
            return -1;
        unsigned body = le(h + 4), fields = le(h + 12), aligned = (fields + 7) & ~7U;
        if (aligned > sizeof(data) || body > sizeof(data) - aligned ||
            all(fd, data, aligned + body, 0))
            return -1;
        unsigned answer = 0;
        for (unsigned p = 0; p < fields;) {
            p = (p + 7) & ~7U;
            if (p + 4 > fields)
                break;
            unsigned tag = data[p], len = data[p + 1];
            if (len != 1 || data[p + 3])
                return -1;
            unsigned type = data[p + 2];
            p += 4;
            if (type == 'u') {
                p = (p + 3) & ~3U;
                if (p + 4 > fields)
                    return -1;
                if (tag == 5)
                    answer = le(data + p);
                p += 4;
            } else if (type == 's' || type == 'o') {
                p = (p + 3) & ~3U;
                if (p + 4 > fields)
                    return -1;
                unsigned n = le(data + p);
                p += 4;
                if (n >= fields - p)
                    return -1;
                p += n + 1;
            } else if (type == 'g') {
                if (p >= fields)
                    return -1;
                unsigned n = data[p++];
                if (n >= fields - p)
                    return -1;
                p += n + 1;
            } else
                return -1;
        }
        if (answer == serial)
            return h[1] == 3 ? 1 : (h[1] == 2 ? 0 : -1);
    }
    return -1;
}
static void put32(unsigned char *p, unsigned n)
{
    for (unsigned i = 0; i < 4; i++)
        p[i] = (unsigned char)(n >> (8 * i));
}
static size_t field(unsigned char *p, size_t n, unsigned tag, char type, const char *s)
{
    while (n % 8)
        p[n++] = 0;
    p[n++] = (unsigned char)tag;
    p[n++] = 1;
    p[n++] = (unsigned char)type;
    p[n++] = 0;
    size_t len = strlen(s);
    put32(p + n, (unsigned)len);
    n += 4;
    memcpy(p + n, s, len + 1);
    return n + len + 1;
}
/* OEM OnDbusMessage 0x1b2d0: Listen(); 0x1b30a: Connect(string address,
 * string service). Limit this client to the two projection services. */
static size_t request(unsigned char *p, const char *method, const char *peer, const char *service)
{
    memset(p, 0, 512);
    p[0] = 'l';
    p[1] = 1;
    p[3] = 1;
    put32(p + 8, 2);
    size_t n = 16;
    n = field(p, n, 1, 'o', "/RiddleBluetoothService");
    n = field(p, n, 2, 's', "org.riddle.BluetoothControl");
    n = field(p, n, 3, 's', method);
    n = field(p, n, 6, 's', "org.riddle");
    if (peer) {
        while (n % 8)
            p[n++] = 0;
        p[n++] = 8;
        p[n++] = 1;
        p[n++] = 'g';
        p[n++] = 0;
        p[n++] = service ? 2 : 1;
        p[n++] = 's';
        if (service)
            p[n++] = 's';
        p[n++] = 0;
    }
    put32(p + 12, (unsigned)n - 16);
    while (n % 8)
        p[n++] = 0;
    size_t start = n;
    if (peer) {
        const char *args[] = {peer, service};
        for (unsigned i = 0; i < (service ? 2U : 1U); i++) {
            while (n % 4)
                p[n++] = 0;
            size_t len = strlen(args[i]);
            put32(p + n, (unsigned)len);
            n += 4;
            memcpy(p + n, args[i], len + 1);
            n += len + 1;
        }
    }
    put32(p + 4, (unsigned)(n - start));
    return n;
}
int main(int argc, char **argv)
{
    unsigned char message[512];
    const unsigned char *call = autoconnect;
    size_t call_size = sizeof(autoconnect);
    const char *label = "AUTOCONNECT";
    if (argc == 2 && !strcmp(argv[1], "--listen")) {
        call_size = request(message, "Listen", NULL, NULL);
        call = message;
        label = "LISTEN";
    } else if (argc == 3 && !strcmp(argv[1], "--forget")) {
        /* OEM 0x1b4ec accepts ForgetBluetoothAddr(string); 0x18aa4 resolves
  * the device and invokes BlueZ RemoveDevice. Never edit linkkeys ourselves. */
        if (strlen(argv[2]) != 17)
            return 2;
        for (unsigned i = 0; i < 17; i++)
            if (i % 3 == 2 ? argv[2][i] != ':' : !strchr("0123456789abcdefABCDEF", argv[2][i]))
                return 2;
        call_size = request(message, "ForgetBluetoothAddr", argv[2], NULL);
        call = message;
        label = "FORGET";
    } else if (argc == 4 && !strcmp(argv[1], "--connect")) {
        int discover_profile = !strcmp(argv[3], "AUTO");
        if (strlen(argv[2]) != 17 ||
            (!discover_profile && strcmp(argv[3], "IAP2") && strcmp(argv[3], "AAP")))
            return 2;
        for (unsigned i = 0; i < 17; i++)
            if (i % 3 == 2 ? argv[2][i] != ':' : !strchr("0123456789abcdefABCDEF", argv[2][i]))
                return 2;
        /* An empty second D-Bus string selects OEM service discovery for
         * this address. Omitting it would change the method signature. */
        call_size = request(message, "Connect", argv[2], discover_profile ? "" : argv[3]);
        call = message;
        label = "CONNECT";
    } else if (argc != 1)
        return 2;
    const char *path = getenv("YAMAHA_DBUS_SOCKET");
    if (!path)
        path = "/var/run/dbus/system_bus_socket";
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof(addr.sun_path))
        return 2;
    strcpy(addr.sun_path, path);
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0 || connect(fd, (void *)&addr, sizeof(addr)))
        return 2;
    char auth[96];
    unsigned char uid[32];
    int n = snprintf((char *)uid, sizeof(uid), "%u", (unsigned)getuid());
    unsigned p = 0;
    auth[p++] = 0;
    memcpy(auth + p, "AUTH EXTERNAL ", 14);
    p += 14;
    for (int i = 0; i < n; i++) {
        auth[p++] = "0123456789abcdef"[uid[i] >> 4];
        auth[p++] = "0123456789abcdef"[uid[i] & 15];
    }
    auth[p++] = '\r';
    auth[p++] = '\n';
    if (all(fd, auth, p, 1))
        return 3;
    char line[256];
    p = 0;
    do {
        if (p == sizeof(line) || all(fd, line + p, 1, 0))
            return 3;
    } while (line[p++] != '\n');
    if (p < 3 || memcmp(line, "OK ", 3) || all(fd, "BEGIN\r\n", 7, 1))
        return 3;
    if (all(fd, (void *)hello, sizeof(hello), 1) || reply(fd, 1))
        return 4;
    /* After sending Connect the phone can still answer even if we lose
     * the local reply. Reserve code 5 for an explicit D-Bus method error. */
    if (all(fd, (void *)call, call_size, 1))
        return 6;
    int result = reply(fd, 2);
    if (result)
        return result > 0 ? 5 : 6;
    close(fd);
    printf("STAGE BLUETOOTH_%s accepted=1; connection_not_yet_confirmed\n", label);
    return 0;
}
