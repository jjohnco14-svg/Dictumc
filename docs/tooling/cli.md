# CLI Reference

## Basic Usage

```bash
dictumc file.dict                    # Transpile to C
dictumc file.dict --backend cpp      # Transpile to C++
dictumc file.dict --compile          # Transpile + compile
dictumc --example Arena              # Run built-in example
dictumc --repl                       # Interactive mode
dictumc --snippet llm                # Print LLM snippet
dictumc --stdlib-info llm            # Show LLM API
dictumc --grammar-guided             # Validate grammar constraints
```

## Flags

| Flag | Description |
|------|-------------|
| `--backend {c,cpp}` | Target backend (default: c) |
| `--cpp-standard {17,20,23}` | C++ standard version |
| `--compile` | Compile emitted code |
| `--header` | Emit header file |
| `--namespace NAME` | C++ namespace |
| `--target TARGET` | Platform target (esp32s3, pi5, etc.) |
| `--stdlib` | Enable stdlib type resolution |
| `--robot` | Enable robotics shim |
| `--no-validate` | Skip safety validation |
| `--summary` | Show natural language summary |
| `--test` | Run integration tests |
| `--test7` | Run Phase 7 stdlib tests |
| `--grammar-guided` | Grammar-constrained validation |
| `--grammar-generate` | Grammar-constrained LLM generation |

## VS Code Commands

| Command | Keybinding |
|---------|-----------|
| Dictum: Transpile | `Ctrl+Shift+T` |
| Dictum: Transpile & Compile | `Ctrl+Shift+B` |
| Dictum: Insert Snippet | `Ctrl+Shift+S` |

## File Extensions

| Extension | Purpose |
|-----------|---------|
| `.dict` | Dictum source file |
| `.dictum` | Alternative extension |
| `.h` / `.hpp` | Generated header |
| `.c` / `.cpp` | Generated source |
