# benchmark.py - v2 encryption throughput of each engine (native C++ when built, and Python).
# Usage: python tests/benchmark.py
#
# It times the engines' seal and open calls alone, so the numbers are CPU and read throughput;
# key derivation (once per run) and the disk flush of an app run are left out.

import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from gfglock.core import format_v2, native_bridge, py_cipher
from gfglock.core.format_v2 import KeyRing

# ── Config ────────────────────────────────────────────────────────────────────

PASSWORD = "BenchmarkPass!2025"
FILE_SIZES_MB = [16, 64, 256]
ALGORITHMS = {"AES-256-GCM": "gcm", "ChaCha20-Poly1305": "chacha"}

Engine = tuple[Callable[..., tuple], Callable[..., tuple]]  # (seal, open)


# ── Data ──────────────────────────────────────────────────────────────────────

@dataclass
class BenchResult:
    """Holds a single encrypt + decrypt measurement pair."""
    label: str
    size_mb: int
    enc_mbs: float
    dec_mbs: float
    error: str = ""


@dataclass
class BenchSuite:
    """Aggregates all results for the final report."""
    results: list[BenchResult] = field(default_factory=list)

    def add(self, result: BenchResult) -> None:
        """Append one result to the suite."""
        self.results.append(result)

    def print_report(self) -> None:
        """Print a formatted throughput table to stdout."""
        col_w = [28, 10, 16, 16, 30]
        header = (
            f"{'Mode':<{col_w[0]}} {'Size (MB)':>{col_w[1]}} "
            f"{'Encrypt (MB/s)':>{col_w[2]}} {'Decrypt (MB/s)':>{col_w[3]}} "
            f"{'Note':<{col_w[4]}}"
        )
        sep = "-" * (sum(col_w) + 4)
        print(f"\n{'BENCHMARK RESULTS':^{len(sep)}}")
        print(sep)
        print(header)
        print(sep)
        for r in self.results:
            enc = f"{r.enc_mbs:.2f}" if r.enc_mbs > 0 else "FAILED"
            dec = f"{r.dec_mbs:.2f}" if r.dec_mbs > 0 else "FAILED"
            print(
                f"{r.label:<{col_w[0]}} {r.size_mb:>{col_w[1]}} "
                f"{enc:>{col_w[2]}} {dec:>{col_w[3]}} "
                f"{r.error:<{col_w[4]}}"
            )
        print(sep)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _engines() -> dict[str, Engine]:
    """The (seal, open) pair of every engine available here."""
    engines: dict[str, Engine] = {}
    if native_bridge.NATIVE_AVAILABLE:
        engines["native"] = (native_bridge.seal_file, native_bridge.open_file)
    engines["Python"] = (py_cipher.seal_stream, py_cipher.open_stream)
    return engines


def _make_file(dirpath: str, size_mb: int) -> str:
    """Create a binary file of the requested size and return its path."""
    path = os.path.join(dirpath, f"bench_{size_mb}mb.bin")
    with open(path, "wb") as f:
        chunk = os.urandom(1024 * 1024)
        for _ in range(size_mb):
            f.write(chunk)
    return path


def _timed(fn: Callable[[], tuple]) -> tuple[tuple, float]:
    """Call fn and return its result with the elapsed seconds."""
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


def _bench(dirpath: str, size_mb: int, label: str, algorithm: str, engine: Engine, keys: KeyRing) -> BenchResult:
    """Seal and open one file of size_mb with one engine and algorithm."""
    seal, open_stream = engine
    source = _make_file(dirpath, size_mb)
    sealed, opened = os.path.join(dirpath, "sealed"), os.path.join(dirpath, "opened")
    header, key = keys.new_header(algorithm)
    metadata = format_v2.pack_metadata(os.path.basename(source), 0)

    (ok, error), elapsed = _timed(lambda: seal(algorithm, source, sealed, header.pack(), key,
                                               header.nonce_prefix, header.chunk_size, metadata))
    if not ok:
        return BenchResult(label, size_mb, 0.0, 0.0, error[:30])
    enc_mbs = size_mb / elapsed

    (ok, error, _stored), elapsed = _timed(lambda: open_stream(algorithm, sealed, opened, header.pack(), key,
                                                               header.nonce_prefix, header.chunk_size))
    if not ok:
        return BenchResult(label, size_mb, enc_mbs, 0.0, error[:30])
    if os.path.getsize(opened) != os.path.getsize(source):
        return BenchResult(label, size_mb, enc_mbs, 0.0, "round trip changed the size")
    return BenchResult(label, size_mb, enc_mbs, size_mb / elapsed)


def _bench_all(suite: BenchSuite) -> None:
    """Run every engine, algorithm, and size, and append the results to suite."""
    keys = KeyRing(PASSWORD)
    keys.new_header("gcm")  # derives the run's Argon2id key now, outside the timings
    for size_mb in FILE_SIZES_MB:
        for engine_name, engine in _engines().items():
            for algorithm_name, algorithm in ALGORITHMS.items():
                label = f"{engine_name:<7}{algorithm_name}"
                print(f"  [{label}] {size_mb} MB ...", end=" ", flush=True)
                with tempfile.TemporaryDirectory(prefix="gfgbench_") as dirpath:
                    result = _bench(dirpath, size_mb, label, algorithm, engine, keys)
                suite.add(result)
                if result.error:
                    print(f"ERROR: {result.error}")
                else:
                    print(f"enc={result.enc_mbs:.2f} MB/s  dec={result.dec_mbs:.2f} MB/s")


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Run the benchmark suite and print the results table."""
    print("=" * 70)
    print("  gfgLock  -  Performance Benchmark")
    print(f"  File sizes: {FILE_SIZES_MB} MB")
    if not native_bridge.NATIVE_AVAILABLE:
        print("  The native module (API 5) is not built: only the Python engine runs")
    print("=" * 70)

    suite = BenchSuite()
    _bench_all(suite)
    suite.print_report()


if __name__ == "__main__":
    main()
