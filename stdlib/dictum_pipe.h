#ifndef DICTUM_PIPE_H
#define DICTUM_PIPE_H

#include "dictum_core.h"

/* Dictum interface:
module Pipe:
    shape Result holds:
        ReadHandle as whole number
        WriteHandle as whole number
        Error as text
    end shape

    action create produces Result
    action read takes H as whole number and MaxLen as count produces text
    action write takes H as whole number and Data as text produces truth value
    action close takes H as whole number produces nothing
end module
*/

typedef struct {
    dictum_whole_t read_handle;
    dictum_whole_t write_handle;
    char error[256];
} dictum_pipe_result_t;

dictum_pipe_result_t dictum_pipe_create(void);
char* dictum_pipe_read(dictum_whole_t h, dictum_count_t max_len);
dictum_truth_t dictum_pipe_write(dictum_whole_t h, const char* data);
void dictum_pipe_close(dictum_whole_t h);

#endif
