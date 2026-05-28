#ifndef DICTUM_CHANNEL_H
#define DICTUM_CHANNEL_H

#include "dictum_core.h"

/* Dictum interface:
module Channel:
    shape Result holds:
        Success as truth value
        Data as text
        Error as text
    end shape

    action create takes Capacity as count produces whole number
    action send takes H as whole number and Data as text produces truth value
    action receive takes H as whole number produces Result
    action close takes H as whole number produces nothing
end module
*/

dictum_whole_t dictum_channel_create(dictum_count_t capacity);
dictum_truth_t dictum_channel_send(dictum_whole_t h, const char* data);
dictum_result_t dictum_channel_receive(dictum_whole_t h);
void dictum_channel_close(dictum_whole_t h);

#endif
