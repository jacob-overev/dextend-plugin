/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Dextend native receiver launcher.
 * Execute an unchanged OEM receiver with its ordinary BtAudio setting in a
 * private mount namespace. No preload, instruction patch, key handling or
 * persistent configuration writes. jsmn is MIT; see third-party/jsmn/LICENSE.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/inotify.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <unistd.h>
#define JSMN_STRICT
#define JSMN_PARENT_LINKS
#include "third-party/jsmn/jsmn.h"

#include "aa-geometry.h"
static struct aa_geometry aa_geometry = AA_YAMAHA_GEOMETRY;

#define CONFIG_LIMIT 65536
#define TOKEN_LIMIT 8192

static int whitespace(char c) { return c == ' ' || c == '\n' || c == '\r' || c == '\t'; }

/* Preserve every byte except the top-level BtAudio value (or insertion).
 * Reject ambiguity instead of editing nested keys or guessing a config type.
 */
static char *set_config(const char *input, size_t length, size_t *out_length, const char *key,
                        const char *value)
{
    if (!length || length > CONFIG_LIMIT || memchr(input, 0, length))
        return NULL;
    jsmntok_t *tokens = calloc(TOKEN_LIMIT, sizeof(*tokens));
    if (!tokens)
        return NULL;
    jsmn_parser parser;
    jsmn_init(&parser);
    int count = jsmn_parse(&parser, input, length, tokens, TOKEN_LIMIT);
    if (count < 1 || tokens[0].type != JSMN_OBJECT || tokens[0].parent != -1)
        goto invalid;
    for (int p = 0; p < tokens[0].start; p++)
        if (!whitespace(input[p]))
            goto invalid;
    for (size_t p = (size_t)tokens[0].end; p < length; p++)
        if (!whitespace(input[p]))
            goto invalid;
    int found = -1;
    for (int i = 1; i < count; i++) {
        if (tokens[i].parent != 0)
            continue;
        if (tokens[i].type != JSMN_STRING)
            goto invalid;
        int n = tokens[i].end - tokens[i].start;
        if (memchr(input + tokens[i].start, '\\', (size_t)n))
            goto invalid;
        if ((size_t)n != strlen(key) || memcmp(input + tokens[i].start, key, (size_t)n))
            continue;
        if (found != -1 || i + 1 >= count || tokens[i + 1].parent != i ||
            tokens[i + 1].type != JSMN_PRIMITIVE)
            goto invalid;
        found = i + 1;
        int value_length = tokens[found].end - tokens[found].start;
        if (!strcmp(key, "BtAudio") && (value_length != 1 || (input[tokens[found].start] != '0' &&
                                                              input[tokens[found].start] != '1')))
            goto invalid;
        if (value_length < 1)
            goto invalid;
        for (int j = 0; j < value_length; j++)
            if (input[tokens[found].start + j] < '0' || input[tokens[found].start + j] > '9')
                goto invalid;
    }
    size_t start, end;
    const char *replacement;
    char insertion[80];
    if (found != -1) {
        start = (size_t)tokens[found].start;
        end = (size_t)tokens[found].end;
        replacement = value;
    } else {
        start = end = (size_t)tokens[0].end - 1;
        snprintf(insertion, sizeof(insertion), "%s\"%s\":%s", tokens[0].size ? "," : "", key,
                 value);
        replacement = insertion;
    }
    size_t addition = strlen(replacement);
    *out_length = length - (end - start) + addition;
    char *out = malloc(*out_length + 1);
    if (!out)
        goto invalid;
    memcpy(out, input, start);
    memcpy(out + start, replacement, addition);
    memcpy(out + start + addition, input + end, length - end);
    out[*out_length] = 0;
    free(tokens);
    return out;
invalid:
    free(tokens);
    return NULL;
}

static char *receiver_config(const char *input, size_t length, size_t *size, int aa)
{
    if (aa == 2)
        return set_config(input, length, size, "AndroidWorkMode", "1");
    if (!aa)
        return set_config(input, length, size, "BtAudio", "1");
    char w[16], h[16];
    snprintf(w, sizeof(w), "%u", aa_geometry.width);
    snprintf(h, sizeof(h), "%u", aa_geometry.height);
    char *width = set_config(input, length, size, "AndroidAutoWidth", w);
    if (!width)
        return NULL;
    char *height = set_config(width, *size, size, "AndroidAutoHeight", h);
    free(width);
    if (!height)
        return NULL;
    /* This OEM advertises DPAD only with its hybrid input profile. Rotary
     * remains available; KnobMode=1 would remove the area-navigation keys. */
    char *input_profile = set_config(height, *size, size, "KnobMode", "0");
    free(height);
    if (!input_profile)
        return NULL;
    char *out = set_config(input_profile, *size, size, "ScreenDPI", "120");
    free(input_profile);
    return out;
}

#ifdef DEXTEND_CONFIG_TEST
/* Host fixture runner only; this build is never copied to the dongle. */
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "aa"))
        aa_geometry = aa_load_geometry(AA_SETTINGS);
    char input[CONFIG_LIMIT + 1];
    size_t n = fread(input, 1, sizeof(input), stdin), size = 0;
    char *out =
        receiver_config(input, n, &size, argc == 2 ? (!strcmp(argv[1], "auto") ? 2 : 1) : 0);
    if (!out)
        return 2;
    int result = fwrite(out, 1, size, stdout) == size ? 0 : 2;
    free(out);
    return result;
}
#else
static int isolate(void)
{
    if (unshare(CLONE_NEWNS))
        return -1;
    return mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL);
}

static const char *failure_stage = "unknown";
static int failed(void)
{
    /* Never print configuration content, device identity or authentication data. */
    fprintf(stderr, "DEXTEND_NATIVE_RECEIVER refused stage=%s errno=%d\n", failure_stage, errno);
    return 2;
}

/* Prepare the Dextend audio configuration inside the receiver namespace. */
static int private_audio_config(const char *path, int aa)
{
    int source = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (source < 0)
        return -1;
    struct stat st;
    if (fstat(source, &st) || !S_ISREG(st.st_mode) || st.st_size < 1 || st.st_size > CONFIG_LIMIT) {
        close(source);
        return -1;
    }
    size_t used = 0, length = (size_t)st.st_size;
    char *input = malloc(length + 1);
    if (!input) {
        close(source);
        return -1;
    }
    while (used < length) {
        ssize_t n = read(source, input + used, length - used);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0) {
            free(input);
            close(source);
            return -1;
        }
        used += (size_t)n;
    }
    close(source);
    size_t size;
    char *out = receiver_config(input, length, &size, aa);
    free(input);
    if (!out)
        return -1;
    char temporary[] = "/tmp/yamaha-sdl/bt-audio-XXXXXX";
    int fd = mkostemp(temporary, O_CLOEXEC);
    if (fd < 0) {
        free(out);
        return -1;
    }
    used = 0;
    while (used < size) {
        ssize_t n = write(fd, out + used, size - used);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0) {
            close(fd);
            unlink(temporary);
            free(out);
            return -1;
        }
        used += (size_t)n;
    }
    free(out);
    if (close(fd)) {
        unlink(temporary);
        return -1;
    }
    int result = mount(temporary, path, NULL, MS_BIND, NULL);
    /* The auto runtime is a parent namespace: receiver children bind over
     * these paths again. On the target kernel an unlinked mount target cannot
     * be overmounted (ENOENT), so keep its two backing files until reboot. */
    if (aa != 2 || result)
        unlink(temporary);
    return result ? -1 : 0;
}

static int private_android_mode(void)
{
    const char *target = "/etc/android_work_mode";
    struct stat st;
    if (lstat(target, &st) || !S_ISREG(st.st_mode) || st.st_size != 4)
        return -1;
    char temporary[] = "/tmp/yamaha-sdl/android-mode-XXXXXX";
    int fd = mkostemp(temporary, O_CLOEXEC);
    if (fd < 0)
        return -1;
    const unsigned char mode[] = {1, 0, 0, 0};
    int result = write(fd, mode, sizeof(mode)) == sizeof(mode) ? 0 : -1;
    if (close(fd))
        result = -1;
    if (!result)
        result = mount(temporary, target, NULL, MS_BIND, NULL);
    unlink(temporary);
    return result;
}
/* One consumer in the private runtime directory. Register the watch before
 * checking for a pending grant so an arrival during setup cannot be missed. */
static int wait_carplay(void)
{
    const char *pending = "carplay-wakeup/pending";
    int fd = inotify_init1(IN_CLOEXEC);
    if (fd < 0)
        return 1;
    int rc = 0;
    if (inotify_add_watch(fd, "carplay-wakeup", IN_CREATE) < 0) {
        rc = 1;
    } else if (unlink(pending) < 0) {
        struct pollfd event = {.fd = fd, .events = POLLIN};
        if (errno != ENOENT || poll(&event, 1, 2000) < 0)
            rc = 1;
        else if (event.revents & POLLIN)
            unlink(pending);
    }
    close(fd);
    return rc;
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--wait-carplay"))
        return wait_carplay();
    if (argc == 2 && !strcmp(argv[1], "--probe")) {
        if (isolate())
            return failed();
        puts("DEXTEND_NATIVE_NAMESPACE_AVAILABLE");
        return 0;
    }
    int probe_auto = argc == 2 && !strcmp(argv[1], "--probe-auto-runtime");
    int auto_runtime = probe_auto || (argc == 2 && !strcmp(argv[1], "--auto-runtime"));
    int aa = auto_runtime ? 2 : argc == 2 && !strcmp(argv[1], "--android-auto");
    int probe_audio = argc == 2 && !strcmp(argv[1], "--probe-phone-audio");
    if (!aa && !probe_audio &&
        (argc < 3 || strcmp(argv[1], "--phone-audio") ||
         (strcmp(argv[2], "/usr/sbin/AppleCarPlay") && strcmp(argv[2], "/usr/sbin/ARMiPhoneIAP2"))))
        return 2;
    /* Isolate before any bind. Parent/sibling namespaces are never modified. */
    failure_stage = "namespace";
    if (isolate())
        return failed();
    if (aa == 1) {
        aa_geometry = aa_load_geometry(AA_SETTINGS);
        if (aa_write_geometry(AA_SESSION, &aa_geometry, 0))
            return failed();
    }
    failure_stage = "persistent_config_bind";
    if (private_audio_config("/etc/riddle.conf", aa))
        return failed();
    failure_stage = "cached_config_bind";
    if (private_audio_config("/tmp/.riddle.conf", aa))
        return failed();
    if (unsetenv("LD_PRELOAD"))
        return failed();
    if (auto_runtime) {
        failure_stage = "android_mode_bind";
        if (private_android_mode())
            return failed();
        if (probe_auto)
            return 0;
        failure_stage = "runtime_environment";
        if (setenv("YAMAHA_PHONE_AUTO", "1", 1) || unsetenv("YAMAHA_AA_MODE") ||
            unsetenv("YAMAHA_AA_PEER"))
            return failed();
        char *const args[] = {"sh", "./boot-live.sh", NULL};
        execv("/bin/sh", args);
        return failed();
    }
    if (aa) {
        char *const args[] = {"/usr/sbin/ARMAndroidAuto", NULL};
        execv(args[0], args);
        return failed();
    }
    fputs("DEXTEND_NATIVE_RECEIVER preload=0 code_patches=0 private_BtAudio=1 "
          "private_config_paths=2\n",
          stderr);
    if (probe_audio) {
        char *const config_argv[] = {"riddleBoxCfg", "-g", "BtAudio", NULL};
        execv("/usr/sbin/riddleBoxCfg", config_argv);
        return failed();
    }
    execv(argv[2], argv + 2);
    return failed();
}
#endif
