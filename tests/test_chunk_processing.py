import os

import pytest

from gfglock.core.chunk_processing import FileChunker


def _read_all(path: str) -> bytes:
    """Read and return the full contents of path."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception as exc:
        pytest.fail(str(exc))


def _write_file(tmp_path, name: str, data: bytes) -> str:
    """Write data to tmp_path/name and return the str path."""
    try:
        p = tmp_path / name
        p.write_bytes(data)
        return str(p)
    except Exception as exc:
        pytest.fail(f"Could not create test file: {exc}")


class TestSplitFile:
    """Unit tests for FileChunker.split_file across various file sizes and chunk sizes."""

    def test_empty_file(self, tmp_path):
        """An empty source file must yield zero chunk files."""
        src = _write_file(tmp_path, "empty.bin", b"")
        chunker = FileChunker()
        try:
            chunks = chunker.split_file(src, 1024)
            assert chunks == []
        finally:
            chunker.cleanup_temp_dir()

    def test_small_data(self, tmp_path):
        """Data smaller than chunk_size must produce exactly one chunk holding all bytes."""
        data = b"gfglock" * 10
        src = _write_file(tmp_path, "small.bin", data)
        chunker = FileChunker()
        try:
            chunks = chunker.split_file(src, 4096)
            assert len(chunks) == 1
            assert _read_all(chunks[0]) == data
        finally:
            chunker.cleanup_temp_dir()

    def test_exact_multiple(self, tmp_path):
        """Data exactly N x chunk_size must produce N chunks each of chunk_size bytes."""
        chunk_size = 1024
        data = os.urandom(chunk_size * 3)
        src = _write_file(tmp_path, "exact.bin", data)
        chunker = FileChunker()
        try:
            chunks = chunker.split_file(src, chunk_size)
            assert len(chunks) == 3
            for cpath in chunks:
                assert len(_read_all(cpath)) == chunk_size
        finally:
            chunker.cleanup_temp_dir()

    def test_with_remainder(self, tmp_path):
        """Data with a partial final chunk must produce a shorter last chunk."""
        chunk_size = 1000
        data = os.urandom(chunk_size * 2 + 337)
        src = _write_file(tmp_path, "remainder.bin", data)
        chunker = FileChunker()
        try:
            chunks = chunker.split_file(src, chunk_size)
            assert len(chunks) == 3
            assert len(_read_all(chunks[0])) == chunk_size
            assert len(_read_all(chunks[1])) == chunk_size
            assert len(_read_all(chunks[2])) == 337
        finally:
            chunker.cleanup_temp_dir()

    def test_mb_heuristic(self, tmp_path):
        """chunk_size in (0, 128] must be interpreted as megabytes, not raw bytes."""
        one_mib = 1024 * 1024
        data = os.urandom(int(one_mib * 1.5))
        src = _write_file(tmp_path, "mb.bin", data)
        chunker = FileChunker()
        try:
            chunks = chunker.split_file(src, 1)
            assert len(chunks) == 2
            assert len(_read_all(chunks[0])) == one_mib
            assert len(_read_all(chunks[1])) == int(one_mib * 1.5) - one_mib
        finally:
            chunker.cleanup_temp_dir()

    def test_roundtrip(self, tmp_path):
        """split_file followed by merge_chunks must reconstruct the original bytes exactly."""
        data = os.urandom(5000)
        src = _write_file(tmp_path, "roundtrip.bin", data)
        out_path = str(tmp_path / "rebuilt.bin")
        chunker = FileChunker()
        try:
            chunks = chunker.split_file(src, 777)
            chunker.merge_chunks(chunks, out_path)
            assert _read_all(out_path) == data
        finally:
            chunker.cleanup_temp_dir()

    def test_missing_file(self, tmp_path):
        """split_file on a nonexistent path must raise, not fail silently."""
        missing = str(tmp_path / "does_not_exist.bin")
        chunker = FileChunker()
        try:
            with pytest.raises(OSError):
                chunker.split_file(missing, 1024)
        finally:
            chunker.cleanup_temp_dir()

    def test_zero_size(self, tmp_path):
        """chunk_size=0 must raise ValueError instead of silently producing zero chunks."""
        data = os.urandom(2048)
        src = _write_file(tmp_path, "zero.bin", data)
        chunker = FileChunker()
        try:
            with pytest.raises(ValueError):
                chunker.split_file(src, 0)
        finally:
            chunker.cleanup_temp_dir()

    def test_negative_size(self, tmp_path):
        """A negative chunk_size must raise ValueError instead of silently reading to EOF."""
        data = os.urandom(2048)
        src = _write_file(tmp_path, "negative.bin", data)
        chunker = FileChunker()
        try:
            with pytest.raises(ValueError):
                chunker.split_file(src, -1)
        finally:
            chunker.cleanup_temp_dir()


class TestMergeChunks:
    """Unit tests for FileChunker.merge_chunks."""

    def test_merge_roundtrip(self, tmp_path):
        """merge_chunks must concatenate in order and delete each source chunk afterward."""
        parts = [b"first-", b"second-", b"third"]
        chunk_paths = []
        for i, part in enumerate(parts):
            chunk_paths.append(_write_file(tmp_path, f"c{i}.tmp", part))
        out_path = str(tmp_path / "merged.bin")
        chunker = FileChunker()
        try:
            chunker.merge_chunks(chunk_paths, out_path)
            assert _read_all(out_path) == b"".join(parts)
            for cpath in chunk_paths:
                assert not os.path.exists(cpath)
        finally:
            chunker.cleanup_temp_dir()

    def test_skip_missing(self, tmp_path):
        """A chunk path that no longer exists must be skipped without raising."""
        present = _write_file(tmp_path, "present.tmp", b"data-present")
        missing = str(tmp_path / "vanished.tmp")
        out_path = str(tmp_path / "merged.bin")
        chunker = FileChunker()
        try:
            chunker.merge_chunks([present, missing], out_path)
            assert _read_all(out_path) == b"data-present"
        finally:
            chunker.cleanup_temp_dir()

    def test_merge_empty(self, tmp_path):
        """Merging an empty chunk list must still create an empty output file."""
        out_path = str(tmp_path / "empty_merge.bin")
        chunker = FileChunker()
        try:
            chunker.merge_chunks([], out_path)
            assert os.path.exists(out_path)
            assert _read_all(out_path) == b""
        finally:
            chunker.cleanup_temp_dir()


class TestStreamChunks:
    """Unit tests for FileChunker.stream_chunks."""

    def test_stream_no_total(self, tmp_path):
        """With total_bytes=None, stream_chunks must yield until EOF and reconstruct the data."""
        data = os.urandom(4500)
        src = _write_file(tmp_path, "stream.bin", data)
        chunker = FileChunker()
        try:
            with open(src, "rb") as f:
                collected = b"".join(chunker.stream_chunks(f, None, 1000))
            assert collected == data
        finally:
            chunker.cleanup_temp_dir()

    def test_stream_limited(self, tmp_path):
        """A total_bytes smaller than the file size must stop the stream early."""
        data = os.urandom(4500)
        src = _write_file(tmp_path, "stream_limited.bin", data)
        chunker = FileChunker()
        try:
            with open(src, "rb") as f:
                collected = b"".join(chunker.stream_chunks(f, 2000, 1000))
            assert collected == data[:2000]
        finally:
            chunker.cleanup_temp_dir()

    def test_stream_exact(self, tmp_path):
        """Streaming data that is an exact multiple of chunk_size must yield uniform chunks."""
        data = os.urandom(3000)
        src = _write_file(tmp_path, "stream_exact.bin", data)
        chunker = FileChunker()
        try:
            with open(src, "rb") as f:
                pieces = list(chunker.stream_chunks(f, None, 1000))
            assert [len(p) for p in pieces] == [1000, 1000, 1000]
        finally:
            chunker.cleanup_temp_dir()

    def test_stream_mb_heuristic(self, tmp_path):
        """chunk_size in (0, 128] must be treated as megabytes for stream_chunks too."""
        one_mib = 1024 * 1024
        data = os.urandom(int(one_mib * 1.2))
        src = _write_file(tmp_path, "stream_mb.bin", data)
        chunker = FileChunker()
        try:
            with open(src, "rb") as f:
                pieces = list(chunker.stream_chunks(f, None, 1))
            assert len(pieces[0]) == one_mib
            assert b"".join(pieces) == data
        finally:
            chunker.cleanup_temp_dir()

    def test_stream_zero(self, tmp_path):
        """chunk_size=0 must raise ValueError instead of silently yielding nothing."""
        data = os.urandom(1024)
        src = _write_file(tmp_path, "stream_zero.bin", data)
        chunker = FileChunker()
        try:
            with open(src, "rb") as f:
                with pytest.raises(ValueError):
                    list(chunker.stream_chunks(f, None, 0))
        finally:
            chunker.cleanup_temp_dir()

    def test_stream_zero_total(self, tmp_path):
        """chunk_size=0 must raise ValueError even when total_bytes is also given."""
        data = os.urandom(1024)
        src = _write_file(tmp_path, "stream_zero_total.bin", data)
        chunker = FileChunker()
        try:
            with open(src, "rb") as f:
                with pytest.raises(ValueError):
                    list(chunker.stream_chunks(f, 512, 0))
        finally:
            chunker.cleanup_temp_dir()

    def test_stream_empty(self, tmp_path):
        """Streaming an empty file must yield no chunks at all."""
        src = _write_file(tmp_path, "stream_empty.bin", b"")
        chunker = FileChunker()
        try:
            with open(src, "rb") as f:
                pieces = list(chunker.stream_chunks(f, None, 1000))
            assert pieces == []
        finally:
            chunker.cleanup_temp_dir()


class TestTempDirLifecycle:
    """Coverage for FileChunker's isolated temp-directory creation and cleanup."""

    def test_custom_base(self, tmp_path):
        """A caller-supplied temp_dir must become the parent of the isolated chunk dir."""
        base = str(tmp_path / "custom_base")
        os.makedirs(base, exist_ok=True)
        data = os.urandom(2000)
        src = _write_file(tmp_path, "custom.bin", data)
        chunker = FileChunker(temp_dir=base)
        try:
            chunks = chunker.split_file(src, 500)
            assert chunks
            isolated = chunker.isolated_temp_dir
            assert isolated is not None
            assert os.path.commonpath([base, isolated]) == base
        finally:
            chunker.cleanup_temp_dir()

    def test_cleanup_removes(self, tmp_path):
        """cleanup_temp_dir must remove the isolated directory and reset the attribute."""
        data = os.urandom(500)
        src = _write_file(tmp_path, "cleanup.bin", data)
        chunker = FileChunker()
        chunker.split_file(src, 200)
        isolated = chunker.isolated_temp_dir
        assert isolated is not None
        assert os.path.exists(isolated)
        chunker.cleanup_temp_dir()
        assert not os.path.exists(isolated)
        assert chunker.isolated_temp_dir is None

    def test_cleanup_idempotent(self, tmp_path):
        """Calling cleanup_temp_dir twice in a row must not raise."""
        data = os.urandom(300)
        src = _write_file(tmp_path, "idempotent.bin", data)
        chunker = FileChunker()
        chunker.split_file(src, 100)
        chunker.cleanup_temp_dir()
        try:
            chunker.cleanup_temp_dir()
        except Exception as exc:
            pytest.fail(f"Second cleanup_temp_dir call raised: {exc}")

    def test_cleanup_unused(self):
        """cleanup_temp_dir on a chunker that never created a temp dir must be a no-op."""
        chunker = FileChunker()
        try:
            chunker.cleanup_temp_dir()
        except Exception as exc:
            pytest.fail(f"cleanup_temp_dir raised on unused chunker: {exc}")
        assert chunker.isolated_temp_dir is None
