# Dictum Skill — Robotics & Motion Control

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: robot controllers, kinematics, motor drivers,
> sensor fusion, control loops, and real-time motion execution in Dictum.

---

## Discovery Questions (ask before generating)

Before writing any code, ask the user:

1. **Platform** — ROS2/Linux, bare-metal MCU, RTOS (FreeRTOS/Zephyr), embedded Linux, simulation?
2. **Kinematics** — serial arm (how many DOF?), delta, mobile base (diff drive / ackermann), quadruped, drone/UAV, fixed manipulator?
3. **Controllers** — STM32 family, ESP32, Jetson, Raspberry Pi, FPGA, CAN-based servo drives, EtherCAT slaves?
4. **Control mode** — PID position/velocity, MPC, force/torque, impedance, path planning only, FSM?
5. **Safety** — ISO 10218 industrial, soft estop only, redundant sensors, no formal requirement?
6. **Comms** — CAN bus, EtherCAT, SPI/I2C, UART, ROS topics, custom protocol?

---

## Domain Concepts → Dictum Patterns

### Joint state shape (universal starting point)

```
shape JointState holds:
    Position as fractional number
    Velocity as fractional number
    Torque as fractional number
    Temperature as fractional number
    ErrorCode as whole number
    Valid as truth value
end shape
```

### Motor command shape

```
shape MotorCommand holds:
    JointID as whole number
    TargetPosition as fractional number
    TargetVelocity as fractional number
    MaxTorque as fractional number
    Mode as whole number
end shape
```

### Robot state shape (full arm or base)

```
shape RobotState holds:
    JointCount as whole number
    EStopActive as truth value
    FaultCode as whole number
    ControlMode as whole number
    Ready as truth value
end shape
```

---

## Control Loop Patterns

### PID controller

```
shape PIDState holds:
    Kp as fractional number
    Ki as fractional number
    Kd as fractional number
    Integral as fractional number
    PrevError as fractional number
    OutputMin as fractional number
    OutputMax as fractional number
end shape

action pid_step takes P as ref PIDState
                and Target as fractional number
                and Current as fractional number
                and Dt as fractional number
                produces fractional number:
    keep Error as fractional number
    keep Derivative as fractional number
    keep Output as fractional number

    put the difference of Target and Current into Error
    put the sum of P.Integral and the product of Error and Dt into P.Integral
    put the quotient of the difference of Error and P.PrevError by Dt into Derivative
    put the sum of the product of P.Kp and Error
        and the sum of the product of P.Ki and P.Integral
              and the product of P.Kd and Derivative
        into Output
    put Error into P.PrevError

    if Output is greater than P.OutputMax then:
        put P.OutputMax into Output
    end if
    if Output is less than P.OutputMin then:
        put P.OutputMin into Output
    end if

    produce success with Output
end action
```

### Encoder read with fault detection

```
action read_encoder takes JointID as whole number produces JointState:
    use Device

    keep J as JointState
    put false into J.Valid
    put JointID into J.ErrorCode

    attempt:
        call Device.read with JointID giving J.Position
        put true into J.Valid
        put 0 into J.ErrorCode
    on failure with Err:
        put Err into J.ErrorCode
        put false into J.Valid
        produce failure with text "encoder read failed"
    end attempt

    if J.Position is greater than 6.2832 then:
        produce failure with text "position out of range"
    end if
    if J.Position is less than -6.2832 then:
        produce failure with text "position out of range"
    end if

    produce success with J
end action
```

### Velocity-limited command dispatch

```
action send_command takes Cmd as MotorCommand produces nothing:
    use Device

    if Cmd.MaxTorque is greater than 100.0 then:
        produce failure with text "torque limit exceeded"
    end if
    if Cmd.TargetVelocity is greater than 50.0 then:
        produce failure with text "velocity limit exceeded"
    end if

    attempt:
        call Device.write with Cmd.JointID and Cmd.TargetPosition
    on failure with Err:
        produce failure with text "motor write failed"
    end attempt

    produce success with nothing
end action
```

---

## Safety Patterns

### Emergency stop handler

```
shape EStopState holds:
    Active as truth value
    Reason as text
    Timestamp as whole number
end shape

action trigger_estop takes Reason as text produces nothing:
    use Device
    use Timer

    # De-energize all drives immediately
    attempt:
        call Device.write with 0 and 0     # broadcast zero torque
    on failure with Err:
        # estop must always attempt even if write fails
    end attempt

    print the text "ESTOP: " and Reason and newline
    produce success with nothing
end action

action check_safety takes J as JointState produces truth value:
    if J.Temperature is greater than 80.0 then:
        call trigger_estop with "overtemperature"
        produce success with false
    end if
    if J.Valid is false then:
        call trigger_estop with "encoder fault"
        produce success with false
    end if
    produce success with true
end action
```

### Watchdog pattern

```
action run_watchdog produces nothing:
    use Timer
    use Device

    keep LastHeartbeat as whole number with value 0
    keep Now as whole number

    repeat forever:
        call Timer.sleep with 100
        call Timer.start with 0 giving Now

        if the difference of Now and LastHeartbeat is greater than 500 then:
            call trigger_estop with "watchdog timeout"
        end if
    end repeat
end action
```

---

## Kinematics Patterns

### Forward kinematics (2-DOF planar example)

```
shape Pose2D holds:
    X as fractional number
    Y as fractional number
    Theta as fractional number
end shape

action forward_kinematics_2dof takes L1 as fractional number
                                 and L2 as fractional number
                                 and Q1 as fractional number
                                 and Q2 as fractional number
                                 produces Pose2D:
    keep P as Pose2D

    keep C1 as fractional number
    keep C12 as fractional number

    call Math.cos with Q1 giving C1
    call Math.cos with the sum of Q1 and Q2 giving C12

    put the sum of the product of L1 and C1
            and the product of L2 and C12
        into P.X

    keep S1 as fractional number
    keep S12 as fractional number
    call Math.sin with Q1 giving S1
    call Math.sin with the sum of Q1 and Q2 giving S12

    put the sum of the product of L1 and S1
            and the product of L2 and S12
        into P.Y

    put the sum of Q1 and Q2 into P.Theta

    produce success with P
end action
```

---

## Real-Time Control Loop (main program template)

```
program RobotController:
    use Device
    use Timer
    use Mutex
    use Thread

    shape Config holds:
        LoopRateHz as whole number
        JointCount as whole number
        MaxVelocity as fractional number
        MaxTorque as fractional number
    end shape

    keep Cfg as Config
    put 1000 into Cfg.LoopRateHz
    put 6 into Cfg.JointCount
    put 2.0 into Cfg.MaxVelocity
    put 50.0 into Cfg.MaxTorque

    keep StateLock as whole number
    call Mutex.create giving StateLock

    action control_loop produces nothing:
        keep J as JointState
        keep Cmd as MotorCommand
        keep Safe as truth value

        repeat forever:
            call Timer.sleep with 1      # 1ms = 1kHz

            call Mutex.lock with StateLock

            repeat Cfg.JointCount times using I:
                attempt:
                    call read_encoder with I giving J
                on failure with Err:
                    call trigger_estop with "encoder fault"
                end attempt

                call check_safety with J giving Safe
                if Safe is false then:
                    call Mutex.unlock with StateLock
                    produce success with nothing
                end if
            end repeat

            call Mutex.unlock with StateLock
        end repeat
    end action

    call Thread.start with control_loop giving _
    print the text "Robot controller started" and newline

    repeat forever:
        call Timer.sleep with 1000
    end repeat
end program
```

---

## Stdlib Modules for Robotics

| Module | Use case |
|---|---|
| `Device` | Read/write encoder registers, GPIO, PWM hardware |
| `Timer` | Loop rate control, watchdog, deadline checking |
| `Mutex` | Protect shared joint state between threads |
| `Thread` | Separate control loop, comms loop, safety monitor |
| `Channel` | Pass commands between task threads |
| `Math` | Kinematics calculations, trig, sqrt |
| `Pipe` | IPC with a supervisor process |
| `Signal` | Handle OS signals for clean shutdown |

---

## Compile Commands

```bash
# Bare-metal C target
python dictumc_cli.py robot.dict --backend c --compile -o robot

# C++ with RAII (Zephyr / Linux C++)
python dictumc_cli.py robot.dict --backend cpp --cpp-standard 17 --compile -o robot

# Validate before compile
python dictumc_cli.py robot.dict --validate

# With stdlib auto-injection
python dictumc_cli.py robot.dict --stdlib --backend c --compile -o robot
```

---

## Domain Rules

1. **Every encoder read** must be inside `attempt` — hardware can fail silently.
2. **Estop must always execute** — never gate estop on a lock or condition check.
3. **Control loop timing** — use `Timer.sleep` with 1ms for 1kHz, 10ms for 100Hz.
4. **Joint limits** — always validate position/velocity/torque against configured limits before sending.
5. **Shared state** — all joint state shared between threads must be protected with `Mutex`.
6. **Watchdog** — every system with a real-time loop needs a watchdog action running in its own thread.
7. **Torque zeroing** — on any fault, first action is always zero torque to all drives.
8. **No blocking calls in control loop** — `Device.read` and `Device.write` must be non-blocking or on a separate thread.
