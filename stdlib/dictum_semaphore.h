#ifndef DICTUM_SEMAPHORE_H
#define DICTUM_SEMAPHORE_H

#include "dictum_core.h"

/* Dictum interface:
module Semaphore:
    action create takes Name as text and Value as whole number produces whole number
    action wait takes H as whole number produces truth value
    action signal takes H as whole number produces truth value
    action destroy takes H as whole number produces nothing
end module
*/

dictum_whole_t dictum_semaphore_create(const char* name, dictum_whole_t value);
dictum_truth_t dictum_semaphore_wait(dictum_whole_t h);
dictum_truth_t dictum_semaphore_signal(dictum_whole_t h);
void dictum_semaphore_destroy(dictum_whole_t h);

#endif
