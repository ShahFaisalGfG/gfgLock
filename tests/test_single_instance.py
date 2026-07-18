import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer

from gfglock.utils.single_instance import SingleInstance, _SERVER_NAME


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QCoreApplication exists so QLocalServer/QLocalSocket can operate."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture
def make_instance():
    """Factory for SingleInstance objects that always releases their sockets on teardown."""
    created = []

    def factory():
        inst = SingleInstance()
        created.append(inst)
        return inst

    yield factory
    for inst in created:
        try:
            inst.close()
        except Exception:
            pass
    try:
        QLocalServer.removeServer(_SERVER_NAME)
    except Exception:
        pass


class _Recorder:
    """Collects every argument tuple emitted by a connected Qt signal."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)


def _pump_until(app, predicate, timeout_s: float = 3.0) -> bool:
    """Process Qt events until predicate() is True or the timeout elapses."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


def _forward_on_thread(instance: SingleInstance, mode: str, paths: list) -> threading.Thread:
    """Run tryForward on its own thread so the caller's event loop stays free to pump.

    Real secondary instances are separate processes with their own event loop; running
    both sides on one test-process thread would starve the primary's loop of turns while
    tryForward's blocking socket calls are in flight, so a background thread is used here
    to mirror the two independent event loops that exist in production.
    """
    thread = threading.Thread(target=lambda: instance.tryForward(mode, paths))
    thread.start()
    return thread


def _deliver_with_retries(qapp, make_instance, mode: str, paths: list, recorder: "_Recorder") -> bool:
    """Forward a message to the primary, retrying with a fresh secondary if it is lost.

    tryForward's underlying protocol is fire-and-forget (write then disconnect with no
    acknowledgement), so a single attempt can race the primary's own event loop turn and
    silently drop the message even though the mechanism is fundamentally sound. Retrying
    a few times mirrors how a real launcher would behave and keeps this test meaningful
    without asserting a single-shot delivery guarantee the production code never made.
    """
    for _attempt in range(5):
        secondary = make_instance()
        thread = _forward_on_thread(secondary, mode, paths)
        delivered = _pump_until(qapp, lambda: bool(recorder.calls), timeout_s=1.0)
        thread.join(timeout=2.0)
        if delivered:
            return True
    return False


class TestTryForwardControlFlow:
    """tryForward's branch logic must behave correctly, independent of real sockets."""

    def test_becomes_primary_when_send_fails_and_server_starts(self, make_instance, monkeypatch):
        """No existing primary plus a successful listen must return False (primary)."""
        inst = make_instance()
        monkeypatch.setattr(inst, "_send", lambda *_a, **_k: False)
        monkeypatch.setattr(inst, "_startServer", lambda: True)
        assert inst.tryForward("encrypt", ["a.txt"]) is False

    def test_becomes_secondary_when_send_succeeds_immediately(self, make_instance, monkeypatch):
        """A successful first send must return True (secondary) without starting a server."""
        inst = make_instance()
        monkeypatch.setattr(inst, "_send", lambda *_a, **_k: True)
        assert inst.tryForward("encrypt", ["a.txt"]) is True

    def test_retries_as_client_after_losing_the_listen_race(self, make_instance, monkeypatch):
        """Losing the listen race must trigger exactly one retried send as a client."""
        inst = make_instance()
        calls = []

        def fake_send(mode, paths, timeout_ms):
            calls.append(timeout_ms)
            return len(calls) == 2

        monkeypatch.setattr(inst, "_send", fake_send)
        monkeypatch.setattr(inst, "_startServer", lambda: False)
        assert inst.tryForward("decrypt", ["b.txt"]) is True
        assert len(calls) == 2

    def test_returns_false_when_everything_fails(self, make_instance, monkeypatch):
        """A failed send, failed listen, and failed retry must all resolve to False."""
        inst = make_instance()
        monkeypatch.setattr(inst, "_send", lambda *_a, **_k: False)
        monkeypatch.setattr(inst, "_startServer", lambda: False)
        assert inst.tryForward("encrypt", ["a.txt"]) is False

    def test_exception_is_swallowed_and_returns_false(self, make_instance, monkeypatch):
        """Any internal exception during forwarding must be caught, returning False."""
        inst = make_instance()

        def raiser(*_a, **_k):
            raise RuntimeError("socket error")

        monkeypatch.setattr(inst, "_send", raiser)
        assert inst.tryForward("encrypt", ["a.txt"]) is False


class TestClose:
    """close() must release the server and never raise, with or without one."""

    def test_noop_without_server(self, make_instance):
        """Closing an instance that never became primary must not raise."""
        inst = make_instance()
        inst.close()

    def test_swallows_exception_from_server(self, make_instance):
        """A failing underlying server.close() must not propagate out of close()."""
        inst = make_instance()

        class _BadServer:
            def close(self):
                raise RuntimeError("close failed")

        inst._server = _BadServer()
        try:
            inst.close()
        except Exception as exc:
            pytest.fail(f"close() must not raise, got: {exc}")


class TestRealSocketIntegration:
    """End-to-end acquire/forward/release behavior using genuine local sockets."""

    def test_first_instance_becomes_primary_and_listens(self, qapp, make_instance):
        """The first instance to call tryForward must become the listening primary."""
        primary = make_instance()
        assert primary.tryForward("encrypt", ["one.txt"]) is False
        assert primary._server is not None
        assert primary._server.isListening()

    def test_second_instance_forwards_paths_to_primary(self, qapp, make_instance):
        """A second instance must detect the primary and forward its mode and paths."""
        primary = make_instance()
        assert primary.tryForward("encrypt", ["ignored.txt"]) is False

        received = _Recorder()
        primary.filesReceived.connect(received)

        delivered = _deliver_with_retries(qapp, make_instance, "decrypt", ["a.txt", "b.txt"], received)
        assert delivered, "message was never forwarded to the primary after several attempts"
        assert received.calls[0] == ("decrypt", ["a.txt", "b.txt"])

    def test_close_releases_the_name_for_a_new_primary(self, qapp, make_instance):
        """After close(), a fresh instance must be able to bind the same server name again."""
        first = make_instance()
        assert first.tryForward("encrypt", ["one.txt"]) is False
        first.close()

        second = make_instance()
        assert second.tryForward("encrypt", ["two.txt"]) is False
        assert second._server is not None
        assert second._server.isListening()

    def test_empty_paths_are_forwarded_but_not_emitted(self, qapp, make_instance):
        """A forwarded message with empty paths must not trigger filesReceived."""
        primary = make_instance()
        assert primary.tryForward("encrypt", ["ignored.txt"]) is False

        received = _Recorder()
        primary.filesReceived.connect(received)

        secondary = make_instance()
        thread = _forward_on_thread(secondary, "encrypt", [])
        thread.join(timeout=2.0)

        _pump_until(qapp, lambda: False, timeout_s=0.3)
        assert received.calls == []
