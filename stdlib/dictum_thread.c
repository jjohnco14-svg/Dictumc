#include "dictum_thread.h"
#include <pthread.h>
#include <unistd.h>
#include <string.h>

/* Rule 4: Thread registry to prevent leaks */
typedef struct {
    pthread_t thread;
    dictum_whole_t id;
    dictum_truth_t active;
} dictum_thread_entry_t;

static dictum_thread_entry_t thread_registry[DICTUM_MAX_THREADS];
static dictum_whole_t thread_next_id = 1;
static pthread_mutex_t thread_lock = PTHREAD_MUTEX_INITIALIZER;

dictum_result_t dictum_thread_spawn(dictum_thread_task_t task, void* arg) {
    pthread_mutex_lock(&thread_lock);

    /* Rule 9: Enforce thread limit */
    int slot = -1;
    for (int i = 0; i < DICTUM_MAX_THREADS; i++) {
        if (!thread_registry[i].active) {
            slot = i;
            break;
        }
    }
    if (slot < 0) {
        pthread_mutex_unlock(&thread_lock);
        return DICTUM_FAILURE("Thread limit reached");
    }

    dictum_whole_t id = thread_next_id++;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, 8 * 1024 * 1024);  /* Rule 1: 8MB stack */

    pthread_t pt;
    if (pthread_create(&pt, &attr, task, arg) != 0) {
        pthread_mutex_unlock(&thread_lock);
        return DICTUM_FAILURE("Thread creation failed");
    }

    thread_registry[slot].thread = pt;
    thread_registry[slot].id = id;
    thread_registry[slot].active = 1;

    pthread_mutex_unlock(&thread_lock);
    return DICTUM_SUCCESS(id);
}

dictum_truth_t dictum_thread_join(dictum_whole_t id) {
    pthread_mutex_lock(&thread_lock);
    for (int i = 0; i < DICTUM_MAX_THREADS; i++) {
        if (thread_registry[i].active && thread_registry[i].id == id) {
            pthread_t pt = thread_registry[i].thread;
            pthread_mutex_unlock(&thread_lock);
            pthread_join(pt, NULL);
            pthread_mutex_lock(&thread_lock);
            thread_registry[i].active = 0;
            pthread_mutex_unlock(&thread_lock);
            return 1;
        }
    }
    pthread_mutex_unlock(&thread_lock);
    return 0;
}

void dictum_thread_sleep(dictum_count_t ms) {
    struct timespec ts;
    ts.tv_sec = (time_t)(ms / 1000);
    ts.tv_nsec = (long)((ms % 1000) * 1000000);
    nanosleep(&ts, NULL);
}

dictum_whole_t dictum_thread_id(void) {
    return (dictum_whole_t)pthread_self();
}
