#!/usr/bin/env python3
"""
dictumc — Dictum Compiler CLI v5.0
Usage:
  dictumc <file.dict> [options]

Options:
  --backend c|cpp      Target backend (default: c)
  --cpp-standard 17|20 C++ standard (default: 17)
  --namespace <name>   Wrap output in C++ namespace
  --validate           Validate only, don't emit
  --compile            Transpile then compile with gcc/g++
  --output <file>      Output file (default: stdout)
  --makefile           Also write a Makefile next to the output file
  --summary            Print AST summary
  --grammar            Enable grammar-guided parsing (strict mode)
  --stdlib             Use stdlib-aware transpiler
  --no-validate        Skip validation
"""

import sys
import os
import argparse
import subprocess
import tempfile

def main() -> int:
    p = argparse.ArgumentParser(prog="dictumc", description="Dictum Compiler v4.0")
    p.add_argument("file", nargs="?", help="Input .dict source file")
    p.add_argument("--backend", choices=["c", "cpp"], default="c")
    p.add_argument("--cpp-standard", type=int, choices=[17, 20, 23], default=17)
    p.add_argument("--namespace", default="")
    p.add_argument("--validate", action="store_true", help="Validate only")
    p.add_argument("--no-validate", action="store_true", help="Skip validation")
    p.add_argument("--compile", action="store_true", help="Compile emitted C/C++")
    p.add_argument("--output", "-o", default="", help="Output path")
    p.add_argument("--makefile", action="store_true", help="Write Makefile alongside output (C backend only)")
    p.add_argument("--summary", action="store_true")
    p.add_argument("--grammar", action="store_true", help="Grammar-constrained parsing")
    p.add_argument("--stdlib", action="store_true", help="Stdlib-aware transpiler")
    p.add_argument("--emit-ast", action="store_true", help="Dump AST repr")
    args = p.parse_args()

    # Read source
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as fh:
                source = fh.read()
        except FileNotFoundError:
            print(f"dictumc: error: file '{args.file}' not found", file=sys.stderr)
            return 1
    else:
        if sys.stdin.isatty():
            p.print_help()
            return 0
        source = sys.stdin.read()

    # Import
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from dictumc.transpiler import Transpiler, StdlibTranspiler
    from dictumc.validator import ValidationError

    TranspilerClass = StdlibTranspiler if args.stdlib else Transpiler

    try:
        t = TranspilerClass(
            source=source,
            backend=args.backend,
            cpp_standard=args.cpp_standard,
            namespace=args.namespace,
        )
        result = t.run(
            validate=not args.no_validate,
            summary=args.summary,
            grammar_guided=args.grammar,
        )
    except (SyntaxError, ValidationError) as e:
        print(f"dictumc: error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"dictumc: internal error: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        return 1

    # Warnings
    for w in result.get("warnings", []):
        print(f"dictumc: warning: {w}", file=sys.stderr)

    if args.validate:
        print("dictumc: validation passed", file=sys.stderr)
        return 0

    if args.emit_ast:
        import pprint
        pprint.pprint(result["ast"])
        return 0

    if args.summary and "summary" in result:
        print(result["summary"])

    code: str = result["code"]

    # Determine output extension
    ext = ".cpp" if args.backend == "cpp" else ".c"
    out_src = args.output if args.output and not args.compile else ""

    if args.compile:
        # Write to temp file, compile with gcc/g++
        compiler = "g++" if args.backend == "cpp" else "gcc"
        flags = [f"-std=c++{args.cpp_standard}"] if args.backend == "cpp" else ["-std=c11"]
        flags += ["-O2", "-lm"]
        binary_out = args.output or (os.path.splitext(args.file)[0] if args.file else "a.out")

        with tempfile.NamedTemporaryFile(suffix=ext, mode='w', delete=False,
                                         encoding='utf-8') as tf:
            tf.write(code)
            src_path = tf.name

        cmd = [compiler] + flags + [src_path, "-o", binary_out]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        os.unlink(src_path)

        if proc.returncode != 0:
            print(f"dictumc: compile error:\n{proc.stderr}", file=sys.stderr)
            return 1
        print(f"dictumc: compiled to '{binary_out}'", file=sys.stderr)

        # Also write the .c/.cpp source for inspection
        if args.output:
            src_out = args.output + ext
            with open(src_out, "w", encoding="utf-8") as fh:
                fh.write(code)
        return 0

    # Write code
    if out_src:
        with open(out_src, "w", encoding="utf-8") as fh:
            fh.write(code)
        print(f"dictumc: wrote '{out_src}'", file=sys.stderr)
    else:
        sys.stdout.write(code)

    # Write header if generated
    if "h_code" in result:
        h_path = (os.path.splitext(out_src)[0] + ".h") if out_src else None
        if h_path:
            with open(h_path, "w", encoding="utf-8") as fh:
                fh.write(result["h_code"])
    elif "hpp_code" in result:
        hpp_path = (os.path.splitext(out_src)[0] + ".hpp") if out_src else None
        if hpp_path:
            with open(hpp_path, "w", encoding="utf-8") as fh:
                fh.write(result["hpp_code"])

    # P2.1: write Makefile if requested and backend is C
    if args.makefile and args.backend == "c" and result.get("makefile"):
        mf_dir  = os.path.dirname(out_src) if out_src else "."
        mf_path = os.path.join(mf_dir, "Makefile")
        prog_name = os.path.splitext(os.path.basename(out_src))[0] if out_src else "program"
        # Re-generate with correct program name
        from dictumc.emit_c import CEmitter
        mf_text = result["makefile"].replace("program:", f"{prog_name}:") \
                                     .replace("program.c", f"{prog_name}.c") \
                                     .replace("-o program ", f"-o {prog_name} ")
        with open(mf_path, "w", encoding="utf-8") as fh:
            fh.write(mf_text)
        print(f"dictumc: wrote '{mf_path}'", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
