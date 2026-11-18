/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Dextend waiting frame */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LIMIT 131072
#define WIDTH 160
#define HEIGHT 96
#define GLYPH_W 7
#define GLYPH_H 12
#define FIRST_ASCII 32
#define LAST_ASCII 126
#define CHROMA_SIZE (WIDTH * HEIGHT / 4)
#define STRIP_SIZE (WIDTH * HEIGHT + 2 * CHROMA_SIZE)

static unsigned char strip[STRIP_SIZE];
static unsigned char font[(LAST_ASCII - FIRST_ASCII + 1) * GLYPH_W * GLYPH_H];
static unsigned char base[LIMIT];
static unsigned char output[LIMIT];
static size_t output_size;
struct bits {
    unsigned char data[4096];
    size_t length;
};

static void put_bit(struct bits *bits, unsigned bit)
{
    if (bit)
        bits->data[bits->length / 8] |= 0x80u >> (bits->length % 8);
    ++bits->length;
}

static void put_ue(struct bits *bits, unsigned value)
{
    unsigned code = value + 1, length = 0;
    for (unsigned rest = code; rest > 1; rest >>= 1)
        ++length;
    for (unsigned i = 0; i < length; ++i)
        put_bit(bits, 0);
    for (unsigned i = length + 1; i > 0; --i)
        put_bit(bits, (code >> (i - 1)) & 1);
}

static int append(const unsigned char *data, size_t n)
{
    if (n > sizeof output - output_size)
        return -1;
    memcpy(output + output_size, data, n);
    output_size += n;
    return 0;
}

static int append_rbsp(const struct bits *bits)
{
    unsigned zeros = 0;
    for (size_t i = 0; i < bits->length / 8; ++i) {
        unsigned char octet = bits->data[i];
        if (zeros == 2 && octet < 4) {
            const unsigned char escape = 3;
            if (append(&escape, 1))
                return -1;
            zeros = 0;
        }
        if (append(&octet, 1))
            return -1;
        zeros = octet ? 0 : zeros + 1;
    }
    return 0;
}

static void copy_plane(struct bits *bits, const unsigned char *plane, unsigned stride, unsigned x,
                       unsigned y, unsigned block)
{
    for (unsigned line = 0; line < block; ++line) {
        memcpy(bits->data + bits->length / 8, plane + (y + line) * stride + x, block);
        bits->length += block * 8;
    }
}

/* Render the version overlay as an H.264 slice. */
static int render_slice(unsigned row, unsigned first_mb)
{
    /* x264 template: IDR, pic_order_cnt_type 2, 4-bit frame_num, deblocking off. */
    const unsigned char start[] = {0, 0, 0, 1, 0x65};
    struct bits bits = {0};
    put_ue(&bits, first_mb);
    put_ue(&bits, 7);
    put_ue(&bits, 0);
    for (unsigned i = 0; i < 4; ++i)
        put_bit(&bits, 0);
    put_ue(&bits, 0);
    put_bit(&bits, 0);
    put_bit(&bits, 0);
    put_ue(&bits, 0); /* slice_qp_delta = 0; PCM samples are lossless. */
    put_ue(&bits, 1); /* disable_deblocking_filter_idc */
    for (unsigned x = 0; x < WIDTH; x += 16) {
        put_ue(&bits, 25); /* I_PCM macroblock */
        while (bits.length % 8)
            put_bit(&bits, 0);
        copy_plane(&bits, strip, WIDTH, x, row * 16, 16);
        copy_plane(&bits, strip + WIDTH * HEIGHT, WIDTH / 2, x / 2, row * 8, 8);
        copy_plane(&bits, strip + WIDTH * HEIGHT + CHROMA_SIZE, WIDTH / 2, x / 2, row * 8, 8);
    }
    put_bit(&bits, 1);
    while (bits.length % 8)
        put_bit(&bits, 0);
    if (append(start, sizeof start))
        return -1;
    return append_rbsp(&bits);
}

static size_t start_code(const unsigned char *data, size_t size, size_t begin)
{
    for (size_t i = begin; i + 2 < size; ++i) {
        if (!data[i] && !data[i + 1] &&
            (data[i + 2] == 1 || (i + 3 < size && !data[i + 2] && data[i + 3] == 1)))
            return i;
    }
    return size;
}

static int first_mb(const unsigned char *payload, size_t size)
{
    if (size < 3)
        return -1;
    unsigned zero = 0, value = 1;
    while (zero < 11 && !(payload[zero / 8] & (0x80u >> (zero % 8))))
        ++zero;
    if (zero == 11)
        return -1;
    for (unsigned i = zero + 1; i <= 2 * zero; ++i)
        value = (value << 1) | !!(payload[i / 8] & (0x80u >> (i % 8)));
    return (int)value - 1;
}

static int write_frame(size_t size)
{
    unsigned count = 0;
    for (size_t start = start_code(base, size, 0); start < size;) {
        size_t nal = start + (base[start + 2] ? 3 : 4);
        if (nal >= size)
            return -1;
        size_t end = start_code(base, size, nal + 1);
        int mb = (base[nal] & 31) == 5 ? first_mb(base + nal + 1, end - nal - 1) : -1;
        if (mb >= 630 && mb <= 830 && (mb - 630) % 40 == 0) {
            if (render_slice((unsigned)(mb - 630) / 40, (unsigned)mb))
                return -1;
            ++count;
        } else if (append(base + start, end - start))
            return -1;
        start = end;
    }
    return count == 6 ? 0 : -1;
}

static void draw(const char *value, unsigned y)
{
    const unsigned x_start = 32;
    size_t length =
        strspn(value, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-");
    if (!length || length > 16 || value[length])
        value = "-";
    for (unsigned i = 0; value[i]; ++i) {
        unsigned char code = (unsigned char)value[i];
        if (code < FIRST_ASCII || code > LAST_ASCII)
            code = '-';
        const unsigned char *glyph = font + (code - FIRST_ASCII) * GLYPH_W * GLYPH_H;
        for (unsigned line = 0; line < GLYPH_H; ++line)
            for (unsigned x = 0; x < GLYPH_W; ++x) {
                unsigned char *pixel = &strip[(y + line) * WIDTH + x_start + i * GLYPH_W + x];
                *pixel += glyph[line * GLYPH_W + x] * (234 - *pixel) / 255;
            }
    }
}

static size_t load(const char *path, unsigned char *data, size_t capacity)
{
    FILE *file = fopen(path, "rb");
    if (!file)
        return 0;
    size_t size = fread(data, 1, capacity, file);
    int valid = !ferror(file) && fgetc(file) == EOF;
    fclose(file);
    return valid ? size : 0;
}

int main(int argc, char **argv)
{
    if (argc != 7)
        return 2;
    size_t size = load(argv[1], base, sizeof base);
    if (!size || load(argv[2], strip, sizeof strip) != sizeof strip ||
        load(argv[3], font, sizeof font) != sizeof font)
        return 2;
    draw(argv[4], 2);
    draw(argv[5], 29);
    draw(argv[6], 56);
    draw("getdextend.com", 83);
    if (write_frame(size))
        return 2;
    return fwrite(output, 1, output_size, stdout) == output_size ? 0 : 2;
}
