#ifndef DICTUM_CONSOLE_H
#define DICTUM_CONSOLE_H

#include "dictum_core.h"

/* Dictum interface:
module Console:
    action write takes S as text produces nothing
    action write_line takes S as text produces nothing
    action read_line produces text
    action read_char produces text
    action clear produces nothing
end module
*/

void dictum_console_write(const char* s);
void dictum_console_write_line(const char* s);
char* dictum_console_read_line(void);
char dictum_console_read_char(void);
void dictum_console_clear(void);

#endif
