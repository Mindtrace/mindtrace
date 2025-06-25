"""
Stress tests for EchoService maximum throughput testing.

This module tests the EchoService under high load to determine its maximum
throughput and performance characteristics under stress conditions.
"""

import asyncio
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from statistics import mean, median, stdev
import sys
import time
import threading

import pytest
from tqdm import tqdm

from mindtrace.services.sample.echo_service import EchoService

# Suppress verbose HTTP logging during stress tests
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# For even cleaner output during stress tests, uncomment the following line:
# logging.getLogger().setLevel(logging.CRITICAL)


class TestEchoServiceThroughput:
    """Stress tests for EchoService maximum throughput."""

    @pytest.mark.slow
    def test_sequential_throughput_stress(self, echo_service_manager):
        """
        Test sequential request throughput to establish baseline performance.
        """
        if echo_service_manager is None:
            pytest.skip("EchoService failed to launch")
        
        iterations = 1000
        response_times = []
        successful_requests = 0
        failed_requests = 0
        
        # Test message for EchoService
        test_message = "Performance test message"
        
        print(f"\nStarting sequential throughput test ({iterations} requests)")
        start_time = time.time()
        
        with tqdm(total=iterations, desc="Sequential requests", file=sys.stderr) as pbar:
            for i in range(iterations):
                request_start = time.time()
                try:
                    # Call with keyword argument, not dictionary
                    response = echo_service_manager.echo(message=test_message)
                    request_end = time.time()
                    
                    # Verify response
                    assert response.echoed == test_message
                    
                    response_times.append(request_end - request_start)
                    successful_requests += 1
                    
                except Exception as e:
                    failed_requests += 1
                    print(f"Request {i} failed: {e}")
                
                pbar.update(1)
                pbar.set_postfix({
                    'success': successful_requests,
                    'failed': failed_requests,
                    'avg_ms': f"{mean(response_times[-100:]) * 1000:.1f}" if response_times else "0"
                })
        
        total_time = time.time() - start_time
        
        # Calculate metrics
        throughput = successful_requests / total_time
        avg_response_time = mean(response_times) if response_times else 0
        median_response_time = median(response_times) if response_times else 0
        p95_response_time = sorted(response_times)[int(0.95 * len(response_times))] if response_times else 0
        
        print(f"\nSequential throughput test completed:")
        print(f"   - Total requests: {iterations}")
        print(f"   - Successful: {successful_requests}")
        print(f"   - Failed: {failed_requests}")
        print(f"   - Success rate: {(successful_requests/iterations)*100:.1f}%")
        print(f"   - Total time: {total_time:.2f}s")
        print(f"   - Throughput: {throughput:.1f} requests/sec")
        print(f"   - Avg response time: {avg_response_time*1000:.1f}ms")
        print(f"   - Median response time: {median_response_time*1000:.1f}ms")
        print(f"   - 95th percentile: {p95_response_time*1000:.1f}ms")
        
        # Assertions
        assert successful_requests > iterations * 0.95, f"Success rate too low: {successful_requests}/{iterations}"
        assert throughput > 10, f"Throughput too low: {throughput:.1f} req/sec"

    @pytest.mark.slow
    def test_concurrent_throughput_stress(self, echo_service_manager):
        """
        Test concurrent request throughput to find maximum concurrent capacity.
        """
        if echo_service_manager is None:
            pytest.skip("EchoService failed to launch")
        
        max_workers = 20
        requests_per_worker = 50
        total_requests = max_workers * requests_per_worker
        
        # Test message for EchoService
        test_message = "Concurrent test"
        
        # Results tracking with thread-safe counters for real-time progress
        results = {
            'successful': 0,
            'failed': 0,
            'response_times': [],
            'errors': []
        }
        results_lock = threading.Lock()
        
        # Real-time counters for progress bar
        completed_counter = {'count': 0}
        counter_lock = threading.Lock()
        
        def worker_function(worker_id):
            """Worker function for concurrent requests."""
            worker_results = {
                'successful': 0,
                'failed': 0,
                'response_times': [],
                'errors': []
            }
            
            for i in range(requests_per_worker):
                request_start = time.time()
                try:
                    # Call with keyword argument, not dictionary
                    response = echo_service_manager.echo(message=test_message)
                    request_end = time.time()
                    
                    # Verify response
                    assert response.echoed == test_message
                    
                    worker_results['response_times'].append(request_end - request_start)
                    worker_results['successful'] += 1
                    
                except Exception as e:
                    worker_results['failed'] += 1
                    worker_results['errors'].append(f"Worker {worker_id}, req {i}: {str(e)}")
                
                # Update real-time counter for progress bar
                with counter_lock:
                    completed_counter['count'] += 1
            
            # Merge worker results at the end
            with results_lock:
                results['successful'] += worker_results['successful']
                results['failed'] += worker_results['failed']
                results['response_times'].extend(worker_results['response_times'])
                results['errors'].extend(worker_results['errors'])
        
        print(f"\nStarting concurrent throughput test ({max_workers} workers × {requests_per_worker} requests)")
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all workers
            futures = [executor.submit(worker_function, i) for i in range(max_workers)]
            
            # Track progress with real-time updates
            with tqdm(total=total_requests, desc="Concurrent requests", file=sys.stderr) as pbar:
                last_completed = 0
                while any(not f.done() for f in futures):
                    time.sleep(0.1)
                    
                    # Update progress bar with real-time completed count
                    with counter_lock:
                        current_completed = completed_counter['count']
                    
                    # Update progress bar by the difference since last check
                    if current_completed > last_completed:
                        pbar.update(current_completed - last_completed)
                        last_completed = current_completed
                    
                    # Update postfix with current stats
                    active_workers = sum(1 for f in futures if not f.done())
                    pbar.set_postfix({
                        'completed': current_completed,
                        'active_workers': active_workers
                    })
                    pbar.refresh()
                
                # Final update to ensure we reach 100%
                with counter_lock:
                    final_completed = completed_counter['count']
                if final_completed > last_completed:
                    pbar.update(final_completed - last_completed)
                
                pbar.set_postfix({
                    'completed': final_completed,
                    'active_workers': 0
                })
                pbar.refresh()
            
            # Wait for all workers to complete
            for future in as_completed(futures):
                future.result()  # This will raise any exceptions
        
        total_time = time.time() - start_time
        
        # Calculate metrics
        throughput = results['successful'] / total_time
        avg_response_time = mean(results['response_times']) if results['response_times'] else 0
        median_response_time = median(results['response_times']) if results['response_times'] else 0
        p95_response_time = sorted(results['response_times'])[int(0.95 * len(results['response_times']))] if results['response_times'] else 0
        p99_response_time = sorted(results['response_times'])[int(0.99 * len(results['response_times']))] if results['response_times'] else 0
        
        print(f"\nConcurrent throughput test completed:")
        print(f"   - Total requests: {total_requests}")
        print(f"   - Concurrent workers: {max_workers}")
        print(f"   - Successful: {results['successful']}")
        print(f"   - Failed: {results['failed']}")
        print(f"   - Success rate: {(results['successful']/total_requests)*100:.1f}%")
        print(f"   - Total time: {total_time:.2f}s")
        print(f"   - Throughput: {throughput:.1f} requests/sec")
        print(f"   - Avg response time: {avg_response_time*1000:.1f}ms")
        print(f"   - Median response time: {median_response_time*1000:.1f}ms")
        print(f"   - 95th percentile: {p95_response_time*1000:.1f}ms")
        print(f"   - 99th percentile: {p99_response_time*1000:.1f}ms")
        
        if results['errors']:
            print(f"   - Sample errors: {results['errors'][:3]}")
        
        # Assertions
        assert results['successful'] > total_requests * 0.90, f"Success rate too low: {results['successful']}/{total_requests}"
        assert throughput > 10, f"Concurrent throughput too low: {throughput:.1f} req/sec"

    @pytest.mark.slow
    def test_sustained_load_stress(self, echo_service_manager):
        """
        Test sustained load over time to check for memory leaks and performance degradation.
        """
        if echo_service_manager is None:
            pytest.skip("EchoService failed to launch")
        
        test_duration = 60  # seconds
        target_rps = 10  # requests per second
        batch_size = 10
        
        # Test message for EchoService
        test_message = "Sustained load test"
        
        # Results tracking
        time_buckets = defaultdict(list)  # bucket -> [response_times]
        total_successful = 0
        total_failed = 0
        start_time = time.time()
        
        print(f"\nStarting sustained load test ({test_duration}s at {target_rps} RPS)")
        
        with tqdm(total=test_duration, desc="Sustained load", unit="s", file=sys.stderr) as pbar:
            while time.time() - start_time < test_duration:
                batch_start = time.time()
                batch_successful = 0
                batch_failed = 0
                batch_response_times = []
                
                # Send batch of requests
                for _ in range(batch_size):
                    request_start = time.time()
                    try:
                        # Call with keyword argument, not dictionary
                        response = echo_service_manager.echo(message=test_message)
                        request_end = time.time()
                        
                        # Verify response
                        assert response.echoed == test_message
                        
                        batch_response_times.append(request_end - request_start)
                        batch_successful += 1
                        
                    except Exception as e:
                        batch_failed += 1
                
                # Record results in time bucket (10-second buckets)
                elapsed = time.time() - start_time
                bucket = int(elapsed / 10) * 10
                time_buckets[bucket].extend(batch_response_times)
                
                total_successful += batch_successful
                total_failed += batch_failed
                
                # Update progress
                pbar.n = elapsed
                current_rps = total_successful / elapsed if elapsed > 0 else 0
                avg_response_time = mean(batch_response_times) if batch_response_times else 0
                
                pbar.set_postfix({
                    'RPS': f"{current_rps:.1f}",
                    'success': total_successful,
                    'failed': total_failed,
                    'avg_ms': f"{avg_response_time*1000:.1f}"
                })
                pbar.refresh()
                
                # Rate limiting - sleep to maintain target RPS
                batch_time = time.time() - batch_start
                target_batch_time = batch_size / target_rps
                if batch_time < target_batch_time:
                    time.sleep(target_batch_time - batch_time)
        
        total_time = time.time() - start_time
        overall_rps = total_successful / total_time
        
        print(f"\nSustained load test completed:")
        print(f"   - Duration: {total_time:.1f}s")
        print(f"   - Total requests: {total_successful + total_failed}")
        print(f"   - Successful: {total_successful}")
        print(f"   - Failed: {total_failed}")
        print(f"   - Success rate: {(total_successful/(total_successful + total_failed))*100:.1f}%")
        print(f"   - Overall RPS: {overall_rps:.1f}")
        
        # Performance over time analysis
        print(f"   - Performance over time:")
        for bucket in sorted(time_buckets.keys()):
            if time_buckets[bucket]:
                bucket_avg = mean(time_buckets[bucket]) * 1000
                bucket_p95 = sorted(time_buckets[bucket])[int(0.95 * len(time_buckets[bucket]))] * 1000
                print(f"     {bucket:2d}-{bucket+10:2d}s: avg={bucket_avg:.1f}ms, p95={bucket_p95:.1f}ms, count={len(time_buckets[bucket])}")
        
        # Assertions
        assert total_successful > (test_duration * target_rps * 0.8), f"Did not meet target RPS: {overall_rps:.1f} < {target_rps * 0.8}"
        assert total_failed < total_successful * 0.05, f"Too many failures: {total_failed}"
        
        # Check for performance degradation over time
        if len(time_buckets) >= 2:
            first_bucket = min(time_buckets.keys())
            last_bucket = max(time_buckets.keys())
            
            if time_buckets[first_bucket] and time_buckets[last_bucket]:
                first_avg = mean(time_buckets[first_bucket])
                last_avg = mean(time_buckets[last_bucket])
                degradation = (last_avg - first_avg) / first_avg * 100
                
                print(f"   - Performance change: {degradation:+.1f}% (first: {first_avg*1000:.1f}ms → last: {last_avg*1000:.1f}ms)")
                assert degradation < 50, f"Performance degraded too much: {degradation:.1f}%"

    @pytest.mark.slow
    def test_variable_payload_throughput_stress(self, echo_service_manager):
        """
        Test throughput with variable payload sizes to stress different aspects of the service.
        """
        if echo_service_manager is None:
            pytest.skip("EchoService failed to launch")
        
        # Different message sizes to test
        test_messages = [
            "small",
            "medium message for testing performance",
            "large message " * 50,
            "extra large message " * 100,
        ]
        
        requests_per_message = 100
        results_by_payload = {}
        
        print(f"\nStarting variable payload throughput test")
        
        for i, test_message in enumerate(test_messages):
            message_size = len(test_message)
            print(f"\nTesting payload {i+1}/4 (size: ~{message_size} chars)")
            
            successful = 0
            failed = 0
            response_times = []
            
            start_time = time.time()
            
            with tqdm(total=requests_per_message, desc=f"Payload {i+1}", file=sys.stderr) as pbar:
                for j in range(requests_per_message):
                    request_start = time.time()
                    try:
                        # Call with keyword argument, not dictionary
                        response = echo_service_manager.echo(message=test_message)
                        request_end = time.time()
                        
                        # Verify response
                        assert response.echoed == test_message
                        
                        response_times.append(request_end - request_start)
                        successful += 1
                        
                    except Exception as e:
                        failed += 1
                    
                    pbar.update(1)
                    pbar.set_postfix({
                        'success': successful,
                        'failed': failed,
                        'avg_ms': f"{mean(response_times[-20:]) * 1000:.1f}" if response_times else "0"
                    })
            
            total_time = time.time() - start_time
            throughput = successful / total_time
            avg_response_time = mean(response_times) if response_times else 0
            
            results_by_payload[f"payload_{i+1}"] = {
                'size': message_size,
                'successful': successful,
                'failed': failed,
                'throughput': throughput,
                'avg_response_time': avg_response_time,
                'response_times': response_times
            }
        
        print(f"\nVariable payload throughput test completed:")
        for payload_name, results in results_by_payload.items():
            success_rate = (results['successful'] / requests_per_message) * 100
            print(f"   - {payload_name} (~{results['size']} chars):")
            print(f"     Success rate: {success_rate:.1f}%")
            print(f"     Throughput: {results['throughput']:.1f} req/sec")
            print(f"     Avg response time: {results['avg_response_time']*1000:.1f}ms")
        
        # Assertions
        for payload_name, results in results_by_payload.items():
            assert results['successful'] > requests_per_message * 0.95, f"{payload_name} success rate too low"
            assert results['throughput'] > 5, f"{payload_name} throughput too low: {results['throughput']:.1f} req/sec"

    @pytest.mark.slow
    def test_multi_worker_concurrent_throughput(self):
        """
        Test concurrent throughput with different numbers of server workers.
        This helps find the optimal worker configuration for concurrent loads.
        """
        
        # Test configuration
        client_workers = 10  # Number of concurrent client threads
        requests_per_worker = 20
        total_requests = client_workers * requests_per_worker
        test_message = "Multi-worker test"
        
        # Test different server worker configurations
        worker_configs = [1, 2, 4]  # Number of server workers to test
        results = {}
        
        print(f"\nTesting concurrent throughput with different server worker configurations")
        print(f"Client load: {client_workers} workers × {requests_per_worker} requests = {total_requests} total")
        
        for num_server_workers in worker_configs:
            print(f"\n--- Testing with {num_server_workers} server worker(s) ---")
            
            # Launch service with specific number of workers
            try:
                with EchoService.launch(
                    url="http://localhost:8091", 
                    timeout=15,
                    num_workers=num_server_workers
                ) as cm:
                    
                    # Results tracking
                    test_results = {
                        'successful': 0,
                        'failed': 0,
                        'response_times': [],
                        'errors': []
                    }
                    results_lock = threading.Lock()
                    completed_counter = {'count': 0}
                    counter_lock = threading.Lock()
                    
                    def worker_function(worker_id):
                        """Worker function for concurrent requests."""
                        worker_results = {
                            'successful': 0,
                            'failed': 0,
                            'response_times': [],
                            'errors': []
                        }
                        
                        for i in range(requests_per_worker):
                            request_start = time.time()
                            try:
                                response = cm.echo(message=test_message)
                                request_end = time.time()
                                
                                assert response.echoed == test_message
                                
                                worker_results['response_times'].append(request_end - request_start)
                                worker_results['successful'] += 1
                                
                            except Exception as e:
                                worker_results['failed'] += 1
                                worker_results['errors'].append(f"Worker {worker_id}, req {i}: {str(e)}")
                            
                            # Update counter for progress
                            with counter_lock:
                                completed_counter['count'] += 1
                        
                        # Merge results
                        with results_lock:
                            test_results['successful'] += worker_results['successful']
                            test_results['failed'] += worker_results['failed']
                            test_results['response_times'].extend(worker_results['response_times'])
                            test_results['errors'].extend(worker_results['errors'])
                    
                    # Run the test
                    start_time = time.time()
                    
                    with ThreadPoolExecutor(max_workers=client_workers) as executor:
                        futures = [executor.submit(worker_function, i) for i in range(client_workers)]
                        
                        # Progress tracking
                        with tqdm(total=total_requests, desc=f"{num_server_workers} workers", file=sys.stderr) as pbar:
                            last_completed = 0
                            while any(not f.done() for f in futures):
                                time.sleep(0.1)
                                
                                with counter_lock:
                                    current_completed = completed_counter['count']
                                
                                if current_completed > last_completed:
                                    pbar.update(current_completed - last_completed)
                                    last_completed = current_completed
                                
                                pbar.set_postfix({
                                    'completed': current_completed,
                                    'workers': num_server_workers
                                })
                                pbar.refresh()
                            
                            # Final update
                            with counter_lock:
                                final_completed = completed_counter['count']
                            if final_completed > last_completed:
                                pbar.update(final_completed - last_completed)
                        
                        # Wait for completion
                        for future in futures:
                            future.result()
                    
                    total_time = time.time() - start_time
                    
                    # Calculate metrics
                    throughput = test_results['successful'] / total_time
                    avg_response_time = mean(test_results['response_times']) if test_results['response_times'] else 0
                    p95_response_time = sorted(test_results['response_times'])[int(0.95 * len(test_results['response_times']))] if test_results['response_times'] else 0
                    
                    # Store results
                    results[num_server_workers] = {
                        'throughput': throughput,
                        'avg_response_time': avg_response_time,
                        'p95_response_time': p95_response_time,
                        'success_rate': (test_results['successful'] / total_requests) * 100,
                        'total_time': total_time,
                        'successful': test_results['successful'],
                        'failed': test_results['failed']
                    }
                    
                    print(f"Results for {num_server_workers} worker(s):")
                    print(f"   - Throughput: {throughput:.1f} req/sec")
                    print(f"   - Success rate: {(test_results['successful']/total_requests)*100:.1f}%")
                    print(f"   - Avg response time: {avg_response_time*1000:.1f}ms")
                    print(f"   - 95th percentile: {p95_response_time*1000:.1f}ms")
                    print(f"   - Total time: {total_time:.2f}s")
                    
                    # Reset counter for next test
                    with counter_lock:
                        completed_counter['count'] = 0
                    
            except Exception as e:
                print(f"Failed to test {num_server_workers} workers: {e}")
                results[num_server_workers] = None
        
        # Summary comparison
        print(f"\nMulti-worker performance comparison:")
        print(f"{'Workers':<8} {'Throughput':<12} {'Avg RT':<10} {'P95 RT':<10} {'Success':<8}")
        print("-" * 55)
        
        best_throughput = 0
        best_config = None
        
        for workers, data in results.items():
            if data:
                throughput = data['throughput']
                avg_rt = data['avg_response_time'] * 1000
                p95_rt = data['p95_response_time'] * 1000
                success = data['success_rate']
                
                print(f"{workers:<8} {throughput:<12.1f} {avg_rt:<10.1f} {p95_rt:<10.1f} {success:<8.1f}%")
                
                if throughput > best_throughput:
                    best_throughput = throughput
                    best_config = workers
            else:
                print(f"{workers:<8} {'FAILED':<12}")
        
        if best_config:
            print(f"\nBest configuration: {best_config} worker(s) with {best_throughput:.1f} req/sec")
        
        # Assertions
        assert len([r for r in results.values() if r is not None]) > 0, "No tests completed successfully"
        
        # At least one configuration should achieve reasonable performance
        max_throughput = max(r['throughput'] for r in results.values() if r is not None)
        assert max_throughput > 5, f"Best throughput too low: {max_throughput:.1f} req/sec"

    @pytest.mark.slow
    def test_delayed_processing_multi_worker_throughput(self):
        """
        Test concurrent throughput with simulated processing delay to clearly demonstrate
        worker scaling benefits. Uses the delay parameter to simulate realistic workloads.
        """
        
        # Test configuration
        client_workers = 12  # Number of concurrent clients
        requests_per_worker = 5  # Fewer requests per worker to keep test reasonable
        total_requests = client_workers * requests_per_worker
        processing_delay = 0.1  # 100ms simulated processing time
        test_message = "Delayed processing test"
        
        # Test different server worker configurations
        worker_configs = [1, 2, 4]
        results = {}
        
        print(f"\nTesting delayed processing concurrent throughput with different server worker configurations")
        print(f"Client load: {client_workers} workers × {requests_per_worker} requests = {total_requests} total")
        print(f"Simulated processing delay: {processing_delay*1000:.0f}ms per request")
        
        for num_server_workers in worker_configs:
            print(f"\n--- Testing with {num_server_workers} server worker(s) ---")
            
            # Launch service with specific number of workers
            try:
                with EchoService.launch(
                    url="http://localhost:8093", 
                    timeout=15,
                    num_workers=num_server_workers
                ) as cm:
                    
                    # Results tracking
                    test_results = {
                        'successful': 0,
                        'failed': 0,
                        'response_times': [],
                        'errors': []
                    }
                    results_lock = threading.Lock()
                    completed_counter = {'count': 0}
                    counter_lock = threading.Lock()
                    
                    def worker_function(worker_id):
                        """Worker function for concurrent requests."""
                        worker_results = {
                            'successful': 0,
                            'failed': 0,
                            'response_times': [],
                            'errors': []
                        }
                        
                        for i in range(requests_per_worker):
                            request_start = time.time()
                            try:
                                # Call with both message and delay parameters
                                response = cm.echo(message=test_message, delay=processing_delay)
                                request_end = time.time()
                                
                                # Verify response
                                assert response.echoed == test_message
                                
                                worker_results['response_times'].append(request_end - request_start)
                                worker_results['successful'] += 1
                                
                            except Exception as e:
                                worker_results['failed'] += 1
                                worker_results['errors'].append(f"Worker {worker_id}, req {i}: {str(e)}")
                            
                            # Update counter for progress
                            with counter_lock:
                                completed_counter['count'] += 1
                        
                        # Merge results
                        with results_lock:
                            test_results['successful'] += worker_results['successful']
                            test_results['failed'] += worker_results['failed']
                            test_results['response_times'].extend(worker_results['response_times'])
                            test_results['errors'].extend(worker_results['errors'])
                    
                    # Run the test
                    start_time = time.time()
                    
                    with ThreadPoolExecutor(max_workers=client_workers) as executor:
                        futures = [executor.submit(worker_function, i) for i in range(client_workers)]
                        
                        # Progress tracking
                        with tqdm(total=total_requests, desc=f"{num_server_workers} workers", file=sys.stderr) as pbar:
                            last_completed = 0
                            while any(not f.done() for f in futures):
                                time.sleep(0.1)
                                
                                with counter_lock:
                                    current_completed = completed_counter['count']
                                
                                if current_completed > last_completed:
                                    pbar.update(current_completed - last_completed)
                                    last_completed = current_completed
                                
                                pbar.set_postfix({
                                    'completed': current_completed,
                                    'workers': num_server_workers
                                })
                                pbar.refresh()
                            
                            # Final update
                            with counter_lock:
                                final_completed = completed_counter['count']
                            if final_completed > last_completed:
                                pbar.update(final_completed - last_completed)
                        
                        # Wait for completion
                        for future in futures:
                            future.result()
                    
                    total_time = time.time() - start_time
                    
                    # Calculate metrics
                    throughput = test_results['successful'] / total_time
                    avg_response_time = mean(test_results['response_times']) if test_results['response_times'] else 0
                    p95_response_time = sorted(test_results['response_times'])[int(0.95 * len(test_results['response_times']))] if test_results['response_times'] else 0
                    
                    # Store results
                    results[num_server_workers] = {
                        'throughput': throughput,
                        'avg_response_time': avg_response_time,
                        'p95_response_time': p95_response_time,
                        'success_rate': (test_results['successful'] / total_requests) * 100,
                        'total_time': total_time,
                        'successful': test_results['successful'],
                        'failed': test_results['failed']
                    }
                    
                    print(f"Results for {num_server_workers} worker(s):")
                    print(f"   - Throughput: {throughput:.1f} req/sec")
                    print(f"   - Success rate: {(test_results['successful']/total_requests)*100:.1f}%")
                    print(f"   - Avg response time: {avg_response_time*1000:.1f}ms")
                    print(f"   - 95th percentile: {p95_response_time*1000:.1f}ms")
                    print(f"   - Total time: {total_time:.2f}s")
                    
                    # Reset counter for next test
                    with counter_lock:
                        completed_counter['count'] = 0
                    
            except Exception as e:
                print(f"Failed to test {num_server_workers} workers: {e}")
                results[num_server_workers] = None
        
        # Summary comparison with scaling analysis
        print(f"\nDelayed processing multi-worker performance comparison:")
        print(f"{'Workers':<8} {'Throughput':<12} {'Scaling':<10} {'Efficiency':<12} {'Avg RT':<10} {'Success':<8}")
        print("-" * 75)
        
        best_throughput = 0
        best_config = None
        baseline_throughput = None
        
        for workers, data in results.items():
            if data:
                throughput = data['throughput']
                avg_rt = data['avg_response_time'] * 1000
                success = data['success_rate']
                
                # Calculate scaling efficiency
                if workers == 1:
                    baseline_throughput = throughput
                    scaling = "1.0x"
                    efficiency = "100%"
                elif baseline_throughput:
                    scaling_factor = throughput / baseline_throughput
                    efficiency_pct = (scaling_factor / workers) * 100
                    scaling = f"{scaling_factor:.1f}x"
                    efficiency = f"{efficiency_pct:.0f}%"
                else:
                    scaling = "N/A"
                    efficiency = "N/A"
                
                print(f"{workers:<8} {throughput:<12.1f} {scaling:<10} {efficiency:<12} {avg_rt:<10.1f} {success:<8.1f}%")
                
                if throughput > best_throughput:
                    best_throughput = throughput
                    best_config = workers
            else:
                print(f"{workers:<8} {'FAILED':<12}")
        
        if best_config and baseline_throughput:
            max_scaling = best_throughput / baseline_throughput
            theoretical_max = best_config
            overall_efficiency = (max_scaling / theoretical_max) * 100
            
            print(f"\nDelayed processing scaling analysis:")
            print(f"   - Best configuration: {best_config} worker(s) with {best_throughput:.1f} req/sec")
            print(f"   - Maximum scaling achieved: {max_scaling:.1f}x")
            print(f"   - Theoretical maximum: {theoretical_max:.0f}x")
            print(f"   - Overall efficiency: {overall_efficiency:.0f}%")
            
            # Expected performance with delay
            expected_min_rt = processing_delay * 1000  # Convert to ms
            actual_min_rt = min(r['avg_response_time'] * 1000 for r in results.values() if r is not None)
            overhead_ms = actual_min_rt - expected_min_rt
            
            print(f"   - Expected minimum response time: {expected_min_rt:.0f}ms")
            print(f"   - Actual minimum response time: {actual_min_rt:.1f}ms")
            print(f"   - HTTP/network overhead: {overhead_ms:.1f}ms")
            
            # Analyze results
            if overall_efficiency >= 80:
                print(f"Excellent scaling efficiency! Workers provide clear benefits.")
            elif overall_efficiency >= 60:
                print(f"Good scaling efficiency. Workers help with concurrent load.")
            elif overall_efficiency >= 40:
                print(f" Moderate scaling efficiency. Some bottlenecks present.")
            else:
                print(f"Poor scaling efficiency. Significant bottlenecks detected.")
                print("   Possible causes:")
                print("   - Connection pooling limitations")
                print("   - Shared resource contention")
                print("   - Network/HTTP overhead still dominates")
        
        # Assertions
        assert len([r for r in results.values() if r is not None]) > 0, "No tests completed successfully"
        
        # With simulated processing delay, we should see better scaling
        max_throughput = max(r['throughput'] for r in results.values() if r is not None)
        assert max_throughput > 2, f"Best throughput too low: {max_throughput:.1f} req/sec"
        
        # Check that delay is actually working (response times should be >= delay)
        min_avg_response = min(r['avg_response_time'] for r in results.values() if r is not None)
        assert min_avg_response >= processing_delay * 0.9, f"Processing delay not working: {min_avg_response*1000:.1f}ms < {processing_delay*1000*.9:.1f}ms"

    @pytest.mark.slow
    def test_single_request_baseline(self, echo_service_manager):
        """
        Test single request performance to establish baseline connection overhead.
        """
        if echo_service_manager is None:
            pytest.skip("EchoService failed to launch")
        
        test_delays = [0.0, 0.05, 0.1, 0.2]  # 0ms, 50ms, 100ms, 200ms
        test_message = "Baseline test"
        
        print(f"\nTesting single request baseline performance:")
        print(f"{'Delay':<8} {'Expected':<10} {'Actual':<10} {'Overhead':<10} {'Efficiency':<10}")
        print("-" * 55)
        
        for delay in test_delays:
            response_times = []
            
            # Run 5 requests to get average
            for i in range(5):
                request_start = time.time()
                try:
                    response = echo_service_manager.echo(message=test_message, delay=delay)
                    request_end = time.time()
                    
                    assert response.echoed == test_message
                    response_times.append(request_end - request_start)
                    
                except Exception as e:
                    print(f"Request failed: {e}")
                    continue
            
            if response_times:
                avg_response_time = mean(response_times) * 1000  # Convert to ms
                expected_time = delay * 1000  # Convert to ms
                overhead = avg_response_time - expected_time
                efficiency = (expected_time / avg_response_time * 100) if avg_response_time > 0 else 0
                
                print(f"{delay*1000:<8.0f} {expected_time:<10.0f} {avg_response_time:<10.1f} {overhead:<10.1f} {efficiency:<10.1f}%")
            else:
                print(f"{delay*1000:<8.0f} {'FAILED':<10}")
        
        print(f"\nBaseline analysis:")
        print(f"   - High overhead (>50ms) suggests connection management issues")
        print(f"   - Low efficiency (<80%) indicates HTTP client bottlenecks")
