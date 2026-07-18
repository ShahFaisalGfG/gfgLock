import os
import shutil
import tempfile
import uuid
from typing import Optional


class FileChunker:
    def __init__(self, temp_dir=None):
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.isolated_temp_dir: Optional[str] = None

    def _ensure_isolated_temp_dir(self):
        """Create a per-operation isolated temp directory if needed."""
        if self.isolated_temp_dir is None:
            uid = uuid.uuid4().hex[:8]
            pid = os.getpid()
            dir_name = f"gfglock_{pid}_{uid}"
            self.isolated_temp_dir = os.path.join(self.temp_dir, dir_name)
            os.makedirs(self.isolated_temp_dir, exist_ok=True)
        return self.isolated_temp_dir

    def cleanup_temp_dir(self):
        """Remove the isolated temp directory and all its contents."""
        if self.isolated_temp_dir and os.path.exists(self.isolated_temp_dir):
            try:
                shutil.rmtree(self.isolated_temp_dir)
            except Exception:
                pass
            self.isolated_temp_dir = None

    def __del__(self):
        self.cleanup_temp_dir()

    @staticmethod
    def _resolve_chunk_size(chunk_size) -> int:
        """Resolve a chunk_size argument to a byte count (1-128 is treated as megabytes).

        Raises ValueError for a non-positive size, since 0 silently reads nothing and a
        negative value reads the whole file at once, neither of which chunks as requested.
        """
        if not isinstance(chunk_size, (int, float)) or chunk_size <= 0:
            raise ValueError(f"chunk_size must be a positive number, got {chunk_size!r}")
        if isinstance(chunk_size, int) and chunk_size <= 128:
            return int(chunk_size * 1024 * 1024)
        return int(chunk_size)

    def split_file(self, file_path, chunk_size: int) -> list:
        """Split a file into chunk files and return their paths."""
        chunk_size_bytes = self._resolve_chunk_size(chunk_size)

        chunk_paths = []
        isolated_temp = self._ensure_isolated_temp_dir()
        with open(file_path, "rb") as f:
            chunk_num = 0
            while True:
                data = f.read(chunk_size_bytes)
                if not data:
                    break
                chunk_path = os.path.join(isolated_temp, f"chunk_{chunk_num}.tmp")
                with open(chunk_path, "wb") as chunk_file:
                    chunk_file.write(data)
                chunk_paths.append(chunk_path)
                chunk_num += 1
        return chunk_paths

    def merge_chunks(self, processed_chunk_paths, output_file_path):
        """Combine chunk files into a single output file."""
        with open(output_file_path, "wb") as output_file:
            for chunk_path in processed_chunk_paths:
                if os.path.exists(chunk_path):
                    with open(chunk_path, "rb") as f:
                        while True:
                            buffer = f.read(64 * 1024)
                            if not buffer:
                                break
                            output_file.write(buffer)
                    try:
                        os.remove(chunk_path)
                    except Exception:
                        pass

    def stream_chunks(self, fileobj, total_bytes=None, chunk_size=64 * 1024):
        """Yield chunks from fileobj; avoids temp files for true streaming."""
        chunk_size_bytes = self._resolve_chunk_size(chunk_size)

        if total_bytes is None:
            while True:
                data = fileobj.read(chunk_size_bytes)
                if not data:
                    break
                yield data
        else:
            remaining = int(total_bytes)
            while remaining > 0:
                to_read = min(remaining, chunk_size_bytes)
                data = fileobj.read(to_read)
                if not data:
                    break
                remaining -= len(data)
                yield data
