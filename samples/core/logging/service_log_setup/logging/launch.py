from mindtrace.services.sample.echo_logging_service import EchoService

if __name__ == "__main__":
    # Run on 0.0.0.0:8080 so it is accessible from host
    EchoService.launch(
        host="0.0.0.0", 
        port=8080, 
        wait_for_launch=True, 
        block=True,
        timeout=100
    )