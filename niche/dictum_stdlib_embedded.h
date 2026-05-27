/*
 * Dictum Niche Standard Library — Embedded / IoT / Firmware Modules
 * Modules: Board, Pin, Bus, Sensor, PWM, Timer, WiFi, BLE, Camera, PIO, Flash, Task
 */

#ifndef DICTUM_STDLIB_EMBEDDED_H
#define DICTUM_STDLIB_EMBEDDED_H

#include "dictum_stdlib_core.h"

/* Forward declarations for cross-module types */
typedef struct dictum_tensor* dictum_tensor_handle;

#ifdef __cplusplus
extern "C" {
#endif

/* =============================================================================
 * MODULE: Board (Platform Introspection)
 * ============================================================================= */

dictum_text dictum_board_target(void);
dictum_count dictum_board_cpu_mhz(void);
dictum_count dictum_board_ram_kb(void);
dictum_count dictum_board_psram_kb(void);
dictum_count dictum_board_flash_kb(void);
void dictum_board_reset(void);
void dictum_board_deep_sleep(dictum_count ms);

/* =============================================================================
 * MODULE: Pin (GPIO)
 * ============================================================================= */

typedef struct {
    dictum_count number;
    char mode[16];          /* "input", "output", "pullup", "pulldown" */
    dictum_truth initial;
} dictum_pin_config;

typedef struct dictum_pin_ctx* dictum_pin_handle;

dictum_result dictum_pin_setup(dictum_pin_config* cfg, dictum_pin_handle* out);
void dictum_pin_write(dictum_count number, dictum_truth state);
dictum_truth dictum_pin_read(dictum_count number);
void dictum_pin_toggle(dictum_count number);

/* =============================================================================
 * MODULE: Bus (I2C, SPI, UART)
 * ============================================================================= */

typedef struct {
    dictum_count sda_pin;
    dictum_count scl_pin;
    dictum_count speed;     /* 100000 or 400000 */
    dictum_count address;   /* 7-bit device address */
} dictum_i2c_config;

typedef struct dictum_i2c_ctx* dictum_i2c_handle;

dictum_result dictum_i2c_init(dictum_i2c_config* cfg, dictum_i2c_handle* out);
dictum_text dictum_i2c_read(dictum_i2c_handle h, dictum_count length);
dictum_result dictum_i2c_write(dictum_i2c_handle h, const char* data);
void dictum_i2c_close(dictum_i2c_handle h);

/* SPI and UART follow same pattern — declared for completeness */
typedef struct dictum_spi_ctx* dictum_spi_handle;
typedef struct dictum_uart_ctx* dictum_uart_handle;

/* =============================================================================
 * MODULE: Sensor (Unified Reading)
 * ============================================================================= */

typedef struct {
    char kind[32];          /* "temperature", "humidity", "pressure", "acceleration" */
    dictum_whole value;     /* fixed-point * 1000 */
    char unit[8];
    dictum_truth valid;
} dictum_sensor_reading;

dictum_sensor_reading dictum_sensor_read(const char* kind, dictum_i2c_handle bus);
dictum_result dictum_sensor_calibrate(const char* kind, dictum_whole offset);

/* =============================================================================
 * MODULE: PWM
 * ============================================================================= */

typedef struct dictum_pwm_ctx* dictum_pwm_handle;

dictum_result dictum_pwm_init(dictum_count pin, dictum_count frequency, dictum_pwm_handle* out);
dictum_result dictum_pwm_set_duty(dictum_pwm_handle h, dictum_whole percent);  /* 0-1000 = 0.0%-100.0% */
void dictum_pwm_fade(dictum_pwm_handle h, dictum_whole target, dictum_count duration_ms);

/* =============================================================================
 * MODULE: Timer
 * ============================================================================= */

typedef struct dictum_timer_ctx* dictum_timer_handle;

dictum_timer_handle dictum_timer_start(dictum_count interval_ms);
dictum_truth dictum_timer_is_ready(dictum_timer_handle h);
void dictum_timer_wait(dictum_timer_handle h);
void dictum_timer_stop(dictum_timer_handle h);

/* =============================================================================
 * MODULE: WiFi (ESP32 / Pi)
 * ============================================================================= */

typedef struct {
    char ssid[64];
    char password[64];
    dictum_count timeout_ms;
} dictum_wifi_config;

dictum_result dictum_wifi_init(dictum_wifi_config* cfg);
dictum_truth dictum_wifi_is_connected(void);
dictum_text dictum_wifi_ip_address(void);
void dictum_wifi_disconnect(void);
dictum_text dictum_wifi_scan(void);

/* =============================================================================
 * MODULE: BLE (nRF52 / Arduino / ESP32)
 * ============================================================================= */

typedef struct {
    char device_name[32];
    dictum_truth is_peripheral;
} dictum_ble_config;

typedef struct dictum_ble_ctx* dictum_ble_handle;

dictum_result dictum_ble_init(dictum_ble_config* cfg, dictum_ble_handle* out);
void dictum_ble_advertise(const char* service_uuid);
void dictum_ble_notify(dictum_ble_handle h, const char* data);
dictum_text dictum_ble_read(dictum_ble_handle h);
void dictum_ble_disconnect(dictum_ble_handle h);

/* =============================================================================
 * MODULE: Camera (ESP32-S3 / Pi)
 * ============================================================================= */

typedef struct {
    dictum_count width;
    dictum_count height;
    char format[16];        /* "rgb", "grayscale", "jpeg" */
} dictum_camera_config;

typedef struct dictum_cam_ctx* dictum_camera_handle;
typedef struct dictum_frame* dictum_frame_handle;

dictum_result dictum_camera_init(dictum_camera_config* cfg, dictum_camera_handle* out);
dictum_frame_handle dictum_camera_capture(dictum_camera_handle h);
dictum_tensor_handle dictum_camera_to_tensor(dictum_frame_handle f, const char* kind);
void dictum_camera_free(dictum_frame_handle f);

/* =============================================================================
 * MODULE: PIO (RP2040 only)
 * ============================================================================= */

typedef struct dictum_pio_ctx* dictum_pio_handle;

dictum_result dictum_pio_load_program(const char* asm_text, dictum_count pin, dictum_pio_handle* out);
void dictum_pio_start(dictum_pio_handle h);
void dictum_pio_stop(dictum_pio_handle h);
void dictum_pio_push(dictum_pio_handle h, dictum_count data);
dictum_count dictum_pio_pull(dictum_pio_handle h);
void dictum_pio_unload(dictum_pio_handle h);

/* =============================================================================
 * MODULE: Flash (Non-volatile storage)
 * ============================================================================= */

dictum_count dictum_flash_sector_size(void);
dictum_text dictum_flash_read(dictum_count address, dictum_count length);
dictum_result dictum_flash_write(dictum_count address, const char* data);
dictum_result dictum_flash_erase(dictum_count address);
void dictum_flash_lock(dictum_count address);
void dictum_flash_unlock(dictum_count address);

/* =============================================================================
 * MODULE: Task (Multi-tasking)
 * ============================================================================= */

typedef struct {
    dictum_count stack_size;    /* 1KB–64KB */
    dictum_count priority;      /* 1-25 */
    char name[32];
} dictum_task_config;

typedef struct dictum_task_ctx* dictum_task_handle;

dictum_result dictum_task_spawn(dictum_task_config* cfg, const char* entry_action, dictum_task_handle* out);
void dictum_task_yield(void);
void dictum_task_sleep(dictum_count ms);
dictum_result dictum_task_join(dictum_task_handle h);
void dictum_task_kill(dictum_task_handle h);

#ifdef __cplusplus
}
#endif

#endif /* DICTUM_STDLIB_EMBEDDED_H */
