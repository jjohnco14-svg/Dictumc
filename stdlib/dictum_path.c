#include "dictum_path.h"
#include <sys/stat.h>
#include <unistd.h>
#include <string.h>

/* Rule 9: Path validation */
dictum_truth_t dictum_path_valid(const char* path) {
    if (!path || path[0] == '\0') return 0;
    /* Block path traversal */
    if (strstr(path, "..") != NULL) return 0;
    /* Block absolute system paths */
    if (strcmp(path, "/") == 0) return 0;
    if (strncmp(path, "/dev/", 5) == 0) return 0;
    if (strncmp(path, "/proc/", 6) == 0) return 0;
    if (strncmp(path, "/sys/", 5) == 0) return 0;
    return 1;
}

dictum_truth_t dictum_path_exists(const char* path) {
    struct stat st;
    return stat(path, &st) == 0;
}

dictum_truth_t dictum_path_is_file(const char* path) {
    struct stat st;
    if (stat(path, &st) != 0) return 0;
    return S_ISREG(st.st_mode);
}

dictum_truth_t dictum_path_is_directory(const char* path) {
    struct stat st;
    if (stat(path, &st) != 0) return 0;
    return S_ISDIR(st.st_mode);
}

dictum_count_t dictum_path_size(const char* path) {
    struct stat st;
    if (stat(path, &st) != 0) return 0;
    return (dictum_count_t)st.st_size;
}
