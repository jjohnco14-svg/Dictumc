# Quick Start

## Installation

```bash
pip install dictum-lang
```

## Your First Program

Create `hello.dict`:

```dictum
program Hello:
    print the text "Hello, World!" and newline
end program
```

Transpile and run:

```bash
dictumc hello.dict --backend c --compile
./hello
```

Output:
```
Hello, World!
```

## Switch to C++

```bash
dictumc hello.dict --backend cpp --cpp-standard 20 --compile
./hello
```

## Use a Snippet

```bash
dictumc --snippet robot > robot.dict
dictumc robot.dict --backend c --compile
```

## Interactive REPL

```bash
dictumc --repl
dictum> keep X as whole number with value 42
dictum> print the text "X=" and X and newline
```

## VS Code Extension

1. Install from marketplace: search "Dictum"
2. Open any `.dict` file
3. Press `Ctrl+Shift+T` to transpile
4. Press `Ctrl+Shift+B` to transpile + compile
