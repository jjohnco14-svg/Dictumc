#!/usr/bin/env python3
"""
Dictum v4 Test Suite
Covers: split module imports, Phase 1-5 bug fixes, grammar wiring.
Run: python -m pytest tests/test_v4.py -v
  or: python tests/test_v4.py
"""

import sys, os, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from dictumc.lexer import Lexer, TokenType
from dictumc.parser import Parser
from dictumc.validator import Validator
from dictumc.emit_c import CEmitter
from dictumc.emit_cpp import CppEmitter
from dictumc.grammar import DictumGrammar, GrammarConstrainedGenerator, resync_from_source
from dictumc.transpiler import Transpiler
from dictumc.ast_nodes import *


def transpile(source: str, backend: str = 'c', validate: bool = False) -> str:
    t = Transpiler(source, backend=backend)
    result = t.run(validate=validate)
    return result["code"]


def compile_and_run(source: str, args: str = "", backend: str = 'c') -> str:
    """Transpile, compile with gcc/g++, run, return stdout."""
    code = transpile(source, backend=backend)
    ext = ".cpp" if backend == "cpp" else ".c"
    with tempfile.NamedTemporaryFile(suffix=ext, mode='w', delete=False, encoding='utf-8') as tf:
        tf.write(code)
        src = tf.name
    binary = src + ".out"
    compiler = "g++" if backend == "cpp" else "gcc"
    flags = [f"-std=c++17"] if backend == "cpp" else ["-std=c11"]
    # P4.1: include stdlib dir and dictum_core.c when attempt/error headers are present
    stdlib_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stdlib')
    extra_srcs = []
    extra_flags = [f"-I{stdlib_dir}"]
    if 'dictum_error_clear' in code or 'DICTUM_HAS_ERROR' in code or 'dictum_last_error' in code:
        core_c = os.path.join(stdlib_dir, 'dictum_core.c')
        if os.path.exists(core_c):
            extra_srcs = [core_c]
    proc = subprocess.run([compiler] + flags + ["-O1", "-lm", src] + extra_srcs + ["-o", binary] + extra_flags,
                          capture_output=True, text=True)
    os.unlink(src)
    if proc.returncode != 0:
        raise RuntimeError(f"Compile error:\n{proc.stderr}\n\nGenerated C:\n{code}")
    result = subprocess.run([binary], capture_output=True, text=True, timeout=5)
    os.unlink(binary)
    return result.stdout


# ============================================================
# MODULE SPLIT TESTS
# ============================================================

class TestModuleSplit(unittest.TestCase):
    def test_lexer_imports(self):
        from dictumc.lexer import Lexer, Token, TokenType
        self.assertTrue(callable(Lexer))

    def test_parser_imports(self):
        from dictumc.parser import Parser
        self.assertTrue(callable(Parser))

    def test_validator_imports(self):
        from dictumc.validator import Validator
        self.assertTrue(callable(Validator))

    def test_emit_c_imports(self):
        from dictumc.emit_c import CEmitter
        self.assertTrue(callable(CEmitter))

    def test_emit_cpp_imports(self):
        from dictumc.emit_cpp import CppEmitter
        self.assertTrue(callable(CppEmitter))

    def test_grammar_imports(self):
        from dictumc.grammar import DictumGrammar, GrammarConstrainedGenerator
        self.assertTrue(callable(DictumGrammar))
        self.assertTrue(callable(GrammarConstrainedGenerator))

    def test_transpiler_uses_split_modules(self):
        """Transpiler should use the new split modules, not a monolith."""
        from dictumc.transpiler import Transpiler
        import inspect
        src = inspect.getsourcefile(Transpiler)
        self.assertIn("transpiler.py", src)
        # Ensure it imports from split modules
        with open(src) as f:
            content = f.read()
        self.assertIn("from .lexer import", content)
        self.assertIn("from .parser import", content)
        self.assertIn("from .emit_c import", content)

    def test_lexer_tokenizes_basic(self):
        source = "program Hello\n    print the text \"hi\" and newline\nend program"
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        types = [t.type for t in tokens]
        self.assertIn(TokenType.WORD, types)
        self.assertIn(TokenType.STRING, types)

    def test_ast_nodes_importable(self):
        from dictumc.ast_nodes import Program, Action, VarDecl, If, While
        self.assertTrue(True)


# ============================================================
# PHASE 1 — TRANSPILER CORE BUG FIXES
# ============================================================

class TestBug01UndeclaredVar(unittest.TestCase):
    """BUG-01: put ... into Z auto-declares Z if not keep-declared."""

    def test_put_into_undeclared_emits_declaration(self):
        src = """
program Test:
    keep X as whole number with value 3
    keep Y as whole number with value 4
    put the sum of X and Y into Z
    print the text Z and newline
end program"""
        code = transpile(src)
        # Should declare Z, not just assign
        self.assertIn("int32_t Z", code)

    def test_put_into_undeclared_compiles_and_runs(self):
        src = """
program Test:
    keep X as whole number with value 10
    keep Y as whole number with value 5
    put the sum of X and Y into Z
    print the text Z and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("15", out)


class TestBug02SetStatement(unittest.TestCase):
    """BUG-02: set X to <expr> parsed as Assignment."""

    def test_set_parsed_as_assignment(self):
        src = """
program Test:
    keep N as whole number with value 0
    set N to 42
    print the text N and newline
end program"""
        code = transpile(src)
        self.assertIn("N = 42", code)

    def test_set_compiles_and_runs(self):
        src = """
program Test:
    keep N as whole number with value 0
    set N to 99
    print the text N and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("99", out)

    def test_set_with_expression(self):
        src = """
program Test:
    keep A as whole number with value 3
    keep B as whole number with value 7
    set A to the sum of A and B
    print the text A and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("10", out)


class TestBug03NaturalEnglishComparisons(unittest.TestCase):
    """BUG-03: is less than or equal to / is greater than or equal to."""

    def test_less_than_or_equal_parses(self):
        src = """
program Test:
    keep N as whole number with value 5
    if N is less than or equal to 5 then
        print the text "yes" and newline
    end if
end program"""
        code = transpile(src)
        self.assertIn("<=", code)

    def test_greater_than_or_equal_parses(self):
        src = """
program Test:
    keep N as whole number with value 10
    if N is greater than or equal to 10 then
        print the text "ok" and newline
    end if
end program"""
        code = transpile(src)
        self.assertIn(">=", code)

    def test_lte_compiles_and_runs(self):
        src = """
program Test:
    keep N as whole number with value 3
    if N is less than or equal to 5 then
        print the text "pass" and newline
    end if
end program"""
        out = compile_and_run(src)
        self.assertIn("pass", out)

    def test_gte_compiles_and_runs(self):
        src = """
program Test:
    keep N as whole number with value 10
    if N is greater than or equal to 10 then
        print the text "pass" and newline
    end if
end program"""
        out = compile_and_run(src)
        self.assertIn("pass", out)

    def test_recursive_fibonacci_uses_lte(self):
        """Fibonacci uses <= 1 — previously crashed on BUG-03."""
        src = """
program Test:
    action fib takes N as whole number produces whole number:
        if N is less than or equal to 1 then
            produce success with N
        end if
        keep A as whole number with value 0
        keep B as whole number with value 0
        call fib with the difference of N and 1 giving A
        call fib with the difference of N and 2 giving B
        produce success with the sum of A and B
    end action
    keep R as whole number with value 0
    call fib with 7 giving R
    print the text R and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("13", out)


class TestBug06DecimalType(unittest.TestCase):
    """BUG-06: decimal number / decimal → double."""

    def test_decimal_number_maps_to_double(self):
        src = """
program Test:
    keep X as decimal number with value 3.14
    print the text X and newline
end program"""
        code = transpile(src)
        self.assertIn("double", code)

    def test_decimal_alias_maps_to_double(self):
        src = """
program Test:
    keep X as decimal with value 2.718
    print the text X and newline
end program"""
        code = transpile(src)
        self.assertIn("double", code)

    def test_decimal_compiles_and_runs(self):
        src = """
program Test:
    keep X as decimal number with value 1.5
    keep Y as decimal number with value 2.5
    put the sum of X and Y into Z
    print the text Z and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("4", out)


class TestBug09CleanReturn(unittest.TestCase):
    """BUG-09: produce success with X emits `return X;` without /* success */."""

    def test_no_comment_in_return(self):
        src = """
program Test:
    action double takes N as whole number produces whole number:
        produce success with the product of N and 2
    end action
    keep R as whole number with value 0
    call double with 5 giving R
    print the text R and newline
end program"""
        code = transpile(src)
        self.assertNotIn("/* success */", code)
        self.assertIn("return", code)

    def test_return_compiles_and_runs(self):
        src = """
program Test:
    action triple takes N as whole number produces whole number:
        produce success with the product of N and 3
    end action
    keep R as whole number with value 0
    call triple with 4 giving R
    print the text R and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("12", out)


class TestBug10ForwardDeclarations(unittest.TestCase):
    """BUG-10: all actions get forward declarations before main."""

    def test_forward_decl_emitted(self):
        src = """
program Test:
    action add takes A as whole number and B as whole number produces whole number:
        produce success with the sum of A and B
    end action
    keep R as whole number with value 0
    call add with 2 and 3 giving R
    print the text R and newline
end program"""
        code = transpile(src)
        lines = code.split("\n")
        # Find first forward decl and first full definition
        fwd_line = next((i for i, ln in enumerate(lines)
                         if "int32_t add(" in ln and ";" in ln and "{" not in ln), None)
        def_line = next((i for i, ln in enumerate(lines)
                         if "int32_t add(" in ln and "{" in ln), None)
        self.assertIsNotNone(fwd_line, "Forward declaration not found")
        self.assertIsNotNone(def_line, "Full definition not found")
        self.assertLess(fwd_line, def_line, "Forward decl must precede definition")

    def test_mutual_recursion_compiles(self):
        """Mutual recursion requires forward decls to compile."""
        src = """
program Test:
    action is_even takes N as whole number produces truth value:
        if N is equal to 0 then
            produce success with true
        end if
        keep M as whole number with value 0
        keep R as truth value with value false
        set M to the difference of N and 1
        call is_odd with M giving R
        produce success with R
    end action
    action is_odd takes N as whole number produces truth value:
        if N is equal to 0 then
            produce success with false
        end if
        keep M as whole number with value 0
        keep R as truth value with value false
        set M to the difference of N and 1
        call is_even with M giving R
        produce success with R
    end action
    keep Result as truth value with value false
    call is_even with 4 giving Result
    if Result is equal to true then
        print the text "even" and newline
    end if
end program"""
        out = compile_and_run(src)
        self.assertIn("even", out)


# ============================================================
# MISSING-04: OTHERWISE / ELSE
# ============================================================

class TestMissing04Otherwise(unittest.TestCase):
    """MISSING-04: otherwise plain else branch."""

    def test_otherwise_emits_else(self):
        src = """
program Test:
    keep X as whole number with value 3
    if X is greater than 5 then
        print the text "big" and newline
    otherwise
        print the text "small" and newline
    end if
end program"""
        code = transpile(src)
        self.assertIn("} else {", code)

    def test_otherwise_runs_correctly(self):
        src = """
program Test:
    keep X as whole number with value 3
    if X is greater than 5 then
        print the text "big" and newline
    otherwise
        print the text "small" and newline
    end if
end program"""
        out = compile_and_run(src)
        self.assertIn("small", out)
        self.assertNotIn("big", out)

    def test_otherwise_true_branch(self):
        src = """
program Test:
    keep X as whole number with value 10
    if X is greater than 5 then
        print the text "big" and newline
    otherwise
        print the text "small" and newline
    end if
end program"""
        out = compile_and_run(src)
        self.assertIn("big", out)


# ============================================================
# MISSING-09: TRUTH VALUE / BOOL
# ============================================================

class TestMissing09BoolType(unittest.TestCase):
    """MISSING-09: truth value → bool; true/false consistent."""

    def test_truth_value_maps_to_bool(self):
        src = """
program Test:
    keep Flag as truth value with value true
    print the text Flag and newline
end program"""
        code = transpile(src)
        self.assertIn("bool", code)

    def test_true_false_literals(self):
        src = """
program Test:
    keep A as truth value with value true
    keep B as truth value with value false
    if A is equal to true then
        print the text "yes" and newline
    end if
end program"""
        out = compile_and_run(src)
        self.assertIn("yes", out)


# ============================================================
# MISSING-01/07/08: ARRAYS + FOR EACH
# ============================================================

class TestMissing01Arrays(unittest.TestCase):
    """MISSING-01: array declaration, index access, for each."""

    def test_array_literal_declaration(self):
        src = """
program Test:
    keep Numbers as whole number with values 1 and 2 and 3
    print the text Numbers at 0 and newline
end program"""
        code = transpile(src)
        self.assertIn("int32_t Numbers[3]", code)

    def test_array_for_each(self):
        src = """
program Test:
    keep Nums as whole number with values 10 and 20 and 30
    for each N in Nums repeat
        print the text N and newline
    end for
end program"""
        out = compile_and_run(src)
        self.assertIn("10", out)
        self.assertIn("20", out)
        self.assertIn("30", out)

    def test_bug08_list_of_type_no_crash(self):
        """BUG-08: `list of whole number` should not crash parser."""
        src = """
program Test:
    keep Items as list of whole number with values 5 and 6
    print the text Items at 0 and newline
end program"""
        # Should not raise
        code = transpile(src)
        self.assertIsNotNone(code)


# ============================================================
# MISSING-02: TEXT / STRINGS
# ============================================================

class TestMissing02Text(unittest.TestCase):
    """MISSING-02: dictum_text typedef emitted; text vars work."""

    def test_text_typedef_in_output(self):
        src = """
program Test:
    keep Msg as text with value "hello"
    print the text Msg and newline
end program"""
        code = transpile(src)
        self.assertIn("dictum_text", code)
        self.assertIn("typedef const char*", code)

    def test_text_variable_compiles(self):
        src = """
program Test:
    keep Msg as text with value "world"
    print the text Msg and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("world", out)


# ============================================================
# MISSING-03: HEAP ALLOCATION
# ============================================================

class TestMissing03Heap(unittest.TestCase):
    """MISSING-03: room_for → malloc; new expr → calloc."""

    def test_room_for_emits_malloc(self):
        src = """
program Test:
    keep Buf as handle to bytes with room for 64
    print the text "ok" and newline
end program"""
        code = transpile(src)
        self.assertIn("malloc", code)

    def test_room_for_compiles(self):
        src = """
program Test:
    keep Buf as handle to bytes with room for 64
    print the text "ok" and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("ok", out)


# ============================================================
# MISSING-05: ATTEMPT BLOCK
# ============================================================

class TestMissing05Attempt(unittest.TestCase):
    """MISSING-05: attempt block emits complete C."""

    def test_attempt_no_longer_emits_unhandled(self):
        src = """
program Test:
    action safe_div takes A as whole number and B as whole number produces whole number:
        produce success with the quotient of A and B
    end action
    attempt
        call safe_div with 10 and 2 giving R
    on success
        print the text "ok" and newline
    on failure with Err
        print the text "fail" and newline
    end attempt
end program"""
        code = transpile(src)
        self.assertNotIn("/* unhandled: Attempt */", code)

    def test_attempt_block_compiles(self):
        src = """
program Test:
    action safe_div takes A as whole number and B as whole number produces whole number:
        produce success with the quotient of A and B
    end action
    attempt
        call safe_div with 10 and 2 giving R
    on success
        print the text "ok" and newline
    end attempt
end program"""
        out = compile_and_run(src)
        self.assertIn("ok", out)


# ============================================================
# BUG-04/05: USE MODULE / MODULE.FUNCTION CALLS
# ============================================================

class TestBug04Bug05StdlibCalls(unittest.TestCase):
    """BUG-04: Module.fn call resolution; BUG-05: use Module → #include."""

    def test_use_emits_include_not_call(self):
        src = """
program Test:
    use Console
    print the text "hi" and newline
end program"""
        code = transpile(src)
        self.assertIn('#include "dictum_console.h"', code)
        self.assertNotIn("Console();", code)

    def test_module_dot_function_resolved(self):
        src = """
program Test:
    use Http
    keep Url as text with value "http://example.com"
    keep Resp as text with value ""
    call Http.get with Url giving Resp
    print the text Resp and newline
end program"""
        code = transpile(src)
        # Http(); and standalone get( should not appear — dictum_http_get is correct
        self.assertNotIn("Http();", code)
        # Should NOT have bare `get(` as a standalone call (only dictum_http_get)
        lines_with_get = [ln for ln in code.split('\n') if 'get(' in ln and 'dictum_http' not in ln]
        self.assertEqual(lines_with_get, [], f"Bare get( found: {lines_with_get}")
        self.assertIn("dictum_http_get", code)

    def test_text_module_wired_to_dictum_text_length(self):
        # P1.6: Text.length now maps to dictum_text_length (not raw strlen).
        # dictum_text_length is a proper wrapper that handles NULL and returns int32_t.
        src = """
program Test:
    use Text
    keep S as text with value "hello"
    keep L as whole number with value 0
    call Text.length with S giving L
    print the text L and newline
end program"""
        code = transpile(src)
        self.assertIn("dictum_text_length", code)
        self.assertNotIn("strlen(", code)  # raw strlen replaced everywhere


# ============================================================
# GRAMMAR INTEGRATION TESTS
# ============================================================

class TestGrammarIntegration(unittest.TestCase):
    """DictumGrammar wired to Parser via grammar= kwarg."""

    def test_grammar_wires_to_parser(self):
        source = """
program Hello:
    keep N as whole number with value 7
    print the text N and newline
end program"""
        grammar = DictumGrammar(cpp_mode=False)
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        parser = Parser(tokens, grammar=grammar)
        ast = parser.parse()
        self.assertIsNotNone(ast)
        self.assertTrue(len(ast) > 0)

    def test_grammar_constrained_generator_parse_with_grammar(self):
        source = """
program Test:
    keep X as whole number with value 42
    print the text X and newline
end program"""
        vocab = {"program": 0, "keep": 1, "as": 2, "whole": 3, "number": 4,
                 "with": 5, "value": 6, "print": 7, "the": 8, "text": 9,
                 "and": 10, "newline": 11, "end": 12, "X": 13, "Test": 14}
        grammar = DictumGrammar()
        gen = GrammarConstrainedGenerator(grammar, vocab)
        ast = gen.parse_with_grammar(source)
        self.assertTrue(len(ast) > 0)

    def test_grammar_set_statement_accepted(self):
        """BUG-02 fix: `set X to` should advance grammar correctly."""
        from dictumc.grammar import GrammarState
        grammar = DictumGrammar()
        # Simulate being inside a program block
        grammar.state_stack = [GrammarState.TOP_LEVEL, GrammarState.BLOCK_BODY]
        grammar.block_depth = 1
        grammar.feed_token("set", "WORD")
        # Should be in SET_TARGET state
        self.assertEqual(grammar.current(), GrammarState.SET_TARGET)
        grammar.feed_token("X", "WORD")
        # Should now be in SET_TO
        self.assertEqual(grammar.current(), GrammarState.SET_TO)

    def test_grammar_lte_accepted(self):
        """BUG-03: `less than or equal to` — grammar should accept 'or' in comparison."""
        grammar = DictumGrammar()
        grammar.feed_token("if", "WORD")
        grammar.feed_token("N", "WORD")
        grammar.feed_token("is", "WORD")
        grammar.feed_token("less", "WORD")
        grammar.feed_token("than", "WORD")
        grammar.feed_token("or", "WORD")   # previously crashed / rejected
        grammar.feed_token("equal", "WORD")
        grammar.feed_token("to", "WORD")
        grammar.feed_token("1", "NUMBER")
        grammar.feed_token("then", "WORD")
        # Should not raise

    def test_resync_from_source(self):
        """resync_from_source should not crash on valid source."""
        grammar = DictumGrammar()
        src = "program Test:\n    keep X as whole number with value 5\nend program"
        resync_from_source(grammar, src)

    def test_grammar_mask_dict(self):
        vocab = {"program": 0, "keep": 1, "module": 2, "shape": 3, "end": 4}
        grammar = DictumGrammar()
        mask = grammar.to_mask_dict(vocab)
        self.assertIsInstance(mask, dict)


# ============================================================
# EXISTING FUNCTIONALITY REGRESSION TESTS
# ============================================================

class TestExistingFunctionality(unittest.TestCase):
    """Ensure existing v3.3 passing tests still pass."""

    def test_basic_program(self):
        src = """
program Hello:
    print the text "Hello, World!" and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("Hello, World!", out)

    def test_function_call(self):
        src = """
program Test:
    action add takes A as whole number and B as whole number produces whole number:
        produce success with the sum of A and B
    end action
    keep R as whole number with value 0
    call add with 3 and 4 giving R
    print the text R and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("7", out)

    def test_for_loop(self):
        src = """
program Test:
    keep S as whole number with value 0
    repeat 5 times using I
        set S to the sum of S and I
    end repeat
    print the text S and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("10", out)

    def test_struct(self):
        src = """
program Test:
    shape Point holds
        X as whole number
        Y as whole number
    end shape
    keep P as Point
    set P.X to 3
    set P.Y to 4
    print the text P.X and newline
    print the text P.Y and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("3", out)
        self.assertIn("4", out)

    def test_recursive_function(self):
        src = """
program Test:
    action fact takes N as whole number produces whole number:
        if N is less than or equal to 1 then
            produce success with 1
        end if
        keep Sub as whole number with value 0
        call fact with the difference of N and 1 giving Sub
        produce success with the product of N and Sub
    end action
    keep R as whole number with value 0
    call fact with 5 giving R
    print the text R and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("120", out)

    def test_if_else_chain(self):
        src = """
program Test:
    keep X as whole number with value 5
    if X is greater than 10 then
        print the text "big" and newline
    otherwise if X is greater than 3 then
        print the text "medium" and newline
    otherwise
        print the text "small" and newline
    end if
end program"""
        out = compile_and_run(src)
        self.assertIn("medium", out)

    def test_while_loop(self):
        src = """
program Test:
    keep I as whole number with value 0
    keep S as whole number with value 0
    while I is less than 5 repeat
        set S to the sum of S and I
        set I to the sum of I and 1
    end while
    print the text S and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("10", out)

    def test_arithmetic_ops(self):
        src = """
program Test:
    keep A as whole number with value 10
    keep B as whole number with value 3
    keep R as whole number with value 0
    set R to the product of A and B
    print the text R and newline
    set R to the quotient of A and B
    print the text R and newline
    set R to the remainder of A by B
    print the text R and newline
end program"""
        out = compile_and_run(src)
        self.assertIn("30", out)
        self.assertIn("3", out)
        self.assertIn("1", out)

    def test_cpp_backend(self):
        src = """
program Test:
    keep N as whole number with value 42
    print the text N and newline
end program"""
        out = compile_and_run(src, backend='cpp')
        self.assertIn("42", out)

    def test_cpp_class(self):
        src = """
program Test:
    shape Counter holds
        Value as whole number
    end shape
    keep C as Counter
    set C.Value to 10
    print the text C.Value and newline
end program"""
        out = compile_and_run(src, backend='cpp')
        self.assertIn("10", out)

    def test_end_to_end_http_client_shape(self):
        """The 'production-ready' shape from the plan docs should parse without error."""
        src = """
program HttpClient:
    use Http
    use Console
    use Json

    action fetch takes Url as text produces text:
        keep Response as text with value ""
        attempt
            call Http.get with Url giving Response
        on success
            produce success with Response
        on failure with Err
            produce success with "ERROR"
        end attempt
        produce success with Response
    end action

    keep Result as text with value ""
    call fetch with "https://api.example.com/data" giving Result
end program"""
        code = transpile(src)
        # Should not raise, should include the include lines
        self.assertIn("dictum_http_get", code)
        self.assertIn("dictum_http.h", code)
        self.assertNotIn("/* unhandled:", code)

    def test_stdlib_auto_inject(self):
        """auto_inject_stdlib_imports inserts Use nodes for referenced modules."""
        from dictumc.stdlib_registry import auto_inject_stdlib_imports
        from dictumc.ast_nodes import FuncCall, Program, Use
        ast = [Program(name="T", body=[
            FuncCall(name="Http.get", args=[])
        ])]
        result = auto_inject_stdlib_imports(ast)
        use_nodes = [n for n in result if isinstance(n, Use)]
        self.assertTrue(any(u.path == "Http" for u in use_nodes))


# ============================================================
# C++ BACKEND SPECIFIC
# ============================================================

class TestCppBackend(unittest.TestCase):
    def test_unique_ptr_syntax(self):
        src = """
program Test:
    keep Buf as unique handle to whole number with room for 32
    print the text "ok" and newline
end program"""
        code = transpile(src, backend='cpp')
        self.assertIn("std::unique_ptr", code)

    def test_attempt_emits_try_catch(self):
        src = """
program Test:
    action safe takes N as whole number produces whole number:
        produce success with N
    end action
    attempt
        call safe with 5 giving R
    on failure with Err
        print the text "fail" and newline
    end attempt
end program"""
        code = transpile(src, backend='cpp')
        self.assertIn("try {", code)
        self.assertIn("catch", code)
        self.assertNotIn("/* unhandled: Attempt */", code)

    def test_for_each_uses_range_for(self):
        src = """
program Test:
    keep Items as whole number with values 1 and 2 and 3
    for each I in Items repeat
        print the text I and newline
    end for
end program"""
        code = transpile(src, backend='cpp')
        self.assertIn("for (auto&", code)


# ============================================================
# PRODUCE FAILURE → THROW (C++)
# ============================================================

class TestProduceFailure(unittest.TestCase):
    def test_produce_failure_cpp_emits_throw(self):
        src = """
program Test:
    action risky takes N as whole number produces whole number:
        if N is equal to 0 then
            produce failure with text "zero"
        end if
        produce success with N
    end action
    keep R as whole number with value 0
    call risky with 5 giving R
    print the text R and newline
end program"""
        code = transpile(src, backend='cpp')
        self.assertIn("throw", code)


if __name__ == "__main__":
    # Simple run
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
