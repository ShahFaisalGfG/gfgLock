# test_single_instance.py - one window per user session: delivery, buffering, busy windows, races

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from ctypes import wintypes

import pytest
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

from gfglock.utils import single_instance
from gfglock.utils.single_instance import LaunchRequest, SingleInstance, hold_app_mutexes

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A launch in its own process, as Explorer starts one. argv: role prefix tag notice [seconds count].
# "send" forwards and exits; "launch" forwards, or becomes the window and collects every launch's
# path until it has `count` of them. PySide6 holds the GIL inside QLocalSocket's waitFor* calls,
# so a sender on a thread of the test process would stall the window's event loop: senders are
# separate processes, as they are in use.
_LAUNCHER = r"""
import json, os, sys, time
from PySide6.QtCore import QCoreApplication
from gfglock.utils import paths
paths._data_dir = os.environ["GFGLOCK_TEST_DATA"]
from gfglock.utils.single_instance import LaunchRequest, SingleInstance

role, prefix, tag, notice = sys.argv[1:5]
app = QCoreApplication([])
instance = SingleInstance(prefix)
started = time.monotonic()
forwarded = instance.try_forward(LaunchRequest("encrypt", (tag,), notice))
waited = time.monotonic() - started
if forwarded or role == "send":
    print(json.dumps({"forwarded": forwarded, "waited": waited}), flush=True)
    sys.exit(0)
received = [tag]
instance.filesReceived.connect(lambda mode, paths: received.extend(paths))
instance.attach()
deadline = time.monotonic() + float(sys.argv[5])
while time.monotonic() < deadline and len(received) < int(sys.argv[6]):
    app.processEvents()
    time.sleep(0.005)
instance.close()
print(json.dumps({"forwarded": False, "received": received}), flush=True)
"""

# A pipe that accepts connections and never answers: a window whose event loop is stuck.
_SILENT_WINDOW = r"""
import sys, time
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer
app = QCoreApplication([])
server = QLocalServer()
server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
print("listening" if server.listen(sys.argv[1]) else "failed", flush=True)
time.sleep(60)
"""


@pytest.fixture(scope="session")
def qapp():
    """The session's QApplication (other test files need the widgets kind, so never a bare QCoreApplication)."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def prefix() -> str:
    """A name prefix of its own, so a test never reaches a gfgLock window open on this PC."""
    return f"gfgLockTest-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def make_instance(qapp, prefix):
    """Factory for SingleInstance objects with the test's prefix, closed on teardown."""
    created: list[SingleInstance] = []

    def factory() -> SingleInstance:
        instance = SingleInstance(prefix)
        created.append(instance)
        return instance

    yield factory
    for instance in created:
        instance.close()


@pytest.fixture
def run_script(isolated_data):
    """Start a Python script in its own process from the repo root; all are stopped on teardown."""
    started: list[subprocess.Popen] = []
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "GFGLOCK_TEST_DATA": str(isolated_data)}

    def start(script: str, *args: str) -> subprocess.Popen:
        proc = subprocess.Popen([sys.executable, "-c", script, *args], cwd=_REPO, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        started.append(proc)
        return proc

    yield start
    for proc in started:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()


@pytest.fixture
def launch(run_script, prefix):
    """Start a launch process with the test's prefix: launch(role, tag, *extra, notice="")."""
    def start(role: str, tag: str, *extra: str, notice: str = "") -> subprocess.Popen:
        return run_script(_LAUNCHER, role, prefix, tag, notice, *extra)

    return start


class _Recorder:
    """Collects every argument tuple emitted by a connected Qt signal."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)


def _pump_until(qapp, done, timeout_s: float = 30.0) -> bool:
    """Process Qt events until done() is true or the timeout passes."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        qapp.processEvents()
        if done():
            return True
        time.sleep(0.005)
    return False


def _result(qapp, proc: subprocess.Popen) -> dict:
    """Keep the window's event loop running until the launch process ends, then return its report."""
    finished = _pump_until(qapp, lambda: proc.poll() is not None)
    if not finished:
        proc.kill()
    out, err = proc.communicate()
    assert finished, f"the launch process didn't finish: {out} {err}"
    assert proc.returncode == 0, err
    return json.loads(out.strip().splitlines()[-1])


def _window(make_instance, attach: bool = True):
    """A SingleInstance that became the window, recording what it delivers."""
    window = make_instance()
    assert window.try_forward(LaunchRequest()) is False
    files, activations, notices = _Recorder(), _Recorder(), _Recorder()
    window.filesReceived.connect(files)
    window.activationRequested.connect(activations)
    window.noticeReceived.connect(notices)
    if attach:
        window.attach()
    return window, files, activations, notices


class TestLaunchRequest:
    def test_round_trip(self):
        request = LaunchRequest("decrypt", ("C:\\a b\\x.gfglock", "D:\\Teachers'"), "1 item couldn't be found.")
        assert LaunchRequest.decode(request.encode().rstrip(b"\n")) == request

    def test_encoding_is_one_line(self):
        encoded = LaunchRequest("encrypt", ("C:\\x",), "two\nlines").encode()
        assert encoded.endswith(b"\n") and encoded.count(b"\n") == 1

    @pytest.mark.parametrize("line", [b"not json", b"[1, 2]", b'{"mode": 1}', b'{"paths": "C:\\\\x"}',
                                      b'{"paths": [1]}', b'{"notice": null}'])
    def test_anything_else_is_refused(self, line):
        with pytest.raises(ValueError):
            LaunchRequest.decode(line)


class TestNames:
    def test_pipe_and_mutex_names_belong_to_this_user_and_session(self, qapp):
        sid = single_instance._own_sid()
        instance = SingleInstance()
        assert sid.startswith("S-1-")
        assert instance._pipe_name == f"gfgLock-{sid}-{single_instance._session_id()}"
        assert instance._mutex_name == f"Local\\gfgLock-instance-{sid}"


class TestDelivery:
    def test_first_send_is_delivered(self, qapp, make_instance, launch):
        window, files, activations, _ = _window(make_instance)
        report = _result(qapp, launch("send", "C:\\one.txt"))
        assert report["forwarded"] is True
        assert files.calls == [("encrypt", ["C:\\one.txt"])]
        assert len(activations.calls) == 1

    def test_notice_is_passed_on(self, qapp, make_instance, launch):
        window, _, _, notices = _window(make_instance)
        assert _result(qapp, launch("send", "C:\\one.txt", notice="2 items couldn't be found."))["forwarded"]
        assert notices.calls == [("2 items couldn't be found.",)]

    def test_launches_while_loading_wait_for_attach_in_order(self, qapp, make_instance, launch):
        window, files, activations, _ = _window(make_instance, attach=False)
        for tag in ("C:\\first.txt", "C:\\second.txt"):
            assert _result(qapp, launch("send", tag))["forwarded"] is True
        assert files.calls == [] and activations.calls == []
        window.attach()
        assert files.calls == [("encrypt", ["C:\\first.txt"]), ("encrypt", ["C:\\second.txt"])]
        assert len(activations.calls) == 2

    def test_busy_window_still_gets_the_files(self, qapp, make_instance, launch):
        window, files, _, _ = _window(make_instance)
        proc = launch("send", "C:\\busy.txt")
        time.sleep(3)  # the window's event loop is blocked, as during a long call on the GUI thread
        report = _result(qapp, proc)
        assert report["forwarded"] is True
        assert report["waited"] > 0.5  # it waited for the busy window instead of giving up
        assert files.calls == [("encrypt", ["C:\\busy.txt"])]

    def test_simultaneous_launches_make_one_window(self, qapp, launch):
        tags = [f"C:\\file {index}.txt" for index in range(4)]
        procs = [launch("launch", tag, "45", "4") for tag in tags]
        reports = [_result(qapp, proc) for proc in procs]
        windows = [report for report in reports if not report["forwarded"]]
        assert len(windows) == 1
        assert sorted(windows[0]["received"]) == sorted(tags)


class TestFallbacks:
    def test_without_a_window_this_launch_becomes_it(self, make_instance):
        instance = make_instance()
        assert instance.try_forward(LaunchRequest("encrypt", ("C:\\a.txt",))) is False
        assert instance._server is not None and instance._server.isListening()

    def test_unanswered_launch_opens_its_own_window(self, make_instance, run_script, monkeypatch):
        sender = make_instance()
        silent = run_script(_SILENT_WINDOW, sender._pipe_name)
        assert silent.stdout is not None and silent.stdout.readline().strip() == "listening"
        monkeypatch.setattr(single_instance, "_ANSWER_MS", 300)
        assert sender.try_forward(LaunchRequest("encrypt", ("C:\\a.txt",))) is False
        assert sender._server is None  # a window exists, so this one doesn't listen as well

    def test_pipe_served_by_another_account_gets_nothing(self, qapp, make_instance, monkeypatch):
        sender = make_instance()
        squatter = QLocalServer()
        assert squatter.listen(sender._pipe_name)
        monkeypatch.setattr(single_instance, "_pipe_owner", lambda sock: "S-1-5-21-1-2-3-1001")
        try:
            assert sender.try_forward(LaunchRequest("encrypt", ("C:\\secret.txt",))) is False
            assert _pump_until(qapp, squatter.hasPendingConnections, timeout_s=5)
            assert squatter.nextPendingConnection().readAll().data() == b""
        finally:
            squatter.close()

    def test_close_frees_the_name_for_a_new_window(self, make_instance):
        first = make_instance()
        assert first.try_forward(LaunchRequest()) is False
        first.close()
        second = make_instance()
        assert second.try_forward(LaunchRequest()) is False
        assert second._server is not None and second._server.isListening()


class TestMutexes:
    def test_named_mutex_makes_a_second_holder_wait(self):
        name = f"Local\\gfgLockTest-{uuid.uuid4().hex}"
        order: list[str] = []
        entered, release = threading.Event(), threading.Event()

        def first():
            with single_instance._named_mutex(name):
                order.append("first in")
                entered.set()
                release.wait(10)
                order.append("first out")

        def second():
            with single_instance._named_mutex(name):
                order.append("second in")

        holder = threading.Thread(target=first)
        holder.start()
        assert entered.wait(10)
        waiter = threading.Thread(target=second)
        waiter.start()
        waiter.join(0.3)
        assert waiter.is_alive()  # still waiting for the first holder
        release.set()
        holder.join(10)
        waiter.join(10)
        assert order == ["first in", "first out", "second in"]

    def test_app_mutexes_exist_for_the_installers(self, monkeypatch):
        names = (f"gfgLockTestMutex-{uuid.uuid4().hex}", f"Global\\gfgLockTestMutex-{uuid.uuid4().hex}")
        held: list[int] = []
        monkeypatch.setattr(single_instance, "APP_MUTEXES", names)
        monkeypatch.setattr(single_instance, "_app_mutexes", held)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenMutexW.restype = wintypes.HANDLE
        kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        hold_app_mutexes()
        try:
            assert held  # the Global one may be refused in some sessions; the local one never is
            handle = kernel32.OpenMutexW(0x00100000, False, names[0])  # SYNCHRONIZE
            assert handle
            kernel32.CloseHandle(handle)
        finally:
            for handle in held:
                kernel32.CloseHandle(handle)

    def test_a_second_window_opens_the_existing_mutexes(self, monkeypatch):
        """A second window (or session) gets a handle too, and nothing is logged as refused."""
        names = (f"gfgLockTestMutex-{uuid.uuid4().hex}",)
        held: list[int] = []
        logged: list[str] = []
        monkeypatch.setattr(single_instance, "APP_MUTEXES", names)
        monkeypatch.setattr(single_instance, "_app_mutexes", held)
        monkeypatch.setattr(single_instance, "write_log", lambda message, *args, **kwargs: logged.append(message))
        try:
            hold_app_mutexes()
            hold_app_mutexes()
            assert len(held) == 2 and all(held)
            assert logged == []
        finally:
            for handle in held:
                ctypes.WinDLL("kernel32").CloseHandle(wintypes.HANDLE(handle))
