import pandas as pd
import pytest

from scripts.long_function_analysis import (
    apply_truncation_policy,
    count_tokens,
)


def test_short_function():
    code = "def add(a, b): return a + b"

    chunks, was_truncated = apply_truncation_policy(code)

    assert len(chunks) == 1
    assert was_truncated is False
    assert chunks[0] == code


def test_long_function_is_split():
    code = "\n".join(f"variable_{i} = {i}" for i in range(1500))

    chunks, was_truncated = apply_truncation_policy(
        code,
        max_tokens=512,
        stride=256,
    )

    assert len(chunks) > 1
    assert was_truncated is True

    for chunk in chunks:
        assert count_tokens(chunk) <= 512


def test_empty_function():
    chunks, was_truncated = apply_truncation_policy("")

    assert chunks == []
    assert was_truncated is False


def test_invalid_max_tokens():
    with pytest.raises(ValueError):
        apply_truncation_policy(
            "def add(a, b): return a + b",
            max_tokens=0,
        )


def test_batch_grouping():
    chunks = [f"chunk_{i}" for i in range(10)]
    batch_size = 4

    batches = [chunks[i : i + batch_size] for i in range(0, len(chunks), batch_size)]

    assert len(batches) == 3
    assert [len(batch) for batch in batches] == [4, 4, 2]
    assert sum(len(batch) for batch in batches) == len(chunks)


def test_parquet_save_and_load(tmp_path):
    df = pd.DataFrame(
        {
            "code": ["def add(a, b): return a + b"],
            "label": [1],
        }
    )

    output_path = tmp_path / "test_output.parquet"

    df.to_parquet(output_path, index=False)
    loaded_df = pd.read_parquet(output_path)

    pd.testing.assert_frame_equal(df, loaded_df)
