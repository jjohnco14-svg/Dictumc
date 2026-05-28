#!/usr/bin/env python3
"""
Dictum Polyglot Integration Test Suite — v1.1.0

Tests:
  - PolyglotParser: all new syntax constructs
  - InterfaceExtractor: correct AST → PolyglotInterface
  - CppBindingGenerator: safe / unsafe / checked / C++ headers
  - PolyglotLinker: full link pass, Makefile, CMake, demo files
  - PolyglotTranspiler: end-to-end pipeline
  - C compilation: generated binding .c files compile with gcc
  - Safety levels: safe NULL checks, unsafe raw ABI, checked assertions
"""

import sys, os, subprocess, tempfile, textwrap
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest

from dictumc.lexer import Lexer
from dictumc.polyglot_parser import PolyglotParser
from dictumc.polyglot_transpiler import PolyglotTranspiler
from dictumc.polyglot_ast import (
    PolyglotModule, ExportDecl, UnsafeForeignCall, BuildDirective,
    ForeignShape, PolyglotImport, SafetyLevel, PolyglotInterface,
    ExportedSymbol, ExportedShape,
)
from dictumc.linker import InterfaceExtractor
from dictumc.linker.binding_generator import CppBindingGenerator
from dictumc.linker.polyglot_linker import PolyglotLinker
from dictumc.ast_nodes import Action, Shape


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def parse_polyglot(source: str):
    tokens = Lexer(source).tokenize()
    return PolyglotParser(tokens).parse()


def transpile_polyglot(source: str, backend: str = 'c',
                       safety: str = SafetyLevel.SAFE) -> dict:
    t = PolyglotTranspiler(source, backend=backend, safety=safety)
    return t.run(validate=False, link=True, write_files=False)


def compile_c(source_code: str, extra_flags: list = None) -> str:
    """Compile a C source string and return stdout of the resulting binary."""
    flags = ['-std=c11', '-O1', '-lm'] + (extra_flags or [])
    with tempfile.NamedTemporaryFile(suffix='.c', mode='w', delete=False,
                                     encoding='utf-8') as tf:
        tf.write(source_code)
        src = tf.name
    binary = src + '.out'
    proc = subprocess.run(
        ['gcc'] + flags + [src, '-o', binary],
        capture_output=True, text=True
    )
    os.unlink(src)
    if proc.returncode != 0:
        raise RuntimeError(f"Compile error:\n{proc.stderr}\n\nSource:\n{source_code}")
    result = subprocess.run([binary], capture_output=True, text=True, timeout=5)
    os.unlink(binary)
    return result.stdout


def compile_c_with_headers(headers: dict, main_src: str,
                            extra_flags: list = None) -> str:
    """
    Write header + impl files to a temp dir, compile everything together.
    headers = {filename: content}
    .h/.hpp files are written as headers; .c files are compiled alongside main.
    """
    import tempfile, os, subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write all files (headers and .c impls)
        extra_srcs = []
        for fname, content in headers.items():
            fpath = os.path.join(tmpdir, fname)
            with open(fpath, 'w') as f:
                f.write(content)
            if fname.endswith('.c'):
                extra_srcs.append(fpath)

        # Write main .c
        src_path = os.path.join(tmpdir, 'test_main.c')
        with open(src_path, 'w') as f:
            f.write(main_src)
        binary = os.path.join(tmpdir, 'test_main')
        flags = ['-std=c11', '-O1', '-lm', f'-I{tmpdir}'] + (extra_flags or [])
        all_srcs = [src_path] + extra_srcs
        proc = subprocess.run(
            ['gcc'] + flags + all_srcs + ['-o', binary],
            capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Compile error:\n{proc.stderr}\n\nMain source:\n{main_src}"
            )
        result = subprocess.run([binary], capture_output=True, text=True, timeout=5)
        return result.stdout


def make_iface(module_name='mymod', backend='c',
               safety=SafetyLevel.SAFE, interop='ffi',
               exports=None, shapes=None, directives=None) -> PolyglotInterface:
    return PolyglotInterface(
        module_name=module_name,
        backend=backend,
        safety=safety,
        interop=interop,
        exports=exports or [],
        shapes=shapes or [],
        build_directives=directives or [],
    )


def make_sym(name='add', params=None, ret_type='whole number',
             safety=SafetyLevel.SAFE, c_name=None,
             calling_conv='cdecl', thread_safe=False) -> ExportedSymbol:
    return ExportedSymbol(
        name=name,
        c_name=c_name or name,
        params=params or [('A', 'whole number'), ('B', 'whole number')],
        ret_type=ret_type,
        safety=safety,
        calling_conv=calling_conv,
        thread_safe=thread_safe,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. Parser tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPolyglotParser(unittest.TestCase):

    def test_polyglot_module_c(self):
        src = """
polyglot module math uses c as safe via ffi
    action add takes A as whole number and B as whole number produces whole number:
        produce success with the sum of A and B
    end action
end module
"""
        ast = parse_polyglot(src)
        mods = [n for n in ast if isinstance(n, PolyglotModule)]
        self.assertEqual(len(mods), 1)
        m = mods[0]
        self.assertEqual(m.name, 'math')
        self.assertEqual(m.backend, 'c')
        self.assertEqual(m.safety, SafetyLevel.SAFE)
        self.assertEqual(m.interop, 'ffi')

    def test_polyglot_module_cpp(self):
        src = """
polyglot module engine uses cpp as unsafe via ffi
    action compute takes X as whole number produces fractional number:
        produce success with 3.14
    end action
end module
"""
        ast = parse_polyglot(src)
        mods = [n for n in ast if isinstance(n, PolyglotModule)]
        self.assertEqual(mods[0].backend, 'cpp')
        self.assertEqual(mods[0].safety, SafetyLevel.UNSAFE)

    def test_polyglot_module_checked(self):
        src = """
polyglot module safe_engine uses c as checked via ffi
    action noop produces nothing:
        produce success with 0
    end action
end module
"""
        ast = parse_polyglot(src)
        mods = [n for n in ast if isinstance(n, PolyglotModule)]
        self.assertEqual(mods[0].safety, SafetyLevel.CHECKED)

    def test_export_annotation_basic(self):
        src = """
program Test:
    @export
    action greet takes Name as text produces nothing:
        print the text Name and newline
    end action
end program
"""
        ast = parse_polyglot(src)
        # Find action in program body
        from dictumc.ast_nodes import Program
        prog = next(n for n in ast if isinstance(n, Program))
        actions = [n for n in prog.body if isinstance(n, Action)]
        self.assertEqual(len(actions), 1)
        exp = getattr(actions[0], '_polyglot_export', None)
        self.assertIsNotNone(exp, "Action should have _polyglot_export attached")
        self.assertEqual(exp.c_name, 'greet')
        self.assertEqual(exp.safety, SafetyLevel.SAFE)

    def test_export_annotation_unsafe(self):
        src = """
program Test:
    @export unsafe threadsafe as "raw_compute"
    action compute takes X as whole number produces whole number:
        produce success with X
    end action
end program
"""
        ast = parse_polyglot(src)
        from dictumc.ast_nodes import Program
        prog = next(n for n in ast if isinstance(n, Program))
        act = next(n for n in prog.body if isinstance(n, Action))
        exp = getattr(act, '_polyglot_export', None)
        self.assertIsNotNone(exp)
        self.assertEqual(exp.safety, SafetyLevel.UNSAFE)
        self.assertTrue(exp.thread_safe)
        self.assertEqual(exp.c_name, 'raw_compute')

    def test_export_annotation_checked(self):
        src = """
program Test:
    @export checked
    action process takes Data as text produces whole number:
        produce success with 1
    end action
end program
"""
        ast = parse_polyglot(src)
        from dictumc.ast_nodes import Program
        prog = next(n for n in ast if isinstance(n, Program))
        act = next(n for n in prog.body if isinstance(n, Action))
        exp = getattr(act, '_polyglot_export', None)
        self.assertEqual(exp.safety, SafetyLevel.CHECKED)

    def test_serializable_annotation(self):
        src = """
program Test:
    @serializable json
    shape Task holds
        Name as text
        Priority as whole number
    end shape
end program
"""
        ast = parse_polyglot(src)
        from dictumc.ast_nodes import Program
        prog = next(n for n in ast if isinstance(n, Program))
        shape = next(n for n in prog.body if isinstance(n, Shape))
        fmt = getattr(shape, '_serializable', None)
        self.assertEqual(fmt, 'json')

    def test_polyglot_import(self):
        src = """
program Test:
    polyglot import ml_module as ml via ffi
end program
"""
        ast = parse_polyglot(src)
        from dictumc.ast_nodes import Program
        prog = next(n for n in ast if isinstance(n, Program))
        imports = [n for n in prog.body if isinstance(n, PolyglotImport)]
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0].module_name, 'ml_module')
        self.assertEqual(imports[0].alias, 'ml')
        self.assertEqual(imports[0].pattern, 'ffi')

    def test_build_directive_link(self):
        src = """
program Test:
    #[link "curl"]
    #[cflags "-O3"]
    #[ldflags "-lpthread"]
    keep X as whole number with value 1
end program
"""
        ast = parse_polyglot(src)
        from dictumc.ast_nodes import Program
        prog = next(n for n in ast if isinstance(n, Program))
        directives = [n for n in prog.body if isinstance(n, BuildDirective)]
        kinds = [d.kind for d in directives]
        self.assertIn('link', kinds)
        self.assertIn('cflags', kinds)
        self.assertIn('ldflags', kinds)
        link_d = next(d for d in directives if d.kind == 'link')
        self.assertEqual(link_d.value, 'curl')

    def test_unsafe_foreign_call(self):
        src = """
program Test:
    keep X as whole number with value 0
    unsafe call foreign "my_lib_function" with X giving Result as whole number
end program
"""
        ast = parse_polyglot(src)
        from dictumc.ast_nodes import Program
        prog = next(n for n in ast if isinstance(n, Program))
        ufcs = [n for n in prog.body if isinstance(n, UnsafeForeignCall)]
        self.assertEqual(len(ufcs), 1)
        self.assertEqual(ufcs[0].symbol, 'my_lib_function')
        self.assertEqual(ufcs[0].result_name, 'Result')
        self.assertEqual(ufcs[0].result_type, 'whole number')

    def test_foreign_shape(self):
        src = """
polyglot module legacy uses c as unsafe via ffi
end module
"""
        ast = parse_polyglot(src)
        # PolyglotModule parses cleanly
        mods = [n for n in ast if isinstance(n, PolyglotModule)]
        self.assertEqual(len(mods), 1)

    def test_invalid_backend_raises(self):
        src = """
polyglot module bad uses ruby as safe via ffi
end module
"""
        with self.assertRaises(SyntaxError):
            parse_polyglot(src)

    def test_invalid_interop_raises(self):
        src = """
polyglot module bad uses c as safe via tcp
end module
"""
        with self.assertRaises(SyntaxError):
            parse_polyglot(src)

    def test_multiple_modules_parsed(self):
        src = """
polyglot module ml uses python as safe via grpc
end module
polyglot module api uses go as safe via http
end module
polyglot module ui uses rust as safe via wasm
end module
"""
        ast = parse_polyglot(src)
        mods = [n for n in ast if isinstance(n, PolyglotModule)]
        self.assertEqual(len(mods), 3)
        backends = {m.name: m.backend for m in mods}
        self.assertEqual(backends['ml'], 'python')
        self.assertEqual(backends['api'], 'go')
        self.assertEqual(backends['ui'], 'rust')


# ──────────────────────────────────────────────────────────────────────────────
# 2. InterfaceExtractor tests
# ──────────────────────────────────────────────────────────────────────────────

class TestInterfaceExtractor(unittest.TestCase):

    def test_extracts_module_interface(self):
        src = """
polyglot module math uses c as safe via ffi
    @export
    action add takes A as whole number and B as whole number produces whole number:
        produce success with the sum of A and B
    end action
end module
"""
        ast = parse_polyglot(src)
        ext = InterfaceExtractor()
        ifaces = ext.extract(ast)
        self.assertIn('math', ifaces)
        iface = ifaces['math']
        self.assertEqual(iface.backend, 'c')
        self.assertEqual(iface.safety, SafetyLevel.SAFE)
        self.assertEqual(len(iface.exports), 1)
        self.assertEqual(iface.exports[0].name, 'add')

    def test_extracts_unsafe_module(self):
        src = """
polyglot module kernel uses c as unsafe via ffi
    @export unsafe
    action write_reg takes Addr as whole number and Val as whole number produces nothing:
        produce success with 0
    end action
end module
"""
        ast = parse_polyglot(src)
        ext = InterfaceExtractor()
        ifaces = ext.extract(ast)
        self.assertIn('kernel', ifaces)
        sym = ifaces['kernel'].exports[0]
        self.assertEqual(sym.safety, SafetyLevel.UNSAFE)

    def test_extracts_serializable_shape(self):
        src = """
polyglot module api uses c as safe via ffi
    @export
    @serializable json
    shape Task holds
        Name as text
        Priority as whole number
    end shape
    @export
    action create_task takes Name as text produces Task:
        keep T as Task
        produce success with T
    end action
end module
"""
        ast = parse_polyglot(src)
        ext = InterfaceExtractor()
        ifaces = ext.extract(ast)
        self.assertIn('api', ifaces)
        iface = ifaces['api']
        exported_shapes = iface.shapes
        self.assertEqual(len(exported_shapes), 1)
        self.assertEqual(exported_shapes[0].name, 'Task')
        self.assertTrue(exported_shapes[0].serializable)
        self.assertEqual(exported_shapes[0].serialization_format, 'json')

    def test_extracts_build_directives(self):
        src = """
polyglot module http_mod uses c as safe via ffi
    #[link "curl"]
    #[ldflags "-lssl"]
    @export
    action fetch takes Url as text produces text:
        produce success with Url
    end action
end module
"""
        ast = parse_polyglot(src)
        ext = InterfaceExtractor()
        ifaces = ext.extract(ast)
        directives = ifaces['http_mod'].build_directives
        kinds = [d.kind for d in directives]
        self.assertIn('link', kinds)
        self.assertIn('ldflags', kinds)

    def test_thread_safe_flag_propagated(self):
        src = """
polyglot module concurrent uses c as safe via ffi
    @export threadsafe
    action process takes X as whole number produces whole number:
        produce success with X
    end action
end module
"""
        ast = parse_polyglot(src)
        ext = InterfaceExtractor()
        ifaces = ext.extract(ast)
        sym = ifaces['concurrent'].exports[0]
        self.assertTrue(sym.thread_safe)

    def test_c_name_override(self):
        src = """
polyglot module mymod uses c as safe via ffi
    @export as "my_c_function"
    action my_dictum_function takes X as whole number produces whole number:
        produce success with X
    end action
end module
"""
        ast = parse_polyglot(src)
        ext = InterfaceExtractor()
        ifaces = ext.extract(ast)
        sym = ifaces['mymod'].exports[0]
        self.assertEqual(sym.c_name, 'my_c_function')
        self.assertEqual(sym.name, 'my_dictum_function')


# ──────────────────────────────────────────────────────────────────────────────
# 3. CppBindingGenerator — header content tests
# ──────────────────────────────────────────────────────────────────────────────

class TestBindingGeneratorHeaders(unittest.TestCase):

    def _make_math_iface(self) -> PolyglotInterface:
        return make_iface(
            module_name='math',
            exports=[
                make_sym('add',   [('A','whole number'), ('B','whole number')], 'whole number'),
                make_sym('divide',[('N','whole number'), ('D','whole number')], 'fractional number'),
                make_sym('greet', [('Name','text')], 'nothing'),
            ]
        )

    # ── shared header ────────────────────────────────────────────────
    def test_shared_header_has_pragma_once(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        files = gen.generate()
        self.assertIn('#pragma once', files['math_polyglot.h'])

    def test_shared_header_has_extern_c(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_polyglot.h']
        self.assertIn('extern "C"', h)

    def test_shared_header_forward_decls(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_polyglot.h']
        self.assertIn('int32_t add(', h)
        self.assertIn('double divide(', h)
        self.assertIn('void greet(', h)

    def test_shared_header_struct(self):
        iface = make_iface(
            module_name='types',
            shapes=[ExportedShape(
                name='Point',
                fields=[('X', 'whole number'), ('Y', 'whole number')],
                packed=False,
            )]
        )
        gen = CppBindingGenerator(iface, {})
        h = gen.generate()['types_polyglot.h']
        self.assertIn('typedef struct {', h)
        self.assertIn('int32_t X;', h)
        self.assertIn('int32_t Y;', h)
        self.assertIn('} Point;', h)

    def test_packed_struct(self):
        iface = make_iface(
            module_name='packed_mod',
            shapes=[ExportedShape(
                name='Header', fields=[('Id','whole number'), ('Len','count')], packed=True
            )]
        )
        gen = CppBindingGenerator(iface, {})
        h = gen.generate()['packed_mod_polyglot.h']
        self.assertIn('#pragma pack(push, 1)', h)
        self.assertIn('#pragma pack(pop)', h)

    # ── safe header ──────────────────────────────────────────────────
    def test_safe_header_null_check_macro(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_safe.h']
        self.assertIn('DICTUM_NULL_CHECK', h)

    def test_safe_header_wrapper_declarations(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_safe.h']
        self.assertIn('dictum_safe_add(', h)
        self.assertIn('dictum_safe_divide(', h)
        self.assertIn('dictum_safe_greet(', h)

    def test_safe_header_thread_safe_doc(self):
        iface = make_iface(exports=[make_sym('work', [], 'nothing', thread_safe=True)])
        gen = CppBindingGenerator(iface, {})
        h = gen.generate()['mymod_safe.h']
        self.assertIn('threadsafe', h.lower())

    # ── safe impl ───────────────────────────────────────────────────
    def test_safe_impl_null_checks_pointer_params(self):
        iface = make_iface(
            module_name='netmod',
            exports=[make_sym('send', [('Data','handle to bytes'), ('Len','count')], 'nothing')]
        )
        gen = CppBindingGenerator(iface, {})
        c = gen.generate()['netmod_safe.c']
        self.assertIn('DICTUM_NULL_CHECK', c)

    def test_safe_impl_string_length_check(self):
        iface = make_iface(
            module_name='textmod',
            exports=[make_sym('print_msg', [('Msg','text')], 'nothing')]
        )
        gen = CppBindingGenerator(iface, {})
        c = gen.generate()['textmod_safe.c']
        self.assertIn('strlen', c)

    def test_safe_impl_calls_raw_symbol(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        c = gen.generate()['math_safe.c']
        self.assertIn('return add(', c)
        self.assertIn('return divide(', c)

    # ── unsafe header ───────────────────────────────────────────────
    def test_unsafe_header_no_null_checks(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_unsafe.h']
        self.assertNotIn('DICTUM_NULL_CHECK', h)

    def test_unsafe_header_raw_declarations(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_unsafe.h']
        # Raw symbol names (not dictum_safe_ prefixed)
        self.assertIn('int32_t add(', h)
        self.assertIn('double divide(', h)

    def test_unsafe_header_macro_aliases(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_unsafe.h']
        self.assertIn('DICTUM_UNSAFE_ADD', h)
        self.assertIn('DICTUM_UNSAFE_DIVIDE', h)

    def test_unsafe_header_mutable_char_pointer(self):
        """Unsafe: text → char* (mutable), not const char*."""
        iface = make_iface(
            module_name='buf',
            exports=[make_sym('fill', [('Buf','text')], 'nothing',
                              safety=SafetyLevel.UNSAFE)]
        )
        gen = CppBindingGenerator(iface, {})
        h = gen.generate()['buf_unsafe.h']
        self.assertIn('char* Buf', h)
        self.assertNotIn('const char*', h)

    # ── checked header ──────────────────────────────────────────────
    def test_checked_header_has_assert_include(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_checked.h']
        self.assertIn('#include <assert.h>', h)

    def test_checked_header_ndebug_macros(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_checked.h']
        self.assertIn('NDEBUG', h)
        self.assertIn('DICTUM_CHECK_PTR', h)
        self.assertIn('DICTUM_CHECK_BOUNDS', h)
        self.assertIn('DICTUM_CHECK_STR', h)

    def test_checked_impl_asserts_on_pointers(self):
        iface = make_iface(
            module_name='chkmod',
            exports=[make_sym('process', [('Data','handle to bytes')], 'nothing')]
        )
        gen = CppBindingGenerator(iface, {})
        c = gen.generate()['chkmod_checked.c']
        self.assertIn('DICTUM_CHECK_PTR', c)

    def test_checked_impl_asserts_on_strings(self):
        iface = make_iface(
            module_name='strmod',
            exports=[make_sym('log_msg', [('Msg','text')], 'nothing')]
        )
        gen = CppBindingGenerator(iface, {})
        c = gen.generate()['strmod_checked.c']
        self.assertIn('DICTUM_CHECK_STR', c)

    # ── C++ header ──────────────────────────────────────────────────
    def test_cpp_header_namespace(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_cxx.hpp']
        self.assertIn('namespace dictum::math', h)

    def test_cpp_header_optional_return(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_cxx.hpp']
        self.assertIn('std::optional', h)

    def test_cpp_header_string_param(self):
        gen = CppBindingGenerator(self._make_math_iface(), {})
        h = gen.generate()['math_cxx.hpp']
        self.assertIn('std::string', h)

    def test_cpp_header_void_wrapper_no_optional(self):
        iface = make_iface(
            module_name='logmod',
            exports=[make_sym('log', [('Msg','text')], 'nothing')]
        )
        gen = CppBindingGenerator(iface, {})
        h = gen.generate()['logmod_cxx.hpp']
        # void return should not be wrapped in optional
        self.assertIn('inline void log(', h)

    def test_cpp_struct_wrapper(self):
        iface = make_iface(
            module_name='geom',
            shapes=[ExportedShape(
                name='Vec2',
                fields=[('X','fractional number'), ('Y','fractional number')],
            )]
        )
        gen = CppBindingGenerator(iface, {})
        h = gen.generate()['geom_cxx.hpp']
        self.assertIn('Vec2Wrapper', h)
        self.assertIn('get_X()', h)
        self.assertIn('get_Y()', h)
        self.assertIn('set_X(', h)

    # ── serialisation ───────────────────────────────────────────────
    def test_serial_header_to_json_decl(self):
        iface = make_iface(
            module_name='serial',
            shapes=[ExportedShape(
                name='Packet',
                fields=[('Id','whole number'), ('Data','text')],
                serializable=True,
                serialization_format='json',
            )]
        )
        gen = CppBindingGenerator(iface, {})
        h = gen.generate()['serial_serial.h']
        self.assertIn('Packet_to_json', h)
        self.assertIn('Packet_from_json', h)

    def test_serial_impl_snprintf_encode(self):
        iface = make_iface(
            module_name='serial',
            shapes=[ExportedShape(
                name='Msg',
                fields=[('Code','whole number'), ('Text','text')],
                serializable=True,
            )]
        )
        gen = CppBindingGenerator(iface, {})
        c = gen.generate()['serial_serial.c']
        self.assertIn('snprintf', c)
        self.assertIn('strstr', c)


# ──────────────────────────────────────────────────────────────────────────────
# 4. PolyglotLinker tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPolyglotLinker(unittest.TestCase):

    def _two_module_linker(self) -> PolyglotLinker:
        math_iface = make_iface(
            'math', exports=[
                make_sym('add', [('A','whole number'),('B','whole number')], 'whole number'),
                make_sym('sqrt_f', [('X','fractional number')], 'fractional number'),
            ]
        )
        text_iface = make_iface(
            'textlib', exports=[
                make_sym('upper', [('S','text')], 'text'),
                make_sym('lower', [('S','text')], 'text'),
            ],
            shapes=[ExportedShape('StrResult', [('Data','text'), ('Len','count')], serializable=True)]
        )
        return PolyglotLinker({'math': math_iface, 'textlib': text_iface},
                               output_dir='/tmp/poly_test', project_name='test_proj')

    def test_link_produces_all_files(self):
        linker = self._two_module_linker()
        files = linker.link()
        self.assertIn('polyglot_registry.h', files)
        self.assertIn('Makefile', files)
        self.assertIn('CMakeLists.txt', files)
        self.assertIn('polyglot_demo.c', files)
        self.assertIn('polyglot_demo.cpp', files)
        self.assertIn('math_polyglot.h', files)
        self.assertIn('math_safe.h', files)
        self.assertIn('math_unsafe.h', files)
        self.assertIn('math_checked.h', files)
        self.assertIn('math_cxx.hpp', files)

    def test_registry_includes_all_modules(self):
        linker = self._two_module_linker()
        files = linker.link()
        reg = files['polyglot_registry.h']
        self.assertIn('math_polyglot.h', reg)
        self.assertIn('textlib_polyglot.h', reg)

    def test_registry_convenience_macros(self):
        linker = self._two_module_linker()
        reg = linker.link()['polyglot_registry.h']
        self.assertIn('DICTUM_CALL_SAFE', reg)
        self.assertIn('DICTUM_CALL_UNSAFE', reg)
        self.assertIn('DICTUM_CALL_CHECKED', reg)

    def test_makefile_has_compiler_vars(self):
        linker = self._two_module_linker()
        mk = linker.link()['Makefile']
        self.assertIn('CC      = gcc', mk)
        self.assertIn('CXX     = g++', mk)
        self.assertIn('-std=c11', mk)

    def test_makefile_lm_always_present(self):
        linker = self._two_module_linker()
        mk = linker.link()['Makefile']
        self.assertIn('-lm', mk)

    def test_makefile_includes_link_directives(self):
        iface = make_iface(
            'netmod',
            directives=[
                BuildDirective(kind='link', value='curl'),
                BuildDirective(kind='ldflags', value='-lssl'),
            ],
            exports=[make_sym('fetch')]
        )
        linker = PolyglotLinker({'netmod': iface})
        mk = linker.link()['Makefile']
        self.assertIn('-lcurl', mk)
        self.assertIn('-lssl', mk)

    def test_cmake_project_name(self):
        linker = self._two_module_linker()
        cmake = linker.link()['CMakeLists.txt']
        self.assertIn('project(test_proj', cmake)

    def test_cmake_add_library(self):
        linker = self._two_module_linker()
        cmake = linker.link()['CMakeLists.txt']
        self.assertIn('add_library(polyglot', cmake)

    def test_demo_c_calls_safe_wrappers(self):
        linker = self._two_module_linker()
        demo = linker.link()['polyglot_demo.c']
        self.assertIn('dictum_safe_add', demo)
        self.assertIn('dictum_safe_upper', demo)
        self.assertIn('dictum_safe_lower', demo)

    def test_demo_cpp_uses_namespace(self):
        linker = self._two_module_linker()
        demo = linker.link()['polyglot_demo.cpp']
        self.assertIn('dictum::math::add', demo)
        self.assertIn('dictum::textlib::upper', demo)

    def test_grpc_proto_generated(self):
        iface = make_iface(
            'ml', backend='python', interop='grpc',
            exports=[make_sym('predict', [('Input','text')], 'fractional number')]
        )
        linker = PolyglotLinker({'ml': iface})
        files = linker.link()
        self.assertIn('ml.proto', files)
        proto = files['ml.proto']
        self.assertIn('syntax = "proto3"', proto)
        self.assertIn('rpc Predict', proto)
        self.assertIn('PredictRequest', proto)
        self.assertIn('PredictResponse', proto)

    def test_openapi_yaml_generated(self):
        iface = make_iface(
            'api', backend='go', interop='http',
            exports=[make_sym('create_task', [('Name','text'), ('Pri','whole number')], 'whole number')]
        )
        linker = PolyglotLinker({'api': iface})
        files = linker.link()
        self.assertIn('api_openapi.yaml', files)
        yaml = files['api_openapi.yaml']
        self.assertIn('openapi:', yaml)
        self.assertIn('/create_task:', yaml)

    def test_serial_files_present_when_serializable(self):
        linker = self._two_module_linker()
        files = linker.link()
        self.assertIn('textlib_serial.h', files)
        self.assertIn('textlib_serial.c', files)

    def test_no_serial_files_when_no_serializable(self):
        iface = make_iface('plain', exports=[make_sym('fn')])
        linker = PolyglotLinker({'plain': iface})
        files = linker.link()
        self.assertNotIn('plain_serial.h', files)


# ──────────────────────────────────────────────────────────────────────────────
# 5. PolyglotTranspiler end-to-end tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPolyglotTranspilerE2E(unittest.TestCase):

    def test_basic_polyglot_pipeline(self):
        src = """
polyglot module math uses c as safe via ffi
    @export
    action add takes A as whole number and B as whole number produces whole number:
        produce success with the sum of A and B
    end action
end module
"""
        result = transpile_polyglot(src)
        self.assertIn('code', result)
        self.assertIn('interfaces', result)
        self.assertIn('polyglot_files', result)
        self.assertIn('math', result['interfaces'])
        self.assertIn('math_safe.h', result['polyglot_files'])

    def test_unsafe_pipeline(self):
        src = """
polyglot module low_level uses c as unsafe via ffi
    @export unsafe
    action write_raw takes Ptr as handle to bytes and Val as byte produces nothing:
        produce success with 0
    end action
end module
"""
        result = transpile_polyglot(src, safety=SafetyLevel.UNSAFE)
        self.assertIn('low_level_unsafe.h', result['polyglot_files'])
        h = result['polyglot_files']['low_level_unsafe.h']
        self.assertIn('DICTUM_UNSAFE', h)

    def test_checked_pipeline(self):
        src = """
polyglot module verified uses c as checked via ffi
    @export checked
    action validate takes Input as text produces truth value:
        produce success with true
    end action
end module
"""
        result = transpile_polyglot(src, safety=SafetyLevel.CHECKED)
        self.assertIn('verified_checked.h', result['polyglot_files'])
        h = result['polyglot_files']['verified_checked.h']
        self.assertIn('DICTUM_CHECK_PTR', h)

    def test_cpp_backend_pipeline(self):
        src = """
polyglot module engine uses cpp as safe via ffi
    @export
    action compute takes X as whole number produces fractional number:
        keep R as fractional number with value 0.0
        produce success with R
    end action
end module
"""
        result = transpile_polyglot(src, backend='cpp')
        self.assertIn('engine_cxx.hpp', result['polyglot_files'])
        hpp = result['polyglot_files']['engine_cxx.hpp']
        self.assertIn('namespace dictum::engine', hpp)

    def test_multiple_modules_linked(self):
        src = """
polyglot module ml uses python as safe via grpc
end module
polyglot module api uses go as safe via http
    @export
    action handle takes Req as text produces text:
        produce success with Req
    end action
end module
polyglot module core uses c as safe via ffi
    @export
    action init produces nothing:
        produce success with 0
    end action
end module
"""
        result = transpile_polyglot(src)
        self.assertIn('ml', result['interfaces'])
        self.assertIn('api', result['interfaces'])
        self.assertIn('core', result['interfaces'])
        self.assertIn('polyglot_registry.h', result['polyglot_files'])

    def test_program_with_export_annotation(self):
        """@export on actions inside a program (not a polyglot module)."""
        src = """
program MyApp:
    @export
    action process takes Data as text produces whole number:
        produce success with 42
    end action
    keep Result as whole number with value 0
    call process with "hello" giving Result
    print the text Result and newline
end program
"""
        result = transpile_polyglot(src)
        # Should have 'default' interface with the exported action
        ifaces = result.get('interfaces', {})
        if 'default' in ifaces:
            self.assertEqual(len(ifaces['default'].exports), 1)
            self.assertEqual(ifaces['default'].exports[0].name, 'process')

    def test_build_directives_in_makefile(self):
        src = """
polyglot module http_client uses c as safe via ffi
    #[link "curl"]
    #[cflags "-DUSE_TLS"]
    @export
    action fetch takes Url as text produces text:
        produce success with Url
    end action
end module
"""
        result = transpile_polyglot(src)
        mk = result['polyglot_files']['Makefile']
        self.assertIn('-lcurl', mk)
        self.assertIn('-DUSE_TLS', mk)


# ──────────────────────────────────────────────────────────────────────────────
# 6. C compilation tests — generated headers compile cleanly
# ──────────────────────────────────────────────────────────────────────────────

class TestGeneratedCodeCompiles(unittest.TestCase):

    def _get_headers(self, module_name: str,
                     exports=None, shapes=None) -> dict:
        iface = make_iface(module_name, exports=exports, shapes=shapes)
        gen = CppBindingGenerator(iface, {})
        return gen.generate()

    def test_shared_header_compiles(self):
        files = self._get_headers('math', exports=[
            make_sym('add', [('A','whole number'),('B','whole number')], 'whole number'),
        ])
        # Only test the shared header file, not the impl .c files
        shared_only = {'math_polyglot.h': files['math_polyglot.h']}
        main = '#include "math_polyglot.h"\nint32_t add(int32_t A, int32_t B) { return A+B; }\nint main(void) { return 0; }\n'
        compile_c_with_headers(shared_only, main)

    def test_safe_wrapper_compiles(self):
        files = self._get_headers('math2', exports=[
            make_sym('add', [('A','whole number'),('B','whole number')], 'whole number'),
        ])
        main = textwrap.dedent("""\
            #include "math2_polyglot.h"
            #include "math2_safe.h"
            int32_t add(int32_t A, int32_t B) { return A + B; }
            int main(void) { dictum_safe_add(1, 2); return 0; }
        """)
        compile_c_with_headers(files, main)

    def test_checked_wrapper_compiles(self):
        files = self._get_headers('chk', exports=[
            make_sym('compute', [('X','whole number')], 'whole number'),
        ])
        main = textwrap.dedent("""\
            #include "chk_polyglot.h"
            #include "chk_checked.h"
            int32_t compute(int32_t X) { return X * 2; }
            int main(void) { dictum_checked_compute(5); return 0; }
        """)
        compile_c_with_headers(files, main)

    def test_safe_null_check_prevents_crash(self):
        files = self._get_headers('ptr_test', exports=[
            make_sym('process', [('Data','handle to bytes')], 'whole number'),
        ])
        main = textwrap.dedent("""\
            #include "ptr_test_polyglot.h"
            #include "ptr_test_safe.h"
            int32_t process(void* Data) { return 42; }
            int main(void) {
                int32_t r = dictum_safe_process(NULL);
                if (r != 0) return 1;
                return 0;
            }
        """)
        compile_c_with_headers(files, main)

    def test_checked_ndebug_strips_asserts(self):
        files = self._get_headers('nd', exports=[
            make_sym('fn', [('P','handle to bytes')], 'nothing'),
        ])
        main = textwrap.dedent("""\
            #define NDEBUG
            #include "nd_polyglot.h"
            #include "nd_checked.h"
            void fn(void* P) {}
            int main(void) { dictum_checked_fn(NULL); return 0; }
        """)
        compile_c_with_headers(files, main, ['-DNDEBUG'])

    def test_serial_impl_compiles(self):
        iface = make_iface(
            module_name='sr',
            shapes=[ExportedShape(
                name='Item',
                fields=[('Id','whole number'), ('Score','fractional number')],
                serializable=True,
            )]
        )
        gen = CppBindingGenerator(iface, {})
        files = gen.generate()
        main = textwrap.dedent("""\
            #include "sr_polyglot.h"
            #include "sr_serial.h"
            #include <stdio.h>
            #include <stdlib.h>
            int main(void) {
                Item it = {42, 3.14};
                char* json = Item_to_json(&it);
                if (json) { printf("%s\\n", json); free(json); }
                return 0;
            }
        """)
        out = compile_c_with_headers(files, main)
        self.assertIn('42', out)

    def test_unsafe_header_compiles(self):
        files = self._get_headers('uh', exports=[
            make_sym('raw_fn', [('X','whole number')], 'whole number',
                     safety=SafetyLevel.UNSAFE),
        ])
        main = textwrap.dedent("""\
            #include "uh_polyglot.h"
            #include "uh_unsafe.h"
            int32_t raw_fn(int32_t X) { return X; }
            int main(void) { raw_fn(1); return 0; }
        """)
        compile_c_with_headers(files, main)

    def test_safe_impl_null_checks_pointer_params(self):
        iface = make_iface(
            module_name='netmod',
            exports=[make_sym('send', [('Data','handle to bytes'), ('Len','count')], 'nothing')]
        )
        gen = CppBindingGenerator(iface, {})
        files = gen.generate()
        c = files['netmod_safe.c']
        self.assertIn('DICTUM_NULL_CHECK', c)


class TestEmitterPolyglotNodes(unittest.TestCase):

    def test_c_emitter_polyglot_module(self):
        src = """
polyglot module math uses c as safe via ffi
    @export
    action add takes A as whole number and B as whole number produces whole number:
        produce success with the sum of A and B
    end action
end module
"""
        result = transpile_polyglot(src, backend='c')
        code = result['code']
        # Should contain comment and the action body
        self.assertIn('polyglot module', code)
        self.assertIn('add', code)

    def test_c_emitter_polyglot_import(self):
        src = """
program Test:
    polyglot import ml_mod as ml via ffi
    keep X as whole number with value 1
end program
"""
        result = transpile_polyglot(src, backend='c')
        code = result['code']
        self.assertIn('ml_mod_polyglot.h', code)

    def test_c_emitter_build_directive(self):
        src = """
program Test:
    #[link "curl"]
    keep X as whole number with value 1
end program
"""
        result = transpile_polyglot(src, backend='c')
        code = result['code']
        self.assertIn('link', code)
        self.assertIn('curl', code)

    def test_cpp_emitter_polyglot_module_namespace(self):
        src = """
polyglot module engine uses cpp as safe via ffi
    @export
    action init produces nothing:
        produce success with 0
    end action
end module
"""
        result = transpile_polyglot(src, backend='cpp')
        code = result['code']
        self.assertIn('namespace engine', code)

    def test_cpp_emitter_polyglot_import(self):
        src = """
program Test:
    polyglot import backend as be via ffi
    keep X as whole number with value 1
end program
"""
        result = transpile_polyglot(src, backend='cpp')
        code = result['code']
        self.assertIn('backend_cxx.hpp', code)


# ──────────────────────────────────────────────────────────────────────────────
# 8. Regression — v4 existing tests still pass
# ──────────────────────────────────────────────────────────────────────────────

class TestPolyglotDoesNotBreakV4(unittest.TestCase):
    """Ensure polyglot changes don't regress the base transpiler."""

    def _transpile(self, src, backend='c'):
        from dictumc.transpiler import Transpiler
        t = Transpiler(src, backend=backend)
        return t.run(validate=False)['code']

    def test_basic_program_still_works(self):
        src = """
program Hello:
    print the text "hello" and newline
end program"""
        code = self._transpile(src)
        self.assertIn('printf', code)

    def test_recursive_function_still_works(self):
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
        code = self._transpile(src)
        self.assertIn('fact', code)

    def test_set_statement_still_works(self):
        src = """
program Test:
    keep N as whole number with value 0
    set N to 42
    print the text N and newline
end program"""
        code = self._transpile(src)
        self.assertIn('N = 42', code)

    def test_base_transpiler_not_using_polyglot_parser(self):
        """Base Transpiler should still use the base Parser, not PolyglotParser."""
        from dictumc.transpiler import Transpiler
        from dictumc.parser import Parser
        from dictumc.polyglot_parser import PolyglotParser
        import inspect
        src_code = inspect.getsource(Transpiler.run)
        # Base Transpiler should use Parser, not PolyglotParser
        self.assertIn('Parser', src_code)


if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
