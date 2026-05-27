# Memory Model

Dictum's C backend follows a simple, safe memory model. All allocation goes through the core allocator which enforces hard size limits and NULL-checks.

## Allocator Rules

- `dictum_alloc(size)` — wraps `calloc`; aborts on NULL or oversized request (limit: 1 GB).
- `dictum_free(ptr)` — wraps `free`; ignores NULL safely.
- `dictum_strdup(s)` — bounded duplicate; returns NULL on oversize.
- `dictum_realloc(ptr, new_size)` — safe realloc with size check.

## Handle Registry

Any `FILE*`, socket, or TLS handle opened through the stdlib is registered in a thread-safe handle registry. On program exit, unreleased handles are logged (in `DICTUM_DEBUG` builds) so leaks are visible during development.

## Strings (`dictum_text`)

`dictum_text` is typedef'd to `const char*`. All stdlib string functions return heap-allocated strings that the caller owns. Always pass them to `dictum_free` when done, or accept that they live until process exit (acceptable for short programs).

The maximum string size is 1 GB (`DICTUM_MAX_STRING`). Operations that would exceed this return NULL.

## Arrays (`list of`)

Arrays declared with `list of whole number` emit as fixed-size C arrays on the stack. They are not heap-allocated and do not need freeing.

## Error Propagation

Stdlib functions that fail set the thread-local `dictum_last_error` buffer (256 bytes) and return a failure value (NULL for pointers, a `dictum_result_t` with `success = false` for handle-returning calls).

The `attempt` block clears this buffer before running its body and branches on whether it is set afterward:

```c
dictum_error_clear();
<body>;
if (!DICTUM_HAS_ERROR()) {
    /* success path */
} else {
    const char* Err = dictum_error_last();
    /* failure path */
}
```
