#ifndef DICTUM_MUTEX_H
#define DICTUM_MUTEX_H

#include "dictum_core.h"

/* Dictum interface:
module Mutex:
    action create produces whole number
    action lock takes H as whole number produces truth value
    action unlock takes H as whole number produces truth value
    action destroy takes H as whole number produces nothing
end module
*/

dictum_whole_t dictum_mutex_create(void);
dictum_truth_t dictum_mutex_lock(dictum_whole_t h);
dictum_truth_t dictum_mutex_unlock(dictum_whole_t h);
void dictum_mutex_destroy(dictum_whole_t h);

#endif
