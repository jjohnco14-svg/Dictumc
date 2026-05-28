#include "dictum_mmap.h"
#include "dictum_path.h"
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>

#define DICTUM_MAX_MMAPS 256

typedef struct {
    void* addr;
    size_t size;
    int fd;
    dictum_truth_t active;
} dictum_mmap_entry_t;

static dictum_mmap_entry_t mmap_registry[DICTUM_MAX_MMAPS];

dictum_result_t dictum_mmap_create(const char* path, dictum_count_t size) {
    if (!dictum_path_valid(path)) return DICTUM_FAILURE("Invalid path");
    if (size == 0 || size > DICTUM_MAX_ALLOC) return DICTUM_FAILURE("Invalid size");

    int fd = open(path, O_RDWR | O_CREAT, 0644);
    if (fd < 0) return DICTUM_FAILURE(strerror(errno));

    if (ftruncate(fd, (off_t)size) != 0) {
        close(fd);
        return DICTUM_FAILURE(strerror(errno));
    }

    void* addr = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (addr == MAP_FAILED) {
        close(fd);
        return DICTUM_FAILURE(strerror(errno));
    }

    for (int i = 0; i < DICTUM_MAX_MMAPS; i++) {
        if (!mmap_registry[i].active) {
            mmap_registry[i].addr = addr;
            mmap_registry[i].size = size;
            mmap_registry[i].fd = fd;
            mmap_registry[i].active = 1;
            dictum_handle_registry_add(addr, "mmap", path);
            return DICTUM_SUCCESS(i);
        }
    }

    munmap(addr, size);
    close(fd);
    return DICTUM_FAILURE("Mmap registry full");
}

char* dictum_mmap_read(dictum_whole_t h, dictum_count_t offset, dictum_count_t len) {
    if (h < 0 || h >= DICTUM_MAX_MMAPS) return NULL;
    if (!mmap_registry[h].active) return NULL;
    if (offset + len > mmap_registry[h].size) return NULL;

    char* buf = dictum_alloc(len + 1);
    if (!buf) return NULL;
    memcpy(buf, (char*)mmap_registry[h].addr + offset, len);
    buf[len] = '\0';
    return buf;
}

dictum_truth_t dictum_mmap_write(dictum_whole_t h, dictum_count_t offset, const char* data) {
    if (h < 0 || h >= DICTUM_MAX_MMAPS) return 0;
    if (!mmap_registry[h].active) return 0;
    size_t len = strlen(data);
    if (offset + len > mmap_registry[h].size) return 0;

    memcpy((char*)mmap_registry[h].addr + offset, data, len);
    return 1;
}

void dictum_mmap_close(dictum_whole_t h) {
    if (h < 0 || h >= DICTUM_MAX_MMAPS) return;
    if (!mmap_registry[h].active) return;

    dictum_handle_registry_remove(mmap_registry[h].addr);
    munmap(mmap_registry[h].addr, mmap_registry[h].size);
    close(mmap_registry[h].fd);
    mmap_registry[h].active = 0;
}
