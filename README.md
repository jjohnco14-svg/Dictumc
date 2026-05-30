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

## Multi-File Module Imports

Dictum programs can import other `.dict` files as named modules using `import`:

```dictum
import MyLib from "mylib.dict"
```

The transpiler resolves the path relative to the importing file's directory, recursively transpiles each imported module, and generates a `.h` / `.c` (or `.hpp` / `.cpp`) pair for each. Circular imports are detected and rejected. The CLI passes `--source-path` or the file path of the root `.dict` so that relative imports resolve correctly from wherever the program lives.

```bash
# Multi-file project layout
src/
  main.dict          # import Math from "utils/math.dict"
  utils/
    math.dict        # shared actions

dictumc src/main.dict -o build/main.c --makefile
# Emits build/main.c + build/math.c + build/math.h + Makefile
```

The generated Makefile includes all discovered module object files automatically.

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

## VibeCoder Web IDE

`dictum-web/server.py` — the hosted browser IDE, deployed on fly.io.

```bash
pip install "dictum[server]"
python dictum-web/server.py
# Open http://localhost:8080
```

### Endpoints

| Endpoint | Description |
|---|---|
| `POST /api/transpile` | Transpile Dictum source → C or C++; returns code + warnings |
| `POST /api/run` | Transpile → compile → execute, optionally on a QEMU target |
| `POST /api/generate` | LLM-powered code generation (BYOK, non-streaming) |
| `POST /api/generate-stream` | SSE streaming generation |
| `GET /api/targets` | List available QEMU cross-compilation targets |
| `GET/POST /api/workspace/*` | SQLite-backed named program storage (persists across sessions) |

### BYOK AI Integration

The `/api/generate` and `/api/generate-stream` endpoints accept any LLM provider. Pass your key and endpoint directly from the browser settings panel — nothing is stored server-side.

```json
{
  "prompt": "write a TCP echo server",
  "api_key": "sk-...",
  "api_endpoint": "https://api.anthropic.com",
  "api_format": "anthropic",
  "model": "claude-opus-4-20250514",
  "skills": ["general", "embedded"]
}
```

Supported providers:

| Provider | `api_format` | `api_endpoint` |
|---|---|---|
| Anthropic | `anthropic` | `https://api.anthropic.com` (default) |
| OpenAI | `openai` | `https://api.openai.com/v1` |
| NVIDIA NIM | `openai` (auto-detected) | `https://integrate.api.nvidia.com/v1` |
| Any OpenAI-compatible | `openai` | your endpoint |

NVIDIA NIM is auto-detected from the endpoint URL — `api_format` does not need to be set manually.

The `skills` field is a list of industry skill IDs (e.g. `["embedded", "security"]`) that are injected into the system prompt to steer generation toward domain-appropriate patterns.

### SQLite Workspace

Named programs are persisted to `workspace.db` in the server directory. The workspace survives tab close and server restart. All CRUD operations are exposed via `/api/workspace/*`.

---

## QEMU Cross-Compilation

QEMU user-mode lets you cross-compile a Dictum program and execute it for a foreign architecture — ARM64, RISC-V, MIPS, PowerPC — entirely on your host machine, no physical hardware required.

### Install cross-compilers (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install -y qemu-user \
    gcc-aarch64-linux-gnu   g++-aarch64-linux-gnu   \
    gcc-riscv64-linux-gnu   g++-riscv64-linux-gnu   \
    gcc-mips-linux-gnu      g++-mips-linux-gnu      \
    gcc-mipsel-linux-gnu    g++-mipsel-linux-gnu    \
    gcc-powerpc64le-linux-gnu g++-powerpc64le-linux-gnu
```

Install only the targets you plan to use. The server detects availability at runtime and reports missing binaries via `GET /api/targets`.

### Target reference

| `target` | Architecture | C compiler | QEMU binary |
|---|---|---|---|
| `linux` | x86-64 (host native) | `gcc` | none |
| `arm64` | ARM64 / AArch64 | `aarch64-linux-gnu-gcc` | `qemu-aarch64` |
| `riscv64` | RISC-V 64-bit | `riscv64-linux-gnu-gcc` | `qemu-riscv64` |
| `mips` | MIPS big-endian | `mips-linux-gnu-gcc` | `qemu-mips` |
| `mipsel` | MIPS little-endian | `mipsel-linux-gnu-gcc` | `qemu-mipsel` |
| `ppc64le` | PowerPC 64-bit LE | `powerpc64le-linux-gnu-gcc` | `qemu-ppc64le` |

### Run on a specific target

```bash
curl -X POST http://localhost:8080/api/run \
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
  "code": "/* generated C11 */\n...",
  "output": "Hello from ARM64\n",
  "stderr": "",
  "exit_code": 0,
  "target": "arm64",
  "target_label": "ARM64 / AArch64",
  "warnings": []
}
```

### How it works

When `target` is anything other than `linux`, the server transpiles your source, invokes the cross-compiler with `-static` (self-contained binary, no sysroot linker dependency), then executes via `qemu-<arch> [-L <sysroot>] ./program`. Compilation timeout is 30 seconds; execution timeout is 10 seconds.

### Platform notes

**macOS** — QEMU user-mode (`qemu-user`) is Linux-only. Use Docker: `docker run --rm -it -p 8080:8080 -v $(pwd):/app ubuntu:24.04 bash` and install dependencies inside.

**WSL2** — install packages as above inside the WSL2 Ubuntu environment.

**Cross-target stdlib limitations** — programs using `Http`, `Tls`, or `Net` require shared libraries not available in a static cross-sysroot. `Console`, `Math`, `Text`, `File`, and `Thread` work on all targets.

---

## Polyglot: C and C++ in the same program

`dictumc/polyglot_transpiler.py`, `polyglot_ast.py`, `polyglot_parser.py`, `linker/`

The polyglot pipeline lets a single Dictum project compile different modules to different backends and link them together.

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

`@export` marks an action or shape for cross-language linking. The polyglot linker generates `.h` / `.hpp` headers, C-ABI shims for C++ → C calls, and a `CMakeLists.txt` or `Makefile` for the combined build.

### Python API

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

Beyond in-process FFI, the polyglot system supports `grpc`, `http`, `msgqueue`, and `wasm` as interop patterns.

---

## Skills System

`industry_skills/` — 50 structured skill definitions mapping Dictum's natural-language programming to real C/C++ systems domains.

### What the skills are

Each skill is a JSON descriptor containing the target industry, Dictum syntax features exercised, underlying C/C++ concepts demonstrated, concrete deliverables, estimated hours to mastery, and prerequisites. They are instruction sets for AI systems — structured enough that an AI given a skill descriptor can generate correct Dictum programs for that domain.

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

### Industry skill packs

`SKILL_EMBEDDED.md`, `SKILL_AEROSPACE.md`, `SKILL_AUTOMOTIVE.md`, `SKILL_EDGEAI.md`, `SKILL_INDUSTRIAL.md`, `SKILL_MEDICAL.md`, `SKILL_GENERAL.md` — each a detailed reference covering Dictum syntax patterns, C ABI patterns, and safety requirements for that domain.

The full `DICTUM_50_INDUSTRY_SKILLS.json` contains all 50 skills in machine-readable form. `docs/Dictum_Skill_System.md` is the AI-facing reference for using skills to drive generation.

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
| Multi-file module imports (`import X from "x.dict"`) | ✅ Recursive, cycle-detected |
| Polyglot C+C++ module linking | ✅ Working |
| QEMU cross-compilation playground | ✅ arm64, riscv64, mips, mipsel, ppc64le |
| VibeCoder browser IDE with SQLite workspace | ✅ Persistent across sessions |
| BYOK AI (Anthropic, OpenAI-compat, NVIDIA NIM) | ✅ Non-streaming + SSE streaming |
| 50 industry skill descriptors | ✅ JSON + markdown |

### Known limitations

- 50 industry skills — JSON descriptors complete; skills that reference `Http`/`Net`/`Json` are marked `"status": "stub"` until end-to-end integration tests pass.
- UTF-8 string operations are byte-length-counted; grapheme-cluster operations are available via `Text.grapheme_*` but not unicode-normalized beyond codepoint counting.
- QEMU cross-targets require Linux host (or Docker on macOS/Windows); QEMU user-mode is not available natively on macOS.

---

## Quick start

```bash
# Install
pip install dictum-lang          # or: pip install -e .

# Build stdlib (once)
cd stdlib && make lib

# Transpile
dictumc examples/level1.dict -o hello.c --makefile

# Build and run
make && ./hello
```

## Requirements

- Python 3.9+
- gcc 11+ or clang 14+
- Linux or macOS (Windows: WSL 2)
- For HTTP/TLS: `libcurl4-openssl-dev`, `libssl-dev`
- For web server: `pip install "dictum-lang[server]"`
- For QEMU targets: see QEMU section above

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

279 unit tests + compile+run integration tests across C and C++ backends, polyglot pipeline, and stdlib. Integration tests are skipped automatically if `gcc` is not on `PATH`. CI runs on Python 3.10, 3.11, and 3.12.

---

## License

Apache 2.0. See LICENSE.
