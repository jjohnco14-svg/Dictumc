/*
 * Dictum Niche Standard Library — Core Implementation
 */

#include "dictum_stdlib_core.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include <time.h>

#ifdef DICTUM_HAS_FREERTOS
  #include "freertos/FreeRTOS.h"
  #include "freertos/task.h"
#endif

#ifdef __linux__
  #include <unistd.h>
  #include <sys/time.h>
  #include <time.h>
#endif

/* =============================================================================
 * HANDLE REGISTRY (Debug Leak Detection)
 * ============================================================================= */

#define DICTUM_MAX_HANDLES 256

static dictum_handle_record g_handle_registry[DICTUM_MAX_HANDLES];
static int g_handle_count = 0;

void dictum_handle_register(dictum_handle h, const char* kind, const char* origin) {
    if (g_handle_count >= DICTUM_MAX_HANDLES) return;
    g_handle_registry[g_handle_count].handle = h;
    g_handle_registry[g_handle_count].kind = kind;
    g_handle_registry[g_handle_count].origin = origin;
    g_handle_registry[g_handle_count].released = false;
    g_handle_count++;
}

void dictum_handle_mark_released(dictum_handle h) {
    for (int i = 0; i < g_handle_count; i++) {
        if (g_handle_registry[i].handle == h) {
            g_handle_registry[i].released = true;
            return;
        }
    }
}

bool dictum_handle_is_alive(dictum_handle h) {
    for (int i = 0; i < g_handle_count; i++) {
        if (g_handle_registry[i].handle == h && !g_handle_registry[i].released) {
            return true;
        }
    }
    return false;
}

#ifdef DICTUM_DEBUG
void dictum_dump_handles(void) {
    printf("[DICTUM] Handle Registry (%d total):\n", g_handle_count);
    for (int i = 0; i < g_handle_count; i++) {
        printf("  [%d] %s @ %s — %s\n", i,
               g_handle_registry[i].kind,
               g_handle_registry[i].origin,
               g_handle_registry[i].released ? "released" : "ALIVE");
    }
}

void dictum_log(const char* file, int line, const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    printf("[DICTUM %s:%d] ", file, line);
    vprintf(fmt, args);
    printf("\n");
    va_end(args);
}
#endif

/* =============================================================================
 * ALLOCATOR (Rule #1: No naked malloc)
 * ============================================================================= */

void* dictum_alloc(size_t size) {
    if (size == 0) return NULL;
    if (size > DICTUM_MAX_ALLOC) return NULL;
    void* p = calloc(1, size);  /* calloc = zeroed */
    DICTUM_LOG("alloc %zu bytes -> %p", size, p);
    return p;
}

void dictum_free(void* ptr) {
    DICTUM_LOG("free %p", ptr);
    free(ptr);
}

void* dictum_realloc(void* ptr, size_t old_size, size_t new_size) {
    (void)old_size;  /* For checked arithmetic verification */
    if (new_size > DICTUM_MAX_ALLOC) return NULL;
    DICTUM_LOG("realloc %p -> %zu bytes", ptr, new_size);
    void* p = realloc(ptr, new_size);
    DICTUM_LOG("realloc result -> %p", p);
    return p;
}

/* =============================================================================
 * STRING UTILITIES (Rule #2: Always null-terminate)
 * ============================================================================= */

char* dictum_strncpy(char* dst, const char* src, size_t n) {
    if (n == 0) return dst;
    size_t i;
    for (i = 0; i < n - 1 && src[i] != '\0'; i++) {
        dst[i] = src[i];
    }
    dst[i] = '\0';
    return dst;
}

size_t dictum_strlen(const char* s) {
    size_t len = 0;
    while (s && s[len]) len++;
    return len;
}

int dictum_strcmp(const char* a, const char* b) {
    if (!a && !b) return 0;
    if (!a) return -1;
    if (!b) return 1;
    while (*a && *a == *b) { a++; b++; }
    return (unsigned char)*a - (unsigned char)*b;
}

bool dictum_strstarts(const char* s, const char* prefix) {
    if (!s || !prefix) return false;
    while (*prefix) {
        if (*s++ != *prefix++) return false;
    }
    return true;
}

bool dictum_strends(const char* s, const char* suffix) {
    if (!s || !suffix) return false;
    size_t sl = dictum_strlen(s);
    size_t xl = dictum_strlen(suffix);
    if (xl > sl) return false;
    return dictum_strcmp(s + sl - xl, suffix) == 0;
}

/* =============================================================================
 * PATH VALIDATION (Safety Contract)
 * ============================================================================= */

bool dictum_path_valid(const char* path) {
    if (!path || path[0] == '\0') return false;
    size_t len = dictum_strlen(path);
    if (len > 256) return false;
    /* Block traversal */
    if (dictum_strstarts(path, "../") || dictum_strstarts(path, "/..")) return false;
    if (dictum_strstarts(path, "./..")) return false;
    /* Block absolute paths on embedded */
    #if !defined(__linux__)
    if (path[0] == '/' && path[1] != 's' && path[1] != 't') return false;  /* Allow /sd /tmp only */
    #endif
    /* Block shell metacharacters (Rule #7) */
    for (size_t i = 0; i < len; i++) {
        char c = path[i];
        if (c == ';' || c == '|' || c == '&' || c == '$' || c == '`' || c == '<' || c == '>') {
            return false;
        }
    }
    return true;
}

bool dictum_path_in_scope(const char* path, const char* allowed_prefix) {
    if (!dictum_path_valid(path)) return false;
    if (!allowed_prefix) return true;
    return dictum_strstarts(path, allowed_prefix);
}

/* =============================================================================
 * TIMEOUT INFRASTRUCTURE (Rule #3)
 * ============================================================================= */

uint32_t dictum_time_ms(void) {
    #ifdef DICTUM_HAS_FREERTOS
        return xTaskGetTickCount() * portTICK_PERIOD_MS;
    #elif defined(__linux__)
        struct timeval tv;
        gettimeofday(&tv, NULL);
        return (uint32_t)(tv.tv_sec * 1000 + tv.tv_usec / 1000);
    #else
        /* Fallback: tick count not available, use simple counter */
        static uint32_t counter = 0;
        return counter++;  /* Degraded — platforms should override */
    #endif
}

void dictum_timeout_init(dictum_timeout* t, uint32_t ms) {
    t->start_ms = dictum_time_ms();
    t->timeout_ms = ms;
}

bool dictum_timeout_expired(dictum_timeout* t) {
    uint32_t now = dictum_time_ms();
    uint32_t elapsed = now - t->start_ms;  /* Unsigned wraparound is OK for timeouts */
    return elapsed >= t->timeout_ms;
}

void dictum_sleep_ms(uint32_t ms) {
    #ifdef DICTUM_HAS_FREERTOS
        vTaskDelay(pdMS_TO_TICKS(ms));
    #elif defined(__linux__)
        struct timespec ts = { .tv_sec = ms / 1000, .tv_nsec = (ms % 1000) * 1000000 };
        nanosleep(&ts, NULL);
    #else
        /* Busy-wait fallback (not ideal but universal) */
        volatile uint32_t count = ms * 1000;  /* Rough */
        while (count--) __asm__ volatile ("nop");
    #endif
}

/* =============================================================================
 * ERROR RECOVERY (Rule #6)
 * ============================================================================= */

dictum_result dictum_ok(void) {
    dictum_result r = {true, {0}};
    return r;
}

dictum_result dictum_err(const char* msg) {
    dictum_result r = {false, {0}};
    dictum_strncpy(r.error, msg, sizeof(r.error));
    return r;
}

dictum_result dictum_errf(const char* fmt, ...) {
    dictum_result r = {false, {0}};
    va_list args;
    va_start(args, fmt);
    vsnprintf(r.error, sizeof(r.error), fmt, args);
    va_end(args);
    return r;
}
