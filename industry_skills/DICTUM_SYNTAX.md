# Dictum Language — Complete Syntax Reference for AI

> This is the authoritative skill file for generating valid Dictum code.
> Load this before any Dictum task. The validator enforces every rule here.
> Compile with: `python dictumc_cli.py <file.dict> --backend c --compile`

---

## What Dictum Is

Dictum is a natural-language programming language that compiles to C or C++.
The AI writes Dictum. The compiler handles all C/C++ details.
The validator catches every structural mistake before it becomes a C bug.

**The rule:** If it reads like an instruction in plain English, it is probably valid Dictum.

---

## File Structure

Every Dictum file is either a `program` (executable entry point) or a `module` (library).

```
program <Name>:
    <statements>
end program
```

```
module <Name>:
    <action definitions>
    <shape definitions>
end module
```

Multiple top-level declarations are allowed in one file.

---

## 1. Variables — `keep`

Declare a variable with `keep`:

```
keep <Name> as <type>
keep <Name> as <type> with value <expr>
keep <Name> as <type> with room for <n>       # fixed-size array
keep <Name> as <type> with values <a> and <b> and <c>
```

### Types

| Dictum type | C type | Notes |
|---|---|---|
| `whole number` | `int` | default integer |
| `fractional number` | `double` | floating point |
| `decimal number` | `double` | alias |
| `truth value` | `bool` | true / false |
| `text` | `char*` | null-terminated string |
| `byte` | `uint8_t` | single byte |
| `bytes` | `uint8_t*` | byte array |
| `count` | `size_t` | unsigned size |
| `nothing` | `void` | return type only |
| `u8` `u16` `u32` `u64` | fixed-width unsigned | |
| `i32` `i64` | fixed-width signed | |
| `list of <type>` | `<type>[]` | array |
| `array of <type>` | `<type>[]` | alias for list |
| `ref <type>` | `<type>&` | C++ reference |
| `const ref <type>` | `const <type>&` | const C++ reference |
| `raw pointer` | `void*` | unsafe raw pointer |
| `unique handle to <T>` | `std::unique_ptr<T>` | C++ only |
| `shared handle to <T>` | `std::shared_ptr<T>` | C++ only |
| `<UserShape>` | `struct UserShape` | user-defined shape |

### Examples

```
keep Count as whole number with value 0
keep Name as text with value "Alice"
keep Buffer as bytes with room for 256
keep Flag as truth value with value true
keep Score as fractional number with value 3.14
```

---

## 2. Assignment — `put ... into` and `set ... to`

```
put <expr> into <Name>
put <expr> into <Shape>.<field>
set <Name> to <expr>
```

```
put 42 into Count
put the sum of Count and 1 into Count
put "hello" into Name
set Score to 9.8
put true into Flag
```

---

## 3. Expressions

### Arithmetic (prefix form — preferred)

```
the sum of A and B          →  A + B
the difference of A and B   →  A - B
the product of A and B      →  A * B
the quotient of A and B     →  A / B
the remainder of A by B     →  A % B
```

### Arithmetic (infix form — also valid)

```
A times B          →  A * B
A modulo B         →  A % B
A divided by B     →  A / B
```

### Math functions

```
the square root of X        →  sqrt(X)
the power of A and B        →  pow(A, B)
the sine of X               →  sin(X)
the cosine of X             →  cos(X)
the exponential of X        →  exp(X)
the length of X             →  strlen(X)
the count of X              →  count/length
```

### Bitwise

```
the bitwise and of A and B  →  A & B
the bitwise or of A and B   →  A | B
the bitwise not of A        →  ~A
the left shift of A by B    →  A << B
the right shift of A by B   →  A >> B
```

### Comparisons

```
X is equal to Y
X is not equal to Y
X is greater than Y
X is less than Y
X is greater than or equal to Y
X is less than or equal to Y
X is at least Y             →  X >= Y
X is at most Y              →  X <= Y
X is true
X is false
X is nothing                →  X == NULL
X is empty
```

### Literals

```
42          whole number
3.14        fractional number
"hello"     text
true        truth value
false       truth value
nothing     NULL / void
empty       empty/null
newline     '\n'
```

### Array/field access

```
item N of MyArray           →  MyArray[N]
MyArray at N                →  MyArray[N]
field of Shape              →  Shape.field
Shape.field                 →  Shape.field
```

---

## 4. Actions (Functions)

```
action <name> takes <param> as <type> produces <return_type>:
    <body>
end action
```

Multiple parameters use `and`:

```
action add takes A as whole number and B as whole number produces whole number:
    produce success with the sum of A and B
end action
```

No parameters:

```
action greet produces nothing:
    print the text "Hello" and newline
end action
```

### Returning values

```
produce success with <expr>     # return a value
produce failure with text <msg> # return an error
return <expr>                   # alternative return form
```

### Calling actions

```
call <name> with <arg> and <arg> giving <ResultVar>
call <name> giving <ResultVar>
call <name> with <arg>
call <name>
```

---

## 5. Control Flow

### If / otherwise

```
if <condition> then:
    <body>
end if

if <condition> then:
    <body>
otherwise:
    <body>
end if

if <condition> then:
    <body>
otherwise if <condition> then:
    <body>
otherwise:
    <body>
end if
```

### While loop

```
while <condition> repeat:
    <body>
end while
```

### Repeat N times

```
repeat <N> times using <Counter>:
    <body>
end repeat
```

`Counter` is the loop variable (whole number, starts at 0).

### For-each loop

```
for each <Item> in <Collection> repeat:
    <body>
end for
```

### Infinite loop

```
repeat forever:
    <body>
end repeat
```

---

## 6. Shapes (Structs)

```
shape <Name> holds:
    <field> as <type>
    <field> as <type>
end shape
```

```
shape Point holds:
    X as fractional number
    Y as fractional number
end shape

keep P as Point
put 3.0 into P.X
put 4.0 into P.Y
```

Packed struct (no padding):

```
#[packed]
shape PackedHeader holds:
    Magic as u32
    Length as u16
end shape
```

---

## 7. Error Handling — `attempt`

The `attempt` block is Dictum's primary error-handling construct.
Use it for any call that can fail (I/O, device access, network, etc.).

```
attempt:
    call <risky_action> with <args> giving <Result>
on failure with <ErrCode>:
    <handle error>
end attempt
```

```
attempt:
    call read_sensor with 0 giving Reading
on failure with Err:
    print the text "sensor failed: " and Err and newline
    produce failure with text "sensor error"
end attempt
```

With success body:

```
attempt:
    call open_file with "data.txt" giving Handle
on success:
    print the text "file opened" and newline
on failure with Err:
    print the text "error: " and Err and newline
end attempt
```

**Rule:** Any action that can fail MUST be wrapped in `attempt`. Never ignore errors.

---

## 8. Modules and Use

Declare a stdlib module interface with `module`:

```
module Http:
    action get takes Url as text produces text
    action post takes Url as text and Body as text produces text
end module
```

Import a module into scope with `use`:

```
use Http
use Math
use File
```

After `use`, call module actions as `ModuleName.action`:

```
use Http
keep Response as text
call Http.get with "https://api.example.com" giving Response
```

---

## 9. Available Stdlib Modules

All modules live in `stdlib/`. Use `use <Module>` to activate.

| Module | Key actions | Header |
|---|---|---|
| `Console` | write, write_line, read_line | dictum_console.h |
| `File` | read, write, exists, delete, list | dictum_file.h |
| `Text` | length, concat, find, slice, trim, split, to_upper, to_lower, replace, starts_with, ends_with, contains, to_number, from_int | dictum_text.h |
| `Math` | sqrt, pow, abs, floor, ceil, round, sin, cos, log, exp | dictum_math.h |
| `Net` | connect, send, receive, close, listen, accept | dictum_net.h |
| `Http` | get, post, put, delete, headers | dictum_http.h |
| `Tls` | wrap, handshake, send, receive, close | dictum_tls.h |
| `Json` | parse, stringify, get, set | dictum_json.h |
| `Thread` | start, join | dictum_thread.h |
| `Mutex` | create, lock, unlock | dictum_mutex.h |
| `Semaphore` | create, wait, signal, destroy | dictum_semaphore.h |
| `Channel` | create, send, receive, close | dictum_channel.h |
| `Timer` | start, stop, sleep | dictum_timer.h |
| `Event` | create, wait, signal, destroy | dictum_event.h |
| `Device` | open, read, write, ioctl, close | dictum_device.h |
| `Path` | valid, exists, is_file, is_directory, size | dictum_path.h |
| `Directory` | create, remove, list, current, change | dictum_directory.h |
| `Process` | spawn, wait, kill, current_id | dictum_process.h |
| `Pipe` | create, read, write, close | dictum_pipe.h |
| `SharedMemory` | create, read, write, close | dictum_shm.h |
| `MemoryMap` | create, read, write, close | dictum_mmap.h |
| `Signal` | on, send, block, unblock | dictum_signal.h |
| `Csv` | read, write, parse_line | dictum_csv.h |

---

## 10. Importing C Functions

Call existing C functions directly with `import`:

```
import the action <c_func_name> from "<header.h>"
    taking <param> as <type>
    produces <return_type>
    as <DictumName>
```

```
import the action malloc from "stdlib.h"
    taking Size as count
    produces raw pointer
    as allocate

keep Buf as raw pointer
call allocate with 256 giving Buf
```

---

## 11. Unsafe Block

For raw C operations that cannot be expressed in Dictum:

```
unsafe:
    # raw C code here — written as Dictum comments
    # The emitter passes this through as-is
end unsafe
```

Use sparingly. Prefer stdlib modules over unsafe blocks.

---

## 12. C++ Features (--backend cpp)

When compiling with `--backend cpp --cpp-standard 17`:

### Methods on shapes

```
shape Counter holds:
    Value as whole number

    method increment produces nothing:
        put the sum of Value and 1 into Value
    end method

    constructor takes Start as whole number:
        put Start into Value
    end constructor

    destructor:
        # cleanup
    end destructor
end shape
```

### Smart pointers

```
keep Ptr as unique handle to Counter
put new Counter with 0 into Ptr
```

### Lambdas

```
keep Handler as action taking X as whole number produces whole number
put action takes X as whole number produces whole number:
    produce success with the product of X and 2
end action into Handler
```

### Possibilities (enum class)

```
possibilities Status:
    Ok
    Pending
    Failed
end possibilities
```

---

## 13. Comments

```
# This is a comment — ignored by the compiler
```

---

## 14. Complete Working Examples

### Hello world

```
program Hello:
    print the text "Hello, world!" and newline
end program
```

### Function with error handling

```
program Divide:
    action safe_divide takes A as whole number and B as whole number produces fractional number:
        if B is equal to 0 then:
            produce failure with text "division by zero"
        end if
        produce success with the quotient of A and B
    end action

    keep Result as fractional number
    attempt:
        call safe_divide with 10 and 2 giving Result
        print the text "Result: " and Result and newline
    on failure with Err:
        print the text "Error: " and Err and newline
    end attempt
end program
```

### Struct + loop

```
program Stats:
    shape Reading holds:
        Value as fractional number
        Valid as truth value
    end shape

    keep Total as fractional number with value 0.0
    keep Samples as list of Reading with room for 10

    repeat 10 times using I:
        put 1.5 into item I of Samples . Value
        put true into item I of Samples . Valid
        put the sum of Total and 1.5 into Total
    end repeat

    print the text "Total: " and Total and newline
end program
```

### File I/O

```
program ReadConfig:
    use File

    keep Contents as text
    attempt:
        call File.read with "config.txt" giving Contents
        print the text "Config: " and Contents and newline
    on failure with Err:
        print the text "Cannot read config: " and Err and newline
    end attempt
end program
```

### Concurrency

```
program Worker:
    use Thread
    use Mutex
    use Channel

    keep Lock as whole number
    keep Ch as whole number

    call Mutex.create giving Lock
    call Channel.create with 10 giving Ch

    action producer produces nothing:
        call Mutex.lock with Lock
        call Channel.send with Ch and "work item"
        call Mutex.unlock with Lock
    end action

    call Thread.start with producer giving _
end program
```

---

## 15. Compilation Reference

```bash
# Validate only (no output)
python dictumc_cli.py file.dict --validate

# Emit C to stdout
python dictumc_cli.py file.dict --backend c

# Emit C and compile to binary
python dictumc_cli.py file.dict --backend c --compile -o myprogram

# Emit C++ (C++17)
python dictumc_cli.py file.dict --backend cpp --cpp-standard 17 --compile -o myprogram

# Emit with Makefile
python dictumc_cli.py file.dict --backend c --output myprogram.c --makefile

# Stdlib-aware transpiler (auto-injects stdlib imports)
python dictumc_cli.py file.dict --stdlib --backend c --compile

# Grammar-constrained strict mode
python dictumc_cli.py file.dict --grammar --validate
```

---

## 16. Rules the Validator Enforces

These will cause a validation error — know them:

1. Every `action` body must end with `produce success with` or `produce failure with text` — never fall off the end silently.
2. Variables must be declared with `keep` before use.
3. `attempt` is required around any call to an action that `produces` a failable type.
4. Shape fields accessed as `Shape.field` — the shape must be declared before the access.
5. Types must match — you cannot put a `text` into a `whole number`.
6. `end` keywords must match their block type (`end action`, `end if`, `end shape`, etc.).
7. Indentation is significant — use 4 spaces per level consistently.
8. No semicolons. No curly braces. No asterisks for pointers in declarations (use `raw pointer` type).

---

## 17. AI Generation Rules

When generating Dictum code:

1. **Always start with** `program <Name>:` or `module <Name>:`.
2. **Always end with** `end program` or `end module`.
3. **Never emit C directly** — write Dictum, let the compiler handle C.
4. **Every failable call** goes inside `attempt ... on failure ... end attempt`.
5. **Every action** ends with `produce success with` or `produce failure with text`.
6. **Use `the sum/difference/product/quotient of A and B`** for math — it is always correct.
7. **Indentation** is 4 spaces. Never tabs.
8. **Types in natural language** — `whole number` not `int`, `truth value` not `bool`.
9. **When unsure about a stdlib call**, declare the module interface with `module` and use `use`.
10. **Run `--validate` first** — fix all validator errors before `--compile`.
