# Dictum Skill — General Planning, Syntax Enforcement & CLI

> This is the **universal base skill** for all Dictum code generation.
> It implements the full Ask → Plan → Verify → Output pipeline.
> Load DICTUM_SYNTAX.md first, then this file.
> All other domain skills (Medical, Embedded, Security, etc.) layer on top of this one.

---

## Pipeline Overview

Every Dictum generation request follows this exact pipeline — no shortcuts:

```
User asks a question
    ↓
1. CLARIFY   — Extract what the program needs to do; ask discovery questions if ambiguous
    ↓
2. PLAN      — Decompose into shapes, actions, modules, control flow, error paths
    ↓
3. VERIFY    — Check every rule in DICTUM_SYNTAX.md § 16 before emitting a single line
    ↓
4. OUTPUT    — Emit valid Dictum; always include compile command
```

Never skip steps. A plan that hasn't been verified will produce validator errors.

---

## Step 1 — CLARIFY

Before writing any code, resolve these if not clear from context:

| Question | Why it matters |
|---|---|
| What does the program produce? | Determines `produces` return type of every top-level action |
| Does it read input? From where? | Console → `Console`, file → `File`, network → `Http`/`Net` |
| Does it write output? To where? | Same modules |
| Are there failure cases? | Determines whether `attempt` blocks are needed |
| What data structures does it need? | Determines `shape` definitions |
| Does it repeat work? | Determines loop type: `while`, `repeat N times`, `for each` |
| Is it a program (main entry) or a module (library)? | Determines top-level keyword |

If any of these is unclear, ask one targeted question. Do not ask more than two at once.

---

## Step 2 — PLAN

Write the plan as a numbered list before generating code. Format:

```
PLAN
----
1. Shapes needed: <list with field names and types>
2. Modules to use: <list of stdlib modules with why>
3. Actions needed: <name, inputs, output type, can it fail?>
4. Control flow: <loops, conditionals, special cases>
5. Error paths: <what can fail and what to do>
6. Entry point: program <Name> calls actions in order: <list>
```

This plan becomes the scaffold. If the plan is wrong, the code will be wrong.

---

## Step 3 — VERIFY

Before emitting code, mentally run through this checklist:

```
VERIFY
------
[ ] Every action ends with `produce success with` or `produce failure with text`
[ ] Every failable call is inside `attempt ... on failure ... end attempt`
[ ] Every variable is declared with `keep` before it is used
[ ] Every `end` keyword matches its block: end action / end if / end shape / end while / end repeat / end for / end program / end module
[ ] Types match: text into text, whole number into whole number — no implicit casts
[ ] Indentation is 4 spaces per level, no tabs
[ ] No semicolons, no curly braces, no asterisks for pointers
[ ] Shape fields accessed as Shape.field (not Shape->field)
[ ] Module functions called as Module.action (after `use Module`)
[ ] Array items accessed as `item N of Array` or `Array at N`
[ ] Math uses `the sum/difference/product/quotient of A and B`
[ ] `repeat N times using Counter` — Counter is the loop variable, starts at 0
```

If any box would be unchecked, fix the plan before writing code.

---

## Step 4 — OUTPUT

Emit the full Dictum program. Always append the compile commands block at the end.

### Compile Commands block (always include)

```bash
# Validate only
python dictumc_cli.py <filename>.dict --validate

# Compile to native binary
python dictumc_cli.py <filename>.dict --backend c --stdlib --compile -o <program_name>

# C++ backend (when using shapes with methods, smart pointers, lambdas)
python dictumc_cli.py <filename>.dict --backend cpp --cpp-standard 17 --stdlib --compile -o <program_name>

# Emit C source without compiling (inspect before build)
python dictumc_cli.py <filename>.dict --backend c --stdlib

# Strict grammar-constrained validation
python dictumc_cli.py <filename>.dict --grammar --validate
```

---

## API Module (BYOK)

When the program needs to call an external REST API, use the `Http` module.
The API key is never hardcoded — it is always read from an environment variable or a config file.

### Pattern — API key from environment

```
program ApiCall:
    use Http
    use Console
    use Text
    use Json

    # Read API key from environment at startup
    import the action getenv from "stdlib.h"
        taking Name as text
        produces text
        as read_env

    keep ApiKey as text
    attempt:
        call read_env with "API_KEY" giving ApiKey
        if ApiKey is nothing then:
            print the text "Error: API_KEY environment variable not set" and newline
            produce failure with text "missing API key"
        end if
    on failure with Err:
        print the text "Failed to read API_KEY: " and Err and newline
        produce failure with text "env read error"
    end attempt

    # Build request
    keep Url as text with value "https://api.example.com/v1/endpoint"
    keep Response as text

    attempt:
        call Http.post with Url and "{\"input\":\"value\"}" giving Response
    on failure with Err:
        print the text "HTTP error: " and Err and newline
        produce failure with text "request failed"
    end attempt

    # Parse response
    keep Parsed as whole number
    attempt:
        call Json.get with Response and "result" giving Parsed
        print the text "Result: " and Parsed and newline
    on failure with Err:
        print the text "Parse error: " and Err and newline
    end attempt
end program
```

### Pattern — API key from config file

```
program ApiCallFromConfig:
    use Http
    use File
    use Text
    use Json

    keep ConfigText as text
    attempt:
        call File.read with "config.json" giving ConfigText
    on failure with Err:
        print the text "Cannot read config.json: " and Err and newline
        produce failure with text "config missing"
    end attempt

    keep ApiKey as text
    attempt:
        call Json.get with ConfigText and "api_key" giving ApiKey
    on failure with Err:
        print the text "api_key not found in config: " and Err and newline
        produce failure with text "config parse error"
    end attempt

    keep Response as text
    attempt:
        call Http.post with "https://api.example.com/v1/data" and "{}" giving Response
    on failure with Err:
        print the text "Request failed: " and Err and newline
    end attempt

    print the text "Done: " and Response and newline
end program
```

### Config file format (config.json)

```json
{
  "api_key": "sk-...",
  "endpoint": "https://api.example.com"
}
```

**Rule:** Never hardcode secrets. Always BYOK through env var or config file. The config file path must be settable — never assume a fixed absolute path.

---

## Common Dictum Patterns (Quick Reference)

### Read a line from stdin

```
use Console
keep Input as text
attempt:
    call Console.read_line giving Input
on failure with Err:
    print the text "Read error: " and Err and newline
end attempt
```

### Write to a file

```
use File
attempt:
    call File.write with "output.txt" and "hello world"
on failure with Err:
    print the text "Write failed: " and Err and newline
end attempt
```

### HTTP GET with response handling

```
use Http
keep Body as text
attempt:
    call Http.get with "https://api.example.com/data" giving Body
    print the text "Response: " and Body and newline
on failure with Err:
    print the text "GET failed: " and Err and newline
end attempt
```

### Parse JSON and extract field

```
use Json
keep Value as text
attempt:
    call Json.get with JsonString and "key" giving Value
on failure with Err:
    print the text "JSON parse error: " and Err and newline
end attempt
```

### Loop with index

```
repeat 10 times using I:
    print the text "Step " and I and newline
end repeat
```

### For-each over array

```
for each Item in MyArray repeat:
    print the text "Item: " and Item and newline
end for
```

### Shape construction and field access

```
shape Config holds:
    Host as text
    Port as whole number
    Debug as truth value
end shape

keep Cfg as Config
put "localhost" into Cfg.Host
put 8080 into Cfg.Port
put false into Cfg.Debug
```

### Conditional with multiple branches

```
if Score is greater than 90 then:
    print the text "Excellent" and newline
otherwise if Score is greater than 70 then:
    print the text "Good" and newline
otherwise:
    print the text "Needs improvement" and newline
end if
```

---

## Common Mistakes to Avoid

| Wrong | Correct |
|---|---|
| `int count = 0;` | `keep Count as whole number with value 0` |
| `count++` | `put the sum of Count and 1 into Count` |
| `if (x == y)` | `if X is equal to Y then:` |
| `return value;` | `produce success with Value` |
| `arr[i]` | `item I of Arr` |
| `struct.field` shorthand in C | `Struct.Field` in Dictum |
| Forgetting `end if` | Every `if` needs `end if` |
| Forgetting `end attempt` | Every `attempt` needs `end attempt` |
| Math as `A + B` | `the sum of A and B` |
| `#include <stdio.h>` | `use Console` |
| Hardcoding API key | Read from env with `getenv` or from config file |

---

## Domain Rules (General)

1. **Ask before assuming** — if the request is ambiguous about input/output/failure behaviour, ask one question.
2. **Plan before coding** — write the PLAN block first; it forces catching design errors early.
3. **Verify before emitting** — run the checklist; a validator error wastes a compile cycle.
4. **Error paths are not optional** — every `attempt` block must have a meaningful `on failure` body, not just a silent swallow.
5. **BYOK always** — never hardcode credentials, API keys, or tokens; always read from environment or config.
6. **Smallest program that works** — do not generate extra shapes or actions that the program does not need.
7. **Compile commands always** — end every code block with the exact CLI commands to validate and compile it.
