"""
Dictum Validator — semantic analysis / type checking / ownership tracking.
Extracted from transpiler.py v3.3.

Fixes applied:
  MISSING-09: 'truth value' and 'bool' consistently mapped; 'decimal number'
              and 'decimal' now accepted as aliases for 'fractional number'.
  BUG-01:     Validator now auto-declares undeclared assignment targets via
              infer_type() rather than emitting an error (mirrors emitter
              behaviour where a declaration is auto-generated).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Set

from .ast_nodes import (
    Node, Program, Module, Shape, Method, Constructor, Destructor,
    VarDecl, Assignment, Action, FuncCall, Return, If, While, ForEach,
    Repeat, Attempt, Literal, Identifier, BinaryOp, UnaryOp,
    FieldAccess, IndexAccess, Assert, Print, ImportC, ImportCpp,
    UnsafeBlock, ExternFn, Transmute, Use, Bind, NewExpr, LambdaExpr,
    Possibilities,
)


class ValidationError(Exception):
    pass


@dataclass
class VarInfo:
    name: str
    type: str
    initialized: bool = False
    is_handle: bool = False
    is_array: bool = False
    array_size: Optional[int] = None
    released: bool = False
    line: int = 0


@dataclass
class ActionSig:
    name: str
    params: List[Tuple[str, str]]
    ret_type: str
    line: int = 0
    template_params: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class ShapeDef:
    name: str
    fields: Dict[str, str]
    line: int = 0


class Scope:
    def __init__(self, parent: Optional['Scope'] = None):
        self.parent = parent
        self.vars: Dict[str, VarInfo] = {}
        self.children: List['Scope'] = []
        if parent:
            parent.children.append(self)

    def declare(self, info: VarInfo) -> None:
        if info.name in self.vars:
            raise ValidationError(
                f"Variable '{info.name}' already declared in this scope (line {info.line})"
            )
        self.vars[info.name] = info

    def resolve(self, name: str) -> Optional[VarInfo]:
        if name in self.vars:
            return self.vars[name]
        if self.parent:
            return self.parent.resolve(name)
        return None

    def all_vars(self) -> Dict[str, VarInfo]:
        result = {}
        if self.parent:
            result.update(self.parent.all_vars())
        result.update(self.vars)
        return result


class Validator:
    # MISSING-09 FIX: added 'bool', 'decimal number', 'decimal' aliases
    PRIMITIVE_TYPES: Set[str] = {
        "whole number", "count", "fractional number", "decimal number", "decimal",
        "truth value", "bool",
        "byte", "text", "handle to bytes", "u16", "u32", "i32", "i64", "u64",
    }

    CPP_ONLY_PREFIXES = {
        'unique handle to ':  "Smart pointers require --backend cpp",
        'shared handle to ':  "Smart pointers require --backend cpp",
        'weak handle to ':    "Smart pointers require --backend cpp",
        'raw handle to ':     "Smart pointers require --backend cpp",
        'const ref ':         "References require --backend cpp",
        'ref ':               "References require --backend cpp",
        'move ':              "Move semantics require --backend cpp",
    }

    NUMERIC_TYPES: Set[str] = {
        "whole number", "count", "fractional number", "decimal number", "decimal",
        "byte", "u16", "u32", "i32", "i64", "u64",
    }

    def __init__(self, cpp_mode: bool = False):
        self.shapes: Dict[str, ShapeDef] = {}
        self.actions: Dict[str, ActionSig] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.in_unsafe = False
        self.cpp_mode = cpp_mode
        self.classes: Dict[str, Shape] = {}
        self.current_class: Optional[str] = None
        self.needed_headers: Set[str] = set()

    def error(self, msg: str, line: int = 0) -> None:
        self.errors.append(f"[Line {line}] {msg}" if line else msg)

    def warning(self, msg: str, line: int = 0) -> None:
        self.warnings.append(f"[Line {line}] {msg}" if line else msg)

    def is_valid_type(self, t: str) -> bool:
        base = t
        if '.' in base:
            base = base.split('.')[-1]
        if base in self.PRIMITIVE_TYPES or base in self.shapes:
            return True
        if not self.cpp_mode:
            for prefix in self.CPP_ONLY_PREFIXES:
                if t.startswith(prefix):
                    return self.is_valid_type(t[len(prefix):].strip())
            if t.startswith('action taking '):
                return False
            return False
        for prefix in ['unique handle to ', 'shared handle to ', 'weak handle to ', 'raw handle to ']:
            if t.startswith(prefix):
                return self.is_valid_type(t[len(prefix):].strip())
        for prefix in ['const ref ', 'ref ', 'move ']:
            if t.startswith(prefix):
                return self.is_valid_type(t[len(prefix):].strip())
        if t.startswith('action taking ') or t.startswith('*'):
            return True
        return False

    # ------------------------------------------------------------------
    def collect_globals(self, nodes: List[Node]) -> None:
        for node in nodes:
            if isinstance(node, Shape):
                fields = {fname: ftype for fname, ftype in node.fields}
                self.shapes[node.name] = ShapeDef(name=node.name, fields=fields, line=node.line)
                if self.cpp_mode and (node.methods or node.constructors or node.destructor or node.parent):
                    self.classes[node.name] = node
            elif isinstance(node, Action):
                self.actions[node.name] = ActionSig(
                    name=node.name, params=node.params, ret_type=node.ret_type,
                    line=node.line, template_params=node.template_params)
            elif isinstance(node, ExternFn):
                self.actions[node.name] = ActionSig(
                    name=node.name, params=node.params, ret_type=node.ret_type, line=node.line)
            elif isinstance(node, (Module, Program)):
                self.collect_globals(node.body)

    def validate(self, nodes: List[Node]) -> Tuple[bool, List[str], List[str]]:
        self.errors.clear(); self.warnings.clear()
        self.collect_globals(nodes)
        for node in nodes:
            self.validate_top_level(node)
        return (len(self.errors) == 0, self.errors, self.warnings)

    def validate_top_level(self, node: Node) -> None:
        if isinstance(node, Program):
            scope = Scope()
            for stmt in node.body:
                if isinstance(stmt, VarDecl):
                    self.declare_var(stmt, scope)
                elif isinstance(stmt, Action):
                    pass
                elif isinstance(stmt, Shape):
                    pass
            for stmt in node.body:
                if isinstance(stmt, (VarDecl, Action, Shape, Module, ImportC, ExternFn, UnsafeBlock, ImportCpp)):
                    self.validate_node(stmt, scope)
                else:
                    self.validate_statement(stmt, scope)
            self.check_scope_ownership(scope, "program exit")
        elif isinstance(node, Module):
            scope = Scope()
            for stmt in node.body:
                if isinstance(stmt, VarDecl):
                    self.declare_var(stmt, scope)
            for stmt in node.body:
                self.validate_node(stmt, scope)
            self.check_scope_ownership(scope, f"module '{node.name}' exit")
        elif isinstance(node, (Action, Shape, ImportC, ExternFn, ImportCpp)):
            scope = Scope()
            self.validate_node(node, scope)

    def validate_node(self, node: Node, scope: Scope) -> None:
        if isinstance(node, VarDecl):           self.validate_vardecl(node, scope)
        elif isinstance(node, Assignment):      self.validate_assignment(node, scope)
        elif isinstance(node, Action):          self.validate_action(node, scope)
        elif isinstance(node, If):              self.validate_if(node, scope)
        elif isinstance(node, While):           self.validate_while(node, scope)
        elif isinstance(node, ForEach):         self.validate_foreach(node, scope)
        elif isinstance(node, Repeat):          self.validate_repeat(node, scope)
        elif isinstance(node, Attempt):         self.validate_attempt(node, scope)
        elif isinstance(node, Return):          self.validate_return(node, scope)
        elif isinstance(node, Assert):          self.validate_assert(node, scope)
        elif isinstance(node, Print):           self.validate_print(node, scope)
        elif isinstance(node, FuncCall):        self.validate_funccall(node, scope)
        elif isinstance(node, Shape):           self.validate_shape(node, scope)
        elif isinstance(node, ImportC):         self.validate_import(node, scope)
        elif isinstance(node, ImportCpp):       self.validate_import_cpp(node, scope)
        elif isinstance(node, ExternFn):        pass
        elif isinstance(node, UnsafeBlock):     self.validate_unsafe(node, scope)
        elif isinstance(node, (Program, Module)): self.validate_top_level(node)
        elif isinstance(node, Method):          self.validate_method(node, scope)
        elif isinstance(node, Constructor):     self.validate_constructor(node, scope)
        elif isinstance(node, Destructor):      self.validate_destructor(node, scope)
        elif isinstance(node, NewExpr):
            if not self.cpp_mode:
                self.error("'new' expressions require --backend cpp", node.line)
            else:
                self.validate_new_expr(node, scope)
        elif isinstance(node, LambdaExpr):
            if not self.cpp_mode:
                self.error("Lambda expressions require --backend cpp", node.line)
            else:
                self.validate_lambda(node, scope)

    def validate_statement(self, node: Node, scope: Scope) -> None:
        self.validate_node(node, scope)

    # ------------------------------------------------------------------
    # Variable declaration & assignment
    # ------------------------------------------------------------------
    def declare_var(self, node: VarDecl, scope: Scope) -> None:
        is_handle = node.type == "handle to bytes"
        is_smart = self.cpp_mode and any(
            node.type.startswith(p) for p in
            ['unique handle to ', 'shared handle to ', 'weak handle to ', 'raw handle to '])
        is_array = isinstance(node.value, Literal) and isinstance(node.value.value, list)
        array_size = len(node.value.value) if is_array else None
        if isinstance(node.value, UnaryOp) and node.value.op == "room_for":
            is_handle = True
        initialized = (node.value is not None) or isinstance(node.value, NewExpr)
        info = VarInfo(name=node.name, type=node.type, initialized=initialized,
                       is_handle=is_handle or is_smart, is_array=is_array,
                       array_size=array_size, line=node.line)
        scope.declare(info)
        if is_array:
            scope.declare(VarInfo(name=f"{node.name}_count", type="count",
                                  initialized=True, line=node.line))
            scope.declare(VarInfo(name=f"{node.name}_size", type="count",
                                  initialized=True, line=node.line))

    def validate_vardecl(self, node: VarDecl, scope: Scope) -> None:
        if not self.is_valid_type(node.type):
            if not self.cpp_mode:
                for prefix, msg in self.CPP_ONLY_PREFIXES.items():
                    if node.type.startswith(prefix):
                        self.error(f"{msg}. Type is valid but wrapper requires C++ backend.", node.line)
                        return
            self.error(f"Unknown type '{node.type}'", node.line)
            return
        if node.value:
            self.check_expression(node.value, scope)
        if scope.resolve(node.name) is None or scope.vars.get(node.name) is None:
            self.declare_var(node, scope)

    def validate_assignment(self, node: Assignment, scope: Scope) -> None:
        self.check_expression(node.value, scope)
        target_name = node.target
        if '.' in target_name:
            parts = target_name.split('.')
            base = parts[0]
            info = scope.resolve(base)
            if info is None:
                self.error(f"Assignment to unknown variable '{base}'", node.line)
                return
        else:
            info = scope.resolve(target_name)
            if info is None:
                # BUG-01 FIX: auto-declare on first assignment
                inferred_type = self.infer_type(node.value, scope)
                if inferred_type:
                    scope.declare(VarInfo(name=target_name, type=inferred_type,
                                          initialized=True, line=node.line))
                else:
                    self.error(f"Assignment to unknown variable '{target_name}'", node.line)
            else:
                info.initialized = True

    def validate_action(self, node: Action, scope: Scope) -> None:
        if not self.cpp_mode and node.template_params:
            self.error("Templates require --backend cpp", node.line)
        body_scope = Scope(parent=scope)
        template_type_names = {tp[0] for tp in node.template_params}
        template_type_names.update({tp[1] for tp in node.template_params})
        old = self.PRIMITIVE_TYPES.copy()
        self.PRIMITIVE_TYPES.update(template_type_names)
        for pname, ptype in node.params:
            body_scope.declare(VarInfo(name=pname, type=ptype, initialized=True,
                                       is_handle=(ptype == "handle to bytes"), line=node.line))
        for stmt in node.body:
            self.validate_statement(stmt, body_scope)
        self.PRIMITIVE_TYPES = old
        self.check_scope_ownership(body_scope, f"action '{node.name}' exit")

    def validate_method(self, node: Method, scope: Scope) -> None:
        body_scope = Scope(parent=scope)
        if self.current_class and self.current_class in self.shapes:
            for fname, ftype in self.shapes[self.current_class].fields.items():
                body_scope.declare(VarInfo(name=fname, type=ftype, initialized=True, line=node.line))
        for pname, ptype in node.params:
            body_scope.declare(VarInfo(name=pname, type=ptype, initialized=True, line=node.line))
        for stmt in node.body:
            self.validate_statement(stmt, body_scope)

    def validate_constructor(self, node: Constructor, scope: Scope) -> None:
        body_scope = Scope(parent=scope)
        if self.current_class and self.current_class in self.shapes:
            for fname, ftype in self.shapes[self.current_class].fields.items():
                body_scope.declare(VarInfo(name=fname, type=ftype, initialized=True, line=node.line))
        for pname, ptype in node.params:
            body_scope.declare(VarInfo(name=pname, type=ptype, initialized=True, line=node.line))
        for stmt in node.body:
            self.validate_statement(stmt, body_scope)

    def validate_destructor(self, node: Destructor, scope: Scope) -> None:
        body_scope = Scope(parent=scope)
        if self.current_class and self.current_class in self.shapes:
            for fname, ftype in self.shapes[self.current_class].fields.items():
                body_scope.declare(VarInfo(name=fname, type=ftype, initialized=True, line=node.line))
        for stmt in node.body:
            self.validate_statement(stmt, body_scope)

    def validate_new_expr(self, node: NewExpr, scope: Scope) -> Optional[str]:
        type_name = node.type_name.split('.')[-1] if '.' in node.type_name else node.type_name
        if type_name not in self.shapes and type_name not in self.classes:
            self.warning(f"new of unknown type '{node.type_name}'", node.line)
        for arg in node.args:
            self.check_expression(arg, scope)
        return node.type_name

    def validate_lambda(self, node: LambdaExpr, scope: Scope) -> Optional[str]:
        body_scope = Scope(parent=scope)
        for pname, ptype in node.params:
            body_scope.declare(VarInfo(name=pname, type=ptype, initialized=True, line=node.line))
        for stmt in node.body:
            self.validate_statement(stmt, body_scope)
        return f"action taking {', '.join(p[1] for p in node.params)} produces {node.ret_type}"

    def check_scope_ownership(self, scope: Scope, context: str) -> None:
        reported = set()
        for name, info in scope.all_vars().items():
            if info.is_handle and not info.released:
                if self.cpp_mode and info.type.startswith(('unique handle to ', 'shared handle to ')):
                    continue
                key = (name, context, info.line)
                if key in reported: continue
                reported.add(key)
                self.error(f"Ownership violation: handle '{name}' not released at {context}", info.line)

    def validate_if(self, node: If, scope: Scope) -> None:
        self.check_expression(node.cond, scope)
        then_scope = Scope(parent=scope)
        for stmt in node.then_body:
            self.validate_statement(stmt, then_scope)
        if node.else_body:
            else_scope = Scope(parent=scope)
            for stmt in node.else_body:
                self.validate_statement(stmt, else_scope)

    def validate_while(self, node: While, scope: Scope) -> None:
        self.check_expression(node.cond, scope)
        body_scope = Scope(parent=scope)
        for stmt in node.body:
            self.validate_statement(stmt, body_scope)

    def validate_foreach(self, node: ForEach, scope: Scope) -> None:
        coll_info = scope.resolve(node.collection)
        if coll_info is None:
            self.error(f"For-each on unknown collection '{node.collection}'", node.line)
        body_scope = Scope(parent=scope)
        item_type = coll_info.type if coll_info else "whole number"
        body_scope.declare(VarInfo(name=node.item, type=item_type, initialized=True, line=node.line))
        for stmt in node.body:
            self.validate_statement(stmt, body_scope)

    def validate_repeat(self, node: Repeat, scope: Scope) -> None:
        self.check_expression(node.count, scope)
        body_scope = Scope(parent=scope)
        body_scope.declare(VarInfo(name=node.counter, type="whole number", initialized=True, line=node.line))
        for stmt in node.body:
            self.validate_statement(stmt, body_scope)

    def validate_attempt(self, node: Attempt, scope: Scope) -> None:
        if node.call is not None:
            self.validate_funccall(node.call, scope)
        if node.result_name:
            existing = scope.resolve(node.result_name)
            if existing is None:
                ret_type = "whole number"
                if node.call and node.call.name in self.actions:
                    ret_type = self.actions[node.call.name].ret_type
                scope.declare(VarInfo(name=node.result_name, type=ret_type,
                                      initialized=True, line=node.line))
            else:
                existing.initialized = True
        for stmt in node.success_body:
            self.validate_statement(stmt, scope)
        if node.failure_name:
            fail_scope = Scope(parent=scope)
            fail_scope.declare(VarInfo(name=node.failure_name, type="text",
                                       initialized=True, line=node.line))
            for stmt in node.failure_body:
                self.validate_statement(stmt, fail_scope)
        else:
            for stmt in node.failure_body:
                self.validate_statement(stmt, scope)

    def validate_return(self, node: Return, scope: Scope) -> None:
        self.check_expression(node.value, scope)
        if isinstance(node.value, FuncCall):
            if node.value.name in ('success', '__produce_success') and node.value.args:
                arg = node.value.args[0]
                if isinstance(arg, Identifier):
                    info = scope.resolve(arg.name)
                    if info and info.is_handle:
                        info.released = True

    def validate_assert(self, node: Assert, scope: Scope) -> None:
        self.check_expression(node.cond, scope)

    def validate_print(self, node: Print, scope: Scope) -> None:
        for part in node.parts:
            self.check_expression(part, scope)

    def validate_funccall(self, node: FuncCall, scope: Scope) -> None:
        if node is None:
            return
        if node.name == "release":
            if len(node.args) != 1:
                self.error("release requires exactly one argument", node.line)
                return
            arg = node.args[0]
            if isinstance(arg, Identifier):
                info = scope.resolve(arg.name)
                if info and info.is_handle:
                    info.released = True
            return
        if node.name == "__defer_release":
            return
        if '->' in node.name:
            parts = node.name.split('->')
            obj_name = parts[0]
            obj_info = scope.resolve(obj_name)
            for arg in node.args:
                self.check_expression(arg, scope)
            return
        if node.name in self.actions:
            sig = self.actions[node.name]
            if len(node.args) != len(sig.params):
                self.error(f"Action '{node.name}' expects {len(sig.params)} args, got {len(node.args)}", node.line)
        else:
            if not node.name.startswith('_'):
                self.warning(f"Call to unknown action '{node.name}'", node.line)
        for arg in node.args:
            self.check_expression(arg, scope)

    def validate_shape(self, node: Shape, scope: Scope) -> None:
        if not self.cpp_mode:
            if node.methods: self.error("Class methods require --backend cpp", node.line)
            if node.constructors: self.error("Constructors require --backend cpp", node.line)
            if node.destructor: self.error("Destructors require --backend cpp", node.line)
            if node.parent: self.error("Inheritance requires --backend cpp", node.line)
        old = self.current_class; self.current_class = node.name
        for m in node.methods: self.validate_method(m, scope)
        for c in node.constructors: self.validate_constructor(c, scope)
        if node.destructor: self.validate_destructor(node.destructor, scope)
        self.current_class = old

    def validate_import(self, node: ImportC, scope: Scope) -> None:
        self.actions[node.alias] = ActionSig(
            name=node.alias,
            params=[(f"arg{i}", p) for i, p in enumerate(node.params)],
            ret_type=node.ret_type, line=node.line)

    def validate_import_cpp(self, node: ImportCpp, scope: Scope) -> None:
        if node.item_type == 'action':
            self.actions[node.alias] = ActionSig(
                name=node.alias,
                params=[(f"arg{i}", p) for i, p in enumerate(node.params)],
                ret_type=node.ret_type, line=node.line)
        elif node.item_type == 'container':
            self.PRIMITIVE_TYPES.add(node.alias)

    def validate_unsafe(self, node: UnsafeBlock, scope: Scope) -> None:
        old = self.in_unsafe; self.in_unsafe = True
        for stmt in node.body:
            self.validate_statement(stmt, scope)
        self.in_unsafe = old

    # ------------------------------------------------------------------
    # Type inference & expression checking
    # ------------------------------------------------------------------
    def check_expression(self, node: Node, scope: Scope) -> Optional[str]:
        if isinstance(node, Literal):
            if isinstance(node.value, bool):   return "truth value"
            if isinstance(node.value, int):    return "whole number"
            if isinstance(node.value, float):  return "fractional number"
            if isinstance(node.value, str):    return "text"
            if isinstance(node.value, list):   return "array"
            return None
        elif isinstance(node, Identifier):
            info = scope.resolve(node.name)
            if info is None:
                if self.current_class and self.current_class in self.shapes:
                    shape = self.shapes[self.current_class]
                    if node.name in shape.fields:
                        return shape.fields[node.name]
                self.error(f"Use of undeclared variable '{node.name}'", node.line)
                return None
            if not info.initialized:
                self.error(f"Use of uninitialized variable '{node.name}'", node.line)
            if info.is_handle and info.released:
                self.error(f"Use-after-free: handle '{node.name}' used after release", node.line)
            return info.type
        elif isinstance(node, FieldAccess):
            base_info = scope.resolve(node.obj)
            if base_info is None:
                self.error(f"Access to unknown object '{node.obj}'", node.line)
                return None
            base_type = base_info.type
            for prefix in ['const ref ', 'ref ', 'move ',
                           'unique handle to ', 'shared handle to ',
                           'weak handle to ', 'raw handle to ']:
                if base_type.startswith(prefix):
                    base_type = base_type[len(prefix):].strip(); break
            if '.' in base_type: base_type = base_type.split('.')[-1]
            if base_type not in self.shapes:
                return None
            shape = self.shapes[base_type]
            if node.field not in shape.fields:
                self.error(f"Shape '{base_type}' has no field '{node.field}'", node.line)
                return None
            return shape.fields[node.field]
        elif isinstance(node, IndexAccess):
            self.check_expression(node.index, scope)
            coll = scope.resolve(node.collection)
            return coll.type if coll else None
        elif isinstance(node, BinaryOp):
            left_type = self.check_expression(node.left, scope)
            right_type = self.check_expression(node.right, scope)
            if node.op in ('==', '!=', '>', '<', '>=', '<='):
                return "truth value"
            return left_type
        elif isinstance(node, UnaryOp):
            if node.op in ('count', 'length'): return "count"
            if node.op in ('tanh', 'sqrt', 'exp', 'sin', 'cos'): return "fractional number"
            if node.op == 'room_for': return "handle to bytes"
            return self.check_expression(node.operand, scope)
        elif isinstance(node, FuncCall):
            for arg in node.args: self.check_expression(arg, scope)
            if node.name in self.actions:
                return self.actions[node.name].ret_type
            return None
        elif isinstance(node, NewExpr):
            return self.validate_new_expr(node, scope)
        elif isinstance(node, LambdaExpr):
            return self.validate_lambda(node, scope)
        return None

    def infer_type(self, node: Node, scope: Scope) -> Optional[str]:
        if isinstance(node, Literal):
            if isinstance(node.value, bool):  return "truth value"
            if isinstance(node.value, int):   return "whole number"
            if isinstance(node.value, float): return "fractional number"
            if isinstance(node.value, str):   return "text"
        if isinstance(node, Identifier):
            info = scope.resolve(node.name)
            if info: return info.type
        if isinstance(node, FuncCall):
            return self.check_expression(node, scope)
        if isinstance(node, BinaryOp):
            return self.infer_type(node.left, scope)
        if isinstance(node, UnaryOp):
            if node.op == 'room_for': return "handle to bytes"
            return self.infer_type(node.operand, scope)
        if isinstance(node, NewExpr):
            return node.type_name
        return None
