/*
 * dictum_json.c — recursive-descent JSON parser for Dictum v5.
 *
 * Replaces the flat string-only pool parser. Now handles:
 *   • Nested objects  { "key": { "inner": "val" } }
 *   • Arrays          { "items": [1, 2, 3] }
 *   • Integer values  { "count": 42 }
 *   • Float values    { "ratio": 3.14 }
 *   • Bool/null       { "ok": true, "data": null }
 *   • Escaped strings { "msg": "hello \"world\"" }
 *   • dictum_json_get_string / dictum_json_get_int (roadmap P1.2 API)
 *
 * Design: nodes are stored in a fixed-size arena (no malloc per node).
 * Each node is one of: OBJECT, ARRAY, STRING, NUMBER, BOOL, NULL_NODE.
 * Children/siblings are linked via indices into the arena.
 *
 * Public API matches dictum_json.h exactly.
 */

#include "dictum_json.h"
#include "dictum_error.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>
#include <math.h>

/* ─── Arena limits ───────────────────────────────────────────────── */
#define DJ_MAX_NODES  4096   /* max total JSON nodes per parse          */
#define DJ_MAX_STR    65536  /* max character pool per parse            */
#define DJ_MAX_ROOTS  64     /* max concurrent parsed documents          */

/* ─── Node types ─────────────────────────────────────────────────── */
typedef enum {
    DJ_OBJECT = 0,
    DJ_ARRAY,
    DJ_STRING,
    DJ_NUMBER,
    DJ_BOOL,
    DJ_NULL
} dj_type_t;

/* ─── Node ───────────────────────────────────────────────────────── */
typedef struct {
    dj_type_t   type;
    int32_t     key_off;   /* offset into str_pool; -1 if no key       */
    int32_t     val_off;   /* for STRING: str offset; NUMBER: unused    */
    double      num;       /* for NUMBER and BOOL (0.0/1.0)            */
    int32_t     child;     /* first child index (-1 = none)            */
    int32_t     next;      /* next sibling (-1 = none)                 */
    int32_t     root_id;   /* which document owns this node            */
} dj_node_t;

/* ─── Document (one parsed JSON value) ──────────────────────────── */
typedef struct {
    int32_t     root_node; /* index of root node in g_nodes             */
    int32_t     active;
} dj_doc_t;

/* ─── Global arenas ─────────────────────────────────────────────── */
static dj_node_t  g_nodes[DJ_MAX_NODES];
static int32_t    g_node_count = 0;

static char       g_strs[DJ_MAX_STR];
static int32_t    g_str_top = 0;

static dj_doc_t   g_docs[DJ_MAX_ROOTS];
static int32_t    g_doc_count = 0;

/* ─── Init (lazy) ────────────────────────────────────────────────── */
static void dj_init(void) {
    static int initialized = 0;
    if (initialized) return;
    initialized = 1;
    memset(g_nodes, 0, sizeof(g_nodes));
    memset(g_strs,  0, sizeof(g_strs));
    memset(g_docs,  0, sizeof(g_docs));
}

/* ─── String pool ────────────────────────────────────────────────── */
static int32_t dj_str_intern(const char* s, size_t len) {
    if (!s || g_str_top + (int32_t)len + 1 >= DJ_MAX_STR) return -1;
    int32_t off = g_str_top;
    memcpy(g_strs + off, s, len);
    g_strs[off + len] = '\0';
    g_str_top += (int32_t)len + 1;
    return off;
}

/* ─── Node allocation ────────────────────────────────────────────── */
static int32_t dj_alloc_node(int32_t doc_id) {
    if (g_node_count >= DJ_MAX_NODES) return -1;
    int32_t idx = g_node_count++;
    g_nodes[idx].type    = DJ_NULL;
    g_nodes[idx].key_off = -1;
    g_nodes[idx].val_off = -1;
    g_nodes[idx].num     = 0.0;
    g_nodes[idx].child   = -1;
    g_nodes[idx].next    = -1;
    g_nodes[idx].root_id = doc_id;
    return idx;
}

/* ─── Parser state ───────────────────────────────────────────────── */
typedef struct {
    const char* src;
    size_t      pos;
    size_t      len;
    int32_t     doc_id;
    int         error;
} dj_ctx_t;

static void dj_skip_ws(dj_ctx_t* cx) {
    while (cx->pos < cx->len && isspace((unsigned char)cx->src[cx->pos]))
        cx->pos++;
}

static char dj_peek(dj_ctx_t* cx) {
    dj_skip_ws(cx);
    return (cx->pos < cx->len) ? cx->src[cx->pos] : '\0';
}

static char dj_next(dj_ctx_t* cx) {
    dj_skip_ws(cx);
    return (cx->pos < cx->len) ? cx->src[cx->pos++] : '\0';
}

/* parse a JSON string value (after opening '"'), return str pool offset */
static int32_t dj_parse_string_raw(dj_ctx_t* cx) {
    /* caller consumed the opening '"' */
    size_t start = cx->pos;
    char   buf[4096];
    size_t blen = 0;

    while (cx->pos < cx->len) {
        char c = cx->src[cx->pos++];
        if (c == '"') {
            return dj_str_intern(buf, blen);
        }
        if (c == '\\' && cx->pos < cx->len) {
            char esc = cx->src[cx->pos++];
            switch (esc) {
                case '"':  c = '"';  break;
                case '\\': c = '\\'; break;
                case '/':  c = '/';  break;
                case 'n':  c = '\n'; break;
                case 'r':  c = '\r'; break;
                case 't':  c = '\t'; break;
                case 'b':  c = '\b'; break;
                case 'f':  c = '\f'; break;
                default:   c = esc;  break;
            }
        }
        if (blen < sizeof(buf) - 1) buf[blen++] = c;
    }
    (void)start;
    cx->error = 1;
    return -1;
}

/* forward declaration */
static int32_t dj_parse_value(dj_ctx_t* cx);

static int32_t dj_parse_object(dj_ctx_t* cx) {
    /* caller consumed '{' */
    int32_t node = dj_alloc_node(cx->doc_id);
    if (node < 0) { cx->error = 1; return -1; }
    g_nodes[node].type = DJ_OBJECT;

    int32_t* tail = &g_nodes[node].child;

    for (;;) {
        char c = dj_peek(cx);
        if (c == '}') { cx->pos++; break; }
        if (c == ',') { cx->pos++; continue; }
        if (c != '"') { cx->error = 1; return -1; }
        cx->pos++;  /* consume '"' */

        int32_t key_off = dj_parse_string_raw(cx);
        if (key_off < 0 || cx->error) return -1;

        c = dj_next(cx);
        if (c != ':') { cx->error = 1; return -1; }

        int32_t child = dj_parse_value(cx);
        if (child < 0 || cx->error) return -1;
        g_nodes[child].key_off = key_off;

        *tail = child;
        tail  = &g_nodes[child].next;
    }
    return node;
}

static int32_t dj_parse_array(dj_ctx_t* cx) {
    /* caller consumed '[' */
    int32_t node = dj_alloc_node(cx->doc_id);
    if (node < 0) { cx->error = 1; return -1; }
    g_nodes[node].type = DJ_ARRAY;

    int32_t* tail = &g_nodes[node].child;

    for (;;) {
        char c = dj_peek(cx);
        if (c == ']') { cx->pos++; break; }
        if (c == ',') { cx->pos++; continue; }

        int32_t child = dj_parse_value(cx);
        if (child < 0 || cx->error) return -1;

        *tail = child;
        tail  = &g_nodes[child].next;
    }
    return node;
}

static int32_t dj_parse_value(dj_ctx_t* cx) {
    char c = dj_peek(cx);
    if (c == '\0') { cx->error = 1; return -1; }

    /* Object */
    if (c == '{') { cx->pos++; return dj_parse_object(cx); }

    /* Array */
    if (c == '[') { cx->pos++; return dj_parse_array(cx); }

    /* String */
    if (c == '"') {
        cx->pos++;
        int32_t off = dj_parse_string_raw(cx);
        if (off < 0 || cx->error) return -1;
        int32_t node = dj_alloc_node(cx->doc_id);
        if (node < 0) { cx->error = 1; return -1; }
        g_nodes[node].type    = DJ_STRING;
        g_nodes[node].val_off = off;
        return node;
    }

    /* Number */
    if (c == '-' || isdigit((unsigned char)c)) {
        char nbuf[64];
        size_t nlen = 0;
        /* consume number chars */
        while (cx->pos < cx->len && nlen < sizeof(nbuf) - 1) {
            char nc = cx->src[cx->pos];
            if (!isdigit((unsigned char)nc) && nc != '-' &&
                nc != '+' && nc != '.' && nc != 'e' && nc != 'E') break;
            nbuf[nlen++] = nc;
            cx->pos++;
        }
        nbuf[nlen] = '\0';
        int32_t node = dj_alloc_node(cx->doc_id);
        if (node < 0) { cx->error = 1; return -1; }
        g_nodes[node].type = DJ_NUMBER;
        g_nodes[node].num  = atof(nbuf);
        return node;
    }

    /* true */
    if (strncmp(cx->src + cx->pos, "true", 4) == 0) {
        cx->pos += 4;
        int32_t node = dj_alloc_node(cx->doc_id);
        if (node < 0) { cx->error = 1; return -1; }
        g_nodes[node].type = DJ_BOOL;
        g_nodes[node].num  = 1.0;
        return node;
    }

    /* false */
    if (strncmp(cx->src + cx->pos, "false", 5) == 0) {
        cx->pos += 5;
        int32_t node = dj_alloc_node(cx->doc_id);
        if (node < 0) { cx->error = 1; return -1; }
        g_nodes[node].type = DJ_BOOL;
        g_nodes[node].num  = 0.0;
        return node;
    }

    /* null */
    if (strncmp(cx->src + cx->pos, "null", 4) == 0) {
        cx->pos += 4;
        int32_t node = dj_alloc_node(cx->doc_id);
        if (node < 0) { cx->error = 1; return -1; }
        g_nodes[node].type = DJ_NULL;
        return node;
    }

    cx->error = 1;
    return -1;
}

/* ─── Public API ─────────────────────────────────────────────────── */

dictum_whole_t dictum_json_parse(const char* s) {
    dj_init();
    if (!s) { dictum_error_set("dictum_json_parse: null input"); return -1; }

    /* Find a free document slot */
    int32_t doc_id = -1;
    for (int i = 0; i < DJ_MAX_ROOTS; i++) {
        if (!g_docs[i].active) { doc_id = i; break; }
    }
    if (doc_id < 0) {
        dictum_error_set("dictum_json_parse: document pool exhausted");
        return -1;
    }

    dj_ctx_t cx;
    cx.src    = s;
    cx.pos    = 0;
    cx.len    = strlen(s);
    cx.doc_id = doc_id;
    cx.error  = 0;

    int32_t root = dj_parse_value(&cx);
    if (root < 0 || cx.error) {
        dictum_error_set("dictum_json_parse: invalid JSON");
        return -1;
    }

    g_docs[doc_id].active    = 1;
    g_docs[doc_id].root_node = root;
    if (doc_id >= g_doc_count) g_doc_count = doc_id + 1;

    return (dictum_whole_t)doc_id;
}

/* Internal: find a child node by key name */
static int32_t dj_find_key(int32_t node_idx, const char* key) {
    if (node_idx < 0 || node_idx >= g_node_count) return -1;
    if (g_nodes[node_idx].type != DJ_OBJECT) return -1;
    int32_t child = g_nodes[node_idx].child;
    while (child >= 0) {
        int32_t ko = g_nodes[child].key_off;
        if (ko >= 0 && strcmp(g_strs + ko, key) == 0) return child;
        child = g_nodes[child].next;
    }
    return -1;
}

/* Internal: navigate a dot-separated path ("slideshow.author") */
static int32_t dj_nav(int32_t root_node, const char* key) {
    if (!key || root_node < 0) return -1;

    /* Check if key contains '.' — do path navigation */
    const char* dot = strchr(key, '.');
    if (!dot) return dj_find_key(root_node, key);

    char segment[256];
    size_t seg_len = (size_t)(dot - key);
    if (seg_len >= sizeof(segment)) return -1;
    memcpy(segment, key, seg_len);
    segment[seg_len] = '\0';

    int32_t child = dj_find_key(root_node, segment);
    if (child < 0) return -1;
    return dj_nav(child, dot + 1);
}

char* dictum_json_get(dictum_whole_t h, const char* key) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return NULL;
    int32_t root = g_docs[h].root_node;
    int32_t node = dj_nav(root, key);
    if (node < 0) return NULL;

    switch (g_nodes[node].type) {
        case DJ_STRING:
            if (g_nodes[node].val_off < 0) return dictum_strdup("");
            return dictum_strdup(g_strs + g_nodes[node].val_off);
        case DJ_NUMBER: {
            char buf[64];
            double v = g_nodes[node].num;
            if (v == (long long)v)
                snprintf(buf, sizeof(buf), "%lld", (long long)v);
            else
                snprintf(buf, sizeof(buf), "%g", v);
            return dictum_strdup(buf);
        }
        case DJ_BOOL:
            return dictum_strdup(g_nodes[node].num != 0.0 ? "true" : "false");
        case DJ_NULL:
            return dictum_strdup("null");
        case DJ_OBJECT:
            return dictum_strdup("[object]");
        case DJ_ARRAY:
            return dictum_strdup("[array]");
    }
    return NULL;
}

/* P1.2 roadmap API: get a string field */
char* dictum_json_get_string(dictum_whole_t h, const char* key) {
    return dictum_json_get(h, key);
}

/* P1.2 roadmap API: get an integer field */
dictum_whole_t dictum_json_get_int(dictum_whole_t h, const char* key) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return 0;
    int32_t root = g_docs[h].root_node;
    int32_t node = dj_nav(root, key);
    if (node < 0) return 0;
    if (g_nodes[node].type == DJ_NUMBER) return (dictum_whole_t)g_nodes[node].num;
    if (g_nodes[node].type == DJ_BOOL)   return (dictum_whole_t)g_nodes[node].num;
    return 0;
}

/* get a float/double field */
double dictum_json_get_float(dictum_whole_t h, const char* key) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return 0.0;
    int32_t root = g_docs[h].root_node;
    int32_t node = dj_nav(root, key);
    if (node < 0) return 0.0;
    if (g_nodes[node].type == DJ_NUMBER) return g_nodes[node].num;
    return 0.0;
}

/* get a truth value field */
dictum_truth_t dictum_json_get_bool(dictum_whole_t h, const char* key) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return 0;
    int32_t root = g_docs[h].root_node;
    int32_t node = dj_nav(root, key);
    if (node < 0) return 0;
    if (g_nodes[node].type == DJ_BOOL)   return (dictum_truth_t)(g_nodes[node].num != 0.0);
    if (g_nodes[node].type == DJ_NUMBER) return (dictum_truth_t)(g_nodes[node].num != 0.0);
    return 0;
}

dictum_truth_t dictum_json_set(dictum_whole_t h, const char* key, const char* value) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return 0;
    if (!key || !value) return 0;
    int32_t root = g_docs[h].root_node;
    if (root < 0 || g_nodes[root].type != DJ_OBJECT) return 0;

    /* Find existing key */
    int32_t child = g_nodes[root].child;
    while (child >= 0) {
        int32_t ko = g_nodes[child].key_off;
        if (ko >= 0 && strcmp(g_strs + ko, key) == 0) {
            /* Update: only works for string nodes */
            int32_t off = dj_str_intern(value, strlen(value));
            if (off < 0) return 0;
            g_nodes[child].type    = DJ_STRING;
            g_nodes[child].val_off = off;
            return 1;
        }
        child = g_nodes[child].next;
    }

    /* Insert new key */
    int32_t koff = dj_str_intern(key,   strlen(key));
    int32_t voff = dj_str_intern(value, strlen(value));
    if (koff < 0 || voff < 0) return 0;

    int32_t new_node = dj_alloc_node(h);
    if (new_node < 0) return 0;
    g_nodes[new_node].type    = DJ_STRING;
    g_nodes[new_node].key_off = koff;
    g_nodes[new_node].val_off = voff;

    /* Append to children */
    int32_t* tail = &g_nodes[root].child;
    while (*tail >= 0) tail = &g_nodes[*tail].next;
    *tail = new_node;
    return 1;
}

/* Recursive stringifier */
static void dj_write_str(char* buf, size_t cap, size_t* pos, const char* s) {
    while (*s && *pos < cap - 1) buf[(*pos)++] = *s++;
}

static void dj_stringify_node(int32_t idx, char* buf, size_t cap, size_t* pos);

static void dj_stringify_str(const char* s, char* buf, size_t cap, size_t* pos) {
    if (*pos < cap - 1) buf[(*pos)++] = '"';
    while (*s && *pos < cap - 2) {
        char c = *s++;
        if (c == '"' || c == '\\') { buf[(*pos)++] = '\\'; }
        buf[(*pos)++] = c;
    }
    if (*pos < cap - 1) buf[(*pos)++] = '"';
}

static void dj_stringify_node(int32_t idx, char* buf, size_t cap, size_t* pos) {
    if (idx < 0 || idx >= g_node_count || *pos >= cap - 1) return;
    dj_node_t* n = &g_nodes[idx];
    switch (n->type) {
        case DJ_STRING:
            dj_stringify_str(n->val_off >= 0 ? g_strs + n->val_off : "", buf, cap, pos);
            break;
        case DJ_NUMBER: {
            char tmp[64];
            if (n->num == (long long)n->num)
                snprintf(tmp, sizeof(tmp), "%lld", (long long)n->num);
            else
                snprintf(tmp, sizeof(tmp), "%g", n->num);
            dj_write_str(buf, cap, pos, tmp);
            break;
        }
        case DJ_BOOL:
            dj_write_str(buf, cap, pos, n->num != 0.0 ? "true" : "false");
            break;
        case DJ_NULL:
            dj_write_str(buf, cap, pos, "null");
            break;
        case DJ_OBJECT: {
            if (*pos < cap - 1) buf[(*pos)++] = '{';
            int32_t child = n->child;
            int first = 1;
            while (child >= 0) {
                if (!first && *pos < cap - 1) buf[(*pos)++] = ',';
                first = 0;
                int32_t ko = g_nodes[child].key_off;
                if (ko >= 0) dj_stringify_str(g_strs + ko, buf, cap, pos);
                if (*pos < cap - 1) buf[(*pos)++] = ':';
                dj_stringify_node(child, buf, cap, pos);
                child = g_nodes[child].next;
            }
            if (*pos < cap - 1) buf[(*pos)++] = '}';
            break;
        }
        case DJ_ARRAY: {
            if (*pos < cap - 1) buf[(*pos)++] = '[';
            int32_t child = n->child;
            int first = 1;
            while (child >= 0) {
                if (!first && *pos < cap - 1) buf[(*pos)++] = ',';
                first = 0;
                dj_stringify_node(child, buf, cap, pos);
                child = g_nodes[child].next;
            }
            if (*pos < cap - 1) buf[(*pos)++] = ']';
            break;
        }
    }
}

char* dictum_json_stringify(dictum_whole_t h) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return NULL;
    size_t cap = 65536;
    char*  buf = dictum_alloc(cap);
    if (!buf) return NULL;
    size_t pos = 0;
    dj_stringify_node(g_docs[h].root_node, buf, cap, &pos);
    buf[pos] = '\0';
    return buf;
}

void dictum_json_destroy(dictum_whole_t h) {
    if (h < 0 || h >= DJ_MAX_ROOTS) return;
    if (!g_docs[h].active) return;
    /* Mark all nodes owned by this doc as freed by clearing doc slot.
       Nodes remain in arena until reset — acceptable for embedded use. */
    g_docs[h].active    = 0;
    g_docs[h].root_node = -1;
}

/* ─── Array navigation (added: JSON array gap fix) ───────────────── */

/* Get the number of children (array elements or object fields) */
dictum_whole_t dictum_json_length(dictum_whole_t h) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return 0;
    int32_t root = g_docs[h].root_node;
    if (root < 0) return 0;
    int32_t count = 0;
    int32_t child = g_nodes[root].child;
    while (child >= 0) { count++; child = g_nodes[child].next; }
    return (dictum_whole_t)count;
}

/* Get array length at a key (e.g. h["items"] is an array — return its length) */
dictum_whole_t dictum_json_array_length(dictum_whole_t h, const char* key) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return 0;
    int32_t root = g_docs[h].root_node;
    int32_t node;
    if (key && key[0]) {
        node = dj_nav(root, key);
    } else {
        node = root;
    }
    if (node < 0 || g_nodes[node].type != DJ_ARRAY) return 0;
    int32_t count = 0;
    int32_t child = g_nodes[node].child;
    while (child >= 0) { count++; child = g_nodes[child].next; }
    return (dictum_whole_t)count;
}

/* Internal: get the Nth child node of a node */
static int32_t dj_get_nth(int32_t node_idx, int32_t n) {
    if (node_idx < 0 || node_idx >= g_node_count) return -1;
    int32_t child = g_nodes[node_idx].child;
    int32_t i = 0;
    while (child >= 0) {
        if (i == n) return child;
        child = g_nodes[child].next;
        i++;
    }
    return -1;
}

/* get element at index i from an array at key (empty key = root array) */
char* dictum_json_get_at(dictum_whole_t h, const char* key, dictum_whole_t index) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return NULL;
    int32_t root = g_docs[h].root_node;
    int32_t arr_node;
    if (key && key[0]) {
        arr_node = dj_nav(root, key);
    } else {
        arr_node = root;
    }
    if (arr_node < 0) return NULL;
    if (g_nodes[arr_node].type != DJ_ARRAY) return NULL;

    int32_t child = dj_get_nth(arr_node, (int32_t)index);
    if (child < 0) return NULL;

    switch (g_nodes[child].type) {
        case DJ_STRING:
            if (g_nodes[child].val_off < 0) return dictum_strdup("");
            return dictum_strdup(g_strs + g_nodes[child].val_off);
        case DJ_NUMBER: {
            char buf[64];
            double v = g_nodes[child].num;
            if (v == (long long)v)
                snprintf(buf, sizeof(buf), "%lld", (long long)v);
            else
                snprintf(buf, sizeof(buf), "%g", v);
            return dictum_strdup(buf);
        }
        case DJ_BOOL:
            return dictum_strdup(g_nodes[child].num != 0.0 ? "true" : "false");
        case DJ_NULL:
            return dictum_strdup("null");
        case DJ_OBJECT:
            return dictum_strdup("[object]");
        case DJ_ARRAY:
            return dictum_strdup("[array]");
    }
    return NULL;
}

/* get integer at index i from array at key */
dictum_whole_t dictum_json_get_int_at(dictum_whole_t h, const char* key,
                                       dictum_whole_t index) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return 0;
    int32_t root = g_docs[h].root_node;
    int32_t arr_node = (key && key[0]) ? dj_nav(root, key) : root;
    if (arr_node < 0 || g_nodes[arr_node].type != DJ_ARRAY) return 0;
    int32_t child = dj_get_nth(arr_node, (int32_t)index);
    if (child < 0) return 0;
    if (g_nodes[child].type == DJ_NUMBER) return (dictum_whole_t)g_nodes[child].num;
    return 0;
}

/* get float at index i from array at key */
double dictum_json_get_float_at(dictum_whole_t h, const char* key,
                                 dictum_whole_t index) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return 0.0;
    int32_t root = g_docs[h].root_node;
    int32_t arr_node = (key && key[0]) ? dj_nav(root, key) : root;
    if (arr_node < 0 || g_nodes[arr_node].type != DJ_ARRAY) return 0.0;
    int32_t child = dj_get_nth(arr_node, (int32_t)index);
    if (child < 0) return 0.0;
    if (g_nodes[child].type == DJ_NUMBER) return g_nodes[child].num;
    return 0.0;
}

/* get sub-object handle at index i (returns a new doc handle for the sub-object) */
dictum_whole_t dictum_json_get_object_at(dictum_whole_t h, const char* key,
                                          dictum_whole_t index) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active) return -1;
    int32_t root = g_docs[h].root_node;
    int32_t arr_node = (key && key[0]) ? dj_nav(root, key) : root;
    if (arr_node < 0 || g_nodes[arr_node].type != DJ_ARRAY) return -1;
    int32_t child = dj_get_nth(arr_node, (int32_t)index);
    if (child < 0) return -1;
    if (g_nodes[child].type != DJ_OBJECT) return -1;

    /* Create a new document slot pointing to this sub-object node */
    int32_t doc_id = -1;
    for (int i = 0; i < DJ_MAX_ROOTS; i++) {
        if (!g_docs[i].active) { doc_id = i; break; }
    }
    if (doc_id < 0) return -1;
    g_docs[doc_id].active    = 1;
    g_docs[doc_id].root_node = child;
    g_nodes[child].root_id   = doc_id;
    if (doc_id >= g_doc_count) g_doc_count = doc_id + 1;
    return (dictum_whole_t)doc_id;
}

/* dot-path with [N] index support: "items.[0].name" */
char* dictum_json_get_path(dictum_whole_t h, const char* path) {
    if (h < 0 || h >= DJ_MAX_ROOTS || !g_docs[h].active || !path) return NULL;

    int32_t node = g_docs[h].root_node;

    /* Tokenize path on '.' */
    char buf[512];
    dictum_strncpy(buf, sizeof(buf), path);
    char* seg = buf;

    while (seg && *seg && node >= 0) {
        char* dot = strchr(seg, '.');
        if (dot) *dot = '\0';

        /* Check if segment is [N] (array index) */
        if (seg[0] == '[') {
            int idx = atoi(seg + 1);
            if (g_nodes[node].type != DJ_ARRAY) return NULL;
            node = dj_get_nth(node, idx);
        } else {
            node = dj_find_key(node, seg);
        }

        seg = dot ? dot + 1 : NULL;
    }

    if (node < 0) return NULL;

    switch (g_nodes[node].type) {
        case DJ_STRING:
            if (g_nodes[node].val_off < 0) return dictum_strdup("");
            return dictum_strdup(g_strs + g_nodes[node].val_off);
        case DJ_NUMBER: {
            char num_buf[64];
            double v = g_nodes[node].num;
            if (v == (long long)v)
                snprintf(num_buf, sizeof(num_buf), "%lld", (long long)v);
            else
                snprintf(num_buf, sizeof(num_buf), "%g", v);
            return dictum_strdup(num_buf);
        }
        case DJ_BOOL:
            return dictum_strdup(g_nodes[node].num != 0.0 ? "true" : "false");
        case DJ_NULL:
            return dictum_strdup("null");
        case DJ_OBJECT:  return dictum_strdup("[object]");
        case DJ_ARRAY:   return dictum_strdup("[array]");
    }
    return NULL;
}
