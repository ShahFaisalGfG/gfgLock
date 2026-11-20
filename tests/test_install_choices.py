"""The installer's connection choices: read from the registry, applied once, never turning anything on."""

import sys
import uuid

import pytest

from gfglock.config.defaults import get_default_settings
from gfglock.utils import install_choices
from gfglock.utils.install_choices import apply_choices, read_choices


def test_a_cleared_choice_turns_update_checks_off() -> None:
    settings = get_default_settings()
    assert apply_choices(settings, {"UpdateChecks": 0})
    assert settings["advanced"]["auto_check_updates"] is False
    assert settings["install"]["connections"] == "UpdateChecks=0"


def test_the_installer_never_turns_update_checks_on() -> None:
    settings = get_default_settings()
    settings["advanced"]["auto_check_updates"] = False  # turned off in Preferences
    apply_choices(settings, {"UpdateChecks": 1})
    assert settings["advanced"]["auto_check_updates"] is False


def test_an_unchanged_choice_does_not_undo_preferences() -> None:
    """A silent in-app update keeps the earlier choice: checks turned back on in Preferences stay on."""
    settings = get_default_settings()
    apply_choices(settings, {"UpdateChecks": 0})
    settings["advanced"]["auto_check_updates"] = True
    assert not apply_choices(settings, {"UpdateChecks": 0})
    assert settings["advanced"]["auto_check_updates"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="the installer's choices live in the Windows registry")
def test_choices_are_read_from_the_registry() -> None:
    import winreg
    key = rf"Software\gfglock-tests-{uuid.uuid4().hex}"
    assert read_choices(key) == {}
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
            winreg.SetValueEx(handle, "UpdateChecks", 0, winreg.REG_DWORD, 0)
        assert read_choices(key) == {"UpdateChecks": 0}
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)


def test_a_source_run_leaves_settings_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only an installed copy applies them; a source checkout or a portable build has no installer."""
    monkeypatch.setattr(install_choices, "read_choices", lambda key=install_choices.CHOICES_KEY: pytest.fail("read"))
    install_choices.apply_install_choices()
