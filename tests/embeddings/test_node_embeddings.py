import torch

from shield_core.embeddings.node_embeddings import CPGNodeEmbedder


def test_cpg_node_embedder():
    # 1. Initialize the embedder
    embedder = CPGNodeEmbedder()

    # Sample code nodes for testing
    node1 = "x = a + b"
    node2 = "if x > 0: print(x)"

    # 2. Test single node embedding
    emb1 = embedder.embed_node(node1)
    assert emb1 is not None
    assert isinstance(emb1, torch.Tensor)
    assert emb1.ndim == 1  # Ensure it's a 1D vector

    # 3. Test caching (Cache Hit for node1)
    emb1_cached = embedder.embed_node(node1)
    assert torch.allclose(emb1, emb1_cached, atol=1e-6)

    # 4. Test another node to increase cache size
    embedder.embed_node(node2)

    # 5. Check cache statistics using your original method
    size, hit_rate = embedder.report_cache_stats()
    assert size == 2  # We stored exactly 2 unique nodes (node1 and node2)
    assert hit_rate > 0.0  # Hit rate should be greater than 0 because node1 was repeated
