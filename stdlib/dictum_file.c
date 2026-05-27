#include "dictum_file.h"
#include "dictum_path.h"
#include <stdio.h>
#include <errno.h>
#include <string.h>
#include <sys/stat.h>

/* P1.5 COMPLETE: seek, stat, append, exists, flush */

/* Rule 9: Path validation */
dictum_result_t dictum_file_open(const char* path, const char* mode) {
    if (!dictum_path_valid(path)) {
        return DICTUM_FAILURE("Invalid path");
    }

    /* Rule 10: Validate mode (allowlisted modes only) */
    if (strcmp(mode, "r") != 0 && strcmp(mode, "w") != 0 &&
        strcmp(mode, "a") != 0 && strcmp(mode, "r+") != 0 &&
        strcmp(mode, "rb") != 0 && strcmp(mode, "wb") != 0) {
        return DICTUM_FAILURE("Invalid mode");
    }

    FILE* f = fopen(path, mode);
    if (!f) {
        return DICTUM_FAILURE(strerror(errno));
    }

    /* Rule 4: Track in registry */
    dictum_handle_registry_add((dictum_handle_t)f, "file", path);

    return DICTUM_SUCCESS((dictum_whole_t)(size_t)f);
}

char* dictum_file_read(dictum_handle_t h, dictum_count_t max_len) {
    FILE* f = (FILE*)h;
    if (!f) return NULL;

    /* Rule 5: Check bounds */
    if (max_len > DICTUM_MAX_READ) {
        max_len = DICTUM_MAX_READ;
    }

    char* buf = dictum_alloc(max_len + 1);
    if (!buf) return NULL;

    size_t n = fread(buf, 1, max_len, f);
    buf[n] = '\0';

    return buf;
}

char* dictum_file_read_line(dictum_handle_t h) {
    FILE* f = (FILE*)h;
    if (!f) return NULL;

    size_t cap = 1024;
    size_t len = 0;
    char* buf = dictum_alloc(cap);
    if (!buf) return NULL;

    int c;
    while ((c = fgetc(f)) != '\n' && c != EOF) {
        if (len + 1 >= cap) {
            size_t new_cap;
            if (!dictum_checked_mul(cap, 2, &new_cap) || new_cap > DICTUM_MAX_STRING) {
                dictum_free(buf);
                return NULL;
            }
            char* new_buf = dictum_realloc(buf, new_cap);
            if (!new_buf) {
                dictum_free(buf);
                return NULL;
            }
            buf = new_buf;
            cap = new_cap;
        }
        buf[len++] = (char)c;
    }
    buf[len] = '\0';
    return buf;
}

/* P1.5: Read entire file as a single heap string */
char* dictum_file_read_all(dictum_handle_t h) {
    FILE* f = (FILE*)h;
    if (!f) return NULL;

    long start = ftell(f);
    if (fseek(f, 0, SEEK_END) != 0) return NULL;
    long end = ftell(f);
    if (fseek(f, start, SEEK_SET) != 0) return NULL;

    size_t sz = (size_t)(end - start);
    if (sz > DICTUM_MAX_READ) sz = DICTUM_MAX_READ;

    char* buf = dictum_alloc(sz + 1);
    if (!buf) return NULL;

    size_t n = fread(buf, 1, sz, f);
    buf[n] = '\0';
    return buf;
}

dictum_result_t dictum_file_write(dictum_handle_t h, const char* data) {
    FILE* f = (FILE*)h;
    if (!f) return DICTUM_FAILURE("Invalid handle");

    size_t len = strlen(data);
    size_t written = fwrite(data, 1, len, f);
    if (written != len) {
        return DICTUM_FAILURE("Write failed");
    }

    return DICTUM_SUCCESS(0);
}

/* P1.5: seek to byte offset */
dictum_result_t dictum_file_seek(dictum_handle_t h, dictum_whole_t offset, int whence) {
    FILE* f = (FILE*)h;
    if (!f) return DICTUM_FAILURE("Invalid handle");
    if (fseek(f, (long)offset, whence) != 0) {
        return DICTUM_FAILURE(strerror(errno));
    }
    return DICTUM_SUCCESS(0);
}

/* P1.5: tell current byte offset */
dictum_whole_t dictum_file_tell(dictum_handle_t h) {
    FILE* f = (FILE*)h;
    if (!f) return -1;
    long pos = ftell(f);
    return (pos < 0) ? -1 : (dictum_whole_t)pos;
}

/* P1.5: flush write buffer */
dictum_result_t dictum_file_flush(dictum_handle_t h) {
    FILE* f = (FILE*)h;
    if (!f) return DICTUM_FAILURE("Invalid handle");
    if (fflush(f) != 0) {
        return DICTUM_FAILURE(strerror(errno));
    }
    return DICTUM_SUCCESS(0);
}

/* P1.5: file size in bytes (-1 on error) */
dictum_whole_t dictum_file_size(const char* path) {
    if (!dictum_path_valid(path)) return -1;
    struct stat st;
    if (stat(path, &st) != 0) return -1;
    return (dictum_whole_t)st.st_size;
}

/* P1.5: check whether a regular file exists */
dictum_truth_t dictum_file_exists(const char* path) {
    if (!path || !dictum_path_valid(path)) return 0;
    struct stat st;
    return (stat(path, &st) == 0 && S_ISREG(st.st_mode)) ? 1 : 0;
}

/* P1.5: delete a file */
dictum_result_t dictum_file_delete(const char* path) {
    if (!dictum_path_valid(path)) return DICTUM_FAILURE("Invalid path");
    if (remove(path) != 0) {
        return DICTUM_FAILURE(strerror(errno));
    }
    return DICTUM_SUCCESS(0);
}

/* P1.5: append text to file without opening a handle */
dictum_result_t dictum_file_append(const char* path, const char* data) {
    if (!dictum_path_valid(path)) return DICTUM_FAILURE("Invalid path");
    FILE* f = fopen(path, "a");
    if (!f) return DICTUM_FAILURE(strerror(errno));
    size_t len = strlen(data);
    size_t written = fwrite(data, 1, len, f);
    fclose(f);
    if (written != len) return DICTUM_FAILURE("Append failed");
    return DICTUM_SUCCESS(0);
}

void dictum_file_close(dictum_handle_t h) {
    FILE* f = (FILE*)h;
    if (!f) return;

    dictum_handle_registry_remove(h);  /* remove before close to avoid UAF warning */
    fclose(f);
}
