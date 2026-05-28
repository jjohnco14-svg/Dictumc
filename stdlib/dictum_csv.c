#include "dictum_csv.h"
#include <stdlib.h>
#include <string.h>

#define DICTUM_MAX_CSV 128
#define DICTUM_CSV_MAX_ROWS 1024
#define DICTUM_CSV_MAX_COLS 64

typedef struct {
    char* cells[DICTUM_CSV_MAX_ROWS][DICTUM_CSV_MAX_COLS];
    size_t rows;
    size_t cols;
    dictum_truth_t active;
} dictum_csv_t;

static dictum_csv_t csv_pool[DICTUM_MAX_CSV];

dictum_whole_t dictum_csv_parse(const char* s) {
    if (!s) return -1;
    for (int i = 0; i < DICTUM_MAX_CSV; i++) {
        if (!csv_pool[i].active) {
            csv_pool[i].rows = 0;
            csv_pool[i].cols = 0;
            csv_pool[i].active = 1;

            const char* p = s;
            size_t row = 0;
            size_t col = 0;

            while (*p && row < DICTUM_CSV_MAX_ROWS) {
                const char* start = p;
                while (*p && *p != ',' && *p != '\n' && *p != '\r') p++;
                size_t len = (size_t)(p - start);

                if (col < DICTUM_CSV_MAX_COLS) {
                    char* cell = dictum_alloc(len + 1);
                    if (cell) {
                        memcpy(cell, start, len);
                        cell[len] = '\0';
                        csv_pool[i].cells[row][col] = cell;
                        col++;
                    }
                }

                if (*p == ',') {
                    p++;
                } else if (*p == '\n' || *p == '\r') {
                    if (col > csv_pool[i].cols) csv_pool[i].cols = col;
                    row++;
                    col = 0;
                    if (*p == '\r' && *(p+1) == '\n') p++;
                    p++;
                } else {
                    break;
                }
            }
            if (col > 0) {
                if (col > csv_pool[i].cols) csv_pool[i].cols = col;
                row++;
            }
            csv_pool[i].rows = row;
            return i;
        }
    }
    return -1;
}

dictum_count_t dictum_csv_rows(dictum_whole_t h) {
    if (h < 0 || h >= DICTUM_MAX_CSV) return 0;
    if (!csv_pool[h].active) return 0;
    return csv_pool[h].rows;
}

dictum_count_t dictum_csv_columns(dictum_whole_t h) {
    if (h < 0 || h >= DICTUM_MAX_CSV) return 0;
    if (!csv_pool[h].active) return 0;
    return csv_pool[h].cols;
}

char* dictum_csv_get(dictum_whole_t h, dictum_count_t row, dictum_count_t col) {
    if (h < 0 || h >= DICTUM_MAX_CSV) return NULL;
    if (!csv_pool[h].active) return NULL;
    if (row >= csv_pool[h].rows || col >= csv_pool[h].cols) return NULL;
    if (!csv_pool[h].cells[row][col]) return dictum_strdup("");
    return dictum_strdup(csv_pool[h].cells[row][col]);
}

void dictum_csv_destroy(dictum_whole_t h) {
    if (h < 0 || h >= DICTUM_MAX_CSV) return;
    if (!csv_pool[h].active) return;
    for (size_t r = 0; r < csv_pool[h].rows; r++) {
        for (size_t c = 0; c < csv_pool[h].cols; c++) {
            dictum_free(csv_pool[h].cells[r][c]);
            csv_pool[h].cells[r][c] = NULL;
        }
    }
    csv_pool[h].rows = 0;
    csv_pool[h].cols = 0;
    csv_pool[h].active = 0;
}
