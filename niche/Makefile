# Dictum v5 — Niche/Embedded/Robotics/EdgeAI Makefile
# Builds robotics, embedded, and edge-AI stdlib modules.
#
# Usage:
#   make                 # native
#   make PLATFORM=pi5    # Raspberry Pi 5 (LLM+WiFi)
#   make PLATFORM=rp2040 # RP2040 embedded

CC     ?= gcc
AR     ?= ar
CFLAGS  = -std=c11 -Wall -Wextra -O2 -fPIC -I. -I../stdlib
LDFLAGS = -lm

PLATFORM ?= native

ifeq ($(PLATFORM),native)
    CFLAGS  += -D__linux__ -D_DEFAULT_SOURCE -DDICTUM_DEBUG
    LDFLAGS += -lpthread
endif
ifeq ($(PLATFORM),pi5)
    CFLAGS  += -DDICTUM_TARGET_PI5 -DDICTUM_HAS_LLM -DDICTUM_HAS_WIFI
    LDFLAGS += -lpthread
endif
ifeq ($(PLATFORM),rp2040)
    CC       = arm-none-eabi-gcc
    AR       = arm-none-eabi-ar
    CFLAGS  += -DPICO_BUILD -mcpu=cortex-m0plus -mthumb
    LDFLAGS  = --specs=nosys.specs -lm
endif

NICHE_SRCS = \
    dictum_stdlib_core.c \
    dictum_stdlib_edgeai.c \
    dictum_stdlib_embedded.c \
    dictum_robotics.c

NICHE_OBJS = $(NICHE_SRCS:.c=.o)
LIB_TARGET = libdictum_niche.a

.PHONY: all lib clean

all: lib

lib: $(LIB_TARGET)

$(LIB_TARGET): $(NICHE_OBJS)
	$(AR) rcs $@ $^
	@echo "[dictum] Built $@"

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(NICHE_OBJS) $(LIB_TARGET)
