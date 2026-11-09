"""W3 seam S02: manifest flags from meta/key.json are prefixed once (M4 writes 'key:modulation' already)."""

from mvh.runner.finalize import key_flags


def test_key_flags_are_not_double_prefixed():
    assert key_flags({"flags": ["key:modulation", "key:parallel_ambiguity"]}) == ["key:modulation", "key:parallel_ambiguity"]
    assert key_flags({"flags": ["low_confidence"]}) == ["key:low_confidence"]
    assert key_flags({}) == []
