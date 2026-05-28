# Dictum Skill — Aerospace & Space Systems

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: DO-178C coding patterns, fault tolerance (DMR/TMR),
> MIL-STD-1553 / SpaceWire protocols, radiation-hardened patterns, and
> deterministic scheduling for flight and space software in Dictum.

---

## Discovery Questions (ask before generating)

1. **Vehicle type** — commercial aircraft avionics, UAV/drone, satellite (LEO/GEO), launch vehicle, spacecraft instrument, ground control?
2. **Certification standard** — DO-178C Level A/B/C/D, ECSS (ESA), MIL-STD-882, NASA NPR 7150.2, none/research?
3. **Communication interfaces** — MIL-STD-1553, SpaceWire, CAN aerospace, ARINC 429, RS-422, Ethernet (AFDX), 1PPS timing sync?
4. **Fault tolerance approach** — simplex, dual modular (DMR), triple modular (TMR), cold standby, hot standby?
5. **Environment** — radiation hardened, SEU mitigation needed, cryogenic, high vibration, vacuum (space)?

---

## Core Aerospace Shapes

```
shape FlightData holds:
    Altitude as fractional number
    Velocity as fractional number
    Heading as fractional number
    PitchRate as fractional number
    RollRate as fractional number
    YawRate as fractional number
    Timestamp as u32
    DataValid as truth value
end shape

shape Arinc429Word holds:
    Label as u8
    SDI as u8
    Data as u32
    SSM as u8                   # Sign/Status Matrix: 0=NO 1=NCD 2=FT 3=NW
    Parity as u8
    Valid as truth value
end shape

shape Mil1553Message holds:
    RTA as u8                   # Remote Terminal Address (0-30)
    TR as u8                    # 0=receive 1=transmit
    SubAddress as u8
    WordCount as u8
    Data as bytes
    StatusWord as u16
    Valid as truth value
end shape

shape FaultStatus holds:
    ChannelA as truth value
    ChannelB as truth value
    ChannelC as truth value
    VotedResult as whole number
    Disagreement as truth value
    Isolated as u8              # which channel was isolated
end shape

shape HealthPacket holds:
    SubsystemID as u8
    FaultFlags as u32
    UptimeSeconds as u32
    PowerDrawMw as whole number
    TempCelsius as fractional number
    LastErrorCode as whole number
end shape
```

---

## DO-178C Compliant Coding Patterns

### All functions must have defined return for every branch

```
action compute_nav_update takes Prev as FlightData
                             and Imu as FlightData
                             and DeltaT as fractional number
                             produces FlightData:
    keep Next as FlightData
    put false into Next.DataValid

    # Input validation — DO-178C requires all inputs validated
    if DeltaT is less than 0.0 then:
        produce failure with text "negative delta-T"
    end if
    if DeltaT is greater than 1.0 then:
        produce failure with text "delta-T exceeds maximum"
    end if
    if Imu.DataValid is false then:
        produce failure with text "IMU data invalid"
    end if

    # Dead-reckoning update
    put the sum of Prev.Altitude
            and the product of Imu.Velocity and DeltaT
        into Next.Altitude

    put Imu.Velocity into Next.Velocity
    put Imu.Heading into Next.Heading
    put Imu.Timestamp into Next.Timestamp
    put true into Next.DataValid

    produce success with Next
end action
```

---

## Fault Tolerance Patterns

### TMR (Triple Modular Redundancy) — DO-178C Level A

```
action tmr_vote takes ValA as fractional number
                  and ValB as fractional number
                  and ValC as fractional number
                  and Tolerance as fractional number
                  produces fractional number:
    keep DiffAB as fractional number
    keep DiffBC as fractional number
    keep DiffAC as fractional number

    put the difference of ValA and ValB into DiffAB
    if DiffAB is less than 0.0 then:
        put the product of DiffAB and -1.0 into DiffAB
    end if

    put the difference of ValB and ValC into DiffBC
    if DiffBC is less than 0.0 then:
        put the product of DiffBC and -1.0 into DiffBC
    end if

    put the difference of ValA and ValC into DiffAC
    if DiffAC is less than 0.0 then:
        put the product of DiffAC and -1.0 into DiffAC
    end if

    # A and B agree — C is faulty
    if DiffAB is at most Tolerance then:
        produce success with the quotient of the sum of ValA and ValB by 2.0
    end if

    # B and C agree — A is faulty
    if DiffBC is at most Tolerance then:
        produce success with the quotient of the sum of ValB and ValC by 2.0
    end if

    # A and C agree — B is faulty
    if DiffAC is at most Tolerance then:
        produce success with the quotient of the sum of ValA and ValC by 2.0
    end if

    # All three disagree — cannot determine valid value
    produce failure with text "TMR: all channels disagree"
end action
```

### DMR (Dual Modular Redundancy) with compare monitor

```
action dmr_compare takes PrimaryVal as fractional number
                     and RedundantVal as fractional number
                     and Tolerance as fractional number
                     produces FaultStatus:
    keep Status as FaultStatus
    put true into Status.ChannelA
    put true into Status.ChannelB
    put false into Status.Disagreement
    put 0 into Status.Isolated

    keep Diff as fractional number
    put the difference of PrimaryVal and RedundantVal into Diff
    if Diff is less than 0.0 then:
        put the product of Diff and -1.0 into Diff
    end if

    if Diff is greater than Tolerance then:
        put true into Status.Disagreement
        # Cannot determine which channel is correct in DMR — alert
        produce success with Status
    end if

    put PrimaryVal into Status.VotedResult
    produce success with Status
end action
```

---

## ARINC 429 Bus Handling

```
action decode_arinc429 takes Word as Arinc429Word produces fractional number:
    if Word.Valid is false then:
        produce failure with text "invalid ARINC 429 word"
    end if

    # Check SSM — only Normal Operation (3) is valid data
    if Word.SSM is not equal to 3 then:
        produce failure with text "ARINC 429 SSM indicates fault"
    end if

    # Extract BNR data (bits 11-29) — 19-bit two's complement
    keep RawData as whole number
    put the bitwise and of Word.Data and 0x7FF800 into RawData
    put the right shift of RawData by 11 into RawData

    # Apply label-specific resolution (example: label 203 = altitude, 1ft/bit)
    keep PhysicalValue as fractional number
    put RawData into PhysicalValue

    produce success with PhysicalValue
end action

action encode_arinc429 takes Label as u8
                          and Value as fractional number
                          produces Arinc429Word:
    keep Word as Arinc429Word
    put Label into Word.Label
    put 3 into Word.SSM            # Normal Operation
    put 0 into Word.SDI

    keep IntValue as whole number
    put Value into IntValue
    put the left shift of IntValue by 11 into Word.Data

    put true into Word.Valid
    produce success with Word
end action
```

---

## MIL-STD-1553 Bus Controller

```
action mil1553_bc_transmit takes RTA as u8
                              and SubAddress as u8
                              and Payload as bytes
                              and WordCount as u8
                              produces Mil1553Message:
    use Device

    keep Msg as Mil1553Message
    put RTA into Msg.RTA
    put 0 into Msg.TR            # BC→RT = receive
    put SubAddress into Msg.SubAddress
    put WordCount into Msg.WordCount
    put false into Msg.Valid

    if RTA is greater than 30 then:
        produce failure with text "invalid RTA address"
    end if

    attempt:
        call Device.ioctl with RTA and SubAddress and WordCount
        call Device.write with 0 and Payload
        call Device.read with 0 giving Msg.StatusWord
        put true into Msg.Valid
    on failure with Err:
        produce failure with text "1553 BC transmit failed"
    end attempt

    # Check status word for errors
    if the bitwise and of Msg.StatusWord and 0x8000 is not equal to 0 then:
        produce failure with text "1553 RT message error bit set"
    end if

    produce success with Msg
end action
```

---

## SEU Mitigation (Radiation Hardening)

```
# Single Event Upset scrubbing — triple-store critical variables
shape TripleStored holds:
    CopyA as whole number
    CopyB as whole number
    CopyC as whole number
end shape

action triple_write takes Value as whole number produces TripleStored:
    keep T as TripleStored
    put Value into T.CopyA
    put Value into T.CopyB
    put Value into T.CopyC
    produce success with T
end action

action triple_read takes T as TripleStored produces whole number:
    # Majority vote to detect and correct bit-flip
    if T.CopyA is equal to T.CopyB then:
        produce success with T.CopyA
    end if
    if T.CopyB is equal to T.CopyC then:
        produce success with T.CopyB
    end if
    if T.CopyA is equal to T.CopyC then:
        produce success with T.CopyA
    end if
    # All three disagree — uncorrectable SEU
    produce failure with text "SEU: uncorrectable triple-store disagreement"
end action

action scrub_triple_store takes T as ref TripleStored produces nothing:
    keep Voted as whole number
    attempt:
        call triple_read with T giving Voted
        # Restore all copies to voted value
        put Voted into T.CopyA
        put Voted into T.CopyB
        put Voted into T.CopyC
    on failure with Err:
        # Log SEU event
        print the text "UNCORRECTABLE SEU DETECTED" and newline
    end attempt
    produce success with nothing
end action
```

---

## Health and Status Telemetry

```
action build_health_packet takes SubsysID as u8 produces HealthPacket:
    use Device
    use Timer

    keep H as HealthPacket
    put SubsysID into H.SubsystemID
    put 0 into H.FaultFlags
    put 0 into H.LastErrorCode

    call Timer.start with 0 giving H.UptimeSeconds

    # Read power telemetry
    attempt:
        call Device.read with 10 giving H.PowerDrawMw
    on failure with Err:
        put the bitwise or of H.FaultFlags and 1 into H.FaultFlags
        put Err into H.LastErrorCode
    end attempt

    # Read temperature
    attempt:
        call Device.read with 11 giving H.TempCelsius
    on failure with Err:
        put the bitwise or of H.FaultFlags and 2 into H.FaultFlags
    end attempt

    produce success with H
end action
```

---

## Stdlib Modules for Aerospace

| Module | Use case |
|---|---|
| `Device` | MIL-1553 BC/RT, ARINC 429 transceiver, SpaceWire link, UART RS-422 |
| `Timer` | Mission time, frame timing, 1PPS sync, watchdog |
| `Mutex` | Protect flight data shared between guidance and telemetry tasks |
| `Thread` | Guidance, navigation, telemetry, health monitor tasks |
| `SharedMemory` | Inter-partition data sharing in ARINC 653 / RTCA partitioned OS |
| `Math` | Navigation computations, coordinate transforms, filter math |
| `Channel` | Pass navigation updates from sensor task to guidance task |

---

## Compile Commands

```bash
# Validate — required before any aerospace code submission
python dictumc_cli.py flight.dict --validate

# DO-178C bare-metal C (cross-compile for target)
python dictumc_cli.py flight.dict --backend c --compile -o flight.elf

# Strict grammar mode
python dictumc_cli.py flight.dict --grammar --validate
```

---

## Domain Rules

1. **Every branch has a return** — DO-178C requires no path through a function that does not produce a value.
2. **All inputs validated** — range-check every parameter at the top of every action, before any computation.
3. **TMR for Level A** — any function used in flight-critical path must use TMR voting.
4. **No dynamic allocation** — `keep ... with room for N` only. No `new`, no heap.
5. **SEU scrubbing** — all long-lived critical variables in space applications must use `TripleStored` pattern.
6. **Deterministic timing** — all tasks must complete within their allocated WCET budget.
7. **1553 status check** — always inspect the Status Word after every BC→RT transfer.
8. **ARINC SSM** — only process words where SSM=3 (Normal Operation); all others are faults.
9. **Health telemetry on every fault** — every `on failure` path must set a bit in the health fault flags.
