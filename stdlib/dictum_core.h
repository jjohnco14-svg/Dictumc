#ifndef DICTUM_CORE_H
#define DICTUM_CORE_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

/* ============================================================================
   Dictum Core -- Safety Infrastructure
   ============================================================================ */

#define DICTUM_MAX_STRING   (1024LL * 1024 * 1024)  /* 1GB */
#define DICTUM_MAX_ALLOC    (1024LL * 1024 * 1024)
#define DICTUM_MAX_READ     (16 * 1024 * 1024)       /* 16MB per read */
#define DICTUM_MAX_NET_READ (4 * 1024 * 1024)        /* 4MB per net read */
#define DICTUM_MAX_HANDLES  4096
#define DICTUM_MAX_THREADS  1000
#define DICTUM_MAX_PATH     4096

typedef int32_t  dictum_whole_t;
typedef size_t   dictum_count_t;
typedef double   dictum_fractional_t;
typedef bool     dictum_truth_t;
typedef void*    dictum_handle_t;

typedef struct {
    dictum_truth_t success;
    dictum_whole_t handle;
    char error[256];
} dictum_result_t;

static inline dictum_result_t dictum_success(dictum_whole_t h) {
    dictum_result_t r = {1, h, {0}};
    return r;
}
static inline dictum_result_t dictum_failure(const char* e) {
    dictum_result_t r = {0, 0, {0}};
    if (e) {
        size_t i = 0;
        while (i < sizeof(r.error) - 1 && e[i]) {
            r.error[i] = e[i];
            i++;
        }
        r.error[i] = '\0';
    }
    return r;
}
#define DICTUM_SUCCESS(h) dictum_success(h)
#define DICTUM_FAILURE(e) dictum_failure(e)

/* Rule 1: Safe Allocation */
void* dictum_alloc(size_t size);
void* dictum_realloc(void* old, size_t new_size);
void  dictum_free(void* p);
char* dictum_strdup(const char* s);

/* Rule 2: Bounded Strings */
dictum_truth_t dictum_strncpy(char* dest, size_t dest_size, const char* src);
size_t dictum_strnlen(const char* s, size_t max);

/* Rule 5: Checked Arithmetic */
dictum_truth_t dictum_checked_add(size_t a, size_t b, size_t* out);
dictum_truth_t dictum_checked_mul(size_t a, size_t b, size_t* out);

/* Rule 4: Handle Registry */
typedef struct {
    dictum_handle_t handle;
    char type[32];
    char info[128];
    const char* file;
    int line;
} dictum_registry_entry_t;

void dictum_handle_registry_add(dictum_handle_t h, const char* type, const char* info);
void dictum_handle_registry_remove(dictum_handle_t h);
void dictum_handle_registry_dump(void);

/* Error handling */
_Thread_local extern char dictum_last_error[256];
const char* dictum_error_last(void);
void dictum_error_clear(void);
void dictum_error_set(const char* msg);
void dictum_error_panic(const char* msg);

/* Path validation (Rule 9) */
dictum_truth_t dictum_path_allowlisted(const char* path);
dictum_truth_t dictum_path_valid(const char* path);

#endif /* DICTUM_CORE_H */
