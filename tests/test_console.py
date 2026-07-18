import io

import pytest

from gfglock.utils import console


class _FakeBufferStdout:
    """Stdout stand-in exposing a binary .buffer, like the real sys.stdout."""

    def __init__(self):
        self.buffer = io.BytesIO()

    def write(self, _text):
        pytest.fail("plain write() must not be used when buffer.write() succeeds")

    def flush(self):
        pass


class _RaisingBufferStdout:
    """Stdout stand-in whose binary buffer always raises, forcing the fallback path."""

    def __init__(self):
        self.written = []

    @property
    def buffer(self):
        raise AttributeError("no buffer here")

    def write(self, text):
        self.written.append(text)

    def flush(self):
        pass


class _FullyBrokenStdout:
    """Stdout stand-in where both the buffer path and the plain-write fallback fail."""

    @property
    def buffer(self):
        raise AttributeError("no buffer")

    def write(self, _text):
        raise OSError("cannot write")

    def flush(self):
        raise OSError("cannot flush")


class TestSafePrint:
    """safe_print must write UTF-8 encoded text, plus a trailing newline, to stdout."""

    def test_writes_utf8_bytes_with_newline(self, monkeypatch):
        """A plain ASCII message must be encoded as UTF-8 bytes with a trailing newline."""
        fake = _FakeBufferStdout()
        monkeypatch.setattr(console.sys, "stdout", fake)
        console.safe_print("hello")
        assert fake.buffer.getvalue() == b"hello\n"

    def test_writes_non_ascii_text(self, monkeypatch):
        """Non-ASCII characters must round-trip correctly through UTF-8 encoding."""
        fake = _FakeBufferStdout()
        monkeypatch.setattr(console.sys, "stdout", fake)
        console.safe_print("cafe ✓ é")
        assert fake.buffer.getvalue().decode("utf-8") == "cafe ✓ é\n"

    def test_converts_non_string_input(self, monkeypatch):
        """Non-string arguments must be stringified before being written."""
        fake = _FakeBufferStdout()
        monkeypatch.setattr(console.sys, "stdout", fake)
        console.safe_print(123)  # type: ignore[arg-type]
        assert fake.buffer.getvalue() == b"123\n"

    def test_falls_back_to_plain_write_when_buffer_fails(self, monkeypatch):
        """When sys.stdout.buffer is unavailable, safe_print must retry with plain write()."""
        fake = _RaisingBufferStdout()
        monkeypatch.setattr(console.sys, "stdout", fake)
        console.safe_print("fallback")
        assert fake.written == ["fallback\n"]

    def test_swallows_exception_when_everything_fails(self, monkeypatch):
        """If both the buffer path and the plain write fallback fail, no exception escapes."""
        monkeypatch.setattr(console.sys, "stdout", _FullyBrokenStdout())
        try:
            console.safe_print("doomed")
        except Exception as exc:
            pytest.fail(f"safe_print must never raise, got: {exc}")

    def test_returns_none(self, monkeypatch):
        """safe_print has no meaningful return value."""
        fake = _FakeBufferStdout()
        monkeypatch.setattr(console.sys, "stdout", fake)
        assert console.safe_print("x") is None
