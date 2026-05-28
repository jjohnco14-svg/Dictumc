#include "dictum_net.h"
#include <sys/socket.h>
#include <sys/time.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>

dictum_result_t dictum_net_connect(const char* host, dictum_count_t port) {
    if (!host || host[0] == '\0') {
        return DICTUM_FAILURE("Invalid host");
    }
    if (port == 0 || port > 65535) {
        return DICTUM_FAILURE("Invalid port");
    }

    /* Rule 10: only AF_INET, no raw sockets */
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) {
        return DICTUM_FAILURE(strerror(errno));
    }

    /* Rule 3: Set timeouts */
    struct timeval tv = {30, 0};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    /* DNS resolve */
    struct hostent* server = gethostbyname(host);
    if (!server) {
        close(sock);
        return DICTUM_FAILURE("DNS resolution failed");
    }

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)port);
    memcpy(&addr.sin_addr.s_addr, server->h_addr_list[0], server->h_length);

    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        close(sock);
        return DICTUM_FAILURE(strerror(errno));
    }

    /* Rule 4: Track in registry */
    dictum_handle_registry_add((dictum_handle_t)(size_t)sock, "socket", host);

    return DICTUM_SUCCESS((dictum_whole_t)sock);
}

dictum_result_t dictum_net_send(dictum_handle_t h, const char* data) {
    int sock = (int)(size_t)h;
    if (sock < 0) return DICTUM_FAILURE("Invalid handle");

    size_t len = strlen(data);
    size_t total = 0;
    while (total < len) {
        ssize_t n = send(sock, data + total, len - total, 0);
        if (n < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                return DICTUM_FAILURE("Send timeout");
            }
            return DICTUM_FAILURE(strerror(errno));
        }
        total += (size_t)n;
    }
    return DICTUM_SUCCESS(0);
}

char* dictum_net_receive(dictum_handle_t h, dictum_count_t max_len) {
    int sock = (int)(size_t)h;
    if (sock < 0) return NULL;

    /* Rule 5: Bounds check */
    if (max_len > DICTUM_MAX_NET_READ) {
        max_len = DICTUM_MAX_NET_READ;
    }

    char* buf = dictum_alloc(max_len + 1);
    if (!buf) return NULL;

    /* Rule 3: Non-blocking with timeout already set */
    int n = recv(sock, buf, max_len, 0);
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            dictum_free(buf);
            return dictum_strdup("");
        }
        dictum_free(buf);
        return NULL;
    }
    buf[n] = '\0';
    return buf;
}

void dictum_net_close(dictum_handle_t h) {
    int sock = (int)(size_t)h;
    if (sock < 0) return;

    dictum_handle_registry_remove(h);
    close(sock);
}
