#ifndef DICTUM_DEVICE_H
#define DICTUM_DEVICE_H

#include "dictum_core.h"

/* Dictum interface:
module Device:
    action open takes Path as text produces Result
    action read takes H as result and MaxLen as count produces text
    action write takes H as result and Data as text produces Result
    action ioctl takes H as result and Request as whole number and Arg as whole number produces Result
    action close takes H as result produces nothing
end module
*/

dictum_result_t dictum_device_open(const char* path);
char* dictum_device_read(dictum_handle_t h, dictum_count_t max_len);
dictum_result_t dictum_device_write(dictum_handle_t h, const char* data);
dictum_result_t dictum_device_ioctl(dictum_handle_t h, dictum_whole_t request, dictum_whole_t arg);
void dictum_device_close(dictum_handle_t h);

#endif
