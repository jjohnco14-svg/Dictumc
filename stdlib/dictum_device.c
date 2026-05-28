#include "dictum_device.h"
#include "dictum_path.h"
#include <sys/ioctl.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>

dictum_result_t dictum_device_open(const char* path) {
    if (!dictum_path_valid(path)) return DICTUM_FAILURE("Invalid path");
    /* Rule 9: Extra block for device paths */
    if (strncmp(path, "/dev/", 5) == 0) return DICTUM_FAILURE("Device paths not allowlisted");

    int fd = open(path, O_RDWR);
    if (fd < 0) return DICTUM_FAILURE(strerror(errno));
    dictum_handle_registry_add((dictum_handle_t)(size_t)fd, "device", path);
    return DICTUM_SUCCESS((dictum_whole_t)fd);
}

char* dictum_device_read(dictum_handle_t h, dictum_count_t max_len) {
    int fd = (int)(size_t)h;
    if (max_len > DICTUM_MAX_READ) max_len = DICTUM_MAX_READ;
    char* buf = dictum_alloc(max_len + 1);
    if (!buf) return NULL;
    ssize_t n = read(fd, buf, max_len);
    if (n < 0) { dictum_free(buf); return NULL; }
    buf[n] = '\0';
    return buf;
}

dictum_result_t dictum_device_write(dictum_handle_t h, const char* data) {
    int fd = (int)(size_t)h;
    size_t len = strlen(data);
    ssize_t n = write(fd, data, len);
    if ((size_t)n != len) return DICTUM_FAILURE("Write failed");
    return DICTUM_SUCCESS(0);
}

dictum_result_t dictum_device_ioctl(dictum_handle_t h, dictum_whole_t request, dictum_whole_t arg) {
    int fd = (int)(size_t)h;
    int rc = ioctl(fd, (unsigned long)request, (void*)(size_t)arg);
    if (rc < 0) return DICTUM_FAILURE(strerror(errno));
    return DICTUM_SUCCESS((dictum_whole_t)rc);
}

void dictum_device_close(dictum_handle_t h) {
    int fd = (int)(size_t)h;
    dictum_handle_registry_remove(h);
    close(fd);
}
