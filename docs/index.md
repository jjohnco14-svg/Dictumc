# Dictum

**Write systems code in English. Let AI handle the C.**

Dictum is a natural-language programming language that transpiles to C/C++.
It's designed for:

- **Embedded systems** (ESP32, STM32, Raspberry Pi)
- **AI/ML inference** (ONNX Runtime, LLMs, speech recognition)
- **Robotics** (servos, motors, PID control)
- **Vibecoding** — let LLMs write correct systems code via grammar constraints

## Why Dictum?

| Raw C | Dictum |
|-------|--------|
| `int32_t* buf = malloc(100);` | `keep Buffer as handle to bytes with room for 100` |
| `if (buf == NULL) { ... }` | `if Buffer is empty then: ...` |
| `free(buf);` | `release Buffer` |
| `std::unique_ptr<Point> p;` | `keep P as unique handle to Point` |

## Quick Start

```bash
pip install dictum-lang
dictumc --example HelloWorld --compile
```

## Features

- [x] Natural language syntax
- [x] Memory safety (ownership tracking, use-after-free detection)
- [x] C and C++ backends
- [x] AI/ML stdlib (ONNX, LLM, speech, diffusion)
- [x] IoT stdlib (GPIO, I2C, WiFi, BLE, camera)
- [x] Robotics stdlib (servo, motor, encoder, PID)
- [x] Grammar-constrained LLM generation
- [x] VS Code extension with LSP
- [x] Interactive REPL
- [x] Comprehensive test suite

## Example: Robot Arm

```dictum
program RobotArm:
    keep Arm as servo handle
    call dictum_servo_init with 9 and 50 and Arm
    call dictum_servo_set_angle with Arm and 90
    call dictum_task_sleep with 1000
    call dictum_servo_detach with Arm
end program
```

[Get Started →](getting-started/quickstart.md){ .md-button .md-button--primary }
