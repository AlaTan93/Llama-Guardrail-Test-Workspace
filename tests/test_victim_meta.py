import hashlib

from src.victim_meta import build_victim_block, sha256_cached


def test_build_victim_block(tmp_path, monkeypatch):
    # isolate the hash cache per test
    monkeypatch.setattr("src.victim_meta.CACHE_PATH", tmp_path / "hashes.json")
    gguf = tmp_path / "model-TEST.gguf"
    gguf.write_bytes(b"0123456789" * 100)

    block = build_victim_block("Q4_K_M", gguf, "meta-llama/Llama-3.1-8B-Instruct",
                               litellm_model="victim-llama")
    assert block["model"] == "meta-llama/Llama-3.1-8B-Instruct"
    assert block["tier"] == "Q4_K_M"
    assert block["gguf"] == "model-TEST.gguf"
    assert block["gguf_size_mb"] == 0.0  # 1000 bytes
    assert block["gguf_sha256"] == hashlib.sha256(b"0123456789" * 100).hexdigest()
    assert block["litellm_model"] == "victim-llama"


def test_hash_cached_and_invalidated(tmp_path, monkeypatch):
    monkeypatch.setattr("src.victim_meta.CACHE_PATH", tmp_path / "hashes.json")
    gguf = tmp_path / "m.gguf"
    gguf.write_bytes(b"first")

    h1 = sha256_cached(gguf)
    assert h1 == hashlib.sha256(b"first").hexdigest()

    # cache file written and second call hits it (same digest)
    import json

    cache = json.loads((tmp_path / "hashes.json").read_text())
    assert list(cache.values())[0]["sha256"] == h1
    assert sha256_cached(gguf) == h1

    # content change -> different mtime/size -> recompute
    gguf.write_bytes(b"second version")
    h2 = sha256_cached(gguf)
    assert h2 == hashlib.sha256(b"second version").hexdigest()
    assert h2 != h1


def test_build_block_without_hash(tmp_path, monkeypatch):
    monkeypatch.setattr("src.victim_meta.CACHE_PATH", tmp_path / "hashes.json")
    gguf = tmp_path / "m.gguf"
    gguf.write_bytes(b"x")
    block = build_victim_block("BF16", gguf, "m", with_hash=False)
    assert block["gguf_sha256"] == ""
    assert not (tmp_path / "hashes.json").exists()
