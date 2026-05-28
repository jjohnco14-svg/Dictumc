#ifndef DICTUM_EVENT_H
#define DICTUM_EVENT_H

#include "dictum_core.h"

/* Dictum interface:
module Event:
    action create produces whole number
    action wait takes H as whole number produces truth value
    action signal takes H as whole number produces truth value
    action destroy takes H as whole number produces nothing
end module
*/

dictum_whole_t dictum_event_create(void);
dictum_truth_t dictum_event_wait(dictum_whole_t h);
dictum_truth_t dictum_event_signal(dictum_whole_t h);
void dictum_event_destroy(dictum_whole_t h);

#endif
