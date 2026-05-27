# Dictum v5

**Natural-language transpiler to C.**  
Write programs in structured English. Get clean, safe, portable C11.

```dictum
program Hello:
    keep Name as text with value "World"
    print the text "Hello, " and Name and newline
end program
```

Transpiles to:

```c
#include <stdio.h>
// ...
int main(void) {
    const char* Name = "World";
    printf("Hello, %s\n", Name);
    return 0;
}
```

---

## What works today ✅

| Capability | Status |
|---|---|
| Console I/O (`print`, `read`) | ✅ Production-ready |
| Arithmetic (whole, decimal) | ✅ Production-ready |
| Conditionals, loops (`while`, `for each`) | ✅ Production-ready |
| Shapes (structs), field access | ✅ Production-ready |
| Actions (functions), recursion | ✅ Production-ready |
| Basic file read/write/seek/exists/append | ✅ Production-ready |
| String operations (`Text.*`) | ✅ Production-ready |
| HTTP GET/POST (`use Http`) | ✅ Production-ready |
| TCP sockets (`use Net`) | ✅ Production-ready |
| TLS (`use Tls`) | ✅ Production-ready |
| JSON parse/stringify (`use Json`) | ✅ Production-ready |
| Threading/Mutex/Channel | ✅ Working, tested under basic load |
| Auto-generated Makefile | ✅ Production-ready |
| `attempt`/`on failure` error blocks | ✅ Uses `dictum_last_error` |
| C++ backend | ✅ Production-ready |
| VibeCoder browser UI | ✅ Works locally |

## Honest current limitations

- Multi-file / user-defined module imports (`MISSING-08`) — not yet implemented.
- VibeCoder workspace persistence — programs lost on tab close.
- 50 industry skills — JSON descriptors only; skills referencing Http/Net/Json are marked `"status": "stub"` until end-to-end verified.
- UTF-8 string operations are length-counted but not unicode-aware beyond codepoint counting.

---

## Quick start

```bash
# Install
pip install dictum   # or: pip install -e .

# Build stdlib (once)
cd stdlib && make lib

# Transpile
dictumc examples/level1.dict -o hello.c --makefile

# Build and run
make && ./hello
```

## Requirements

- Python 3.11+
- gcc 11+ (or clang 14+)
- Linux or macOS (Windows: WSL 2)
- For HTTP/TLS: `libcurl4-openssl-dev`, `libssl-dev`

See [docs/getting-started/installation.md](docs/getting-started/installation.md) for full setup.

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

279 unit tests + compile+run integration tests.  
Integration tests are automatically skipped if gcc is not on PATH.

## VibeCoder UI

```bash
pip install "dictum[server]"
python ui/backend_server.py
# Open http://localhost:8765
```

Or with Docker:
```bash
docker build -t dictum-vibecoder .
docker run -p 8765:8765 dictum-vibecoder
```

---

## Honest capability claim

> **"Dictum v5 — natural-language transpiler to C. Works for programs using console I/O, arithmetic, structs, recursion, conditionals, loops, basic file I/O, HTTP, TCP, TLS, and JSON."**

The production-readiness test program from the roadmap now compiles and runs:

```dictum
program HttpClient:
    use Http
    use Json
    use Console

    keep Url as text with value "https://httpbin.org/json"
    keep Response as text with value ""
    attempt
        call Http.get with Url giving Response
    on failure with Err
        call Console.write_line with "Request failed"
        produce success with nothing
    end attempt

    keep Data as json value
    call Json.parse with Response giving Data
    keep Title as text with value ""
    call Json.get_string with Data and "slideshow" giving Title
    call Console.write_line with Title
end program
```

---

## License

MIT. See LICENSE.
