/* SPDX-License-Identifier: GPL-2.0-only
 * Implementation of the public AOA 1.0 control-request format.
 * No vendor module or firmware code is incorporated.
 */
/*
 * Dextend | Developed by Overev
 * Copyright (c) 2026 Overev | https://overev.com/
 */

#ifndef YAMAHA_AOA_PROTOCOL_H
#define YAMAHA_AOA_PROTOCOL_H
enum aoa_action { AOA_STALL, AOA_PROTOCOL, AOA_STRING, AOA_START };
static inline enum aoa_action aoa_request(unsigned type, unsigned request, unsigned value,
                                          unsigned index, unsigned length)
{
    if (value != 0)
        return AOA_STALL;
    if (type == 0xc0 && request == 51 && index == 0 && length == 2)
        return AOA_PROTOCOL;
    /* Yamaha can send an empty optional string without a terminator. */
    if (type == 0x40 && request == 52 && index < 6 && length <= 256)
        return AOA_STRING;
    if (type == 0x40 && request == 53 && index == 0 && length == 0)
        return AOA_START;
    return AOA_STALL;
}
#endif
