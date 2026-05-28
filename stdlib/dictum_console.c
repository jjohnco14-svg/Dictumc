#include "dictum_console.h"
#include <stdio.h>
#include <stdlib.h>

/* Rule 7: Hardcoded format strings only */
void dictum_console_write(const char* s) {
    if (!s) return;
    fputs(s, stdout);
}

void dictum_console_write_line(const char* s) {
    if (!s) return;
    puts(s);  /* Adds newline automatically */
}

/* Rule 3: read_line with bounded buffer and timeout-aware growth */
char* dictum_console_read_line(void) {
    size_t cap = 1024;
    size_t len = 0;
    char* buf = dictum_alloc(cap);
    if (!buf) return NULL;

    int c;
    while ((c = getchar()) != '\n' && c != EOF) {
        if (len + 1 >= cap) {
            size_t new_cap;
            if (!dictum_checked_mul(cap, 2, &new_cap) || new_cap > DICTUM_MAX_STRING) {
                dictum_free(buf);
                return NULL;
            }
            char* new_buf = dictum_realloc(buf, new_cap);
            if (!new_buf) {
                dictum_free(buf);
                return NULL;
            }
            buf = new_buf;
            cap = new_cap;
        }
        buf[len++] = (char)c;
    }
    buf[len] = '\0';
    return buf;
}

char dictum_console_read_char(void) {
    return (char)getchar();
}

void dictum_console_clear(void) {
    printf("\033[2J\033[H");
}
