import json

import pytest
from fastapi.testclient import TestClient

from app.core import ui_store
from app.main import app


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_store, "PATH", tmp_path / "ui-store.json")
    return ui_store


def test_updates_preserve_other_preferences_and_migration_backup(store):
    store.update_values({"stemdeck.language": "pt"})
    store.update_values(
        {"stemdeck.folders": {"v": 2, "folders": [{"id": "trash", "items": ["song"]}]}}, backup=True
    )
    assert store.read_values()["stemdeck.language"] == "pt"
    assert store.read_values()["stemdeck.folders"]["folders"][0]["items"] == ["song"]
    assert json.loads(store.PATH.with_suffix(".before-migration.json").read_text()) == {
        "stemdeck.language": "pt"
    }


def test_only_app_preferences_can_be_shared(store):
    assert store.allowed("stemdeck:mix:abcdef123456")
    for key in ("cookie", "password", "stemdeck.api_key", "../../secrets", "stemdeck:mix:../bad"):
        with pytest.raises(ValueError):
            store.update_values({key: "secret"})
    assert not store.PATH.exists()


def test_ui_store_is_host_only_and_survives_separate_reads(store):
    remote = TestClient(app, client=("198.51.100.1", 50000))
    assert remote.get("/api/ui-store").status_code == 403
    local = TestClient(app, client=("127.0.0.1", 50000))
    assert (
        local.post("/api/ui-store", json={"values": {"stemdeck.language": "pt"}}).status_code == 200
    )
    assert local.get("/api/ui-store").json()["values"] == {"stemdeck.language": "pt"}
    assert local.post("/api/ui-store", json={"values": {"password": "secret"}}).status_code == 422
    assert local.get("/api/ui-store").json()["values"] == {"stemdeck.language": "pt"}


def test_setlists_and_per_playlist_mix_persist_without_replacing_song_mix(store):
    song_mix = {"bass": {"volume": 1, "muted": False}}
    playlist = {"version": 1, "selectedId": "p1", "playlists": [
        {"id": "p1", "name": "Baixo mudo", "metro": {"enabled": True, "countInBars": 2},
         "entries": [{"id": "song", "mix": {"bass": {"volume": 0.8, "muted": True}}}]}
    ]}
    store.update_values({"stemdeck:mix:song": song_mix})
    store.update_values({"stemdeck:setlist": playlist})
    saved = store.read_values()
    assert saved["stemdeck:setlist"] == playlist
    assert saved["stemdeck:mix:song"] == song_mix


def test_theme_preference_keeps_existing_mix_and_playlist(store):
    original = {"stemdeck:mix:demo": {"bass": {"pan": -.2}}, "stemdeck:setlist": {"playlists": ["keep"]}}
    store.update_values(original)
    for theme in ("light", "dark", "system"):
        store.update_values({"stemdeck.theme": theme})
        result = store.read_values()
        assert result["stemdeck.theme"] == theme
        assert all(result[key] == value for key, value in original.items())
