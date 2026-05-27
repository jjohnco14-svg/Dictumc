#include "dictum_pipe.h"
#include <unistd.h>
#include <string.h>
#include <errno.h>

dictum_pipe_result_t dictum_pipe_create(void) {
    dictum_pipe_result_t r = {0, 0, ""};
    int fds[2];
    if (pipe(fds) != 0) {
        dictum_strncpy(r.error, sizeof(r.error), strerror(errno));
        return r;
    }
    r.read_handle = fds[0];
    r.write_handle = fds[1];
    return r;
}

char* dictum_pipe_read(dictum_whole_t h, dictum_count_t max_len) {
    int fd = (int)h;
    if (max_len > DICTUM_MAX_READ) max_len = DICTUM_MAX_READ;
    char* buf = dictum_alloc(max_len + 1);
    if (!buf) return NULL;
    ssize_t n = read(fd, buf, max_len);
    if (n < 0) { dictum_free(buf); return NULL; }
    buf[n] = '\0';
    return buf;
}

dictum_truth_t dictum_pipe_write(dictum_whole_t h, const char* data) {
    int fd = (int)h;
    size_t len = strlen(data);
    ssize_t n = write(fd, data, len);
    return (size_t)n == len;
}

void dictum_pipe_close(dictum_whole_t h) {
    close((int)h);
}
