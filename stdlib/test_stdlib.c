/* Test suite for Dictum Standard Library Level 1 & 2 */
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "dictum_core.h"
#include "dictum_console.h"
#include "dictum_text.h"
#include "dictum_math.h"
#include "dictum_error.h"
#include "dictum_file.h"
#include "dictum_path.h"
#include "dictum_directory.h"

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name) void test_##name(void)
#define RUN(name) do {     printf("  [TEST] " #name " ... ");     test_##name();     printf("OK\n");     tests_passed++; } while(0)

#define FAIL(msg) do {     printf("FAIL\n    %s\n", msg);     tests_failed++;     return; } while(0)

/* ---------- Core ---------- */
TEST(core_alloc) {
    void* p = dictum_alloc(100);
    if (!p) FAIL("alloc failed");
    /* calloc zeroes */
    if (((char*)p)[0] != 0) FAIL("not zeroed");
    dictum_free(p);
}

TEST(core_checked_arithmetic) {
    size_t out;
    if (!dictum_checked_add(10, 20, &out)) FAIL("add failed");
    if (out != 30) FAIL("add wrong");
    if (dictum_checked_mul(SIZE_MAX, 2, &out)) FAIL("mul should overflow");
}

TEST(core_strncpy) {
    char buf[8];
    if (!dictum_strncpy(buf, sizeof(buf), "hello")) FAIL("strncpy fit");
    if (strcmp(buf, "hello") != 0) FAIL("strncpy content");
    if (dictum_strncpy(buf, sizeof(buf), "hello world")) FAIL("strncpy should truncate");
    if (strcmp(buf, "hello w") != 0) FAIL("strncpy truncation content");
}

/* ---------- Text ---------- */
TEST(text_length) {
    if (dictum_text_length("hello") != 5) FAIL("length");
    if (dictum_text_length("") != 0) FAIL("empty length");
    if (dictum_text_length(NULL) != 0) FAIL("null length");
}

TEST(text_find) {
    if (dictum_text_find("hello world", "world") != 7) FAIL("find");
    if (dictum_text_find("hello", "z") != 0) FAIL("find missing");
}

TEST(text_slice) {
    char* s = dictum_text_slice("hello", 1, 4);
    if (!s) FAIL("slice null");
    if (strcmp(s, "ell") != 0) FAIL("slice content");
    dictum_free(s);
    if (dictum_text_slice("hello", 10, 20) != NULL) FAIL("slice oob");
}

TEST(text_join) {
    char* s = dictum_text_join("hello", " world");
    if (!s) FAIL("join null");
    if (strcmp(s, "hello world") != 0) FAIL("join content");
    dictum_free(s);
}

TEST(text_compare) {
    if (!dictum_text_compare("a", "a")) FAIL("compare equal");
    if (dictum_text_compare("a", "b")) FAIL("compare diff");
}

TEST(text_starts_ends) {
    if (!dictum_text_starts_with("hello", "hel")) FAIL("starts");
    if (!dictum_text_ends_with("hello", "llo")) FAIL("ends");
    if (dictum_text_starts_with("hello", "lo")) FAIL("starts false");
}

TEST(text_replace) {
    char* s = dictum_text_replace("hello world", "world", "dictum");
    if (!s) FAIL("replace null");
    if (strcmp(s, "hello dictum") != 0) FAIL("replace content");
    dictum_free(s);
}

/* ---------- Math ---------- */
TEST(math_abs) {
    if (dictum_math_abs(-5) != 5) FAIL("abs neg");
    if (dictum_math_abs(5) != 5) FAIL("abs pos");
}

TEST(math_min_max) {
    if (dictum_math_min(3, 7) != 3) FAIL("min");
    if (dictum_math_max(3, 7) != 7) FAIL("max");
}

/* ---------- Error ---------- */
TEST(error_roundtrip) {
    dictum_error_clear();
    if (strlen(dictum_error_last()) != 0) FAIL("not cleared");
    dictum_error_set("test error");
    if (strcmp(dictum_error_last(), "test error") != 0) FAIL("set failed");
}

/* ---------- File + Path ---------- */
TEST(file_open_write_read) {
    const char* testfile = "test_tmp.txt";
    /* Clean up if exists */
    remove(testfile);

    dictum_result_t r = dictum_file_open(testfile, "w");
    if (!r.success) FAIL("open w");

    dictum_result_t w = dictum_file_write((dictum_handle_t)(size_t)r.handle, "dictum");
    if (!w.success) FAIL("write");

    dictum_file_close((dictum_handle_t)(size_t)r.handle);

    r = dictum_file_open(testfile, "r");
    if (!r.success) FAIL("open r");

    char* data = dictum_file_read((dictum_handle_t)(size_t)r.handle, 1024);
    if (!data) FAIL("read null");
    if (strcmp(data, "dictum") != 0) FAIL("read content");

    dictum_free(data);
    dictum_file_close((dictum_handle_t)(size_t)r.handle);
    remove(testfile);
}

TEST(path_validation) {
    if (dictum_path_valid("../etc/passwd")) FAIL("path traversal allowed");
    if (dictum_path_valid("/dev/null")) FAIL("/dev allowed");
    if (!dictum_path_valid("data.txt")) FAIL("valid path rejected");
}

TEST(directory_create_list_remove) {
    const char* testdir = "test_tmp_dir";
    dictum_directory_remove(testdir);  /* ignore errors */

    if (!dictum_directory_create(testdir)) FAIL("create");
    if (!dictum_path_is_directory(testdir)) FAIL("is_directory");

    char* list = dictum_directory_list(testdir);
    if (!list) FAIL("list null");
    /* Should be empty (no . or .. in output) */
    if (strlen(list) != 0) FAIL("list not empty for new dir");
    dictum_free(list);

    if (!dictum_directory_remove(testdir)) FAIL("remove");
    if (dictum_path_exists(testdir)) FAIL("exists after remove");
}

/* ---------- Main ---------- */
int main(void) {
    printf("========================================\n");
    printf("Dictum Standard Library Test Suite\n");
    printf("========================================\n");

    RUN(core_alloc);
    RUN(core_checked_arithmetic);
    RUN(core_strncpy);
    RUN(text_length);
    RUN(text_find);
    RUN(text_slice);
    RUN(text_join);
    RUN(text_compare);
    RUN(text_starts_ends);
    RUN(text_replace);
    RUN(math_abs);
    RUN(math_min_max);
    RUN(error_roundtrip);
    RUN(file_open_write_read);
    RUN(path_validation);
    RUN(directory_create_list_remove);

    printf("========================================\n");
    printf("Results: %d passed, %d failed\n", tests_passed, tests_failed);
    printf("========================================\n");
    return tests_failed > 0 ? 1 : 0;
}
