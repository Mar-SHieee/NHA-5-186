# Long-Function Strategy Report (W1-P3-03)

## 1. Measured Token Length Distribution
We analyzed the token lengths of functions across our datasets using the CodeBERT tokenizer (`microsoft/codebert-base`, max limit = 512 tokens).

* **Total Functions Analyzed:**
* **Functions Exceeding 512 Tokens:**
* **Measured Percentage:**
---

## 2. Evaluation of Strategies (The 3 Options)

We evaluated three main strategies to handle functions exceeding the 512-token limit:

1. **Truncation (Head Only):**
   * *Description:* Keeps the first 512 tokens and drops the rest.
   * *Best Use Case:* When functions are mostly short, and core definitions/structures reside at the very beginning. Chosen as our primary baseline for V1 due to high speed and efficiency.

2. **Head + Tail:**
   * *Description:* Keeps a mix of tokens from both the beginning and the end of the function.
   * *Best Use Case:* When important logic or variables might appear at both ends of a long function block.

3. **Sliding Window:**
   * *Description:* Splits the function into overlapping chunks of 512 tokens.
   * *Best Use Case:* When maximum accuracy is required without losing any code context, though it introduces high computational overhead.
