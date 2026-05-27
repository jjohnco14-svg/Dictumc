#ifndef DICTUM_THREAD_H
#define DICTUM_THREAD_H

#include "dictum_core.h"

/* Dictum interface:
module Thread:
    action spawn takes Task as action produces whole number
    action join takes Id as whole number produces truth value
    action sleep takes Ms as count produces nothing
    action id produces whole number
end module
*/

typedef void* (*dictum_thread_task_t)(void*);

dictum_result_t dictum_thread_spawn(dictum_thread_task_t task, void* arg);
dictum_truth_t dictum_thread_join(dictum_whole_t id);
void dictum_thread_sleep(dictum_count_t ms);
dictum_whole_t dictum_thread_id(void);

#endif
