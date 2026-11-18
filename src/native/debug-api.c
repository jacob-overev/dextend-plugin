/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

#define _GNU_SOURCE
/* Restored from the existing Dextend debug panel backend. */
/* Dextend USB debug Wi-Fi CGI and supervisor helper. No shell, PSKs in argv or logs.
 * Only the qualified TP-Link AR9271 USB device and its own interface may be controlled. */
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <fcntl.h>
#include <glob.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <arpa/inet.h>
#ifndef ROOT
#define ROOT "/tmp/dextend-service"
#endif
#ifndef STORE
#define STORE "/etc/yamaha-sdl/service"
#endif
#ifndef SYS
#define SYS "/sys"
#endif
static char reply[65536], device[PATH_MAX], netif[IFNAMSIZ];
static int sock = -1;
static char local[108];
static void cleanup(void)
{
    if (sock >= 0)
        close(sock);
    if (*local)
        unlink(local);
}
static int read_text(const char *path, char *value, size_t n)
{
    FILE *f = fopen(path, "r");
    if (!f)
        return -1;
    int ok = fgets(value, (int)n, f) != NULL;
    fclose(f);
    if (!ok)
        return -1;
    value[strcspn(value, "\r\n")] = 0;
    return 0;
}
static int present(void)
{
    glob_t matches = {0};
    char path[PATH_MAX], vendor[32], product[32];
    if (glob(SYS "/bus/usb/devices/*/idVendor", 0, NULL, &matches))
        return 0;
    int found = 0;
    for (size_t i = 0; i < matches.gl_pathc; ++i) {
        if (read_text(matches.gl_pathv[i], vendor, sizeof vendor) || strcmp(vendor, "0cf3"))
            continue;
        snprintf(path, sizeof path, "%s", matches.gl_pathv[i]);
        char *end = strrchr(path, '/');
        if (!end)
            continue;
        *end = 0;
        if (strlen(path) + 11 >= sizeof path)
            continue;
        char id[PATH_MAX];
        snprintf(id, sizeof id, "%.*s/idProduct", PATH_MAX - 11, path);
        if (!read_text(id, product, sizeof product) && !strcmp(product, "1006")) {
            if (realpath(path, device)) {
                found = 1;
                break;
            }
        }
    }
    globfree(&matches);
    return found;
}
static int ready(void)
{
    glob_t interfaces = {0};
    char path[PATH_MAX], driver[PATH_MAX];
    netif[0] = 0;
    if (!*device || glob(SYS "/class/net/*/device", 0, NULL, &interfaces))
        return 0;
    for (size_t i = 0; i < interfaces.gl_pathc; i++) {
        if (!realpath(interfaces.gl_pathv[i], path))
            continue;
        size_t n = strlen(device);
        if (strncmp(path, device, n) || (path[n] != '/' && path[n] != ':'))
            continue;
        char link[PATH_MAX];
        if (snprintf(link, sizeof link, "%s/driver", interfaces.gl_pathv[i]) >= (int)sizeof link)
            continue;
        if (!realpath(link, driver))
            continue;
        char *leaf = strrchr(driver, '/');
        if (!leaf || strcmp(leaf + 1, "ath9k_htc"))
            continue;
        const char *name = interfaces.gl_pathv[i] + strlen(SYS "/class/net/");
        size_t size = strcspn(name, "/");
        if (!size || size >= sizeof netif)
            continue;
        int safe = 1;
        for (size_t j = 0; j < size; j++)
            if (!isalnum((unsigned char)name[j]) && name[j] != '_' && name[j] != '-' &&
                name[j] != '.')
                safe = 0;
        if (!safe)
            continue;
        if (*netif) {
            netif[0] = 0;
            break;
        } /* Ambiguous adapters: do not select one. */
        memcpy(netif, name, size);
        netif[size] = 0;
    }
    globfree(&interfaces);
    return *netif != 0;
}
static int oem_ready(void)
{
    char path[PATH_MAX];
    if (!realpath(SYS "/class/net/wlan0/device/subsystem", path))
        return 0;
    const char *leaf = strrchr(path, '/');
    return leaf && !strcmp(leaf + 1, "sdio");
}
static int ip_address(char *out, size_t length)
{
    if (!ready())
        return 0;
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0)
        return 0;
    struct ifreq ifr = {0};
    snprintf(ifr.ifr_name, sizeof ifr.ifr_name, "%s", netif);
    int good = !ioctl(fd, SIOCGIFADDR, &ifr);
    close(fd);
    return good && inet_ntop(AF_INET, &((struct sockaddr_in *)&ifr.ifr_addr)->sin_addr, out,
                             length) != NULL;
}
static int request(const char *command)
{
    if (sock < 0) {
        struct sockaddr_un addr = {.sun_family = AF_UNIX};
        sock = socket(AF_UNIX, SOCK_DGRAM, 0);
        if (sock < 0)
            return -1;
        snprintf(local, sizeof local, ROOT "/api-%ld", (long)getpid());
        snprintf(addr.sun_path, sizeof addr.sun_path, "%s", local);
        unlink(local);
        if (bind(sock, (struct sockaddr *)&addr, sizeof addr))
            return -1;
        snprintf(addr.sun_path, sizeof addr.sun_path, ROOT "/ctrl/%s", netif);
        if (connect(sock, (struct sockaddr *)&addr, sizeof addr))
            return -1;
        struct timeval timeout = {.tv_sec = 2};
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
    }
    if (send(sock, command, strlen(command), 0) < 0)
        return -1;
    ssize_t n = recv(sock, reply, sizeof reply - 1, 0);
    if (n < 0 || n == (ssize_t)sizeof reply - 1)
        return -1;
    reply[n] = 0;
    return strncmp(reply, "FAIL", 4) && strncmp(reply, "UNKNOWN", 7) ? 0 : -1;
}
static int ok(const char *command) { return !request(command) && !strcmp(reply, "OK\n"); }
static void json(const char *s)
{
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        if (*p == '"' || *p == '\\') {
            putchar('\\');
            putchar(*p);
        } else if (*p < 32)
            printf("\\u%04x", *p);
        else
            putchar(*p);
    }
    putchar('"');
}
static void header(int status)
{
    printf("Status: %d %s\r\nContent-Type: application/json\r\nCache-Control: "
           "no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n",
           status, status == 200 ? "OK" : "Error");
}
static int error(int status, const char *message)
{
    header(status);
    printf("{\"error\":");
    json(message);
    puts("}");
    return 0;
}
static int copy_file(const char *src, const char *dst)
{
    int in = open(src, O_RDONLY | O_NOFOLLOW);
    if (in < 0)
        return -1;
    int out = open(dst, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW, 0600);
    if (out < 0) {
        close(in);
        return -1;
    }
    fchmod(out, 0600);
    char buffer[4096];
    ssize_t n;
    int result = 0;
    while ((n = read(in, buffer, sizeof buffer)) > 0) {
        ssize_t offset = 0;
        while (offset < n) {
            ssize_t w = write(out, buffer + offset, (size_t)(n - offset));
            if (w <= 0) {
                result = -1;
                break;
            }
            offset += w;
        }
        if (result)
            break;
    }
    if (n < 0 || fsync(out))
        result = -1;
    close(in);
    if (close(out))
        result = -1;
    return result;
}
static int persist(void)
{
    /* Hardware trials keep every setting in RAM, including remembered networks. */
    if (!access(ROOT "/ram-only", F_OK))
        return 0;
    char name[] = STORE "/network.conf.XXXXXX";
    int fd = mkstemp(name);
    if (fd < 0)
        return -1;
    close(fd);
    int result = copy_file(ROOT "/network.conf", name);
    if (!result)
        result = rename(name, STORE "/network.conf");
    unlink(name);
    if (!result) {
        fd = open(STORE, O_RDONLY | O_DIRECTORY);
        if (fd >= 0) {
            fsync(fd);
            close(fd);
        }
    }
    return result;
}
static int hexval(int c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    c = tolower(c);
    return c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}
/* Strict form decoding: no NUL/newline command injection, duplicates or unknown keys. */
static int decode(char *s)
{
    char *out = s;
    for (char *p = s; *p; p++) {
        int c = (unsigned char)*p;
        if (c == '+')
            c = ' ';
        else if (c == '%') {
            if (!p[1] || !p[2])
                return -1;
            int a = hexval(p[1]), b = hexval(p[2]);
            if (a < 0 || b < 0)
                return -1;
            c = a * 16 + b;
            p += 2;
        }
        if (c < 32 || c == 127)
            return -1;
        *out++ = (char)c;
    }
    *out = 0;
    return 0;
}
static int valid_id(const char *s)
{
    if (!*s || strlen(s) > 6)
        return 0;
    for (; *s; s++)
        if (!isdigit((unsigned char)*s))
            return 0;
    return 1;
}
static void hex_string(const char *src, char *dst)
{
    for (const unsigned char *p = (const unsigned char *)src; *p; p++) {
        sprintf(dst, "%02x", *p);
        dst += 2;
    }
    *dst = 0;
}
static const char *env(const char *key)
{
    const char *v = getenv(key);
    return v ? v : "";
}
static int trusted(void)
{
    /* Same-origin custom header + literal server IP prevent CSRF/DNS rebinding.
     * Endpoint is for the local management network, not a public server. */
    if (strcmp(env("HTTP_X_DEXTEND_REQUEST"), "1"))
        return 0;
    char host[256];
    snprintf(host, sizeof host, "%s", env("HTTP_HOST"));
    char *port = strchr(host, ':');
    if (port)
        *port = 0;
    struct in_addr literal;
    if (inet_pton(AF_INET, host, &literal) != 1)
        return 0;
    int local_host = *env("SERVER_ADDR") && !strcmp(host, env("SERVER_ADDR"));
    if (!local_host) {
        /* The panel is served on the factory AP or external debug interface.
         * Fixed SIOCGIFADDR probes avoid a netlink/getifaddrs runtime dependency. */
        int fd = socket(AF_INET, SOCK_DGRAM, 0);
        if (fd >= 0) {
            ready();
            const char *names[] = {"wlan0", netif, "lo"};
            for (size_t i = 0; i < sizeof names / sizeof names[0]; i++) {
                struct ifreq interface = {0};
                snprintf(interface.ifr_name, sizeof interface.ifr_name, "%s", names[i]);
                if (!ioctl(fd, SIOCGIFADDR, &interface) &&
                    ((struct sockaddr_in *)&interface.ifr_addr)->sin_addr.s_addr == literal.s_addr)
                    local_host = 1;
            }
            close(fd);
        }
    }
    if (!local_host)
        return 0;
    if (*env("HTTP_ORIGIN")) {
        char expected[300];
        snprintf(expected, sizeof expected, "http://%s", env("HTTP_HOST"));
        if (strcmp(expected, env("HTTP_ORIGIN")))
            return 0;
    }
    return strcmp(env("HTTP_SEC_FETCH_SITE"), "cross-site") != 0;
}
static void property(const char *name, const char *value)
{
    json(name);
    putchar(':');
    json(value);
}
#ifndef MANAGEMENT_IFACE
#define MANAGEMENT_IFACE "wlan0"
#endif
/* Enabling root access requires a client on the adapter's management Wi-Fi. */
static int management_client(void)
{
    struct ifreq iface = {0};
    struct in_addr peer, host;
    char hostname[256];
    snprintf(hostname, sizeof hostname, "%s", env("HTTP_HOST"));
    hostname[strcspn(hostname, ":")] = 0;
    if (inet_pton(AF_INET, hostname, &host) != 1 ||
        inet_pton(AF_INET, env("REMOTE_ADDR"), &peer) != 1)
        return 0;
    snprintf(iface.ifr_name, sizeof iface.ifr_name, "%s", MANAGEMENT_IFACE);
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0)
        return 0;
    int ok = !ioctl(fd, SIOCGIFADDR, &iface) &&
             ((struct sockaddr_in *)&iface.ifr_addr)->sin_addr.s_addr == host.s_addr &&
             !ioctl(fd, SIOCGIFNETMASK, &iface);
    close(fd);
    unsigned mask = ((struct sockaddr_in *)&iface.ifr_netmask)->sin_addr.s_addr;
    return ok && mask && ((host.s_addr ^ peer.s_addr) & mask) == 0;
}
/* One explicitly selected Ed25519 public key per diagnostic session. */
static int configure_ssh(const char *key)
{
    if (!key || !*key) {
        if (unlink(ROOT "/session-key") && errno != ENOENT)
            return error(500, "SSH: zapis nie powiódł się.");
    } else {
        if (!management_client())
            return error(403, "Połącz się z Wi-Fi adaptera, aby włączyć SSH.");
        const char *prefix = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI";
        size_t n = strcspn(key, " ");
        if (n != 11 || strncmp(key, prefix, strlen(prefix)) ||
            strspn(key + 12, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/") != 68 ||
            (key[80] && key[80] != ' '))
            return error(400, "Wprowadź klucz publiczny Ed25519.");
        char tmp[] = ROOT "/key.XXXXXX";
        int fd = mkstemp(tmp);
        if (fd < 0)
            return error(500, "SSH: zapis nie powiódł się.");
        int ok = write(fd, key, 80) == 80 && write(fd, "\n", 1) == 1;
        if (close(fd) || !ok || link(tmp, ROOT "/session-key")) {
            unlink(tmp);
            return error(409, "Wyłącz SSH przed zmianą klucza.");
        }
        unlink(tmp);
    }
    header(200);
    puts("{\"ok\":true}");
    return 0;
}
static int status(void)
{
    int usable = ready() && !request("STATUS");
    header(200);
    printf("{\"present\":%s,\"ready\":%s,\"volatile\":%s", *device ? "true" : "false",
           usable ? "true" : "false", access(ROOT "/ram-only", F_OK) ? "false" : "true");
    char ssh_key[512];
    int ssh_enabled = !access(ROOT "/session-key", F_OK);
    printf(",\"ssh_enabled\":%s,", ssh_enabled ? "true" : "false");
    property("ssh_key", read_text(ssh_enabled ? ROOT "/session-key" : ROOT "/authorized_keys",
                                  ssh_key, sizeof ssh_key) ? "" : ssh_key);
    char service_state[80], ssh_state[80];
    if (!read_text(ROOT "/status", service_state, sizeof service_state)) {
        putchar(',');
        property("service_status", service_state);
    }
    if (!read_text(ROOT "/ssh-status", ssh_state, sizeof ssh_state)) {
        putchar(',');
        property("ssh_status", ssh_state);
    }
    if (usable) {
        char *save = NULL;
        for (char *line = strtok_r(reply, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
            char *eq = strchr(line, '=');
            if (!eq)
                continue;
            *eq++ = 0;
            if (!strcmp(line, "wpa_state") || !strcmp(line, "ssid") ||
                !strcmp(line, "ip_address")) {
                putchar(',');
                property(line, eq);
            }
        }
    }
    if (ready() && !request("LIST_NETWORKS")) {
        printf(",\"networks\":");
        json(reply);
    }
    if (ready() && !request("SCAN_RESULTS")) {
        printf(",\"scan\":");
        json(reply);
    }
    puts("}");
    return 0;
}
int main(int argc, char **argv)
{
    umask(077);
    atexit(cleanup);
    alarm(15);
    int has_device = present();
    if (argc == 2) {
        if (!strcmp(argv[1], "--oem-ready"))
            return oem_ready() ? 0 : 1;
        if (!strcmp(argv[1], "--device")) {
            if (has_device)
                puts(device);
            return has_device ? 0 : 1;
        }
        if (!strcmp(argv[1], "--ready"))
            return ready() ? 0 : 1;
        if (!strcmp(argv[1], "--iface")) {
            if (!ready())
                return 1;
            puts(netif);
            return 0;
        }
        if (!strcmp(argv[1], "--ip")) {
            char ip[INET_ADDRSTRLEN];
            if (!ip_address(ip, sizeof ip))
                return 1;
            puts(ip);
            return 0;
        }
        if (!strcmp(argv[1], "--state")) {
            if (!ready() || request("STATUS")) {
                puts("UNAVAILABLE");
                return 0;
            }
            char *p = strstr(reply, "wpa_state=");
            if (!p) {
                puts("UNKNOWN");
                return 0;
            }
            p += 10;
            size_t n = strcspn(p, "\n");
            if (!n || n > 32) {
                puts("UNKNOWN");
                return 0;
            }
            for (size_t i = 0; i < n; i++)
                if (p[i] != '_' && (p[i] < 'A' || p[i] > 'Z')) {
                    puts("UNKNOWN");
                    return 0;
                }
            printf("%.*s\n", (int)n, p);
            return 0;
        }
        if (!strcmp(argv[1], "--ping")) {
            if (!ready() || request("PING") || strcmp(reply, "PONG\n") || request("STATUS"))
                return 1;
            return strstr(reply, "wpa_state=INTERFACE_DISABLED\n") ? 1 : 0;
        }
        if (!strcmp(argv[1], "--link")) {
            if (!ready() || request("STATUS") || !strstr(reply, "wpa_state=COMPLETED\n"))
                return 1;
            char *start = strstr(reply, "bssid=");
            if (!start)
                return 1;
            start += 6;
            size_t n = strcspn(start, "\n");
            if (n != 17)
                return 1;
            for (size_t i = 0; i < n; i++)
                if (start[i] != ':' && !isxdigit((unsigned char)start[i]))
                    return 1;
            printf("%.*s\n", (int)n, start);
            return 0;
        }
        if (!strcmp(argv[1], "--reconnect")) {
            if (!ready() || request("STATUS"))
                return 1;
            if (strstr(reply, "wpa_state=COMPLETED\n"))
                return 0;
            return ok("RECONNECT") ? 0 : 1;
        }
        return 2;
    }
    if (!trusted())
        return error(403, "Otwórz panel przez adres IP dongla w tej samej sieci.");
    const char *method = env("REQUEST_METHOD");
    if (!strcmp(method, "GET")) {
        if (!strcmp(env("QUERY_STRING"), "diagnostics=1")) {
            printf("Status: 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nCache-Control: "
                   "no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n");
            fflush(stdout);
            execl("/bin/sh", "sh", ROOT "/diagnostics.sh", "report", (char *)NULL);
            puts("DIAGNOSTICS_UNAVAILABLE");
            return 0;
        }
        return status();
    }
    if (strcmp(method, "POST"))
        return error(405, "Niedozwolona metoda.");
    if (strcmp(env("CONTENT_TYPE"), "application/x-www-form-urlencoded"))
        return error(415, "Niepoprawny format żądania.");
    const char *length = env("CONTENT_LENGTH");
    long size = 0;
    for (const char *p = length; *p; p++) {
        if (!isdigit((unsigned char)*p) || size > 2048)
            return error(400, "Niepoprawne żądanie.");
        size = size * 10 + (*p - '0');
    }
    if (!*length || size <= 0 || size > 2048)
        return error(400, "Niepoprawne żądanie.");
    char body[2049];
    if (fread(body, 1, (size_t)size, stdin) != (size_t)size)
        return error(400, "Niepełne żądanie.");
    body[size] = 0;
    if (strlen(body) != (size_t)size)
        return error(400, "Niepoprawne żądanie.");
    char *key = NULL, *action = NULL, *ssid = NULL, *password = NULL, *id = NULL, *save = NULL;
    for (char *pair = strtok_r(body, "&", &save); pair; pair = strtok_r(NULL, "&", &save)) {
        char *value = strchr(pair, '=');
        if (!value)
            return error(400, "Niepoprawne pole.");
        *value++ = 0;
        if (decode(pair) || decode(value))
            return error(400, "Niepoprawne znaki.");
        char **target = !strcmp(pair, "action")     ? &action
                        : !strcmp(pair, "key")      ? &key
                        : !strcmp(pair, "ssid")     ? &ssid
                        : !strcmp(pair, "password") ? &password
                        : !strcmp(pair, "id")       ? &id
                                                    : NULL;
        if (!target || *target)
            return error(400, "Niepoprawne pole.");
        *target = value;
    }
    if (!action)
        return error(400, "Brak operacji.");
    int lock = open(ROOT "/config.lock", O_CREAT | O_RDWR | O_NOFOLLOW, 0600);
    if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB))
        return error(409, "Inna operacja jest w toku.");
    if (!strcmp(action, "ssh-off"))
        return configure_ssh(NULL);
    if (!has_device || !ready())
        return error(409, "Karta debug nie jest gotowa.");
    if (!strcmp(action, "ssh-on"))
        return key && *key ? configure_ssh(key) : error(400, "Wprowadź klucz publiczny Ed25519.");
    if (!strcmp(action, "scan")) {
        if (!ok("SCAN"))
            return error(503, "Nie można rozpocząć skanowania.");
        header(200);
        puts("{\"ok\":true}");
        return 0;
    }
    if (!strcmp(action, "reconnect")) {
        if (!ok("RECONNECT"))
            return error(503, "Nie można ponowić połączenia.");
        header(200);
        puts("{\"ok\":true}");
        return 0;
    }
    if (!strcmp(action, "connect")) {
        if (!id || !valid_id(id))
            return error(400, "Niepoprawny identyfikator sieci.");
        char command[64];
        snprintf(command, sizeof command, "SELECT_NETWORK %s", id);
        int selected = ok(command);
        /* Always restore eligibility, even if selecting a removed/stale ID fails. */
        int enabled = ok("ENABLE_NETWORK all");
        if (!selected || !enabled)
            return error(503, "Nie można wybrać sieci.");
        header(200);
        puts("{\"ok\":true}");
        return 0;
    }
    int adding = !strcmp(action, "remember"), removing = !strcmp(action, "forget");
    if (!adding && !removing)
        return error(400, "Nieznana operacja.");
    if (adding && (!ssid || !*ssid || strlen(ssid) > 32 || !password || strlen(password) < 8 ||
                   strlen(password) > 63))
        return error(400, "Wymagane SSID do 32 bajtów i hasło WPA2 od 8 do 63 znaków.");
    if (removing && (!id || !valid_id(id)))
        return error(400, "Niepoprawny identyfikator sieci.");
    if (adding) {
        if (request("LIST_NETWORKS"))
            return error(503, "Nie można odczytać zapamiętanych sieci.");
        int count = 0;
        for (const char *p = reply; *p; p++)
            if (*p == '\n')
                count++;
        if (count > 16)
            return error(409, "Limit 16 sieci. Usuń nieużywany profil przed dodaniem kolejnego.");
    }
    if (copy_file(ROOT "/network.conf", ROOT "/network.rollback"))
        return error(500, "Nie można przygotować zapisu.");
    char command[512];
    int success = 0;
    if (adding) {
        /* Create disabled; do not disturb existing networks until all fields validate. */
        if (!request("ADD_NETWORK")) {
            reply[strcspn(reply, "\n")] = 0;
            if (valid_id(reply)) {
                char netid[16], hex[65];
                snprintf(netid, sizeof netid, "%.6s", reply);
                hex_string(ssid, hex);
                snprintf(command, sizeof command, "SET_NETWORK %s ssid %s", netid, hex);
                if (ok(command)) {
                    char quoted[130], *q = quoted;
                    *q++ = '"';
                    for (const char *p = password; *p; p++)
                        *q++ = *p;
                    *q++ = '"';
                    *q = 0;
                    snprintf(command, sizeof command, "SET_NETWORK %s psk %s", netid, quoted);
                    if (ok(command)) {
                        snprintf(command, sizeof command, "SET_NETWORK %s key_mgmt WPA-PSK", netid);
                        if (ok(command)) {
                            snprintf(command, sizeof command, "ENABLE_NETWORK %s", netid);
                            success = ok(command);
                            if (success) {
                                snprintf(command, sizeof command, "SELECT_NETWORK %s", netid);
                                success = ok(command);
                            }
                            if (!ok("ENABLE_NETWORK all"))
                                success = 0;
                        }
                    }
                    memset(quoted, 0, sizeof quoted);
                }
            }
        }
    } else {
        snprintf(command, sizeof command, "REMOVE_NETWORK %s", id);
        success = ok(command);
    }
    memset(body, 0, sizeof body);
    memset(command, 0, sizeof command);
    if (!success || !ok("SAVE_CONFIG") || persist()) {
        copy_file(ROOT "/network.rollback", ROOT "/network.conf");
        ok("RECONFIGURE");
        unlink(ROOT "/network.rollback");
        return error(500, "Nie zapisano konfiguracji. Przywrócono poprzednie ustawienia.");
    }
    unlink(ROOT "/network.rollback");
    /* RECONNECT keeps all saved networks eligible; SELECT_NETWORK would disable others. */
    ok("RECONNECT");
    header(200);
    puts("{\"ok\":true}");
    return 0;
}
