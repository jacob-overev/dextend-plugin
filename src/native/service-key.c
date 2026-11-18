/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Remove only our exact insertion while preserving later key edits. */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
static unsigned char data[3][65537];
static size_t read_file(const char *p, unsigned char *out)
{
    int fd = open(p, O_RDONLY | O_NOFOLLOW);
    struct stat st;
    if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size < 0 || st.st_size > 65536)
        exit(2);
    size_t n = 0;
    ssize_t got;
    while ((got = read(fd, out + n, 65537 - n)) > 0)
        n += (size_t)got;
    close(fd);
    if (got < 0 || n > 65536)
        exit(2);
    return n;
}
int main(int argc, char **argv)
{
    if (argc != 4)
        return 2;
    size_t a = read_file(argv[1], data[0]), b = read_file(argv[2], data[1]),
           c = read_file(argv[3], data[2]);
    if (b <= a || memcmp(data[0], data[1], a))
        return 2;
    if (c == a && !memcmp(data[0], data[2], a))
        return fwrite(data[2], 1, c, stdout) == c ? 0 : 2;
    unsigned char *insertion = data[1] + a;
    size_t size = b - a, offset = 0, count = 0;
    /* A journal may only describe a single public key, not arbitrary text. */
    size_t lead = size && insertion[0] == '\n' ? 1 : 0;
    if (size - lead < 13 || memcmp(insertion + lead, "ssh-ed25519 ", 12) ||
        insertion[size - 1] != '\n')
        return 2;
    for (size_t i = lead; i < size - 1; i++)
        if (insertion[i] == '\n' || insertion[i] == '\0')
            return 2;
    for (size_t i = 0; i + size <= c; i++)
        if (!memcmp(data[2] + i, insertion, size)) {
            offset = i;
            count++;
        }
    if (count != 1)
        return 3; /* Ambiguous/edited entry: leave it to the owner. */
    if (fwrite(data[2], 1, offset, stdout) != offset)
        return 2;
    size_t tail = c - offset - size;
    return fwrite(data[2] + offset + size, 1, tail, stdout) == tail ? 0 : 2;
}
