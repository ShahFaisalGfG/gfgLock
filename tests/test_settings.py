import json
import os

import pytest

from gfglock.utils import settings as settings_mod


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """Each test starts without a cached file or a pending damaged-file report, and leaves none behind."""
    monkeypatch.setattr(settings_mod, "_cache", None)
    monkeypatch.setattr(settings_mod, "_read_error", False)


class TestGetSettingsFile:
    """settings.json lives in the app's data folder (see test_paths), or beside the module from source."""

    def test_built_app_uses_the_data_folder(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings_mod, "data_dir", lambda: str(tmp_path))
        assert settings_mod.get_settings_file() == os.path.join(str(tmp_path), "settings.json")

    def test_from_source_uses_the_module_folder(self, monkeypatch):
        monkeypatch.setattr(settings_mod, "data_dir", lambda: None)
        assert settings_mod.get_settings_file() == os.path.join(
            os.path.dirname(os.path.abspath(settings_mod.__file__)), "settings.json")


class TestGetDefaultSettings:
    """get_default_settings must expose the full default settings tree."""

    def test_top_level_keys_present(self):
        """All expected top-level setting groups must be present."""
        defaults = settings_mod.get_default_settings()
        assert set(defaults.keys()) == {"theme", "encryption", "decryption", "advanced"}

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

    def test_byte_order_mark_is_accepted(self, monkeypatch, tmp_path):
        """A file saved by an editor that writes a UTF-8 byte order mark still loads."""
        target = tmp_path / "settings.json"
        target.write_bytes(b"\xef\xbb\xbf" + json.dumps({"theme": "dark"}).encode("utf-8"))
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        assert settings_mod.load_settings()["theme"] == "dark"
        assert settings_mod.take_read_error() is False


class TestDamagedFile:
    """A damaged settings.json is parsed once, not on every load, and reported once."""

    @pytest.fixture
    def damaged(self, monkeypatch, tmp_path):
        target = tmp_path / "settings.json"
        target.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        return target

    def test_failure_is_cached_until_the_file_changes(self, damaged, monkeypatch):
        parsed: list[int] = []
        real_load = settings_mod.json.load
        monkeypatch.setattr(settings_mod.json, "load", lambda fh: parsed.append(1) or real_load(fh))
        for _ in range(3):
            assert settings_mod.load_settings() == settings_mod.get_default_settings()
        assert len(parsed) == 1
        damaged.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        assert settings_mod.load_settings()["theme"] == "dark"

    def test_reported_once(self, damaged):
        settings_mod.load_settings()
        settings_mod.load_settings()
        assert settings_mod.take_read_error() is True
        assert settings_mod.take_read_error() is False

    def test_a_good_or_missing_file_reports_nothing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(tmp_path / "settings.json"))
        settings_mod.load_settings()
        assert settings_mod.take_read_error() is False

    def test_a_locked_file_is_read_again_next_time(self, monkeypatch, tmp_path):
        """An open failure (another program holding the file a moment) is not cached as damage."""
        target = tmp_path / "settings.json"
        target.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        real_open = open
        attempts: list[int] = []

        def flaky_open(path, *args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise PermissionError(13, "The process cannot access the file")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", flaky_open)
        assert settings_mod.load_settings()["theme"] == "system"
        assert settings_mod.load_settings()["theme"] == "dark"
        assert settings_mod.take_read_error() is False


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

    def test_temp_file_reaches_the_disk_before_it_replaces_the_settings(self, monkeypatch, tmp_path):
        """fsync runs on the temp file before os.replace, so a power cut can't leave an empty file."""
        target = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        events: list[str] = []
        real_fsync, real_replace = os.fsync, os.replace
        monkeypatch.setattr(settings_mod.os, "fsync", lambda fd: events.append("fsync") or real_fsync(fd))
        monkeypatch.setattr(settings_mod.os, "replace", lambda a, b: events.append("replace") or real_replace(a, b))
        assert settings_mod.save_settings({"theme": "light"}) is True
        assert events == ["fsync", "replace"]

    def test_unserializable_settings_leave_the_file_and_no_temp(self, monkeypatch, tmp_path):
        target = tmp_path / "settings.json"
        target.write_text('{"theme": "dark"}', encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(target))
        assert settings_mod.save_settings({"theme": object()}) is False
        assert target.read_text(encoding="utf-8") == '{"theme": "dark"}'
        assert os.listdir(tmp_path) == ["settings.json"]

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


class TestDropInvalid:
    """Settings written by older versions lose the options this version no longer has."""

    def test_obsolete_keys_are_dropped_on_load(self, monkeypatch, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({
            "theme": "dark",
            "appearance": {"log_text_wrap": False},
            "decryption": {"cpu_threads": 3, "encrypt_filenames": True},
        }), encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(path))
        loaded = settings_mod.load_settings()
        assert "appearance" not in loaded
        assert loaded["theme"] == "dark"
        assert loaded["decryption"]["cpu_threads"] == 3
        assert "encrypt_filenames" not in loaded["decryption"]

    def test_scalar_in_place_of_a_section_is_dropped(self):
        defaults = {"advanced": {"enable_logs": False}, "theme": "system"}
        assert settings_mod.drop_invalid({"advanced": "oops", "theme": "dark"}, defaults) == {"theme": "dark"}

    def test_wrong_typed_values_fall_back_to_defaults(self):
        defaults = {"encryption": {"cpu_threads": 4, "read_size": 0}, "advanced": {"enable_logs": False}, "theme": "system"}
        loaded = {"encryption": {"cpu_threads": "abc", "read_size": None}, "advanced": {"enable_logs": 1}, "theme": 7}
        assert settings_mod.drop_invalid(loaded, defaults) == {"encryption": {}, "advanced": {}}

    def test_bool_and_int_are_told_apart(self):
        defaults = {"encryption": {"cpu_threads": 4}, "advanced": {"enable_logs": False}}
        loaded = {"encryption": {"cpu_threads": True}, "advanced": {"enable_logs": True}}
        assert settings_mod.drop_invalid(loaded, defaults) == {"encryption": {}, "advanced": {"enable_logs": True}}

    @pytest.mark.parametrize("section, key, value", [
        (None, "theme", "purple"),
        ("advanced", "log_level", "x"),
        ("advanced", "encryption_mode", "aes256_cfb"),  # CFB only decrypts now
        ("advanced", "encryption_mode", "rot13"),
        ("encryption", "read_size", 1),
        ("decryption", "read_size", 10 * 1024 ** 3),
        ("encryption", "read_size", 4 * 1024 * 1024 + 1),
        ("encryption", "cpu_threads", 0),
        ("decryption", "cpu_threads", 10_000),
    ])
    def test_values_outside_their_choices_load_as_the_default(self, monkeypatch, tmp_path, section, key, value):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({key: value} if section is None else {section: {key: value}}), encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(path))
        defaults = settings_mod.get_default_settings()
        loaded = settings_mod.load_settings()
        assert (loaded[key] if section is None else loaded[section][key]) == (
            defaults[key] if section is None else defaults[section][key])

    def test_values_within_their_choices_are_kept(self, monkeypatch, tmp_path):
        values = {
            "theme": "dark",
            "encryption": {"cpu_threads": 1, "read_size": 32 * 1024 * 1024},
            "decryption": {"cpu_threads": os.cpu_count() or 1, "read_size": 0},
            "advanced": {"encryption_mode": "chacha20_poly1305", "log_level": "all"},
        }
        path = tmp_path / "settings.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(path))
        loaded = settings_mod.load_settings()
        assert loaded["theme"] == "dark"
        assert loaded["encryption"]["cpu_threads"] == 1 and loaded["encryption"]["read_size"] == 32 * 1024 * 1024
        assert loaded["decryption"]["cpu_threads"] == (os.cpu_count() or 1)
        assert loaded["advanced"]["encryption_mode"] == "chacha20_poly1305"
        assert loaded["advanced"]["log_level"] == "all"
        assert settings_mod.take_read_error() is False  # odd values aren't a damaged file

    def test_damaged_file_loads_the_defaults(self, monkeypatch, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(path))
        assert settings_mod.load_settings() == settings_mod.get_default_settings()


class TestMigrateSettings:
    """A read size picked in 3.0.x ("chunk_size") carries over; the old defaults become the default."""

    MB = 1024 * 1024

    def test_chosen_size_carries_over_to_the_nearest_offered_size(self):
        old = {"encryption": {"chunk_size": 32 * self.MB}, "decryption": {"chunk_size": 128 * self.MB}}
        migrated = settings_mod.migrate_settings(old)
        assert migrated["encryption"]["read_size"] == 32 * self.MB
        assert migrated["decryption"]["read_size"] == 64 * self.MB

    def test_old_defaults_and_off_become_the_default(self):
        old = {"encryption": {"chunk_size": 16 * self.MB}, "decryption": {"chunk_size": None}}
        migrated = settings_mod.migrate_settings(old)
        assert "read_size" not in migrated["encryption"] and "read_size" not in migrated["decryption"]

    def test_saved_4_mb_becomes_the_default(self):
        migrated = settings_mod.migrate_settings({"encryption": {"read_size": 4 * self.MB}})
        assert migrated["encryption"]["read_size"] == 0

    def test_existing_read_size_wins(self):
        old = {"encryption": {"chunk_size": 64 * self.MB, "read_size": 0}}
        assert settings_mod.migrate_settings(old)["encryption"]["read_size"] == 0

    def test_load_applies_the_migration_and_drops_the_old_key(self, monkeypatch, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({"encryption": {"chunk_size": 8 * self.MB}}), encoding="utf-8")
        monkeypatch.setattr(settings_mod, "get_settings_file", lambda: str(path))
        loaded = settings_mod.load_settings()
        assert loaded["encryption"]["read_size"] == 8 * self.MB
        assert "chunk_size" not in loaded["encryption"]
        assert loaded["decryption"]["read_size"] == 0
