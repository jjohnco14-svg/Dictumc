# Dictum Skill — Embedded Systems & MCU Firmware

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: MCU peripheral drivers, RTOS task patterns, ISR-safe
> communication, power management, OTA updates, and bootloader patterns in Dictum.

---

## Discovery Questions (ask before generating)

1. **MCU family** — STM32, NXP i.MX RT, Nordic nRF5x, ESP32, PIC, AVR, RISC-V, TI MSP430?
2. **RTOS or execution model** — bare-metal superloop, FreeRTOS, Zephyr, ThreadX, RIOT, custom?
3. **Peripherals** — UART, SPI, I2C, ADC, PWM, USB device, CAN, Ethernet, external flash, display?
4. **Memory constraints** — very tight (<32KB RAM), tight (32–128KB), moderate (128KB–1MB), relaxed?
5. **Special constraints** — battery powered (low power), real-time hard deadlines, OTA updates, secure boot, MISRA C?
6. **What does the system actually do?** (sensor node, motor controller, data logger, gateway, etc.)

---

## Core Embedded Shapes

```
shape PeripheralHandle holds:
    DeviceID as whole number
    Initialized as truth value
    ErrorCount as whole number
    LastError as whole number
end shape

shape SpiTransfer holds:
    TxBuffer as bytes
    RxBuffer as bytes
    Length as whole number
    ChipSelect as u8
    Complete as truth value
end shape

shape I2cMessage holds:
    Address as u8
    Register as u8
    Data as bytes
    Length as whole number
    Direction as u8             # 0=write 1=read
    Ack as truth value
end shape

shape AdcReading holds:
    Channel as u8
    RawCounts as u16
    Voltage as fractional number
    Oversampled as truth value
end shape

shape UartFrame holds:
    Data as bytes
    Length as whole number
    Parity as u8
    Overflow as truth value
end shape

shape PowerState holds:
    VccMv as whole number
    BatteryPct as u8
    ChargingActive as truth value
    LowBatteryAlarm as truth value
    SleepAllowed as truth value
end shape
```

---

## Peripheral Init Patterns

### Generic peripheral init with retry

```
action init_peripheral takes DevID as whole number
                         and MaxRetries as whole number
                         produces PeripheralHandle:
    use Device

    keep Handle as PeripheralHandle
    put DevID into Handle.DeviceID
    put false into Handle.Initialized
    put 0 into Handle.ErrorCount
    put 0 into Handle.LastError

    keep Tries as whole number with value 0

    while Tries is less than MaxRetries repeat:
        attempt:
            call Device.open with DevID giving _
            put true into Handle.Initialized
            produce success with Handle
        on failure with Err:
            put Err into Handle.LastError
            put the sum of Handle.ErrorCount and 1 into Handle.ErrorCount
            put the sum of Tries and 1 into Tries
        end attempt
    end while

    produce failure with text "peripheral init failed after retries"
end action
```

### SPI driver pattern

```
action spi_transfer takes Xfer as SpiTransfer produces SpiTransfer:
    use Device

    keep Result as SpiTransfer
    put Xfer.Length into Result.Length
    put false into Result.Complete

    # Assert chip select
    attempt:
        call Device.ioctl with Xfer.ChipSelect and 0 and 0    # CS low
    on failure with Err:
        produce failure with text "SPI CS assert failed"
    end attempt

    # Transfer
    attempt:
        call Device.write with 0 and Xfer.TxBuffer
        call Device.read with 0 giving Result.RxBuffer
        put true into Result.Complete
    on failure with Err:
        call Device.ioctl with Xfer.ChipSelect and 1 and 0    # CS high always
        produce failure with text "SPI transfer failed"
    end attempt

    # Deassert chip select
    attempt:
        call Device.ioctl with Xfer.ChipSelect and 1 and 0    # CS high
    on failure with Err:
        produce failure with text "SPI CS deassert failed"
    end attempt

    produce success with Result
end action
```

### I2C read/write pattern

```
action i2c_write_register takes Addr as u8
                             and Reg as u8
                             and Value as u8
                             produces nothing:
    use Device

    keep Msg as I2cMessage
    put Addr into Msg.Address
    put Reg into Msg.Register
    put Value into item 0 of Msg.Data
    put 1 into Msg.Length
    put 0 into Msg.Direction

    attempt:
        call Device.ioctl with Addr and Reg and Value
    on failure with Err:
        produce failure with text "I2C write failed"
    end attempt

    produce success with nothing
end action

action i2c_read_register takes Addr as u8 and Reg as u8 produces u8:
    use Device

    keep Value as whole number

    attempt:
        call Device.ioctl with Addr and Reg and -1
        call Device.read with Addr giving Value
    on failure with Err:
        produce failure with text "I2C read failed"
    end attempt

    produce success with Value
end action
```

---

## ADC Oversampling Pattern

```
action adc_read_oversampled takes Channel as u8
                               and Samples as whole number
                               produces AdcReading:
    use Device

    keep R as AdcReading
    put Channel into R.Channel
    put false into R.Oversampled
    put 0 into R.RawCounts

    keep Accumulator as whole number with value 0
    keep SingleRead as whole number

    repeat Samples times using I:
        attempt:
            call Device.read with Channel giving SingleRead
            put the sum of Accumulator and SingleRead into Accumulator
        on failure with Err:
            produce failure with text "ADC read failed"
        end attempt
    end repeat

    put the quotient of Accumulator by Samples into R.RawCounts
    put the quotient of the product of R.RawCounts and 3300 by 65535 into R.Voltage
    put true into R.Oversampled

    produce success with R
end action
```

---

## RTOS Task Patterns

### FreeRTOS-style task (thread per peripheral)

```
program FirmwareMain:
    use Thread
    use Mutex
    use Channel
    use Timer

    keep SensorLock as whole number
    keep DataChannel as whole number
    call Mutex.create giving SensorLock
    call Channel.create with 32 giving DataChannel

    action sensor_task produces nothing:
        keep Reading as AdcReading

        repeat forever:
            call Timer.sleep with 10        # 100Hz

            call Mutex.lock with SensorLock
            attempt:
                call adc_read_oversampled with 0 and 16 giving Reading
                call Channel.send with DataChannel and Reading.RawCounts
            on failure with Err:
                print the text "sensor error: " and Err and newline
            end attempt
            call Mutex.unlock with SensorLock
        end repeat
    end action

    action processing_task produces nothing:
        keep Value as text

        repeat forever:
            attempt:
                call Channel.receive with DataChannel giving Value
                print the text "data: " and Value and newline
            on failure with Err:
                call Timer.sleep with 1
            end attempt
        end repeat
    end action

    call Thread.start with sensor_task giving _
    call Thread.start with processing_task giving _

    repeat forever:
        call Timer.sleep with 1000
    end repeat
end program
```

---

## ISR-Safe Communication Pattern

Dictum's `Channel` compiles to a lock-free ring buffer — safe for ISR-to-task communication.

```
action isr_safe_uart_receive produces nothing:
    use Channel

    keep UartChannel as whole number
    call Channel.create with 256 giving UartChannel

    # ISR side — called from interrupt context (mapped via import)
    action uart_rx_isr produces nothing:
        keep Byte as whole number
        # read from UART data register via Device
        attempt:
            call Device.read with 1 giving Byte
            call Channel.send with UartChannel and Byte
        on failure with Err:
            # ISR must never block — discard on channel full
        end attempt
        produce success with nothing
    end action

    # Task side — processes bytes from the channel
    action uart_process_task produces nothing:
        keep Frame as UartFrame
        keep Byte as text

        repeat forever:
            attempt:
                call Channel.receive with UartChannel giving Byte
                # accumulate into frame here
            on failure with Err:
                call Timer.sleep with 1
            end attempt
        end repeat
    end action
end action
```

---

## Power Management Patterns

```
action check_power_state produces PowerState:
    use Device

    keep P as PowerState
    put false into P.LowBatteryAlarm
    put false into P.SleepAllowed

    attempt:
        call Device.read with 5 giving P.VccMv    # ADC channel 5 = battery
    on failure with Err:
        produce failure with text "battery read failed"
    end attempt

    # Map voltage to percentage (Li-ion: 3000mV=0%, 4200mV=100%)
    if P.VccMv is less than 3000 then:
        put 0 into P.BatteryPct
        put true into P.LowBatteryAlarm
    end if
    if P.VccMv is greater than 4200 then:
        put 100 into P.BatteryPct
    end if

    if P.LowBatteryAlarm is false then:
        put true into P.SleepAllowed
    end if

    produce success with P
end action

action enter_low_power_sleep takes DurationMs as whole number produces nothing:
    use Device
    use Timer

    # Disable non-essential peripherals
    attempt:
        call Device.ioctl with 99 and 0 and 0    # peripheral powerdown command
    on failure with Err:
        # Non-fatal — attempt sleep anyway
    end attempt

    call Timer.sleep with DurationMs

    # Re-enable peripherals after wake
    attempt:
        call Device.ioctl with 99 and 1 and 0
    on failure with Err:
        produce failure with text "peripheral wake failed"
    end attempt

    produce success with nothing
end action
```

---

## OTA Update Pattern (bare-metal)

```
shape OtaSlot holds:
    Address as u32
    Size as u32
    Crc32 as u32
    Valid as truth value
    Active as truth value
end shape

action validate_ota_slot takes Slot as OtaSlot produces truth value:
    use Device

    keep ComputedCrc as u32
    keep ChunkSize as whole number with value 256
    keep BytesRead as whole number with value 0

    # Read slot and compute CRC32 — compare against stored CRC
    while BytesRead is less than Slot.Size repeat:
        attempt:
            call Device.read with Slot.Address giving ComputedCrc
        on failure with Err:
            produce success with false
        end attempt
        put the sum of BytesRead and ChunkSize into BytesRead
    end while

    if ComputedCrc is equal to Slot.Crc32 then:
        produce success with true
    end if

    produce success with false
end action

action commit_ota_update takes NewSlot as OtaSlot produces nothing:
    keep Valid as truth value
    call validate_ota_slot with NewSlot giving Valid

    if Valid is false then:
        produce failure with text "OTA CRC validation failed — not committing"
    end if

    # Set boot flag to new slot — actual jump handled by bootloader
    attempt:
        call Device.ioctl with 0 and 0xBEEF and NewSlot.Address
    on failure with Err:
        produce failure with text "OTA commit failed"
    end attempt

    produce success with nothing
end action
```

---

## Stdlib Modules for Embedded

| Module | Use case |
|---|---|
| `Device` | GPIO, SPI, I2C, ADC, PWM, UART register access |
| `Timer` | Loop rate control, debounce, timeout, sleep/wake |
| `Mutex` | Protect shared peripheral state |
| `Thread` | Per-peripheral tasks (sensor, comms, watchdog) |
| `Channel` | ISR-to-task safe byte/message passing |
| `Semaphore` | Event signaling from ISR to task |
| `SharedMemory` | Shared data between bootloader and application |

---

## Compile Commands

```bash
# Validate
python dictumc_cli.py firmware.dict --validate

# Bare-metal C (arm-none-eabi-gcc compatible)
python dictumc_cli.py firmware.dict --backend c --compile -o firmware.elf

# MISRA-compatible (use --grammar for strict mode)
python dictumc_cli.py firmware.dict --grammar --validate
python dictumc_cli.py firmware.dict --backend c --compile -o firmware.elf
```

---

## Domain Rules

1. **No malloc in production code** — use `keep ... with room for N` for all buffers.
2. **ISR handlers must be minimal** — read hardware register, push to Channel, return.
3. **Every peripheral init must retry** — hardware is not always ready at first call.
4. **Watchdog** — refresh in every main loop iteration; if it stops, the system resets.
5. **Power check before sleep** — never enter deep sleep with active transfers in flight.
6. **OTA validation** — always verify CRC32 before committing; never boot unvalidated firmware.
7. **Channel for ISR/task boundary** — never share raw buffers between ISR and task without a Channel or Semaphore.
8. **Chip select timing** — always deassert CS in the `on failure` path of SPI transfers.
