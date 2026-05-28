#ifndef DICTUM_HTTP_H
#define DICTUM_HTTP_H

#include "dictum_core.h"

/*
 * Dictum HTTP/HTTPS module.
 * Automatically routes http:// through TCP and https:// through TLS 1.3.
 * Requires: dictum_net.c (always), dictum_tls.c + libssl for HTTPS.
 *
 * Dictum interface:
 * module Http:
 *     shape Response holds:
 *         Status as whole number
 *         Body as text
 *         Error as text
 *     end shape
 *     action get          takes Url as text produces Response
 *     action post         takes Url as text and Body as text produces Response
 *     action post_form    takes Url as text and Body as text produces Response
 *     action put          takes Url as text and Body as text produces Response
 *     action delete       takes Url as text produces Response
 *     action patch        takes Url as text and Body as text produces Response
 * end module
 */

typedef struct {
    dictum_whole_t  status;
    char*           body;
    char            error[256];
} dictum_http_response_t;

dictum_http_response_t dictum_http_get(const char* url);
dictum_http_response_t dictum_http_post(const char* url, const char* body);
dictum_http_response_t dictum_http_post_form(const char* url, const char* body);
dictum_http_response_t dictum_http_put(const char* url, const char* body);
dictum_http_response_t dictum_http_delete(const char* url);
dictum_http_response_t dictum_http_patch(const char* url, const char* body);

#endif
