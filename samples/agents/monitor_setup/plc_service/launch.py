"""
Launch script for MockPLC Service with interactive log generation.

This script:
1. Launches the MockPLC service
2. Sends requests to generate various log patterns
3. Simulates different scenarios (normal, errors, high-load)

Usage:
    python launch.py                    # Just run the service
    python launch.py --demo             # Run service + interactive demo
    python launch.py --demo --chaos     # Run with high error rate demo
"""

import argparse
import asyncio
import random
import time
from datetime import datetime

import httpx

from mock_plc_service import MockPLCService, ScanType


async def run_demo(base_url: str, chaos_mode: bool = False):
    """Run interactive demo that generates various log patterns."""
    
    print("\n" + "=" * 70)
    print("Demo Mode - Generating log patterns...")
    print("=" * 70 + "\n")
    
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        
        # Wait for service to be ready
        print("Waiting for service to be ready...")
        for i in range(10):
            try:
                resp = await client.get("/status")
                if resp.status_code == 200:
                    print("Service is ready!\n")
                    break
            except Exception:
                pass
            await asyncio.sleep(1)
        else:
            print("Service not ready after 10 seconds")
            return

        # ─────────────────────────────────────────────────────────────────
        # Scenario 1: Normal Operations
        # ─────────────────────────────────────────────────────────────────
        print("📋 Scenario 1: Normal Operations")
        print("-" * 50)
        
        for i in range(3):
            scan_type = random.choice(list(ScanType))
            serial = f"DEMO-{datetime.now().strftime('%H%M%S')}-{i:03d}"
            
            print(f"  → Triggering {scan_type.value} scan for {serial}")
            
            resp = await client.post("/trigger_scan", json={
                "scan_type": scan_type.value,
                "serial_number": serial,
                "part_number": f"PART-DEMO-{i:04d}",
                "simulate_error": False,
            })
            
            if resp.status_code == 200:
                print(f"    ✓ {resp.json()['message']}")
            
            await asyncio.sleep(1)
        
        print()
        await asyncio.sleep(3)  # Let scans complete
        
        # ─────────────────────────────────────────────────────────────────
        # Scenario 2: Simulated Errors
        # ─────────────────────────────────────────────────────────────────
        print("Scenario 2: Simulated Errors (Timeouts)")
        print("-" * 50)
        
        error_count = 5 if chaos_mode else 2
        for i in range(error_count):
            serial = f"ERR-{datetime.now().strftime('%H%M%S')}-{i:03d}"
            
            print(f"  → Triggering ERROR scan for {serial}")
            
            resp = await client.post("/trigger_scan", json={
                "scan_type": "STATIC",
                "serial_number": serial,
                "simulate_error": True,  # Force error
            })
            
            if resp.status_code == 200:
                print(f"    ⚠ {resp.json()['message']} (will timeout)")
            
            await asyncio.sleep(0.5)
        
        print()
        await asyncio.sleep(2)
        
        # ─────────────────────────────────────────────────────────────────
        # Scenario 3: Rapid Fire (High Load)
        # ─────────────────────────────────────────────────────────────────
        print(" Scenario 3: High Load Burst")
        print("-" * 50)
        
        burst_count = 10 if chaos_mode else 5
        print(f"  → Sending {burst_count} concurrent scan requests...")
        
        tasks = []
        for i in range(burst_count):
            serial = f"BURST-{datetime.now().strftime('%H%M%S')}-{i:03d}"
            scan_type = random.choice(list(ScanType))
            
            tasks.append(client.post("/trigger_scan", json={
                "scan_type": scan_type.value,
                "serial_number": serial,
                "simulate_error": random.random() < 0.2,  # 20% errors
            }))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        print(f"    ✓ {success_count}/{burst_count} requests succeeded")
        
        print()
        await asyncio.sleep(5)  # Let burst complete
        
        # ─────────────────────────────────────────────────────────────────
        # Scenario 4: ML Response Simulation
        # ─────────────────────────────────────────────────────────────────
        print("Scenario 4: ML Response Callbacks")
        print("-" * 50)
        
        for i in range(3):
            request_id = f"ML-CALLBACK-{i:03d}"
            is_defective = random.random() < 0.3
            
            status = "Defective" if is_defective else "Healthy"
            print(f"  → Sending ML result: {request_id} = {status}")
            
            resp = await client.post("/ml_response", json={
                "request_id": request_id,
                "part_status": status,
                "defect_code": 1001 if is_defective else None,
            })
            
            if resp.status_code == 200:
                print(f"    ✓ {resp.json()['message']}")
            
            await asyncio.sleep(0.5)
        
        print()
        
        # ─────────────────────────────────────────────────────────────────
        # Final Status
        # ─────────────────────────────────────────────────────────────────
        print("Final Status")
        print("-" * 50)
        
        resp = await client.get("/status")
        if resp.status_code == 200:
            status = resp.json()
            print(f"  Service:          {status['service_name']}")
            print(f"  Uptime:           {status['uptime_seconds']:.1f}s")
            print(f"  Total Scans:      {status['total_scans']}")
            print(f"  Successful:       {status['successful_scans']}")
            print(f"  Failed:           {status['failed_scans']}")
            print(f"  Active:           {status['active_scans']}")
        
        print("\n" + "=" * 70)
        print("🎬 DEMO COMPLETE - Check your logs!")
        print("=" * 70 + "\n")


async def continuous_load(base_url: str, interval: float = 2.0):
    """Generate continuous load for extended testing."""
    
    print("\nContinuous Load Mode - Press Ctrl+C to stop\n")
    
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        cycle = 0
        while True:
            cycle += 1
            try:
                # Random scan type and parameters
                scan_type = random.choice(list(ScanType))
                serial = f"SCAN-{datetime.now().strftime('%H%M%S')}-{cycle:05d}"
                simulate_error = random.random() < 0.1  # 10% errors
                
                resp = await client.post("/trigger_scan", json={
                    "scan_type": scan_type.value,
                    "serial_number": serial,
                    "simulate_error": simulate_error,
                })
                
                status_icon = "Error" if simulate_error else "Success"
                print(f"  {status_icon} Cycle {cycle}: {scan_type.value} scan for {serial}")
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                print("\nStopping continuous load...")
                break
            except Exception as e:
                print(f"  Error: {e}")
                await asyncio.sleep(interval)


def run_service_with_demo(args):
    """Run the service and demo in separate processes."""
    import multiprocessing
    import signal
    import sys
    
    # Start service in a subprocess
    def start_service():
        service = MockPLCService(
            plc_id=args.plc_id,
            error_rate=args.error_rate,
            timeout_rate=args.timeout_rate,
            auto_scan_interval=args.scan_interval,
        )
        service.launch(
            host=args.host,
            port=args.port,
            wait_for_launch=True,
            block=True,
            timeout=300,
        )
    
    service_process = multiprocessing.Process(target=start_service)
    service_process.start()
    
    # Wait for service to start
    time.sleep(3)
    
    base_url = f"http://{args.host}:{args.port}"
    
    try:
        if args.continuous:
            asyncio.run(continuous_load(base_url, args.load_interval))
        else:
            asyncio.run(run_demo(base_url, args.chaos))
            
            # Keep service running after demo
            print("Service still running. Press Ctrl+C to stop.\n")
            while service_process.is_alive():
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        service_process.terminate()
        service_process.join(timeout=5)
        if service_process.is_alive():
            service_process.kill()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mock PLC Service for testing monitoring agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launch.py                     # Just run the service
  python launch.py --demo              # Run service + one-time demo
  python launch.py --demo --chaos      # Demo with more errors
  python launch.py --demo --continuous # Continuous load generation
        """
    )
    
    # Service options
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--plc-id", default="PLC_001", help="PLC identifier for logs")
    parser.add_argument("--error-rate", type=float, default=0.1, help="Error rate 0-1 (default: 0.1)")
    parser.add_argument("--timeout-rate", type=float, default=0.05, help="Timeout rate 0-1 (default: 0.05)")
    parser.add_argument("--scan-interval", type=float, default=5.0, help="Auto-scan interval in seconds")
    
    # Demo options
    parser.add_argument("--demo", action="store_true", help="Run interactive demo after starting service")
    parser.add_argument("--chaos", action="store_true", help="Chaos mode: more errors and higher load")
    parser.add_argument("--continuous", action="store_true", help="Generate continuous load (use with --demo)")
    parser.add_argument("--load-interval", type=float, default=2.0, help="Interval between load requests")
    
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                     MockPLC Service                              ║
╠══════════════════════════════════════════════════════════════════╣
║  PLC ID:         {args.plc_id:<46} ║
║  Host:           {args.host}:{args.port:<40} ║
║  Error Rate:     {args.error_rate*100:.0f}%{' '*43}║
║  Timeout Rate:   {args.timeout_rate*100:.0f}%{' '*43}║
║  Scan Interval:  {args.scan_interval}s{' '*42}║
║  Demo Mode:      {'ON' if args.demo else 'OFF':<45} ║
║  Chaos Mode:     {'ON' if args.chaos else 'OFF':<45} ║
╠══════════════════════════════════════════════════════════════════╣
║  Endpoints:                                                      ║
║    POST /trigger_scan   - Manually trigger a scan                ║
║    GET  /status         - Get service statistics                 ║
║    POST /ml_response    - Submit ML inference result             ║
║                                                                  ║
║  Log Types Generated:                                            ║
║    • static_scan_started/complete                                ║
║    • robot_vision_scan_started/complete                          ║
║    • thread_check_scan_started/complete                          ║
║    • capture_timeout (errors)                                    ║
║    • defect_detected (warnings)                                  ║
║    • plc_communication_error (errors)                            ║
╚══════════════════════════════════════════════════════════════════╝
    """)

    if args.demo:
        run_service_with_demo(args)
    else:
        # Just run the service
        service = MockPLCService(
            plc_id=args.plc_id,
            error_rate=args.error_rate,
            timeout_rate=args.timeout_rate,
            auto_scan_interval=args.scan_interval,
        )

        service.launch(
            host=args.host,
            port=args.port,
            wait_for_launch=True,
            block=True,
            timeout=300,
        )
