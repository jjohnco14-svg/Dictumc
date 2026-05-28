# Dictum v5

**The AI-native systems programming language.**

Dictum is not a C/C++ transpiler. It is a language designed from the ground up so that AI can write, validate, and reason about systems-level programs using natural language — and have those programs compile to production-quality C11 or C++17/20/23. Humans can write it too; it reads like structured English. But the grammar engine, validator, and constraint system exist specifically to give AI a formally-checkable surface to generate against.

```dictum
program Hello:
    keep Name as text with value "World"
    print the text "Hello, " and Name and newline
end program
```

Transpiles to clean, portable C11:

```c
#include <stdio.h>
int main(void) {
    const char* Name = "World";
    printf("Hello, %s\n", Name);
    return 0;
}
```

---

## Why Dictum exists

Most AI code generation targets languages that were designed for humans. Token-by-token generation into Python or C produces syntactically plausible but semantically broken output, because nothing in the generation loop knows whether the next token is valid in the current grammar state.

Dictum solves this at the architecture level:

- The **grammar engine** exposes a state machine that maps grammar positions to valid next-token sets, feeding directly into LLM logit masking.
- The **validator** catches type errors, ownership issues, and scope violations *before* any C is emitted — so an AI that generates Dictum gets structured error feedback, not compiler spew.
- The **natural-language surface** means the same NL description the user gives the AI is structurally close to valid Dictum code — no translation layer.

The C and C++ output is a consequence, not the goal. Dictum happens to produce excellent C because the constraint system forces well-structured programs.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│               DICTUM SOURCE (.dict)               │
│  "keep X as whole number with value 5"            │
└──────────────────────────────────────────────────┘
                        │
           ┌────────────┴────────────┐
           ▼                         ▼
   ┌──────────────┐         ┌──────────────────┐
   │    LEXER     │         │  GRAMMAR ENGINE  │
   │ (tokenizer)  │         │  (state machine  │
   └──────────────┘         │  + LLM bridge)   │
           │                └──────────────────┘
           └────────────┬────────────┘
                        ▼
               ┌──────────────┐
               │    PARSER    │
               │  (AST gen)   │
               └──────────────┘
                        │
           ┌────────────┴────────────┐
           ▼                         ▼
   ┌──────────────┐         ┌──────────────────┐
   │  VALIDATOR   │         │   SUMMARIZER     │
   │(type/memory/ │         │  (NL AST output) │
   │  ownership)  │         └──────────────────┘
   └──────────────┘
           │
   ┌───────┴───────┐
   ▼               ▼
┌──────────┐  ┌──────────┐
│ C EMITTER│  │C++ EMITTER│
│ (CEmitter│  │(CppEmitter│
│  → .c/.h)│  │→ .cpp/.hpp│
└──────────┘  └──────────┘
           │
   ┌───────┴────────────────────────────────┐
   │         POLYGLOT PIPELINE              │
   │  PolyglotParser → PolyglotLinker       │
   │  binding_generator → glue files        │
   └────────────────────────────────────────┘
```

---

## Grammar Engine

`dictumc/grammar.py` — the grammar-constraint system. Its primary audience is LLMs generating Dictum code.

### State machine

`DictumGrammar` is a push-down automaton over `GrammarState` enums. Every grammatical position in Dictum (`BLOCK_BODY`, `KEEP_TYPE`, `CALL_WITH`, `ATTEMPT_FAILURE`, etc.) is a named state. The machine tracks:

- A **state stack** for nested block contexts
- An **indent stack** for Dictum's indentation-sensitive grammar
- A `pending_expr_pop` flag for expression completion

### Token masking for LLM generation

```python
from dictumc.grammar import DictumGrammar, GrammarTokenizerBridge

grammar = DictumGrammar()
bridge = GrammarTokenizerBridge(vocab=tokenizer.vocab)

# After each token, get the valid next-token IDs for logit masking
valid_ids = bridge.get_valid_token_ids(grammar.get_valid_tokens())
# Pass valid_ids as a logit_bias / token_allowed mask to your LLM
```

The `GrammarTokenizerBridge` uses a trie over the BPE vocabulary to map grammar-valid strings to token IDs, including identifier, number, and string literal categories.

### Grammar-constrained parsing

`GrammarConstrainedGenerator.parse_with_grammar(source)` re-runs the full Lex → Parse pipeline with the grammar state machine wired into the parser. Every consumed token advances the automaton; a violation in strict mode raises `SyntaxError` immediately.

```python
from dictumc.grammar import DictumGrammar, GrammarConstrainedGenerator

grammar = DictumGrammar()
gen = GrammarConstrainedGenerator(grammar, vocab)
ast = gen.parse_with_grammar(source)  # raises SyntaxError on grammar violation
```

### Speculative decoding support

`GrammarCheckpoint` is an immutable snapshot of the full grammar state. Use it for tree-search or speculative decoding:

```python
cp = gen.speculative_branch()   # save state
try:
    result = gen.step(candidate_token, token_type)
except SyntaxError:
    gen.revert(cp)              # roll back, try next candidate
```

---

## Validator

`dictumc/validator.py` — semantic analysis before any code is emitted.

### What it checks

- **Type checking** — every expression has an inferred type; mismatches raise `ValidationError`
- **Scope analysis** — undeclared variables are caught; forward references handled via two-pass shape/action scanning
- **Ownership tracking** — handle types (`file_handle`, `net_socket`, `mutex_handle`, etc.) tracked through `VarInfo.is_handle`; released handles caught on re-use
- **Array bounds** — statically-sized arrays track their declared size
- **Auto-declaration** — undeclared assignment targets are inferred and declared rather than erroring, mirroring emitter behavior
- **Unsafe contexts** — `UnsafeBlock` nodes flip `in_unsafe`; inside, raw pointer operations and `ExternFn` calls are permitted without further complaint

### Type system surface

| Dictum type | C type | C++ type |
|---|---|---|
| `whole number` | `int32_t` | `int32_t` |
| `count` | `size_t` | `size_t` |
| `decimal number` / `decimal` | `double` | `double` |
| `fractional number` | `double` | `double` |
| `truth value` / `bool` | `bool` | `bool` |
| `text` | `const char*` (`dictum_text`) | `std::string` |
| `byte` | `uint8_t` | `uint8_t` |
| `nothing` | `void` | `void` |
| `*_handle` types | opaque `intptr_t` | opaque `intptr_t` |

---

## Emitters

### C Emitter (`emit_c.py` — `CEmitter`)

Produces C11 from the AST. Notable behaviors:

- **Module call routing** — `Http.get`, `Json.parse`, `Text.find`, etc. are resolved through `_MODULE_CALL_MAP` to their `dictum_*` C implementations. No `use Module` statement ever emits a function call; it emits `#include`.
- **Forward declarations** — all actions and `extern` functions are forward-declared before `main()`, so recursive and mutually-recursive programs compile cleanly.
- **Array emission** — typed C arrays with bounds, for-each index loops, and initializer lists.
- **`attempt`/`on failure`** — compiled to `setjmp`/`longjmp` pattern with `dictum_last_error` for structured error propagation.
- **Heap allocation** — `NewExpr` nodes emit `malloc`/`calloc` with cast.
- **Makefile generation** — `--makefile` produces a working `Makefile` wired to the stdlib `.a` archive with the right `-lcurl`, `-lssl`, `-lpthread` flags based on which modules the program uses.

### C++ Emitter (`emit_cpp.py` — `CppEmitter`)

Produces C++17/20/23 from the same AST. Differences from the C emitter:

- `text` maps to `std::string` instead of `const char*`
- `attempt`/`on failure` compiles to `try`/`catch`
- Classes, constructors, destructors, and methods emit proper C++ syntax with access specifiers
- Templates emit as `template<typename T>` with parameter constraints
- Lambda expressions emit as C++11 closures
- Smart pointer types (`unique_ptr`, `shared_ptr`) supported via `TYPE_SMART_PTR` grammar state
- Namespaces supported via `--namespace` flag

Both emitters share `_MODULE_CALL_MAP` and `_USE_INCLUDE_MAP` so stdlib module resolution is consistent.

---

## Unsafe Feature

Dictum is safe by default — all memory is stack-allocated or handle-tracked, bounds are checked, and foreign calls go through typed wrappers. Unsafe mode is an explicit opt-in that widens the grammar, not an escape hatch that breaks the parser.

### `unsafe` block

```dictum
unsafe:
    extern void* raw_alloc(size_t n)
    keep Ptr as raw pointer to byte
    transmute Ptr from whole number with value 0
end unsafe
```

Inside an `unsafe` block:
- `ExternFn` nodes are allowed — declare any C ABI symbol with its raw type signature
- `Transmute` nodes perform type-punning (`(TargetType)(expr)` in C)
- `Bind` nodes alias an existing C symbol under a Dictum name
- Raw pointer types (`raw pointer to <type>`) are accepted by the validator
- The validator's `in_unsafe` flag is set; type violations that would normally error are downgraded or passed through

The emitter still produces correct C for all unsafe constructs — `extern` declarations, casts, and pointer arithmetic — but the validator stops enforcing Dictum's ownership rules inside the block.

### Polyglot safety levels

The `PolyglotTranspiler` accepts a `safety` parameter that applies at the module boundary:

| Level | Behavior |
|---|---|
| `safe` | Bounds-checked, no raw pointers across FFI boundary |
| `checked` | Raw C ABI but with runtime assertions injected |
| `unsafe` | Raw C pointers, manual memory, no checks |

---

## Modules

`dictumc/stdlib_registry.py` — maps Dictum `use Module` surface syntax to C implementations.

### Standard modules

| Module | Dictum surface | C backing |
|---|---|---|
| `Http` | `call Http.get with Url giving Response` | `dictum_http_get` (libcurl) |
| `Json` | `call Json.parse with Data giving Handle` | `dictum_json_parse` (cJSON) |
| `File` | `call File.read with Path giving Content` | `dictum_file_read` |
| `Console` | `call Console.write_line with Msg` | `dictum_console_write_line` |
| `Net` | `call Net.connect with Host and Port giving Socket` | `dictum_net_connect` (POSIX) |
| `Tls` | `call Tls.wrap with Socket giving Context` | `dictum_tls_wrap` (OpenSSL) |
| `Text` | `call Text.find with Haystack and Needle giving Index` | `dictum_text_find` |
| `Math` | `call Math.sqrt with X giving Result` | `dictum_math_sqrt` |
| `Thread` | `call Thread.spawn with Task giving Id` | `dictum_thread_spawn` (pthreads) |
| `Mutex` | `call Mutex.create giving Handle` | `dictum_mutex_create` |
| `Channel` | `call Channel.send with Handle and Data` | `dictum_channel_send` |

### Module-level definitions (`.dict` files)

Level 4 and 5 stdlib interfaces define higher-level modules (`MemoryMap`, `Signal`, `Process`, `Pipe`, `SharedMemory`, `Semaphore`, `Timer`, `Event`, `Device`) as Dictum `module` declarations — typed action signatures that the validator and emitter resolve to their C implementations.

### `use Module` semantics

`use Http` in a Dictum program emits exactly one `#include "dictum_http.h"` — never a function call. Module initialization is implicit. The emitter checks which modules are active via `detect_stdlib_includes()` and injects only the required headers and linker flags.

---

## CLI

`dictumc_cli.py` — the `dictumc` command.

```
dictumc <file.dict> [options]
```

| Option | Description |
|---|---|
| `--backend c\|cpp` | Target language (default: `c`) |
| `--cpp-standard 17\|20\|23` | C++ standard when using cpp backend |
| `--namespace <name>` | Wrap C++ output in a namespace |
| `--validate` | Semantic validation only — no code emitted |
| `--no-validate` | Skip validation, emit directly |
| `--compile` | Transpile then invoke `gcc`/`g++` directly |
| `--output <file>` / `-o` | Output path (default: stdout) |
| `--makefile` | Write a `Makefile` alongside the output (C only) |
| `--grammar` | Enable grammar-constrained parsing (strict mode) |
| `--stdlib` | Use `StdlibTranspiler` with auto-injected stdlib imports |
| `--summary` | Print a natural-language AST summary |
| `--emit-ast` | Dump the raw AST repr |

### Examples

```bash
# Validate only
dictumc myprogram.dict --validate

# Transpile to C and write with Makefile
dictumc myprogram.dict -o myprogram.c --makefile

# Transpile and compile in one step
dictumc myprogram.dict --compile -o myprogram

# C++17 output in a namespace
dictumc myprogram.dict --backend cpp --cpp-standard 17 --namespace myapp -o myprogram.cpp

# Grammar-strict mode (recommended for AI-generated programs)
dictumc myprogram.dict --grammar --stdlib -o myprogram.c

# Stdin pipeline
echo 'program X: print the text "ok" end program' | dictumc --backend c
```

Warnings are printed to stderr. The exit code is 0 on success, 1 on any error (syntax, validation, or compile failure).

---

## VibeCoder Playground + QEMU

`ui/backend_server.py` — FastAPI backend for the browser-based IDE.

```bash
pip install "dictum[server]"
python ui/backend_server.py
# Open http://localhost:8765
```

The playground exposes `/transpile` and `/run` endpoints. The VibeCoder HTML frontend sends Dictum source, gets back C/C++ and (optionally) execution output, and persists named programs to a SQLite workspace that survives tab close and server restart.

---

## QEMU Connection Guide

QEMU user-mode lets you cross-compile a Dictum program and execute it for a foreign architecture — ARM64, RISC-V, MIPS, PowerPC — entirely on your host machine, no physical hardware required. The playground server handles all of this transparently once the toolchain is installed.

### Step 1 — Install the backend server dependencies

```bash
pip install fastapi uvicorn pydantic
```

### Step 2 — Install QEMU user-mode and cross-compilers

On Ubuntu 22.04+ or Debian 12+:

```bash
sudo apt update
sudo apt install -y qemu-user \
    gcc-aarch64-linux-gnu   g++-aarch64-linux-gnu   \
    gcc-riscv64-linux-gnu   g++-riscv64-linux-gnu   \
    gcc-mips-linux-gnu      g++-mips-linux-gnu      \
    gcc-mipsel-linux-gnu    g++-mipsel-linux-gnu    \
    gcc-powerpc64le-linux-gnu g++-powerpc64le-linux-gnu
```

You don't need all of them. Install only the targets you plan to use. The server detects availability at runtime.

On macOS (via Homebrew), QEMU user-mode is not available — only `qemu-system-*` is. Use a Linux VM or Docker container for cross-compilation targets on macOS.

On WSL2 (Windows), install the packages as above inside the WSL2 Ubuntu environment.

### Step 3 — Start the backend server

```bash
# From the Dictumc project root
python ui/backend_server.py
```

The server starts on `http://0.0.0.0:8765`. Open `ui/dictum_vibecoder.html` in a browser, or hit the API directly.

### Step 4 — Verify which targets are available

```bash
curl http://localhost:8765/targets
```

Response:

```json
{
  "targets": [
    { "id": "linux",   "label": "Linux x86-64 (host native)", "available": true,  "reason": null },
    { "id": "arm64",   "label": "ARM64 / AArch64",            "available": true,  "reason": null },
    { "id": "riscv64", "label": "RISC-V 64-bit",              "available": false, "reason": "missing: qemu-riscv64" },
    { "id": "mips",    "label": "MIPS big-endian",            "available": false, "reason": "missing: mips-linux-gnu-gcc, qemu-mips" },
    { "id": "mipsel",  "label": "MIPS little-endian",         "available": false, "reason": "missing: mipsel-linux-gnu-gcc, qemu-mipsel" },
    { "id": "ppc64le", "label": "PowerPC 64-bit LE",          "available": false, "reason": "missing: powerpc64le-linux-gnu-gcc, qemu-ppc64le" }
  ]
}
```

Any target with `"available": false` shows exactly which binaries are missing. Install them from Step 2 and restart the server.

### Step 5 — Run a program on a specific target

`POST /run` with a `target` field set to any available target ID:

```bash
curl -X POST http://localhost:8765/run \
  -H "Content-Type: application/json" \
  -d '{
    "source": "program Hello:\n    print the text \"Hello from ARM64\" and newline\nend program",
    "backend": "c",
    "target": "arm64",
    "compile": true,
    "stdlib": true
  }'
```

Response:

```json
{
  "ok": true,
  "code": "/* generated C11 */\n#include <stdio.h>\n...",
  "output": "Hello from ARM64\n",
  "stderr": "",
  "exit_code": 0,
  "target": "arm64",
  "target_label": "ARM64 / AArch64",
  "warnings": []
}
```

### Target reference

| `target` | Architecture | C compiler | C++ compiler | QEMU binary |
|---|---|---|---|---|
| `linux` | x86-64 (host native) | `gcc` | `g++` | none |
| `arm64` | ARM64 / AArch64 | `aarch64-linux-gnu-gcc` | `aarch64-linux-gnu-g++` | `qemu-aarch64` |
| `riscv64` | RISC-V 64-bit | `riscv64-linux-gnu-gcc` | `riscv64-linux-gnu-g++` | `qemu-riscv64` |
| `mips` | MIPS big-endian | `mips-linux-gnu-gcc` | `mips-linux-gnu-g++` | `qemu-mips` |
| `mipsel` | MIPS little-endian | `mipsel-linux-gnu-gcc` | `mipsel-linux-gnu-g++` | `qemu-mipsel` |
| `ppc64le` | PowerPC 64-bit LE | `powerpc64le-linux-gnu-gcc` | `powerpc64le-linux-gnu-g++` | `qemu-ppc64le` |

### How it works internally

When you set `target` to anything other than `linux`, the server:

1. Transpiles your Dictum source to C (or C++) normally.
2. Invokes the cross-compiler with `-static` — static linking is required because the binary needs to be self-contained inside the QEMU sandbox (dynamic linker paths differ between sysroots).
3. Executes the binary via `qemu-<arch> [-L <sysroot>] ./program`. The `-L` flag points QEMU at the correct multiarch sysroot when one is present at `/usr/<arch>-linux-gnu`.
4. Returns stdout, stderr, and exit code exactly as the native path does.

The timeout is 30 seconds for compilation and 10 seconds for execution. Programs that produce no output or hang are killed.

### Using the C++ backend with QEMU

The `backend` field can be `"c"` or `"cpp"` independently of the target. For example, to run a C++17 program on ARM64:

```bash
curl -X POST http://localhost:8765/run \
  -H "Content-Type: application/json" \
  -d '{
    "source": "program Vec:\n    use Console\n    keep Items as array of whole number with 3 elements\n    put 1 into Items at 0\n    put 2 into Items at 1\n    put 3 into Items at 2\n    for each Item in Items repeat\n        call Console.write_line with Item\n    end for\nend program",
    "backend": "cpp",
    "cpp_standard": 17,
    "target": "arm64",
    "compile": true,
    "stdlib": true
  }'
```

### Troubleshooting

**`"missing: qemu-aarch64"`** — run `sudo apt install qemu-user` and restart the server. The server does not auto-detect newly installed binaries until restart.

**`"missing: aarch64-linux-gnu-gcc"`** — run `sudo apt install gcc-aarch64-linux-gnu`. The package name pattern is `gcc-<arch>-linux-gnu`.

**Compile error on cross target but not on `linux`** — this usually means your program uses a stdlib module (`Http`, `Tls`, `Net`) that requires shared libraries not available in the static cross-sysroot. Pure-logic programs and programs using only `Console`, `Math`, `Text`, `File`, and `Thread` are safe for cross targets.

**QEMU exits with a non-zero code, no stderr** — check `exit_code` in the response. Exit code 139 is a segfault inside QEMU — this is a program bug surfaced by the target's ABI, not a QEMU issue.

**Slow first compile on a new target** — the cross-compiler caches object files in `/tmp`. Subsequent runs are fast.

**macOS: targets unavailable** — QEMU user-mode (`qemu-user`) is a Linux-only package. On macOS you can run `qemu-system-aarch64` for full VM emulation, but that is not integrated with the playground server. Use Docker: `docker run --rm -it -p 8765:8765 -v $(pwd):/app ubuntu:24.04 bash` and install dependencies inside the container.

---

## Polyglot: C and C++ in the same program

`dictumc/polyglot_transpiler.py`, `polyglot_ast.py`, `polyglot_parser.py`, `linker/`

The polyglot pipeline lets a single Dictum project compile different modules to different backends and link them together. The canonical use case is a mixed C/C++ program where performance-critical or C-ABI-exposed parts emit C, and object-oriented or template-heavy parts emit C++.

### Declaring a polyglot module

```dictum
polyglot module CoreEngine uses c with safety safe:
    @export
    action compute takes Input as whole number produces decimal number
    
    @export
    action reset produces nothing
end module

polyglot module Interface uses cpp with safety checked:
    @export
    shape Result holds:
        Value as decimal number
        Error as text
    end shape

    action run takes Input as whole number produces Result
end module
```

`@export` marks an action or shape for cross-language linking. The polyglot linker (`PolyglotLinker`) generates:
- A `.h` / `.hpp` header for each exported interface
- A C-ABI shim for C++ → C calls
- A `CMakeLists.txt` or `Makefile` that builds both modules and links them

### Safety levels at module boundaries

```python
from dictumc.polyglot_transpiler import PolyglotTranspiler

t = PolyglotTranspiler(
    source=source,
    backend='c',
    safety='checked',       # 'safe' | 'unsafe' | 'checked'
    project_name='my_app',
    output_dir='build/polyglot'
)
result = t.run(link=True, write_files=True)

# result['code']           — main transpiled C/C++
# result['polyglot_files'] — dict of generated binding/header/build files
# result['interfaces']     — PolyglotInterface objects (exported symbols)
```

`safe` — bounds-checked, no raw pointers across the boundary.  
`checked` — raw C ABI but with runtime assertions injected at the boundary.  
`unsafe` — raw C pointers and manual memory, no checks.

### Interop patterns

Beyond in-process FFI, the polyglot system supports `grpc`, `http`, `msgqueue`, and `wasm` as interop patterns — declared in the `polyglot module` header. The binding generator produces the appropriate glue (gRPC stubs, REST client wrappers, etc.) based on the pattern.

---

## Skills System

`industry_skills/` — 50 structured skill definitions mapping Dictum's natural-language programming to real C/C++ systems domains.

### What the skills are

Each skill is a JSON descriptor containing:
- Target industry and domain
- Dictum syntax features exercised
- Underlying C/C++ concepts the generated code demonstrates
- Concrete deliverables (programs to ship)
- Estimated hours to mastery
- Prerequisites from prior skills

The skills are not tutorials. They are **instruction sets for AI systems** — structured enough that an AI given a skill descriptor can generate correct Dictum programs for that domain without improvising.

### Skill tiers

| Tier | Skills | Complexity |
|---|---|---|
| 1 | 1 | Foundations — console apps |
| 2 | 2–3 | Memory & files |
| 3 | 4–6, 9, 18–19 | Systems, networking, security, DevOps |
| 4 | 7, 14–17, 20, 22, 25, 27–29, 31–32, 34, 37–38 | C++, AI/ML, cloud, bioinformatics |
| 5 | 10–13, 23, 26, 30, 39–40, 42–43, 45–48 | Embedded, IoT, robotics, medical, automotive |
| 6 | 24, 41, 44, 49 | Aerospace, quantum, neuromorphic |
| 7 | 8, 50 | OS kernels, language design |

### Industry skills included

`SKILL_EMBEDDED.md`, `SKILL_AEROSPACE.md`, `SKILL_AUTOMOTIVE.md`, `SKILL_EDGEAI.md`, `SKILL_INDUSTRIAL.md`, `SKILL_MEDICAL.md`, `SKILL_GENERAL.md` — each a detailed reference covering Dictum syntax patterns, C ABI patterns, and safety requirements specific to that domain.

The full `DICTUM_50_INDUSTRY_SKILLS.json` contains all 50 skills in machine-readable form. The `Dictum_Skill_System.md` in `docs/` is the AI-facing reference that describes how to use the skills to drive code generation.

---

## What Dictum is and is not

**Dictum is:** an AI-native language where the grammar, validator, and constraint system are first-class features designed to make LLM code generation reliable and checkable for systems programming.

**Dictum is not:** a C/C++ transpiler in the sense of "translate your Python-style code to C." The natural-language surface is the language. C and C++ are the compilation targets, chosen because they are the right output for the domains Dictum targets — embedded, systems, IoT, robotics, aerospace, high-performance computing.

The difference matters because Dictum's grammar and validator give AI structured feedback. An LLM generating C directly has no feedback loop until `gcc` runs. An LLM generating Dictum gets `ValidationError: Variable 'X' used before declaration at line 4` — actionable, token-precise, recoverable.

---

## What works today

| Capability | Status |
|---|---|
| Console I/O (`print`, `read`) | ✅ Production-ready |
| Arithmetic (whole, decimal) | ✅ Production-ready |
| Conditionals, loops (`while`, `for each`) | ✅ Production-ready |
| Shapes (structs), field access | ✅ Production-ready |
| Actions (functions), recursion | ✅ Production-ready |
| Arrays with for-each | ✅ Production-ready |
| Basic file I/O (read/write/seek/exists/append) | ✅ Production-ready |
| String operations (`Text.*`) | ✅ Production-ready |
| HTTP GET/POST/PUT/DELETE/PATCH (`use Http`) | ✅ Production-ready |
| TCP sockets (`use Net`) | ✅ Production-ready |
| TLS (`use Tls`) | ✅ Production-ready |
| JSON parse/stringify/navigate (`use Json`) | ✅ Production-ready |
| Threading / Mutex / Channel | ✅ Working, tested under basic load |
| `attempt`/`on failure` error blocks | ✅ setjmp/longjmp (C), try/catch (C++) |
| Auto-generated Makefile | ✅ Production-ready |
| C++ backend (classes, templates, lambdas) | ✅ Production-ready |
| Unsafe blocks (`extern`, `transmute`, `bind`) | ✅ Grammar-gated |
| Grammar-constrained generation / token masking | ✅ Production-ready |
| Polyglot C+C++ module linking | ✅ Working |
| QEMU cross-compilation playground | ✅ arm64, riscv64, mips, mipsel, ppc64le |
| VibeCoder browser IDE with SQLite workspace | ✅ Persistent across sessions |
| 50 industry skill descriptors | ✅ JSON + markdown |

### Current limitations

- Multi-file module imports (`import MyModule from "mymodule.dict"`) — AST node exists (`ImportDict`), transpiler integration pending.
- 50 industry skills — JSON descriptors complete; skills that reference `Http`/`Net`/`Json` are marked `"status": "stub"` until end-to-end integration tests pass.
- UTF-8 string operations are byte-length-counted; grapheme-cluster operations are available via `Text.grapheme_*` but not unicode-normalized beyond codepoint counting.

---

## Quick start

```bash
# Install
pip install dictum          # or: pip install -e .

# Build stdlib (once)
cd stdlib && make lib

# Transpile
dictumc examples/level1.dict -o hello.c --makefile

# Build and run
make && ./hello
```

## Requirements

- Python 3.11+
- gcc 11+ or clang 14+
- Linux or macOS (Windows: WSL 2)
- For HTTP/TLS: `libcurl4-openssl-dev`, `libssl-dev`
- For QEMU targets: see QEMU section above

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

279 unit tests + compile+run integration tests. Integration tests are skipped automatically if gcc is not on `PATH`.

---

## License

MIT. See LICENSE.
