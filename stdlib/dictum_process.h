#ifndef DICTUM_PROCESS_H
#define DICTUM_PROCESS_H

#include "dictum_core.h"

/* Dictum interface:
module Process:
    action spawn takes Path as text and Args as text produces whole number
    action wait takes Pid as whole number produces whole number
    action kill takes Pid as whole number produces truth value
    action current_id produces whole number
end module
*/

dictum_result_t dictum_process_spawn(const char* path, const char* args);
dictum_whole_t dictum_process_wait(dictum_whole_t pid);
dictum_truth_t dictum_process_kill(dictum_whole_t pid);
dictum_whole_t dictum_process_current_id(void);

#endif
