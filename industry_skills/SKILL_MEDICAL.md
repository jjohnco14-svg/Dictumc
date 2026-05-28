# Dictum Skill — Medical Device Firmware

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: IEC 62304 patterns, sensor validation, alarm management,
> watchdog integration, fail-safe state machines, and audit logging in Dictum.

---

## Discovery Questions (ask before generating)

1. **Device class** — Class I (low risk), Class II (moderate), Class III (high risk), IVD, SaMD?
2. **Platform** — ARM Cortex-M bare-metal, RTOS on MCU, Linux SBC, FPGA, PC-based?
3. **Standards** — IEC 62304, ISO 14971, IEC 60601, FDA 510(k), MISRA C, ISO 13485?
4. **Sensor types** — ECG/biopotential, SpO2, pressure (invasive/non-invasive), temperature, IMU, imaging, lab analyte?
5. **Safety requirements** — watchdog mandatory, redundant ADC paths, cryptographic audit log, alarm escalation, fail-safe outputs?
6. **Connectivity** — USB, BLE, Wi-Fi, Ethernet, RS-232 serial, none?

---

## Core Safety Shapes

```
shape VitalReading holds:
    RawADC as whole number
    Calibrated as fractional number
    Timestamp as whole number
    ChannelID as whole number
    Valid as truth value
    ErrorCode as whole number
end shape

shape AlarmState holds:
    Active as truth value
    Level as whole number       # 1=advisory 2=caution 3=warning 4=crisis
    Source as text
    Acknowledged as truth value
    OnsetTime as whole number
end shape

shape AuditEntry holds:
    EventCode as whole number
    Timestamp as whole number
    Value as fractional number
    UserID as whole number
    Checksum as whole number
end shape

shape DeviceState holds:
    Operational as truth value
    FaultCode as whole number
    BatteryLevel as fractional number
    CalibrationValid as truth value
    WatchdogArmed as truth value
end shape
```

---

## Sensor Read Pattern (IEC 62304 compliant)

Every sensor read must validate range, check consistency, and produce a failure on any anomaly.

```
action read_sensor takes ChannelID as whole number produces VitalReading:
    use Device
    use Timer

    keep R as VitalReading
    put ChannelID into R.ChannelID
    put false into R.Valid
    put 0 into R.ErrorCode
    call Timer.start with 0 giving R.Timestamp

    # Primary read
    attempt:
        call Device.read with ChannelID giving R.RawADC
    on failure with Err:
        put Err into R.ErrorCode
        produce failure with text "primary sensor read failed"
    end attempt

    # Range validation — reject physically impossible values
    if R.RawADC is less than 0 then:
        put -1 into R.ErrorCode
        produce failure with text "ADC underrange"
    end if
    if R.RawADC is greater than 65535 then:
        put -2 into R.ErrorCode
        produce failure with text "ADC overrange"
    end if

    # Calibration scaling (example: 16-bit ADC, 3.3V ref, gain=10)
    put the quotient of the product of R.RawADC and 3.3 by 65535.0 into R.Calibrated

    put true into R.Valid
    produce success with R
end action
```

### Redundant dual-channel sensor validation

```
action read_sensor_redundant takes ChA as whole number
                               and ChB as whole number
                               produces VitalReading:
    keep ReadingA as VitalReading
    keep ReadingB as VitalReading
    keep Diff as fractional number

    attempt:
        call read_sensor with ChA giving ReadingA
    on failure with Err:
        produce failure with text "primary channel failed"
    end attempt

    attempt:
        call read_sensor with ChB giving ReadingB
    on failure with Err:
        produce failure with text "redundant channel failed"
    end attempt

    # Cross-check — channels must agree within tolerance
    put the difference of ReadingA.Calibrated and ReadingB.Calibrated into Diff
    if Diff is less than -0.1 then:
        produce failure with text "sensor disagreement"
    end if
    if Diff is greater than 0.1 then:
        produce failure with text "sensor disagreement"
    end if

    produce success with ReadingA
end action
```

---

## Alarm Management (IEC 60601-1-8 pattern)

```
action raise_alarm takes Level as whole number and Source as text produces nothing:
    use Timer

    keep A as AlarmState
    put true into A.Active
    put Level into A.Level
    put Source into A.Source
    put false into A.Acknowledged
    call Timer.start with 0 giving A.OnsetTime

    # Crisis level — immediate output
    if Level is equal to 4 then:
        call activate_crisis_output with A.Source
    end if

    print the text "ALARM L" and Level and ": " and Source and newline
    produce success with nothing
end action

action check_vital_limits takes R as VitalReading
                            and LowLimit as fractional number
                            and HighLimit as fractional number
                            produces whole number:
    if R.Valid is false then:
        call raise_alarm with 3 and "sensor invalid"
        produce success with 3
    end if
    if R.Calibrated is less than LowLimit then:
        call raise_alarm with 3 and "value below low limit"
        produce success with 3
    end if
    if R.Calibrated is greater than HighLimit then:
        call raise_alarm with 3 and "value above high limit"
        produce success with 3
    end if
    produce success with 0
end action
```

---

## Watchdog Pattern (mandatory for Class II+)

```
action arm_watchdog produces nothing:
    use Timer
    use Device

    # Hardware watchdog — must be refreshed within timeout window
    attempt:
        call Device.ioctl with 0 and 1 and 5000   # arm, 5s timeout
    on failure with Err:
        produce failure with text "watchdog arm failed"
    end attempt

    produce success with nothing
end action

action refresh_watchdog produces nothing:
    use Device

    attempt:
        call Device.ioctl with 0 and 2 and 0      # kick watchdog
    on failure with Err:
        # If watchdog refresh fails the device will reset — this is correct behavior
        print the text "watchdog refresh failed" and newline
        produce failure with text "watchdog refresh failed"
    end attempt

    produce success with nothing
end action
```

---

## Audit Log Pattern (21 CFR Part 11 / IEC 62304)

```
action write_audit_entry takes EventCode as whole number
                           and Value as fractional number
                           and UserID as whole number
                           produces nothing:
    use File
    use Timer
    use Math

    keep E as AuditEntry
    put EventCode into E.EventCode
    put Value into E.Value
    put UserID into E.UserID
    call Timer.start with 0 giving E.Timestamp

    # Simple checksum — sum of fields modulo 65536
    keep Sum as whole number
    put the sum of EventCode and UserID into Sum
    put the remainder of Sum by 65536 into E.Checksum

    # Append to tamper-evident log file
    attempt:
        call File.write with "audit.log" and EventCode
    on failure with Err:
        # Audit log failure is a system fault — escalate
        call raise_alarm with 4 and "audit log failure"
        produce failure with text "audit write failed"
    end attempt

    produce success with nothing
end action
```

---

## Fail-Safe State Machine

```
possibilities DeviceMode:
    Initializing
    SelfTest
    Operational
    Fault
    Shutdown
end possibilities

action run_state_machine produces nothing:
    use Timer

    keep Mode as whole number with value 0   # 0=Init, 1=SelfTest, 2=Op, 3=Fault, 4=Shutdown
    keep FaultCode as whole number with value 0

    repeat forever:
        if Mode is equal to 0 then:
            # Initializing
            attempt:
                call arm_watchdog
                put 1 into Mode
            on failure with Err:
                put Err into FaultCode
                put 3 into Mode
            end attempt
        end if

        if Mode is equal to 1 then:
            # Self-test
            attempt:
                call run_self_test
                put 2 into Mode
            on failure with Err:
                put Err into FaultCode
                put 3 into Mode
            end attempt
        end if

        if Mode is equal to 2 then:
            # Operational — normal monitoring loop
            attempt:
                call refresh_watchdog
            on failure with Err:
                put Err into FaultCode
                put 3 into Mode
            end attempt
        end if

        if Mode is equal to 3 then:
            # Fault — safe state, alert user, stop therapy outputs
            call raise_alarm with 4 and "device fault"
            call disable_therapy_outputs
            call Timer.sleep with 1000
        end if

        call Timer.sleep with 10    # 100Hz state machine
    end repeat
end action
```

---

## Self-Test Pattern (IEC 62304 §5.5.3)

```
action run_self_test produces nothing:
    keep TestReading as VitalReading
    keep RomChecksum as whole number

    # RAM test — write/read pattern
    keep TestBuf as bytes with room for 256
    put 0xAA into item 0 of TestBuf
    if item 0 of TestBuf is not equal to 170 then:
        produce failure with text "RAM test failed"
    end if

    # Sensor baseline check
    attempt:
        call read_sensor with 0 giving TestReading
    on failure with Err:
        produce failure with text "sensor self-test failed"
    end attempt

    if TestReading.Valid is false then:
        produce failure with text "sensor returned invalid on self-test"
    end if

    produce success with nothing
end action
```

---

## Stdlib Modules for Medical Devices

| Module | Use case |
|---|---|
| `Device` | ADC reads, GPIO control, hardware watchdog ioctl |
| `Timer` | Timestamps for audit log, alarm onset, watchdog refresh |
| `File` | Audit log, configuration storage, calibration data |
| `Math` | Calibration scaling, signal filtering, trend analysis |
| `Mutex` | Protect vital sign state between monitoring and alarm threads |
| `Thread` | Separate monitoring, alarm, and comms threads |
| `Channel` | Pass readings between acquisition and processing threads |

---

## Compile Commands

```bash
# Validate (always first for medical code)
python dictumc_cli.py device.dict --validate

# MISRA-compatible C
python dictumc_cli.py device.dict --backend c --compile -o firmware

# With stdlib
python dictumc_cli.py device.dict --stdlib --backend c --compile -o firmware
```

---

## Domain Rules

1. **Every sensor read** must validate range — never pass a raw ADC value to an alarm check.
2. **Every action that can fail** must use `attempt` — no silent failures in medical firmware.
3. **Watchdog must be refreshed in the main loop** — if the loop stalls, the device must reset.
4. **Audit log failures** are a crisis alarm — the regulatory trail must be intact.
5. **Fail-safe default** — on any unhandled fault, disable therapy outputs and alert the user.
6. **No dynamic allocation** in safety-critical paths — use `keep ... with room for N` for all buffers.
7. **Alarm level 4 (crisis)** — must activate an output immediately, never queue or defer.
8. **Self-test on every boot** — validate RAM, sensors, and communication before entering operational mode.
9. **Class III devices** — all therapy-delivery actions require dual confirmation before execution.
