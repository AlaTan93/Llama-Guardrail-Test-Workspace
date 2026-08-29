from src.run_meta import read_meta, update_meta


def test_read_meta_missing_returns_defaults(tmp_path):
    meta = read_meta(tmp_path)
    assert meta["tier"] == ""
    assert meta["status"] == "new"


def test_update_meta_roundtrip(tmp_path):
    update_meta(tmp_path, tier="Q4_K_M", dataset_size=10)
    meta = read_meta(tmp_path)
    assert meta["tier"] == "Q4_K_M"
    assert meta["dataset_size"] == 10
    assert meta["created_at"] != ""
    assert meta["updated_at"] != ""

    update_meta(tmp_path, notes="hello", bogus="ignored")
    meta = read_meta(tmp_path)
    assert meta["notes"] == "hello"
    assert "bogus" not in meta
    assert meta["dataset_size"] == 10


def test_victim_block_roundtrip(tmp_path):
    victim = {
        "model": "meta-llama/Llama-3.1-8B-Instruct",
        "tier": "Q6_K",
        "gguf": "m.gguf",
        "gguf_size_mb": 6.6,
        "gguf_sha256": "cd" * 32,
        "litellm_model": "victim-llama",
    }
    update_meta(tmp_path, victim=victim)
    meta = read_meta(tmp_path)
    assert meta["victim"] == victim

    # partial victim blocks survive (older runs)
    update_meta(tmp_path, victim={"litellm_model": "victim-llama"})
    assert read_meta(tmp_path)["victim"] == {"litellm_model": "victim-llama"}


def test_read_meta_survives_corrupt_file(tmp_path):
    (tmp_path / "meta.json").write_text("{not json", encoding="utf-8")
    assert read_meta(tmp_path)["status"] == "new"
