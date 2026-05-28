#ifndef DICTUM_JSON_H
#define DICTUM_JSON_H

#include "dictum_core.h"

/*
 * Dictum JSON module — recursive-descent parser, no external dependencies.
 *
 * Supports: nested objects, arrays, strings, integers, floats, booleans, null.
 * Dot-path navigation: dictum_json_get(h, "slideshow.author") works.
 *
 * Dictum interface:
 * module Json:
 *     action parse         takes S as text produces whole number
 *     action get           takes H as whole number and Key as text produces text
 *     action get_string    takes H as whole number and Key as text produces text
 *     action get_int       takes H as whole number and Key as text produces whole number
 *     action get_float     takes H as whole number and Key as text produces decimal number
 *     action get_bool      takes H as whole number and Key as text produces truth value
 *     action set           takes H as whole number and Key as text and Value as text produces truth value
 *     action stringify     takes H as whole number produces text
 *     action destroy       takes H as whole number produces nothing
 * end module
 */

dictum_whole_t  dictum_json_parse(const char* s);
char*           dictum_json_get(dictum_whole_t h, const char* key);
char*           dictum_json_get_string(dictum_whole_t h, const char* key);
dictum_whole_t  dictum_json_get_int(dictum_whole_t h, const char* key);
double          dictum_json_get_float(dictum_whole_t h, const char* key);
dictum_truth_t  dictum_json_get_bool(dictum_whole_t h, const char* key);
dictum_truth_t  dictum_json_set(dictum_whole_t h, const char* key, const char* value);
char*           dictum_json_stringify(dictum_whole_t h);
void            dictum_json_destroy(dictum_whole_t h);

/* Array / nested navigation */
dictum_whole_t  dictum_json_length(dictum_whole_t h);
dictum_whole_t  dictum_json_array_length(dictum_whole_t h, const char* key);
char*           dictum_json_get_at(dictum_whole_t h, const char* key, dictum_whole_t index);
dictum_whole_t  dictum_json_get_int_at(dictum_whole_t h, const char* key, dictum_whole_t index);
double          dictum_json_get_float_at(dictum_whole_t h, const char* key, dictum_whole_t index);
dictum_whole_t  dictum_json_get_object_at(dictum_whole_t h, const char* key, dictum_whole_t index);
char*           dictum_json_get_path(dictum_whole_t h, const char* path);

#endif
