/*
 * dictum_http.c — HTTP and HTTPS client for Dictum v5.
 *
 * HTTP  (port 80)  uses dictum_net.c (POSIX TCP sockets).
 * HTTPS (port 443) uses dictum_tls.c (OpenSSL TLS 1.3).
 *
 * URL routing:
 *   http://host/path  → plain TCP, port 80
 *   https://host/path → TLS, port 443
 *
 * No libcurl dependency.
 */

#include "dictum_http.h"
#include "dictum_net.h"
#include "dictum_tls.h"
#include "dictum_text.h"
#include "dictum_error.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* ── URL parser ─────────────────────────────────────────────────── */

typedef struct {
    int   use_tls;
    char  host[256];
    dictum_count_t port;
    char  path[2048];
} parsed_url_t;

static parsed_url_t parse_url(const char* url) {
    parsed_url_t r = {0, "", 80, "/"};
    if (!url) return r;

    const char* p = url;

    if (strncmp(p, "https://", 8) == 0) {
        r.use_tls = 1;
        r.port    = 443;
        p += 8;
    } else if (strncmp(p, "http://", 7) == 0) {
        r.use_tls = 0;
        r.port    = 80;
        p += 7;
    }

    const char* slash = strchr(p, '/');
    const char* colon = strchr(p, ':');

    /* host:port/path  or  host/path  or  host */
    if (colon && (!slash || colon < slash)) {
        size_t hl = (size_t)(colon - p);
        if (hl >= sizeof(r.host)) hl = sizeof(r.host) - 1;
        memcpy(r.host, p, hl);
        r.host[hl] = '\0';
        r.port = (dictum_count_t)atoi(colon + 1);
        if (slash) dictum_strncpy(r.path, sizeof(r.path), slash);
    } else if (slash) {
        size_t hl = (size_t)(slash - p);
        if (hl >= sizeof(r.host)) hl = sizeof(r.host) - 1;
        memcpy(r.host, p, hl);
        r.host[hl] = '\0';
        dictum_strncpy(r.path, sizeof(r.path), slash);
    } else {
        dictum_strncpy(r.host, sizeof(r.host), p);
    }

    if (r.path[0] == '\0') { r.path[0] = '/'; r.path[1] = '\0'; }
    return r;
}

/* ── Response reader (shared between TCP and TLS paths) ────────── */

typedef struct {
    char* buf;
    size_t len;
    size_t cap;
    int ok;
} read_buf_t;

static read_buf_t buf_new(void) {
    read_buf_t b = {NULL, 0, 65536, 1};
    b.buf = dictum_alloc(b.cap);
    if (!b.buf) b.ok = 0;
    return b;
}

static void buf_append(read_buf_t* b, const char* chunk, size_t clen) {
    if (!b->ok || !chunk || clen == 0) return;
    if (b->len + clen + 1 >= b->cap) {
        size_t nc;
        if (!dictum_checked_mul(b->cap, 2, &nc) || nc > DICTUM_MAX_STRING) {
            b->ok = 0; return;
        }
        char* nb = dictum_realloc(b->buf, nc);
        if (!nb) { b->ok = 0; return; }
        b->buf = nb; b->cap = nc;
    }
    memcpy(b->buf + b->len, chunk, clen);
    b->len += clen;
    b->buf[b->len] = '\0';
}

/* ── HTTP response parser ──────────────────────────────────────── */

static dictum_http_response_t build_response(read_buf_t* b) {
    dictum_http_response_t resp = {0, NULL, ""};
    if (!b->ok || !b->buf) {
        dictum_strncpy(resp.error, sizeof(resp.error), "Read error");
        return resp;
    }

    char* raw = b->buf;
    size_t len = b->len;

    /* Parse status line */
    if (len > 12 && (strncmp(raw, "HTTP/1.1 ", 9) == 0 ||
                     strncmp(raw, "HTTP/1.0 ", 9) == 0)) {
        resp.status = atoi(raw + 9);
    }

    /* Find body after double CRLF */
    char* body_start = strstr(raw, "\r\n\r\n");
    if (body_start) {
        body_start += 4;
        /* Handle chunked transfer encoding */
        char* te = strstr(raw, "Transfer-Encoding: chunked");
        if (te && te < body_start) {
            /* Decode chunked body */
            char* decoded = dictum_alloc(len);
            size_t dlen = 0;
            char* pos = body_start;
            while (*pos) {
                size_t chunk_size = (size_t)strtol(pos, &pos, 16);
                if (chunk_size == 0) break;
                if (*pos == '\r') pos++;
                if (*pos == '\n') pos++;
                if (dlen + chunk_size >= len) break;
                memcpy(decoded + dlen, pos, chunk_size);
                dlen += chunk_size;
                pos += chunk_size;
                if (*pos == '\r') pos++;
                if (*pos == '\n') pos++;
            }
            decoded[dlen] = '\0';
            resp.body = decoded;
        } else {
            resp.body = dictum_strdup(body_start);
        }
    } else {
        resp.body = dictum_strdup("");
    }

    dictum_free(b->buf);
    b->buf = NULL;
    return resp;
}

/* ── Core request (auto-routes HTTP vs HTTPS) ──────────────────── */

static dictum_http_response_t do_request(const char* method,
                                          const char* url,
                                          const char* req_body,
                                          const char* content_type) {
    dictum_http_response_t resp = {0, NULL, ""};
    parsed_url_t pu = parse_url(url);

    /* Build request string */
    char request[8192] = {0};
    if (req_body && req_body[0]) {
        const char* ct = content_type ? content_type : "application/json";
        snprintf(request, sizeof(request),
            "%s %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "Content-Type: %s\r\n"
            "Content-Length: %zu\r\n"
            "Connection: close\r\n"
            "User-Agent: Dictum/5.0\r\n"
            "\r\n%s",
            method, pu.path, pu.host, ct, strlen(req_body), req_body);
    } else {
        snprintf(request, sizeof(request),
            "%s %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "Connection: close\r\n"
            "User-Agent: Dictum/5.0\r\n"
            "\r\n",
            method, pu.path, pu.host);
    }

    read_buf_t b = buf_new();
    if (!b.ok) {
        dictum_strncpy(resp.error, sizeof(resp.error), "Out of memory");
        return resp;
    }

    if (pu.use_tls) {
        /* ── HTTPS path through dictum_tls.c ── */
        dictum_result_t cr = dictum_tls_connect(pu.host, pu.port);
        if (!cr.success) {
            dictum_strncpy(resp.error, sizeof(resp.error), cr.error);
            dictum_free(b.buf);
            return resp;
        }
        dictum_handle_t h = (dictum_handle_t)(size_t)cr.handle;

        dictum_result_t sr = dictum_tls_send(h, request);
        if (!sr.success) {
            dictum_strncpy(resp.error, sizeof(resp.error), sr.error);
            dictum_tls_close(h);
            dictum_free(b.buf);
            return resp;
        }

        while (1) {
            char* chunk = dictum_tls_receive(h);
            if (!chunk || chunk[0] == '\0') { dictum_free(chunk); break; }
            buf_append(&b, chunk, strlen(chunk));
            dictum_free(chunk);
            if (!b.ok) break;
        }
        dictum_tls_close(h);

    } else {
        /* ── HTTP path through dictum_net.c ── */
        dictum_result_t cr = dictum_net_connect(pu.host, pu.port);
        if (!cr.success) {
            dictum_strncpy(resp.error, sizeof(resp.error), cr.error);
            dictum_free(b.buf);
            return resp;
        }
        dictum_handle_t sock = (dictum_handle_t)(size_t)cr.handle;

        dictum_result_t sr = dictum_net_send(sock, request);
        if (!sr.success) {
            dictum_strncpy(resp.error, sizeof(resp.error), sr.error);
            dictum_net_close(sock);
            dictum_free(b.buf);
            return resp;
        }

        while (1) {
            char* chunk = dictum_net_receive(sock, 4096);
            if (!chunk || chunk[0] == '\0') { dictum_free(chunk); break; }
            buf_append(&b, chunk, strlen(chunk));
            dictum_free(chunk);
            if (!b.ok) break;
        }
        dictum_net_close(sock);
    }

    return build_response(&b);
}

/* ── Public API ─────────────────────────────────────────────────── */

dictum_http_response_t dictum_http_get(const char* url) {
    return do_request("GET", url, NULL, NULL);
}

dictum_http_response_t dictum_http_post(const char* url, const char* body) {
    return do_request("POST", url, body, "application/json");
}

dictum_http_response_t dictum_http_post_form(const char* url, const char* body) {
    return do_request("POST", url, body, "application/x-www-form-urlencoded");
}

dictum_http_response_t dictum_http_put(const char* url, const char* body) {
    return do_request("PUT", url, body, "application/json");
}

dictum_http_response_t dictum_http_delete(const char* url) {
    return do_request("DELETE", url, NULL, NULL);
}

dictum_http_response_t dictum_http_patch(const char* url, const char* body) {
    return do_request("PATCH", url, body, "application/json");
}
