"""
Dictum AST Nodes — shared dataclasses for all compiler phases.
Extracted from monolith transpiler.py v3.3.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any, Dict


@dataclass
class Node:
    line: int = field(default=0, kw_only=True)


@dataclass
class Program(Node):
    name: str = ''
    body: List[Node] = field(default_factory=list)
    export: bool = False


@dataclass
class Module(Node):
    name: str = ''
    body: List[Node] = field(default_factory=list)
    export: bool = False


@dataclass
class Shape(Node):
    name: str = ''
    fields: List[Tuple[str, str]] = field(default_factory=list)
    is_packed: bool = False
    parent: Optional[str] = None
    methods: List['Method'] = field(default_factory=list)
    constructors: List['Constructor'] = field(default_factory=list)
    destructor: Optional['Destructor'] = None
    access_map: Dict[str, str] = field(default_factory=dict)
    export: bool = False


@dataclass
class Method(Node):
    name: str = ''
    params: List[Tuple[str, str]] = field(default_factory=list)
    ret_type: str = ''
    body: List[Node] = field(default_factory=list)
    access: str = 'public'
    is_virtual: bool = False
    is_override: bool = False


@dataclass
class Constructor(Node):
    params: List[Tuple[str, str]] = field(default_factory=list)
    body: List[Node] = field(default_factory=list)
    access: str = 'public'


@dataclass
class Destructor(Node):
    body: List[Node] = field(default_factory=list)
    access: str = 'public'
    is_virtual: bool = False


@dataclass
class VarDecl(Node):
    name: str = ''
    type: str = ''
    value: Optional[Node] = None
    export: bool = False


@dataclass
class Assignment(Node):
    target: str = ''
    value: Node = field(default_factory=lambda: Literal(0))


@dataclass
class Action(Node):
    name: str = ''
    params: List[Tuple[str, str]] = field(default_factory=list)
    ret_type: str = ''
    body: List[Node] = field(default_factory=list)
    template_params: List[Tuple[str, str]] = field(default_factory=list)
    export: bool = False


@dataclass
class FuncCall(Node):
    name: str = ''
    args: List[Node] = field(default_factory=list)


@dataclass
class Return(Node):
    value: Node = field(default_factory=lambda: Literal(0))


@dataclass
class If(Node):
    cond: Node = field(default_factory=lambda: Literal(True))
    then_body: List[Node] = field(default_factory=list)
    else_body: List[Node] = field(default_factory=list)


@dataclass
class While(Node):
    cond: Node = field(default_factory=lambda: Literal(True))
    body: List[Node] = field(default_factory=list)


@dataclass
class ForEach(Node):
    item: str = ''
    collection: str = ''
    body: List[Node] = field(default_factory=list)


@dataclass
class Repeat(Node):
    count: Node = field(default_factory=lambda: Literal(0))
    counter: str = ''
    body: List[Node] = field(default_factory=list)


@dataclass
class Attempt(Node):
    call: Optional['FuncCall'] = None
    result_name: str = ''
    success_body: List[Node] = field(default_factory=list)
    failure_name: str = ''
    failure_body: List[Node] = field(default_factory=list)


@dataclass
class Literal(Node):
    value: Any = None


@dataclass
class Identifier(Node):
    name: str = ''


@dataclass
class BinaryOp(Node):
    op: str = ''
    left: Node = field(default_factory=lambda: Literal(0))
    right: Node = field(default_factory=lambda: Literal(0))


@dataclass
class UnaryOp(Node):
    op: str = ''
    operand: Node = field(default_factory=lambda: Literal(0))


@dataclass
class FieldAccess(Node):
    obj: str = ''
    field: str = ''


@dataclass
class IndexAccess(Node):
    collection: str = ''
    index: Node = field(default_factory=lambda: Literal(0))


@dataclass
class Assert(Node):
    cond: Node = field(default_factory=lambda: Literal(True))


@dataclass
class Print(Node):
    parts: List[Node] = field(default_factory=list)


@dataclass
class ImportC(Node):
    action_name: str = ''
    params: List[str] = field(default_factory=list)
    ret_type: str = ''
    alias: str = ''


@dataclass
class ImportCpp(Node):
    item_type: str = ''
    item_name: str = ''
    params: List[str] = field(default_factory=list)
    ret_type: str = ''
    alias: str = ''


@dataclass
class ImportDict(Node):
    """MISSING-08: import MyModule from "mymodule.dict"
    Resolved by the Transpiler at run-time: transpile the .dict file,
    emit #include "mymodule.h", and return the .c/.h pair for the module.
    """
    module_name: str = ''   # e.g. "MyModule"
    file_path:   str = ''   # e.g. "mymodule.dict"
    alias:       str = ''   # optional alias, defaults to module_name


@dataclass
class UnsafeBlock(Node):
    body: List[Node] = field(default_factory=list)


@dataclass
class ExternFn(Node):
    name: str = ''
    params: List[Tuple[str, str]] = field(default_factory=list)
    ret_type: str = ''
    syscall_name: Optional[str] = None


@dataclass
class Transmute(Node):
    expr: Node = field(default_factory=lambda: Literal(0))
    type: str = ''


@dataclass
class Use(Node):
    path: str = ''
    is_system: bool = False


@dataclass
class Bind(Node):
    name: str = ''
    params: List[Tuple[str, str]] = field(default_factory=list)
    ret_type: str = ''
    alias: str = ''


@dataclass
class NewExpr(Node):
    type_name: str = ''
    args: List[Node] = field(default_factory=list)


@dataclass
class LambdaExpr(Node):
    params: List[Tuple[str, str]] = field(default_factory=list)
    ret_type: str = ''
    body: List[Node] = field(default_factory=list)


# Possibilities (enum) — not a dataclass in original, kept as simple class
class Possibilities:
    def __init__(self, name: str, variants: List[str], line: int = 0):
        self.name = name
        self.variants = variants
        self.line = line
