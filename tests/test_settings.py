import json
import os

import pytest

from gfglock.utils import settings as settings_mod


class TestGetSettingsFile:
    """get_settings_file must resolve to the frozen-app data directory and create it."""

    def test_frozen_uses_appdata(self, monkeypatch, tmp_path):
        """When frozen, settings.json must live under <APPDATA>/gfgLock/."""
        monkeypatch.setattr(settings_mod.sys, "frozen", True, raising=False)
        monkeypatch.setenv("APPDATA", str(tmp_path))
        result = settings_mod.get_settings_file()
        assert result == os.path.join(str(tmp_path), "gfgLock", "settings.json")
        assert os.path.isdir(os.path.dirname(result))

    def test_frozen_without_appdata_falls_back_to_home(self, monkeypatch, tmp_path):
        """Missing APPDATA must fall back to the user home directory."""
        monkeypatch.setattr(settings_mod.sys, "frozen", True, raising=False)
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setattr(settings_mod.os.path, "expanduser", lambda _p: str(tmp_path))
        result = settings_mod.get_settings_file()
        assert result == os.path.join(str(tmp_path), "gfgLock", "settings.json")


class TestGetDefaultSettings:
    """get_default_settings must expose the full default settings tree."""

    def test_top_level_keys_present(self):
        """All expected top-level setting groups must be present."""
        defaults = settings_mod.get_default_settings()
        assert set(defaults.keys()) == {"theme", "appearance", "encryption", "decryption", "advanced"}

    def test_known_default_values(self):
        """A few representative default values must match the documented defaults."""
        defaults = settings_mod.get_default_settings()
        assert defaults["advanced"]["encryption_mode"] == "aes256_gcm"
        assert defaults["advanced"]["enable_logs"] is False
        assert defaults["theme"] == "system"


class TestLoadSettings:
    """load_settings must merge on-disk overrides onto the built-in defaults."""

    def test_missing_file_returns_defaults(self, monkeypatch, tmp_path):
        """No settings.json on disk must yield the plain defaults."""
        target = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        assert settings_mod.load_settings() == settings_mod.get_default_settings()

    def test_merges_partial_overrides(self, monkeypatch, tmp_path):
        """User overrides must layer onto defaults without dropping untouched keys."""
        target = tmp_path / "settings.json"
        target.write_text(json.dumps({"theme": "dark", "advanced": {"log_level": "all"}}), encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        result = settings_mod.load_settings()
        assert result["theme"] == "dark"
        assert result["advanced"]["log_level"] == "all"
        assert result["advanced"]["encryption_mode"] == "aes256_gcm"
        assert result["encryption"] == settings_mod.get_default_settings()["encryption"]

    def test_corrupt_json_falls_back_to_defaults(self, monkeypatch, tmp_path):
        """Invalid JSON on disk must not raise; it must fall back to defaults."""
        target = tmp_path / "settings.json"
        target.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        assert settings_mod.load_settings() == settings_mod.get_default_settings()

    def test_non_dict_json_falls_back_to_defaults(self, monkeypatch, tmp_path):
        """A JSON array instead of an object must fall back to defaults, not crash."""
        target = tmp_path / "settings.json"
        target.write_text("[1, 2, 3]", encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        assert settings_mod.load_settings() == settings_mod.get_default_settings()


class TestSaveSettings:
    """save_settings must persist a settings dict to disk as JSON."""

    def test_writes_json_and_returns_true(self, monkeypatch, tmp_path):
        """A successful save must write valid JSON matching the input dict."""
        target = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        assert settings_mod.save_settings({"theme": "light"}) is True
        with open(target, "r", encoding="utf-8") as f:
            assert json.load(f) == {"theme": "light"}

    def test_returns_false_on_write_failure(self, monkeypatch, tmp_path):
        """An unwritable path must return False instead of raising."""
        bad_path = str(tmp_path / "missing_dir" / "settings.json")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: bad_path)
        assert settings_mod.save_settings({"theme": "light"}) is False

    def test_save_then_load_roundtrip(self, monkeypatch, tmp_path):
        """Settings saved to disk must be recovered unchanged by load_settings."""
        target = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        custom = settings_mod.get_default_settings()
        custom["theme"] = "dark"
        custom["advanced"]["enable_logs"] = True
        assert settings_mod.save_settings(custom) is True
        assert settings_mod.load_settings() == custom


class TestMergeSettings:
    """merge_settings must deep-merge overrides onto defaults without mutating inputs."""

    def test_overrides_scalar_value(self):
        """A scalar override must replace the default value for that key."""
        assert settings_mod.merge_settings({"a": 1, "b": 2}, {"a": 5}) == {"a": 5, "b": 2}

    def test_recurses_into_nested_dicts(self):
        """Nested dict overrides must merge key-by-key, not replace wholesale."""
        result = settings_mod.merge_settings({"a": {"x": 1, "y": 2}}, {"a": {"x": 9}})
        assert result == {"a": {"x": 9, "y": 2}}

    def test_adds_new_keys_from_overrides(self):
        """Keys present only in the overrides must be added to the result."""
        assert settings_mod.merge_settings({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_non_dict_override_replaces_dict_default(self):
        """If the override is not a dict, it must replace the default outright."""
        assert settings_mod.merge_settings({"a": {"x": 1}}, {"a": 5}) == {"a": 5}

    def test_does_not_mutate_inputs(self):
        """Neither the defaults dict nor the overrides dict may be modified in place."""
        defaults = {"a": {"x": 1, "y": 2}}
        overrides = {"a": {"x": 9}}
        settings_mod.merge_settings(defaults, overrides)
        assert defaults == {"a": {"x": 1, "y": 2}}
        assert overrides == {"a": {"x": 9}}
