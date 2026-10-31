"""Stable schema values and hash behavior."""

import hashlib

from shield_core.graph_dataset.schema import (
    CONVERTER_VERSION,
    EDGE_TYPES,
    NODE_TYPES,
    NUM_NODE_FEATURES,
    ConverterConfig,
    text_hash64,
)


def test_schema_contract_is_fixed():
    assert len(NODE_TYPES) == 12
    assert list(EDGE_TYPES.values()) == list(range(6))
    assert NUM_NODE_FEATURES == 15
    assert CONVERTER_VERSION == "1.0"


def test_config_validation_and_stable_fingerprint():
    assert ConverterConfig().fingerprint() == ConverterConfig().fingerprint()
    assert ConverterConfig(max_nodes=999).fingerprint() != ConverterConfig().fingerprint()
    for kwargs in ({"stub_rule": "C"}, {"max_nodes": 0}, {"edge_types": ("bad",)}):
        try:
            ConverterConfig(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid config accepted: {kwargs}")


def test_text_hash_uses_signed_first_sha256_word():
    expected = int(hashlib.sha256(b"node").hexdigest()[:16], 16)
    expected = expected - 2**64 if expected >= 2**63 else expected
    assert text_hash64("node") == expected
    assert -(2**63) <= expected < 2**63
