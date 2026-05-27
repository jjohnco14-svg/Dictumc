#ifndef DICTUM_ERROR_H
#define DICTUM_ERROR_H

#include "dictum_core.h"

/* P4.1: structured error type for attempt blocks */
typedef struct {
    int         code;       /* 0 = no error */
    const char* message;    /* points into dictum_last_error or a literal */
} dictum_error_t;

/* Thread-local last error — populated by any stdlib function that fails */
#define DICTUM_HAS_ERROR()      (dictum_last_error[0] != '\0')
#define DICTUM_CLEAR_ERROR()    (dictum_error_clear())

/* Dictum interface:
module Error:
    action last produces text
    action clear produces nothing
    action set takes Msg as text produces nothing
    action panic takes Msg as text produces nothing
end module
*/

const char* dictum_error_last(void);
void        dictum_error_clear(void);
void        dictum_error_set(const char* msg);
void        dictum_error_panic(const char* msg);

/* Convenience: build a dictum_error_t from the thread-local error buffer */
static inline dictum_error_t dictum_error_capture(void) {
    dictum_error_t e;
    e.message = dictum_error_last();
    e.code    = (e.message && e.message[0]) ? 1 : 0;
    return e;
}

#endif
