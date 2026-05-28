#ifndef DICTUM_SHM_H
#define DICTUM_SHM_H

#include "dictum_core.h"

/* Dictum interface:
module SharedMemory:
    action create takes Name as text and Size as count produces whole number
    action read takes H as whole number and Offset as count and Len as count produces text
    action write takes H as whole number and Offset as count and Data as text produces truth value
    action close takes H as whole number produces nothing
end module
*/

dictum_result_t dictum_shm_create(const char* name, dictum_count_t size);
char* dictum_shm_read(dictum_whole_t h, dictum_count_t offset, dictum_count_t len);
dictum_truth_t dictum_shm_write(dictum_whole_t h, dictum_count_t offset, const char* data);
void dictum_shm_close(dictum_whole_t h);

#endif
