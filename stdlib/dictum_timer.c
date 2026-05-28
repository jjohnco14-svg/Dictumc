#include "dictum_timer.h"
#include <pthread.h>
#include <time.h>
#include <unistd.h>
#include <stdlib.h>

#define DICTUM_MAX_TIMERS 256

typedef struct {
    pthread_t thread;
    dictum_count_t ms;
    void (*callback)(void);
    dictum_truth_t active;
} dictum_timer_entry_t;

static dictum_timer_entry_t timer_pool[DICTUM_MAX_TIMERS];

static void* timer_thread(void* arg) {
    dictum_timer_entry_t* t = (dictum_timer_entry_t*)arg;
    struct timespec ts = {(time_t)(t->ms / 1000), (long)((t->ms % 1000) * 1000000)};
    nanosleep(&ts, NULL);
    if (t->active && t->callback) {
        t->callback();
    }
    t->active = 0;
    return NULL;
}

dictum_whole_t dictum_timer_start(dictum_count_t ms, void (*callback)(void)) {
    for (int i = 0; i < DICTUM_MAX_TIMERS; i++) {
        if (!timer_pool[i].active) {
            timer_pool[i].ms = ms;
            timer_pool[i].callback = callback;
            timer_pool[i].active = 1;
            if (pthread_create(&timer_pool[i].thread, NULL, timer_thread, &timer_pool[i]) != 0) {
                timer_pool[i].active = 0;
                return 0;
            }
            return i + 1;
        }
    }
    return 0;
}

void dictum_timer_stop(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_TIMERS) return;
    int idx = (int)h - 1;
    if (!timer_pool[idx].active) return;
    timer_pool[idx].active = 0;
    pthread_cancel(timer_pool[idx].thread);
    pthread_join(timer_pool[idx].thread, NULL);
}

void dictum_timer_sleep(dictum_count_t ms) {
    struct timespec ts = {(time_t)(ms / 1000), (long)((ms % 1000) * 1000000)};
    nanosleep(&ts, NULL);
}
