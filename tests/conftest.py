import pytest

_PAYLOAD: bytes = b"gfgLock test vector\n" * 250 + bytes(range(256)) * 10


@pytest.fixture(scope="session")
def sample_data() -> bytes:
    """Deterministic binary payload shared across all encryption tests."""
    return _PAYLOAD


@pytest.fixture
def password() -> str:
    """Password used for all encrypt/decrypt calls in the test suite."""
    return "T3st!P@ss#2025_gfg"


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
