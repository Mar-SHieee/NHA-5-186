import hashlib
import os

import torch
from transformers import AutoModel, AutoTokenizer


class CodeBERTEmbedder:
    def __init__(self, model_name="microsoft/codebert-base", cache_dir="./data/cache"):
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

    def get_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_embedding(self, code_snippet: str):
        code_hash = self.get_hash(code_snippet)
        cache_path = os.path.join(self.cache_dir, f"{code_hash}.pt")

        if os.path.exists(cache_path):
            return torch.load(cache_path)

        inputs = self.tokenizer(
            code_snippet, return_tensors="pt", padding=True, truncation=True, max_length=512
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            embedding = outputs.last_hidden_state.mean(dim=1).squeeze().cpu()

        torch.save(embedding, cache_path)
        return embedding


# Code
#   ↓
# Hash
#   ↓
# Check Cache
#   ↓
# If exists → Load Embedding
#   ↓
# If not exists
#   ↓
# Tokenizer
#   ↓
# CodeBERT
#   ↓
# Mean Pooling
#   ↓
# Embedding
#   ↓
# Save in Cache
#   ↓
# Return Embedding
