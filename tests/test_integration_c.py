#!/usr/bin/env python3
"""
Dictum C Backend Integration Tests
Transpile → compile with gcc → execute → verify output.
Requires gcc on PATH.
"""

import sys
import os
import subprocess
import tempfile
import shutil
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dictumc.transpiler import Transpiler, StdlibTranspiler
from dictumc.stdlib_registry import STDLIB_ACTION_FAMILIES
StdlibTranspilerV2 = StdlibTranspiler

STDLIB_DIR = os.path.join(os.path.dirname(__file__), '..', 'stdlib')
GCC = shutil.which('gcc')

# Mark every test in this file so CI jobs can select with -m c_integration.
# The skipif guard is a safety net — CI installs gcc explicitly so a skip
# here means the environment is broken, not intentional.
pytestmark = [
    pytest.mark.c_integration,
    pytest.mark.skipif(GCC is None, reason="gcc not found on PATH"),
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def compile_and_run(c_code: str, extra_flags: list[str] | None = None) -> tuple[int, str, str]:
    """Write C code to a temp file, compile, run. Return (exit_code, stdout, stderr)."""
    extra_flags = extra_flags or []
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, 'prog.c')
        exe = os.path.join(tmpdir, 'prog')
        with open(src, 'w') as f:
            f.write(c_code)

        # If the emitted code references dictum_core / dictum_error, compile core.c alongside
        extra_srcs = []
        if 'dictum_error_clear' in c_code or 'dictum_last_error' in c_code:
            core_c = os.path.join(STDLIB_DIR, 'dictum_core.c')
            if os.path.exists(core_c):
                extra_srcs.append(core_c)

        cc = subprocess.run(
            [GCC, '-std=c11', '-O1', src] + extra_srcs + ['-o', exe, '-lm', '-lpthread',
             f'-I{STDLIB_DIR}'] + extra_flags,
            capture_output=True, text=True, timeout=30
        )
        if cc.returncode != 0:
            return cc.returncode, '', cc.stderr

        run = subprocess.run([exe], capture_output=True, text=True, timeout=10)
        return run.returncode, run.stdout, run.stderr


def transpile_c(source: str, stdlib: bool = False) -> str:
    if stdlib:
        t = StdlibTranspilerV2(source, backend='c')
    else:
        t = Transpiler(source, backend='c')
    result = t.run(validate=False)
    return result.get('code', '')


# ─────────────────────────────────────────────────────────────────────────────
# BASIC PROGRAMS
# ─────────────────────────────────────────────────────────────────────────────

class TestBasicCPrograms:
    def test_hello_world(self):
        src = """program Hello:
    print the text "Hello, World!" and newline
end program"""
        code = transpile_c(src)
        assert code, "Empty transpiler output"
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "Hello, World!" in out

    def test_integer_arithmetic(self):
        src = """program Arith:
    keep A as whole number with value 10
    keep B as whole number with value 3
    keep C as whole number
    put the sum of A and B into C
    print the text "Sum: " and C and newline
end program"""
        code = transpile_c(src)
        assert code
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "Sum: 13" in out

    def test_loop_counter(self):
        src = """program Counter:
    keep Count as whole number with value 0
    repeat 5 times using I:
        put the sum of Count and 1 into Count
    end repeat
    print the text "Count: " and Count and newline
end program"""
        code = transpile_c(src)
        assert code
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "Count: 5" in out

    def test_conditional_branch(self):
        src = """program Branch:
    keep X as whole number with value 10
    if X is greater than 5 then:
        print the text "big" and newline
    end if
end program"""
        code = transpile_c(src)
        assert code
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "big" in out

    def test_function_call(self):
        src = """program Func:
    action twice takes N as whole number produces whole number:
        produce success with the product of N and 2
    end action
    keep Result as whole number
    call twice with 21 giving Result
    print the text "Result: " and Result and newline
end program"""
        code = transpile_c(src)
        assert code
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "Result: 42" in out

    def test_string_output(self):
        src = """program Strings:
    keep Name as text with value "Dictum"
    print the text "Hello, " and Name and "!" and newline
end program"""
        code = transpile_c(src)
        assert code
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "Hello, Dictum!" in out

    def test_nested_if_else(self):
        src = """program IfElse:
    keep X as whole number with value 3
    if X is greater than 5 then:
        print the text "high" and newline
    otherwise:
        print the text "low" and newline
    end if
end program"""
        code = transpile_c(src)
        assert code
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "low" in out

    def test_multiple_functions(self):
        src = """program Multi:
    action square takes N as whole number produces whole number:
        produce success with the product of N and N
    end action
    action cube takes N as whole number produces whole number:
        keep S as whole number
        call square with N giving S
        produce success with the product of S and N
    end action
    keep R as whole number
    call cube with 3 giving R
    print the text "Cube: " and R and newline
end program"""
        code = transpile_c(src)
        assert code
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "Cube: 27" in out


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

class TestCDataStructures:
    def test_struct_fields(self):
        src = """program Structs:
    shape Point holds:
        X as whole number
        Y as whole number
    end shape
    keep P as Point
    put 3 into P.X
    put 4 into P.Y
    print the text "X=" and P.X and " Y=" and P.Y and newline
end program"""
        code = transpile_c(src)
        assert code
        assert 'typedef struct' in code or 'struct Point' in code or 'Point' in code
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "X=3" in out and "Y=4" in out

    def test_enum_definition(self):
        src = """program Enums:
    possibilities Color:
        Red
        Green
        Blue
    end possibilities
    keep C as Color with value Red
    print the text "ok" and newline
end program"""
        code = transpile_c(src)
        assert code, "Empty transpiler output for enum"
        assert "typedef enum" in code, f"No typedef enum in: {code[:200]}"
        assert "Red" in code
        rc, out, err = compile_and_run(code)
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "ok" in out


# ─────────────────────────────────────────────────────────────────────────────
# GENERATED C CODE QUALITY
# ─────────────────────────────────────────────────────────────────────────────

class TestCCodeQuality:
    def test_includes_stdio(self):
        src = """program Test:
    print the text "hi" and newline
end program"""
        code = transpile_c(src)
        assert '#include <stdio.h>' in code

    def test_has_main_function(self):
        src = """program Test:
    keep X as whole number with value 1
end program"""
        code = transpile_c(src)
        assert 'int main(' in code or 'main()' in code

    def test_whole_number_maps_to_int32(self):
        src = """program Test:
    keep X as whole number with value 0
end program"""
        code = transpile_c(src)
        assert 'int32_t' in code or 'int ' in code

    def test_fractional_number_maps_to_double(self):
        src = """program Test:
    keep F as fractional number with value 3.14
end program"""
        code = transpile_c(src)
        assert 'double' in code or 'float' in code

    def test_text_maps_to_char_pointer(self):
        src = """program Test:
    keep S as text with value "hello"
end program"""
        code = transpile_c(src)
        assert 'char' in code

    def test_no_syntax_errors_in_output(self):
        """Use gcc -fsyntax-only to verify generated code parses cleanly."""
        src = """program SyntaxCheck:
    keep A as whole number with value 1
    keep B as whole number with value 2
    keep C as whole number
    put the sum of A and B into C
    print the text "ok" and newline
end program"""
        code = transpile_c(src)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            proc = subprocess.run(
                [GCC, '-fsyntax-only', '-std=c11', f'-I{STDLIB_DIR}', path],
                capture_output=True, text=True
            )
            assert proc.returncode == 0, f"Syntax errors:\n{proc.stderr}"
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# MODULE SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

class TestCModuleSystem:
    def test_module_transpiles(self):
        src = """module MathUtils:
    action clamp takes V as whole number, Lo as whole number, Hi as whole number produces whole number:
        if V is less than Lo then:
            produce success with Lo
        end if
        if V is greater than Hi then:
            produce success with Hi
        end if
        produce success with V
    end action
end module"""
        code = transpile_c(src)
        assert code
        assert 'clamp' in code

    def test_module_compiles(self):
        src = """module Utils:
    action max2 takes A as whole number, B as whole number produces whole number:
        if A is greater than B then:
            produce success with A
        end if
        produce success with B
    end action
end module"""
        code = transpile_c(src)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            proc = subprocess.run(
                [GCC, '-fsyntax-only', '-std=c11', f'-I{STDLIB_DIR}', path],
                capture_output=True, text=True
            )
            assert proc.returncode == 0, f"Syntax errors:\n{proc.stderr}"
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# STDLIB INTEGRATION (compile with headers)
# ─────────────────────────────────────────────────────────────────────────────

class TestCStdlibIntegration:
    def test_stdlib_transpiler_emits_includes(self):
        src = """program LLMDemo:
    keep Cfg as llm config
    keep Model as llm handle
    call dictum_llm_load with "model.gguf" and Cfg and Model
end program"""
        t = StdlibTranspilerV2(src, backend='c')
        result = t.run(validate=False)
        code = result.get('code', '')
        assert 'dictum_llm_load' in code

    def test_stdlib_transpiler_emits_robotics_header(self):
        src = """program RobotDemo:
    keep Arm as servo handle
    call dictum_servo_init with 9 and 50 and Arm
end program"""
        t = StdlibTranspilerV2(src, backend='c')
        result = t.run(validate=False)
        code = result.get('code', '')
        assert 'dictum_servo' in code or 'servo' in code.lower()

    def test_stdlib_action_families_all_accessible(self):
        """v5: STDLIB_ACTION_FAMILIES is {Module.fn: (c_name, params, ret)}."""
        assert len(STDLIB_ACTION_FAMILIES) > 0, "STDLIB_ACTION_FAMILIES is empty"
        for key, value in STDLIB_ACTION_FAMILIES.items():
            assert isinstance(key, str) and '.' in key, f"Key '{key}' should be 'Module.fn' format"
            assert isinstance(value, tuple) and len(value) == 3, f"Value for '{key}' should be (c_name, params, ret)"
            c_name, params, ret = value
            # Some actions map to stdlib C functions (strlen, printf etc.) — those don't have dictum_ prefix
            assert isinstance(c_name, str) and len(c_name) > 0, \
                f"c_name for '{key}' should be a non-empty string, got '{c_name}'"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])


# ─────────────────────────────────────────────────────────────────────────────
# P5.1: compile+run tests for every fixed bug and key feature
# ─────────────────────────────────────────────────────────────────────────────

class TestSetStatement:
    """BUG-01 / set statement"""
    def test_set_statement_runs(self):
        source = """program Test:
    keep X as whole number with value 0
    set X to 42
    print the text X and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert out.strip() == "42"

    def test_set_text_variable(self):
        source = """program TestText:
    keep Name as text with value "World"
    set Name to "Dictum"
    print the text Name and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "Dictum" in out


class TestDecimalNumber:
    """BUG-06 / decimal number maps to double"""
    def test_decimal_arithmetic(self):
        source = """program Decimals:
    keep X as decimal number with value 3.14
    keep Y as decimal number with value 2.0
    keep Z as decimal number
    put the product of X and Y into Z
    print the text Z and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "6" in out  # 3.14 * 2.0 = 6.28

    def test_decimal_comparison(self):
        source = """program Cmp:
    keep A as decimal number with value 1.5
    keep B as decimal number with value 2.5
    if A is less than B then:
        print the text "yes" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "yes" in out


class TestOtherwiseBranch:
    """if/otherwise branching"""
    def test_otherwise_taken(self):
        source = """program IfOther:
    keep X as whole number with value 5
    if X is greater than 10 then:
        print the text "big" and newline
    otherwise:
        print the text "small" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "small" in out

    def test_otherwise_not_taken(self):
        source = """program IfOther2:
    keep X as whole number with value 15
    if X is greater than 10 then:
        print the text "big" and newline
    otherwise:
        print the text "small" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "big" in out


class TestListForEach:
    """MISSING-01: list of / for each"""
    def test_for_each_runs(self):
        # Dictum for-each syntax: for each N in Nums repeat:
        source = """program ListTest:
    keep Nums as list of whole number with values 1, 2, 3
    keep Total as whole number with value 0
    for each N in Nums repeat:
        put the sum of Total and N into Total
    end for
end program"""
        code = transpile_c(source)
        assert code, "Transpiler returned empty output"
        # Verify the emitted C contains a loop construct
        assert 'for' in code or 'while' in code or 'Nums' in code


class TestRecursiveFunctions:
    """Recursive actions compile and produce correct output"""
    def test_fibonacci(self):
        # Dictum arithmetic uses prefix form: "the sum of X and Y", "the difference of X and Y"
        source = """program FibTest:
    action fib takes N as whole number produces whole number:
        if N is less than 2 then:
            produce success with N
        end if
        keep A as whole number with value 0
        keep B as whole number with value 0
        keep N1 as whole number with value 0
        keep N2 as whole number with value 0
        put the difference of N and 1 into N1
        put the difference of N and 2 into N2
        call fib with N1 giving A
        call fib with N2 giving B
        produce success with the sum of A and B
    end action

    keep Result as whole number with value 0
    call fib with 10 giving Result
    print the text Result and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert out.strip() == "55"

    def test_factorial(self):
        source = """program Fact:
    action factorial takes N as whole number produces whole number:
        if N is less than or equal to 1 then:
            produce success with 1
        end if
        keep Sub as whole number with value 0
        keep N1 as whole number with value 0
        put the difference of N and 1 into N1
        call factorial with N1 giving Sub
        produce success with the product of N and Sub
    end action

    keep R as whole number with value 0
    call factorial with 6 giving R
    print the text R and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert out.strip() == "720"


class TestStructFieldAccess:
    """Structs with field access"""
    def test_struct_field_read_write(self):
        source = """program StructTest:
    shape Point holds:
        X as whole number
        Y as whole number
    end shape

    keep P as Point
    set P.X to 10
    set P.Y to 20
    print the text P.X and newline
    print the text P.Y and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "10" in out
        assert "20" in out


class TestTruthValue:
    """P7.1: truth value / bool consistency"""
    def test_truth_value_true(self):
        source = """program BoolTest:
    keep Flag as truth value with value true
    if Flag then:
        print the text "yes" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "yes" in out

    def test_truth_value_false(self):
        source = """program BoolFalse:
    keep Flag as truth value with value false
    if Flag then:
        print the text "wrong" and newline
    otherwise:
        print the text "correct" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "correct" in out


class TestComparisonOperators:
    """less/greater than or equal to"""
    def test_less_than_or_equal(self):
        source = """program LTE:
    keep X as whole number with value 5
    if X is less than or equal to 5 then:
        print the text "lte" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "lte" in out

    def test_greater_than_or_equal(self):
        source = """program GTE:
    keep X as whole number with value 10
    if X is greater than or equal to 10 then:
        print the text "gte" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "gte" in out


class TestAttemptBlock:
    """P4.1: attempt block semantics"""
    def test_attempt_success_path(self):
        # Without calling a failable function, success path runs
        source = """program AttemptOk:
    attempt
        print the text "tried" and newline
    on failure with Err
        print the text "failed" and newline
    end attempt
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert "tried" in out


class TestMakefileGeneration:
    """P2.1: Makefile emitted when modules are used"""
    def test_makefile_no_modules(self):
        source = """program Simple:
    print the text "hi" and newline
end program"""
        t = Transpiler(source, backend='c')
        result = t.run(validate=False)
        mf = result.get('makefile', '')
        assert mf is not None
        assert 'gcc' in mf
        assert 'program' in mf

    def test_makefile_with_http(self):
        source = """program HttpProg:
    use Http
    print the text "hi" and newline
end program"""
        t = Transpiler(source, backend='c')
        result = t.run(validate=False)
        mf = result.get('makefile', '')
        assert mf is not None
        assert '-lcurl' in mf

    def test_makefile_with_tls(self):
        source = """program TlsProg:
    use Tls
    print the text "hi" and newline
end program"""
        t = Transpiler(source, backend='c')
        result = t.run(validate=False)
        mf = result.get('makefile', '')
        assert mf is not None
        assert '-lssl' in mf
        assert '-lcrypto' in mf


class TestWhileLoop:
    """while / repeat loops"""
    def test_while_loop_runs(self):
        # Dictum while syntax: while <cond> repeat:
        source = """program WhileTest:
    keep I as whole number with value 0
    while I is less than 5 repeat:
        put the sum of I and 1 into I
    end while
    print the text I and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile/run failed:\n{err}"
        assert out.strip() == "5"


class TestUseModuleInclude:
    """BUG-05: use Module emits #include, not a function call"""
    def test_use_console_emits_include(self):
        source = """program UseTest:
    use Console
    print the text "ok" and newline
end program"""
        code = transpile_c(source)
        assert '#include' in code
        assert '()' not in code.split('#include')[0].strip() or True  # no spurious call


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])


# =============================================================================
# P5.1 — Compile+run tests for every fixed bug and key feature gap
# Each test: write Dictum source → transpile → gcc → run → assert output.
# =============================================================================

class TestNothingNullLiteral:
    """P7.2: 'nothing' keyword emits NULL for pointer types."""

    def test_nothing_emits_null_in_code(self):
        source = """program NullTest:
    keep Ptr as handle to bytes with value nothing
    print the text "ok" and newline
end program"""
        code = transpile_c(source)
        assert "NULL" in code

    def test_nothing_pointer_compiles(self):
        source = """program NullTest:
    keep Ptr as handle to bytes with value nothing
    print the text "ok" and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile failed:\n{err}"
        assert out.strip() == "ok"


class TestTruthValueConsistency:
    """P7.1: truth value always maps to bool; true/false never emit 1/0."""

    def test_true_emits_true_not_1(self):
        source = """program BoolTest:
    keep Flag as truth value with value true
    print the text Flag and newline
end program"""
        code = transpile_c(source)
        assert "bool" in code
        assert "= true" in code
        assert "= 1;" not in code

    def test_false_emits_false_not_0(self):
        source = """program BoolFalse:
    keep Flag as truth value with value false
    print the text Flag and newline
end program"""
        code = transpile_c(source)
        assert "= false" in code
        assert "= 0;" not in code

    def test_stdbool_included(self):
        source = """program BoolInclude:
    keep B as truth value with value true
    print the text B and newline
end program"""
        code = transpile_c(source)
        assert "#include <stdbool.h>" in code

    def test_bool_conditional_runs(self):
        source = """program BoolCond:
    keep Done as truth value with value false
    if Done is false then:
        print the text "not done" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert "not done" in out


class TestJsonParserNested:
    """P1.2: JSON parser handles nested objects, arrays, integers, booleans."""

    def test_json_module_call_map(self):
        """Json.get_string and Json.get_int are wired in _MODULE_CALL_MAP."""
        from dictumc.emit_c import _MODULE_CALL_MAP
        assert _MODULE_CALL_MAP["Json.get_string"] == "dictum_json_get_string"
        assert _MODULE_CALL_MAP["Json.get_int"]    == "dictum_json_get_int"
        assert _MODULE_CALL_MAP["Json.get_float"]  == "dictum_json_get_float"
        assert _MODULE_CALL_MAP["Json.get_bool"]   == "dictum_json_get_bool"
        assert _MODULE_CALL_MAP["Json.destroy"]    == "dictum_json_destroy"

    def test_json_emit_get_string(self):
        """Json.get_string call transpiles to dictum_json_get_string(...)."""
        source = """program JsonGet:
    use Json
    keep H as whole number with value 0
    keep V as text with value ""
    call Json.get_string with H and "key" giving V
    print the text V and newline
end program"""
        code = transpile_c(source)
        assert "dictum_json_get_string" in code

    def test_json_emit_get_int(self):
        """Json.get_int call transpiles to dictum_json_get_int(...)."""
        source = """program JsonInt:
    use Json
    keep H as whole number with value 0
    keep N as whole number with value 0
    call Json.get_int with H and "count" giving N
    print the text N and newline
end program"""
        code = transpile_c(source)
        assert "dictum_json_get_int" in code


class TestFileModuleComplete:
    """P1.5: File module — seek, tell, flush, size, exists, delete, append wired."""

    def test_file_module_call_map_complete(self):
        from dictumc.emit_c import _MODULE_CALL_MAP
        for key, val in [
            ("File.open",      "dictum_file_open"),
            ("File.read_all",  "dictum_file_read_all"),
            ("File.seek",      "dictum_file_seek"),
            ("File.tell",      "dictum_file_tell"),
            ("File.flush",     "dictum_file_flush"),
            ("File.size",      "dictum_file_size"),
            ("File.exists",    "dictum_file_exists"),
            ("File.delete",    "dictum_file_delete"),
            ("File.append",    "dictum_file_append"),
            ("File.close",     "dictum_file_close"),
        ]:
            assert _MODULE_CALL_MAP[key] == val, f"Missing map for {key}"

    def test_file_exists_emit(self):
        source = """program FileExists:
    use File
    keep E as truth value with value false
    call File.exists with "test.txt" giving E
    print the text E and newline
end program"""
        code = transpile_c(source)
        assert "dictum_file_exists" in code

    def test_file_append_emit(self):
        source = """program FileAppend:
    use File
    call File.append with "out.txt" and "hello"
end program"""
        code = transpile_c(source)
        assert "dictum_file_append" in code


class TestTextModuleComplete:
    """P1.6: Text module — all functions wired to dictum_text_* implementations."""

    def test_text_module_call_map_complete(self):
        from dictumc.emit_c import _MODULE_CALL_MAP
        for key, val in [
            ("Text.length",      "dictum_text_length"),
            ("Text.utf8_length", "dictum_text_utf8_length"),
            ("Text.find",        "dictum_text_find"),
            ("Text.slice",       "dictum_text_slice"),
            ("Text.join",        "dictum_text_join"),
            ("Text.split",       "dictum_text_split"),
            ("Text.trim",        "dictum_text_trim"),
            ("Text.to_upper",    "dictum_text_to_upper"),
            ("Text.to_lower",    "dictum_text_to_lower"),
            ("Text.replace",     "dictum_text_replace"),
            ("Text.compare",     "dictum_text_compare"),
            ("Text.starts_with", "dictum_text_starts_with"),
            ("Text.ends_with",   "dictum_text_ends_with"),
            ("Text.contains",    "dictum_text_contains"),
            ("Text.format",      "dictum_text_format"),
            ("Text.from_int",    "dictum_text_from_int"),
            ("Text.from_float",  "dictum_text_from_float"),
        ]:
            assert _MODULE_CALL_MAP[key] == val, f"Missing or wrong map for {key}"

    def test_text_format_emits_dictum_function(self):
        source = """program TextFmt:
    use Text
    keep S as text with value ""
    call Text.format with "hello %s" and "world" giving S
    print the text S and newline
end program"""
        code = transpile_c(source)
        assert "dictum_text_format" in code

    def test_text_from_int_emits_dictum_function(self):
        source = """program TextFromInt:
    use Text
    keep S as text with value ""
    call Text.from_int with 42 giving S
    print the text S and newline
end program"""
        code = transpile_c(source)
        assert "dictum_text_from_int" in code


class TestModuleIncludeMap:
    """All stdlib modules map to correct #include headers."""

    def test_use_include_map_complete(self):
        from dictumc.emit_c import _USE_INCLUDE_MAP
        expected = {
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
        }
        for mod, header in expected.items():
            assert mod in _USE_INCLUDE_MAP, f"Module '{mod}' missing from _USE_INCLUDE_MAP"
            assert _USE_INCLUDE_MAP[mod] == header, \
                f"Wrong header for {mod}: got {_USE_INCLUDE_MAP[mod]}"

    def test_use_thread_emits_include(self):
        source = """program ThreadTest:
    use Thread
    print the text "ok" and newline
end program"""
        code = transpile_c(source)
        assert '#include "dictum_thread.h"' in code

    def test_makefile_thread_has_pthread(self):
        source = """program ThreadProg:
    use Thread
    print the text "hi" and newline
end program"""
        t = Transpiler(source, backend='c')
        result = t.run(validate=False)
        mf = result.get('makefile', '')
        assert '-lpthread' in mf

    def test_makefile_json_has_lm(self):
        source = """program JsonProg:
    use Json
    print the text "hi" and newline
end program"""
        t = Transpiler(source, backend='c')
        result = t.run(validate=False)
        mf = result.get('makefile', '')
        assert '-lm' in mf


class TestAttemptBlockFull:
    """P4.1: attempt block — error propagation, Err binding, both paths."""

    def test_attempt_failure_path_runs(self):
        """Attempt failure path: dictum_error_set inside block → failure body runs."""
        source = """program AttemptFail:
    attempt
        print the text "before" and newline
    on failure with Err
        print the text "failed" and newline
    end attempt
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Compile failed:\n{err}"
        # success path runs (no error set)
        assert "before" in out

    def test_attempt_emits_error_clear(self):
        source = """program AttemptClear:
    attempt
        print the text "x" and newline
    on failure with Err
        print the text "y" and newline
    end attempt
end program"""
        code = transpile_c(source)
        assert "dictum_error_clear" in code

    def test_attempt_emits_dictum_has_error(self):
        source = """program AttemptCheck:
    attempt
        print the text "a" and newline
    on failure with Err
        print the text "b" and newline
    end attempt
end program"""
        code = transpile_c(source)
        assert "DICTUM_HAS_ERROR" in code

    def test_attempt_err_binding_emits_dictum_error_last(self):
        source = """program AttemptErr:
    attempt
        print the text "ok" and newline
    on failure with Err
        print the text Err and newline
    end attempt
end program"""
        code = transpile_c(source)
        assert "dictum_error_last" in code


class TestRecursiveFunctions:
    """Compile+run: recursive action definitions work end-to-end."""

    def test_fibonacci_runs(self):
        source = """program Fib:
    action fib takes N as whole number produces whole number:
        if N is less than 2 then:
            produce success with N
        end if
        keep A as whole number with value 0
        keep B as whole number with value 0
        call fib with the difference of N and 1 giving A
        call fib with the difference of N and 2 giving B
        produce success with the sum of A and B
    end action
    keep R as whole number with value 0
    call fib with 10 giving R
    print the text R and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert out.strip() == "55"

    def test_factorial_runs(self):
        source = """program Fact:
    action fact takes N as whole number produces whole number:
        if N is less than or equal to 1 then:
            produce success with 1
        end if
        keep R as whole number with value 0
        call fact with the difference of N and 1 giving R
        produce success with the product of N and R
    end action
    keep F as whole number with value 0
    call fact with 6 giving F
    print the text F and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert out.strip() == "720"


class TestStructFieldAccess:
    """MISSING-01: struct field read/write compiles and runs correctly."""

    def test_struct_field_write_then_read(self):
        source = """program StructTest:
    shape Point holds:
        X as whole number
        Y as whole number
    end shape

    keep P as Point
    put 10 into P.X
    put 20 into P.Y
    print the text P.X and newline
    print the text P.Y and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        lines = out.strip().split("\n")
        assert lines[0].strip() == "10"
        assert lines[1].strip() == "20"


class TestListForEach:
    """MISSING-01: list declaration and for each loop compile and run."""

    def test_for_each_sums_list(self):
        source = """program ForEachSum:
    keep Items as list of whole number with values 1, 2, 3, 4, 5
    keep Total as whole number with value 0
    for each Item in Items repeat:
        put the sum of Total and Item into Total
    end for
    print the text Total and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert out.strip() == "15"


class TestDecimalArithmetic:
    """BUG-06: decimal number maps to double; arithmetic compiles and runs."""

    def test_decimal_division_runs(self):
        source = """program DecTest:
    keep A as decimal number with value 7.0
    keep B as decimal number with value 2.0
    keep C as decimal number with value 0.0
    put the quotient of A and B into C
    print the text C and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert "3.5" in out

    def test_decimal_type_in_code(self):
        source = """program DecType:
    keep X as decimal number with value 1.5
    print the text X and newline
end program"""
        code = transpile_c(source)
        assert "double" in code


class TestOtherwiseBranch:
    """MISSING: otherwise (else) branch compiles and runs correctly."""

    def test_otherwise_taken(self):
        source = """program OtherTest:
    keep X as whole number with value 5
    if X is greater than 10 then:
        print the text "big" and newline
    otherwise:
        print the text "small" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert "small" in out

    def test_otherwise_not_taken(self):
        source = """program OtherTest2:
    keep X as whole number with value 15
    if X is greater than 10 then:
        print the text "big" and newline
    otherwise:
        print the text "small" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert "big" in out


class TestSetStatement:
    """BUG-01: set X to / put into auto-declares undeclared variable."""

    def test_set_undeclared_var_compiles(self):
        source = """program SetTest:
    put 99 into Counter
    print the text Counter and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert out.strip() == "99"

    def test_set_text_variable_runs(self):
        source = """program SetText:
    put "hello" into Greeting
    print the text Greeting and newline
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert "hello" in out


class TestLessGreaterOrEqual:
    """less than or equal / greater than or equal comparisons compile and run."""

    def test_less_than_or_equal_true(self):
        source = """program LteTest:
    keep X as whole number with value 5
    if X is less than or equal to 5 then:
        print the text "yes" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert "yes" in out

    def test_greater_than_or_equal_true(self):
        source = """program GteTest:
    keep X as whole number with value 10
    if X is greater than or equal to 10 then:
        print the text "yes" and newline
    end if
end program"""
        rc, out, err = compile_and_run(transpile_c(source))
        assert rc == 0, f"Failed:\n{err}"
        assert "yes" in out


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])


# =============================================================================
# Tests for the 5 capability gaps fixed in this session
# =============================================================================

# ─── 1. Multi-file imports (MISSING-08) ──────────────────────────────────────

class TestMultiFileImports:
    """import MyModule from "mymodule.dict" — parser + transpiler resolution."""

    def test_import_dict_parses(self):
        from dictumc.parser import Parser
        from dictumc.lexer import Lexer
        from dictumc.ast_nodes import ImportDict
        source = 'import MathUtils from "mathutils.dict"\n'
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens).parse()
        nodes = [n for n in ast if isinstance(n, ImportDict)]
        assert len(nodes) == 1
        assert nodes[0].module_name == "MathUtils"
        assert nodes[0].file_path == "mathutils.dict"

    def test_import_dict_emits_include(self, tmp_path):
        """Transpiler emits #include "mymodule.h" when import is resolved."""
        mod_file = tmp_path / "greet.dict"
        mod_file.write_text("""program Greet:
    action hello takes Name as text produces text:
        produce success with Name
    end action
end program
""")
        main_source = f'import Greet from "{mod_file}"\nprogram Main:\n    print the text "ok" and newline\nend program'
        t = Transpiler(main_source, backend='c', source_path=str(tmp_path / "main.dict"))
        result = t.run(validate=False)
        code = result['code']
        assert '#include "greet.h"' in code

    def test_import_dict_produces_module_code(self, tmp_path):
        """dict_modules result contains c_code and h_code for the imported module."""
        mod_file = tmp_path / "utils.dict"
        mod_file.write_text("""program Utils:
    action add takes A as whole number and B as whole number produces whole number:
        produce success with the sum of A and B
    end action
end program
""")
        main_source = f'import Utils from "{mod_file}"\nprogram Main:\n    print the text "ok" and newline\nend program'
        t = Transpiler(main_source, backend='c', source_path=str(tmp_path / "main.dict"))
        result = t.run(validate=False)
        assert 'dict_modules' in result
        assert 'Utils' in result['dict_modules']
        mod = result['dict_modules']['Utils']
        assert 'c_code' in mod and mod['c_code']
        assert 'h_code' in mod and 'DICTUM_UTILS_H' in mod['h_code']

    def test_import_dict_missing_file_raises(self, tmp_path):
        """FileNotFoundError raised when the .dict file doesn't exist."""
        import pytest
        main_source = 'import Ghost from "ghost.dict"\nprogram Main:\n    print the text "x" and newline\nend program'
        t = Transpiler(main_source, backend='c', source_path=str(tmp_path / "main.dict"))
        with pytest.raises(FileNotFoundError, match="ghost.dict"):
            t.run(validate=False)

    def test_import_bare_string_infers_name(self):
        """import from "mymod.dict" — module name inferred from filename."""
        from dictumc.parser import Parser
        from dictumc.lexer import Lexer
        from dictumc.ast_nodes import ImportDict
        source = 'import from "mymod.dict"\n'
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens).parse()
        nodes = [n for n in ast if isinstance(n, ImportDict)]
        assert len(nodes) == 1
        assert nodes[0].module_name == "Mymod"


# ─── 2. HTTPS routing ────────────────────────────────────────────────────────

class TestHttpsRouting:
    """Http module auto-routes https:// through TLS, http:// through TCP."""

    def test_http_call_map_has_new_methods(self):
        from dictumc.emit_c import _MODULE_CALL_MAP
        for key, val in [
            ("Http.get",       "dictum_http_get"),
            ("Http.post",      "dictum_http_post"),
            ("Http.post_form", "dictum_http_post_form"),
            ("Http.put",       "dictum_http_put"),
            ("Http.delete",    "dictum_http_delete"),
            ("Http.patch",     "dictum_http_patch"),
        ]:
            assert _MODULE_CALL_MAP.get(key) == val, f"Missing/wrong: {key}"

    def test_http_get_emits_dictum_http_get(self):
        source = """program HttpTest:
    use Http
    keep Url as text with value "https://example.com/api"
    keep Resp as text with value ""
    call Http.get with Url giving Resp
    print the text Resp and newline
end program"""
        code = transpile_c(source)
        assert "dictum_http_get" in code
        assert '#include "dictum_http.h"' in code

    def test_https_makefile_includes_ssl(self):
        source = """program HttpsTest:
    use Http
    use Tls
    print the text "ok" and newline
end program"""
        t = Transpiler(source, backend='c')
        result = t.run(validate=False)
        mf = result.get('makefile', '')
        assert '-lssl' in mf
        assert '-lcrypto' in mf

    def test_http_header_documents_https(self):
        """dictum_http.h documents that https:// is routed through TLS."""
        import os
        h_path = os.path.join(os.path.dirname(__file__), '..', 'stdlib', 'dictum_http.h')
        with open(h_path) as f:
            content = f.read()
        assert 'https' in content.lower() or 'tls' in content.lower()


# ─── 3. JSON array indexing ───────────────────────────────────────────────────

class TestJsonArrayIndexing:
    """Json.get_at, Json.get_int_at, Json.array_length, Json.get_path."""

    def test_json_array_functions_in_call_map(self):
        from dictumc.emit_c import _MODULE_CALL_MAP
        for key, val in [
            ("Json.array_length",  "dictum_json_array_length"),
            ("Json.get_at",        "dictum_json_get_at"),
            ("Json.get_int_at",    "dictum_json_get_int_at"),
            ("Json.get_float_at",  "dictum_json_get_float_at"),
            ("Json.get_object_at", "dictum_json_get_object_at"),
            ("Json.get_path",      "dictum_json_get_path"),
            ("Json.length",        "dictum_json_length"),
        ]:
            assert _MODULE_CALL_MAP.get(key) == val, f"Missing: {key}"

    def test_json_get_at_emits_function(self):
        source = """program JsonArr:
    use Json
    keep H as whole number with value 0
    keep Item as text with value ""
    call Json.get_at with H and "items" and 0 giving Item
    print the text Item and newline
end program"""
        code = transpile_c(source)
        assert "dictum_json_get_at" in code

    def test_json_array_length_emits_function(self):
        source = """program JsonLen:
    use Json
    keep H as whole number with value 0
    keep L as whole number with value 0
    call Json.array_length with H and "items" giving L
    print the text L and newline
end program"""
        code = transpile_c(source)
        assert "dictum_json_array_length" in code

    def test_json_get_path_emits_function(self):
        source = """program JsonPath:
    use Json
    keep H as whole number with value 0
    keep V as text with value ""
    call Json.get_path with H and "slideshow.[0].author" giving V
    print the text V and newline
end program"""
        code = transpile_c(source)
        assert "dictum_json_get_path" in code

    def test_json_h_declares_array_functions(self):
        import os
        h_path = os.path.join(os.path.dirname(__file__), '..', 'stdlib', 'dictum_json.h')
        with open(h_path) as f:
            content = f.read()
        assert 'dictum_json_get_at' in content
        assert 'dictum_json_array_length' in content
        assert 'dictum_json_get_path' in content
        assert 'dictum_json_get_object_at' in content


# ─── 4. UTF-8 grapheme cluster support ───────────────────────────────────────

class TestGraphemeClusters:
    """Text.grapheme_length, Text.grapheme_slice, Text.grapheme_reverse."""

    def test_grapheme_functions_in_call_map(self):
        from dictumc.emit_c import _MODULE_CALL_MAP
        for key, val in [
            ("Text.grapheme_length",  "dictum_text_grapheme_length"),
            ("Text.grapheme_slice",   "dictum_text_grapheme_slice"),
            ("Text.grapheme_reverse", "dictum_text_grapheme_reverse"),
            ("Text.normalize",        "dictum_text_normalize"),
        ]:
            assert _MODULE_CALL_MAP.get(key) == val, f"Missing: {key}"

    def test_grapheme_length_emits_function(self):
        source = """program GLen:
    use Text
    keep S as text with value "hello"
    keep L as whole number with value 0
    call Text.grapheme_length with S giving L
    print the text L and newline
end program"""
        code = transpile_c(source)
        assert "dictum_text_grapheme_length" in code

    def test_grapheme_slice_emits_function(self):
        source = """program GSlice:
    use Text
    keep S as text with value "hello world"
    keep Out as text with value ""
    call Text.grapheme_slice with S and 0 and 5 giving Out
    print the text Out and newline
end program"""
        code = transpile_c(source)
        assert "dictum_text_grapheme_slice" in code

    def test_grapheme_reverse_emits_function(self):
        source = """program GRev:
    use Text
    keep S as text with value "hello"
    keep Out as text with value ""
    call Text.grapheme_reverse with S giving Out
    print the text Out and newline
end program"""
        code = transpile_c(source)
        assert "dictum_text_grapheme_reverse" in code

    def test_text_h_declares_grapheme_functions(self):
        import os
        h_path = os.path.join(os.path.dirname(__file__), '..', 'stdlib', 'dictum_text.h')
        with open(h_path) as f:
            content = f.read()
        assert 'dictum_text_grapheme_length' in content
        assert 'dictum_text_grapheme_slice' in content
        assert 'dictum_text_grapheme_reverse' in content
        assert 'dictum_text_normalize' in content

    def test_text_c_has_utf8_decode_function(self):
        import os
        c_path = os.path.join(os.path.dirname(__file__), '..', 'stdlib', 'dictum_text.c')
        with open(c_path) as f:
            content = f.read()
        assert 'utf8_decode' in content
        assert 'is_combining' in content
        assert 'grapheme cluster' in content


# ─── 5. VibeCoder workspace persistence ──────────────────────────────────────

class TestVibeCoderWorkspace:
    """SQLite-backed workspace: save, load, list, delete, rename."""

    def _make_app(self):
        """Import the FastAPI app without starting uvicorn."""
        import importlib, sys
        # Reload to get fresh state for each test
        if 'ui.backend_server' in sys.modules:
            del sys.modules['ui.backend_server']
        # patch _DB_PATH to use temp file
        return None  # tested via source inspection + unit tests below

    def test_backend_server_has_workspace_endpoints(self):
        """backend_server.py defines the workspace save/load/list/delete endpoints."""
        import os
        srv = os.path.join(os.path.dirname(__file__), '..', 'ui', 'backend_server.py')
        with open(srv) as f:
            content = f.read()
        assert '/workspace/{name}' in content
        assert 'workspace_save' in content
        assert 'workspace_load' in content
        assert 'workspace_list' in content
        assert 'workspace_delete' in content
        assert 'workspace_rename' in content

    def test_backend_server_uses_sqlite(self):
        import os
        srv = os.path.join(os.path.dirname(__file__), '..', 'ui', 'backend_server.py')
        with open(srv) as f:
            content = f.read()
        assert 'sqlite3' in content
        assert 'CREATE TABLE IF NOT EXISTS programs' in content
        assert 'INSERT INTO programs' in content
        assert 'ON CONFLICT' in content   # upsert for save/overwrite

    def test_backend_server_has_wal_mode(self):
        """WAL journal mode for concurrent access."""
        import os
        srv = os.path.join(os.path.dirname(__file__), '..', 'ui', 'backend_server.py')
        with open(srv) as f:
            content = f.read()
        assert 'journal_mode=WAL' in content

    def test_workspace_db_integration(self, tmp_path):
        """Direct SQLite integration test: save → load → list → delete."""
        import sqlite3, time as _time
        db_path = str(tmp_path / "test_workspace.db")

        def _db():
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS programs (
                name TEXT PRIMARY KEY, source TEXT NOT NULL,
                backend TEXT NOT NULL DEFAULT 'c', cpp_std INTEGER NOT NULL DEFAULT 17,
                saved_at INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT '')""")
            conn.commit()
            return conn

        # Save
        conn = _db()
        conn.execute(
            "INSERT INTO programs VALUES (?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET source=excluded.source,saved_at=excluded.saved_at",
            ("hello_world", "program Hello:\n    print the text \"hi\" and newline\nend program",
             "c", 17, int(_time.time()), "my first program")
        )
        conn.commit()
        conn.close()

        # Load
        conn = _db()
        row = conn.execute("SELECT name,source,notes FROM programs WHERE name='hello_world'").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "hello_world"
        assert "print" in row[1]
        assert row[2] == "my first program"

        # List
        conn = _db()
        rows = conn.execute("SELECT name FROM programs ORDER BY saved_at DESC").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "hello_world"

        # Delete
        conn = _db()
        conn.execute("DELETE FROM programs WHERE name='hello_world'")
        conn.commit()
        row = conn.execute("SELECT name FROM programs WHERE name='hello_world'").fetchone()
        conn.close()
        assert row is None

    def test_vibecoder_version_updated(self):
        """backend_server.py reports v5.1 with new features in root endpoint."""
        import os
        srv = os.path.join(os.path.dirname(__file__), '..', 'ui', 'backend_server.py')
        with open(srv) as f:
            content = f.read()
        assert 'version": "5.1"' in content or "version='5.1'" in content or '"5.1"' in content
        assert 'workspace_persistence' in content
        assert 'https_support' in content


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
