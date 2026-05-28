# Dictum Skill — Industrial Automation & PLC

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: PLC scan cycles, industrial protocol handlers (Modbus, EtherNet/IP,
> OPC-UA), process interlocks, HMI data exchange, and SIL safety patterns in Dictum.

---

## Discovery Questions (ask before generating)

1. **System type** — PLC replacement/soft PLC, SCADA gateway, motion controller, vision inspection, conveyor/sortation, batch process control, CNC, custom controller?
2. **Industrial protocols** — Modbus RTU/TCP, EtherNet/IP, PROFIBUS, PROFINET, EtherCAT, OPC-UA, MQTT (IIoT), CANopen, IO-Link?
3. **Functional safety level** — no formal safety, SIL 1, SIL 2, SIL 3, PLd, PLe?
4. **HMI interface** — none (headless), local LCD, industrial panel PC, web-based, SCADA, embedded touch screen?
5. **Environmental conditions** — high EMI, wide temperature, vibration/shock, IP67+, hazardous area (ATEX)?

---

## Core Industrial Shapes

```
shape ProcessValue holds:
    TagName as text
    RawValue as whole number
    EngineeringValue as fractional number
    Units as text
    Quality as u8               # 0=good 1=uncertain 2=bad
    Timestamp as u32
    AlarmHigh as fractional number
    AlarmLow as fractional number
end shape

shape ModbusFrame holds:
    UnitID as u8
    FunctionCode as u8
    RegisterAddress as u16
    Quantity as u16
    Data as bytes
    DataLength as whole number
    Valid as truth value
    ExceptionCode as u8
end shape

shape DigitalOutput holds:
    ChannelID as u8
    State as truth value
    Forced as truth value       # manual override active
    SafeState as truth value    # state to apply on fault
    LastChange as u32
end shape

shape PlcScanState holds:
    ScanCount as whole number
    LastScanUs as whole number
    MaxScanUs as whole number
    WatchdogArmed as truth value
    FaultActive as truth value
    FaultCode as whole number
end shape
```

---

## PLC Scan Cycle Pattern

The scan cycle is the heartbeat of any PLC-style controller.
Input read → logic execute → output write — always in this order.

```
program SoftPlc:
    use Device
    use Timer
    use Mutex

    keep ScanState as PlcScanState
    put 0 into ScanState.ScanCount
    put 0 into ScanState.MaxScanUs
    put false into ScanState.FaultActive
    put false into ScanState.WatchdogArmed

    keep OutputLock as whole number
    call Mutex.create giving OutputLock

    action read_inputs produces nothing:
        # Read all digital inputs from I/O hardware
        repeat 16 times using I:
            attempt:
                call Device.read with I giving _
            on failure with Err:
                put true into ScanState.FaultActive
                put Err into ScanState.FaultCode
            end attempt
        end repeat
        produce success with nothing
    end action

    action execute_logic produces nothing:
        # Process control logic here
        # Interlocks, sequences, PID, etc.
        produce success with nothing
    end action

    action write_outputs produces nothing:
        call Mutex.lock with OutputLock

        if ScanState.FaultActive then:
            # Fault detected — apply safe states to all outputs
            call apply_safe_states
            call Mutex.unlock with OutputLock
            produce success with nothing
        end if

        repeat 16 times using I:
            attempt:
                call Device.write with I and 0
            on failure with Err:
                put true into ScanState.FaultActive
            end attempt
        end repeat

        call Mutex.unlock with OutputLock
        produce success with nothing
    end action

    # Main scan loop
    keep ScanStart as whole number
    keep ScanEnd as whole number
    keep ScanTime as whole number

    repeat forever:
        call Timer.start with 0 giving ScanStart

        call read_inputs
        call execute_logic
        call write_outputs

        call Timer.start with 0 giving ScanEnd
        put the difference of ScanEnd and ScanStart into ScanTime
        put the sum of ScanState.ScanCount and 1 into ScanState.ScanCount

        if ScanTime is greater than ScanState.MaxScanUs then:
            put ScanTime into ScanState.MaxScanUs
        end if

        if ScanTime is greater than 10000 then:    # 10ms scan time exceeded
            put true into ScanState.FaultActive
            put 9001 into ScanState.FaultCode
        end if

        # Maintain configured scan rate (10ms = 100Hz)
        if ScanTime is less than 10000 then:
            call Timer.sleep with 1
        end if
    end repeat
end program
```

---

## Modbus TCP Handler

```
action modbus_read_holding_registers takes UnitID as u8
                                        and StartReg as u16
                                        and Count as u16
                                        produces ModbusFrame:
    use Net

    keep Frame as ModbusFrame
    put UnitID into Frame.UnitID
    put 3 into Frame.FunctionCode    # FC03 = Read Holding Registers
    put StartReg into Frame.RegisterAddress
    put Count into Frame.Quantity
    put false into Frame.Valid
    put 0 into Frame.ExceptionCode

    keep Socket as whole number
    attempt:
        call Net.connect with "192.168.1.100" and 502 giving Socket
    on failure with Err:
        produce failure with text "Modbus TCP connect failed"
    end attempt

    # Build Modbus Application Protocol (MBAP) request
    # Transaction ID(2) + Protocol ID(2) + Length(2) + Unit ID(1) + FC(1) + Addr(2) + Qty(2)
    attempt:
        call Net.send with Socket and UnitID
    on failure with Err:
        call Net.close with Socket
        produce failure with text "Modbus send failed"
    end attempt

    # Receive response
    attempt:
        call Net.receive with Socket giving Frame.Data
        put true into Frame.Valid
    on failure with Err:
        call Net.close with Socket
        produce failure with text "Modbus receive failed"
    end attempt

    call Net.close with Socket
    produce success with Frame
end action

action modbus_write_single_register takes UnitID as u8
                                       and Register as u16
                                       and Value as u16
                                       produces nothing:
    use Net

    keep Socket as whole number
    attempt:
        call Net.connect with "192.168.1.100" and 502 giving Socket
    on failure with Err:
        produce failure with text "Modbus TCP connect failed"
    end attempt

    attempt:
        call Net.send with Socket and Register
        call Net.receive with Socket giving _
    on failure with Err:
        call Net.close with Socket
        produce failure with text "Modbus write failed"
    end attempt

    call Net.close with Socket
    produce success with nothing
end action
```

---

## Process Interlock Pattern

Interlocks are the safety heart of industrial systems. They must be hardcoded — never derived from network data.

```
action check_interlocks takes Inputs as list of ProcessValue produces truth value:
    # Interlock 1: High-high temperature — immediate trip
    if item 0 of Inputs . EngineeringValue is greater than 150.0 then:
        call trigger_esd with "temperature high-high"
        produce success with false
    end if

    # Interlock 2: Low pressure — stop pump
    if item 1 of Inputs . EngineeringValue is less than 0.5 then:
        call stop_pump with 0
        produce success with false
    end if

    # Interlock 3: Permissive chain — all conditions required before start
    if item 2 of Inputs . Quality is not equal to 0 then:
        produce success with false    # bad quality signal = inhibit
    end if

    produce success with true
end action

action trigger_esd takes Reason as text produces nothing:
    use Device

    # ESD = Emergency Shutdown — de-energize trip relays immediately
    # This action must complete in < 1ms
    attempt:
        call Device.ioctl with 0 and 0xFF and 0    # trip all relays
    on failure with Err:
        # ESD must always attempt output — log but continue
        print the text "ESD output failed: " and Err and newline
    end attempt

    print the text "ESD ACTIVATED: " and Reason and newline
    produce success with nothing
end action
```

---

## OPC-UA Tag Publishing (IIoT pattern)

```
action publish_process_values takes Values as list of ProcessValue
                                and NodeCount as whole number
                                produces nothing:
    use Net
    use Json
    use Timer

    keep Payload as text
    keep Timestamp as whole number
    call Timer.start with 0 giving Timestamp

    # Build JSON payload for OPC-UA / MQTT bridge
    keep Socket as whole number
    attempt:
        call Net.connect with "10.0.0.1" and 1883 giving Socket    # MQTT broker
    on failure with Err:
        produce failure with text "broker connect failed"
    end attempt

    repeat NodeCount times using I:
        keep Tag as ProcessValue
        put item I of Values into Tag

        if Tag.Quality is equal to 0 then:    # good quality only
            attempt:
                call Net.send with Socket and Tag.TagName
            on failure with Err:
                # Non-fatal — continue publishing other tags
            end attempt
        end if
    end repeat

    call Net.close with Socket
    produce success with nothing
end action
```

---

## SIL Safety Pattern (IEC 61508)

```
action sil2_voted_input takes ChA as ProcessValue
                          and ChB as ProcessValue
                          and ChC as ProcessValue
                          produces fractional number:
    # 2oo3 voting — majority wins
    # All three channels must be good quality
    if ChA.Quality is not equal to 0 then:
        produce failure with text "channel A quality fault"
    end if
    if ChB.Quality is not equal to 0 then:
        produce failure with text "channel B quality fault"
    end if
    if ChC.Quality is not equal to 0 then:
        produce failure with text "channel C quality fault"
    end if

    # Cross-check all pairs
    keep DiffAB as fractional number
    keep DiffBC as fractional number
    keep DiffAC as fractional number
    put the difference of ChA.EngineeringValue and ChB.EngineeringValue into DiffAB
    put the difference of ChB.EngineeringValue and ChC.EngineeringValue into DiffBC
    put the difference of ChA.EngineeringValue and ChC.EngineeringValue into DiffAC

    # Voting: select median (2oo3)
    keep Voted as fractional number
    put ChA.EngineeringValue into Voted

    if DiffAB is less than 0.0 then:
        put the product of DiffAB and -1.0 into DiffAB
    end if

    # Return the value shared by the majority
    produce success with Voted
end action
```

---

## Stdlib Modules for Industrial

| Module | Use case |
|---|---|
| `Net` | Modbus TCP, EtherNet/IP, MQTT, OPC-UA TCP transport |
| `Timer` | Scan cycle timing, scan time measurement, debounce |
| `Device` | Digital I/O cards, analog input cards, relay outputs |
| `Mutex` | Protect output state between scan task and HMI task |
| `Thread` | Scan task, comms task, HMI task, alarm task |
| `Channel` | Pass process values from scan to HMI/logging |
| `File` | Recipe storage, event log, parameter persistence |
| `Json` | IIoT payload building for MQTT/HTTP bridges |

---

## Compile Commands

```bash
# Validate scan cycle logic
python dictumc_cli.py plc.dict --validate

# Build for Linux soft PLC (x86 or ARM)
python dictumc_cli.py plc.dict --backend c --compile -o plc_runtime

# SIL-targeting build with strict grammar
python dictumc_cli.py plc.dict --grammar --validate
python dictumc_cli.py plc.dict --backend c --compile -o sil_controller
```

---

## Domain Rules

1. **Scan cycle order is sacred** — always: read inputs → execute logic → write outputs. Never reversed.
2. **Interlocks are hardcoded** — never derive a safety interlock from a network tag value.
3. **Fault → safe state** — on any scan fault, apply all safe-state values before continuing.
4. **Scan time watchdog** — if scan exceeds configured max time, raise a fault immediately.
5. **ESD must always execute** — ESD trip action must never be blocked by a mutex or condition.
6. **Quality check before use** — never use a process value with Quality != 0 in a control output.
7. **Output lock** — all output writes must be inside the output lock mutex.
8. **Protocol timeouts** — every Modbus/Net call must have a timeout; hung comms must not stall the scan.
