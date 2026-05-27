#ifndef DICTUM_TEXT_H
#define DICTUM_TEXT_H

#include "dictum_core.h"

/* Dictum interface:
module Text:
    action length takes S as text produces count
    action utf8_length takes S as text produces count
    action find takes S as text and Pattern as text produces count
    action find_from takes S as text and Pattern as text and Start as count produces count
    action slice takes S as text and Start as count and End as count produces text
    action join takes A as text and B as text produces text
    action split takes S as text and Delim as text produces text
    action trim takes S as text produces text
    action to_upper takes S as text produces text
    action to_lower takes S as text produces text
    action replace takes S as text and Old as text and New as text produces text
    action compare takes A as text and B as text produces truth value
    action starts_with takes S as text and Prefix as text produces truth value
    action ends_with takes S as text and Suffix as text produces truth value
    action contains takes S as text and Sub as text produces truth value
    action format takes Fmt as text and ... produces text
    action from_int takes N as whole number produces text
    action from_float takes F as decimal number produces text
end module
*/

dictum_count_t  dictum_text_length(const char* s);
dictum_count_t  dictum_text_utf8_length(const char* s);
dictum_count_t  dictum_text_find(const char* s, const char* pattern);
dictum_count_t  dictum_text_find_from(const char* s, const char* pattern, dictum_count_t start);
char*           dictum_text_slice(const char* s, dictum_count_t start, dictum_count_t end);
char*           dictum_text_join(const char* a, const char* b);
char*           dictum_text_split(const char* s, const char* delim);
char*           dictum_text_trim(const char* s);
char*           dictum_text_to_upper(const char* s);
char*           dictum_text_to_lower(const char* s);
char*           dictum_text_replace(const char* s, const char* old, const char* new_str);
dictum_truth_t  dictum_text_compare(const char* a, const char* b);
dictum_truth_t  dictum_text_starts_with(const char* s, const char* prefix);
dictum_truth_t  dictum_text_ends_with(const char* s, const char* suffix);
dictum_truth_t  dictum_text_contains(const char* s, const char* sub);
char*           dictum_text_format(const char* fmt, ...);
char*           dictum_text_from_int(dictum_whole_t n);
char*           dictum_text_from_float(dictum_fractional_t f);

/* UTF-8 grapheme cluster operations */
dictum_count_t  dictum_text_grapheme_length(const char* s);
char*           dictum_text_grapheme_slice(const char* s, dictum_count_t start, dictum_count_t end);
char*           dictum_text_grapheme_reverse(const char* s);
char*           dictum_text_normalize(const char* s);

#endif
