#include "dictum_directory.h"
#include "dictum_path.h"
#include <sys/stat.h>
#include <unistd.h>
#include <dirent.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>

dictum_truth_t dictum_directory_create(const char* path) {
    if (!dictum_path_valid(path)) return 0;
    return mkdir(path, 0755) == 0;
}

dictum_truth_t dictum_directory_remove(const char* path) {
    if (!dictum_path_valid(path)) return 0;
    return rmdir(path) == 0;
}

char* dictum_directory_list(const char* path) {
    if (!dictum_path_valid(path)) return NULL;
    DIR* d = opendir(path);
    if (!d) return NULL;

    size_t cap = 4096;
    size_t len = 0;
    char* buf = dictum_alloc(cap);
    if (!buf) { closedir(d); return NULL; }

    struct dirent* entry;
    while ((entry = readdir(d)) != NULL) {
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
            continue;
        size_t name_len = strlen(entry->d_name);
        size_t need = len + name_len + 2;  /* name + newline + null */
        if (need > cap) {
            size_t new_cap = cap * 2;
            while (new_cap < need) new_cap *= 2;
            char* nb = dictum_realloc(buf, new_cap);
            if (!nb) { dictum_free(buf); closedir(d); return NULL; }
            buf = nb; cap = new_cap;
        }
        memcpy(buf + len, entry->d_name, name_len);
        buf[len + name_len] = '\n';
        len += name_len + 1;
    }
    buf[len] = '\0';
    closedir(d);
    return buf;
}

char* dictum_directory_current(void) {
    char* buf = dictum_alloc(DICTUM_MAX_PATH);
    if (!buf) return NULL;
    if (!getcwd(buf, DICTUM_MAX_PATH)) {
        dictum_free(buf);
        return NULL;
    }
    return buf;
}

dictum_truth_t dictum_directory_change(const char* path) {
    if (!dictum_path_valid(path)) return 0;
    return chdir(path) == 0;
}
