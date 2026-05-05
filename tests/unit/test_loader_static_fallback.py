import json

from utils import loader


def test_loader_uses_static_fallback_when_runtime_data_mount_hides_roster(tmp_path, monkeypatch):
    runtime_data = tmp_path / "data"
    static_data = tmp_path / "static_data"
    runtime_data.mkdir()
    static_data.mkdir()
    (static_data / "gods.json").write_text(json.dumps({"all": ["Ymir"], "pools": {}}), encoding="utf-8")

    monkeypatch.setattr(loader, "DATA_DIR", runtime_data)
    monkeypatch.setattr(loader, "STATIC_DATA_DIR", static_data)
    loader.reload()

    assert loader.gods() == {"all": ["Ymir"], "pools": {}}

    loader.reload()
