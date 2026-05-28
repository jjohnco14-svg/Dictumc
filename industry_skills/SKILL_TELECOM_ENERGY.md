# Dictum Skill — Telecom & 5G Protocol Software

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: 5G NR PHY/MAC layer patterns, zero-copy packet handling,
> DPDK-style ring buffers, timing synchronization, and O-RAN split interfaces in Dictum.

---

## Discovery Questions (ask before generating)

1. **Protocol layer** — PHY, MAC/RLC/PDCP, RRC/NAS, core network function, O-RAN DU/CU, baseband, transport?
2. **Standard** — 3GPP 5G NR, 4G LTE, Wi-Fi 802.11ax, private LTE/5G, LoRaWAN, NB-IoT, satellite?
3. **Signal processing hardware** — x86 server (DPDK), ARM server, FPGA (Xilinx/Intel), DSP (TI/ADI), GPU (CUDA), USRP/SDR?
4. **Timing requirements** — IEEE 1588 PTP, GPS disciplined, SyncE, <1µs accuracy, <100ns accuracy?
5. **Deployment** — virtualized (VNF/CNF), bare-metal, embedded small cell, O-RAN, cloud-native?

---

## Core Telecom Shapes

```
shape PacketBuffer holds:
    Data as bytes
    Length as whole number
    PhysOffset as u32           # physical memory offset for zero-copy
    RadioBearerID as u8
    QosClass as u8
    Timestamp as u32
    Sequence as u32
    Valid as truth value
end shape

shape RadioFrame holds:
    FrameNumber as u32
    SubframeIndex as u8
    SlotIndex as u8
    SymbolIndex as u8
    CenterFreqHz as u32
    BandwidthHz as u32
    Modulation as u8            # 0=BPSK 1=QPSK 2=16QAM 3=64QAM 4=256QAM
    Valid as truth value
end shape

shape HarqProcess holds:
    ProcessID as u8
    RoundVoyageCount as u8
    CodeRate as fractional number
    RedundancyVersion as u8
    NackReceived as truth value
    BufferIndex as whole number
end shape

shape TimingInfo holds:
    SfnSf as u32                # System Frame Number + Subframe
    TimestampNs as u32
    PtpOffset as whole number   # PTP offset in nanoseconds
    Locked as truth value
    HoldoverActive as truth value
end shape

shape OranSplit7 holds:
    MsgType as u8               # C-plane or U-plane
    SeqID as u16
    SectionID as u16
    PRBCount as u8
    SymbolID as u8
    IQData as bytes
    IQLength as whole number
end shape
```

---

## Zero-Copy Packet Pipeline

```
action enqueue_packet takes Pkt as PacketBuffer
                         and RingHandle as whole number
                         produces nothing:
    use Channel

    if Pkt.Valid is false then:
        produce failure with text "invalid packet"
    end if

    attempt:
        call Channel.send with RingHandle and Pkt.Sequence
    on failure with Err:
        # Ring full — apply backpressure, never drop silently in production
        produce failure with text "packet ring full — backpressure"
    end attempt

    produce success with nothing
end action

action dequeue_packet takes RingHandle as whole number produces PacketBuffer:
    use Channel

    keep Pkt as PacketBuffer
    keep SeqMsg as text
    put false into Pkt.Valid

    attempt:
        call Channel.receive with RingHandle giving SeqMsg
        put true into Pkt.Valid
    on failure with Err:
        produce failure with text "ring empty"
    end attempt

    produce success with Pkt
end action
```

---

## MAC Scheduler Pattern (simplified proportional fair)

```
shape UeContext holds:
    RNTI as u16
    CQI as u8                   # Channel Quality Indicator 0-15
    BufferBytes as whole number
    ThroughputAvg as fractional number
    LastScheduledSlot as u32
    Active as truth value
end shape

action schedule_slot takes UeList as list of UeContext
                       and UeCount as whole number
                       and AvailablePRBs as u8
                       produces u16:
    # Proportional fair: maximize CQI / avg_throughput ratio
    keep BestRNTI as u16 with value 0
    keep BestMetric as fractional number with value 0.0

    repeat UeCount times using I:
        keep Ue as UeContext
        put item I of UeList into Ue

        if Ue.Active is false then:
            # skip inactive UEs
        end if
        if Ue.BufferBytes is equal to 0 then:
            # skip UEs with nothing to send
        end if

        keep Metric as fractional number
        if Ue.ThroughputAvg is greater than 0.0 then:
            put the quotient of Ue.CQI and Ue.ThroughputAvg into Metric
        otherwise:
            put Ue.CQI into Metric
        end if

        if Metric is greater than BestMetric then:
            put Metric into BestMetric
            put Ue.RNTI into BestRNTI
        end if
    end repeat

    produce success with BestRNTI
end action
```

---

## HARQ Retransmission Pattern

```
action handle_harq_feedback takes Process as ref HarqProcess
                               and NackReceived as truth value
                               produces truth value:
    # Returns true if retransmission needed
    if NackReceived is false then:
        put 0 into Process.RoundVoyageCount
        put false into Process.NackReceived
        produce success with false    # ACK — transmission complete
    end if

    put true into Process.NackReceived
    put the sum of Process.RoundVoyageCount and 1 into Process.RoundVoyageCount

    # Max 4 HARQ rounds in 5G NR
    if Process.RoundVoyageCount is greater than 4 then:
        put 0 into Process.RoundVoyageCount
        produce failure with text "HARQ max retransmissions reached"
    end if

    # Increment redundancy version: 0→2→3→1→0 (5G NR RV sequence)
    keep RvTable as list of whole number with room for 4
    put 0 into item 0 of RvTable
    put 2 into item 1 of RvTable
    put 3 into item 2 of RvTable
    put 1 into item 3 of RvTable

    keep RvIdx as whole number
    put the remainder of Process.RoundVoyageCount by 4 into RvIdx
    put item RvIdx of RvTable into Process.RedundancyVersion

    produce success with true    # retransmit needed
end action
```

---

## PTP Timing Synchronization

```
action sync_timing takes Info as ref TimingInfo
                     and MeasuredOffsetNs as whole number
                     produces nothing:
    use Device
    use Timer

    # Apply PI servo to minimize offset
    keep Kp as fractional number with value 0.1
    keep Ki as fractional number with value 0.01
    keep Correction as fractional number

    put the product of Kp and MeasuredOffsetNs into Correction

    # Apply frequency correction to hardware clock
    attempt:
        call Device.ioctl with 0 and 1 and Correction
        put MeasuredOffsetNs into Info.PtpOffset
    on failure with Err:
        put true into Info.HoldoverActive
        produce failure with text "PTP servo apply failed"
    end attempt

    if MeasuredOffsetNs is less than 100 then:
        put true into Info.Locked
        put false into Info.HoldoverActive
    otherwise:
        put false into Info.Locked
    end if

    produce success with nothing
end action
```

---

## Stdlib Modules for Telecom

| Module | Use case |
|---|---|
| `Channel` | Zero-copy ring buffer between PHY/MAC/RLC layers |
| `Thread` | RX task, TX task, scheduler task, timing task |
| `Mutex` | Protect UE context table during scheduling |
| `Timer` | Slot timing, HARQ timer, PTP measurement interval |
| `Net` | Fronthaul eCPRI transport, backhaul SCTP/UDP |
| `MemoryMap` | Huge page mapping for zero-copy DMA buffers |
| `Math` | FFT support, channel estimation, CQI computation |

---

## Compile Commands

```bash
# C++ backend for template-heavy signal processing
python dictumc_cli.py phy.dict --backend cpp --cpp-standard 17 --compile -o phy_layer

# O-RAN DU bare C
python dictumc_cli.py du.dict --backend c --compile -o du_app
```

## Domain Rules

1. **Never drop packets silently** — backpressure or log; dropping without accounting breaks QoS.
2. **Zero-copy boundaries** — pass `PhysOffset` not data copies between pipeline stages.
3. **Timing determinism** — all slot processing must complete within the 0.5ms slot boundary.
4. **HARQ max rounds** — enforce max 4 retransmissions; discard TB and report failure after.
5. **Backpressure on ring full** — produce failure up the stack; let the caller decide to drop.
6. **PTP holdover** — track `HoldoverActive`; degrade gracefully when PTP lock is lost.
7. **SSM/CQI quality gates** — never schedule a UE with CQI=0 or a bad quality signal.

---
---

# Dictum Skill — Energy & Smart Grid Firmware

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: inverter control, BMS cell management, protection relay logic,
> grid-tie synchronization, metering, and IEC 61850 GOOSE messaging in Dictum.

---

## Discovery Questions (ask before generating)

1. **System type** — solar inverter, BMS, wind turbine controller, grid storage (ESS), smart meter, EV charging (EVSE), substation automation, microgrid?
2. **Standards** — IEC 61850, IEC 62351, IEEE 1547, UL 1741, IEC 62443, NERC CIP, OCPP?
3. **Protocols** — Modbus RTU/TCP, DNP3, IEC 61850 GOOSE/SV, MQTT, DLMS/COSEM, Zigbee, PLC, cellular?
4. **Safety and protection functions** — islanding detection, over/under voltage, over/under frequency, ground fault, arc fault, BMS cell protection, emergency shutdown?
5. **Metering precision** — revenue grade (0.2%), sub-metering (1%), monitoring (5%), power quality, waveform capture?

---

## Core Energy Shapes

```
shape GridMeasurement holds:
    VoltageV as fractional number
    CurrentA as fractional number
    FrequencyHz as fractional number
    PowerFactorPct as fractional number
    ActivePowerW as fractional number
    ReactivePowerVAR as fractional number
    Timestamp as u32
    QualityOk as truth value
end shape

shape BatteryCell holds:
    CellID as u8
    VoltageV as fractional number
    TemperatureC as fractional number
    StateOfChargePct as fractional number
    CycleCount as u16
    OverVoltage as truth value
    UnderVoltage as truth value
    OverTemp as truth value
    Balanced as truth value
end shape

shape ProtectionState holds:
    OverVoltageTrip as truth value
    UnderVoltageTrip as truth value
    OverFreqTrip as truth value
    UnderFreqTrip as truth value
    IslandingDetected as truth value
    GroundFaultDetected as truth value
    ArcFaultDetected as truth value
    TripReason as text
    TripTimestamp as u32
end shape

shape InverterCommand holds:
    TargetPowerW as fractional number
    ReactivePowerVAR as fractional number
    EnableOutput as truth value
    SafetyGated as truth value
    Timestamp as u32
end shape

shape MeterAccumulator holds:
    ActiveEnergyWh as u32           # fixed-point: Wh * 1000 for 0.001 Wh resolution
    ReactiveEnergyVARh as u32
    PeakDemandW as fractional number
    TariffPeriod as u8
    LastResetTimestamp as u32
end shape
```

---

## Protection Relay Logic (IEEE 1547 / IEC 62361)

Protection functions must execute within one measurement cycle (typically 20ms).

```
action evaluate_protection takes Meas as GridMeasurement produces ProtectionState:
    keep Prot as ProtectionState
    put false into Prot.OverVoltageTrip
    put false into Prot.UnderVoltageTrip
    put false into Prot.OverFreqTrip
    put false into Prot.UnderFreqTrip
    put false into Prot.IslandingDetected
    put false into Prot.GroundFaultDetected

    if Meas.QualityOk is false then:
        put true into Prot.OverVoltageTrip    # conservative — trip on bad quality
        put "measurement quality fault" into Prot.TripReason
        produce success with Prot
    end if

    # IEEE 1547 default trip thresholds
    # Over-voltage: >120% nominal (1.2 * 120V = 144V for 120V system)
    if Meas.VoltageV is greater than 144.0 then:
        put true into Prot.OverVoltageTrip
        put "over-voltage" into Prot.TripReason
    end if

    # Under-voltage: <88% nominal
    if Meas.VoltageV is less than 105.6 then:
        put true into Prot.UnderVoltageTrip
        put "under-voltage" into Prot.TripReason
    end if

    # Over-frequency: >60.5 Hz
    if Meas.FrequencyHz is greater than 60.5 then:
        put true into Prot.OverFreqTrip
        put "over-frequency" into Prot.TripReason
    end if

    # Under-frequency: <59.3 Hz
    if Meas.FrequencyHz is less than 59.3 then:
        put true into Prot.UnderFreqTrip
        put "under-frequency" into Prot.TripReason
    end if

    produce success with Prot
end action

action trip_inverter takes Prot as ProtectionState produces nothing:
    use Device
    use Timer

    # Immediately disable inverter output — must be first action
    attempt:
        call Device.ioctl with 0 and 0 and 0    # disable gate drive
    on failure with Err:
        # Trip must always attempt — log but do not return without disabling
        print the text "TRIP OUTPUT FAILED: " and Err and newline
    end attempt

    call Timer.start with 0 giving Prot.TripTimestamp
    print the text "INVERTER TRIP: " and Prot.TripReason and newline

    produce success with nothing
end action
```

---

## BMS Cell Management

```
action scan_cells takes Cells as list of BatteryCell
                    and CellCount as whole number
                    produces truth value:
    use Device

    keep AllOk as truth value with value true

    repeat CellCount times using I:
        keep Cell as BatteryCell
        put I into Cell.CellID

        attempt:
            call Device.read with I giving Cell.VoltageV
            call Device.read with the sum of I and 100 giving Cell.TemperatureC
        on failure with Err:
            put false into AllOk
            produce success with false
        end attempt

        # Cell voltage limits (Li-ion: 2.5V min, 4.2V max)
        if Cell.VoltageV is greater than 4.2 then:
            put true into Cell.OverVoltage
            put false into AllOk
            call emergency_cell_protection with Cell
        end if
        if Cell.VoltageV is less than 2.5 then:
            put true into Cell.UnderVoltage
            put false into AllOk
        end if

        # Temperature limits
        if Cell.TemperatureC is greater than 60.0 then:
            put true into Cell.OverTemp
            put false into AllOk
            call emergency_cell_protection with Cell
        end if

        put Cell into item I of Cells
    end repeat

    produce success with AllOk
end action

action balance_cells takes Cells as list of BatteryCell
                        and CellCount as whole number
                        produces nothing:
    use Device

    # Find min/max cell voltage
    keep MinV as fractional number with value 5.0
    keep MaxV as fractional number with value 0.0

    repeat CellCount times using I:
        if item I of Cells . VoltageV is less than MinV then:
            put item I of Cells . VoltageV into MinV
        end if
        if item I of Cells . VoltageV is greater than MaxV then:
            put item I of Cells . VoltageV into MaxV
        end if
    end repeat

    # Enable passive balancing on cells above MinV + 10mV threshold
    repeat CellCount times using I:
        keep Diff as fractional number
        put the difference of item I of Cells . VoltageV and MinV into Diff

        if Diff is greater than 0.01 then:
            attempt:
                call Device.ioctl with I and 1 and 0    # enable bleed resistor
                put false into item I of Cells . Balanced
            on failure with Err:
                print the text "balance failed cell " and I and newline
            end attempt
        otherwise:
            put true into item I of Cells . Balanced
        end if
    end repeat

    produce success with nothing
end action
```

---

## Islanding Detection (Passive — ROCOF method)

```
action detect_islanding takes PrevMeas as GridMeasurement
                           and CurrMeas as GridMeasurement
                           and DeltaTSec as fractional number
                           produces truth value:
    # Rate of Change of Frequency (ROCOF)
    # IEEE 1547: trip if ROCOF > 1 Hz/s
    keep FreqDelta as fractional number
    keep ROCOF as fractional number

    put the difference of CurrMeas.FrequencyHz and PrevMeas.FrequencyHz into FreqDelta
    put the quotient of FreqDelta by DeltaTSec into ROCOF

    if ROCOF is less than 0.0 then:
        put the product of ROCOF and -1.0 into ROCOF
    end if

    if ROCOF is greater than 1.0 then:
        produce success with true     # islanding detected
    end if

    produce success with false
end action
```

---

## Revenue-Grade Metering (IEC 62053)

```
action accumulate_energy takes Acc as ref MeterAccumulator
                            and PowerW as fractional number
                            and DeltaTSec as fractional number
                            produces nothing:
    # Fixed-point accumulation: store mWh to avoid float drift
    # Energy (mWh) = Power(W) * DeltaT(s) / 3.6
    keep EnergyMwh as whole number
    put the quotient of the product of PowerW and DeltaTSec by 3.6 into EnergyMwh

    put the sum of Acc.ActiveEnergyWh and EnergyMwh into Acc.ActiveEnergyWh

    if PowerW is greater than Acc.PeakDemandW then:
        put PowerW into Acc.PeakDemandW
    end if

    produce success with nothing
end action
```

---

## Stdlib Modules for Energy

| Module | Use case |
|---|---|
| `Device` | ADC (voltage/current measurement), GPIO (relay/contactor), PWM (inverter gate) |
| `Timer` | Protection trip timing, metering interval, synchronization frame |
| `Net` | Modbus TCP, DNP3, MQTT, IEC 61850 GOOSE over Ethernet |
| `Mutex` | Protect meter accumulators between measurement and reporting threads |
| `Thread` | Measurement task, protection task, comms task, balancing task |
| `Math` | Power factor computation, RMS calculation, ROCOF |
| `File` | Energy log, event log, configuration storage |

---

## Compile Commands

```bash
# Validate
python dictumc_cli.py inverter.dict --validate

# Energy C firmware
python dictumc_cli.py inverter.dict --backend c --compile -o inverter_fw

# BMS C firmware
python dictumc_cli.py bms.dict --backend c --compile -o bms_fw
```

---

## Domain Rules

1. **Protection functions first** — trip evaluation runs at the top of every measurement cycle, before any other logic.
2. **Trip output on any quality fault** — conservative approach: trip when measurement quality is bad.
3. **Fixed-point for energy accumulation** — floating-point drift makes revenue-grade metering inaccurate over time.
4. **Cell protection is immediate** — overvoltage/overtemp must call emergency protection in the same scan pass.
5. **Islanding must trip within 2 seconds** — IEEE 1547 requires clearing within the standard window.
6. **Balancing only when idle** — never balance cells during high-rate charge or discharge.
7. **Trip action always attempts output** — even on `on failure`, the gate drive disable must be attempted.
8. **Meter accumulation uses integer math** — multiply first, divide last to preserve precision.
