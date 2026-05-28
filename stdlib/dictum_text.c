#include "dictum_text.h"
#include <string.h>
#include <ctype.h>
#include <stdio.h>
#include <stdarg.h>

/* Rule 2: Bounded string operations */
dictum_count_t dictum_text_length(const char* s) {
    if (!s) return 0;
    return (dictum_count_t)dictum_strnlen(s, DICTUM_MAX_STRING);
}

dictum_count_t dictum_text_find(const char* s, const char* pattern) {
    if (!s || !pattern) return 0;
    const char* found = strstr(s, pattern);
    return found ? (dictum_count_t)(found - s) + 1 : 0;
}

dictum_count_t dictum_text_find_from(const char* s, const char* pattern, dictum_count_t start) {
    if (!s || !pattern) return 0;
    size_t len = dictum_text_length(s);
    if (start >= len) return 0;
    const char* found = strstr(s + start, pattern);
    return found ? (dictum_count_t)(found - s) + 1 : 0;
}

char* dictum_text_slice(const char* s, dictum_count_t start, dictum_count_t end) {
    if (!s) return NULL;
    dictum_count_t len = dictum_text_length(s);
    if (start > end || end > len) return NULL;

    dictum_count_t out_len = end - start;
    char* out = dictum_alloc(out_len + 1);
    if (!out) return NULL;

    memcpy(out, s + start, out_len);
    out[out_len] = '\0';
    return out;
}

char* dictum_text_join(const char* a, const char* b) {
    if (!a || !b) return NULL;
    dictum_count_t len_a = dictum_text_length(a);
    dictum_count_t len_b = dictum_text_length(b);

    size_t total;
    if (!dictum_checked_add(len_a, len_b, &total)) return NULL;
    if (!dictum_checked_add(total, 1, &total)) return NULL;

    char* out = dictum_alloc(total);
    if (!out) return NULL;

    memcpy(out, a, len_a);
    memcpy(out + len_a, b, len_b);
    out[total - 1] = '\0';
    return out;
}

char* dictum_text_split(const char* s, const char* delim) {
    if (!s || !delim) return NULL;
    const char* found = strstr(s, delim);
    if (!found) return dictum_strdup(s);
    return dictum_text_slice(s, 0, (dictum_count_t)(found - s));
}

char* dictum_text_trim(const char* s) {
    if (!s) return NULL;
    while (isspace((unsigned char)*s)) s++;
    if (*s == '\0') return dictum_strdup("");
    const char* end = s + strlen(s) - 1;
    while (end > s && isspace((unsigned char)*end)) end--;
    return dictum_text_slice(s, 0, (dictum_count_t)(end - s) + 1);
}

char* dictum_text_to_upper(const char* s) {
    if (!s) return NULL;
    size_t len = dictum_text_length(s);
    char* out = dictum_alloc(len + 1);
    if (!out) return NULL;
    for (size_t i = 0; i < len; i++) {
        out[i] = (char)toupper((unsigned char)s[i]);
    }
    out[len] = '\0';
    return out;
}

char* dictum_text_to_lower(const char* s) {
    if (!s) return NULL;
    size_t len = dictum_text_length(s);
    char* out = dictum_alloc(len + 1);
    if (!out) return NULL;
    for (size_t i = 0; i < len; i++) {
        out[i] = (char)tolower((unsigned char)s[i]);
    }
    out[len] = '\0';
    return out;
}

char* dictum_text_replace(const char* s, const char* old, const char* new_str) {
    if (!s || !old || !new_str) return NULL;
    size_t s_len   = dictum_text_length(s);
    size_t old_len = dictum_text_length(old);
    size_t new_len = dictum_text_length(new_str);
    if (old_len == 0) return dictum_strdup(s);

    size_t count = 0;
    const char* tmp = s;
    while ((tmp = strstr(tmp, old)) != NULL) {
        count++;
        tmp += old_len;
    }

    size_t result_size;
    if (!dictum_checked_mul(count, new_len, &result_size)) return NULL;
    size_t sub;
    if (!dictum_checked_mul(count, old_len, &sub)) return NULL;
    if (!dictum_checked_add(result_size, s_len - sub, &result_size)) return NULL;
    if (!dictum_checked_add(result_size, 1, &result_size)) return NULL;

    char* result = dictum_alloc(result_size);
    if (!result) return NULL;

    char* dst = result;
    const char* src = s;
    while ((tmp = strstr(src, old)) != NULL) {
        size_t prefix = (size_t)(tmp - src);
        memcpy(dst, src, prefix);
        dst += prefix;
        memcpy(dst, new_str, new_len);
        dst += new_len;
        src = tmp + old_len;
    }
    strcpy(dst, src);
    return result;
}

dictum_truth_t dictum_text_compare(const char* a, const char* b) {
    if (!a || !b) return 0;
    return strcmp(a, b) == 0;
}

dictum_truth_t dictum_text_starts_with(const char* s, const char* prefix) {
    if (!s || !prefix) return 0;
    size_t s_len = dictum_text_length(s);
    size_t p_len = dictum_text_length(prefix);
    if (p_len > s_len) return 0;
    return strncmp(s, prefix, p_len) == 0;
}

dictum_truth_t dictum_text_ends_with(const char* s, const char* suffix) {
    if (!s || !suffix) return 0;
    size_t s_len = dictum_text_length(s);
    size_t x_len = dictum_text_length(suffix);
    if (x_len > s_len) return 0;
    return strcmp(s + s_len - x_len, suffix) == 0;
}

/* P1.6: dictum_text_format — safe sprintf-based string formatting.
   Uses vsnprintf with a growing buffer. Returns heap-allocated result. */
char* dictum_text_format(const char* fmt, ...) {
    if (!fmt) return NULL;

    /* First pass: measure */
    va_list args1, args2;
    va_start(args1, fmt);
    va_copy(args2, args1);
    int needed = vsnprintf(NULL, 0, fmt, args1);
    va_end(args1);

    if (needed < 0) {
        va_end(args2);
        return NULL;
    }

    size_t sz;
    if (!dictum_checked_add((size_t)needed, 1, &sz)) {
        va_end(args2);
        return NULL;
    }
    if (sz > DICTUM_MAX_STRING) {
        va_end(args2);
        dictum_error_set("dictum_text_format: result too large");
        return NULL;
    }

    char* out = dictum_alloc(sz);
    if (!out) { va_end(args2); return NULL; }

    vsnprintf(out, sz, fmt, args2);
    va_end(args2);
    return out;
}

/* P1.6: dictum_text_format_int — format a whole number as text */
char* dictum_text_from_int(dictum_whole_t n) {
    return dictum_text_format("%d", n);
}

/* P1.6: dictum_text_format_float — format a decimal number as text */
char* dictum_text_from_float(dictum_fractional_t f) {
    return dictum_text_format("%g", f);
}

/* P7.1: UTF-8 codepoint count (not byte count) */
dictum_count_t dictum_text_utf8_length(const char* s) {
    if (!s) return 0;
    dictum_count_t count = 0;
    size_t max = dictum_strnlen(s, DICTUM_MAX_STRING);
    for (size_t i = 0; i < max; ) {
        unsigned char c = (unsigned char)s[i];
        if (c == 0) break;
        if      ((c & 0x80) == 0x00) i += 1;
        else if ((c & 0xE0) == 0xC0) i += 2;
        else if ((c & 0xF0) == 0xE0) i += 3;
        else if ((c & 0xF8) == 0xF0) i += 4;
        else                          i += 1; /* invalid byte, skip */
        count++;
    }
    return count;
}

/* dictum_text_contains — convenience wrapper */
dictum_truth_t dictum_text_contains(const char* s, const char* sub) {
    if (!s || !sub) return 0;
    return strstr(s, sub) != NULL;
}

/* ─── UTF-8 grapheme cluster support ────────────────────────────── */
/*
 * Grapheme cluster: a user-perceived character. In most cases a grapheme
 * is a single codepoint, but combining marks (accent + base letter),
 * emoji ZWJ sequences, and Hangul jamo are multi-codepoint graphemes.
 *
 * We implement the most common cases:
 *   - Skip combining marks (U+0300–U+036F, U+1AB0–U+1AFF, U+1DC0–U+1DFF,
 *     U+20D0–U+20FF, U+FE20–U+FE2F)
 *   - Skip Zero-Width Joiner (U+200D) and the character following it
 *   - Skip Variation Selectors (U+FE0F, U+FE0E)
 *   - Emoji keycap and regional indicator pairs
 *
 * This covers the vast majority of real-world text without pulling in ICU.
 */

/* Decode one UTF-8 codepoint from s; advance *s past it. Returns 0 on error. */
static uint32_t utf8_decode(const char** s) {
    const unsigned char* p = (const unsigned char*)*s;
    if (!p || !*p) return 0;

    uint32_t cp;
    size_t bytes;

    if (*p < 0x80)        { cp = *p;                   bytes = 1; }
    else if (*p < 0xC0)   { (*s)++; return 0xFFFD; }   /* continuation byte */
    else if (*p < 0xE0)   { cp = *p & 0x1F;            bytes = 2; }
    else if (*p < 0xF0)   { cp = *p & 0x0F;            bytes = 3; }
    else if (*p < 0xF8)   { cp = *p & 0x07;            bytes = 4; }
    else                  { (*s)++; return 0xFFFD; }

    for (size_t i = 1; i < bytes; i++) {
        if ((p[i] & 0xC0) != 0x80) { *s += i; return 0xFFFD; }
        cp = (cp << 6) | (p[i] & 0x3F);
    }
    *s += bytes;
    return cp;
}

/* True if cp is a combining mark / ZWJ / variation selector */
static int is_combining(uint32_t cp) {
    /* Combining Diacritical Marks */
    if (cp >= 0x0300 && cp <= 0x036F) return 1;
    if (cp >= 0x1AB0 && cp <= 0x1AFF) return 1;
    if (cp >= 0x1DC0 && cp <= 0x1DFF) return 1;
    if (cp >= 0x20D0 && cp <= 0x20FF) return 1;
    if (cp >= 0xFE20 && cp <= 0xFE2F) return 1;
    /* Variation selectors */
    if (cp == 0xFE0E || cp == 0xFE0F) return 1;
    if (cp >= 0xFE00 && cp <= 0xFE0F) return 1;
    if (cp >= 0xE0100 && cp <= 0xE01EF) return 1;
    /* Zero-width joiner (handled separately as it pulls in next cp) */
    return 0;
}

/* True if cp is a Regional Indicator Symbol (emoji flags come in pairs) */
static int is_regional_indicator(uint32_t cp) {
    return cp >= 0x1F1E6 && cp <= 0x1F1FF;
}

/* Count grapheme clusters in a UTF-8 string. */
dictum_count_t dictum_text_grapheme_length(const char* s) {
    if (!s) return 0;
    dictum_count_t clusters = 0;
    const char* p = s;

    while (*p) {
        uint32_t cp = utf8_decode(&p);
        if (cp == 0) break;
        clusters++;

        /* Consume combining marks that don't start a new cluster */
        while (*p) {
            const char* save = p;
            uint32_t next = utf8_decode(&p);
            if (next == 0) { p = save; break; }

            if (is_combining(next)) {
                /* absorbed into the current cluster */
                continue;
            }
            if (next == 0x200D) {
                /* ZWJ: absorb the ZWJ and the next character into this cluster */
                if (*p) utf8_decode(&p);
                continue;
            }
            if (is_regional_indicator(cp) && is_regional_indicator(next)) {
                /* flag emoji: two regional indicators = one cluster */
                cp = next;
                continue;
            }
            /* Not a combining character — put it back */
            p = save;
            break;
        }
    }
    return clusters;
}

/* Slice by grapheme clusters [start, end) — returns newly allocated string. */
char* dictum_text_grapheme_slice(const char* s, dictum_count_t start,
                                  dictum_count_t end) {
    if (!s || start >= end) return dictum_strdup("");

    dictum_count_t cluster_idx = 0;
    const char* p = s;
    const char* slice_start = NULL;
    const char* slice_end   = NULL;

    while (*p) {
        if (cluster_idx == start) slice_start = p;

        /* consume one grapheme cluster */
        uint32_t cp = utf8_decode(&p);
        if (cp == 0) break;
        while (*p) {
            const char* save = p;
            uint32_t next = utf8_decode(&p);
            if (next == 0) { p = save; break; }
            if (is_combining(next)) continue;
            if (next == 0x200D) { if (*p) utf8_decode(&p); continue; }
            if (is_regional_indicator(cp) && is_regional_indicator(next)) {
                cp = next; continue;
            }
            p = save; break;
        }

        cluster_idx++;
        if (cluster_idx == end) { slice_end = p; break; }
    }

    if (!slice_start) return dictum_strdup("");
    if (!slice_end)   slice_end = p;

    size_t len = (size_t)(slice_end - slice_start);
    char* out = dictum_alloc(len + 1);
    if (!out) return NULL;
    memcpy(out, slice_start, len);
    out[len] = '\0';
    return out;
}

/* Reverse a UTF-8 string by grapheme clusters (not bytes). */
char* dictum_text_grapheme_reverse(const char* s) {
    if (!s || !*s) return dictum_strdup("");

    /* Collect cluster byte spans */
    typedef struct { const char* start; size_t len; } span_t;
    /* max 4096 clusters */
    span_t spans[4096];
    int nspan = 0;

    const char* p = s;
    while (*p && nspan < 4096) {
        const char* cs = p;
        uint32_t cp = utf8_decode(&p);
        if (cp == 0) break;
        while (*p) {
            const char* save = p;
            uint32_t next = utf8_decode(&p);
            if (next == 0) { p = save; break; }
            if (is_combining(next)) continue;
            if (next == 0x200D) { if (*p) utf8_decode(&p); continue; }
            if (is_regional_indicator(cp) && is_regional_indicator(next)) {
                cp = next; continue;
            }
            p = save; break;
        }
        spans[nspan].start = cs;
        spans[nspan].len   = (size_t)(p - cs);
        nspan++;
    }

    size_t total = strlen(s);
    char* out = dictum_alloc(total + 1);
    if (!out) return NULL;

    size_t pos = 0;
    for (int i = nspan - 1; i >= 0; i--) {
        memcpy(out + pos, spans[i].start, spans[i].len);
        pos += spans[i].len;
    }
    out[pos] = '\0';
    return out;
}

/* Normalize: decompose then recompose (stub — returns copy; full NFC needs Unicode tables) */
char* dictum_text_normalize(const char* s) {
    /* Without ICU, full NFC is impractical. Return a validated UTF-8 copy,
       replacing invalid sequences with U+FFFD (EF BF BD). */
    if (!s) return dictum_strdup("");
    size_t len = strlen(s);
    char* out = dictum_alloc(len * 3 + 1);  /* worst case: each byte → 3 bytes FFFD */
    if (!out) return NULL;

    const char* p = s;
    size_t op = 0;
    while (*p) {
        const char* save = p;
        uint32_t cp = utf8_decode(&p);
        if (cp == 0xFFFD && p == save + 1) {
            /* Invalid byte — emit U+FFFD */
            out[op++] = (char)0xEF;
            out[op++] = (char)0xBF;
            out[op++] = (char)0xBD;
        } else {
            size_t span = (size_t)(p - save);
            memcpy(out + op, save, span);
            op += span;
        }
    }
    out[op] = '\0';
    return out;
}
