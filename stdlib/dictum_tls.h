#ifndef DICTUM_TLS_H
#define DICTUM_TLS_H

#include "dictum_core.h"

/* Dictum interface:
module Tls:
    shape Result holds:
        Success as truth value
        Handle as whole number
        Error as text
    end shape

    action connect takes Host as text and Port as count produces Result
    action send takes H as result and Data as text produces Result
    action receive takes H as result and MaxLen as count produces text
    action close takes H as result produces nothing
end module
*/

dictum_result_t dictum_tls_connect(const char* host, dictum_count_t port);
dictum_result_t dictum_tls_send(dictum_handle_t h, const char* data);
char* dictum_tls_receive(dictum_handle_t h, dictum_count_t max_len);
void dictum_tls_close(dictum_handle_t h);

#endif
