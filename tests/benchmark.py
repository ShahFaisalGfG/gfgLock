# benchmark.py — CPU encryption throughput benchmark.
# Usage: python tests/benchmark.py

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from gfglock.core import native_bridge

# ── Config ────────────────────────────────────────────────────────────────────

PASSWORD = "BenchmarkPass!2025"
FILE_SIZES_MB = [16, 64, 256]
WARMUP_RUNS = 1


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
            note = r.error or ""
            print(
                f"{r.label:<{col_w[0]}} {r.size_mb:>{col_w[1]}} "
                f"{enc:>{col_w[2]}} {dec:>{col_w[3]}} "
                f"{note:<{col_w[4]}}"
            )
        print(sep)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_file(dirpath: str, size_mb: int) -> str:
    """Create a temp binary file of the requested size and return its path."""
    path = os.path.join(dirpath, f"bench_{size_mb}mb.bin")
    with open(path, "wb") as f:
        chunk = os.urandom(1024 * 1024)
        for _ in range(size_mb):
            f.write(chunk)
    return path


def _timed(fn: Callable[[], tuple[bool, str]]) -> tuple[bool, float, str]:
    """Call fn, return (success, elapsed_seconds, message)."""
    t0 = time.perf_counter()
    try:
        ok, msg = fn()
        return ok, time.perf_counter() - t0, msg
    except Exception as exc:
        return False, time.perf_counter() - t0, str(exc)


def _throughput(size_mb: int, elapsed: float) -> float:
    """Return MB/s given file size and elapsed time; 0.0 on division by zero."""
    try:
        return size_mb / elapsed if elapsed > 0 else 0.0
    except Exception:
        return 0.0


def _find_encrypted(dirpath: str, exts: tuple) -> Optional[str]:
    """Return the first file in dirpath matching one of the given extensions."""
    try:
        for name in os.listdir(dirpath):
            if name.lower().endswith(exts):
                return os.path.join(dirpath, name)
    except Exception:
        pass
    return None


# ── CPU Benchmarks ────────────────────────────────────────────────────────────

def _bench_cpu_mode(
    dirpath: str,
    size_mb: int,
    label: str,
    enc_fn: Callable,
    dec_exts: tuple,
    dec_fn: Callable,
) -> BenchResult:
    """Benchmark one CPU encryption mode at one file size."""
    src = _make_file(dirpath, size_mb)
    enc_mbs = dec_mbs = 0.0
    error = ""

    try:
        for _ in range(WARMUP_RUNS):
            _timed(lambda: enc_fn(src + ".warmup", PASSWORD))

        ok, elapsed, msg = _timed(lambda: enc_fn(src, PASSWORD))
        if not ok:
            return BenchResult(label, size_mb, 0.0, 0.0, msg[:50])
        enc_mbs = _throughput(size_mb, elapsed)

        enc_path = _find_encrypted(dirpath, dec_exts)
        if enc_path is None:
            return BenchResult(label, size_mb, enc_mbs, 0.0, "encrypted file missing")

        ok, elapsed, msg = _timed(lambda: dec_fn(enc_path, PASSWORD))
        if not ok:
            return BenchResult(label, size_mb, enc_mbs, 0.0, msg[:50])
        dec_mbs = _throughput(size_mb, elapsed)

    except Exception as exc:
        error = str(exc)[:50]
    finally:
        for name in os.listdir(dirpath):
            fp = os.path.join(dirpath, name)
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass

    return BenchResult(label, size_mb, enc_mbs, dec_mbs, error)


def _bench_all_cpu(suite: BenchSuite) -> None:
    """Run all CPU mode benchmarks and append results to suite."""
    if not native_bridge.NATIVE_AVAILABLE:
        print("[CPU] native .pyd not available — skipping CPU benchmarks")
        return

    modes = [
        ("CPU  AES-256-GCM",       native_bridge.encrypt_gcm,    (".gfglock",), native_bridge.decrypt_gcm),
        ("CPU  AES-256-CFB",       native_bridge.encrypt_cfb,    (".gfglck",),  native_bridge.decrypt_cfb),
        ("CPU  ChaCha20-Poly1305", native_bridge.encrypt_chacha, (".gfgcha",),  native_bridge.decrypt_chacha),
    ]

    for size_mb in FILE_SIZES_MB:
        for label, enc_fn, dec_exts, dec_fn in modes:
            print(f"  [{label}] {size_mb} MB ...", end=" ", flush=True)
            dirpath = tempfile.mkdtemp(prefix="gfgbench_")
            try:
                result = _bench_cpu_mode(dirpath, size_mb, label, enc_fn, dec_exts, dec_fn)
            finally:
                shutil.rmtree(dirpath, ignore_errors=True)
            suite.add(result)
            if result.error:
                print(f"ERROR: {result.error}")
            else:
                print(f"enc={result.enc_mbs:.2f} MB/s  dec={result.dec_mbs:.2f} MB/s")


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Run the CPU benchmark suite and print the results table."""
    print("=" * 70)
    print("  gfgLock  —  Performance Benchmark")
    print(f"  File sizes: {FILE_SIZES_MB} MB")
    print("=" * 70)

    suite = BenchSuite()

    print("\n[CPU] Running CPU benchmarks ...")
    _bench_all_cpu(suite)

    suite.print_report()


if __name__ == "__main__":
    main()
