#ifndef DICTUM_CSV_H
#define DICTUM_CSV_H

#include "dictum_core.h"

/* Dictum interface:
module Csv:
    action parse takes S as text produces whole number
    action rows takes H as whole number produces count
    action columns takes H as whole number produces count
    action get takes H as whole number and Row as count and Col as count produces text
    action destroy takes H as whole number produces nothing
end module
*/

dictum_whole_t dictum_csv_parse(const char* s);
dictum_count_t dictum_csv_rows(dictum_whole_t h);
dictum_count_t dictum_csv_columns(dictum_whole_t h);
char* dictum_csv_get(dictum_whole_t h, dictum_count_t row, dictum_count_t col);
void dictum_csv_destroy(dictum_whole_t h);

#endif
