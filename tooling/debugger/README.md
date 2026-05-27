# Dictum Debugger

GDB DAP (Debug Adapter Protocol) bridge for Dictum programs.

## Usage

```bash
# Compile with debug symbols
python -m dictumc program.dict --backend c --debug-symbols -o program.c
gcc -g program.c -o program

# Start debugger
python dictum_debugger.py --target ./program --port 4711
```

## Features

- Source-mapped breakpoints (Dictum line ↔ C line)
- Variable inspection with Dictum type names
- Step-over / step-into / step-out
- Watch expressions in Dictum syntax
- VS Code DAP integration via port 4711
