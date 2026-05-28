#ifndef DICTUM_TIMER_H
#define DICTUM_TIMER_H

#include "dictum_core.h"

/* Dictum interface:
module Timer:
    action start takes Ms as count and Callback as action produces whole number
    action stop takes H as whole number produces nothing
    action sleep takes Ms as count produces nothing
end module
*/

dictum_whole_t dictum_timer_start(dictum_count_t ms, void (*callback)(void));
void dictum_timer_stop(dictum_whole_t h);
void dictum_timer_sleep(dictum_count_t ms);

#endif
