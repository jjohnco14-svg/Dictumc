#include "dictum_tls.h"
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <netinet/in.h>
#include <netdb.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>

static SSL_CTX* tls_ctx = NULL;

static SSL_CTX* get_tls_ctx(void) {
    if (!tls_ctx) {
        SSL_library_init();
        SSL_load_error_strings();
        tls_ctx = SSL_CTX_new(TLS_client_method());
        if (!tls_ctx) return NULL;
        /* Rule 10: TLS 1.3 only, no compression */
        SSL_CTX_set_min_proto_version(tls_ctx, TLS1_3_VERSION);
        SSL_CTX_set_options(tls_ctx, SSL_OP_NO_COMPRESSION);
    }
    return tls_ctx;
}

dictum_result_t dictum_tls_connect(const char* host, dictum_count_t port) {
    if (!host || host[0] == '\0') return DICTUM_FAILURE("Invalid host");
    if (port == 0 || port > 65535) return DICTUM_FAILURE("Invalid port");

    SSL_CTX* ctx = get_tls_ctx();
    if (!ctx) return DICTUM_FAILURE("TLS context init failed");

    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return DICTUM_FAILURE(strerror(errno));

    struct timeval tv = {30, 0};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    struct hostent* server = gethostbyname(host);
    if (!server) { close(sock); return DICTUM_FAILURE("DNS failed"); }

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)port);
    memcpy(&addr.sin_addr.s_addr, server->h_addr_list[0], server->h_length);

    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        close(sock);
        return DICTUM_FAILURE(strerror(errno));
    }

    SSL* ssl = SSL_new(ctx);
    if (!ssl) { close(sock); return DICTUM_FAILURE("SSL_new failed"); }

    SSL_set_fd(ssl, sock);
    if (SSL_connect(ssl) <= 0) {
        SSL_free(ssl);
        close(sock);
        return DICTUM_FAILURE("TLS handshake failed");
    }

    dictum_handle_registry_add((dictum_handle_t)ssl, "tls", host);
    return DICTUM_SUCCESS((dictum_whole_t)(size_t)ssl);
}

dictum_result_t dictum_tls_send(dictum_handle_t h, const char* data) {
    SSL* ssl = (SSL*)h;
    if (!ssl) return DICTUM_FAILURE("Invalid handle");

    size_t len = strlen(data);
    size_t total = 0;
    while (total < len) {
        int n = SSL_write(ssl, data + total, (int)(len - total));
        if (n <= 0) {
            int err = SSL_get_error(ssl, n);
            if (err == SSL_ERROR_WANT_WRITE || err == SSL_ERROR_WANT_READ) {
                return DICTUM_FAILURE("TLS send timeout");
            }
            return DICTUM_FAILURE("TLS send failed");
        }
        total += (size_t)n;
    }
    return DICTUM_SUCCESS(0);
}

char* dictum_tls_receive(dictum_handle_t h, dictum_count_t max_len) {
    SSL* ssl = (SSL*)h;
    if (!ssl) return NULL;

    if (max_len > DICTUM_MAX_NET_READ) max_len = DICTUM_MAX_NET_READ;

    char* buf = dictum_alloc(max_len + 1);
    if (!buf) return NULL;

    int n = SSL_read(ssl, buf, (int)max_len);
    if (n <= 0) {
        dictum_free(buf);
        return NULL;
    }
    buf[n] = '\0';
    return buf;
}

void dictum_tls_close(dictum_handle_t h) {
    SSL* ssl = (SSL*)h;
    if (!ssl) return;

    int sock = SSL_get_fd(ssl);
    SSL_shutdown(ssl);
    SSL_free(ssl);
    if (sock >= 0) close(sock);
    dictum_handle_registry_remove(h);
}
