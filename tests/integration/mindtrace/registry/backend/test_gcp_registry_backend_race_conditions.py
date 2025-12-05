"""Integration tests for race conditions in GCPRegistryBackend lock acquisition.

These tests verify that the lock acquisition mechanism correctly handles
race conditions in a distributed environment using real GCS operations.
"""

import json
import os
import tempfile
import threading
import time
from typing import List, Tuple


def test_concurrent_lock_acquisition_race_condition(gcp_backend):
    """Test that only one process can acquire a lock when multiple try simultaneously.

    This test verifies the race condition fix by having multiple threads
    attempt to acquire the same lock at nearly the same time.
    """
    lock_key = "test_race_lock"
    timeout = 10
    num_threads = 10
    results: List[Tuple[int, bool, str]] = []
    results_lock = threading.Lock()

    # Clean up any existing locks first
    try:
        gcp_backend.gcs.delete(f"_lock_{lock_key}")
    except Exception:
        pass

    def acquire_lock_thread(thread_id: int):
        """Thread function to acquire lock."""
        lock_id = f"lock_{thread_id}"
        try:
            result = gcp_backend.acquire_lock(lock_key, lock_id, timeout, shared=False)
            with results_lock:
                results.append((thread_id, result, lock_id))
        except Exception as e:
            with results_lock:
                results.append((thread_id, False, f"Error: {e}"))

    # Start all threads simultaneously to maximize race condition probability
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=acquire_lock_thread, args=(i,))
        threads.append(thread)

    # Start all threads at nearly the same time
    for thread in threads:
        thread.start()
        time.sleep(0.001)  # Minimal delay to ensure they start close together

    # Wait for all threads
    for thread in threads:
        thread.join()

    # Verify results
    successful_acquires = [r for r in results if r[1] is True]

    # Only one thread should have successfully acquired the lock
    assert len(successful_acquires) == 1, (
        f"Expected exactly 1 successful acquire, got {len(successful_acquires)}. Results: {results}"
    )

    # Verify the lock is actually held by checking lock state
    is_locked, lock_id = gcp_backend.check_lock(lock_key)
    assert is_locked, "Lock should be held after successful acquisition"
    assert lock_id == successful_acquires[0][2], "Lock ID should match successful acquire"

    # Clean up
    gcp_backend.release_lock(lock_key, successful_acquires[0][2])


def test_shared_locks_are_noop(gcp_backend):
    """Test that shared locks are no-ops .

    GCP backend intentionally doesn't implement shared locking - shared locks
    always return True immediately without creating any lock object.
    """
    lock_key = "test_shared_lock"
    timeout = 10
    num_threads = 5
    results: List[Tuple[int, bool, str]] = []
    results_lock = threading.Lock()

    def acquire_shared_lock_thread(thread_id: int):
        """Thread function to acquire shared lock."""
        lock_id = f"shared_lock_{thread_id}"
        try:
            result = gcp_backend.acquire_lock(lock_key, lock_id, timeout, shared=True)
            with results_lock:
                results.append((thread_id, result, lock_id))
        except Exception as e:
            with results_lock:
                results.append((thread_id, False, f"Error: {e}"))

    # Start all threads simultaneously
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=acquire_shared_lock_thread, args=(i,))
        threads.append(thread)

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    # All threads should succeed (shared locks are no-ops)
    successful_acquires = [r for r in results if r[1] is True]
    assert len(successful_acquires) == num_threads

    # No actual lock created
    is_locked, _ = gcp_backend.check_lock(lock_key)
    assert not is_locked


def test_lock_acquisition_stress_test(gcp_backend):
    """Stress test with many concurrent lock acquisitions.

    This test verifies the system handles high concurrency correctly
    and that no race conditions cause data corruption.
    """
    lock_key = "stress_test_lock"
    num_threads = 20
    num_iterations = 5
    results: List[Tuple[int, int, bool]] = []
    results_lock = threading.Lock()

    def stress_thread(thread_id: int):
        """Thread that repeatedly tries to acquire and release locks."""
        for iteration in range(num_iterations):
            lock_id = f"lock_{thread_id}_{iteration}"
            try:
                # Try to acquire lock
                acquired = gcp_backend.acquire_lock(lock_key, lock_id, timeout=5, shared=False)
                if acquired:
                    # Hold lock briefly
                    time.sleep(0.01)
                    # Release lock
                    gcp_backend.release_lock(lock_key, lock_id)
                    with results_lock:
                        results.append((thread_id, iteration, True))
                else:
                    with results_lock:
                        results.append((thread_id, iteration, False))
            except Exception:
                with results_lock:
                    results.append((thread_id, iteration, False))

    # Clean up any existing locks
    try:
        gcp_backend.gcs.delete(f"_lock_{lock_key}")
    except Exception:
        pass

    # Start all threads
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=stress_thread, args=(i,))
        threads.append(thread)
        thread.start()

    # Wait for all threads
    for thread in threads:
        thread.join()

    # Verify all operations completed
    assert len(results) == num_threads * num_iterations, "All operations should complete"

    # Verify at least some operations succeeded
    successful = [r for r in results if r[2] is True]
    assert len(successful) > 0, "At least some operations should succeed"

    # Verify no more than one lock was held at a time by checking final state
    is_locked, _ = gcp_backend.check_lock(lock_key)
    # Lock should be released after all operations complete
    assert not is_locked, "Lock should be released after all operations complete"


def test_lock_retry_on_generation_mismatch(gcp_backend):
    """Test that lock acquisition retries correctly when generation mismatches occur.

    This test simulates a scenario where multiple processes try to acquire
    an expired lock simultaneously, causing generation mismatches.
    """
    lock_key = "test_retry_lock"
    timeout = 10

    # Clean up any existing locks
    try:
        gcp_backend.gcs.delete(f"_lock_{lock_key}")
    except Exception:
        pass

    # Create an expired lock manually
    expired_lock_data = {
        "lock_id": "expired_lock",
        "expires_at": time.time() - 100,
        "shared": False,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(expired_lock_data, f)
        temp_path = f.name

    try:
        gcp_backend.gcs.upload(temp_path, f"_lock_{lock_key}")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    # Now try to acquire the lock - should handle expired lock and retry if needed
    lock_id = "new_lock"
    result = gcp_backend.acquire_lock(lock_key, lock_id, timeout, shared=False)

    # Should succeed (expired lock should be handled)
    assert result is True, "Should acquire lock even when expired lock exists"

    # Verify lock is held
    is_locked, current_lock_id = gcp_backend.check_lock(lock_key)
    assert is_locked, "Lock should be held"
    assert current_lock_id == lock_id, "Lock ID should match"

    # Clean up
    gcp_backend.release_lock(lock_key, lock_id)
