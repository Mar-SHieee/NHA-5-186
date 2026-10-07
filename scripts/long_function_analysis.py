import os

import pandas as pd
from transformers import RobertaTokenizer

# 1. Load the CodeBERT tokenizer
tokenizer = RobertaTokenizer.from_pretrained("microsoft/codebert-base")


# 2. Function to count the number of Tokens for each code snippet
def count_tokens(code_snippet):
    if not isinstance(code_snippet, str):
        return 0
    tokens = tokenizer.encode(code_snippet, add_special_tokens=True, truncation=False)
    return len(tokens)


# 3. Function to apply the chosen strategy (Truncation Policy for long functions)
def apply_truncation_policy(code_snippet, max_tokens=512):
    tokens = tokenizer.encode(code_snippet, add_special_tokens=True, truncation=False)
    if len(tokens) > max_tokens:
        # Truncate excess tokens and decode back to text
        tokens = tokens[:max_tokens]
        truncated_code = tokenizer.decode(tokens, skip_special_tokens=True)
        return truncated_code, True  # Truncated
    return code_snippet, False  # Within limit


data_path = "data/interim/megavul.parquet"  # <-----------------------------------------------

if os.path.exists(data_path):
    print(f"Loading dataset from {data_path}...")
    df = pd.read_parquet(data_path)

    print("Calculating token lengths for dataset...")
    df["token_count"] = df["code"].apply(count_tokens)

    total_functions = len(df)
    long_functions = len(df[df["token_count"] > 512])
    percentage = (long_functions / total_functions) * 100

    print("\n--- Actual Dataset Results ---")
    print(f"Total functions: {total_functions}")
    print(f"Functions larger than 512 tokens: {long_functions}")
    print(f"Percentage: {percentage:.2f}%")

    # Apply strategy on the dataset
    print("Applying truncation policy to dataset...")
    df["processed_code"], df["was_truncated"] = zip(
        *df["code"].apply(apply_truncation_policy), strict=False
    )
    print(f"Total truncated functions handled: {df['was_truncated'].sum()}")
else:
    # Temporary test sample
    data = {
        "code": [
            "print('hello world')",
            "def foo():\n    return 1",
            "x = 1\n" * 600,
        ]
    }
    df = pd.DataFrame(data)
    df["token_count"] = df["code"].apply(count_tokens)

    # Test strategy on sample
    df["processed_code"], df["was_truncated"] = zip(
        *df["code"].apply(apply_truncation_policy), strict=False
    )
    df["processed_token_count"] = df["processed_code"].apply(count_tokens)
    print(df[["token_count", "was_truncated", "processed_token_count"]])
    print(f"Test percentage: {(len(df[df['token_count'] > 512]) / len(df)) * 100:.2f}%")
