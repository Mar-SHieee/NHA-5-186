from transformers import AutoTokenizer

DEFAULT_MODEL = "microsoft/codebert-base"
DEFAULT_MAX_TOKENS = 512
DEFAULT_STRIDE = 256

tokenizer = AutoTokenizer.from_pretrained(DEFAULT_MODEL)


def count_tokens(code_snippet: str) -> int:
    if not isinstance(code_snippet, str):
        return 0

    tokens = tokenizer.encode(
        code_snippet,
        add_special_tokens=True,
        truncation=False,
    )

    return len(tokens)


def apply_truncation_policy(
    code_snippet: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    stride: int = DEFAULT_STRIDE,
) -> tuple[list[str], bool]:
    if not isinstance(code_snippet, str):
        return [], False

    special_tokens_count = tokenizer.num_special_tokens_to_add(pair=False)
    content_limit = max_tokens - special_tokens_count

    tokens = tokenizer.encode(
        code_snippet,
        add_special_tokens=False,
        truncation=False,
    )

    if len(tokens) + special_tokens_count <= max_tokens:
        return [code_snippet], False

    chunks = []

    for start in range(0, len(tokens), stride):
        chunk_tokens = tokens[start : start + content_limit]

        if not chunk_tokens:
            break

        chunk = tokenizer.decode(
            chunk_tokens,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )

        chunks.append(chunk)

        if start + content_limit >= len(tokens):
            break

    return chunks, True
