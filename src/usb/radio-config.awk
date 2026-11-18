# Dextend | Developed by Overev
# Copyright (c) 2026 Overev | https://overev.com/

# Change only the two OEM display-name fields; never evaluate JSON.

{
    texts[FILENAME] = texts[FILENAME] $0 "\n"
}

END {
    if (bad) {
        exit 1
    }
    parse(texts[ARGV[1]], 1)
    if (action == "restore") {
        parse(texts[ARGV[2]], 2)
        same = 1
        for (i = 1; i <= count[1]; i++) {
            k = keys[1, i]
            if (! owned(k) && fields[1, k] != fields[2, k]) {
                same = 0
            }
        }
        for (i = 1; i <= count[2]; i++) {
            k = keys[2, i]
            if (! owned(k) && fields[1, k] != fields[2, k]) {
                same = 0
            }
        }
        if (same) {
            printf "%s", texts[ARGV[2]]
            exit
        }
    } else if (action != "apply") {
        fail()
    }
    printf "{\n"
    for (i = 1; i <= count[1]; i++) {
        k = keys[1, i]
        if (! owned(k)) {
            emit(k, fields[1, k])
        }
    }
    if (action == "apply") {
        emit("CustomWifiName", "\"Dextend\"")
        emit("CustomBluetoothName", "\"Dextend\"")
    } else {
        for (i = 1; i <= count[2]; i++) {
            k = keys[2, i]
            if (owned(k)) {
                emit(k, fields[2, k])
            }
        }
    }
    printf "\n}\n"
}

function emit(k, v)
{
    if (comma) {
        printf ",\n"
    }
    printf "  \"%s\": %s", k, v
    comma = 1
}

function fail()
{
    bad = 1
    exit 1
}

function owned(k)
{
    return (k == "CustomWifiName" || k == "CustomBluetoothName")
}

function parse(text, which, key, start, n)
{
    s = text
    p = 1
    ws()
    if (substr(s, p++, 1) != "{") {
        fail()
    }
    ws()
    if (substr(s, p, 1) != "}") {
        while (1) {
            ws()
            start = p
            string()
            key = substr(s, start + 1, p - start - 2)
            # OEM keys are plain ASCII. Refuse ambiguous escaped aliases.
            if (key ~ /\\/ || ((which SUBSEP key) in fields)) {
                fail()
            }
            ws()
            if (substr(s, p++, 1) != ":") {
                fail()
            }
            ws()
            start = p
            value(0)
            fields[which, key] = substr(s, start, p - start)
            keys[which, ++count[which]] = key
            ws()
            if (substr(s, p, 1) == "}") {
                break
            }
            if (substr(s, p++, 1) != ",") {
                fail()
            }
        }
    }
    p++
    ws()
    if (p <= length(s)) {
        fail()
    }
}

function string(c, h)
{
    if (substr(s, p++, 1) != "\"") {
        fail()
    }
    while (p <= length(s)) {
        c = substr(s, p++, 1)
        if (c == "\"") {
            return
        }
        if (c == "\\") {
            c = substr(s, p++, 1)
            if (c == "u") {
                h = substr(s, p, 4)
                if (length(h) != 4 || h ~ /[^0-9a-fA-F]/) {
                    fail()
                }
                p += 4
            } else if (! index("\"\\/bfnrt", c) || c == "") {
                fail()
            }
        } else if (c ~ /[[:cntrl:]]/) {
            fail()
        }
    }
    fail()
}

function value(depth, c, k, start, token, seen)
{
    if (depth > 32) {
        fail()
    }
    ws()
    c = substr(s, p, 1)
    if (c == "\"") {
        string()
        return
    }
    if (c == "{" || c == "[") {
        p++
        ws()
        if (substr(s, p, 1) == (c == "{" ? "}" : "]")) {
            p++
            return
        }
        while (1) {
            if (c == "{") {
                ws()
                string()
                ws()
                if (substr(s, p++, 1) != ":") {
                    fail()
                }
            }
            value(depth + 1)
            ws()
            k = substr(s, p++, 1)
            if (k == (c == "{" ? "}" : "]")) {
                return
            }
            if (k != ",") {
                fail()
            }
        }
    }
    token = substr(s, p)
    if (match(token, /^(true|false|null)/)) {
        p += RLENGTH
        return
    }
    if (match(token, /^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?/)) {
        p += RLENGTH
        return
    }
    fail()
}

function ws()
{
    while (substr(s, p, 1) ~ /[ \t\r\n]/ && p <= length(s)) {
        p++
    }
}
