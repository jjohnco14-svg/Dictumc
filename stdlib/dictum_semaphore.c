#include "dictum_semaphore.h"
#include <semaphore.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>

#define DICTUM_MAX_SEMAPHORES 256

typedef struct {
    sem_t* sem;
    char name[64];
    dictum_truth_t active;
} dictum_sem_entry_t;

static dictum_sem_entry_t sem_pool[DICTUM_MAX_SEMAPHORES];

dictum_whole_t dictum_semaphore_create(const char* name, dictum_whole_t value) {
    if (!name || name[0] == '\0') return 0;
    if (value < 0) value = 0;

    for (int i = 0; i < DICTUM_MAX_SEMAPHORES; i++) {
        if (!sem_pool[i].active) {
            sem_t* s = sem_open(name, O_CREAT, 0666, (unsigned int)value);
            if (s == SEM_FAILED) return 0;
            sem_pool[i].sem = s;
            dictum_strncpy(sem_pool[i].name, sizeof(sem_pool[i].name), name);
            sem_pool[i].active = 1;
            return i + 1;
        }
    }
    return 0;
}

dictum_truth_t dictum_semaphore_wait(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_SEMAPHORES) return 0;
    int idx = (int)h - 1;
    if (!sem_pool[idx].active) return 0;
    return sem_wait(sem_pool[idx].sem) == 0;
}

dictum_truth_t dictum_semaphore_signal(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_SEMAPHORES) return 0;
    int idx = (int)h - 1;
    if (!sem_pool[idx].active) return 0;
    return sem_post(sem_pool[idx].sem) == 0;
}

void dictum_semaphore_destroy(dictum_whole_t h) {
    if (h < 1 || h > DICTUM_MAX_SEMAPHORES) return;
    int idx = (int)h - 1;
    if (!sem_pool[idx].active) return;
    sem_close(sem_pool[idx].sem);
    sem_unlink(sem_pool[idx].name);
    sem_pool[idx].active = 0;
}
