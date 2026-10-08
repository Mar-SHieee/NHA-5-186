import time

from shield_core.models.embedding.embedder import CodeBERTEmbedder


def test_embedder_cache():
    embedder = CodeBERTEmbedder()

    sample_code = """
    def secure_login(username, password):
        if not username or not password:
            return False
        return check_credentials(username, password)
    """

    start_time = time.time()
    emb1 = embedder.get_embedding(sample_code)
    time_first = time.time() - start_time

    start_time = time.time()
    emb2 = embedder.get_embedding(sample_code)
    time_second = time.time() - start_time

    print(f"First run time (Computing): {time_first:.4f} seconds")
    print(f"Second run time (From Cache): {time_second:.4f} seconds")

    assert (emb1 == emb2).all()
