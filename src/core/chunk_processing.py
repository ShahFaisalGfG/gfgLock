import os
import tempfile
import uuid
import shutil
from typing import Optional

class FileChunker:
    def __init__(self, temp_dir=None):
        # If no temp_dir is provided, it uses the OS default temp folder
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.isolated_temp_dir: Optional[str] = None  # Per-operation isolated temp directory

    def _ensure_isolated_temp_dir(self):
        """Create a per-operation isolated temp directory if not already created.
        Uses a unique directory name to avoid collisions between concurrent operations.
        """
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
        """Cleanup temp directory on object destruction."""
        self.cleanup_temp_dir()

    def split_file(self, file_path, chunk_size: int) -> list:
        """
        Splits a file into small binary chunks saved to disk.
        Accepts `chunk_size` in bytes. For backward compatibility a caller
        may pass an integer representing megabytes; if the value is <= 128
        it's treated as megabytes. Otherwise it's treated as bytes.

        :param file_path: Path to the source file
        :param chunk_size: Chunk size in bytes or (small) megabytes
        :return: List of paths to the created chunk files
        """
        # allow callers to pass small integers as MB for convenience
        if isinstance(chunk_size, int) and chunk_size > 0 and chunk_size <= 128:
            chunk_size_bytes = int(chunk_size * 1024 * 1024)
        else:
            chunk_size_bytes = int(chunk_size)

        chunk_paths = []
        isolated_temp = self._ensure_isolated_temp_dir()
        
        # Open source file in Read Binary mode
        with open(file_path, 'rb') as f:
            chunk_num = 0
            while True:
                data = f.read(chunk_size_bytes)
                if not data:
                    break

                # Use simple sequential filename within isolated temp dir (fast, no mkstemp needed)
                chunk_path = os.path.join(isolated_temp, f"chunk_{chunk_num}.tmp")
                with open(chunk_path, 'wb') as chunk_file:
                    chunk_file.write(data)

                chunk_paths.append(chunk_path)
                chunk_num += 1

        return chunk_paths

    def merge_chunks(self, processed_chunk_paths, output_file_path):
        """
        Combines processed chunks back into a single file.
        :param processed_chunk_paths: List of paths to the (encrypted/decrypted) chunks
        :param output_file_path: Where to save the final reconstructed file
        """
        with open(output_file_path, 'wb') as output_file:
            for chunk_path in processed_chunk_paths:
                if os.path.exists(chunk_path):
                    with open(chunk_path, 'rb') as f:
                        # Use a small internal buffer (e.g., 64KB) to merge files without RAM spikes
                        while True:
                            buffer = f.read(64 * 1024)
                            if not buffer:
                                break
                            output_file.write(buffer)
                    
                    # Optional: Delete the chunk after merging to save disk space
                    try:
                        os.remove(chunk_path)
                    except Exception:
                        pass

    def split_stream(self, fileobj, total_bytes: int, chunk_size: int) -> list:
        """
        Read `total_bytes` from an open binary file-like object `fileobj`
        and write it out into temporary chunk files of up to `chunk_size` bytes.
        Returns list of chunk file paths in order.
        The fileobj's current position will be advanced by `total_bytes`.
        """
        if isinstance(chunk_size, int) and chunk_size > 0 and chunk_size <= 128:
            chunk_size_bytes = int(chunk_size * 1024 * 1024)
        else:
            chunk_size_bytes = int(chunk_size)

        paths = []
        remaining = int(total_bytes)
        isolated_temp = self._ensure_isolated_temp_dir()
        idx = 0
        
        while remaining > 0:
            to_read = min(remaining, chunk_size_bytes)
            data = fileobj.read(to_read)
            if not data:
                break
            
            # Use simple sequential filename within isolated temp dir (fast)
            tmp_name = os.path.join(isolated_temp, f"stream_chunk_{idx}.tmp")
            with open(tmp_name, 'wb') as tf:
                tf.write(data)
            
            paths.append(tmp_name)
            remaining -= len(data)
            idx += 1
        
        return paths

    def stream_chunks(self, fileobj, total_bytes=None, chunk_size=64*1024):
        """
        Generator that yields up to `chunk_size` bytes from `fileobj`.
        If `total_bytes` is provided, it will yield at most that many bytes
        (useful for reading a section of a file). Otherwise it yields until EOF.
        This avoids creating temp files and supports true streaming.
        """
        if isinstance(chunk_size, int) and chunk_size > 0 and chunk_size <= 128:
            # treat small ints as MB for backward compatibility
            chunk_size_bytes = chunk_size * 1024 * 1024
        else:
            chunk_size_bytes = int(chunk_size)

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