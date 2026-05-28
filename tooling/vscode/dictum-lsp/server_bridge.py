"""
Dictum LSP Server Bridge — v5.0
Bridges the LSP server to the Dictum v5 transpiler (split package).

Updated from v3.3: imports from dictumc package, not monolith transpiler.py.
STDLIB_ACTION_FAMILIES format adapted from v5 flat dict.
"""
import sys
import os
from typing import List, Dict, Optional

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
sys.path.insert(0, os.path.normpath(_PROJECT_ROOT))

from dictumc.lexer import Lexer
from dictumc.parser import Parser
from dictumc.validator import Validator, ValidationError
from dictumc.grammar import DictumGrammar
from dictumc.stdlib_registry import DICTUM_STDLIB_TYPES, STDLIB_ACTION_FAMILIES


def get_diagnostics(source: str, cpp_mode: bool = False) -> List[dict]:
    """Run lexer → parser → validator and return LSP-compatible diagnostic dicts."""
    diagnostics = []
    try:
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens).parse()
        ok, errors, warnings = Validator(cpp_mode=cpp_mode).validate(ast)
        for e in errors:
            diagnostics.append({"severity": 1, "message": str(e), "source": "dictum"})
        for w in warnings:
            diagnostics.append({"severity": 2, "message": str(w), "source": "dictum"})
    except Exception as e:
        diagnostics.append({"severity": 1, "message": str(e), "source": "dictum-parse"})
    return diagnostics


def get_completions(source: str, position: int, cpp_mode: bool = False) -> List[dict]:
    """Return completion items at the given character position."""
    items = []
    try:
        g = DictumGrammar(cpp_mode=cpp_mode)
        tokens = g.get_valid_tokens() if hasattr(g, "get_valid_tokens") else []
        for tok in tokens:
            items.append({"label": tok, "kind": 14})  # kind 14 = keyword
    except Exception:
        pass
    # v5: STDLIB_ACTION_FAMILIES keys are "Module.fn" strings
    for key in STDLIB_ACTION_FAMILIES:
        items.append({"label": key, "kind": 3, "detail": f"stdlib"})
    return items


def get_hover(word: str) -> Optional[dict]:
    """Return hover documentation for a word (type or stdlib function)."""
    # v5: DICTUM_STDLIB_TYPES is a set of type name strings
    if word in DICTUM_STDLIB_TYPES:
        return {"contents": f"**{word}**\nDictum stdlib type → `dictum_{word}_t`"}
    # v5: STDLIB_ACTION_FAMILIES[Module.fn] = (c_name, params, ret)
    for key, (c_name, params, ret) in STDLIB_ACTION_FAMILIES.items():
        fn = key.split('.')[-1]
        if fn == word or key == word:
            takes_str = ', '.join(params) if params else 'nothing'
            return {
                "contents": (
                    f"**{key}**\n"
                    f"Takes: `{takes_str}`\n"
                    f"Produces: `{ret}`\n"
                    f"C: `{c_name}`"
                )
            }
    return None
