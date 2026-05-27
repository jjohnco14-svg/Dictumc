/*
 * Dictum Niche Standard Library — Core Infrastructure
 * Target: Edge AI/ML + Embedded/IoT/Firmware
 * Version: 1.0.0 (matches Transpiler v2.2)
 * 
 * Safety Rules (Part 7 Compliance):
 *   1. NO naked malloc/free — dictum_alloc() only (NULL-checked, 1GB max, zeroed)
 *   2. NO unchecked string ops — dictum_strncpy() always null-terminates
 *   3. NO blocking forever — all I/O uses timeouts (default 30s), non-blocking mode
 *   4. NO resource leaks — all handles have explicit close functions + debug registry
 *   5. NO UB in arithmetic — checked_add, checked_mul macros
 *   6. ALL errors recoverable — no abort(), no assert() in production
 *   7. NO user-controlled format strings — all formats hardcoded
 *   8. NO raw memory access — no pointer arithmetic exposed
 *   9. NO privilege escalation
 *   10. NO deprecated protocols — TLS 1.3 only, AES-GCM only
 */

#ifndef DICTUM_STDLIB_CORE_H
#define DICTUM_STDLIB_CORE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* =============================================================================
 * TARGET DETECTION & FEATURE MATRIX
 * ============================================================================= */

/* =============================================================================
 * TARGET DETECTION & FEATURE MATRIX
 * ============================================================================= */

#if defined(ESP_PLATFORM)
  #if CONFIG_IDF_TARGET_ESP32S3
    #ifndef DICTUM_TARGET_ESP32S3
      #define DICTUM_TARGET_ESP32S3
      #define DICTUM_HAS_PSRAM
      #define DICTUM_HAS_CAMERA
      #define DICTUM_HAS_LLM
      #define DICTUM_HAS_WIFI
      #define DICTUM_HAS_BLE
      #define DICTUM_MAX_GPIO 48
      #define DICTUM_SRAM_KB 512
      #define DICTUM_PSRAM_KB 8192
      #define DICTUM_FLASH_KB 16384
      #define DICTUM_HAS_FREERTOS
    #endif
  #elif CONFIG_IDF_TARGET_ESP32
    #ifndef DICTUM_TARGET_ESP32
      #define DICTUM_TARGET_ESP32
      #define DICTUM_HAS_PSRAM
      #define DICTUM_HAS_WIFI
      #define DICTUM_HAS_BLE
      #define DICTUM_MAX_GPIO 39
      #define DICTUM_SRAM_KB 320
      #define DICTUM_PSRAM_KB 8192
      #define DICTUM_FLASH_KB 16384
      #define DICTUM_HAS_FREERTOS
    #endif
  #endif
#elif defined(STM32F4xx)
  #ifndef DICTUM_TARGET_STM32F4
    #define DICTUM_TARGET_STM32F4
    #define DICTUM_HAS_CMSIS_NN
    #define DICTUM_MAX_GPIO 144
    #define DICTUM_SRAM_KB 192
    #define DICTUM_FLASH_KB 1024
  #endif
#elif defined(STM32H7xx)
  #ifndef DICTUM_TARGET_STM32H7
    #define DICTUM_TARGET_STM32H7
    #define DICTUM_HAS_CMSIS_NN
    #define DICTUM_HAS_LLM  /* Only with external SDRAM */
    #define DICTUM_MAX_GPIO 224
    #define DICTUM_SRAM_KB 1024
    #define DICTUM_FLASH_KB 2048
  #endif
#elif defined(PICO_BUILD)
  #ifndef DICTUM_TARGET_RP2040
    #define DICTUM_TARGET_RP2040
    #define DICTUM_HAS_PIO
    #define DICTUM_MAX_GPIO 30
    #define DICTUM_SRAM_KB 264
    #define DICTUM_FLASH_KB 2048
  #endif
#elif defined(NRF52840_XXAA)
  #ifndef DICTUM_TARGET_NRF52840
    #define DICTUM_TARGET_NRF52840
    #define DICTUM_HAS_BLE
    #define DICTUM_MAX_GPIO 48
    #define DICTUM_SRAM_KB 256
    #define DICTUM_FLASH_KB 1024
  #endif
#elif defined(__linux__)
  #if defined(__arm__)
    #ifndef DICTUM_TARGET_PI_ZERO_2W
      #define DICTUM_TARGET_PI_ZERO_2W
      #define DICTUM_HAS_LLM
      #define DICTUM_HAS_SPEECH
      #define DICTUM_HAS_DIFFUSION
      #define DICTUM_HAS_RUNTIME
      #define DICTUM_HAS_WIFI
      #define DICTUM_HAS_BLE
      #define DICTUM_HAS_CAMERA
      #define DICTUM_SRAM_KB 512000
      #define DICTUM_PSRAM_KB 0
      #define DICTUM_FLASH_KB 0
    #endif
  #else
    #ifndef DICTUM_TARGET_PI5
      #define DICTUM_TARGET_PI5
      #define DICTUM_HAS_LLM
      #define DICTUM_HAS_SPEECH
      #define DICTUM_HAS_DIFFUSION
      #define DICTUM_HAS_RUNTIME
      #define DICTUM_HAS_WIFI
      #define DICTUM_HAS_BLE
      #define DICTUM_HAS_CAMERA
      #define DICTUM_SRAM_KB 8192000
      #define DICTUM_PSRAM_KB 0
      #define DICTUM_FLASH_KB 0
    #endif
  #endif
#endif

/* =============================================================================
 * TARGET DETECTION & FEATURE MATRIX
 * ============================================================================= */

#if defined(ESP_PLATFORM)
  #if CONFIG_IDF_TARGET_ESP32S3
    #define DICTUM_TARGET_ESP32S3
    #define DICTUM_HAS_PSRAM
    #define DICTUM_HAS_CAMERA
    #define DICTUM_HAS_LLM
    #define DICTUM_HAS_WIFI
    #define DICTUM_HAS_BLE
    #define DICTUM_MAX_GPIO 48
    #define DICTUM_SRAM_KB 512
    #define DICTUM_PSRAM_KB 8192
    #define DICTUM_FLASH_KB 16384
    #define DICTUM_HAS_FREERTOS
  #elif CONFIG_IDF_TARGET_ESP32
    #define DICTUM_TARGET_ESP32
    #define DICTUM_HAS_PSRAM
    #define DICTUM_HAS_WIFI
    #define DICTUM_HAS_BLE
    #define DICTUM_MAX_GPIO 39
    #define DICTUM_SRAM_KB 320
    #define DICTUM_PSRAM_KB 8192
    #define DICTUM_FLASH_KB 16384
    #define DICTUM_HAS_FREERTOS
  #endif
#elif defined(STM32F4xx)
  #define DICTUM_TARGET_STM32F4
  #define DICTUM_HAS_CMSIS_NN
  #define DICTUM_MAX_GPIO 144
  #define DICTUM_SRAM_KB 192
  #define DICTUM_FLASH_KB 1024
#elif defined(STM32H7xx)
  #define DICTUM_TARGET_STM32H7
  #define DICTUM_HAS_CMSIS_NN
  #define DICTUM_HAS_LLM  /* Only with external SDRAM */
  #define DICTUM_MAX_GPIO 224
  #define DICTUM_SRAM_KB 1024
  #define DICTUM_FLASH_KB 2048
#elif defined(PICO_BUILD)
  #define DICTUM_TARGET_RP2040
  #define DICTUM_HAS_PIO
  #define DICTUM_MAX_GPIO 30
  #define DICTUM_SRAM_KB 264
  #define DICTUM_FLASH_KB 2048
  /* No LLM, No Diffusion, Tensor max 2D */
#elif defined(NRF52840_XXAA)
  #define DICTUM_TARGET_NRF52840
  #define DICTUM_HAS_BLE
  #define DICTUM_MAX_GPIO 48
  #define DICTUM_SRAM_KB 256
  #define DICTUM_FLASH_KB 1024
#elif defined(__linux__)
  #if defined(__arm__)
    #define DICTUM_TARGET_PI_ZERO_2W
    #define DICTUM_HAS_LLM
    #define DICTUM_HAS_SPEECH
    #define DICTUM_HAS_DIFFUSION
    #define DICTUM_HAS_RUNTIME
    #define DICTUM_HAS_WIFI
    #define DICTUM_HAS_BLE
    #define DICTUM_HAS_CAMERA
    #define DICTUM_SRAM_KB 512000
    #define DICTUM_PSRAM_KB 0
    #define DICTUM_FLASH_KB 0
  #else
    #define DICTUM_TARGET_PI5
    #define DICTUM_HAS_LLM
    #define DICTUM_HAS_SPEECH
    #define DICTUM_HAS_DIFFUSION
    #define DICTUM_HAS_RUNTIME
    #define DICTUM_HAS_WIFI
    #define DICTUM_HAS_BLE
    #define DICTUM_HAS_CAMERA
    #define DICTUM_SRAM_KB 8192000
    #define DICTUM_PSRAM_KB 0
    #define DICTUM_FLASH_KB 0
  #endif
#endif

/* =============================================================================
 * CORE TYPES
 * ============================================================================= */

typedef int32_t  dictum_whole;
typedef size_t   dictum_count;
typedef double   dictum_frac;
typedef bool     dictum_truth;
typedef uint8_t  dictum_byte;
typedef char*    dictum_text;
typedef void*    dictum_handle;

/* Result type — every action that can fail returns this */
typedef struct {
    bool     ok;
    char     error[256];  /* Fixed buffer, no allocation */
} dictum_result;

/* Handle registry for leak detection (debug builds only) */
typedef struct {
    dictum_handle handle;
    const char*   kind;      /* "llm", "speech", "i2c", etc. */
    const char*   origin;    /* __FILE__:__LINE__ */
    bool          released;
} dictum_handle_record;

/* =============================================================================
 * CORE ALLOCATOR (Rule #1)
 * ============================================================================= */

#define DICTUM_MAX_ALLOC ((size_t)1024 * 1024 * 1024)  /* 1GB hard limit */

void* dictum_alloc(size_t size);
void  dictum_free(void* ptr);
void* dictum_realloc(void* ptr, size_t old_size, size_t new_size);

/* =============================================================================
 * STRING UTILITIES (Rule #2)
 * ============================================================================= */

/* Always null-terminates; returns dst */
char* dictum_strncpy(char* dst, const char* src, size_t n);
size_t dictum_strlen(const char* s);
int   dictum_strcmp(const char* a, const char* b);
bool  dictum_strstarts(const char* s, const char* prefix);
bool  dictum_strends(const char* s, const char* suffix);

/* =============================================================================
 * SAFE ARITHMETIC (Rule #5)
 * ============================================================================= */

#define DICTUM_CHECKED_ADD(a, b, out) \
    (__builtin_add_overflow((a), (b), (out)) ? false : true)

#define DICTUM_CHECKED_MUL(a, b, out) \
    (__builtin_mul_overflow((a), (b), (out)) ? false : true)

/* =============================================================================
 * PATH VALIDATION (Safety Contract)
 * ============================================================================= */

bool dictum_path_valid(const char* path);
bool dictum_path_in_scope(const char* path, const char* allowed_prefix);

/* =============================================================================
 * TIMEOUT INFRASTRUCTURE (Rule #3)
 * ============================================================================= */

#define DICTUM_DEFAULT_TIMEOUT_MS 30000

typedef struct {
    uint32_t start_ms;
    uint32_t timeout_ms;
} dictum_timeout;

void dictum_timeout_init(dictum_timeout* t, uint32_t ms);
bool dictum_timeout_expired(dictum_timeout* t);
void dictum_sleep_ms(uint32_t ms);
uint32_t dictum_time_ms(void);

/* =============================================================================
 * DEBUG / DIAGNOSTICS
 * ============================================================================= */

#ifdef DICTUM_DEBUG
  #define DICTUM_LOG(fmt, ...) dictum_log(__FILE__, __LINE__, fmt, ##__VA_ARGS__)
  void dictum_log(const char* file, int line, const char* fmt, ...);
  void dictum_dump_handles(void);
#else
  #define DICTUM_LOG(fmt, ...) ((void)0)
#endif

/* Handle registry API */
void dictum_handle_register(dictum_handle h, const char* kind, const char* origin);
void dictum_handle_mark_released(dictum_handle h);
bool dictum_handle_is_alive(dictum_handle h);

/* =============================================================================
 * ERROR RECOVERY (Rule #6) — No abort()
 * ============================================================================= */

dictum_result dictum_ok(void);
dictum_result dictum_err(const char* msg);
dictum_result dictum_errf(const char* fmt, ...);

#ifdef __cplusplus
}
#endif

#endif /* DICTUM_STDLIB_CORE_H */
