#!/usr/bin/env python3
"""
Dictum REPL v5.0 — Interactive Mode
Read-Eval-Print Loop with stateful session, history, and vibecoding support.

Updated for v5: imports from split dictumc package instead of monolith.
"""

import sys
import os
import atexit
from typing import List, Optional, Dict, Any

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

try:
    import readline
except ImportError:
    readline = None  # Windows fallback

# v5 imports from split dictumc package
from dictumc.lexer import Lexer, TokenType
from dictumc.parser import Parser
from dictumc.validator import Validator, ValidationError
from dictumc.emit_c import CEmitter
from dictumc.emit_cpp import CppEmitter
from dictumc.transpiler import Transpiler, StdlibTranspiler
from dictumc.grammar import DictumGrammar
from dictumc.stdlib_registry import STDLIB_ACTION_FAMILIES, DICTUM_STDLIB_TYPES
from dictumc.ast_nodes import (
    Node, Program, VarDecl, Action, Shape, Literal, FuncCall, Identifier
)

DICTUM_VERSION = "5.0.0"
REPL_BANNER = f"""
╔═══════════════════════════════════════════════╗
║          Dictum Language REPL v{DICTUM_VERSION}          ║
║  Type Dictum code. `help` for commands.       ║
║  `exit` or Ctrl-D to quit.                    ║
╚═══════════════════════════════════════════════╝
"""


class REPLSession:
    """Persistent REPL session with accumulated declarations."""

    def __init__(self, backend: str = 'c', cpp_standard: int = 17):
        self.backend = backend
        self.cpp_standard = cpp_standard
        self.globals_ast: List[Node] = []
        self.scope_vars: Dict[str, str] = {}
        self.actions: Dict[str, Any] = {}
        self.shapes: Dict[str, Any] = {}
        self.history_file = os.path.expanduser("~/.dictum_history")
        self._load_history()

    def _load_history(self):
        if readline and os.path.exists(self.history_file):
            readline.read_history_file(self.history_file)
        if readline:
            atexit.register(self._save_history)

    def _save_history(self):
        if readline:
            readline.write_history_file(self.history_file)

    def _make_program_source(self, stmt: str) -> str:
        """Wrap a statement in a full program context with accumulated globals."""
        return f"program REPL:\n    {stmt}\nend program"

    def transpile(self, source: str) -> Dict[str, Any]:
        t = StdlibTranspiler(source, backend=self.backend, cpp_standard=self.cpp_standard)
        return t.run(validate=True)

    def eval_line(self, line: str) -> Optional[str]:
        source = self._make_program_source(line)
        try:
            result = self.transpile(source)
            return result.get("code", "")
        except Exception as e:
            return f"Error: {e}"


class DictumREPL:
    """Main REPL driver."""

    COMMANDS = {
        "help":    "Show this help message",
        "exit":    "Exit the REPL",
        "quit":    "Exit the REPL",
        "clear":   "Clear session state",
        "backend": "Switch backend: backend c | backend cpp",
        "skills":  "List available stdlib modules",
    }

    def __init__(self, backend: str = 'c'):
        self.session = REPLSession(backend=backend)
        self._multiline_buf: List[str] = []

    def _handle_command(self, cmd: str) -> bool:
        parts = cmd.strip().split()
        if not parts:
            return False
        verb = parts[0].lower()
        if verb in ("exit", "quit"):
            print("Goodbye.")
            sys.exit(0)
        if verb == "help":
            print("\nCommands:")
            for c, desc in self.COMMANDS.items():
                print(f"  {c:<10} {desc}")
            print()
            return True
        if verb == "clear":
            self.session = REPLSession(backend=self.session.backend)
            print("Session cleared.")
            return True
        if verb == "backend" and len(parts) >= 2:
            self.session.backend = parts[1].lower()
            print(f"Backend set to: {self.session.backend}")
            return True
        if verb == "skills":
            mods = sorted({k.split('.')[0] for k in STDLIB_ACTION_FAMILIES})
            print("Available stdlib modules:", ", ".join(mods))
            return True
        return False

    def run(self):
        print(REPL_BANNER)
        while True:
            try:
                prompt = "... " if self._multiline_buf else "dictum> "
                line = input(prompt)
            except EOFError:
                print("\nGoodbye.")
                break
            except KeyboardInterrupt:
                self._multiline_buf = []
                print()
                continue

            stripped = line.strip()

            # Empty line flushes multiline buffer
            if not stripped:
                if self._multiline_buf:
                    full = "\n    ".join(self._multiline_buf)
                    self._multiline_buf = []
                    output = self.session.eval_line(full)
                    if output:
                        print(output)
                continue

            if self._handle_command(stripped):
                continue

            # Multiline detection: line ends with ':'
            if stripped.endswith(':'):
                self._multiline_buf.append(stripped)
                continue

            if self._multiline_buf:
                self._multiline_buf.append("    " + stripped)
                continue

            output = self.session.eval_line(stripped)
            if output:
                print(output)


def main():
    import argparse
    p = argparse.ArgumentParser(description="Dictum REPL v5")
    p.add_argument("--backend", default="c", choices=["c", "cpp"], help="Emit C or C++")
    args = p.parse_args()
    DictumREPL(backend=args.backend).run()


if __name__ == "__main__":
    main()
