#include "dictum_math.h"
#include <stdlib.h>
#include <time.h>

/* Seed once at load time */
static dictum_truth_t math_seeded = 0;
static void ensure_seeded(void) {
    if (!math_seeded) {
        srand((unsigned)time(NULL));
        math_seeded = 1;
    }
}

dictum_whole_t dictum_math_abs(dictum_whole_t x) {
    return x < 0 ? -x : x;
}

dictum_whole_t dictum_math_min(dictum_whole_t a, dictum_whole_t b) {
    return a < b ? a : b;
}

dictum_whole_t dictum_math_max(dictum_whole_t a, dictum_whole_t b) {
    return a > b ? a : b;
}

dictum_count_t dictum_math_random(void) {
    ensure_seeded();
    return (dictum_count_t)rand();
}

dictum_count_t dictum_math_random_between(dictum_count_t min, dictum_count_t max) {
    ensure_seeded();
    if (min >= max) return min;
    return min + (dictum_count_t)(rand() % (max - min));
}
