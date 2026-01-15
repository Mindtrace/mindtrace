"""Integration tests for concurrency in GCPRegistryBackend.

These tests verify that concurrent operations are handled correctly:
- Immutable registries: Rely on atomic GCS operations for conflict detection
- Mutable registries: Use internal locking for serialization

Tests use the public push()/pull()/delete() API with acquire_lock parameter
to control locking behavior.
"""

import threading
import time
import uuid
from typing import List, Tuple

import pytest

from mindtrace.registry.core.exceptions import RegistryVersionConflict


@pytest.fixture
def test_files(gcp_temp_dir):
    """Create test files for push operations."""
    test_dir = gcp_temp_dir / "test_files"
    test_dir.mkdir()
    (test_dir / "data.txt").write_text("test data")
    return test_dir


@pytest.fixture
def test_metadata():
    """Create test metadata for push operations."""
    return {
        "class": "builtins.str",
        "materializer": "test.materializer",
        "_files": ["data.txt"],
        "hash": "abc123",
    }


class TestImmutableRegistryConcurrency:
    """Tests for immutable registry behavior (no locking, atomic operations)."""

    def test_concurrent_push_same_version_immutable(self, gcp_backend, test_files, test_metadata):
        """Test that concurrent pushes to same version with immutable registry correctly detect conflicts.

        In immutable mode (acquire_lock=False), GCS atomic operations ensure only one
        push succeeds when multiple processes try to create the same version.
        """
        object_name = f"test:concurrent-immutable-{uuid.uuid4().hex[:8]}"
        version = "1.0.0"
        num_threads = 5
        results: List[Tuple[int, str]] = []  # (thread_id, status)
        results_lock = threading.Lock()

        def push_worker(thread_id: int):
            """Thread function to push object."""
            try:
                # Create unique metadata for this thread
                meta = dict(test_metadata)
                meta["thread_id"] = thread_id

                result = gcp_backend.push(
                    object_name,
                    version,
                    test_files,
                    metadata=meta,
                    on_conflict="skip",  # Detect conflicts, don't overwrite
                    acquire_lock=False,  # Immutable mode
                )

                with results_lock:
                    if result.first().ok:
                        results.append((thread_id, "success"))
                    elif result.first().is_skipped:
                        results.append((thread_id, "skipped"))
                    else:
                        results.append((thread_id, f"error: {result.first().message}"))
            except RegistryVersionConflict:
                with results_lock:
                    results.append((thread_id, "conflict"))
            except Exception as e:
                with results_lock:
                    results.append((thread_id, f"error: {e}"))

        # Start all threads simultaneously
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=push_worker, args=(i,))
            threads.append(thread)

        for thread in threads:
            thread.start()
            time.sleep(0.001)  # Minimal stagger to increase race probability

        for thread in threads:
            thread.join()

        # Verify results: exactly one should succeed, others should be skipped/conflict
        successes = [r for r in results if r[1] == "success"]
        skipped = [r for r in results if r[1] in ("skipped", "conflict")]

        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}. Results: {results}"
        assert len(skipped) == num_threads - 1, f"Expected {num_threads - 1} skipped, got {len(skipped)}"

        # Verify object exists
        assert gcp_backend.has_object(object_name, version)[(object_name, version)]

    def test_concurrent_push_different_versions_immutable(self, gcp_backend, test_files, test_metadata):
        """Test that concurrent pushes to different versions all succeed.

        When pushing to different versions, there's no conflict - all should succeed.
        """
        object_name = f"test:concurrent-diff-{uuid.uuid4().hex[:8]}"
        num_threads = 3
        results: List[Tuple[int, str]] = []
        results_lock = threading.Lock()

        def push_worker(thread_id: int):
            """Thread function to push object with unique version."""
            try:
                version = f"1.0.{thread_id}"
                meta = dict(test_metadata)
                meta["thread_id"] = thread_id

                result = gcp_backend.push(
                    object_name,
                    version,
                    test_files,
                    metadata=meta,
                    on_conflict="skip",
                    acquire_lock=False,
                )

                with results_lock:
                    if result.first().ok:
                        results.append((thread_id, "success"))
                    else:
                        results.append((thread_id, f"failed: {result.first().message}"))
            except Exception as e:
                with results_lock:
                    results.append((thread_id, f"error: {e}"))

        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=push_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All should succeed since they're pushing to different versions
        successes = [r for r in results if r[1] == "success"]
        assert len(successes) == num_threads, (
            f"Expected {num_threads} successes, got {len(successes)}. Results: {results}"
        )

        # Verify all versions exist
        for i in range(num_threads):
            version = f"1.0.{i}"
            assert gcp_backend.has_object(object_name, version)[(object_name, version)]


class TestMutableRegistryConcurrency:
    """Tests for mutable registry behavior (with locking)."""

    def test_concurrent_push_same_version_mutable_overwrite(self, gcp_backend, test_files, test_metadata):
        """Test that concurrent pushes with overwrite are serialized via locking.

        In mutable mode (acquire_lock=True), operations are serialized via locks.
        Only one thread can hold the lock at a time. Threads that fail to acquire
        the lock will fail. At least one thread must succeed for the operation
        to be valid.
        """
        object_name = f"test:concurrent-mutable-{uuid.uuid4().hex[:8]}"
        version = "1.0.0"
        num_threads = 3
        results: List[Tuple[int, str]] = []
        results_lock = threading.Lock()

        def push_worker(thread_id: int):
            """Thread function to push object with overwrite."""
            try:
                meta = dict(test_metadata)
                meta["thread_id"] = thread_id
                meta["timestamp"] = time.time()

                result = gcp_backend.push(
                    object_name,
                    version,
                    test_files,
                    metadata=meta,
                    on_conflict="overwrite",  # Overwrite existing
                    acquire_lock=True,  # Mutable mode - required for overwrite
                )

                with results_lock:
                    if result.first().ok or result.first().is_overwritten:
                        results.append((thread_id, "success"))
                    else:
                        results.append((thread_id, f"failed: {result.first().message}"))
            except Exception as e:
                with results_lock:
                    # Lock acquisition failure is expected with concurrent access
                    if "lock" in str(e).lower():
                        results.append((thread_id, "lock_failed"))
                    else:
                        results.append((thread_id, f"error: {e}"))

        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=push_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # At least one should succeed (the lock holder)
        successes = [r for r in results if r[1] == "success"]
        lock_failures = [r for r in results if r[1] == "lock_failed"]

        assert len(successes) >= 1, f"Expected at least 1 success, got {len(successes)}. Results: {results}"
        # Remaining threads should either succeed or fail due to lock contention
        assert len(successes) + len(lock_failures) == num_threads, f"Unexpected errors. Results: {results}"

        # Verify object exists
        assert gcp_backend.has_object(object_name, version)[(object_name, version)]

    def test_concurrent_push_lock_contention(self, gcp_backend, test_files, test_metadata):
        """Test lock contention handling in mutable mode.

        When multiple threads try to acquire locks simultaneously, some may
        fail to acquire. This tests that failures are handled gracefully.
        """
        object_name = f"test:lock-contention-{uuid.uuid4().hex[:8]}"
        num_threads = 5
        results: List[Tuple[int, str]] = []
        results_lock = threading.Lock()

        def push_worker(thread_id: int):
            """Thread function to push with unique version but acquire lock."""
            try:
                version = f"1.0.{thread_id}"
                meta = dict(test_metadata)
                meta["thread_id"] = thread_id

                result = gcp_backend.push(
                    object_name,
                    version,
                    test_files,
                    metadata=meta,
                    on_conflict="skip",
                    acquire_lock=True,  # Will try to acquire locks
                )

                with results_lock:
                    if result.first().ok:
                        results.append((thread_id, "success"))
                    elif result.first().is_error:
                        results.append((thread_id, f"lock_failed: {result.first().message}"))
                    else:
                        results.append((thread_id, f"other: {result.first().message}"))
            except Exception as e:
                with results_lock:
                    results.append((thread_id, f"error: {e}"))

        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=push_worker, args=(i,))
            threads.append(thread)
            thread.start()
            time.sleep(0.001)

        for thread in threads:
            thread.join()

        # At least some should succeed
        successes = [r for r in results if r[1] == "success"]
        assert len(successes) >= 1, f"Expected at least 1 success, got {len(successes)}. Results: {results}"


class TestConcurrentPullOperations:
    """Tests for concurrent pull (read) operations."""

    def test_concurrent_pull_same_version(self, gcp_backend, test_files, test_metadata, gcp_temp_dir):
        """Test that concurrent pulls of the same version all succeed.

        Reading is inherently safe for concurrent access.
        """
        object_name = f"test:concurrent-pull-{uuid.uuid4().hex[:8]}"
        version = "1.0.0"

        # First, push an object
        gcp_backend.push(
            object_name,
            version,
            test_files,
            metadata=test_metadata,
            on_conflict="skip",
            acquire_lock=False,
        )

        num_threads = 5
        results: List[Tuple[int, str]] = []
        results_lock = threading.Lock()

        def pull_worker(thread_id: int):
            """Thread function to pull object."""
            try:
                # Each thread pulls to its own directory
                pull_dir = gcp_temp_dir / f"pull_{thread_id}"
                pull_dir.mkdir()

                result = gcp_backend.pull(
                    object_name,
                    version,
                    pull_dir,
                    acquire_lock=False,
                    metadata=[test_metadata],  # Pull requires list of dicts
                )

                with results_lock:
                    if result.first().ok:
                        results.append((thread_id, "success"))
                    else:
                        results.append((thread_id, f"failed: {result.first().message}"))
            except Exception as e:
                with results_lock:
                    results.append((thread_id, f"error: {e}"))

        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=pull_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All pulls should succeed
        successes = [r for r in results if r[1] == "success"]
        assert len(successes) == num_threads, (
            f"Expected {num_threads} successes, got {len(successes)}. Results: {results}"
        )


class TestReadWhileWrite:
    """Tests for reading while write operations are in progress."""

    def test_read_while_overwrite_in_progress(self, gcp_backend, test_files, test_metadata, gcp_temp_dir):
        """Test reading an object while it's being overwritten.

        GCS provides strong consistency, so reads should either get the old
        or the new version, never corrupted/partial data.
        """
        object_name = f"test:read-while-write-{uuid.uuid4().hex[:8]}"
        version = "1.0.0"

        # First, push initial version
        initial_metadata = dict(test_metadata)
        initial_metadata["version_tag"] = "initial"
        gcp_backend.push(
            object_name,
            version,
            test_files,
            metadata=initial_metadata,
            on_conflict="skip",
            acquire_lock=False,
        )

        # Verify initial push
        assert gcp_backend.has_object(object_name, version)[(object_name, version)]

        # Track results
        write_started = threading.Event()
        write_done = threading.Event()
        read_results: List[Tuple[int, str, dict | None]] = []  # (thread_id, status, metadata)
        results_lock = threading.Lock()

        def slow_write_worker():
            """Perform a slow overwrite operation."""
            try:
                write_started.set()
                # Create modified files for overwrite
                write_dir = gcp_temp_dir / "write_data"
                write_dir.mkdir(exist_ok=True)
                (write_dir / "data.txt").write_text("updated data - slow write")

                updated_metadata = dict(test_metadata)
                updated_metadata["version_tag"] = "updated"
                updated_metadata["_files"] = ["data.txt"]

                gcp_backend.push(
                    object_name,
                    version,
                    write_dir,
                    metadata=updated_metadata,
                    on_conflict="overwrite",
                    acquire_lock=True,
                )
            finally:
                write_done.set()

        def read_worker(thread_id: int):
            """Read object while write may be in progress."""
            try:
                # Wait for write to start
                write_started.wait(timeout=5)
                time.sleep(0.01 * thread_id)  # Stagger reads

                pull_dir = gcp_temp_dir / f"read_{thread_id}"
                pull_dir.mkdir(exist_ok=True)

                # Fetch metadata to see which version we got
                meta_result = gcp_backend.fetch_metadata(object_name, version)
                fetched_meta = meta_result.first().metadata if meta_result.first().ok else None

                result = gcp_backend.pull(
                    object_name,
                    version,
                    pull_dir,
                    acquire_lock=False,
                    metadata=[fetched_meta] if fetched_meta else [test_metadata],
                )

                with results_lock:
                    if result.first().ok:
                        read_results.append((thread_id, "success", fetched_meta))
                    else:
                        read_results.append((thread_id, f"failed: {result.first().message}", None))
            except Exception as e:
                with results_lock:
                    read_results.append((thread_id, f"error: {e}", None))

        # Start write thread
        write_thread = threading.Thread(target=slow_write_worker)
        write_thread.start()

        # Start multiple read threads
        read_threads = []
        for i in range(3):
            t = threading.Thread(target=read_worker, args=(i,))
            read_threads.append(t)
            t.start()

        # Wait for all to complete
        write_thread.join(timeout=30)
        for t in read_threads:
            t.join(timeout=10)

        # All reads should succeed (no corrupted data)
        successes = [r for r in read_results if r[1] == "success"]
        assert len(successes) == 3, f"Expected 3 successful reads, got {len(successes)}. Results: {read_results}"

        # Each read should have gotten either "initial" or "updated" version
        for thread_id, _, meta in read_results:
            if meta:
                version_tag = meta.get("version_tag")
                assert version_tag in ("initial", "updated"), (
                    f"Thread {thread_id} got unexpected version_tag: {version_tag}"
                )

    def test_read_during_initial_write(self, gcp_backend, test_files, test_metadata, gcp_temp_dir):
        """Test reading an object that doesn't exist yet while first write is in progress.

        Read should either fail with 'not found' or succeed if write completed.
        """
        object_name = f"test:read-during-create-{uuid.uuid4().hex[:8]}"
        version = "1.0.0"

        write_started = threading.Event()
        read_results: List[Tuple[int, str]] = []
        results_lock = threading.Lock()

        def write_worker():
            """Push new object."""
            write_started.set()
            gcp_backend.push(
                object_name,
                version,
                test_files,
                metadata=test_metadata,
                on_conflict="skip",
                acquire_lock=False,
            )

        def read_worker(thread_id: int):
            """Try to read object that may not exist yet."""
            try:
                write_started.wait(timeout=5)
                time.sleep(0.005 * thread_id)  # Stagger

                pull_dir = gcp_temp_dir / f"early_read_{thread_id}"
                pull_dir.mkdir(exist_ok=True)

                # Check if object exists
                exists = gcp_backend.has_object(object_name, version)[(object_name, version)]
                if not exists:
                    with results_lock:
                        read_results.append((thread_id, "not_found"))
                    return

                result = gcp_backend.pull(
                    object_name,
                    version,
                    pull_dir,
                    acquire_lock=False,
                    metadata=[test_metadata],
                )

                with results_lock:
                    if result.first().ok:
                        read_results.append((thread_id, "success"))
                    else:
                        read_results.append((thread_id, f"failed: {result.first().message}"))
            except Exception as e:
                with results_lock:
                    error_msg = str(e).lower()
                    if "not found" in error_msg or "does not exist" in error_msg:
                        read_results.append((thread_id, "not_found"))
                    else:
                        read_results.append((thread_id, f"error: {e}"))

        # Start write
        write_thread = threading.Thread(target=write_worker)
        write_thread.start()

        # Start reads immediately
        read_threads = []
        for i in range(3):
            t = threading.Thread(target=read_worker, args=(i,))
            read_threads.append(t)
            t.start()

        write_thread.join(timeout=30)
        for t in read_threads:
            t.join(timeout=10)

        # Each read should either succeed or get not_found (no errors/corruption)
        for thread_id, status in read_results:
            assert status in ("success", "not_found"), f"Thread {thread_id} got unexpected status: {status}"

        # After write completes, object should exist
        assert gcp_backend.has_object(object_name, version)[(object_name, version)]


class TestConcurrentDeleteOperations:
    """Tests for concurrent delete operations."""

    def test_concurrent_delete_different_versions(self, gcp_backend, test_files, test_metadata):
        """Test that concurrent deletes of different versions all succeed."""
        object_name = f"test:concurrent-delete-{uuid.uuid4().hex[:8]}"
        num_versions = 3

        # First, push multiple versions
        for i in range(num_versions):
            version = f"1.0.{i}"
            gcp_backend.push(
                object_name,
                version,
                test_files,
                metadata=test_metadata,
                on_conflict="skip",
                acquire_lock=False,
            )

        results: List[Tuple[int, str]] = []
        results_lock = threading.Lock()

        def delete_worker(thread_id: int):
            """Thread function to delete a version."""
            try:
                version = f"1.0.{thread_id}"
                result = gcp_backend.delete(
                    object_name,
                    version,
                    acquire_lock=False,
                )

                with results_lock:
                    if result.first().ok:
                        results.append((thread_id, "success"))
                    else:
                        results.append((thread_id, f"failed: {result.first().message}"))
            except Exception as e:
                with results_lock:
                    results.append((thread_id, f"error: {e}"))

        threads = []
        for i in range(num_versions):
            thread = threading.Thread(target=delete_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All deletes should succeed
        successes = [r for r in results if r[1] == "success"]
        assert len(successes) == num_versions, (
            f"Expected {num_versions} successes, got {len(successes)}. Results: {results}"
        )

        # Verify all versions are deleted
        for i in range(num_versions):
            version = f"1.0.{i}"
            assert not gcp_backend.has_object(object_name, version)[(object_name, version)]


class TestStressTests:
    """Stress tests for high concurrency scenarios."""

    @pytest.mark.slow
    def test_high_concurrency_push_different_objects(self, gcp_backend, test_files, test_metadata):
        """Stress test with many concurrent pushes to different objects."""
        num_threads = 10
        results: List[Tuple[int, str]] = []
        results_lock = threading.Lock()

        def push_worker(thread_id: int):
            """Thread function to push unique object."""
            try:
                object_name = f"test:stress-{uuid.uuid4().hex[:8]}"
                version = "1.0.0"
                meta = dict(test_metadata)
                meta["thread_id"] = thread_id

                result = gcp_backend.push(
                    object_name,
                    version,
                    test_files,
                    metadata=meta,
                    on_conflict="skip",
                    acquire_lock=False,
                )

                with results_lock:
                    if result.first().ok:
                        results.append((thread_id, "success"))
                    else:
                        results.append((thread_id, f"failed: {result.first().message}"))
            except Exception as e:
                with results_lock:
                    results.append((thread_id, f"error: {e}"))

        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=push_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All should succeed since they're pushing to different objects
        successes = [r for r in results if r[1] == "success"]
        assert len(successes) == num_threads, (
            f"Expected {num_threads} successes, got {len(successes)}. Results: {results}"
        )
