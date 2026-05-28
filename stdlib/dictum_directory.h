#ifndef DICTUM_DIRECTORY_H
#define DICTUM_DIRECTORY_H

#include "dictum_core.h"

/* Dictum interface:
module Directory:
    action create takes P as text produces truth value
    action remove takes P as text produces truth value
    action list takes P as text produces text
    action current produces text
    action change takes P as text produces truth value
end module
*/

dictum_truth_t dictum_directory_create(const char* path);
dictum_truth_t dictum_directory_remove(const char* path);
char* dictum_directory_list(const char* path);
char* dictum_directory_current(void);
dictum_truth_t dictum_directory_change(const char* path);

#endif
