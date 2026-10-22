import pytest

from gfglock.core.format_v2 import KdfParams, KeyRing
from gfglock.utils import paths, settings

_PAYLOAD: bytes = b"gfgLock test vector\n" * 250 + bytes(range(256)) * 10
# Argon2id at its smallest cost: the default costs take about 0.4 s per run.
FAST_KDF = KdfParams(memory_kib=64, iterations=1, lanes=1)


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch, tmp_path_factory):
    """Settings and logs of every test go to a temp folder, never the repo's logs/ or settings.json."""
    folder = tmp_path_factory.mktemp("gfglock-data")
    monkeypatch.setattr(paths, "_data_dir", str(folder))
    monkeypatch.setattr(settings, "_read_error", False)  # a damaged file in one test must not flag the next
    return folder


@pytest.fixture(scope="session")
def sample_data() -> bytes:
    """Deterministic binary payload shared across all encryption tests."""
    return _PAYLOAD


@pytest.fixture
def password() -> str:
    """Password used for all encrypt/decrypt calls in the test suite."""
    return "T3st!P@ss#2025_gfg"


@pytest.fixture
def keys(password) -> KeyRing:
    """The run key ring for `password`, with cheap Argon2id costs."""
    return KeyRing(password, FAST_KDF)


@pytest.fixture
def make_file(tmp_path, sample_data):
    """Factory: writes sample_data to tmp_path/{name} and returns the str path."""
    def _factory(name: str = "payload.bin") -> str:
        try:
            p = tmp_path / name
            p.write_bytes(sample_data)
            return str(p)
        except Exception as exc:
            pytest.fail(f"Could not create test file: {exc}")
    return _factory
