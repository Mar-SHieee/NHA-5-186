"""Tests for sliding-window splitting and the long-function embedding pipeline.

The pipeline tests use a fake embedder, so CodeBERT itself is never loaded.
The windowing tests need the CodeBERT *tokenizer* (a small download, cached after the
first run). If it cannot be loaded, these tests are skipped instead of failing.
"""

import math

import numpy as np
import pandas as pd
import pytest
import torch

from scripts.embeddings import long_embedding as le
from scripts.embeddings import long_function_analysis as lfa

LIMIT = 510  # 512 minus <s> and </s>


@pytest.fixture(scope="module", autouse=True)
def _tokenizer_available():
    try:
        lfa.get_tokenizer()
    except Exception as exc:  # no network and nothing cached
        pytest.skip(f"CodeBERT tokenizer unavailable: {exc}")


def make_code(n_repeats: int, head: str = "", tail: str = "") -> str:
    """Synthetic function: optional marker at the start, filler, optional marker at the end."""
    return head + "x = x + 1\n" * n_repeats + tail


def n_real_tokens(code: str) -> int:
    return len(lfa.get_tokenizer().encode(code, add_special_tokens=False))


class FakeEmbedder:
    """Returns a constant vector per chunk: value = len(text) % 7 + 1. None for empty text."""

    def __init__(self, dim: int = 8):
        self.dim = dim
        self.calls: list[int] = []

    def get_embeddings_batch(self, texts, batch_size=16):
        self.calls.append(len(texts))
        out = []
        for text in texts:
            if not isinstance(text, str) or not text.strip():
                out.append(None)
            else:
                out.append(torch.full((self.dim,), float(len(text) % 7 + 1)))
        return out


# ----------------------------------------------------------------------- windowing


def test_short_function_comes_back_unchanged():
    code = "int add(int a, int b) { return a + b; }"
    chunks, was_split = lfa.apply_truncation_policy(code)
    assert chunks == [code]
    assert was_split is False


def test_non_string_input_gives_no_chunks():
    assert lfa.apply_truncation_policy(None) == ([], False)
    assert lfa.apply_truncation_policy(float("nan")) == ([], False)
    assert lfa.count_tokens(None) == 0


def test_long_function_is_split_into_several_chunks():
    code = make_code(1500)  # well over 512 tokens
    chunks, was_split = lfa.apply_truncation_policy(code, max_windows=None)
    assert was_split is True
    assert len(chunks) > 1


def test_every_chunk_fits_in_512_tokens_after_retokenizing():
    """Chunks are text, so the embedder tokenizes them again and adds <s> and </s>."""
    code = make_code(2000)
    chunks, _ = lfa.apply_truncation_policy(code, max_windows=None)
    for chunk in chunks:
        assert lfa.count_tokens(chunk) <= 512


def test_max_windows_cap_is_respected():
    code = make_code(5000)
    chunks, _ = lfa.apply_truncation_policy(code, max_windows=4)
    assert 1 < len(chunks) <= 4


def test_no_cap_gives_more_windows_than_a_cap():
    code = make_code(5000)
    capped, _ = lfa.apply_truncation_policy(code, max_windows=4)
    uncapped, _ = lfa.apply_truncation_policy(code, max_windows=None)
    assert len(uncapped) > len(capped)


def test_more_overlap_means_more_windows():
    code = make_code(2000)
    small, _ = lfa.apply_truncation_policy(code, overlap=0, max_windows=None)
    large, _ = lfa.apply_truncation_policy(code, overlap=256, max_windows=None)
    assert len(large) > len(small)


@pytest.mark.parametrize(
    ("overflow", "keeps_head", "keeps_tail"),
    [("head_tail", True, True), ("head", True, False), ("tail", False, True)],
)
def test_overflow_modes_keep_the_right_end(overflow, keeps_head, keeps_tail):
    code = make_code(6000, head="HEADMARK = 1\n", tail="TAILMARK = 2\n")
    chunks, _ = lfa.apply_truncation_policy(code, max_windows=2, overflow=overflow)
    joined = "\n".join(chunks)
    assert ("HEADMARK" in joined) is keeps_head
    assert ("TAILMARK" in joined) is keeps_tail


@pytest.mark.parametrize(
    "kwargs",
    [
        {"overlap": 600},
        {"overlap": -1},
        {"max_windows": 0},
        {"overflow": "middle"},
        {"head_ratio": 1.5},
    ],
)
def test_invalid_settings_raise(kwargs):
    with pytest.raises(ValueError):
        lfa.apply_truncation_policy(make_code(2000), **kwargs)


def test_window_budget_matches_the_policy_note():
    # 510 + (8 - 1) * (510 - 64) = 3632 real tokens
    assert lfa.window_budget(overlap=64, max_windows=8) == 3632
    assert lfa.window_budget(overlap=64, max_windows=None) == math.inf


@pytest.mark.parametrize("n_repeats", [10, 60, 400, 1500, 4000])
@pytest.mark.parametrize("max_windows", [None, 4])
def test_windows_needed_matches_actual_chunk_count(n_repeats, max_windows):
    code = make_code(n_repeats)
    chunks, _ = lfa.apply_truncation_policy(code, overlap=64, max_windows=max_windows)
    expected = lfa.windows_needed(n_real_tokens(code), overlap=64, max_windows=max_windows)
    assert len(chunks) == expected


# ----------------------------------------------------------------------- pipeline


def build_df():
    return pd.DataFrame(
        {
            "code": [
                "int a;",  # short
                make_code(1500),  # long
                "   ",  # empty
            ],
            "label": [0, 1, 0],
        }
    )


def test_missing_code_column_raises():
    with pytest.raises(ValueError, match="code"):
        le.process_dataset(pd.DataFrame({"x": [1]}), FakeEmbedder())


def test_non_positive_batch_size_raises():
    with pytest.raises(ValueError, match="batch_size"):
        le.process_dataset(build_df(), FakeEmbedder(), batch_size=0)


def test_matrix_has_one_row_per_function():
    df, matrix = le.process_dataset(build_df(), FakeEmbedder(dim=8), max_windows=None)
    assert matrix.shape == (3, 8)
    assert matrix.dtype == np.float32
    assert len(df) == 3


def test_short_function_vector_is_its_single_chunk():
    df, matrix = le.process_dataset(build_df(), FakeEmbedder(dim=8))
    assert df.loc[0, "num_chunks"] == 1
    assert df.loc[0, "was_truncated"] is False or not df.loc[0, "was_truncated"]
    assert np.allclose(matrix[0], len("int a;") % 7 + 1)


def test_long_function_vector_is_the_mean_of_its_chunks():
    code = make_code(1500)
    df, matrix = le.process_dataset(build_df(), FakeEmbedder(dim=8), max_windows=None)
    chunks, _ = lfa.apply_truncation_policy(code, overlap=le.OVERLAP, max_windows=None)
    expected = np.mean([len(c) % 7 + 1 for c in chunks])
    assert df.loc[1, "num_chunks"] == len(chunks) > 1
    assert np.allclose(matrix[1], expected)


def test_empty_code_gets_zero_vector_and_flag():
    df, matrix = le.process_dataset(build_df(), FakeEmbedder(dim=8))
    assert bool(df.loc[2, "has_embedding"]) is False
    assert np.all(matrix[2] == 0)
    assert bool(df.loc[0, "has_embedding"]) is True


def test_num_chunks_never_exceeds_the_cap():
    df, _ = le.process_dataset(build_df(), FakeEmbedder(), max_windows=3)
    assert df["num_chunks"].max() <= 3


def test_embedder_gets_all_chunks_in_one_call():
    embedder = FakeEmbedder()
    df, _ = le.process_dataset(build_df(), embedder, max_windows=None)
    assert embedder.calls == [int(df["num_chunks"].sum())]


def test_output_keeps_metadata_but_not_code_or_chunk_text():
    df, _ = le.process_dataset(build_df(), FakeEmbedder())
    for column in ("token_count", "was_truncated", "num_chunks", "has_embedding", "label"):
        assert column in df.columns
    assert "code" not in df.columns
    assert "processed_code" not in df.columns


def test_row_order_is_preserved_when_index_is_not_default():
    df = build_df()
    df.index = [30, 10, 20]
    out, matrix = le.process_dataset(df, FakeEmbedder(dim=8))
    assert list(out["label"]) == [0, 1, 0]
    assert np.allclose(matrix[0], len("int a;") % 7 + 1)
