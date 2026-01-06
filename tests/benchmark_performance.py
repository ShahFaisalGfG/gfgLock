#!/usr/bin/env python3
"""
Comprehensive performance benchmark script for gfgLock encryption algorithms.
Tests all three algorithms with various file sizes and chunk settings.
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core import aes256_gcm_cfb
from core import chacha20_poly1305


class BenchmarkConfig:
    """Configuration for benchmark runs."""
    PASSWORD = "test_password_12345"
    TEMP_DIR: str | None = None
    CHUNK_SIZES = [
        (None, "Off (no chunking)"),
        (1024 * 1024, "1 MB chunks"),
        (8 * 1024 * 1024, "8 MB chunks"),
        (32 * 1024 * 1024, "32 MB chunks"),
    ]
    FILE_SIZES = [
        (1024 * 100, "100 KB"),
        (1024 * 1024, "1 MB"),
        (10 * 1024 * 1024, "10 MB"),
        (50 * 1024 * 1024, "50 MB"),
        (100 * 1024 * 1024, "100 MB"),
    ]


def create_test_file(size_bytes, name="test_file"):
    """Create a test file filled with random data."""
    if BenchmarkConfig.TEMP_DIR is None:
        raise ValueError("TEMP_DIR is not initialized")
    path = os.path.join(BenchmarkConfig.TEMP_DIR, name)
    with open(path, 'wb') as f:
        chunk = os.urandom(min(1024 * 1024, size_bytes))
        remaining = size_bytes
        while remaining > 0:
            to_write = min(len(chunk), remaining)
            f.write(chunk[:to_write])
            remaining -= to_write
    return path


def cleanup_file(path):
    """Securely remove test file."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        pass


def find_encrypted_file(base_path):
    """Find the encrypted file that was created from base_path."""
    for ext in ['.gfglock', '.gfglck', '.gfgcha']:
        candidate = base_path + ext
        if os.path.exists(candidate):
            return candidate
    return None


def run_benchmark_suite():
    """Run complete benchmark suite for all algorithms."""
    print("=" * 100)
    print("gfgLock Encryption Performance Benchmark Suite".center(100))
    print("=" * 100)
    print()
    
    algorithms = [
        ("AES-256 GCM", aes256_gcm_cfb.encrypt_file, aes256_gcm_cfb.decrypt_file, True),
        ("AES-256 CFB", aes256_gcm_cfb.encrypt_file, aes256_gcm_cfb.decrypt_file, False),
        ("ChaCha20-Poly1305", chacha20_poly1305.encrypt_file, chacha20_poly1305.decrypt_file, None),
    ]
    
    results = {}
    
    for algo_name, enc_func, dec_func, aead_param in algorithms:
        print(f"\n{'Algorithm: ' + algo_name:^100}")
        print("-" * 100)
        
        algo_results = {}
        
        for file_size, size_label in BenchmarkConfig.FILE_SIZES:
            print(f"\n  File Size: {size_label:>15} | {'Chunk Config':<25} | {'Enc (s)':<10} | {'Speed (MB/s)':<12} | {'Dec (s)':<10} | {'Speed (MB/s)':<12}")
            print(f"  {'-' * 98}")
            
            size_results = {}
            
            for chunk_size, chunk_label in BenchmarkConfig.CHUNK_SIZES:
                # Create test file with unique name per test
                test_file_base = f"test_{size_label.replace(' ', '_').replace('/', '_')}_{chunk_label.replace(' ', '_')}"
                test_file = create_test_file(file_size, test_file_base)
                
                try:
                    # Encryption
                    start = time.time()
                    if aead_param is not None:
                        # AES variants - pass AEAD parameter
                        success, msg = enc_func(test_file, BenchmarkConfig.PASSWORD, 
                                               encrypt_name=False, chunk_size=chunk_size, AEAD=aead_param)
                    else:
                        # ChaCha20 - no AEAD parameter needed
                        success, msg = enc_func(test_file, BenchmarkConfig.PASSWORD,
                                               encrypt_name=False, chunk_size=chunk_size)
                    enc_time = time.time() - start
                    
                    if not success:
                        print(f"  {'':15} | {chunk_label:<25} | ERROR during encryption")
                        cleanup_file(test_file)
                        continue
                    
                    # Find encrypted file
                    encrypted_file = find_encrypted_file(test_file)
                    if not encrypted_file:
                        print(f"  {'':15} | {chunk_label:<25} | ERROR: encrypted file not found")
                        cleanup_file(test_file)
                        continue
                    
                    enc_size = os.path.getsize(encrypted_file)
                    enc_speed = (enc_size / 1024 / 1024) / enc_time if enc_time > 0 else 0
                    
                    # Decryption
                    start = time.time()
                    success, msg = dec_func(encrypted_file, BenchmarkConfig.PASSWORD, chunk_size=chunk_size)
                    dec_time = time.time() - start
                    
                    if not success:
                        print(f"  {'':15} | {chunk_label:<25} | {enc_time:>8.4f}s | {enc_speed:>10.2f}   | ERROR during decryption")
                        cleanup_file(test_file)
                        cleanup_file(encrypted_file)
                        continue
                    
                    # Find decrypted file
                    decrypted_file = test_file[:-len(test_file_base)] + os.path.basename(test_file)
                    dec_speed = (file_size / 1024 / 1024) / dec_time if dec_time > 0 else 0
                    
                    print(f"  {size_label:>15} | {chunk_label:<25} | {enc_time:>8.4f}s | {enc_speed:>10.2f}   | {dec_time:>8.4f}s | {dec_speed:>10.2f}")
                    
                    size_results[chunk_label] = {
                        'enc_time': enc_time,
                        'enc_speed': enc_speed,
                        'dec_time': dec_time,
                        'dec_speed': dec_speed,
                    }
                    
                except Exception as e:
                    print(f"  {'':15} | {chunk_label:<25} | EXCEPTION: {str(e)[:40]}")
                
                finally:
                    # Clean up all related files
                    cleanup_file(test_file)
                    cleanup_file(test_file + '.gfglock')
                    cleanup_file(test_file + '.gfglck')
                    cleanup_file(test_file + '.gfgcha')
            
            algo_results[size_label] = size_results
        
        results[algo_name] = algo_results
    
    # Print summary
    print("\n" + "=" * 100)
    print("PERFORMANCE SUMMARY".center(100))
    print("=" * 100)
    
    for algo_name, algo_results in results.items():
        print(f"\n{algo_name:^100}")
        print("-" * 100)
        
        total_enc_speed = 0
        total_dec_speed = 0
        count = 0
        
        for size_label, size_results in algo_results.items():
            for chunk_label, metrics in size_results.items():
                total_enc_speed += metrics['enc_speed']
                total_dec_speed += metrics['dec_speed']
                count += 1
        
        if count > 0:
            avg_enc_speed = total_enc_speed / count
            avg_dec_speed = total_dec_speed / count
            print(f"  Average Encryption Speed: {avg_enc_speed:.2f} MB/s")
            print(f"  Average Decryption Speed: {avg_dec_speed:.2f} MB/s")
            print(f"  Tests Completed:  {count}/{len(BenchmarkConfig.FILE_SIZES) * len(BenchmarkConfig.CHUNK_SIZES)}")
    
    print("\n" + "=" * 100)
    print("Optimization Notes:".center(100))
    print("-" * 100)
    print("  • BUFFER_SIZE set to 64KB for optimal I/O performance on modern SSDs")
    print("  • Small files (<10MB) automatically use non-chunked mode regardless of chunk_size setting")
    print("  • Chunked mode uses max(chunk_size, BUFFER_SIZE) for better disk I/O efficiency")
    print("  • Hardware acceleration enabled via cryptography + OpenSSL and pycryptodome")
    print("=" * 100)


def main():
    """Main entry point."""
    BenchmarkConfig.TEMP_DIR = tempfile.mkdtemp(prefix="gfglock_bench_")
    
    try:
        print(f"Using temporary directory: {BenchmarkConfig.TEMP_DIR}\n")
        run_benchmark_suite()
    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user.")
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            if BenchmarkConfig.TEMP_DIR and os.path.exists(BenchmarkConfig.TEMP_DIR):
                shutil.rmtree(BenchmarkConfig.TEMP_DIR)
                print(f"\nCleaned up temporary directory")
        except Exception as e:
            print(f"\nWarning: could not remove temporary directory: {e}")


if __name__ == "__main__":
    main()
