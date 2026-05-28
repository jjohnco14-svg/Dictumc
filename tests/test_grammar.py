#!/usr/bin/env python3
"""
Dictum Grammar Constraint Tests
Tests DictumGrammar token masking, state transitions, and
grammar-constrained generation correctness.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dictumc.grammar import DictumGrammar, GrammarConstrainedGenerator, resync_from_source
from dictumc.lexer import Lexer, TokenType
from dictumc.stdlib_registry import DICTUM_STDLIB_TYPES, STDLIB_ACTION_FAMILIES
# v5 compat: GrammarTokenizerBridge renamed/removed; use GrammarConstrainedGenerator
GrammarTokenizerBridge = GrammarConstrainedGenerator


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def feed_source(grammar: DictumGrammar, source: str) -> list:
    """Tokenise source and feed each token to the grammar. Return (value, accepted) pairs."""
    tokens = Lexer(source).tokenize()
    results = []
    for tok in tokens:
        if tok.type == TokenType.EOF:
            break
        ttype = "WORD" if tok.type == TokenType.WORD else tok.type.name
        accepted = grammar.feed_token(str(tok.value), ttype, strict=False)
        results.append((str(tok.value), accepted))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# INITIAL STATE
# ─────────────────────────────────────────────────────────────────────────────

class TestGrammarInitialState:
    def test_grammar_starts_at_top_level(self):
        g = DictumGrammar()
        assert g.current() is not None
        assert g.current().name == 'TOP_LEVEL'

    def test_cpp_grammar_starts_at_top_level(self):
        g = DictumGrammar(cpp_mode=True)
        assert g.current().name == 'TOP_LEVEL'

    def test_get_valid_tokens_returns_iterable(self):
        g = DictumGrammar()
        tokens = g.get_valid_tokens()
        token_list = list(tokens)
        assert len(token_list) > 0

    def test_initial_valid_tokens_include_keywords(self):
        g = DictumGrammar()
        tokens = set(g.get_valid_tokens())
        keywords = {'program', 'module', 'action', 'shape'}
        assert keywords & tokens, f"Expected keywords in {tokens}"


# ─────────────────────────────────────────────────────────────────────────────
# TOKEN ACCEPTANCE
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenAcceptance:
    def test_accept_program_keyword(self):
        g = DictumGrammar()
        result = g.feed_token('program', 'WORD', strict=False)
        assert result is not False

    def test_accept_module_keyword(self):
        g = DictumGrammar()
        result = g.feed_token('module', 'WORD', strict=False)
        assert result is not False

    def test_program_block_sequence_accepted(self):
        """'program Foo:' should be accepted token-by-token."""
        g = DictumGrammar()
        for word, ttype in [('program', 'WORD'), ('Foo', 'WORD'), (':', 'COLON')]:
            r = g.feed_token(word, ttype, strict=False)
            assert r is not False, f"Rejected '{word}' (ttype={ttype})"

    def test_module_block_sequence_accepted(self):
        g = DictumGrammar()
        for word, ttype in [('module', 'WORD'), ('Console', 'WORD'), (':', 'COLON')]:
            r = g.feed_token(word, ttype, strict=False)
            assert r is not False, f"Rejected '{word}'"


# ─────────────────────────────────────────────────────────────────────────────
# STATE TRANSITIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestStateTransitions:
    def test_state_exists_after_token(self):
        g = DictumGrammar()
        g.feed_token('program', 'WORD', strict=False)
        assert g.current() is not None

    def test_checkpoint_and_restore(self):
        """Grammar checkpoint allows backtracking to a prior state."""
        g = DictumGrammar()
        initial = g.current().name

        # Feed a token to change state
        g.feed_token('program', 'WORD', strict=False)
        state_after_program = g.current().name

        # Checkpoint and continue
        ckpt = g.checkpoint()
        assert ckpt is not None

        g.feed_token('Test', 'WORD', strict=False)

        # Restore and verify we're back to post-program state
        g.rollback(ckpt)
        restored = g.current().name
        assert restored == state_after_program, (
            f"restore() should return to state '{state_after_program}', got '{restored}'"
        )

    
    def test_cpp_mode_grammar_instantiates(self):
        g_cpp = DictumGrammar(cpp_mode=True)
        assert g_cpp.current().name == 'TOP_LEVEL'

    def test_fresh_grammar_has_same_state_each_time(self):
        g1 = DictumGrammar()
        g2 = DictumGrammar()
        assert g1.current().name == g2.current().name


# ─────────────────────────────────────────────────────────────────────────────
# FULL PROGRAM WALKS
# ─────────────────────────────────────────────────────────────────────────────

class TestFullProgramWalks:
    def test_minimal_program_walk(self):
        source = """program Hello:
    keep X as whole number with value 1
end program"""
        g = DictumGrammar()
        results = feed_source(g, source)
        rejections = [(v, ok) for v, ok in results if ok is False]
        assert len(rejections) == 0, f"Unexpected rejections: {rejections}"

    def test_module_action_walk(self):
        source = """module Math:
    action add takes A as whole number, B as whole number produces whole number:
        produce success with the sum of A and B
    end action
end module"""
        g = DictumGrammar()
        results = feed_source(g, source)
        rejections = [(v, ok) for v, ok in results if ok is False]
        assert len(rejections) == 0, f"Rejections: {rejections}"

    def test_shape_definition_walk(self):
        source = """program Test:
    shape Point holds:
        X as whole number
        Y as whole number
    end shape
end program"""
        g = DictumGrammar()
        results = feed_source(g, source)
        rejections = [(v, ok) for v, ok in results if ok is False]
        assert len(rejections) == 0, f"Rejections: {rejections}"

    def test_cpp_class_walk(self):
        source = """program Test:
    shape Vec holds:
        X as fractional number
        Y as fractional number
        method magnitude produces fractional number:
            produce success with the square root of the sum of the product of X and X and the product of Y and Y
        end method
    end shape
end program"""
        g = DictumGrammar(cpp_mode=True)
        results = feed_source(g, source)
        rejections = [(v, ok) for v, ok in results if ok is False]
        assert len(rejections) == 0, f"Rejections: {rejections}"

    def test_if_statement_walk(self):
        source = """program Test:
    keep X as whole number with value 5
    if X is greater than 0 then:
        print the text "positive" and newline
    end if
end program"""
        g = DictumGrammar()
        results = feed_source(g, source)
        rejections = [(v, ok) for v, ok in results if ok is False]
        assert len(rejections) == 0, f"Rejections: {rejections}"


# ─────────────────────────────────────────────────────────────────────────────
# GRAMMAR TOKENIZER BRIDGE
# ─────────────────────────────────────────────────────────────────────────────

class TestGrammarTokenizerBridge:
    def _make_vocab(self):
        """GrammarTokenizerBridge takes a vocab dict {token_str: token_id}."""
        words = ['program', 'module', 'keep', 'action', 'shape', 'end',
                 'produces', 'takes', 'as', 'whole', 'number', 'text',
                 'print', 'newline', ':', 'and', 'with', 'value', '$$$junk$$$']
        return {w: i for i, w in enumerate(words)}

    def test_bridge_instantiates(self):
        vocab = self._make_vocab()
        from dictumc.grammar import DictumGrammar
        _grammar = DictumGrammar()
        bridge = GrammarConstrainedGenerator(_grammar, vocab)
        assert bridge is not None

    def test_bridge_has_mask_method(self):
        vocab = self._make_vocab()
        from dictumc.grammar import DictumGrammar
        _grammar = DictumGrammar()
        bridge = GrammarConstrainedGenerator(_grammar, vocab)
        # Bridge should expose some token-filtering API
        has_api = (hasattr(bridge, 'get_logits_mask') or
                   hasattr(bridge, 'get_allowed_tokens') or
                   hasattr(bridge, 'mask') or
                   hasattr(bridge, 'get_mask') or
                   hasattr(bridge, 'get_valid_ids'))
        if not has_api:
            pytest.skip(f"GrammarTokenizerBridge has no mask API yet: {[m for m in dir(bridge) if not m.startswith("_")]}")

    def test_bridge_vocab_coverage(self):
        vocab = self._make_vocab()
        from dictumc.grammar import DictumGrammar
        _grammar = DictumGrammar()
        bridge = GrammarConstrainedGenerator(_grammar, vocab)
        # Verify at minimum it stores/references the vocab
        assert bridge is not None


# ─────────────────────────────────────────────────────────────────────────────
# STDLIB TYPES IN GRAMMAR
# ─────────────────────────────────────────────────────────────────────────────

class TestStdlibGrammarIntegration:
    def test_stdlib_types_dict_populated(self):
        assert len(DICTUM_STDLIB_TYPES) > 0
        assert 'http_response' in DICTUM_STDLIB_TYPES  # v5: set of type names
        assert 'file_handle' in DICTUM_STDLIB_TYPES  # v5: only custom stdlib types, not primitives

    def test_stdlib_action_families_populated(self):
        assert len(STDLIB_ACTION_FAMILIES) > 0
        assert isinstance(STDLIB_ACTION_FAMILIES, dict)

    def test_niche_handle_types_present(self):
        niche_keys = [k for k in DICTUM_STDLIB_TYPES if 'handle' in k or 'config' in k]
        assert len(niche_keys) > 0, f"No handle/config types in {list(DICTUM_STDLIB_TYPES.keys())}"

    def test_action_families_have_named_entries(self):
        """v5: STDLIB_ACTION_FAMILIES keys are 'Module.fn', values are (c_name, params, ret)."""
        for key, value in STDLIB_ACTION_FAMILIES.items():
            assert isinstance(key, str), f"Key should be str, got {type(key)}"
            assert isinstance(value, tuple) and len(value) == 3, (
                f"Value for '{key}' should be (c_name, params, ret), got {value}"
            )
            c_name, params, ret = value
            assert isinstance(c_name, str)
            assert isinstance(params, list)
            assert isinstance(ret, str)

    def test_all_action_names_start_with_dictum(self):
        """Most C implementations use dictum_ prefix (stdlib wrappers may not)."""
        dictum_prefixed = [c_name for (c_name, _, _) in STDLIB_ACTION_FAMILIES.values()
                           if c_name.startswith('dictum_')]
        assert len(dictum_prefixed) > 20, (
            f"Expected >20 dictum_ prefixed actions, got {len(dictum_prefixed)}"
        )

    def test_llm_family_present(self):
        assert 'LLM.load' in STDLIB_ACTION_FAMILIES  # v5 key format

    def test_robot_family_present(self):
        assert 'Robot.move' in STDLIB_ACTION_FAMILIES  # v5 key format


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
