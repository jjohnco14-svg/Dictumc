#ifndef DICTUM_NET_H
#define DICTUM_NET_H

#include "dictum_core.h"

/* Dictum interface:
module Net:
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

dictum_result_t dictum_net_connect(const char* host, dictum_count_t port);
dictum_result_t dictum_net_send(dictum_handle_t h, const char* data);
char* dictum_net_receive(dictum_handle_t h, dictum_count_t max_len);
void dictum_net_close(dictum_handle_t h);

#endif
