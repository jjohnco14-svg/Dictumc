#include "dictum_mutex.h"
#include <pthread.h>
#include <stdlib.h>

#define DICTUM_MAX_MUTEXES 4096

static pthread_mutex_t* mutex_pool[DICTUM_MAX_MUTEXES];
static dictum_truth_t mutex_used[DICTUM_MAX_MUTEXES] = {0};
static pthread_mutex_t pool_lock = PTHREAD_MUTEX_INITIALIZER;

dictum_whole_t dictum_mutex_create(void) {
    pthread_mutex_lock(&pool_lock);
    for (int i = 0; i < DICTUM_MAX_MUTEXES; i++) {
        if (!mutex_used[i]) {
            pthread_mutex_t* m = malloc(sizeof(pthread_mutex_t));
            if (!m) { pthread_mutex_unlock(&pool_lock); return 0; }
            pthread_mutex_init(m, NULL);
            mutex_pool[i] = m;
            mutex_used[i] = 1;
            pthread_mutex_unlock(&pool_lock);
            return i + 1;  /* 0 reserved for error */
        }
    }
    pthread_mutex_unlock(&pool_lock);
    return 0;
}

dictum_truth_t dictum_mutex_lock(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_MUTEXES) return 0;
    int idx = (int)h - 1;
    if (!mutex_used[idx]) return 0;
    return pthread_mutex_lock(mutex_pool[idx]) == 0;
}

dictum_truth_t dictum_mutex_unlock(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_MUTEXES) return 0;
    int idx = (int)h - 1;
    if (!mutex_used[idx]) return 0;
    return pthread_mutex_unlock(mutex_pool[idx]) == 0;
}

void dictum_mutex_destroy(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_MUTEXES) return;
    int idx = (int)h - 1;
    pthread_mutex_lock(&pool_lock);
    if (mutex_used[idx]) {
        pthread_mutex_destroy(mutex_pool[idx]);
        free(mutex_pool[idx]);
        mutex_used[idx] = 0;
    }
    pthread_mutex_unlock(&pool_lock);
}
