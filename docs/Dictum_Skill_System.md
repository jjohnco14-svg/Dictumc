# Dictum Programming Language — AI Skill System

> **Version**: 3.2 Phase 7 (Production-Ready)  
> **Purpose**: Enable AI systems to act as Full-Stack Systems Programmer, Embedded Engineer, AI/ML Engineer, Language Designer, and Robotics Specialist through the Dictum transpiler ecosystem.  
> **Target Users**: Vibecoders with zero C background building from simple apps to OS-level complexity.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Core Language Reference](#2-core-language-reference)
3. [Backend Targets (C / C++)](#3-backend-targets)
4. [Standard Library Integration](#4-standard-library-integration)
5. [AI/ML Module (Edge AI)](#5-aiml-module-edge-ai)
6. [Embedded/IoT Module](#6-embeddediot-module)
7. [Robotics Module](#7-robotics-module)
8. [Grammar-Constrained Generation](#8-grammar-constrained-generation)
9. [Skill: Full-Stack Systems Programmer](#9-skill-full-stack-systems-programmer)
10. [Skill: Embedded Engineer](#10-skill-embedded-engineer)
11. [Skill: AI/ML Engineer](#11-skill-aiml-engineer)
12. [Skill: Language Designer](#12-skill-language-designer)
13. [Skill: Robotics Specialist](#13-skill-robotics-specialist)
14. [Integration Patterns](#14-integration-patterns)
15. [Production Checklist](#15-production-checklist)
16. [Appendix: Complete Type Map](#16-appendix-complete-type-map)

---

## 1. Architecture Overview

### 1.1 System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     DICTUM SOURCE (.dict)                    │
│  Natural-language syntax: "keep X as whole number with 5"     │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                 ▼
            ┌──────────────┐   ┌──────────────┐
            │    LEXER     │   │   GRAMMAR    │
            │  (tokenizer) │   │  (constraint)│
            └──────────────┘   └──────────────┘
                    │                 │
                    └─────────┬───────┘
                              ▼
                    ┌──────────────┐
                    │    PARSER    │
                    │   (AST gen)  │
                    └──────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                 ▼
            ┌──────────────┐   ┌──────────────┐
            │  VALIDATOR   │   │  SUMMARIZER  │
            │(type/memory) │   │  (NL output) │
            └──────────────┘   └──────────────┘
                    │
            ┌───────┴───────┐
            ▼               ▼
    ┌────────────┐  ┌────────────┐
    │  C EMITTER │  │ C++ EMITTER│
    │  (CEmitter)│  │(CppEmitter)│
    └────────────┘  └────────────┘
            │               │
            ▼               ▼
    ┌────────────┐  ┌────────────┐
    │  .c + .h   │  │ .cpp + .hpp│
    │  (gcc)     │  │  (g++)     │
    └────────────┘  └────────────┘
```

### 1.2 Pipeline Stages

| Stage | Class | Purpose | Failure Mode |
|-------|-------|---------|--------------|
| Lex | `Lexer` | Source → Tokens | `SyntaxError` on unterminated string |
| Parse | `Parser` | Tokens → AST | `SyntaxError` on unexpected token |
| Validate | `Validator` | AST → Type/Memory Check | `ValidationError` on type mismatch |
| Emit | `CEmitter` / `CppEmitter` | AST → Target Code | N/A (always succeeds) |
| Summarize | `Summarizer` | AST → Natural Language | N/A |

### 1.3 Key Design Principles

1. **Natural Language Syntax**: `keep X as whole number with value 5` instead of `int x = 5;`
2. **Grammar-Constrained Generation**: LLM token masking via `DictumGrammar` ensures syntactically valid output
3. **Memory Safety**: Ownership tracking for handles, RAII for smart pointers
4. **Zero-Boilerplate Stdlib**: Auto-inject imports for `dictum_stdlib.h` functions
5. **Multi-Backend**: Single source compiles to C (embedded) or C++ (systems/AI)

---

## 2. Core Language Reference

### 2.1 Primitive Types

| Dictum Surface | C Backend | C++ Backend | Notes |
|---------------|-----------|-------------|-------|
| `whole number` | `int32_t` | `int32_t` | Signed 32-bit integer |
| `count` | `size_t` | `size_t` | Unsigned size type |
| `fractional number` | `double` | `double` | 64-bit float |
| `truth value` | `bool` | `bool` | Boolean |
| `byte` | `uint8_t` | `uint8_t` | Single byte |
| `text` | `char*` | `const char*` | Null-terminated string |
| `handle to bytes` | `void*` | N/A | Raw memory pointer (C only) |
| `nothing` | `void` | `void` | Void/Unit type |

### 2.2 C++-Only Types (Smart Pointers & References)

| Dictum Surface | C++ Mapping | Ownership |
|---------------|-------------|-----------|
| `unique handle to T` | `std::unique_ptr<T>` | Exclusive, auto-free |
| `shared handle to T` | `std::shared_ptr<T>` | Reference counted |
| `weak handle to T` | `std::weak_ptr<T>` | Non-owning observer |
| `raw handle to T` | `T*` | Manual `release`/`delete` |
| `const ref T` | `const T&` | Borrow (read-only) |
| `ref T` | `T&` | Borrow (mutable) |
| `move T` | `T&&` | Rvalue reference |

### 2.3 Variable Declaration

```dictum
# Basic declaration
keep X as whole number with value 5

# Uninitialized
keep Y as fractional number

# Array literal
keep Numbers as whole number with values 1 and 2 and 3 and 4

# Dynamic allocation (C: malloc, C++: new)
keep Buffer as handle to bytes with room for 100

# Smart pointer (C++ only)
keep Ptr as unique handle to Point with new Point with 1.0 and 2.0
```

### 2.4 Assignment

```dictum
# Simple assignment
put 42 into X

# Expression assignment
put the sum of X and Y into Z

# Array index assignment
put 99 into Index at 0 of Numbers

# Field assignment
put 3.14 into Radius of Circle
```

### 2.5 Control Flow

```dictum
# If-then-otherwise
if X is greater than 0 then:
    print the text "positive" and newline
otherwise:
    print the text "non-positive" and newline
end if

# While loop
while Counter is less than 10 repeat:
    put the sum of Counter and 1 into Counter
end while

# For-each
for each Item in Numbers repeat:
    print the text Item and newline
end for

# Repeat N times
repeat 5 times using I:
    print the text "Iteration " and I and newline
end repeat
```

### 2.6 Actions (Functions)

```dictum
# Basic action
action add takes A as whole number, B as whole number produces whole number:
    produce success with the sum of A and B
end action

# Template action (C++20 concepts)
action swap_values takes A as any Type, B as any Type produces nothing:
    keep Temp as Type
    put A into Temp
    put B into A
    put Temp into B
end action

# Result type inference (auto-detect from produce success)
action create_buffer takes Size as count produces result:
    keep Memory as handle to bytes with room for Size
    if Memory is empty then:
        produce failure with text "allocation failed"
    end if
    produce success with Memory
end action
```

### 2.7 Shapes (Structs/Classes)

```dictum
# Plain struct (C compatible)
shape Point holds:
    X as fractional number
    Y as fractional number
end shape

# Class with methods (C++ only)
shape Circle holds:
    Center as Point
    Radius as fractional number

    method area produces fractional number:
        produce success with the product of 3.14159 and the power of Radius and 2
    end method
end shape

# Inheritance (C++ only)
shape Animal holds:
    method speak produces text:
        produce success with "unknown"
    end method
end shape

shape Dog is a Animal holds:
    method speak produces text:
        produce success with "woof"
    end method
end shape
```

### 2.8 Error Handling (Attempt/Result)

```dictum
attempt call risky_operation with Arg giving Result:
    on success
        print the text "Got: " and Result and newline
    on failure with ErrorMsg
        print the text "Failed: " and ErrorMsg and newline
end attempt
```

### 2.9 Unsafe Blocks

```dictum
unsafe:
    keep RawPtr as * byte
    put transmute Buffer as * byte into RawPtr
    put the sum of RawPtr and 4 into RawPtr
end unsafe
```

### 2.10 FFI (Foreign Function Interface)

```dictum
# Import C function
import from C the action malloc takes count produces handle to bytes as allocate

# Import C++ container
import from C++ the container vector of whole number as number list

# Bind to existing C function
bind memcpy takes Source as handle to bytes, Dest as handle to bytes, Size as count produces handle to bytes as copy_memory
```

---

## 3. Backend Targets

### 3.1 C Backend (`--backend c`)

**Use for**: Embedded systems, kernels, bare-metal, microcontrollers, legacy integration.

**Features**:
- Manual memory management (`malloc`/`free`)
- Raw pointers with unsafe blocks
- Structs (no methods)
- No exceptions (attempt compiles to error-code pattern)

**Emitted Pattern for Attempt**:
```c
int result_ok = 0;
int32_t result = 0;
result_ok = risky_operation(arg);
if (result_ok) {
    printf("Got: %d\n", result);
} else {
    char* error_msg = "error";
    printf("Failed: %s\n", error_msg);
}
```

### 3.2 C++ Backend (`--backend cpp`)

**Use for**: Systems programming, AI/ML runtimes, game engines, desktop apps.

**Features**:
- Smart pointers (RAII)
- Classes with virtual methods
- Templates/generics via C++20 concepts
- Lambda expressions with automatic capture analysis
- Exception-based attempt (try/catch)
- `std::function` for action types

**Emitted Pattern for Attempt**:
```cpp
try {
    auto result = risky_operation(arg);
    std::printf("Got: %d\n", result);
} catch (const std::exception& e) {
    std::printf("Failed: %s\n", e.what());
}
```

### 3.3 Backend Selection Matrix

| Target | Backend | Std | Flags |
|--------|---------|-----|-------|
| ESP32-S3 | C | c11 | `-mlongcalls` |
| STM32H7 | C | c11 | `-mcpu=cortex-m7` |
| Raspberry Pi 5 | C++ | c++20 | `-O3 -march=armv8.2-a` |
| Desktop Linux | C++ | c++20 | `-O2` |
| WebAssembly | C | c11 | `-target wasm32` |
| Bare-metal ARM | C | c11 | `-mcpu=cortex-m4 -mthumb` |

---

## 4. Standard Library Integration

### 4.1 Auto-Detection System

The transpiler scans AST for stdlib function calls and auto-injects `#include` directives. No manual imports needed.

```dictum
# This source requires ZERO import declarations
program AutoDemo:
    keep Model as llm handle
    call dictum_llm_load with "model.gguf" and nothing and Model
    keep Reply as text
    call dictum_llm_chat with Model and "user" and "Hello!" giving Reply
    print the text Reply and newline
end program
```

**Auto-emitted includes**:
```c
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
/* ── Dictum stdlib ── */
#include "dictum_stdlib.h"
```

### 4.2 Type Registry

| Surface Type | C Type | Module |
|-------------|--------|--------|
| `llm handle` | `dictum_llm_handle` | edge-ai |
| `speech handle` | `dictum_speech_handle` | edge-ai |
| `diffusion handle` | `dictum_diffusion_handle` | edge-ai |
| `session handle` | `dictum_session_handle` | runtime |
| `tensor handle` | `dictum_tensor_handle` | runtime |
| `pin handle` | `dictum_pin_handle` | embedded |
| `i2c handle` | `dictum_i2c_handle` | embedded |
| `pwm handle` | `dictum_pwm_handle` | embedded |
| `wifi config` | `dictum_wifi_config` | embedded |
| `ble handle` | `dictum_ble_handle` | embedded |
| `task handle` | `dictum_task_handle` | embedded |
| `servo handle` | `dictum_servo_handle` | robotics |
| `motor handle` | `dictum_motor_handle` | robotics |
| `pid handle` | `dictum_pid_handle` | robotics |

### 4.3 Snippet Generator

Quick-start templates for each module:

```bash
# Print ready-to-use Dictum source
python dictumc.py --snippet llm
python dictumc.py --snippet robot
python dictumc.py --snippet wifi
python dictumc.py --snippet sensor
```

---

## 5. AI/ML Module (Edge AI)

### 5.1 LLM Runtime

```dictum
program LLMDemo:
    keep Cfg as llm config
    put "cpu" into Cfg.backend

    keep Model as llm handle
    attempt call dictum_llm_load with "model.gguf" and Cfg and Model
    on success
        keep Reply as text
        call dictum_llm_chat with Model and "user" and "Hello!" giving Reply
        print the text Reply and newline
        call dictum_llm_unload with Model
    on failure with Err
        print the text "Load failed: " and Err and newline
    end attempt
end program
```

**API Surface**:
| Function | Takes | Produces |
|----------|-------|----------|
| `dictum_llm_load` | text, llm config*, llm handle* | result |
| `dictum_llm_prompt` | llm handle, text | result |
| `dictum_llm_generate` | llm handle, count | text |
| `dictum_llm_chat` | llm handle, text, text | text |
| `dictum_llm_embed` | llm handle, text | result |
| `dictum_llm_kv_clear` | llm handle | nothing |
| `dictum_llm_token_count` | llm handle | count |
| `dictum_llm_unload` | llm handle | nothing |

### 5.2 Speech Recognition

```dictum
program SpeechDemo:
    keep Cfg as speech config
    put "en" into Cfg.language
    put false into Cfg.translate

    keep Stt as speech handle
    call dictum_speech_load with "whisper.bin" and Cfg and Stt

    keep Audio as handle
    keep Text as text
    call dictum_speech_transcribe with Stt and Audio giving Text
    print the text Text and newline
end program
```

### 5.3 Diffusion/Image Generation

```dictum
program DiffusionDemo:
    keep Cfg as diffusion config
    put 512 into Cfg.width
    put 512 into Cfg.height
    put 20 into Cfg.steps

    keep Model as diffusion handle
    call dictum_diffusion_load with "sd-v1-5.ggml" and Cfg and Model

    keep Img as image handle
    call dictum_diffusion_txt2img with Model and "sunset over Manila" and "" and Img
    call dictum_diffusion_save with Img and "output.png"
end program
```

### 5.4 ONNX Runtime

```dictum
program OnnxDemo:
    keep Session as session handle
    call dictum_runtime_session with "model.onnx" and "cpu" and Session

    keep Desc as tensor desc
    put 1 into Desc.dims
    put 128 into Desc.d_0
    put "float32" into Desc.kind

    keep Input as tensor handle
    call dictum_runtime_tensor with Desc and Input

    keep Output as tensor handle
    call dictum_runtime_run with Session and Input and Output

    keep Score as whole number
    call dictum_runtime_tensor_get with Output and 0 giving Score
    print the text "Score: " and Score and newline
end program
```

---

## 6. Embedded/IoT Module

### 6.1 GPIO/Pin Control

```dictum
program BlinkDemo:
    keep Cfg as pin config
    put 2 into Cfg.number
    put "output" into Cfg.mode
    put false into Cfg.initial

    keep Led as pin handle
    call dictum_pin_setup with Cfg and Led

    repeat 10 times using I:
        call dictum_pin_toggle with 2
        call dictum_task_sleep with 500
    end repeat
end program
```

### 6.2 I2C Sensor Reading

```dictum
program SensorDemo:
    keep BusCfg as i2c config
    put 21 into BusCfg.sda_pin
    put 22 into BusCfg.scl_pin
    put 400000 into BusCfg.speed
    put 118 into BusCfg.address

    keep Bus as i2c handle
    call dictum_i2c_init with BusCfg and Bus

    keep Reading as sensor reading
    call dictum_sensor_read with "temperature" and Bus giving Reading

    if Reading.valid is equal to true then:
        print the text "Temp: " and Reading.value and " " and Reading.unit and newline
    end if

    call dictum_i2c_close with Bus
end program
```

### 6.3 WiFi Connection

```dictum
program WiFiDemo:
    keep Cfg as wifi config
    put "MySSID" into Cfg.ssid
    put "MyPass" into Cfg.password
    put 10000 into Cfg.timeout_ms

    attempt call dictum_wifi_init with Cfg
    on success
        keep IP as text
        call dictum_wifi_ip_address giving IP
        print the text "Connected: " and IP and newline
    on failure with Err
        print the text "WiFi failed: " and Err and newline
    end attempt
end program
```

### 6.4 Task/Cooperative Multitasking

```dictum
program TaskDemo:
    keep Cfg as task config
    put "worker" into Cfg.name
    put 4096 into Cfg.stack_size

    keep Worker as task handle
    call dictum_task_spawn with Cfg and "worker_func" and Worker

    call dictum_task_sleep with 1000
    call dictum_task_yield
    call dictum_task_join with Worker
end program
```

### 6.5 Target Platform Macros

```bash
# Auto-inject platform-specific defines
python dictumc.py source.dict --target esp32s3
python dictumc.py source.dict --target stm32h7
python dictumc.py source.dict --target rp2040
python dictumc.py source.dict --target pi5
```

| Target | Injected Define |
|--------|----------------|
| `esp32s3` | `CONFIG_IDF_TARGET_ESP32S3` |
| `esp32` | `CONFIG_IDF_TARGET_ESP32` |
| `stm32f4` | `STM32F4xx` |
| `stm32h7` | `STM32H7xx` |
| `rp2040` | `PICO_BUILD` |
| `nrf52840` | `NRF52840_XXAA` |
| `pi5` | `__linux__` |
| `pi-zero-2w` | `__linux__ __arm__` |

---

## 7. Robotics Module

### 7.1 Servo Control

```dictum
program ServoDemo:
    keep Arm as servo handle
    call dictum_servo_init with 9 and 50 and Arm

    call dictum_servo_set_angle with Arm and 90
    call dictum_task_sleep with 1000
    call dictum_servo_set_angle with Arm and 0
    call dictum_servo_detach with Arm
end program
```

### 7.2 DC Motor + PWM

```dictum
program MotorDemo:
    keep Drive as motor handle
    call dictum_motor_init with 6 and 7 and 5 and Drive

    call dictum_motor_set_speed with Drive and 800
    call dictum_task_sleep with 2000
    call dictum_motor_stop with Drive
    call dictum_motor_free with Drive
end program
```

### 7.3 Quadrature Encoder

```dictum
program EncoderDemo:
    keep Enc as encoder handle
    call dictum_encoder_init with 10 and 11 and Enc

    repeat 100 times using I:
        keep Count as whole number
        call dictum_encoder_count with Enc giving Count
        print the text "Count: " and Count and newline
        call dictum_task_sleep with 100
    end repeat

    call dictum_encoder_free with Enc
end program
```

### 7.4 PID Controller

```dictum
program PIDDemo:
    keep Ctrl as pid handle
    call dictum_pid_init with 1.0 and 0.1 and 0.05 and Ctrl

    keep Setpoint as fractional number with value 100.0
    keep Measured as fractional number with value 90.0
    keep Dt as fractional number with value 0.01

    keep Output as fractional number
    call dictum_pid_step with Ctrl and Setpoint and Measured and Dt giving Output
    print the text "PID output: " and Output and newline

    call dictum_pid_free with Ctrl
end program
```

### 7.5 Kinematics Helpers

```dictum
program KinematicsDemo:
    keep Degrees as fractional number with value 90.0
    keep Radians as fractional number
    put call dictum_kin_deg2rad with Degrees into Radians
    print the text "90° = " and Radians and " rad" and newline

    keep Mapped as fractional number
    put call dictum_kin_map with 50.0 and 0.0 and 100.0 and 0.0 and 255.0 into Mapped
    print the text "Mapped: " and Mapped and newline
end program
```

### 7.6 Auto-Emit Robotics Header

When robotics functions are detected, the transpiler auto-generates `dictum_robotics.h`:

```bash
python dictumc.py robot.dict --robot --emit-robotics-header
```

---

## 8. Grammar-Constrained Generation

### 8.1 Purpose

Dictum's `DictumGrammar` class provides **grammar-constrained token masking** for LLMs. This ensures AI-generated code is syntactically valid Dictum at every token position.

### 8.2 Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│  LLM logits │────▶│ Grammar mask    │────▶│ Valid next  │
│  (vocab)    │     │ (Trie-based)    │     │ token IDs   │
└─────────────┘     └─────────────────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
            ┌──────────┐  ┌──────────┐
            │ Checkpoint│  │ Rollback  │
            │ (save)    │  │ (restore) │
            └──────────┘  └──────────┘
```

### 8.3 State Machine

| State | Valid Next Tokens | Transition On |
|-------|-------------------|---------------|
| `TOP_LEVEL` | `program`, `module`, `shape`, `action`, `import` | `program` → `PROGRAM_NAME` |
| `PROGRAM_NAME` | `<IDENTIFIER>` | name → `BLOCK_BODY` |
| `BLOCK_BODY` | `keep`, `put`, `if`, `while`, `for`, `repeat`, `attempt`, `action`, `shape`, `end` | `keep` → `KEEP_NAME` |
| `KEEP_NAME` | `<IDENTIFIER>`, `as` | name → `KEEP_TYPE` |
| `KEEP_TYPE` | type words, `with`, `<NEWLINE>` | `with` → `KEEP_WITH` |
| `KEEP_WITH` | `value`, `values`, `all`, `no`, `room` | `value` → `KEEP_INIT` |
| `KEEP_INIT` | expressions, `<NEWLINE>` | value → pop |
| `IF_COND` | expressions, `then` | `then` → `IF_THEN` |
| `IF_THEN` | `<NEWLINE>`, `<INDENT>` | indent → `BLOCK_BODY` |
| `EXPRESSION` | operators, literals, `then`, `into`, `with`, `end` | `is` → `COMPARISON` |
| `COMPARISON` | `equal`, `not`, `greater`, `less`, `at`, `empty` | `equal` → `to` |
| `ATTEMPT_CALL` | expressions, `giving`, `<NEWLINE>` | `giving` → `ATTEMPT_GIVING` |
| `ATTEMPT_GIVING` | `<IDENTIFIER>` | name → `ATTEMPT_SUCCESS` |
| `ATTEMPT_SUCCESS` | `<NEWLINE>`, `<INDENT>`, `on` | indent → `BLOCK_BODY` |

### 8.4 Integration with LLM

```python
# Initialize grammar for C++ mode
grammar = DictumGrammar(cpp_mode=True, strict=True)

# Build tokenizer bridge (maps BPE tokens to grammar states)
bridge = GrammarTokenizerBridge(vocab)

# During generation:
for step in range(max_tokens):
    # Get valid token IDs from grammar
    valid_ids = grammar.to_mask_dict(vocab)

    # Apply mask to LLM logits
    masked_logits = apply_mask(raw_logits, valid_ids)

    # Sample next token
    next_token = sample(masked_logits)

    # Advance grammar state
    grammar.feed_token(token_text, token_type, strict=True)

    # Speculative decoding support
    checkpoint = grammar.checkpoint()
    # ... try speculative tokens ...
    # if rejected: grammar.rollback(checkpoint)
```

### 8.5 Key Features

1. **Trie-based BPE decomposition**: O(m) prefix matching where m = token length
2. **Checkpoint/rollback**: Supports speculative decoding with state restoration
3. **Nested block tracking**: Correct DEDENT handling for nested if/repeat
4. **Expression continuation**: Smart NEWLINE detection for multi-line expressions
5. **Keyword/identifier disambiguation**: Context-aware keyword vs. identifier resolution
6. **C++ mode extensions**: States for templates, smart pointers, methods, lambdas

### 8.6 Strict Mode

```python
# Strict mode: reject any token not in valid set
grammar.feed_token("unexpected", "WORD", strict=True)  # → False (rejected)

# Non-strict: permissive for development
grammar.feed_token("unexpected", "WORD", strict=False)  # → True (accepted)
```

---

## 9. Skill: Full-Stack Systems Programmer

### 9.1 Role Definition

Designs and implements complete software stacks from kernel modules to user-facing applications using Dictum's C and C++ backends.

### 9.2 Competency Matrix

| Skill | Level | Dictum Feature |
|-------|-------|----------------|
| Memory management | Expert | `handle to bytes`, smart pointers, ownership tracking |
| System calls | Expert | `extern fn` with `@syscall` annotation |
| Process management | Advanced | `process`, `pipe`, `signal` modules |
| Threading | Advanced | `thread`, `mutex`, `event`, `timer` |
| Network programming | Advanced | `net`, `HTTP`, `TLS` modules |
| File systems | Advanced | `file`, `path`, `directory`, `mmap`, `SHM` |
| Build systems | Intermediate | `--cmake`, `--build-manifest` flags |

### 9.3 Workflow

```
1. Design system architecture (shapes for data structures)
2. Implement kernel/module layer (C backend, unsafe blocks)
3. Implement user-space services (C++ backend, classes)
4. Add network/IPC layer (stdlib net module)
5. Generate build files (--cmake --build-manifest)
6. Cross-compile for target (--target flag)
```

### 9.4 Example: System Monitor

```dictum
module System:
    shape ProcessInfo holds:
        PID as whole number
        Name as text
        CPU as fractional number
        Memory as count
    end shape

    action get_processes produces result:
        keep List as raw handle to ProcessInfo with room for 100
        # unsafe: direct kernel interface
        unsafe:
            call read_procfs with List giving Count
        end unsafe
        produce success with List
    end action
end module

program Monitor:
    keep Processes as raw handle to System.ProcessInfo
    call System.get_processes giving Processes

    for each P in Processes repeat:
        print the text P.Name and " CPU: " and P.CPU and newline
    end for
end program
```

### 9.5 Build Integration

```bash
# Generate complete build system
python dictumc.py monitor.dict --backend cpp --cpp-standard 20     --cmake --build-manifest --header --compile

# Outputs:
#   monitor.cpp       (source)
#   monitor.hpp       (header)
#   CMakeLists.txt    (build)
#   Dictum.toml       (manifest)
#   monitor           (binary)
```

---

## 10. Skill: Embedded Engineer

### 10.1 Role Definition

Develops firmware for microcontrollers and SoCs, handling GPIO, buses, sensors, wireless, and real-time constraints.

### 10.2 Competency Matrix

| Skill | Level | Dictum Feature |
|-------|-------|----------------|
| GPIO control | Expert | `pin` module, `dictum_pin_setup/read/write/toggle` |
| I2C/SPI/UART | Expert | `i2c`, `spi`, `uart` modules |
| Sensor integration | Expert | `sensor` module with auto-calibration |
| PWM/Timers | Expert | `pwm`, `timer` modules |
| WiFi/BLE | Advanced | `wifi`, `ble` modules |
| Camera/vision | Advanced | `camera` module, tensor conversion |
| Flash storage | Advanced | `flash` module |
| Power management | Advanced | `dictum_board_deep_sleep` |
| RTOS tasks | Advanced | `task` module (cooperative) |

### 10.3 Target Platforms

| Platform | Target Flag | Typical Use |
|----------|-------------|-------------|
| ESP32-S3 | `--target esp32s3` | AI inference + WiFi |
| ESP32 | `--target esp32` | General IoT |
| STM32F4 | `--target stm32f4` | Motor control |
| STM32H7 | `--target stm32h7` | High-performance embedded |
| RP2040 | `--target rp2040` | Raspberry Pi Pico |
| nRF52840 | `--target nrf52840` | BLE wearables |

### 10.4 Example: Environmental Sensor Node

```dictum
program SensorNode:
    # Initialize I2C for BME280
    keep BusCfg as i2c config
    put 21 into BusCfg.sda_pin
    put 22 into BusCfg.scl_pin
    put 400000 into BusCfg.speed
    put 118 into BusCfg.address

    keep Bus as i2c handle
    call dictum_i2c_init with BusCfg and Bus

    # Calibrate temperature sensor
    call dictum_sensor_calibrate with "temperature" and 0

    # Main loop
    repeat 1000 times using Cycle:
        keep Reading as sensor reading
        call dictum_sensor_read with "temperature" and Bus giving Reading

        if Reading.valid is equal to true then:
            print the text "Temp: " and Reading.value and "C" and newline
        end if

        call dictum_task_sleep with 5000
    end repeat

    call dictum_i2c_close with Bus
    call dictum_board_deep_sleep with 300000
end program
```

### 10.5 Power Management

```dictum
# Deep sleep for 5 minutes
call dictum_board_deep_sleep with 300000

# Check wake cause
keep Cause as text
call dictum_board_wake_cause giving Cause
```

---

## 11. Skill: AI/ML Engineer

### 11.1 Role Definition

Deploys and optimizes machine learning models on edge devices, from LLMs to computer vision pipelines.

### 11.2 Competency Matrix

| Skill | Level | Dictum Feature |
|-------|-------|----------------|
| LLM inference | Expert | `llm` module, KV cache management |
| Speech recognition | Expert | `speech` module, streaming |
| Image generation | Expert | `diffusion` module |
| ONNX runtime | Expert | `runtime` module, tensor ops |
| Model quantization | Advanced | `tensor desc` with `kind` field |
| Pipeline orchestration | Advanced | `task` module for async inference |
| Hardware acceleration | Advanced | `--target` for NPU/GPU flags |

### 11.3 Model Lifecycle

```
1. Load model (dictum_llm_load / dictum_diffusion_load)
2. Configure runtime (CPU/GPU/NPU backend)
3. Run inference (dictum_llm_generate / dictum_runtime_run)
4. Post-process outputs (tensor extraction)
5. Unload model (dictum_llm_unload)
```

### 11.4 Example: Multi-Modal Pipeline

```dictum
program MultiModal:
    # Load LLM
    keep LlmCfg as llm config
    put "gpu" into LlmCfg.backend
    keep LLM as llm handle
    call dictum_llm_load with "llama-7b.gguf" and LlmCfg and LLM

    # Load diffusion model
    keep DiffCfg as diffusion config
    put 512 into DiffCfg.width
    put 512 into DiffCfg.height
    keep Diffusion as diffusion handle
    call dictum_diffusion_load with "sd-v1-5.ggml" and DiffCfg and Diffusion

    # Generate image from LLM prompt
    keep Prompt as text
    call dictum_llm_generate with LLM and 50 giving Prompt

    keep Image as image handle
    call dictum_diffusion_txt2img with Diffusion and Prompt and "" and Image
    call dictum_diffusion_save with Image and "output.png"

    # Cleanup
    call dictum_diffusion_free with Image
    call dictum_diffusion_unload with Diffusion
    call dictum_llm_unload with LLM
end program
```

### 11.5 Tensor Operations

```dictum
# Create tensor descriptor
keep Desc as tensor desc
put 3 into Desc.dims        # 3D tensor
put 224 into Desc.d_0      # batch
put 224 into Desc.d_1      # height
put 3 into Desc.d_2        # channels
put "float32" into Desc.kind

# Allocate tensor
keep Tensor as tensor handle
call dictum_runtime_tensor with Desc and Tensor

# Set values
repeat 224 times using I:
    call dictum_runtime_tensor_set with Tensor and I and 0.5
end repeat

# Get value
keep Val as whole number
call dictum_runtime_tensor_get with Tensor and 0 giving Val
```

---

## 12. Skill: Language Designer

### 12.1 Role Definition

Extends Dictum's syntax, type system, and backends to target new languages and platforms.

### 12.2 Extension Points

| Component | File | Extension Method |
|-----------|------|------------------|
| Lexer | `Lexer` class | Add token types to `tokenize()` |
| Parser | `Parser` class | Add `parse_*` methods |
| AST | `Node` dataclasses | Add new `@dataclass` nodes |
| Validator | `Validator` class | Add `validate_*` methods |
| C Emitter | `CEmitter` class | Add `emit_node` branches |
| C++ Emitter | `CppEmitter` class | Add `emit_node` branches |
| Grammar | `DictumGrammar` class | Add `GrammarState` + transitions |
| Types | `types` dicts | Add surface→target mappings |

### 12.3 Adding a New Backend (e.g., Rust)

```python
# Step 1: Create emitter
class RustEmitter:
    def __init__(self):
        self.output = []
        self.indent = 0
        self.types = {
            "whole number": "i32",
            "count": "usize",
            "fractional number": "f64",
            "truth value": "bool",
            "text": "&str",
            "nothing": "()",
        }

    def emit_node(self, node: Node):
        if isinstance(node, VarDecl):
            self.emit_vardecl(node)
        elif isinstance(node, Action):
            self.emit_action(node)
        # ... etc

    def emit_vardecl(self, node: VarDecl):
        rust_type = self.types.get(node.type, node.type)
        if node.value:
            val = self.expr_to_rust(node.value)
            self.emit(f"let {node.name}: {rust_type} = {val};")
        else:
            self.emit(f"let {node.name}: {rust_type};")

    def emit_action(self, node: Action):
        params = ", ".join(f"{pname}: {self.types.get(ptype, ptype)}" 
                          for pname, ptype in node.params)
        ret = self.types.get(node.ret_type, node.ret_type)
        self.emit(f"fn {node.name}({params}) -> {ret} {{")
        self.indent += 1
        for stmt in node.body:
            self.emit_node(stmt)
        self.indent -= 1
        self.emit("}")

# Step 2: Register in Transpiler
def run(self, ...):
    if self.backend == 'rust':
        emitter = RustEmitter()
    # ...
```

### 12.4 Adding New Syntax

```python
# Example: Add "match" expression

# 1. AST node
@dataclass
class Match(Node):
    expr: Node = field(default_factory=lambda: Literal(0))
    arms: List[Tuple[Node, List[Node]]] = field(default_factory=list)

# 2. Parser method
def parse_match(self) -> Match:
    line = self.advance().line  # 'match'
    expr = self.parse_expression()
    self.expect_word('with')
    arms = []
    while not self.match_word('end'):
        pattern = self.parse_expression()
        self.expect_word('then')
        body = self.parse_block()
        arms.append((pattern, body))
    return Match(expr=expr, arms=arms, line=line)

# 3. Validator
def validate_match(self, node: Match, scope: Scope):
    expr_type = self.check_expression(node.expr, scope)
    for pattern, body in node.arms:
        pat_type = self.check_expression(pattern, scope)
        if pat_type != expr_type:
            self.error(f"Pattern type {pat_type} doesn't match {expr_type}")
        body_scope = Scope(parent=scope)
        for stmt in body:
            self.validate_statement(stmt, body_scope)

# 4. Emitter (C++)
def emit_match(self, node: Match):
    expr = self.expr_to_cpp(node.expr)
    self.emit(f"switch ({expr}) {{")
    for pattern, body in node.arms:
        pat = self.expr_to_cpp(pattern)
        self.emit(f"case {pat}:")
        self.indent += 1
        for stmt in body:
            self.emit_node(stmt)
        self.emit("break;")
        self.indent -= 1
    self.emit("}}")
```

### 12.5 Grammar Extension

```python
# Add MATCH state to DictumGrammar
class GrammarState(Enum):
    # ... existing states ...
    MATCH_EXPR = auto()
    MATCH_WITH = auto()
    MATCH_ARMS = auto()
    MATCH_PATTERN = auto()
    MATCH_THEN = auto()

# In _init_valid_tokens:
GrammarState.MATCH_EXPR: frozenset(EXPR_START | {'with'}),
GrammarState.MATCH_WITH: frozenset({'with'}),
GrammarState.MATCH_ARMS: frozenset(EXPR_START | {'end'}),
GrammarState.MATCH_PATTERN: frozenset({'then'}),
GrammarState.MATCH_THEN: frozenset({'<NEWLINE>', '<INDENT>'}),

# In feed_token:
if state == GrammarState.BLOCK_BODY and token_text == 'match':
    self.push(GrammarState.MATCH_EXPR)
if state == GrammarState.MATCH_EXPR and token_text == 'with':
    self.pop()
    self.push(GrammarState.MATCH_ARMS)
```

---

## 13. Skill: Robotics Specialist

### 13.1 Role Definition

Develops control systems for robotic platforms, including servo control, motor drivers, PID loops, and kinematics.

### 13.2 Competency Matrix

| Skill | Level | Dictum Feature |
|-------|-------|----------------|
| Servo control | Expert | `dictum_servo_init/set_angle/detach` |
| DC motor control | Expert | `dictum_motor_init/set_speed/stop/free` |
| Encoder feedback | Expert | `dictum_encoder_init/count/reset/free` |
| PID control | Expert | `dictum_pid_init/step/reset/free` |
| Kinematics | Advanced | `dictum_kin_deg2rad/rad2deg/map/clamp` |
| Multi-axis coordination | Advanced | Task module + timer handles |
| Safety interlocks | Advanced | Attempt blocks + assert |

### 13.3 Control Loop Pattern

```dictum
program ControlLoop:
    # Hardware init
    keep Joint1 as servo handle
    call dictum_servo_init with 9 and 50 and Joint1

    keep Enc1 as encoder handle
    call dictum_encoder_init with 10 and 11 and Enc1

    keep PID1 as pid handle
    call dictum_pid_init with 2.0 and 0.5 and 0.1 and PID1

    # Target position
    keep Target as whole number with value 90

    # Control loop: 100Hz
    repeat 1000 times using Tick:
        # Read encoder
        keep Actual as whole number
        call dictum_encoder_count with Enc1 giving Actual

        # Compute PID
        keep Error as fractional number
        put the difference of Target and Actual into Error

        keep Dt as fractional number with value 0.01
        keep Output as fractional number
        call dictum_pid_step with PID1 and Target and Actual and Dt giving Output

        # Clamp output to servo range (0-180)
        keep Clamped as fractional number
        call dictum_kin_clamp with Output and 0.0 and 180.0 giving Clamped

        # Apply to servo
        call dictum_servo_set_angle with Joint1 and Clamped

        # 10ms delay
        call dictum_task_sleep with 10
    end repeat

    # Cleanup
    call dictum_servo_detach with Joint1
    call dictum_encoder_free with Enc1
    call dictum_pid_free with PID1
end program
```

### 13.4 Multi-Axis Robot Arm

```dictum
program RobotArm:
    shape Joint holds:
        Servo as servo handle
        Encoder as encoder handle
        PID as pid handle
        Target as whole number
        Actual as whole number
    end shape

    action init_joint takes Pin as count, EncA as count, EncB as count, 
                        Kp as fractional number, Ki as fractional number, 
                        Kd as fractional number produces result:
        keep J as Joint
        call dictum_servo_init with Pin and 50 and J.Servo
        call dictum_encoder_init with EncA and EncB and J.Encoder
        call dictum_pid_init with Kp and Ki and Kd and J.PID
        produce success with J
    end action

    action update_joint takes J as ref Joint produces nothing:
        call dictum_encoder_count with J.Encoder giving J.Actual
        keep Dt as fractional number with value 0.01
        keep Output as fractional number
        call dictum_pid_step with J.PID and J.Target and J.Actual and Dt giving Output
        keep Clamped as fractional number
        call dictum_kin_clamp with Output and 0.0 and 180.0 giving Clamped
        call dictum_servo_set_angle with J.Servo and Clamped
    end action

    # Initialize 3-DOF arm
    keep Base as Joint
    call init_joint with 9 and 10 and 11 and 2.0 and 0.5 and 0.1 giving Base

    keep Shoulder as Joint
    call init_joint with 12 and 13 and 14 and 1.5 and 0.3 and 0.05 giving Shoulder

    keep Elbow as Joint
    call init_joint with 15 and 16 and 17 and 1.0 and 0.2 and 0.02 giving Elbow

    # Set targets
    put 90 into Base.Target
    put 45 into Shoulder.Target
    put 135 into Elbow.Target

    # Run synchronized control
    repeat 500 times using Step:
        call update_joint with Base
        call update_joint with Shoulder
        call update_joint with Elbow
        call dictum_task_sleep with 10
    end repeat
end program
```

---

## 14. Integration Patterns

### 14.1 AI-Assisted Coding Workflow

```
1. User describes intent in natural language
   → "Create a program that reads temperature from I2C sensor
      and prints it every 5 seconds"

2. AI generates Dictum source using grammar constraints
   → Grammar mask ensures syntactic validity at every token
   → Checkpoint/rollback enables speculative decoding

3. Transpiler validates and emits C/C++
   → Type checking catches errors before compilation
   → Memory ownership tracking prevents leaks

4. User reviews natural language summary
   → Summarizer explains what the code does in plain English

5. Compile and deploy to target
   → --target flag injects platform-specific macros
   → --compile flag builds binary automatically
```

### 14.2 Multi-File Projects

```dictum
# main.dict
use "sensor.dict"
use "network.dict"

program Main:
    keep Temp as sensor reading
    call sensor.read_temperature giving Temp
    call network.send_reading with Temp
end program

# sensor.dict
module Sensor:
    shape Reading holds:
        Value as fractional number
        Unit as text
    end shape

    action read_temperature produces result:
        # ... implementation ...
    end action
end module

# network.dict
module Network:
    action send_reading takes R as sensor.Reading produces result:
        # ... implementation ...
    end action
end module
```

### 14.3 CI/CD Integration

```yaml
# .github/workflows/dictum-ci.yml
name: Dictum CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Transpile and test
        run: |
          python dictumc.py src/*.dict --backend cpp --cpp-standard 20             --compile --test
      - name: Generate headers
        run: |
          python dictumc.py src/*.dict --backend cpp --header             --namespace MyProject
```

---

## 15. Production Checklist

### 15.1 Before Shipping

- [ ] All examples transpile with `--backend cpp --cpp-standard 20`
- [ ] C backend tests pass for embedded targets
- [ ] Grammar walk tests pass in strict mode
- [ ] No validation warnings for production code
- [ ] Memory ownership validated (no handle leaks)
- [ ] Cross-compilation tested for target platforms
- [ ] Headers generated for all exported symbols
- [ ] CMakeLists.txt generated and tested
- [ ] Documentation generated (`--stdlib-info`, `--snippet`)

### 15.2 Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Transpile time | <100ms/1KLOC | `time dictumc.py large.dict` |
| Grammar check | <1ms/token | Profile `feed_token()` |
| Emit code size | <2x source | Compare `.dict` vs `.cpp` |
| Compile time | Native C++ equivalent | `g++ -O2` benchmark |
| Runtime overhead | Zero (direct translation) | Compare hand-written C |

### 15.3 Safety Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| No null derefs | `empty` → `nullptr`/`NULL` checks |
| No use-after-free | Ownership tracking in validator |
| No double-free | `released` flag in `VarInfo` |
| Bounds checking | Array size tracking + runtime checks |
| Type safety | Full type inference and checking |
| Memory leaks | RAII for smart pointers, warnings for raw |

---

## 16. Appendix: Complete Type Map

### 16.1 Dictum → C Type Map

| Dictum | C | Header |
|--------|---|--------|
| `whole number` | `int32_t` | `<stdint.h>` |
| `count` | `size_t` | `<stddef.h>` |
| `fractional number` | `double` | Built-in |
| `truth value` | `bool` | `<stdbool.h>` |
| `byte` | `uint8_t` | `<stdint.h>` |
| `text` | `char*` | Built-in |
| `u8` | `uint8_t` | `<stdint.h>` |
| `u16` | `uint16_t` | `<stdint.h>` |
| `u32` | `uint32_t` | `<stdint.h>` |
| `i32` | `int32_t` | `<stdint.h>` |
| `i64` | `int64_t` | `<stdint.h>` |
| `u64` | `uint64_t` | `<stdint.h>` |
| `handle to bytes` | `void*` | Built-in |
| `nothing` | `void` | Built-in |
| `result` | `void*` | `dictum_stdlib.h` |
| `llm handle` | `dictum_llm_handle` | `dictum_stdlib.h` |
| `speech handle` | `dictum_speech_handle` | `dictum_stdlib.h` |
| `diffusion handle` | `dictum_diffusion_handle` | `dictum_stdlib.h` |
| `session handle` | `dictum_session_handle` | `dictum_stdlib.h` |
| `tensor handle` | `dictum_tensor_handle` | `dictum_stdlib.h` |
| `pin handle` | `dictum_pin_handle` | `dictum_stdlib.h` |
| `i2c handle` | `dictum_i2c_handle` | `dictum_stdlib.h` |
| `pwm handle` | `dictum_pwm_handle` | `dictum_stdlib.h` |
| `timer handle` | `dictum_timer_handle` | `dictum_stdlib.h` |
| `camera handle` | `dictum_camera_handle` | `dictum_stdlib.h` |
| `ble handle` | `dictum_ble_handle` | `dictum_stdlib.h` |
| `task handle` | `dictum_task_handle` | `dictum_stdlib.h` |
| `servo handle` | `dictum_servo_handle` | `dictum_robotics.h` |
| `motor handle` | `dictum_motor_handle` | `dictum_robotics.h` |
| `encoder handle` | `dictum_encoder_handle` | `dictum_robotics.h` |
| `pid handle` | `dictum_pid_handle` | `dictum_robotics.h` |

### 16.2 Dictum → C++ Type Map

| Dictum | C++ | Header |
|--------|-----|--------|
| `whole number` | `int32_t` | `<cstdint>` |
| `count` | `size_t` | `<cstddef>` |
| `fractional number` | `double` | Built-in |
| `truth value` | `bool` | Built-in |
| `text` | `const char*` | Built-in |
| `unique handle to T` | `std::unique_ptr<T>` | `<memory>` |
| `shared handle to T` | `std::shared_ptr<T>` | `<memory>` |
| `weak handle to T` | `std::weak_ptr<T>` | `<memory>` |
| `raw handle to T` | `T*` | Built-in |
| `const ref T` | `const T&` | Built-in |
| `ref T` | `T&` | Built-in |
| `move T` | `T&&` | Built-in |
| `action taking ... produces ...` | `std::function<...>` | `<functional>` |

### 16.3 Operator Mapping

| Dictum Syntax | C/C++ | Category |
|--------------|-------|----------|
| `the sum of A and B` | `A + B` | Arithmetic |
| `the difference of A and B` | `A - B` | Arithmetic |
| `the product of A and B` | `A * B` | Arithmetic |
| `the quotient of A and B` | `A / B` | Arithmetic |
| `the remainder of A by B` | `A % B` | Arithmetic |
| `A modulo B` | `A % B` | Arithmetic |
| `A times B` | `A * B` | Arithmetic |
| `A divided by B` | `A / B` | Arithmetic |
| `A is equal to B` | `A == B` | Comparison |
| `A is not equal to B` | `A != B` | Comparison |
| `A is greater than B` | `A > B` | Comparison |
| `A is less than B` | `A < B` | Comparison |
| `A is at least B` | `A >= B` | Comparison |
| `A is at most B` | `A <= B` | Comparison |
| `the bitwise and of A and B` | `A & B` | Bitwise |
| `the bitwise or of A and B` | `A \| B` | Bitwise |
| `the bitwise not of A` | `~A` | Bitwise |
| `the left shift of A by B` | `A << B` | Bitwise |
| `the right shift of A by B` | `A >> B` | Bitwise |
| `the power of A and B` | `pow(A, B)` / `std::pow(A, B)` | Math |
| `the square root of A` | `sqrt(A)` / `std::sqrt(A)` | Math |
| `the exponential of A` | `exp(A)` / `std::exp(A)` | Math |
| `the sine of A` | `sin(A)` / `std::sin(A)` | Math |
| `the cosine of A` | `cos(A)` / `std::cos(A)` | Math |
| `the tanh of A` | `tanh(A)` / `std::tanh(A)` | Math |
| `the count of A` | `sizeof(A)/sizeof(A[0])` | Array |
| `the length of A` | `strlen(A)` / `std::strlen(A)` | String |

---

## Quick Reference Card

### File Extensions
| Extension | Purpose |
|-----------|---------|
| `.dict` | Dictum source |
| `.c` / `.h` | C backend output |
| `.cpp` / `.hpp` | C++ backend output |
| `.toml` | Build manifest |

### CLI Flags
```bash
python dictumc.py source.dict [options]
  --backend {c,cpp}           Target language
  --cpp-standard {17,20,23}   C++ standard
  --target {esp32s3,stm32h7,...}  Platform macro
  --stdlib                    Enable stdlib integration
  --robot                     Enable robotics shim
  --compile                   Compile emitted code
  --header                    Generate header file
  --summary                   Show NL summary
  --no-validate               Skip validation (dangerous)
  --namespace NAME            C++ namespace
  --cmake                     Generate CMakeLists.txt
  --build-manifest            Generate Dictum.toml
  --stdlib-info [FAMILY]      Show API surface
  --snippet NAME              Print ready-to-use code
  --emit-robotics-header      Print robotics header
  --grammar-guided            Enable grammar constraints
  --test                      Run integration tests
  --test7                     Run Phase 7 tests
```

### Emergency Patterns
```dictum
# Panic: how do I print?
print the text "Hello" and newline

# Panic: how do I loop?
repeat 10 times using I:
    print the text I and newline
end repeat

# Panic: how do I allocate?
keep Buffer as handle to bytes with room for 100

# Panic: how do I handle errors?
attempt call risky with Arg giving Result:
    on success
        print the text "OK" and newline
    on failure with Err
        print the text "ERR: " and Err and newline
end attempt

# Panic: how do I import C?
import from C the action malloc takes count produces handle to bytes as allocate
```

---

*End of Dictum Skill System Documentation v3.2 Phase 7*
*Generated for AI vibecoding platform integration*
