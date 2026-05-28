#!/usr/bin/env python3
"""
Dictum Language Server Protocol (LSP) Implementation — v5.0
Provides: diagnostics, completions, hover, go-to-definition.

Updated for v5: imports from split dictumc package.
STDLIB_ACTION_FAMILIES format changed from v3.3:
  v3.3: {family: [{name, takes, produces}]}
  v5:   {Module.fn: (c_name, [param_types], ret_type)}
This file adapts the v5 format for LSP use.
"""

import sys
import re
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Set

# Modern pygls v2.x API
try:
    from pygls.lsp.server import LanguageServer
    from lsprotocol import types as lsp
except ImportError:
    print("Install: pip install pygls lsprotocol", file=sys.stderr)
    sys.exit(1)

# Add project root to path
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _PROJECT_ROOT)

try:
    from dictumc.lexer import Lexer, TokenType
    from dictumc.parser import Parser
    from dictumc.validator import Validator, ValidationError
    from dictumc.stdlib_registry import DICTUM_STDLIB_TYPES, STDLIB_ACTION_FAMILIES
    _DICTUM_AVAILABLE = True
except ImportError:
    _DICTUM_AVAILABLE = False
    DICTUM_STDLIB_TYPES = set()
    STDLIB_ACTION_FAMILIES = {}
    class Lexer:
        def __init__(self, s): pass
        def tokenize(self): return []
    class Parser:
        def __init__(self, t): pass
        def parse(self): return []
    class Validator:
        def __init__(self, cpp_mode=False): pass
        def validate(self, nodes): return True, [], []


# ---------------------------------------------------------------------------
# Adapt v5 STDLIB_ACTION_FAMILIES to LSP-friendly grouped format
# v5 key: "Http.get" → (c_name, [param_types], ret_type)
# LSP needs: grouped by module with {name, takes, produces}
# ---------------------------------------------------------------------------

def _build_lsp_stdlib() -> Dict[str, List[dict]]:
    """Convert v5 flat dict to grouped format for LSP display."""
    grouped: Dict[str, List[dict]] = {}
    for key, (c_name, params, ret) in STDLIB_ACTION_FAMILIES.items():
        if '.' in key:
            family, fn_name = key.split('.', 1)
        else:
            family, fn_name = 'Core', key
        grouped.setdefault(family, []).append({
            'name': fn_name,
            'full_name': key,
            'c_name': c_name,
            'takes': params,
            'produces': ret,
        })
    return grouped

LSP_STDLIB = _build_lsp_stdlib()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    filename='/tmp/dictum-lsp.log',
    filemode='w',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('dictum-lsp')

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

server = LanguageServer('dictum-lsp', 'v5.0.0')


def _get_word_at_position(document, position: lsp.Position) -> str:
    try:
        line = document.lines[position.line]
    except IndexError:
        return ''
    start = position.character
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == '_'):
        start -= 1
    end = position.character
    while end < len(line) and (line[end].isalnum() or line[end] == '_'):
        end += 1
    return line[start:end]


def _parse_document(uri: str, text: str):
    try:
        lexer = Lexer(text)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        return parser.parse()
    except Exception as e:
        logger.error(f"Parse error for {uri}: {e}")
        return None


def _validate_document(uri: str, text: str) -> List[lsp.Diagnostic]:
    diagnostics = []
    try:
        ast = _parse_document(uri, text)
        if ast is None:
            return diagnostics
        validator = Validator(cpp_mode=False)
        ok, errors, warnings = validator.validate(ast)
        for err in errors:
            m = re.match(r'\[Line (\d+)\] (.+)', err)
            if m:
                line = max(0, int(m.group(1)) - 1)
                diagnostics.append(lsp.Diagnostic(
                    range=lsp.Range(
                        start=lsp.Position(line=line, character=0),
                        end=lsp.Position(line=line, character=999),
                    ),
                    message=m.group(2),
                    severity=lsp.DiagnosticSeverity.Error,
                    source='dictum',
                ))
        for warn in warnings:
            m = re.match(r'\[Line (\d+)\] (.+)', warn)
            if m:
                line = max(0, int(m.group(1)) - 1)
                diagnostics.append(lsp.Diagnostic(
                    range=lsp.Range(
                        start=lsp.Position(line=line, character=0),
                        end=lsp.Position(line=line, character=999),
                    ),
                    message=m.group(2),
                    severity=lsp.DiagnosticSeverity.Warning,
                    source='dictum',
                ))
    except Exception as e:
        logger.error(f"Validation error: {e}")
    return diagnostics


# ---------------------------------------------------------------------------
# LSP Features
# ---------------------------------------------------------------------------

@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams):
    doc = server.workspace.get_text_document(params.text_document.uri)
    server.publish_diagnostics(doc.uri, _validate_document(doc.uri, doc.source))


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(params: lsp.DidChangeTextDocumentParams):
    doc = server.workspace.get_text_document(params.text_document.uri)
    server.publish_diagnostics(doc.uri, _validate_document(doc.uri, doc.source))


@server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: lsp.DidSaveTextDocumentParams):
    doc = server.workspace.get_text_document(params.text_document.uri)
    server.publish_diagnostics(doc.uri, _validate_document(doc.uri, doc.source))


@server.feature(lsp.TEXT_DOCUMENT_COMPLETION)
def completions(params: lsp.CompletionParams):
    items = []
    doc = server.workspace.get_text_document(params.text_document.uri)
    current_line = doc.lines[params.position.line][:params.position.character]
    word = _get_word_at_position(doc, params.position)

    keywords = [
        'program', 'module', 'shape', 'action', 'keep', 'put', 'set', 'if', 'then',
        'otherwise', 'while', 'repeat', 'for', 'each', 'in', 'attempt',
        'on', 'success', 'failure', 'return', 'produce', 'assert', 'print',
        'call', 'run', 'defer', 'release', 'end', 'import', 'from', 'bind',
        'use', 'extern', 'unsafe', 'new', 'method', 'constructor', 'destructor',
        'public', 'private', 'protected', 'virtual', 'override', 'export',
        'any', 'Type', 'takes', 'produces', 'as', 'with', 'into', 'holds',
        'giving', 'using', 'times', 'and', 'or', 'is', 'not', 'empty',
        'true', 'false', 'nothing', 'newline',
    ]
    for kw in keywords:
        if kw.startswith(word) or not word:
            items.append(lsp.CompletionItem(
                label=kw,
                kind=lsp.CompletionItemKind.Keyword,
                insert_text=kw,
            ))

    primitive_types = [
        'whole number', 'count', 'fractional number', 'decimal number',
        'truth value', 'byte', 'text', 'handle to bytes', 'nothing',
        'u8', 'u16', 'u32', 'i32', 'i64', 'u64',
    ]
    for t in primitive_types + list(DICTUM_STDLIB_TYPES):
        if str(t).startswith(word) or not word:
            items.append(lsp.CompletionItem(
                label=str(t),
                kind=lsp.CompletionItemKind.TypeParameter,
                insert_text=str(t),
            ))

    # Stdlib module.function completions
    for family, actions in LSP_STDLIB.items():
        for act in actions:
            label = act['full_name']
            takes_str = ', '.join(act['takes']) if act['takes'] else 'nothing'
            if act['name'].startswith(word) or label.startswith(word) or not word:
                items.append(lsp.CompletionItem(
                    label=label,
                    kind=lsp.CompletionItemKind.Function,
                    detail=f"→ {act['produces']}",
                    documentation=lsp.MarkupContent(
                        kind=lsp.MarkupKind.Markdown,
                        value=(
                            f"**{label}**\n\n"
                            f"Family: `{family}`\n"
                            f"Takes: `{takes_str}`\n"
                            f"Produces: `{act['produces']}`\n"
                            f"C: `{act['c_name']}`"
                        ),
                    ),
                    insert_text=label,
                ))

    return lsp.CompletionList(is_incomplete=False, items=items)


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(params: lsp.HoverParams):
    doc = server.workspace.get_text_document(params.text_document.uri)
    word = _get_word_at_position(doc, params.position)
    if not word:
        return None

    for family, actions in LSP_STDLIB.items():
        for act in actions:
            if act['name'] == word or act['full_name'] == word:
                takes_str = ', '.join(act['takes']) if act['takes'] else 'nothing'
                return lsp.Hover(contents=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=(
                        f"### `{act['full_name']}`\n\n"
                        f"**Family:** {family}\n"
                        f"**Takes:** `{takes_str}`\n"
                        f"**Produces:** `{act['produces']}`\n"
                        f"**C implementation:** `{act['c_name']}`"
                    ),
                ))

    type_docs = {
        'whole number': '32-bit signed integer (`int32_t`)',
        'count': 'Unsigned size type (`size_t`)',
        'fractional number': 'Double-precision float (`double`)',
        'decimal number': 'Double-precision float (`double`) — alias',
        'truth value': 'Boolean (`bool`)',
        'byte': '8-bit unsigned integer (`uint8_t`)',
        'text': 'Null-terminated string (`const char*` / `dictum_text`)',
        'handle to bytes': 'Raw memory pointer (`void*`)',
    }
    if word in type_docs:
        return lsp.Hover(contents=lsp.MarkupContent(
            kind=lsp.MarkupKind.Markdown,
            value=f"### `{word}`\n\n{type_docs[word]}",
        ))

    return None


@server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
def definition(params: lsp.DefinitionParams):
    doc = server.workspace.get_text_document(params.text_document.uri)
    word = _get_word_at_position(doc, params.position)
    if not word:
        return None
    ast = _parse_document(doc.uri, doc.source)
    if not ast:
        return None
    locations = []

    def _scan(nodes):
        for node in nodes:
            if hasattr(node, 'name') and node.name == word and hasattr(node, 'line'):
                locations.append(lsp.Location(
                    uri=doc.uri,
                    range=lsp.Range(
                        start=lsp.Position(line=node.line - 1, character=0),
                        end=lsp.Position(line=node.line - 1, character=999),
                    ),
                ))
            for attr in ('body', 'then_body', 'else_body', 'success_body', 'failure_body'):
                child = getattr(node, attr, None)
                if child:
                    _scan(child)

    try:
        _scan(ast)
    except Exception as e:
        logger.error(f"Definition scan error: {e}")

    return locations or None


@server.feature(lsp.TEXT_DOCUMENT_SIGNATURE_HELP)
def signature_help(params: lsp.SignatureHelpParams):
    doc = server.workspace.get_text_document(params.text_document.uri)
    line = doc.lines[params.position.line]
    prefix = line[:params.position.character]
    match = re.search(r'call\s+([\w.]+)', prefix)
    if not match:
        return None
    func_name = match.group(1)
    # Look up full module.fn or just fn name
    for family, actions in LSP_STDLIB.items():
        for act in actions:
            if act['full_name'] == func_name or act['name'] == func_name:
                param_infos = [
                    lsp.ParameterInformation(label=f"arg{i}: {t}")
                    for i, t in enumerate(act['takes'])
                ]
                sig = lsp.SignatureInformation(
                    label=f"{act['full_name']}({', '.join(act['takes'])})",
                    documentation=f"Produces: {act['produces']}",
                    parameters=param_infos,
                )
                return lsp.SignatureHelp(
                    signatures=[sig],
                    active_signature=0,
                    active_parameter=0,
                )
    return None


@server.command('dictum.stdlibInfo')
def cmd_stdlib_info(ls, args):
    return {
        "types": list(DICTUM_STDLIB_TYPES),
        "families": {
            fam: [a['full_name'] for a in acts]
            for fam, acts in LSP_STDLIB.items()
        },
    }


if __name__ == '__main__':
    logger.info("Starting Dictum LSP v5.0 server...")
    server.start_io()
