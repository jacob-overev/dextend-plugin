/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Bounded local HTTP transport; installation runs separately. */
#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>
#include "third-party/monocypher/monocypher-ed25519.h"
#ifndef UPDATE_KEY_HEADER
#define UPDATE_KEY_HEADER "update-key.h"
#endif
#include UPDATE_KEY_HEADER
static int unhex(unsigned char *out, const char *in, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        int a = (unsigned char)in[i * 2], b = (unsigned char)in[i * 2 + 1];
        if (!isxdigit(a) || !isxdigit(b))
            return -1;
        out[i] = (unsigned char)((isdigit(a) ? a - '0' : tolower(a) - 'a' + 10) * 16 +
                                 (isdigit(b) ? b - '0' : tolower(b) - 'a' + 10));
    }
    return 0;
}
static int verify(const char *path)
{
    unsigned char data[512], sig[64];
    FILE *f = fopen(path, "rb");
    if (!f)
        return 1;
    size_t n = fread(data, 1, sizeof(data), f);
    fclose(f);
    if (n < 130 || n == sizeof(data) || data[n - 1] != '\n')
        return 1;
    size_t len = n - 129;
    if (!len || data[len - 1] != '\n' || unhex(sig, (char *)data + len, 64))
        return 1;
    return crypto_ed25519_check(sig, update_key, data, len) != 0;
}
static int local_ip(const char *ip)
{
    struct in_addr a;
    if (inet_pton(AF_INET, ip, &a) != 1)
        return 0;
    unsigned long v = ntohl(a.s_addr);
    return (v >> 24) == 10 || (v >> 20) == 0xac1 || (v >> 16) == 0xc0a8 || (v >> 16) == 0xa9fe ||
           (v >> 24) == 127;
}
static void bad(int fd)
{
    const char *s = "HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n";
    ssize_t ignored = write(fd, s, strlen(s));
    (void)ignored;
}
static void serve(int fd, const char *script)
{
    char headers[8192], method[12], path[160], proto[16], host[128] = "", origin[256] = "",
                                                          token[80] = "", length[16] = "0";
    size_t n = 0;
    int seen_length = 0;
    alarm(25);
    struct timeval timeout = {.tv_sec = 10, .tv_usec = 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    while (n < sizeof(headers) - 1) {
        if (read(fd, headers + n, 1) != 1)
            return;
        n++;
        if (n >= 4 && !memcmp(headers + n - 4, "\r\n\r\n", 4))
            break;
    }
    headers[n] = 0;
    if (n == sizeof(headers) - 1 || sscanf(headers, "%11s %159s %15s", method, path, proto) != 3 ||
        (strcmp(proto, "HTTP/1.1") && strcmp(proto, "HTTP/1.0")) || strstr(path, "..") ||
        strchr(path, '%')) {
        bad(fd);
        return;
    }
    char *save = NULL, *line = strtok_r(headers, "\r\n", &save);
    while ((line = strtok_r(NULL, "\r\n", &save))) {
        char *colon = strchr(line, ':');
        if (!colon) {
            bad(fd);
            return;
        }
        *colon++ = 0;
        while (*colon == ' ' || *colon == '\t')
            colon++;
        for (char *p = line; *p; p++)
            *p = (char)tolower((unsigned char)*p);
        char *dest = NULL;
        size_t cap = 0;
        if (!strcmp(line, "host")) {
            dest = host;
            cap = sizeof(host);
        }
        if (!strcmp(line, "origin")) {
            dest = origin;
            cap = sizeof(origin);
        }
        if (!strcmp(line, "x-dextend-token")) {
            dest = token;
            cap = sizeof(token);
        }
        if (!strcmp(line, "content-length")) {
            if (seen_length++) {
                bad(fd);
                return;
            }
            if (!*colon || strspn(colon, "0123456789") != strlen(colon) || strlen(colon) > 6 ||
                strtoul(colon, NULL, 10) > 65536) {
                bad(fd);
                return;
            }
            strcpy(length, colon);
        }
        if (!strcmp(line, "transfer-encoding") || !strcmp(line, "expect")) {
            bad(fd);
            return;
        }
        if (dest) {
            if (*dest || strlen(colon) >= cap) {
                bad(fd);
                return;
            }
            strcpy(dest, colon);
        }
    }
    char address[128];
    strcpy(address, host);
    char *port = strchr(address, ':');
    if (port)
        *port = 0;
    if (!local_ip(address) && strcmp(address, "autobox.com") &&
        strcmp(address, "www.autobox.com")) {
        bad(fd);
        return;
    }
    if (strcmp(method, "GET") && strcmp(method, "POST") && strcmp(method, "OPTIONS")) {
        bad(fd);
        return;
    }
    if ((!strcmp(method, "POST") && !seen_length) || strpbrk(path, "\r\n ")) {
        bad(fd);
        return;
    }
    clearerr(stdout);
    setenv("REQUEST_METHOD", method, 1);
    setenv("REQUEST_URI", path, 1);
    setenv("HTTP_HOST", host, 1);
    setenv("HTTP_ORIGIN", origin, 1);
    setenv("HTTP_X_DEXTEND_TOKEN", token, 1);
    setenv("CONTENT_LENGTH", length, 1);
    FILE *input = tmpfile();
    if (!input) {
        bad(fd);
        return;
    }
    size_t remaining = (size_t)strtoul(length, NULL, 10);
    char body[8192];
    while (remaining) {
        size_t amount = remaining < sizeof(body) ? remaining : sizeof(body);
        ssize_t got = read(fd, body, amount);
        if (got <= 0 || fwrite(body, 1, (size_t)got, input) != (size_t)got) {
            fclose(input);
            bad(fd);
            return;
        }
        remaining -= (size_t)got;
    }
    rewind(input);
    dup2(fileno(input), 0);
    dup2(fd, 1);
    fclose(input);
    close(fd);
    execl("/bin/sh", "sh", script, (char *)NULL);
}
int main(int argc, char **argv)
{
    if (argc == 3 && !strcmp(argv[1], "--verify"))
        return verify(argv[2]);
    if (argc != 3)
        return 2;
    char *end;
    long port = strtol(argv[1], &end, 10);
    if (*end || port < 1024 || port > 65535)
        return 2;
    int s = socket(AF_INET, SOCK_STREAM, 0), one = 1;
    if (s < 0)
        return 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    struct sockaddr_in a = {.sin_family = AF_INET,
                            .sin_port = htons((unsigned short)port),
                            .sin_addr = {.s_addr = INADDR_ANY}};
    if (bind(s, (void *)&a, sizeof(a)) || listen(s, 8))
        return 1;
    signal(SIGPIPE, SIG_IGN);
    int children = 0;
    for (;;) {
        while (waitpid(-1, NULL, WNOHANG) > 0)
            children--;
        struct sockaddr_in peer;
        socklen_t size = sizeof(peer);
        int fd = accept(s, (void *)&peer, &size);
        if (fd < 0) {
            if (errno == EINTR)
                continue;
            return 1;
        }
        char ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &peer.sin_addr, ip, sizeof(ip));
        if (children >= 8 || !local_ip(ip)) {
            close(fd);
            continue;
        }
        pid_t pid = fork();
        if (pid == 0) {
            close(s);
            serve(fd, argv[2]);
            close(fd);
            _exit(0);
        }
        if (pid > 0)
            children++;
        close(fd);
    }
}
