import subprocess

import pytest

from gfglock.services import notifier


class _FakePopen:
    """Records the arguments a Popen call was made with, without spawning anything."""

    def __init__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class TestSendNotificationWindows:
    """send_notification must build and fire a PowerShell toast on win32 only."""

    def test_invokes_popen_on_win32(self, monkeypatch):
        """On win32, send_notification must launch exactly one hidden PowerShell process."""
        calls = []
        monkeypatch.setattr(notifier.sys, "platform", "win32")
        monkeypatch.setattr(
            notifier.subprocess, "Popen",
            lambda *a, **kw: calls.append((a, kw)) or _FakePopen(*a, **kw),
        )
        notifier.send_notification("Title", "Body")
        assert len(calls) == 1

    def test_popen_uses_hidden_window_and_no_console(self, monkeypatch):
        """The PowerShell process must run hidden with stdout/stderr suppressed."""
        captured = {}
        monkeypatch.setattr(notifier.sys, "platform", "win32")

        def fake_popen(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return _FakePopen(args, **kwargs)

        monkeypatch.setattr(notifier.subprocess, "Popen", fake_popen)
        notifier.send_notification("Title", "Body")
        assert captured["kwargs"]["stdout"] == subprocess.DEVNULL
        assert captured["kwargs"]["stderr"] == subprocess.DEVNULL
        assert captured["kwargs"]["creationflags"] == 0x08000000
        assert "-WindowStyle" in captured["args"]
        assert "Hidden" in captured["args"]

    def test_script_embeds_title_and_body(self, monkeypatch):
        """The generated PowerShell script must contain the given title and body text."""
        captured = {}
        monkeypatch.setattr(notifier.sys, "platform", "win32")
        monkeypatch.setattr(
            notifier.subprocess, "Popen",
            lambda args, **kw: captured.setdefault("args", args) or _FakePopen(args, **kw),
        )
        notifier.send_notification("My Title", "My Body")
        script = captured["args"][-1]
        assert "My Title" in script
        assert "My Body" in script

    def test_double_quotes_in_text_are_sanitized(self, monkeypatch):
        """Double quotes in title/body must be replaced so the embedded script stays valid."""
        captured = {}
        monkeypatch.setattr(notifier.sys, "platform", "win32")
        monkeypatch.setattr(
            notifier.subprocess, "Popen",
            lambda args, **kw: captured.setdefault("args", args) or _FakePopen(args, **kw),
        )
        notifier.send_notification('Say "hi"', 'Body "quoted"')
        script = captured["args"][-1]
        assert "Say 'hi'" in script
        assert "Body 'quoted'" in script


class TestSendNotificationNonWindows:
    """On non-win32 platforms send_notification must be a strict no-op."""

    def test_no_popen_on_linux(self, monkeypatch):
        """No subprocess must be spawned when platform is not win32."""
        calls = []
        monkeypatch.setattr(notifier.sys, "platform", "linux")
        monkeypatch.setattr(notifier.subprocess, "Popen", lambda *a, **kw: calls.append(1))
        result = notifier.send_notification("Title", "Body")
        assert calls == []
        assert result is None


class TestSendNotificationErrorHandling:
    """Any failure while building or launching the toast must be swallowed."""

    def test_popen_exception_is_swallowed(self, monkeypatch):
        """A Popen failure must not propagate out of send_notification."""
        monkeypatch.setattr(notifier.sys, "platform", "win32")

        def raiser(*a, **kw):
            raise OSError("boom")

        monkeypatch.setattr(notifier.subprocess, "Popen", raiser)
        try:
            result = notifier.send_notification("Title", "Body")
        except Exception as exc:
            pytest.fail(f"send_notification must not raise, got: {exc}")
        assert result is None

    def test_returns_none_on_success(self, monkeypatch):
        """send_notification has no return value on the happy path either."""
        monkeypatch.setattr(notifier.sys, "platform", "win32")
        monkeypatch.setattr(notifier.subprocess, "Popen", lambda *a, **kw: _FakePopen(*a, **kw))
        assert notifier.send_notification("Title", "Body") is None
