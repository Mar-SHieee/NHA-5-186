import hashlib
import os

import torch
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
        missing_texts = []
        missing_indices = []

        for index, text in enumerate(code_snippets):
            if not isinstance(text, str) or not text.strip():
                continue

            cache_path = os.path.join(
                self.cache_dir,
                f"{self.get_hash(text)}.pt",
            )

            if os.path.exists(cache_path):
                results[index] = torch.load(
                    cache_path,
                    map_location="cpu",
                    weights_only=True,
                )
            else:
                missing_texts.append(text)
                missing_indices.append(index)

        for start in range(0, len(missing_texts), batch_size):
            batch_texts = missing_texts[start : start + batch_size]
            batch_indices = missing_indices[start : start + batch_size]

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

            for index, text, embedding in zip(
                batch_indices,
                batch_texts,
                batch_embeddings,
                strict=True,
            ):
                cache_path = os.path.join(
                    self.cache_dir,
                    f"{self.get_hash(text)}.pt",
                )

                torch.save(embedding, cache_path)
                results[index] = embedding

        return results
