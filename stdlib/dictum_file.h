#ifndef DICTUM_FILE_H
#define DICTUM_FILE_H

#include "dictum_core.h"
#include <stdio.h>  /* SEEK_SET, SEEK_CUR, SEEK_END */

/* Dictum interface:
module File:
    shape Result holds:
        Success as truth value
        Handle as whole number
        Error as text
    end shape

    action open takes Path as text and Mode as text produces Result
    action read takes H as handle and MaxLen as count produces text
    action read_line takes H as handle produces text
    action read_all takes H as handle produces text
    action write takes H as handle and Data as text produces Result
    action seek takes H as handle and Offset as whole number and Whence as whole number produces Result
    action tell takes H as handle produces whole number
    action flush takes H as handle produces Result
    action size takes Path as text produces whole number
    action exists takes Path as text produces truth value
    action delete takes Path as text produces Result
    action append takes Path as text and Data as text produces Result
    action close takes H as handle produces nothing
end module
*/

dictum_result_t  dictum_file_open(const char* path, const char* mode);
char*            dictum_file_read(dictum_handle_t h, dictum_count_t max_len);
char*            dictum_file_read_line(dictum_handle_t h);
char*            dictum_file_read_all(dictum_handle_t h);
dictum_result_t  dictum_file_write(dictum_handle_t h, const char* data);
dictum_result_t  dictum_file_seek(dictum_handle_t h, dictum_whole_t offset, int whence);
dictum_whole_t   dictum_file_tell(dictum_handle_t h);
dictum_result_t  dictum_file_flush(dictum_handle_t h);
dictum_whole_t   dictum_file_size(const char* path);
dictum_truth_t   dictum_file_exists(const char* path);
dictum_result_t  dictum_file_delete(const char* path);
dictum_result_t  dictum_file_append(const char* path, const char* data);
void             dictum_file_close(dictum_handle_t h);

#endif
