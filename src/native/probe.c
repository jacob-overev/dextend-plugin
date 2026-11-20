/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Experimental SDL mobile client for the CPC200-CCPA USB gadget.
 * No vendor daemon or SDL SDK is linked into this program. */
#define _GNU_SOURCE
#include <errno.h>
#include <ctype.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "aa-sps.h"

#define MAX_FRAME (1024U * 1024U)
static volatile sig_atomic_t stopped;
static FILE *log_file;
static int usb_logging;
static unsigned ipc_diagnostic_count;
static const char *log_path;
static FILE *trace_file;
static int link_fd = -1;
static unsigned char rx[MAX_FRAME + 12];
static size_t rx_len;
static unsigned version = 4, session, next_message = 1;
static unsigned char rpc_hash[4];
static int have_rpc_hash, ending_rpc, end_rpc_ack;
static unsigned long video_tx_count, video_tx_bytes, video_ack_count;
/* Opt-in diagnostic bound, not a guarantee against decoder faults. */
static int video_guard, video_guard_blocked;
static unsigned long video_guard_sent, video_guard_acked, video_guard_written;
static unsigned aa_mode;

static int live_mode, ccu_failed;
static const char *device_path, *runtime_dir;
static uint64_t retry_at, session_deadline, last_ccu_rx, video_deadline, video_retry_at;
static unsigned retry_delay = 1000;
static uint64_t mono_ms(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static void marker(const char *name, const char *value)
{
    if (!runtime_dir)
        return;
    char path[4096];
    if (snprintf(path, sizeof(path), "%s/%s", runtime_dir, name) >= (int)sizeof(path))
        return;
    FILE *f = fopen(path, "w");
    if (f) {
        fputs(value, f);
        fclose(f);
    }
}
/* Short monotonic milestones for the ordinary diagnostic report. */
static void projection_event(const char *stage)
{
    char path[4096];
    if (!runtime_dir || snprintf(path, sizeof(path), "%s/projection-events", runtime_dir) >=
                            (int)sizeof(path))
        return;
    int fd = open(path, O_WRONLY | O_APPEND | O_CLOEXEC | O_NOFOLLOW | O_CREAT, 0600);
    if (fd < 0)
        return;
    if (lseek(fd, 0, SEEK_END) < 8192 || !ftruncate(fd, 0)) {
        uint64_t ms = mono_ms();
        dprintf(fd, "%llu.%03u %s %s\n", (unsigned long long)(ms / 1000),
                (unsigned)(ms % 1000), aa_mode ? "AA" : "CP", stage);
    }
    close(fd);
}
static int marked(const char *name)
{
    char path[4096];
    return runtime_dir &&
           snprintf(path, sizeof(path), "%s/%s", runtime_dir, name) < (int)sizeof(path) &&
           access(path, F_OK) == 0;
}
static void unmark(const char *name)
{
    char path[4096];
    if (runtime_dir && snprintf(path, sizeof(path), "%s/%s", runtime_dir, name) < (int)sizeof(path))
        unlink(path);
}
struct tx_item {
    struct tx_item *next;
    size_t size, offset;
    int video;
    unsigned char data[];
};
static struct tx_item *tx_head, *tx_tail;
static size_t tx_bytes;
static uint64_t tx_progress;
static void clear_tx(void)
{
    while (tx_head) {
        struct tx_item *next = tx_head->next;
        free(tx_head);
        tx_head = next;
    }
    tx_tail = NULL;
    tx_bytes = 0;
}
static void invalidate_video(void);
static void recover_ccu(const char *reason);
static void on_signal(int sig)
{
    (void)sig;
    stopped = 1;
}
static uint32_t be32(const unsigned char *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}
static void put32(unsigned char *p, uint32_t x)
{
    p[0] = (unsigned char)(x >> 24);
    p[1] = (unsigned char)(x >> 16);
    p[2] = (unsigned char)(x >> 8);
    p[3] = (unsigned char)x;
}
static void event(const char *level, const char *fmt, ...)
{
    if (usb_logging) {
        /* Only the recorder creates the parent directory. Each write uses
         * the current session, including after an unplug and reinsert. */
        log_file = fopen(log_path, "a");
        if (!log_file)
            return;
    }
    if (usb_logging && fseek(log_file, 0, SEEK_END)) {
        fclose(log_file);
        log_file = NULL;
        return;
    }
    const long limit = usb_logging ? 512 * 1024 : 2 * 1024 * 1024;
    if (log_path && ftell(log_file) >= limit) {
        char previous[4096];
        if (snprintf(previous, sizeof(previous), "%s.previous", log_path) < (int)sizeof(previous) &&
            rename(log_path, previous) == 0) {
            FILE *next = fopen(log_path, "a");
            if (next) {
                fclose(log_file);
                log_file = next;
            }
        }
    }
    char stamp[40];
    struct timespec ts;
    struct tm tm;
    clock_gettime(CLOCK_REALTIME, &ts);
    gmtime_r(&ts.tv_sec, &tm);
    strftime(stamp, sizeof stamp, "%Y-%m-%dT%H:%M:%S", &tm);
    va_list ap;
    va_start(ap, fmt);
    fprintf(log_file, "%s.%03ldZ %-5s ", stamp, ts.tv_nsec / 1000000, level);
    vfprintf(log_file, fmt, ap);
    va_end(ap);
    fputc('\n', log_file);
    if (usb_logging) {
        fclose(log_file);
        log_file = NULL;
    } else
        fflush(log_file);
}
static void hex_prefix(const unsigned char *data, size_t size, char *out, size_t cap)
{
    size_t n = size < 32 ? size : 32, pos = 0;
    for (size_t i = 0; i < n && pos + 4 < cap; i++)
        pos += (size_t)snprintf(out + pos, cap - pos, "%02x ", data[i]);
    out[pos] = 0;
}
static void trace_frame(unsigned char direction, const unsigned char *header, size_t header_size,
                        const void *payload, size_t payload_size)
{
    if (!trace_file)
        return;
    /* The diagnostic trace shares the dongle's small RAM filesystem. */
    const long trace_limit = 8L * 1024 * 1024;
    long position = ftell(trace_file);
    if (position < 0 || header_size + payload_size + 5 > (size_t)trace_limit ||
        position > trace_limit - (long)(header_size + payload_size + 5)) {
        fclose(trace_file);
        trace_file = NULL;
        event("INFO", "TRACE_STOPPED size_limit_bytes=%ld; video continues", trace_limit);
        return;
    }
    unsigned char prefix[5] = {direction, 0, 0, 0, 0};
    put32(prefix + 1, (uint32_t)(header_size + payload_size));
    if (fwrite(prefix, 1, 5, trace_file) != 5 ||
        fwrite(header, 1, header_size, trace_file) != header_size ||
        (payload_size && fwrite(payload, 1, payload_size, trace_file) != payload_size)) {
        event("ERROR", "Trace write failed errno=%d", errno);
    }
    fflush(trace_file);
}
static int write_all(const void *data, size_t size)
{
    const unsigned char *p = data;
    while (size && !stopped) {
        struct pollfd pf = {link_fd, POLLOUT, 0};
        if (poll(&pf, 1, 5000) <= 0) {
            event("ERROR", "USB write poll timeout/error errno=%d", errno);
            return -1;
        }
        ssize_t n = write(link_fd, p, size);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0) {
            event("ERROR", "USB write failed errno=%d (%s)", errno, strerror(errno));
            return -1;
        }
        p += n;
        size -= (size_t)n;
    }
    return stopped ? -1 : 0;
}
static int send_frame(unsigned ver, unsigned kind, unsigned svc, unsigned info, unsigned sess,
                      const void *payload, size_t length)
{
    if (length > MAX_FRAME || (ver == 1 && length > 1500))
        return -1;
    unsigned char hdr[12] = {0};
    size_t hlen = ver == 1 ? 8 : 12;
    hdr[0] = (unsigned char)((ver << 4) | kind);
    hdr[1] = (unsigned char)svc;
    hdr[2] = (unsigned char)info;
    hdr[3] = (unsigned char)sess;
    put32(hdr + 4, (uint32_t)length);
    if (ver != 1)
        put32(hdr + 8, next_message++);
    if (svc == 11 && kind == 1) {
        video_tx_count++;
        video_tx_bytes += length;
    } else
        event("TX", "SDL v%u kind=%u service=%u info=%u session=%u bytes=%zu message=%u", ver, kind,
              svc, info, sess, length, ver == 1 ? 0 : next_message - 1);
    trace_frame(1, hdr, hlen, payload, length);
    if (live_mode) {
        if (link_fd < 0 || ccu_failed)
            return -1;
        if (tx_bytes + hlen + length > 512 * 1024) {
            event("ERROR", "CCU_TX_QUEUE_FULL bytes=%zu", tx_bytes);
            ccu_failed = 1;
            return -1;
        }
        struct tx_item *item = malloc(sizeof(*item) + hlen + length);
        if (!item) {
            ccu_failed = 1;
            return -1;
        }
        *item = (struct tx_item){.size = hlen + length, .video = (svc == 11 && kind == 1)};
        memcpy(item->data, hdr, hlen);
        if (length)
            memcpy(item->data + hlen, payload, length);
        if (tx_tail)
            tx_tail->next = item;
        else {
            tx_head = item;
            tx_progress = mono_ms();
        }
        tx_tail = item;
        tx_bytes += item->size;
        return 0;
    }
    if (write_all(hdr, hlen))
        return -1;
    return length ? write_all(payload, length) : 0;
}
static int send_rpc_registration(void)
{
    /* Yamaha compatibility identity. Keep all three values together:
       acceptance by a development SDL Core does not validate a new identity. */
    static const char json[] =
        "{\"appName\":\"Motorize\",\"appID\":\"7a5f3f258b\","
        "\"fullAppID\":\"7a5f3f25-8b82-4e0f-a173-80aefee79897\","
        "\"isMediaApplication\":false,\"languageDesired\":\"EN-US\","
        "\"hmiDisplayLanguageDesired\":\"EN-US\",\"appHMIType\":[\"NAVIGATION\"],"
        "\"syncMsgVersion\":{\"majorVersion\":7,\"minorVersion\":0}}";
    unsigned char buf[12 + sizeof json];
    size_t jlen = sizeof json - 1;
    put32(buf, 1);
    put32(buf + 4, 1);
    put32(buf + 8, (uint32_t)jlen);
    memcpy(buf + 12, json, jlen);
    if (usb_logging)
        event("INFO", "RegisterAppInterface request");
    else
        event("INFO", "RegisterAppInterface request JSON=%s", json);
    return send_frame(version, 1, 7, 0, session, buf, 12 + jlen);
}
static int send_video_start(void)
{
    /* Protocol v4 allows empty StartService payload. Resolution/codec are
       negotiated through RegisterAppInterface capabilities in later versions. */
    return send_frame(version, 0, 11, 1, session, NULL, 0);
}
static int send_video(const unsigned char *data, size_t length)
{
    if (live_mode && video_guard) {
        if (video_guard_blocked)
            return 0;
        /* AA command 12 also changes video focus. Absorb short ACK bursts
         * locally before discarding an access unit and requesting an IDR. */
        unsigned capacity = aa_mode ? 12 : 4;
        if (video_guard_sent >= video_guard_acked + capacity ||
            (aa_mode && video_guard_sent > video_guard_acked && tx_bytes + length + 12 > 480 * 1024)) {
            video_guard_blocked = 1;
            event("WARN", "VIDEO_GUARD_PAUSED sent=%lu acked=%lu; waiting for all outstanding ACKs",
                  video_guard_sent, video_guard_acked);
            return 0;
        }
    }
    if (length + 12 <= 131084) {
        int result = send_frame(version, 1, 11, 0, session, data, length);
        if (!result)
            video_guard_sent++;
        return result;
    }
    event("ERROR", "Video access unit too large for one SDL frame: %zu", length);
    return -1;
}
static int registered, hmi_full, video_requested, video_ack, buttons_requested;
/* A waiting card and the phone must never share a decoder configuration. */
static int video_source, video_ending; /* source: 0 unset, 1 card, 2 phone */
static uint64_t video_end_deadline, startup_refresh_at;
static unsigned startup_refresh_ms = 2000;
static void forward_button(unsigned preset);
static unsigned diagnostic_correlation = 1000;
static void diagnostic_rpc(unsigned fn, const unsigned char *json, size_t n)
{
    if ((fn != 2 && fn != 13 && fn != 18 && fn != 19 && fn != 20) || n < 2 || n > 512 ||
        json[0] != '{' || json[n - 1] != '}')
        return;
    unsigned char payload[524];
    put32(payload, fn);
    put32(payload + 4, ++diagnostic_correlation);
    put32(payload + 8, (unsigned)n);
    memcpy(payload + 12, json, n);
    send_frame(version, 1, 7, 0, session, payload, n + 12);
    event("INPUT", "DIAGNOSTIC_RPC function=%u correlation=%u", fn, diagnostic_correlation);
}
static unsigned button_accepted, button_finished;
static unsigned char button_attempts[16];
static uint64_t button_retry_at[16];
static unsigned show_correlation = 200;
static void show_navigation(int active)
{
    const char *json =
        active ? "{\"mainField1\":\"NAV_LEAVE_TOP_PAGE\"}" : "{\"mainField1\":\"NAV_ON_TOP_PAGE\"}";
    unsigned char payload[100];
    size_t n = strlen(json);
    put32(payload, 13);
    put32(payload + 4, ++show_correlation);
    put32(payload + 8, (unsigned)n);
    memcpy(payload + 12, json, n);
    send_frame(version, 1, 7, 0, session, payload, n + 12);
    event("INPUT", "NAVIGATION_STATE active=%d correlation=%u", active, show_correlation);
}
static void subscribe_buttons(void)
{
    if (!registered || !hmi_full)
        return;
    buttons_requested = 1;
    static const char *buttons[] = {"PRESET_0",  "PRESET_1", "PRESET_2", "PRESET_3",
                                    "PRESET_4",  "PRESET_5", "PRESET_6", "PRESET_7",
                                    "PRESET_8",  "PRESET_9", "OK",       "SEEKLEFT",
                                    "SEEKRIGHT", "TUNEUP",   "TUNEDOWN", "SEARCH"};
    for (unsigned i = 0; i < sizeof(buttons) / sizeof(buttons[0]); i++) {
        if ((button_finished & (1U << i)) || mono_ms() < button_retry_at[i])
            continue;
        if (button_attempts[i] >= 3) {
            button_finished |= 1U << i;
            event("WARN", "SUBSCRIBE_RETRIES_EXHAUSTED button_index=%u", i);
            continue;
        }
        button_attempts[i]++;
        button_retry_at[i] = mono_ms() + 5000;
        char json[64];
        unsigned char payload[100];
        int n = snprintf(json, sizeof(json), "{\"buttonName\":\"%s\"}", buttons[i]);
        put32(payload, 18);
        put32(payload + 4, 101 + i);
        put32(payload + 8, (unsigned)n);
        memcpy(payload + 12, json, (size_t)n);
        send_frame(version, 1, 7, 0, session, payload, 12 + (size_t)n);
        event("INPUT", "SUBSCRIBE %s correlation=%u", buttons[i], 101 + i);
    }
}
static void maybe_start_video(void)
{
    if (registered && hmi_full && !video_requested && !video_ending && !ending_rpc &&
        mono_ms() >= video_retry_at) {
        subscribe_buttons();
        show_navigation(1);
        video_requested = 1;
        video_deadline = mono_ms() + 8000;
        event("STAGE", "HMI_FULL_AND_REGISTERED: requesting video service");
        send_video_start();
    }
}
/* Match a top-level JSON member, ignoring whitespace outside strings. */
static int json_top_equals(const char *j, size_t n, const char *key, const char *value)
{
    unsigned depth = 0;
    for (size_t i = 0; i < n; i++) {
        if (j[i] == '{' || j[i] == '[') {
            depth++;
            continue;
        }
        if (j[i] == '}' || j[i] == ']') {
            if (depth)
                depth--;
            continue;
        }
        if (j[i] != '"')
            continue;
        size_t start = ++i;
        while (i < n && j[i] != '"') {
            if (j[i] == '\\' && i + 1 < n)
                i++;
            i++;
        }
        if (i >= n)
            return 0;
        if (depth != 1 || i - start != strlen(key) || memcmp(j + start, key, i - start))
            continue;
        size_t pos = i + 1;
        while (pos < n && isspace((unsigned char)j[pos]))
            pos++;
        if (pos == n || j[pos++] != ':')
            continue;
        while (pos < n && isspace((unsigned char)j[pos]))
            pos++;
        size_t len = strlen(value);
        if (len > n - pos || memcmp(j + pos, value, len))
            return 0;
        pos += len;
        return pos == n || j[pos] == ',' || j[pos] == '}' || isspace((unsigned char)j[pos]);
    }
    return 0;
}
static void log_rpc(const unsigned char *p, size_t n)
{
    if (n < 12) {
        event("WARN", "Short RPC payload %zu", n);
        return;
    }
    uint32_t first = be32(p), corr = be32(p + 4), json_size = be32(p + 8);
    unsigned typ = first >> 28, fn = first & 0x0fffffff;
    event("RPC", "type=%u function=%u correlation=%u json_bytes=%u", typ, fn, corr, json_size);
    if (json_size > n - 12) {
        event("ERROR", "Truncated RPC JSON");
        return;
    }
    if (json_size && !usb_logging)
        event("JSON", "%.*s", (int)json_size, (const char *)(p + 12));
    if (typ == 1 && fn == 1 && corr == 1) {
        const char *j = (const char *)(p + 12);
        if (json_top_equals(j, json_size, "success", "true")) {
            registered = 1;
            session_deadline = 0;
            event("STAGE", "REGISTERED: waiting for HMI_FULL on CCU");
            maybe_start_video();
        } else {
            event("STAGE", "REGISTRATION_REJECTED");
            ccu_failed = 1;
        }
    } else if (typ == 1 && fn == 2) {
        event("STAGE", "APP_UNREGISTER_RESPONSE: reconnecting CCU");
        ccu_failed = 1;
    } else if (typ == 1 && fn == 13) {
        event("INPUT", "SHOW_RESULT correlation=%u accepted=%d", corr,
              json_top_equals((const char *)p + 12, json_size, "success", "true"));
    } else if (typ == 1 && fn == 18) {
        int accepted = json_top_equals((const char *)p + 12, json_size, "success", "true");
        if (corr >= 101 && corr < 117) {
            unsigned i = corr - 101;
            if (accepted) {
                button_accepted |= 1U << i;
                button_finished |= 1U << i;
            }
            /* Optional unsupported buttons must not cause endless retries. */
            else if (i >= 7 || json_top_equals((const char *)p + 12, json_size, "resultCode",
                                               "\"UNSUPPORTED_RESOURCE\""))
                button_finished |= 1U << i;
        }
        event("INPUT", "SUBSCRIBE_RESULT correlation=%u accepted=%d", corr, accepted);
    } else if (typ == 2 && fn == 32771 && hmi_full) {
        for (unsigned i = 0; i < 7; i++) {
            char name[24];
            snprintf(name, sizeof(name), "\"PRESET_%u\"", i);
            if (json_top_equals((const char *)p + 12, json_size, "buttonName", name)) {
                forward_button(i);
            }
        }
    } else if (typ == 2 && fn == 32769) {
        registered = video_ack = 0;
        event("STAGE", "APP_UNREGISTERED: reconnecting CCU");
        if (live_mode)
            ccu_failed = 1;
        else
            stopped = 1;
    } else if (typ == 2 && fn == 32768 && json_size) {
        const char *j = (const char *)(p + 12);
        int was_full = hmi_full;
        hmi_full = json_top_equals(j, json_size, "hmiLevel", "\"FULL\"");
        if (hmi_full != was_full) {
            projection_event(hmi_full ? "HMI_FULL" : "HMI_LEFT");
            invalidate_video();
        }
        if (hmi_full && !was_full) {
            /* Navigation re-entry is an explicit retry trigger for missing
             * essential subscriptions, without duplicating successful ones. */
            for (unsigned i = 0; i < 7; i++)
                if (!(button_accepted & (1U << i))) {
                    button_finished &= ~(1U << i);
                    button_attempts[i] = 0;
                    button_retry_at[i] = 0;
                }
            video_retry_at = 0;
            if (video_requested && !video_ack)
                video_requested = 0;
            if (video_ack)
                show_navigation(1);
        }
        event("STAGE", "HMI_STATUS full=%d", hmi_full);
        maybe_start_video();
    }
}
static void process_frame(const unsigned char *p, size_t n)
{
    unsigned ver = p[0] >> 4, kind = p[0] & 7, svc = p[1], info = p[2], sess = p[3];
    unsigned hlen = ver == 1 ? 8 : 12;
    uint32_t len = be32(p + 4);
    int start_ack = svc == 7 && kind == 0 && info == 2;
    if ((start_ack && session) || (!start_ack && sess != session)) {
        event("WARN", "STALE_SESSION_FRAME incoming=%u active=%u service=%u info=%u", sess, session,
              svc, info);
        return;
    }
    if (!session && !start_ack && svc != 0)
        return;
    last_ccu_rx = mono_ms();
    char hex[128];
    if (!usb_logging && !(svc == 11 && kind == 0 && info == 254))
        hex_prefix(p + hlen, len, hex, sizeof hex);
    trace_frame(2, p, n, NULL, 0);
    if (svc == 11 && kind == 0 && info == 254) {
        video_ack_count++;
        if (video_guard_acked < video_guard_written)
            video_guard_acked++;
        if (video_guard && video_guard_blocked && video_guard_acked == video_guard_sent) {
            video_guard_blocked = 0;
            invalidate_video();
            event("STAGE", "VIDEO_GUARD_RESUME sent=%lu acked=%lu; fresh IDR required",
                  video_guard_sent, video_guard_acked);
        }
    } else if (usb_logging)
        event("RX", "SDL v%u kind=%u service=%u info=%u session=%u bytes=%u message=%u", ver, kind,
              svc, info, sess, len, ver == 1 ? 0 : be32(p + 8));
    else
        event("RX", "SDL v%u kind=%u service=%u info=%u session=%u bytes=%u message=%u prefix=%s",
              ver, kind, svc, info, sess, len, ver == 1 ? 0 : be32(p + 8), hex);
    if (svc == 7 && kind == 0 && info == 2) {
        have_rpc_hash = len == 4;
        if (have_rpc_hash)
            memcpy(rpc_hash, p + hlen, 4);
        version = ver;
        session = sess;
        session_deadline = mono_ms() + 8000;
        event("STAGE", "RPC_SERVICE_ACK: protocol=%u session=%u", version, session);
        send_rpc_registration();
    } else if (svc == 7 && kind == 0 && info == 3) {
        event("STAGE", "RPC_SERVICE_NAK");
        ccu_failed = 1;
    } else if (svc == 11 && kind == 0 && info == 2) {
        if (video_ending) {
            event("WARN", "VIDEO_START_ACK_DURING_END");
            return;
        }
        video_guard_sent = video_guard_written = video_guard_acked = 0;
        video_guard_blocked = 0;
        video_ack = 1;
        video_source = 0;
        video_deadline = 0;
        invalidate_video();
        projection_event("VIDEO_SERVICE_ACK");
        event("STAGE", "VIDEO_SERVICE_ACK: ready to send H.264");
    } else if (svc == 11 && kind == 0 && info == 3) {
        event("STAGE", "VIDEO_SERVICE_NAK");
        video_requested = video_ack = 0;
        video_retry_at = mono_ms() + 2000;
        invalidate_video();
    } else if (svc == 11 && kind == 0 && (info == 4 || info == 5)) {
        int planned = video_ending;
        video_ack = video_requested = video_ending = video_source = 0;
        video_end_deadline = 0;
        video_retry_at = mono_ms() + (planned ? 100 : 2000);
        invalidate_video();
        if (info == 4)
            send_frame(ver, 0, 11, 5, sess, NULL, 0);
        event("STAGE", "VIDEO_SERVICE_ENDED info=%u planned=%d", info, planned);
    } else if (svc == 11 && kind == 0 && info == 6 && video_ending) {
        event("ERROR", "VIDEO_END_SERVICE_NAK");
        ccu_failed = 1;
    } else if (svc == 7 && kind == 0 && (info == 4 || info == 5)) {
        if (ending_rpc && info == 5)
            end_rpc_ack = 1;
        else
            ccu_failed = 1;
    } else if (svc == 7 && kind == 1) {
        log_rpc(p + hlen, n - hlen);
    } else if (kind == 0 && info == 0) {
        send_frame(ver, 0, svc, 255, sess, NULL, 0);
    }
}
static int read_pending(int timeout_ms)
{
    if (link_fd < 0)
        return 0;
    struct pollfd pf = {link_fd, POLLIN, 0};
    int result = poll(&pf, 1, timeout_ms);
    if (result < 0 && errno == EINTR)
        return 0;
    if (result < 0) {
        event("ERROR", "USB read poll errno=%d", errno);
        return -1;
    }
    if (!result)
        return 0;
    if (pf.revents & (POLLHUP | POLLERR | POLLNVAL)) {
        event("ERROR", "USB poll revents=0x%x", pf.revents);
        return -1;
    }
    ssize_t n = read(link_fd, rx + rx_len, sizeof rx - rx_len);
    if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK))
        return 0;
    if (n <= 0) {
        event("ERROR", "USB read=%zd errno=%d (%s)", n, errno, strerror(errno));
        return -1;
    }
    rx_len += (size_t)n;
    while (rx_len >= 8) {
        unsigned ver = rx[0] >> 4, hlen = ver == 1 ? 8 : 12;
        if (ver < 1 || ver > 5) {
            event("ERROR", "Invalid SDL protocol byte %02x", rx[0]);
            return -1;
        }
        if (rx_len < hlen)
            break;
        uint32_t len = be32(rx + 4);
        if (len > MAX_FRAME) {
            event("ERROR", "Invalid SDL length %u", len);
            return -1;
        }
        if (rx_len < hlen + len)
            break;
        process_frame(rx, hlen + len);
        if (ccu_failed)
            return -1;
        memmove(rx, rx + hlen + len, rx_len - hlen - len);
        rx_len -= hlen + len;
    }
    return 0;
}
static unsigned char *load_file(const char *path, size_t *size)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return NULL;
    if (fseek(f, 0, SEEK_END) || (*size = (size_t)ftell(f)) > MAX_FRAME || fseek(f, 0, SEEK_SET)) {
        fclose(f);
        return NULL;
    }
    unsigned char *p = malloc(*size ? *size : 1);
    if (!p || fread(p, 1, *size, f) != *size) {
        free(p);
        fclose(f);
        return NULL;
    }
    fclose(f);
    return p;
}
static uint32_t le32(const unsigned char *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
#define IPC_CLIENTS 6
struct ipc_client {
    int fd;
    unsigned char *data;
    size_t used;
    unsigned type;
    unsigned char out[65560];
    size_t out_used, out_sent;
    uint64_t out_since;
};
static struct ipc_client clients[IPC_CLIENTS];
static int ipc_listener = -1, ipc_lock = -1, live_synced, refresh_requested, carplay_ready;
static int smooth_transitions, inplace_transitions, stable_h264_level, source_guard_blocked;
static int wireless_video_watchdog;
static uint64_t source_video_at, source_probe_at;
static int ipc_diagnostics;
static int ipc_logging_enabled(void)
{
    return usb_logging ? marked("usb-debug") : ipc_diagnostics && ipc_diagnostic_count < 512;
}
static int bt_handover_test;
static int iap2_wifi_router_test;
static unsigned phone_generation;
struct iap2_pending {
    unsigned char data[65560];
    size_t used;
    uint64_t since;
};
static struct iap2_pending iap2_pending[2];
static pid_t bt_handover_child;
static uint64_t bt_handover_started;
static uint64_t phone_ready_since, transition_ready_until, waiting_started;
static unsigned char *waiting_frame;
static size_t waiting_size, waiting_pos = 8;
static int waiting_clip;
/* Codec configuration only, never a cached phone frame/GOP. */
static unsigned char source_sps[4096], source_pps[4096];
static size_t source_sps_size, source_pps_size;
static const char *source_snapshot_path;
static const char *source_sequence_path;
static unsigned source_sequence_frames;
static size_t source_sequence_bytes;
static uint64_t source_sequence_until;
static uint64_t waiting_last, idr_wait_since, phone_retry_at, manual_trigger_ms;
static void close_client(struct ipc_client *c);
static void ipc_metadata(const char *direction, unsigned type, unsigned command, size_t n)
{
    if (!ipc_logging_enabled())
        return;
    event("IPC", "CONTROL_META uptime_ms=%llu direction=%s type=%u command=%u payload_bytes=%zu",
          (unsigned long long)mono_ms(), direction, type, command, n);
    if (!usb_logging && ++ipc_diagnostic_count == 512)
        event("INFO", "IPC_DIAGNOSTICS_LIMIT records=512; metadata logging stopped");
}
/* Factory receiver 0x2cb60: inner type 12, word 4, 17-byte deviceID,
 * 3 trailing bytes. Do not inspect trailing padding or print the deviceID.
 * This classifies evidence only: it must not disconnect Bluetooth. */
static const char *ipc_bluetooth_handover(unsigned client_type, const unsigned char *p, size_t n)
{
    if (client_type != 3 || n != 32 || le32(p) != 24 || le32(p + 4) != 12 || le32(p + 8) != 4)
        return "not_matched";
    for (unsigned i = 0; i < 17; i++) {
        unsigned char ch = p[12 + i];
        if (i % 3 == 2) {
            if (ch != ':')
                return "invalid_device_id";
        } else if (!((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f') ||
                     (ch >= 'A' && ch <= 'F')))
            return "invalid_device_id";
    }
    return "disable_bluetooth_request";
}
/* Opt-in RAM experiment. The requested peer is passed only to hcitool,
 * never to a shell or logger. Run outside the SDL loop with a deadline. */
static void bluetooth_handover_tick(void)
{
    if (!bt_handover_child)
        return;
    int status = 0;
    pid_t result = waitpid(bt_handover_child, &status, WNOHANG);
    if (result == bt_handover_child || (result < 0 && errno == ECHILD)) {
        event("IPC", "BT_HANDOVER_TEST finished=1 success=%d",
              result > 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0);
        bt_handover_child = 0;
    } else if (mono_ms() - bt_handover_started >= 3000) {
        kill(bt_handover_child, SIGKILL);
        /* Reap on a later tick; never block the SDL thread. */
    }
}
static void bluetooth_handover_request(unsigned client_type, unsigned command,
                                       const unsigned char *p, size_t n)
{
    if (!bt_handover_test || !runtime_dir || command != 6 || bt_handover_child ||
        strcmp(ipc_bluetooth_handover(client_type, p, n), "disable_bluetooth_request"))
        return;
    char path[4096], mode[16] = {0};
    if (snprintf(path, sizeof(path), "%s/phone-mode", runtime_dir) >= (int)sizeof(path))
        return;
    int fd = open(path, O_RDONLY | O_NOFOLLOW);
    if (fd < 0)
        return;
    ssize_t count = read(fd, mode, sizeof(mode) - 1);
    close(fd);
    if (count != 9 || memcmp(mode, "wireless\n", 9))
        return;
    char peer[18];
    memcpy(peer, p + 12, 17);
    peer[17] = 0;
    if (!strcmp(peer, "00:00:00:00:00:00") || !strcasecmp(peer, "ff:ff:ff:ff:ff:ff"))
        return;
    long max_fd = sysconf(_SC_OPEN_MAX);
    if (max_fd < 0)
        return;
    pid_t child = fork();
    if (child < 0) {
        event("WARN", "BT_HANDOVER_TEST fork_failed=1");
        return;
    }
    if (!child) {
        int nullfd = open("/dev/null", O_RDWR);
        if (nullfd < 0)
            _exit(126);
        for (int i = 0; i < 3; i++)
            if (dup2(nullfd, i) < 0)
                _exit(126);
        for (long i = 3; i < max_fd; i++)
            close((int)i);
        execlp("hcitool", "hcitool", "dc", peer, (char *)NULL);
        _exit(127);
    }
    bt_handover_child = child;
    bt_handover_started = mono_ms();
    event("IPC", "BT_HANDOVER_TEST requested=1 target=request_device_id");
}
static void ipc_received_metadata(unsigned client_type, unsigned command, const unsigned char *p,
                                  size_t n)
{
    if (command != 6) {
        ipc_metadata("RX", client_type, command, n);
        return;
    }
    /* Outer command 6 also carries control. Only inner type 1 is video.
     * Record framing fields, never the contents of a control message.
     */
    if (!ipc_logging_enabled() || n < 8 || le32(p) != n - 8 || le32(p + 4) == 1)
        return;
    unsigned known_control = 0;
    if (client_type == 3 && n == 12 && le32(p + 4) == 12) {
        /* Only enum values identified in the inspected receiver; never dump
         * an arbitrary four-byte payload under a diagnostic label. */
        switch (le32(p + 8)) {
        case 3:
        case 412:
        case 500:
        case 501:
        case 506:
        case 507:
        case 508:
            known_control = le32(p + 8);
            break;
        }
    }
    event("IPC",
          "CONTROL_INNER_META uptime_ms=%llu direction=RX type=%u command=6 inner_type=%u "
          "payload_bytes=%zu handover=%s action=observe_only known_control12=%u",
          (unsigned long long)mono_ms(), client_type, le32(p + 4), n - 8,
          ipc_bluetooth_handover(client_type, p, n), known_control);
    if (!usb_logging && ++ipc_diagnostic_count == 512)
        event("INFO", "IPC_DIAGNOSTICS_LIMIT records=512; metadata logging stopped");
}
static int ipc_send(struct ipc_client *c, const void *p, size_t n)
{
    const unsigned char *bytes = p;
    if (n >= 16 && le32(bytes) == 0x55aa55aa && le32(bytes + 12) == ~le32(bytes + 8))
        ipc_metadata("TX", c->type, le32(bytes + 8), le32(bytes + 4));
    if (n > sizeof(c->out) - c->out_used) {
        event("WARN", "PHONE_IPC_QUEUE_OVERFLOW type=%u", c->type);
        if (c->type == 3 || c->type == 32)
            marker("phone-restart", "1\n");
        close_client(c);
        return -1;
    }
    if (!c->out_used)
        c->out_since = mono_ms();
    memcpy(c->out + c->out_used, p, n);
    c->out_used += n;
    return 0;
}
/* Preserve ordering while a Wi-Fi iAP2 peer registers during handover.
 * Bounded, session-local queue: timeout means renegotiate, never stale replay. */
static void iap2_route_tick(void)
{
    for (unsigned k = 0; k < 2; k++) {
        struct iap2_pending *q = &iap2_pending[k];
        if (!q->used)
            continue;
        if (mono_ms() - q->since >= 8000) {
            event("WARN", "IAP2_WIFI_ROUTE peer timeout; phone retry requested");
            memset(iap2_pending, 0, sizeof(iap2_pending));
            marker("phone-restart", "1\n");
            return;
        }
        for (unsigned i = 0; i < IPC_CLIENTS; i++) {
            struct ipc_client *c = &clients[i];
            if (c->fd < 0 || c->type != (k ? 32U : 3U))
                continue;
            if (ipc_send(c, q->data, q->used))
                marker("phone-restart", "1\n");
            q->used = 0;
            break;
        }
    }
}
/* Factory ARMadb 0x176fc-0x1772a routes inner 102 between clients 3/32.
 * Keep the original envelope and bytes; never decode or log private iAP2. */
static void route_iap2_wifi(struct ipc_client *source, unsigned command, const unsigned char *p,
                            size_t n)
{
    if (!iap2_wifi_router_test || command != 6 || n < 8 || le32(p) != n - 8 || le32(p + 4) != 102)
        return;
    unsigned target = source->type == 3 ? 32 : source->type == 32 ? 3 : 0;
    if (!target)
        return;
    struct iap2_pending *q = &iap2_pending[target == 32];
    for (unsigned i = 0; !q->used && i < IPC_CLIENTS; i++) {
        struct ipc_client *destination = &clients[i];
        if (destination == source || destination->fd < 0 || destination->type != target)
            continue;
        if (ipc_send(destination, p - 16, n + 16))
            marker("phone-restart", "1\n");
        return;
    }
    if (n + 16 > sizeof(q->data) - q->used) {
        event("WARN", "IAP2_WIFI_ROUTE pending overflow; phone retry requested");
        memset(iap2_pending, 0, sizeof(iap2_pending));
        marker("phone-restart", "1\n");
        return;
    }
    if (!q->used)
        q->since = mono_ms();
    memcpy(q->data + q->used, p - 16, n + 16);
    q->used += n + 16;
}
static unsigned long live_frames, live_dropped;
static const char *ipc_path;
static uint64_t last_keyframe_request_ms;
/* Explicit RAM diagnostic, never part of normal pairing/recovery.
 * Inspected receiver: outer command 6 -> {length=4,type=12,command=410}
 * -> AirPlayReceiverSessionRequestUI -> showUI. No pairing ACK is assumed.
 */
static int diagnostic_show_ui(void)
{
    const char *enabled = getenv("YAMAHA_PAIRING_UI_TEST");
    if (!enabled || strcmp(enabled, "1") || !carplay_ready)
        return -1;
    for (unsigned i = 0; i < IPC_CLIENTS; i++) {
        if (clients[i].fd < 0 || clients[i].type != 3)
            continue;
        unsigned char packet[28];
        const uint32_t words[] = {0x55aa55aa, 12, 6, ~6U, 4, 12, 410};
        for (unsigned w = 0; w < 7; w++)
            for (unsigned b = 0; b < 4; b++)
                packet[4 * w + b] = (unsigned char)(words[w] >> (8 * b));
        int result = ipc_send(&clients[i], packet, sizeof(packet));
        event("PAIRING", "SHOW_UI_TEST command=410 queued=%d", result == 0);
        return result;
    }
    return -1;
}
static unsigned aa_header_zero, phone_auto;
static unsigned auto_cp_refresh;
static int auto_cp_router, auto_cp_watchdog;
static uint64_t aa_back_at;
/* 0 active, 1 phone yielded video focus, 2 awaiting a fresh resume IDR. */
static unsigned aa_video_focus;
static uint64_t aa_resume_at;
/* One focus request before the first picture, after an OEM video-state event.
 * An explicit focus yield cancels it for the lifetime of this AA client. */
static int aa_initial_focus_allowed;
static uint64_t aa_initial_focus_at;
static void forward_button(unsigned preset)
{
    if (preset > 6)
        return;
    if (preset != 0)
        aa_back_at = 0;
    if (preset == 6) {
        event("INPUT", "PRESET_6 action=HOME_NOTIFICATION; no CarPlay HID command");
        uint64_t now = mono_ms();
        if (aa_mode && aa_video_focus == 1) {
            aa_initial_focus_at = 0;
            aa_initial_focus_allowed = 0;
            aa_video_focus = 2;
            aa_resume_at = now;
            event("STAGE", "AA_VIDEO_RESUME requested_by=navigation_return");
        }
        if (!carplay_ready && (!manual_trigger_ms || now - manual_trigger_ms >= 5000)) {
            marker("phone-trigger", "navigation_button");
            manual_trigger_ms = now;
            event("RECOVERY", "PHONE trigger=navigation_button session_not_ready=1");
        }
        if (!refresh_requested)
            idr_wait_since = 0;
        refresh_requested = 1;
        last_keyframe_request_ms = 0;
        /* Request video refresh only; never infer HMI ownership from this button. */
        /* PRESET_6 reports the CCU-owned display switch, not an app page change. */
        return;
    }
    /* 111/112 are HID X-axis; 100/101 are rotary wheel steps. */
    static const unsigned keys[7] = {106, 104, 100, 101, 102, 103, 200};
    static const char *names[7] = {"BACK", "SELECT", "ROTARY_PREVIOUS",  "ROTARY_NEXT",
                                   "UP",   "DOWN",   "HOME_NOTIFICATION"};
    if (aa_mode) {
        static const unsigned aa_keys[6] = {106, 104, 100, 101, 102, 103};
        static const char *aa_names[6] = {"BACK", "SELECT",  "PREVIOUS",
                                          "NEXT", "AREA_UP", "AREA_DOWN"};
        /* The 120 DPI layout has a bottom bar: up/down nudges between areas,
         * while left/right sends rotary steps to select within an area.
         * Both must be advertised by the receiver (OEM no_touch omits DPAD).
         * It emits its own press/release pair; CarPlay's 105 is not an AA release. */
        for (unsigned i = 0; i < IPC_CLIENTS; i++) {
            if (clients[i].fd < 0 || clients[i].type != 5)
                continue;
            uint64_t now = mono_ms();
            int resume = aa_video_focus != 0;
            if (resume && aa_resume_at && now - aa_resume_at < 2000) {
                event("INPUT", "PRESET_%u deferred: AA awaiting resume IDR", preset);
                return;
            }
            int home = !resume && preset == 0 && aa_back_at && now - aa_back_at <= 500;
            unsigned key = resume ? 12 : home ? 200 : aa_keys[preset];
            unsigned char packet[28];
            /* OEM command 200 generates KEYCODE_HOME (3). A second Back
             * supplies a deliberate escape without guessing the phone's UI. */
            const unsigned words[] = {0x55aa55aa, 12, 9, aa_header_zero ? 0 : ~9U, 4, 12, key};
            for (unsigned w = 0; w < 7; w++)
                for (unsigned b = 0; b < 4; b++)
                    packet[4 * w + b] = (unsigned char)(words[w] >> (8 * b));
            int result = ipc_send(&clients[i], packet, sizeof(packet));
            aa_back_at = preset == 0 && !home && !resume && !result ? now : 0;
            if (resume && !result) {
                aa_initial_focus_at = 0;
                aa_initial_focus_allowed = 0;
                aa_video_focus = 2;
                aa_resume_at = now;
                invalidate_video();
                last_keyframe_request_ms = now;
                idr_wait_since = now;
            }
            event("INPUT", "PRESET_%u action=%s aa_command=%u queued=%d", preset,
                  resume ? "RESUME_VIDEO"
                  : home ? "HOME_DOUBLE_BACK"
                         : aa_names[preset],
                  key, result == 0);
            return;
        }
        event("INPUT", "PRESET_%u dropped: no AA IPC client", preset);
        return;
    }
    unsigned char packets[56];
    for (unsigned i = 0; i < IPC_CLIENTS; i++) {
        if (clients[i].fd < 0 || clients[i].type != 3)
            continue;
        for (unsigned k = 0; k < 2; k++) {
            unsigned char *p = packets + k * 28;
            unsigned values[7] = {0x55aa55aa, 12, 6, ~6U, 4, 12, k ? 105 : keys[preset]};
            for (unsigned w = 0; w < 7; w++)
                for (unsigned b = 0; b < 4; b++)
                    p[w * 4 + b] = (unsigned char)(values[w] >> (8 * b));
        }
        ssize_t n = ipc_send(&clients[i], packets, sizeof(packets)) ? -1 : (ssize_t)sizeof(packets);
        event("INPUT", "PRESET_%u action=%s carplay_key=%u sent=%zd", preset, names[preset],
              keys[preset], n);
        if (n != (ssize_t)sizeof(packets))
            event("ERROR", "INPUT_SEND_FAILED errno=%d", errno);
        return;
    }
    event("INPUT", "PRESET_%u dropped: no CarPlay IPC client", preset);
}

static int live_init(void)
{
    ipc_path = getenv("YAMAHA_CARPLAY_SOCKET");
    if (!ipc_path)
        ipc_path = "/tmp/yamaha-sdl/carplay-ipc.sock";
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(ipc_path) >= sizeof(address.sun_path))
        return -1;
    strcpy(address.sun_path, ipc_path);
    for (unsigned i = 0; i < IPC_CLIENTS; i++)
        clients[i].fd = -1;
    ipc_listener = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (ipc_listener < 0)
        return -1;
    char lock_path[4096];
    snprintf(lock_path, sizeof(lock_path), "%s.lock", ipc_path);
    ipc_lock = open(lock_path, O_CREAT | O_RDWR | O_CLOEXEC, 0600);
    if (ipc_lock < 0 || flock(ipc_lock, LOCK_EX | LOCK_NB))
        return -1;
    if (!aa_mode)
        unlink(ipc_path); /* AA trial must never replace an OEM endpoint. */
    if (bind(ipc_listener, (void *)&address, sizeof(address)) || chmod(ipc_path, 0600) ||
        listen(ipc_listener, 4))
        return -1;
    event("STAGE", "CARPLAY_IPC_LISTEN path=%s", ipc_path);
    return 0;
}
static int has_nal(const unsigned char *p, size_t n, unsigned type)
{
    for (size_t i = 0; i + 3 < n; i++) {
        if (!p[i] && !p[i + 1] && p[i + 2] == 1 && (p[i + 3] & 31) == type)
            return 1;
    }
    return 0;
}
static size_t nal_prefix(const unsigned char *p, size_t n)
{
    if (n >= 4 && !p[0] && !p[1] && !p[2] && p[3] == 1)
        return 4;
    if (n >= 3 && !p[0] && !p[1] && p[2] == 1)
        return 3;
    return 0;
}

static const char *aa_peer;
static const char *aa_rfcomm_path = "/tmp/rfcomm_AAP";
static int aa_start_pending;
static unsigned aa_start_check;
static int aa_sps_ready;
static struct aa_geometry aa_geometry = AA_YAMAHA_GEOMETRY;

static void aa_put32(unsigned char *p, unsigned x)
{
    for (unsigned i = 0; i < 4; i++)
        p[i] = (unsigned char)(x >> (8 * i));
}
static int aa_start(struct ipc_client *c, unsigned check)
{
    unsigned char p[60] = {0};
    char session[4096];
    const char *dir = runtime_dir ? runtime_dir : "/tmp/yamaha-sdl";
    if (snprintf(session, sizeof(session), "%s/%s", dir, AA_SESSION_NAME) >= (int)sizeof(session))
        return -1;
    aa_geometry = aa_load_geometry(session);
    const unsigned words[] = {
        0x55aa55aa, 44, 9, check ? ~9U : 0, 36, 200,
        aa_mode, aa_geometry.width, aa_geometry.height, 30
    };
    for (unsigned i = 0; i < 10; i++)
        aa_put32(p + 4 * i, words[i]);
    if (aa_mode == 2)
        memcpy(p + 40, aa_peer, 17);
    aa_header_zero = !check;
    aa_initial_focus_allowed = 1;
    aa_initial_focus_at = 0;
    event("STAGE", "AA_START_LINK mode=%u view=%ux%u fps=30", aa_mode, aa_geometry.width,
          aa_geometry.height);
    int result = ipc_send(c, p, sizeof(p));
    if (!result)
        projection_event("AA_LINK_REQUEST");
    return result;
}
/* Only raise the observed High-profile level 3.0 declaration to 3.1.
   No encoding parameters or slice bytes change; never lower a level. */
static void stabilize_h264_level(unsigned char *p, size_t n)
{
    for (size_t i = 0; i < n;) {
        size_t prefix = nal_prefix(p + i, n - i);
        if (!prefix) {
            i++;
            continue;
        }
        size_t start = i + prefix, end = start;
        while (end < n && !nal_prefix(p + end, n - end))
            end++;
        if (end - start >= 4 && (p[start] & 31) == 7 &&
            (p[start + 1] != 100 || p[start + 3] > 31)) {
            source_guard_blocked = 1;
            carplay_ready = 0;
            event("ERROR", "H264_SOURCE_REJECTED profile=%u level=%u; phone recovery requested",
                  p[start + 1], p[start + 3]);
            marker("phone-restart", "unsupported_h264_configuration");
            return;
        }
        if (end - start >= 4 && (p[start] & 31) == 7 && p[start + 1] == 100 && p[start + 3] == 30) {
            p[start + 3] = 31;
            event("STAGE", "H264_LEVEL_NORMALIZED from=30 to=31");
        }
        i = end;
    }
}
static void cache_source_parameters(const unsigned char *p, size_t n)
{
    for (size_t i = 0; i < n;) {
        size_t prefix = nal_prefix(p + i, n - i);
        if (!prefix || i + prefix >= n) {
            i++;
            continue;
        }
        size_t end = i + prefix + 1;
        while (end < n && !nal_prefix(p + end, n - end))
            end++;
        unsigned type = p[i + prefix] & 31;
        if ((type == 7 || type == 8) && end - i <= sizeof(source_sps)) {
            unsigned char *out = type == 7 ? source_sps : source_pps;
            size_t *size = type == 7 ? &source_sps_size : &source_pps_size;
            memcpy(out, p + i, end - i);
            *size = end - i;
        }
        i = end;
    }
}
static int send_source_idr(const unsigned char *p, size_t n)
{
    size_t sps = has_nal(p, n, 7) ? 0 : source_sps_size;
    size_t pps = has_nal(p, n, 8) ? 0 : source_pps_size;
    if ((!has_nal(p, n, 7) && !sps) || (!has_nal(p, n, 8) && !pps)) {
        event("WARN", "CARPLAY_IDR_MISSING_PARAMETERS; requesting fresh configuration");
        live_dropped++;
        return 1;
    }
    if (!sps && !pps)
        return send_video(p, n) ? -1 : 0;
    unsigned char *unit = malloc(sps + pps + n);
    if (!unit)
        return -1;
    memcpy(unit, source_sps, sps);
    memcpy(unit + sps, source_pps, pps);
    memcpy(unit + sps + pps, p, n);
    int result = send_video(unit, sps + pps + n);
    free(unit);
    event("STAGE", "CARPLAY_DECODER_CONFIG_RESTORED sps_bytes=%zu pps_bytes=%zu", sps, pps);
    return result ? -1 : 0;
}
/* Ask the live CarPlay session for a new IDR; never retain a trip's GOP. */
static void invalidate_video(void)
{
    live_synced = 0;
    refresh_requested = 0;
    last_keyframe_request_ms = 0;
    idr_wait_since = 0;
    waiting_last = 0;
    startup_refresh_at = 0;
    transition_ready_until = 0;
    waiting_started = 0;
    waiting_pos = 8;
    /* Remove unsent video on HMI loss; finish an already-started SDL packet. */
    struct tx_item **at = &tx_head;
    tx_tail = NULL;
    while (*at) {
        struct tx_item *item = *at;
        if (item->video && !item->offset) {
            *at = item->next;
            tx_bytes -= item->size;
            if (video_guard_sent > video_guard_acked)
                video_guard_sent--;
            free(item);
        } else {
            tx_tail = item;
            at = &item->next;
        }
    }
}

static int request_keyframe(void)
{
    uint64_t ms = mono_ms();
    int initial = aa_mode && aa_initial_focus_at && ms >= aa_initial_focus_at &&
                  registered && hmi_full && video_ack && !video_ending;
    if (!initial && aa_mode && aa_video_focus == 1)
        return 0;
    if (!initial && (!carplay_ready ||
        (!source_probe_at && (!video_ack || !hmi_full || (live_synced && !refresh_requested)))))
        return 0;
    /* Keep displaying the card while the phone settles. Do not change codec
       until a complete, fresh IDR proves the source can supply a picture. */
    if (!source_probe_at && smooth_transitions && video_source == 1 &&
        ms - phone_ready_since < 2000)
        return 0;
    if (last_keyframe_request_ms && ms - last_keyframe_request_ms < 2000)
        return 0;
    for (unsigned i = 0; i < IPC_CLIENTS; i++) {
        if (clients[i].fd < 0 || clients[i].type != (aa_mode ? 5U : 3U))
            continue;
        unsigned char packet[28];
        unsigned words[7] = {0x55aa55aa, 12, 6, ~6U, 4, 12, 12};
        if (aa_mode) {
            words[2] = 9;
            words[3] = aa_header_zero ? 0 : ~9U;
        }
        for (unsigned w = 0; w < 7; w++)
            for (unsigned b = 0; b < 4; b++)
                packet[w * 4 + b] = (unsigned char)(words[w] >> (8 * b));
        ssize_t n = ipc_send(&clients[i], packet, sizeof(packet)) ? -1 : (ssize_t)sizeof(packet);
        /* A liveness probe accepts any valid video reply. It must not start
           the independent decoder synchronization deadline. */
        if (initial) {
            aa_initial_focus_at = 0;
            aa_initial_focus_allowed = 0;
            if (n >= 0 && aa_video_focus == 1) {
                aa_video_focus = 2;
                aa_resume_at = ms;
            }
            projection_event(n >= 0 ? "INITIAL_VIDEO_REQUEST" : "INITIAL_REQUEST_FAILED");
            event("STAGE", "AA_INITIAL_VIDEO_REQUEST queued=%d", n >= 0);
        }
        if (!initial && !source_probe_at && !idr_wait_since && (!live_synced || refresh_requested))
            idr_wait_since = ms;
        last_keyframe_request_ms = ms;
        event("STAGE", "CARPLAY_REQUEST_KEYFRAME command=12 sent=%zd", n);
        return n == (ssize_t)sizeof(packet) ? 0 : -1;
    }
    return 0;
}
static int live_packet(unsigned command, const unsigned char *p, size_t n)
{
    if (command == 0xf1 && n == 4)
        event("IPC", "REGISTER client_type=%u", le32(p));
    else if (command == 5 && n == 4) {
        event("IPC", "CARPLAY_PHASE phase=%u", le32(p));
        if (le32(p) == 1) {
            source_guard_blocked = 0;
            carplay_ready = 0;
            phone_ready_since = 0;
            transition_ready_until = 0;
            source_sps_size = source_pps_size = 0;
            invalidate_video();
        }
        if (le32(p) == 3 && !source_guard_blocked) {
            if (!carplay_ready) {
                phone_ready_since = mono_ms();
                source_video_at = phone_ready_since;
                source_probe_at = 0;
            }
            carplay_ready = 1;
        }
        if (le32(p) == 102) {
            carplay_ready = 0;
            phone_ready_since = 0;
            transition_ready_until = 0;
            source_sps_size = source_pps_size = 0;
            invalidate_video();
        }
    } else if (command == 6 && n >= 8 && le32(p) == n - 8 && le32(p + 4) == 1) {
        p += 8;
        n -= 8;
        if (n == 8)
            event("IPC", "VIDEO_DIMENSIONS width=%u height=%u", le32(p), le32(p + 4));
        if (n < 5 || memcmp(p, "\0\0\0\1", 4))
            return 0;
        cache_source_parameters(p, n);
        /* Opt-in, bounded diagnostic clip. Include predictive frames: the first
         * IDR after AA focus acquisition may contain only the blank transition. */
        if (source_sequence_frames) {
            if (mono_ms() > source_sequence_until || n > 2097152 - source_sequence_bytes) {
                source_sequence_frames = 0;
            } else {
                int fd = open(source_sequence_path, O_WRONLY | O_APPEND | O_CLOEXEC);
                FILE *f = fd < 0 ? NULL : fdopen(fd, "ab");
                int ok = 0;
                if (f) {
                    ok = fwrite(p, 1, n, f) == n;
                    if (fclose(f))
                        ok = 0;
                } else if (fd >= 0)
                    close(fd);
                source_sequence_bytes += n;
                if (!ok)
                    source_sequence_frames = 0;
                else
                    source_sequence_frames--;
            }
            if (!source_sequence_frames) {
                event("INFO", "SOURCE_SEQUENCE stopped bytes=%zu", source_sequence_bytes);
                source_sequence_path = NULL;
            }
        }
        if (marked("capture-source") && !source_snapshot_path)
            source_snapshot_path = usb_logging ? NULL : getenv("YAMAHA_SOURCE_SNAPSHOT");
        /* Optional diagnostic filter: transition IDRs are often tiny/blank.
         * This is only a size heuristic, never a video forwarding rule. */
        if (source_snapshot_path && marked("capture-source") &&
            (!aa_mode || !marked("capture-aa-content") || marked("capture-sequence") || n > 4096) &&
            n <= 131072 && has_nal(p, n, 5) && (has_nal(p, n, 7) || source_sps_size) &&
            (has_nal(p, n, 8) || source_pps_size)) {
            int fd = open(source_snapshot_path, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
            FILE *f = fd < 0 ? NULL : fdopen(fd, "wb");
            int ok = 0;
            if (f) {
                ok = 1;
                if (!has_nal(p, n, 7) &&
                    fwrite(source_sps, 1, source_sps_size, f) != source_sps_size)
                    ok = 0;
                if (!has_nal(p, n, 8) &&
                    fwrite(source_pps, 1, source_pps_size, f) != source_pps_size)
                    ok = 0;
                if (fwrite(p, 1, n, f) != n)
                    ok = 0;
                if (fclose(f))
                    ok = 0;
            } else if (fd >= 0)
                close(fd);
            event(ok ? "INFO" : "ERROR", "SOURCE_SNAPSHOT saved=%d idr_bytes=%zu; one_shot=1", ok,
                  n);
            if (ok && marked("capture-sequence")) {
                source_sequence_path = source_snapshot_path;
                source_sequence_frames = 89;
                source_sequence_bytes = n + source_sps_size + source_pps_size;
                source_sequence_until = mono_ms() + 10000;
                unmark("capture-sequence");
                event("INFO",
                      "SOURCE_SEQUENCE started max_frames=90 max_bytes=2097152 max_ms=10000");
            }
            char marker_path[4096];
            if (runtime_dir && snprintf(marker_path, sizeof(marker_path), "%s/capture-source",
                                        runtime_dir) < (int)sizeof(marker_path))
                unlink(marker_path);
            source_snapshot_path = NULL;
        }
        source_video_at = mono_ms();
        source_probe_at = 0;
        if (!carplay_ready) {
            projection_event("SOURCE_VIDEO");
            phone_ready_since = mono_ms();
        }
        carplay_ready = 1; /* A real video packet also proves wireless source readiness. */
        if (smooth_transitions && video_ack && hmi_full && video_source == 1 &&
            mono_ms() - phone_ready_since >= 2000 && has_nal(p, n, 5) &&
            (has_nal(p, n, 7) || source_sps_size) && (has_nal(p, n, 8) || source_pps_size) &&
            n <= 131072) {
            transition_ready_until = mono_ms() + 1000;
            if (inplace_transitions && !video_ending) {
                /* The incoming IDR is the handoff, not a promise of a later
                   frame. Remove queued waiting pictures before enqueueing it. */
                invalidate_video();
                video_source = 2;
                event("STAGE", "VIDEO_SOURCE_INPLACE from=1 to=2 bytes=%zu", n);
            } else
                event(
                    "STAGE",
                    "CARPLAY_TRANSITION_READY bytes=%zu; requesting fresh IDR after video restart",
                    n);
        }
        if (!video_ack || !hmi_full || video_source == 1 || video_ending) {
            live_synced = 0;
            live_dropped++;
            return 0;
        }
        int idr = has_nal(p, n, 5);
        if (!live_synced && !idr) {
            live_dropped++;
            return 0;
        }
        if (idr && (!live_synced || refresh_requested)) {
            int result = send_source_idr(p, n);
            if (result < 0) {
                ccu_failed = 1;
                return 0;
            }
            if (result > 0 || video_guard_blocked)
                return 0;
            if (aa_mode) {
                aa_initial_focus_allowed = 0;
                aa_initial_focus_at = 0;
            }
            if (!live_synced) {
                projection_event("IDR_QUEUED");
                startup_refresh_at = aa_mode ? 0 : mono_ms() + startup_refresh_ms;
                event("STAGE", "LIVE_CARPLAY_IDR bytes=%zu dropped_before_start=%lu", n,
                      live_dropped);
            } else
                event("STAGE", "LIVE_CARPLAY_REFRESH_IDR bytes=%zu", n);
            live_synced = 1;
            refresh_requested = 0;
            idr_wait_since = 0;
        } else if (send_video(p, n)) {
            ccu_failed = 1;
            return 0;
        }
        video_source = 2;
        live_frames++;
        if (live_frames == 1 || live_frames % 100 == 0)
            event("INFO", "LIVE_CARPLAY frames=%lu bytes=%zu", live_frames, n);
    }
    return 0;
}
static int aa_video(const unsigned char *p, size_t n)
{
    if (n < 12 || le32(p) != n - 8 || le32(p + 4) != 1 || !nal_prefix(p + 8, n - 8))
        return 0;
    if (aa_video_focus == 1)
        return 0; /* Late queued frames cannot cancel focus loss. */
    unsigned char *out = NULL;
    size_t used = 0;
    for (size_t i = 8; i < n;) {
        size_t prefix = nal_prefix(p + i, n - i);
        if (!prefix || i + prefix >= n)
            goto invalid;
        size_t a = i + prefix, end = a + 1;
        while (end < n && !nal_prefix(p + end, n - end))
            ++end;
        unsigned kind = p[a] & 31;
        if (kind == 7 || (i == 8 && prefix == 3)) {
            if (!out) {
                out = malloc(MAX_FRAME);
                if (!out)
                    goto invalid;
                memcpy(out, p, i);
                used = i;
            }
        }
        if (kind == 7) {
            unsigned char sps[816];
            int bytes = aa_crop_sps(p + a, end - a, sps, &aa_geometry);
            if (!bytes || used + 4 + (size_t)bytes > MAX_FRAME)
                goto invalid;
            memcpy(out + used, "\0\0\0\1", 4);
            used += 4;
            memcpy(out + used, sps, (size_t)bytes);
            used += (size_t)bytes;
            aa_sps_ready = 1;
        } else {
            if ((kind == 1 || kind == 5) && !aa_sps_ready)
                goto invalid;
            if (out) {
                if (used + 1 + end - i > MAX_FRAME)
                    goto invalid;
                if (i == 8 && prefix == 3)
                    out[used++] = 0;
                memcpy(out + used, p + i, end - i);
                used += end - i;
            }
        }
        i = end;
    }
    if (out)
        aa_put32(out, (unsigned)used - 8);
    if (aa_sps_ready && aa_video_focus == 2 &&
        has_nal((out ? out : p) + 8, (out ? used : n) - 8, 5)) {
        aa_video_focus = 0;
        aa_resume_at = 0;
        event("STAGE", "AA_VIDEO_ACTIVE fresh_idr=1");
    }
    int result = aa_sps_ready ? live_packet(6, out ? out : p, out ? used : n) : 0;
    free(out);
    return result;
invalid:
    free(out);
    aa_sps_ready = 0;
    carplay_ready = 0;
    source_sps_size = source_pps_size = 0;
    invalidate_video();
    event("WARN", "AA_VIDEO_REJECTED expected=800x480_h264");
    return 0;
}
static void close_client(struct ipc_client *c)
{
    if (c->type == (aa_mode ? 5U : 3U)) {
        source_sequence_frames = 0;
        source_sequence_path = NULL;
    }
    if (aa_mode && c->type == 5) {
        aa_initial_focus_at = 0;
        aa_initial_focus_allowed = 0;
        aa_video_focus = 0;
        aa_resume_at = 0;
        aa_back_at = 0;
        aa_start_pending = 0;
        aa_sps_ready = 0;
        carplay_ready = 0;
        source_sps_size = source_pps_size = 0;
        invalidate_video();
    }
    if (c->type == 32) {
        memset(iap2_pending, 0, sizeof(iap2_pending));
        if (marked("iap2-wifi-active"))
            marker("iap2-wifi-request", "1\n");
    }
    if (c->type == 3) {
        unmark("iap2-wifi-request");
        unmark("iap2-wifi-active");
        memset(iap2_pending, 0, sizeof(iap2_pending));
        source_guard_blocked = 0;
        carplay_ready = 0;
        phone_ready_since = 0;
        transition_ready_until = 0;
        source_sps_size = source_pps_size = 0;
        invalidate_video();
    }
    close(c->fd);
    free(c->data);
    c->fd = -1;
    c->data = NULL;
    c->used = c->out_used = c->out_sent = 0;
    c->type = 0;
}
static int live_pending(void)
{
    iap2_route_tick();
    if (marked("request-carplay-ui")) {
        char path[4096];
        if (snprintf(path, sizeof(path), "%s/request-carplay-ui", runtime_dir) <
                (int)sizeof(path) &&
            !unlink(path)) {
            if (diagnostic_show_ui())
                event("PAIRING", "SHOW_UI_TEST skipped=1");
        }
    }
    int fd = accept4(ipc_listener, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (fd >= 0) {
        unsigned i;
        for (i = 0; i < IPC_CLIENTS; i++)
            if (clients[i].fd < 0)
                break;
        if (i == IPC_CLIENTS)
            close(fd);
        else {
            clients[i].data = malloc(MAX_FRAME + 16);
            if (!clients[i].data) {
                close(fd);
                return -1;
            }
            clients[i].used = 0;
            clients[i].type = 0;
            clients[i].fd = fd;
            event("IPC", "CLIENT_CONNECTED slot=%u", i);
        }
    } else if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)
        return -1;
    if (!video_ack || !hmi_full)
        live_synced = 0;
    if (request_keyframe())
        event("WARN", "KEYFRAME_REQUEST_FAILED; retrying phone client");
    for (unsigned i = 0; i < IPC_CLIENTS; i++) {
        struct ipc_client *c = &clients[i];
        if (c->fd < 0)
            continue;
        if (c->out_used) {
            ssize_t sent = send(c->fd, c->out + c->out_sent, c->out_used - c->out_sent,
                                MSG_DONTWAIT | MSG_NOSIGNAL);
            if (sent > 0)
                c->out_sent += (size_t)sent;
            else if (sent == 0 || (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK)) {
                close_client(c);
                continue;
            }
            if (c->out_sent == c->out_used)
                c->out_used = c->out_sent = 0;
            else if (mono_ms() - c->out_since > 2000) {
                event("WARN", "PHONE_IPC_WRITE_TIMEOUT");
                close_client(c);
                continue;
            }
        }
        ssize_t r = recv(c->fd, c->data + c->used, MAX_FRAME + 16 - c->used, MSG_DONTWAIT);
        if (r < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
            continue;
        if (r <= 0) {
            event("IPC", "CLIENT_DISCONNECTED slot=%u", i);
            close_client(c);
            continue;
        }
        c->used += (size_t)r;
        while (c->used >= 16) {
            unsigned command = le32(c->data + 8);
            uint32_t n = le32(c->data + 4);
            if (le32(c->data) != 0x55aa55aa ||
                (le32(c->data + 12) != ~command && !(aa_mode && !le32(c->data + 12))) ||
                n > MAX_FRAME) {
                event("ERROR", "INVALID_IPC_HEADER slot=%u", i);
                close_client(c);
                break;
            }
            if (c->used < n + 16)
                break;
            if (command == 0xf1 && n == 4) {
                c->type = le32(c->data + 16);
                if (phone_auto && !aa_mode && c->type == 5) {
                    close_client(c);
                    break;
                }
                if (aa_mode) {
                    if (c->type != 5) {
                        close_client(c);
                        break;
                    }
                    for (unsigned j = 0; j < IPC_CLIENTS; j++)
                        if (j != i && clients[j].fd >= 0 && clients[j].type == 5)
                            close_client(&clients[j]);
                    aa_video_focus = 0;
                    aa_resume_at = 0;
                    aa_back_at = 0;
                    aa_sps_ready = 0;
                    carplay_ready = 0;
                    source_sps_size = source_pps_size = 0;
                    invalidate_video();
                    aa_start_check = le32(c->data + 12);
                    if (aa_mode == 2) {
                        aa_start_pending = 1;
                        event("STAGE", "AA_WAIT_RFCOMM");
                    } else if (aa_start(c, aa_start_check)) {
                        close_client(c);
                        break;
                    }
                }
                if (c->type == 32 || c->type == 34) {
                    for (unsigned j = 0; j < IPC_CLIENTS; j++)
                        if (j != i && clients[j].fd >= 0 && clients[j].type == c->type)
                            close_client(&clients[j]);
                    if (c->type == 32)
                        unmark("iap2-wifi-request");
                }
                if (c->type == 3) {
                    char generation[96];
                    snprintf(generation, sizeof(generation), "%ld:%llu:%u\n", (long)getpid(),
                             (unsigned long long)mono_ms(), ++phone_generation);
                    marker("phone-generation", generation);
                    unmark("iap2-wifi-request");
                    unmark("iap2-wifi-active");
                    memset(iap2_pending, 0, sizeof(iap2_pending));
                    for (unsigned j = 0; j < IPC_CLIENTS; j++)
                        if (j != i && clients[j].fd >= 0 && clients[j].type == 3)
                            close_client(&clients[j]);
                    carplay_ready = 0;
                    phone_ready_since = 0;
                    transition_ready_until = 0;
                    source_sps_size = source_pps_size = 0;
                    invalidate_video();
                }
            }
            ipc_received_metadata(c->type, command, c->data + 16, n);
            bluetooth_handover_request(c->type, command, c->data + 16, n);
            route_iap2_wifi(c, command, c->data + 16, n);
            if (iap2_wifi_router_test && c->type == 3 && command == 5 && n == 4 &&
                le32(c->data + 16) == 2)
                marker("iap2-wifi-request", "1\n");
            if (command == 0x59414d42 && n >= 6 && c->type == 0x59414d41 &&
                (hmi_full || (registered && le32(c->data + 16) == 2))) {
                diagnostic_rpc(le32(c->data + 16), c->data + 20, n - 4);
            }
            if (command == 0x59414d41 && n == 4 && c->type == 0x59414d41 && hmi_full) {
                unsigned action = le32(c->data + 16);
                if (action <= 1)
                    show_navigation((int)action);
                else if (action >= 10 && action <= 16)
                    forward_button(action - 10);
            }
            if (stable_h264_level && !source_guard_blocked && command == 6 && c->type == 3 &&
                n >= 8 && le32(c->data + 16) == n - 8 && le32(c->data + 20) == 1)
                stabilize_h264_level(c->data + 24, n - 8);
            if (aa_mode && c->type == 5 && (command == 9 || command == 6)) {
                const unsigned char *body = c->data + 16;
                if (n == 12 && le32(body) == 4 && le32(body + 4) == 12) {
                    unsigned control = le32(body + 8);
                    /* OEM onVideoFocusChanged(2) emits 3; non-ignored
                     * onVideoStateChanged emits 500 (start) / 501 (stop). */
                    if (control == 3) {
                        aa_initial_focus_at = 0;
                        aa_initial_focus_allowed = 0;
                    } else if ((control == 500 || control == 501) &&
                               aa_initial_focus_allowed && !aa_initial_focus_at) {
                        aa_initial_focus_at = mono_ms() + 2000;
                    }
                    if (control == 3 || (control == 501 && aa_video_focus != 2)) {
                        if (aa_video_focus != 1)
                            projection_event(control == 3 ? "FOCUS_YIELDED" : "VIDEO_STOP");
                        aa_video_focus = 1;
                        aa_resume_at = 0;
                        aa_back_at = 0;
                        invalidate_video();
                        event("STAGE", "AA_VIDEO_BACKGROUND control=%u; waiting_for_user=1",
                              control);
                    } else if (control == 500 && aa_video_focus == 1) {
                        aa_video_focus = 2;
                        aa_resume_at = mono_ms();
                        last_keyframe_request_ms = aa_resume_at;
                        event("STAGE", "AA_VIDEO_RESUMING control=500; waiting_for_idr=1");
                    }
                }
                if (aa_video(body, n))
                    return -1;
            }
            if (c->type == 3 && (command != 6 || !source_guard_blocked) &&
                live_packet(command, c->data + 16, n))
                return -1;
            memmove(c->data, c->data + n + 16, c->used - n - 16);
            c->used -= n + 16;
        }
    }
    return 0;
}
static int tx_writable(void)
{
    return tx_head && (!video_guard || !aa_mode || !tx_head->video || tx_head->offset ||
                       video_guard_written < video_guard_acked + 4);
}
/* Wait for either CCU input or any CarPlay client, without a USB-only delay. */
static int wait_live(void)
{
    struct pollfd fds[IPC_CLIENTS + 2];
    unsigned count = 0;
    fds[count++] = (struct pollfd){link_fd, POLLIN | (tx_writable() ? POLLOUT : 0), 0};
    fds[count++] = (struct pollfd){ipc_listener, POLLIN, 0};
    for (unsigned i = 0; i < IPC_CLIENTS; i++)
        if (clients[i].fd >= 0)
            fds[count++] =
                (struct pollfd){clients[i].fd, POLLIN | (clients[i].out_used ? POLLOUT : 0), 0};
    int result = poll(fds, count, 100);
    if (result < 0 && errno != EINTR) {
        event("ERROR", "LIVE_POLL errno=%d", errno);
        return -1;
    }
    return 0;
}
static void video_stats(void)
{
    static uint64_t previous_ms;
    static unsigned long frames, bytes, acks;
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t now = (uint64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
    if (!previous_ms) {
        previous_ms = now;
        return;
    }
    if (now - previous_ms < 1000)
        return;
    event("PERF", "VIDEO interval_ms=%llu frames=%lu bytes=%lu acks=%lu total_frames=%lu",
          (unsigned long long)(now - previous_ms), video_tx_count - frames, video_tx_bytes - bytes,
          video_ack_count - acks, video_tx_count);
    previous_ms = now;
    frames = video_tx_count;
    bytes = video_tx_bytes;
    acks = video_ack_count;
}
static void flush_tx(void);
/* A planned restart must end the current RPC session using its exact hash.
   The USB endpoint disappearing alone did not release the app on this CCU. */
static void end_rpc_service(void)
{
    if (link_fd < 0 || !session || !have_rpc_hash || ccu_failed)
        return;
    invalidate_video();
    ending_rpc = 1;
    end_rpc_ack = 0;
    if (video_ack)
        send_frame(version, 0, 11, 4, session, rpc_hash, sizeof(rpc_hash));
    send_frame(version, 0, 7, 4, session, rpc_hash, sizeof(rpc_hash));
    uint64_t deadline = mono_ms() + 500;
    while (mono_ms() < deadline && !ccu_failed && !end_rpc_ack) {
        flush_tx();
        if (read_pending(10))
            break;
    }
    event("STAGE", "RPC_END_SERVICE session=%u acknowledged=%d", session, end_rpc_ack);
    ending_rpc = 0;
}
/* CCU recovery keeps the phone session alive when possible. */
static void recover_ccu(const char *reason)
{
    event("RECOVERY", "CCU reason=%s retry_ms=%u phone_kept=1", reason, retry_delay);
    if (!strcmp(reason, "transport_preparing"))
        end_rpc_service();
    if (link_fd >= 0)
        close(link_fd);
    have_rpc_hash = 0;
    link_fd = -1;
    clear_tx();
    rx_len = 0;
    registered = hmi_full = video_requested = video_ack = buttons_requested = 0;
    button_accepted = button_finished = 0;
    memset(button_attempts, 0, sizeof(button_attempts));
    memset(button_retry_at, 0, sizeof(button_retry_at));
    video_source = video_ending = 0;
    video_end_deadline = 0;
    session = 0;
    version = 4;
    next_message = 1;
    ccu_failed = 0;
    session_deadline = video_deadline = video_retry_at = 0;
    invalidate_video();
    retry_at = mono_ms() + retry_delay;
    if (retry_delay < 32000) {
        retry_delay *= 2;
        if (retry_delay > 32000)
            retry_delay = 32000;
    }
    marker("ccu-fd", "closed\n");
    if (!marked("ccu-preparing"))
        marker("ccu-recover", reason);
}
static void flush_tx(void)
{
    size_t budget = 65536;
    while (tx_writable() && budget && !ccu_failed) {
        struct tx_item *item = tx_head;
        size_t n = item->size - item->offset;
        if (n > budget)
            n = budget;
        ssize_t wrote = write(link_fd, item->data + item->offset, n);
        if (wrote < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
            break;
        if (wrote <= 0) {
            ccu_failed = 1;
            break;
        }
        item->offset += (size_t)wrote;
        budget -= (size_t)wrote;
        tx_progress = mono_ms();
        if (item->offset == item->size) {
            if (item->video)
                video_guard_written++;
            tx_head = item->next;
            tx_bytes -= item->size;
            free(item);
            if (!tx_head)
                tx_tail = NULL;
        }
    }
    if (tx_head && mono_ms() - tx_progress > 2000) {
        event("ERROR", "CCU_TX_STALLED");
        ccu_failed = 1;
    }
}
static void wireless_source_tick(uint64_t now)
{
    if (wireless_video_watchdog && carplay_ready && source_video_at && now >= source_video_at &&
        now - source_video_at >= 2000 && runtime_dir) {
        char path[4096], mode[16] = {0};
        if (snprintf(path, sizeof(path), "%s/phone-mode", runtime_dir) < (int)sizeof(path)) {
            FILE *f = fopen(path, "r");
            if (f) {
                if (!fgets(mode, sizeof(mode), f))
                    mode[0] = 0;
                fclose(f);
            }
        }
        if (!strcmp(mode, "wireless\n")) {
            if (!source_probe_at) {
                source_probe_at = now;
                last_keyframe_request_ms = 0;
                event("STAGE", "WIRELESS_VIDEO_PROBE silent_ms=%llu",
                      (unsigned long long)(now - source_video_at));
                request_keyframe();
            } else if (now - source_probe_at >= 2000) {
                carplay_ready = 0;
                phone_ready_since = 0;
                transition_ready_until = 0;
                source_sps_size = source_pps_size = 0;
                invalidate_video();
                marker("phone-restart", "wireless_video_unresponsive");
                event("RECOVERY",
                      "PHONE reason=wireless_video_unresponsive; waiting card requested");
                source_probe_at = 0;
            }
        }
    }
}
/* Supervisor selects one receiver family; acknowledge only after stale IPC
 * clients and video state have been discarded. CCU/SDL stays connected. */
static void auto_phone_tick(uint64_t now)
{
    static uint64_t next;
    static char selected[64], peer[18];
    if (!phone_auto || !runtime_dir || now < next)
        return;
    next = now + 250;
    char path[4096], value[64] = {0};
    if (snprintf(path, sizeof(path), "%s/phone-selection", runtime_dir) >= (int)sizeof(path))
        return;
    int fd = open(path, O_RDONLY | O_NOFOLLOW);
    if (fd < 0)
        return;
    ssize_t n = read(fd, value, sizeof(value) - 1);
    close(fd);
    if (n <= 0 || n == (ssize_t)sizeof(value) - 1)
        return;
    unsigned mode = 0;
    if (!strcmp(value, "carplay\n"))
        mode = 0;
    else if (!strcmp(value, "aa-usb\n"))
        mode = 1;
    else if (n == 30 && !memcmp(value, "aa-wireless\n", 12) && value[29] == '\n') {
        for (unsigned i = 0; i < 17; i++)
            if (i % 3 == 2 ? value[12 + i] != ':'
                           : !strchr("0123456789abcdefABCDEF", value[12 + i]))
                return;
        mode = 2;
    } else
        return;
    if (!strcmp(value, selected)) {
        if (!marked("phone-selected"))
            marker("phone-selected", mode == 2   ? "aa-wireless\n"
                                     : mode == 1 ? "aa-usb\n"
                                                 : "carplay\n");
        return;
    }
    for (unsigned i = 0; i < IPC_CLIENTS; i++)
        if (clients[i].fd >= 0 && (clients[i].type == 3 || clients[i].type == 5 ||
                                   clients[i].type == 32 || clients[i].type == 34))
            close_client(&clients[i]);
    aa_mode = mode;
    aa_initial_focus_at = 0;
    aa_initial_focus_allowed = 0;
    aa_video_focus = 0;
    aa_resume_at = 0;
    aa_back_at = 0;
    aa_start_pending = 0;
    aa_sps_ready = 0;
    carplay_ready = 0;
    phone_ready_since = 0;
    transition_ready_until = 0;
    source_guard_blocked = 0;
    source_sps_size = source_pps_size = 0;
    source_probe_at = 0;
    startup_refresh_at = 0;
    invalidate_video();
    iap2_wifi_router_test = mode ? 0 : auto_cp_router;
    wireless_video_watchdog = mode ? 0 : auto_cp_watchdog;
    startup_refresh_ms = mode ? 0 : auto_cp_refresh;
    if (mode == 2) {
        memcpy(peer, value + 12, 17);
        peer[17] = 0;
        aa_peer = peer;
    }
    memcpy(selected, value, (size_t)n + 1);
    marker("phone-selected", mode == 2 ? "aa-wireless\n" : mode == 1 ? "aa-usb\n" : "carplay\n");
    event("STAGE", "PHONE_PLATFORM selected=%s",
          mode == 2   ? "aa-wireless"
          : mode == 1 ? "aa-usb"
                      : "carplay");
}
static void connection_tick(void)
{
    uint64_t now = mono_ms();
    auto_phone_tick(now);
    if (aa_start_pending && !access(aa_rfcomm_path, F_OK)) {
        aa_start_pending = 0;
        for (unsigned i = 0; i < IPC_CLIENTS; i++)
            if (clients[i].fd >= 0 && clients[i].type == 5) {
                if (aa_start(&clients[i], aa_start_check))
                    close_client(&clients[i]);
                break;
            }
    }
    wireless_source_tick(now);
    if (marked("ccu-preparing") && link_fd >= 0)
        recover_ccu("transport_preparing");
    if (ccu_failed)
        recover_ccu("protocol_or_transport");
    if (link_fd < 0 && now >= retry_at && !marked("ccu-preparing") && !marked("ccu-recover")) {
        const char *state_path = getenv("YAMAHA_CCU_STATE");
        char state[32] = {0};
        if (state_path) {
            FILE *f = fopen(state_path, "r");
            if (f) {
                if (!fgets(state, sizeof(state), f))
                    state[0] = 0;
                fclose(f);
            }
        }
        if (state_path && strncmp(state, "CONFIGURED", 10)) {
            retry_at = now + 1000;
            return;
        }
        link_fd = open(device_path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
        if (link_fd < 0) {
            recover_ccu("open_failed");
            return;
        }
        /* Dispose of replies left in the endpoint by the previous process
           before starting a new session; they cannot belong to this request. */
        size_t drained = 0;
        while (drained < 256 * 1024) {
            ssize_t count = read(link_fd, rx, sizeof(rx));
            if (count <= 0)
                break;
            drained += (size_t)count;
        }
        if (drained)
            event("INFO", "STALE_USB_INPUT_DRAINED bytes=%zu", drained);
        rx_len = 0;
        marker("ccu-fd", "open\n");
        last_ccu_rx = now;
        session_deadline = now + 8000;
        event("STAGE", "USB_DEVICE_OPEN; sending SDL v1 RPC StartService");
        if (send_frame(1, 0, 7, 1, 0, NULL, 0))
            ccu_failed = 1;
    }
    if (link_fd < 0)
        return;
    if ((session_deadline && now >= session_deadline) || now - last_ccu_rx > 15000) {
        recover_ccu("response_timeout");
        return;
    }
    if (registered && now - last_ccu_rx < 5000)
        retry_delay = 1000;
    if (video_requested && !video_ack && video_deadline && now >= video_deadline) {
        event("WARN", "VIDEO_ACK_TIMEOUT");
        video_requested = 0;
        video_retry_at = now + 2000;
    }
    if (video_ending && now >= video_end_deadline) {
        recover_ccu("video_end_timeout");
        return;
    }
    int desired_source = carplay_ready ? 2 : 1;
    if (smooth_transitions && video_source == 1 && carplay_ready &&
        (inplace_transitions || now >= transition_ready_until))
        desired_source = 1;
    if (video_ack && hmi_full && video_source && video_source != desired_source) {
        int previous = video_source;
        if (inplace_transitions) {
            invalidate_video();
            video_source = desired_source;
            event("STAGE", "VIDEO_SOURCE_INPLACE from=%d to=%d", previous, desired_source);
        } else {
            invalidate_video();
            video_ack = 0;
            video_ending = 1;
            video_end_deadline = now + 8000;
            /* Keep any partially written SDL packet ahead of EndService, discard
               all untouched video, and wait for ACK before the next StartService.
               The v4 mobile SDK sends the session hash for every service. */
            send_frame(version, 0, 11, 4, session, have_rpc_hash ? rpc_hash : NULL,
                       have_rpc_hash ? 4 : 0);
            event("STAGE", "VIDEO_SOURCE_SWITCH from=%d to=%d waiting_for_end_ack=1", previous,
                  carplay_ready ? 2 : 1);
        }
    }
    maybe_start_video();
    if (video_ack && hmi_full) {
        /* A phone reconnect may begin with a valid but black startup IDR.
           Request one more independent picture after startup has settled,
           using the same refresh as Home, without changing either session. */
        if (live_synced && carplay_ready && startup_refresh_at && now >= startup_refresh_at) {
            startup_refresh_at = 0;
            refresh_requested = 1;
            last_keyframe_request_ms = 0;
            event("STAGE", "CARPLAY_STARTUP_REFRESH reason=first_live_idr");
        }
        unsigned waiting_interval =
            waiting_clip
                ? 100
                : (smooth_transitions && waiting_started && now - waiting_started < 2000 ? 200
                                                                                         : 1000);
        if ((!carplay_ready || (smooth_transitions && video_source == 1)) && !live_synced &&
            waiting_frame && (!waiting_last || now - waiting_last >= waiting_interval)) {
            const unsigned char *picture = waiting_frame;
            size_t picture_size = waiting_size;
            if (waiting_clip) {
                if (waiting_pos == waiting_size)
                    waiting_pos = 8;
                picture_size = le32(waiting_frame + waiting_pos);
                picture = waiting_frame + waiting_pos + 4;
            }
            if (!send_video(picture, picture_size)) {
                if (waiting_clip)
                    waiting_pos += 4 + picture_size;
                if (!waiting_last)
                    event("STAGE", "WAITING_FOR_CARPLAY_FRAME");
                if (!waiting_started)
                    waiting_started = now;
                waiting_last = now;
                video_source = 1;
            }
        }
        if ((!live_synced || refresh_requested) && carplay_ready && idr_wait_since &&
            now >= idr_wait_since && now - idr_wait_since >= 10000 && now >= phone_retry_at) {
            event("RECOVERY", "PHONE reason=keyframe_timeout");
            marker("phone-restart", "keyframe_timeout");
            phone_retry_at = now + 30000;
            idr_wait_since = now;
        }
    }
}
static void health_tick(void)
{
    bluetooth_handover_tick();
    static uint64_t last;
    uint64_t now = mono_ms();
    if (now - last < 1000)
        return;
    last = now;
    char health[64];
    snprintf(health, sizeof(health), "%llu\n", (unsigned long long)(now / 1000));
    marker("bridge-heartbeat", health);
    marker("phone-state", carplay_ready ? "ready\n" : "waiting\n");
}
static int validate_clip(const unsigned char *data, size_t size)
{
    size_t pos = 8;
    unsigned count = 0;
    while (pos < size) {
        if (size - pos < 4)
            return -1;
        uint32_t n = le32(data + pos);
        pos += 4;
        if (n < 5 || n > 131072 || n > size - pos)
            return -1;
        if (memcmp(data + pos, "\0\0\0\1", 4))
            return -1;
        pos += n;
        count++;
    }
    return count ? (int)count : -1;
}
int main(int argc, char **argv)
{
    if (argc != 5 && argc != 6) {
        fprintf(stderr, "usage: %s DEVICE IDR.h264|--live LOGFILE SECONDS [TRACEFILE]\n", argv[0]);
        return 2;
    }
    log_path = strcmp(argv[3], "-") == 0 ? NULL : argv[3];
    const char *usb = getenv("YAMAHA_USB_DEBUG_LOGGING");
    usb_logging = log_path && usb && !strcmp(usb, "1");
    if (!usb_logging)
        log_file = log_path ? fopen(log_path, "a") : stdout;
    if (!usb_logging && !log_file) {
        perror("log");
        return 2;
    }
    if (!usb_logging && argc == 6) {
        trace_file = fopen(argv[5], "wb");
        if (!trace_file) {
            perror("trace");
            return 2;
        }
    }
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    int live = !strcmp(argv[2], "--live");
    live_mode = live;
    device_path = argv[1];
    runtime_dir = getenv("YAMAHA_RUNTIME");
    source_snapshot_path = usb_logging ? NULL : getenv("YAMAHA_SOURCE_SNAPSHOT");
    const char *handover = getenv("YAMAHA_BT_HANDOVER_TEST");
    bt_handover_test = handover && !strcmp(handover, "1");
    event("INFO", "BT_HANDOVER_TEST enabled=%d", bt_handover_test);
    const char *iap2_router = getenv("YAMAHA_IAP2_WIFI_ROUTER_TEST");
    iap2_wifi_router_test = iap2_router && !strcmp(iap2_router, "1");
    event("INFO", "IAP2_WIFI_ROUTER_TEST enabled=%d", iap2_wifi_router_test);
    const char *diagnostics = getenv("YAMAHA_IPC_DIAGNOSTICS");
    ipc_diagnostics = diagnostics && !strcmp(diagnostics, "1");
    if (usb_logging)
        event("INFO", "IPC_DIAGNOSTICS usb_opt_in=1 payload_logging=0");
    else
        event("INFO", "IPC_DIAGNOSTICS enabled=%d max_records=512 payload_logging=0",
              ipc_diagnostics);
    const char *guard = getenv("YAMAHA_VIDEO_ACK_GUARD");
    video_guard = guard && !strcmp(guard, "1");
    event("INFO", "VIDEO_ACK_GUARD enabled=%d window=4 diagnostic=1", video_guard);
    const char *level = getenv("YAMAHA_STABLE_H264_LEVEL");
    stable_h264_level = level && !strcmp(level, "1");
    const char *watchdog = getenv("YAMAHA_WIRELESS_VIDEO_WATCHDOG");
    wireless_video_watchdog = watchdog && !strcmp(watchdog, "1");
    event("INFO", "WIRELESS_VIDEO_WATCHDOG enabled=%d silence_ms=2000 probe_ms=2000",
          wireless_video_watchdog);
    event("INFO", "STABLE_H264_LEVEL enabled=%d observed_high_30_to_31_only=1", stable_h264_level);
    const char *smooth = getenv("YAMAHA_SMOOTH_TRANSITIONS");
    const char *inplace = getenv("YAMAHA_INPLACE_TRANSITIONS");
    inplace_transitions = inplace && !strcmp(inplace, "1");
    smooth_transitions = inplace_transitions || (smooth && !strcmp(smooth, "1"));
    const char *fast_refresh = getenv("YAMAHA_FAST_STARTUP_REFRESH");
    if (fast_refresh && !strcmp(fast_refresh, "1"))
        startup_refresh_ms = 500;
    event("INFO", "STARTUP_REFRESH delay_ms=%u", startup_refresh_ms);
    event("INFO", "INPLACE_TRANSITIONS enabled=%d experimental=1", inplace_transitions);
    event("INFO", "SMOOTH_TRANSITIONS enabled=%d", smooth_transitions);
    size_t idr_size = 0;
    unsigned char *idr = live ? NULL : load_file(argv[2], &idr_size);
    if (!live && (!idr || idr_size < 8)) {
        event("ERROR", "Cannot load H.264 sample %s", argv[2]);
        return 2;
    }
    phone_auto = getenv("YAMAHA_PHONE_AUTO") && !strcmp(getenv("YAMAHA_PHONE_AUTO"), "1");
    auto_cp_refresh = startup_refresh_ms;
    auto_cp_router = iap2_wifi_router_test;
    auto_cp_watchdog = wireless_video_watchdog;
    const char *aa = getenv("YAMAHA_AA_MODE");
    if (phone_auto && aa && *aa)
        return 2;
    if (aa && *aa) {
        if (!strcmp(aa, "usb"))
            aa_mode = 1;
        else if (!strcmp(aa, "wireless")) {
            aa_mode = 2;
            aa_peer = getenv("YAMAHA_AA_PEER");
            const char *rfcomm = getenv("YAMAHA_AA_RFCOMM_PATH");
            if (rfcomm && *rfcomm)
                aa_rfcomm_path = rfcomm;
            if (!aa_peer || strlen(aa_peer) != 17)
                return 2;
            for (unsigned i = 0; i < 17; i++) {
                if (i % 3 == 2 ? aa_peer[i] != ':' : !strchr("0123456789abcdefABCDEF", aa_peer[i]))
                    return 2;
            }
        } else
            return 2;
    }
    if (live && live_init()) {
        event("ERROR", "IPC_LISTEN errno=%d", errno);
        return 2;
    }
    if (live) {
        marker("ccu-fd", "closed\n");
        const char *waiting = getenv("YAMAHA_WAITING_FRAME");
        if (!waiting)
            waiting = inplace_transitions ? "/tmp/yamaha-sdl/waiting-inplace.frames"
                                          : "/tmp/yamaha-sdl/waiting.h264";
        waiting_frame = load_file(waiting, &waiting_size);
        waiting_clip = waiting_frame && waiting_size >= 8 && !memcmp(waiting_frame, "YCPAU001", 8);
        int valid =
            waiting_frame && waiting_size <= 131072 && has_nal(waiting_frame, waiting_size, 5);
        if (waiting_clip) {
            valid = validate_clip(waiting_frame, waiting_size) > 0;
            for (size_t pos = 8; valid && pos < waiting_size;) {
                size_t size = le32(waiting_frame + pos);
                pos += 4;
                valid = has_nal(waiting_frame + pos, size, 5) &&
                        has_nal(waiting_frame + pos, size, 7) &&
                        has_nal(waiting_frame + pos, size, 8);
                pos += size;
            }
            if (valid)
                event("INFO", "WAITING_ANIMATION fps=10 bytes=%zu", waiting_size);
        }
        if (!valid) {
            event("WARN", "WAITING_FRAME_UNAVAILABLE path=%s", waiting);
            free(waiting_frame);
            waiting_frame = NULL;
        }
    }
    int clip = !live && !memcmp(idr, "YCPAU001", 8);
    size_t clip_pos = 8;
    if (clip) {
        int frames = validate_clip(idr, idr_size);
        if (frames < 1) {
            event("ERROR", "Invalid recorded access-unit file");
            free(idr);
            return 2;
        }
        event("INFO", "SOURCE_RECORDED_CARPLAY frames=%d; playback at 20 fps, looping", frames);
    }
    event("INFO", "START device=%s video=%s video_bytes=%zu seconds=%s", argv[1], argv[2], idr_size,
          argv[4]);
    if (!live) {
        link_fd = open(argv[1], O_RDWR | O_NONBLOCK);
        if (link_fd < 0) {
            event("ERROR", "OPEN_DEVICE errno=%d (%s)", errno, strerror(errno));
            return 1;
        }
        event("STAGE", "USB_DEVICE_OPEN; sending SDL v1 RPC StartService");
        if (send_frame(1, 0, 7, 1, 0, NULL, 0))
            return 1;
    }
    int seconds = atoi(argv[4]);
    if (seconds < 0 || seconds > 3600)
        seconds = 30;
    struct timespec started;
    clock_gettime(CLOCK_MONOTONIC, &started);
    time_t until = started.tv_sec + seconds, last_heartbeat = 0;
    uint64_t last_video_ms = 0;
    while (!stopped) {
        if (live) {
            connection_tick();
            health_tick();
        }
        if (live && wait_live())
            break;
        if (read_pending(live ? 0 : 20)) {
            if (live)
                recover_ccu("read_failed");
            else
                break;
        }
        if (live) {
            video_stats();
            subscribe_buttons();
        }
        if (live && live_pending()) {
            event("ERROR", "LIVE_IPC_FAILED errno=%d", errno);
            break;
        }
        if (live && link_fd >= 0)
            flush_tx();
        struct timespec current;
        clock_gettime(CLOCK_MONOTONIC, &current);
        time_t now = current.tv_sec;
        if (seconds && now >= until)
            break;
        if (session && now > last_heartbeat + 4) {
            send_frame(version, 0, 0, 0, session, NULL, 0);
            last_heartbeat = now;
        }
        struct timespec tick;
        clock_gettime(CLOCK_MONOTONIC, &tick);
        uint64_t now_ms = (uint64_t)tick.tv_sec * 1000 + tick.tv_nsec / 1000000;
        if (!video_ack || !hmi_full)
            clip_pos = 8;
        if (!live && video_ack && hmi_full && now_ms >= last_video_ms + 50) {
            if (clip) {
                if (clip_pos == idr_size)
                    clip_pos = 8;
                uint32_t n = le32(idr + clip_pos);
                clip_pos += 4;
                if (send_video(idr + clip_pos, n))
                    break;
                clip_pos += n;
            } else if (send_video(idr, idr_size))
                break;
            last_video_ms = now_ms;
        }
    }
    event("INFO", "END session=%u video_ack=%d stopped=%d", session, video_ack, stopped);
    if (link_fd >= 0) {
        if (live)
            end_rpc_service();
        close(link_fd);
    }
    marker("ccu-fd", "closed\n");
    if (live) {
        event("INFO", "LIVE_END frames=%lu dropped=%lu", live_frames, live_dropped);
        for (unsigned i = 0; i < IPC_CLIENTS; i++)
            if (clients[i].fd >= 0)
                close_client(&clients[i]);
        close(ipc_listener);
        unlink(ipc_path);
    }
    clear_tx();
    free(waiting_frame);
    free(idr);
    if (trace_file)
        fclose(trace_file);
    if (log_file && log_file != stdout)
        fclose(log_file);
    return video_ack ? 0 : 1;
}
