"""ADR 0008 S2 — game home + world library (C9/I5b)."""

from app.core import world_library


class TestSagaHome:
    def test_env_override_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAGA_HOME", str(tmp_path / "custom"))
        assert world_library.saga_home() == tmp_path / "custom"

    def test_default_is_dot_saga_in_home(self, monkeypatch):
        monkeypatch.delenv("SAGA_HOME", raising=False)
        assert world_library.saga_home().name == ".saga"


class TestEnsureLibrary:
    def test_creates_lazily_and_seeds_example(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAGA_HOME", str(tmp_path))
        worlds = world_library.ensure_library()
        assert worlds == tmp_path / "worlds"
        assert (worlds / "the-awakening" / "world.yaml").is_file()

    def test_does_not_reseed_nonempty_library(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAGA_HOME", str(tmp_path))
        worlds = tmp_path / "worlds" / "my-world"
        worlds.mkdir(parents=True)
        (worlds / "world.yaml").write_text("meta: {name: Mine}\nkind: world\n")
        world_library.ensure_library()
        assert not (tmp_path / "worlds" / "the-awakening").exists()

    def test_git_repo_initialized_with_local_identity(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAGA_HOME", str(tmp_path))
        worlds = world_library.ensure_library()
        assert (worlds / ".git").is_dir()
        config = (worlds / ".git" / "config").read_text()
        assert "SAGA World Editor" in config


class TestListWorlds:
    def test_lists_meta_cards(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAGA_HOME", str(tmp_path))
        world_library.ensure_library()
        cards = world_library.list_worlds()
        assert cards[0]["slug"] == "the-awakening"
        assert cards[0]["name"] == "The Awakening"
        assert "tutorial" in cards[0]["tags"]

    def test_world_path_lookup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAGA_HOME", str(tmp_path))
        world_library.ensure_library()
        assert world_library.world_path("the-awakening") is not None
        assert world_library.world_path("atlantis") is None
