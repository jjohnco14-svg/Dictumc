#ifndef DICTUM_PATH_H
#define DICTUM_PATH_H

#include "dictum_core.h"

/* Dictum interface:
module Path:
    action valid takes P as text produces truth value
    action exists takes P as text produces truth value
    action is_file takes P as text produces truth value
    action is_directory takes P as text produces truth value
    action size takes P as text produces count
end module
*/

dictum_truth_t dictum_path_valid(const char* path);
dictum_truth_t dictum_path_exists(const char* path);
dictum_truth_t dictum_path_is_file(const char* path);
dictum_truth_t dictum_path_is_directory(const char* path);
dictum_count_t dictum_path_size(const char* path);

#endif
