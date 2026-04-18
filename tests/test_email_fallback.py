"""Tests for email_fallback.py — pattern-guess emails."""
from __future__ import annotations

from email_fallback import apply_pattern


def test_apply_pattern_first():
    assert apply_pattern("Alex", "Chen", "example.com", "{first}") == "alex@example.com"


def test_apply_pattern_first_dot_last():
    assert apply_pattern("Alex", "Chen", "example.com", "{first}.{last}") == "alex.chen@example.com"


def test_apply_pattern_first_initial_last():
    assert apply_pattern("Alex", "Chen", "example.com", "{f}{last}") == "achen@example.com"


def test_apply_pattern_last_first_initial():
    assert apply_pattern("Alex", "Chen", "example.com", "{last}{f}") == "chena@example.com"


def test_apply_pattern_handles_mixed_case_and_trims():
    assert apply_pattern("  ALEX ", "chen", "EXAMPLE.com", "{first}.{last}") == "alex.chen@example.com"


def test_apply_pattern_unknown_token_raises():
    import pytest
    with pytest.raises(ValueError, match="unknown"):
        apply_pattern("A", "B", "example.com", "{middle}")
