"""
Stress tests for Registry maximum throughput and concurrent access testing.

This module tests the Registry under high load to determine its maximum
throughput and performance characteristics under stress conditions.
"""

import json
import logging
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from tempfile import TemporaryDirectory

import pytest
from tqdm import tqdm

from mindtrace.registry import LocalRegistryBackend, Registry

# Suppress verbose logging during stress tests
logging.getLogger("mindtrace.registry").setLevel(logging.WARNING)
logging.getLogger("zenml").setLevel(logging.WARNING)

# For even cleaner output during stress tests, uncomment the following line:
# logging.getLogger().setLevel(logging.CRITICAL)


class TestRegistryThroughput:
    """Stress tests for Registry maximum throughput."""

    @pytest.fixture
    def temp_registry_dir(self):
        """Create a temporary directory for registry storage."""
        with TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def registry(self, temp_registry_dir):
        """Create a Registry instance with a temporary directory."""
        return Registry(registry_dir=temp_registry_dir)

    @pytest.fixture
    def test_objects(self):
        """Create test objects of various types and sizes."""
        return {
            "small_string": "test",
            "medium_string": "test_string_" * 50,
            "large_string": "large_test_string_" * 1000,
            "small_int": 42,
            "large_int": 999999999,
            "float_val": 3.14159,
            "bool_val": True,
            "small_list": [1, 2, 3, 4, 5],
            "large_list": list(range(1000)),
            "small_dict": {"a": 1, "b": 2, "c": 3},
            "large_dict": {f"key_{i}": f"value_{i}" for i in range(500)},
        }

    @pytest.mark.slow
    def test_sequential_save_load_throughput(self, registry, test_objects):
        """
        Test sequential save/load throughput to establish baseline performance.
        """
        iterations = 100
        save_times = []
        load_times = []
        successful_saves = 0
        successful_loads = 0
        failed_operations = 0

        # Use a single object type for consistent testing
        test_obj = test_objects["medium_string"]

        print(f"\nStarting sequential save/load throughput test ({iterations} iterations)")
        start_time = time.time()

        with tqdm(total=iterations * 2, desc="Sequential operations", file=sys.stderr) as pbar:
            for i in range(iterations):
                obj_name = f"test:obj:{i}"
                
                # Save operation
                save_start = time.time()
                try:
                    registry.save(obj_name, test_obj)
                    save_end = time.time()
                    save_times.append(save_end - save_start)
                    successful_saves += 1
                except Exception as e:
                    failed_operations += 1
                    print(f"Save {i} failed: {e}")
                pbar.update(1)

                # Load operation
                load_start = time.time()
                try:
                    loaded_obj = registry.load(obj_name)
                    load_end = time.time()
                    assert loaded_obj == test_obj
                    load_times.append(load_end - load_start)
                    successful_loads += 1
                except Exception as e:
                    failed_operations += 1
                    print(f"Load {i} failed: {e}")
                pbar.update(1)

                # Update progress
                if i % 10 == 0:
                    pbar.set_postfix({
                        "saves": successful_saves,
                        "loads": successful_loads,
                        "failed": failed_operations,
                        "save_avg_ms": f"{mean(save_times[-10:]) * 1000:.1f}" if save_times else "0",
                        "load_avg_ms": f"{mean(load_times[-10:]) * 1000:.1f}" if load_times else "0",
                    })

        total_time = time.time() - start_time
        total_operations = successful_saves + successful_loads

        # Calculate metrics
        save_throughput = successful_saves / total_time
        load_throughput = successful_loads / total_time
        overall_throughput = total_operations / total_time
        
        avg_save_time = mean(save_times) if save_times else 0
        avg_load_time = mean(load_times) if load_times else 0
        
        p95_save_time = sorted(save_times)[int(0.95 * len(save_times))] if save_times else 0
        p95_load_time = sorted(load_times)[int(0.95 * len(load_times))] if load_times else 0

        print("\nSequential throughput test completed:")
        print(f"   - Total operations: {iterations * 2}")
        print(f"   - Successful saves: {successful_saves}")
        print(f"   - Successful loads: {successful_loads}")
        print(f"   - Failed operations: {failed_operations}")
        print(f"   - Success rate: {(total_operations / (iterations * 2)) * 100:.1f}%")
        print(f"   - Total time: {total_time:.2f}s")
        print(f"   - Save throughput: {save_throughput:.1f} ops/sec")
        print(f"   - Load throughput: {load_throughput:.1f} ops/sec")
        print(f"   - Overall throughput: {overall_throughput:.1f} ops/sec")
        print(f"   - Avg save time: {avg_save_time * 1000:.1f}ms")
        print(f"   - Avg load time: {avg_load_time * 1000:.1f}ms")
        print(f"   - 95th percentile save: {p95_save_time * 1000:.1f}ms")
        print(f"   - 95th percentile load: {p95_load_time * 1000:.1f}ms")

        # Assertions
        assert total_operations > (iterations * 2) * 0.95, f"Success rate too low: {total_operations}/{iterations * 2}"
        assert overall_throughput > 5, f"Throughput too low: {overall_throughput:.1f} ops/sec"

    @pytest.mark.slow
    def test_concurrent_save_load_throughput(self, registry, test_objects):
        """
        Test concurrent save/load throughput to find maximum concurrent capacity.
        """
        max_workers = 10
        operations_per_worker = 20
        total_operations = max_workers * operations_per_worker

        # Use medium string for consistent testing
        test_obj = test_objects["medium_string"]

        # Results tracking with thread-safe counters
        results = {"successful_saves": 0, "successful_loads": 0, "failed": 0, "save_times": [], "load_times": []}
        results_lock = threading.Lock()
        completed_counter = {"count": 0}
        counter_lock = threading.Lock()

        def worker_function(worker_id):
            """Worker function for concurrent save/load operations."""
            worker_results = {"successful_saves": 0, "successful_loads": 0, "failed": 0, "save_times": [], "load_times": []}

            for i in range(operations_per_worker):
                obj_name = f"concurrent:obj:{worker_id}:{i}"
                
                # Save operation
                save_start = time.time()
                try:
                    registry.save(obj_name, test_obj)
                    save_end = time.time()
                    worker_results["save_times"].append(save_end - save_start)
                    worker_results["successful_saves"] += 1
                except Exception as e:
                    worker_results["failed"] += 1
                    print(f"Worker {worker_id} save {i} failed: {e}")

                # Load operation  
                load_start = time.time()
                try:
                    loaded_obj = registry.load(obj_name)
                    load_end = time.time()
                    assert loaded_obj == test_obj
                    worker_results["load_times"].append(load_end - load_start)
                    worker_results["successful_loads"] += 1
                except Exception as e:
                    worker_results["failed"] += 1
                    print(f"Worker {worker_id} load {i} failed: {e}")

                # Update counter for progress
                with counter_lock:
                    completed_counter["count"] += 2  # 2 operations per iteration

            # Merge worker results
            with results_lock:
                results["successful_saves"] += worker_results["successful_saves"]
                results["successful_loads"] += worker_results["successful_loads"]
                results["failed"] += worker_results["failed"]
                results["save_times"].extend(worker_results["save_times"])
                results["load_times"].extend(worker_results["load_times"])

        print(f"\nStarting concurrent save/load throughput test ({max_workers} workers × {operations_per_worker} ops × 2)")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker_function, i) for i in range(max_workers)]

            # Track progress
            with tqdm(total=total_operations * 2, desc="Concurrent operations", file=sys.stderr) as pbar:
                last_completed = 0
                while any(not f.done() for f in futures):
                    time.sleep(0.1)
                    
                    with counter_lock:
                        current_completed = completed_counter["count"]
                    
                    if current_completed > last_completed:
                        pbar.update(current_completed - last_completed)
                        last_completed = current_completed
                    
                    active_workers = sum(1 for f in futures if not f.done())
                    pbar.set_postfix({"completed": current_completed, "active_workers": active_workers})

                # Final update
                with counter_lock:
                    final_completed = completed_counter["count"]
                if final_completed > last_completed:
                    pbar.update(final_completed - last_completed)

            # Wait for all workers to complete
            for future in futures:
                future.result()

        total_time = time.time() - start_time
        total_successful = results["successful_saves"] + results["successful_loads"]
        
        # Calculate metrics
        save_throughput = results["successful_saves"] / total_time
        load_throughput = results["successful_loads"] / total_time
        overall_throughput = total_successful / total_time
        
        avg_save_time = mean(results["save_times"]) if results["save_times"] else 0
        avg_load_time = mean(results["load_times"]) if results["load_times"] else 0
        
        p95_save_time = sorted(results["save_times"])[int(0.95 * len(results["save_times"]))] if results["save_times"] else 0
        p95_load_time = sorted(results["load_times"])[int(0.95 * len(results["load_times"]))] if results["load_times"] else 0

        print("\nConcurrent save/load throughput test completed:")
        print(f"   - Total operations: {total_operations * 2}")
        print(f"   - Concurrent workers: {max_workers}")
        print(f"   - Successful saves: {results['successful_saves']}")
        print(f"   - Successful loads: {results['successful_loads']}")
        print(f"   - Failed operations: {results['failed']}")
        print(f"   - Success rate: {(total_successful / (total_operations * 2)) * 100:.1f}%")
        print(f"   - Total time: {total_time:.2f}s")
        print(f"   - Save throughput: {save_throughput:.1f} ops/sec")
        print(f"   - Load throughput: {load_throughput:.1f} ops/sec")
        print(f"   - Overall throughput: {overall_throughput:.1f} ops/sec")
        print(f"   - Avg save time: {avg_save_time * 1000:.1f}ms")
        print(f"   - Avg load time: {avg_load_time * 1000:.1f}ms")
        print(f"   - 95th percentile save: {p95_save_time * 1000:.1f}ms")
        print(f"   - 95th percentile load: {p95_load_time * 1000:.1f}ms")

        # Assertions
        assert total_successful > (total_operations * 2) * 0.90, f"Success rate too low: {total_successful}/{total_operations * 2}"
        assert overall_throughput > 5, f"Concurrent throughput too low: {overall_throughput:.1f} ops/sec"

    @pytest.mark.slow
    def test_mixed_operations_stress(self, registry, test_objects):
        """
        Test mixed operations (save/load/delete/info) under concurrent load.
        """
        max_workers = 8
        operations_per_worker = 25
        total_operations = max_workers * operations_per_worker

        # Results tracking
        results = {"saves": 0, "loads": 0, "deletes": 0, "infos": 0, "failed": 0, "operation_times": []}
        results_lock = threading.Lock()
        completed_counter = {"count": 0}
        counter_lock = threading.Lock()

        def worker_function(worker_id):
            """Worker function for mixed operations."""
            worker_results = {"saves": 0, "loads": 0, "deletes": 0, "infos": 0, "failed": 0, "operation_times": []}
            
            for i in range(operations_per_worker):
                obj_name = f"mixed:obj:{worker_id}:{i}"
                operation_start = time.time()
                
                try:
                    # Choose operation type based on probability
                    import random
                    op_type = random.choices(
                        ["save", "load", "delete", "info"], 
                        weights=[0.4, 0.3, 0.2, 0.1]
                    )[0]
                    
                    if op_type == "save":
                        # Save operation
                        test_obj = test_objects["small_string"]
                        registry.save(obj_name, test_obj)
                        worker_results["saves"] += 1
                        
                    elif op_type == "load":
                        # Load operation (might fail if object doesn't exist)
                        try:
                            registry.load(obj_name)
                            worker_results["loads"] += 1
                        except ValueError:
                            # Object doesn't exist, save it first
                            registry.save(obj_name, test_objects["small_string"])
                            registry.load(obj_name)
                            worker_results["saves"] += 1
                            worker_results["loads"] += 1
                            
                    elif op_type == "delete":
                        # Delete operation (might fail if object doesn't exist)
                        try:
                            registry.delete(obj_name)
                            worker_results["deletes"] += 1
                        except KeyError:
                            # Object doesn't exist, create and delete it
                            registry.save(obj_name, test_objects["small_string"])
                            registry.delete(obj_name)
                            worker_results["saves"] += 1
                            worker_results["deletes"] += 1
                            
                    elif op_type == "info":
                        # Info operation
                        registry.info()
                        worker_results["infos"] += 1
                        
                    operation_end = time.time()
                    worker_results["operation_times"].append(operation_end - operation_start)
                    
                except Exception as e:
                    worker_results["failed"] += 1
                    print(f"Worker {worker_id} operation {i} ({op_type}) failed: {e}")

                # Update counter
                with counter_lock:
                    completed_counter["count"] += 1

            # Merge results
            with results_lock:
                for key in worker_results:
                    if key == "operation_times":
                        results[key].extend(worker_results[key])
                    else:
                        results[key] += worker_results[key]

        print(f"\nStarting mixed operations stress test ({max_workers} workers × {operations_per_worker} ops)")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker_function, i) for i in range(max_workers)]

            # Track progress
            with tqdm(total=total_operations, desc="Mixed operations", file=sys.stderr) as pbar:
                last_completed = 0
                while any(not f.done() for f in futures):
                    time.sleep(0.1)
                    
                    with counter_lock:
                        current_completed = completed_counter["count"]
                    
                    if current_completed > last_completed:
                        pbar.update(current_completed - last_completed)
                        last_completed = current_completed
                    
                    pbar.set_postfix({
                        "completed": current_completed,
                        "saves": results["saves"],
                        "loads": results["loads"],
                        "deletes": results["deletes"],
                        "failed": results["failed"]
                    })

                # Final update
                with counter_lock:
                    final_completed = completed_counter["count"]
                if final_completed > last_completed:
                    pbar.update(final_completed - last_completed)

            # Wait for completion
            for future in futures:
                future.result()

        total_time = time.time() - start_time
        total_successful = results["saves"] + results["loads"] + results["deletes"] + results["infos"]
        throughput = total_successful / total_time
        avg_operation_time = mean(results["operation_times"]) if results["operation_times"] else 0

        print("\nMixed operations stress test completed:")
        print(f"   - Total operations: {total_operations}")
        print(f"   - Successful saves: {results['saves']}")
        print(f"   - Successful loads: {results['loads']}")
        print(f"   - Successful deletes: {results['deletes']}")
        print(f"   - Successful infos: {results['infos']}")
        print(f"   - Failed operations: {results['failed']}")
        print(f"   - Success rate: {(total_successful / total_operations) * 100:.1f}%")
        print(f"   - Total time: {total_time:.2f}s")
        print(f"   - Throughput: {throughput:.1f} ops/sec")
        print(f"   - Avg operation time: {avg_operation_time * 1000:.1f}ms")

        # Assertions
        assert total_successful > total_operations * 0.85, f"Success rate too low: {total_successful}/{total_operations}"
        assert throughput > 3, f"Mixed operations throughput too low: {throughput:.1f} ops/sec"

    @pytest.mark.slow
    def test_object_size_performance(self, registry, test_objects):
        """
        Test performance with different object sizes.
        """
        iterations_per_size = 50
        
        # Test different object sizes
        test_cases = [
            ("small:string", test_objects["small_string"]),
            ("medium:string", test_objects["medium_string"]),
            ("large:string", test_objects["large_string"]),
            ("small:list", test_objects["small_list"]),
            ("large:list", test_objects["large_list"]),
            ("small:dict", test_objects["small_dict"]),
            ("large:dict", test_objects["large_dict"]),
        ]
        
        results_by_size = {}

        print("\nStarting object size performance test")

        for size_name, test_obj in test_cases:
            print(f"\nTesting {size_name} (size: ~{len(str(test_obj))} chars)")
            
            save_times = []
            load_times = []
            successful_saves = 0
            successful_loads = 0
            failed_ops = 0

            with tqdm(total=iterations_per_size * 2, desc=f"{size_name}", file=sys.stderr) as pbar:
                for i in range(iterations_per_size):
                    obj_name = f"size:test:{size_name}:{i}"
                    
                    # Save operation
                    save_start = time.time()
                    try:
                        registry.save(obj_name, test_obj)
                        save_end = time.time()
                        save_times.append(save_end - save_start)
                        successful_saves += 1
                    except Exception as e:
                        failed_ops += 1
                        print(f"Save failed for {obj_name}: {e}")
                    pbar.update(1)

                    # Load operation
                    load_start = time.time()
                    try:
                        loaded_obj = registry.load(obj_name)
                        load_end = time.time()
                        assert loaded_obj == test_obj
                        load_times.append(load_end - load_start)
                        successful_loads += 1
                    except Exception as e:
                        failed_ops += 1
                        print(f"Load failed for {obj_name}: {e}")
                    pbar.update(1)

            # Calculate metrics
            avg_save_time = mean(save_times) if save_times else 0
            avg_load_time = mean(load_times) if load_times else 0
            total_successful = successful_saves + successful_loads
            
            results_by_size[size_name] = {
                "object_size": len(str(test_obj)),
                "successful_saves": successful_saves,
                "successful_loads": successful_loads,
                "failed_ops": failed_ops,
                "avg_save_time": avg_save_time,
                "avg_load_time": avg_load_time,
                "success_rate": (total_successful / (iterations_per_size * 2)) * 100
            }

        print("\nObject size performance test completed:")
        print(f"{'Size':<15} {'Obj Size':<10} {'Save (ms)':<10} {'Load (ms)':<10} {'Success %':<10}")
        print("-" * 65)
        
        for size_name, results in results_by_size.items():
            print(f"{size_name:<15} {results['object_size']:<10} {results['avg_save_time']*1000:<10.1f} {results['avg_load_time']*1000:<10.1f} {results['success_rate']:<10.1f}")

        # Assertions
        for size_name, results in results_by_size.items():
            assert results["success_rate"] > 95, f"{size_name} success rate too low: {results['success_rate']:.1f}%"

    @pytest.mark.slow
    def test_version_management_stress(self, registry):
        """
        Test stress on version management with many versions of the same object.
        """
        object_name = "version:test:obj"
        num_versions = 100
        test_value = "test_value_for_versioning"
        
        save_times = []
        load_times = []
        successful_saves = 0
        successful_loads = 0
        failed_ops = 0

        print(f"\nStarting version management stress test ({num_versions} versions)")
        start_time = time.time()

        with tqdm(total=num_versions * 2, desc="Version operations", file=sys.stderr) as pbar:
            for i in range(num_versions):
                version = f"1.0.{i}"
                versioned_value = f"{test_value}_{i}"
                
                # Save with explicit version
                save_start = time.time()
                try:
                    registry.save(object_name, versioned_value, version=version)
                    save_end = time.time()
                    save_times.append(save_end - save_start)
                    successful_saves += 1
                except Exception as e:
                    failed_ops += 1
                    print(f"Save version {version} failed: {e}")
                pbar.update(1)

                # Load specific version
                load_start = time.time()
                try:
                    loaded_obj = registry.load(object_name, version=version)
                    load_end = time.time()
                    assert loaded_obj == versioned_value
                    load_times.append(load_end - load_start)
                    successful_loads += 1
                except Exception as e:
                    failed_ops += 1
                    print(f"Load version {version} failed: {e}")
                pbar.update(1)

        # Test version listing performance
        list_start = time.time()
        try:
            versions = registry.list_versions(object_name)
            list_end = time.time()
            list_time = list_end - list_start
            assert len(versions) == successful_saves
        except Exception as e:
            print(f"Version listing failed: {e}")
            list_time = 0

        total_time = time.time() - start_time
        total_successful = successful_saves + successful_loads
        throughput = total_successful / total_time
        avg_save_time = mean(save_times) if save_times else 0
        avg_load_time = mean(load_times) if load_times else 0

        print("\nVersion management stress test completed:")
        print(f"   - Total versions: {num_versions}")
        print(f"   - Successful saves: {successful_saves}")
        print(f"   - Successful loads: {successful_loads}")
        print(f"   - Failed operations: {failed_ops}")
        print(f"   - Success rate: {(total_successful / (num_versions * 2)) * 100:.1f}%")
        print(f"   - Total time: {total_time:.2f}s")
        print(f"   - Throughput: {throughput:.1f} ops/sec")
        print(f"   - Avg save time: {avg_save_time * 1000:.1f}ms")
        print(f"   - Avg load time: {avg_load_time * 1000:.1f}ms")
        print(f"   - Version list time: {list_time * 1000:.1f}ms")

        # Assertions
        assert total_successful > (num_versions * 2) * 0.95, f"Success rate too low: {total_successful}/{num_versions * 2}"
        assert throughput > 2, f"Version management throughput too low: {throughput:.1f} ops/sec"

    @pytest.mark.slow
    def test_lock_contention_stress(self, registry):
        """
        Test lock contention with many threads accessing the same objects.
        """
        max_workers = 15
        operations_per_worker = 10
        shared_objects = ["shared:obj:1", "shared:obj:2", "shared:obj:3"]
        
        # Results tracking
        results = {"saves": 0, "loads": 0, "failed": 0, "lock_wait_times": []}
        results_lock = threading.Lock()
        completed_counter = {"count": 0}
        counter_lock = threading.Lock()

        def worker_function(worker_id):
            """Worker function that creates lock contention."""
            worker_results = {"saves": 0, "loads": 0, "failed": 0, "lock_wait_times": []}
            
            for i in range(operations_per_worker):
                import random
                obj_name = random.choice(shared_objects)
                
                # Measure lock wait time
                lock_start = time.time()
                
                try:
                    # Randomly save or load
                    if random.random() < 0.5:
                        # Save operation
                        test_value = f"worker:{worker_id}:op:{i}"
                        registry.save(obj_name, test_value)
                        worker_results["saves"] += 1
                    else:
                        # Load operation
                        try:
                            registry.load(obj_name)
                            worker_results["loads"] += 1
                        except ValueError:
                            # Object doesn't exist, save it first
                            registry.save(obj_name, f"initial:value:{worker_id}:{i}")
                            registry.load(obj_name)
                            worker_results["saves"] += 1
                            worker_results["loads"] += 1
                    
                    lock_end = time.time()
                    worker_results["lock_wait_times"].append(lock_end - lock_start)
                    
                except Exception as e:
                    worker_results["failed"] += 1
                    print(f"Worker {worker_id} operation {i} failed: {e}")

                # Update counter
                with counter_lock:
                    completed_counter["count"] += 1

            # Merge results
            with results_lock:
                for key in worker_results:
                    if key == "lock_wait_times":
                        results[key].extend(worker_results[key])
                    else:
                        results[key] += worker_results[key]

        print(f"\nStarting lock contention stress test ({max_workers} workers, {len(shared_objects)} shared objects)")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker_function, i) for i in range(max_workers)]

            # Track progress
            total_ops = max_workers * operations_per_worker
            with tqdm(total=total_ops, desc="Lock contention", file=sys.stderr) as pbar:
                last_completed = 0
                while any(not f.done() for f in futures):
                    time.sleep(0.1)
                    
                    with counter_lock:
                        current_completed = completed_counter["count"]
                    
                    if current_completed > last_completed:
                        pbar.update(current_completed - last_completed)
                        last_completed = current_completed
                    
                    pbar.set_postfix({
                        "completed": current_completed,
                        "saves": results["saves"],
                        "loads": results["loads"],
                        "failed": results["failed"]
                    })

                # Final update
                with counter_lock:
                    final_completed = completed_counter["count"]
                if final_completed > last_completed:
                    pbar.update(final_completed - last_completed)

            # Wait for completion
            for future in futures:
                future.result()

        total_time = time.time() - start_time
        total_successful = results["saves"] + results["loads"]
        throughput = total_successful / total_time
        avg_lock_wait = mean(results["lock_wait_times"]) if results["lock_wait_times"] else 0
        p95_lock_wait = sorted(results["lock_wait_times"])[int(0.95 * len(results["lock_wait_times"]))] if results["lock_wait_times"] else 0

        # Prepare results summary
        summary = {
            "test_name": "test_lock_contention_stress",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_operations": total_ops,
            "concurrent_workers": max_workers,
            "shared_objects": len(shared_objects),
            "successful_saves": results['saves'],
            "successful_loads": results['loads'],
            "failed_operations": results['failed'],
            "success_rate_percent": (total_successful / total_ops) * 100,
            "total_time_seconds": total_time,
            "throughput_ops_per_sec": throughput,
            "avg_lock_wait_ms": avg_lock_wait * 1000,
            "p95_lock_wait_ms": p95_lock_wait * 1000,
            "test_passed": True
        }

        # Print summary to console
        print("\nLock contention stress test completed:")
        print(f"   - Total operations: {total_ops}")
        print(f"   - Concurrent workers: {max_workers}")
        print(f"   - Shared objects: {len(shared_objects)}")
        print(f"   - Successful saves: {results['saves']}")
        print(f"   - Successful loads: {results['loads']}")
        print(f"   - Failed operations: {results['failed']}")
        print(f"   - Success rate: {(total_successful / total_ops) * 100:.1f}%")
        print(f"   - Total time: {total_time:.2f}s")
        print(f"   - Throughput: {throughput:.1f} ops/sec")
        print(f"   - Avg lock wait time: {avg_lock_wait * 1000:.1f}ms")
        print(f"   - 95th percentile lock wait: {p95_lock_wait * 1000:.1f}ms")

        # Save results to file
        self.save_results(summary, "lock_contention_stress_results.json")

        # Assertions
        try:
            assert total_successful > total_ops * 0.75, f"Success rate too low: {total_successful}/{total_ops}"
            assert throughput > 2, f"Lock contention throughput too low: {throughput:.1f} ops/sec"
            assert avg_lock_wait < 0.5, f"Lock wait time too high: {avg_lock_wait * 1000:.1f}ms"
        except AssertionError as e:
            summary["test_passed"] = False
            summary["failure_reason"] = str(e)
            self.save_results(summary, "lock_contention_stress_results.json")
            raise

    @pytest.mark.slow
    def test_dictionary_interface_stress(self, registry, test_objects):
        """
        Test stress on dictionary-like interface operations.
        """
        max_workers = 8
        operations_per_worker = 30
        total_operations = max_workers * operations_per_worker

        # Results tracking
        results = {"gets": 0, "sets": 0, "dels": 0, "contains": 0, "failed": 0, "operation_times": []}
        results_lock = threading.Lock()
        completed_counter = {"count": 0}
        counter_lock = threading.Lock()

        def worker_function(worker_id):
            """Worker function for dictionary interface operations."""
            worker_results = {"gets": 0, "sets": 0, "dels": 0, "contains": 0, "failed": 0, "operation_times": []}
            
            for i in range(operations_per_worker):
                obj_name = f"dict:obj:{worker_id}:{i}"
                operation_start = time.time()
                
                try:
                    import random
                    op_type = random.choice(["set", "get", "del", "contains"])
                    
                    if op_type == "set":
                        # Dictionary set operation
                        registry[obj_name] = test_objects["small_string"]
                        worker_results["sets"] += 1
                        
                    elif op_type == "get":
                        # Dictionary get operation
                        try:
                            _ = registry[obj_name]
                            worker_results["gets"] += 1
                        except KeyError:
                            # Object doesn't exist, create it first
                            registry[obj_name] = test_objects["small_string"]
                            _ = registry[obj_name]
                            worker_results["sets"] += 1
                            worker_results["gets"] += 1
                            
                    elif op_type == "del":
                        # Dictionary delete operation
                        try:
                            del registry[obj_name]
                            worker_results["dels"] += 1
                        except KeyError:
                            # Object doesn't exist, create and delete it
                            registry[obj_name] = test_objects["small_string"]
                            del registry[obj_name]
                            worker_results["sets"] += 1
                            worker_results["dels"] += 1
                            
                    elif op_type == "contains":
                        # Dictionary contains operation
                        _ = obj_name in registry
                        worker_results["contains"] += 1
                    
                    operation_end = time.time()
                    worker_results["operation_times"].append(operation_end - operation_start)
                    
                except Exception as e:
                    worker_results["failed"] += 1
                    print(f"Worker {worker_id} dict operation {i} ({op_type}) failed: {e}")

                # Update counter
                with counter_lock:
                    completed_counter["count"] += 1

            # Merge results
            with results_lock:
                for key in worker_results:
                    if key == "operation_times":
                        results[key].extend(worker_results[key])
                    else:
                        results[key] += worker_results[key]

        print(f"\nStarting dictionary interface stress test ({max_workers} workers × {operations_per_worker} ops)")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker_function, i) for i in range(max_workers)]

            # Track progress
            with tqdm(total=total_operations, desc="Dict operations", file=sys.stderr) as pbar:
                last_completed = 0
                while any(not f.done() for f in futures):
                    time.sleep(0.1)
                    
                    with counter_lock:
                        current_completed = completed_counter["count"]
                    
                    if current_completed > last_completed:
                        pbar.update(current_completed - last_completed)
                        last_completed = current_completed
                    
                    pbar.set_postfix({
                        "completed": current_completed,
                        "gets": results["gets"],
                        "sets": results["sets"],
                        "dels": results["dels"],
                        "failed": results["failed"]
                    })

                # Final update
                with counter_lock:
                    final_completed = completed_counter["count"]
                if final_completed > last_completed:
                    pbar.update(final_completed - last_completed)

            # Wait for completion
            for future in futures:
                future.result()

        total_time = time.time() - start_time
        total_successful = results["gets"] + results["sets"] + results["dels"] + results["contains"]
        throughput = total_successful / total_time
        avg_operation_time = mean(results["operation_times"]) if results["operation_times"] else 0

        # Prepare results summary
        summary = {
            "test_name": "test_dictionary_interface_stress",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_operations": total_operations,
            "concurrent_workers": max_workers,
            "operations_per_worker": operations_per_worker,
            "successful_gets": results['gets'],
            "successful_sets": results['sets'],
            "successful_dels": results['dels'],
            "successful_contains": results['contains'],
            "failed_operations": results['failed'],
            "success_rate_percent": (total_successful / total_operations) * 100,
            "total_time_seconds": total_time,
            "throughput_ops_per_sec": throughput,
            "avg_operation_time_ms": avg_operation_time * 1000,
            "test_passed": True
        }

        # Print summary to console
        print("\nDictionary interface stress test completed:")
        print(f"   - Total operations: {total_operations}")
        print(f"   - Successful gets: {results['gets']}")
        print(f"   - Successful sets: {results['sets']}")
        print(f"   - Successful dels: {results['dels']}")
        print(f"   - Successful contains: {results['contains']}")
        print(f"   - Failed operations: {results['failed']}")
        print(f"   - Success rate: {(total_successful / total_operations) * 100:.1f}%")
        print(f"   - Total time: {total_time:.2f}s")
        print(f"   - Throughput: {throughput:.1f} ops/sec")
        print(f"   - Avg operation time: {avg_operation_time * 1000:.1f}ms")

        # Save results to file
        self.save_results(summary, "dictionary_interface_stress_results.json")

        # Assertions
        try:
            assert total_successful > total_operations * 0.85, f"Success rate too low: {total_successful}/{total_operations}"
            assert throughput > 3, f"Dictionary interface throughput too low: {throughput:.1f} ops/sec"
        except AssertionError as e:
            summary["test_passed"] = False
            summary["failure_reason"] = str(e)
            self.save_results(summary, "dictionary_interface_stress_results.json")
            raise

    def save_results(self, results, filename):
        """
        Save stress test results to a JSON file for tracking performance over time.
        """
        # Create results directory if it doesn't exist
        results_dir = Path("stress_test_results")
        results_dir.mkdir(exist_ok=True)
        
        # Save to results directory
        filepath = results_dir / filename
        timestamp = datetime.now().isoformat()
        results_with_timestamp = {"timestamp": timestamp, "results": results}
        
        with open(filepath, "w") as f:
            json.dump(results_with_timestamp, f, indent=2)
        
        print(f"Results saved to: {filepath}")
