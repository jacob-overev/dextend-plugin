/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

/* Strict SPS gate for this PoC: progressive 4:2:0 8-bit 800x480 only. */
#include "aa-geometry.h"

struct bits {
    unsigned char p[4096];
    size_t n, pos;
    int bad;
};
static unsigned bit_read(struct bits *b, unsigned count)
{
    if (count > 32 || count > b->n * 8 - b->pos) {
        b->bad = 1;
        return 0;
    }
    unsigned v = 0;
    while (count--) {
        v = (v << 1) | ((b->p[b->pos / 8] >> (7 - b->pos % 8)) & 1);
        b->pos++;
    }
    return v;
}
static unsigned ue(struct bits *b)
{
    unsigned zeros = 0;
    while (!b->bad && !bit_read(b, 1)) {
        if (++zeros > 20) {
            b->bad = 1;
            return 0;
        }
    }
    return b->bad ? 0 : ((1U << zeros) - 1 + bit_read(b, zeros));
}
static int se(struct bits *b)
{
    unsigned v = ue(b);
    return v & 1 ? (int)((v + 1) / 2) : -(int)(v / 2);
}
static void put_bit(unsigned char *p, size_t *pos, unsigned bit)
{
    if (bit)
        p[*pos / 8] |= 1U << (7 - *pos % 8);
    ++*pos;
}
static int aa_crop_sps(const unsigned char *p, size_t n, unsigned char *out,
                       const struct aa_geometry *geometry)
{
    struct bits b = {0};
    if (n < 5 || n > 512 || (p[0] & 31) != 7)
        return 0;
    unsigned zeros = 0;
    for (size_t i = 1; i < n; i++) {
        if (zeros == 2 && p[i] == 3) {
            if (i + 1 == n || p[i + 1] > 3)
                return 0;
            zeros = 0;
            continue;
        }
        b.p[b.n++] = p[i];
        zeros = p[i] == 0 ? zeros + 1 : 0;
    }
    unsigned profile = bit_read(&b, 8);
    bit_read(&b, 8);
    unsigned level = bit_read(&b, 8);
    ue(&b);
    if (level > 31)
        return 0;
    if (profile == 100 || profile == 110 || profile == 122 || profile == 244 || profile == 44 ||
        profile == 83 || profile == 86 || profile == 118 || profile == 128 || profile == 138 ||
        profile == 139 || profile == 134 || profile == 135) {
        if (ue(&b) != 1 || ue(&b) != 0 || ue(&b) != 0)
            return 0;
        bit_read(&b, 1);
        if (bit_read(&b, 1)) {
            for (unsigned i = 0; i < 8; i++)
                if (bit_read(&b, 1)) {
                    int last = 8, next = 8;
                    for (unsigned j = 0; j < (i < 6 ? 16U : 64U); j++) {
                        if (next)
                            next = (last + se(&b) + 256) % 256;
                        last = next ? next : last;
                    }
                }
        }
    } else if (profile != 66 && profile != 77 && profile != 88)
        return 0;
    if (ue(&b) > 12)
        return 0;
    unsigned poc = ue(&b);
    if (poc == 0) {
        if (ue(&b) > 12)
            return 0;
    } else if (poc == 1) {
        bit_read(&b, 1);
        se(&b);
        se(&b);
        unsigned cycle = ue(&b);
        if (cycle > 256)
            return 0;
        for (unsigned i = 0; i < cycle; i++)
            se(&b);
    } else if (poc > 2)
        return 0;
    ue(&b);
    bit_read(&b, 1);
    unsigned w = ue(&b), h = ue(&b), progressive = bit_read(&b, 1);
    if (!progressive || w != 49 || h != 29)
        return 0;
    bit_read(&b, 1);
    size_t crop = b.pos;
    if (bit_read(&b, 1)) {
        unsigned l = ue(&b), r = ue(&b), t = ue(&b), bottom = ue(&b);
        if (l || r || t || bottom)
            return 0;
    }
    if (b.bad)
        return 0;
    size_t end = b.n * 8;
    while (end > b.pos && !(b.p[(end - 1) / 8] & (1U << (7 - (end - 1) % 8))))
        --end;
    if (end <= b.pos)
        return 0;
    unsigned char rbsp[544] = {0};
    size_t pos = 0;
    for (size_t i = 0; i < crop; i++)
        put_bit(rbsp, &pos, (b.p[i / 8] >> (7 - i % 8)) & 1);
    put_bit(rbsp, &pos, 1);
    /* Progressive 4:2:0 SPS crop offsets are in units of two pixels. */
    const unsigned offsets[] = {geometry->left / 2, geometry->right / 2,
                                geometry->top / 2, geometry->bottom / 2};
    for (unsigned i = 0; i < 4; i++) {
        unsigned v = offsets[i] + 1, log = 0;
        for (unsigned x = v; x > 1; x >>= 1)
            ++log;
        for (unsigned j = 0; j < log; j++)
            put_bit(rbsp, &pos, 0);
        for (int j = (int)log; j >= 0; j--)
            put_bit(rbsp, &pos, (v >> j) & 1);
    }
    for (size_t i = b.pos; i < end; i++)
        put_bit(rbsp, &pos, (b.p[i / 8] >> (7 - i % 8)) & 1);
    size_t size = 1;
    out[0] = p[0];
    zeros = 0;
    for (size_t i = 0; i < (pos + 7) / 8; i++) {
        if (zeros == 2 && rbsp[i] <= 3) {
            out[size++] = 3;
            zeros = 0;
        }
        out[size++] = rbsp[i];
        zeros = rbsp[i] == 0 ? zeros + 1 : 0;
    }
    return (int)size;
}
