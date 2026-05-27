#include "dictum_channel.h"
#include <pthread.h>
#include <stdlib.h>
#include <string.h>

#define DICTUM_MAX_CHANNELS 1024

typedef struct {
    char** buffer;
    size_t capacity;
    size_t count;
    size_t head;
    size_t tail;
    pthread_mutex_t lock;
    pthread_cond_t not_empty;
    pthread_cond_t not_full;
    dictum_truth_t closed;
    dictum_truth_t active;
} dictum_channel_t;

static dictum_channel_t* channel_pool[DICTUM_MAX_CHANNELS];
static dictum_truth_t channel_used[DICTUM_MAX_CHANNELS] = {0};
static pthread_mutex_t channel_pool_lock = PTHREAD_MUTEX_INITIALIZER;

dictum_whole_t dictum_channel_create(dictum_count_t capacity) {
    if (capacity == 0 || capacity > 10000) return 0;

    pthread_mutex_lock(&channel_pool_lock);
    for (int i = 0; i < DICTUM_MAX_CHANNELS; i++) {
        if (!channel_used[i]) {
            dictum_channel_t* ch = calloc(1, sizeof(dictum_channel_t));
            if (!ch) { pthread_mutex_unlock(&channel_pool_lock); return 0; }

            ch->buffer = calloc(capacity, sizeof(char*));
            if (!ch->buffer) { free(ch); pthread_mutex_unlock(&channel_pool_lock); return 0; }

            ch->capacity = capacity;
            pthread_mutex_init(&ch->lock, NULL);
            pthread_cond_init(&ch->not_empty, NULL);
            pthread_cond_init(&ch->not_full, NULL);
            ch->active = 1;

            channel_pool[i] = ch;
            channel_used[i] = 1;
            pthread_mutex_unlock(&channel_pool_lock);
            return i + 1;
        }
    }
    pthread_mutex_unlock(&channel_pool_lock);
    return 0;
}

dictum_truth_t dictum_channel_send(dictum_whole_t h, const char* data) {
    if (h < 1 || h > DICTUM_MAX_CHANNELS) return 0;
    int idx = (int)h - 1;
    if (!channel_used[idx]) return 0;

    dictum_channel_t* ch = channel_pool[idx];
    pthread_mutex_lock(&ch->lock);
    if (ch->closed) { pthread_mutex_unlock(&ch->lock); return 0; }

    while (ch->count >= ch->capacity && !ch->closed) {
        pthread_cond_wait(&ch->not_full, &ch->lock);
    }
    if (ch->closed) { pthread_mutex_unlock(&ch->lock); return 0; }

    ch->buffer[ch->tail] = dictum_strdup(data);
    ch->tail = (ch->tail + 1) % ch->capacity;
    ch->count++;
    pthread_cond_signal(&ch->not_empty);
    pthread_mutex_unlock(&ch->lock);
    return 1;
}

dictum_result_t dictum_channel_receive(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_CHANNELS) return DICTUM_FAILURE("Invalid handle");
    int idx = (int)h - 1;
    if (!channel_used[idx]) return DICTUM_FAILURE("Invalid handle");

    dictum_channel_t* ch = channel_pool[idx];
    pthread_mutex_lock(&ch->lock);

    while (ch->count == 0 && !ch->closed) {
        pthread_cond_wait(&ch->not_empty, &ch->lock);
    }
    if (ch->count == 0) {
        pthread_mutex_unlock(&ch->lock);
        return DICTUM_FAILURE("Channel closed");
    }

    char* data = ch->buffer[ch->head];
    ch->head = (ch->head + 1) % ch->capacity;
    ch->count--;
    pthread_cond_signal(&ch->not_full);
    pthread_mutex_unlock(&ch->lock);

    dictum_result_t r = DICTUM_SUCCESS(0);
    dictum_strncpy(r.error, sizeof(r.error), data ? data : "");
    /* Reuse error field for data since result shape has no data field */
    /* Caller should use dictum_strdup on r.error */
    dictum_free(data);
    return r;
}

void dictum_channel_close(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_CHANNELS) return;
    int idx = (int)h - 1;
    if (!channel_used[idx]) return;

    dictum_channel_t* ch = channel_pool[idx];
    pthread_mutex_lock(&ch->lock);
    ch->closed = 1;
    pthread_cond_broadcast(&ch->not_empty);
    pthread_cond_broadcast(&ch->not_full);
    pthread_mutex_unlock(&ch->lock);

    pthread_mutex_lock(&channel_pool_lock);
    for (size_t i = 0; i < ch->capacity; i++) {
        dictum_free(ch->buffer[i]);
    }
    free(ch->buffer);
    pthread_mutex_destroy(&ch->lock);
    pthread_cond_destroy(&ch->not_empty);
    pthread_cond_destroy(&ch->not_full);
    free(ch);
    channel_used[idx] = 0;
    pthread_mutex_unlock(&channel_pool_lock);
}
