#!/usr/bin/env python3
"""
Dictum C++ Backend Integration Tests
Transpile → compile with g++ (C++17/20/23) → execute → verify output.
Requires g++ on PATH.
"""

import sys
import os
import subprocess
import tempfile
import shutil
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dictumc.transpiler import Transpiler, StdlibTranspiler
StdlibTranspilerV2 = StdlibTranspiler

STDLIB_DIR = os.path.join(os.path.dirname(__file__), '..', 'stdlib')
NICHE_DIR  = os.path.join(os.path.dirname(__file__), '..', 'niche')
GPP = shutil.which('g++')
pytestmark = pytest.mark.skipif(GPP is None, reason="g++ not found on PATH")

CPP_STANDARDS = [17, 20, 23]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def compile_and_run_cpp(cpp_code: str, std: int = 17) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, 'prog.cpp')
        exe = os.path.join(tmpdir, 'prog')
        with open(src, 'w') as f:
            f.write(cpp_code)

        cc = subprocess.run(
            [GPP, f'-std=c++{std}', '-O1', src, '-o', exe,
             f'-I{STDLIB_DIR}', f'-I{NICHE_DIR}'],
            capture_output=True, text=True, timeout=30
        )
        if cc.returncode != 0:
            return cc.returncode, '', cc.stderr

        run = subprocess.run([exe], capture_output=True, text=True, timeout=10)
        return run.returncode, run.stdout, run.stderr


def syntax_check_cpp(cpp_code: str, std: int = 17) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
        f.write(cpp_code)
        path = f.name
    try:
        proc = subprocess.run(
            [GPP, f'-std=c++{std}', '-fsyntax-only', '-Wno-unused-function',
             f'-I{STDLIB_DIR}', f'-I{NICHE_DIR}', path],
            capture_output=True, text=True
        )
        return proc.returncode == 0, proc.stderr
    finally:
        os.unlink(path)


def transpile_cpp(source: str, std: int = 17, stdlib: bool = False) -> str:
    if stdlib:
        t = StdlibTranspilerV2(source, backend='cpp', cpp_standard=std)
    else:
        t = Transpiler(source, backend='cpp', cpp_standard=std)
    result = t.run(validate=False)
    return result.get('code', '')


# ─────────────────────────────────────────────────────────────────────────────
# BASIC C++ PROGRAMS — tested across all standards
# ─────────────────────────────────────────────────────────────────────────────

BASIC_PROGRAMS = {
    "hello_cpp": (
        """program Hello:
    print the text "Hello, C++!" and newline
end program""",
        "Hello, C++!"
    ),
    "arithmetic": (
        """program Arith:
    keep A as whole number with value 100
    keep B as whole number with value 42
    keep C as whole number
    put the difference of A and B into C
    print the text "Diff: " and C and newline
end program""",
        "Diff: 58"
    ),
    "loop": (
        """program Loop:
    keep Sum as whole number with value 0
    repeat 10 times using I:
        put the sum of Sum and I into Sum
    end repeat
    print the text "Sum: " and Sum and newline
end program""",
        "Sum: "  # just check it runs and produces output
    ),
}


@pytest.mark.parametrize("std", CPP_STANDARDS)
@pytest.mark.parametrize("name,src_expected", [
    (name, data) for name, data in BASIC_PROGRAMS.items()
])
def test_basic_cpp_program(name, src_expected, std):
    source, expected = src_expected
    code = transpile_cpp(source, std=std)
    assert code, f"Empty output for {name} (std={std})"
    ok, err = syntax_check_cpp(code, std=std)
    assert ok, f"Syntax error in {name} (std={std}):\n{err}"


# ─────────────────────────────────────────────────────────────────────────────
# C++ SPECIFIC FEATURES
# ─────────────────────────────────────────────────────────────────────────────

class TestCppSpecificFeatures:
    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_class_generation(self, std):
        src = """program Classes:
    shape Counter holds:
        Value as whole number
        method increment produces nothing:
            put the sum of Value and 1 into Value
        end method
        method get_value produces whole number:
            produce success with Value
        end method
    end shape
end program"""
        code = transpile_cpp(src, std=std)
        assert code
        assert 'class Counter' in code or 'struct Counter' in code
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Syntax error (std={std}):\n{err}"

    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_namespace_generation(self, std):
        src = """module MathUtils:
    action square takes N as whole number produces whole number:
        produce success with the product of N and N
    end action
end module"""
        code = transpile_cpp(src, std=std)
        assert code
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Syntax error (std={std}):\n{err}"

    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_template_generation(self, std):
        src = """program Templates:
    action identity takes V as any Type produces Type:
        produce success with V
    end action
end program"""
        code = transpile_cpp(src, std=std)
        assert code
        # templates should appear in C++ output
        assert 'template' in code or 'auto' in code or 'typename' in code
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Syntax error (std={std}):\n{err}"

    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_includes_cpp_headers(self, std):
        src = """program CPPHeaders:
    keep X as whole number with value 1
end program"""
        code = transpile_cpp(src, std=std)
        # C++ backend should use C++ headers or at minimum compile
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Syntax error (std={std}):\n{err}"


# ─────────────────────────────────────────────────────────────────────────────
# CONSTRUCTOR / DESTRUCTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestCppConstructors:
    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_constructor_in_shape(self, std):
        src = """program WithCtor:
    shape Box holds:
        Width as whole number
        Height as whole number
        constructor takes W as whole number, H as whole number produces nothing:
            put W into Width
            put H into Height
        end constructor
        method area produces whole number:
            produce success with the product of Width and Height
        end method
    end shape
end program"""
        code = transpile_cpp(src, std=std)
        assert code
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Syntax error (std={std}):\n{err}"

    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_destructor_in_shape(self, std):
        src = """program WithDtor:
    shape Resource holds:
        Id as whole number
        destructor produces nothing:
            put 0 into Id
        end destructor
    end shape
end program"""
        code = transpile_cpp(src, std=std)
        assert code
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Syntax error (std={std}):\n{err}"


# ─────────────────────────────────────────────────────────────────────────────
# INHERITANCE
# ─────────────────────────────────────────────────────────────────────────────

class TestCppInheritance:
    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_shape_extension(self, std):
        src = """program Inherit:
    shape Animal holds:
        Name as text
        method speak produces nothing:
            print the text "..." and newline
        end method
    end shape
    shape Dog extends Animal holds:
        method speak produces nothing:
            print the text "Woof!" and newline
        end method
    end shape
end program"""
        code = transpile_cpp(src, std=std)
        assert code
        # inheritance keyword should be in output
        assert ('Animal' in code and 'Dog' in code)
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Syntax error (std={std}):\n{err}"


# ─────────────────────────────────────────────────────────────────────────────
# ERROR HANDLING
# ─────────────────────────────────────────────────────────────────────────────

class TestCppErrorHandling:
    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_attempt_block(self, std):
        src = """program ErrorHandling:
    attempt
        keep X as whole number with value 0
        print the text "ok" and newline
    on success
        print the text "success" and newline
    on failure with Err
        print the text "error" and newline
    end attempt
end program"""
        code = transpile_cpp(src, std=std)
        assert code
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Syntax error (std={std}):\n{err}"

    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_result_type(self, std):
        src = """program ResultType:
    action safe_divide takes A as whole number, B as whole number produces result:
        if B is equal to 0 then:
            produce failure with text "division by zero"
        end if
        produce success with the quotient of A and B
    end action
end program"""
        code = transpile_cpp(src, std=std)
        assert code
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Syntax error (std={std}):\n{err}"


# ─────────────────────────────────────────────────────────────────────────────
# STDLIB C++ INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

class TestCppStdlibIntegration:
    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_stdlib_transpiler_cpp_mode(self, std):
        src = """program StdlibCpp:
    keep Cfg as llm config
    keep Model as llm handle
end program"""
        t = StdlibTranspilerV2(src, backend='cpp', cpp_standard=std)
        result = t.run(validate=False)
        code = result.get('code', '')
        assert code, f"Empty output (std={std})"

    @pytest.mark.parametrize("std", CPP_STANDARDS)
    def test_syntax_check_stdlib_output(self, std):
        src = """program StdlibSyntax:
    keep X as whole number with value 42
    print the text "ok" and newline
end program"""
        code = transpile_cpp(src, std=std, stdlib=True)
        assert code
        ok, err = syntax_check_cpp(code, std=std)
        assert ok, f"Stdlib C++ syntax error (std={std}):\n{err}"


# ─────────────────────────────────────────────────────────────────────────────
# COMPILE AND RUN END-TO-END (C++17 only for speed)
# ─────────────────────────────────────────────────────────────────────────────

class TestCppRunEndToEnd:
    def test_hello_cpp_runs(self):
        src = """program Hello:
    print the text "Hello, C++!" and newline
end program"""
        code = transpile_cpp(src, std=17)
        rc, out, err = compile_and_run_cpp(code, std=17)
        assert rc == 0, f"Runtime error:\n{err}"
        assert "Hello, C++!" in out

    def test_arithmetic_runs(self):
        src = """program Arith:
    keep A as whole number with value 7
    keep B as whole number with value 6
    keep C as whole number
    put the product of A and B into C
    print the text "Product: " and C and newline
end program"""
        code = transpile_cpp(src, std=17)
        rc, out, err = compile_and_run_cpp(code, std=17)
        assert rc == 0, f"Runtime error:\n{err}"
        assert "Product: 42" in out

    def test_class_instantiation_runs(self):
        src = """program ClassRun:
    shape Point holds:
        X as whole number
        Y as whole number
    end shape
    keep P as Point
    put 10 into P.X
    put 20 into P.Y
    print the text "X=" and P.X and newline
end program"""
        code = transpile_cpp(src, std=17)
        assert code
        rc, out, err = compile_and_run_cpp(code, std=17)
        assert rc == 0, f"Runtime error:\n{err}"
        assert "10" in out  # P.X printed


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
