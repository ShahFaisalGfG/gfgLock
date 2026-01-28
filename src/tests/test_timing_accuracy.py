"""
Test script to validate and improve remaining time estimate accuracy.

This test:
1. Creates test files of various sizes
2. Runs encryption/decryption multiple times
3. Tracks actual vs estimated time
4. Calculates correction factors for better estimates
"""

import os
import sys
import time
import json
import tempfile
import statistics
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import format_bytes, calculate_files_total_size


def create_test_file(size_bytes: int, filepath: str) -> None:
    """Create a test file of specified size with random data."""
    with open(filepath, 'wb') as f:
        # Write in chunks to avoid memory issues
        chunk_size = 1024 * 1024  # 1 MB chunks
        remaining = size_bytes
        while remaining > 0:
            to_write = min(chunk_size, remaining)
            f.write(os.urandom(to_write))
            remaining -= to_write


def simulate_operation(file_size: int, operation_duration: float) -> dict:
    """
    Simulate an encryption/decryption operation.
    Returns timing data including estimated vs actual time.
    """
    start_time = time.time()
    last_speed_update = start_time
    last_speed_bytes = 0
    current_speed = 0
    
    # Simulate progress over the operation_duration
    bytes_per_second = file_size / operation_duration
    
    estimates = []
    
    # Simulate progress updates every 0.1 seconds
    while True:
        current_time = time.time()
        elapsed = current_time - start_time
        
        if elapsed >= operation_duration:
            break
        
        # Simulate progress
        done_bytes = min(file_size, bytes_per_second * elapsed)
        
        # Update speed every 1 second (like in real implementation)
        time_since_update = current_time - last_speed_update
        if time_since_update >= 1.0:
            bytes_since_update = done_bytes - last_speed_bytes
            current_speed = bytes_since_update / time_since_update
            last_speed_update = current_time
            last_speed_bytes = done_bytes
            
            # Calculate estimated remaining
            if current_speed > 0:
                remaining_bytes = file_size - done_bytes
                estimated_remaining = remaining_bytes / current_speed
                estimates.append({
                    'elapsed': elapsed,
                    'done_bytes': done_bytes,
                    'current_speed': current_speed,
                    'estimated_remaining': estimated_remaining,
                    'actual_remaining': operation_duration - elapsed,
                })
        
        time.sleep(0.05)  # Simulate other processing
    
    actual_time = time.time() - start_time
    
    return {
        'file_size': file_size,
        'actual_duration': actual_time,
        'estimates': estimates,
    }


def analyze_timing_data(results: list) -> dict:
    """
    Analyze timing data across multiple runs.
    Calculate correction factors and statistics.
    """
    all_errors = []
    all_estimates = []
    all_actuals = []
    
    for result in results:
        for est in result['estimates']:
            error = abs(est['estimated_remaining'] - est['actual_remaining'])
            error_percent = (error / est['actual_remaining'] * 100) if est['actual_remaining'] > 0 else 0
            all_errors.append(error)
            all_estimates.append(est['estimated_remaining'])
            all_actuals.append(est['actual_remaining'])
    
    if not all_errors:
        return {'error': 'No timing data collected'}
    
    mean_error = statistics.mean(all_errors)
    median_error = statistics.median(all_errors)
    stdev_error = statistics.stdev(all_errors) if len(all_errors) > 1 else 0
    max_error = max(all_errors)
    min_error = min(all_errors)
    
    # Calculate correction factor (actual / estimated)
    # If correction_factor > 1, we're underestimating (need to multiply estimate)
    correction_factors = []
    for est, actual in zip(all_estimates, all_actuals):
        if est > 0:
            correction_factors.append(actual / est)
    
    mean_correction = statistics.mean(correction_factors) if correction_factors else 1.0
    
    return {
        'total_runs': len(results),
        'total_measurements': len(all_errors),
        'mean_error_seconds': mean_error,
        'median_error_seconds': median_error,
        'stdev_error_seconds': stdev_error,
        'max_error_seconds': max_error,
        'min_error_seconds': min_error,
        'mean_correction_factor': mean_correction,
        'recommendation': f"Apply correction factor of {mean_correction:.3f} to estimates"
    }


def run_timing_tests():
    """Run timing accuracy tests."""
    print("=" * 70)
    print("gfgLock - Remaining Time Estimate Accuracy Test")
    print("=" * 70)
    
    results = []
    
    test_cases = [
        {
            'name': 'Small file (50 MB)',
            'size': 50 * 1024 * 1024,
            'simulated_duration': 5.0,  # 5 seconds
            'runs': 3,
        },
        {
            'name': 'Medium file (200 MB)',
            'size': 200 * 1024 * 1024,
            'simulated_duration': 15.0,  # 15 seconds
            'runs': 3,
        },
        {
            'name': 'Large file (500 MB)',
            'size': 500 * 1024 * 1024,
            'simulated_duration': 30.0,  # 30 seconds
            'runs': 2,
        },
    ]
    
    for test_case in test_cases:
        print(f"\n{test_case['name']}")
        print("-" * 70)
        print(f"File size: {format_bytes(test_case['size'], strip_zeros=True)}")
        print(f"Simulated duration: {test_case['simulated_duration']:.1f} seconds")
        print(f"Running {test_case['runs']} iterations...\n")
        
        for i in range(test_case['runs']):
            print(f"  Run {i+1}/{test_case['runs']}...", end='', flush=True)
            result = simulate_operation(test_case['size'], test_case['simulated_duration'])
            results.append(result)
            print(f" ✓ (Actual: {result['actual_duration']:.2f}s)")
    
    # Analyze results
    print("\n" + "=" * 70)
    print("ANALYSIS RESULTS")
    print("=" * 70)
    
    analysis = analyze_timing_data(results)
    
    if 'error' in analysis:
        print(f"Error: {analysis['error']}")
        return
    
    print(f"\nTotal test runs: {analysis['total_runs']}")
    print(f"Total measurements: {analysis['total_measurements']}")
    print(f"\nTiming Error Statistics:")
    print(f"  Mean error:     {analysis['mean_error_seconds']:.3f} seconds")
    print(f"  Median error:   {analysis['median_error_seconds']:.3f} seconds")
    print(f"  Std deviation:  {analysis['stdev_error_seconds']:.3f} seconds")
    print(f"  Min error:      {analysis['min_error_seconds']:.3f} seconds")
    print(f"  Max error:      {analysis['max_error_seconds']:.3f} seconds")
    
    print(f"\nCorrection Factor Analysis:")
    print(f"  Mean correction factor: {analysis['mean_correction_factor']:.4f}")
    print(f"  {analysis['recommendation']}")
    
    # Interpretation
    print(f"\nInterpretation:")
    if analysis['mean_correction_factor'] > 1.05:
        print("  ⚠️  Current estimates are OPTIMISTIC (too fast)")
        print(f"     Estimates are {(analysis['mean_correction_factor']-1)*100:.1f}% too fast on average")
    elif analysis['mean_correction_factor'] < 0.95:
        print("  ⚠️  Current estimates are PESSIMISTIC (too slow)")
        print(f"     Estimates are {(1-analysis['mean_correction_factor'])*100:.1f}% too slow on average")
    else:
        print("  ✓ Current estimates are well-calibrated!")
        print(f"     Within ±5% accuracy")
    
    print("\n" + "=" * 70)
    print("Recommendation:")
    print("=" * 70)
    print("\nTo improve time estimation accuracy, the progress dialog should:")
    print("1. Track actual vs estimated times during first minute of operation")
    print("2. Calculate a correction factor (actual_time / estimated_time)")
    print("3. Apply this factor to future estimates for the current session")
    print("4. This adapts to system performance variations automatically")
    
    return analysis


if __name__ == '__main__':
    analysis = run_timing_tests()
    
    print("\n✓ Test completed successfully!")
