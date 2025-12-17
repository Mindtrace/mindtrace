import argparse
from samples.agents.monitor_setup.logging.logging_service import LoggingService



if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Logging Service for testing monitoring agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
 
    )
    
    # Service options
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--error-rate", type=float, default=0.1, help="Error rate 0-1 (default: 0.1)")
    parser.add_argument("--timeout-rate", type=float, default=0.05, help="Timeout rate 0-1 (default: 0.05)")
    parser.add_argument("--auto-scan-interval", type=float, default=5.0, help="Auto-scan interval in seconds (default: 5.0)")
   
    args = parser.parse_args()
    service = LoggingService(
        error_rate=args.error_rate,
        timeout_rate=args.timeout_rate,
        auto_scan_interval=args.auto_scan_interval,
    )
    service.launch(
        host=args.host,
        port=args.port,
        wait_for_launch=True,
        block=True,
        timeout=300,
    )
