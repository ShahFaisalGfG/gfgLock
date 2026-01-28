#!/usr/bin/env python3
"""
Comprehensive performance benchmark for gfgLock encryption algorithms.
Measures encryption/decryption speed for AES-GCM, AES-CFB, and ChaCha20-Poly1305.
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
import statistics

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core import aes256_gcm_cfb as aes_core
from core import chacha20_poly1305 as chacha_core
from utils import safe_print


class BenchmarkResult:
    """Store and format benchmark results."""
    def __init__(self, algorithm: str, mode: str, file_size: int, chunk_size: int, threads: int):
        self.algorithm = algorithm
        self.mode = mode
        self.file_size = file_size
        self.chunk_size = chunk_size
        self.threads = threads
        self.enc_times: List[float] = []
        self.dec_times: List[float] = []
        self.enc_speed_mbps: List[float] = []  # MB/s
        self.dec_speed_mbps: List[float] = []
    
    def add_encryption(self, elapsed: float):
        """Add encryption time in seconds."""
        self.enc_times.append(elapsed)
        mbps = (self.file_size / (1024 * 1024)) / elapsed if elapsed > 0 else 0
        self.enc_speed_mbps.append(mbps)
    
    def add_decryption(self, elapsed: float):
        """Add decryption time in seconds."""
        self.dec_times.append(elapsed)
        mbps = (self.file_size / (1024 * 1024)) / elapsed if elapsed > 0 else 0
        self.dec_speed_mbps.append(mbps)
    
    def avg_enc_time(self) -> float:
        return statistics.mean(self.enc_times) if self.enc_times else 0
    
    def avg_dec_time(self) -> float:
        return statistics.mean(self.dec_times) if self.dec_times else 0
    
    def avg_enc_speed(self) -> float:
        return statistics.mean(self.enc_speed_mbps) if self.enc_speed_mbps else 0
    
    def avg_dec_speed(self) -> float:
        return statistics.mean(self.dec_speed_mbps) if self.dec_speed_mbps else 0
    
    def stdev_enc(self) -> float:
        return statistics.stdev(self.enc_times) if len(self.enc_times) > 1 else 0
    
    def stdev_dec(self) -> float:
        return statistics.stdev(self.dec_times) if len(self.dec_times) > 1 else 0
    
    def __str__(self) -> str:
        size_mb = self.file_size / (1024 * 1024)
        chunk_str = f"{self.chunk_size}MB" if self.chunk_size else "no-chunk"
        
        enc_avg = self.avg_enc_time()
        dec_avg = self.avg_dec_time()
        enc_speed = self.avg_enc_speed()
        dec_speed = self.avg_dec_speed()
        enc_stdev = self.stdev_enc()
        dec_stdev = self.stdev_dec()
        
        return (
            f"{self.algorithm:15} | {size_mb:7.1f}MB | {chunk_str:12} | threads={self.threads} | "
            f"ENC: {enc_avg:6.2f}s ({enc_speed:6.1f}MB/s ±{enc_stdev:.2f}s) | "
            f"DEC: {dec_avg:6.2f}s ({dec_speed:6.1f}MB/s ±{dec_stdev:.2f}s)"
        )


class PerformanceBenchmark:
    """Run comprehensive performance benchmarks."""
    
    def __init__(self, test_dir: str = None, password: str = "testpassword123"): # type: ignore
        self.test_dir = test_dir or tempfile.mkdtemp(prefix="gfglock_bench_")
        self.password = password
        self.results: List[BenchmarkResult] = []
        self.test_files: Dict[int, str] = {}  # file_size -> path
        safe_print(f"[BENCH] Test directory: {self.test_dir}")
    
    def generate_test_file(self, size_mb: int) -> str:
        """Generate a test file of specified size in MB."""
        if size_mb in self.test_files and os.path.exists(self.test_files[size_mb]):
            return self.test_files[size_mb]
        
        file_path = os.path.join(self.test_dir, f"test_{size_mb}mb.bin")
        if os.path.exists(file_path):
            return file_path
        
        safe_print(f"[BENCH] Generating {size_mb}MB test file...")
        chunk_size = 10 * 1024 * 1024  # 10MB chunks for generation
        remaining = size_mb * 1024 * 1024
        
        with open(file_path, 'wb') as f:
            while remaining > 0:
                to_write = min(chunk_size, remaining)
                f.write(os.urandom(to_write))
                remaining -= to_write
        
        self.test_files[size_mb] = file_path
        return file_path
    
    def benchmark_encrypt_decrypt(self, algorithm: str, file_size_mb: int, 
                                   chunk_size_mb: int = None, threads: int = 1,  # type: ignore
                                   runs: int = 1) -> Tuple[bool, BenchmarkResult]:
        """Benchmark encryption and decryption for a specific algorithm."""
        test_file = self.generate_test_file(file_size_mb)
        result = BenchmarkResult(algorithm, "encrypt/decrypt", 
                                file_size_mb * 1024 * 1024, 
                                chunk_size_mb, threads)
        
        safe_print(f"[BENCH] {algorithm} | {file_size_mb}MB | chunk={chunk_size_mb}MB | threads={threads} | runs={runs}")
        
        for run in range(runs):
            # Create a fresh copy of test file for this run
            work_dir = os.path.join(self.test_dir, f"run_{algorithm}_{file_size_mb}_{run}")
            os.makedirs(work_dir, exist_ok=True)
            work_file = os.path.join(work_dir, f"test.bin")
            
            try:
                shutil.copy(test_file, work_file)
                
                # Encryption
                enc_start = time.time()
                if algorithm == "aes256_gcm":
                    success, msg = aes_core.encrypt_file(work_file, self.password, 
                                                         encrypt_name=False, 
                                                         chunk_size=chunk_size_mb,
                                                         AEAD=True)
                    encrypted_ext = '.gfglock'
                elif algorithm == "aes256_cfb":
                    success, msg = aes_core.encrypt_file(work_file, self.password,
                                                         encrypt_name=False,
                                                         chunk_size=chunk_size_mb,
                                                         AEAD=False)
                    encrypted_ext = '.gfglck'
                elif algorithm == "chacha20_poly1305":
                    success, msg = chacha_core.encrypt_file(work_file, self.password,
                                                            encrypt_name=False,
                                                            chunk_size=chunk_size_mb)
                    encrypted_ext = '.gfgcha'
                else:
                    safe_print(f"[BENCH] Unknown algorithm: {algorithm}")
                    return False, result
                
                enc_time = time.time() - enc_start
                
                if not success:
                    safe_print(f"[BENCH] Encryption failed: {msg}")
                    return False, result
                
                # Find the encrypted file (name depends on encrypt_name setting)
                encrypted_file = work_file.replace('.bin', encrypted_ext)
                if not os.path.exists(encrypted_file):
                    safe_print(f"[BENCH] Encrypted file not found: {encrypted_file}")
                    return False, result
                
                result.add_encryption(enc_time)
                safe_print(f"  Run {run+1}/{runs}: ENC {enc_time:.2f}s ({(file_size_mb * 1024 * 1024 / (1024*1024)) / enc_time:.1f}MB/s)")
                
                # Decryption
                dec_start = time.time()
                if algorithm == "aes256_gcm":
                    success, msg = aes_core.decrypt_file(encrypted_file, self.password,
                                                         chunk_size=chunk_size_mb)
                elif algorithm == "aes256_cfb":
                    success, msg = aes_core.decrypt_file(encrypted_file, self.password,
                                                         chunk_size=chunk_size_mb)
                elif algorithm == "chacha20_poly1305":
                    success, msg = chacha_core.decrypt_file(encrypted_file, self.password,
                                                            chunk_size=chunk_size_mb)
                
                dec_time = time.time() - dec_start
                
                if not success:
                    safe_print(f"[BENCH] Decryption failed: {msg}")
                    return False, result
                
                result.add_decryption(dec_time)
                safe_print(f"  Run {run+1}/{runs}: DEC {dec_time:.2f}s ({(file_size_mb * 1024 * 1024 / (1024*1024)) / dec_time:.1f}MB/s)")
            
            except Exception as e:
                safe_print(f"[BENCH] Benchmark error: {e}")
                return False, result
            
            finally:
                # Cleanup run directory
                try:
                    if os.path.exists(work_dir):
                        shutil.rmtree(work_dir)
                except Exception as e:
                    safe_print(f"[BENCH] Cleanup error: {e}")
        
        self.results.append(result)
        return True, result
    
    def print_summary(self):
        """Print a formatted summary of all results."""
        safe_print("\n" + "="*180)
        safe_print("PERFORMANCE BENCHMARK SUMMARY")
        safe_print("="*180)
        safe_print(f"{'Algorithm':15} | {'File Size':>7} | {'Chunk Size':>12} | {'Threads':>8} | {'Encryption':>35} | {'Decryption':>35}")
        safe_print("-"*180)
        
        for result in self.results:
            safe_print(str(result))
        
        safe_print("="*180)
        safe_print("Legend: ENC/DEC times in seconds, Speed in MB/s, ± shows standard deviation\n")
    
    def cleanup(self):
        """Clean up test directory."""
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
                safe_print(f"[BENCH] Cleaned up test directory")
            except Exception as e:
                safe_print(f"[BENCH] Cleanup error: {e}")


def main():
    """Run comprehensive benchmark suite."""
    safe_print("[BENCH] Starting gfgLock performance benchmark...")
    
    bench = PerformanceBenchmark()
    
    try:
        # Test configurations: (file_size_mb, chunk_size_mb, threads, runs)
        test_configs = [
            # Small file benchmark (no chunking)
            (50, None, 1, 2),
            
            # Medium file benchmarks
            (100, 32, 1, 2),
            (100, 32, 2, 2),
            (100, 32, 4, 2),
            
            # Larger file benchmarks (matching real-world scenario)
            (200, 32, 1, 1),
            (200, 32, 4, 1),
        ]
        
        algorithms = ["aes256_gcm", "aes256_cfb", "chacha20_poly1305"]
        
        for algo in algorithms:
            safe_print(f"\n[BENCH] Benchmarking {algo}...")
            for file_size, chunk_size, threads, runs in test_configs:
                success, result = bench.benchmark_encrypt_decrypt(
                    algo, file_size, chunk_size, threads, runs
                )
                if not success:
                    safe_print(f"[BENCH] Skipping remaining tests for {algo}")
                    break
        
        # Print summary
        bench.print_summary()
        
    finally:
        bench.cleanup()


if __name__ == "__main__":
    main()
