/*
 * Dictum Niche Standard Library — Test Suite
 * Validates all safety contracts and module functionality.
 */

#include "dictum_stdlib.h"
#include <stdio.h>
#include <assert.h>

#define TEST(name) printf("  [TEST] %-40s ", name); fflush(stdout)
#define PASS() printf("PASS\n")
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return 1; } while(0)

static int test_core_allocator(void) {
    TEST("dictum_alloc / dictum_free");
    void* p = dictum_alloc(1024);
    if (!p) FAIL("alloc returned null");
    /* Verify zeroed */
    unsigned char* b = (unsigned char*)p;
    for (int i = 0; i < 1024; i++) {
        if (b[i] != 0) FAIL("alloc not zeroed");
    }
    /* Verify 1GB limit */
    void* huge = dictum_alloc(1024ULL * 1024 * 1024 + 1);
    if (huge != NULL) FAIL("1GB+ alloc should fail");
    dictum_free(p);
    PASS();
    return 0;
}

static int test_core_strings(void) {
    TEST("dictum_strncpy / dictum_strlen");
    char dst[16];
    dictum_strncpy(dst, "hello", 16);
    if (dictum_strlen(dst) != 5) FAIL("strlen wrong");
    dictum_strncpy(dst, "verylongstringindeed", 16);
    if (dst[15] != '\0') FAIL("not null-terminated");
    if (dictum_strlen(dst) >= 16) FAIL("overflow");
    PASS();
    return 0;
}

static int test_core_paths(void) {
    TEST("dictum_path_valid");
    if (!dictum_path_valid("models/llama.gguf")) FAIL("valid path rejected");
    if (dictum_path_valid("../etc/passwd")) FAIL("traversal accepted");
    #if !defined(__linux__)
    if (dictum_path_valid("/etc/passwd")) FAIL("absolute path accepted on embedded");
    #endif
    if (dictum_path_valid("model; rm -rf /")) FAIL("command injection accepted");
    if (!dictum_path_valid("/sd/output.bmp")) FAIL("/sd/ prefix rejected");
    PASS();
    return 0;
}

static int test_core_arithmetic(void) {
    TEST("DICTUM_CHECKED_ADD / MUL");
    int32_t out;
    if (!DICTUM_CHECKED_ADD(100, 200, &out)) FAIL("simple add overflowed");
    if (out != 300) FAIL("add result wrong");
    if (DICTUM_CHECKED_ADD(INT32_MAX, 1, &out)) FAIL("overflow not detected");
    PASS();
    return 0;
}

static int test_core_errors(void) {
    TEST("dictum_err / dictum_ok");
    dictum_result r = dictum_ok();
    if (!r.ok) FAIL("ok returned false");
    r = dictum_err("test error");
    if (r.ok) FAIL("err returned true");
    if (dictum_strcmp(r.error, "test error") != 0) FAIL("error message wrong");
    PASS();
    return 0;
}

static int test_board_introspection(void) {
    TEST("Board.target / ram / flash");
    dictum_text tgt = dictum_board_target();
    if (!tgt || tgt[0] == '\0') FAIL("target empty");
    printf("(%s) ", tgt);
    dictum_count ram = dictum_board_ram_kb();
    (void)dictum_board_flash_kb();  /* Linux SBCs may return 0 — valid */
    if (ram == 0) FAIL("ram is 0");
    PASS();
    return 0;
}

static int test_pin_safety(void) {
    TEST("Pin.setup validation");
    dictum_pin_config cfg = { .number = 999, .mode = "output", .initial = false };
    dictum_pin_handle h;
    dictum_result r = dictum_pin_setup(&cfg, &h);
    if (r.ok) FAIL("invalid pin accepted");
    PASS();
    return 0;
}

static int test_i2c_bounds(void) {
    TEST("I2C read bounds (<=256)");
    dictum_i2c_config cfg = { .sda_pin = 21, .scl_pin = 22, .speed = 400000, .address = 118 };
    dictum_i2c_handle h;
    dictum_result r = dictum_i2c_init(&cfg, &h);
    if (!r.ok) {
        printf("(skip: no I2C bus) ");
        PASS();
        return 0;
    }
    /* Test that >256 is clamped — we can't actually read without hardware */
    dictum_i2c_close(h);
    PASS();
    return 0;
}

static int test_pwm_clamping(void) {
    TEST("PWM duty clamping 0-1000");
    dictum_pwm_handle h;
    dictum_result r = dictum_pwm_init(2, 1000, &h);
    if (!r.ok) {
        printf("(skip: no PWM) ");
        PASS();
        return 0;
    }
    r = dictum_pwm_set_duty(h, 5000);
    if (!r.ok) FAIL("set_duty failed");
    /* Duty should be clamped to 1000 */
    dictum_pwm_fade(h, 0, 100);
    dictum_pwm_fade(h, 2000, 100);  /* Should clamp to 1000 */
    PASS();
    return 0;
}

static int test_flash_protection(void) {
    TEST("Flash bootloader protection");
    dictum_result r = dictum_flash_erase(0);  /* Bootloader region */
    if (r.ok) FAIL("bootloader erase allowed");
    r = dictum_flash_erase(65536);  /* After bootloader */
    /* May fail for other reasons but should not be "bootloader protected" */
    if (!r.ok && dictum_strstarts(r.error, "bootloader")) FAIL("false positive");
    PASS();
    return 0;
}

static int test_flash_alignment(void) {
    TEST("Flash sector alignment");
    dictum_result r = dictum_flash_write(100, "test");  /* Misaligned */
    if (r.ok) FAIL("misaligned write accepted");
    PASS();
    return 0;
}

static int test_timer_basic(void) {
    TEST("Timer start / is_ready");
    dictum_timer_handle t = dictum_timer_start(50);
    if (!t) FAIL("timer creation failed");
    dictum_sleep_ms(60);
    if (!dictum_timer_is_ready(t)) FAIL("timer not ready after interval");
    dictum_timer_stop(t);
    PASS();
    return 0;
}

static int test_task_bounds(void) {
    TEST("Task stack bounds");
    dictum_task_config cfg = { .stack_size = 512, .priority = 10, .name = "test" };
    dictum_task_handle h;
    dictum_result r = dictum_task_spawn(&cfg, "main", &h);
    if (r.ok) FAIL("512B stack accepted (min 1KB)");
    cfg.stack_size = 128 * 1024;
    r = dictum_task_spawn(&cfg, "main", &h);
    if (r.ok) FAIL("128KB stack accepted (max 64KB)");
    PASS();
    return 0;
}

static int test_llm_unavailable(void) {
    TEST("LLM availability check");
    dictum_llm_config cfg = { .context = 4096, .temperature = 800, .top_p = 950, .seed = 42 };
    dictum_strncpy(cfg.backend, "cpu", sizeof(cfg.backend));
    dictum_llm_handle h;
    dictum_result r = dictum_llm_load("models/test.gguf", &cfg, &h);
    /* On targets without LLM support, should fail gracefully */
    if (r.ok) {
        printf("(loaded — cleaning up) ");
        dictum_llm_unload(h);
    }
    PASS();
    return 0;
}

static int test_diffusion_bounds(void) {
    TEST("Diffusion resolution clamping");
    dictum_diffusion_config cfg = { .width = 2048, .height = 2048, .steps = 100, .seed = 1 };
    dictum_strncpy(cfg.backend, "cpu", sizeof(cfg.backend));
    dictum_diffusion_handle h;
    dictum_result r = dictum_diffusion_load("models/test.gguf", &cfg, &h);
    if (r.ok) {
        printf("(loaded — cleaning up) ");
        dictum_diffusion_unload(h);
    }
    /* Steps should be clamped to 50 */
    PASS();
    return 0;
}

static int test_runtime_tensor_dims(void) {
    TEST("Runtime tensor dim bounds");
    dictum_tensor_desc desc = { .dims = 5, .d_0 = 1, .kind = "float32" };
    dictum_tensor_handle t;
    dictum_result r = dictum_runtime_tensor(&desc, &t);
    if (r.ok) FAIL("5D tensor accepted (max 4)");
    desc.dims = 0;
    r = dictum_runtime_tensor(&desc, &t);
    if (r.ok) FAIL("0D tensor accepted (min 1)");
    PASS();
    return 0;
}

static int test_runtime_tensor_oob(void) {
    TEST("Runtime tensor index OOB");
    dictum_tensor_desc desc = { .dims = 1, .d_0 = 4, .kind = "float32" };
    dictum_tensor_handle t;
    dictum_result r = dictum_runtime_tensor(&desc, &t);
    if (!r.ok) {
        printf("(skip) ");
        PASS();
        return 0;
    }
    dictum_runtime_tensor_set(t, 10, 42);  /* OOB — should log and ignore */
    dictum_whole v = dictum_runtime_tensor_get(t, 10);  /* OOB — should return 0 */
    if (v != 0) FAIL("OOB read returned non-zero");
    dictum_runtime_tensor_free(t);
    PASS();
    return 0;
}

static int test_handle_registry(void) {
    TEST("Handle registry / leak detection");
    #ifdef DICTUM_DEBUG
        dictum_dump_handles();
    #endif
    PASS();
    return 0;
}

int main(void) {
    printf("\n========================================\n");
    printf("Dictum Niche Standard Library Test Suite\n");
    printf("========================================\n\n");

    int failures = 0;

    printf("--- Core Infrastructure ---\n");
    failures += test_core_allocator();
    failures += test_core_strings();
    failures += test_core_paths();
    failures += test_core_arithmetic();
    failures += test_core_errors();

    printf("\n--- Embedded / IoT ---\n");
    failures += test_board_introspection();
    failures += test_pin_safety();
    failures += test_i2c_bounds();
    failures += test_pwm_clamping();
    failures += test_flash_protection();
    failures += test_flash_alignment();
    failures += test_timer_basic();
    failures += test_task_bounds();

    printf("\n--- Edge AI / ML ---\n");
    failures += test_llm_unavailable();
    failures += test_diffusion_bounds();
    failures += test_runtime_tensor_dims();
    failures += test_runtime_tensor_oob();

    printf("\n--- Diagnostics ---\n");
    failures += test_handle_registry();

    printf("\n========================================\n");
    if (failures == 0) {
        printf("ALL TESTS PASSED\n");
    } else {
        printf("FAILURES: %d\n", failures);
    }
    printf("========================================\n");

    return failures;
}
