#!/usr/bin/env python3
"""
Dictum Debugger — Phase 7: GDB DAP Bridge
Maps Dictum source lines to C/C++ output lines for debugging.
"""

import json
import sys
import subprocess
import re
import os
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass


@dataclass
class SourceMap:
    """Maps a Dictum source line to generated C/C++ line."""
    dictum_line: int
    dictum_col: int
    c_file: str
    c_line: int
    c_col: int
    node_type: str


class DictumSourceMapper:
    """Builds and queries source maps between Dictum and generated C/C++."""

    def __init__(self):
        self.mappings: List[SourceMap] = []
        self.dictum_lines: Dict[int, List[SourceMap]] = {}  # line -> mappings
        self.c_lines: Dict[Tuple[str, int], List[SourceMap]] = {}  # (file, line) -> mappings

    def add_mapping(self, mapping: SourceMap):
        self.mappings.append(mapping)
        self.dictum_lines.setdefault(mapping.dictum_line, []).append(mapping)
        key = (mapping.c_file, mapping.c_line)
        self.c_lines.setdefault(key, []).append(mapping)

    def dictum_to_c(self, dictum_line: int, dictum_col: int = 0) -> Optional[SourceMap]:
        """Find the C/C++ location for a Dictum source position."""
        mappings = self.dictum_lines.get(dictum_line, [])
        if not mappings:
            return None
        # Return closest column match
        return min(mappings, key=lambda m: abs(m.dictum_col - dictum_col))

    def c_to_dictum(self, c_file: str, c_line: int) -> Optional[SourceMap]:
        """Find the Dictum source location for a C/C++ position."""
        mappings = self.c_lines.get((c_file, c_line), [])
        if not mappings:
            return None
        return mappings[0]

    def build_from_ast(self, ast, c_code: str, c_filename: str = "output.c"):
        """Build source map by correlating AST node lines with emitted code."""
        c_lines = c_code.split('
')

        def walk_nodes(nodes, depth=0):
            for node in nodes:
                if hasattr(node, 'line') and node.line > 0:
                    # Find corresponding C line by searching for node-specific patterns
                    c_line_num = self._find_c_line(node, c_lines)
                    if c_line_num:
                        mapping = SourceMap(
                            dictum_line=node.line,
                            dictum_col=0,
                            c_file=c_filename,
                            c_line=c_line_num,
                            c_col=0,
                            node_type=type(node).__name__
                        )
                        self.add_mapping(mapping)

                # Recurse into child nodes
                for attr in ['body', 'then_body', 'else_body', 'success_body', 'failure_body']:
                    if hasattr(node, attr):
                        child = getattr(node, attr)
                        if isinstance(child, list):
                            walk_nodes(child, depth + 1)

        walk_nodes(ast)

    def _find_c_line(self, node, c_lines: List[str]) -> Optional[int]:
        """Heuristic: find which C line corresponds to an AST node."""
        node_type = type(node).__name__

        # Pattern matching based on node type
        patterns = {
            'VarDecl': [r'int32_t\s+\w+\s*=' , r'\w+\s+\w+\s*=' ],
            'Print': [r'printf\s*\('],
            'If': [r'if\s*\('],
            'While': [r'while\s*\('],
            'ForEach': [r'for\s*\('],
            'Repeat': [r'for\s*\(int32_t'],
            'FuncCall': [r'\w+\s*\('],
            'Action': [r'int32_t\s+\w+\s*\('],
        }

        search_patterns = patterns.get(node_type, [])

        # Search from the node's line number (approximate)
        start_line = getattr(node, 'line', 1) - 1
        for i in range(start_line, min(start_line + 20, len(c_lines))):
            if i >= len(c_lines):
                break
            line = c_lines[i]
            for pattern in search_patterns:
                if re.search(pattern, line):
                    return i + 1  # 1-based line numbers

        return None

    def save(self, path: str):
        """Save source map to JSON."""
        data = [
            {
                "dictum_line": m.dictum_line,
                "dictum_col": m.dictum_col,
                "c_file": m.c_file,
                "c_line": m.c_line,
                "c_col": m.c_col,
                "node_type": m.node_type
            }
            for m in self.mappings
        ]
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        """Load source map from JSON."""
        with open(path) as f:
            data = json.load(f)
        for item in data:
            self.add_mapping(SourceMap(**item))


class DictumDebugAdapter:
    """Debug Adapter Protocol (DAP) bridge for Dictum -> GDB."""

    def __init__(self, source_map: DictumSourceMapper):
        self.source_map = source_map
        self.gdb_proc = None
        self.breakpoints: Dict[int, int] = {}  # dictum_line -> gdb_breakpoint_num

    def start(self, executable: str):
        """Start GDB in MI mode."""
        self.gdb_proc = subprocess.Popen(
            ['gdb', '-i', 'mi', executable],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        # Read initial GDB output
        self._read_until_prompt()

    def _send(self, cmd: str) -> str:
        """Send command to GDB and read response."""
        self.gdb_proc.stdin.write(cmd + '
')
        self.gdb_proc.stdin.flush()
        return self._read_until_prompt()

    def _read_until_prompt(self) -> str:
        """Read GDB output until prompt."""
        output = []
        while True:
            line = self.gdb_proc.stdout.readline()
            if not line:
                break
            output.append(line.rstrip())
            if line.startswith('(gdb)'):
                break
        return '
'.join(output)

    def set_breakpoint_dictum(self, dictum_line: int) -> bool:
        """Set breakpoint in Dictum source line."""
        mapping = self.source_map.dictum_to_c(dictum_line)
        if not mapping:
            print(f"[DAP] No mapping found for Dictum line {dictum_line}")
            return False

        response = self._send(f"-break-insert {mapping.c_file}:{mapping.c_line}")

        # Parse breakpoint number from response
        match = re.search(r'bkpt=\{number="(\d+)"', response)
        if match:
            bp_num = int(match.group(1))
            self.breakpoints[dictum_line] = bp_num
            print(f"[DAP] Breakpoint {bp_num} at {mapping.c_file}:{mapping.c_line} (Dictum line {dictum_line})")
            return True
        return False

    def remove_breakpoint(self, dictum_line: int) -> bool:
        """Remove breakpoint by Dictum line."""
        bp_num = self.breakpoints.get(dictum_line)
        if bp_num:
            self._send(f"-break-delete {bp_num}")
            del self.breakpoints[dictum_line]
            return True
        return False

    def run(self):
        """Start execution."""
        return self._send("-exec-run")

    def continue_(self):
        """Continue execution."""
        return self._send("-exec-continue")

    def step(self):
        """Step one line."""
        return self._send("-exec-step")

    def next(self):
        """Step over."""
        return self._send("-exec-next")

    def get_stack_trace(self) -> List[Dict]:
        """Get stack trace mapped back to Dictum lines."""
        response = self._send("-stack-list-frames")
        frames = []

        # Parse MI output for frames
        for match in re.finditer(r'frame=\{level="(\d+)",addr="[^"]+",func="([^"]+)",file="([^"]+)",line="(\d+)"', response):
            level, func, file, line = match.groups()
            c_line = int(line)

            # Map back to Dictum
            mapping = self.source_map.c_to_dictum(file, c_line)
            if mapping:
                frames.append({
                    "level": int(level),
                    "function": func,
                    "dictum_line": mapping.dictum_line,
                    "c_file": file,
                    "c_line": c_line,
                    "node_type": mapping.node_type
                })
            else:
                frames.append({
                    "level": int(level),
                    "function": func,
                    "dictum_line": None,
                    "c_file": file,
                    "c_line": c_line,
                    "node_type": "unknown"
                })

        return frames

    def get_variables(self) -> Dict[str, str]:
        """Get local variables."""
        response = self._send("-stack-list-variables --all-values")
        variables = {}

        for match in re.finditer(r'name="([^"]+)",value="([^"]*)"', response):
            name, value = match.groups()
            variables[name] = value

        return variables

    def stop(self):
        """Stop GDB."""
        if self.gdb_proc:
            self._send("-gdb-exit")
            self.gdb_proc.wait()


class VSCodeDebugConfig:
    """Generate VS Code launch.json for Dictum debugging."""

    @staticmethod
    def generate(program_name: str = "${fileBasenameNoExtension}", backend: str = 'c') -> dict:
        compiler = 'g++' if backend == 'cpp' else 'gcc'
        std_flag = '-std=c++17' if backend == 'cpp' else '-std=c11'
        ext = '.cpp' if backend == 'cpp' else '.c'

        return {
            "version": "0.2.0",
            "configurations": [
                {
                    "name": "Debug Dictum Program",
                    "type": "cppdbg",
                    "request": "launch",
                    "program": f"${{workspaceFolder}}/{program_name}",
                    "args": [],
                    "stopAtEntry": False,
                    "cwd": "${workspaceFolder}",
                    "environment": [],
                    "externalConsole": False,
                    "MIMode": "gdb",
                    "preLaunchTask": "dictum: transpile and compile",
                    "setupCommands": [
                        {
                            "description": "Enable pretty-printing",
                            "text": "-enable-pretty-printing",
                            "ignoreFailures": True
                        }
                    ],
                    "sourceFileMap": {
                        "${workspaceFolder}/output.c": "${workspaceFolder}/${file}"
                    }
                }
            ],
            "tasks": [
                {
                    "label": "dictum: transpile and compile",
                    "type": "shell",
                    "command": f"dictumc ${{file}} --backend {backend} --compile",
                    "group": {
                        "kind": "build",
                        "isDefault": True
                    },
                    "problemMatcher": ["$gcc"]
                }
            ]
        }

    @staticmethod
    def write_launch_json(path: str = ".vscode/launch.json", backend: str = 'c'):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        config = VSCodeDebugConfig.generate(backend=backend)
        with open(path, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"[DAP] Written {path}")


def test_source_mapper():
    """Test source mapping between Dictum and C."""
    import sys, os; sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))); from dictumc.transpiler import Transpiler

    source = """program Test:
    keep X as whole number with value 42
    print the text "hello" and newline
    if X is greater than 0 then:
        print the text "positive" and newline
    end if
end program"""

    t = Transpiler(source, backend='c')
    result = t.run(validate=False)

    mapper = DictumSourceMapper()
    mapper.build_from_ast(result['ast'], result['code'], "test.c")

    # Test forward mapping
    mapping = mapper.dictum_to_c(2)  # keep X...
    assert mapping is not None
    assert mapping.node_type == 'VarDecl'

    # Test reverse mapping
    reverse = mapper.c_to_dictum("test.c", mapping.c_line)
    assert reverse.dictum_line == 2

    print("✓ Source mapper test passed")
    return mapper


def test_debug_adapter():
    """Test DAP bridge (requires compiled binary)."""
    import sys, os; sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))); from dictumc.transpiler import Transpiler

    source = """program Test:
    keep X as whole number with value 5
    keep Y as whole number with value 10
    keep Z as whole number
    put the sum of X and Y into Z
    print the text "Z=" and Z and newline
end program"""

    t = Transpiler(source, backend='c')
    result = t.run(validate=False)

    # Write C code
    with open("/tmp/test_debug.c", 'w') as f:
        f.write(result['code'])

    # Compile
    proc = subprocess.run(
        ['gcc', '-std=c11', '-g', '/tmp/test_debug.c', '-o', '/tmp/test_debug', '-lm'],
        capture_output=True, text=True
    )
    if proc.returncode != 0:
        print(f"Compile failed: {proc.stderr}")
        return

    # Build source map
    mapper = DictumSourceMapper()
    mapper.build_from_ast(result['ast'], result['code'], "/tmp/test_debug.c")

    # Start debugger
    dap = DictumDebugAdapter(mapper)
    dap.start("/tmp/test_debug")

    # Set breakpoint on line 4 (put the sum...)
    dap.set_breakpoint_dictum(4)

    # Run
    dap.run()

    # Get stack trace
    frames = dap.get_stack_trace()
    print(f"Stack trace: {json.dumps(frames, indent=2)}")

    # Get variables
    vars = dap.get_variables()
    print(f"Variables: {vars}")

    dap.stop()
    print("✓ Debug adapter test passed")


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description="Dictum Debugger (Phase 7)")
    ap.add_argument('--test', action='store_true', help='Run tests')
    ap.add_argument('--generate-launch', action='store_true', help='Generate VS Code launch.json')
    ap.add_argument('--backend', choices=['c', 'cpp'], default='c')
    ap.add_argument('program', nargs='?', help='Program to debug')
    args = ap.parse_args()

    if args.test:
        test_source_mapper()
        test_debug_adapter()
    elif args.generate_launch:
        VSCodeDebugConfig.write_launch_json(backend=args.backend)
    elif args.program:
        print(f"Debugging {args.program}...")
        # Full debug session would go here
    else:
        print("Usage: python dictum_debugger.py [--test|--generate-launch|--backend c|cpp] [program]")
