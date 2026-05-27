"""
Dictum C Emitter — emits ANSI C from the AST.
Extracted and heavily fixed from transpiler.py v3.3.

Phase 1-5 fixes applied:
  BUG-01:  `put ... into Z` auto-declares Z with inferred type if undeclared.
  BUG-04:  Module.function calls (Http.get) correctly routed via STDLIB_ACTION_FAMILIES.
  BUG-05:  `use Module` emits #include, never a function call.
  BUG-06:  `decimal number` / `decimal` mapped to `double`.
  BUG-09:  `produce success with X` emits `return X;` without noise comments.
  BUG-10:  Forward declarations emitted for ALL actions before main().
  MISSING-01: Arrays work: declaration, indexed read/write, `for each` emission.
  MISSING-02: `dictum_text` typedef added; Text.* ops wired to string helpers.
  MISSING-03: NewExpr emits malloc/calloc for C heap allocation.
  MISSING-05: `attempt` block emits complete C with setjmp/longjmp pattern.
  MISSING-09: truth value → bool; true/false consistent.
"""

from __future__ import annotations
import re
from typing import List, Dict, Optional, Set, Tuple, Any

from .ast_nodes import (
    Node, Program, Module, Shape, Method, Constructor, Destructor,
    VarDecl, Assignment, Action, FuncCall, Return, If, While, ForEach,
    Repeat, Attempt, Literal, Identifier, BinaryOp, UnaryOp,
    FieldAccess, IndexAccess, Assert, Print, ImportC, ImportCpp, ImportDict,
    UnsafeBlock, ExternFn, Transmute, Use, Bind, NewExpr, LambdaExpr,
    Possibilities,
)

# BUG-04 FIX: mapping of Module.function surface syntax → C function names
# Populated from STDLIB_ACTION_FAMILIES in the stdlib module.
_MODULE_CALL_MAP: Dict[str, str] = {
    "Text.grapheme_length":  "dictum_text_grapheme_length",
    "Text.grapheme_slice":   "dictum_text_grapheme_slice",
    "Text.grapheme_reverse": "dictum_text_grapheme_reverse",
    "Text.normalize":        "dictum_text_normalize",
    # Http (complete — HTTP + HTTPS auto-routing)
    "Http.get":              "dictum_http_get",
    "Http.post":             "dictum_http_post",
    "Http.post_form":        "dictum_http_post_form",
    "Http.put":              "dictum_http_put",
    "Http.delete":           "dictum_http_delete",
    "Http.patch":            "dictum_http_patch",
    # Console
    "Console.write":     "dictum_console_write",
    "Console.write_line":"dictum_console_write_line",
    "Console.read_line": "dictum_console_read_line",
    # Json
    "Json.parse":           "dictum_json_parse",
    "Json.get":             "dictum_json_get",
    "Json.get_string":      "dictum_json_get_string",
    "Json.get_int":         "dictum_json_get_int",
    "Json.get_float":       "dictum_json_get_float",
    "Json.get_bool":        "dictum_json_get_bool",
    "Json.set":             "dictum_json_set",
    "Json.stringify":       "dictum_json_stringify",
    "Json.destroy":         "dictum_json_destroy",
    "Json.length":          "dictum_json_length",
    "Json.array_length":    "dictum_json_array_length",
    "Json.get_at":          "dictum_json_get_at",
    "Json.get_int_at":      "dictum_json_get_int_at",
    "Json.get_float_at":    "dictum_json_get_float_at",
    "Json.get_object_at":   "dictum_json_get_object_at",
    "Json.get_path":        "dictum_json_get_path",
    # File
    "File.open":            "dictum_file_open",
    "File.read":            "dictum_file_read",
    "File.read_line":       "dictum_file_read_line",
    "File.read_all":        "dictum_file_read_all",
    "File.write":           "dictum_file_write",
    "File.seek":            "dictum_file_seek",
    "File.tell":            "dictum_file_tell",
    "File.flush":           "dictum_file_flush",
    "File.size":            "dictum_file_size",
    "File.exists":          "dictum_file_exists",
    "File.delete":          "dictum_file_delete",
    "File.append":          "dictum_file_append",
    "File.close":           "dictum_file_close",
    # Text module  (MISSING-02 + P1.6)
    "Text.length":          "dictum_text_length",
    "Text.utf8_length":     "dictum_text_utf8_length",
    "Text.find":            "dictum_text_find",
    "Text.find_from":       "dictum_text_find_from",
    "Text.slice":           "dictum_text_slice",
    "Text.join":            "dictum_text_join",
    "Text.split":           "dictum_text_split",
    "Text.trim":            "dictum_text_trim",
    "Text.to_upper":        "dictum_text_to_upper",
    "Text.to_lower":        "dictum_text_to_lower",
    "Text.replace":         "dictum_text_replace",
    "Text.compare":         "dictum_text_compare",
    "Text.starts_with":     "dictum_text_starts_with",
    "Text.ends_with":       "dictum_text_ends_with",
    "Text.contains":        "dictum_text_contains",
    "Text.format":          "dictum_text_format",
    "Text.from_int":        "dictum_text_from_int",
    "Text.from_float":      "dictum_text_from_float",
    # Legacy aliases — only kept for raw C passthrough; use Text.* for Dictum programs
    "Text.copy":            "strcpy",
    "Text.concat":          "strcat",
    # Net
    "Net.connect":       "dictum_net_connect",
    "Net.send":          "dictum_net_send",
    "Net.receive":       "dictum_net_receive",
    "Net.close":         "dictum_net_close",
    # Tls
    "Tls.wrap":          "dictum_tls_wrap",
}

# BUG-05 FIX: `use Module` → #include path mapping
_USE_INCLUDE_MAP: Dict[str, str] = {
    "Http":      "dictum_http.h",
    "Console":   "dictum_console.h",
    "Json":      "dictum_json.h",
    "File":      "dictum_file.h",
    "Net":       "dictum_net.h",
    "Tls":       "dictum_tls.h",
    "Text":      "dictum_text.h",
    "Thread":    "dictum_thread.h",
    "Mutex":     "dictum_mutex.h",
    "Channel":   "dictum_channel.h",
    "Semaphore": "dictum_semaphore.h",
    "Timer":     "dictum_timer.h",
    "Process":   "dictum_process.h",
    "Signal":    "dictum_signal.h",
    "Pipe":      "dictum_pipe.h",
    "Mmap":      "dictum_mmap.h",
    "Shm":       "dictum_shm.h",
    "Path":      "dictum_path.h",
    "Directory": "dictum_directory.h",
    "Device":    "dictum_device.h",
    "Csv":       "dictum_csv.h",
    "Event":     "dictum_event.h",
    "Math":      "math.h",
    "Io":        "stdio.h",
}


class CEmitter:
    def __init__(self) -> None:
        self.output: List[str] = []
        self.indent: int = 0
        self._struct_buffer: List[str] = []
        self._action_buffer: List[str] = []
        self._extra_includes: List[str] = []     # BUG-05: `use` directives
        self._includes_emitted: bool = False
        self._fwd_sigs: List[str] = []           # BUG-10: forward declarations
        self._main_inits: List[str] = []          # room_for globals init in main
        # BUG-01 / MISSING-01: track declared variable types for auto-decl
        self.declared_vars: Dict[str, str] = {}
        self.shapes: Dict[str, Any] = {}         # name → fields list/dict
        # P2.1: track which stdlib modules are `use`d for Makefile generation
        self._used_modules: Set[str] = set()

        # MISSING-09 FIX + BUG-06 FIX
        self.types: Dict[str, str] = {
            "whole number":     "int32_t",
            "count":            "size_t",
            "fractional number":"double",
            "decimal number":   "double",   # BUG-06
            "decimal":          "double",   # BUG-06
            "truth value":      "bool",     # MISSING-09
            "bool":             "bool",
            "byte":             "uint8_t",
            "text":             "dictum_text",   # MISSING-02
            "handle to bytes":  "void*",
            "nothing":          "void",
            "u8":               "uint8_t",
            "u16":              "uint16_t",
            "u32":              "uint32_t",
            "i32":              "int32_t",
            "i64":              "int64_t",
            "u64":              "uint64_t",
            "result":           "void*",
        }
        self.actions: Set[str] = set()

    # ------------------------------------------------------------------
    def emit(self, line: str) -> None:
        self.output.append("    " * self.indent + line)

    def type_to_c(self, t: str) -> str:
        if t.startswith('*'):
            rest = t[1:].strip()
            if rest.startswith('volatile'):
                inner = rest[8:].strip()
                return f"volatile {self.types.get(inner, inner.replace(' ', '_'))}*"
            return f"{self.types.get(rest, rest.replace(' ', '_'))}*"
        # Strip 'list of <type>' prefix form (MISSING-01 FIX)
        if t.startswith('list of '):
            t = t[len('list of '):].strip()
        elif t.startswith('array of '):
            t = t[len('array of '):].strip()
        # Strip trailing ' list' / ' array' suffix form
        for suffix in (' list', ' array'):
            if t.endswith(suffix):
                t = t[:-len(suffix)].strip()
                break
        return self.types.get(t, t.replace(" ", "_"))

    # ------------------------------------------------------------------
    # BUG-04 FIX: resolve Module.function names
    # ------------------------------------------------------------------
    def _resolve_call_name(self, name: str) -> str:
        if '.' in name:
            return _MODULE_CALL_MAP.get(name, name.replace('.', '_'))
        return name

    # ------------------------------------------------------------------
    # Expression → C string
    # ------------------------------------------------------------------
    def expr_to_c(self, node: Node) -> str:
        if isinstance(node, Literal):
            if isinstance(node.value, bool):
                return "true" if node.value else "false"
            if isinstance(node.value, str):
                if node.value in ("nothing", "null", "NULL"):
                    return "NULL"   # P7.2: nothing → NULL
                if node.value == "\n": return '"\\n"'
                return f'"{node.value}"'
            if isinstance(node.value, list):
                return "{" + ", ".join(str(v) for v in node.value) + "}"
            if node.value is None:
                return "NULL"
            return str(node.value)
        elif isinstance(node, Identifier):
            return node.name
        elif isinstance(node, FieldAccess):
            return f"{node.obj}.{node.field}"
        elif isinstance(node, IndexAccess):
            idx = self.expr_to_c(node.index)
            return f"{node.collection}[{idx}]"
        elif isinstance(node, BinaryOp):
            left = self.expr_to_c(node.left)
            right = self.expr_to_c(node.right)
            if right in ('"empty"', "'empty'"):
                right = 'NULL'
            if node.op == 'pow':
                return f"pow({left}, {right})"
            return f"({left} {node.op} {right})"
        elif isinstance(node, UnaryOp):
            op = node.op
            operand = self.expr_to_c(node.operand)
            if op == "count":   return f"sizeof({operand}) / sizeof({operand}[0])"
            if op == "length":  return f"strlen({operand})"
            if op == "tanh":    return f"tanh({operand})"
            if op == "sqrt":    return f"sqrt({operand})"
            if op == "exp":     return f"exp({operand})"
            if op == "sin":     return f"sin({operand})"
            if op == "cos":     return f"cos({operand})"
            if op == "room_for":return f"(void*)malloc({operand})"  # MISSING-03
            if op == "addrof":  return f"(&{operand})"
            if op == "deref":   return f"(*{operand})"
            return f"({op}{operand})"
        elif isinstance(node, Transmute):
            expr = self.expr_to_c(node.expr)
            type_ = self.type_to_c(node.type)
            return f"(({type_}){expr})"
        elif isinstance(node, NewExpr):
            # MISSING-03 FIX: NewExpr → calloc in C
            type_c = self.type_to_c(node.type_name.replace('.', '_'))
            if node.args:
                args = ", ".join(self.expr_to_c(a) for a in node.args)
                return f"calloc(1, sizeof({type_c})) /* new {node.type_name}({args}) */"
            return f"calloc(1, sizeof({type_c}))"
        elif isinstance(node, FuncCall):
            c_name = self._resolve_call_name(node.name)  # BUG-04
            args = ", ".join(self.expr_to_c(a) for a in node.args)
            if c_name in ('success', '__produce_success'):
                return args
            if c_name == 'failure':
                return f"/* failure: {args} */ 0"
            return f"{c_name}({args})"
        return f"/* expr: {type(node).__name__} */"

    def lvalue_to_c(self, target: str) -> str:
        return target

    # ------------------------------------------------------------------
    # Infer C type from expression (BUG-01 helper)
    # ------------------------------------------------------------------
    def _infer_type_from_expr(self, node: Node) -> Optional[str]:
        if isinstance(node, Literal):
            if isinstance(node.value, bool):  return "bool"
            if isinstance(node.value, int):   return "int32_t"
            if isinstance(node.value, float): return "double"
            if isinstance(node.value, str):   return "dictum_text"
        if isinstance(node, Identifier):
            return self.declared_vars.get(node.name)
        if isinstance(node, BinaryOp):
            lt = self._infer_type_from_expr(node.left)
            rt = self._infer_type_from_expr(node.right)
            if node.op in ('==', '!=', '>', '<', '>=', '<='):
                return "bool"
            return lt or rt
        if isinstance(node, UnaryOp):
            if node.op == 'room_for': return "void*"
            return self._infer_type_from_expr(node.operand)
        if isinstance(node, FuncCall):
            return None   # unknown without action table
        if isinstance(node, NewExpr):
            return self.type_to_c(node.type_name.replace('.', '_')) + "*"
        return None

    # ------------------------------------------------------------------
    # BUG-10 FIX: collect forward declaration signatures
    # ------------------------------------------------------------------
    def _collect_fwd_sig(self, node: Action) -> Optional[str]:
        params = ", ".join(f"{self.type_to_c(ptype)} {pname}" for pname, ptype in node.params)
        if not params:
            params = "void"
        ret = self.type_to_c(node.ret_type) if node.ret_type != 'result' else 'void*'
        return f"{ret} {node.name}({params})"

    # ------------------------------------------------------------------
    # Node emission
    # ------------------------------------------------------------------
    def emit_node(self, node: Node) -> None:
        # ----------------------------------------------------------------
        if isinstance(node, Program):
            # Collect `use` and `polyglot import` directives BEFORE emitting (BUG-05)
            for stmt in node.body:
                if isinstance(stmt, Use):
                    # P2.1: track for Makefile generation
                    self._used_modules.add(stmt.path)
                    inc_path = _USE_INCLUDE_MAP.get(stmt.path,
                                                     f"dictum_{stmt.path.lower()}.h")
                    if stmt.is_system or not inc_path.startswith('dictum_'):
                        inc_line = f"#include <{inc_path}>"
                    else:
                        inc_line = f'#include "{inc_path}"'
                    if inc_line not in self._extra_includes:
                        self._extra_includes.append(inc_line)
                else:
                    # Polyglot import and build directives
                    try:
                        from .polyglot_ast import PolyglotImport, BuildDirective
                        if isinstance(stmt, PolyglotImport):
                            inc = f'#include "{stmt.module_name}_polyglot.h"  /* polyglot import {stmt.module_name} via {stmt.pattern} */'
                            if inc not in self._extra_includes:
                                self._extra_includes.append(inc)
                        elif isinstance(stmt, BuildDirective):
                            if stmt.kind == 'link':
                                self._extra_includes.append(f'/* #[link "{stmt.value}"] — add -l{stmt.value} to LDFLAGS */')
                            elif stmt.kind in ('cflags', 'ldflags', 'include_path'):
                                self._extra_includes.append(f'/* #[{stmt.kind} "{stmt.value}"] */')
                    except ImportError:
                        pass
            # PHASE 0: system includes
            self.emit("#include <stdint.h>")
            self.emit("#include <stdbool.h>")
            self.emit("#include <stdio.h>")
            self.emit("#include <stdlib.h>")
            self.emit("#include <string.h>")
            self.emit("#include <assert.h>")
            self.emit("#include <math.h>")
            self.emit("#include <setjmp.h>")   # MISSING-05: attempt support
            # P4.1: error handling for attempt blocks and stdlib modules.
            # Only include when stdlib modules are used OR attempt blocks are present
            # (avoids breaking old tests that compile without -I stdlib/).
            _needs_core = bool(self._extra_includes) or self._has_attempt_nodes(node)
            if _needs_core:
                self.emit('#include "dictum_core.h"')
                self.emit('#include "dictum_error.h"')
            # BUG-05: stdlib includes
            for inc in self._extra_includes:
                self.emit(inc)
            self._extra_includes.clear()
            # MISSING-02: dictum_text typedef
            self.emit("")
            self.emit("typedef const char* dictum_text;")
            self.emit("")
            self._includes_emitted = True
            # Flush buffered structs from pre-program shapes
            for line in self._struct_buffer:
                self.emit(line)
            self._struct_buffer.clear()
            # PHASE 1: shapes & enums
            for stmt in node.body:
                if isinstance(stmt, Shape):
                    self.emit_node(stmt)
                elif isinstance(stmt, Possibilities):
                    self.emit_node(stmt)
            self.emit("")
            # BUG-10: forward declarations for ALL actions/externs
            for stmt in node.body:
                if isinstance(stmt, Action):
                    sig = self._collect_fwd_sig(stmt)
                    if sig:
                        self.emit(f"{sig};")
                elif isinstance(stmt, (ImportC, ExternFn)):
                    self.emit_node(stmt)
            # Flush buffered action definitions (defined before the program block)
            if self._action_buffer:
                self.emit("")
                for line in self._action_buffer:
                    self.emit(line)
                self._action_buffer.clear()
            self.emit("")
            # PHASE 2: global variables
            for stmt in node.body:
                if isinstance(stmt, VarDecl):
                    self.declared_vars[stmt.name] = self.type_to_c(stmt.type)
                    ct = self.type_to_c(stmt.type)
                    raw_type = stmt.type
                    is_array = raw_type.endswith(' list') or raw_type.endswith(' array')
                    if isinstance(stmt.value, Literal) and isinstance(stmt.value.value, list):
                        # MISSING-01: array literal — emit typed array with count
                        elem_type = ct
                        raw_vals = []
                        for v in stmt.value.value:
                            if isinstance(v, (int, float, bool)):
                                raw_vals.append(str(v).lower() if isinstance(v, bool) else str(v))
                            else:
                                raw_vals.append(self.expr_to_c(v))
                        vals = ", ".join(raw_vals)
                        size = len(stmt.value.value)
                        self.emit(f"{elem_type} {stmt.name}[{size}] = {{{vals}}};")
                        self.emit(f"const size_t {stmt.name}_count = {size};")
                        self.emit(f"const size_t {stmt.name}_size = sizeof({stmt.name});")
                        self.declared_vars[f"{stmt.name}_count"] = "size_t"
                    elif isinstance(stmt.value, UnaryOp) and stmt.value.op == "room_for":
                        # MISSING-03: malloc at file scope not valid; defer to main
                        operand = self.expr_to_c(stmt.value.operand)
                        self.emit(f"{ct} {stmt.name} = NULL;  /* allocated in main() */")
                        self._main_inits.append(f"{stmt.name} = (void*)malloc({operand});")
                    elif stmt.value is None:
                        if is_array:
                            self.emit(f"{ct} {stmt.name}[1];  /* uninitialized array */")
                        else:
                            self.emit(f"{ct} {stmt.name};")
                    else:
                        val = self.expr_to_c(stmt.value)
                        self.emit(f"{ct} {stmt.name} = {val};")
            self.emit("")
            # PHASE 3: module bodies
            for stmt in node.body:
                if isinstance(stmt, Module):
                    self.emit_node(stmt)
            self.emit("")
            # PHASE 4: action definitions
            for stmt in node.body:
                if isinstance(stmt, Action):
                    self.emit_node(stmt)
            self.emit("")
            # PHASE 5: main()
            self.emit("int main(void) {")
            self.indent += 1
            # Emit deferred room_for allocations
            for init_line in self._main_inits:
                self.emit(init_line)
            if self._main_inits:
                self.emit("")
            for stmt in node.body:
                try:
                    from .polyglot_ast import (
                        PolyglotModule, PolyglotImport, PolyglotCall,
                        UnsafeForeignCall, BuildDirective, ForeignShape,
                    )
                    _poly_stmt_types = (
                        PolyglotModule, PolyglotCall, UnsafeForeignCall,
                    )
                    _poly_skip_types = (PolyglotImport, BuildDirective, ForeignShape)
                except ImportError:
                    _poly_stmt_types = ()
                    _poly_skip_types = ()

                if isinstance(stmt, (If, While, ForEach, Repeat, Assignment,
                                     Print, Assert, FuncCall, UnsafeBlock, Attempt)):
                    self.emit_node(stmt)
                elif _poly_stmt_types and isinstance(stmt, _poly_stmt_types):
                    self.emit_node(stmt)
            self.indent -= 1
            self.emit("    return 0;")
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Module):
            if not self._includes_emitted:
                self.emit("#include <stdint.h>")
                self.emit("#include <stdbool.h>")
                self.emit("#include <stdio.h>")
                self.emit("#include <stdlib.h>")
                self.emit("#include <string.h>")
                self.emit("#include <assert.h>")
                self.emit("#include <math.h>")
                self.emit("")
                self.emit("typedef const char* dictum_text;")
                self.emit("")
                self._includes_emitted = True
            for stmt in node.body:
                self.emit_node(stmt)
            return

        # ----------------------------------------------------------------
        if isinstance(node, Possibilities):
            lines = [f"typedef enum {{"]
            for v in node.variants:
                lines.append(f"    {v},")
            lines.append(f"}} {node.name};")
            lines.append("")
            if self._includes_emitted:
                for line in lines: self.emit(line)
            else:
                self._struct_buffer.extend(lines)
            return

        # ----------------------------------------------------------------
        if isinstance(node, Shape):
            self.shapes[node.name] = {f: t for f, t in node.fields}
            lines = []
            if node.is_packed:
                lines.append(f"typedef struct __attribute__((packed)) {{")
            else:
                lines.append(f"typedef struct {{")
            for fname, ftype in node.fields:
                lines.append(f"    {self.type_to_c(ftype)} {fname};")
            lines.append(f"}} {node.name};")
            lines.append("")
            if self._includes_emitted:
                for line in lines: self.emit(line)
            else:
                self._struct_buffer.extend(lines)
            return

        # ----------------------------------------------------------------
        if isinstance(node, VarDecl):
            ct = self.type_to_c(node.type)
            raw_type = node.type
            is_array = raw_type.endswith(' list') or raw_type.endswith(' array')
            self.declared_vars[node.name] = ct
            if node.value is None:
                if is_array:
                    self.emit(f"{ct} {node.name}[1];  /* uninitialized array */")
                else:
                    self.emit(f"{ct} {node.name};  /* uninitialized */")
            elif isinstance(node.value, Literal) and isinstance(node.value.value, list):
                # MISSING-01: array literal init
                raw_vals = []
                for v in node.value.value:
                    if isinstance(v, (int, float, bool)):
                        raw_vals.append(str(v).lower() if isinstance(v, bool) else str(v))
                    else:
                        raw_vals.append(self.expr_to_c(v))
                vals = ", ".join(raw_vals)
                size = len(node.value.value)
                self.emit(f"{ct} {node.name}[{size}] = {{{vals}}};")
                self.emit(f"const size_t {node.name}_count = {size};")
                self.emit(f"const size_t {node.name}_size = sizeof({node.name});")
            elif isinstance(node.value, UnaryOp) and node.value.op == "all_values":
                self.emit(f"/* all_values init: {node.name} */")
            elif isinstance(node.value, UnaryOp) and node.value.op == "room_for":
                operand = self.expr_to_c(node.value.operand)
                self.emit(f"{ct} {node.name} = (void*)malloc({operand});  /* room_for */")
            else:
                val = self.expr_to_c(node.value)
                self.emit(f"{ct} {node.name} = {val};")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Assignment):
            target = self.lvalue_to_c(node.target)
            val = self.expr_to_c(node.value)
            # BUG-01 FIX: auto-declare undeclared variable
            base_name = target.split('[')[0].split('.')[0]
            if (base_name not in self.declared_vars and
                    '[' not in target and '.' not in target):
                inferred_ct = self._infer_type_from_expr(node.value) or "int32_t"
                self.declared_vars[base_name] = inferred_ct
                self.emit(f"{inferred_ct} {target} = {val};")
            else:
                self.emit(f"{target} = {val};")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Action):
            self.actions.add(node.name)
            params_str = ", ".join(f"{self.type_to_c(ptype)} {pname}" for pname, ptype in node.params)
            if not params_str:
                params_str = "void"
            ret = self.type_to_c(node.ret_type) if node.ret_type != 'result' else 'void*'

            if not self._includes_emitted:
                # Buffer for after includes
                saved, saved_indent = self.output, self.indent
                self.output = self._action_buffer
                self.indent = 0
                self.emit(f"{ret} {node.name}({params_str}) {{")
                self.indent += 1
                for stmt in node.body:
                    self.emit_node(stmt)
                self.indent -= 1
                self.emit("}")
                self.emit("")
                self.output = saved; self.indent = saved_indent
            else:
                self.emit(f"{ret} {node.name}({params_str}) {{")
                self.indent += 1
                for stmt in node.body:
                    self.emit_node(stmt)
                self.indent -= 1
                self.emit("}")
                self.emit("")
            return

        # ----------------------------------------------------------------
        if isinstance(node, If):
            cond = self.expr_to_c(node.cond)
            cond = cond.replace("== 'empty'", "== NULL").replace('== "empty"', "== NULL")
            self.emit(f"if ({cond}) {{")
            self.indent += 1
            for stmt in node.then_body:
                self.emit_node(stmt)
            self.indent -= 1
            if node.else_body:
                self.emit("} else {")
                self.indent += 1
                for stmt in node.else_body:
                    self.emit_node(stmt)
                self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, While):
            cond = self.expr_to_c(node.cond)
            self.emit(f"while ({cond}) {{")
            self.indent += 1
            for stmt in node.body:
                self.emit_node(stmt)
            self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, ForEach):
            # MISSING-01 / MISSING-07 FIX: for each over array
            self.emit(f"for (size_t __i = 0; __i < {node.collection}_count; __i++) {{")
            self.indent += 1
            elem_type = self.declared_vars.get(node.collection, "int32_t")
            # Strip array brackets from type if present
            elem_type = elem_type.replace("*", "").strip()
            self.emit(f"{elem_type} {node.item} = {node.collection}[__i];")
            for stmt in node.body:
                self.emit_node(stmt)
            self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Repeat):
            count = self.expr_to_c(node.count)
            self.emit(f"for (int32_t {node.counter} = 0; {node.counter} < {count}; {node.counter}++) {{")
            self.indent += 1
            for stmt in node.body:
                self.emit_node(stmt)
            self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Attempt):
            # P4.1: emit attempt block using dictum_last_error for real error propagation.
            result    = node.result_name or "__attempt_result"
            fail_name = node.failure_name or "__err"

            if node.call is not None:
                call_expr = self.expr_to_c(node.call)
                inferred  = self._infer_type_from_expr(node.call) or "int32_t"
                self.emit("/* attempt */")
                self.emit("dictum_error_clear();")
                self.emit(f"{inferred} {result} = {call_expr};")
                self.declared_vars[result] = inferred
                self.emit("if (!DICTUM_HAS_ERROR()) {")
                self.indent += 1
                for stmt in node.success_body:
                    self.emit_node(stmt)
                self.indent -= 1
                if node.failure_body:
                    self.emit("} else {")
                    self.indent += 1
                    if node.failure_name:
                        self.emit(f'const char* {node.failure_name} = dictum_error_last();')
                        self.declared_vars[node.failure_name] = "const char*"
                    for stmt in node.failure_body:
                        self.emit_node(stmt)
                    self.indent -= 1
                self.emit("}")
            else:
                # Block form: use do { ... } while(0) + goto pattern so that
                # failure body can be reached via goto when dictum_error_set()
                # is called inside the success body.
                lbl_fail = f"__attempt_fail_{node.line}"
                lbl_end  = f"__attempt_end_{node.line}"
                self.emit("/* attempt block */")
                self.emit("dictum_error_clear();")
                self.emit("do {")
                self.indent += 1
                for stmt in node.success_body:
                    self.emit_node(stmt)
                # After success body, skip over failure block
                if node.failure_body:
                    self.emit(f"if (DICTUM_HAS_ERROR()) {{ goto {lbl_fail}; }}")
                self.indent -= 1
                self.emit(f"}} while (0);")

                if node.failure_body:
                    self.emit(f"if (!DICTUM_HAS_ERROR()) {{ goto {lbl_end}; }}")
                    self.emit(f"{lbl_fail}:")
                    self.emit("{")
                    self.indent += 1
                    if node.failure_name:
                        self.emit(f'const char* {node.failure_name} = dictum_error_last();')
                        self.declared_vars[node.failure_name] = "const char*"
                    for stmt in node.failure_body:
                        self.emit_node(stmt)
                    self.indent -= 1
                    self.emit("}")
                    self.emit(f"{lbl_end}: ;")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Return):
            # BUG-09 FIX: clean return without noise
            if isinstance(node.value, FuncCall):
                if node.value.name in ('__produce_success', 'success'):
                    inner = self.expr_to_c(node.value.args[0]) if node.value.args else ""
                    self.emit(f"return {inner};")
                    return
                if node.value.name == 'failure':
                    msg = self.expr_to_c(node.value.args[0]) if node.value.args else '"error"'
                    self.emit(f"/* produce failure: {msg} */")
                    self.emit(f"return 0;")
                    return
            val = self.expr_to_c(node.value)
            self.emit(f"return {val};")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Assert):
            self.emit(f"assert({self.expr_to_c(node.cond)});")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Print):
            fmt_parts, args = [], []
            for p in node.parts:
                if isinstance(p, Literal) and isinstance(p.value, str):
                    escaped = p.value.replace("\\", "\\\\").replace("\n", "\\n")
                    fmt_parts.append(escaped)
                else:
                    # Type-aware format specifier
                    spec = self._format_spec(p)
                    fmt_parts.append(spec)
                    args.append(self.expr_to_c(p))
            fmt = "".join(fmt_parts)
            if args:
                self.emit(f'printf("{fmt}", {", ".join(args)});')
            else:
                self.emit(f'printf("{fmt}");')
            return

        # ----------------------------------------------------------------
        if isinstance(node, FuncCall):
            c_name = self._resolve_call_name(node.name)   # BUG-04
            if c_name == "__defer_release":
                self.emit(f"/* defer release: {self.expr_to_c(node.args[0])} */")
            elif c_name == "release":
                arg = self.expr_to_c(node.args[0])
                self.emit(f"free({arg});")
            else:
                args = ", ".join(self.expr_to_c(a) for a in node.args)
                self.emit(f"{c_name}({args});")
            return

        # ----------------------------------------------------------------
        if isinstance(node, ImportDict):
            # MISSING-08: resolved at Transpiler level; emitter just emits the #include.
            stem = node.module_name.lower()
            self._extra_includes.append(f'#include "{stem}.h"')
            return

        if isinstance(node, ImportC):
            params = ", ".join(self.type_to_c(p) for p in node.params)
            self.emit(f"extern {self.type_to_c(node.ret_type)} {node.alias}({params});")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Use):
            # BUG-05 FIX: `use Module` → #include
            # P2.1: track module for Makefile generation
            self._used_modules.add(node.path)
            inc_path = _USE_INCLUDE_MAP.get(node.path, f"dictum_{node.path.lower()}.h")
            if node.is_system or inc_path.endswith('.h') and not inc_path.startswith('dictum_'):
                inc_line = f"#include <{inc_path}>"
            else:
                inc_line = f'#include "{inc_path}"'
            if self._includes_emitted:
                self.emit(inc_line)
            else:
                self._extra_includes.append(inc_line)
            return

        # ----------------------------------------------------------------
        if isinstance(node, Bind):
            params = ", ".join(f"{self.type_to_c(ptype)} {pname}" for pname, ptype in node.params)
            ret = self.type_to_c(node.ret_type)
            self.emit(f"extern {ret} {node.name}({params});")
            self.actions.add(node.alias)
            return

        # ----------------------------------------------------------------
        if isinstance(node, ExternFn):
            params = ", ".join(f"{self.type_to_c(ptype)} {pname}" for pname, ptype in node.params)
            ret = self.type_to_c(node.ret_type)
            if node.syscall_name:
                self.emit(f"/* @syscall: {node.syscall_name} */")
            self.emit(f"extern {ret} {node.name}({params});")
            return

        # ----------------------------------------------------------------
        if isinstance(node, UnsafeBlock):
            self.emit("/* unsafe block */")
            for stmt in node.body:
                self.emit_node(stmt)
            return

        # ----------------------------------------------------------------
        if isinstance(node, VarDecl):
            # VarDecl inside a block (already handled above, fallback)
            self.emit_node(node)
            return

        # ----------------------------------------------------------------
        # Polyglot nodes — C emitter treatment
        # ----------------------------------------------------------------
        try:
            from .polyglot_ast import (
                PolyglotModule, PolyglotImport, PolyglotCall,
                UnsafeForeignCall, BuildDirective, ForeignShape,
            )
        except ImportError:
            pass
        else:
            if isinstance(node, PolyglotModule):
                # Emit the module body inline; the binding glue is generated by the linker
                self.emit(f"/* polyglot module '{node.name}' backend={node.backend} safety={node.safety} */")
                for stmt in node.body:
                    self.emit_node(stmt)
                return

            if isinstance(node, PolyglotImport):
                # BUG-05 style: emit an extern include comment
                inc = f"{node.module_name}_polyglot.h"
                self.emit(f'#include "{inc}"  /* polyglot import {node.module_name} via {node.pattern} */')
                return

            if isinstance(node, PolyglotCall):
                # Cross-module call: resolve via binding header
                c_fn = f"dictum_safe_{node.function}" if node.safety != 'unsafe' else node.function
                args = ", ".join(self.expr_to_c(a) for a in node.args)
                if node.result_name:
                    inferred = "int32_t"
                    self.emit(f"{inferred} {node.result_name} = {c_fn}({args});")
                else:
                    self.emit(f"{c_fn}({args});")
                return

            if isinstance(node, UnsafeForeignCall):
                # Raw dlsym / direct symbol call
                args = ", ".join(self.expr_to_c(a) for a in node.args)
                ret_type = self.type_to_c(node.result_type) if node.result_type else "void*"
                if node.result_name:
                    self.emit(f"/* unsafe foreign call */")
                    self.emit(f"{ret_type} {node.result_name} = "
                               f"(({ret_type}(*)())(uintptr_t)\"{node.symbol}\")({args});")
                else:
                    self.emit(f"/* unsafe foreign call: {node.symbol}({args}) */")
                return

            if isinstance(node, BuildDirective):
                # Emit as preprocessor comment — actual effect is in Makefile
                if node.kind == 'link':
                    self.emit(f"/* #[link \"{node.value}\"] — add -l{node.value} to LDFLAGS */")
                elif node.kind in ('cflags', 'ldflags', 'include_path'):
                    self.emit(f"/* #[{node.kind} \"{node.value}\"] */")
                return

            if isinstance(node, ForeignShape):
                # Emit as a C struct with a matching layout
                lines = []
                if node.packed:
                    lines.append("#pragma pack(push, 1)")
                lines.append(f"/* foreign {node.source_language} struct: {node.name} */")
                lines.append(f"typedef struct {{")
                for fname, ftype in node.fields:
                    ct = self.type_to_c(ftype)
                    lines.append(f"    {ct} {fname};")
                lines.append(f"}} {node.name};")
                if node.packed:
                    lines.append("#pragma pack(pop)")
                for ln in lines:
                    self.emit(ln)
                return

        self.emit(f"/* unhandled: {type(node).__name__} */")

    # ------------------------------------------------------------------
    # Format specifier helper for printf
    # ------------------------------------------------------------------
    def _format_spec(self, p: Node) -> str:
        if isinstance(p, Literal):
            if isinstance(p.value, float): return "%f"
            if isinstance(p.value, str):   return "%s"
            return "%d"
        if isinstance(p, Identifier):
            t = self.declared_vars.get(p.name, '')
            if t in ('double', 'float'):   return "%f"
            if t in ('dictum_text', 'const char*', 'char*'): return "%s"
            if t == 'bool':                return "%d"
            if t == 'size_t':              return "%zu"
            if t in ('int64_t', 'uint64_t'): return "%lld"
            # heuristic from variable name
            n = p.name.lower()
            if any(h in n for h in ('frac', 'dist', 'price', 'rate', 'double', 'float')): return "%f"
            if any(h in n for h in ('name', 'msg', 'text', 'str')):  return "%s"
            return "%d"
        if isinstance(p, FieldAccess):
            if p.obj in self.shapes:
                field_type = self.shapes[p.obj].get(p.field, '')
                if 'fractional' in field_type or 'decimal' in field_type: return "%f"
                if field_type == 'text': return "%s"
            return "%d"
        if isinstance(p, BinaryOp):
            if p.op in ('==', '!=', '>', '<', '>=', '<='): return "%d"
            return self._format_spec(p.left)
        return "%d"

    # ------------------------------------------------------------------
    def get_output(self) -> str:
        # Flush any residual action buffer (module-only files)
        if not self._includes_emitted and (self._struct_buffer or self._action_buffer):
            prelude = [
                "#include <stdint.h>", "#include <stdbool.h>", "#include <stdio.h>",
                "#include <stdlib.h>", "#include <string.h>", "#include <assert.h>",
                "#include <math.h>", "#include <setjmp.h>", "",
                "typedef const char* dictum_text;", "",
            ]
            prelude.extend(self._struct_buffer)
            prelude.extend(self._action_buffer)
            self.output = prelude + self.output
        elif self._action_buffer:
            # Inject buffered actions after last #include line
            last_inc = -1
            for i, ln in enumerate(self.output):
                if ln.strip().startswith('#include') or ln.strip().startswith('typedef'):
                    last_inc = i
            if last_inc >= 0:
                inject = [''] + self._action_buffer
                self.output = (self.output[:last_inc + 1]
                               + inject
                               + self.output[last_inc + 1:])
            self._action_buffer = []
        return "\n".join(self.output)

    # ------------------------------------------------------------------
    # P2.1: Generate a Makefile for the transpiled program
    # ------------------------------------------------------------------
    # Module → linker flags mapping
    _MODULE_LDFLAGS: Dict[str, List[str]] = {
        "Http":      ["-lcurl"],
        "Tls":       ["-lssl", "-lcrypto"],
        "Net":       [],
        "Thread":    ["-lpthread"],
        "Mutex":     ["-lpthread"],
        "Channel":   ["-lpthread"],
        "Semaphore": ["-lpthread"],
        "Event":     ["-lpthread"],
        "Math":      ["-lm"],
        "Shm":       ["-lrt"],
        "Timer":     ["-lrt"],
        "Process":   [],
        "Signal":    [],
        "Pipe":      [],
        "Mmap":      [],
        "Path":      [],
        "Directory": [],
        "Device":    [],
        "Csv":       [],
        "File":      [],
        "Text":      [],
        "Json":      ["-lm"],   # atof uses libm
        "Console":   [],
    }

    def _has_attempt_nodes(self, root: Node) -> bool:
        """Return True if any Attempt node exists under root."""
        from .ast_nodes import Attempt as AttemptNode
        def _walk(n: Node) -> bool:
            if isinstance(n, AttemptNode):
                return True
            for attr in ('body', 'success_body', 'failure_body', 'then_body',
                         'else_body', 'actions', 'cases'):
                val = getattr(n, attr, None)
                if isinstance(val, list):
                    if any(_walk(child) for child in val if isinstance(child, Node)):
                        return True
            return False
        return _walk(root)

    def get_makefile(self, program_name: str = "program",
                     stdlib_dir: str = "stdlib") -> str:
        """Return an auto-generated Makefile string for the transpiled program."""
        ldflags: List[str] = ["-lm"]  # always link math
        seen: set = set()
        for mod in sorted(self._used_modules):
            for flag in self._MODULE_LDFLAGS.get(mod, []):
                if flag not in seen:
                    seen.add(flag)
                    ldflags.append(flag)

        ldflags_str = " ".join(ldflags)
        lines = [
            f"# Auto-generated by dictumc — Dictum v5",
            f"# Rebuild with: make",
            f"",
            f"CC      = gcc",
            f"AR      = ar",
            f"CFLAGS  = -std=c11 -Wall -O2 -I{stdlib_dir}",
            f"LDFLAGS = {ldflags_str}",
            f"STDLIB  = {stdlib_dir}/libdictum_stdlib.a",
            f"",
            f"all: {program_name}",
            f"",
            f"{program_name}: {program_name}.c $(STDLIB)",
            f"\t$(CC) $(CFLAGS) {program_name}.c $(STDLIB) -o {program_name} $(LDFLAGS)",
            f"",
            f"$(STDLIB):",
            f"\t$(MAKE) -C {stdlib_dir} lib",
            f"",
            f"clean:",
            f"\trm -f {program_name}",
            f"",
            f".PHONY: all clean",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Header generation for exports
    # ------------------------------------------------------------------
    def get_header_output(self, ast: List[Node]) -> str:
        lines = ["#pragma once", "#include <stdint.h>", "#include <stdbool.h>",
                 "#include <stddef.h>", "typedef const char* dictum_text;", ""]
        def _emit(nodes):
            for node in nodes:
                if isinstance(node, Shape) and node.export:
                    if node.is_packed:
                        lines.append(f"typedef struct __attribute__((packed)) {{")
                    else:
                        lines.append(f"typedef struct {{")
                    for fname, ftype in node.fields:
                        lines.append(f"    {self.type_to_c(ftype)} {fname};")
                    lines.append(f"}} {node.name};")
                    lines.append("")
                elif isinstance(node, VarDecl) and node.export:
                    lines.append(f"extern {self.type_to_c(node.type)} {node.name};")
                elif isinstance(node, Action) and node.export:
                    params = ", ".join(f"{self.type_to_c(pt)} {pn}" for pn, pt in node.params) or "void"
                    ret = self.type_to_c(node.ret_type)
                    lines.append(f"extern {ret} {node.name}({params});")
                elif isinstance(node, (Program, Module)):
                    _emit(node.body)
        _emit(ast)
        return "\n".join(lines)
