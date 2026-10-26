"""Sliding-window splitting for functions longer than CodeBERT's 512-token limit.

Every tunable setting is a module-level default AND a keyword argument, so you can
change the default here or override it per call:

    apply_truncation_policy(code)                                  # use the defaults
    apply_truncation_policy(code, overlap=128, max_windows=12)     # override per call
    apply_truncation_policy(code, max_windows=None)                # no cap at all

Settings
--------
model_name   tokenizer to use (must match the embedding model)
max_tokens   model input limit including <s> and </s> (512 for CodeBERT)
overlap      tokens shared between neighbouring windows (0 = no overlap)
max_windows  cap on windows per function; None = no cap
overflow     what to do when a function needs more than max_windows:
               "head_tail" keep the start and the end, drop the middle
               "head"      keep only the start
               "tail"      keep only the end
head_ratio   for "head_tail": share of the budget given to the head (0.5 = half/half)
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Literal

from transformers import AutoTokenizer

# ----------------------------------------------------------------------- defaults
# Edit these to change the default behaviour everywhere.

DEFAULT_MODEL = "microsoft/codebert-base"
DEFAULT_MAX_TOKENS = 512
DEFAULT_OVERLAP = 64
DEFAULT_MAX_WINDOWS: int | None = None
DEFAULT_OVERFLOW = "head_tail"
DEFAULT_HEAD_RATIO = 0.5

OverflowMode = Literal["head_tail", "head", "tail"]


# ----------------------------------------------------------------------- helpers


@lru_cache(maxsize=4)
def get_tokenizer(model_name: str = DEFAULT_MODEL):
    """Load a tokenizer once per model name."""
    return AutoTokenizer.from_pretrained(model_name)


def content_limit(max_tokens: int = DEFAULT_MAX_TOKENS, model_name: str = DEFAULT_MODEL) -> int:
    """Real tokens that fit in one window (max_tokens minus <s> and </s>)."""
    tok = get_tokenizer(model_name)
    return max_tokens - tok.num_special_tokens_to_add(pair=False)


def _check_settings(
    limit: int,
    overlap: int,
    max_windows: int | None,
    overflow: str,
    head_ratio: float,
) -> int:
    """Validate the settings and return the stride (step between window starts)."""
    if limit <= 0:
        raise ValueError(f"max_tokens leaves no room for content (content limit = {limit}).")
    if overlap < 0 or overlap >= limit:
        raise ValueError(f"overlap must be between 0 and {limit - 1}, got {overlap}.")
    if max_windows is not None and max_windows < 1:
        raise ValueError("max_windows must be at least 1, or None for no cap.")
    if overflow not in ("head_tail", "head", "tail"):
        raise ValueError("overflow must be 'head_tail', 'head' or 'tail'.")
    if not 0.0 <= head_ratio <= 1.0:
        raise ValueError("head_ratio must be between 0 and 1.")
    return limit - overlap


def window_budget(
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap: int = DEFAULT_OVERLAP,
    max_windows: int | None = DEFAULT_MAX_WINDOWS,
    model_name: str = DEFAULT_MODEL,
) -> float:
    """Most real tokens a function can have before the overflow rule kicks in."""
    if max_windows is None:
        return math.inf
    limit = content_limit(max_tokens, model_name)
    stride = _check_settings(limit, overlap, max_windows, DEFAULT_OVERFLOW, DEFAULT_HEAD_RATIO)
    return limit + (max_windows - 1) * stride


def windows_needed(
    n_tokens: int,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap: int = DEFAULT_OVERLAP,
    max_windows: int | None = DEFAULT_MAX_WINDOWS,
    model_name: str = DEFAULT_MODEL,
) -> int:
    """How many windows a function of n_tokens real tokens produces (no tokenizing).

    Use it on the saved token-length files to estimate cost before a full run.
    Note: saved counts include <s> and </s>, so pass n_tokens - 2.
    """
    limit = content_limit(max_tokens, model_name)
    stride = _check_settings(limit, overlap, max_windows, DEFAULT_OVERFLOW, DEFAULT_HEAD_RATIO)
    if n_tokens <= limit:
        return 1
    needed = math.ceil((n_tokens - limit) / stride) + 1
    return needed if max_windows is None else min(needed, max_windows)


# ----------------------------------------------------------------------- main API


def count_tokens(code_snippet: str, model_name: str = DEFAULT_MODEL) -> int:
    """Token count including <s> and </s>, no truncation."""
    if not isinstance(code_snippet, str):
        return 0

    tok = get_tokenizer(model_name)
    return len(tok.encode(code_snippet, add_special_tokens=True, truncation=False))


def apply_truncation_policy(
    code_snippet: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap: int = DEFAULT_OVERLAP,
    max_windows: int | None = DEFAULT_MAX_WINDOWS,
    overflow: OverflowMode = DEFAULT_OVERFLOW,
    head_ratio: float = DEFAULT_HEAD_RATIO,
    model_name: str = DEFAULT_MODEL,
) -> tuple[list[str], bool]:
    """Split one function into windows of text.

    Returns (chunks, was_split). A function that already fits in one window comes back
    unchanged as a single chunk with was_split = False.
    """
    if not isinstance(code_snippet, str):
        return [], False

    tok = get_tokenizer(model_name)
    limit = content_limit(max_tokens, model_name)
    stride = _check_settings(limit, overlap, max_windows, overflow, head_ratio)

    tokens = tok.encode(code_snippet, add_special_tokens=False, truncation=False)

    if len(tokens) <= limit:
        return [code_snippet], False

    # Overflow rule: only when a cap exists and the function is longer than it covers.
    if max_windows is not None:
        budget = limit + (max_windows - 1) * stride
        if len(tokens) > budget:
            if overflow == "head":
                tokens = tokens[:budget]
            elif overflow == "tail":
                tokens = tokens[-budget:]
            else:  # head_tail
                head = int(budget * head_ratio)
                tail = budget - head
                tokens = tokens[:head] + (tokens[-tail:] if tail > 0 else [])

    chunks: list[str] = []
    for start in range(0, len(tokens), stride):
        chunk_tokens = tokens[start : start + limit]
        if not chunk_tokens:
            break

        chunks.append(
            tok.decode(
                chunk_tokens,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        )

        if start + limit >= len(tokens):
            break

    return chunks, True


# ----------------------------------------------------------------------- quick check

if __name__ == "__main__":
    sample = "int x = 0;\n" * 3000  # long synthetic function
    for ov, cap in [(64, 8), (64, 32), (128, 12), (64, None)]:
        chunks, split = apply_truncation_policy(sample, overlap=ov, max_windows=cap)
        print(f"overlap={ov:<3} max_windows={cap!s:<5} -> {len(chunks)} chunks, split={split}")
