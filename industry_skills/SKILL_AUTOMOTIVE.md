# Dictum Skill — Automotive ECU Firmware

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: AUTOSAR patterns, CAN/CAN-FD handling, ASIL defensive coding,
> diagnostic services (UDS), ECU state management, and ADAS sensor fusion in Dictum.

---

## Discovery Questions (ask before generating)

1. **ECU type** — powertrain, chassis (brake/steer), body control, infotainment, gateway, ADAS perception, BMS, domain controller?
2. **Software architecture** — AUTOSAR Classic, AUTOSAR Adaptive, non-AUTOSAR bare-metal, OSEK?
3. **Communication buses** — CAN 2.0, CAN-FD, LIN, FlexRay, Automotive Ethernet, UDS diagnostics?
4. **ADAS functions** — camera, radar/LiDAR fusion, ultrasonic, lane keeping, AEB, none?
5. **ASIL safety integrity level** — QM, ASIL A, B, C, D?
6. **Chipset / target** — Infineon AURIX, NXP S32K, Renesas RH850, STM32, TI TDA4?

---

## Core ECU Shapes

```
shape CanFrame holds:
    MessageID as u32
    DLC as u8
    Data as bytes
    Timestamp as u32
    BusID as u8
    Valid as truth value
end shape

shape EcuState holds:
    RunMode as whole number     # 0=off 1=init 2=run 3=fault 4=shutdown
    FaultCode as u32
    DtcCount as whole number
    PowerSupplyMv as whole number
    IgnitionOn as truth value
    NmState as whole number     # network management
end shape

shape SensorInput holds:
    SignalID as u16
    RawValue as whole number
    PhysicalValue as fractional number
    Status as u8                # 0=ok 1=init 2=timeout 3=error
    Timestamp as u32
end shape

shape ActuatorCommand holds:
    ActuatorID as u16
    RequestedValue as fractional number
    SafetyGated as truth value
    Source as u8                # 0=normal 1=redundant 2=default
end shape
```

---

## CAN Bus Patterns

### CAN frame receive handler

```
action handle_can_rx takes Frame as CanFrame produces nothing:
    # AUTOSAR ComStack pattern — route by message ID
    if Frame.Valid is false then:
        produce failure with text "invalid CAN frame"
    end if

    if Frame.MessageID is equal to 0x100 then:
        call process_engine_rpm with Frame
    end if
    if Frame.MessageID is equal to 0x200 then:
        call process_vehicle_speed with Frame
    end if
    if Frame.MessageID is equal to 0x300 then:
        call process_brake_pressure with Frame
    end if

    produce success with nothing
end action
```

### CAN frame transmit with timeout

```
action transmit_can_frame takes Frame as CanFrame
                            and TimeoutMs as whole number
                            produces nothing:
    use Device
    use Timer

    keep Start as whole number
    keep Elapsed as whole number
    call Timer.start with 0 giving Start

    attempt:
        call Device.write with Frame.BusID and Frame.MessageID
    on failure with Err:
        produce failure with text "CAN TX failed"
    end attempt

    call Timer.start with 0 giving Elapsed
    if the difference of Elapsed and Start is greater than TimeoutMs then:
        produce failure with text "CAN TX timeout"
    end if

    produce success with nothing
end action
```

### Signal extraction from CAN frame (big-endian, Intel byte order)

```
action extract_signal takes Frame as CanFrame
                        and StartBit as u8
                        and Length as u8
                        and Factor as fractional number
                        and Offset as fractional number
                        produces fractional number:
    keep RawSignal as u32
    keep ByteIdx as whole number
    keep Physical as fractional number

    put the quotient of StartBit by 8 into ByteIdx
    put item ByteIdx of Frame.Data into RawSignal

    # Apply DBC-style linear scaling: Physical = Raw * Factor + Offset
    put the sum of the product of RawSignal and Factor and Offset into Physical
    produce success with Physical
end action
```

---

## ASIL Defensive Coding Patterns

### ASIL B — range check + default

```
action safe_actuator_command takes Cmd as ActuatorCommand
                               and MinVal as fractional number
                               and MaxVal as fractional number
                               produces ActuatorCommand:
    keep SafeCmd as ActuatorCommand
    put Cmd.ActuatorID into SafeCmd.ActuatorID
    put Cmd.RequestedValue into SafeCmd.RequestedValue
    put false into SafeCmd.SafetyGated
    put 0 into SafeCmd.Source

    # Range gate — clamp to safe operating limits
    if Cmd.RequestedValue is less than MinVal then:
        put MinVal into SafeCmd.RequestedValue
        put true into SafeCmd.SafetyGated
        put 2 into SafeCmd.Source    # defaulted
    end if
    if Cmd.RequestedValue is greater than MaxVal then:
        put MaxVal into SafeCmd.RequestedValue
        put true into SafeCmd.SafetyGated
        put 2 into SafeCmd.Source
    end if

    produce success with SafeCmd
end action
```

### ASIL C/D — dual-channel plausibility check

```
action plausibility_check takes Primary as SensorInput
                            and Redundant as SensorInput
                            and TolerancePct as fractional number
                            produces truth value:
    keep Diff as fractional number
    keep Tolerance as fractional number
    keep AverageVal as fractional number

    put the quotient of
            the sum of Primary.PhysicalValue and Redundant.PhysicalValue
            by 2.0
        into AverageVal

    put the difference of Primary.PhysicalValue and Redundant.PhysicalValue into Diff
    if Diff is less than 0.0 then:
        put the product of Diff and -1.0 into Diff    # abs value
    end if

    put the product of AverageVal and TolerancePct into Tolerance

    if Diff is greater than Tolerance then:
        produce success with false    # signals disagree — fault
    end if

    produce success with true
end action
```

---

## UDS Diagnostic Services (ISO 14229)

```
shape UdsRequest holds:
    ServiceID as u8
    SubFunction as u8
    DataLength as whole number
    Data as bytes
    Addressed as truth value
end shape

shape UdsResponse holds:
    ResponseCode as u8
    DataLength as whole number
    Data as bytes
    Positive as truth value
end shape

action handle_uds_request takes Req as UdsRequest produces UdsResponse:
    keep Resp as UdsResponse
    put false into Resp.Positive

    # 0x10 — Diagnostic Session Control
    if Req.ServiceID is equal to 16 then:
        call uds_session_control with Req giving Resp
        produce success with Resp
    end if

    # 0x11 — ECU Reset
    if Req.ServiceID is equal to 17 then:
        call uds_ecu_reset with Req giving Resp
        produce success with Resp
    end if

    # 0x22 — Read Data By Identifier
    if Req.ServiceID is equal to 34 then:
        call uds_read_data_by_id with Req giving Resp
        produce success with Resp
    end if

    # 0x27 — Security Access
    if Req.ServiceID is equal to 39 then:
        call uds_security_access with Req giving Resp
        produce success with Resp
    end if

    # 0x19 — Read DTC Information
    if Req.ServiceID is equal to 25 then:
        call uds_read_dtc with Req giving Resp
        produce success with Resp
    end if

    # NRC 0x11 — serviceNotSupported
    put 127 into Resp.ResponseCode
    produce success with Resp
end action
```

---

## DTC (Diagnostic Trouble Code) Management

```
shape DtcEntry holds:
    Code as u32
    Status as u8                # bit-field: confirmed/pending/aged
    OccurrenceCount as u8
    FirstOccurrence as u32
    LastOccurrence as u32
end shape

action store_dtc takes Code as u32 and Timestamp as u32 produces nothing:
    use File

    keep Entry as DtcEntry
    put Code into Entry.Code
    put 9 into Entry.Status      # 0b00001001 = testFailed + confirmed
    put 1 into Entry.OccurrenceCount
    put Timestamp into Entry.FirstOccurrence
    put Timestamp into Entry.LastOccurrence

    attempt:
        call File.write with "dtc.bin" and Code
    on failure with Err:
        produce failure with text "DTC storage failed"
    end attempt

    produce success with nothing
end action
```

---

## ECU State Machine (AUTOSAR EcuM pattern)

```
program EcuMain:
    use Timer
    use Device

    keep State as EcuState
    put 0 into State.RunMode
    put 0 into State.FaultCode
    put false into State.IgnitionOn

    action ecu_init produces nothing:
        attempt:
            call Device.open with "/dev/can0" giving _
            put 1 into State.RunMode
        on failure with Err:
            put Err into State.FaultCode
            put 3 into State.RunMode
            produce failure with text "ECU init failed"
        end attempt
        produce success with nothing
    end action

    action ecu_run produces nothing:
        keep Frame as CanFrame
        attempt:
            call Device.read with 0 giving Frame.MessageID
            put true into Frame.Valid
            call handle_can_rx with Frame
        on failure with Err:
            put Err into State.FaultCode
        end attempt
        produce success with nothing
    end action

    action ecu_fault produces nothing:
        # Activate default values on all actuators
        keep DefaultCmd as ActuatorCommand
        put 0 into DefaultCmd.ActuatorID
        put 0.0 into DefaultCmd.RequestedValue
        put true into DefaultCmd.SafetyGated
        put 2 into DefaultCmd.Source

        call Device.write with 0 and 0
        print the text "ECU FAULT: " and State.FaultCode and newline
        produce success with nothing
    end action

    # Main state machine loop
    attempt:
        call ecu_init
    on failure with Err:
        put 3 into State.RunMode
    end attempt

    repeat forever:
        call Timer.sleep with 10    # 100Hz main loop

        if State.RunMode is equal to 2 then:
            call ecu_run
        end if
        if State.RunMode is equal to 3 then:
            call ecu_fault
        end if
    end repeat
end program
```

---

## Stdlib Modules for Automotive

| Module | Use case |
|---|---|
| `Device` | CAN bus read/write, GPIO (ignition line), SPI sensor |
| `Timer` | Task scheduling, CAN timeout, NVM write delay |
| `Mutex` | Protect ECU state shared between CAN RX and control tasks |
| `Thread` | CAN RX task, diagnostic task, NVM write task |
| `Channel` | Route decoded signals from CAN RX to control algorithms |
| `File` | DTC storage, NVM parameter sets, calibration data |

---

## Compile Commands

```bash
# Validate first
python dictumc_cli.py ecu.dict --validate

# AUTOSAR-compatible C (C11)
python dictumc_cli.py ecu.dict --backend c --compile -o ecu.elf

# AUTOSAR Adaptive (C++17)
python dictumc_cli.py ecu.dict --backend cpp --cpp-standard 17 --compile -o ecu
```

---

## Domain Rules

1. **ASIL A+** — every input signal must be range-checked before use in control output.
2. **ASIL C/D** — plausibility check required between redundant sensor channels.
3. **CAN receive handlers** must be deterministic — no heap allocation, no blocking calls.
4. **DTC must be stored** on every detected fault — never discard diagnostic information.
5. **Default values on fault** — all actuators must have a defined safe-state value applied on any ECU fault.
6. **UDS session security** — 0x27 security access must be validated before any write/calibration service.
7. **Timing determinism** — all main loop tasks must complete within their allocated time slot.
8. **No floating point in interrupt context** — use scaled integer for CAN signal processing in ISRs.
