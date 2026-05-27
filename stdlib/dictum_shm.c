#include "dictum_shm.h"
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>

#define DICTUM_MAX_SHM 128

typedef struct {
    void* addr;
    size_t size;
    dictum_truth_t active;
} dictum_shm_entry_t;

static dictum_shm_entry_t shm_registry[DICTUM_MAX_SHM];

dictum_result_t dictum_shm_create(const char* name, dictum_count_t size) {
    if (!name || name[0] == '\0') return DICTUM_FAILURE("Invalid name");
    if (size == 0 || size > DICTUM_MAX_ALLOC) return DICTUM_FAILURE("Invalid size");

    int fd = shm_open(name, O_RDWR | O_CREAT, 0666);
    if (fd < 0) return DICTUM_FAILURE(strerror(errno));

    if (ftruncate(fd, (off_t)size) != 0) {
        close(fd);
        return DICTUM_FAILURE(strerror(errno));
    }

    void* addr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (addr == MAP_FAILED) return DICTUM_FAILURE(strerror(errno));

    for (int i = 0; i < DICTUM_MAX_SHM; i++) {
        if (!shm_registry[i].active) {
            shm_registry[i].addr = addr;
            shm_registry[i].size = size;
            shm_registry[i].active = 1;
            dictum_handle_registry_add(addr, "shm", name);
            return DICTUM_SUCCESS(i);
        }
    }
    munmap(addr, size);
    return DICTUM_FAILURE("SHM registry full");
}

char* dictum_shm_read(dictum_whole_t h, dictum_count_t offset, dictum_count_t len) {
    if (h < 0 || h >= DICTUM_MAX_SHM) return NULL;
    if (!shm_registry[h].active) return NULL;
    if (offset + len > shm_registry[h].size) return NULL;

    char* buf = dictum_alloc(len + 1);
    if (!buf) return NULL;
    memcpy(buf, (char*)shm_registry[h].addr + offset, len);
    buf[len] = '\0';
    return buf;
}

dictum_truth_t dictum_shm_write(dictum_whole_t h, dictum_count_t offset, const char* data) {
    if (h < 0 || h >= DICTUM_MAX_SHM) return 0;
    if (!shm_registry[h].active) return 0;
    size_t len = strlen(data);
    if (offset + len > shm_registry[h].size) return 0;
    memcpy((char*)shm_registry[h].addr + offset, data, len);
    return 1;
}

void dictum_shm_close(dictum_whole_t h) {
    if (h < 0 || h >= DICTUM_MAX_SHM) return;
    if (!shm_registry[h].active) return;
    dictum_handle_registry_remove(shm_registry[h].addr);
    munmap(shm_registry[h].addr, shm_registry[h].size);
    shm_registry[h].active = 0;
}
