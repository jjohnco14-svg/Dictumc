#include "dictum_core.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

/* Thread-local error storage */
_Thread_local char dictum_last_error[256] = {0};

/* Handle registry */
static dictum_registry_entry_t registry[DICTUM_MAX_HANDLES];
static size_t registry_count = 0;

/* ============================================================================
   Rule 1: Safe Allocation -- No naked malloc/free
   ============================================================================ */
void* dictum_alloc(size_t size) {
    if (size == 0 || size > DICTUM_MAX_ALLOC) {
        dictum_error_set("Allocation size invalid or too large");
        return NULL;
    }
    void* p = calloc(1, size);  /* calloc zeroes memory */
    if (!p) {
        dictum_error_set("Out of memory");
    }
    return p;
}

void* dictum_realloc(void* old, size_t new_size) {
    if (new_size > DICTUM_MAX_ALLOC) {
        dictum_error_set("Realloc size too large");
        return NULL;
    }
    return realloc(old, new_size);
}

void dictum_free(void* p) {
    free(p);
}

char* dictum_strdup(const char* s) {
    if (!s) return NULL;
    size_t len = dictum_strnlen(s, DICTUM_MAX_STRING);
    char* copy = dictum_alloc(len + 1);
    if (!copy) return NULL;
    memcpy(copy, s, len);
    copy[len] = '\0';
    return copy;
}

/* ============================================================================
   Rule 2: Bounded String Operations
   ============================================================================ */
dictum_truth_t dictum_strncpy(char* dest, size_t dest_size, const char* src) {
    if (!dest || !src || dest_size == 0) return 0;
    size_t i;
    for (i = 0; i < dest_size - 1 && src[i]; i++) {
        dest[i] = src[i];
    }
    dest[i] = '\0';
    return src[i] == '\0' ? 1 : 0;  /* 1 if fit, 0 if truncated */
}

size_t dictum_strnlen(const char* s, size_t max) {
    if (!s) return 0;
    size_t i = 0;
    while (i < max && s[i]) i++;
    return i;
}

/* ============================================================================
   Rule 5: Checked Arithmetic
   ============================================================================ */
dictum_truth_t dictum_checked_add(size_t a, size_t b, size_t* out) {
    if (a > SIZE_MAX - b) return 0;
    *out = a + b;
    return 1;
}

dictum_truth_t dictum_checked_mul(size_t a, size_t b, size_t* out) {
    if (a != 0 && b > SIZE_MAX / a) return 0;
    *out = a * b;
    return 1;
}

/* ============================================================================
   Rule 4: Handle Registry -- No Resource Leaks
   ============================================================================ */
void dictum_handle_registry_add(dictum_handle_t h, const char* type, const char* info) {
    if (!h || !type) return;
    if (registry_count >= DICTUM_MAX_HANDLES) {
        dictum_error_set("Handle registry full");
        return;
    }
    registry[registry_count].handle = h;
    dictum_strncpy(registry[registry_count].type, sizeof(registry[0].type), type);
    if (info) {
        dictum_strncpy(registry[registry_count].info, sizeof(registry[0].info), info);
    }
    registry[registry_count].file = __FILE__;
    registry[registry_count].line = __LINE__;
    registry_count++;
}

void dictum_handle_registry_remove(dictum_handle_t h) {
    if (!h) return;
    for (size_t i = 0; i < registry_count; i++) {
        if (registry[i].handle == h) {
            registry[i] = registry[--registry_count];
            return;
        }
    }
}

void dictum_handle_registry_dump(void) {
    fprintf(stderr, "=== Dictum Handle Registry (%zu handles) ===\n", registry_count);
    for (size_t i = 0; i < registry_count; i++) {
        fprintf(stderr, "  [%zu] type=%s info=%s\n", i, registry[i].type, registry[i].info);
    }
}

/* ============================================================================
   Error Module
   ============================================================================ */
const char* dictum_error_last(void) {
    return dictum_last_error;
}

void dictum_error_clear(void) {
    dictum_last_error[0] = '\0';
}

void dictum_error_set(const char* msg) {
    if (!msg) return;
    dictum_strncpy(dictum_last_error, sizeof(dictum_last_error), msg);
}

void dictum_error_panic(const char* msg) {
    /* Rule 6: Controlled exit, not abort() */
    fprintf(stderr, "PANIC: %s\n", msg ? msg : "unknown");
    dictum_handle_registry_dump();
    exit(1);
}

