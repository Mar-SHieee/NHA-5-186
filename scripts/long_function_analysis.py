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


def apply_truncation_policy(code_snippet, max_tokens=512, stride=256):
    tokens = tokenizer.encode(code_snippet, add_special_tokens=True, truncation=False)

    # Function is already within the limit
    if len(tokens) <= max_tokens:
        return [code_snippet], False

    # Create overlapping chunks using a sliding window
    chunks = []

    for start in range(0, len(tokens), stride):
        chunk_tokens = tokens[start : start + max_tokens]

        # Stop if there are no more tokens
        if not chunk_tokens:
            break

        # Decode tokens back to code
        chunk = tokenizer.decode(chunk_tokens, skip_special_tokens=True)

        chunks.append(chunk)

        # Stop when the last chunk reaches the end
        if start + max_tokens >= len(tokens):
            break

    return chunks, True


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
    print("Applying Sliding Window policy to dataset...")

    df["processed_code"], df["was_truncated"] = zip(
        *df["code"].apply(apply_truncation_policy), strict=False
    )

    df["num_chunks"] = df["processed_code"].apply(len)

    print(f"Total long functions handled: {df['was_truncated'].sum()}")
else:
    # Temporary test sample
    long_code = """
    def process_user_data(users):
        results = []

        for user in users:
            user_id = user.get("id")
            username = user.get("username")
            email = user.get("email")
            age = user.get("age", 0)
            country = user.get("country", "unknown")
            is_active = user.get("is_active", False)

            if not user_id:
                continue

            if not username:
                username = "unknown_user"

            if not email:
                email = "no_email@example.com"

            if age < 18:
                category = "minor"
            elif age < 30:
                category = "young_adult"
            elif age < 50:
                category = "adult"
            else:
                category = "senior"

            if country == "Egypt":
                region = "Africa"
            elif country in ["France", "Germany", "Italy", "Spain"]:
                region = "Europe"
            elif country in ["USA", "Canada", "Mexico"]:
                region = "North America"
            elif country in ["Japan", "China", "India", "Korea"]:
                region = "Asia"
            else:
                region = "Other"

            account_status = "active" if is_active else "inactive"

            user_result = {
                "id": user_id,
                "username": username,
                "email": email,
                "age": age,
                "category": category,
                "country": country,
                "region": region,
                "status": account_status
            }

            if age >= 18 and is_active:
                user_result["eligible"] = True
            else:
                user_result["eligible"] = False

            results.append(user_result)

        return results
    """
    data = {
        "code": [
            "print('hello world')",
            "def foo():\n    return 1",
            long_code,
        ]
    }
    df = pd.DataFrame(data)
    df["token_count"] = df["code"].apply(count_tokens)

    # Test strategy on sample
    df["processed_code"], df["was_truncated"] = zip(
        *df["code"].apply(apply_truncation_policy), strict=False
    )

    df["num_chunks"] = df["processed_code"].apply(len)

    # print(df[["token_count", "was_truncated", "num_chunks"]])
    print(df.head())
    for i, chunk in enumerate(df.loc[2, "processed_code"], 1):
        print(f"\n--- Chunk {i} ---")
        print(chunk)
    print(f"Test percentage: {(len(df[df['token_count'] > 512]) / len(df)) * 100:.2f}%")
