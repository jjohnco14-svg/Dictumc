# Dictum Skill — Edge AI & On-Device Inference

> Load DICTUM_SYNTAX.md first, then this file.
> This skill covers: model loading, inference pipelines, pre/post-processing,
> NPU/TPU dispatch, multi-model orchestration, and OTA model updates in Dictum.

---

## Discovery Questions (ask before generating)

1. **Hardware** — Jetson Orin/Nano, Raspberry Pi + Coral TPU, STM32 + CubeAI, Kendryte K210, Hailo-8, custom NPU FPGA?
2. **Model type** — image classification (CNN), object detection (YOLO), semantic segmentation, audio/keyword spotting, time-series anomaly, small LLM, pose estimation?
3. **Inference runtime** — TFLite Micro, ONNX Runtime, TensorRT, OpenVINO, ncnn, CMSIS-NN, vendor SDK?
4. **Constraints** — <1ms latency required, battery powered, no OS, INT8 only, multi-model pipeline, camera/audio real-time input?
5. **Deployment** — factory flash, OTA WiFi/BLE, SD card, USB DFU, cloud-managed?

---

## Core Edge AI Shapes

```
shape TensorBuffer holds:
    Data as bytes
    Width as whole number
    Height as whole number
    Channels as whole number
    Dtype as u8                 # 0=float32 1=int8 2=uint8 3=float16
    Stride as whole number
    Valid as truth value
end shape

shape InferenceResult holds:
    ClassID as whole number
    Confidence as fractional number
    BBoxX as fractional number
    BBoxY as fractional number
    BBoxW as fractional number
    BBoxH as fractional number
    LatencyUs as whole number
    Valid as truth value
end shape

shape ModelContext holds:
    Handle as whole number
    InputWidth as whole number
    InputHeight as whole number
    InputChannels as whole number
    OutputClasses as whole number
    QuantScale as fractional number
    QuantZeroPoint as whole number
    Loaded as truth value
end shape

shape DetectionList holds:
    Count as whole number
    Scores as list of fractional number
    ClassIDs as list of whole number
    Boxes as list of fractional number    # flat: x,y,w,h per detection
end shape
```

---

## Model Load Pattern

```
action load_model takes ModelPath as text produces ModelContext:
    use File
    use MemoryMap

    keep Ctx as ModelContext
    put false into Ctx.Loaded
    put 0 into Ctx.Handle

    # Verify model file exists
    keep Exists as truth value
    call File.exists with ModelPath giving Exists
    if Exists is false then:
        produce failure with text "model file not found"
    end if

    # Memory-map the model for zero-copy loading
    attempt:
        call MemoryMap.create with ModelPath and 0 giving Ctx.Handle
    on failure with Err:
        produce failure with text "model mmap failed"
    end attempt

    # Set default input geometry — caller should override
    put 224 into Ctx.InputWidth
    put 224 into Ctx.InputHeight
    put 3 into Ctx.InputChannels
    put 1000 into Ctx.OutputClasses
    put 1.0 into Ctx.QuantScale
    put 0 into Ctx.QuantZeroPoint
    put true into Ctx.Loaded

    produce success with Ctx
end action
```

---

## Pre-Processing Pipeline

### Resize + normalize (float32 input)

```
action preprocess_image takes Input as TensorBuffer
                          and Ctx as ModelContext
                          produces TensorBuffer:
    keep Output as TensorBuffer
    put Ctx.InputWidth into Output.Width
    put Ctx.InputHeight into Output.Height
    put Ctx.InputChannels into Output.Channels
    put 0 into Output.Dtype    # float32
    put false into Output.Valid

    # Validate input
    if Input.Valid is false then:
        produce failure with text "invalid input tensor"
    end if
    if Input.Channels is not equal to 3 then:
        produce failure with text "expected RGB input"
    end if

    # Bilinear resize — call into stdlib C implementation
    attempt:
        call resize_bilinear with Input and Output
    on failure with Err:
        produce failure with text "resize failed"
    end attempt

    # Normalize to [-1, 1] range (MobileNet-style)
    # pixel_normalized = (pixel / 127.5) - 1.0
    keep TotalPixels as whole number
    put the product of Output.Width and the product of Output.Height and Output.Channels
        into TotalPixels

    repeat TotalPixels times using I:
        keep Pixel as fractional number
        put item I of Output.Data into Pixel
        put the difference of the quotient of Pixel by 127.5 and 1.0
            into item I of Output.Data
    end repeat

    put true into Output.Valid
    produce success with Output
end action
```

### INT8 quantization

```
action quantize_input takes Input as TensorBuffer
                        and Scale as fractional number
                        and ZeroPoint as whole number
                        produces TensorBuffer:
    keep Output as TensorBuffer
    put Input.Width into Output.Width
    put Input.Height into Output.Height
    put Input.Channels into Output.Channels
    put 1 into Output.Dtype    # int8
    put false into Output.Valid

    keep TotalPixels as whole number
    put the product of Input.Width and the product of Input.Height and Input.Channels
        into TotalPixels

    repeat TotalPixels times using I:
        keep FloatVal as fractional number
        keep IntVal as whole number
        put item I of Input.Data into FloatVal
        put the sum of the quotient of FloatVal by Scale and ZeroPoint into IntVal

        # Clamp to int8 range [-128, 127]
        if IntVal is greater than 127 then:
            put 127 into IntVal
        end if
        if IntVal is less than -128 then:
            put -128 into IntVal
        end if

        put IntVal into item I of Output.Data
    end repeat

    put true into Output.Valid
    produce success with Output
end action
```

---

## Inference Dispatch

### Single inference with latency measurement

```
action run_inference takes Ctx as ModelContext
                       and Input as TensorBuffer
                       produces InferenceResult:
    use Timer

    keep Result as InferenceResult
    put false into Result.Valid
    put 0 into Result.ClassID
    put 0.0 into Result.Confidence

    if Ctx.Loaded is false then:
        produce failure with text "model not loaded"
    end if
    if Input.Valid is false then:
        produce failure with text "invalid input"
    end if

    keep StartUs as whole number
    call Timer.start with 0 giving StartUs

    attempt:
        call model_forward with Ctx.Handle and Input.Data giving Result.ClassID
        put true into Result.Valid
    on failure with Err:
        produce failure with text "inference failed"
    end attempt

    keep EndUs as whole number
    call Timer.start with 0 giving EndUs
    put the difference of EndUs and StartUs into Result.LatencyUs

    # Confidence threshold gate
    if Result.Confidence is less than 0.5 then:
        put false into Result.Valid
    end if

    produce success with Result
end action
```

### Object detection with NMS (Non-Maximum Suppression pattern)

```
action run_detection takes Ctx as ModelContext
                       and Input as TensorBuffer
                       and ConfThreshold as fractional number
                       and IouThreshold as fractional number
                       produces DetectionList:
    keep Results as DetectionList
    put 0 into Results.Count

    keep RawOutput as TensorBuffer
    attempt:
        call model_forward with Ctx.Handle and Input.Data giving RawOutput.Data
    on failure with Err:
        produce failure with text "detection inference failed"
    end attempt

    # Filter by confidence threshold
    keep BoxIdx as whole number with value 0
    repeat Ctx.OutputClasses times using I:
        keep Score as fractional number
        put item I of RawOutput.Data into Score

        if Score is greater than ConfThreshold then:
            put Score into item Results.Count of Results.Scores
            put I into item Results.Count of Results.ClassIDs
            put the sum of Results.Count and 1 into Results.Count
        end if
    end repeat

    produce success with Results
end action
```

---

## Multi-Model Pipeline

```
program VisionPipeline:
    use Thread
    use Channel
    use Timer
    use MemoryMap

    keep FrameChannel as whole number
    keep ResultChannel as whole number
    call Channel.create with 4 giving FrameChannel      # 4-frame queue
    call Channel.create with 4 giving ResultChannel

    keep DetectorCtx as ModelContext
    keep ClassifierCtx as ModelContext

    action capture_task produces nothing:
        repeat forever:
            keep Frame as TensorBuffer
            put 640 into Frame.Width
            put 480 into Frame.Height
            put 3 into Frame.Channels
            put true into Frame.Valid

            attempt:
                call Channel.send with FrameChannel and Frame.Width
            on failure with Err:
                # Channel full — drop frame
            end attempt

            call Timer.sleep with 33     # ~30fps
        end repeat
    end action

    action detection_task produces nothing:
        keep FrameMsg as text
        keep Frame as TensorBuffer
        keep Detections as DetectionList
        keep Preprocessed as TensorBuffer

        repeat forever:
            attempt:
                call Channel.receive with FrameChannel giving FrameMsg
                call preprocess_image with Frame and DetectorCtx giving Preprocessed
                call run_detection with DetectorCtx and Preprocessed and 0.5 and 0.45 giving Detections

                if Detections.Count is greater than 0 then:
                    call Channel.send with ResultChannel and Detections.Count
                end if
            on failure with Err:
                print the text "detection error: " and Err and newline
            end attempt
        end repeat
    end action

    # Load models
    attempt:
        call load_model with "detector.tflite" giving DetectorCtx
        call load_model with "classifier.tflite" giving ClassifierCtx
    on failure with Err:
        print the text "model load failed: " and Err and newline
    end attempt

    call Thread.start with capture_task giving _
    call Thread.start with detection_task giving _

    repeat forever:
        call Timer.sleep with 1000
    end repeat
end program
```

---

## Audio Keyword Spotting Pattern

```
shape AudioFrame holds:
    Samples as list of fractional number
    SampleRate as whole number
    WindowMs as whole number
    Valid as truth value
end shape

action extract_mfcc takes Frame as AudioFrame
                      and NumCoefficients as whole number
                      produces TensorBuffer:
    keep Features as TensorBuffer
    put NumCoefficients into Features.Width
    put 1 into Features.Height
    put 1 into Features.Channels
    put 0 into Features.Dtype
    put false into Features.Valid

    if Frame.Valid is false then:
        produce failure with text "invalid audio frame"
    end if

    # Pre-emphasis filter: y[n] = x[n] - 0.97 * x[n-1]
    repeat the count of Frame.Samples times using I:
        if I is greater than 0 then:
            keep Curr as fractional number
            keep Prev as fractional number
            put item I of Frame.Samples into Curr
            put item the difference of I and 1 of Frame.Samples into Prev
            put the difference of Curr and the product of 0.97 and Prev
                into item I of Frame.Samples
        end if
    end repeat

    put true into Features.Valid
    produce success with Features
end action
```

---

## Stdlib Modules for Edge AI

| Module | Use case |
|---|---|
| `MemoryMap` | Zero-copy model weight loading from flash/filesystem |
| `Thread` | Capture, preprocessing, inference, and postprocessing tasks |
| `Channel` | Pass frames and results between pipeline stages |
| `Timer` | Latency measurement, frame rate control |
| `Mutex` | Protect model context during concurrent calls |
| `Math` | Normalization, scaling, sigmoid/softmax approximations |
| `File` | Model file existence check, OTA model slot validation |
| `Device` | Camera capture (V4L2), microphone (ALSA), NPU device node |

---

## Compile Commands

```bash
# C++ backend for template-heavy inference wrappers
python dictumc_cli.py pipeline.dict --backend cpp --cpp-standard 17 --compile -o pipeline

# Bare-metal CMSIS-NN target
python dictumc_cli.py kws.dict --backend c --compile -o kws.elf

# Validate first
python dictumc_cli.py pipeline.dict --validate
```

---

## Domain Rules

1. **Always check model loaded** before calling inference — `Ctx.Loaded is false` must produce failure.
2. **Confidence threshold gate** — never act on a result below the calibrated threshold.
3. **Latency budget** — measure `LatencyUs` on every inference; log if it exceeds the SLA.
4. **Channel as pipeline buffer** — never share raw tensor buffers between threads; pass through Channel.
5. **INT8 clamping** — quantized values must be clamped to [-128, 127] — overflow is a silent accuracy bug.
6. **Frame drop on full channel** — capture tasks must drop frames rather than block the pipeline.
7. **Zero-copy model loading** — use `MemoryMap` not `File.read` for model weights to avoid double-buffering.
8. **Multi-model** — each model gets its own `ModelContext`; never share handles between models.
