# Dictum v5 — Stdlib Makefile
# Builds all stdlib C modules into a static library: libdictum_stdlib.a
#
# Quick start:
#   make                    # native build (Linux/macOS)
#   make PLATFORM=esp32     # cross-compile (ESP-IDF must be on PATH)
#   make test               # run native tests
#   make lib                # static library only
#
# Prerequisites (Ubuntu/Debian):
#   apt-get install -y gcc libcurl4-openssl-dev libssl-dev
#
# Platforms: native | esp32 | esp32s3 | rp2040 | stm32f4 | stm32h7 | pi5

CC      ?= gcc
AR      ?= ar
CFLAGS   = -std=c11 -Wall -Wextra -Werror -O2 -fPIC -fno-strict-aliasing -fwrapv
CFLAGS  += -I.
LDFLAGS  = -lm

PLATFORM ?= native

ifeq ($(PLATFORM),native)
    CFLAGS  += -D__linux__ -D_DEFAULT_SOURCE -DDICTUM_DEBUG
    LDFLAGS += -lpthread -lrt -lcurl -lssl -lcrypto
endif
ifeq ($(PLATFORM),esp32)
    CFLAGS  += -DESP_PLATFORM -DCONFIG_IDF_TARGET_ESP32
endif
ifeq ($(PLATFORM),esp32s3)
    CFLAGS  += -DESP_PLATFORM -DCONFIG_IDF_TARGET_ESP32S3
endif
ifeq ($(PLATFORM),rp2040)
    CC       = arm-none-eabi-gcc
    AR       = arm-none-eabi-ar
    CFLAGS  += -DPICO_BUILD -mcpu=cortex-m0plus -mthumb
    LDFLAGS  = --specs=nosys.specs -lm
endif
ifeq ($(PLATFORM),stm32f4)
    CC       = arm-none-eabi-gcc
    AR       = arm-none-eabi-ar
    CFLAGS  += -DSTM32F4xx -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
    LDFLAGS  = --specs=nosys.specs -lm
endif
ifeq ($(PLATFORM),stm32h7)
    CC       = arm-none-eabi-gcc
    AR       = arm-none-eabi-ar
    CFLAGS  += -DSTM32H7xx -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard
    LDFLAGS  = --specs=nosys.specs -lm
endif
ifeq ($(PLATFORM),pi5)
    CFLAGS  += -DDICTUM_TARGET_PI5 -DDICTUM_HAS_LLM -DDICTUM_HAS_WIFI
    LDFLAGS += -lpthread -lrt -lcurl -lssl -lcrypto
endif

# ── Sources ───────────────────────────────────────────────────────────────────
STDLIB_SRCS = \
    dictum_core.c \
    dictum_console.c \
    dictum_text.c \
    dictum_math.c \
    dictum_error.c \
    dictum_file.c \
    dictum_path.c \
    dictum_directory.c \
    dictum_json.c \
    dictum_csv.c \
    dictum_net.c \
    dictum_http.c \
    dictum_tls.c \
    dictum_thread.c \
    dictum_mutex.c \
    dictum_channel.c \
    dictum_mmap.c \
    dictum_signal.c \
    dictum_process.c \
    dictum_pipe.c \
    dictum_shm.c \
    dictum_semaphore.c \
    dictum_timer.c \
    dictum_event.c \
    dictum_device.c

STDLIB_OBJS  = $(STDLIB_SRCS:.c=.o)
LIB_TARGET   = libdictum_stdlib.a
TEST_SRCS    = test_dictum_stdlib.c test_stdlib.c
TEST_BIN     = test_stdlib

.PHONY: all lib test clean

all: lib

lib: $(LIB_TARGET)

$(LIB_TARGET): $(STDLIB_OBJS)
	$(AR) rcs $@ $^
	@echo "[dictum] Built $@"

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

test: lib
	$(CC) $(CFLAGS) test_dictum_stdlib.c -o $(TEST_BIN) -L. -ldictum_stdlib $(LDFLAGS)
	./$(TEST_BIN)

clean:
	rm -f $(STDLIB_OBJS) $(LIB_TARGET) $(TEST_BIN)
