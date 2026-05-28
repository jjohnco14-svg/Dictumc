# Performance Notes

Dictum v5 targets correctness and readability over micro-optimization. That said, the emitted C is standard C11 compiled with `-O2`, so LLVM/GCC optimizers apply normally.

## What is fast

- Arithmetic and control flow: identical to hand-written C at `-O2`.
- Struct field access: zero overhead (direct member dereference).
- `dictum_text` operations: thin wrappers around `string.h`; `strlen`, `strstr`, `memcpy`.
- File I/O: direct `fread`/`fwrite`; no extra copies.

## Known overhead sources

- String allocation: most `dictum_text_*` functions return heap-allocated strings. Each call is an `malloc` + potential `free`. For tight loops over strings, consider calling into C directly via `import from C`.
- JSON: the built-in `dictum_json.c` uses a fixed pool of 256 objects. If you need to parse thousands of JSON blobs in a loop, vendor a faster parser (simdjson, yyjson) via the C interop layer.
- HTTP: `dictum_http.c` opens a new TCP connection per request. There is no connection pooling. For bulk HTTP, use a loop with explicit keep-alive headers or drop to the Net module.

## Compile flags

The stdlib Makefile uses `-O2 -fwrapv -fno-strict-aliasing`. For release builds of your program, add `-O3 -march=native`:

```makefile
CFLAGS += -O3 -march=native
```

## Profiling

Because Dictum emits plain C, you can profile with `gprof`, `perf`, or `valgrind` without any special steps:

```bash
gcc -pg -O2 program.c stdlib/libdictum_stdlib.a -Istdlib -lm -o program
./program
gprof program gmon.out | head -30
```
