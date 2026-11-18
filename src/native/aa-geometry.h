/* Dextend | Developed by Overev | https://overev.com/ */
#ifndef DEXTEND_AA_GEOMETRY_H
#define DEXTEND_AA_GEOMETRY_H
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
#include <unistd.h>

#ifndef AA_SETTINGS
#define AA_SETTINGS "/etc/yamaha-sdl/aa-video.conf"
#endif
#define AA_SESSION_NAME "aa-video-session"
#define AA_SESSION "/tmp/yamaha-sdl/" AA_SESSION_NAME
struct aa_geometry {
    unsigned width, height, left, right, top, bottom;
};
#define AA_YAMAHA_GEOMETRY {624, 352, 44, 76, 32, 40}

static inline int aa_parse_geometry(const char *s, struct aa_geometry *out)
{
    unsigned v[6];
    while (isspace((unsigned char)*s))
        ++s;
    if (*s++ != '[')
        return -1;
    for (unsigned i = 0; i < 6; i++) {
        while (isspace((unsigned char)*s))
            ++s;
        if (!isdigit((unsigned char)*s) || (*s == '0' && isdigit((unsigned char)s[1])))
            return -1;
        unsigned n = 0;
        while (isdigit((unsigned char)*s)) {
            n = n * 10 + (*s++ - '0');
            if (n > 800)
                return -1;
        }
        if (n % 2)
            return -1;
        v[i] = n;
        while (isspace((unsigned char)*s))
            ++s;
        if (*s++ != (i == 5 ? ']' : ','))
            return -1;
    }
    while (isspace((unsigned char)*s))
        ++s;
    if (*s || v[0] < 2 || v[1] < 2 || v[1] > 480 || v[2] + v[3] >= 800 || v[4] + v[5] >= 480)
        return -1;
    *out = (struct aa_geometry){v[0], v[1], v[2], v[3], v[4], v[5]};
    return 0;
}
static inline struct aa_geometry aa_load_geometry(const char *file)
{
    struct aa_geometry g = AA_YAMAHA_GEOMETRY;
    FILE *f = fopen(file, "r");
    if (f) {
        char buf[128];
        size_t n = fread(buf, 1, sizeof(buf), f);
        if (n < sizeof(buf) && !ferror(f) && !memchr(buf, 0, n)) {
            buf[n] = 0;
            aa_parse_geometry(buf, &g);
        }
        fclose(f);
    }
    return g;
}
static inline void aa_print_geometry(FILE *f, const struct aa_geometry *g)
{
    fprintf(f, "[%u,%u,%u,%u,%u,%u]", g->width, g->height, g->left, g->right, g->top, g->bottom);
}
static inline int aa_write_geometry(const char *file, const struct aa_geometry *g, int durable)
{
    char tmp[600];
    if (snprintf(tmp, sizeof(tmp), "%s.XXXXXX", file) >= (int)sizeof(tmp))
        return -1;
    int fd = mkstemp(tmp);
    if (fd < 0)
        return -1;
    FILE *f = fdopen(fd, "w");
    int rc = -1;
    if (f) {
        aa_print_geometry(f, g);
        rc = ferror(f) || fflush(f) || (durable && fsync(fd));
        if (fclose(f))
            rc = -1;
        if (!rc)
            rc = rename(tmp, file);
    } else
        close(fd);
    if (!rc && durable) {
        char *slash = strrchr(tmp, '/');
        if (!slash)
            return -1;
        *slash = 0;
        int dir = open(tmp, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (dir < 0)
            return -1;
        rc = fsync(dir);
        close(dir);
        return rc;
    }
    if (rc)
        unlink(tmp);
    return rc;
}
#endif
