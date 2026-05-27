#ifndef DICTUM_MATH_H
#define DICTUM_MATH_H

#include "dictum_core.h"

/* Dictum interface:
module Math:
    action abs takes X as whole number produces whole number
    action min takes A as whole number and B as whole number produces whole number
    action max takes A as whole number and B as whole number produces whole number
    action random produces count
    action random_between takes Min as count and Max as count produces count
end module
*/

dictum_whole_t dictum_math_abs(dictum_whole_t x);
dictum_whole_t dictum_math_min(dictum_whole_t a, dictum_whole_t b);
dictum_whole_t dictum_math_max(dictum_whole_t a, dictum_whole_t b);
dictum_count_t dictum_math_random(void);
dictum_count_t dictum_math_random_between(dictum_count_t min, dictum_count_t max);

#endif
