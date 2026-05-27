# Dictum REPL

Interactive read-eval-print loop for the Dictum language.

## Usage

```bash
pip install -r requirements.txt
python repl.py                          # default: C backend
python repl.py --backend cpp --cpp-standard 20
python repl.py --target embedded
```

## Commands

| Command | Description |
|---|---|
| `:help` | Show available commands |
| `:backend c\|cpp` | Switch transpile backend |
| `:mode validate\|novalidate` | Toggle type validation |
| `:clear` | Clear session history |
| `:quit` | Exit the REPL |

Multi-line input: end a line with `\` to continue on the next.
