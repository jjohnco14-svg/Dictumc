# Dictum Python API

The `dictumc` package exposes three transpiler classes.

## `Transpiler`

Basic transpiler for programs that don't use stdlib modules.

```python
from dictumc.transpiler import Transpiler

source = """program Hello:
    print the text "Hello" and newline
end program"""

t = Transpiler(source, backend='c')   # or backend='cpp'
result = t.run()

print(result['code'])      # emitted C source
print(result['makefile'])  # auto-generated Makefile
print(result['warnings'])  # list of validation warnings
```

### `Transpiler.run()` return keys

| Key          | Type           | Description                                      |
|--------------|----------------|--------------------------------------------------|
| `code`       | `str`          | Emitted C (or C++) source                        |
| `ast`        | `list[Node]`   | Parsed AST nodes                                 |
| `warnings`   | `list[str]`    | Validation warnings (non-fatal)                  |
| `makefile`   | `str \| None`  | Auto-generated Makefile (C backend only)         |
| `h_code`     | `str`          | Header file for exported symbols (if any)        |

## `StdlibTranspiler`

Extends `Transpiler` with stdlib type and action registrations. Use when the program calls `use Http`, `use Json`, etc.

```python
from dictumc.transpiler import StdlibTranspiler

t = StdlibTranspiler(source, backend='c')
result = t.run()

print(result['stdlib_headers'])   # list of stdlib headers included
print(result['needs_robotics'])   # True if robotics module was referenced
```

## `get_makefile(program_name, stdlib_dir)`

Call on the `CEmitter` directly, or via the `makefile` key in `result`:

```python
result = t.run()
makefile_text = result['makefile']
with open('Makefile', 'w') as f:
    f.write(makefile_text)
```

The emitted Makefile automatically includes the correct `-l` linker flags based on which modules are `use`d:

| Module    | Added flags              |
|-----------|--------------------------|
| `Http`    | `-lcurl`                 |
| `Tls`     | `-lssl -lcrypto`         |
| `Thread`  | `-lpthread`              |
| `Math`    | `-lm` (always present)   |
| `Shm`     | `-lrt`                   |

## Command-Line Interface

```bash
dictumc program.dict              # transpile to C, print to stdout
dictumc program.dict -o prog.c    # write to file
dictumc program.dict --backend cpp -o prog.cpp
dictumc program.dict --makefile   # also write Makefile
```
