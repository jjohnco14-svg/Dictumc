# Contributing to Dictum

## Repository Layout

```
dictum_v5/
├── dictumc/          # Python transpiler (lexer, parser, validator, emitters)
├── stdlib/           # C standard library implementations
├── tests/            # pytest test suite
├── examples/         # .dict example programs (level1–level5)
├── docs/             # This documentation
├── ui/               # VibeCoder browser UI + backend server
└── industry_skills/  # Skill JSON descriptors
```

## Running the Test Suite

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

The integration tests require `gcc` on `PATH`. They are automatically skipped if gcc is absent.

## Adding a New Stdlib Module

1. Create `stdlib/dictum_mymodule.h` and `stdlib/dictum_mymodule.c`.
2. Add `dictum_mymodule.c` to `STDLIB_SRCS` in `stdlib/Makefile`.
3. Add the module include mapping to `_USE_INCLUDE_MAP` in `dictumc/emit_c.py`.
4. Register the module's actions in `dictumc/stdlib_registry.py` under `STDLIB_ACTION_FAMILIES`.
5. Add compile+run integration tests in `tests/test_integration_c.py`.

## Fixing a Transpiler Bug

1. Write a failing test first in `tests/test_integration_c.py` (or `test_dictum.py` for string-match tests).
2. Identify the affected node type in `dictumc/emit_c.py` (`emit_node`) or `dictumc/parser.py`.
3. Fix and run `pytest tests/ -k your_test_name`.
4. Run the full suite to check for regressions: `pytest tests/ -x`.

## Code Style

- Python: follow PEP 8; type-annotate public methods.
- C: C11, `snake_case`, `dictum_` prefix for all public symbols, `DICTUM_` for macros.
- Every public C function must check its inputs and return a safe default or `DICTUM_FAILURE` on bad args.

## Commit Messages

```
fix(emit_c): attempt block now uses dictum_last_error for real error propagation
feat(stdlib): dictum_file_seek/tell/exists/flush/append — P1.5 complete
test(integration): compile+run tests for all P5.1 features
```
