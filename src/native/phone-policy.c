/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Local paired-phone policy and bounded CGI. No pairing keys leave this process. */
#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <signal.h>
#include <unistd.h>
#define JSMN_STRICT
#define JSMN_PARENT_LINKS
#include "third-party/jsmn/jsmn.h"
#include "aa-geometry.h"
#define MAX_PHONES 32
struct phone {
    char id[18], name[256], service[8];
    int bonded, rank;
};
static struct phone phones[MAX_PHONES];
static unsigned count;
static char preferred[16] = "none", order[MAX_PHONES][18];
static unsigned orders;
static const char *root = "";
static void path(char *out, size_t size, const char *suffix)
{
    snprintf(out, size, "%s%s", root, suffix);
}
static int address(const char *s)
{
    if (strlen(s) != 17)
        return 0;
    for (unsigned i = 0; i < 17; i++)
        if (i % 3 == 2 ? s[i] != ':' : !isxdigit((unsigned char)s[i]))
            return 0;
    return strcmp(s, "00:00:00:00:00:00") && strcasecmp(s, "FF:FF:FF:FF:FF:FF");
}
static struct phone *find(const char *id, int add)
{
    if (!address(id))
        return NULL;
    for (unsigned i = 0; i < count; i++)
        if (!strcasecmp(phones[i].id, id))
            return phones + i;
    if (!add || count == MAX_PHONES)
        return NULL;
    struct phone *p = phones + count++;
    memset(p, 0, sizeof(*p));
    for (unsigned i = 0; i < 18; i++)
        p->id[i] = (char)toupper((unsigned char)id[i]);
    p->rank = MAX_PHONES;
    return p;
}
static FILE *read_file(const char *name)
{
    int fd = open(name, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC);
    struct stat st;
    if (fd < 0)
        return NULL;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size > 65536) {
        close(fd);
        return NULL;
    }
    return fdopen(fd, "r");
}
static void lines(const char *file, int kind)
{
    FILE *f = read_file(file);
    if (!f)
        return;
    char line[1024];
    while (fgets(line, sizeof(line), f)) {
        if (!strchr(line, '\n') && !feof(f)) {
            int c;
            while ((c = fgetc(f)) != EOF && c != '\n') {
            }
            continue;
        }
        if (strlen(line) < 18 || line[17] != ' ')
            continue;
        line[17] = 0;
        struct phone *p = find(line, kind == 0);
        if (!p)
            continue;
        char *v = line + 18;
        v[strcspn(v, "\r\n")] = 0;
        if (kind == 0)
            p->bonded = 1; /* Parse the address only; never copy key material. */
        else if (kind == 1) {
            snprintf(p->name, sizeof(p->name), "%.*s", 255, v);
        } else if (!strcmp(v, "IAP2") || !strcmp(v, "AAP"))
            snprintf(p->service, sizeof(p->service), "%.7s", v);
    }
    fclose(f);
}
static void discover(void)
{
    char base[512];
    path(base, sizeof(base), "/tmp/bluetooth");
    DIR *d = opendir(base);
    if (!d)
        return;
    struct dirent *e;
    char file[1024];
    while ((e = readdir(d)))
        if (address(e->d_name)) {
            snprintf(file, sizeof(file), "%s/%s/linkkeys", base, e->d_name);
            lines(file, 0);
            snprintf(file, sizeof(file), "%s/%s/names", base, e->d_name);
            lines(file, 1);
        }
    closedir(d);
    snprintf(file, sizeof(file), "%s/services", base);
    lines(file, 2);
}
static int token_eq(const char *s, jsmntok_t *t, const char *v)
{
    return t->type == JSMN_STRING && (size_t)(t->end - t->start) == strlen(v) &&
           !memcmp(s + t->start, v, strlen(v));
}
static int parse(const char *s, size_t size, int paired_only)
{
    jsmntok_t t[128];
    jsmn_parser p;
    jsmn_init(&p);
    int n = jsmn_parse(&p, s, size, t, 128);
    if (n < 7 || t[0].type != JSMN_OBJECT || t[0].size != 3 || memchr(s, 0, size))
        return -1;
    for (int i = 0; i < t[0].start; i++)
        if (!isspace((unsigned char)s[i]))
            return -1;
    for (size_t i = (size_t)t[0].end; i < size; i++)
        if (!isspace((unsigned char)s[i]))
            return -1;
    unsigned seen = 0, num = 0;
    char pref[16] = "", ids[MAX_PHONES][18];
    for (int i = 1; i < n; i++) {
        if (t[i].parent != 0)
            continue;
        if (i + 1 >= n || t[i + 1].parent != i)
            return -1;
        jsmntok_t *v = t + i + 1;
        if (token_eq(s, t + i, "schema")) {
            if (seen & 1 || v->type != JSMN_PRIMITIVE || v->end - v->start != 1 ||
                s[v->start] != '1')
                return -1;
            seen |= 1;
        } else if (token_eq(s, t + i, "preferred")) {
            if (seen & 2)
                return -1;
            seen |= 2;
            if (token_eq(s, v, "carplay"))
                strcpy(pref, "carplay");
            else if (token_eq(s, v, "android-auto"))
                strcpy(pref, "android-auto");
            else if (token_eq(s, v, "none"))
                strcpy(pref, "none");
            else
                return -1;
        } else if (token_eq(s, t + i, "order")) {
            if (seen & 4 || v->type != JSMN_ARRAY || v->size > MAX_PHONES)
                return -1;
            seen |= 4;
            for (int j = i + 2; j < n && t[j].start < v->end; j++) {
                if (t[j].parent != i + 1 || t[j].type != JSMN_STRING ||
                    t[j].end - t[j].start != 17 || num >= MAX_PHONES)
                    return -1;
                memcpy(ids[num], s + t[j].start, 17);
                ids[num][17] = 0;
                if (!address(ids[num]))
                    return -1;
                for (unsigned k = 0; k < 17; k++)
                    ids[num][k] = (char)toupper((unsigned char)ids[num][k]);
                if (paired_only && !find(ids[num], 0))
                    return -1;
                for (unsigned k = 0; k < num; k++)
                    if (!strcmp(ids[k], ids[num]))
                        return -1;
                num++;
            }
        } else
            return -1;
    }
    if (seen != 7)
        return -1;
    strcpy(preferred, pref);
    memcpy(order, ids, num * 18);
    orders = num;
    return 0;
}
/* Separate bounded operation; rejects extra fields, escapes and unknown phones. */
static int parse_forget(const char *s, size_t size, char id[18])
{
    jsmntok_t t[8];
    jsmn_parser p;
    jsmn_init(&p);
    int n = jsmn_parse(&p, s, size, t, 8);
    if (n != 5 || t[0].type != JSMN_OBJECT || t[0].size != 2 || memchr(s, 0, size))
        return -1;
    for (int i = 0; i < t[0].start; i++)
        if (!isspace((unsigned char)s[i]))
            return -1;
    for (size_t i = (size_t)t[0].end; i < size; i++)
        if (!isspace((unsigned char)s[i]))
            return -1;
    unsigned seen = 0;
    for (int i = 1; i < 5; i += 2) {
        if (token_eq(s, t + i, "action") && !(seen & 1) && token_eq(s, t + i + 1, "forget"))
            seen |= 1;
        else if (token_eq(s, t + i, "id") && !(seen & 2) && t[i + 1].type == JSMN_STRING &&
                 t[i + 1].end - t[i + 1].start == 17) {
            memcpy(id, s + t[i + 1].start, 17);
            id[17] = 0;
            seen |= 2;
        } else
            return -1;
    }
    return seen == 3 && address(id) && find(id, 0) ? 0 : -1;
}
/* The daemon owns bond persistence; success also requires the bond to vanish.
 * A method-return alone only acknowledges its request handler. */
static int forget_phone(const char *id)
{
    char file[512];
    path(file, sizeof(file), "/tmp/yamaha-sdl/phone-control.lock");
    int lock = open(file, O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (lock < 0)
        return -1;
    if (flock(lock, LOCK_EX | LOCK_NB)) {
        close(lock);
        return -2;
    }
    path(file, sizeof(file), "/tmp/yamaha-sdl/bluetooth-autoconnect");
    pid_t child = fork();
    if (child == 0) {
        int null = open("/dev/null", O_RDWR);
        if (null < 0)
            _exit(127);
        dup2(null, 0);
        dup2(null, 1);
        dup2(null, 2);
        if (null > 2)
            close(null);
        execl(file, file, "--forget", id, (char *)NULL);
        _exit(127);
    }
    int result = -1, status = 0, done = 0;
    if (child > 0) {
        for (unsigned i = 0; i < 60; i++) {
            pid_t rc = waitpid(child, &status, WNOHANG);
            if (rc == child) {
                done = 1;
                break;
            }
            if (rc < 0 && errno != EINTR)
                break;
            usleep(100000);
        }
        if (!done) {
            kill(child, SIGKILL);
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
            }
        } else if (WIFEXITED(status) && WEXITSTATUS(status) == 0) {
            for (unsigned i = 0; i < 10; i++) {
                count = 0;
                discover();
                if (!find(id, 0)) {
                    result = 0;
                    break;
                }
                usleep(100000);
            }
        }
    }
    close(lock);
    return result;
}
static void load(void)
{
    char file[512], data[4097];
    path(file, sizeof(file), "/etc/yamaha-sdl/phone-policy.json");
    FILE *f = read_file(file);
    if (!f)
        return;
    size_t n = fread(data, 1, sizeof(data), f);
    fclose(f);
    if (n < sizeof(data))
        parse(data, n, 0);
}
static int group(const struct phone *p)
{
    if (!strcmp(preferred, "none"))
        return 0;
    if (!*p->service)
        return 2;
    return (!strcmp(preferred, "carplay") && strcmp(p->service, "IAP2")) ||
           (!strcmp(preferred, "android-auto") && strcmp(p->service, "AAP"));
}
static int compare(const void *a, const void *b)
{
    const struct phone *x = a, *y = b;
    int d = group(x) - group(y);
    if (d)
        return d;
    d = x->rank - y->rank;
    return d ? d : strcmp(x->id, y->id);
}
static void sort(void)
{
    for (unsigned i = 0; i < count; i++)
        for (unsigned j = 0; j < orders; j++)
            if (!strcmp(phones[i].id, order[j]))
                phones[i].rank = (int)j;
    qsort(phones, count, sizeof(*phones), compare);
}
/* JSON names from the Bluetooth cache may end in a split UTF-8 character. */
static unsigned utf8_width(const unsigned char *p)
{
    unsigned first = p[0], width, code, min;
    if (first < 0x80)
        return 1;
    if (first >= 0xc2 && first <= 0xdf) {
        width = 2;
        code = first & 0x1f;
        min = 0x80;
    } else if (first >= 0xe0 && first <= 0xef) {
        width = 3;
        code = first & 0x0f;
        min = 0x800;
    } else if (first >= 0xf0 && first <= 0xf4) {
        width = 4;
        code = first & 0x07;
        min = 0x10000;
    } else
        return 0;
    for (unsigned i = 1; i < width; i++) {
        if ((p[i] & 0xc0) != 0x80)
            return 0;
        code = (code << 6) | (p[i] & 0x3f);
    }
    return code < min || (code >= 0xd800 && code <= 0xdfff) || code > 0x10ffff ? 0 : width;
}
static void quote(const char *s)
{
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)s; *p;) {
        unsigned width = utf8_width(p);
        if (!width) {
            fputs("\\ufffd", stdout);
            p++;
            continue;
        }
        if (*p == '"' || *p == '\\')
            printf("\\%c", *p);
        else if (*p < 32 || *p == 127)
            printf("\\u%04x", *p);
        else
            fwrite(p, 1, width, stdout);
        p += width;
    }
    putchar('"');
}
/* Dextend policy writes use an atomic rename under the shared installer lock. */
static int save(void)
{
    char dir[512], tmp[544], dest[544], lock[544];
    path(dir, sizeof(dir), "/etc/yamaha-sdl");
    snprintf(lock, sizeof(lock), "%s/phone-policy.lock", dir);
    int l = open(lock, O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (l < 0)
        return -1;
    if (flock(l, LOCK_EX | LOCK_NB)) {
        close(l);
        return -1;
    }
    snprintf(tmp, sizeof(tmp), "%s/phone-policy.XXXXXX", dir);
    int fd = mkstemp(tmp);
    if (fd < 0) {
        close(l);
        return -1;
    }
    FILE *f = fdopen(fd, "w");
    if (!f) {
        close(fd);
        unlink(tmp);
        close(l);
        return -1;
    }
    fprintf(f, "{\"schema\":1,\"preferred\":\"%s\",\"order\":[", preferred);
    for (unsigned i = 0; i < orders; i++)
        fprintf(f, "%s\"%s\"", i ? "," : "", order[i]);
    fputs("]}\n", f);
    int rc = fflush(f) || fsync(fd);
    if (fclose(f))
        rc = -1;
    snprintf(dest, sizeof(dest), "%s/phone-policy.json", dir);
    if (!rc)
        rc = rename(tmp, dest);
    int d = open(dir, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (d < 0)
        rc = -1;
    else {
        if (fsync(d))
            rc = -1;
        close(d);
    }
    unlink(tmp);
    close(l);
    return rc;
}
static int csrf(char out[65], int create)
{
    char file[512];
    path(file, sizeof(file), "/tmp/yamaha-sdl/phone-web-token");
    if (create) {
        unsigned char bytes[32];
        int r = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
        if (r < 0)
            return -1;
        ssize_t n = read(r, bytes, sizeof(bytes));
        close(r);
        if (n != sizeof(bytes))
            return -1;
        for (unsigned i = 0; i < 32; i++)
            snprintf(out + 2 * i, 3, "%02x", bytes[i]);
        int fd = open(file, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, 0600);
        if (fd >= 0) {
            int rc = write(fd, out, 64) == 64 ? 0 : -1;
            close(fd);
            return rc;
        }
        if (errno != EEXIST)
            return -1;
    }
    FILE *f = read_file(file);
    if (!f)
        return -1;
    size_t n = fread(out, 1, 65, f);
    fclose(f);
    if (n != 64)
        return -1;
    out[64] = 0;
    for (unsigned i = 0; i < 64; i++)
        if (!isxdigit((unsigned char)out[i]))
            return -1;
    return 0;
}
static void headers(int code)
{
    printf("Status: %d\r\nContent-Type: application/json; charset=utf-8\r\nCache-Control: "
           "no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n",
           code);
}
static int fail(int code, const char *message)
{
    headers(code);
    printf("{\"error\":\"%s\"}\n", message);
    return 0;
}
static int host_ok(const char *host)
{
    if (!host || strlen(host) > 80)
        return 0;
    char name[81];
    strcpy(name, host);
    char *port = strchr(name, ':');
    if (port) {
        *port++ = 0;
        if (!*port)
            return 0;
        for (char *p = port; *p; p++)
            if (!isdigit((unsigned char)*p))
                return 0;
    }
    if (!strcmp(name, "localhost") || !strcmp(name, "autobox.com") ||
        !strcmp(name, "www.autobox.com"))
        return 1;
    unsigned a, b, c, d;
    char extra;
    return sscanf(name, "%u.%u.%u.%u%c", &a, &b, &c, &d, &extra) == 4 && a < 256 && b < 256 &&
           c < 256 && d < 256;
}
int main(int argc, char **argv)
{
#ifdef DEXTEND_PHONE_TEST
    const char *fixture = getenv("DEXTEND_PHONE_ROOT");
    if (fixture)
        root = fixture;
#endif
    const char *query = getenv("QUERY_STRING");
    int video = argc == 1 && query && !strcmp(query, "view=aa-video");
    if (!video) {
        discover();
        load();
        sort();
    }
    if (argc == 2 && !strcmp(argv[1], "--init")) {
        char token[65];
        return csrf(token, 1) ? 2 : 0;
    }
    if (argc == 2 && !strcmp(argv[1], "--candidates")) {
        for (unsigned i = 0; i < count; i++)
            printf("%s %s\n", phones[i].id, *phones[i].service ? phones[i].service : "AUTO");
        return 0;
    }
    if (argc == 4 && !strcmp(argv[1], "--choose")) {
        if (!address(argv[2]) || !address(argv[3]))
            return 2;
        for (unsigned i = 0; i < count; i++)
            if (!strcasecmp(phones[i].id, argv[2]) || !strcasecmp(phones[i].id, argv[3])) {
                puts(!strcasecmp(phones[i].id, argv[2]) ? "aa-wireless" : "carplay");
                return 0;
            }
        puts("carplay");
        return 0;
    }
    if (argc != 1)
        return 2;
    const char *method = getenv("REQUEST_METHOD"), *host = getenv("HTTP_HOST");
    if (!host_ok(host))
        return fail(403, "Nieprawidłowy adres panelu.");
    char token[65];
    if (csrf(token, 0))
        return fail(503, "Panel nie jest jeszcze gotowy.");
    char video_path[512];
    path(video_path, sizeof(video_path), AA_SETTINGS);
    struct aa_geometry geometry;
    if (method && !strcmp(method, "POST")) {
        const char *sent = getenv("HTTP_X_DEXTEND_TOKEN"), *origin = getenv("HTTP_ORIGIN"),
                   *ct = getenv("CONTENT_TYPE"), *cl = getenv("CONTENT_LENGTH");
        char expected[100];
        snprintf(expected, sizeof(expected), "http://%s", host);
        if (!sent || strcmp(sent, token) || !origin || strcmp(origin, expected))
            return fail(403, "Odśwież panel i spróbuj ponownie.");
        if (!ct || strcmp(ct, "application/json") || !cl)
            return fail(400, "Nieprawidłowe ustawienia.");
        char *end;
        unsigned long n = strtoul(cl, &end, 10);
        if (*end || !n || n > 4096)
            return fail(400, "Nieprawidłowe ustawienia.");
        char data[4097];
        if (fread(data, 1, n, stdin) != n)
            return fail(400, "Nieprawidłowe ustawienia.");
        data[n] = 0;
        if (video && (memchr(data, 0, n) || aa_parse_geometry(data, &geometry)))
            return fail(400, "Nieprawidłowe ustawienia.");
        char forget_id[18];
        int forgetting = !video && !parse_forget(data, n, forget_id);
        if (!video && !forgetting && parse(data, n, 1))
            return fail(400, "Nieprawidłowa kolejność telefonów.");
        /* Serialize persistent writes with installation and OEM restoration. */
        char installer_lock[512];
        path(installer_lock, sizeof(installer_lock), "/tmp/dextend-usb-lock");
        if (mkdir(installer_lock, 0700))
            return fail(409, "Trwa operacja na oprogramowaniu adaptera.");
        int result = video        ? aa_write_geometry(video_path, &geometry, 1)
                     : forgetting ? forget_phone(forget_id)
                                  : save();
        int reload_requested = 0;
        if (video && !result) {
            char marker[512];
            path(marker, sizeof(marker), "/tmp/yamaha-sdl/aa-video-reload");
            int fd = open(marker, O_WRONLY | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
            if (fd >= 0) {
                close(fd);
                reload_requested = 1;
            }
        }
        rmdir(installer_lock);
        if (forgetting) {
            if (result == -2)
                return fail(409, "Bluetooth jest zajęty. Spróbuj ponownie.");
            if (result)
                return fail(503, "Nie udało się potwierdzić usunięcia telefonu. Odśwież listę.");
            headers(200);
            puts("{\"forgotten\":true}");
            return 0;
        }
        if (result)
            return fail(500, "Nie udało się zapisać ustawień. Odśwież panel.");
        headers(200);
        if (video)
            printf("{\"saved\":true,\"reloadRequested\":%s}\n",
                   reload_requested ? "true" : "false");
        else
            puts("{\"saved\":true}");
        return 0;
    }
    if (!method || strcmp(method, "GET"))
        return fail(405, "Niedozwolona metoda.");
    headers(200);
    if (video) {
        geometry = aa_load_geometry(video_path);
        printf("{\"token\":\"%s\",\"geometry\":", token);
        aa_print_geometry(stdout, &geometry);
        const struct aa_geometry defaults = AA_YAMAHA_GEOMETRY;
        fputs(",\"defaultGeometry\":", stdout);
        aa_print_geometry(stdout, &defaults);
        puts("}");
        return 0;
    }
    printf("{\"schema\":1,\"preferred\":\"%s\",\"token\":\"%s\",\"devices\":[", preferred, token);
    for (unsigned i = 0; i < count; i++) {
        struct phone *p = phones + i;
        if (i)
            putchar(',');
        fputs("{\"id\":", stdout);
        quote(p->id);
        fputs(",\"name\":", stdout);
        quote(*p->name ? p->name : "Telefon bez nazwy");
        fputs(",\"platform\":", stdout);
        quote(!strcmp(p->service, "AAP")    ? "android-auto"
              : !strcmp(p->service, "IAP2") ? "carplay"
                                            : "unknown");
        putchar('}');
    }
    puts("]}");
    return 0;
}
