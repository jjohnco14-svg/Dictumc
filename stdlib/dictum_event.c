#include "dictum_event.h"
#include <pthread.h>
#include <stdlib.h>

#define DICTUM_MAX_EVENTS 256

typedef struct {
    pthread_cond_t cond;
    pthread_mutex_t lock;
    dictum_truth_t signaled;
    dictum_truth_t active;
} dictum_event_t;

static dictum_event_t* event_pool[DICTUM_MAX_EVENTS];
static dictum_truth_t event_used[DICTUM_MAX_EVENTS] = {0};

dictum_whole_t dictum_event_create(void) {
    for (int i = 0; i < DICTUM_MAX_EVENTS; i++) {
        if (!event_used[i]) {
            dictum_event_t* e = calloc(1, sizeof(dictum_event_t));
            if (!e) return 0;
            pthread_mutex_init(&e->lock, NULL);
            pthread_cond_init(&e->cond, NULL);
            e->active = 1;
            event_pool[i] = e;
            event_used[i] = 1;
            return i + 1;
        }
    }
    return 0;
}

dictum_truth_t dictum_event_wait(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_EVENTS) return 0;
    int idx = (int)h - 1;
    if (!event_used[idx]) return 0;
    dictum_event_t* e = event_pool[idx];
    pthread_mutex_lock(&e->lock);
    while (!e->signaled) {
        pthread_cond_wait(&e->cond, &e->lock);
    }
    e->signaled = 0;
    pthread_mutex_unlock(&e->lock);
    return 1;
}

dictum_truth_t dictum_event_signal(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_EVENTS) return 0;
    int idx = (int)h - 1;
    if (!event_used[idx]) return 0;
    dictum_event_t* e = event_pool[idx];
    pthread_mutex_lock(&e->lock);
    e->signaled = 1;
    pthread_cond_broadcast(&e->cond);
    pthread_mutex_unlock(&e->lock);
    return 1;
}

void dictum_event_destroy(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_EVENTS) return;
    int idx = (int)h - 1;
    if (!event_used[idx]) return;
    dictum_event_t* e = event_pool[idx];
    pthread_mutex_destroy(&e->lock);
    pthread_cond_destroy(&e->cond);
    free(e);
    event_used[idx] = 0;
}
