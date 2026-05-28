"""
Dictum C++ Emitter — emits C++17/20/23 from the AST.
Extracted and fixed from transpiler.py v3.3.

Fixes applied (same set as CEmitter where applicable):
  BUG-01:  auto-declare undeclared assignment targets.
  BUG-04:  Module.function call resolution via _MODULE_CALL_MAP.
  BUG-05:  `use Module` → #include, never a function call.
  BUG-06:  decimal number → double.
  BUG-09:  produce success emits clean return.
  BUG-10:  forward declarations for all actions before main().
  MISSING-02: std::string support alongside const char*.
  MISSING-04: `otherwise` plain else branch (parser handles; emitter unchanged).
  MISSING-05: attempt → try/catch.
  MISSING-09: truth value → bool consistently.
"""

from __future__ import annotations
import re
from typing import List, Dict, Optional, Set, Tuple, Any

from .ast_nodes import (
    Node, Program, Module, Shape, Method, Constructor, Destructor,
    VarDecl, Assignment, Action, FuncCall, Return, If, While, ForEach,
    Repeat, Attempt, Literal, Identifier, BinaryOp, UnaryOp,
    FieldAccess, IndexAccess, Assert, Print, ImportC, ImportCpp,
    UnsafeBlock, ExternFn, Transmute, Use, Bind, NewExpr, LambdaExpr,
    Possibilities,
)

# BUG-04/BUG-05 — reuse same maps from C emitter
from .emit_c import _MODULE_CALL_MAP, _USE_INCLUDE_MAP


class CppEmitter:
    def __init__(self, cpp_standard: int = 17) -> None:
        self.output: List[str] = []
        self.indent: int = 0
        self.cpp_standard = cpp_standard
        self.declared_vars: Dict[str, str] = {}
        self._includes: List[str] = []
        self._action_buffer: List[str] = []
        self._extra_includes: List[str] = []
        self._includes_emitted: bool = False
        self.namespace: str = ""
        self.shapes: Dict[str, Any] = {}
        self.actions: Set[str] = set()
        self.imported_containers: Dict[str, str] = {}
        self.imported_actions: Dict[str, Tuple] = {}

        # BUG-06 + MISSING-09 fixes
        self.types: Dict[str, str] = {
            "whole number":      "int32_t",
            "count":             "size_t",
            "fractional number": "double",
            "decimal number":    "double",   # BUG-06
            "decimal":           "double",   # BUG-06
            "truth value":       "bool",     # MISSING-09
            "bool":              "bool",
            "byte":              "uint8_t",
            "text":              "const char*",
            "handle to bytes":   "void*",
            "nothing":           "void",
            "u8":                "uint8_t",
            "u16":               "uint16_t",
            "u32":               "uint32_t",
            "i32":               "int32_t",
            "i64":               "int64_t",
            "u64":               "uint64_t",
            "result":            "void*",
        }

    # ------------------------------------------------------------------
    def emit(self, line: str) -> None:
        self.output.append("    " * self.indent + line)

    def type_to_cpp(self, t: str) -> str:
        if t.startswith('unique handle to '):
            return f"std::unique_ptr<{self.type_to_cpp(t[len('unique handle to '):].strip())}>"
        if t.startswith('shared handle to '):
            return f"std::shared_ptr<{self.type_to_cpp(t[len('shared handle to '):].strip())}>"
        if t.startswith('weak handle to '):
            return f"std::weak_ptr<{self.type_to_cpp(t[len('weak handle to '):].strip())}>"
        if t.startswith('raw handle to '):
            return f"{self.type_to_cpp(t[len('raw handle to '):].strip())}*"
        if t.startswith('const ref '):
            return f"const {self.type_to_cpp(t[len('const ref '):].strip())}&"
        if t.startswith('ref '):
            return f"{self.type_to_cpp(t[len('ref '):].strip())}&"
        if t.startswith('move '):
            return f"{self.type_to_cpp(t[len('move '):].strip())}&&"
        if t.startswith('action taking '):
            return "std::function<bool(int32_t)>"
        if t.startswith('*'):
            rest = t[1:].strip()
            if rest.startswith('volatile'):
                inner = rest[8:].strip()
                return f"volatile {self.types.get(inner, inner.replace(' ', '_'))}*"
            return f"{self.types.get(rest, rest.replace(' ', '_'))}*"
        if t.endswith(' list') or t.endswith(' array'):
            # Return vector type for list/array in C++
            elem = t.rsplit(' ', 1)[0].strip()
            return f"std::vector<{self.type_to_cpp(elem)}>"
        if t in self.imported_containers:
            return self.imported_containers[t]
        base = self.types.get(t, t.replace(" ", "_"))
        if '.' in base:
            base = base.replace('.', '::')
        return base

    def _resolve_call_name(self, name: str) -> str:
        if '.' in name:
            return _MODULE_CALL_MAP.get(name, name.replace('.', '_'))
        return name

    # ------------------------------------------------------------------
    def expr_to_cpp(self, node: Node) -> str:
        if isinstance(node, Literal):
            if isinstance(node.value, bool):
                return "true" if node.value else "false"
            if isinstance(node.value, str):
                if node.value in ("nothing", "null", "NULL"):
                    return "nullptr"   # P7.2: nothing → nullptr in C++
                if node.value == "\n": return '"\\n"'
                return f'"{node.value}"'
            if isinstance(node.value, list):
                return "{" + ", ".join(str(v) for v in node.value) + "}"
            if node.value is None:
                return "nullptr"
            return str(node.value)
        elif isinstance(node, Identifier):
            return node.name
        elif isinstance(node, FieldAccess):
            # Smart pointer field access → ->
            base_type = self.declared_vars.get(node.obj, '')
            if any(base_type.startswith(p) for p in
                   ['unique handle to ', 'shared handle to ', 'weak handle to ', 'raw handle to ']):
                return f"{node.obj}->{node.field}"
            return f"{node.obj}.{node.field}"
        elif isinstance(node, IndexAccess):
            return f"{node.collection}[{self.expr_to_cpp(node.index)}]"
        elif isinstance(node, BinaryOp):
            left = self.expr_to_cpp(node.left)
            right = self.expr_to_cpp(node.right)
            if right in ('"empty"', "'empty'"):
                right = 'nullptr'
            if node.op == 'pow':
                return f"std::pow({left}, {right})"
            return f"({left} {node.op} {right})"
        elif isinstance(node, UnaryOp):
            op = node.op; operand = self.expr_to_cpp(node.operand)
            if op == "count":   return f"sizeof({operand}) / sizeof({operand}[0])"
            if op == "length":  return f"std::strlen({operand})"
            if op == "tanh":    return f"std::tanh({operand})"
            if op == "sqrt":    return f"std::sqrt({operand})"
            if op == "exp":     return f"std::exp({operand})"
            if op == "sin":     return f"std::sin({operand})"
            if op == "cos":     return f"std::cos({operand})"
            if op == "room_for":
                return f"std::make_unique<int32_t[]>({operand})"
            if op == "addrof":  return f"(&{operand})"
            if op == "deref":   return f"(*{operand})"
            return f"({op}{operand})"
        elif isinstance(node, Transmute):
            return f"static_cast<{self.type_to_cpp(node.type)}>({self.expr_to_cpp(node.expr)})"
        elif isinstance(node, NewExpr):
            type_name = node.type_name.replace('.', '::')
            args = ", ".join(self.expr_to_cpp(a) for a in node.args)
            if args:
                return f"std::make_unique<{type_name}>({args})"
            return f"std::make_unique<{type_name}>()"
        elif isinstance(node, LambdaExpr):
            params = ", ".join(f"{self.type_to_cpp(pt)} {pn}" for pn, pt in node.params)
            ret = self.type_to_cpp(node.ret_type)
            body_lines: List[str] = []
            saved, saved_indent = self.output, self.indent
            self.output = body_lines; self.indent = 0
            for stmt in node.body:
                self.emit_node(stmt)
            self.output = saved; self.indent = saved_indent
            body_str = " ".join(l.strip() for l in body_lines)
            captures = self._analyze_captures(node.body, {p[0] for p in node.params})
            cap_str = ", ".join(f"&{c}" for c in sorted(captures))
            return f"[{cap_str}]({params}) -> {ret} {{ {body_str} }}"
        elif isinstance(node, FuncCall):
            c_name = self._resolve_call_name(node.name)
            processed = []
            for a in node.args:
                arg_str = self.expr_to_cpp(a)
                if isinstance(a, Identifier) and a.name in self.declared_vars:
                    vt = self.declared_vars[a.name]
                    if any(vt.startswith(p) for p in
                           ['unique handle to ', 'shared handle to ', 'weak handle to ']):
                        arg_str = f"(*{arg_str})"
                processed.append(arg_str)
            args = ", ".join(processed)
            if c_name in ('success', '__produce_success'):
                return args
            if c_name == 'failure':
                return f"/* failure: {args} */ 0"
            if '->' in c_name:
                parts = c_name.split('->')
                return f"{parts[0]}->{parts[1]}({args})"
            return f"{c_name}({args})"
        return f"/* expr: {type(node).__name__} */"

    def lvalue_to_cpp(self, target: str) -> str:
        if '.' in target:
            parts = target.split('.')
            base = parts[0]
            if base in self.declared_vars:
                bt = self.declared_vars[base]
                if any(bt.startswith(p) for p in
                       ['unique handle to ', 'shared handle to ', 'weak handle to ', 'raw handle to ']):
                    dot_path = '.'.join(parts[1:])
                    return f"{base}->{dot_path}"
        return target

    def _infer_type_from_expr(self, node: Node) -> Optional[str]:
        if isinstance(node, Literal):
            if isinstance(node.value, bool):  return "bool"
            if isinstance(node.value, int):   return "int32_t"
            if isinstance(node.value, float): return "double"
            if isinstance(node.value, str):   return "const char*"
        if isinstance(node, Identifier):
            return self.declared_vars.get(node.name)
        if isinstance(node, BinaryOp):
            lt = self._infer_type_from_expr(node.left)
            if node.op in ('==', '!=', '>', '<', '>=', '<='): return "bool"
            return lt or self._infer_type_from_expr(node.right)
        if isinstance(node, NewExpr):
            return f"std::unique_ptr<{node.type_name.replace('.', '::')}>"
        return None

    # ------------------------------------------------------------------
    def emit_node(self, node: Node) -> None:

        # ----------------------------------------------------------------
        if isinstance(node, Program):
            # Pre-scan for polyglot imports and build directives (add to extra_includes)
            try:
                from .polyglot_ast import PolyglotImport, BuildDirective
                for stmt in node.body:
                    if isinstance(stmt, PolyglotImport):
                        inc = f'#include "{stmt.module_name}_cxx.hpp"  /* polyglot import {stmt.module_name} */'
                        if inc not in self._extra_includes:
                            self._extra_includes.append(inc)
                    elif isinstance(stmt, BuildDirective):
                        if stmt.kind in ('cflags', 'ldflags', 'link', 'include_path'):
                            self._extra_includes.append(f'/* #[{stmt.kind} "{stmt.value}"] */')
            except ImportError:
                pass
            self._emit_includes()
            self.emit("")
            ns = self.namespace
            if ns:
                self.emit(f"namespace {ns} {{")
                self.indent += 1
            # Pre-pass: register global var types
            for stmt in node.body:
                if isinstance(stmt, VarDecl):
                    self.declared_vars[stmt.name] = self.type_to_cpp(stmt.type)
            # Shapes, imports, externs, forward decls
            for stmt in node.body:
                if isinstance(stmt, (Shape, Possibilities)):
                    self.emit_node(stmt)
            self.emit("")
            # BUG-10: forward declarations
            for stmt in node.body:
                if isinstance(stmt, Action):
                    self._emit_fwd_decl(stmt)
                elif isinstance(stmt, (ImportC, ExternFn, ImportCpp)):
                    self.emit_node(stmt)
            # Flush buffered actions
            if self._action_buffer:
                self.emit("")
                for line in self._action_buffer:
                    self.output.append(line)
                self._action_buffer.clear()
            self.emit("")
            # Global variables
            for stmt in node.body:
                if isinstance(stmt, VarDecl):
                    self.emit_node(stmt)
            self.emit("")
            # Module bodies
            for stmt in node.body:
                if isinstance(stmt, Module):
                    self.emit_node(stmt)
            self.emit("")
            # Action definitions
            for stmt in node.body:
                if isinstance(stmt, Action):
                    self.emit_node(stmt)
            self.emit("")
            # main()
            self.emit("int main() {")
            self.indent += 1
            for stmt in node.body:
                if isinstance(stmt, (If, While, ForEach, Repeat, Assignment,
                                     Print, Assert, FuncCall, UnsafeBlock, Attempt)):
                    self.emit_node(stmt)
                else:
                    try:
                        from .polyglot_ast import (
                            PolyglotModule, PolyglotCall, UnsafeForeignCall,
                        )
                        if isinstance(stmt, (PolyglotModule, PolyglotCall, UnsafeForeignCall)):
                            self.emit_node(stmt)
                    except ImportError:
                        pass
            self.indent -= 1
            self.emit("    return 0;")
            self.emit("}")
            if ns:
                self.indent -= 1
                self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Module):
            ns_name = f"{self.namespace}::{node.name}" if self.namespace else node.name
            self.emit(f"namespace {ns_name} {{")
            self.indent += 1
            for stmt in node.body:
                self.emit_node(stmt)
            self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Possibilities):
            self.emit(f"enum class {node.name} {{")
            self.indent += 1
            for v in node.variants:
                self.emit(f"{v},")
            self.indent -= 1
            self.emit("};")
            self.emit("")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Shape):
            self.shapes[node.name] = {f: t for f, t in node.fields}
            is_class = bool(node.methods or node.constructors or node.destructor or node.parent)
            if is_class:
                base = f"class {node.name}"
                if node.is_packed:
                    base = f"class __attribute__((packed)) {node.name}"
                if node.parent:
                    base += f" : public {node.parent}"
                self.emit(f"{base} {{")
                self.indent += 1
                self.emit("public:")
                for fname, ftype in node.fields:
                    self.emit(f"{self.type_to_cpp(ftype)} {fname};")
                if not any(len(c.params) == 0 for c in node.constructors):
                    self.emit(f"{node.name}() = default;")
                for ctor in node.constructors:
                    params = ", ".join(f"{self.type_to_cpp(pt)} {pn}" for pn, pt in ctor.params)
                    self.emit(f"{node.name}({params}) {{")
                    self.indent += 1
                    for stmt in ctor.body:
                        self.emit_node(stmt)
                    self.indent -= 1
                    self.emit("}")
                if node.destructor:
                    self.emit(f"~{node.name}() {{")
                    self.indent += 1
                    for stmt in node.destructor.body:
                        self.emit_node(stmt)
                    self.indent -= 1
                    self.emit("}")
                for method in node.methods:
                    params = ", ".join(f"{self.type_to_cpp(pt)} {pn}" for pn, pt in method.params)
                    ret = self.type_to_cpp(method.ret_type)
                    virt = "virtual " if (method.is_virtual or method.is_override or node.parent) else ""
                    override = " override" if method.is_override else ""
                    self.emit(f"{virt}{ret} {method.name}({params}){override} {{")
                    self.indent += 1
                    for stmt in method.body:
                        self.emit_node(stmt)
                    self.indent -= 1
                    self.emit("}")
                self.indent -= 1
                self.emit("};")
            else:
                pfx = "struct __attribute__((packed))" if node.is_packed else "struct"
                self.emit(f"{pfx} {node.name} {{")
                self.indent += 1
                for fname, ftype in node.fields:
                    self.emit(f"{self.type_to_cpp(ftype)} {fname};")
                self.indent -= 1
                self.emit("};")
            self.emit("")
            return

        # ----------------------------------------------------------------
        if isinstance(node, VarDecl):
            raw_type = node.type
            is_array = raw_type.endswith(' list') or raw_type.endswith(' array')
            ct = self.type_to_cpp(raw_type)
            self.declared_vars[node.name] = raw_type
            if node.value is None:
                self.emit(f"{ct} {node.name};  /* uninitialized */")
            elif isinstance(node.value, Literal) and isinstance(node.value.value, list):
                vals = ", ".join(
                    str(v).lower() if isinstance(v, bool) else str(v)
                    for v in node.value.value
                )
                size = len(node.value.value)
                elem_t = self.type_to_cpp(raw_type.rsplit(' ', 1)[0].strip()) if is_array else ct
                self.emit(f"{elem_t} {node.name}[{size}] = {{{vals}}};")
                self.emit(f"const size_t {node.name}_count = {size};")
            elif isinstance(node.value, UnaryOp) and node.value.op == "room_for":
                operand = self.expr_to_cpp(node.value.operand)
                if raw_type.startswith('unique handle to '):
                    inner = raw_type[len('unique handle to '):].strip()
                    self.emit(f"{ct} {node.name} = std::make_unique<{self.type_to_cpp(inner)}[]>({operand});")
                elif raw_type.startswith('shared handle to '):
                    inner = raw_type[len('shared handle to '):].strip()
                    self.emit(f"{ct} {node.name} = std::make_shared<{self.type_to_cpp(inner)}[]>({operand});")
                else:
                    self.emit(f"{ct} {node.name} = std::make_unique<int32_t[]>({operand});")
            else:
                # Smart pointer assignment from NewExpr
                if isinstance(node.value, NewExpr):
                    type_name = node.value.type_name.replace('.', '::')
                    args = ", ".join(self.expr_to_cpp(a) for a in node.value.args)
                    if raw_type.startswith('unique handle to '):
                        inner = self.type_to_cpp(raw_type[len('unique handle to '):].strip())
                        if args:
                            self.emit(f"{ct} {node.name} = std::make_unique<{inner}>({args});")
                        else:
                            self.emit(f"{ct} {node.name} = std::make_unique<{inner}>();")
                        return
                    elif raw_type.startswith('shared handle to '):
                        inner = self.type_to_cpp(raw_type[len('shared handle to '):].strip())
                        if args:
                            self.emit(f"{ct} {node.name} = std::make_shared<{inner}>({args});")
                        else:
                            self.emit(f"{ct} {node.name} = std::make_shared<{inner}>();")
                        return
                val = self.expr_to_cpp(node.value)
                self.emit(f"{ct} {node.name} = {val};")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Assignment):
            target = self.lvalue_to_cpp(node.target)
            val = self.expr_to_cpp(node.value)
            # Smart pointer reset from NewExpr
            target_type = self.declared_vars.get(node.target, '')
            if isinstance(node.value, NewExpr):
                type_name = node.value.type_name.replace('.', '::')
                args = ", ".join(self.expr_to_cpp(a) for a in node.value.args)
                if target_type.startswith('unique handle to '):
                    inner = self.type_to_cpp(target_type[len('unique handle to '):].strip())
                    if args:
                        self.emit(f"{target} = std::make_unique<{inner}>({args});")
                    else:
                        self.emit(f"{target} = std::make_unique<{inner}>();")
                    return
                elif target_type.startswith('shared handle to '):
                    inner = self.type_to_cpp(target_type[len('shared handle to '):].strip())
                    if args:
                        self.emit(f"{target} = std::make_shared<{inner}>({args});")
                    else:
                        self.emit(f"{target} = std::make_shared<{inner}>();")
                    return
            # BUG-01 FIX: auto-declare
            base_name = node.target.split('[')[0].split('.')[0]
            if (base_name not in self.declared_vars and
                    '[' not in node.target and '.' not in node.target):
                inferred = self._infer_type_from_expr(node.value) or "int32_t"
                self.declared_vars[base_name] = inferred
                self.emit(f"{inferred} {target} = {val};")
            else:
                self.emit(f"{target} = {val};")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Action):
            self.actions.add(node.name)
            template_decl = ""
            if node.template_params:
                if self.cpp_standard >= 20:
                    tparams = ", ".join(f"typename {tp[0]}" for tp in node.template_params)
                else:
                    tparams = ", ".join(f"typename {tp[0]}" for tp in node.template_params)
                template_decl = f"template <{tparams}>"

            params = ", ".join(f"{self.type_to_cpp(pt)} {pn}" for pn, pt in node.params)
            ret = self.type_to_cpp(node.ret_type)
            if node.ret_type == 'result':
                ret = 'std::optional<int32_t>'

            # Buffer if includes not yet emitted
            if not self._includes_emitted:
                saved, saved_indent = self.output, self.indent
                self.output = self._action_buffer; self.indent = 0
                if template_decl: self.emit(template_decl)
                self.emit(f"{ret} {node.name}({params}) {{")
                self.indent += 1
                for stmt in node.body: self.emit_node(stmt)
                self.indent -= 1
                self.emit("}")
                self.emit("")
                self.output = saved; self.indent = saved_indent
            else:
                if template_decl: self.emit(template_decl)
                self.emit(f"{ret} {node.name}({params}) {{")
                self.indent += 1
                for stmt in node.body: self.emit_node(stmt)
                self.indent -= 1
                self.emit("}")
                self.emit("")
            return

        # ----------------------------------------------------------------
        if isinstance(node, If):
            cond = self.expr_to_cpp(node.cond)
            cond = cond.replace('== "empty"', "== nullptr").replace("== 'empty'", "== nullptr")
            self.emit(f"if ({cond}) {{")
            self.indent += 1
            for stmt in node.then_body: self.emit_node(stmt)
            self.indent -= 1
            if node.else_body:
                self.emit("} else {")
                self.indent += 1
                for stmt in node.else_body: self.emit_node(stmt)
                self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, While):
            self.emit(f"while ({self.expr_to_cpp(node.cond)}) {{")
            self.indent += 1
            for stmt in node.body: self.emit_node(stmt)
            self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, ForEach):
            self.emit(f"for (auto& {node.item} : {node.collection}) {{")
            self.indent += 1
            for stmt in node.body: self.emit_node(stmt)
            self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Repeat):
            count = self.expr_to_cpp(node.count)
            self.emit(f"for (int32_t {node.counter} = 0; {node.counter} < {count}; {node.counter}++) {{")
            self.indent += 1
            for stmt in node.body: self.emit_node(stmt)
            self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Attempt):
            # MISSING-05 FIX: complete try/catch
            fail_name = node.failure_name or "e"
            self.emit("try {")
            self.indent += 1
            if node.call is not None:
                call_expr = self.expr_to_cpp(node.call)
                result = node.result_name or "__result"
                inferred = self._infer_type_from_expr(node.call) or "auto"
                self.emit(f"auto {result} = {call_expr};")
                self.declared_vars[result] = inferred
            for stmt in node.success_body:
                self.emit_node(stmt)
            self.indent -= 1
            self.emit(f"}} catch (const std::exception& {fail_name}) {{")
            self.indent += 1
            if node.failure_body:
                for stmt in node.failure_body:
                    self.emit_node(stmt)
            else:
                self.emit(f"/* unhandled exception: {fail_name}.what() */")
            self.indent -= 1
            self.emit("}")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Return):
            # BUG-09 FIX
            if isinstance(node.value, FuncCall):
                if node.value.name in ('__produce_success', 'success'):
                    inner = self.expr_to_cpp(node.value.args[0]) if node.value.args else ""
                    self.emit(f"return {inner};")
                    return
                if node.value.name == 'failure':
                    msg = self.expr_to_cpp(node.value.args[0]) if node.value.args else '"error"'
                    self.emit(f"throw std::runtime_error({msg});")
                    return
            self.emit(f"return {self.expr_to_cpp(node.value)};")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Assert):
            self.emit(f"assert({self.expr_to_cpp(node.cond)});")
            return

        # ----------------------------------------------------------------
        if isinstance(node, Print):
            fmt_parts, args = [], []
            for p in node.parts:
                if isinstance(p, Literal) and isinstance(p.value, str):
                    escaped = p.value.replace("\\", "\\\\").replace("\n", "\\n")
                    fmt_parts.append(escaped)
                else:
                    spec = self._format_spec(p)
                    fmt_parts.append(spec)
                    expr = self.expr_to_cpp(p)
                    if isinstance(p, Identifier) and p.name in self.declared_vars:
                        vt = self.declared_vars[p.name]
                        if any(vt.startswith(px) for px in
                               ['unique handle to ', 'shared handle to ', 'weak handle to ']):
                            expr = f"*{expr}"
                    args.append(expr)
            fmt = "".join(fmt_parts)
            if args:
                self.emit(f'std::printf("{fmt}", {", ".join(args)});')
            else:
                self.emit(f'std::printf("{fmt}");')
            return

        # ----------------------------------------------------------------
        if isinstance(node, FuncCall):
            c_name = self._resolve_call_name(node.name)
            if c_name == "__defer_release":
                self.emit(f"/* defer: {self.expr_to_cpp(node.args[0])} */")
            elif c_name == "release":
                arg = self.expr_to_cpp(node.args[0])
                arg_type = self.declared_vars.get(getattr(node.args[0], 'name', ''), '')
                if any(arg_type.startswith(p) for p in ('unique handle to ', 'shared handle to ')):
                    self.emit(f"{arg}.reset();")
                else:
                    self.emit(f"delete {arg};")
            else:
                args = ", ".join(self.expr_to_cpp(a) for a in node.args)
                if '->' in c_name:
                    parts = c_name.split('->')
                    self.emit(f"{parts[0]}->{parts[1]}({args});")
                else:
                    self.emit(f"{c_name}({args});")
            return

        # ----------------------------------------------------------------
        if isinstance(node, ImportC):
            params = ", ".join(self.type_to_cpp(p) for p in node.params)
            self.emit(f"extern {self.type_to_cpp(node.ret_type)} {node.alias}({params});")
            return

        if isinstance(node, ImportCpp):
            if node.item_type == 'action':
                self.imported_actions[node.alias] = (node.params, node.ret_type)
            elif node.item_type == 'container':
                self.imported_containers[node.alias] = self._map_container(node.item_name)
            return

        if isinstance(node, ExternFn):
            params = ", ".join(f"{self.type_to_cpp(pt)} {pn}" for pn, pt in node.params)
            ret = self.type_to_cpp(node.ret_type)
            if node.syscall_name:
                self.emit(f"/* @syscall: {node.syscall_name} */")
            self.emit(f"extern {ret} {node.name}({params});")
            return

        if isinstance(node, Use):
            # BUG-05 FIX
            inc_path = _USE_INCLUDE_MAP.get(node.path, f"dictum_{node.path.lower()}.h")
            if node.is_system or not inc_path.startswith('dictum_'):
                inc_line = f"#include <{inc_path}>"
            else:
                inc_line = f'#include "{inc_path}"'
            if self._includes_emitted:
                self.emit(inc_line)
            else:
                self._extra_includes.append(inc_line)
            return

        if isinstance(node, UnsafeBlock):
            self.emit("/* unsafe block */")
            for stmt in node.body: self.emit_node(stmt)
            return

        # ----------------------------------------------------------------
        # Polyglot nodes — C++ emitter treatment
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
                ns = node.name
                self.emit(f"namespace {ns} {{  /* polyglot module backend={node.backend} safety={node.safety} */")
                self.indent += 1
                for stmt in node.body:
                    self.emit_node(stmt)
                self.indent -= 1
                self.emit(f"}}  /* namespace {ns} */")
                return

            if isinstance(node, PolyglotImport):
                inc = f"{node.module_name}_cxx.hpp"
                self.emit(f'#include "{inc}"  /* polyglot import {node.module_name} */')
                return

            if isinstance(node, PolyglotCall):
                # C++ calls go through the namespace wrapper
                ns_fn = f"dictum::{node.module}::{node.function}"
                args = ", ".join(self.expr_to_cpp(a) for a in node.args)
                if node.result_name:
                    self.emit(f"auto {node.result_name} = {ns_fn}({args});")
                else:
                    self.emit(f"{ns_fn}({args});")
                return

            if isinstance(node, UnsafeForeignCall):
                args = ", ".join(self.expr_to_cpp(a) for a in node.args)
                ret_type = self.type_to_cpp(node.result_type) if node.result_type else "void*"
                if node.result_name:
                    self.emit(f"/* unsafe foreign call */")
                    self.emit(f"auto {node.result_name} = reinterpret_cast<{ret_type}(*)()>"
                               f"(\"{node.symbol}\")();  /* {args} */")
                else:
                    self.emit(f"/* unsafe foreign: {node.symbol}({args}) */")
                return

            if isinstance(node, BuildDirective):
                if node.kind == 'link':
                    self.emit(f"/* #[link \"{node.value}\"] — add to target_link_libraries() */")
                else:
                    self.emit(f"/* #[{node.kind} \"{node.value}\"] */")
                return

            if isinstance(node, ForeignShape):
                pfx = "struct __attribute__((packed))" if node.packed else "struct"
                self.emit(f"/* foreign {node.source_language} struct: {node.name} */")
                self.emit(f"extern \"C\" {pfx} {node.name} {{")
                self.indent += 1
                for fname, ftype in node.fields:
                    self.emit(f"{self.type_to_cpp(ftype)} {fname};")
                self.indent -= 1
                self.emit("};")
                return

        self.emit(f"/* unhandled: {type(node).__name__} */")

    # ------------------------------------------------------------------
    def _emit_fwd_decl(self, node: Action) -> None:
        """BUG-10 FIX: emit forward declaration."""
        params = ", ".join(f"{self.type_to_cpp(pt)} {pn}" for pn, pt in node.params)
        ret = self.type_to_cpp(node.ret_type)
        if node.ret_type == 'result':
            ret = 'std::optional<int32_t>'
        if node.template_params:
            tparams = ", ".join(f"typename {tp[0]}" for tp in node.template_params)
            self.emit(f"template <{tparams}>")
        self.emit(f"{ret} {node.name}({params});")

    def _emit_includes(self) -> None:
        includes = [
            "#include <cstdint>", "#include <cstdbool>", "#include <cstdio>",
            "#include <cstdlib>", "#include <cstring>", "#include <cassert>",
            "#include <cmath>", "#include <memory>", "#include <vector>",
            "#include <map>", "#include <string>", "#include <functional>",
            "#include <optional>", "#include <stdexcept>",
        ]
        if self.cpp_standard >= 20:
            includes.append("#include <concepts>")
        for inc in includes:
            self.emit(inc)
        for inc in self._extra_includes:
            self.emit(inc)
        self._includes = includes
        self._includes_emitted = True

    def _format_spec(self, p: Node) -> str:
        if isinstance(p, Literal):
            if isinstance(p.value, float): return "%f"
            if isinstance(p.value, str):   return "%s"
            return "%d"
        if isinstance(p, Identifier):
            t = self.declared_vars.get(p.name, '')
            if 'double' in t or 'float' in t: return "%f"
            if 'char' in t:                   return "%s"
            if 'size_t' in t:                 return "%zu"
            n = p.name.lower()
            if any(h in n for h in ('frac','dist','price','rate','double','float')): return "%f"
            if any(h in n for h in ('name','msg','text','str')): return "%s"
            return "%d"
        if isinstance(p, FieldAccess):
            if p.obj in self.shapes:
                ft = self.shapes[p.obj].get(p.field, '')
                if 'fractional' in ft or 'decimal' in ft: return "%f"
                if ft == 'text': return "%s"
            return "%d"
        return "%d"

    def _map_container(self, item_name: str) -> str:
        parts = item_name.split()
        if parts[0] == 'vector' and 'of' in parts:
            idx = parts.index('of')
            inner = ' '.join(parts[idx+1:])
            return f"std::vector<{self.type_to_cpp(inner)}>"
        if parts[0] == 'map' and 'of' in parts and 'to' in parts:
            oi = parts.index('of'); ti = parts.index('to')
            k = ' '.join(parts[oi+1:ti]); v = ' '.join(parts[ti+1:])
            return f"std::map<{self.type_to_cpp(k)}, {self.type_to_cpp(v)}>"
        return item_name

    def _analyze_captures(self, body: List[Node], param_names: Set[str]) -> Set[str]:
        captures: Set[str] = set()
        def _walk(n: Node) -> None:
            if isinstance(n, Identifier):
                if n.name not in param_names and n.name in self.declared_vars:
                    captures.add(n.name)
            elif isinstance(n, (BinaryOp,)):
                _walk(n.left); _walk(n.right)
            elif isinstance(n, UnaryOp):
                _walk(n.operand)
            elif isinstance(n, FuncCall):
                for a in n.args: _walk(a)
            elif isinstance(n, FieldAccess):
                if n.obj in self.declared_vars and n.obj not in param_names:
                    captures.add(n.obj)
            elif isinstance(n, IndexAccess):
                if n.collection in self.declared_vars and n.collection not in param_names:
                    captures.add(n.collection)
                _walk(n.index)
            elif isinstance(n, (Assignment,)):
                if isinstance(n.target, str) and n.target in self.declared_vars:
                    captures.add(n.target)
                _walk(n.value)
            elif isinstance(n, Return):
                _walk(n.value)
            elif isinstance(n, If):
                _walk(n.cond)
                for s in n.then_body: _walk(s)
                for s in n.else_body: _walk(s)
            elif isinstance(n, While):
                _walk(n.cond)
                for s in n.body: _walk(s)
            elif isinstance(n, (ForEach, Repeat)):
                for s in n.body: _walk(s)
            elif isinstance(n, Print):
                for part in n.parts: _walk(part)
        for stmt in body: _walk(stmt)
        return captures

    # ------------------------------------------------------------------
    def get_output(self) -> str:
        if self._action_buffer:
            # Inject after includes block
            last_inc = -1
            for i, ln in enumerate(self.output):
                if ln.strip().startswith('#include'):
                    last_inc = i
            if last_inc >= 0:
                inject = [''] + self._action_buffer
                self.output = (self.output[:last_inc + 1]
                               + inject
                               + self.output[last_inc + 1:])
            self._action_buffer.clear()
        return "\n".join(self.output)

    def get_header_output(self, ast: List[Node]) -> str:
        lines = ["#pragma once", "#include <cstdint>", "#include <cstdbool>",
                 "#include <cstddef>", "#include <memory>", "#include <string>",
                 "#include <vector>", "#include <map>", "#include <functional>", ""]
        def _emit(nodes: List[Node]) -> None:
            for node in nodes:
                if isinstance(node, Shape) and node.export:
                    is_class = bool(node.methods or node.constructors or node.destructor or node.parent)
                    keyword = "class" if is_class else "struct"
                    pfx = f"{keyword} __attribute__((packed))" if node.is_packed else keyword
                    inh = f" : public {node.parent}" if node.parent else ""
                    lines.append(f"{pfx} {node.name}{inh} {{")
                    lines.append("public:")
                    for fname, ftype in node.fields:
                        lines.append(f"    {self.type_to_cpp(ftype)} {fname};")
                    for m in node.methods:
                        params = ", ".join(f"{self.type_to_cpp(pt)} {pn}" for pn, pt in m.params)
                        virt = "virtual " if (m.is_virtual or is_class) else ""
                        override = " override" if m.is_override else ""
                        lines.append(f"    {virt}{self.type_to_cpp(m.ret_type)} {m.name}({params}){override};")
                    lines.append("};")
                    lines.append("")
                elif isinstance(node, VarDecl) and node.export:
                    lines.append(f"extern {self.type_to_cpp(node.type)} {node.name};")
                elif isinstance(node, Action) and node.export:
                    params = ", ".join(f"{self.type_to_cpp(pt)} {pn}" for pn, pt in node.params) or ""
                    lines.append(f"extern {self.type_to_cpp(node.ret_type)} {node.name}({params});")
                elif isinstance(node, (Program, Module)):
                    _emit(node.body)
        _emit(ast)
        return "\n".join(lines)
