# Long-Function Policy for CodeBERT (W1-P3-03, Step 23)

CodeBERT accepts at most 512 tokens per input, including the `<s>` and `</s>` special tokens. This note records how many functions exceed that limit in our datasets and the policy we use for them.

All distribution numbers come from the **deduplicated** datasets, tokenized with the `microsoft/codebert-base` tokenizer (special tokens included, no truncation).

## 1. Measurements

### Length distribution (tokens)

| Dataset | Language | Rows | Over 512 | Median | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|
| Big-Vul (deduped) | C/C++ | 103,345 | 18.7% | 159 | 920 | 1,671 | 4,647 |
| MegaVul (deduped) | C/C++ | 336,803 | 21.7% | 206 | 888 | 1,258 | 2,494 |
| CVEfixes C/C++ (deduped) | C/C++ | 2,628 | 54.3% | 588 | 2,778 | 5,071 | 21,450 |
| CVEfixes Python (deduped) | Python | 4,486 | 36.1% | 356 | 1,596 | 2,636 | 8,092 |

### Share of functions that fit within N tokens

| Dataset | <= 512 | <= 1024 | <= 2048 | <= 4096 | <= 8192 | Vulnerable only, <= 2048 | Vulnerable only, <= 4096 |
|---|---|---|---|---|---|---|---|
| Big-Vul (deduped) | 81.3% | 91.1% | 96.3% | 98.8% | 99.6% | 88.4% | 94.3% |
| MegaVul (deduped) | 78.3% | 92.3% | 98.5% | 99.5% | 99.9% | 78.6% | 90.6% |
| CVEfixes Python (deduped) | 63.9% | 82.4% | 92.3% | 97.4% | 99.0% | 93.0% | 97.6% |
| CVEfixes C/C++ (deduped) | 45.7% | 68.3% | 84.6% | 93.8% | 97.0% | 86.7% | 94.3% |

### Overflow rate by label

| Dataset | Clean over 512 | Vulnerable over 512 |
|---|---|---|
| MegaVul (deduped) | 19.7% | 60.1% |
| Big-Vul (deduped) | 17.3% | 41.5% |
| CVEfixes C/C++ (deduped) | 58.1% | 48.9% |
| CVEfixes Python (deduped) | 39.0% | 33.9% |

## 2. Findings

1. **Truncation is not acceptable.** 19-22% of C/C++ functions in Big-Vul and MegaVul and 36% of Python functions exceed 512 tokens. Plain truncation keeps only the start of the function, and the vulnerable line can be anywhere.
2. **Truncation would hurt the vulnerable class most in C/C++.** In MegaVul, 60% of vulnerable functions overflow vs 20% of clean ones. In Big-Vul it is 42% vs 17%.
3. **Length is correlated with the label in MegaVul and Big-Vul.** A model can score well by learning that long functions are vulnerable. V2 adds length and complexity features, so it is the most exposed. CVEfixes shows the opposite direction or no effect. The evaluation must include a length-only baseline (section 6).
4. **The tail is heavy.** Maximum lengths reach 40,000 to 160,000 tokens, so a hard cap is needed.
5. **Dedupe barely changes the percentages** (Python: 35.9% before, 36.1% after) but removes many rows (Big-Vul about 52%, CVEfixes C/C++ about 83%).

## 3. Policy

For any function longer than one window:

1. Tokenize the full function without special tokens.
2. Split it into **sliding windows of 510 tokens with 64 tokens of overlap** (step of 446 tokens), then let the embedder add `<s>` and `</s>`, so each window is at most 512 tokens.
3. Embed every window with frozen CodeBERT (masked mean pooling inside each window).
4. **Mean-pool the window embeddings** into one 768-dimensional vector per function. Max-pooling is tested as an ablation.
5. **No cap on the number of windows** (`max_windows = None`): a function gets as many windows as it needs. GPU memory does not limit this, because windows are embedded in batches of fixed size, so peak VRAM depends on the batch size and not on how many windows a function has. The batch size is the VRAM control: it is lowered automatically if the GPU runs out of memory (section 3, "Memory control"). A cap can still be set (`--max-windows N`); when it is, the overflow rule applies (keep the head and tail, drop the middle).
6. A function that fits in one window is embedded unchanged, exactly as before.

**Why not the alternatives**

| Option | Verdict |
|---|---|
| Truncate to the first 512 tokens | Rejected: discards the vulnerable part too often (findings 1 and 2). |
| Head + tail only (256 + 254) | Cheap. Kept as a baseline for the ablation. |
| Sliding window + pooling (chosen) | Covers the whole function up to the cap. Extra cost applies only to the 20-35% of functions that overflow. |

**Why no cap.** A cap only matters for a small share of functions: those above 8,192 tokens are at most 0.4% (Big-Vul), 0.1% (MegaVul), 1.0% (CVEfixes Python) and 3.0% (CVEfixes C/C++). Without a cap, none of the function is dropped. The price is time and cache size, not memory: the longest functions (up to 160,000 tokens) produce hundreds of windows each, so a handful of functions add a noticeable number of chunks. Mean pooling over that many windows also dilutes the signal of the one window that holds the vulnerable code, which the max-pooling ablation checks (section 6).

**Memory control.** Peak VRAM was 0.40 GB at batch size 16 and 1.50 GB at batch size 128, so the 8 GB limit leaves a lot of room. The embedding call retries with half the batch size if CUDA runs out of memory, and the batch size is set with `--batch-size`. Chunk embeddings are 768 float32 values each (about 3 KB), so 500,000 chunks need about 1.5 GB of system RAM while pooling.

**Where the settings live.** All settings (`max_tokens`, `overlap`, `max_windows` (default `None`, no cap), `overflow`, `head_ratio`, `model_name`) are defaults and keyword arguments in `scripts/embeddings/long_function_analysis.py`, and command-line flags in `long_embedding.py` (`--overlap`, `--max-windows`, `--no-cap`). Changing a setting does not need a code change.

## 4. Measured cost

Run on the first 5,000 rows of deduped MegaVul (not a random sample; the file appears to be ordered, and 25.4% of these rows overflow vs 21.7% overall):

- 1,271 functions (25.4%) were split; total 7,360 chunks for 5,000 functions, an average of **1.47 chunks per function**.
- Median 1 chunk, 75th percentile 2, maximum 36 (that run used a cap of 128, which none of the 5,000 functions reached; the first 5,000 rows are not a random sample, so longer functions elsewhere will produce more chunks).
- No NaN values, and every row received an embedding.

Extrapolating the average to full MegaVul gives about 500,000 chunks, roughly 1.5 times the work of plain truncation.

Throughput and peak VRAM (Step 7), measured on an NVIDIA GeForce RTX 4060 Laptop GPU (8 GB), fp16, 512-token windows, overlap 64, no cap, each run on the same 7,360 chunks with an empty cache folder:

| Batch size | Embedding time | Throughput | Peak VRAM allocated (PyTorch) | Memory in `nvidia-smi` |
|---|---|---|---|---|
| 16 | 56.1 s | **131.3 chunks/s** | 0.40 GB | about 0.6 GB |
| 128 | 66.8 s | 110.2 chunks/s | 1.50 GB | about 2.1 GB |

Findings:

- **A larger batch was slower, not faster.** A likely reason is padding: chunks are not sorted by length, so each batch is padded to its longest chunk, and a bigger batch wastes more work on short ones (not verified separately).
- Both batch sizes use a small part of the 8 GB per-GPU ceiling, so VRAM is not a constraint on this card.
- Extrapolation: full deduped MegaVul (about 500,000 chunks, somewhat more with no cap) takes roughly 1 hour at batch size 16 and roughly 75 minutes at batch size 128. Big-Vul and the CVEfixes sets take less.

**Settings saved for the full runs:** `batch_size = 16` (fastest measured), `overlap = 64`, `max_windows = None` (no cap), `max_tokens = 512`, fp16.

These values are tunable and should be adjusted to the GPU being used:

- `batch_size` is the memory control. Lower it on a smaller card, and test larger values on a bigger one, because a larger batch is not automatically faster (see the table). If CUDA runs out of memory the run retries with half the batch size automatically.
- `overlap` and `max_windows` trade coverage and quality against time and cache size. They do not change VRAM use. They are set with `--overlap` and `--max-windows` / `--no-cap`, or by editing the defaults in `long_function_analysis.py` and `long_embedding.py`.
- Embedding speed depends on the GPU. The numbers above are for the RTX 4060 Laptop GPU and will differ on other machines. Compare runs on the same GPU only, and always use an empty `--cache-dir` when timing, because cached chunks are read from disk and skip the model.
- Possible speed-up, not yet tested: sort chunks by length before batching so that each batch holds chunks of similar size. This reduces padding and may make larger batches worthwhile.

## 5. Impact on other components

- **Cache:** chunks are cached by the hash of the chunk text, so a change of overlap or cap produces different chunks and therefore different cache keys. Embeddings from the old truncating pipeline are not reused for windows that differ from the old input.
- **V1/V2:** use the pooled function embedding (`<dataset>_embeddings.npy`, row-aligned with `<dataset>_processed.parquet`).
- **V3 (GNN):** unaffected by the 512 limit. Node code text from the CPG is short, so each node fits in one window.

## 6. Evaluation requirements that follow from this

- Report a **length-only baseline** (XGBoost on token count alone). V1 and V2 count as real gains only if they clearly beat it.
- Report metrics separately for **short (<= 512 tokens) and long (> 512 tokens) functions**.
- Run the **head+tail vs sliding window** ablation on at least one language.
- Run the **overlap 64 vs larger overlap (for example 254)** comparison on a sample, and keep 64 unless the larger overlap clearly wins.
- Compare **mean vs max pooling** of window embeddings.

## 7. Limitations

- CVEfixes Python (4,486 rows) and CVEfixes C/C++ (2,628 rows) are small, so their percentages are less stable than the Big-Vul and MegaVul ones.
- CVEfixes C/C++ is much longer than Big-Vul and MegaVul (median 588 vs 159-206). Confirm that its rows are function-level and not file-level or multi-function chunks.
- Distribution numbers are for the current deduplicated files and will change if dedupe or merge rules change.
- With no cap, the cost of the longest functions is high and their pooled vector is an average over hundreds of windows, which can hide a single vulnerable window. If this shows up in the long-function metrics, set a cap (for example 32 windows, about 14,300 tokens) and compare.
- Windows are decoded to text and re-tokenized by the embedder. A test checks that each chunk stays within 512 tokens after this round trip.
- Mean pooling can dilute the signal of the one window that contains the vulnerable code. This is why the max-pooling ablation is required.

## 8. Reproduce

```
python scripts/embeddings/token_length_stats.py      # section 1 tables
python -m scripts.embeddings.long_embedding --limit 200
pytest tests/embeddings/test_long_embedding.py -v
```
