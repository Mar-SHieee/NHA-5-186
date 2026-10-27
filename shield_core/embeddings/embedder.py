import hashlib
import os

import torch
from tqdm import tqdm  # Added tqdm
from transformers import AutoModel, AutoTokenizer


class CodeBERTEmbedder:
    def __init__(
        self,
        model_name="microsoft/codebert-base",
        cache_dir="./data/cache",
        max_tokens=512,
    ):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device}")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)

        if self.device.type == "cuda":
            self.model = self.model.half()

        self.model.to(self.device)
        self.model.eval()

        self.cache_dir = cache_dir
        # We can keep this so it doesn't break other scripts,
        # but we won't actually save individual files anymore.
        os.makedirs(self.cache_dir, exist_ok=True)

        self.max_tokens = max_tokens

    def get_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_embedding(self, code_snippet: str):
        embeddings = self.get_embeddings_batch([code_snippet])
        return embeddings[0]

    def get_embeddings_batch(
        self,
        code_snippets: list[str],
        batch_size: int = 16,
    ) -> list[torch.Tensor | None]:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")

        results = [None] * len(code_snippets)
        valid_texts = []
        valid_indices = []

        # 1. Filter out empty strings but skip the disk checking
        for index, text in enumerate(code_snippets):
            if not isinstance(text, str) or not text.strip():
                continue
            valid_texts.append(text)
            valid_indices.append(index)

        # 2. Batch process strictly in memory, wrapped with tqdm for progress tracking
        for start in tqdm(range(0, len(valid_texts), batch_size), desc="Embedding batches"):
            batch_texts = valid_texts[start : start + batch_size]
            batch_indices = valid_indices[start : start + batch_size]

            inputs = self.tokenizer(
                batch_texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self.max_tokens,
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)

                attention_mask = inputs["attention_mask"].unsqueeze(-1)
                attention_mask = attention_mask.to(outputs.last_hidden_state.dtype)

                token_embeddings = outputs.last_hidden_state * attention_mask
                summed_embeddings = token_embeddings.sum(dim=1)
                token_counts = attention_mask.sum(dim=1).clamp(min=1)

                batch_embeddings = (summed_embeddings / token_counts).float().cpu()

            # Store the result in memory (no disk saving here!)
            for i, idx in enumerate(batch_indices):
                results[idx] = batch_embeddings[i]

        return results
