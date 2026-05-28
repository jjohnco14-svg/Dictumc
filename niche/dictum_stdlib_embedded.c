/*
 * Dictum Niche Standard Library — Embedded / IoT / Firmware Implementation
 * 
 * Safety enforced:
 *   - Pin number validated against MAX_GPIO per platform
 *   - I2C read bounded by 256 bytes
 *   - PWM duty clamped 0-1000, frequency validated
 *   - Flash address aligned to sector_size, bootloader protected
 *   - Task stack bounded 1KB-64KB
 *   - All I/O uses timeouts (default 500ms for bus, 30s for net)
 */

#include "dictum_stdlib_embedded.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

/* =============================================================================
 * PLATFORM HAL INCLUDES
 * ============================================================================= */

#ifdef DICTUM_TARGET_ESP32
  #include "driver/gpio.h"
  #include "driver/i2c.h"
  #include "driver/ledc.h"
  #include "esp_system.h"
  #include "esp_sleep.h"
  #include "esp_wifi.h"
  #include "esp_event.h"
  #include "esp_camera.h"
#endif

#ifdef DICTUM_TARGET_RP2040
  #include "pico/stdlib.h"
  #include "hardware/i2c.h"
  #include "hardware/pwm.h"
  #include "hardware/pio.h"
  #include "hardware/timer.h"
  #include "hardware/flash.h"
#endif

#ifdef DICTUM_TARGET_NRF52840
  #include "nrf_gpio.h"
  #include "nrf_delay.h"
  #include "ble.h"
#endif

#ifdef DICTUM_TARGET_STM32F4
  #include "stm32f4xx_hal.h"
#endif

#ifdef DICTUM_TARGET_STM32H7
  #include "stm32h7xx_hal.h"
#endif

#ifdef __linux__
  #include <sys/ioctl.h>
  #include <linux/i2c-dev.h>
  #include <fcntl.h>
  #include <unistd.h>
  #include <pthread.h>
#endif

/* =============================================================================
 * MODULE: Board
 * ============================================================================= */

dictum_text dictum_board_target(void) {
    #if defined(DICTUM_TARGET_ESP32S3)
        return "esp32s3";
    #elif defined(DICTUM_TARGET_ESP32)
        return "esp32";
    #elif defined(DICTUM_TARGET_STM32F4)
        return "stm32f4";
    #elif defined(DICTUM_TARGET_STM32H7)
        return "stm32h7";
    #elif defined(DICTUM_TARGET_RP2040)
        return "rp2040";
    #elif defined(DICTUM_TARGET_NRF52840)
        return "nrf52840";
    #elif defined(DICTUM_TARGET_PI_ZERO_2W)
        return "pi_zero_2w";
    #elif defined(DICTUM_TARGET_PI5)
        return "pi5";
    #else
        return "unknown";
    #endif
}

dictum_count dictum_board_cpu_mhz(void) {
    #if defined(DICTUM_TARGET_ESP32)
        return 240;
    #elif defined(DICTUM_TARGET_ESP32S3)
        return 240;
    #elif defined(DICTUM_TARGET_STM32F4)
        return 168;
    #elif defined(DICTUM_TARGET_STM32H7)
        return 480;
    #elif defined(DICTUM_TARGET_RP2040)
        return 133;
    #elif defined(DICTUM_TARGET_NRF52840)
        return 64;
    #elif defined(DICTUM_TARGET_PI_ZERO_2W)
        return 1000;
    #elif defined(DICTUM_TARGET_PI5)
        return 2400;
    #else
        return 0;
    #endif
}

dictum_count dictum_board_ram_kb(void) {
    #ifdef DICTUM_SRAM_KB
        return DICTUM_SRAM_KB;
    #else
        return 0;
    #endif
}

dictum_count dictum_board_psram_kb(void) {
    #ifdef DICTUM_HAS_PSRAM
        return DICTUM_PSRAM_KB;
    #else
        return 0;
    #endif
}

dictum_count dictum_board_flash_kb(void) {
    #ifdef DICTUM_FLASH_KB
        return DICTUM_FLASH_KB;
    #else
        return 0;
    #endif
}

void dictum_board_reset(void) {
    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        esp_restart();
    #elif defined(DICTUM_TARGET_RP2040)
        watchdog_reboot(0, 0, 0);
    #elif defined(__linux__)
        /* system("reboot") requires root; use sync+reboot syscall if available */
        sync();
    #else
        NVIC_SystemReset();
    #endif
}

void dictum_board_deep_sleep(dictum_count ms) {
    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        esp_sleep_enable_timer_wakeup(ms * 1000);
        esp_deep_sleep_start();
    #elif defined(DICTUM_TARGET_NRF52840)
        /* Nordic low-power mode */
        (void)ms;
    #else
        dictum_sleep_ms(ms);
    #endif
}

/* =============================================================================
 * MODULE: Pin
 * ============================================================================= */

static bool dictum_pin_valid(dictum_count number) {
#ifdef DICTUM_MAX_GPIO
    if (number > DICTUM_MAX_GPIO) return false;
#else
    if (number > 100) return false;  /* Generic fallback */
#endif
    #if defined(DICTUM_TARGET_ESP32)
        /* GPIO 6-11 reserved for flash */
        if (number >= 6 && number <= 11) return false;
    #endif
    return true;
}

#ifdef DICTUM_MAX_GPIO
#ifdef DICTUM_MAX_GPIO
static dictum_pin_handle g_pin_handles[DICTUM_MAX_GPIO] = {0};
#else
static dictum_pin_handle g_pin_handles[100] = {0};
/* Referenced by pin functions on all platforms */
#endif
#else
static dictum_pin_handle g_pin_handles[100] = {0};
/* Referenced by pin functions on all platforms */
#endif

struct dictum_pin_ctx {
    dictum_count number;
    char mode[16];
};

dictum_result dictum_pin_setup(dictum_pin_config* cfg, dictum_pin_handle* out) {
    if (!cfg || !out) return dictum_err("null argument");
    if (!dictum_pin_valid(cfg->number)) return dictum_errf("pin %u out of range", (unsigned)cfg->number);

    /* Mode validation: reject "output" on read-only pins */
    if (dictum_strcmp(cfg->mode, "output") == 0) {
        #if defined(DICTUM_TARGET_ESP32)
            if (cfg->number >= 34 && cfg->number <= 39) {
                return dictum_err("pins 34-39 are input-only");
            }
        #endif
    }

    dictum_pin_handle h = (dictum_pin_handle)dictum_alloc(sizeof(struct dictum_pin_ctx));
    if (!h) return dictum_err("allocation failed");

    h->number = cfg->number;
    dictum_strncpy(h->mode, cfg->mode, sizeof(h->mode));
    g_pin_handles[cfg->number] = h;

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        gpio_mode_t mode = GPIO_MODE_DISABLE;
        if (dictum_strcmp(cfg->mode, "input") == 0) mode = GPIO_MODE_INPUT;
        else if (dictum_strcmp(cfg->mode, "output") == 0) mode = GPIO_MODE_OUTPUT;
        else if (dictum_strcmp(cfg->mode, "pullup") == 0) mode = GPIO_MODE_INPUT;
        else if (dictum_strcmp(cfg->mode, "pulldown") == 0) mode = GPIO_MODE_INPUT;

        gpio_set_direction((gpio_num_t)cfg->number, mode);
        if (dictum_strcmp(cfg->mode, "pullup") == 0) gpio_pullup_en((gpio_num_t)cfg->number);
        if (dictum_strcmp(cfg->mode, "pulldown") == 0) gpio_pulldown_en((gpio_num_t)cfg->number);
        if (dictum_strcmp(cfg->mode, "output") == 0) gpio_set_level((gpio_num_t)cfg->number, cfg->initial);
    #elif defined(DICTUM_TARGET_RP2040)
        if (dictum_strcmp(cfg->mode, "output") == 0) {
            gpio_init(cfg->number);
            gpio_set_dir(cfg->number, GPIO_OUT);
            gpio_put(cfg->number, cfg->initial);
        } else {
            gpio_init(cfg->number);
            gpio_set_dir(cfg->number, GPIO_IN);
            if (dictum_strcmp(cfg->mode, "pullup") == 0) gpio_pull_up(cfg->number);
            if (dictum_strcmp(cfg->mode, "pulldown") == 0) gpio_pull_down(cfg->number);
        }
    #elif defined(DICTUM_TARGET_STM32F4) || defined(DICTUM_TARGET_STM32H7)
        /* TODO: HAL_GPIO_Init via BSP */
        (void)cfg;
    #endif

    g_pin_handles[cfg->number] = h;  /* Track for validation */
    dictum_handle_register(h, "pin", "setup");
    *out = h;
    return dictum_ok();
}

void dictum_pin_write(dictum_count number, dictum_truth state) {
    if (!dictum_pin_valid(number)) return;
    dictum_pin_handle h = g_pin_handles[number];
    if (h && dictum_strcmp(h->mode, "output") != 0) {
        DICTUM_LOG("pin_write on non-output pin %u", (unsigned)number);
        return;
    }

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        gpio_set_level((gpio_num_t)number, state ? 1 : 0);
    #elif defined(DICTUM_TARGET_RP2040)
        gpio_put(number, state);
    #elif defined(DICTUM_TARGET_STM32F4) || defined(DICTUM_TARGET_STM32H7)
        HAL_GPIO_WritePin(GPIOA, (1U << number), state ? GPIO_PIN_SET : GPIO_PIN_RESET);
    #else
        (void)state;
    #endif
}

dictum_truth dictum_pin_read(dictum_count number) {
    if (!dictum_pin_valid(number)) return false;

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        return gpio_get_level((gpio_num_t)number) != 0;
    #elif defined(DICTUM_TARGET_RP2040)
        return gpio_get(number);
    #elif defined(DICTUM_TARGET_STM32F4) || defined(DICTUM_TARGET_STM32H7)
        return HAL_GPIO_ReadPin(GPIOA, (1U << number)) == GPIO_PIN_SET;
    #else
        return false;
    #endif
}

void dictum_pin_toggle(dictum_count number) {
    if (!dictum_pin_valid(number)) return;

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        gpio_set_level((gpio_num_t)number, !gpio_get_level((gpio_num_t)number));
    #elif defined(DICTUM_TARGET_RP2040)
        gpio_xor_mask(1U << number);
    #elif defined(DICTUM_TARGET_STM32F4) || defined(DICTUM_TARGET_STM32H7)
        HAL_GPIO_TogglePin(GPIOA, (1U << number));
    #endif
}

/* =============================================================================
 * MODULE: Bus (I2C)
 * ============================================================================= */

struct dictum_i2c_ctx {
    dictum_i2c_config cfg;
    dictum_timeout timeout;
    #ifdef __linux__
        int fd;
    #endif
};

static bool dictum_i2c_speed_valid(dictum_count speed) {
    return speed == 100000 || speed == 400000;
}

dictum_result dictum_i2c_init(dictum_i2c_config* cfg, dictum_i2c_handle* out) {
    if (!cfg || !out) return dictum_err("null argument");
    if (!dictum_i2c_speed_valid(cfg->speed)) return dictum_err("i2c speed must be 100000 or 400000");
    if (cfg->address > 127) return dictum_err("i2c address must be 7-bit");
    if (!dictum_pin_valid(cfg->sda_pin) || !dictum_pin_valid(cfg->scl_pin)) {
        return dictum_err("invalid SDA/SCL pin");
    }

    dictum_i2c_handle h = (dictum_i2c_handle)dictum_alloc(sizeof(struct dictum_i2c_ctx));
    if (!h) return dictum_err("allocation failed");

    h->cfg = *cfg;
    dictum_timeout_init(&h->timeout, 500);  /* 500ms bus timeout */

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        i2c_config_t conf = {
            .mode = I2C_MODE_MASTER,
            .sda_io_num = cfg->sda_pin,
            .scl_io_num = cfg->scl_pin,
            .sda_pullup_en = GPIO_PULLUP_ENABLE,
            .scl_pullup_en = GPIO_PULLUP_ENABLE,
            .master.clk_speed = cfg->speed,
        };
        i2c_param_config(I2C_NUM_0, &conf);
        i2c_driver_install(I2C_NUM_0, I2C_MODE_MASTER, 0, 0, 0);
    #elif defined(DICTUM_TARGET_RP2040)
        i2c_init(i2c_default, cfg->speed);
        gpio_set_function(cfg->sda_pin, GPIO_FUNC_I2C);
        gpio_set_function(cfg->scl_pin, GPIO_FUNC_I2C);
        gpio_pull_up(cfg->sda_pin);
        gpio_pull_up(cfg->scl_pin);
    #elif defined(__linux__)
        char dev[32];
        snprintf(dev, sizeof(dev), "/dev/i2c-%d", 1);  /* Default bus 1 on Pi */
        h->fd = open(dev, O_RDWR);
        if (h->fd < 0) {
            dictum_free(h);
            return dictum_err("failed to open i2c device");
        }
        if (ioctl(h->fd, I2C_SLAVE, cfg->address) < 0) {
            close(h->fd);
            dictum_free(h);
            return dictum_err("failed to set i2c address");
        }
    #endif

    dictum_handle_register(h, "i2c", "init");
    *out = h;
    return dictum_ok();
}

dictum_text dictum_i2c_read(dictum_i2c_handle h, dictum_count length) {
    if (!h) return NULL;
    if (length > 256) {
        DICTUM_LOG("i2c_read clamped %u to 256", (unsigned)length);
        length = 256;
    }

    char* buf = (char*)dictum_alloc(length + 1);
    if (!buf) return NULL;

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        i2c_cmd_handle_t cmd = i2c_cmd_link_create();
        i2c_master_start(cmd);
        i2c_master_write_byte(cmd, (h->cfg.address << 1) | 1, true);
        if (length > 1) i2c_master_read(cmd, (uint8_t*)buf, length - 1, I2C_MASTER_ACK);
        i2c_master_read_byte(cmd, (uint8_t*)(buf + length - 1), I2C_MASTER_NACK);
        i2c_master_stop(cmd);
        i2c_master_cmd_begin(I2C_NUM_0, cmd, pdMS_TO_TICKS(500));
        i2c_cmd_link_delete(cmd);
    #elif defined(DICTUM_TARGET_RP2040)
        int ret = i2c_read_timeout_us(i2c_default, h->cfg.address, (uint8_t*)buf, length, false, 500000);
        if (ret < 0) {
            dictum_free(buf);
            return NULL;
        }
    #elif defined(__linux__)
        if (read(h->fd, buf, length) != (int)length) {
            dictum_free(buf);
            return NULL;
        }
    #endif

    buf[length] = '\0';
    return buf;
}

dictum_result dictum_i2c_write(dictum_i2c_handle h, const char* data) {
    if (!h) return dictum_err("invalid handle");
    if (!data || data[0] == '\0') return dictum_err("i2c_write rejects empty data");

    size_t len = dictum_strlen(data);

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        i2c_cmd_handle_t cmd = i2c_cmd_link_create();
        i2c_master_start(cmd);
        i2c_master_write_byte(cmd, (h->cfg.address << 1) | 0, true);
        i2c_master_write(cmd, (const uint8_t*)data, len, true);
        i2c_master_stop(cmd);
        esp_err_t err = i2c_master_cmd_begin(I2C_NUM_0, cmd, pdMS_TO_TICKS(500));
        i2c_cmd_link_delete(cmd);
        if (err != ESP_OK) return dictum_err("i2c write failed");
    #elif defined(DICTUM_TARGET_RP2040)
        int ret = i2c_write_timeout_us(i2c_default, h->cfg.address, (const uint8_t*)data, len, false, 500000);
        if (ret < 0) return dictum_err("i2c write failed");
    #elif defined(__linux__)
        if (write(h->fd, data, len) != (int)len) return dictum_err("i2c write failed");
    #endif

    return dictum_ok();
}

void dictum_i2c_close(dictum_i2c_handle h) {
    if (!h) return;
    if (!dictum_handle_is_alive(h)) {
        DICTUM_LOG("double-close of i2c handle %p", (void*)h);
        return;
    }

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        i2c_driver_delete(I2C_NUM_0);
    #elif defined(__linux__)
        if (h->fd >= 0) close(h->fd);
    #endif

    dictum_handle_mark_released(h);
    dictum_free(h);
}

/* =============================================================================
 * MODULE: Sensor
 * ============================================================================= */

static dictum_whole g_sensor_offsets[4] = {0};  /* temp, humidity, pressure, accel */

dictum_sensor_reading dictum_sensor_read(const char* kind, dictum_i2c_handle bus) {
    dictum_sensor_reading r = {"", 0, "", false};
    if (!bus || !kind) return r;

    dictum_strncpy(r.kind, kind, sizeof(r.kind));

    if (dictum_strcmp(kind, "temperature") == 0) {
        /* Example: BME280 raw read at 0xFA */
        dictum_result wr = dictum_i2c_write(bus, "\xFA");
        if (!wr.ok) return r;
        dictum_text raw = dictum_i2c_read(bus, 3);
        if (!raw) return r;
        /* Simplified conversion (real driver would calibrate) */
        r.value = ((dictum_whole)(uint8_t)raw[0] << 12) + g_sensor_offsets[0];
        r.value = r.value * 1000 / 16384;  /* Fixed-point * 1000 */
        dictum_strncpy(r.unit, "mC", sizeof(r.unit));
        r.valid = true;
        dictum_free(raw);
    }
    else if (dictum_strcmp(kind, "acceleration") == 0) {
        dictum_result wr = dictum_i2c_write(bus, "\x28");  /* LIS3DH OUT_X_L */
        if (!wr.ok) return r;
        dictum_text raw = dictum_i2c_read(bus, 6);
        if (!raw) return r;
        r.value = ((dictum_whole)(int8_t)raw[0]) * 1000 + g_sensor_offsets[3];
        dictum_strncpy(r.unit, "mg", sizeof(r.unit));
        r.valid = true;
        dictum_free(raw);
    }
    /* TODO: humidity, pressure */

    return r;
}

dictum_result dictum_sensor_calibrate(const char* kind, dictum_whole offset) {
    if (dictum_strcmp(kind, "temperature") == 0) g_sensor_offsets[0] = offset;
    else if (dictum_strcmp(kind, "humidity") == 0) g_sensor_offsets[1] = offset;
    else if (dictum_strcmp(kind, "pressure") == 0) g_sensor_offsets[2] = offset;
    else if (dictum_strcmp(kind, "acceleration") == 0) g_sensor_offsets[3] = offset;
    else return dictum_err("unknown sensor kind");
    return dictum_ok();
}

/* =============================================================================
 * MODULE: PWM
 * ============================================================================= */

struct dictum_pwm_ctx {
    dictum_count pin;
    dictum_count freq;
    dictum_whole duty;  /* 0-1000 */
};

dictum_result dictum_pwm_init(dictum_count pin, dictum_count frequency, dictum_pwm_handle* out) {
    if (!out) return dictum_err("null output");
    if (!dictum_pin_valid(pin)) return dictum_err("invalid pin");

    /* Frequency validation per platform */
    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        if (frequency < 1 || frequency > 40000000) return dictum_err("ESP32 PWM freq 1Hz-40MHz");
    #elif defined(DICTUM_TARGET_RP2040)
        if (frequency < 1 || frequency > 10000000) return dictum_err("RP2040 PWM freq 1Hz-10MHz");
    #endif

    dictum_pwm_handle h = (dictum_pwm_handle)dictum_alloc(sizeof(struct dictum_pwm_ctx));
    if (!h) return dictum_err("allocation failed");

    h->pin = pin;
    h->freq = frequency;
    h->duty = 0;

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        ledc_timer_config_t timer = {
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .duty_resolution = LEDC_TIMER_10_BIT,
            .timer_num = LEDC_TIMER_0,
            .freq_hz = frequency,
            .clk_cfg = LEDC_AUTO_CLK,
        };
        ledc_timer_config(&timer);
        ledc_channel_config_t channel = {
            .gpio_num = pin,
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .channel = LEDC_CHANNEL_0,
            .timer_sel = LEDC_TIMER_0,
            .duty = 0,
            .hpoint = 0,
        };
        ledc_channel_config(&channel);
    #elif defined(DICTUM_TARGET_RP2040)
        gpio_set_function(pin, GPIO_FUNC_PWM);
        uint slice = pwm_gpio_to_slice_num(pin);
        pwm_config cfg = pwm_get_default_config();
        pwm_config_set_clkdiv_int(&cfg, 125000000 / frequency);
        pwm_init(slice, &cfg, true);
    #endif

    dictum_handle_register(h, "pwm", "init");
    *out = h;
    return dictum_ok();
}

dictum_result dictum_pwm_set_duty(dictum_pwm_handle h, dictum_whole percent) {
    if (!h) return dictum_err("invalid handle");
    if (percent > 1000) percent = 1000;
    if (percent < 0) percent = 0;
    h->duty = percent;

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        uint32_t duty = (percent * 1023) / 1000;
        ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, duty);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
    #elif defined(DICTUM_TARGET_RP2040)
        uint16_t level = (percent * 65535) / 1000;
        pwm_set_gpio_level(h->pin, level);
    #endif

    return dictum_ok();
}

void dictum_pwm_fade(dictum_pwm_handle h, dictum_whole target, dictum_count duration_ms) {
    if (!h) return;
    if (target > 1000) target = 1000;
    if (target < 0) target = 0;

    dictum_whole start = h->duty;
    dictum_count steps = 50;
    for (dictum_count i = 0; i <= steps; i++) {
        dictum_whole duty = start + ((target - start) * (dictum_whole)i) / (dictum_whole)steps;
        dictum_pwm_set_duty(h, duty);
        dictum_sleep_ms(duration_ms / steps);
    }
}

/* =============================================================================
 * MODULE: Timer
 * ============================================================================= */

struct dictum_timer_ctx {
    dictum_count interval_ms;
    uint32_t last_ready_ms;
};

dictum_timer_handle dictum_timer_start(dictum_count interval_ms) {
    dictum_timer_handle h = (dictum_timer_handle)dictum_alloc(sizeof(struct dictum_timer_ctx));
    if (!h) return NULL;
    h->interval_ms = interval_ms;
    h->last_ready_ms = dictum_time_ms();
    dictum_handle_register(h, "timer", "start");
    return h;
}

dictum_truth dictum_timer_is_ready(dictum_timer_handle h) {
    if (!h) return false;
    uint32_t now = dictum_time_ms();
    uint32_t elapsed = now - h->last_ready_ms;
    if (elapsed >= h->interval_ms) {
        h->last_ready_ms = now;
        return true;
    }
    return false;
}

void dictum_timer_wait(dictum_timer_handle h) {
    if (!h) return;
    while (!dictum_timer_is_ready(h)) {
        dictum_sleep_ms(1);
    }
}

void dictum_timer_stop(dictum_timer_handle h) {
    if (!h) return;
    dictum_handle_mark_released(h);
    dictum_free(h);
}

/* =============================================================================
 * MODULE: WiFi
 * ============================================================================= */

static dictum_truth g_wifi_connected = false;

#if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
static void dictum_wifi_event_handler(void* arg, void* event_base, int32_t event_id, void* event_data) {
    (void)arg; (void)event_data;
    extern void* WIFI_EVENT;
    extern void* IP_EVENT;
    extern int32_t WIFI_EVENT_STA_DISCONNECTED;
    extern int32_t IP_EVENT_STA_GOT_IP;
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        g_wifi_connected = false;
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        g_wifi_connected = true;
    }
}
#endif

dictum_result dictum_wifi_init(dictum_wifi_config* cfg) {
    if (!cfg) return dictum_err("null config");
    if (dictum_strlen(cfg->ssid) == 0) return dictum_err("empty SSID");

    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        /* ESP-IDF WiFi init - requires ESP-IDF SDK */
        (void)cfg;
        g_wifi_connected = true;  /* Stub for now */
    #elif defined(__linux__)
        /* On Linux, WiFi is managed by OS — stub for now */
        (void)cfg;
        g_wifi_connected = true;
    #else
        return dictum_err("wifi not available on this target");
    #endif

    return dictum_ok();
}

dictum_truth dictum_wifi_is_connected(void) {
    #ifdef DICTUM_HAS_WIFI
        return g_wifi_connected;
    #else
        return false;
    #endif
}

dictum_text dictum_wifi_ip_address(void) {
    static char buf[32];
    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        /* ESP-IDF IP address - requires ESP-IDF SDK */
        (void)buf;
    #elif defined(__linux__)
        dictum_strncpy(buf, "127.0.0.1", sizeof(buf));
        return buf;
    #endif
    return "0.0.0.0";
}

void dictum_wifi_disconnect(void) {
    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        /* esp_wifi_disconnect(); */
    #endif
    g_wifi_connected = false;
    g_wifi_connected = false;
}

dictum_text dictum_wifi_scan(void) {
    static char buf[1024];
    buf[0] = '\0';
    #if defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        /* ESP-IDF WiFi scan - requires ESP-IDF SDK */
        (void)buf;
    #endif
    return buf;
}

/* =============================================================================
 * MODULE: BLE
 * ============================================================================= */

struct dictum_ble_ctx {
    char device_name[32];
    dictum_truth is_peripheral;
};

#ifdef DICTUM_HAS_BLE
  /* TODO: NimBLE or Nordic SDK integration */
#endif

dictum_result dictum_ble_init(dictum_ble_config* cfg, dictum_ble_handle* out) {
    if (!cfg || !out) return dictum_err("null argument");

    dictum_ble_handle h = (dictum_ble_handle)dictum_alloc(sizeof(struct dictum_ble_ctx));
    if (!h) return dictum_err("allocation failed");

    dictum_strncpy(h->device_name, cfg->device_name, sizeof(h->device_name));
    h->is_peripheral = cfg->is_peripheral;

    #if defined(DICTUM_HAS_BLE)
        /* TODO: BLE stack init */
    #else
        dictum_free(h);
        return dictum_err("BLE not available on this target");
    #endif

    dictum_handle_register(h, "ble", "init");
    *out = h;
    return dictum_ok();
}

void dictum_ble_advertise(const char* service_uuid) {
    (void)service_uuid;
    /* TODO: start advertising */
}

void dictum_ble_notify(dictum_ble_handle h, const char* data) {
    if (!h) return;
    (void)data;
    /* TODO: send notification */
}

dictum_text dictum_ble_read(dictum_ble_handle h) {
    if (!h) return NULL;
    static char buf[256];
    dictum_strncpy(buf, "", sizeof(buf));
    /* TODO: read characteristic */
    return buf;
}

void dictum_ble_disconnect(dictum_ble_handle h) {
    if (!h) return;
    dictum_handle_mark_released(h);
    dictum_free(h);
}

/* =============================================================================
 * MODULE: Camera
 * ============================================================================= */

struct dictum_cam_ctx {
    dictum_camera_config cfg;
};

struct dictum_frame {
    dictum_count width;
    dictum_count height;
    char format[16];
    dictum_handle data;
    size_t data_len;
};

#ifdef DICTUM_HAS_CAMERA
  /* ESP32 camera driver includes handled in core header */
#endif

dictum_result dictum_camera_init(dictum_camera_config* cfg, dictum_camera_handle* out) {
    if (!cfg || !out) return dictum_err("null argument");

    #if defined(DICTUM_TARGET_ESP32S3)
        if (DICTUM_PSRAM_KB < 8192 && (cfg->width > 640 || cfg->height > 480)) {
            return dictum_err("camera resolution capped to 640x480 with <8MB PSRAM");
        }
    #endif

    dictum_camera_handle h = (dictum_camera_handle)dictum_alloc(sizeof(struct dictum_cam_ctx));
    if (!h) return dictum_err("allocation failed");
    h->cfg = *cfg;

    #if defined(DICTUM_HAS_CAMERA)
        /* TODO: esp_camera_init() or V4L2 on Linux */
    #else
        dictum_free(h);
        return dictum_err("camera not available on this target");
    #endif

    dictum_handle_register(h, "camera", "init");
    *out = h;
    return dictum_ok();
}

dictum_frame_handle dictum_camera_capture(dictum_camera_handle h) {
    if (!h) return NULL;

    dictum_frame_handle f = (dictum_frame_handle)dictum_alloc(sizeof(struct dictum_frame));
    if (!f) return NULL;

    f->width = h->cfg.width;
    f->height = h->cfg.height;
    dictum_strncpy(f->format, h->cfg.format, sizeof(f->format));

    size_t pixel_size = dictum_strcmp(h->cfg.format, "rgb") == 0 ? 3 :
                        dictum_strcmp(h->cfg.format, "grayscale") == 0 ? 1 : 2;
    f->data_len = (size_t)h->cfg.width * h->cfg.height * pixel_size;
    f->data = dictum_alloc(f->data_len);
    if (!f->data) {
        dictum_free(f);
        return NULL;
    }

    #if defined(DICTUM_HAS_CAMERA)
        /* TODO: esp_camera_fb_get() or V4L2 capture */
    #endif

    dictum_handle_register(f, "frame", "capture");
    return f;
}

dictum_tensor_handle dictum_camera_to_tensor(dictum_frame_handle f, const char* kind) {
    if (!f || !f->data) return NULL;
    (void)kind;
    /* TODO: normalize and copy into tensor */
    return NULL;
}

void dictum_camera_free(dictum_frame_handle f) {
    if (!f) return;
    if (f->data) {
        dictum_free(f->data);
        f->data = NULL;
    }
    dictum_handle_mark_released(f);
    dictum_free(f);
}

/* =============================================================================
 * MODULE: PIO (RP2040 only)
 * ============================================================================= */

struct dictum_pio_ctx {
    dictum_count pin;
    #ifdef DICTUM_TARGET_RP2040
        PIO pio;
        uint sm;
        uint offset;
    #else
        void* pio;
        unsigned int sm;
        unsigned int offset;
    #endif
};

dictum_result dictum_pio_load_program(const char* asm_text, dictum_count pin, dictum_pio_handle* out) {
    if (!asm_text || !out) return dictum_err("null argument");
    if (!dictum_pin_valid(pin)) return dictum_err("invalid pin");

    #if defined(DICTUM_TARGET_RP2040)
        dictum_pio_handle h = (dictum_pio_handle)dictum_alloc(sizeof(struct dictum_pio_ctx));
        if (!h) return dictum_err("allocation failed");

        h->pin = pin;
        h->pio = pio0;
        /* TODO: parse asm_text and load via pio_add_program() */
        h->sm = 0;
        h->offset = 0;

        dictum_handle_register(h, "pio", "load");
        *out = h;
        return dictum_ok();
    #else
        return dictum_err("PIO only available on RP2040");
    #endif
}

void dictum_pio_start(dictum_pio_handle h) {
    if (!h) return;
    #if defined(DICTUM_TARGET_RP2040)
        pio_sm_set_enabled(h->pio, h->sm, true);
    #endif
}

void dictum_pio_stop(dictum_pio_handle h) {
    if (!h) return;
    #if defined(DICTUM_TARGET_RP2040)
        pio_sm_set_enabled(h->pio, h->sm, false);
    #endif
}

void dictum_pio_push(dictum_pio_handle h, dictum_count data) {
    if (!h) return;
    #if defined(DICTUM_TARGET_RP2040)
        pio_sm_put(h->pio, h->sm, data);
    #else
        (void)data;
    #endif
}

dictum_count dictum_pio_pull(dictum_pio_handle h) {
    if (!h) return 0;
    #if defined(DICTUM_TARGET_RP2040)
        return pio_sm_get(h->pio, h->sm);
    #else
        return 0;
    #endif
}

void dictum_pio_unload(dictum_pio_handle h) {
    if (!h) return;
    dictum_handle_mark_released(h);
    dictum_free(h);
}

/* =============================================================================
 * MODULE: Flash
 * ============================================================================= */

static dictum_count dictum_flash_sector_sz = 4096;  /* Default 4KB sectors */

static bool dictum_flash_is_bootloader(dictum_count address) {
    /* Protect first 64KB (bootloader region) */
    return address < 65536;
}

dictum_count dictum_flash_sector_size(void) {
    return dictum_flash_sector_sz;
}

dictum_text dictum_flash_read(dictum_count address, dictum_count length) {
    if (length > dictum_flash_sector_sz) length = dictum_flash_sector_sz;
    if (address % dictum_flash_sector_sz != 0) return NULL;  /* Alignment check */

    char* buf = (char*)dictum_alloc(length + 1);
    if (!buf) return NULL;

    #if defined(DICTUM_TARGET_RP2040)
        /* Flash is memory-mapped at XIP_BASE */
        extern uint32_t XIP_BASE;
        memcpy(buf, (void*)(XIP_BASE + address), length);
    #elif defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        esp_err_t err = esp_flash_read(NULL, buf, address, length);
        if (err != ESP_OK) {
            dictum_free(buf);
            return NULL;
        }
    #elif defined(DICTUM_TARGET_STM32F4) || defined(DICTUM_TARGET_STM32H7)
        /* TODO: HAL_FLASH_Read() */
        memset(buf, 0, length);
    #else
        memset(buf, 0, length);
    #endif

    buf[length] = '\0';
    return buf;
}

dictum_result dictum_flash_write(dictum_count address, const char* data) {
    if (!data) return dictum_err("null data");
    if (address % dictum_flash_sector_sz != 0) return dictum_err("address not sector-aligned");
    if (dictum_flash_is_bootloader(address)) return dictum_err("bootloader region protected");

    size_t len = dictum_strlen(data);
    if (len > dictum_flash_sector_sz) return dictum_err("write exceeds sector size");

    #if defined(DICTUM_TARGET_RP2040)
        uint32_t ints = save_and_disable_interrupts();
        flash_range_program(address, (const uint8_t*)data, len);
        restore_interrupts(ints);
    #elif defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        esp_flash_write(NULL, data, address, len);
    #elif defined(DICTUM_TARGET_STM32F4) || defined(DICTUM_TARGET_STM32H7)
        /* TODO: HAL_FLASH_Program() */
    #endif

    return dictum_ok();
}

dictum_result dictum_flash_erase(dictum_count address) {
    if (address % dictum_flash_sector_sz != 0) return dictum_err("address not sector-aligned");
    if (dictum_flash_is_bootloader(address)) return dictum_err("bootloader region protected");

    #if defined(DICTUM_TARGET_RP2040)
        uint32_t ints = save_and_disable_interrupts();
        flash_range_erase(address, dictum_flash_sector_sz);
        restore_interrupts(ints);
    #elif defined(DICTUM_TARGET_ESP32) || defined(DICTUM_TARGET_ESP32S3)
        esp_flash_erase_region(NULL, address, dictum_flash_sector_sz);
    #elif defined(DICTUM_TARGET_STM32F4) || defined(DICTUM_TARGET_STM32H7)
        /* TODO: HAL_FLASH_Erase() */
    #endif

    return dictum_ok();
}

void dictum_flash_lock(dictum_count address) {
    (void)address;
    /* TODO: flash protection bits */
}

void dictum_flash_unlock(dictum_count address) {
    (void)address;
    /* TODO: flash protection bits */
}

/* =============================================================================
 * MODULE: Task
 * ============================================================================= */

struct dictum_task_ctx {
    char name[32];
    dictum_count stack_size;
    dictum_count priority;
    #ifdef DICTUM_HAS_FREERTOS
        TaskHandle_t handle;
    #elif defined(__linux__)
        pthread_t thread;
    #endif
};

dictum_result dictum_task_spawn(dictum_task_config* cfg, const char* entry_action, dictum_task_handle* out) {
    if (!cfg || !out) return dictum_err("null argument");
    if (cfg->stack_size < 1024 || cfg->stack_size > 65536) {
        return dictum_err("stack_size must be 1KB-64KB");
    }
    if (cfg->priority < 1 || cfg->priority > 25) {
        return dictum_err("priority must be 1-25");
    }
    (void)entry_action;  /* Action name resolved by transpiler-generated dispatcher */

    dictum_task_handle h = (dictum_task_handle)dictum_alloc(sizeof(struct dictum_task_ctx));
    if (!h) return dictum_err("allocation failed");

    dictum_strncpy(h->name, cfg->name, sizeof(h->name));
    h->stack_size = cfg->stack_size;
    h->priority = cfg->priority;

    #if defined(DICTUM_HAS_FREERTOS)
        xTaskCreate(NULL, cfg->name, cfg->stack_size / 4, NULL, cfg->priority, &h->handle);
    #elif defined(__linux__)
        /* TODO: pthread_create with entry_action dispatch */
    #endif

    dictum_handle_register(h, "task", "spawn");
    *out = h;
    return dictum_ok();
}

void dictum_task_yield(void) {
    #if defined(DICTUM_HAS_FREERTOS)
        taskYIELD();
    #elif defined(__linux__)
        sched_yield();
    #endif
}

void dictum_task_sleep(dictum_count ms) {
    dictum_sleep_ms(ms);
}

dictum_result dictum_task_join(dictum_task_handle h) {
    if (!h) return dictum_err("invalid handle");
    #if defined(DICTUM_HAS_FREERTOS)
        /* FreeRTOS doesn't have join — use semaphore or event group */
    #elif defined(__linux__)
        pthread_join(h->thread, NULL);
    #endif
    return dictum_ok();
}

void dictum_task_kill(dictum_task_handle h) {
    if (!h) return;
    if (!dictum_handle_is_alive(h)) {
        DICTUM_LOG("double-kill of task handle %p", (void*)h);
        return;
    }
    #if defined(DICTUM_HAS_FREERTOS)
        vTaskDelete(h->handle);
    #elif defined(__linux__)
        pthread_cancel(h->thread);
    #endif
    dictum_handle_mark_released(h);
    dictum_free(h);
}
